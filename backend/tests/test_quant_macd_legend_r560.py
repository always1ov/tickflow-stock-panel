"""[fork R560] 量化MACD: 标题带里的图例 + 悬停说明。

用户: 「量化macd也加标注」(趋势量化那张 R555 已有)。只加注释, 公式(indicators/quant_macd.py)
与图里的画法一样没动 —— 图例画在副图外面的标题带里。
"""
from __future__ import annotations

from tests.frontend_source import code_of


def test_R560_副图标题带里有图例_悬停有说明():
    chart = code_of("components/stock-analysis/AnalysisKChart.tsx")
    assert "quantMacdLegendGraphic(" in chart, "量化MACD 的图例没画"
    assert "title={QUANT_MACD_HELP}" in chart, "量化MACD 图例的悬停说明没接上"


def test_R560_说明只有一个产地_五样都讲到():
    src = code_of("lib/quantMacdSeries.ts")
    assert "export const QUANT_MACD_LEGEND" in src
    for name in ("'DIFF'", "'DEA'", "'共振'", "'金叉'", "'死叉'"):
        assert f"name: {name}" in src, f"图例少了 {name}"
    assert "DIFF:" not in code_of("components/stock-analysis/AnalysisKChart.tsx"), "图表里另写了一份说明"
