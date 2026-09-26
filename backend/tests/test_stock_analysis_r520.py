"""[fork R520] 个股分析页整改 —— 决策台每行压成一行, 页头与工具条精简。

用户: 「个股分析页面也需要整改」, 看过方案图后「确认」。
钉的是: 行是单行(不再 2×2、不再上下叠)、空仓不是按钮、表左对齐、页头没有功能清单副标题、
工具条没有第二个标题。数据、列、筛选、弹窗入口的守卫在原处(test_flip_trades 等)。
"""
from __future__ import annotations

from tests.frontend_source import code_of

BOARD = "components/stock-analysis/WatchlistDecisionBoard.tsx"
CELLS = "components/stock-analysis/decision-board/cells.tsx"
PAGE = "pages/StockAnalysis.tsx"


def test_R520_行是单行():
    cells = code_of(CELLS)
    assert "export const TD_BASE = 'align-middle py-1.5'" in cells, "行高又长回去了 / 又全列居中了"
    cell = cells[cells.index("export function TrendPositionCell"):]
    cell = cell[cell.index("return ("):cell.index("</td>")]
    assert "grid-rows-2" not in cell and "flex w-full cursor-pointer items-center gap-x-2" in cell, \
        "走势/位置又排成两行了 —— 那是一行 80px 的根源之一"
    board = code_of(BOARD)
    assert "min-h-[2.25rem]" not in board and "flex-col items-center" not in board, "名称 / 持仓那一格又竖排了"
    assert "flex max-w-full items-center text-left cursor-pointer group" in board


def test_R520_空仓不是按钮_持有才亮():
    board = code_of(BOARD)
    i = board.index("{r.held ? '持有' : '空仓'}")
    seg = board[i - 600:i]
    # [R527] 持有 / 空仓改成同一颗 xs 按钮的几何(用户: 「持仓和空仓应该是在同一个位置」), 空仓走 ghost:
    # 没边框、压暗(text-muted/50) —— 「空仓不是一颗带边框的按钮」这条立论没变, 变的只是等高等宽
    assert "? buttonClass({ size: 'xs', selected: true }" in seg, "持有那一档不亮了"
    assert "variant: 'ghost' }, 'text-muted/50" in seg and "buttonClass({ size: 'xs', selected: r.held })" not in seg, \
        "空仓又成了一颗带边框的按钮 —— 120 行里 110 行都在说「没拿」"


def test_R520_页头没有功能清单_搜索在页头右侧():
    page = code_of(PAGE)
    assert "AI 四维分析(技术" not in page, "副标题那份功能清单又回来了"
    head = page[page.index("<PageHeader"):page.index('<div className="w-full px-3 pb-4 pt-3')]
    assert "<StockFinancialSearch" in head, "搜索框不在页头里 —— 它自己占一行"


def test_R520_工具条没有第二个标题_三个管理按钮只留图标():
    board = code_of(BOARD)
    assert "<span className={TYPE.card}>自选决策台</span>" not in board, "一页两个名字: 页头「个股分析」+ 表头「自选决策台」"
    for label in ("刷新", "全量回测", "导出"):
        assert f'<span className="sr-only">{label}</span>' in board, f"「{label}」不该再印文字, 但读屏要读得到"
    cols = board[board.index("const BOARD_COLS = ["):board.index("] as const", board.index("const BOARD_COLS = ["))]
    import re
    assert sum(int(x) for x in re.findall(r"w: '(\d+)%'", cols)) == 100, "列宽加起来不是 100"
