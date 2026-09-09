"""[R249] 决策台的列顺序。

用户: 「我有点乱, 是否有好办法整理好顺序调整显示和列」。

重排之后一行从左到右是: **认票 → 凭什么 → 我的账 → 别人的意见**

    标的 · 现价/涨跌  |  走势 · 结论  |  仓位 · 成本 · 浮盈  |  AI 分析 · AI 信号

原来账目三列横在「现价」与「走势」之间 —— 扫表时要连着读的两列判断被切开了。

`BOARD_COLS` 的注释从 R194 起就写着「**顺序必须与 thead 里的 <th> 一一对应**」,
可**没有任何东西在守它**: 对不上时列宽会整体错位一格, 而且看不出是哪一列的问题。
这一组就是那个守卫。
"""
from __future__ import annotations

import pathlib
import re

import pytest

_BOARD = (pathlib.Path(__file__).resolve().parents[2] / "frontend" / "src"
          / "components" / "stock-analysis" / "WatchlistDecisionBoard.tsx")


def _src() -> str:
    if not _BOARD.exists():
        pytest.skip("拿不到前端源码(只跑后端时正常)")
    return _BOARD.read_text(encoding="utf-8")


def _cols(src: str) -> list[str]:
    """BOARD_COLS 里的 label, 按声明顺序。"""
    block = src[src.index("const BOARD_COLS = ["):]
    block = block[:block.index("] as const")]
    return re.findall(r"label:\s*'([^']+)'", block)


def _headers(src: str) -> list[str]:
    """thead 里每个 <th> 的可见文字。"""
    head = src[src.index("<thead"):src.index("</thead>")]
    out = []
    for th in re.findall(r"<th\b.*?</th>", head, re.S):
        txt = th
        # 顺序要紧: 先剥 JSX 表达式(排序标记、caret), 再剥**属性值**, 最后剥标签。
        # 属性必须先剥 —— title="… > … < …" 里带着尖括号, 直接剥标签会被它骗到
        # (第一版就栽在这里)。
        for _ in range(6):                       # 表达式会嵌套, 由内向外剥几遍
            txt = re.sub(r"\{[^{}]*\}", "", txt)
        txt = re.sub(r'=\s*"[^"]*"', "", txt)     # 属性值
        txt = re.sub(r"=\s*'[^']*'", "", txt)
        txt = re.sub(r"<[^<>]*>", "", txt)        # 标签
        txt = txt.replace("&nbsp;", " ").strip()
        if txt:
            out.append(txt)
    return out


def test_列的顺序是_认票_凭什么_我的账_别人的意见():
    """这条把**顺序本身**钉住 —— 它是这次重排的全部内容, 不写下来下次就会漂回去。"""
    assert _cols(_src()) == [
        "标的", "现价/涨跌",          # 认票
        "走势", "结论",               # 凭什么(判断必须连着, 不许被账目切开)
        "仓位", "成本", "浮盈",       # 我的账
        "AI 分析", "AI 信号",         # 别人的意见
    ]


def test_账目三列必须排在判断之后():
    """R249 之前它们在「现价」与「走势」之间。这条独立于上面那条写 ——
    就算以后列增减, **判断不许被账目切开**这条纪律也得留着。"""
    cols = _cols(_src())
    judge = max(cols.index("走势"), cols.index("结论"))
    ledger = min(cols.index("仓位"), cols.index("成本"), cols.index("浮盈"))
    assert ledger > judge, (
        f"账目列插到判断列中间了 —— 扫表时「走势→结论」读不连贯。当前顺序: {cols}"
    )


def test_表头与_BOARD_COLS_一一对应():
    """`BOARD_COLS` 只管**列宽**(colgroup)与空表提示的 colSpan, 表头是另一处写的。
    两边对不上时整张表的列宽会错位一格, 而且看不出是哪一列的问题 ——
    这正是 R249 重排时最容易漏的一步(要同时改三处: BOARD_COLS / thead / tbody)。
    """
    src = _src()
    cols, heads = _cols(src), _headers(src)
    assert len(cols) == len(heads), (
        f"BOARD_COLS 有 {len(cols)} 列而 thead 有 {len(heads)} 个 <th>\n"
        f"  BOARD_COLS: {cols}\n  thead:      {heads}"
    )
    for i, (c, h) in enumerate(zip(cols, heads)):
        assert c == h, f"第 {i + 1} 列对不上: BOARD_COLS 是「{c}」, 表头是「{h}」"


def test_六态天数与结论天数同一个说法():
    """同一行里两个天数。六态写「3天」而结论写「已25天」时, 读的人得先判断
    这两个数是不是一回事 —— 是的: 都是尾部连续段、都按交易日、都是「到今天还在」。

    用户: 「必须要统一表达, 不能又两种多种表述」。
    """
    root = _BOARD.parent
    cells = (root / "decision-board" / "cells.tsx").read_text(encoding="utf-8")
    # 只看渲染出去的文本, 注释里复述历史说法是允许的
    body = "\n".join(ln for ln in cells.splitlines()
                     if not ln.lstrip().startswith(("//", "*", "/*")))
    assert "已{trend.duration}天" in body, "六态徽标没用统一说法「已N天」"
    assert "已{d.days}天" in body, "结论徽标没用统一说法「已N天」"

    bar = (root / "TrendStateBar.tsx")
    if bar.exists():
        bar_body = "\n".join(ln for ln in bar.read_text(encoding="utf-8").splitlines()
                             if not ln.lstrip().startswith(("//", "*", "/*")))
        assert "第 <span" not in bar_body, "复盘条又写回「第 N 天」了"


def test_R250_结论表头只有结论两个字():
    """用户: 「别搞贵不贵怎么办, 我就只想显示结论两个字」。

    原来点一下会在表头缀出「贵不贵」/「怎么办」标当前排序目标 —— 那是把
    **内部分层**摆到表头上, 而这一列对外就叫「结论」。排序照旧在两者之间
    轮换, 说明留在悬停里。

    `_headers()` 已经把 JSX 表达式剥掉了, 所以那个缀字在它眼里是隐形的 ——
    这条得直接盯源码。
    """
    src = _src()
    th = src[src.index("<thead"):src.index("</thead>")]
    conclusion = th[th.index("toggleSort(sort.key === 'verdict'"):]
    conclusion = conclusion[:conclusion.index("</th>")]
    body = conclusion[conclusion.index(">") + 1:]      # 跳过 <button …> 那一串属性
    for bad in ("贵不贵", "怎么办"):
        assert bad not in body.split("title=")[0] or "{/*" in body, "先粗筛"
    # 精确一点: 渲染区(去掉注释与 title 属性)里不许出现这两个词
    render = body
    render = __import__("re").sub(r"\{/\*.*?\*/\}", "", render, flags=16)   # re.S
    render = __import__("re").sub(r"title=\{[^}]*(?:\}[^}]*)*?\}", "", render, flags=16)
    assert "贵不贵" not in render and "怎么办" not in render, (
        f"表头又缀上排序目标了 —— 用户只要「结论」两个字。渲染区: {render.strip()[:200]}"
    )
