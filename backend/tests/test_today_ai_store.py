"""[fork 增强] R27 今日总览 AI 结果缓存 + AI 定时配置。"""
import pytest


@pytest.fixture()
def store(tmp_path, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    from app.services import today_ai_store
    return today_ai_store


def test_empty_when_never_generated(store):
    assert store.load() is None


def test_save_and_load_roundtrip(store):
    entry = store.save(
        {"brief": "盘前保持谨慎。", "picks": [{"symbol": "600487.SH", "reason": "放量突破"}],
         "analyzed": 6},
        as_of="2026-08-19", source="scheduled")
    assert entry["source"] == "scheduled"
    got = store.load()
    assert got["brief"] == "盘前保持谨慎。"
    assert got["picks"][0]["symbol"] == "600487.SH"
    assert got["as_of"] == "2026-08-19"
    assert got["created_at"]


def test_save_overwrites_previous(store):
    store.save({"brief": "旧的", "picks": [], "analyzed": 1}, as_of="2026-08-18")
    store.save({"brief": "新的", "picks": [], "analyzed": 2}, as_of="2026-08-19")
    got = store.load()
    assert got["brief"] == "新的" and got["as_of"] == "2026-08-19"


def test_corrupt_file_returns_none(store):
    store._path().write_text("{ not json", encoding="utf-8")
    assert store.load() is None


# ---------- 定时配置 ----------

@pytest.fixture()
def prefs(tmp_path, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    from app.services import preferences
    return preferences


def test_today_ai_schedule_defaults_off(prefs):
    cfg = prefs.get_today_ai_schedule()
    assert cfg == {"enabled": False, "hour": 18, "minute": 30}


def test_today_ai_schedule_roundtrip_and_clamp(prefs):
    assert prefs.set_today_ai_schedule(True, 20, 15)["enabled"] is True
    assert prefs.get_today_ai_schedule()["hour"] == 20
    assert prefs.set_today_ai_schedule(True, 99, 99)["hour"] == 23


# [R131 → R435 退役] 「个股 AI 信号批量定时」偏好的两条(默认值 / 校验)随 AI 信号整套停用
# 撤了 —— get / set_signal_ai_schedule 已删, 反面由 test_scheduled_ai_jobs.py 钉。
