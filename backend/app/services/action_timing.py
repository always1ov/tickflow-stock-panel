"""[fork R158] 出手时机 —— 每只机会一句结论: 今天动手 / 收盘再动 / 不动手。

起因: 「距触发 -2.55%」要人在脑子里再翻译一次(负数是已越过? 越过多少算追高?
回升那种还没突破的怎么算?), 而用户要的是结论。这里把散在各列里的原料收成一句话。

**与评分的分工**(R134 定的, 不动): 把握分说的是「这票值不值得进候选」, 本模块
说的是「今天这一天能不能下手」。前者冻在收盘口径; 后者允许看盘中价, 因为它回答
的正是盘中的问题。所以本模块是**注记**: 一分不进评分, 不改名次, 只多一列。

三个结论的定义:

  今天动手   已确认上涨趋势(六态 UT), 信号新鲜(≤3 天, 与 FRESH_CURVE 的拐点一致),
             价格还贴着关键点(高出不到 5%), 没贴上轨, 盘中没跌回关键点下方,
             大盘不在防守档。—— 可以分批, 建仓路径见「建议仓位」。
  收盘再动   方向对但**还差一个确认**: 盘中临时信号 / 回升途中盘中刚过关键点 /
             距触发价 2% 以内 / 转多第 4~5 天 / 盘中回落到关键点附近。
             利弗莫尔的规矩是收盘价说话 —— 收盘站稳(或守住)关键点再动。
  不动手     任一条排除项命中: 大盘防守、盘中跌破生命线、当日涨幅已到板幅的 70%、
             已高出关键点 5%+、贴短期上轨、转多第 6 天起(信号已老)、回升途中
             还没突破关键点(等站上再看)。

阈值全部是价格判据, 可回测; 与 opportunity_score 的曲线常数对齐, 不另立口径。
"""
from __future__ import annotations

from app.price_limits import board_limit_pct

TODAY = "today"
AFTER_CLOSE = "after_close"
HOLD_OFF = "hold_off"
LABELS = {TODAY: "今天动手", AFTER_CLOSE: "收盘再动", HOLD_OFF: "不动手"}

CHASE_ABOVE_PIVOT_PCT = 5.0    # 已高出关键点 5% 以上 = 追高
FRESH_MAX_DAY = 3              # FRESH_CURVE: 第 3 天 72 分, 第 4 天掉到 46 —— 拐点在这
STALE_DAY = 6                  # 第 6 天起信号已老(第 5 天 30 分, 第 8 天 12 分)
UPPER_BAND_PCT = 0.85          # 贴短期上轨(与 POS_CURVE 0.85 → 50 分的位置一致)
INTRADAY_CHASE_FRACTION = 0.7  # 当日涨幅 ≥ 板幅 × 0.7(主板 7%, 双创 14%)不追
INTRADAY_PULLBACK_PCT = -3.0   # 盘中回落 ≥3% → 等收盘看守没守住
NEAR_TRIGGER_PCT = 2.0         # 与 today._NEAR_BREAKOUT_PCT 一致


def _num(v) -> float | None:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _fmt(v: float | None) -> str:
    return "—" if v is None else f"{v:g}"


def decide(o: dict, posture: str | None) -> dict:
    """一只机会行 → {code, label, reason, trigger}。纯函数, 不读盘、不改入参。

    读的字段: trend_state / duration / gap_pct / channel_pct / pivot / kinds /
    intraday / live{price, change_pct, below_lifeline, ma20} / symbol。缺哪个就
    跳过那条规则 —— 缺数据不制造结论, 但也不因为缺数据就放行。
    """
    sym = str(o.get("symbol") or "")
    state = o.get("trend_state")
    dur = int(o.get("duration") or 0)
    gap = _num(o.get("gap_pct"))            # (关键点 - 收盘)/收盘 × 100; 负 = 已越过
    cpct = _num(o.get("channel_pct"))
    pivot = _num(o.get("pivot"))
    kinds = list(o.get("kinds") or [])
    live = o.get("live") or {}
    lp = _num(live.get("price"))
    lchg = _num(live.get("change_pct"))

    def out(code: str, reason: str, trigger: float | None = None) -> dict:
        return {"code": code, "label": LABELS[code], "reason": reason, "trigger": trigger}

    # ---- 一、排除项: 任一命中即不动手 ----
    if posture == "防守":
        return out(HOLD_OFF, "大盘防守档, 不开新仓")
    if live.get("below_lifeline"):
        return out(HOLD_OFF, f"盘中已跌破生命线 {_fmt(_num(live.get('ma20')))}")
    if lchg is not None:
        cap = board_limit_pct(sym) * 100 * INTRADAY_CHASE_FRACTION
        if lchg >= cap:
            return out(HOLD_OFF, f"今日已涨 {lchg:.1f}%, 不追")
    if gap is not None and gap <= -CHASE_ABOVE_PIVOT_PCT:
        return out(HOLD_OFF, f"已高出关键点 {-gap:.1f}%, 追高", pivot)
    if cpct is not None and cpct >= UPPER_BAND_PCT:
        return out(HOLD_OFF, "贴短期上轨, 等回踩")
    if state == "UT" and dur >= STALE_DAY:
        return out(HOLD_OFF, f"转多第 {dur} 天, 信号已老")

    # ---- 二、需要收盘确认的 ----
    if o.get("intraday"):
        return out(AFTER_CLOSE, "盘中临时信号, 收盘确认后再动", pivot)
    if state != "UT":
        # 回升 / 次级回升 / 逼近触发价: 关键点还在上方, 突破没发生
        if pivot is None:
            return out(HOLD_OFF, "没有关键点, 等突破确认")
        if lp is not None and lp >= pivot:
            return out(AFTER_CLOSE, f"盘中已过关键点 {_fmt(pivot)}, 收盘站稳再动", pivot)
        if "near_breakout" in kinds and gap is not None and 0 <= gap <= NEAR_TRIGGER_PCT:
            return out(AFTER_CLOSE, f"距触发价 {_fmt(pivot)} 还差 {gap:.1f}%, 收盘站上再动", pivot)
        gap_txt = f"(还差 {gap:.1f}%)" if gap is not None and gap > 0 else ""
        return out(HOLD_OFF, f"未突破关键点 {_fmt(pivot)}{gap_txt}, 等站上再看", pivot)

    # ---- 三、已确认上涨趋势(UT) ----
    if lchg is not None and lchg <= INTRADAY_PULLBACK_PCT:
        return out(AFTER_CLOSE, f"盘中回落 {lchg:.1f}%, 收盘守住关键点再动", pivot)
    if pivot is not None and lp is not None and lp < pivot:
        return out(AFTER_CLOSE, f"盘中跌回关键点 {_fmt(pivot)} 下方, 收盘守住再动", pivot)
    if dur > FRESH_MAX_DAY:
        return out(AFTER_CLOSE, f"转多第 {dur} 天, 收盘仍站稳关键点再动", pivot)
    above = -gap if gap is not None else None
    why = f"上涨趋势第 {dur} 天" if dur else "上涨趋势确认"
    if above is not None and above >= 0:
        why += f", 高出关键点 {above:.1f}%"
    if posture in ("谨慎", "观察"):
        why += f", {posture}档轻仓试"
    return out(TODAY, why + ", 可分批", pivot)
