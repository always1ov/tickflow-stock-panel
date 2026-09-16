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
