"""[R433] 个股弹窗「现状」块 + [R434] 视图切换靠右、量化MACD 副图四行等高。

R433 用户排版图「结论后面加」: 上半是「现状」(现成读数), 下半是一整套新的买卖判定
(条件清单 / 进场区 / 止损 / 目标)。用户选「先做现状, 规则写成草案给你审」——
所以这里钉两件事: 现状只用现成读数、各自取自原来的产地; 下半块没有被偷偷做进来。

R434 用户: 「日分时关键价位放到右边, 量化macd是四行等高的行限制着的」。
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
    assert "days={reviewDays}" in dlg[i:dlg.index("/>", i)], "这一格历来没跟头部天数走"


def test_R433_读数各自取自原来的产地():
    st = code_of(ST)
    assert "useStockTrend(symbol)" in st, "六态没走图上方那条六态条同一个查询"
    assert "useStockReview(symbol, days)" in st, "通道那几样没走复盘同一个查询"
    assert "comboHistory(d.rows, here)" in st, "这一格历来另算了一份"
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


def test_R436_副图不画红框_横格一直等间距():
    """[R434 → R436] 用户: 「量化macd别搞红框框出来, 你知道是一直等间距就行了,
    可以里面等间距两格子, 再往外就等间距比例使用空间」。"""
    chart = code_of(CHART)
    assert "QUANT_MACD_COLORS.frame" not in chart, "红框又回来了"
    assert "show: !isDark, backgroundColor: QUANT_MACD_COLORS.paneBg, borderWidth: 0" in chart
    # 纵轴是窗口里的真实跨度, 横格由 markLine 按数据值画(0 一定压线)
    assert "const qGrid = quantMacdGrid(qa, zoomStart, dates.length - 1)" in chart
    assert "{ gridIndex: 1, min: qGrid.min, max: qGrid.max," in chart
    assert "data: qGrid.lines.map(v => ({ yAxis: v }))" in chart
    # 拖动缩放后按新窗口重算, 否则横格停在打开那一刻的窗口上
    zoom = chart[chart.index("inst.on('datazoom'"):]
    zoom = zoom[:zoom.index("\n      })")]
    assert "quantMacdGrid(r.qa, from, to)" in zoom and "id: QMACD_GRID_ID" in zoom
    qm = code_of(QM)
    assert "export const QMACD_GRID_SPLIT = 3" in qm, "里面两格 = 跨度分三份"
    # 上下各多留 1/4 格, 最外那条线才不会贴着边(贴边看着又是一道框)
    assert "export const QMACD_GRID_PAD = 0.25" in qm
    assert "min: lo - k * QMACD_GRID_PAD, max: hi + k * QMACD_GRID_PAD" in qm
    assert "QMACD_ROWS" not in qm and "quantMacdRange" not in qm
