"""[fork R555] 趋势量化副图: 三种线的图例 + 悬停说明。

用户: 「我好像发现有绿线和紫线, 都代表什么含义。我想加点注释」。
只加注释, 公式(backend/app/indicators/trend_quant.py)与画法一样没动。
"""
from __future__ import annotations

from tests.frontend_source import code_of


def test_R555_副图画了图例_悬停有说明():
    chart = code_of("components/stock-analysis/AnalysisKChart.tsx")
    assert "trendQuantLegendGraphic(" in chart, "趋势量化的图例没画"
    assert "title={TREND_QUANT_HELP}" in chart, "图例的悬停说明没接上"


def test_R555_说明只有一个产地():
    series = code_of("lib/trendQuantSeries.ts")
    assert "export const TREND_QUANT_LEGEND" in series
    # 图表里不另写一份说明文字
    assert "吸筹:" not in code_of("components/stock-analysis/AnalysisKChart.tsx")
