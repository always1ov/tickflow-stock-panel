"""[fork R508] 自选页: 默认视图换成「按小分队」网格, 卡片视图 / 分组卡片 / 分组统计条撤掉, 默认 5 列。

用户: 「开始整改自选页」→ 看过现状四种视图的分析图后: 「我感觉你改过后还是每个个股占用很多空间」
→ 看过两版密排后: 「a默认保留切换按钮」。

钉的是: 三种重复画法真撤干净; 网格是同一份行(筛选、排序一视同仁)、零额外请求; 分组条折起;
默认列是那 5 个; 视图与顺序两个偏好记住。
"""
from __future__ import annotations

import re
from pathlib import Path

from tests.frontend_source import code_of

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "frontend" / "src"
PAGE = "pages/Watchlist.tsx"
GRID = "components/WatchlistGroupGrid.tsx"
BAR = "components/WatchlistGroups.tsx"


def test_R508_三种重复画法撤干净():
    for gone in ("WatchlistGroupCards.tsx", "WatchlistGroupStatsBar.tsx", "GroupStatsSettings.tsx"):
        assert not (SRC / "components" / gone).exists(), f"{gone} 还在"
    page = code_of(PAGE)
    for gone in ("StockCard", "useCardColumnCount", "useVirtualizer", "groupCardsOpen", "groupStatsOpen",
                 "卡片视图", "分组卡片视图", "分组统计", "'card'"):
        assert gone not in page, f"自选页还留着 {gone}"
    lib = code_of("lib/watchlistGroupStats.ts")
    for gone in ("GROUP_METRICS", "sortGroupKeys", "loadGroupStatsConfig"):
        assert gone not in lib, f"只为撤掉的两个组件服务的 {gone} 还在"
    assert "watchlistGroupStats:" not in code_of("lib/storage.ts")


def test_R508_两个视图_默认按小分队_偏好记住():
    page = code_of(PAGE)
    assert "storage.watchlistView.get('grid') === 'table' ? 'table' : 'grid'" in page, "默认不是网格 / 老值 card 没兜住"
    assert "[['grid', '按小分队'], ['table', '一张表']]" in page
    assert "storage.watchlistView.set(next)" in page
    assert "storage.watchlistGridSort.set(next)" in page and "[['order', '分组顺序'], ['pct', '今日涨跌']]" in page


def test_R508_网格吃的是同一份行_零额外请求():
    page = code_of(PAGE)
    i = page.index("<WatchlistGroupGrid")
    props = page[i:page.index("/>", i)]
    assert "rows={sortedRows}" in props, "网格没吃筛选 + 排序后的那份行 —— 筛选条件会对两种视图说两套话"
    assert "entries={listEntries}" in props and "selected={selectedGroup}" in props
    grid = code_of(GRID)
    assert "useQuery" not in grid and "api." not in grid, "网格自己发了请求"
    # 表格专属的两份重请求(日K批量 / 分钟批量)在网格下不发
    assert "enabled: dailyKVisible && symbols.length > 0 && viewMode === 'table'" in page
    assert "enabled: intradayVisible && minuteSymbols.length > 0 && viewMode === 'table'" in page


def test_R508_网格每只一行_块内按涨跌_未分组垫底():
    grid = code_of(GRID)
    for cell in ("fmtPrice(price)", "fmtPct(pct)", "r.pct_since_added", "r.symbol.slice(0, 6)"):
        assert cell in grid, f"一行少了 {cell}"
    assert "const bySymbolPct = (a: any, b: any) => (rowPct(b) ?? -Infinity) - (rowPct(a) ?? -Infinity)" in grid
    assert "name: '未分组'" in grid and "return loose ? [...ranked, loose] : ranked" in grid, "未分组该垫底"
    assert "grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4" in grid
    # 数据不加装饰性动效
    for banned in ("motion", "animate-", "transition-all", "hover:scale", "translate"):
        assert banned not in grid, f"网格里出现了 {banned}"


def test_R508_块内按涨跌与未分组垫底_算法层():
    """把 buildBlocks 的判据用同一份口径在这里复算一遍 —— 守卫扫源码只知道写了排序, 不知道排对没有。"""
    grid = code_of(GRID)
    # 同一只票属于两个组 → 两个块各出现一次(与分组条计数同口径)
    assert "rows.filter(r => (gids.get(r.symbol) ?? []).includes(g.id))" in grid
    # 选中某组时只出那一块; 选「未分组」时只出未分组
    assert "if (selected !== 'all' && selected !== g.id) continue" in grid
    assert "if (selected === 'all' || selected === 'ungrouped')" in grid


def test_R508_分组条折起_药丸压矮带边框():
    bar = code_of(BAR)
    assert "max-h-[6.75rem] overflow-hidden" in bar and "'max-h-[34vh] overflow-y-auto'" in bar, "折起 / 展开两档没了"
    assert "el.scrollHeight > el.clientHeight + 1" in bar, "没量溢出就画不出「全部 N 组」按钮"
    assert "`全部 ${groups.length} 组`" in bar
    assert "inline-flex h-7 shrink-0 items-center gap-1.5 rounded-btn border px-2.5" in bar, "药丸没压到 28px"
    assert "? `border-border ${color.text} hover:bg-elevated`" in bar, "未选中的彩色药丸又没边框了"
    assert "'border-border text-secondary hover:bg-elevated hover:text-foreground'" in bar, "未选中的全部 / 未分组又没边框了"
    # 手机上药丸区独占整行
    assert "order-2 flex min-w-0 basis-full flex-wrap" in bar and "sm:order-1 sm:basis-0 sm:flex-1" in bar


def test_R508_默认列就是那5个():
    cols = code_of("lib/watchlist-columns.ts")
    body = cols[cols.index("export const BUILTIN_COLUMNS"):cols.index("export const COLUMN_GROUPS")]
    visible = re.findall(r"key: '([a-z_0-9]+)' \}, label: '[^']+', visible: true", body)
    assert visible == ["symbol", "price", "pct", "added_at", "pct_since_added"], visible


def test_R508_插槽契约只加不改():
    types = code_of("extensions/types.ts")
    assert "viewMode: 'table' | 'card' | 'grid'" in types, "watchlist.toolbar 的 viewMode 该是只加值不去值"
    doc = (ROOT / "docs" / "secondary-development.md").read_text(encoding="utf-8")
    assert "'grid'" in doc and "'card'" in doc
