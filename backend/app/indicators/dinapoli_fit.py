"""[R412 · fork 增强] 粗细档怎么选 —— 回测**「这些线画得准不准」**。

用户: 「粗中细我看不懂, 这个调优能不能交给 ai 就像我六态设置了一个回测按钮」。

## 先修正我自己说过的一句话

R406 我写过:「这个指标不出买卖信号、不进把握分, **没有可打分的目标函数,
也就没有"校准"这回事**」。**那句话说快了。**

"赚不赚钱"确实评不了 —— 那要先定一条买卖规则, 而这一整组东西的口径就是
「只有位置, 没有动作」(用户原话:「是否共振我自己人工判断, 不打算代码判断」)。
**但还有另一样东西完全可以回测, 而且它正好就是"粗细档"在问的问题**:

    这些线画得准不准 —— 历史上每一次上攻之后, 实际回踩的最低点,
    有没有落在当时画出来的某条线上 / 那条密集带里?

这个量**不需要任何买卖规则**, 不碰判定层, 也不进把握分。

## 为什么必须除以线数

**细档画更多线, 蒙中的概率天然更高。** 不除这一下, 任何"命中率"排序都会必然
推荐最细的那一档 —— 那不是调参, 那是过拟合的标准形态。所以这里的主指标是

    每条线的贡献 = 命中率 ÷ 平均线数

同一个命中率下, 线越少越好; 这也正好对上用户那条「大道至简」。

## 不用未来数据

每一段都只用**那一段结束时**已经知道的东西:

  · 反应点只在聚焦点之前找(`reactions_before` 本身就是这个口径);
  · 容差用**那一段结束那根的 ATR**, 不是最后一根的 —— 拿今天的 ATR 去量
    三年前那一段, 等于把今天的波动率泄露回过去;
  · 实际回踩低点取的是那一段结束**之后**的行情, 那是被评估的答案, 不是输入。

## 最后一段不算数

它的回踩还没走完(甚至还没开始)—— 拿一段没结束的行情当答案, 算出来的是
"到目前为止的最低点", 会系统性地偏高。所以**只评估已经有完整回踩的那些段**,
并把样本数如实报出来: 一只票近几年可能只有五六次上攻, 样本太少就不给建议。
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import polars as pl

from app.indicators.dinapoli import (
    GRAINS, MAX_REACTIONS, TOL_ATR, cluster_zone, displaced_sma, focus_of,
    reactions_before, retracements, thrust_segments,
)

# 样本少于这个数就不给建议 —— 三次上攻里蒙对两次说明不了任何事。
MIN_SAMPLES = 3

# 两档命中率差在这个数以内, 就算"差不多", 这时选线更少的那一档。
# **这是一条写死的、读得懂的规则, 不是拟合出来的阈值** —— 它表达的是
# 「大道至简」: 同样准的两个方案, 取简单的那个。
TIE_BAND = 0.10


@dataclass
class GrainFit:
    """一档粗细在这只票上的表现。**全是可以数出来的量, 没有一个是收益。**"""
    grain: str
    k: int
    samples: int = 0            # 有完整回踩、能评估的上攻段数
    hits: int = 0               # 实际回踩低点落在某条回踩位上的次数
    zone_hits: int = 0          # 落在回踩密集带里的次数
    zones: int = 0              # 这些段里有多少段算得出密集带
    total_lines: int = 0        # 这些段一共画了多少条回踩位

    @property
    def hit_rate(self) -> float | None:
        return self.hits / self.samples if self.samples else None

    @property
    def zone_rate(self) -> float | None:
        """**分母是"算得出密集带的段数", 不是全部段数。**

        没有密集带的段, 它本来就没做出这个预测 —— 拿它当"没中"会把
        「这一档更少给出密集带」这件事记成"更不准", 那是两回事。
        """
        return self.zone_hits / self.zones if self.zones else None

    @property
    def avg_lines(self) -> float | None:
        return self.total_lines / self.samples if self.samples else None

    @property
    def per_line(self) -> float | None:
        """每条线的贡献 = 命中率 ÷ 平均线数。**防"线多蒙中"的那一下。**"""
        hr, al = self.hit_rate, self.avg_lines
        return hr / al if hr is not None and al else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "grain": self.grain, "k": self.k, "samples": self.samples,
            "hits": self.hits, "zone_hits": self.zone_hits, "zones": self.zones,
            "hit_rate": self.hit_rate, "zone_rate": self.zone_rate,
            "avg_lines": self.avg_lines, "per_line": self.per_line,
        }


@dataclass
class _Case:
    """一段上攻 + 它之后实际回踩到哪。"""
    seg_end: int
    focus: float
    low: float                  # 回踩实际最低点
    tol: float
    levels: list[dict] = field(default_factory=list)
    zone: dict | None = None


def pullback_low(
    highs: list[float], lows: list[float], seg_end: int, focus: float,
    next_seg_start: int | None, *, min_bars: int = 3,
) -> float | None:
    """这一段上攻之后, 行情实际回踩到的最低点。

    **窗口在哪结束**是这个回测里唯一需要定义的东西, 这里定的是:

      · 价格重新站上聚焦点(出现 `high > focus`)—— 回撤结束了, 后面是新的行情;
      · 或者下一段上攻开始 —— 同上;
      · 或者数据到头。

    **数据到头那一种要当心**: 窗口太短的话, "到目前为止的最低点"还没跌完,
    算出来会系统性偏高。所以不足 `min_bars` 根就返回 `None`(这一段不算数)。
    """
    n = min(len(highs), len(lows))
    start = seg_end + 1
    if start >= n:
        return None
    stop = n
    if next_seg_start is not None:
        stop = min(stop, next_seg_start)
    for j in range(start, stop):
        if highs[j] > focus:
            stop = j
            break
    if stop - start < min_bars:
        return None
    return min(lows[start:stop])


def _cases(df: pl.DataFrame, k: int) -> list[_Case]:
    closes = [float(x) for x in df["close"].to_list()]
    highs = [float(x) for x in df["high"].to_list()]
    lows = [float(x) for x in df["low"].to_list()]
    atr = ([None if x is None else float(x) for x in df["atr_14"].to_list()]
           if "atr_14" in df.columns else [None] * len(closes))

    dma = displaced_sma(closes, 3, 3)
    segs = thrust_segments(closes, dma, highs, lows, atr)
    out: list[_Case] = []
    for idx, seg in enumerate(segs):
        s, e = seg
        # **容差用这一段结束那根的 ATR** —— 用最后一根的等于把今天的波动率
        # 泄露回过去, 那会让老的那几段被一把更宽/更窄的尺子量。
        a = atr[e] if e < len(atr) else None
        if a is None or not math.isfinite(a) or a <= 0:
            continue
        tol = TOL_ATR * a
        focus, focus_bar = focus_of(highs, seg)
        reacts = reactions_before(lows, focus_bar, k=k,
                                  max_count=MAX_REACTIONS, min_gap=tol)
        if not reacts:
            continue                      # 画不出线的段评不了
        lv = retracements(focus, lows, reacts)
        if not lv:
            continue
        nxt = segs[idx + 1][0] if idx + 1 < len(segs) else None
        low = pullback_low(highs, lows, e, focus, nxt)
        if low is None:
            continue                      # 回踩还没走完 —— 最后一段通常落在这里
        out.append(_Case(seg_end=e, focus=focus, low=low, tol=tol,
                         levels=lv, zone=cluster_zone(lv, tol)))
    return out


def evaluate_grain(df: pl.DataFrame, grain: str, k: int) -> GrainFit:
    """一档粗细在这只票上画得准不准。"""
    fit = GrainFit(grain=grain, k=k)
    for c in _cases(df, k):
        fit.samples += 1
        fit.total_lines += len(c.levels)
        if any(abs(c.low - float(x["value"])) <= c.tol for x in c.levels):
            fit.hits += 1
        if c.zone:
            fit.zones += 1
            if c.zone["low"] - c.tol <= c.low <= c.zone["high"] + c.tol:
                fit.zone_hits += 1
    return fit


def backtest_grains(df: pl.DataFrame,
                    grains: dict[str, int] | None = None) -> list[GrainFit]:
    """三档各跑一遍。纯几何, 没有任何买卖规则。"""
    g = grains or GRAINS
    if df.is_empty() or not {"high", "low", "close"}.issubset(df.columns):
        return [GrainFit(grain=name, k=k) for name, k in g.items()]
    return [evaluate_grain(df, name, k) for name, k in g.items()]


def advise(fits: list[GrainFit]) -> dict[str, Any]:
    """按一条**写死的、读得懂的**规则给建议。

    规则就两句:

      1. **样本不够就不给建议。** 三次上攻里蒙对两次说明不了任何事 ——
         这一条比任何排序都重要, 六态那个回测也有同一条。
      2. **命中率差在 10 个百分点以内算"差不多", 这时选线更少的那一档。**
         它表达的是「大道至简」: 同样准的两个方案取简单的那个; 也顺手挡住
         "细档线多所以蒙得多"这条必然的捷径。

    **故意不做成加权评分。** 一个 0.4×命中率 + 0.3×带命中 + 0.3×线数 的公式
    看着科学, 实际上那几个权重是我编的, 而且没人能反驳也没人能复核 ——
    不如把两句话写在这儿, 你一眼能看出它凭什么这么选。
    """
    usable = [f for f in fits if f.samples >= MIN_SAMPLES and f.hit_rate is not None]
    if not usable:
        most = max((f.samples for f in fits), default=0)
        return {"grain": None,
                "reason": f"样本太少（最多的一档也只有 {most} 次可评估的上攻）——"
                          f"不够 {MIN_SAMPLES} 次, 给不出建议, 自己看图选一档。"}
    best = max(usable, key=lambda f: f.hit_rate or 0.0)
    # `- 1e-9`: 命中率是两个整数相除, `0.8 - 0.10` 在浮点里是 0.7000000000000001,
    # 于是**正好差 10 个百分点的那一档会被挤出"差不多"的范围** —— 而它恰恰是
    # 这条规则最该照顾到的边界。测试当场抓到的。
    close_ones = [f for f in usable
                  if (f.hit_rate or 0) >= (best.hit_rate or 0) - TIE_BAND - 1e-9]
    pick = min(close_ones, key=lambda f: f.avg_lines or 0.0)
    cn = {"coarse": "粗", "mid": "中", "fine": "细"}
    if pick is best or len(close_ones) == 1:
        reason = (f"「{cn.get(pick.grain, pick.grain)}」档命中率最高"
                  f"（{pick.samples} 次上攻里中 {pick.hits} 次）,"
                  f"平均每次画 {pick.avg_lines:.1f} 条。")
    else:
        reason = (f"「{cn.get(best.grain, best.grain)}」档命中率稍高, 但"
                  f"「{cn.get(pick.grain, pick.grain)}」档只差"
                  f"{abs((best.hit_rate or 0) - (pick.hit_rate or 0)) * 100:.0f} 个百分点, "
                  f"而平均每次少画 {(best.avg_lines or 0) - (pick.avg_lines or 0):.1f} 条 ——"
                  f"一样准就取线少的那个。")
    return {"grain": pick.grain, "reason": reason}
