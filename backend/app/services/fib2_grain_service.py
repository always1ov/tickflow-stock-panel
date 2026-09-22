"""[R412 · fork 增强] 粗细档回测的服务层 —— 取数、跑表、给建议、(可选)问 AI。

**与六态那个「回测调参」按钮同一个形状**(用户原话:「就像我六态设置了一个回测
按钮, 参考这种模式」): 纯计算出一张指标表 → 规则建议保底 → AI 顾问可选。

但**评的东西不一样, 这一点必须说清楚**:

    六态那个评的是「跟着做赚不赚」—— 它出买卖信号, 有收益可算。
    这个评的是「线画得准不准」—— 它不出任何买卖信号, 也就没有收益这回事。

为什么不能评收益: 要算收益就得先定一条买卖规则(在哪条回踩位买、在哪卖),
而这一整组东西的口径从 R405 起就是「只有位置, 没有动作」, 用户原话
「是否共振我自己人工判断, 不打算代码判断」。**编一条规则去回测, 等于把被砍掉的
判定层从后门接回来**, 而且卖出那一半还会和止盈线/生命线抢答案。

几何本身怎么评、为什么必须除以线数, 见 `indicators/dinapoli_fit`。
"""
from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from typing import Any

from app.indicators.dinapoli_fit import advise, backtest_grains

logger = logging.getLogger(__name__)

# 回测窗口。**比画图那 120 天长得多** —— 一只票一年也未必有三次像样的上攻,
# 拿 120 天去回测基本只会得到"样本太少"。三年是"够凑出样本"与"太久远的行情
# 已经不像现在"之间的一个取舍。
WINDOW_DAYS = 750

_AI_SYSTEM = (
    "你是量化图表参数顾问。你要做的**只有一件事**: 在给定的三档粗细里选一档。\n"
    "\n"
    "背景: 这是一组画在 K 线图上的**位置线**(斐波那契二型的回踩位), 它不产生任何买卖\n"
    "信号, 也不参与打分。粗细档只决定「多小的回调算一个回调」—— 调粗线少而稳,\n"
    "调细线多而密。\n"
    "\n"
    "指标表的含义:\n"
    "  samples   可评估的上攻段数(样本量)\n"
    "  hit_rate  历史上实际回踩的最低点, 落在当时画出的某条线上的比例\n"
    "  zone_rate 落在「几条线挤在一起」那个带里的比例(分母是算得出带的段数)\n"
    "  avg_lines 每次平均画几条线\n"
    "  per_line  hit_rate ÷ avg_lines\n"
    "\n"
    "纪律(违反任何一条都算答错):\n"
    "  1. **线多必然更容易蒙中。** 只看 hit_rate 排序等于必然推荐最细那一档,\n"
    "     那是过拟合。必须把 avg_lines 的代价算进去。\n"
    "  2. **样本不足就说不足**, 不要硬选。少于 3 个样本的档一律不推荐。\n"
    "  3. **不许给任何买卖、仓位、止盈止损建议** —— 你选的是画多细, 不是做不做。\n"
    "  4. 只能选给定的档名之一, 不许自创参数。\n"
    "\n"
    '只输出 JSON: {"grain": "coarse|mid|fine|null", "reason": "一两句中文理由"}'
)


def _load(repo, symbol: str):
    end = date.today()
    start = end - timedelta(days=WINDOW_DAYS)
    return repo.get_daily_asset(repo.resolve_asset_type(symbol), symbol, start, end)


async def run_grain_backtest(repo, symbol: str, use_ai: bool = True) -> dict[str, Any]:
    """三档各跑一遍 + 规则建议 + (可选)AI 顾问。"""
    sym = (symbol or "").strip().upper()
    if not sym:
        return {"error": "symbol 不能为空"}
    df = _load(repo, sym)
    if df.is_empty():
        return {"symbol": sym, "error": "没有日 K 数据, 无法回测"}

    fits = backtest_grains(df)
    rows = [f.to_dict() for f in fits]
    rule = advise(fits)
    out: dict[str, Any] = {
        "symbol": sym,
        "window_days": int(df.height),
        "grid": rows,
        "rule_suggestion": rule,
        "ai": None,
    }
    if not use_ai:
        return out

    from app.services.ai_provider import ai_configured, generate_ai_text
    if not ai_configured():
        out["ai_error"] = "未配置 AI(规则建议仍可用)"
        return out
    try:
        from app.services.ai_json import extract_json_object
        text = await generate_ai_text(
            [
                {"role": "system", "content": _AI_SYSTEM},
                {"role": "user", "content": (
                    f"标的: {sym}\n可评估窗口: {df.height} 根日线\n"
                    f"三档指标表(JSON):\n{json.dumps(rows, ensure_ascii=False)}")},
            ],
            temperature=0.2,
            # [上游标准] 分析类调用不限制输出(推理模型的思考段计入预算)
            max_tokens=None,
        )
        obj = extract_json_object(text)
        if isinstance(obj, dict) and obj.get("grain") in {"coarse", "mid", "fine", None}:
            out["ai"] = {"grain": obj.get("grain"), "reason": str(obj.get("reason", ""))}
        else:
            out["ai_error"] = "AI 返回的档名不在三档之内, 已忽略(规则建议仍可用)"
    except Exception as e:  # noqa: BLE001
        logger.warning("fib2 grain ai advisor failed: %s", e)
        out["ai_error"] = f"AI 调用失败: {e}(规则建议仍可用)"
    return out
