"""[fork R370] 「设置 → 菜单」与侧栏菜单必须对得上。

用户: 「菜单设置里面的菜单, 要是没有的, 就应该删除」。

起因是表里躺着一条 `/paper-trading`「AI 操盘手 (仓位中心)」—— R327 把整套 AI
操盘手换成转折模拟盘之后, 那条路由只剩一个 `<Navigate to="/lots">`, 而侧栏
`nav` 里**根本没有它**。于是设置页给出一个「排序与显隐都作用不到任何东西」的
开关: 拖它、勾掉它, 屏幕上不会有任何变化, **而且不报错**。

[R598] 上游 v0.3.36 把两处菜单来源收成 `lib/navigation.ts` 一处 —— 侧栏与设置页
都从 `getNavigationEntries()` 取, 一致性由"同一产地"保证; 本文件改为钉这件事,
并保留「空壳页面不许回到菜单里」和「外部网页要能配」两条原始诉求。

读的是源码不是运行时, 因此下面每一步都自证切到了东西(切空了断言会恒真)。
"""
from __future__ import annotations

import re

from tests.frontend_source import code_of

LAYOUT = "components/Layout.tsx"
MENU = "pages/settings/MenuSettings.tsx"
NAV = "lib/navigation.ts"


def _core_nav() -> set[str]:
    """导航条目产地 `CORE_NAVIGATION = [...]` 里那一串 `id:`。"""
    code = code_of(NAV)
    i = code.index("CORE_NAVIGATION")
    blk = code[i:code.index("\n].map", i)]
    assert blk.strip(), "切到的 CORE_NAVIGATION 是空的"
    ids = set(re.findall(r"\{ id: '(/[a-z-]+)'", blk))
    assert len(ids) > 10, f"只解出 {len(ids)} 条, 多半是正则没对上写法"
    return ids


def test_R370_设置里的每一条菜单_侧栏都真有():
    """**这一条是这次改动的正题。**

    设置里列一条侧栏没有的, 等于给一个作用不到任何东西的开关 —— 拖它、勾掉它,
    屏幕上没有任何变化, 而且不报错。收成一个产地后, 两处取的必然是同一张表。
    """
    assert "getNavigationEntries(" in code_of(LAYOUT), "侧栏没走统一菜单来源"
    menu = code_of(MENU)
    assert "getNavigationEntries(" in menu, "设置页没走统一菜单来源"
    assert "CORE_NAVIGATION" in code_of(NAV), "统一菜单来源不见了"


def test_R370_那条空壳AI操盘手确实删了():
    """顺手把这一次删掉的那条钉住, 免得哪天又被加回来却没人记得当初为什么删。"""
    code = code_of(NAV)
    i = code.index("CORE_NAVIGATION")
    blk = code[i:code.index("\n].map", i)]
    assert "'/paper-trading'" not in blk, "那条空壳菜单又回来了"
    assert "AI 操盘手" not in blk, "R327 之后这套东西已经不存在了"
    # **但路由那条要留着** —— router 里写着「书签、菜单设置里存的旧路径不能断」
    router = code_of("router.tsx")
    # [R564] 转折模拟盘(/lots)并进虚拟账户, 旧入口跟着指到 /paper
    assert "{ path: 'paper-trading', element: <Navigate to=\"/paper\" replace /> }" in router, \
        "重定向路由被一起删了 —— 老书签会断"


def test_R370_侧栏有的_设置里也要能配():
    """反过来那一半: 侧栏有、设置里没有的话, 那一条**永远隐藏不掉也拖不动**。

    `/external-page` 由「外部网页」开关动态生成，不是常驻页面；两边都必须把这个
    开关喂给同一个来源，否则开关打开后侧栏多一页、设置里却配不到。
    """
    for rel in (LAYOUT, MENU):
        code = code_of(rel)
        assert "external_page_enabled" in code, f"{rel} 没把外部网页开关喂给菜单来源"
    assert "'/external-page'" in code_of(NAV), "外部网页页面的 ID 没在统一来源里"


# ── [R378] 任何一行都能拖进 / 拖出「闲置功能」 ──────────────────────────
#
# 用户: 「想要所有菜单都可以随时调整, 比如都能拉进拉出闲置里面」。
#
# 在这之前成员是编译期常量, 而设置页把顶层与组内**开了两个 DndContext** ——
# 两个上下文互相看不见对方, 从一个里拖出来的东西另一个接不住。于是界面上那几行
# 看着能拖, 实际只能在组内换先后。**这一点正是要钉死的**。
#
# [R598] 上游把「分类」做成一等公民: 分组行与页面行同在一条扁平列表里, 所以
# 只需要一个 DndContext / 一个 SortableContext, 分组行仍然整块移动。


def _menu_code() -> str:
    code = code_of(MENU)
    assert "SortableContext" in code, "切到的设置页源码不对"
    return code


def test_R378_设置页只有一个拖拽上下文():
    """两个上下文之间拖不过去 —— 这是旧版「拉不进拉不出」的根因, 不许回潮。"""
    code = _menu_code()
    n = len(re.findall(r"<DndContext\b", code))
    assert n == 1, f"设置页出现了 {n} 个 DndContext —— 跨组拖拽要求它只有一个"
    assert len(re.findall(r"<SortableContext\b", code)) == 1, \
        "分组行与页面行要在同一条扁平列表里, 才能整块挪"


def test_R378_跨容器的搬运真的接上了线():
    """`onDragEnd` 是落点那一步 —— 少接这一根线, 拖过去会弹回原处。"""
    code = _menu_code()
    assert "onDragEnd={handleDragEnd}" in code, "DndContext 没接 onDragEnd"
    assert "moveNavPage(" in code, "落点没交给 navLayout.moveNavPage 处理"
    end = code[code.index("const handleDragEnd"):]
    end = end[:end.index("\n  }")]
    assert "HOME_NAV_ID" in end, "没拦住「把固定置顶页拖走」"


def test_R378_空组还接得住东西():
    """成员全拖出来之后, 组里一个可投放点都不剩 ——
    没有这块投放区, 就成了「拖得出去, 再也拖不回来」, 而且不报错。"""
    code = _menu_code()
    assert "useDroppable({ id: 'nav:root'" in code, "顶层投放区不是真的 droppable"
    assert "<RootDropTarget" in code, "投放区没有渲染"


def test_R378_还留了一条不用拖的路():
    """键盘拖拽摸不准落点, 所以每一行另给一个归属选择框。
    固定置顶行不给 —— 它不能挪走。"""
    code = _menu_code()
    assert "移动${label}到" in code, "一键移入/移出没了"
    assert "node.type === 'page' && !home" in code, "固定置顶行不该能改归属"


def test_R378_归属只有一个产地():
    """侧栏与设置页各算各的话, 会出现「设置里在组内, 侧栏里在顶层」这种
    两边都不报错的分裂。两处都必须走 `resolveNavLayout`。"""
    assert "resolveNavLayout(" in code_of(LAYOUT), "侧栏没走统一归属计算"
    assert "resolveNavLayout(" in _menu_code(), "设置页没走统一归属计算"
    # 旧分组名单只许在 navLayout 里翻成节点用, 不许各处再拿它当归属判据
    for rel in (LAYOUT, MENU):
        assert "browseMembersOf" not in code_of(rel), \
            f"{rel} 还在自己算分组归属"
    assert "browseMembersOf(" in code_of(NAV.replace("navigation.ts", "navLayout.ts")), \
        "旧 nav_order 的分组标记没在 navLayout 里迁移"
