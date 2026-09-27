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


def test_R558_趋势量化纵轴留余量_字压在白柱之上():
    tq = code_of("lib/trendQuantSeries.ts")
    assert "TQ_Y_MIN = -0.45" in tq and "TQ_Y_MAX = 4.35" in tq
    assert "min: TQ_Y_MIN, max: TQ_Y_MAX" in code_of("components/stock-analysis/AnalysisKChart.tsx")
    assert "z: 8 + k * 0.01" in tq, "字又被吸筹白柱盖住了"
    assert "textBorderWidth" in tq


def test_R558_庄现画法没动():
    # 狗头的位置只看「哪一天」、贴副图底边 —— 冻结(R485), 这次只动了副图纵轴
    z = code_of("lib/zhuangXianSeries.ts")
    assert "y + height - DOGE_SIZE - BOTTOM_GAP" in z
