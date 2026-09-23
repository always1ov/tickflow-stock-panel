"""[R405] 斐波那契二型的**地基**: 摆点 / 推进段 / 聚焦点 / 聚类。

规格第 1 节自己写明:「原书对『有意义的摆点』没有硬公式, 这里用分形摆点补定
规则, **是全套系统中最需要校准的部分**」。FOCUS 认错一根, 上面所有回撤线和
目标全是错的 —— 所以这一层每一步都单独喂手工数据验, 而不是等到出图才看。

**每条用例的期望值都是手算的**, 写在断言旁边。用真实行情跑出来的数当期望值
等于把当时的 bug 一起钉住, 这仓库栽过那一族。
"""
from __future__ import annotations

import math

import polars as pl

from app.indicators import dinapoli as dn


# ================================================================
# 位移均线
# ================================================================

def test_R405_位移均线是往后移不是往前看():
    """SMA(3) 往后移 3 根。**移过去的值都是已收盘数据算的**, 不是未来函数。"""
    vals = [1.0, 2.0, 3.0, 10.0, 20.0, 30.0, 40.0]
    out = dn.displaced_sma(vals, 3, 3)
    #  前 5 个位置没有值: 下标 0..2 连 SMA 都不够, 3..4 是移位留出的空档
    assert out[:5] == [None] * 5
    # 下标 5 = SMA(vals[0..2]) = (1+2+3)/3 = 2.0
    assert out[5] == 2.0
    # 下标 6 = SMA(vals[1..3]) = (2+3+10)/3 = 5.0
    assert out[6] == 5.0


def test_R405_露到最后一根之外的那几个值():
    """图上「未来」区那一段 —— 今天就已经算得出来。"""
    vals = [1.0, 2.0, 3.0, 10.0, 20.0, 30.0, 40.0]
    fut = dn.future_dma(vals, 3, 3)
    # 末尾三根分别由 vals[2..4]、vals[3..5]、vals[4..6] 算出
    assert fut == [11.0, 20.0, 30.0]


def test_R405_数据不够时不瞎猜():
    assert dn.displaced_sma([1.0, 2.0], 3, 3) == [None, None]
    assert dn.future_dma([1.0, 2.0], 3, 3) == []


# ================================================================
# 分形摆点
# ================================================================

def test_R405_分形低点两端各留k根不判():
    #        0    1    2    3    4    5    6
    lows = [5.0, 4.0, 3.0, 1.0, 3.0, 4.0, 5.0]
    # k=3: 只有下标 3 可判(两端各留 3 根), 它确实是窗口最小
    assert dn.pivot_lows(lows, k=3) == [3]
    # k=1: 下标 1..5 可判, 只有 3 是局部最小
    assert dn.pivot_lows(lows, k=1) == [3]


def test_R405_分形高点与低点镜像():
    highs = [1.0, 2.0, 3.0, 9.0, 3.0, 2.0, 1.0]
    assert dn.pivot_highs(highs, k=3) == [3]
    assert dn.pivot_highs(highs, k=1) == [3]


def test_R405_平台上的相等值也算摆点_不是漏判():
    """用 `==` 而不是 `>` 是有意的: 一段平底也是低点。

    **这一条钉的是取舍本身** —— 改成严格不等会把所有平台形态整个漏掉,
    而 A 股里一字板、横盘平台非常常见。
    """
    lows = [5.0, 2.0, 2.0, 2.0, 5.0]
    assert dn.pivot_lows(lows, k=1) == [1, 2, 3]


# ================================================================
# 推进段
# ================================================================

def _thrust_case(closes, dma, highs, lows, atr, **kw):
    return dn.thrust_segments(closes, dma, highs, lows, atr, **kw)


def test_R405_推进段要够长():
    closes = [10.0] * 10
    dma = [9.0] * 10                       # 全程 C > DMA
    highs = [12.0] * 10
    lows = [8.0] * 10
    atr = [1.0] * 10
    # 长度 10 >= 8, 幅度 12-8=4 >= 3×1 → 成立
    assert _thrust_case(closes, dma, highs, lows, atr) == [(0, 9)]
    # 把门槛抬到 11 根 → 不成立
    assert _thrust_case(closes, dma, highs, lows, atr, min_len=11) == []


def test_R405_磨盘被幅度门槛滤掉():
    """连着站在均线上方**不等于**一波推进 —— 横着走的一串小阳线也满足。"""
    closes = [10.0] * 10
    dma = [9.9] * 10
    highs = [10.1] * 10
    lows = [9.9] * 10                      # 幅度只有 0.2
    atr = [1.0] * 10                       # 3×ATR = 3.0, 远够不着
    assert _thrust_case(closes, dma, highs, lows, atr) == []


def test_R405_跌回均线下方就断段():
    closes = [10.0] * 5 + [8.0] + [10.0] * 9
    dma = [9.0] * 15
    highs = [12.0] * 15
    lows = [8.0] * 15
    atr = [1.0] * 15
    # 下标 5 跌回下方 → 前段只有 5 根(不够 8), 后段 6..14 共 9 根成立
    assert _thrust_case(closes, dma, highs, lows, atr) == [(6, 14)]


def test_R405_ATR缺失时不硬算():
    closes = [10.0] * 10
    dma = [9.0] * 10
    assert _thrust_case(closes, dma, [12.0] * 10, [8.0] * 10, [None] * 10) == []


# ================================================================
# 聚焦点与反应点
# ================================================================

def test_R405_聚焦点取推进段内最高():
    highs = [1.0, 5.0, 9.0, 7.0, 3.0]
    assert dn.focus_of(highs, (1, 3)) == (9.0, 2)


def test_R405_反应点必须其后没被更低点盖住():
    """这是帝纳波利挑反应点的关键一条。

    下标 2 是个分形低点(值 3), 但下标 6 更低(值 1) —— 到 focus 之前它已经被
    盖住了, **不能再拿它量回撤**, 因为那一段的起点早就换人了。
    """
    #        0    1    2    3    4    5    6    7    8    9   10   11
    lows = [9.0, 8.0, 3.0, 8.0, 9.0, 8.0, 1.0, 8.0, 9.0, 9.0, 9.0, 9.0]
    focus_bar = 11
    got = dn.reactions_before(lows, focus_bar, k=1, max_count=5)
    # 下标 6(值 1)保留; 下标 2(值 3)其后有更低的 1, 剔除
    assert 6 in got
    assert 2 not in got


def test_R405_反应点由近到远且有上限():
    """**台阶式上涨**才会有一串合格的反应点 —— 每个谷底都比前一个高,
    所以谁也没被后面更低的点盖住。

    (第一版用例写成一路走低, 断言了 3 个反应点 —— **是用例错不是代码错**:
    单调下跌里根本不存在分形低点, 每一根右边都有更低的。这一条顺带说明了
    一件对的事: **下跌途中出不来做多的反应点**, 与「逆势的机会一律不给」
    正好同向。)
    """
    #        0    1    2    3    4    5     6    7     8     9
    lows = [5.0, 4.0, 5.0, 8.0, 6.0, 8.0, 12.0, 9.0, 12.0, 20.0]
    got = dn.reactions_before(lows, focus_bar=9, k=1, max_count=3)
    assert got == [7, 4, 1], f"应当由近到远取到三个谷底, 实际 {got}"
    assert got == sorted(got, reverse=True), "反应点该由近到远"
    # 上限真的起作用
    assert dn.reactions_before(lows, focus_bar=9, k=1, max_count=2) == [7, 4]


def test_R405_横盘平台上的反应点只算一个():
    """**这一条是冒烟时抓出来的真 bug, 不是补测试。**

    一段横盘里每一根都是分形低点、而且全都满足"其后没有更低", 于是五个反应点
    挤在同一个价位上, 量出五条**完全一样**的回撤线 —— 聚类一看"五条重合",
    报了个 `strength=5` 的强支撑区。那是**同一条线数了五遍**, 而这个读数的
    全部意义恰恰是"几段不同的行情指到同一处"。A 股的平台、一字板天天触发它。
    """
    #        0    1    2    3    4    5    6    7     8
    lows = [9.0, 5.0, 9.0, 5.0, 9.0, 5.0, 9.0, 5.0, 20.0]
    # 不去重: 四个等价低点全收
    assert len(dn.reactions_before(lows, 8, k=1, min_gap=0.0)) == 4
    # 去重(容差 0.5): 它们价位相同, 只留最近的那个
    assert dn.reactions_before(lows, 8, k=1, min_gap=0.5) == [7]


def test_R405_去重只按价位不按根数():
    """价位真的拉开了就各算各的 —— 去重不该把有信息的反应点也吃掉。"""
    #        0     1    2    3    4    5     6
    lows = [9.0, 3.0, 9.0, 6.0, 9.0, 8.0, 20.0]
    got = dn.reactions_before(lows, 6, k=1, min_gap=0.5)
    assert got == [5, 3, 1], f"三个价位各不相同, 都该留下, 实际 {got}"


def test_R405_下跌途中没有合格的反应点():
    """单调下跌里每一根右边都有更低的, 一个分形低点都不存在 ——
    也就不会给出做多的回撤位。这与「逆势的『机会』一律不给」同向。"""
    lows = [10.0 - i * 0.5 for i in range(20)]
    assert dn.pivot_lows(lows, k=1) == []
    assert dn.reactions_before(lows, focus_bar=19, k=1) == []


# ================================================================
# 回撤位 / 目标位
# ================================================================

def test_R405_回撤比例是原书那两个固定值():
    lows = [0.0] * 5
    lows[1] = 10.0
    out = dn.retracements(20.0, lows, [1])
    # span = 20 − 10 = 10; 浅 = 20 − 3.82 = 16.18; 深 = 20 − 6.18 = 13.82
    assert [round(x["value"], 2) for x in out] == [16.18, 13.82]
    assert [x["kind"] for x in out] == ["shallow", "deep"]


def test_R405_目标锚在回撤低点上_不是锚在聚焦点上():
    """回撤越深目标越低 —— 这是这套算法自带的保守性, 不许"优化"掉。"""
    # A=10, B=20 → span=10;  C=15 时
    out = dn.targets_from(10.0, 20.0, 15.0)
    assert [round(x["value"], 2) for x in out] == [21.18, 25.0, 31.18]
    # C 更低(回撤更深)→ 三个目标同步下移
    lower = dn.targets_from(10.0, 20.0, 12.0)
    assert all(l["value"] < h["value"] for l, h in zip(lower, out))


def test_R405_波段方向不对就不出目标():
    assert dn.targets_from(20.0, 10.0, 15.0) == []


# ================================================================
# 聚类 —— 界面上那句「N 条回撤重合」的来源
# ================================================================

def _lv(k, value, kind="deep"):
    return {"k": k, "bar": 0, "kind": kind, "value": value}


def test_R405_同一个反应点的两条不算重合():
    """浅/深本来就离得远; 真正有意义的是**两段不同的行情量出同一个位置**。"""
    levels = [_lv(1, 10.0, "shallow"), _lv(1, 10.05, "deep")]
    assert dn.cluster_zone(levels, tol=0.5) is None


def test_R405_不同反应点挤在一起才是强支撑区():
    levels = [_lv(1, 10.0), _lv(2, 10.2), _lv(3, 10.3), _lv(4, 20.0)]
    zone = dn.cluster_zone(levels, tol=0.5)
    assert zone is not None
    assert zone["strength"] == 3
    assert (zone["low"], zone["high"]) == (10.0, 10.3)


def test_R405_容差之外不并组():
    levels = [_lv(1, 10.0), _lv(2, 12.0)]
    assert dn.cluster_zone(levels, tol=0.5) is None


def test_R405_重合多的那一组胜出():
    levels = [_lv(1, 10.0), _lv(2, 10.1),
              _lv(3, 30.0), _lv(4, 30.1), _lv(5, 30.2)]
    zone = dn.cluster_zone(levels, tol=0.5)
    assert zone["strength"] == 3 and zone["low"] == 30.0


# ================================================================
# 失效位
# ================================================================

def test_R405_失效位取区下方最近的那条再让一点():
    levels = [_lv(1, 9.0), _lv(2, 8.0), _lv(3, 10.0)]
    # zone_low=10, tol=0.5 → 低于 9.5 的有 9.0 与 8.0, 取最大的 9.0
    got = dn.invalidation_price(levels, zone_low=10.0, tol=0.5, atr=1.0, fallback=5.0)
    assert math.isclose(got, 9.0 - 0.1)


def test_R405_下方没有回撤位时退回主波段起点():
    levels = [_lv(1, 10.0)]
    got = dn.invalidation_price(levels, zone_low=10.0, tol=0.5, atr=1.0, fallback=5.0)
    assert math.isclose(got, 5.0 - 0.1)


# ================================================================
# 首次回踩
# ================================================================

def test_R405_首次回踩是推进结束后第一次收盘跌回均线下方():
    closes = [10.0] * 6 + [9.0, 8.0]
    dma = [9.5] * 8
    assert dn.first_pullback_after(closes, dma, thrust_end=5) == 6


def test_R405_一直没跌回就没有这个标记():
    closes = [10.0] * 8
    dma = [9.5] * 8
    assert dn.first_pullback_after(closes, dma, thrust_end=5) is None


# ================================================================
# 总入口的兜底
# ================================================================

def test_R405_数据不够或缺列一律返回空而不抛():
    assert dn.compute(pl.DataFrame()).is_empty()
    short = pl.DataFrame({"high": [1.0], "low": [1.0], "close": [1.0]})
    assert dn.compute(short).is_empty()
    no_col = pl.DataFrame({"close": [1.0] * 40})
    assert dn.compute(no_col).is_empty()


def test_R405_没有推进段时不出任何位置():
    n = 60
    df = pl.DataFrame({
        "high": [10.1] * n, "low": [9.9] * n, "close": [10.0] * n,
        "atr_14": [1.0] * n,
    })
    res = dn.compute(df)
    assert res.is_empty() and res.levels == [] and res.targets == []


def test_R405_一波像样的上攻能走通全程():
    """横盘 30 根 → 拉升 12 根 → 回撤 8 根。手工构造, 期望值按定义推。"""
    base = [10.0] * 30
    up = [10.0 + i * 0.8 for i in range(1, 13)]        # 10.8 → 19.6
    down = [19.6 - i * 0.5 for i in range(1, 9)]       # 回撤
    closes = base + up + down
    highs = [c + 0.2 for c in closes]
    lows = [c - 0.2 for c in closes]
    df = pl.DataFrame({"high": highs, "low": lows, "close": closes,
                       "atr_14": [0.5] * len(closes)})
    res = dn.compute(df)
    assert not res.is_empty(), "这么明显的一波都认不出来"
    assert res.thrust is not None and res.thrust[1] >= 30
    assert res.focus is not None and res.focus > 19.0
    assert res.reactions, "拉升之前应当找得到反应点"
    assert res.levels, "有反应点就该有回撤位"
    # 回撤位必须落在 反应点低 与 FOCUS 之间
    for x in res.levels:
        assert lows[x["bar"]] < x["value"] < res.focus
    # 目标必须在 FOCUS 之上(往上推算)
    for t in res.targets:
        assert t["value"] > res.focus * 0.99
    assert res.first_pullback_bar is not None, "回撤了却没标出首次回踩"


def test_R405_出线格式与其余价位组同构():
    # [R476] 59 根(原来 60): 最后一根低 10.4, 跌破了上攻起点那根(低 10.6), 按 R476 整组作废
    n = 59
    closes = [10.0] * 30 + [10.0 + i * 0.8 for i in range(1, 13)] + \
             [19.6 - i * 0.5 for i in range(1, 19)]
    closes = closes[:n]
    df = pl.DataFrame({
        "high": [c + 0.2 for c in closes], "low": [c - 0.2 for c in closes],
        "close": closes, "atr_14": [0.5] * n,
    })
    res = dn.compute(df)
    out = dn.to_levels(res, closes[-1])
    assert out, "算出来了却没转成横线"
    for p in out:
        # `color` 是这一组独有的: 一组里有三种意思不同的线(回撤/目标/失效位),
        # 全涂成组颜色等于把三件事说成一件。别的组不带这个字段。
        assert set(p) == {"value", "label", "type", "side", "strength", "color"}
        assert p["type"] == "fib2"
        assert p["side"] in ("resistance", "support", "neutral")
        assert p["value"] > 0
        assert p["color"].startswith("#")
    # 同一个价位不重复画
    assert len({p["value"] for p in out}) == len(out)


def test_R405_三种意思不同的线用三种颜色():
    """规格 §12:「每种颜色全站只表达一种含义」。回踩位/推算位/作废线是三件事。

    [R410] **分类改成按几何来源, 不按标签文字。** 原来是拿 `label.startswith("目标")`
    之类去分的 —— 那样一改名(而名字确实改了一轮)断言就落空, 而且落空的方式是
    "所有线都被归进同一类", 于是"每类只有一种颜色"永远成立, **测试变绿而洞还在**。
    现在直接问 `Fib2` 那个结果对象: 哪些值是回踩位、哪些是推算位、哪个是作废线。
    """
    # [R410] **换了一份数据**, 因为原来那份根本出不了作废线(没有密集带就没有
    # 作废线), 于是这条断言一直只覆盖了三类里的两类, 而且是**绿着漏的** ——
    # 分类拿不到的那一类不会报错, 只会不出现在结果里。这份是搜出来的:
    # 上攻途中有两次浅回调, 两条回踩位挤到一起形成密集带, 三类线齐全。
    closes = [10.0] * 30 + [
        9.6, 10.6, 11.6, 11.2, 12.2, 13.1, 12.6, 12.2, 13.1, 14.1, 15.0,
        14.7, 14.2, 13.9, 14.9, 14.5, 15.4, 16.3, 15.8, 15.4, 15.1, 14.8,
        14.3, 14.0, 13.3, 12.6, 12.1, 11.8, 11.1,
        # [R473→R476] 尾巴截在 11.1: 原来一路跌到 7.1。R476 起上攻从第一根收回 3×3 均线
        # 上方的那根(低 10.4)算起, 跌回它下方 = 整组作废不画 —— 这份数据要测的是强弱 / 颜色
    ]
    n = len(closes)
    df = pl.DataFrame({
        "high": [c + 0.2 for c in closes], "low": [c - 0.2 for c in closes],
        "close": closes, "atr_14": [0.5] * n,
    })
    res = dn.compute(df)
    out = dn.to_levels(res, closes[-1])
    kinds: dict[float, str] = {}
    for x in res.levels:
        kinds[round(float(x["value"]), 2)] = "回踩位"
    for t in res.targets:
        kinds[round(float(t["value"]), 2)] = "推算位"
    if res.invalid_at is not None:
        kinds[round(float(res.invalid_at), 2)] = "作废线"
    assert len(set(kinds.values())) == 3, f"这份数据没同时出三类线, 测不出东西: {kinds}"
    by = {}
    for p in out:
        kind = kinds[round(float(p["value"]), 2)]
        by.setdefault(kind, set()).add(p["color"])
    assert len(by) == 3, f"三类线没都画出来: {sorted(by)}"
    for kind, colors in by.items():
        assert len(colors) == 1, f"「{kind}」自己就用了多种颜色: {colors}"
    assert len({next(iter(c)) for c in by.values()}) == len(by), \
        f"三种线撞了颜色: {by}"
    # K 线是红涨绿跌 —— 价位线一律不用红绿
    for p in out:
        assert p["color"].lower() not in ("#ff0000", "#00ff00")


def test_R405_界面用词是白话_不露原术语():
    """规格第 12 节的对照表: 界面一律白话, F3/F5/COP/OP/XOP 只留在代码里。"""
    # [R476] 59 根(原来 60): 最后一根低 10.4, 跌破了上攻起点那根(低 10.6), 按 R476 整组作废
    n = 59
    closes = [10.0] * 30 + [10.0 + i * 0.8 for i in range(1, 13)] + \
             [19.6 - i * 0.5 for i in range(1, 19)]
    closes = closes[:n]
    df = pl.DataFrame({
        "high": [c + 0.2 for c in closes], "low": [c - 0.2 for c in closes],
        "close": closes, "atr_14": [0.5] * n,
    })
    out = dn.to_levels(dn.compute(df), closes[-1])
    blob = " ".join(p["label"] for p in out)
    for jargon in ("F3", "F5", "COP", "OP", "XOP", "Fib", "斐波那契", "DiNapoli"):
        assert jargon not in blob, f"界面标签里露了原术语: {jargon}"


# ================================================================
# [R406] 粗细档 —— 旋钮必须真的拧得动
# ================================================================

def test_R406_三档是三个不同的粗细():
    assert dn.GRAINS == {"coarse": 5, "mid": dn.PIVOT_K, "fine": 2}
    assert len(set(dn.GRAINS.values())) == 3, "三档撞值了, 等于只有两档"


def test_R406_旋钮真的拧得动():
    """**这条防的是"假旋钮"** —— 界面上给了三个按钮, 切来切去图上不变,
    那比没有这个按钮更坏(用户会以为自己已经试过粗细了)。

    数据是刻意构造的: 下标 8 那个 6.5 在 ±2 的窗口里是最低, 但 ±5 的窗口里
    有下标 5 的 6.0 更低 —— 所以它只在「细」档才算一个回调。
    """
    #        0     1     2     3     4    5    6    7    8    9   10    11    12    13    14
    lows = [10.0, 10.0, 10.0, 10.0, 10.0, 6.0, 7.0, 8.0, 6.5, 8.0, 9.0, 10.0, 11.0, 12.0, 20.0]
    got = {name: dn.reactions_before(lows, 14, k=k, min_gap=0.0)
           for name, k in dn.GRAINS.items()}
    assert got["coarse"] == [5], got
    assert got["fine"] == [8, 5], got
    assert len({tuple(v) for v in got.values()}) > 1, "三档给出同一个结果 = 假旋钮"


def test_R406_越细认得越多_方向不许反():
    """粗 = 只认大级别回调(少而稳), 细 = 小回调也算(多而密)。
    这是旋钮的**语义**, 反了的话界面上那两句说明就成了假话。"""
    lows = [10.0, 10.0, 10.0, 10.0, 10.0, 6.0, 7.0, 8.0, 6.5, 8.0, 9.0, 10.0, 11.0, 12.0, 20.0]
    n = {name: len(dn.reactions_before(lows, 14, k=k, min_gap=0.0))
         for name, k in dn.GRAINS.items()}
    assert n["coarse"] <= n["mid"] <= n["fine"], f"档位方向反了: {n}"


def test_R406_平滑趋势里三档一样是对的_不是旋钮坏了():
    """**这一条是留给下一个人的。**

    一段干净的台阶式上涨里, 浅回调要么不存在、要么后来被更低的点盖住了 ——
    于是粗细三档给出同一批反应点。那时候切档图上不变, **是对的**,
    不要当成接线断了去"修"。旋钮咬不咬得住, 取决于有没有"浅且没被盖过"的回调。
    """
    # 三段干净的 V 型: 每条腿都是严格单调(没有平台), 谷底彼此隔开 6 根以上 ——
    # 于是连最粗的档也认得出这三个谷底, 而最细的档也找不出第四个。
    def leg(a: float, b: float, n: int) -> list[float]:
        return [a + (b - a) * i / (n - 1) for i in range(1, n)]
    lows = ([12.0] + leg(12, 7, 7) + leg(7, 14, 9) + leg(14, 9, 7)
            + leg(9, 17, 9) + leg(17, 12, 7) + leg(12, 25, 9))
    got = {name: dn.reactions_before(lows, len(lows) - 1, k=k, min_gap=0.0)
           for name, k in dn.GRAINS.items()}
    assert len({tuple(v) for v in got.values()}) == 1, f"这份数据本该三档一致: {got}"
    assert len(got["mid"]) == 3, f"三个谷底应当都认得出来: {got['mid']}"


def test_R406_compute也真的吃这个参数():
    """接线断了的典型样子: 参数收下了但没往下传。"""
    import polars as pl
    # `compute` 要求至少 30 根 —— 第一版只给了 25 根, 三档一起返回空, 断言当场红。
    # **是用例错不是接线错**, 记在这儿免得下次又照着改代码。
    # [R476] 换数据: 锚只在上攻段里找之后, 原来那份的回调(6.5)落在上攻起点之前, 三档一样。
    # 这份在上攻途中放了一个只有细档认得出的小回调(11.3)。
    lows = ([10.0] * 5 + [6.0, 7.0, 8.0, 6.5, 8.0, 9.0]
            + [9.6, 10.2, 9.8, 10.8, 11.4, 12.0, 11.3, 12.6, 13.2, 13.8, 14.4, 13.9,
               15.0, 15.6, 16.2, 16.8, 17.4, 18.0, 18.6, 19.2, 19.8, 20.4])
    closes = [x + 0.3 for x in lows]
    n = len(closes)
    df = pl.DataFrame({"high": [c + 0.2 for c in closes], "low": lows,
                       "close": closes, "atr_14": [0.4] * n})
    got = {name: dn.compute(df, pivot_k=k).reactions for name, k in dn.GRAINS.items()}
    assert len({tuple(v) for v in got.values()}) > 1, \
        f"compute() 没把 pivot_k 往下传, 三档结果一样: {got}"
