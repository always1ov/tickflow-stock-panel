"""[R395] 手机上宽表格钉住第一列 —— 两条性质各自钉住。

用户选的方案: 「首列钉住 + 横向滑」。表格形式不变, 但「代码/名称」「标的」那一列
钉在左边缘不跑 —— 往右滑时始终知道自己在看哪一只。实测自选页 390px 宽只露得出
两列半(scrollWidth 990 / clientWidth 350), 滑过去之后满屏数字对不上是哪一行。

这里钉的两条都是**一旦破了就静默变难看**的那种:

1. **钉住的格子必须不透明。** 它要盖住从底下滑过去的内容; 背景透明的话两层字
   叠在一起, 比不钉更糟, 而且没有任何报错。
2. **只在窄屏钉。** 宽屏本来就放得下, 用户这一轮要的是"桌面零影响" ——
   每一处 `sticky left-0` 都必须配一个 `lg:static` 把它收回去。
"""
from __future__ import annotations

import re

import pytest

from tests.frontend_source import SRC, code_of

#: 这一轮开了钉住的表。**不扫全前端** —— 别处可能有正当的 `sticky left-0`
#: (比如始终钉住的侧栏), 那不归这条管。
#: [R526] 决策台那张从这里撤了: 用户「手机版现在不搞左右滑动, 能否像监控中心那样,
#: 每一行就能显示完整」—— 它在手机上改成一行一块, 不横滑也就无所谓钉。
PINNED = (
    "components/stock-table/StockDataTable.tsx",   # 自选 / 策略两张表的共用骨架
)

BOARD = "components/stock-analysis/WatchlistDecisionBoard.tsx"


def _code(rel: str) -> str:
    try:
        return code_of(rel)
    except OSError:
        pytest.skip("拿不到前端源码(只跑后端时正常)")


def _sticky_left_class_strings(code: str) -> list[str]:
    """每一处含 `sticky left-0` 的类名串(以引号/反引号为界取一段)。"""
    out = []
    for m in re.finditer(r"sticky left-0", code):
        # 往两边找最近的引号, 取出这一整串 class
        start = max(code.rfind(q, 0, m.start()) for q in ("'", '"', "`"))
        ends = [e for e in (code.find(q, m.end()) for q in ("'", '"', "`")) if e > 0]
        out.append(code[start + 1:min(ends)] if ends else code[start + 1:m.end()])
    return out


def test_R395_钉住的格子必须不透明():
    """透明的话, 从它底下滑过去的读数会直接透上来 —— 两层字叠在一起,
    比不钉更糟, 而且一声不响。"""
    bad = []
    for rel in PINNED:
        for cls in _sticky_left_class_strings(_code(rel)):
            # `lg:bg-transparent` 是宽屏那一侧的还原, 不算窄屏的底色
            narrow = " ".join(w for w in cls.split() if not w.startswith("lg:"))
            if not re.search(r"\bbg-[a-z]", narrow):
                bad.append(f"{rel}: {cls.strip()[:80]}")
    assert not bad, "这些钉住的格子没有不透明底色, 内容会透上来:\n  " + "\n  ".join(bad)


def test_R395_只在窄屏钉住_宽屏要还原():
    """用户这一轮要的是"桌面零影响"。每一处 `sticky left-0` 都得配一个
    `lg:static` —— 少一处, 宽屏上那一列就会无缘无故粘住。"""
    bad = []
    for rel in PINNED:
        for cls in _sticky_left_class_strings(_code(rel)):
            if "lg:static" not in cls:
                bad.append(f"{rel}: {cls.strip()[:80]}")
    assert not bad, "这些钉住没有在宽屏还原(缺 lg:static):\n  " + "\n  ".join(bad)


def test_R526_决策台手机上不横滑_不钉():
    """[R395] 原来钉的是「表头和表体要么都钉要么都不钉」。[R526] 决策台在手机上整张表
    折成一行一块(table / tbody 变块, thead 藏起, tr 变 flex-wrap), 没有横向滚动, 钉住也
    就一并撤了 —— 留一处 `sticky left-0` 都是残余。"""
    code = _code(BOARD)
    assert "sticky left-0" not in code, "决策台里还有钉住的格子 —— 手机上已经不横滑了"
    assert 'className="w-full text-xs max-sm:block"' in code, "表在手机上没变块"
    assert "'z-20 max-sm:hidden'" in code, "表头在手机上没藏起"
    assert '<tbody className="max-sm:block">' in code
    assert "max-sm:flex max-sm:flex-wrap max-sm:items-center" in code, "行在手机上没变 flex-wrap"


def test_R395_共用骨架把钉住做成开关而不是写死():
    """`StockDataTable` 是自选与策略两页共用的。钉住写死的话, 以后某张不该钉的
    表也会跟着钉上 —— 得是调用方说了算。"""
    code = _code("components/stock-table/StockDataTable.tsx")
    assert "pinFirstColumn" in code, "共用骨架里没有钉住开关了"
    assert re.search(r"pinFirstColumn\s*=\s*false", code), (
        "钉住的默认值不是关 —— 共用骨架不该替没表态的调用方做决定")


def test_R395_三张表都真的开了钉住():
    """反面: 别把开关加好了却没人打开。"""
    missing = [rel for rel in ("pages/Watchlist.tsx", "components/screener/ScreenerTable.tsx")
               if "pinFirstColumn" not in _code(rel)]
    assert not missing, f"这些表没开钉住: {missing}"


def test_R395_扩大可点范围不许改变视觉尺寸():
    """`.tap-target` 用 ::before 把**可点范围**撑到 28px, 视觉尺寸一个像素不变 ——
    这一页的密度是刻意的。谁要是把它改成直接加 padding/min-height, 那就是拿
    密度换手感, 得是一次有意的决定, 不该混在"顺手修一下"里。"""
    css = (SRC / "index.css").read_text(encoding="utf-8")
    m = re.search(r"\.tap-target::before\s*\{([^}]*)\}", css)
    assert m, "`.tap-target::before` 不在了 —— 扩大可点范围的机制换了"
    body = m.group(1)
    assert "position: absolute" in body, "不是绝对定位的话, 它会把按钮自己撑大"
    assert "max(100%, 28px)" in body, "撑到的尺寸变了 —— 变更要是有意的, 改这条断言"
