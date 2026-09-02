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


def test_gate_is_on_by_default_since_r160():
    """[R160] 用户明确要"真的聚焦" → 默认开。关掉即回到全推。"""
    fl.save_snapshot(TODAY, HOLD, OPPS)
    assert preferences.get_push_focus_only() is True
    assert fl.should_push("000001.SZ", {"scope": "all"}) is False
    preferences.set_push_focus_only(False)
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
    assert v["counts"] == {fl.TIER_HELD: 2, fl.TIER_PLAN: 1, fl.TIER_BAND: 0, fl.TIER_WATCH: 1}
    # 排序: 持有档在前(钉住的算持有档待遇), 观察档垫底
    assert {x["symbol"] for x in v["items"][:2]} == {"600000.SH", "000001.SZ"}
    assert v["items"][-1]["symbol"] == "000002.SZ"
    by = {x["symbol"]: x for x in v["items"]}
    assert by["000001.SZ"]["override"] == "pin" and by["000001.SZ"]["effective"] == fl.TIER_HELD
    assert by["000002.SZ"]["name"] == "万科A" and by["000002.SZ"]["effective"] == fl.TIER_WATCH
    assert v["fresh"] is True and v["focus_only"] is True   # [R160] 默认开


# ---------------------------------------------------------------- [R161] 短期贴/破上下轨进焦点


def _bands(pos: str, pct: float) -> dict:
    return {"s": {"pos": pos, "pos_cn": {"above": "破上轨", "near_upper": "贴上轨", "inside": "通道内",
                                          "near_lower": "贴下轨", "below": "破下轨"}[pos], "pct": pct}}


def test_band_tier_from_keltner_short_position():
    """用户: 「我经常关注 Keltner 短期处于上轨和下轨状态的票」—— 贴/破上下轨进焦点, 通道内不进。"""
    snap = fl.save_snapshot(TODAY, HOLD, OPPS, {
        "000001.SZ": _bands("near_upper", 0.92),
        "000002.SZ": _bands("below", -0.05),
        "000003.SZ": _bands("inside", 0.55),
    })
    assert snap["items"]["000001.SZ"]["tier"] == fl.TIER_BAND
    assert "贴上轨" in snap["items"]["000001.SZ"]["reason"] and "92%" in snap["items"]["000001.SZ"]["reason"]
    assert snap["items"]["000002.SZ"]["tier"] == fl.TIER_BAND
    assert "000003.SZ" not in snap["items"]


def test_band_does_not_override_held_or_plan():
    snap = fl.save_snapshot(TODAY, HOLD, OPPS, {
        "600000.SH": _bands("above", 1.1),     # 持有
        "300750.SZ": _bands("near_lower", 0.1),  # 计划中
    })
    assert snap["items"]["600000.SH"]["tier"] == fl.TIER_HELD
    assert snap["items"]["300750.SZ"]["tier"] == fl.TIER_PLAN


def test_band_tier_passes_the_gate():
    fl.save_snapshot(TODAY, HOLD, OPPS, {"000001.SZ": _bands("near_lower", 0.08)})
    preferences.set_push_focus_only(True)
    assert fl.should_push("000001.SZ", {"scope": "all"}) is True
    assert fl.should_push("000009.SZ", {"scope": "all"}) is False


def test_band_uses_keltner_vocabulary_not_its_own_threshold():
    """到轨判定只认 keltner.classify 的五档, 本模块不另立百分比阈值。"""
    from app.indicators import keltner
    assert fl._BAND_POS == {keltner.POS_ABOVE, keltner.POS_NEAR_UPPER, keltner.POS_NEAR_LOWER, keltner.POS_BELOW}


# ---------------------------------------------------------------- [R160] 所有打扰通道认同一个章


def test_r160_stamp_is_set_before_persist_and_read_by_every_outlet():
    """焦点章在评估处盖一次, 落盘 / SSE / 系统通知 / Webhook 都只认章。"""
    from app.services import quote_service
    src = inspect.getsource(quote_service.QuoteService)
    stamp = src.index('ev["focus_muted"] = not focus_list.should_push(')
    persist = src.index("alert_store.append_many(")
    assert stamp < persist, "章必须在落盘之前盖, 触发记录才带得上它"
    assert '"focus_muted": bool(ev.get("focus_muted"))' in src, "SSE 告警要带章"
    sysn = inspect.getsource(quote_service.QuoteService._maybe_send_system_notifications)
    assert 'if ev.get("focus_muted")' in sysn, "系统通知要认章"
    hook = inspect.getsource(quote_service.QuoteService._maybe_send_webhook)
    assert 'if ev.get("focus_muted")' in hook, "Webhook 要认章"


def test_r160_alerts_api_focus_filter(tmp_path, monkeypatch):
    """/api/alerts?focus=1: 去掉盖了章的, total 也按过滤后算 —— 侧栏徽标靠这个。"""
    import time as _t
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api import alerts as alerts_api
    from app.services import alert_store

    class _Store:
        data_dir = tmp_path

    class _Repo:
        store = _Store()

    now_ms = int(_t.time() * 1000)
    alert_store.append_many(tmp_path, [
        {"ts": now_ms - 3, "source": "signal", "type": "x", "symbol": "000001.SZ", "message": "焦点外", "focus_muted": True},
        {"ts": now_ms - 2, "source": "signal", "type": "x", "symbol": "600000.SH", "message": "焦点内", "focus_muted": False},
        {"ts": now_ms - 1, "source": "signal", "type": "x", "symbol": "300750.SZ", "message": "老记录没章"},
    ])
    app = FastAPI()
    app.state.repo = _Repo()
    app.include_router(alerts_api.router)
    c = TestClient(app)

    everything = c.get("/api/alerts").json()
    assert everything["total"] == 3 and len(everything["alerts"]) == 3

    focus = c.get("/api/alerts", params={"focus": 1, "limit": 1}).json()
    assert focus["total"] == 2, "没章的老记录算焦点内(不能因为旧数据没章就藏起来)"
    assert len(focus["alerts"]) == 1
    assert all(not a.get("focus_muted") for a in focus["alerts"])


def test_today_overview_saves_snapshot_and_webhook_gate_wired():
    from app.api import today
    from app.services import quote_service
    assert "focus_list.save_snapshot(as_of, holdings, opportunities, bands_map)" in inspect.getsource(today._build_overview)
    src = inspect.getsource(quote_service.QuoteService._maybe_send_webhook)
    assert "focus_list.should_push(" in src
    # 门必须在"规则没勾渠道就跳过"之后、真正投递之前
    assert src.index("if not channels") < src.index("focus_list.should_push(") < src.index("_WEBHOOK_EXECUTOR.submit")
