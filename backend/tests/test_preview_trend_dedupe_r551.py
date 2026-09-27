"""[fork R551] 个股弹窗: 「关键价位」图上方那条六态条与「现状」卡重复, 撤掉。

用户在截图上圈出现状卡的六态格和图上方的六态条: 「圈出来的部分重复了, 整改」。
两处读的是同一个查询(useStockTrend), 状态名 / 已 N 天 / 由谁转入 / 跌破转弱 / 站上转强逐字相同。
六态条独有的三样不能跟着丢: 回测调参入口、当天的转折信号、操作建议与关键点参考数(悬停)。
"""
from __future__ import annotations

from tests.frontend_source import code_of


def test_R551_个股弹窗不再印六态条():
    dlg = code_of("components/StockPreviewDialog.tsx")
    assert "trendBar={false}" in dlg, "个股弹窗的关键价位图上方又印回了六态条, 与现状卡重复"


def test_R551_六态条独有的东西搬进了现状卡():
    st = code_of("components/stock-preview/StatusSection.tsx")
    assert "<TrendBacktestButton" in st, "回测调参入口跟着六态条一起丢了"
    assert "<TrendSignalBadge" in st, "转折信号徽标跟着六态条一起丢了"
    assert "t.action" in st and "trendPivotTitle(t)" in st, "操作建议 / 关键点参考数跟着六态条一起丢了"


def test_R551_独立的关键价位弹窗照旧有六态条():
    # 那里上面没有现状卡, 六态条是唯一一处
    assert "trendBar={false}" not in code_of("components/stock-analysis/LevelsDialog.tsx")
    panel = code_of("components/stock-analysis/StockLevelsPanel.tsx")
    assert "trendBar = true" in panel


def test_R551_按钮与徽标只有一个产地():
    bar = code_of("components/stock-analysis/TrendStateBar.tsx")
    assert bar.count("回测调参 {") == 1, "回测调参按钮又复制出了第二份"
    assert "<TrendBacktestButton" in bar and "<TrendSignalBadge" in bar
