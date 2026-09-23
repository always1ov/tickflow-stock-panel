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
    """[R479] 旧内容删了(用户框出整块:「我是想删除掉框出来的这部分」)。顺序剩 头部 → 现状 →
    图表与价位 → 复盘; 头部以下整块一起滚。"""
    dlg = code_of(DLG)
    hero, status = dlg.index("<PreviewHero"), dlg.index("<StatusSection")
    sec, review = dlg.index("<ChartLevelsSection"), dlg.index("<ReviewSection")
    assert hero < status < sec < review, "顺序应是 头部 → 现状 → 图表与价位 → 复盘"
    scroll = dlg.index('className="min-h-0 flex-1 overflow-auto"')
    assert hero < scroll < status


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
    for attr in ("symbol={symbol}", "days={effectiveIntradayDays}", "height={480}",
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
