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
HERO = "components/stock-preview/PreviewHero.tsx"
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
    assert "const ph = d?.channel?.phase ?? null" in st and "{ph?.cn ?? '—'}" in st, "通道阶段没用复盘接口那份"
    # 距离用后端给的带符号的数, 不在前端另算一遍
    # [R760] 「跌破转弱 / 站上转强」两格已按 R682/R707 撤出本块, 翻转距离现在只
    # 留在接口类型里、前端没有第二个产地 —— 原意改成: 不许在本文件里另算一遍。
    assert "distance_pct" not in st, "翻转距离又在前端自己算了"


def test_R433_下半块那套买卖判定没有被偷偷做进来():
    st = code_of(ST)
    for word in ("止损", "目标一", "进场", "开仓", "做多", "盈亏比", "条件清单", "到位提醒"):
        assert word not in st, f"「{word}」—— 那套判定还没经用户审过"


def test_R434_视图切换靠右():
    """[R612] 切换条从「图表与价位」卡里提到右栏顶部, 仍然靠右、随视图变的那格靠左。

    [R760] R658/R679 把切换条并进弹窗头部右侧操作组(60/120/250 日左边), 它不再
    自带 `ml-auto` —— 靠右由头部那条 `justify-between` 的第二组保证。守的原意没变:
    仍靠右、仍在天数左边。
    """
    dlg = code_of(DLG)
    hero = code_of(HERO)
    assert "viewControls={viewControls}" in dlg, "视图切换没挂到弹窗头部"
    group = hero[hero.index('className="flex shrink-0 flex-wrap items-center gap-2"'):]
    assert group.index("{viewControls}") < group.index("HERO_DAYS.map"), "视图切换没排在右边天数左边"
    assert 'role="tablist" aria-label="图表视图" className="inline-flex shrink-0 items-center gap-2"' in dlg


def test_R612_双栏_左栏只放现状_窄屏单列():
    """[R612] 用户选的「双栏大弹窗」: 左「现状」/ 右图表与复盘;
    ≥1280 才分栏, 768~1279 单列(现状在上), 手机上整屏。

    [R760] R672/R707 恢复左中右三栏、R732 再在 2xl 拆出复盘列, 「双栏」已被多栏
    取代 —— 原意逐条改钉当前实现: 现状独占一栏、窄屏单列且现状在图之前、手机整屏。
    """
    dlg = code_of(DLG)
    st = code_of(ST)
    grid = dlg[dlg.index("xl:grid xl:grid-cols-[minmax(240px,290px)_minmax(0,1fr)_minmax(250px,300px)]"):]
    left = grid[grid.index("xl:overflow-y-auto xl:border-b-0 xl:border-r"):]
    left = left[:left.index("</div>")]
    assert "<StatusSection" in left and "<ChartLevelsSection" not in left, "左栏不是只放现状"
    assert grid.index("<StatusSection") < grid.index("<ChartLevelsSection"), "现状没排在图前面"
    assert "grid grid-cols-1 items-start" in st and "sm:grid-cols-2" not in st, "左栏只有 240~290px, 现状该是单列"
    assert "max-md:w-screen" in dlg and "max-md:h-[100dvh]" in dlg, "手机上没铺满整屏"


def test_R439_量化MACD副图不画红线():
    """[R434 → R436 → R439] 副图的横格先是四行等高 + 红框, 再是三格等间距的红点线。
    用户: 「量化macd还是有红线划分间距, 我不需要红线删掉」—— 整套撤掉, 回到 R423 的样子。"""
    chart = code_of(CHART)
    for w in ("QMACD_GRID", "quantMacdGrid", "qmacdGridRef", "gridLine", "markLine: { data: g."):
        assert w not in chart, f"「{w}」—— 副图横线又回来了"
    # [R596] lightweight 的 pane 本身没有外框/背景横线; 只要没人把 paneBg/splitLine 加回来即可
    assert "paneBg" not in chart, "副图又铺底色外框了"
    assert "splitLine" not in chart, "副图背景横线又画出来了"
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


def test_R445_现状块删掉打码的部分_没有分隔竖线_四块等分():
    """[R445] 用户在截图上打码: 通道那一格的档位徽标、三字组合码、「该盯什么」那一句,
    连同分隔竖线, 「删除掉我打码的部分和间隔符合, 然后排版好显示」。"""
    st = code_of(ST)
    for gone in ("VERDICT_CLS", "三档都在中部", "geo?.combo", "该盯什么", "ph?.watch", "border-l"):
        assert gone not in st, f"「{gone}」是用户打码删掉的"
    # 那一格只剩阶段, 标题跟着改名 —— 「通道档位」底下放阶段就是一个名字两个意思
    assert '<Cell label="通道阶段">' in st and "通道档位" not in st
    # [R760] R707 把本块收成左栏一条纵列(240~290px), 「四块等分一行」不再成立;
    # 守的原意改成: 单一列、顶端对齐, 不许再摊成多列。
    assert "grid grid-cols-1 items-start" in st and "lg:grid-cols-4" not in st
    # [R760] 「跌破转弱 / 站上转强」两格按 R682 撤掉、R707 未恢复 —— 改为守下架状态。
    assert "FlipCell" not in st and "跌破转弱" not in st and "站上转强" not in st
    # [R448] 用户: 「删掉三档位置这四个字」
    assert "三档位置" not in st, "三档位置那块的小标题又回来了"


# ================================================================
# [R760] 反向守卫的另一半
# ================================================================
#
# R682/R707/R445 之后, 本文件有几条只能守"撤掉的格子不许回来"。这里补上现在
# 该有的三格 —— 免得哪天有人把现状卡删空, 上面那些反向断言照样全绿。

def test_R760_现状卡那三格都还在():
    """趋势状态(六态) / 通道阶段 / 三档位置(上中下轨) —— [R707] 用户:
    「恢复左中右布局, 左里面放『趋势状态 · 六态』和『通道阶段』」, 随后
    「上中下轨也放到左里面」。三格都常驻, 不带卡框、单列排。"""
    st = code_of(ST)
    assert "<Cell label={<>趋势状态 · 六态" in st, "趋势状态那一格没了"
    assert "{t.state_cn}" in st and "{t.duration}" in st, "六态读数/已 N 天没了"
    assert "<TrendSignalBadge" in st, "转折信号徽标丢了"
    assert '<Cell label="通道阶段">' in st and "{ph?.cn ?? '—'}" in st, "通道阶段那一格没了"
    assert "{BAND_CN[k]}" in st and "POS_FILL[b.pos]" in st, "三档位置的上中下轨没了"
    for gone in ('<Cell label="三档位置"', '三档位置'):
        assert gone not in st, "三档位置的小标题(R448 删过)又回来了"


def test_R760_六态读数只在现状卡一处():
    """[R551] 撤掉图上方那条六态条之后, 六态读数只有现状卡这一个产地 ——
    正反都要守: 现状卡里得有, 图侧任何一个容器里都不许再挂。"""
    assert "{t.state_cn}" in code_of(ST), "现状卡里的六态读数没了"
    for rel in (DLG, "components/StockPanel.tsx", "components/StockDailyKChart.tsx",
                "components/stock-preview/ChartLevelsSection.tsx"):
        src = code_of(rel)
        assert "<TrendStateBar" not in src and "trendBar" not in src, (
            f"{rel} 又把六态条挂回图上方")
