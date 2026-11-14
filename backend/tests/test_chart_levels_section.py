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
    """[R612] 双栏: 头部 → (左栏)现状 / (右栏)图表与复盘。复盘成了右栏的视图,
    不再是图表下面的一块; 头部以下仍是同一块可滚区域。"""
    dlg = code_of(DLG)
    hero, status, sec = dlg.index("<PreviewHero"), dlg.index("<StatusSection"), dlg.index("<ChartLevelsSection")
    assert hero < status < sec, "顺序应是 头部 → 现状 → 图表"
    body = dlg.index('className="min-h-0 flex-1 overflow-y-auto xl:grid')
    assert hero < body < status, "头部以下不是同一块滚动/分栏区域"


def test_R479_旧顶栏与旧内容删干净了():
    dlg = code_of(DLG)
    for gone in ("setView(", "<StockReviewPanel", 'className="rounded border border-border/50 bg-base/30 p-3"',
                 "<NavPager", "<StockFinancialSearch", "triggerInfo", "AB_STATUS_META", "setMaximized",
                 "recent.filter("):
        assert gone not in dlg, f"「{gone}」—— 旧顶栏 / 切换条 / 信息条 / 旧内容又回来了"
    # 这几样不在框里, 删旧内容时必须留着
    assert "useListNav<NavItem>(" in dlg, "方向键切股没了"
    assert "<NavWrapToast" in dlg, "首尾循环提示没了"
    assert "{showMonitorEditor && symbol && (" in dlg, "加监控的规则编辑器没了"
    assert 'name="stock-preview.footer"' in dlg, "二开公开插槽 stock-preview.footer 没了"


def test_R432_没有右侧列表了_开关回到图上方():
    sec = code_of(SEC)
    assert "side?:" not in sec and "withSide" not in sec, "区块又能往图旁边塞一张卡片了"
    assert "lg:grid-cols" not in sec, "图旁边又留出了一栏"
    assert "LevelSideList" not in code_of(DLG)
    chart = code_of(CHART)
    i = chart.index("{levels && controls && (")
    assert "<LevelToolbar groups={LEVEL_GROUPS} controls={controls}" in chart[i:i + 200]
    # 位置: 就在老那排小开关的地方, 在图(chartRef)之前
    assert i < chart.index("{levels && !controls && (") < chart.index("<FinancialPlot")


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
    # [R596] lightweight 版把「露几根」交给 FinancialPlot 的 visibleBars(按根数, 不是百分比)
    assert "visibleBars={visibleBars" in chart, "起点要按第几根给 —— 按百分比取整 60 日会露出 62 根"
    assert "Math.round((1 - showBars" not in chart


def test_R430_每类的数与小开关文案只有一个产地():
    chart, bar, ctl = code_of(CHART), code_of(BAR), code_of(CTL)
    for src, name in ((chart, "老那排小开关"), (bar, "方形按钮那排")):
        assert re.search(r"levelGroupStat\((?:g|group)\.key, (?:g|group)\.label, effLevels, fib2Raw, pivotRank\)", src), \
            f"{name}没用共用的计数"
        for c in ("PIVOT_RANK_TITLES[", "FIB2_GRAINS.map", "title={FIB2_TARGETS_TITLE}",
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
    """[R612] 页签提到右栏顶部, 收窄规则跟着过去。"""
    assert "enableLevelsView ? VIEW_TABS : VIEW_TABS.filter(t => t.key !== 'levels')" in code_of(DLG)


def test_R612_图表退化成一张卡片_不再自带页签():
    sec = code_of(SEC)
    for gone in ('role="tablist"', "TABS", "SectionTitle", "toolbar"):
        assert gone not in sec, f"「{gone}」—— 图表卡又自己管页签/标题了"


def test_R612_只有分时跟着右栏放宽():
    """[R614] 分时没有副图, 但仍要减掉图外的天数行与卡片内边距, 否则底部时间轴被裁。"""
    dlg = code_of(DLG)
    assert "Math.max(480, Math.min(chartAreaH - INTRADAY_CHROME_H, CHART_MAX_HEIGHT))" in dlg, (
        "分时图没按右栏量出来的可用高度放宽")
    assert "new ResizeObserver(entries => setChartAreaH(entries[0].contentRect.height))" in dlg


def test_R614_关键价位按右栏减两张副图定主图高_一屏装下():
    """[R614] 用户: 「按这个方案调整副图高度」。整张卡 = 固定开销(卡片内边距/边框/开关排/图例)
    + 主图 + 2×96, 主图取右栏减掉这些, 一屏装下; 太低时下限 260, 由右栏滚动兜底。
    [R615] 图下方的价位统计面板挪去左栏后, 固定开销里不再含它, 257 → 131。"""
    dlg = code_of(DLG)
    assert "Math.max(240, Math.min(chartAreaH - LEVELS_CHROME_H - 2 * CHART_LAYOUT.subPaneSlot, CHART_MAX_HEIGHT))" in dlg, (
        "关键价位没按「右栏 − 固定开销 − 两张副图」定主图高")
    assert "const LEVELS_CHROME_H = 131" in dlg, "固定开销常量没了, 装不下时无从核对"
    assert "const INTRADAY_CHROME_H = 109" in dlg, "分时也要减掉图外的天数行, 不然底部时间轴被裁"
    assert "Math.max(480, Math.min(chartAreaH - INTRADAY_CHROME_H, CHART_MAX_HEIGHT))" in dlg, (
        "分时没按「右栏 − 图外开销」定高")
    assert "height={chartHeight ?? 520}" in dlg, "窄屏/未测量时没回落到 520"


def test_R615_价位统计面板挪到左栏_图里不再画():
    """[R615] 用户: 「量化macd下面那部分，也就是当前价那些，可以放到左侧部分里面显示」。

    面板本身仍是 `LevelOverview` 这一个产地, 只是改由弹窗画在左栏(窄栏一列到底);
    图内传 overview={false} 不再重复画。悬停高亮跨组件, 状态提到弹窗里两边共用。"""
    dlg = code_of(DLG)
    assert "<LevelOverview" in dlg, "左栏里没有价位统计面板"
    assert "overview={false}" in dlg, "图里那份没关掉, 面板会两处各画一遍"
    assert "hoveredKey={levelHover}" in dlg and "onHoverKey={setLevelHover}" in dlg, (
        "左栏面板与图上的价位标签没联动")
    assert "useShownLevels(levelsQ.data?.levels, levelsQ.data?.fib2, heroRows" in dlg, (
        "「画了哪几条」没有复用图里那份 useShownLevels, 两处会各算一套")

    chart = code_of(CHART)
    assert "export function LevelOverview(" in chart, "面板得导出来才能给左栏用"
    assert "overview = true" in chart, "个股分析页默认仍要画在图的下面"
    assert "stacked" in chart, "窄栏要能一列到底"


def test_R616_副图按R565画法补画_数据口径不变():
    """[R616] 用户: 「副图的趋势量化和量化macd没有和我升级到R565之前显示的一样, 但要保持数据
    和我升级到R565之前一样」。lightweight 版把三样画法丢了(从昨值起的短柱、八种字、金叉死叉箭头),
    这里在 lightweight 里按旧代码补画, 并用回 R565 的副图高度比例; 数据仍只有后端那一份。"""
    decor = code_of("components/charts/SubPaneDecor.ts")
    for item in ("class PaneDecor", "ICON_UP", "ICON_DOWN", "HOLLOW_DASH", "'hollow'", "'text'", "'icon'"):
        assert item in decor, f"副图补画缺了 {item}"

    plot = code_of("components/charts/FinancialPlot.tsx")
    assert "paneDecor" in plot, "图组件没提供按 pane 挂补画图元的入口"

    chart = code_of(CHART)
    # 高度回到 R565(`lib/levelsChartLayout.ts`): 主图 48%, 限 160~220; 趋势量化再 +50 字道
    for c in ("const SUB_PANE_RATIO = 0.48", "const SUB_PANE_MIN = 160", "const SUB_PANE_MAX = 220",
              "const TREND_LANES_EXTRA = 50", "const PANE_HEADER_H = 18"):
        assert c in chart, f"副图高度没按 R565 的比例: 少了 {c}"
    assert "tqYRange(paneH, PANE_HEADER_H)" in chart, "字道占的像素没同步进纵轴范围"

    # 三样画法都由补画图元承担, 原生 Histogram/整条线近似必须撤掉
    for gone in ("tq:stick", "tq:wave", "qm:yellow", "splitBySign"):
        assert gone not in chart, f"「{gone}」—— 旧的近似画法还在"
    assert "'stick'" in chart and "'hollow'" in chart and "'icon'" in chart and "'text'" in chart
    assert "diffExposed" in chart, "DIFF 只露 DEA 之外那一截的旧规则没了"

    # 数据一字不改: 对齐用的字段仍在
    trend = code_of("lib/trendQuantSeries.ts")
    quant = code_of("lib/quantMacdSeries.ts")
    for field in ("wave_prev", "stick_up", "xichou_bar", "marks"):
        assert field in trend, f"趋势量化的数据字段 {field} 被动了"
    for field in ("gold_icon", "dead_icon", "yellow"):
        assert field in quant, f"量化MACD 的数据字段 {field} 被动了"


def test_R612fix_日K保持原高_右栏可滚_副图不能被裁():
    """[R612-fix] 用户: 「原来的趋势macd、趋势量化那些副图都没了」。
    根因是右栏 overflow-hidden，而这两张图的画布都在 height 之外再挂副图：
    关键价位 +2×96，日K 每张指标副图 +96，画布比右栏高就被裁。
    修法: 右栏自己可滚(兜底); 日K 的副图数量由图内工具栏决定、外面算不出来, 维持 420。
    [R614] 关键价位改成按右栏算出主图高，见上一条。"""
    dlg = code_of(DLG)
    assert "height={chartHeight ?? 420}" in dlg, "日K 被拉高了 —— 指标副图会被推到视口外"
    assert 'className="mt-3 min-h-0 flex-1 overflow-y-auto"' in dlg, "右栏不可滚, 副图会被裁"
    assert "chartView === 'review' && 'overflow-y-auto'" not in dlg, "复盘之外又只给一个视图开了滚动"


def test_R437_新分时与旧分时同一套_信息栏不能漏():
    """[R437] R430 搬分时视图时漏了图上方那条信息栏(`StockPanel infoBarOnly`)。原来靠与旧分时
    逐字比对守; [R479] 旧分时删了, 把旧分时那一组属性写死在这里 —— 少一个都红。"""
    dlg = code_of(DLG)
    sec = _sec(dlg)
    new = sec[sec.rindex("chartView === 'intraday' ? ("):]      # 第一处是工具栏那格, 取最后一处
    bar = _call(new, "<StockPanel")
    for attr in ("symbol={symbol}", "dateRange={heroRange}", "infoBarOnly", "prefetchSymbols={prefetchSymbols}",
                 "intradayDays={effectiveIntradayDays}", "addedDate={addedDate}"):
        assert attr in bar, f"分时信息栏少了 {attr}"
    chart = _call(new, "<StockMultiDayIntradayChart")
    for attr in ("symbol={symbol}", "days={effectiveIntradayDays}", "height={chartHeight ?? 480}",
                 "refetchIntervalMs={intradayRefetchMs}", "priceLines={monitorPriceLines}",
                 "onPriceDoubleClick={openPriceAlert}"):
        assert attr in chart, f"多日分时少了 {attr}"


def test_R437_刷新同时认新旧两个视图():
    """[R437] 刷新原来只看旧 `view`, 新块在分时时刷的却是关键价位那份。[R479] 旧 `view` 随旧顶栏
    删了, 刷新只认 chartView —— 三个视图各刷各的那份。"""
    dlg = code_of(DLG)
    fn = dlg[dlg.index("const handleRefresh = () => {"):]
    fn = fn[:fn.index("\n  }\n")]
    assert "chartView === 'daily'" in fn and "chartView === 'intraday'" in fn
    assert "QK.stockQuantMacd(symbol)" in fn
    assert "view ===" not in fn.replace("chartView ===", ""), "还在按旧 view 判"
