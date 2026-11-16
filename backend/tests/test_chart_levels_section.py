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
    # [R760] 弹窗已不再挂 StockLevelsPanel(R663 撤「关键价位」视图), 日K 换成 StockPanel;
    # 同一份开关现在经 StockPanel 的 levelControls 透传到 StockDailyKChart。
    # 口径跟着实现走, 「图与开关读写同一份状态」这条意图不变。
    dlg = code_of(DLG)
    assert "const levelCtl = useLevelControls()" in dlg
    assert "levelControls={levelCtl}" in _call(_sec(dlg), "<StockPanel")
    assert "const levelCtl = levelControls ?? ownLevelCtl" in code_of("components/StockDailyKChart.tsx")


def test_R430_图跟着头部天数走():
    sec = _sec(code_of(DLG))
    # [R760] StockLevelsPanel 已不在弹窗里(见上一条); 现在的日K 就是 StockPanel,
    # 区间与露出根数仍必须跟着头部的 60 / 120 / 250 日走。
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
    # [R760] R705 起这排按钮会按 `groups` 拆分并进 MA 那一行 —— 从属小开关先判「这一份里
    # 有没有这一类」, 否则两行都各出一次。行为不变, 断言跟着这层守卫写。
    assert "{groups.some(g => g.key === 'pivot') && activeTypes.has('pivot') && (effLevels?.pivot?.length ?? 0) > 0 && (" in bar
    assert "{groups.some(g => g.key === 'fib2') && activeTypes.has('fib2') && fib2?.grain && (" in bar
    chart = code_of(CHART)
    call = chart[chart.index("<LevelToolbar"):]
    assert "onOpenFit={symbol ? () => setFib2FitOpen(true) : undefined}" in call[:300], (
        "「回测这三档」没接到图里那个回测弹窗")


def test_R430_关不掉关键价位时没有这个视图():
    """[R612] 页签提到右栏顶部, 收窄规则跟着过去。

    [R663] 用户: 「如果没问题就可以删除关键价位这部分了」—— 「关键价位」这个视图整页下架
    (`docs/hidden-features.md` 已登记), 于是不再有「关不掉时把页签收窄」这回事。
    [R760] 守卫改成守下架状态: 页签只剩日 K / 分时 / 复盘, 旧开关一个都不许回来。
    """
    dlg = code_of(DLG)
    assert "export type PreviewView = 'daily' | 'intraday' | 'review'" in dlg, "「关键价位」视图又回到类型里了"
    assert "{ key: 'daily', label: '日 K'" in dlg
    assert "{ key: 'intraday', label: '分时'" in dlg
    assert "{ key: 'review', label: '复盘'" in dlg
    assert "key: 'levels'" not in dlg and "enableLevelsView" not in dlg, "被下架的「关键价位」视图/开关又回来了"


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
    + 主图 + 两张副图, 主图取右栏减掉这些, 一屏装下; 太低时下限 260, 由右栏滚动兜底。
    [R615] 图下方的价位统计面板挪去左栏后, 固定开销里不再含它, 257 → 131。
    [R623] 反算抽进 `lib/chart-layout.ts` 的 `fitLevelsMainHeight`(与画图同源)。
    [R635] 轴底裁 9px + 卡片底留白 16px 让给 MACD: 131 → 87。

    [R668] 用户: 「主图显示还是恢复原来日K里面的风格吧」「要到最近一次右侧留白带之前那个版本」——
    「日K 接管关键价位版式」整套撤回, `fitLevelsMainHeight` / `LEVELS_CHROME_H` / `DAILY_CHROME_H`
    全部删除, 日K 回到自己的默认高度。守卫过期的是「按关键价位反算」这半段, 不是「一屏装下」的
    意图本身 —— [R760] 口径改为: 反算链路不许回来 + 分时仍按「右栏 − 图外开销」定高。
    """
    dlg = code_of(DLG)
    for gone in ("fitLevelsMainHeight", "const LEVELS_CHROME_H", "const DAILY_CHROME_H"):
        assert gone not in dlg, f"「{gone}」—— R668 已撤掉的「日K 接管关键价位版式」又回来了"
    assert "const INTRADAY_CHROME_H = 109" in dlg, "分时也要减掉图外的天数行, 不然底部时间轴被裁"
    assert "Math.max(480, Math.min(chartAreaH - INTRADAY_CHROME_H, CHART_MAX_HEIGHT))" in dlg, (
        "分时没按「右栏 − 图外开销」定高")
    assert "height={chartHeight ?? 480}" in dlg, "窄屏/未测量时分时没回落到 480"


def test_R615_价位统计面板挪到左栏_图里不再画():
    """[R615] 用户: 「量化macd下面那部分，也就是当前价那些，可以放到左侧部分里面显示」。

    面板本身仍是 `LevelOverview` 这一个产地, 只是改由弹窗画在图外(现为右栏, [R732] 四栏);
    图内不再重复画。悬停高亮跨组件, 状态提到弹窗里两边共用。

    [R760] 日K 换成 StockPanel + StockDailyKChart 后, 图组件里已经根本没有 `LevelOverview`
    可传 —— 「图里不再画」改由「两个图组件都不引用它 + 弹窗只出现一次」来守。
    """
    dlg = code_of(DLG)
    assert dlg.count("<LevelOverview") == 1, "价位统计面板必须只有一处产地(图外那条栏)"
    assert "overview={false}" not in dlg, "图内那份开关又回来了, 面板会两处各画一遍"
    assert "hoveredKey={levelHover}" in dlg and "onHover={setLevelHover}" in dlg, (
        "栏里面板与图上的价位标签没联动")
    assert "levelHoveredKey={levelHover}" in dlg and "onLevelHoverKey={setLevelHover}" in dlg, (
        "图上悬停没回传给图外那条栏")
    assert "useShownLevels(levelsQ.data?.levels, levelsQ.data?.fib2, heroRows" in dlg, (
        "「画了哪几条」没有复用图里那份 useShownLevels, 两处会各算一套")
    for rel in ("components/StockPanel.tsx", "components/StockDailyKChart.tsx"):
        assert "LevelOverview" not in code_of(rel), f"{rel} 又把价位统计画了一遍"

    chart = code_of(CHART)
    assert "export function LevelOverview(" in chart, "面板得导出来才能给图外用"
    assert "overview = true" in chart, "个股分析页默认仍要画在图的下面"
    assert "stacked" in chart, "窄栏要能一列到底"


def test_R616_副图按R565画法补画_数据口径不变():
    """[R616] 用户: 「副图的趋势量化和量化macd没有和我升级到R565之前显示的一样, 但要保持数据
    和我升级到R565之前一样」。lightweight 版把三样画法丢了(从昨值起的短柱、八种字、金叉死叉箭头),
    这里在 lightweight 里按旧代码补画; 数据仍只有后端那一份。

    [R724] 用户: 「彻底删掉趋势量化这个指标」—— 八种字那条「字道」随趋势量化一起删了,
    `kind: 'text'` 与 `TREND_LANES_EXTRA` / `tqYRange` 不再存在; 剩下的 DRAWTEXT 是
    `kind: 'note'`([R714]), 量化MACD 的柱/框/箭头也改由 `lib/analysisPanes.ts` 出。
    [R760] 守卫跟着当前产地走, 画法三样与数据字段一项不少。
    """
    decor = code_of("components/charts/SubPaneDecor.ts")
    for item in ("class PaneDecor", "ICON_UP", "ICON_DOWN", "HOLLOW_DASH", "'hollow'", "'note'", "'icon'"):
        assert item in decor, f"副图补画缺了 {item}"

    plot = code_of("components/charts/FinancialPlot.tsx")
    assert "paneDecor" in plot, "图组件没提供按 pane 挂补画图元的入口"

    # [R623] 副图高度判据搬进 `lib/chart-layout.ts`(画图与弹窗反算同源); [R626] 48% → 28%
    layout = code_of("lib/chart-layout.ts")
    for c in ("const ANALYSIS_SUB_PANE_RATIO = 0.28", "const ANALYSIS_SUB_PANE_MIN = 108",
              "const ANALYSIS_SUB_PANE_MAX = 136", "export const SUB_PANE_GAP = 12",
              "export const MACD_PANE_EXTRA = 25"):
        assert c in layout, f"副图高度判据不对: 少了 {c}"

    # [R648] pane 标题行高度与量化MACD 的柱/框/箭头都搬进了 `lib/analysisPanes.ts`
    panes = code_of("lib/analysisPanes.ts")
    assert "export const PANE_HEADER_H = 18" in panes, "pane 标题行高度没了"
    assert "diffExposed" in panes, "DIFF 只露 DEA 之外那一截的旧规则没了"
    for kind in ("'stick'", "'hollow'", "'icon'"):
        assert kind in panes, f"副图补画缺了 {kind}"

    chart = code_of(CHART)
    # 三样画法都由补画图元承担, 原生 Histogram/整条线近似必须撤掉
    for gone in ("tq:stick", "tq:wave", "qm:yellow", "splitBySign"):
        assert gone not in chart, f"「{gone}」—— 旧的近似画法还在"

    # 数据一字不改: 对齐用的字段仍在
    quant = code_of("lib/quantMacdSeries.ts")
    for field in ("gold_icon", "dead_icon", "yellow"):
        assert field in quant, f"量化MACD 的数据字段 {field} 被动了"


def test_R612fix_日K保持原高_右栏可滚_副图不能被裁():
    """[R612-fix] 用户: 「原来的趋势macd、趋势量化那些副图都没了」。
    根因是右栏 overflow-hidden，而这两张图的画布都在 height 之外再挂副图：
    日K 每张指标副图 +96，画布比右栏高就被裁。
    修法: 图所在那一栏自己可滚(兜底); 日K 的副图数量由图内工具栏决定、外面算不出来, 维持 420。
    [R614] 关键价位那张图曾按右栏算出主图高。
    [R668] 那套反算撤了, 日K 回到自己的默认高度 —— 但「可滚 + 副图不被裁」这条兜底仍在。
    [R760] 滚动容器上的间距从 `mt-3` 收到 `mt-1`([R700]), 断言跟着当前类名写。
    """
    dlg = code_of(DLG)
    assert "height={chartHeight ?? 420}" in dlg, "日K 被拉高了 —— 指标副图会被推到视口外"
    assert 'className="mt-1 min-h-0 flex-1 overflow-y-auto"' in dlg, "图所在那栏不可滚, 副图会被裁"
    assert "chartView === 'review' && 'overflow-y-auto'" not in dlg, "复盘之外又只给一个视图开了滚动"


def test_R437_新分时与旧分时同一套_信息栏不能漏():
    """[R437] R430 搬分时视图时漏了图上方那条信息栏(`StockPanel infoBarOnly`)。原来靠与旧分时
    逐字比对守; [R479] 旧分时删了, 把旧分时那一组属性写死在这里 —— 少一个都红。

    [R671] 用户: 「市值那一行也融入到顶部去」—— 信息栏并进弹窗头部第二行(`headerStats`),
    分时分支不再挂 `StockPanel infoBarOnly`。信息照旧一个不少, 只是产地换了。
    [R760] 断言改为: 头部第二行带同一份指标行 + 多日分时那几个属性一个不能少, 且不再重复画信息栏。
    """
    dlg = code_of(DLG)
    sec = _sec(dlg)
    assert "infoBarOnly" not in dlg, "分时信息栏又单独画了一条(它已并进头部第二行)"
    # 信息栏(指标行)在头部: PreviewHero 的 stats 槽位里那只 StockPanel
    hero = dlg[dlg.index("<PreviewHero"):dlg.index("<ChartLevelsSection")]
    stats = _call(hero, "<StockPanel")
    for attr in ("symbol={symbol}", "dateRange={heroRange}", "headerStats",
                 "prefetchSymbols={prefetchSymbols}", "addedDate={addedDate}"):
        assert attr in stats, f"头部信息行少了 {attr}"
    assert "stats={(" in hero, "PreviewHero 没挂第二行指标槽位"
    chart = _call(sec, "<StockMultiDayIntradayChart")
    for attr in ("symbol={symbol}", "days={effectiveIntradayDays}", "height={chartHeight ?? 480}",
                 "refetchIntervalMs={intradayRefetchMs}", "priceLines={monitorPriceLines}",
                 "onPriceDoubleClick={openPriceAlert}", "flat"):
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


# ================================================================
# [R760] 反向守卫的另一半: 功能真被删干净时, 「下架的不许回来」照样绿
# ================================================================
#
# 上面 R430/R614/R551 几条在 R663/R668 之后只能守"下架的视图与反算链路不许回来"。
# 这类反向断言有个盲区: 哪天有人把整套关键价位功能一起删了, 测试不会响。
# 这里补正向那一半 —— 撤掉的是那个视图, 不是这套功能本身。

def test_R760_关键价位功能链路仍在_只撤了视图():
    """日K 图上的价位开关、价位统计面板、图表侧的价位画法都还在用。

    [R663] 用户: 「如果没问题就可以删除关键价位这部分了」—— 删的是弹窗里那个
    独立视图与独立弹窗; 图上的开关(LevelToolbar)、图外的统计面板(LevelOverview)、
    阶梯画法(levelLines / levelSeries / levelRanges)仍被日K 组装使用。
    """
    dlg = code_of(DLG)
    sec = _sec(dlg)
    chart = code_of(CHART)
    daily = code_of("components/StockDailyKChart.tsx")
    assert "<StockLevelsPanel" not in dlg, "已被 R663 下架的独立面板又挂回弹窗"
    # 开关: 弹窗持有一份, 经 StockPanel 透传到日K, 图内用同一个 LevelToolbar 渲染
    assert "levelControls={levelCtl}" in _call(sec, "<StockPanel"), "开关没从弹窗透传到日K"
    assert "export function LevelToolbar(" in code_of(BAR), "价位开关件没了"
    assert daily.count("<LevelToolbar") >= 2, "日K 图上的价位开关(两张画布各一处)少了"
    # 阶梯画法: 线上的价位、区间带仍由日K 组装后交给图组件
    assert "levelLines={levelLines}" in daily and "levelSeries={levelSeries}" in daily, "价位阶梯的数据没再交给图"
    assert "levelRanges=" in daily, "二型区间带没再交给图"
    # 统计面板仍是唯一产地, 且仍导出来给图外那条栏用
    assert "export function LevelOverview(" in chart, "价位统计面板被删了"
    assert "export function StockLevelsPanel(" in code_of("components/stock-analysis/StockLevelsPanel.tsx"), (
        "关键价位共用面板被删了 —— 下架视图不等于删功能")


def test_R760_图表高仍按右栏实测走():
    """[R614] 的「一屏装下」意图在 R668 之后靠实测高度兜: 分时按右栏反算,
    日K 回到自己的默认高度 —— 但两者都得跟着右栏实测值, 不许写死一个常数。"""
    dlg = code_of(DLG)
    assert "const [chartAreaH, setChartAreaH] = useState(0)" in dlg, "右栏高度不再实测"
    assert "setChartAreaH(entries[0].contentRect.height)" in dlg, "实测值没接进来"
    expr = dlg[dlg.index("const chartHeight = wide && chartAreaH > 0"):]
    expr = expr[:expr.index("\n  const ")]
    assert "chartView === 'intraday'" in expr and "INTRADAY_CHROME_H" in expr, (
        "分时没按「右栏 − 图外开销」定高")
    assert "fillHeight={chartAreaH > 0 ? chartAreaH : undefined}" in dlg, (
        "日K 拿不到右栏可视高度, 两张分析副图按什么收")
