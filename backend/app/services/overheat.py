"""[fork 增强] R41 短期过热 —— 系统缺的那句"涨太急了"。

今日总览只说得出两件事:"该买了"(转多/回升)和"该跑了"(破线/趋势转坏)。
中间那句"涨得太急, 先落袋一部分"它说不出来 —— 持仓体检的三个减仓触发
(转空头 / AI 看空 / 逼近出场线)全是**风险驱动**, 没有一条是**过热驱动**。

本模块只负责测量, 不负责决策。它回答的是一个事实问题:"这只票现在离它自己的
均线有多远、涨得有多急"。要不要因此减仓, 由决策层(``today.holding_stance``)结合
趋势状态去判 —— 测量层和决策层分开, 是因为"新转强第 2 天 RSI 就 80"和"横盘半年
突然拉到 RSI 80"是同一个读数、完全不同的两件事。

口径两个要点:

1. **用 ATR 归一化, 不用固定百分比**。乖离 15% 对主板是极端, 对 20cm 的创业板/
   科创板很常见。``(close - ma20) / atr14`` 自动按这只票自己的波动尺度缩放,
   不需要维护一张按板块分的阈值表, 也不会系统性地把高波动的票全判成过热。
2. **两个条件同时满足才算数**。只看 RSI 会把健康的强势趋势大批误伤 —— 一轮像样的
   主升浪 RSI 常年在 70 以上。必须同时"指标超买"且"价格远离均线"才算冲过头。
"""
from __future__ import annotations

from typing import Any

LEVEL_HOT = "hot"        # 过热: 明显冲过头
LEVEL_WARM = "warm"      # 偏热: 有点急了
LEVEL_CN = {LEVEL_HOT: "过热", LEVEL_WARM: "偏热"}

# RSI 门槛。70 是传统超买线, 75 以上在 A 股日线上已经属于少见的急拉。
RSI_HOT = 75.0
RSI_WARM = 70.0
# 离 MA20 多少个 ATR。3 个 ATR 意味着按这只票自己的日常波动幅度算,
# 已经连着走了三天满幅还没回过头。
DEV_ATR_HOT = 3.0
DEV_ATR_WARM = 2.0


def _num(v: Any) -> float | None:
    """能转成有限浮点才算数; None / NaN / 字符串一律当缺失。"""
    if isinstance(v, bool) or v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f and f not in (float("inf"), float("-inf")) else None


def deviation_atr(close: Any, ma20: Any, atr: Any) -> float | None:
    """价格高于 MA20 多少个 ATR。低于均线返回负数, 取不到返回 None。"""
    c, m, a = _num(close), _num(ma20), _num(atr)
    if c is None or m is None or a is None or a <= 0:
        return None
    return (c - m) / a


def assess(*, rsi: Any = None, close: Any = None, ma20: Any = None,
           atr: Any = None) -> dict | None:
    """测量短期过热程度。够不着门槛返回 None(而不是一个 level=None 的空壳)。

    返回 {level, level_cn, rsi, dev_atr, text} —— text 是给界面直接显示的一句话,
    带上真实数字, 用户能自己复核而不是只看到一个"过热"标签。
    """
    r = _num(rsi)
    dev = deviation_atr(close, ma20, atr)
    if r is None or dev is None:
        return None

    if r >= RSI_HOT and dev >= DEV_ATR_HOT:
        level = LEVEL_HOT
    elif r >= RSI_WARM and dev >= DEV_ATR_WARM:
        level = LEVEL_WARM
    else:
        return None

    return {
        "level": level,
        "level_cn": LEVEL_CN[level],
        "rsi": round(r, 1),
        "dev_atr": round(dev, 1),
        "text": f"RSI {r:.0f}、离 20 日线 {dev:.1f} 个 ATR",
    }


def is_hot(heat: dict | None) -> bool:
    return bool(heat) and heat.get("level") == LEVEL_HOT


def extract(row: dict) -> dict | None:
    """从一行 enriched 数据里取所需字段做测量。列名缺失时安静返回 None。"""
    return assess(rsi=row.get("rsi_14"), close=row.get("close"),
                  ma20=row.get("ma20"), atr=row.get("atr_14"))
