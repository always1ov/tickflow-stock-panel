"""[fork R370] 「设置 → 菜单」那张表与侧栏菜单必须对得上。

用户: 「菜单设置里面的菜单, 要是没有的, 就应该删除」。

起因是表里躺着一条 `/paper-trading`「AI 操盘手 (仓位中心)」—— R327 把整套 AI
操盘手换成转折模拟盘之后, 那条路由只剩一个 `<Navigate to="/lots">`, 而侧栏
`nav` 里**根本没有它**。于是设置页给出一个「排序与显隐都作用不到任何东西」的
开关: 拖它、勾掉它, 屏幕上不会有任何变化, **而且不报错**。

这类不一致**只会越攒越多**: 每删一个页面就多一条。所以这里钉的不是"那一条没了",
而是**两张表必须一一对上** —— 让它不能再犯。

两张表都在前端源码里, 所以靠正则读源码比对。**读的是源码不是运行时**, 因此
下面每一步都自证切到了东西(切空了断言会恒真, 这仓库栽过好几次)。
"""
from __future__ import annotations

import re

from tests.frontend_source import code_of

LAYOUT = "components/Layout.tsx"
MENU = "pages/settings/MenuSettings.tsx"


def _sidebar_nav() -> set[str]:
    """侧栏 `const nav = [...]` 里那一串 `to:`。"""
    code = code_of(LAYOUT)
    i = code.index("const nav = [")
    blk = code[i:code.index("\n]", i)]
    assert blk.strip(), "切到的 nav 是空的"
    ids = set(re.findall(r"\{ to: '(/[a-z-]+)'", blk))
    assert len(ids) > 10, f"只解出 {len(ids)} 条, 多半是正则没对上写法"
    return ids


def _builtin_pages() -> set[str]:
    """设置页 `const BUILTIN_PAGES = [...]` 里那一串 `id:`(分组行不算页面)。"""
    code = code_of(MENU)
    i = code.index("const BUILTIN_PAGES")
    blk = code[i:code.index("\n]", i)]
    assert blk.strip(), "切到的 BUILTIN_PAGES 是空的"
    ids = set(re.findall(r"\{ id: '(/[a-z-]+)'", blk))
    assert len(ids) > 10, f"只解出 {len(ids)} 条, 多半是正则没对上写法"
    return ids


def test_R370_设置里的每一条菜单_侧栏都真有():
    """**这一条是这次改动的正题。**

    设置里列一条侧栏没有的, 等于给一个作用不到任何东西的开关 —— 拖它、勾掉它,
    屏幕上没有任何变化, 而且不报错。
    """
    extra = _builtin_pages() - _sidebar_nav()
    assert not extra, (
        "设置 → 菜单里这几条在侧栏根本不存在, 它们的排序/显隐作用不到任何东西:\n  "
        + "\n  ".join(sorted(extra)))


def test_R370_那条空壳AI操盘手确实删了():
    """顺手把这一次删掉的那条钉住, 免得哪天又被加回来却没人记得当初为什么删。"""
    code = code_of(MENU)
    i = code.index("const BUILTIN_PAGES")
    blk = code[i:code.index("\n]", i)]
    assert "'/paper-trading'" not in blk, "那条空壳菜单又回来了"
    assert "AI 操盘手" not in blk, "R327 之后这套东西已经不存在了"
    # **但路由那条要留着** —— router 里写着「书签、菜单设置里存的旧路径不能断」
    router = code_of("router.tsx")
    assert "{ path: 'paper-trading', element: <Navigate to=\"/lots\" replace /> }" in router, \
        "重定向路由被一起删了 —— 老书签会断"


def test_R370_侧栏有的_设置里也要能配():
    """反过来那一半: 侧栏有、设置里没有的话, 那一条**永远隐藏不掉也拖不动**。

    `/external-page` 是有意不在这张表里的 —— 它由「外部网页」自己那个开关控制
    要不要出现, 不是一个常驻页面。除它之外不该再有第二个。
    """
    missing = _sidebar_nav() - _builtin_pages()
    assert missing <= {"/external-page"}, (
        "侧栏有这几条, 但设置里配不到(隐藏不掉也拖不动):\n  "
        + "\n  ".join(sorted(missing - {"/external-page"})))


# ── [R378] 任何一行都能拖进 / 拖出「闲置功能」 ──────────────────────────
#
# 用户: 「想要所有菜单都可以随时调整, 比如都能拉进拉出闲置里面」。
#
# 在这之前成员是编译期常量, 而设置页把顶层与组内**开了两个 DndContext** ——
# 两个上下文互相看不见对方, 从一个里拖出来的东西另一个接不住。于是界面上那几行
# 看着能拖, 实际只能在组内换先后。**这一点正是要钉死的**: 合成一个上下文之后,
# 很容易在后续改动里因为"组内排序不该把分组行卷进去"这种理由又被拆回两个。


def _menu_code() -> str:
    code = code_of(MENU)
    assert "SortableContext" in code, "切到的设置页源码不对"
    return code


def test_R378_设置页只有一个拖拽上下文():
    """两个上下文之间拖不过去 —— 这是旧版「拉不进拉不出」的根因, 不许回潮。"""
    code = _menu_code()
    n = len(re.findall(r"<DndContext\b", code))
    assert n == 1, f"设置页出现了 {n} 个 DndContext —— 跨组拖拽要求它只有一个"
    # 两串仍然分开(分组行要能整块挪), 所以 SortableContext 该是两个
    assert len(re.findall(r"<SortableContext\b", code)) == 2, \
        "成员不再单独成一串的话, 拖分组行就不是整块挪了"


def test_R378_跨容器的搬运真的接上了线():
    """`onDragOver` 是跨容器那一步的落点 —— 少接这一根线, 拖过去会弹回原处。"""
    code = _menu_code()
    for hook in ("onDragStart={handleDragStart}", "onDragOver={handleDragOver}",
                 "onDragEnd={handleDragEnd}", "onDragCancel={handleDragCancel}"):
        assert hook in code, f"DndContext 少接了 {hook}"
    over = code[code.index("const handleDragOver"):]
    over = over[:over.index("\n  }")]
    assert over.strip()
    # 分组行不能钻进自己肚子里
    assert "activeId === BROWSE_GROUP_ID" in over, "没拦住「把分组行拖进它自己」"
    assert "MEMBER_DROP_ID" in over, "空组的投放区没接进来"


def test_R378_空组还接得住东西():
    """成员全拖出来之后, `SortableContext` 里一个可投放点都不剩 ——
    没有这块投放区, 就成了「拖得出去, 再也拖不回来」, 而且不报错。"""
    code = _menu_code()
    assert "useDroppable({ id: MEMBER_DROP_ID })" in code, "空组投放区不是真的 droppable"
    assert "memberEntries.length === 0 && (" in code, "投放区没有在空组时渲染"


def test_R378_还留了一条不用拖的路():
    """跨容器的**键盘**拖拽摸不准落点, 所以每一行另给一个一键移入/移出。
    分组行不给 —— 它不能钻进自己肚子里。"""
    code = _menu_code()
    assert "const toggleGroup = (id: string)" in code, "一键移入/移出没了"
    assert "onToggleGroup={entry.id === BROWSE_GROUP_ID ? undefined : toggleGroup}" in code, \
        "分组行不该有「收进自己」这个按钮"
    assert "onToggleGroup={toggleGroup}" in code, "组内成员没有「移出」按钮"


def test_R378_归属只有一个产地():
    """侧栏与设置页各算各的话, 会出现「设置里在组内, 侧栏里在顶层」这种
    两边都不报错的分裂。两处都必须走 `browseMembersOf`。"""
    layout = code_of(LAYOUT)
    assert "browseMembersOf(savedOrder)" in layout, "侧栏没按保存的顺序算归属"
    assert "browseMembersOf(effectiveOrder)" in _menu_code(), "设置页没按保存的顺序算归属"
    # 写死的名单只许当默认值用, 不许再有人拿它当归属判据
    for rel in (LAYOUT, MENU):
        assert "BROWSE_GROUP.paths" not in code_of(rel), \
            f"{rel} 还在直接读默认名单 —— 那是默认值, 不是归属"
