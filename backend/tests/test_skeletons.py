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

FLIP = "components/paper/FlipFollowCard.tsx"   # [R351] 今日总览删了, 骨架落到模拟盘 → [R564] 跟着搬进虚拟账户的信号块
BOARD = "components/stock-analysis/WatchlistDecisionBoard.tsx"
BOARD_SK = "components/stock-analysis/decision-board/BoardSkeletonRows.tsx"


def test_R324_模拟盘首次加载画骨架_不再转圈():
    """[R324 → R351] 今日总览删了, **这条立论跟着落到模拟盘**: 首次加载画出版面的
    形状, 而不是一个居中转圈 —— 内容填进来不跳。模拟盘有自己的 `LoadingSkeleton`,
    要守的东西一个字没变, 换的只是去哪个文件里找。
    """
    code = code_of(FLIP)
    assert "{q.isLoading ? (\n          <FlipSkeleton />" in code
    assert 'role="status"' in code, "骨架要报给读屏器"


def test_R351_骨架的形状跟着版面走():
    """**骨架与版面必须同步改。** 画出一个填不进东西的形状比直接转圈更糟 ——
    它先许诺了一个版面, 然后食言。

    [R564] 模拟盘那一排统计格随页面删了; 首页落到虚拟账户, 立论跟着搬到「跟六态转折」
    信号块: 骨架的两段栅格(明早开盘的卡片、持仓的方块)断点逐个与真东西对上。
    """
    import re

    code = code_of(FLIP)
    sk = code[code.index("function FlipSkeleton"):]
    sk = sk[:sk.index("\n}\n")]
    card = code[code.index("export function FlipFollowCard"):code.index("function FlipSkeleton")]

    def grids(block: str) -> list[str]:
        return re.findall(r'className="(?:mt-2 )?(grid [^"]*grid-cols[^"]*)"', block)

    want = [g.replace("mt-2 ", "") for g in grids(card)]
    got = grids(sk)
    # 明早开盘那段的卡片栅格、持仓那段的方块栅格, 骨架里都得有一份一模一样的
    for g in ("grid gap-2 lg:grid-cols-2 2xl:grid-cols-3", "grid grid-cols-2 gap-2 lg:grid-cols-3 2xl:grid-cols-5"):
        assert g in want, f"版面里没有这一段栅格了: {g}"
        assert g in got, f"骨架没跟上版面: 缺 {g}"

def test_R324_决策台加载中画骨架行_不印自选为空():
    code = code_of(BOARD)
    # [R526] tbody 在手机上要变块, 标签带了 className —— 不再按 `<tbody>` 整字匹配
    tbody = code[code.index("<tbody"):code.index("</tbody>")]
    i_load = tbody.index("enriched.isLoading ? (")
    i_empty = tbody.index("totalRows === 0 ? (")   # [R530] 空表只剩「自选为空」一种, 判的是自选总数
    assert i_load < i_empty, "加载判定必须排在「为空」判定前面 —— 否则加载中照样印「自选为空」"
    blk = tbody[i_load:i_empty]
    assert "<BoardSkeletonRows cols={BOARD_COLS.length} />" in blk, "列数跟着 BOARD_COLS 走, 不写死"
    assert "import { BoardSkeletonRows } from '@/components/stock-analysis/decision-board/BoardSkeletonRows'" in code


def test_R324_骨架只认_isLoading_不认_isFetching():
    # [R351] 今日总览那一项换成模拟盘 —— 立论不变: 后台重取时上一份数据还在,
    # 盖骨架等于把已经能看的东西藏起来。
    for rel, needle in ((FLIP, "q.isLoading ? ("), (BOARD, "enriched.isLoading ? (")):
        code = code_of(rel)
        assert needle in code
        assert needle.replace("isLoading", "isFetching") not in code, \
            f"{rel}: 后台重取时上一份数据还在, 不该盖骨架"


def test_R324_骨架行对读屏是隐藏的_且行数有默认值():
    code = code_of(BOARD_SK)
    assert 'aria-hidden="true"' in code
    assert "rows = 6" in code
