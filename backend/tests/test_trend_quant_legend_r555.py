"""[fork R555] 趋势量化副图: 三种线的图例 + 悬停说明。

用户: 「我好像发现有绿线和紫线, 都代表什么含义。我想加点注释」。
只加注释, 公式(backend/app/indicators/trend_quant.py)与画法一样没动。
"""
from __future__ import annotations

from tests.frontend_source import code_of


def test_R555_副图画了图例_悬停有说明():
    chart = code_of("components/stock-analysis/AnalysisKChart.tsx")
    # [R626] 图例从图外那条画布挪进趋势量化的读数行(paneReadouts), 三样仍在。
    assert "trendReadouts" in chart, "趋势量化的读数行没了"
    for text in ("平均线", "吸筹", "超买 3.2 / 超卖 0.5"):
        assert f"text: '{text}'" in chart, f"趋势量化读数行少了 {text}"
    # 悬停说明挂到开关键排最右的「?」(R626)
    assert "TREND_QUANT_HELP" in chart, "图例的悬停说明没接上"


def test_R555_说明只有一个产地():
    series = code_of("lib/trendQuantSeries.ts")
    assert "export const TREND_QUANT_LEGEND" in series
    # 图表里不另写一份说明文字
    assert "吸筹:" not in code_of("components/stock-analysis/AnalysisKChart.tsx")


def test_R556_黄线名字写在右端_图例行不重复():
    """用户: 「超买超卖想在黄线右端注明」。"""
    chart = code_of("components/stock-analysis/AnalysisKChart.tsx")
    decor = code_of("components/charts/SubPaneDecor.ts")
    # [R557] 用户: 「超买超卖不需要显示数值了」—— 右端只写名字
    labels = [line for line in chart.splitlines() if "kind: 'label'" in line]
    assert [line.split("text: ")[1].split(",")[0].strip() for line in labels] == ["'超买'", "'超卖'"]
    assert "{ kind: 'label', value: 3.2, text: '超买'" in chart
    assert "{ kind: 'label', value: 0.5, text: '超卖'" in chart
    # 名字贴在副图右边缘、纵向对准那条线的值, 并垫一层黑描边(亮色主题下白底黄字看不见)
    assert "kind: 'label'" in decor and "priceToCoordinate(label.value)" in decor
    assert "ctx.strokeText(label.text" in decor
