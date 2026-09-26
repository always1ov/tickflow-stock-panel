"""[fork R538] 回测页整改: 策略栏左侧配置栏加宽、分栏条走共用件。

用户: 「剩下的所有页面都需要整改」, 看过回测页方案图后「确认」。只改表达, 策略/参数/回测逻辑一个没动。
"""
from __future__ import annotations

from tests.frontend_source import code_of


def test_R538_配置栏够宽_日期不折行():
    sb = code_of("pages/backtest/StrategyBacktest.tsx")
    # 18rem 时回测区间两个日期各 ~118px, 「2026-06-26」折成两行; 建仓口径被截断
    assert "xl:grid-cols-[21rem_minmax(0,1fr)]" in sb
    assert "xl:grid-cols-[18rem_minmax(0,1fr)]" not in sb


def test_R538_分栏条走共用件():
    page = code_of("pages/Backtest.tsx")
    assert "<PageTabs" in page and "SEG_ITEM" not in page
    # 老链接兼容照旧
    assert "requestedTab === 'factor'" in page and "requestedTab === 'mining'" in page
