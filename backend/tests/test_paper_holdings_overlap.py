"""[R170] AI 操盘手持仓的**聚合**计数 —— 供「我的批次」表做对照标记。

这一组测试盯的核心是**不泄露**: 只能回"几个操作员持有", 不能带出是谁、成本、理由。
作者在 paper_trader 里明写了界面不做"所有人持仓一览"(看完再去调提示词会破坏操作员
隔离), 聚合计数是这条线上能给的最大信息量, 越界了就违背了那条约束。
"""
from __future__ import annotations

import pytest

from app.config import settings
from app.services import paper_trader as pt


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    return tmp_path


def _trader(tid: str, market: dict, watchlist: dict) -> dict:
    def _book(positions):
        bk = pt.new_book(100000.0)
        bk["positions"] = positions
        return bk
    return {"id": tid, "name": tid, "profile_id": "p",
            "books": {pt.SCOPE_MARKET: _book(market), pt.SCOPE_WATCHLIST: _book(watchlist)}}


def _seed(traders):
    pt._write({"traders": traders})


def test_empty(data_dir):
    _seed([])
    assert pt.holdings_overlap() == ({}, 0)


def test_counts_distinct_traders(data_dir):
    _seed([
        _trader("a", {"600519.SH": {"shares": 100}}, {}),
        _trader("b", {}, {"600519.SH": {"shares": 200}}),
    ])
    counts, total = pt.holdings_overlap()
    assert counts == {"600519.SH": 2}
    assert total == 2


def test_same_trader_two_books_counts_once(data_dir):
    """问的是"几个人也拿着", 不是"几本账" —— 同一个人两本账都有只算一次。"""
    _seed([_trader("a", {"600519.SH": {"shares": 100}}, {"600519.SH": {"shares": 50}})])
    counts, _ = pt.holdings_overlap()
    assert counts == {"600519.SH": 1}


def test_zero_share_positions_are_not_held(data_dir):
    """清完仓但残留 0 股的条目不算持有。"""
    _seed([_trader("a", {"600519.SH": {"shares": 0}}, {})])
    assert pt.holdings_overlap()[0] == {}


def test_symbol_case_normalized(data_dir):
    _seed([_trader("a", {"600519.sh": {"shares": 100}}, {}),
           _trader("b", {"600519.SH": {"shares": 100}}, {})])
    assert pt.holdings_overlap()[0] == {"600519.SH": 2}


def test_leaks_nothing_but_counts(data_dir):
    """返回值里不得出现操作员 id/名字、成本、理由 —— 这是这个接口存在的前提。"""
    _seed([_trader("secret_trader", {"600519.SH": {"shares": 100, "cost": 1500.0}}, {})])
    counts, total = pt.holdings_overlap()
    blob = repr(counts)
    assert "secret_trader" not in blob
    assert "1500" not in blob
    assert counts == {"600519.SH": 1} and total == 1


def test_malformed_books_do_not_raise(data_dir):
    """账本结构坏了不能把对照标记连带弄挂 —— 它只是「我的批次」表上的一个小标。"""
    _seed([{"id": "a", "books": "not-a-dict"},
           {"id": "b", "books": {"market": None}},
           _trader("c", {"600519.SH": {"shares": 10}}, {})])
    assert pt.holdings_overlap() == ({"600519.SH": 1}, 3)
