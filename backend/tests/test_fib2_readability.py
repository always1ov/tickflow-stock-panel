"""[fork R410] 斐波那契二型「看得懂 / 抓得住」的那几条。

用户: 「目标1目标2失效位这些表达没能让用户抓得住重点看得懂, 而且好多根线,
好难抓住之前说的做不做在哪里做, 走不走这些」。

R405 把这一组做出来时把重点放在**算得对**上, 界面名照着规格的对照表抄了一遍
就算完了 —— 结果是: 名字是中文的, 但没有一个回答"这条线是干嘛的"; 线是算对
的, 但一次画将近二十根, 该看的那几条淹在里面。

这份守卫钉的是**"重点还在不在"**, 不是"名字叫什么":

  · 挤在一起的那几条必须被标成 strong, 落单的必须是 weak —— 帝纳波利这套东西
    的全部意思就在"几条挤在一起", 强弱不表达出来就等于让用户自己去数;
  · 作废线必须是 strong —— 它是「走不走」的下界;
  · 默认档必须是最粗那一档, 推算位默认必须不画 —— 这两条是"让图先安静下来";
  · 开关上的数必须如实说藏了几条 —— 减线最坏的结果不是少看了几条, 是**用户
    以为这一档就这么多线**。
"""
from __future__ import annotations

import re

import polars as pl

from app.indicators import dinapoli as dn
from tests.frontend_source import code_lines, read_src

CHART = "components/stock-analysis/AnalysisKChart.tsx"
# [R430] 开关状态与每类的计数从图里提了出来(个股弹窗的右侧列表与图共用), 默认值与
# 「藏了几条」的说法现在都在这里; 两排开关各自只剩「按整档判断能不能点」。
CTL = "components/stock-analysis/levelControls.ts"
SIDE = "components/stock-analysis/LevelToolbar.tsx"   # [R432] 右侧列表撤了, 方形按钮那排回到图上方

# 上攻途中两次浅回调 → 两条回踩位挤成密集带 → 三类线齐全的一份数据。
# (与 `test_dinapoli_pivots` 里那份同源, 那边记着它是怎么搜出来的。)
CLOSES = [10.0] * 30 + [
    9.6, 10.6, 11.6, 11.2, 12.2, 13.1, 12.6, 12.2, 13.1, 14.1, 15.0,
    14.7, 14.2, 13.9, 14.9, 14.5, 15.4, 16.3, 15.8, 15.4, 15.1, 14.8,
    14.3, 14.0, 13.3, 12.6, 12.1, 11.8, 11.1, 10.6, 10.1,
    # [R473] 尾巴截在 10.1: 原来一路跌到 7.1(低于这波起点 9.4), 按「最近一波上涨」
    # 口径那叫还在跌、不画 —— 这份数据要测的是强弱 / 颜色, 不是选哪一波
]


def _res():
    n = len(CLOSES)
    df = pl.DataFrame({
        "high": [c + 0.2 for c in CLOSES], "low": [c - 0.2 for c in CLOSES],
        "close": CLOSES, "atr_14": [0.5] * n,
    })
    return dn.compute(df)


def test_R410_挤在一起的画强_落单的画弱():
    """强弱不再是"全都 medium" —— 让粗细浓淡直接把"哪几条挤在一起"说出来。"""
    res = _res()
    assert res.zone, "这份数据本该出密集带, 出不来就测不到东西"
    # 带半分容差 —— 出去的值四舍五入到分, 带的上下沿没有。理由写在 `to_levels`。
    lo, hi = res.zone["low"] - 0.005, res.zone["high"] + 0.005
    out = dn.to_levels(res, CLOSES[-1])
    retr = [p for p in out if p["color"] == dn.C_RETR]
    assert retr, "一条回踩位都没有"
    inside = [p for p in retr if lo <= p["value"] <= hi]
    outside = [p for p in retr if not (lo <= p["value"] <= hi)]
    assert inside, "密集带里一条回踩位都没有 —— 那这个带是凭空画的"
    assert outside, "全都在带里的话这条断言测不出强弱之分"
    for p in inside:
        assert p["strength"] == "strong", f"带里的 {p['value']} 标成了 {p['strength']}"
    for p in outside:
        assert p["strength"] == "weak", f"落单的 {p['value']} 标成了 {p['strength']}"


def test_R410_作废线是强的():
    """它是「走不走」的下界, 不能和一条落单的回踩位一样淡。"""
    out = dn.to_levels(_res(), CLOSES[-1])
    inv = [p for p in out if p["color"] == dn.C_INVALID]
    assert inv, "没出作废线"
    assert all(p["strength"] == "strong" for p in inv)


def test_R410_界面上不出现原书术语():
    """**钉的是"没有黑话漏出去", 不是某个名字叫什么。**

    名字改过一轮(还会再改), 逐字钉名字的断言下次改名只会被顺手放宽。
    真正不许发生的是 F3/COP/XOP 这种只有读过原书的人才懂的词出现在界面上。
    """
    out = dn.to_levels(_res(), CLOSES[-1])
    labels = [p["label"] for p in out]
    for jargon in ("F3", "F5", "COP", "OP", "XOP", "FOCUS", "DMA"):
        assert not any(jargon in x for x in labels), f"「{jargon}」漏到界面了: {labels}"
    for x in labels:
        assert not re.search(r"R\d", x), \
            f"标签里还带着摆点编号「{x}」—— 那个数对看盘的人没有意义"


def test_R410_默认档是最粗的那一档():
    """用户: 「好多根线」。默认给最少的那一档, 想看细的自己点。

    **不钉字面量 `'coarse'`, 钉"它是 GRAINS 里最粗的那个"** —— 改档名或者加
    一档都不该让这条哑掉。
    """
    code = code_lines(read_src(CTL))
    m = re.search(r"useState<Fib2Grain>\('(\w+)'\)", code)
    assert m, "读不出默认档"
    coarsest = max(dn.GRAINS, key=lambda k: dn.GRAINS[k])
    assert m[1] == coarsest, f"默认档是 {m[1]}, 而最粗的那一档是 {coarsest}"


def test_R410_推算位默认不画():
    """它们回答「涨上去会路过哪」, 与当下的「在哪里做 / 走不走」无关。"""
    code = code_lines(read_src(CTL))
    m = re.search(r"const \[fib2ShowTargets, setFib2ShowTargets\] = useState\((\w+)\)", code)
    assert m, "推算位那个开关读不出来"
    assert m[1] == "false", "推算位又变成默认画了"


def test_R410_推算位是按角色键过滤的_不是按标签文字():
    """按文字挑的话, 后端改一次界面名前端就会**静默**漏掉(线照画, 没人报错)。"""
    code = code_lines(read_src(CHART))
    i = code.index("export function thinFib2")
    body = code[i:i + 1200]
    assert "FIB2_ROLE_TARGET" in body, "thinFib2 没按角色键挑推算位"
    for name in ("上攻推算位一", "上攻推算位二", "上攻推算位三"):
        assert name not in body, f"thinFib2 里又出现了标签文字「{name}」"


def test_R410_开关上要如实说藏了几条():
    """减线最坏的结果不是少看几条, 是**用户以为这一档就这么多线**。

    所以开关的 title 必须同时给出"画了几条"和"这一档共几条"。
    """
    src = read_src(CTL)
    i = src.index("const total = key === 'fib2'")
    blk = src[i:i + 900]
    assert "fib2Raw?.length" in blk, "总条数不是从整档来的 —— 那就说不出藏了几条"
    assert "total > count" in blk, "没有判断「有没有藏」就直接写数, 会在没藏时也胡说"
    assert "这一档共" in blk, "title 里没写出这一档一共多少条"
    for where in (CHART, SIDE):
        assert "disabled={total === 0}" in read_src(where), \
            f"{where}: 能不能点按画出来的条数算了 —— 该按整档算, 否则藏光了开关就点不开"


# ── [R413] 主图上那三样 ────────────────────────────────────
def test_R413_未来区只在二型开着的时候才存在():
    """**这一条是「别影响六态那些」的机器形式。**

    画「未来」区要往右扩几个空槽, 而 x 轴是**所有价位组共用的** —— 扩了之后
    六态的分段底色、所有组的价位线都会跟着多出 3 格。用户定的做法是
    「避开影响就独立显示」, 落实成一句话就是:

        二型开关没开 → 一个空槽都不加 → 整张图与加这段之前逐字节相同。

    退化的方式很安静: 把那个 `activeTypes.has('fib2')` 去掉, 图上看起来只是
    右边多了一小条灰底, 没人会觉得不对 —— 但那时候**每一只票、每一次打开都在
    动共用坐标轴**, 而二型可能根本没开。
    """
    code = code_lines(read_src(CHART))
    m = re.search(r"const futureVals = ([^\n]+)", code)
    assert m, "未来区那个开关读不出来"
    assert "activeTypes.has('fib2')" in m[1], \
        f"未来区没有跟着二型开关走: {m[1]}"
    # 空的时候必须原样返回基础数组, 不许重建(重建 = 每次渲染都换新引用)
    i = code.index("const futureVals")
    blk = code[i:i + 900]
    assert "if (!futureVals.length)" in blk, "没有「没有未来值就原样返回」那条早返回"
    assert "dates: baseDates" in blk, "早返回时没有把原来的 dates 原样交回去"


def test_R413_现价贴签在右边单独占一列_不靠图层压():
    """价位线和它在同一片画布上, **调 z/zlevel 压不住** —— 出图两次才看清楚。

    所以做法是结构上不重叠: 让到价位标签右边一截, 单独占一列。
    这条钉的是"让开的距离明显大于价位标签的距离", 而不是某个具体像素。
    """
    code = code_lines(read_src(CHART))
    i = code.index("const nowLine")
    blk = code[i:i + 800]
    m = re.search(r"position: 'end' as const, distance: (\d+)", blk)
    assert m, "现价贴签的位置读不出来"
    now_d = int(m[1])
    # 价位线/曲线的 endLabel 用的距离
    others = [int(x) for x in re.findall(r"distance: (\d+),\n\s*\}", code)]
    others += [int(x) for x in re.findall(r"padding: \[2, 5\], borderRadius: 2,\n\s*distance: (\d+)", code)]
    assert now_d >= 40, f"现价贴签只让了 {now_d}px, 会和价位标签挤在一起"
    for d in others:
        assert now_d > d + 20, f"现价贴签({now_d})没比价位标签({d})让开足够"


def test_R413_密集带标签带上下沿价格():
    """一块没有数字的色带挂不了单 —— 而它是这一组里唯一真会拿来挂单的东西。"""
    code = code_lines(read_src(CHART))
    i = code.index("name: `回踩密集带")
    line = code[i:i + 160]
    assert "z.low.toFixed(2)" in line and "z.high.toFixed(2)" in line, \
        f"密集带标签没带上下沿价格: {line}"
