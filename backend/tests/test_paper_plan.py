"""[R171] 模拟盘交易计划: 买入即立止盈线/止损线/到期日。

这一组盯三件事:
1. 三条线的算法与「持仓提醒」的批次**同口径**(成本 ± %, 到期按自然日);
2. 纪律分档没跑偏 —— **止损/到期硬执行, 止盈只提醒**;
3. 模型写出离谱参数时**夹到边界而不是丢掉** —— 丢掉等于这笔没有计划,
   反而退回升级前的状态。
"""
from __future__ import annotations

import pytest

from app.services import paper_plan as pp


# ── 推导三条线 ──────────────────────────────────────────────
def test_derive_lines_matches_lots_formula():
    """与批次页同一个算法: 止盈 = 成本×(1+x%), 止损 = 成本×(1−y%)。"""
    plan = pp.derive_plan(10.0, target_pct=20, stop_pct=8, hold_days=30, buy_date="2026-09-01")
    assert plan["target_price"] == pytest.approx(12.0)
    assert plan["stop_price"] == pytest.approx(9.2)
    assert plan["due_date"] == "2026-10-01"          # 自然日, 与批次页到期日同口径
    assert plan["based_on_cost"] == 10.0


def test_partial_plan_is_allowed():
    """只填止损也算计划 —— 批次页也允许三项里只填一项。"""
    plan = pp.derive_plan(10.0, stop_pct=8)
    assert plan["stop_price"] == pytest.approx(9.2)
    assert plan["target_price"] is None
    assert plan["due_date"] is None


def test_no_params_is_no_plan():
    assert pp.derive_plan(10.0) is None


def test_bad_cost_is_no_plan():
    assert pp.derive_plan(0) is None
    assert pp.derive_plan(-1, stop_pct=8) is None
    assert pp.derive_plan("x", stop_pct=8) is None


def test_out_of_range_params_are_clamped_not_dropped():
    """模型偶尔写"止损 0.5%"(一个跳就打掉)或"止盈 500%"(等于没设) ——
    夹到边界比丢掉有用: 丢掉的话这笔就完全没有计划。"""
    plan = pp.derive_plan(10.0, target_pct=500, stop_pct=0.5)
    assert plan["target_pct"] == pp.MAX_TARGET_PCT
    assert plan["stop_pct"] == pp.MIN_STOP_PCT


def test_hold_days_clamped():
    plan = pp.derive_plan(10.0, hold_days=9999, buy_date="2026-09-01")
    assert plan["hold_days"] == int(pp.MAX_HOLD_DAYS)


def test_bad_buy_date_keeps_price_lines():
    """买入日不是日期 → 算不出到期, 但止盈止损照立, 不该整个计划作废。"""
    plan = pp.derive_plan(10.0, target_pct=20, stop_pct=8, hold_days=30, buy_date="不是日期")
    assert plan["due_date"] is None
    assert plan["target_price"] == pytest.approx(12.0)


def test_bool_is_not_a_number():
    """True 在 Python 里是 1, 不挡住会变成"止盈 1%"。"""
    assert pp.derive_plan(10.0, target_pct=True) is None


# ── 触线判定与纪律分档 ──────────────────────────────────────
def _pos(**plan_kw):
    return {"shares": 100, "cost": 10.0, "plan": pp.derive_plan(10.0, **plan_kw)}


def test_stop_is_enforced():
    hit = pp.check_plan(_pos(stop_pct=8), close=9.0, today="2026-09-10")
    assert hit["kind"] == pp.KIND_STOP
    assert hit["enforce"] is True


def test_due_is_enforced():
    hit = pp.check_plan(_pos(hold_days=5, buy_date="2026-09-01"), close=10.5, today="2026-09-06")
    assert hit["kind"] == pp.KIND_DUE
    assert hit["enforce"] is True


def test_target_is_reminder_only():
    """止盈是策略不是纪律 —— 落袋还是让利润奔跑该由模型自己判断。"""
    hit = pp.check_plan(_pos(target_pct=20), close=12.5, today="2026-09-10")
    assert hit["kind"] == pp.KIND_TARGET
    assert hit["enforce"] is False
    assert pp.KIND_TARGET not in pp.ENFORCED


def test_stop_beats_due_on_same_day():
    """同一天既跌破止损又到期, 记止损 —— 那才是这笔亏在哪的真实原因,
    记成"到期"会让出场原因分布失真。"""
    pos = _pos(stop_pct=8, hold_days=5, buy_date="2026-09-01")
    hit = pp.check_plan(pos, close=9.0, today="2026-09-06")
    assert hit["kind"] == pp.KIND_STOP


def test_stop_beats_target():
    """极端行情下同时满足(比如计划本身就写反了), 保命优先。"""
    pos = {"shares": 100, "cost": 10.0,
           "plan": {"stop_price": 12.0, "target_price": 11.0, "based_on_cost": 10.0}}
    assert pp.check_plan(pos, close=11.5, today="2026-09-10")["kind"] == pp.KIND_STOP


def test_untouched_returns_none():
    pos = _pos(target_pct=20, stop_pct=8, hold_days=30, buy_date="2026-09-01")
    assert pp.check_plan(pos, close=10.5, today="2026-09-10") is None


def test_position_without_plan_never_triggers():
    """升级前建的仓没有 plan 字段 —— 必须原样放过, 不能凭空给它安一条线。"""
    assert pp.check_plan({"shares": 100, "cost": 10.0}, close=1.0, today="2026-09-10") is None
    assert pp.check_plan({"shares": 100, "cost": 10.0, "plan": "坏数据"}, 1.0, "2026-09-10") is None


def test_bad_close_returns_none():
    """拿不到价就不判 —— 没价不能凭空成交(与生命线那一路同一个原则)。"""
    pos = _pos(stop_pct=8)
    assert pp.check_plan(pos, close=0, today="2026-09-10") is None
    assert pp.check_plan(pos, close="x", today="2026-09-10") is None


def test_due_needs_today():
    """today 为空时不判到期, 免得空串比较出意外结果。"""
    pos = _pos(hold_days=5, buy_date="2026-09-01")
    assert pp.check_plan(pos, close=10.5, today="") is None


# ── 给 AI 的上下文行 ────────────────────────────────────────
def test_plan_line_is_human_readable():
    pos = _pos(target_pct=20, stop_pct=8, hold_days=30, buy_date="2026-09-01")
    line = pp.plan_line("600000.SH", pos, close=11.0)
    assert "止盈 12.00" in line and "止损 9.20" in line and "到期 2026-10-01" in line
    assert "+9.1%" in line          # 离止盈还有多远, 写成人话而不是塞数字


def test_plan_line_empty_without_plan():
    assert pp.plan_line("600000.SH", {"shares": 100}, close=10.0) == ""
