"""[fork 增强] R189 趋势模板 —— Minervini 的八条, 原样搬过来当「质地」的主因子。

## 为什么要它

现有把握分里描述"这只票本身好不好"的东西只有两个: 六态状态(UT/NR/SR)和
20 日相对强度。两个都只看**最近一个月**。于是一只刚从三年下跌里反弹一个月的
票, 和一只在 200 日均线上方走了一年的票, 在"质地"上拿到的分几乎一样 ——
而这两者是完全不同的东西。

八条模板补的正是这一段: 它全部在讲**长周期的价格结构**(50/150/200 日均线的
排列与方向、离 52 周高低点多远), 与新鲜度、量比、通道位置这些当天的量没有
任何重叠。

## 周期为什么不改成 20/60/120

本 fork 自己那套是 20/60/120(生命线 / 中期 / 牛熊边界)。这里刻意**保留
50/150/200 原值**: 引入一个外部标准, 价值恰恰在于它是被公开检验过的那一组
数; 把周期换成本地口径, 得到的就只是"一个长得像趋势模板的东西", 外部的
检验记录一并作废。两套周期并存不是不一致 —— 它们回答的是不同的问题。

## 只用收盘价

52 周高低点按**收盘**算, 不按盘中最高最低。理由与六态一致: 本 fork 的趋势
判定全线是收盘口径, 混入盘中极值会让"距高点 25% 以内"这一条在插针行情里
跳来跳去, 而那一根影线并不代表任何人真的在那个价上持有过。

## 数据不够怎么办

单条算不出来时 `pass=None`(而不是 False) —— "没读到"和"没通过"是两回事,
这条纪律与 opportunity_score 的门槛层一致。调用方拿 `known` 决定这份模板
算不算数; `assess` 自己不做那个决定。
"""
from __future__ import annotations

# 均线周期。原值, 见模块头「周期为什么不改」。
MA_SHORT, MA_MID, MA_LONG = 50, 150, 200
# MA200 斜率的回看跨度(交易日)。Minervini 原文是"至少一个月", 取 22 个交易日。
SLOPE_LOOKBACK = 22
# 52 周 ≈ 250 个交易日
YEAR_BARS = 250
# 离 52 周低点至少高这么多 / 离 52 周高点最多低这么多
OFF_LOW_MIN = 0.30
NEAR_HIGH_MAX = 0.25

TOTAL = 8


def _ma(closes: list[float], period: int, offset: int = 0) -> float | None:
    """倒数第 offset+1 根上的 period 日均线。数据不够返回 None(不拿短窗凑数)。"""
    end = len(closes) - offset
    if end < period or end <= 0:
        return None
    return sum(closes[end - period:end]) / period


def _c(code: str, label: str, ok: bool | None, detail: str) -> dict:
    return {"code": code, "label": label, "pass": ok, "detail": detail}


def assess(closes: list[float] | None, rs_6m: float | None = None) -> dict:
    """八条模板。

    closes: 升序日收盘价(越长越好, 要 250+ 根才可能八条全给得出)。
    rs_6m:  近 6 个月**超额收益**(个股 − 基准), 小数(0.12 = 跑赢 12 个点)。
            这是第 8 条 RS 排名的近似 —— 真排名要全市场分位, 本系统还没有,
            用超额正负代替, 见 `criteria[7]["detail"]` 里的注明。

    返回 {passed, known, total, criteria, complete}。
    **不返回分数** —— 八条通过几条是事实, "通过 6 条值多少分"是打分的事,
    归 opportunity_score 管(本项目所有规则层共守的一条纪律: 判定层只出事实与档位,
    分数在打分层给)。
    """
    cs = [c for c in (closes or []) if c is not None]
    n = len(cs)
    close = cs[-1] if n else None

    ma50, ma150, ma200 = (_ma(cs, MA_SHORT), _ma(cs, MA_MID), _ma(cs, MA_LONG))
    ma200_prev = _ma(cs, MA_LONG, SLOPE_LOOKBACK)

    win = cs[-YEAR_BARS:] if n >= YEAR_BARS else None
    hi52 = max(win) if win else None
    lo52 = min(win) if win else None

    out: list[dict] = []

    out.append(
        _c("above_mid_long", f"收盘站上 MA{MA_MID} 与 MA{MA_LONG}",
           (close > ma150 and close > ma200) if (close and ma150 and ma200) else None,
           f"收盘 {close:.2f} · MA{MA_MID} {ma150:.2f} · MA{MA_LONG} {ma200:.2f}"
           if (close and ma150 and ma200) else f"历史不足 {MA_LONG} 根"))

    out.append(
        _c("mid_above_long", f"MA{MA_MID} 在 MA{MA_LONG} 之上",
           (ma150 > ma200) if (ma150 and ma200) else None,
           f"MA{MA_MID} {ma150:.2f} · MA{MA_LONG} {ma200:.2f}"
           if (ma150 and ma200) else f"历史不足 {MA_LONG} 根"))

    out.append(
        _c("long_rising", f"MA{MA_LONG} 已上行至少一个月",
           (ma200 > ma200_prev) if (ma200 and ma200_prev) else None,
           f"较 {SLOPE_LOOKBACK} 日前 {(ma200 / ma200_prev - 1) * 100:+.1f}%"
           if (ma200 and ma200_prev) else f"历史不足 {MA_LONG + SLOPE_LOOKBACK} 根"))

    out.append(
        _c("ma_stacked", f"MA{MA_SHORT} > MA{MA_MID} > MA{MA_LONG}",
           (ma50 > ma150 > ma200) if (ma50 and ma150 and ma200) else None,
           f"{ma50:.2f} / {ma150:.2f} / {ma200:.2f}"
           if (ma50 and ma150 and ma200) else f"历史不足 {MA_LONG} 根"))

    out.append(
        _c("above_short", f"收盘站上 MA{MA_SHORT}",
           (close > ma50) if (close and ma50) else None,
           f"收盘 {close:.2f} · MA{MA_SHORT} {ma50:.2f}({(close / ma50 - 1) * 100:+.1f}%)"
           if (close and ma50) else f"历史不足 {MA_SHORT} 根"))

    out.append(
        _c("off_low", f"高出 52 周最低收盘 {OFF_LOW_MIN:.0%} 以上",
           (close >= lo52 * (1 + OFF_LOW_MIN)) if (close and lo52) else None,
           f"52 周低点 {lo52:.2f} · 现高出 {(close / lo52 - 1) * 100:.0f}%"
           if (close and lo52) else f"历史不足 {YEAR_BARS} 根"))

    out.append(
        _c("near_high", f"距 52 周最高收盘 {NEAR_HIGH_MAX:.0%} 以内",
           (close >= hi52 * (1 - NEAR_HIGH_MAX)) if (close and hi52) else None,
           f"52 周高点 {hi52:.2f} · 现低于 {(1 - close / hi52) * 100:.0f}%"
           if (close and hi52) else f"历史不足 {YEAR_BARS} 根"))

    out.append(
        _c("rs_positive", "近 6 个月跑赢基准",
           (rs_6m > 0) if rs_6m is not None else None,
           f"超额 {rs_6m * 100:+.1f}%(近似:原版要全市场 RS 分位, 本系统暂用超额正负)"
           if rs_6m is not None else "缺少基准或个股 6 个月收益"))

    passed = sum(1 for c in out if c["pass"] is True)
    known = sum(1 for c in out if c["pass"] is not None)
    return {"passed": passed, "known": known, "total": TOTAL,
            "criteria": out, "complete": known == TOTAL}


def summary(res: dict) -> str:
    """一句能直接摆在悬停里的话。"""
    if not res or not res.get("known"):
        return "趋势模板:历史不足,八条一条都判不了"
    if not res.get("complete"):
        return f"趋势模板:{res['passed']}/{res['known']} 条(另有 {TOTAL - res['known']} 条历史不足)"
    miss = [c["label"] for c in res["criteria"] if c["pass"] is False]
    tail = ";差:" + "、".join(miss[:3]) if miss else ";八条全过"
    return f"趋势模板:{res['passed']}/{TOTAL} 条{tail}"
