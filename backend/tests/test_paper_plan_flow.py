"""[R171] 交易计划走通整条链: 下单落计划 → 纪律检查 → 出场归因统计。

test_paper_plan.py 盯的是纯算法; 这一组盯的是**接进账本之后行为对不对** ——
尤其是「升级不能改掉老账本的行为」这条: 没有 plan 的老持仓必须原样运作。
"""
from __future__ import annotations

import pytest

from app.services import paper_plan as pp
from app.services import paper_trader as pt
from app.services import paper_trader_run as run


class _Repo:
    """只需要给出收盘价 —— check_plans 走的是收盘口径。"""
    def __init__(self, prices):
        self.prices = prices


@pytest.fixture
def patched(monkeypatch):
    """把 check_plans 依赖的两个外部读盘换掉, 只留纪律逻辑本身。"""
    holder = {"prices": {}, "as_of": "2026-09-10"}
    monkeypatch.setattr(run, "latest_prices", lambda repo, syms: dict(holder["prices"]))
    monkeypatch.setattr(run, "_overview", lambda repo: {"as_of": holder["as_of"]})
    saved: list = []
    monkeypatch.setattr(pt, "save", lambda t: saved.append(t))
    return holder


def _trader(book):
    return {"id": "t1", "name": "t1", "profile_id": "p",
            "books": {pt.SCOPE_MARKET: book, pt.SCOPE_WATCHLIST: pt.new_book(100000.0)}}


def _bought(target=20, stop=8, hold=30, day="2026-09-01", price=10.0, cash=100000.0):
    bk = pt.new_book(cash)
    pt.apply_order(bk, action=pt.ACTION_BUY, symbol="600000.SH", shares=1000,
                   price=price, trade_date=day, reason="建仓",
                   plan={"target_pct": target, "stop_pct": stop, "hold_days": hold})
    return bk


# ── 下单即立计划 ────────────────────────────────────────────
def test_buy_stores_plan_on_position():
    bk = _bought()
    plan = bk["positions"]["600000.SH"]["plan"]
    # 成交价含滑点, 所以线按**实际成本**立而不是按报价
    cost = bk["positions"]["600000.SH"]["cost"]
    assert plan["target_price"] == pytest.approx(round(cost * 1.20, 3))
    assert plan["stop_price"] == pytest.approx(round(cost * 0.92, 3))
    assert plan["due_date"] == "2026-10-01"


def test_buy_without_plan_leaves_position_planless():
    """模型没给参数就是这一笔没立计划 —— 退回升级前的行为, 不该凭空造一条线。"""
    bk = pt.new_book(100000.0)
    pt.apply_order(bk, action=pt.ACTION_BUY, symbol="600000.SH", shares=1000,
                   price=10.0, trade_date="2026-09-01", reason="建仓")
    assert "plan" not in bk["positions"]["600000.SH"]


def test_add_position_recomputes_lines_on_new_cost():
    """加仓后成本变了, 三条线必须跟着动 —— 挂着旧线的话它就不再是「成本±x%」。"""
    bk = _bought()
    old = bk["positions"]["600000.SH"]["plan"]["stop_price"]
    pt.apply_order(bk, action=pt.ACTION_BUY, symbol="600000.SH", shares=1000,
                   price=12.0, trade_date="2026-09-05", reason="加仓")
    pos = bk["positions"]["600000.SH"]
    assert pos["plan"]["stop_price"] > old                     # 成本抬高 → 止损线跟着抬
    assert pos["plan"]["stop_price"] == pytest.approx(round(pos["cost"] * 0.92, 3))


def test_add_position_keeps_original_due_date():
    """到期日锚在**第一次**买入那天 —— 否则每加一次仓就把期限往后推, 期限就成了空话。"""
    bk = _bought()
    pt.apply_order(bk, action=pt.ACTION_BUY, symbol="600000.SH", shares=1000,
                   price=12.0, trade_date="2026-09-05", reason="加仓")
    assert bk["positions"]["600000.SH"]["plan"]["due_date"] == "2026-10-01"


def test_add_position_without_params_keeps_discipline():
    """加仓不带参数不该把已有的纪律抹掉。"""
    bk = _bought()
    pt.apply_order(bk, action=pt.ACTION_BUY, symbol="600000.SH", shares=1000,
                   price=12.0, trade_date="2026-09-05", reason="加仓")
    assert bk["positions"]["600000.SH"]["plan"]["stop_pct"] == 8


# ── 纪律检查 ────────────────────────────────────────────────
def test_stop_is_sold_without_asking_ai(patched):
    bk = _bought()
    cost = bk["positions"]["600000.SH"]["cost"]
    patched["prices"] = {"600000.SH": cost * 0.90}       # 跌破止损
    res = run.check_plans(_Repo({}), _trader(bk), pt.SCOPE_MARKET)
    assert len(res["forced"]) == 1
    assert res["forced"][0]["exit_reason"] == pt.EXIT_STOP
    assert "600000.SH" not in bk["positions"]


def test_due_is_sold_without_asking_ai(patched):
    bk = _bought()
    patched["prices"] = {"600000.SH": 11.0}
    patched["as_of"] = "2026-10-01"                      # 到期日当天
    res = run.check_plans(_Repo({}), _trader(bk), pt.SCOPE_MARKET)
    assert res["forced"][0]["exit_reason"] == pt.EXIT_DUE


def test_target_only_reminds_never_sells(patched):
    """止盈是策略不是纪律 —— 系统绝不替它卖。"""
    bk = _bought()
    cost = bk["positions"]["600000.SH"]["cost"]
    patched["prices"] = {"600000.SH": cost * 1.30}       # 远超止盈线
    res = run.check_plans(_Repo({}), _trader(bk), pt.SCOPE_MARKET)
    assert res["forced"] == []
    assert res["reminders"][0]["kind"] == pp.KIND_TARGET
    assert bk["positions"]["600000.SH"]["shares"] == 1000   # 仓一股没动


def test_reminder_is_persisted_for_next_context(patched):
    """止盈只提醒 —— 提醒必须落在账上, 否则下一轮模型看不见, 等于没提醒。"""
    bk = _bought()
    patched["prices"] = {"600000.SH": bk["positions"]["600000.SH"]["cost"] * 1.30}
    run.check_plans(_Repo({}), _trader(bk), pt.SCOPE_MARKET)
    assert bk["plan_reminders"][0]["symbol"] == "600000.SH"


def test_planless_position_is_untouched(patched):
    """升级前建的仓没有 plan —— 跌到地板也不该被这一路碰。"""
    bk = pt.new_book(100000.0)
    pt.apply_order(bk, action=pt.ACTION_BUY, symbol="600000.SH", shares=1000,
                   price=10.0, trade_date="2026-09-01", reason="建仓")
    patched["prices"] = {"600000.SH": 1.0}
    res = run.check_plans(_Repo({}), _trader(bk), pt.SCOPE_MARKET)
    assert res["forced"] == [] and res["reminders"] == []
    assert bk["positions"]["600000.SH"]["shares"] == 1000


def test_missing_price_is_skipped(patched):
    """拿不到价就不判 —— 没价不能凭空成交(与生命线那一路同一个原则)。"""
    bk = _bought()
    patched["prices"] = {}
    res = run.check_plans(_Repo({}), _trader(bk), pt.SCOPE_MARKET)
    assert res["forced"] == []
    assert bk["positions"]["600000.SH"]["shares"] == 1000


def test_t1_blocks_same_day_stop(patched):
    """当天买当天触止损: T+1 挡住, 记一条拒单留痕, 明天再触发一次。"""
    bk = _bought(day="2026-09-10")
    patched["prices"] = {"600000.SH": bk["positions"]["600000.SH"]["cost"] * 0.90}
    patched["as_of"] = "2026-09-10"
    res = run.check_plans(_Repo({}), _trader(bk), pt.SCOPE_MARKET)
    assert res["forced"][0]["rejected"]
    assert bk["positions"]["600000.SH"]["shares"] == 1000


def test_empty_book_is_noop(patched):
    assert run.check_plans(_Repo({}), _trader(pt.new_book(100000.0)), pt.SCOPE_MARKET) == {
        "forced": [], "reminders": []}


# ── 出场归因统计 ────────────────────────────────────────────
def test_exit_stats_splits_by_reason(patched):
    bk = _bought()
    cost = bk["positions"]["600000.SH"]["cost"]
    patched["prices"] = {"600000.SH": cost * 0.90}
    run.check_plans(_Repo({}), _trader(bk), pt.SCOPE_MARKET)
    st = pt.exit_stats(bk)
    assert st["counts"][pt.EXIT_STOP] == 1
    assert st["closed"] == 1
    assert st["win_rate"] == 0.0            # 止损按定义不算计划兑现


def test_exit_stats_counts_ai_sell_as_default():
    """模型自己决定卖的没传 exit_reason —— 归到"主动卖", 不该留空。"""
    bk = _bought()
    pt.apply_order(bk, action=pt.ACTION_SELL, symbol="600000.SH", shares=1000,
                   price=12.0, trade_date="2026-09-05", reason="它自己想走")
    st = pt.exit_stats(bk)
    assert st["counts"][pt.EXIT_AI] == 1
    assert st["win_rate"] == 1.0            # 12 > 成本, 赚钱出场

def test_exit_stats_ignores_rejected_orders():
    """拒单不是出场 —— 混进来会把分布和胜率都算错。"""
    bk = _bought()
    pt.apply_order(bk, action=pt.ACTION_SELL, symbol="600000.SH", shares=1000,
                   price=12.0, trade_date="2026-09-01", reason="当天买当天卖")  # T+1 拒
    assert pt.exit_stats(bk)["closed"] == 0


def test_sell_records_realized_pnl():
    bk = _bought()
    cost = bk["positions"]["600000.SH"]["cost"]
    e = pt.apply_order(bk, action=pt.ACTION_SELL, symbol="600000.SH", shares=1000,
                       price=12.0, trade_date="2026-09-05", reason="走")
    assert e["cost"] == pytest.approx(round(cost, 4))
    assert e["pnl_pct"] == pytest.approx(round(e["price"] / cost - 1, 4))
