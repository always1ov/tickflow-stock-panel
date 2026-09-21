"""[R391] 台账不记的时候, 得有人说 —— 静默跳过的第二种形状。

## 这一条补的是 R274 那组守卫的盲区

`test_today_health.py::test_R274_每一处跳过都要登记` 扫的是 `except` —— 「算挂了
却没人知道」那一种。但 `_build_overview` 里还有另一种静默跳过, 它**根本不抛异常**:

    if as_of and not any(t.get("intraday") for t in trends.values()):
        score_ledger.record_day(...)
    # ← 条件不成立时, 一声不吭

不记本身是对的(盘中的现价不是收盘价, 拿它当收益起点会算出一份假收益), 错的是
**不说**。用户开着实时行情看盘, 台账就天天不记, 而界面上没有任何一个地方提过这件
事; 攒了几周之后点开「体检」, 只看到一句「台账还是空的」—— 那句话解释不了为什么,
也给不出出路。这正是用户报的「体检按钮的功能失效了」。

所以这条钉的是**性质而不是措辞**: 记账那段 try 里, if 链的**每一条终端分支**都必须
要么真的记一笔, 要么把这次不记登记进自检。少一条 else 也算漏 —— 隐式的那条路
恰恰是最容易忘的那条。
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from tests.frontend_source import code_of

TODAY_PY = Path(__file__).resolve().parents[1] / "app" / "api" / "today.py"
DIALOG = "components/ScoreLedgerDialog.tsx"


def _ledger_try() -> ast.Try:
    """`_build_overview` 里落台账那一段 try。"""
    tree = ast.parse(TODAY_PY.read_text(encoding="utf-8"))
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "_build_overview")
    hits = [n for n in ast.walk(fn)
            if isinstance(n, ast.Try) and "record_day" in ast.dump(n)]
    assert len(hits) == 1, f"落台账那段 try 没定位到(找到 {len(hits)} 段)"
    return hits[0]


def _called(nodes: list[ast.stmt]) -> set[str]:
    """这一段语句里调到的函数名(裸名与属性名都算)。"""
    out: set[str] = set()
    for n in nodes:
        for sub in ast.walk(n):
            if isinstance(sub, ast.Call):
                f = sub.func
                if isinstance(f, ast.Name):
                    out.add(f.id)
                elif isinstance(f, ast.Attribute):
                    out.add(f.attr)
    return out


def _terminal_branches(node: ast.If) -> list[tuple[str, ast.expr | None, list[ast.stmt]]]:
    """if/elif/else 链摊平成 (标签, 判据, 语句)。

    **没有 else 时补一条空分支** —— 那条隐式的路才是真正会被忘掉的。
    """
    out: list[tuple[str, ast.expr | None, list[ast.stmt]]] = [("if", node.test, node.body)]
    orelse = node.orelse
    if not orelse:
        out.append(("else(缺)", None, []))
    elif len(orelse) == 1 and isinstance(orelse[0], ast.If):
        out.extend(_terminal_branches(orelse[0]))
    else:
        out.append(("else", None, orelse))
    return out


# ================================================================
# 后端: 每一条分支要么记账, 要么上报
# ================================================================

def test_R391_记账那段没有一条不吭声的分支():
    node = _ledger_try()
    ifs = [n for n in node.body if isinstance(n, ast.If)]
    assert ifs, "记账那段里一个 if 都没有, 这条守卫的锚没了"
    silent: list[str] = []
    for top in ifs:
        for label, _cond, body in _terminal_branches(top):
            if not ({"record_day", "skip"} & _called(body)):
                silent.append(f"{label} 分支: 既没记账也没 _h.skip")
    assert not silent, (
        "这些分支走过去什么都不会发生 —— 台账没记, 界面上也没人说:\n  "
        + "\n  ".join(silent))


def test_R391_盘中那条路要上报而不是悄悄跳过():
    """具体钉住「实时价参与判定」那一支 —— 它是用户真踩到的那条。

    不按措辞找, 按**数据流**找: 先看哪个名字是从 `intraday` 算出来的, 再看哪条
    分支拿它当判据。这样改文案不会误伤, 而把那条分支改成什么都不做会当场红。
    """
    node = _ledger_try()
    from_intraday = {
        t.id
        for st in node.body if isinstance(st, ast.Assign)
        for t in st.targets if isinstance(t, ast.Name)
        if "intraday" in ast.unparse(st.value)
    }
    assert from_intraday, "没有任何名字是从 intraday 算出来的, 盘中判据不在这段里了"
    checked = [
        body
        for top in node.body if isinstance(top, ast.If)
        for _, cond, body in _terminal_branches(top)
        if cond is not None and from_intraday & {
            n.id for n in ast.walk(cond) if isinstance(n, ast.Name)}
    ]
    assert checked, f"没有分支拿 {from_intraday} 当判据 —— 盘中那条路不见了"
    assert all("skip" in _called(b) for b in checked), (
        "盘中不记的那一支没有把这次跳过登记进自检 —— "
        "用户只会看到台账一直是空的, 而没有任何地方说过为什么")


def test_R391_记账的返回值不许丢():
    """`record_day` 自己吞异常, 失败时只返回 `{"ok": False}` —— 不看返回值的话,
    写失败和写成功在界面上长得一模一样, 又是一次静默跳过, 只是换了个位置。"""
    node = _ledger_try()
    bound = {
        t.id
        for _, _, body in [b for top in node.body if isinstance(top, ast.If)
                           for b in _terminal_branches(top)]
        for st in body if isinstance(st, ast.Assign)
        for t in st.targets if isinstance(t, ast.Name)
        if "record_day" in ast.unparse(st.value)
    }
    assert bound, "记账的返回值没接住 —— 写失败了也没人知道"
    checked = [
        sub for sub in ast.walk(node)
        if isinstance(sub, ast.If)
        and bound & {n.id for n in ast.walk(sub.test) if isinstance(n, ast.Name)}
        and "skip" in _called(sub.body)
    ]
    assert checked, f"接住了 {bound} 却没拿它判过 —— 写失败仍然是静默的"


def test_R391_自检登记表里有台账这一项():
    """上报要有落点 —— key 没登记的话, 报出来的是个英文 key, 界面上看不懂。"""
    from app.api.today import _Health
    assert "score_ledger" in _Health.SITES


# ================================================================
# 前端: 空态要说得出「为什么空」
# ================================================================

def _dialog_code() -> str:
    try:
        return code_of(DIALOG)
    except OSError:
        pytest.skip("拿不到前端源码(只跑后端时正常)")


def test_R391_空态不许再指向已经删掉的那一页():
    """原文写的是「打开**今日总览**会自动记一天」—— 那一页在 R340/R343 拆掉了,
    照着做是做不到的。**剥注释之后再扫** —— 上面那段解释里必然要写出旧说法。"""
    assert "今日总览" not in _dialog_code(), (
        "体检弹窗里还在让用户去开「今日总览」, 而那一页已经没有了")


def test_R391_空态要说清盘中不记这件事():
    code = _dialog_code()
    assert "盘中" in code and "收盘" in code, "空态没提口径, 用户不知道该怎么让它开始记"


def test_R391_全是老口径时不许只说一句台账还是空的():
    """`legacy_days` 原来只渲染在 `recorded_days > 0` 那一支里 —— 而「攒的全是
    换口径之前的」恰恰会让 `recorded_days` 是 0, 于是唯一能解释这件事的那句话
    **正好在最需要它的时候不可达**。"""
    code = _dialog_code()
    empty = code.split("recorded_days === 0", 1)
    assert len(empty) == 2, "空态那一支的锚没了"
    # 空态分支到下一个顶层分支之间
    seg = empty[1].split("recorded_days > 0", 1)[0]
    assert "legacy_days" in seg, (
        "空态里读不到 legacy_days —— 攒的全是老口径时, 用户只会看到「台账还是空的」")
