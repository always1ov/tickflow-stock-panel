"""[fork 增强 R171] 模拟盘的交易计划 —— 买入即立止盈线 / 止损线 / 到期日。

## 借鉴自「持仓提醒」的批次

批次那边: 记一笔买入 → 按成本价 ± 止盈/止损% 生成价格监控; 填了到期日就生成
到期提醒。**只生成提醒, 不做记账** —— 因为那是真钱, 由人拍板。

模拟盘这边没有人, 所以「提醒发给谁」得先定清楚。答案是分两档:

| 触线 | 怎么处理 | 为什么 |
| --- | --- | --- |
| **止损** | **硬执行**, 不问 AI | 保命的事不该给模型「再看看」的机会 —— 和生命线(R61)同一条道理 |
| **到期** | **硬执行**, 不问 AI | 「最长持有 N 天」是买入时自己立的期限; 到了还能续, 那期限就是空话 |
| **止盈** | **只提醒**, 写进下一轮上下文 | 落袋还是让利润奔跑, 那是**策略**不是纪律, 该由模型自己判断 |

## 这解决了什么

升级前, 模型每天重新自由决定买卖, 唯一机械的只有生命线。它下单时不必说自己
打算持有多久、赚多少走、亏多少认 —— 于是复盘时**没法回答「它的计划靠不靠谱」**。
立了计划之后, 每笔出场都能归到「止盈 / 止损 / 到期 / 生命线 / 主动卖」里的一类,
一段时间下来就能看出这个模型是不是只会画大饼。

## 边界

本模块**纯函数, 不碰 I/O, 不碰账本** —— 只负责「成本价 + 计划 → 三条线」与
「持仓 + 今日价 → 触了哪条线」。真正的成交在 paper_trader_run 里做。
"""
from __future__ import annotations

from datetime import date as _date
from datetime import timedelta

# 计划参数的合理区间。越界不是报错而是**夹到边界** —— 模型偶尔会写出
# "止损 0.5%"(一个跳就打掉)或"止盈 500%"(等于没设)这种数, 夹住比丢掉更有用:
# 丢掉的话这笔就完全没有计划, 反而退回升级前的状态。
MIN_TARGET_PCT = 2.0
MAX_TARGET_PCT = 100.0
MIN_STOP_PCT = 2.0
MAX_STOP_PCT = 30.0
MIN_HOLD_DAYS = 1
MAX_HOLD_DAYS = 250

# [R264] 这里原先立着 `TARGET_NAG_LIMIT = 3`(「止盈提醒连刷三轮之后不再进上下文」),
# 常量和注释都在, 限流逻辑从来没写。R262 普查时把它报出来待定, 结论是**不接, 删掉** ——
# 三条理由, 记下来免得以后又有人觉得是漏掉的:
#
# ① **在趋势系统里这条限流是说反了。** 一只票连着二十天挂在止盈线上方, 那正是主升浪,
#    是最该让模型每天都清楚知道"这只在赚钱、纪律没要求你走"的一只。按轮次静音, 等于对
#    最该拿住的票减少信息 —— 与「减少买卖次数, 趋势为王」相悖。
# ② **它想省的东西不存在。** 一只触线一行, 比候选清单小两个数量级。
# ③ **接上的代价远大于收益。** 得往账本存按标的的连续轮次计数, 还要定清归零规则
#    (掉回线下? 加仓改了成本因而改了止盈线? 清仓又买回?); 且不能在 `check_plans` 里砍,
#    砍了前端那个「已到止盈线(N 只)」也会跟着消失, 人是要一直看见的。
#
# 现状(每轮全量重摆, 不随轮次衰减)由 test_paper_plan_flow 里的守卫钉着。

KIND_STOP = "stop"
KIND_DUE = "due"
KIND_TARGET = "target"

#: 硬执行的两类。止盈不在其中 —— 见模块开头那张表。
ENFORCED = frozenset({KIND_STOP, KIND_DUE})

def _clamp(v, lo: float, hi: float) -> float | None:
    """夹到区间; 不是数或 <=0 视为「没填」返回 None。"""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    f = float(v)
    if f <= 0:
        return None
    return max(lo, min(hi, f))


def derive_plan(cost: float, *, target_pct=None, stop_pct=None,
                hold_days=None, buy_date: str = "") -> dict | None:
    """成本价 + 计划参数 → {止盈线, 止损线, 到期日}。三项全空返回 None。

    与批次页一模一样的算法: 止盈线 = 成本 ×(1+止盈%), 止损线 = 成本 ×(1−止损%),
    到期日 = 买入日 + 最长持有天数(**自然日**, 与批次页的到期日同口径)。
    """
    try:
        c = float(cost)
    except (TypeError, ValueError):
        return None
    if c <= 0:
        return None

    tp = _clamp(target_pct, MIN_TARGET_PCT, MAX_TARGET_PCT)
    sp = _clamp(stop_pct, MIN_STOP_PCT, MAX_STOP_PCT)
    hd = _clamp(hold_days, MIN_HOLD_DAYS, MAX_HOLD_DAYS)
    hd = int(hd) if hd is not None else None

    due = None
    if hd is not None and buy_date:
        try:
            due = (_date.fromisoformat(buy_date) + timedelta(days=hd)).isoformat()
        except ValueError:
            due = None          # 买入日不是日期就没法算到期, 但止盈止损照样立

    if tp is None and sp is None and due is None:
        return None
    return {
        "target_pct": tp,
        "stop_pct": sp,
        "hold_days": hd,
        "target_price": round(c * (1 + tp / 100), 3) if tp is not None else None,
        "stop_price": round(c * (1 - sp / 100), 3) if sp is not None else None,
        "due_date": due,
        "based_on_cost": round(c, 3),
    }


def check_plan(pos: dict, close: float, today: str) -> dict | None:
    """持仓 + 今日收盘价 → 触了哪条线。没触返回 None。

    优先级 **止损 > 到期 > 止盈**: 同一天既跌破止损又到期, 记成止损 ——
    那才是这笔亏在哪的真实原因; 记成"到期"会让复盘时的出场原因分布失真。
    """
    plan = pos.get("plan")
    if not isinstance(plan, dict):
        return None
    try:
        px = float(close)
    except (TypeError, ValueError):
        return None
    if px <= 0:
        return None

    stop = plan.get("stop_price")
    if isinstance(stop, (int, float)) and px <= float(stop):
        return {
            "kind": KIND_STOP, "enforce": True, "price": px, "line": float(stop),
            "reason": f"触止损线 —— 收盘 {px:.2f} ≤ 止损 {float(stop):.2f}"
                      f"(成本 {plan.get('based_on_cost')} − {plan.get('stop_pct')}%)",
        }

    due = plan.get("due_date")
    if due and today and str(today) >= str(due):
        return {
            "kind": KIND_DUE, "enforce": True, "price": px, "line": None,
            "reason": f"到期 —— 买入时定的最长持有 {plan.get('hold_days')} 天已满({due})",
        }

    target = plan.get("target_price")
    if isinstance(target, (int, float)) and px >= float(target):
        return {
            "kind": KIND_TARGET, "enforce": False, "price": px, "line": float(target),
            "reason": f"已到止盈线 {float(target):.2f}(成本 +{plan.get('target_pct')}%)"
                      f", 收盘 {px:.2f} —— 走不走你自己定",
        }
    return None


def plan_line(sym: str, pos: dict, close: float | None) -> str:
    """给 AI 上下文用的一行说明。没有计划时返回空串。

    写成人话而不是塞 JSON: 模型读"离止损还有 3.2%"比读一串数字更容易用对。
    """
    plan = pos.get("plan")
    if not isinstance(plan, dict):
        return ""
    parts: list[str] = []
    tp, sp = plan.get("target_price"), plan.get("stop_price")
    if tp:
        gap = f", 差 {(float(tp) / close - 1) * 100:+.1f}%" if close else ""
        parts.append(f"止盈 {float(tp):.2f}{gap}")
    if sp:
        gap = f", 差 {(float(sp) / close - 1) * 100:+.1f}%" if close else ""
        parts.append(f"止损 {float(sp):.2f}{gap}")
    if plan.get("due_date"):
        parts.append(f"到期 {plan['due_date']}")
    return f"{sym} 买入时立的计划: " + " · ".join(parts) if parts else ""
