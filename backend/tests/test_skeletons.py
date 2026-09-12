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


def test_R324_今日骨架按真实版面摆_四个区块():
    code = code_of(TODAY_SK)
    body = code[code.index("export function TodaySkeleton"):]
    # 市场状态卡那排五个统计格, 与 MarketStatusCard 同一套栅格
    assert "sm:grid-cols-3 lg:grid-cols-5" in body
    assert "Array.from({ length: 5 }" in body
    # 三个 section: 需要行动 / 持仓体检 / 机会
    assert body.count("<SectionHead") == 3
    assert 'role="status"' in body
    assert "from '@/components/data/Skeleton'" in code, "复用仓库已有的 Skeleton 原语, 不另造一个"


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
