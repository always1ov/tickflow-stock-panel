"""[fork 增强] R42 Keltner 通道的口径与位置判定(纯函数)。

原来这套公式只写在 ``levels._keltner_band`` 里, 供个股分析的图表按单只标的算。
决策台要给整张自选表加三列, 走的是批量路径 —— 两条路径各写一份公式,
图表说"贴着上轨"、决策台说"通道内"的那天就没法查了。所以把口径抽到这里,
两边都调它。

三档参数(与图表逐字一致):
    短期  MA20  ± 2.0 × ATR14   近一个月的波动带
    中期  MA60  ± 2.5 × ATR14   一个季度
    长期  MA120 ± 3.0 × ATR14   半年, 牛熊边界

"贴近"用 ATR 度量而不是百分比: 通道宽度本身就是 ATR 的倍数, 用百分比判贴近
会让高波动的票永远"不贴", 低波动的票永远"贴着"。
"""
from __future__ import annotations

import math
from typing import Any

# (key, 均线列名(None = 现场算), 窗口, ATR 倍数, 中文档名)
BANDS: tuple[tuple[str, str | None, int, float, str], ...] = (
    ("s", "ma20", 20, 2.0, "短期"),
    ("m", "ma60", 60, 2.5, "中期"),
    ("l", None, 120, 3.0, "长期"),
)
BAND_KEYS = tuple(b[0] for b in BANDS)

# 距离轨道多少个 ATR 以内算"贴着"。0.5 个 ATR ≈ 半天的正常波动就能碰到。
NEAR_ATR = 0.5

POS_ABOVE = "above"           # 上轨之上
POS_NEAR_UPPER = "near_upper"  # 贴近上轨
POS_INSIDE = "inside"          # 通道内
POS_NEAR_LOWER = "near_lower"  # 贴近下轨
POS_BELOW = "below"            # 下轨之下

POS_CN = {
    POS_ABOVE: "破上轨",
    POS_NEAR_UPPER: "贴上轨",
    POS_INSIDE: "通道内",
    POS_NEAR_LOWER: "贴下轨",
    POS_BELOW: "破下轨",
}
# 中性措辞: 通道位置是事实描述, 不是买卖指令。同一个"破上轨"在趋势票上是强势
# 确认、在震荡票上是超买, 系统不该替用户下这个判断。
POS_HINT = {
    POS_ABOVE: "收盘站上通道上轨 —— 强势突破或短线超买, 看趋势状态定性",
    POS_NEAR_UPPER: "逼近通道上轨, 上方阻力临近",
    POS_INSIDE: "在通道内运行, 没触及任何一边",
    POS_NEAR_LOWER: "逼近通道下轨, 下方支撑临近",
    POS_BELOW: "收盘跌破通道下轨 —— 弱势破位或短线超卖, 看趋势状态定性",
}


def _num(v: Any) -> float | None:
    """能转成有限浮点才算数。注意 0 是合法的 —— 只有 ATR 需要额外要求为正。"""
    if isinstance(v, bool) or v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def band(ma: Any, atr: Any, n: float) -> tuple[float, float] | None:
    """均线 ± n×ATR。任一输入缺失或 ATR 非正返回 None(不返回退化成一条线的通道)。"""
    m, a = _num(ma), _num(atr)
    if m is None or a is None or a <= 0:
        return None
    return m + n * a, m - n * a


def classify(close: Any, upper: Any, lower: Any, atr: Any) -> str | None:
    """价格落在通道的哪一段。判定顺序: 先看是否已经在轨外, 再看是否贴着。

    先判轨外要紧 —— 已经破上轨的票同时也"在上轨 0.5 ATR 以内", 反过来判
    会把突破说成"贴近", 那是两件完全不同的事。
    """
    c, u, low, a = _num(close), _num(upper), _num(lower), _num(atr)
    if c is None or u is None or low is None or a is None or a <= 0 or u <= low:
        return None
    if c > u:
        return POS_ABOVE
    if c < low:
        return POS_BELOW
    gap = NEAR_ATR * a
    if u - c <= gap:
        return POS_NEAR_UPPER
    if c - low <= gap:
        return POS_NEAR_LOWER
    return POS_INSIDE


def pct_in_channel(close: Any, upper: Any, lower: Any) -> float | None:
    """在通道里的相对位置: 0 = 贴着下轨, 1 = 贴着上轨。轨外会 <0 或 >1。

    一个数就能说清全部位置, 比五档文字更细 —— 界面用它排序和上色。
    """
    c, u, low = _num(close), _num(upper), _num(lower)
    if c is None or u is None or low is None or u <= low:
        return None
    return (c - low) / (u - low)


def assess(*, close: Any, ma: Any, atr: Any, n: float) -> dict | None:
    """一档通道的完整读数。算不出来返回 None, 不返回半个空壳。"""
    b = band(ma, atr, n)
    if b is None:
        return None
    upper, lower = b
    pos = classify(close, upper, lower, atr)
    if pos is None:
        return None
    c = _num(close)
    return {
        "pos": pos,
        "pos_cn": POS_CN[pos],
        "hint": POS_HINT[pos],
        "upper": round(upper, 2),
        "lower": round(lower, 2),
        "pct": round(pct_in_channel(close, upper, lower) or 0.0, 3),
        # 到最近那条轨还有多远(按 ATR 算) —— 界面显示"还差 0.3 个 ATR 到上轨"
        "to_upper_atr": round((upper - c) / float(atr), 2) if c is not None else None,
        "to_lower_atr": round((c - lower) / float(atr), 2) if c is not None else None,
    }


# ---------- 三档合成: 高抛 / 低吸压力 ----------

# 高抛侧与低吸侧的位置集合。贴轨与破轨都算 —— 等真破了再动手往往已经过了那个价。
_HIGH = (POS_ABOVE, POS_NEAR_UPPER)
_LOW = (POS_BELOW, POS_NEAR_LOWER)

SIDE_HIGH = "high"   # 该高抛
SIDE_LOW = "low"     # 该低吸
LEVEL_STRONG = "strong"
LEVEL_MILD = "mild"


def pressure(bands: dict | None) -> dict | None:
    """三档通道读数 → 高抛/低吸压力。纯函数。

    判定只看**短期档**定方向, 用**中期档**定强弱:

    · 短期贴/破上轨 = 该高抛; 短期贴/破下轨 = 该低吸。短期是操作级别,
      这是你真正要动手的那一档。
    · 中期同向 = strong(两个级别共振), 否则 mild。中期只放大不改向 ——
      让中期能否决短期的话, 一只中期在通道中部、短期已经破上轨的票会被判成
      "没事", 而它明明已经短线过热了。
    · 长期档只带在文本里供参考, 不参与判定。半年通道太钝, 拿它决定
      这周该不该减仓等于用尺子量头发。

    两侧同时成立是不可能的(短期只有一个位置), 所以不需要处理冲突。
    """
    if not bands:
        return None
    short = bands.get("s")
    if not short:
        return None
    pos = short.get("pos")
    if pos in _HIGH:
        side = SIDE_HIGH
    elif pos in _LOW:
        side = SIDE_LOW
    else:
        return None

    same = _HIGH if side == SIDE_HIGH else _LOW
    mid = (bands.get("m") or {}).get("pos")
    long = (bands.get("l") or {}).get("pos")
    level = LEVEL_STRONG if mid in same else LEVEL_MILD

    where = "上轨" if side == SIDE_HIGH else "下轨"
    parts = [f"短期{short.get('pos_cn', '')}"]
    if mid in same:
        parts.append(f"中期也{POS_CN.get(mid, '')}")
    if long in same:
        parts.append(f"长期同样{POS_CN.get(long, '')}")
    return {
        "side": side,
        "level": level,
        "text": "、".join(parts),
        "where": where,
        # 共振了几档 —— 界面按这个决定标签轻重
        "bands_aligned": sum(1 for x in (pos, mid, long) if x in same),
    }


def is_high(p: dict | None) -> bool:
    return bool(p) and p.get("side") == SIDE_HIGH


def is_strong(p: dict | None) -> bool:
    return bool(p) and p.get("level") == LEVEL_STRONG
