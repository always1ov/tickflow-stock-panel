"""[fork R526] 决策台手机上一行一块 —— 四格折成: 名字·代码 + 价 / 持仓 / 走势·位置。

用户拿手机截图: 「手机版现在不搞左右滑动, 能否像监控中心那样, 每一行就能显示完整」。
钉的是四格在手机上的落位(order)与占位(basis), 宽屏一个类名没动(全是 max-sm:)。
"""
from __future__ import annotations

from tests.frontend_source import code_of

BOARD = "components/stock-analysis/WatchlistDecisionBoard.tsx"
CELLS = "components/stock-analysis/decision-board/cells.tsx"


def test_R526_四格在手机上的落位():
    board = code_of(BOARD)
    cells = code_of(CELLS)
    # 第一行左半: 名字 · 代码。基准宽 10rem 不是 0 —— 基准 0 的话 flex-wrap 永远不会把「持仓」挤到下一行,
    # 持有那几行的成本输入就把名字压扁、代码叠到价格上(第一版出图看到的); 11rem 在 390 宽又会把「空仓」挤下去
    assert "px-3 border-l-2 max-sm:order-1 max-sm:min-w-0 max-sm:grow max-sm:basis-40 max-sm:py-0 max-sm:pr-0 max-sm:pl-2" in board
    # 第一行右半: 现价 涨跌
    assert "text-right max-sm:order-2 max-sm:px-0 max-sm:py-0" in board
    # 持仓: 格子本身在手机上 display:contents, 持有 / 空仓那颗按钮跟在价的后面, 批次 / 出场线落到最后一行
    # ([R527] 成本输入框撤掉后, 持有与空仓同一颗 xs 按钮的几何, 两种行里它落在同一个位置)
    assert "whitespace-nowrap px-2 max-sm:contents" in board
    assert "buttonClass({ size: 'xs', selected: true }, 'max-sm:order-3')" in board
    assert "buttonClass({ size: 'xs', variant: 'ghost' }, 'text-muted/50 hover:text-secondary max-sm:order-3')" in board
    assert "sm:contents max-sm:order-5 max-sm:flex max-sm:basis-full" in board
    # 走势 / 位置最后, 独占一整行, 四段按段换行
    assert "whitespace-nowrap px-2 max-sm:order-4 max-sm:basis-full max-sm:px-0 max-sm:py-0" in cells
    assert "max-sm:flex-wrap max-sm:gap-y-1 max-sm:px-0" in cells


def test_R526_宽屏一个类名没动():
    """所有手机改动都挂在 max-sm: 下 —— 出现不带前缀的 flex/block 就是把宽屏的表也改了。"""
    board = code_of(BOARD)
    for cls in ("max-sm:block", "max-sm:hidden", "max-sm:flex"):
        assert cls in board
    # 表本体在宽屏仍是 table: 不许出现裸的 `block` 挂在 table / tbody 上
    assert 'className="w-full text-xs block' not in board
    assert '<tbody className="block' not in board
