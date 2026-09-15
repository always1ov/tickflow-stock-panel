"""[R324] 转圈换骨架 —— 今日总览首次加载画版面, 决策台首次加载画骨架行。

两条硬规矩:
  1. 骨架只在 `isLoading`(本地没有任何缓存)时出现 —— 后台重取时上一份数据还在,
     盖骨架等于把好好的页面抹掉再画一遍;
  2. 决策台加载中不许再印「自选为空」—— 那句话在加载中是假的(R276 那个坑的
     另一半)。

全部走 `code_of`(剥掉注释再断言)。
"""
from __future__ import annotations

from tests.frontend_source import code_of

FLIP = "pages/FlipPaper.tsx"   # [R351] 今日总览删了, 骨架那条立论落到模拟盘
BOARD = "components/stock-analysis/WatchlistDecisionBoard.tsx"
BOARD_SK = "components/stock-analysis/decision-board/BoardSkeletonRows.tsx"


def test_R324_模拟盘首次加载画骨架_不再转圈():
    """[R324 → R351] 今日总览删了, **这条立论跟着落到模拟盘**: 首次加载画出版面的
    形状, 而不是一个居中转圈 —— 内容填进来不跳。模拟盘有自己的 `LoadingSkeleton`,
    要守的东西一个字没变, 换的只是去哪个文件里找。
    """
    code = code_of(FLIP)
    assert "{q.isLoading && <LoadingSkeleton />}" in code
    assert 'role="status"' in code, "骨架要报给读屏器"


def test_R351_骨架的形状跟着版面走():
    """**骨架与版面必须同步改。** 画出一个填不进东西的形状比直接转圈更糟 ——
    它先许诺了一个版面, 然后食言。(R340 那条同名守卫钉的是今日总览的两块,
    那一页没了; 立论搬到模拟盘, 对象换成「四格统计 + 一张曲线」。)

    [R358] 净值图改成**默认收起**之后, 那块曲线骨架自己成了食言的那一个 ——
    画一块 240px 的灰块, 数据到了那儿却是一条折叠条。所以这条守卫现在**反过来
    钉它不在**。
    """
    code = code_of(FLIP)
    sk = code[code.index("function LoadingSkeleton"):]
    # 四格统计 —— 与 `Summary` 那一排同一套栅格
    assert "sm:grid-cols-4" in sk and "Array.from({ length: 4 }" in sk
    assert "h-[240px]" not in sk, \
        "净值图已经默认收起了, 骨架还在画一块曲线大小的灰块 —— 先许诺再食言"
    # 骨架画的东西页面上得真有。**`Summary` 现在挂在筛选卡的插槽上**
    # (R358 用户: 「我是想合并到筛选的卡片里面」), 所以在整页里找, 不是只在
    # `{d && !d.reason}` 那一段里找 —— 那一段现在没有它了。
    assert "<Summary d={d} />" in code, "骨架画了四格统计, 页面上却没有 Summary"
    assert "extra={summary}" in code, "Summary 没接到筛选卡上"


def test_R324_决策台加载中画骨架行_不印自选为空():
    code = code_of(BOARD)
    tbody = code[code.index("<tbody>"):code.index("</tbody>")]
    i_load = tbody.index("enriched.isLoading ? (")
    i_empty = tbody.index("rows.length === 0 ? (")
    assert i_load < i_empty, "加载判定必须排在「为空」判定前面 —— 否则加载中照样印「自选为空」"
    blk = tbody[i_load:i_empty]
    assert "<BoardSkeletonRows cols={BOARD_COLS.length} />" in blk, "列数跟着 BOARD_COLS 走, 不写死"
    assert "import { BoardSkeletonRows } from '@/components/stock-analysis/decision-board/BoardSkeletonRows'" in code


def test_R324_骨架只认_isLoading_不认_isFetching():
    # [R351] 今日总览那一项换成模拟盘 —— 立论不变: 后台重取时上一份数据还在,
    # 盖骨架等于把已经能看的东西藏起来。
    for rel, needle in ((FLIP, "q.isLoading && <LoadingSkeleton"), (BOARD, "enriched.isLoading ? (")):
        code = code_of(rel)
        assert needle in code
        assert needle.replace("isLoading", "isFetching") not in code, \
            f"{rel}: 后台重取时上一份数据还在, 不该盖骨架"


def test_R324_骨架行对读屏是隐藏的_且行数有默认值():
    code = code_of(BOARD_SK)
    assert 'aria-hidden="true"' in code
    assert "rows = 6" in code
