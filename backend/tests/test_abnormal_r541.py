"""[fork R541] 异动监控整改: 分栏进页头并记在 ?tab=、信号标签三种颜色、手机不横滑、竞价铺满。

用户: 「剩下的所有页面都需要整改」, 看过异动监控方案图后「确认」。只改表达, 信号/阈值/规则/刷新一个没动。
"""
from __future__ import annotations

import re

from tests.frontend_source import code_of

PAGE = "pages/AbnormalMoves.tsx"


def test_R541_分栏走共用件_记在地址上():
    page = code_of(PAGE)
    assert "<PageTabs" in page and "usePageTab(TABS, 'intraday')" in page
    assert "useState<AbnormalTab>" not in page, "分栏又回到组件状态, 一刷新就丢"


def test_R541_信号标签只剩三种意思():
    page = code_of(PAGE)
    meta = page[page.index("const SIGNAL_META"):page.index("export function AbnormalMoves")]
    # 涨停红 / 跌停绿 / 炸板琥珀, 其余中性
    assert "text-bull" in meta and "text-bear" in meta and "text-warning" in meta
    for hue in ("orange", "cyan", "amber", "sky", "lime"):
        assert f"{hue}-" not in meta, f"信号标签又用回 {hue}"
    assert not re.search(r"\b(cyan|amber|orange|sky|lime)-\d{3}", page), "页面里又写死了调色板颜色"


def test_R541_手机上盘中不横滑():
    page = code_of(PAGE)
    assert "max-sm:block sm:min-w-[900px]" in page
    assert "min-w-[900px] text-xs" not in page


def test_R541_竞价铺满():
    page = code_of(PAGE)
    assert "max-w-3xl flex-col gap-4 overflow-y-auto" not in page
