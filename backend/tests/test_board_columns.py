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


def test_R250_表头只印列名不印排序目标():
    """用户: 「别搞贵不贵怎么办, 我就只想显示结论两个字」→(问到走势列时)「要」。

    原来三列在排序时会在表头缀出当前排序目标:

        结论 贵不贵     走势 六态 / 间距 / 短中长     现价/涨跌 价 / 涨跌

    那是**把内部分层摆到表头上**, 而这几列对外就叫「结论」「走势」。
    排序行为照旧(点击仍在各目标之间轮换), 说明留在悬停里, 只是不印在表头。

    **这条得直接盯源码**: `_headers()` 会把 JSX 表达式整个剥掉, 那些缀字在
    它眼里是隐形的 —— 靠它守不住。
    """
    import re

    src = _src()
    th_block = src[src.index("<thead"):src.index("</thead>")]
    # 表头里**渲染出去**的部分: 去掉注释、去掉 title 属性(那里面本来就要解释轮换)
    render = re.sub(r"\{/\*.*?\*/\}", "", th_block, flags=re.S)
    render = re.sub(r'title=(?:"[^"]*"|\{(?:[^{}]|\{[^{}]*\})*\})', "", render, flags=re.S)

    for bad in ("贵不贵", "怎么办", "六态", "间距", "'价'", "涨跌'"):
        assert bad not in render, (
            f"表头又缀上排序目标「{bad}」了 —— 用户只要列名本身"
        )
    # 正面: 三个列名都还在
    for name in ("结论", "走势", "现价/涨跌"):
        assert name in render, f"表头把「{name}」弄丢了"


# ===== [R251] 每列的排序 =====
#
# 用户: 「检查每列的排序, 我感觉有点不对劲」。查出三个:
#
#   ① 多目标那三列传的是**当前排序键本身**给箭头函数 —— 判等恒真, 箭头永远亮。
#      按「成本」排时四个箭头一起亮, 看不出按哪列排。
#      (R250 把表头缀字去掉之后这个 bug 才裸出来 —— 缀字之前一直在替它遮丑)
#   ② 「怎么办」首次点击是降序, 而 order 越小越急 —— **把「没事」顶到最前面**,
#      与表头 title 写的「按纪律走 > 今天就得动 > …」正好相反。
#   ③ 「AI 信号」同理 —— 把「观望」顶到最前面。
#
# ②③ 是**看不出来的错**: 表面上排了序, 排出来的却是最不该先看的那些。


def _board_body() -> str:
    """去掉注释的源码 —— 注释里复述 bug 是允许的, 不能算数。"""
    out, in_block = [], False
    for ln in _src().splitlines():
        t = ln.strip()
        if in_block:
            if "*/" in t:
                in_block = False
            continue
        if t.startswith("/*"):
            in_block = "*/" not in t
            continue
        if t.startswith("//"):
            continue
        out.append(ln)
    return "\n".join(out)


def test_R251_箭头不许拿当前排序键跟自己比():
    """`caret(sort.key)` —— 判等恒真, 那个箭头就永远亮着。

    这一条盯的是**写法本身**: 传进去的必须是这一列自己的排序目标(字面量),
    不能是当前排序键。
    """
    body = _board_body()
    assert "caret(sort.key)" not in body, (
        "箭头又拿当前排序键跟自己比了 —— 判等恒真, 那一列的箭头会永远亮着"
    )


def test_R251_多目标的列把自己的目标全列给箭头():
    """漏列一个, 按那个目标排时这一列的箭头就不亮 —— 反过来的毛病。"""
    body = _board_body()
    for cols in ("'close', 'changePct'",
                 "'trend', 'spread', 'ks', 'km', 'kl'",
                 "'verdict', 'play'"):
        assert f"caret({cols})" in body, f"表头少给箭头列出目标: caret({cols})"


def test_R251_越小越要紧的那几个必须升序打头():
    """`order` / `SIGNAL_RANK` 都是**越小越要紧**。首次点击给降序, 就是把最不该
    先看的顶到最前面 —— 而且看不出来, 因为它确实排序了。"""
    body = _board_body()
    block = body[body.index("FIRST_DIR"):]
    block = block[:block.index("}")]
    for key, why in (("urgency", "该动了: order 越小越急"),
                     ("play", "怎么办: 按纪律走=0, 没事=5"),
                     ("signal", "AI 信号: 买入=0, 观望=3"),
                     ("spread", "间距: 刚走出来的在前"),
                     ("ks", "通道位置: 最便宜的在前")):
        assert f"{key}: 'asc'" in block, f"{key} 的首次方向不是升序 —— {why}"
    for key, why in (("trend", "六态: 值取了负, 降序才是多头在前"),
                     ("verdict", "贵不贵: rank 越大越偏卖"),
                     ("report", "AI 报告: 最新在前")):
        assert f"{key}: 'desc'" in block, f"{key} 的首次方向不是降序 —— {why}"


def test_R251_每个排序键都定了首次方向():
    """漏一个就会 undefined —— 那一列点下去方向是随机的(实际是 undefined,
    比较时当 desc 处理), 而且悄无声息。"""
    body = _board_body()
    keys = re.findall(r"'([a-zA-Z]+)'", body[body.index("type SortKey"):body.index("\n", body.index("type SortKey") + 200)])
    block = body[body.index("FIRST_DIR"):]
    block = block[:block.index("\n  }")]
    for k in keys:
        assert re.search(rf"\b{k}: '(asc|desc)'", block), f"排序键「{k}」没定首次方向"


def test_R251_表头说的和实际做的一致():
    """[R214 的教训] 判定写对了、接线接错了, 而测试恰好只测了判定。

    「怎么办」的表头 title 写着「按急迫程度排: 按纪律走 > …」—— 那句话只有在
    升序时才成立。说明与行为不一致时, **说明会赢**(用户信它), 于是排出来的表
    与预期相反而没人发现。
    """
    src = _src()
    th = src[src.index("<thead"):src.index("</thead>")]
    assert "按急迫程度排" in th, "「怎么办」的排序说明没了"
    body = _board_body()
    block = body[body.index("FIRST_DIR"):]
    assert "play: 'asc'" in block[:block.index("}")], (
        "表头说「按纪律走排最前」, 而首次点击是降序 —— 说明与行为相反"
    )


def test_R252_粘性表头必须有_z_index():
    """用户: 「怎么背后的东西也显示出来了, 层级是不是不对」。

    `position: sticky` 不带 z-index 时, 行里任何**自己造层叠上下文**的东西
    (`opacity < 1`、`transform`、`filter`…)都会画到表头上面 —— 决策台那个
    `opacity-70` 的天数徽标正是这样穿透过去的。

    这条盯**全仓所有粘性表头**, 不只决策台 —— 同一个毛病当时有三处。
    """
    import pathlib

    root = _BOARD.parents[2]            # frontend/src
    if not root.exists():
        pytest.skip("拿不到前端源码(只跑后端时正常)")
    bad = []
    for f in root.rglob("*.tsx"):
        in_block = False
        for i, ln in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            # 注释里复述这个 bug 是允许的 —— 不去注释的话守卫会被自己的说明文字
            # 骗到(第一版就栽了一次)
            t = ln.strip()
            if in_block:
                in_block = "*/" not in t
                continue
            if t.startswith(("//", "*")):
                continue
            if t.startswith(("/*", "{/*")):
                in_block = not any(x in t for x in ("*/", "*/}"))
                continue
            if "sticky top-0" in ln and not re.search(r"\bz-(\[|\d)", ln):
                bad.append(f"{f.relative_to(root)}:{i}")
    assert not bad, (
        "这些粘性表头没有 z-index, 行内容会穿透上来:\n  " + "\n  ".join(bad)
    )


def test_R252_决策台表头背景是实心的():
    """半透明表头底下是**正在划走的行** —— 让它透出来没有任何好处, 只会把
    表头读成花的。"""
    src = _src()
    head = src[src.index("<thead"):src.index(">", src.index("<thead")) + 1]
    assert "bg-surface/" not in head, f"表头背景又半透明了: {head}"
    assert "bg-surface" in head, "表头没有背景色 —— 行会直接透上来"
