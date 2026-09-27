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
    assert "trendTop - SUB_HEADER + 3" in chart and "subTop - SUB_HEADER + 3" in chart, "副图名字又写回图里了"


def test_R559_字画在图顶图底两条字道里_不压线不互叠():
    """用户对 R558: 「字还是重叠」。R558 的纵轴留余量 + 字压白柱 + 叠字让一行, 字仍写在
    原文的高度上(那正是线与柱子所在处), 所以换成字道。"""
    tq = code_of("lib/trendQuantSeries.ts")
    assert "export function laneLayout(" in tq and "export function tqYRange(" in tq
    assert "lane: 'top'" in tq and "lane: 'bottom'" in tq
    # 字不再按原文高度画在图里
    assert "type: 'scatter', ...axis, name: m.text" not in tq, "字又写回图里了"
    assert "...tqYRange(trendH)" in code_of("components/stock-analysis/AnalysisKChart.tsx")
    assert "subH + TREND_LANES_EXTRA" in code_of("lib/levelsChartLayout.ts"), "字道占了地方, 副图没跟着加高"


def test_R558_庄现画法没动():
    # 狗头的位置只看「哪一天」、贴副图底边 —— 冻结(R485), 这次只动了副图纵轴
    z = code_of("lib/zhuangXianSeries.ts")
    assert "y + height - DOGE_SIZE - BOTTOM_GAP" in z
