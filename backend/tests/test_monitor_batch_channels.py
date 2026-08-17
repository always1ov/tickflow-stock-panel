"""[fork 增强] 监控规则批量设置推送渠道。"""
import pytest

from app.strategy import monitor_rules


def _rule(rid, channels=None):
    return monitor_rules.normalize({
        "id": rid, "name": f"规则{rid}", "type": "price", "scope": "symbols",
        "symbols": ["000001.SZ"],
        "conditions": [{"field": "close", "op": ">=", "value": 10.0}],
        "webhook_channels": channels or [],
    })


@pytest.fixture()
def store(tmp_path):
    for rid, ch in (("r1", []), ("r2", ["feishu"]), ("r3", ["dingtalk"])):
        monitor_rules.save_one(tmp_path, _rule(rid, ch))
    return tmp_path


def _channels(store):
    return {r["id"]: sorted(r.get("webhook_channels") or [])
            for r in monitor_rules.load_all(store)}


def test_add_appends_without_duplicates(store):
    updated = monitor_rules.batch_set_channels(store, None, ["dingtalk"], "add")
    assert updated == 2, "r3 已有钉钉不重写"
    assert _channels(store) == {"r1": ["dingtalk"], "r2": ["dingtalk", "feishu"],
                                "r3": ["dingtalk"]}


def test_set_replaces_everything(store):
    monitor_rules.batch_set_channels(store, None, ["wecom"], "set")
    assert _channels(store) == {"r1": ["wecom"], "r2": ["wecom"], "r3": ["wecom"]}


def test_set_empty_clears_external_channels(store):
    monitor_rules.batch_set_channels(store, None, [], "set")
    assert _channels(store) == {"r1": [], "r2": [], "r3": []}


def test_remove_only_removes_selected(store):
    updated = monitor_rules.batch_set_channels(store, None, ["feishu"], "remove")
    assert updated == 1
    assert _channels(store)["r2"] == []
    assert _channels(store)["r3"] == ["dingtalk"]


def test_scoped_to_given_rule_ids(store):
    updated = monitor_rules.batch_set_channels(store, ["r1"], ["dingtalk"], "add")
    assert updated == 1
    ch = _channels(store)
    assert ch["r1"] == ["dingtalk"]
    assert ch["r2"] == ["feishu"], "未指定的规则不动"
