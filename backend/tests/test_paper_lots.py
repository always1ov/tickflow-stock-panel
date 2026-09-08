"""[fork 增强] R183 模拟盘的批次视图与绩效指标。

守两件事:
  · **批次视图是派生的, 不写进作者的 lots.json** —— 写进去会派生真实监控规则,
    并且经 effective_positions 污染决策台的成本口径(那几列管的是真钱)。
  · **算不出的指标给 None, 绝不用 0 顶替** —— 回撤 0 会被读成"从没回撤过"。
"""
from app.services import paper_lots as pl


def _book(positions=None, navs=None, cap=100000.0):
    return {
        "initial_capital": cap, "cash": cap,
        "positions": positions or {},
        "nav_history": navs or [],
    }


# ---------- 批次视图 ----------

def test_持仓转成批次的字段名与作者批次一致():
    """界面上就是批次表, 字段名不一样的话渲染要写两套。"""
    bk = _book({"600000.SH": {"shares": 500, "cost": 10.5, "opened_on": "2026-09-01"}})
    got = pl.lots_for_book("gpt", "watchlist", bk, {"600000.SH": 11.0})[0]
    assert got["cost_price"] == 10.5
    assert got["qty"] == 500
    assert got["buy_date"] == "2026-09-01"


def test_带上模拟盘特有的盈亏():
    """作者的批次「只生成监控规则, 不做会计」; 模拟盘必须看得见盈亏。"""
    bk = _book({"A": {"shares": 100, "cost": 10.0, "opened_on": "2026-09-01"}})
    got = pl.lots_for_book("t", "watchlist", bk, {"A": 12.0})[0]
    assert got["market_value"] == 1200.0
    assert got["pnl_pct"] == 0.2


def test_没有现价时不编市值():
    bk = _book({"A": {"shares": 100, "cost": 10.0}})
    got = pl.lots_for_book("t", "watchlist", bk, {})[0]
    assert got["market_value"] is None
    assert got["pnl_pct"] is None


def test_已清仓的不进批次表():
    bk = _book({"A": {"shares": 0, "cost": 10.0}})
    assert pl.lots_for_book("t", "watchlist", bk, {}) == []


def test_批次id带上操作员与账本():
    """同一只票在不同操作员/不同账本里是不同批次, id 撞了会互相覆盖。"""
    bk = _book({"A": {"shares": 100, "cost": 10.0}})
    a = pl.lots_for_book("gpt", "watchlist", bk, {})[0]["id"]
    b = pl.lots_for_book("gpt", "market", bk, {})[0]["id"]
    c = pl.lots_for_book("kimi", "watchlist", bk, {})[0]["id"]
    assert len({a, b, c}) == 3


def test_按市值降序():
    bk = _book({
        "SMALL": {"shares": 100, "cost": 1.0},
        "BIG": {"shares": 100, "cost": 1.0},
    })
    got = pl.lots_for_book("t", "watchlist", bk, {"SMALL": 1.0, "BIG": 50.0})
    assert got[0]["symbol"] == "BIG"


def test_不碰作者的lots模块():
    """派生视图不该 import 作者的批次领域层 —— 一旦 import 就有写进去的可能。"""
    import inspect
    src = inspect.getsource(pl)
    assert "strategy import lots" not in src
    assert "strategy.lots" not in src


# ---------- 绩效指标 ----------

def test_样本不足时回撤给None而不是零():
    """0 会被读成"从没回撤过" —— 那是假的。"""
    assert pl._max_drawdown([]) is None
    assert pl._max_drawdown([100.0]) is None


def test_回撤算的是从峰值起的最大跌幅():
    # 100 → 120 → 90: 峰值 120, 谷底 90 → 回撤 25%
    assert pl._max_drawdown([100, 120, 90, 110]) == 0.25


def test_一路上涨没有回撤():
    assert pl._max_drawdown([100, 110, 120]) == 0.0


def test_样本太少不给夏普():
    """5 个点算出来的夏普是噪声, 摆出来只会误导。"""
    assert pl._sharpe([100.0 + i for i in range(5)]) is None


def test_样本够才给夏普():
    navs = [100.0 * (1.001 ** i) for i in range(40)]
    assert pl._sharpe(navs) is not None


def test_没有基准时不编一个():
    """一个没有对照的收益率说明不了任何事, 但编一个基准比没有更糟。"""
    got = pl.metrics_for_book(_book(navs=[{"date": "d1", "nav": 100000}]))
    assert got["benchmark_return"] is None
    assert got["excess_return"] is None


def test_有基准时给超额():
    bk = _book(navs=[{"date": "d1", "nav": 100000, "market_value": 0},
                     {"date": "d2", "nav": 110000, "market_value": 5}])
    got = pl.metrics_for_book(bk, benchmark=[{"date": "d1", "nav": 100},
                                             {"date": "d2", "nav": 105}])
    assert got["total_return"] == 0.1
    assert got["benchmark_return"] == 0.05
    assert abs(got["excess_return"] - 0.05) < 1e-9


def test_曝光度是有持仓的交易日占比():
    """空仓躺着不动跑平也不叫本事 —— 得看它到底下没下场。"""
    bk = _book(navs=[
        {"date": "d1", "nav": 100000, "market_value": 0},
        {"date": "d2", "nav": 100000, "market_value": 5000},
    ])
    assert pl.metrics_for_book(bk)["exposure"] == 0.5


def test_没有净值历史时不崩():
    got = pl.metrics_for_book(_book())
    assert got["days"] == 0
    assert got["max_drawdown"] is None
