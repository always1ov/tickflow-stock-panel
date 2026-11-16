"""[fork R551] 个股弹窗: 「关键价位」图上方那条六态条与「现状」卡重复, 撤掉。

用户在截图上圈出现状卡的六态格和图上方的六态条: 「圈出来的部分重复了, 整改」。
两处读的是同一个查询(useStockTrend), 状态名 / 已 N 天 / 由谁转入 / 跌破转弱 / 站上转强逐字相同。
六态条独有的三样不能跟着丢: 回测调参入口、当天的转折信号、操作建议与关键点参考数(悬停)。
"""
from __future__ import annotations

from tests.frontend_source import SRC, code_of


def test_R551_个股弹窗不再印六态条():
    # [R760] 弹窗已不再挂 StockLevelsPanel(R663 撤「关键价位」视图), `trendBar={false}` 这个
    # 断面没有了。口径改为: 头部以下不出现六态条, 图上也不再挂 TrendStateBar —— 六态读数
    # 只在左栏现状卡一处。
    dlg = code_of("components/StockPreviewDialog.tsx")
    assert "<TrendStateBar" not in dlg and "trendBar=" not in dlg, \
        "个股弹窗的关键价位图上方又印回了六态条, 与现状卡重复"
    for rel in ("components/StockPanel.tsx", "components/StockDailyKChart.tsx"):
        assert "<TrendStateBar" not in code_of(rel), f"{rel} 又把六态条印回图上方"


def test_R551_六态条独有的东西搬进了现状卡():
    st = code_of("components/stock-preview/StatusSection.tsx")
    # [R760] 回测调参入口 [R679]/[R680] 已再从现状卡上移到弹窗头部工具栏(「异动 / 自选」之后),
    # 它仍在、只是换了产地; 徽标与操作建议/关键点参考数按 R551 留在现状卡。
    assert "<TrendSignalBadge" in st, "转折信号徽标跟着六态条一起丢了"
    assert "t.action" in st and "trendPivotTitle(t)" in st, "操作建议 / 关键点参考数跟着六态条一起丢了"
    dlg = code_of("components/StockPreviewDialog.tsx")
    assert "<TrendBacktestButton" in dlg, "回测调参入口跟着六态条一起丢了"
    assert "toolbarExtra={<BacktestEntry symbol={symbol} />}" in dlg, \
        "回测调参入口没接到图上方工具栏(它现在的产地)"


def test_R551_独立的关键价位弹窗照旧有六态条():
    # [R663] 用户: 「如果没问题就可以删除关键价位这部分了」—— 独立的 LevelsDialog 已整页撤下,
    # `docs/hidden-features.md` 已登记。原有对象消失, [R760] 改为守下架状态: 旧组件不许回来,
    # 而共用面板仍默认带六态条(哪天独立入口复用面板时, 那条仍在)。
    assert not (SRC / "components/stock-analysis/LevelsDialog.tsx").exists(), \
        "已下架(R663)的关键价位独立弹窗又回来了"
    panel = code_of("components/stock-analysis/StockLevelsPanel.tsx")
    assert "trendBar = true" in panel


def test_R551_按钮与徽标只有一个产地():
    bar = code_of("components/stock-analysis/TrendStateBar.tsx")
    assert bar.count("回测调参 {") == 1, "回测调参按钮又复制出了第二份"
    assert "<TrendBacktestButton" in bar and "<TrendSignalBadge" in bar
