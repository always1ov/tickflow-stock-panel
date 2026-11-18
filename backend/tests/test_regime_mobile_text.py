"""[R401] 市场环境页在手机上"字是断的"。

用户发来手机截图 + 一句「文字有问题」。量出来是四处, 根因只有两个:

**一、定高药丸 + 允许被压扁。** 视图页签(市场环境/情绪周期)与时间范围
(1年/2年/全部/自定义)都是 `h-6`/`h-7` 的定高药丸, 而它们所在的 flex 行既
不许换行、药丸组又是默认的 `shrink: 1`。旁边那句说明一长, 药丸就被挤窄,
里面的字换行, 而盒子是定高的 —— **换出来的那个字直接画到药丸外面**。
实测 375px 下「市场环境」这个按钮 `scrollHeight 34 > clientHeight 28`,
屏幕上就是「市场环」一行、「境」孤零零掉在药丸下面。
区块标题「环境综合分趋势」被腰斩成「环境综合/分趋势」是同一件事的另一面:
右边那句说明是同一行里的兄弟, 它一长就把标题压到只剩四个字宽。

**二、页头跟着内容滚, 而汉堡是钉死在视口上的。** R394 给标题块留了 `pl-11`
专门让开那个 `fixed left-3 top-3` 的悬浮汉堡 —— 但页头会滚走, 汉堡不会。
往下滚一点, 汉堡就压在了下面第一排控件上(用户截图里压住「1年」; 实测滚
120px 之后压住的是「市场环境」页签)。**让位让了个寂寞。**

图例压住轴名那一处不在这个文件里 —— 它是算出来的, 由
`frontend/src/lib/echartsLegend.test.ts` 钉着。
"""
from __future__ import annotations

import re

from tests.frontend_source import code_of

REGIME_CSS = "pages/Regime.css"
HEADER = "components/PageHeader.tsx"
SHELL = "components/PageShell.tsx"


def _has(selector: str, declaration: str) -> bool:
    """`Regime.css` 里有没有一条规则(选择器列表含该项)带这条声明。

    选择器可能和其他规则共用一行(`.regime-toolbar, .regime-range { … }`),
    所以按逗号拆开比; 媒体查询里的同名规则也算(只要有一处成立即可)。
    """
    css = code_of(REGIME_CSS)
    for raw_selector, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
        parts = [part.strip() for part in raw_selector.split(",")]
        if selector in parts and declaration in body:
            return True
    return False


def test_R401_定高药丸里的字不许断():
    """定高盒子里的字一旦换行就会画到盒子外面 —— 所以定高就必须配不换行。

    [R811] 这一页换成了作者版的 `regime-range` / `regime-tabs` 分段切换,
    不再是 fork 的 SEG; 守卫跟着换锚点, 钉的还是同一件事。
    """
    for selector in (".regime-range button", ".regime-tabs button"):
        assert _has(selector, "white-space: nowrap"), (
            f"{selector} 没写 white-space: nowrap, 窄屏上字会换行并溢出盒子")


def test_R401_药丸组不许被旁边的说明挤扁():
    """药丸自己不换行还不够: 外面那层若允许被压缩, 压到比内容还窄时字照样换行。

    钉的是"这两层一起成立" —— 药丸组 `flex-shrink: 0`, 且它所在的行允许换行
    (放不下就整组换到下一行去, 而不是把自己压扁)。
    """
    for selector in (".regime-toolbar", ".regime-tabbar"):
        assert _has(selector, "flex-wrap: wrap"), (
            f"{selector} 不许换行, 放不下时只能把药丸压扁")
    for selector in (".regime-range", ".regime-tabs"):
        assert _has(selector, "flex-shrink: 0"), f"{selector} 会被旁边的说明挤扁"


def test_R401_区块标题不许被右边的说明腰斩():
    """`SectionTitle` 的 `hint` 最长的一条有三小句, 窄屏上会把标题压成两行。"""
    assert _has(".regime-section-heading", "flex-wrap: wrap"), (
        "标题行不许换行 —— 说明放不下时就只能去挤标题")
    assert _has(".regime-section-title", "flex-shrink: 0"), (
        "区块标题会被右边的说明压窄")
    assert _has(".regime-section-title h2", "white-space: nowrap"), (
        "区块标题会被腰斩")


def test_R401_页头粘住_否则R394的让位是假的():
    """R394 给标题块留的 `pl-11` 只在"汉堡确实悬在页头上"时才有意义。

    页头一旦滚走, 那个 `fixed` 的汉堡就落到页面内容上 —— 让位让了个寂寞。
    """
    src = code_of(HEADER)
    assert re.search(r"'sticky top-0[^']*'", src), "页头没有粘住"
    assert "pl-11" in src, "给悬浮汉堡让位的内边距没了(R394)"


def test_R401_粘住的页头必须是不透明的():
    """内容会从粘住的页头底下滑过去。留一点透明就是两层字淡淡叠在一起。

    **两处都要查**: `PageShell` 传进来的 className 经 `cn()` 会盖掉 `PageHeader`
    自己写的那个背景色, 只改一处不生效 —— 这是本仓库反复踩的那一类。
    """
    for path in (HEADER, SHELL):
        src = code_of(path)
        for m in re.finditer(r"bg-base/\d+", src):
            raise AssertionError(
                f"{path} 里页头背景是半透明的({m.group(0)}) —— 粘住之后内容会透上来")
