"""[R276] 决策台的分组筛选 —— **筛掉的东西必须有人交代**。

用户: 「这里还要加个选择按钮, 能下拉菜单只看哪个分组」。

## 加一个筛选, 就是加三个"东西会凭空消失"的入口

这一组守的不是"下拉菜单画出来了没有"(那个看一眼就知道), 而是**筛选把行藏起来
之后, 界面还说不说得清楚**。这个仓库里同一个形状的毛病已经犯过好几轮了(R271 的
假孤儿、R274 的静默 except、R275 的 500), 分组筛选把它原样又摆了三份:

1. **记住的分组被删掉** → 表永远是空的, 底下写着「自选为空」。那句话是假的,
   而且指向完全错误的动作(去自选页添加标的)。
2. **定位定不到** → 那只票被筛选挡着, 点「定位」看起来就是没反应。
   而且挡路的可能不止一个 —— 只撤一个照样出不来。
3. **下拉里的数字口径** → 写"这个组有 8 只"而点进去 0 行, 人只会以为它坏了。

## 还有一处顺带纠正的错位

表头「N 只 · 持有 M」里两个数**原本来自不同的批次**: N 是筛过的, M 是全自选的。
加了分组之后这个错位天天撞见(「12 只 · 持有 8」而那 12 只里一只持仓都没有),
所以一并改成同一批。
"""
from __future__ import annotations

import re

import pytest

from tests.frontend_source import code_of, read_src

BOARD = "components/stock-analysis/WatchlistDecisionBoard.tsx"


@pytest.fixture(scope="module")
def code() -> str:
    return code_of(BOARD)


# ================================================================
# 接线: 分组归属真的取到了, 也真的用来筛了
# ================================================================

def test_R276_分组归属得单独取():
    """`/watchlist/enriched` **不带 group_ids** —— 它只出行情。

    忘了这件事的话会写成"从 enriched 的行里读分组", 那永远是 undefined,
    于是每一只都算「未分组」: 选任何一个分组都是空表, 而且不报错。
    """
    code = code_of(BOARD)
    assert "api.watchlistList()" in code, "分组归属在自选列表里, 得单独取一份"
    assert "QK.watchlist," in code, "走已有的 QK, 与自选页共用缓存(不多一次请求)"
    assert "group_ids" in code


def test_R276_归属没到之前不许筛():
    """空的归属表会让每一只都看着像「未分组」。

    选了某个分组的人在加载那一瞬间会看到一张空表 —— 而那不是真的。
    与「只看要动的」在判定没回来时不过滤是同一个取舍: 宁可多显示。
    """
    code = code_of(BOARD)
    fn = code[code.index("const inGroup"):]
    fn = fn[:fn.index("\n  const signalsQ")]
    assert "!groupsReady" in fn, "归属还没到时必须一律返回 true(不筛)"


def test_R276_三个筛选是分开两层的():
    """`scoped`(过了持有/要动的) → `rows`(再过分组)。

    合成一层的话下拉里的数字就没法算 —— 那些数字要的正是"过完另外两个筛选、
    但还没过分组"的那一批。
    """
    code = code_of(BOARD)
    assert "const scoped = useMemo(" in code
    assert "scoped.filter((r) => inGroup(r.symbol))" in code


# ================================================================
# ① 记住的分组被删掉 —— 最容易变成"永远空表"的那一条
# ================================================================

def test_R276_选择要记住():
    code = code_of(BOARD)
    assert "storage.boardGroupFilter" in code, "分组是长期编队, 刷新一次就忘等于没做"


def test_R276_分组没了要自动退回并说一声():
    """**这一条是这组里分量最重的。**

    自选页删掉一个分组之后, 决策台还挂着那个 id: 表永远是空的, 而底下那句
    「自选为空」既说错了原因、又把人指向完全错误的动作。
    """
    code = code_of(BOARD)
    i = code.index("groupsQ.data, groupFilter")
    blk = code[code.rindex("useEffect", 0, i):i]
    assert "if (!groupsQ.data) return" in blk, "名录还没加载完就判「不存在」是冤枉它"
    assert "setGroupFilter(G_ALL)" in blk, "对不上要退回全部"
    assert "toast(" in blk, "**必须说一声** —— 悄悄退回就是另一种静默"


def test_R276_哨兵不是null():
    """「未分组」本身是一个可选项。拿 null 表示它, 就和"没存过"撞在一起了。"""
    code = code_of(BOARD)
    assert "const G_ALL = 'all'" in code
    assert "const G_UNGROUPED = 'ungrouped'" in code
    store = code_of("lib/storage.ts")
    assert "boardGroupFilter:     kv<string>(" in store, "存字符串, 不是 string | null"


# ================================================================
# ② 定位: 挡路的可能不止一个
# ================================================================

def test_R276_定位要认全三个筛选():
    """原来只认「只看持有」。漏掉的那两个会让「定位」看起来是坏的。"""
    code = code_of(BOARD)
    blk = code[code.index("const locate ="):]
    blk = blk[:blk.index("useEffect(")]
    assert "const byHeld" in blk and "const byAction" in blk and "const byGroup" in blk, \
        "三个筛选都要判"
    assert "urgency[sym]?.level === 'idle'" in blk, "「只看要动的」原来根本没判"


def test_R276_挡路的要一次全撤掉():
    """只撤一个的话行还是不出现 —— 从用户那边看就是"点了定位没反应"。"""
    code = code_of(BOARD)
    blk = code[code.index("const locate ="):]
    blk = blk[:blk.index("useEffect(")]
    for cond, act in (("byHeld", "setHeldOnly(false)"),
                      ("byAction", "setActionableOnly(false)"),
                      ("byGroup", "setGroupFilter(G_ALL)")):
        assert f"if ({cond}) {act}" in blk, f"{cond} 挡住时没撤掉它"
    assert "blockers.join" in blk, "撤了哪几个要说出来"


def test_R276_只撤挡路的那个():
    """反向: 没挡路的筛选不该被顺手关掉 —— 那是在替人做没请求过的决定。"""
    code = code_of(BOARD)
    blk = code[code.index("const locate ="):]
    blk = blk[:blk.index("useEffect(")]
    assert "if (groupFilter !== G_ALL) setGroupFilter(G_ALL)" not in blk, \
        "撤分组的条件必须是「它挡路了」, 不是「它开着」"


# ================================================================
# ③ 下拉里那些数字的口径
# ================================================================

def test_R276_数字是能看到几行不是组里有几只():
    """两者在开着「只看要动的」时能差很远。

    写"组里有 8 只"而点进去 0 行, 人只会以为它坏了 —— 界面说的和界面做的
    必须是同一件事。
    """
    code = code_of(BOARD)
    blk = code[code.index("const groupCounts = useMemo("):]
    blk = blk[:blk.index("useEffect(")]
    assert "for (const r of scoped)" in blk, "从 scoped 算(已过另两个筛选), 不是从全量自选"


def test_R276_口径要写在菜单上():
    """不写的话反过来会被读成"这个组只剩 3 只票了"。"""
    code = code_of(BOARD)
    assert "menuLabel=\"只看哪个分组(数字=当前筛选下能看到几只)\"" in code


def test_R276_一票多组两边各计一次():
    """与 lib/watchlistGroupStats.ts 同口径 —— 两处各判一套迟早对不上。"""
    code = code_of(BOARD)
    blk = code[code.index("const groupCounts = useMemo("):]
    blk = blk[:blk.index("useEffect(")]
    assert "for (const id of ids) c[id] = (c[id] ?? 0) + 1" in blk


def test_R276_空分组也要列出来():
    """只从 scoped 累加的话, 今天一只都没命中的分组会从菜单里**整个消失** ——
    人会以为分组被删了。先按名录铺 0, 再累加。"""
    code = code_of(BOARD)
    blk = code[code.index("const groupCounts = useMemo("):]
    blk = blk[:blk.index("useEffect(")]
    assert "for (const g of groups) c[g.id] = 0" in blk


# ================================================================
# 版面: 空表提示 / 表头计数 / 导出页脚
# ================================================================

def test_R276_空表不许再说自选为空():
    """开着筛选把行筛成 0 时, 「自选为空」既说错原因又指向错误的动作。"""
    code = code_of(BOARD)
    assert "totalRows === 0" in code, "得先分清是真的空还是被筛空的"
    assert "之后一只不剩" in code


def test_R276_空表要点名是谁挡的():
    code = code_of(BOARD)
    i = code.index("之后一只不剩")
    blk = code[code.rindex("totalRows === 0", 0, i):i]
    for name in ("只看要动的", "只看持有", "groupLabel"):
        assert name in blk, f"没点名 {name}"


def test_R276_表头两个数出自同一批():
    """原来 N 是筛过的、M 是全自选的 —— 「12 只 · 持有 8」而那 12 只里可能一只都没有。"""
    code = code_of(BOARD)
    assert "持有 {heldInView}" in code
    assert "rows.filter((r) => r.held).length" in code


def test_R276_全自选持有数仍留给分析按钮():
    """`heldCount` 不能跟着改成看得见的行数 —— 「分析持有」跑的是**全部**持有股
    (heldSyms 走 allSyms), 拿看得见的行数去关那个按钮会对不上。"""
    code = code_of(BOARD)
    assert "const heldCount = Object.values(positions).filter((p) => p.held).length" in code
    assert "{heldCount > 0 && (" in code


def test_R276_筛掉了多少要写出来():
    """否则「12 只」会被读成"我的自选只剩 12 只了"。"""
    code = code_of(BOARD)
    assert "rows.length < totalRows" in code and "自选共 {totalRows}" in code


def test_R276_导出页脚的分母是自选总数():
    """原来传的是筛完的 rows.length, 页脚永远写成「导出 12 只(自选共 12 只)」——
    而那句话的用处**正是**让人知道筛掉了多少。"""
    code = code_of(BOARD)
    assert "buildBoardHtml(exportRows, totalRows, exportCols)" in code
    assert "自选共 ${rows.length}" not in code


# ================================================================
# 复用与开销
# ================================================================

def test_R276_下拉复用已有的分组菜单():
    """定位/键盘/点外面关闭/配色全都现成 —— 另写一个只会多一份要同步的东西。"""
    code = code_of(BOARD)
    assert "WatchlistGroupMenu" in code
    assert "resolveWatchlistGroupColor" in code, "选中时按分组自己的颜色亮, 与自选页同一套"


def test_R276_不新增接口():
    """两份数据都走已有的 QK, 与自选页/侧栏/监控共用同一份 React Query 缓存。"""
    code = code_of(BOARD)
    assert "QK.watchlistGroups" in code
    assert "staleTime: 60_000" in code


def test_R276_断言没被自己的注释喂饱():
    """第七次防同一个坑: 这个文件里查的标识符要真的出现在**代码**里。

    `code_of` 已经按块剥了注释, 这里再自证一次 —— 原文里注释很多, 万一剥漏了,
    上面一大半断言会变成永远绿。
    """
    raw = read_src(BOARD)
    code = code_of(BOARD)
    assert "R276" in raw, "原文里应该有 R276 的说明"
    assert len(code) < len(raw), "一个字都没剥掉? 那剥注释这一步没生效"
    # 只出现在注释里的字眼, 剥完必须消失
    assert "宁可多显示" not in code
    assert re.search(r"\bconst G_ALL\b", code), "剥过头把代码也吃了"
