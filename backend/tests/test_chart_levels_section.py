"""[R430 → R432] 个股弹窗「图表与价位」。

R430(用户排版图第二块): 日 K / 分时 / 关键价位三个视图; 图跟着头部 60 / 120 / 250 日走;
枢轴点档位、二型粗细这些小开关跟着那一类走。

R432 用户: 「图表与价位这部分提取到结论后面, 而且关键价位还是按照以前那样显示吧,
在右侧很不方便, 可以保留方形按钮。后面再梳理一遍统一删除」——
  · 新块紧跟在头部(「结论」那一行)之后, 旧顶栏及以下整体挪到新块后面;
  · 右侧列表撤了, 开关回到图的正上方, 样子是方形按钮(`LevelToolbar`)。
"""
import re

from tests.frontend_source import code_of

DLG = "components/StockPreviewDialog.tsx"
CHART = "components/stock-analysis/AnalysisKChart.tsx"
CTL = "components/stock-analysis/levelControls.ts"
BAR = "components/stock-analysis/LevelToolbar.tsx"
SEC = "components/stock-preview/ChartLevelsSection.tsx"


def _call(src: str, tag: str) -> str:
    i = src.index(tag)
    return src[i:src.index("/>", i)]


def _sec(dlg: str) -> str:
    return dlg[dlg.index("<ChartLevelsSection"):dlg.index("</ChartLevelsSection>")]


def test_R432_新块紧跟头部_旧内容整体在后面():
    dlg = code_of(DLG)
    hero, sec, review = dlg.index("<PreviewHero"), dlg.index("<ChartLevelsSection"), dlg.index("<ReviewSection")
    old_bar = dlg.index("onClick={() => setView('review')}")          # 旧顶栏
    old_body = dlg.index('className="rounded border border-border/50 bg-base/30 p-3"')
    assert hero < sec < review < old_bar < old_body, "顺序应是 头部 → 图表与价位 → 复盘 → 旧顶栏 → 旧内容"
    # 头部以下整块一起滚: 滚动容器从头部之后开始, 把新块与旧顶栏都包进去
    scroll = dlg.index('<div className="min-h-0 flex-1 overflow-auto">')
    assert hero < scroll < sec and scroll < old_bar


def test_R432_没有右侧列表了_开关回到图上方():
    sec = code_of(SEC)
    assert "side?:" not in sec and "withSide" not in sec, "区块又能往图旁边塞一张卡片了"
    assert "lg:grid-cols" not in sec, "图旁边又留出了一栏"
    assert "LevelSideList" not in code_of(DLG)
    chart = code_of(CHART)
    i = chart.index("{levels && controls && (")
    assert "<LevelToolbar groups={LEVEL_GROUPS} controls={controls}" in chart[i:i + 200]
    # 位置: 就在老那排小开关的地方, 在图(chartRef)之前
    assert i < chart.index("{levels && !controls && (") < chart.index("<div ref={chartRef}")


def test_R432_保留方形按钮_点开的反相_色点换另一套主题():
    bar = code_of(BAR)
    assert "const SQ = 'inline-flex h-8" in bar and "rounded-btn border" in bar
    assert "const SQ_ON = 'border-foreground bg-foreground text-surface font-medium'" in bar
    assert "const LC_ON = levelColors(theme === 'dark' ? 'light' : 'dark')" in bar
    assert "backgroundColor: on ? LC_ON[g.key] : LC[g.key]" in bar
    assert "onClick={controls.clearAll} disabled={activeTypes.size === 0}" in bar


def test_R430_图与开关读写同一份状态_切视图不丢():
    dlg = code_of(DLG)
    assert "const levelCtl = useLevelControls()" in dlg
    assert "controls={levelCtl}" in _call(_sec(dlg), "<StockLevelsPanel")
    assert "const ctl = controls ?? ownControls" in code_of(CHART)


def test_R430_图跟着头部天数走():
    sec = _sec(code_of(DLG))
    assert "visibleBars={reviewDays}" in _call(sec, "<StockLevelsPanel")
    daily = _call(sec, "<StockPanel")
    assert "dateRange={heroRange}" in daily and "visibleBars={reviewDays}" in daily, (
        "日 K 没跟头部天数走(带分时小图时它默认只露 40 根)")
    chart = code_of(CHART)
    assert "startValue: zoomStart" in chart, "起点要按第几根给 —— 按百分比取整 60 日会露出 62 根"
    assert "Math.round((1 - showBars" not in chart


def test_R430_每类的数与小开关文案只有一个产地():
    chart, bar, ctl = code_of(CHART), code_of(BAR), code_of(CTL)
    for src, name in ((chart, "老那排小开关"), (bar, "方形按钮那排")):
        assert "levelGroupStat(g.key, g.label, effLevels, fib2Raw, pivotRank)" in src, f"{name}没用共用的计数"
        for c in ("PIVOT_RANK_TITLES[r]", "FIB2_GRAINS.map", "title={FIB2_TARGETS_TITLE}",
                  "title={FIB2_BACKTEST_TITLE}"):
            assert c in src, f"{name}没用共用的文案 {c}"
    for text in ("画了 ${count} 条", "P + R1/S1", "三点推算", "线画得准不准"):
        assert text in ctl
        assert text not in chart and text not in bar, f"「{text}」又在别处写了一份"
    mid = re.search(r"\['mid', '中', '([^']*)'\]", ctl)
    assert mid and "默认" not in mid.group(1), "中档又被叫成默认档(默认是粗档)"


def test_R432_小开关照以前_那一类开着时接在后面():
    bar = code_of(BAR)
    assert "{activeTypes.has('pivot') && (effLevels?.pivot?.length ?? 0) > 0 && (" in bar
    assert "{activeTypes.has('fib2') && fib2?.grain && (" in bar
    chart = code_of(CHART)
    call = chart[chart.index("<LevelToolbar"):]
    assert "onOpenFit={symbol ? () => setFib2FitOpen(true) : undefined}" in call[:300], (
        "「回测这三档」没接到图里那个回测弹窗")


def test_R430_关不掉关键价位时没有这个视图():
    assert "levelsEnabled ? TABS : TABS.filter(t => t.key !== 'levels')" in code_of(SEC)


def test_R437_新分时与旧分时同一套_信息栏不能漏():
    """[R437] 用户: 「检查新的弹窗 ... 每个模块是否代码都几乎和以前一模一样, 尤其是图形部分」。
    R430 搬分时视图时漏了图上方那条信息栏(`StockPanel infoBarOnly`)。新旧两处的分时图
    与信息栏, 属性必须一样多 —— 只有区间(`dateRange`)按用户选的「图跟着头部走」换成 heroRange。"""
    dlg = code_of(DLG)
    sec = _sec(dlg)
    new = sec[sec.rindex("chartView === 'intraday' ? ("):]      # 第一处是工具栏那格, 取最后一处
    old = dlg[dlg.index("view === 'intraday' ? (\n                <div"):]
    for tag in ("<StockMultiDayIntradayChart", "<StockPanel"):
        new_call = _call(new, tag)
        old_call = _call(old, tag)
        norm = lambda c: re.sub(r"\s+", " ", c.replace("heroRange", "dateRange")).strip()
        assert norm(new_call) == norm(old_call), f"新分时的 {tag} 与旧分时不一样:\n{new_call}\n----\n{old_call}"
    assert "infoBarOnly" in _call(new, "<StockPanel")


def test_R437_刷新同时认新旧两个视图():
    """旧顶栏的刷新原来只看旧 `view`; 新块自己的 `chartView` 在分时时, 刷的却是关键价位那份。"""
    dlg = code_of(DLG)
    fn = dlg[dlg.index("const handleRefresh = () => {"):]
    fn = fn[:fn.index("\n  }\n")]
    assert "new Set<PreviewView>([view, chartView])" in fn
    assert "view === 'daily'" not in fn, "分支得按循环变量判, 不是按旧 view"
