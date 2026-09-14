"""[fork 增强] R329 今日信号 —— 「收盘前五分钟该挂什么单」。

用户: 「我只有一个要求, 你怎么设计补充都可以但**一定要根据转折才能出手**」。

R327 做的模拟盘是**纯回测**: 打开时从历史日线重算过去两年。它回答"这套判定长期
行不行", 但**不在今天做任何事** —— 用户问「现在模拟盘是每天收盘前五分钟买的
吗」, 答案是否。这一层补的就是那个缺口。

## 三档, 而且只有第一档能出手

    ① 已转折   最新那根**已落盘**的日 K 让状态翻了面   → **出手**
    ② 盘中越线 按此刻现价当收盘算, 会翻面              → **不出手**, 尾盘再看
    ③ 还没到   离触发价还有 N%                        → **不出手**, 只是盯着

**②③ 永远不是出手理由, 这是用户那条唯一要求的落点。** 代码上的保证不是"提示语
写清楚", 而是结构: 只有 ①  这一档带 `act`(买/卖), ②③ 的 `act` 恒为 `None`;
守卫直接断言后两档的 `act` 是空的。提示语会被改, 结构不会被顺手改掉。

**为什么 ② 不能出手**: 盘中价会变回去。14:30 跌破了触发价, 14:58 又拉回来 ——
那天**没有转折**, 因为转折是拿收盘价算的。真按 ② 出手, 做的就不是这套判定了,
是"这套判定 + 一个我编的抢跑规则", 而那个规则从来没被回测过。

② 存在的唯一意义是**让你知道今天尾盘要盯哪几只**。

## 触发价从哪来

作者的 `compute()` 每天给 `flip_up` / `flip_down`: 「收盘站上这个价就转多」
「收盘跌破这个价就转空」。**开盘前就定死**, 这正是"尾盘挂单可执行"的依据,
也是 R327 那个成交口径的全部底气。**不自己另算一条线。**

## 实时价可有可无

实时行情是按需开的开关。关着时 ② 这一档整个不出现, ③ 按上一收盘价算距离并
标注 `live=false` —— **不替用户去开一个要花额度的开关**。

纯函数那一半在 `evaluate()`: 不读盘、不调网。取数在 `flip_today_run`。
"""
from __future__ import annotations

import logging

from app.services.flip_trades import BEAR, BULL, trend_days

logger = logging.getLogger(__name__)

# 三档的码
STAGE_FLIPPED = "flipped"       # 已转折 —— 唯一能出手的一档
STAGE_CROSSING = "crossing"     # 盘中越线, 收盘才算数
STAGE_WATCH = "watch"           # 还没到

ACT_BUY = "buy"
ACT_SELL = "sell"

# ③ 这一档只列**近的**。离触发价 20% 的票每天都在名单里, 等于没有名单。
WATCH_WITHIN = 0.05


def evaluate(steps: list[dict], *, held: bool, last_close: float | None,
             live_close: float | None = None) -> dict | None:
    """一只票今天的信号。没有可说的就返回 None。

    steps       `livermore.compute()` 的输出(原样)。**最后一根必须是已落盘的
                日 K** —— 盘中价不进 steps, 否则算出来的"转折"会随分时抖动。
    held        模拟盘现在拿着它吗 —— 决定「转空」是「清仓」还是「本来就空仓」
    last_close  最新已落盘收盘价
    live_close  此刻现价; None = 实时没开

    返回::

        {stage, act, side, state_cn, flip_price, ref_price, gap_pct, live}

        act 只在 stage == "flipped" 时有值; 另外两档恒为 None。
    """
    if not steps:
        return None
    days = trend_days(steps)            # ← 多空判据只此一处
    last = days[-1]
    side = last.get("side")
    state_cn = last.get("state_cn")

    # ── ① 已转折 —— 唯一能出手的一档 ──────────────────────────────────
    if last.get("flipped"):
        if side == BULL and not held:
            act = ACT_BUY
        elif side == BEAR and held:
            act = ACT_SELL
        else:
            # 转了但手上状态已经对上了(比如转多而本来就拿着)—— 不重复动手
            act = None
        return {
            "stage": STAGE_FLIPPED,
            "act": act,
            "side": side,
            "state_cn": state_cn,
            "flip_price": None,
            "ref_price": last_close,
            "gap_pct": None,
            "live": False,      # ① 是拿已落盘的日 K 算的, 与实时无关
        }

    # ── ②③ 还没转 —— 看离触发价多远 ───────────────────────────────────
    raw = steps[-1]
    # 多头侧盯着"跌破就转空", 空头侧盯着"站上就转多"。**方向要对上** ——
    # 拿反了会把"还早得很"说成"就快了"。
    flip_price = raw.get("flip_down") if side == BULL else raw.get("flip_up")
    flip_price = _f(flip_price)
    if flip_price is None:
        return None

    ref = _f(live_close) if live_close is not None else _f(last_close)
    if ref is None:
        return None
    is_live = live_close is not None

    # 越线判定: 多头侧是"跌到触发价或更低", 空头侧是"涨到触发价或更高"。
    crossed = ref <= flip_price if side == BULL else ref >= flip_price
    gap = (flip_price - ref) / ref

    if crossed:
        if not is_live:
            # 已落盘的收盘价越了线却没 flipped —— 状态机自有它的道理(阈值、
            # 段内极值), **不替它下结论**。这种情况不报。
            return None
        return {
            "stage": STAGE_CROSSING,
            "act": None,        # ← 盘中越线**不是**出手理由
            "side": side,
            "state_cn": state_cn,
            "flip_price": flip_price,
            "ref_price": ref,
            "gap_pct": round(gap, 6),
            "live": True,
        }

    if abs(gap) > WATCH_WITHIN:
        return None
    return {
        "stage": STAGE_WATCH,
        "act": None,            # ← 接近**不是**出手理由
        "side": side,
        "state_cn": state_cn,
        "flip_price": flip_price,
        "ref_price": ref,
        "gap_pct": round(gap, 6),
        "live": is_live,
    }


def _f(v) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if f != f or f <= 0 else f
