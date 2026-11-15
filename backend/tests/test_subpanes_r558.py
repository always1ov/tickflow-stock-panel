"""[fork R558] 量化MACD 副图: 不挤、字看得清。

用户: 「需要整改, 感觉空间有点挤, 有些东西看不清楚了, 量化macd也要整改」, 看过方案图后「确认」。
只改显示, 公式(indicators/quant_macd.py)与柱子 / 图标一样没动。
[R724] 用户: 「彻底删掉趋势量化这个指标」—— 趋势量化副图整张拿掉, 这里只留量化MACD 的版面。
"""
from __future__ import annotations

from tests.frontend_source import code_of


def test_R558_名字与图例在副图顶上的标题带里():
    layout = code_of("lib/levelsChartLayout.ts")
    assert "SUB_HEADER = 18" in layout
    assert "GAP_MAIN_SUB + SUB_HEADER" in layout
    chart = code_of("components/stock-analysis/AnalysisKChart.tsx")
    # [R596] lightweight 版把副图名字/读数列交给 FinancialPlot 的 pane 标题带, 不再画进图里
    assert "paneTitles={['', quantTitle]}" in chart, "副图名字又写回图里了"
    # [R626] 图例搬进副图读数行(R560), 标题带里只留名字
    assert "paneReadouts={[[], quantReadouts]}" in chart, "副图读数行没走 paneReadouts"
