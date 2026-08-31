"""[fork 增强] R93 — 使用观察笔记的增删改查与并发安全。"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest

from app import config as app_config
from app.services import usage_notes


@pytest.fixture(autouse=True)
def isolated_store(monkeypatch: pytest.MonkeyPatch, tmp_path):
    monkeypatch.setattr(app_config.settings, "data_dir", tmp_path)
    yield


def test_create_list_update_delete_roundtrip():
    note = usage_notes.create_note("异动监控盘中开着最有用")
    assert note["id"].startswith("note_")
    assert note["created_at"] == note["updated_at"]

    items = usage_notes.list_notes()
    assert [n["id"] for n in items] == [note["id"]]

    updated = usage_notes.update_note(note["id"], content="异动监控 + 放量规则一起用")
    assert updated is not None
    assert updated["content"] == "异动监控 + 放量规则一起用"
    assert updated["created_at"] == note["created_at"]

    assert usage_notes.delete_note(note["id"]) is True
    assert usage_notes.list_notes() == []


def test_update_missing_returns_none_and_delete_missing_false():
    assert usage_notes.update_note("note_nope", content="x") is None
    assert usage_notes.delete_note("note_nope") is False


def test_empty_or_oversize_content_rejected():
    with pytest.raises(ValueError):
        usage_notes.create_note("   ")
    with pytest.raises(ValueError):
        usage_notes.create_note("x" * (usage_notes.MAX_CONTENT_CHARS + 1))
    note = usage_notes.create_note("ok")
    with pytest.raises(ValueError):
        usage_notes.update_note(note["id"], content="")
    with pytest.raises(ValueError):
        usage_notes.update_note(note["id"], status="bogus")


def test_list_orders_by_updated_desc():
    a = usage_notes.create_note("第一条")
    b = usage_notes.create_note("第二条")
    usage_notes.update_note(a["id"], content="第一条改过了")
    items = usage_notes.list_notes()
    assert [n["id"] for n in items][0] == a["id"]
    assert {n["id"] for n in items} == {a["id"], b["id"]}


def test_concurrent_creates_do_not_lose_notes():
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda i: usage_notes.create_note(f"note-{i}"), range(24)))
    assert len(usage_notes.list_notes()) == 24


def test_status_and_pin_do_not_touch_updated_at():
    a = usage_notes.create_note("凯特纳贴下轨买入胜率高")
    b = usage_notes.create_note("昨日AI优选明天可能涨")
    # 标状态/置顶不刷新 updated_at, 不该把旧观察顶到最前
    tagged = usage_notes.update_note(a["id"], status="verified")
    assert tagged is not None and tagged["status"] == "verified"
    assert tagged["updated_at"] == a["updated_at"]
    pinned = usage_notes.update_note(a["id"], pinned=True)
    assert pinned is not None and pinned["pinned"] is True
    # 置顶的排最前, 未置顶组内仍按时间降序
    items = usage_notes.list_notes()
    assert [n["id"] for n in items] == [a["id"], b["id"]]


def test_legacy_rows_get_default_fields(tmp_path):
    import json
    from app.services.usage_notes import _path
    _path().parent.mkdir(parents=True, exist_ok=True)
    _path().write_text(json.dumps([
        {"id": "note_old", "content": "老数据", "created_at": "2026-01-01T00:00:00",
         "updated_at": "2026-01-01T00:00:00"},
    ]), encoding="utf-8")
    items = usage_notes.list_notes()
    assert items[0]["status"] == "" and items[0]["pinned"] is False
