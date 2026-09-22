"""[R402] 手机上第三轮: 自选分组栏够不到下面 + 还有四处「字是断的」。

R401 修的是市场环境那一页, 用户接着发来两张截图:

**一、「自选股看不到下面, 滚动下去也不行」。** 分组栏是 `flex-wrap`, 分组一多
就往下堆, 而它**既没有高度上限, 也不滚**。它是 `flex flex-col h-full` 里的一个
flex 项, `min-height: auto` 让它不肯缩到内容高度以下, 于是有多高占多高。后果
分两档: 分组中等多 → 表格被挤成一条缝(实测 375×780 下只剩 **184px**, 而里面
有 6527px 的内容); 分组再多 → 整栏超出视口, 外层又是 `h-full` 没有页面级滚动,
**下面的东西根本够不到, 也没有任何东西能滚**。

**二、异动监控那一页的字被拆成竖排。** 「全板块」成了「全/板/块」。与 R401
同一族: **定高盒子 + 允许被压扁 = 字换行之后画到盒子外面**。

**三、`/dashboard` 没有 `PageHeader`**, 所以 R401 给页头加的「粘住」惠及不到它,
那个 `fixed` 的悬浮汉堡一路压在页面内容上。(`/limit-ladder` 查过了, 它是用
`PageHeader` 的 —— R401 已经覆盖到, 这里只钉住"别再把它拆掉"。)

## 这一组不钉"某一页某个类名", 钉的是同一条规律

一个盒子**定高**, 里面的字就**必须不换行**, 外面还得**有地方让它换行**。
三样缺一样, 窄屏上就会出现"字画到盒子外面"。所以下面按这条规律逐个扫,
而不是把用户截图里那几个字面量抄进断言 —— 抄字面量的话, 换个文案就漏。
"""
from __future__ import annotations

import re

import pytest

from tests.frontend_source import code_of

#: (文件, 说明) —— 这一轮改到的那几处定高药丸/工具条
FIXED_HEIGHT_PILLS = [
    ("pages/AbnormalMoves.tsx", "异动监控的板块分段控件与工具条"),
    ("pages/settings/TickflowKeys.tsx", "TickFlow key 那一排工具按钮"),
]


@pytest.mark.parametrize("path,desc", FIXED_HEIGHT_PILLS)
def test_R402_定高盒子里的字必须不换行(path, desc):
    """`h-6`/`h-7` 这类定高盒子, 字一换行就画到盒子外面 —— 而且不报错。"""
    src = code_of(path)
    bad = []
    for m in re.finditer(r'className=[`"]([^`"]*\bh-[67]\b[^`"]*)[`"]', src):
        cls = m.group(1)
        # 只管**自己装着文字**的盒子, 两类不在此列:
        #   纯图标按钮(带 w-N 的方形) —— 里面没字;
        #   只是外框的容器(`overflow-hidden` 的分段控件外壳) —— 字在子按钮上,
        #     子按钮自己写了 nowrap 就够了, 外壳再写一遍是噪音。
        if re.search(r"\bw-[0-9]", cls) or "overflow-hidden" in cls:
            continue
        if "whitespace-nowrap" not in cls:
            bad.append(cls[:90])
    assert not bad, f"{desc}: 定高盒子没写 whitespace-nowrap, 窄屏会把字挤到盒子外面:\n  " \
                    + "\n  ".join(bad)


def test_R402_异动监控的分段控件不许被挤扁():
    """分段控件(全板块/主板/创业板/科创板/北交所)在窄屏上会被右边的搜索框挤。

    钉三层一起成立: 整组 `shrink-0` / 每个按钮不换行 / 外面那行允许换行。
    """
    src = code_of("pages/AbnormalMoves.tsx")
    i = src.index("function SegmentedControl")
    body = src[i:i + 900]
    # **分开查外壳和按钮** —— 只查"这一段里有没有 shrink-0"是条死断言:
    # 按钮自己也带 shrink-0, 把外壳那个拿掉照样绿(变异测试当场证过)。
    shell = re.search(r'className="(inline-flex[^"]*h-7[^"]*)"', body)
    assert shell, "找不到分段控件的外壳"
    assert "shrink-0" in shell.group(1), \
        f"分段控件整组会被旁边的搜索框挤扁: {shell.group(1)}"
    btn = re.search(r"className=\{`([^`]*px-2\.5[^`]*)`", body)
    assert btn, "找不到分段控件的按钮"
    assert "whitespace-nowrap" in btn.group(1), \
        f"分段控件里的字会断: {btn.group(1)}"
    # 它所在的工具条得允许换行, 否则挤不动就只能压扁自己
    assert 'className="ml-auto flex flex-wrap items-center gap-2"' in src, \
        "异动监控的工具条不许换行 —— 放不下时只能把里面的控件压扁"


def test_R402_自选分组栏有高度上限且自己能滚():
    """没有上限 = 要么把表格挤成一条缝, 要么整栏超出视口而**什么都滚不动**。"""
    src = code_of("components/WatchlistGroups.tsx")
    m = re.search(r'role="tablist"(.{0,600}?)className="([^"]*)"', src, re.S)
    assert m, "找不到分组栏的 tablist"
    cls = m.group(2)
    assert re.search(r"max-h-\[\d+(vh|px)\]", cls), \
        f"分组栏没有高度上限, 分组一多会把表格挤没:\n  {cls}"
    assert "overflow-y-auto" in cls, \
        f"分组栏有上限却不能滚 —— 那是把「看不到下面」从挤没变成裁掉:\n  {cls}"


def test_R402_分组拖拽的自动滚动跟着改成纵向():
    """这一支原来滚的是 `scrollLeft`, 且开头 `scrollWidth <= clientWidth` 就返回。

    而这一栏自从改成 `flex-wrap` 之后**永远不横向溢出**, 条件恒真 —— 整个函数
    每次都在第一行返回, 是死的。加了纵向滚动之后它该管的是纵向。
    """
    src = code_of("components/WatchlistGroups.tsx")
    i = src.index("const autoScroll")
    body = src[i:i + 500]
    assert "scrollTop" in body, "自动滚动还在滚横向 —— 这一栏溢出的是纵向"
    assert "scrollHeight" in body and "clientHeight" in body, \
        "自动滚动的判据还看着横向尺寸, 那个条件恒真"
    assert "clientY" in code_of("components/WatchlistGroups.tsx"), \
        "拖拽时传进去的还是横坐标"


def test_R402_看板页自己补上粘住的页头():
    """`/dashboard` 是全站唯一不用 `PageHeader` 的页(它的渐变条是看板自己的仪表)。

    代价是 R401 的"粘住"惠及不到它, 那个 `fixed` 的悬浮汉堡会一路压在内容上。
    钉三件: 粘住 / 背景不透明 / 给汉堡让位。
    """
    src = code_of("pages/Dashboard.tsx")
    m = re.search(r'className="(sticky top-0[^"]*)"', src)
    assert m, "看板页的头部条没有粘住"
    cls = m.group(1)
    assert re.search(r"\bbg-base\b(?!/)", cls), \
        f"粘住的那一层背景是半透明的, 内容会从底下透上来: {cls}"
    # 让位给悬浮汉堡 —— 与 PageHeader(R394) 同一个内边距、同一个断点
    band = src[m.start():m.start() + 1400]
    assert "pl-11" in band, "看板页的头部条没给悬浮汉堡让位"


def test_R402_连板梯队仍然走公共页头():
    """它不是手搓页头 —— 查过了, 三处渲染分支都用 `PageHeader`, R401 已经覆盖。

    这条钉的是"别哪天把它改成手搓的", 那样就会和看板页一样掉队。
    """
    src = code_of("pages/LimitUpLadder.tsx")
    assert src.count("<PageHeader") >= 2, "连板梯队不再走公共页头了"
