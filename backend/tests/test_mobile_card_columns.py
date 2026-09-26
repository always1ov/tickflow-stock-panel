"""[R398] 窄屏上"一行一张"的卡片要铺满那一列。

用户截图(策略页, 手机): 每张策略卡宽度都不一样, 右边缘是锯齿状 ——
「跌破生命线」窄、「相对活力指数转强」几乎顶到边。

原因是这些卡是 `inline-flex` 的, **按各自内容撑宽**。宽屏上一行塞得下好几张,
平铺开来看不出问题; 到手机上一行只放得下一张, 每张的宽度差就全暴露了。

**这条钉的是性质**: 卡片在窄屏有一个铺满的宽度, 并且在 `sm` 以上把它还原回
自适应 —— 少了前者是锯齿, 少了后者会把宽屏的平铺也毁掉(每张占满一行)。
"""
from __future__ import annotations

import re

import pytest

from tests.frontend_source import code_of

CARD = "components/screener/StrategyCard.tsx"


def _code() -> str:
    try:
        return code_of(CARD)
    except OSError:
        pytest.skip("拿不到前端源码(只跑后端时正常)")


def _root_class() -> str:
    """卡片根元素那一串 className。"""
    code = _code()
    # [R522] 四档卡片统一成一颗芯片, 根元素的 className 不再拼 `cs.card`; 锚改成芯片根元素那一串
    m = re.search(r"className=\{`inline-flex h-7([^`]*)`\}", code)
    assert m, "芯片根元素的 className 形状变了 —— 这条守卫的锚要跟着改"
    return m.group(1)


def test_R398_窄屏铺满一列():
    cls = _root_class()
    assert re.search(r"(?<!:)\bw-full\b", cls), (
        "卡片在窄屏没有铺满宽度 —— 一行一张时每张宽度各不相同, 右边缘会是锯齿")


def test_R398_宽屏要还原成自适应():
    cls = _root_class()
    assert "sm:w-auto" in cls, (
        "窄屏铺满之后没有在 sm 以上还原 —— 宽屏会变成每张卡独占一行, "
        "把原来的平铺毁掉")


def test_R398_说明文字的限宽也要跟着放开():
    """描述那几行原来写死 `max-w-[120px]`/`[140px]` —— 那是给平铺态定的宽度,
    卡片铺满整列之后它会把说明提前截断, 右边空着一大片却显示省略号。"""
    code = _code()
    # **逐处**看, 不是全文件查一遍 —— 文件里别处有一个带 `sm:` 的同名类,
    # 全文件查就会让"某一处退回写死"照样绿(第一版就是这么漏的)。
    bad = []
    for m in re.finditer(r"(sm:)?max-w-\[\d+px\]", code):
        if m.group(1):
            continue                      # 已经是 sm: 前缀的那一半, 正常
        head = code[max(0, m.start() - 12):m.start()]
        if "max-w-none " not in head:      # 无前缀的那一处必须紧跟在 max-w-none 之后
            bad.append(code[max(0, m.start() - 24):m.end()].strip()[-40:])
    assert not bad, f"这些限宽没有在窄屏放开(应写成 max-w-none sm:max-w-[...]): {bad}"
