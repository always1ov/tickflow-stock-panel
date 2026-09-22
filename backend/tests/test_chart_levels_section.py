"""[R430] 个股弹窗重做第二块:「图表与价位」(左图右列表)。

用户排版图 + 四条答复: 新块加上、旧的先留着; 枢轴点档位 / 二型粗细等小开关放右侧
列表、点开那一类时展开; 图下面的价位清单先留着; 图跟着头部的 60 / 120 / 250 日走。
"""
import re

from tests.frontend_source import code_of

DLG = "components/StockPreviewDialog.tsx"
CHART = "components/stock-analysis/AnalysisKChart.tsx"
CTL = "components/stock-analysis/levelControls.ts"
SIDE = "components/stock-preview/LevelSideList.tsx"
SEC = "components/stock-preview/ChartLevelsSection.tsx"


def _call(src: str, tag: str) -> str:
    i = src.index(tag)
    return src[i:src.index("/>", i)]


def test_R430_新块在旧内容之前_旧的还在():
    dlg = code_of(DLG)
    assert "<ChartLevelsSection" in dlg
    # 旧的内衬卡片(日K/分时/关键价位/复盘)原样在, 且排在新块后面
    old = 'className="rounded border border-border/50 bg-base/30 p-3"'
    assert old in dlg, "旧内容被删了 —— 用户说「旧的先留着」"
    assert dlg.index("<ChartLevelsSection") < dlg.index(old)
    assert "onClick={() => setView('review')}" in dlg, "旧顶栏的复盘入口不见了"


def test_R430_图与右侧列表读写同一份开关():
    dlg = code_of(DLG)
    assert "const levelCtl = useLevelControls()" in dlg
    sec = dlg[dlg.index("<ChartLevelsSection"):dlg.index("</ChartLevelsSection>")]
    assert "controls={levelCtl}" in _call(sec, "<LevelSideList")
    lv = _call(sec, "<StockLevelsPanel")
    assert "controls={levelCtl}" in lv, "图没接外面的开关 —— 右边点了图上不变"
    # 图自己那一排开关在受控时不画: 同一件事两处都能点, 只会让人找哪个才算数
    chart = code_of(CHART)
    assert "const ctl = controls ?? ownControls" in chart
    assert "{levels && !controls && (" in chart


def test_R430_图跟着头部天数走():
    dlg = code_of(DLG)
    sec = dlg[dlg.index("<ChartLevelsSection"):dlg.index("</ChartLevelsSection>")]
    assert "visibleBars={reviewDays}" in _call(sec, "<StockLevelsPanel")
    daily = _call(sec, "<StockPanel")
    assert "dateRange={heroRange}" in daily and "visibleBars={reviewDays}" in daily, (
        "日 K 没跟头部天数走(带分时小图时它默认只露 40 根)")
    # 起点按第几根给, 不按百分比取整 —— 取整后 60 日会露出 62 根
    chart = code_of(CHART)
    assert "startValue: zoomStart" in chart
    assert "Math.round((1 - showBars" not in chart


def test_R430_每类的数与小开关文案只有一个产地():
    chart, side, ctl = code_of(CHART), code_of(SIDE), code_of(CTL)
    for src, name in ((chart, "图上方那一排"), (side, "右侧列表")):
        assert "levelGroupStat(g.key, g.label, effLevels, fib2Raw, pivotRank)" in src, (
            f"{name}没用共用的计数")
        for c in ("PIVOT_RANK_TITLES[r]", "FIB2_GRAINS.map", "title={FIB2_TARGETS_TITLE}",
                  "title={FIB2_BACKTEST_TITLE}"):
            assert c in src, f"{name}没用共用的文案 {c}"
    for text in ("画了 ${count} 条", "P + R1/S1", "三点推算", "线画得准不准"):
        assert text in ctl
        assert text not in chart and text not in side, f"「{text}」又在别处写了一份"
    # 中档原来写「默认档」, 而默认早在 R410 改成了粗档
    mid = re.search(r"\['mid', '中', '([^']*)'\]", ctl)
    assert mid and "默认" not in mid.group(1)


def test_R430_小开关只在那一类点开时展开():
    side = code_of(SIDE)
    assert "{on && g.key === 'pivot' && (" in side
    assert "{on && g.key === 'fib2' && fib2?.grain && (" in side


def test_R430_看日K时点某一类_切过去并且只开不关():
    side = code_of(SIDE)
    pick = side[side.index("const pick = "):]
    pick = pick[:pick.index("\n  }\n")]
    assert "if (showing) controls.toggleType(t)" in pick
    assert "controls.turnOn(t); onReveal()" in pick
    dlg = code_of(DLG)
    assert "onReveal={() => setChartView('levels')}" in dlg


def test_R430_选中行反相_圆点换另一套主题的颜色():
    """选中行亮色主题黑底、暗色主题白底; 圆点不换色的话, 暗色主题里近白的
    六态关键点画在白底上就没了。"""
    side = code_of(SIDE)
    assert "const LC_ON = levelColors(theme === 'dark' ? 'light' : 'dark')" in side
    assert "backgroundColor: on ? LC_ON[g.key] : LC[g.key]" in side


def test_R430_全部清除():
    side, ctl = code_of(SIDE), code_of(CTL)
    assert "onClick={controls.clearAll} disabled={activeTypes.size === 0}" in side
    assert "const clearAll = useCallback(() => setActiveTypes(new Set()), [])" in ctl


def test_R430_关不掉关键价位时_没有这个视图也没有右侧列表():
    sec = code_of(SEC)
    assert "levelsEnabled ? TABS : TABS.filter(t => t.key !== 'levels')" in sec
    assert "const withSide = levelsEnabled && side" in sec
