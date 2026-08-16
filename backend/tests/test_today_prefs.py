"""[fork 增强] 今日总览偏好: 机会区门槛的读写与边界。"""
import json

import pytest

from app.api.today import rank_opportunities


@pytest.fixture()
def prefs(tmp_path, monkeypatch):
    from app.config import settings
    from app.services import today_prefs
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    return today_prefs


def test_defaults_when_unset(prefs):
    assert prefs.load() == prefs.DEFAULTS


def test_save_and_reload_roundtrip(prefs):
    saved = prefs.save(min_score=75, max_show=5, max_single=30, target_vol=4, max_drawdown=8)
    expect = {"min_score": 75, "max_show": 5, "max_single": 30,
              "target_vol": 4, "max_drawdown": 8}
    assert expect.items() <= saved.items()  # 子集断言: 未传字段保持默认即可
    assert prefs.load() == saved


def test_partial_update_keeps_other_field(prefs):
    prefs.save(min_score=75, max_show=5, max_single=30)
    after = prefs.save(min_score=40)
    assert after["min_score"] == 40
    assert after["max_show"] == 5
    assert after["max_single"] == 30


def test_values_are_clamped_to_valid_range(prefs):
    up = prefs.save(min_score=999, max_show=999, max_single=999, target_vol=999,
                    max_drawdown=999, pyramid_probe=999, pyramid_confirm=999,
                    pyramid_days=999)
    assert {"min_score": 100, "max_show": 50, "max_single": 100, "target_vol": 10,
            "max_drawdown": 30, "pyramid_probe": 60, "pyramid_confirm": 90,
            "pyramid_days": 5}.items() <= up.items()
    dn = prefs.save(min_score=-50, max_show=0, max_single=1, target_vol=0,
                    max_drawdown=1, pyramid_probe=1, pyramid_confirm=1, pyramid_days=0)
    assert {"min_score": 0, "max_show": 1, "max_single": 5, "target_vol": 1,
            "max_drawdown": 3, "pyramid_probe": 10, "pyramid_confirm": 40,
            "pyramid_days": 1}.items() <= dn.items()


def test_corrupt_file_falls_back_to_defaults(prefs):
    p = prefs._store_path()
    p.write_text("{ not json", encoding="utf-8")
    assert prefs.load() == prefs.DEFAULTS


def test_garbage_values_fall_back_per_field(prefs):
    prefs._store_path().write_text(
        json.dumps({"min_score": "高一点", "max_show": 7}), encoding="utf-8")
    loaded = prefs.load()
    assert loaded["min_score"] == prefs.DEFAULTS["min_score"]
    assert loaded["max_show"] == 7
    assert loaded["max_single"] == prefs.DEFAULTS["max_single"]


def _trend(duration):
    return {"signal": "转多", "signal_desc": "突破上关键点 10.0",
            "duration": duration, "close": 10.0, "side": "多头"}


def test_threshold_actually_changes_what_is_shown():
    """同一批候选, 门槛调高后显示变少 —— 门槛是真的生效的。"""
    names = {f"S{i}": f"票{i}" for i in range(6)}
    trends = {s: _trend(1 + i) for i, s in enumerate(names)}
    loose, loose_filtered = rank_opportunities(trends, {}, names, min_score=0, max_show=50)
    strict, strict_filtered = rank_opportunities(trends, {}, names, min_score=80, max_show=50)
    assert len(strict) < len(loose)
    assert strict_filtered > loose_filtered
    assert all(o["score"] >= 80 for o in strict)


def test_max_show_caps_list():
    names = {f"S{i}": f"票{i}" for i in range(8)}
    trends = {s: _trend(1) for s in names}
    shown, filtered = rank_opportunities(trends, {}, names, min_score=0, max_show=3)
    assert len(shown) == 3
    assert filtered == 5
