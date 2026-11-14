"""[fork R558] 趋势量化 / 量化MACD 两张副图: 不挤、字看得清。

用户: 「需要整改, 感觉空间有点挤, 有些东西看不清楚了, 量化macd也要整改」, 看过方案图后「确认」。
只改显示, 两张图的公式(indicators/trend_quant.py、quant_macd)与量化MACD 的柱子 / 图标一样没动。
"""
from __future__ import annotations

from tests.frontend_source import code_of


def test_R558_名字与图例在副图顶上的标题带里():
    layout = code_of("lib/levelsChartLayout.ts")
    assert "SUB_HEADER = 18" in layout
    assert "GAP_MAIN_SUB + SUB_HEADER" in layout
    chart = code_of("components/stock-analysis/AnalysisKChart.tsx")
    # [R596] lightweight 版把副图名字/读数列交给 FinancialPlot 的 pane 标题带, 不再画进图里
    assert "paneTitles={['', trendTitle, quantTitle]}" in chart, "副图名字又写回图里了"
    # [R626] 图例搬进副图读数行(R555/R560), 标题带里只留名字
    assert "paneReadouts={[[], trendReadouts, quantReadouts]}" in chart, "副图读数行没走 paneReadouts"


def test_R559_字画在图顶图底两条字道里_不压线不互叠():
    """用户对 R558: 「字还是重叠」。R558 的纵轴留余量 + 字压白柱 + 叠字让一行, 字仍写在
    原文的高度上(那正是线与柱子所在处), 所以换成字道。"""
    tq = code_of("lib/trendQuantSeries.ts")
    assert "export function laneLayout(" in tq and "export function tqYRange(" in tq
    assert "lane: 'top'" in tq and "lane: 'bottom'" in tq
    # 字不再按原文高度画在图里
    assert "type: 'scatter', ...axis, name: m.text" not in tq, "字又写回图里了"
    assert "paneReadouts={[[], trendReadouts, quantReadouts]}" in code_of("components/stock-analysis/AnalysisKChart.tsx"), \
        "字没走副图读数列"
    assert "subH + TREND_LANES_EXTRA" in code_of("lib/levelsChartLayout.ts"), "字道占了地方, 副图没跟着加高"
