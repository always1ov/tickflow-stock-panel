"""[R433] 个股弹窗「现状」块 + [R434] 视图切换靠右、量化MACD 副图四行等高。

R433 用户排版图「结论后面加」: 上半是「现状」(现成读数), 下半是一整套新的买卖判定
(条件清单 / 进场区 / 止损 / 目标)。用户选「先做现状, 规则写成草案给你审」——
所以这里钉两件事: 现状只用现成读数、各自取自原来的产地; 下半块没有被偷偷做进来。

R434 用户: 「日分时关键价位放到右边, 量化macd是四行等高的行限制着的」。
R439: 副图的红色横线整套撤掉(见 `test_R439_量化MACD副图不画红线`)。
"""
from tests.frontend_source import code_of

DLG = "components/StockPreviewDialog.tsx"
ST = "components/stock-preview/StatusSection.tsx"
SEC = "components/stock-preview/ChartLevelsSection.tsx"
CHART = "components/stock-analysis/AnalysisKChart.tsx"
QM = "lib/quantMacdSeries.ts"


def test_R433_现状紧跟头部_排在图表与价位之前():
    dlg = code_of(DLG)
    i = dlg.index("<StatusSection")
    assert dlg.index("<PreviewHero") < i < dlg.index("<ChartLevelsSection")
    # 与复盘块同一个天数 → 同一个复盘查询键, 不多发一次回算
    assert "days={reviewDays}" in dlg[i:dlg.index("/>", i)], "现状没跟头部天数走"


def test_R433_读数各自取自原来的产地():
    st = code_of(ST)
    assert "useStockTrend(symbol)" in st, "六态没走图上方那条六态条同一个查询"
    assert "useStockReview(symbol, days)" in st, "通道那几样没走复盘同一个查询"
    assert "POS_FILL[b.pos]" in st and "b?.pos_cn" in st, "三档位置的颜色 / 名字没用原来那份"
    assert "VERDICT_CLS[now.tone]" in st
    # 通道这一层唯一能照着做的一句(R269: 别的都能收, 它不行)
    assert "该盯什么: " in st and "{ph?.watch && <div" in st, "「该盯什么」没按条件渲染出来"
    # 距离用后端给的带符号的数, 不在前端另算一遍
    assert "t.flip_down_distance_pct" in st and "t.flip_up_distance_pct" in st


def test_R433_下半块那套买卖判定没有被偷偷做进来():
    st = code_of(ST)
    for word in ("止损", "目标一", "进场", "开仓", "做多", "盈亏比", "条件清单", "到位提醒"):
        assert word not in st, f"「{word}」—— 那套判定还没经用户审过"


def test_R434_视图切换靠右():
    sec = code_of(SEC)
    tool, tabs = sec.index("{toolbar}"), sec.index('role="tablist"')
    assert tool < tabs, "视图切换没排在右边"
    assert 'className="ml-auto inline-flex shrink-0 items-center gap-1 rounded-btn' in sec


def test_R439_量化MACD副图不画红线():
    """[R434 → R436 → R439] 副图的横格先是四行等高 + 红框, 再是三格等间距的红点线。
    用户: 「量化macd还是有红线划分间距, 我不需要红线删掉」—— 整套撤掉, 回到 R423 的样子。"""
    chart = code_of(CHART)
    for w in ("QMACD_GRID", "quantMacdGrid", "qmacdGridRef", "gridLine", "markLine: { data: g."):
        assert w not in chart, f"「{w}」—— 副图横线又回来了"
    assert "show: !isDark, backgroundColor: QUANT_MACD_COLORS.paneBg, borderWidth: 0" in chart, "外框回来了"
    sub = chart[chart.index("{ scale: false, gridIndex: 1, splitNumber: 2,"):]
    sub = sub[:sub.index("axisLabel")]
    assert "splitLine: { show: false }" in sub, "副图背景横线又画出来了"
    qm = code_of(QM)
    for w in ("QMACD_GRID", "quantMacdGrid", "QMACD_ROWS", "quantMacdRange"):
        assert w not in qm
    assert "gridLine" not in code_of("lib/theme.ts")

def test_R438_现状里没有这一格历来():
    """[R438] 用户看着「这一格历来(近 120 天) 5 段 +1.6% 3/4 段」: 「这没用了, 删掉」。"""
    st = code_of(ST)
    for w in ("这一格历来", "comboHistory", "HistoryCell"):
        assert w not in st, f"「{w}」又回到现状块了"
    # 六态成了第一格, 前面不该再有分隔竖线
    trend = st[st.index("<Cell label={<>趋势状态 · 六态"):]
    assert "md:border-l" not in trend[:trend.index("\n")]
