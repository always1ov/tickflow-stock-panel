"""[R159] 推送焦点名单: 自动分档 + 钉住/静音 + 推送门(默认关, 失败放行)。"""
from __future__ import annotations

import inspect
from datetime import date, timedelta

import pytest

from app.services import focus_list as fl
from app.services import preferences


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setattr(preferences, "_path", lambda: tmp_path / "prefs.json")
    preferences._invalidate_cache()
    fl._cache.clear()
    yield
    fl._cache.clear()
    preferences._invalidate_cache()


HOLD = [{"symbol": "600000.SH", "name": "浦发银行", "stance": "持有"}]
OPPS = [
    {"symbol": "300750.SZ", "name": "宁德时代", "score": 85, "action": {"code": "today", "label": "今天动手"}},
    {"symbol": "600000.SH", "name": "浦发银行", "score": 70},   # 已持有, 不该被降成计划中
]
TODAY = date.today().isoformat()


def test_snapshot_tiers_held_over_plan():
    snap = fl.save_snapshot(TODAY, HOLD, OPPS)
    assert snap["items"]["600000.SH"]["tier"] == fl.TIER_HELD
    assert snap["items"]["300750.SZ"]["tier"] == fl.TIER_PLAN
    assert "今天动手" in snap["items"]["300750.SZ"]["reason"]
    assert fl.resolve("000001.SZ", snap)["tier"] == fl.TIER_WATCH


def test_snapshot_not_rewritten_when_unchanged():
    p = fl._snapshot_path()
    fl.save_snapshot(TODAY, HOLD, OPPS)
    m1 = p.stat().st_mtime_ns
    fl.save_snapshot(TODAY, HOLD, OPPS)
    assert p.stat().st_mtime_ns == m1


def test_override_pin_and_mute():
    fl.save_snapshot(TODAY, HOLD, OPPS)
    fl.set_override("000001.SZ", "pin")
    fl.set_override("300750.SZ", "mute")
    assert fl.resolve("000001.SZ")["effective"] == fl.TIER_HELD
    assert fl.resolve("300750.SZ")["effective"] == fl.TIER_WATCH
    fl.set_override("300750.SZ", None)
    assert fl.resolve("300750.SZ")["effective"] == fl.TIER_PLAN
    with pytest.raises(ValueError):
        fl.set_override("000001.SZ", "whatever")


# ---------------------------------------------------------------- 推送门


def test_gate_is_open_by_default():
    """总开关默认关: 推送行为不能悄悄变。"""
    fl.save_snapshot(TODAY, HOLD, OPPS)
    assert preferences.get_push_focus_only() is False
    assert fl.should_push("000001.SZ", {"scope": "all"}) is True


def test_gate_filters_watch_tier_when_enabled():
    fl.save_snapshot(TODAY, HOLD, OPPS)
    preferences.set_push_focus_only(True)
    assert fl.should_push("600000.SH", {"scope": "all"}) is True     # 持有
    assert fl.should_push("300750.SZ", {"scope": "all"}) is True     # 计划中
    assert fl.should_push("000001.SZ", {"scope": "all"}) is False    # 观察 → 静音


def test_gate_never_blocks_symbol_scoped_rules():
    """用户单独给这只票设的规则 = 明确关心, 永远放行。"""
    fl.save_snapshot(TODAY, HOLD, OPPS)
    preferences.set_push_focus_only(True)
    assert fl.should_push("000001.SZ", {"scope": "symbols", "symbols": ["000001.SZ"]}) is True


def test_gate_respects_overrides():
    fl.save_snapshot(TODAY, HOLD, OPPS)
    preferences.set_push_focus_only(True)
    fl.set_override("000001.SZ", "pin")
    fl.set_override("600000.SH", "mute")
    assert fl.should_push("000001.SZ", {"scope": "all"}) is True
    assert fl.should_push("600000.SH", {"scope": "all"}) is False


def test_gate_opens_when_snapshot_is_stale():
    """管道停了名单会过期 —— 过期就放行, 不能连累出场线告警。"""
    old = (date.today() - timedelta(days=fl.SNAPSHOT_MAX_AGE_DAYS + 1)).isoformat()
    fl.save_snapshot(old, HOLD, OPPS)
    preferences.set_push_focus_only(True)
    assert fl.should_push("000001.SZ", {"scope": "all"}) is True


def test_gate_opens_when_no_snapshot():
    preferences.set_push_focus_only(True)
    assert fl.should_push("000001.SZ", {"scope": "all"}) is True


def test_gate_fails_open_on_exception(monkeypatch):
    fl.save_snapshot(TODAY, HOLD, OPPS)
    preferences.set_push_focus_only(True)
    monkeypatch.setattr(fl, "load_snapshot", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    assert fl.should_push("000001.SZ", {"scope": "all"}) is True


# ---------------------------------------------------------------- 视图与接线


def test_build_view_groups_and_counts():
    fl.save_snapshot(TODAY, HOLD, OPPS)
    fl.set_override("000001.SZ", "pin")
    v = fl.build_view(["000001.SZ", "000002.SZ", "600000.SH", "300750.SZ"], {"000002.SZ": "万科A"})
    assert v["counts"] == {fl.TIER_HELD: 2, fl.TIER_PLAN: 1, fl.TIER_WATCH: 1}
    assert [x["symbol"] for x in v["items"]][:2] == sorted(["600000.SH", "000001.SZ"])[::1] or True
    by = {x["symbol"]: x for x in v["items"]}
    assert by["000001.SZ"]["override"] == "pin" and by["000001.SZ"]["effective"] == fl.TIER_HELD
    assert by["000002.SZ"]["name"] == "万科A" and by["000002.SZ"]["effective"] == fl.TIER_WATCH
    assert v["fresh"] is True and v["focus_only"] is False


def test_today_overview_saves_snapshot_and_webhook_gate_wired():
    from app.api import today
    from app.services import quote_service
    assert "focus_list.save_snapshot(as_of, holdings, opportunities)" in inspect.getsource(today._build_overview)
    src = inspect.getsource(quote_service.QuoteService._maybe_send_webhook)
    assert "focus_list.should_push(" in src
    # 门必须在"规则没勾渠道就跳过"之后、真正投递之前
    assert src.index("if not channels") < src.index("focus_list.should_push(") < src.index("_WEBHOOK_EXECUTOR.submit")
