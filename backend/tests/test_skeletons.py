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

TODAY = "pages/Today.tsx"
TODAY_SK = "components/today/TodaySkeleton.tsx"
BOARD = "components/stock-analysis/WatchlistDecisionBoard.tsx"
BOARD_SK = "components/stock-analysis/decision-board/BoardSkeletonRows.tsx"


def test_R324_今日总览首次加载画骨架_不再转圈():
    code = code_of(TODAY)
    assert "{q.isLoading && <TodaySkeleton />}" in code
    assert "import { TodaySkeleton } from '@/components/today/TodaySkeleton'" in code
    # 原来那个居中转圈不许还在同一处
    assert "{q.isLoading && (\n        <div className=\"flex items-center justify-center py-16\">" not in code


def test_R324_今日骨架按真实版面摆():
    """[R340] 区块数从三个降到一个 —— 「需要行动」「持仓体检」整块删了。

    **这条断言的价值恰恰在这次体现了**: 删页面时它立刻变红, 逼着骨架跟着改。
    骨架画出一个填不进东西的形状, 比直接转圈更糟 —— 它先许诺了一个版面, 然后食言。
    """
    code = code_of(TODAY_SK)
    body = code[code.index("export function TodaySkeleton"):]
    # 市场状态卡那排五个统计格, 与 MarketStatusCard 同一套栅格
    assert "sm:grid-cols-3 lg:grid-cols-5" in body
    assert "Array.from({ length: 5 }" in body
    # 只剩「值得关注」一个 section
    assert body.count("<SectionHead") == 1
    assert 'role="status"' in body
    assert "from '@/components/data/Skeleton'" in code, "复用仓库已有的 Skeleton 原语, 不另造一个"


def test_R340_两块整个删干净_骨架跟着同步():
    """**同步的是两个文件, 不是一句注释。** 骨架多画一块或少画一块都在说谎。

    `code_of` 已经把注释剥掉了, 所以这里扫到的「需要行动」只可能来自真正会渲染
    的文字 —— 说明它为什么被删的那段注释不会把断言喂饱。
    """
    page = code_of(TODAY)
    sk = code_of(TODAY_SK)
    for gone in ("需要行动", "持仓体检", "回撤纪律线"):
        assert gone not in page, f"页面还留着「{gone}」"
    assert page.count("<section") == 1, "页面只该剩「值得关注」一个 section"
    assert sk[sk.index("export function TodaySkeleton"):].count("<SectionHead") == 1


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
    for rel, needle in ((TODAY, "q.isLoading && <TodaySkeleton"), (BOARD, "enriched.isLoading ? (")):
        code = code_of(rel)
        assert needle in code
        assert needle.replace("isLoading", "isFetching") not in code, \
            f"{rel}: 后台重取时上一份数据还在, 不该盖骨架"


def test_R324_骨架行对读屏是隐藏的_且行数有默认值():
    code = code_of(BOARD_SK)
    assert 'aria-hidden="true"' in code
    assert "rows = 6" in code
