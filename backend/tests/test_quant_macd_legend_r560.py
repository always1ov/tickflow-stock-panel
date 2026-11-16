"""[fork R560] 量化MACD: 图例 + 悬停说明。

用户: 「量化macd也加标注」(趋势量化那张 R555 已有)。只加注释, 公式(indicators/quant_macd.py)
与图里的画法一样没动。图例 R560 首版画在副图外面的标题带里, R626 起搬进副图自己的
读数行(`quantPaneReadouts`), R648 起读数行与标题收进 `lib/analysisPanes.ts` 一处产地。
"""
from __future__ import annotations

from tests.frontend_source import code_of


def test_R560_副图标题带里有图例_悬停有说明():
    panes = code_of("lib/analysisPanes.ts")
    chart = code_of("components/stock-analysis/AnalysisKChart.tsx")
    # [R626] 用户: 「这些不应该放在主图上面, 应该放在副图合适的位置」——
    # 图例已挪进量化MACD 的读数行(paneReadouts), 五样仍在。
    # [R760] R648 把读数行搬进 `lib/analysisPanes.ts`(日K 与关键价位共用一份),
    # 旧断言对着 AnalysisKChart 找 `text: 'DIFF'` 已经找不到 —— 产地搬了, 口径没变。
    # 量化MACD 按通达信原文写 `DIFF`(标准 MACD 副图那只才是 `DIF`), 别改成 DIF。
    assert "quantPaneReadouts" in panes, "量化MACD 的读数行没了"
    for text in ("DIFF", "DEA", "共振", "↑金叉", "↓死叉"):
        assert f"text: '{text}'" in panes, f"量化MACD 读数行少了 {text}"
    assert "paneReadouts={[[], quantReadouts]}" in chart, "量化MACD 读数行没挂到副图上"
    # 悬停说明挂到开关键排最右的「?」(R626), 仍只有一份产地
    assert "QUANT_MACD_HELP" in panes, "量化MACD 的悬停说明没接上"
    assert "ANALYSIS_PANE_HELP" in chart, "悬停说明没挂到「?」上"


def test_R560_说明只有一个产地_五样都讲到():
    src = code_of("lib/quantMacdSeries.ts")
    assert "export const QUANT_MACD_LEGEND" in src
    for name in ("'DIFF'", "'DEA'", "'共振'", "'金叉'", "'死叉'"):
        assert f"name: {name}" in src, f"图例少了 {name}"
    assert "DIFF:" not in code_of("components/stock-analysis/AnalysisKChart.tsx"), "图表里另写了一份说明"
