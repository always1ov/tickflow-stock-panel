"""[fork 增强] AI 一键分组: 输出解析校验 + 落库应用。"""
import sys
import types

import pytest

if "tickflow" not in sys.modules:
    _stub = types.ModuleType("tickflow")
    _stub.AsyncTickFlow = object
    _stub.TickFlow = object
    sys.modules["tickflow"] = _stub

from app.services.watchlist_ai_group import parse_groups  # noqa: E402

VALID = {"600487.SH", "603083.SH", "300502.SZ", "002463.SZ", "688981.SH"}
NAMES = {
    "600487.SH": "亨通光电", "603083.SH": "剑桥科技", "300502.SZ": "新易盛",
    "002463.SZ": "沪电股份", "688981.SH": "中芯国际",
}


def _text(groups):
    import json
    return json.dumps({"groups": groups}, ensure_ascii=False)


def test_basic_grouping():
    g, un = parse_groups(_text([
        {"name": "光模块", "symbols": ["600487.SH", "603083.SH", "300502.SZ"], "reason": "CPO 主线"},
        {"name": "PCB", "symbols": ["002463.SZ", "688981.SH"], "reason": "算力配套"},
    ]), VALID, NAMES)
    assert [x["name"] for x in g] == ["光模块", "PCB"]
    assert g[0]["names"] == ["亨通光电", "剑桥科技", "新易盛"]
    assert un == []


def test_fabricated_symbols_dropped():
    """AI 编造的代码必须被丢弃, 不能污染分组。"""
    g, un = parse_groups(_text([
        {"name": "光模块", "symbols": ["600487.SH", "999999.SZ", "603083.SH"]},
    ]), VALID, NAMES)
    assert g[0]["symbols"] == ["600487.SH", "603083.SH"]
    assert "999999.SZ" not in un, "编造的代码不属于自选, 不该出现在未分组里"


def test_symbol_only_enters_first_group():
    g, _un = parse_groups(_text([
        {"name": "光模块", "symbols": ["600487.SH", "603083.SH"]},
        {"name": "重复组", "symbols": ["600487.SH", "300502.SZ", "002463.SZ"]},
    ]), VALID, NAMES)
    assert g[0]["symbols"] == ["600487.SH", "603083.SH"]
    assert "600487.SH" not in g[1]["symbols"]


def test_single_member_group_rejected_and_returned_to_ungrouped():
    """单只成组没意义 —— 丢弃该组, 且这只票要回到未分组。"""
    g, un = parse_groups(_text([
        {"name": "光模块", "symbols": ["600487.SH", "603083.SH"]},
        {"name": "孤儿", "symbols": ["300502.SZ"]},
    ]), VALID, NAMES)
    assert [x["name"] for x in g] == ["光模块"]
    assert "300502.SZ" in un


def test_uncovered_symbols_reported_as_ungrouped():
    g, un = parse_groups(_text([
        {"name": "光模块", "symbols": ["600487.SH", "603083.SH"]},
    ]), VALID, NAMES)
    assert len(g) == 1
    assert set(un) == {"300502.SZ", "002463.SZ", "688981.SH"}


def test_long_group_name_truncated():
    g, _ = parse_groups(_text([
        {"name": "这是一个特别长的分组名称", "symbols": ["600487.SH", "603083.SH"]},
    ]), VALID, NAMES)
    assert len(g[0]["name"]) == 6


def test_garbage_output_yields_no_groups():
    for bad in ("", None, "今天天气不错", '{"groups": []}'):
        g, un = parse_groups(bad, VALID, NAMES)
        assert g == []
        assert set(un) == VALID


def test_fenced_and_think_wrapped_output_parsed():
    """复用容错解析: 围栏/思考段包裹的输出也要能解析。"""
    body = _text([{"name": "光模块", "symbols": ["600487.SH", "603083.SH"]}])
    for wrapped in (f"```json\n{body}\n```", f"<think>let me group these...</think>{body}"):
        g, _ = parse_groups(wrapped, VALID, NAMES)
        assert [x["name"] for x in g] == ["光模块"]


# ---------- 落库应用 ----------

@pytest.fixture()
def wl(tmp_path, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    from app.services import watchlist
    for s in ("600487.SH", "603083.SH", "300502.SZ"):
        watchlist.add(s)
    return watchlist


def test_apply_creates_groups_and_assigns(wl):
    from app.services.watchlist_ai_group import apply
    r = apply([{"name": "光模块", "symbols": ["600487.SH", "603083.SH"]}])
    assert r["groups_created"] == 1
    assert r["symbols_assigned"] == 2
    gid = {g["name"]: g["id"] for g in wl.list_groups()}["光模块"]
    by_sym = {e["symbol"]: e.get("group_id") for e in wl.list_symbols()}
    assert by_sym["600487.SH"] == gid
    assert by_sym["300502.SZ"] is None, "方案未覆盖的票保持原样"


def test_apply_reuses_existing_group_name(wl):
    from app.services.watchlist_ai_group import apply
    wl.create_group("光模块", "sky")
    r = apply([{"name": "光模块", "symbols": ["600487.SH", "603083.SH"]}])
    assert r["groups_created"] == 0, "同名分组应复用而非重建"
    assert len([g for g in wl.list_groups() if g["name"] == "光模块"]) == 1


def test_apply_replace_existing_clears_first(wl):
    from app.services.watchlist_ai_group import apply
    _gs, old = wl.create_group("旧组", "rose")
    wl.set_group("300502.SZ", old["id"])
    apply([{"name": "光模块", "symbols": ["600487.SH", "603083.SH"]}],
          replace_existing=True)
    by_sym = {e["symbol"]: e.get("group_id") for e in wl.list_symbols()}
    assert by_sym["300502.SZ"] is None, "彻底重分时旧归属应被清空"
