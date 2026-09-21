"""[R394] 手机上页头不许再塌 —— 三条纪律各自钉住。

用户: 「我用手机看网页显示排版非常不正常, 所有页面都是」。改之前实测 19 条路由
里有 12 条的页标题压在悬浮汉堡底下, 其中「策略」那一页的工具栏被压成一个字宽
(中文竖着排), 按钮甚至排到了 x=391 —— 屏幕才 390 宽, 整条被根节点的
`overflow-hidden` 吃掉。改完同一份扫描 0/19。

这里钉的是让它不再塌的那三件事。**都钉性质, 不钉那一串 class 字面量** ——
`test_theme_palette.py::test_R379_页头有呼吸感而且只有一个产地` 当初就是钉了整串
`"flex min-w-0 items-center gap-2.5"`, 这次对齐方式一个字没动、只是多加了几个
响应式类, 它就红了(那条已改成只问 `items-center`)。同一个坑, 不重复踩。
"""
from __future__ import annotations

import re

import pytest

from tests.frontend_source import SRC, code_of

HEADER = "components/PageHeader.tsx"
LAYOUT = "components/Layout.tsx"


def _code(rel: str) -> str:
    try:
        return code_of(rel)
    except OSError:
        pytest.skip("拿不到前端源码(只跑后端时正常)")


def _u(n: str) -> int:
    """Tailwind 间距刻度 → px(1 = 0.25rem = 4px)。"""
    return int(n) * 4


# ================================================================
# ① 页头自己就得会换行 —— 不能指望调用方传
# ================================================================

def test_R394_页头的基础类里就有换行():
    """**根因是这一条。** `flex-wrap` 原来只写在 `PageShell` 传进来的 className
    里, 而有 10 个页面是**直接用 `PageHeader`** 的, 拿不到那份 className ——
    于是页头是一行不换的 flex, 工具栏要么被压扁要么溢出视口。

    钉法: 只看 `cn(...)` 里**基础类那一段**(className 参数之前), 调用方传什么
    都不算数。
    """
    code = _code(HEADER)
    base = code.split("cn(", 1)[1].split("className,", 1)[0]
    assert "flex-wrap" in base, (
        "页头的基础类里没有 flex-wrap —— 不经 PageShell 的那些页面又会压扁/溢出")
    assert "flex-nowrap" in base, (
        "宽屏没有还原成一行: 页头在大屏上本来就该是一行, 换行会白占一屏高度")


# ================================================================
# ② 给悬浮汉堡让的位置, 要跟汉堡自己的位置对得上
# ================================================================

def test_R394_标题让出的位置盖得住那个悬浮汉堡():
    """两个数分别写在两个文件里, **各改各的必然对不上**, 而对不上的表现就是
    标题又压回按钮底下 —— 不报错, 只是难看。所以这里把两边的数算一遍。

    `Layout` 的按钮: `fixed left-{L} ... p-{P}`, 图标 `h-4 w-4`(16px), 一圈 1px 边框
    →  右缘 = L*4 + (P*4*2 + 16 + 2)
    页头的标题块: header 自己的 `px-{X}` + 标题块的 `pl-{N}`
    """
    header, layout = _code(HEADER), _code(LAYOUT)

    burger = re.search(r"isDesktop \?[^:]+:\s*'left-(\d+) top-(\d+) p-(\d+)'", layout)
    assert burger, "定位不到移动端汉堡的那行样式 —— 这条守卫的锚要跟着改"
    right_edge = _u(burger.group(1)) + _u(burger.group(3)) * 2 + 16 + 2

    title_row = header.split("<h1", 1)[0].rsplit("<div", 1)[-1]
    pl = re.search(r"\bpl-(\d+)\b", title_row)
    assert pl, "标题块没有给汉堡让位(pl-*), 标题会压在按钮底下"
    assert "md:pl-0" in title_row, "宽屏没有把让出来的位置收回去, 标题会白白缩进"

    px = re.search(r"\bpx-(\d+)\b", header.split("cn(", 1)[1].split("className,", 1)[0])
    assert px, "页头没有水平内边距了, 这条守卫的算式要跟着改"

    have = _u(px.group(1)) + _u(pl.group(1))
    assert have >= right_edge, (
        f"标题从 {have}px 起排, 而汉堡的右缘在 {right_edge}px —— 标题压在按钮底下了")


def test_R394_两边用同一个断点():
    """按钮在哪个宽度出现, 位置就得在哪个宽度让出来。各写各的断点, 中间那一段
    宽度里必然错一头: 要么按钮还在而位置已经收回, 要么反过来白缩进。"""
    mq = _code("lib/useMediaQuery.ts")
    bp = re.search(r"useIsDesktop[\s\S]{0,200}?min-width:\s*(\d+)px", mq)
    assert bp, "定位不到 useIsDesktop 的断点 —— 这条守卫的锚要跟着改"
    assert bp.group(1) == "768", (
        f"按钮改在 {bp.group(1)}px 出现, 而标题让位收回仍写死在 md(768px) —— "
        "中间那段宽度里必然错一头")
    title_row = _code(HEADER).split("<h1", 1)[0].rsplit("<div", 1)[-1]
    assert "md:pl-0" in title_row, "让位的收回断点不是 md(768px), 与按钮出现的断点对不上"


# ================================================================
# ③ 塞进页头右边的工具栏, 自己也得会换行
# ================================================================

def test_R394_页头右边的工具栏都能换行():
    """`PageHeader` 的 `right` 容器是 `flex-wrap` 的, 但它只管**直接子节点**。
    页面往往只塞一个 `<div className="flex items-center gap-2">` 进去 —— 那一个
    div 就是唯一的直接子节点, 于是里面十几个按钮全被压扁, 外层的 wrap 一点用
    没有。用户截图里「策略池」竖着排成一列, 就是这么来的。
    """
    bad: list[str] = []
    for p in sorted(SRC.rglob("*.tsx")):
        rel = str(p.relative_to(SRC))
        for m in re.finditer(r'right=\{\s*\n?\s*<div className="([^"]*)"', p.read_text(encoding="utf-8")):
            cls = m.group(1)
            if "flex" in cls and "flex-wrap" not in cls and "grid" not in cls:
                bad.append(f"{rel}: {cls}")
    assert not bad, (
        "这些页头工具栏是一行不换的 flex —— 窄屏上会把按钮压成一个字宽:\n  "
        + "\n  ".join(bad))
