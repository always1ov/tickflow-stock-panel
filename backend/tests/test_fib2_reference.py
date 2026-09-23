"""[R473 → R476] 斐波那契Ⅱ型 —— **以用户给的那张对照图为准**。

用户拿别人的通达信图(中际旭创 300308)对比:「斐波那契Ⅱ型出来的结果不对…你要完美复刻
还原, 他的才是准确有效的」「严格按照那个图, 那个图片的结果经过调试的, 一定对的」「就只有
这张图了, 只能靠你推理出来了」。拿不到对方源码, 下面的期望值都是**从图上读下来的原数**。

对照图上能读到、且能逐位对上的(聚焦点 974.99, F3 = 38.2%、F5 = 61.8% 回撤):

    锚点(标 1.000)    F3                 F5
    858.00            930.30             902.69(被标注箭头盖住, 灰括号连着 930.30)
    836.13            921.95             889.17

读图时认错过的(R473 那一版的守卫就是照错的认识写的, R476 纠正):
  · 932.41 是**黑字**, 挨着蓝色折线上的红点 —— 那是 3×3 均线在那一点的值, 不是回撤线;
  · 827.74 / 844.59 挨着底下红色折线上的点 —— 也是均线值, 不是锚点;
  · 934.95 是 F3(下面标着 F3), 反推锚点 ≈870.17 —— 那是 858 之后那根大阳线的开盘价 / 最低价,
    既不是回调低点也不是上攻起点, **这一条目前没能解释, 不钉**。

锚点怎么挑(R476 从这张图推出来的):
  · 上攻段的底 = 上一次高过聚焦点以来的最低点(804.02, 9 月初那根下影线);
  · 上攻从底之后**第一根收回 3×3 均线上方**的那根算起 —— 836.13 正是那根大阳线的最低价;
  · 锚 = 上攻起点那根的低点 + 上攻段里回调的低点(858.00)。804、以及更早的 793 / 554 都在
    起点之前, 对照图上没有它们的线。
"""
from __future__ import annotations

import polars as pl
import pytest

from app.indicators import dinapoli as dn

FOCUS = 974.99
F3_ON_CHART = {930.30, 921.95}
F5_ON_CHART = {902.69, 889.17}
# 804.02 那一组(我们 R475 时画出来、对照图上没有的)
NOT_ON_CHART = {909.68, 869.33}


def _lin(a: float, b: float, n: int) -> list[float]:
    return [a + (b - a) * i / n for i in range(1, n + 1)]


# 截图(我们的图, 同一天)上按像素量出来的最后 19 根(开, 高, 低, 收); 锚点那几个换成对照图上的原数。
# 高点 974.99、当天收 928.50 也是对照图上的原数。
MEASURED = [
    (835.0, 862.8, 829.5, 851.3), (852.6, 885.8, 837.8, 859.0), (839.8, 847.4, 814.2, 822.5),
    (832.7, 835.3, 804.02, 812.9), (824.4, 834.0, 809.0, 813.5), (838.5, 901.2, 836.13, 898.0),
    (898.6, 933.2, 894.2, 901.8), (931.9, 933.2, 901.2, 908.9), (889.7, 908.2, 882.0, 890.5),
    (898.0, 928.1, 891.6, 925.5), (898.0, 928.1, 891.6, 925.5), (889.7, 894.2, 866.6, 873.0),
    (873.0, 882.6, 858.00, 863.4), (870.17, 915.0, 870.17, 909.0), (905.0, 927.0, 892.9, 897.0),
    (910.0, 946.0, 893.5, 925.6), (939.0, 958.7, 931.5, 940.5), (967.1, FOCUS, 921.0, 927.4),
    (935.8, 937.7, 918.5, 928.50),
]


def _chart_df() -> pl.DataFrame:
    """前面接一段 790 → 1050 → 850 的大结构(与截图一致), 再接量出来的 19 根。ATR 取 45。"""
    pre = [900.0] * 5 + _lin(900, 790, 10) + _lin(790, 1050, 8) + _lin(1050, 850, 12)
    rows = [(c, c + 8, c - 8, c) for c in pre] + MEASURED
    return pl.DataFrame({"open": [r[0] for r in rows], "high": [r[1] for r in rows],
                         "low": [r[2] for r in rows], "close": [r[3] for r in rows],
                         "atr_14": [45.0] * len(rows)})


@pytest.mark.parametrize("grain", list(dn.GRAINS))
def test_R476_画出对照图上的每一条线(grain: str):
    res = dn.compute(_chart_df(), pivot_k=dn.GRAINS[grain])
    assert res.focus == FOCUS, f"[{grain}] 聚焦点是 {res.focus}, 图上是 {FOCUS}"
    shallow = {round(x["value"], 2) for x in res.levels if x["kind"] == "shallow"}
    deep = {round(x["value"], 2) for x in res.levels if x["kind"] == "deep"}
    assert F3_ON_CHART <= shallow, f"[{grain}] 图上的 F3 缺了 {sorted(F3_ON_CHART - shallow)}"
    assert F5_ON_CHART <= deep, f"[{grain}] 图上的 F5 缺了 {sorted(F5_ON_CHART - deep)}"


@pytest.mark.parametrize("grain", list(dn.GRAINS))
def test_R476_上攻起点之前的低点不当锚(grain: str):
    """804.02 在上攻起点(第一根收回 3×3 均线上方那根)之前 —— 对照图上没有它的 909.68 / 869.33。"""
    res = dn.compute(_chart_df(), pivot_k=dn.GRAINS[grain])
    got = {round(x["value"], 2) for x in res.levels}
    assert not (got & NOT_ON_CHART), f"[{grain}] 画出了对照图上没有的 {sorted(got & NOT_ON_CHART)}"
    lows = [float(x) for x in _chart_df()["low"].to_list()]
    assert sorted(lows[i] for i in res.reactions) == [836.13, 858.00]


@pytest.mark.parametrize("grain", list(dn.GRAINS))
def test_R477_密集带只圈真挤在一起的那两条(grain: str):
    """[R477] 用户看了 R476 部署后的图(889~930 被连成一整块):「肯定要处理啊」。
    按价格 1% 聚类: 921.95 / 930.30(相距 0.9%, 两个锚量出同一处 —— 用户在对照图上画红框
    的那一带)归一块; 902.69 / 889.17(1.5%)不算。「这组作废」跟着落到 902.69 下方。"""
    res = dn.compute(_chart_df(), pivot_k=dn.GRAINS[grain])
    z = res.zone
    assert z is not None and (round(z["low"], 2), round(z["high"], 2)) == (921.95, 930.30), \
        f"[{grain}] 密集带是 {z}"
    assert z["strength"] == 2
    assert res.invalid_at is not None and 889.17 < res.invalid_at < 902.69, \
        f"[{grain}] 这组作废 {res.invalid_at} 应在 902.69 下方、889.17 上方"


def test_R473_聚焦点不等摆点确认():
    """974.99 后面只有一根 —— 分形摆点要左右各 k 根, 等它确认就永远画不出这张图。"""
    df = _chart_df()
    assert dn.compute(df).focus_bar == df.height - 2


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
