"""[R473] 斐波那契Ⅱ型 —— **以用户给的那张对照图为准**。

用户拿别人的通达信图(中际旭创 300308)对比:「斐波那契Ⅱ型出来的结果不对…你要完美复刻
还原, 他的才是准确有效的」, 又补一句:「严格按照那个图, 那个图片的结果经过调试的,
一定对的」。拿不到对方源码, 下面每个期望值都是**从图上读下来的原数**, 不是我们自己
算出来再抄回去的 —— 这份守卫钉的是「给出图上那组低点和高点, 必须画出图上那几条线」。

图上读得到、且能逐位对上的:

    聚焦点                974.99            截图前一根大阴线的最高点(后面只剩当天一根)
    锚点(标 1.000)        858.00 / 836.13
    F3 = 38.2% 回撤       930.30 ← 858.00   921.95 ← 836.13
                          932.41 ← 863.52   934.95 ← 870.17(这两个锚点图上没标, 按同一公式反推)
    F5 = 61.8% 回撤       889.17 ← 836.13

图上的红框 / 红箭头是标注, 不是指标画的; 当天收 928.50。
"""
from __future__ import annotations

import polars as pl
import pytest

from app.indicators import dinapoli as dn

FOCUS = 974.99
# 这一波里的低点, 由远到近一个比一个高(互不覆盖)。827.74 是图上红色折线的起点
VALLEYS = [827.74, 836.13, 858.00, 863.52, 870.17]
# 图上的数(两位小数原样)
F3_ON_CHART = {930.30, 921.95, 932.41, 934.95}
F5_ON_CHART = {889.17}


def _chart_df(atr: float = 45.0) -> pl.DataFrame:
    """按图摆一份日 K: 五个谷一个比一个高, 然后冲到 974.99(倒数第二根), 当天收 928.50。

    每个谷左右各 5 根都更高 —— 粗档(k=5)也认得出, 三档都该画出同一组。
    ATR 取 45: 中际旭创这个价位的真实量级, 也正是旧门槛(3 倍 ATR)会卡住的那一档。
    """
    lows = [900.0] * 20
    for v in VALLEYS:
        lows += [v + 30, v + 20, v + 10, v + 5, v + 2, v, v + 2, v + 5, v + 10, v + 20]
    lows += [885, 900, 915, 930, 945, 955]
    highs = [x + 12 for x in lows]
    lows += [935.0, 918.0]
    highs += [FOCUS, 940.0]
    closes = [(h + lo) / 2 for h, lo in zip(highs, lows)]
    closes[-1] = 928.50
    return pl.DataFrame({"high": highs, "low": lows, "close": closes,
                         "atr_14": [atr] * len(lows)})


@pytest.mark.parametrize("grain", list(dn.GRAINS))
def test_R473_画出对照图上的每一条线(grain: str):
    res = dn.compute(_chart_df(), pivot_k=dn.GRAINS[grain])
    assert res.focus == FOCUS, f"[{grain}] 聚焦点是 {res.focus}, 图上是 {FOCUS}"
    shallow = {round(x["value"], 2) for x in res.levels if x["kind"] == "shallow"}
    deep = {round(x["value"], 2) for x in res.levels if x["kind"] == "deep"}
    assert F3_ON_CHART <= shallow, f"[{grain}] 图上的 F3 缺了 {sorted(F3_ON_CHART - shallow)}"
    assert F5_ON_CHART <= deep, f"[{grain}] 图上的 F5 缺了 {sorted(F5_ON_CHART - deep)}"


def test_R473_聚焦点不等摆点确认():
    """974.99 后面只有一根 —— 分形摆点要左右各 k 根, 等它确认就永远画不出这张图。"""
    df = _chart_df()
    res = dn.compute(df)
    assert res.focus_bar == df.height - 2


def test_R473_相隔五六块的低点各算各的():
    """858.00 / 863.52 / 870.17 各有一条 F3(930.30 / 932.41 / 934.95)。原来拿聚类容差
    (0.5×ATR ≈ 22)去重, 这三个会被并成一个, 图上那两条就没了。"""
    res = dn.compute(_chart_df())
    lows = [float(x) for x in _chart_df()["low"].to_list()]
    assert [lows[i] for i in res.reactions] == list(reversed(VALLEYS))


def test_R473_还在跌就不画():
    """最低点就是最后一根 = 这一波还没开始, 下跌里的回撤线不是机会(AGENTS.md 第 10 条)。"""
    closes = [100.0 - i for i in range(60)]
    df = pl.DataFrame({"high": [c + 1 for c in closes], "low": [c - 1 for c in closes],
                       "close": closes, "atr_14": [2.0] * 60})
    assert dn.compute(df).is_empty()


def _path(points: list[tuple[float, int]], atr: float = 45.0) -> pl.DataFrame:
    """按拐点连一条走势: [(价, 走几根到这里)...], 每根高低各 ±6。"""
    closes: list[float] = []
    prev = points[0][0]
    for price, bars in points:
        for j in range(1, bars + 1):
            closes.append(prev + (price - prev) * j / bars)
        prev = price
    return pl.DataFrame({"high": [c + 6 for c in closes], "low": [c - 6 for c in closes],
                         "close": closes, "atr_14": [atr] * len(closes)})


def test_R474_中间隔着一段下跌_聚焦点仍是最后一段上涨的顶():
    """[R474] 用户第二张截图(中际旭创, 现价 929.26): 走势是
    790(7 月底下影线) → 1050(8 月初) → 805(9 月初) → 974.99(9 月 22 日) → 929。
    R473 取「近 60 根最低点之后的最高点」, 会落到 8 月初的 1050; 对照图是 974.99。"""
    df = _path([(1000, 5), (790, 20), (1050, 8), (805, 20), (974.99, 15), (929, 1)])
    res = dn.compute(df)
    assert res.focus is not None and abs(res.focus - (974.99 + 6)) < 1e-6, \
        f"聚焦点 {res.focus} —— 应是最后一段上涨的顶, 不是 8 月初那个 1050"


def test_R474_下跌已跌破这段上涨的起点就不画():
    df = _path([(1000, 5), (790, 20), (1050, 8), (805, 20), (974.99, 15), (780, 15)])
    assert dn.compute(df).is_empty()


def test_R474_回踩没跌破起点_照样量这段上涨():
    """转成下跌波段、但还在这段上涨的起点之上 —— 那正是回踩在量它的时候。"""
    df = _path([(1000, 5), (790, 20), (1050, 8), (805, 20), (974.99, 15), (860, 8)])
    res = dn.compute(df)
    assert res.focus is not None and abs(res.focus - (974.99 + 6)) < 1e-6


def test_R475_大跌之后波动变大_仍认得出最近这一波():
    """[R475] 用户部署后发图:「好像还是不对, 是不是对方用了最近的」—— R474 选到了 7 月
    一段 4 天的小反弹。7、8 月大跌把 ATR 抬到八九十, 「2 倍 ATR 才算拐」的门槛一百六七十点,
    9 月 805 → 974.99(≈170)贴着门槛没被认出来。拐点门槛改成百分比之后必须认得出。"""
    df = _path([(600, 5), (1400, 40), (1100, 10), (1300, 10), (790, 25),
                (1050, 8), (805, 20), (974.99, 15), (930, 3)], atr=95.0)
    res = dn.compute(df)
    assert res.focus is not None and abs(res.focus - (974.99 + 6)) < 1e-6, \
        f"聚焦点 {res.focus} —— 应是最近这一波的顶 974.99"
