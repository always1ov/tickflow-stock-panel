"""[R562] 虚拟账户「跟六态转折」—— 纯判定那一半。

一天收盘之后, 给定每只票当天的多空与是否转折、账户的持仓与在途单, 算出今晚该挂
什么单(全部是**次日开盘单**)、该撤什么单、哪些信号放弃了以及为什么。

规则与转折模拟盘(R327)逐条对上, 只有成交时点不同(用户定案: 只按**已确认**的转折
出手, 次日开盘成交 —— R329「一定要根据转折才能出手」):

  · 只在转折日动手; 转多买、转空清仓, 不做空
  · 先卖后买; 等权, 每笔目标 = 当日净值 ÷ N; 仓位满了不顺延
  · 封板/停牌没成交 → 顺延重挂, 方向反了就作废
"""
from __future__ import annotations

from app.services import flip_follow as ff
from app.services.flip_trades import BEAR, BULL

DAY = "2026-09-28"
FEES = {"commission_pct": 0.0002, "stamp_tax_pct": 0.0005, "slippage_bps": 5.0}


def _row(side: str, *, flipped: bool = False, close: float = 10.0) -> dict:
    return {"side": side, "flipped": flipped, "close": close}


def _decide(rows, *, held=None, intents=None, nav=100_000.0, cash=100_000.0, n=2):
    return ff.decide(
        day=DAY, rows=rows, held=held or {}, intents=intents or {},
        nav=nav, cash=cash, max_positions=n, **FEES,
    )


def test_转多买入_按净值除以N_整手():
    plan = _decide({"A": _row(BULL, flipped=True, close=10.0)}, n=2)
    assert plan.sells == []
    [buy] = plan.buys
    assert buy["symbol"] == "A"
    assert buy["since"] == DAY
    # 目标 5 万, 10 元 × 滑点 5bp → 能买 4900 股(5000 股加滑点和佣金超出 5 万)
    assert buy["qty"] == 4900


def test_不转折的日子一动不动():
    plan = _decide({"A": _row(BULL), "B": _row(BEAR)}, held={"B": 1000})
    assert plan.buys == [] and plan.sells == [] and plan.cancels == []


def test_转空清仓_整个持仓():
    plan = _decide({"A": _row(BEAR, flipped=True)}, held={"A": 1300})
    assert plan.sells == [{"symbol": "A", "qty": 1300, "since": DAY}]


def test_转空但没拿着_什么也不做():
    plan = _decide({"A": _row(BEAR, flipped=True)})
    assert plan.sells == [] and plan.skipped == []


def test_转多但已经拿着_不重复买():
    plan = _decide({"A": _row(BULL, flipped=True)}, held={"A": 100})
    assert plan.buys == []


def test_满仓时同一晚先卖后买_卖出的钱和位置都算给买单():
    # 两只满仓, 现金为 0; A 转空、C 转多 —— A 腾出的位置和回款要能让 C 买上
    plan = _decide(
        {"A": _row(BEAR, flipped=True, close=10.0), "B": _row(BULL, close=10.0),
         "C": _row(BULL, flipped=True, close=10.0)},
        held={"A": 5000, "B": 5000}, nav=100_000.0, cash=0.0, n=2,
    )
    assert [s["symbol"] for s in plan.sells] == ["A"]
    [buy] = plan.buys
    assert buy["symbol"] == "C" and buy["qty"] >= 4800


def test_仓位满了不顺延_记一条原因():
    plan = _decide({"A": _row(BULL), "B": _row(BULL), "C": _row(BULL, flipped=True)},
                   held={"A": 100, "B": 100}, n=2)
    assert plan.buys == []
    assert plan.skipped == [{"symbol": "C", "act": "buy", "since": DAY, "reason": ff.WHY_NO_SLOT}]
    assert "C" not in plan.intents


def test_同一晚转多的票超过空位_按代码顺序取_与回放同一条():
    plan = _decide({s: _row(BULL, flipped=True) for s in ("C", "A", "B")}, n=2)
    assert [b["symbol"] for b in plan.buys] == ["A", "B"]
    assert [s["symbol"] for s in plan.skipped] == ["C"]


def test_钱不够一手_记一条原因():
    plan = _decide({"A": _row(BULL, flipped=True, close=100.0)}, nav=5_000.0, cash=5_000.0)
    assert plan.buys == []
    assert plan.skipped[0]["reason"] == ff.WHY_NO_CASH


def test_封板没成交的买单_方向没变就今晚重挂_信号日不变():
    it = {"A": {"act": "buy", "since": "2026-09-25"}}
    plan = _decide({"A": _row(BULL)}, intents=it)
    [buy] = plan.buys
    assert buy["symbol"] == "A" and buy["since"] == "2026-09-25"


def test_封板没卖掉的卖单_方向没变就今晚重挂():
    it = {"A": {"act": "sell", "since": "2026-09-25"}}
    plan = _decide({"A": _row(BEAR)}, held={"A": 700}, intents=it)
    assert plan.sells == [{"symbol": "A", "qty": 700, "since": "2026-09-25"}]


def test_方向反了_在途单撤掉_记作废():
    it = {"A": {"act": "buy", "since": "2026-09-25", "order_id": "o1", "qty": 100, "est": 1000.0}}
    plan = _decide({"A": _row(BEAR, flipped=True)}, intents=it)
    assert plan.cancels == ["A"]
    assert plan.skipped[0]["reason"] == ff.WHY_VOIDED
    assert plan.buys == [] and plan.sells == [] and "A" not in plan.intents


def test_在途单不重复挂_仍然占位置和钱():
    it = {"A": {"act": "buy", "since": DAY, "order_id": "o1", "qty": 4900, "est": 49_100.0}}
    plan = _decide({"A": _row(BULL), "B": _row(BULL, flipped=True), "C": _row(BULL, flipped=True)},
                   intents=it, nav=100_000.0, cash=100_000.0, n=2)
    assert [b["symbol"] for b in plan.buys] == ["B"]
    assert plan.intents["A"]["order_id"] == "o1"
    assert [s["symbol"] for s in plan.skipped] == ["C"]


def test_停牌没行情_信号原样留着():
    it = {"A": {"act": "sell", "since": "2026-09-25"}}
    plan = _decide({}, held={"A": 700}, intents=it)
    assert plan.sells == [] and plan.intents == it
