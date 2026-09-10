"""[R274] 今日总览自检 —— **每一次静默跳过都要有人知道**。

用户: 「有没有办法验证今日总览的所有显示有没有问题、是否在正常工作」。

## 问题不在"会不会崩", 在"崩了没人知道"

这一页的构建过程里有十几处 `try/except`, 每一处都是**只写一行日志然后继续**。
那个设计本身是对的(中观算不出来不该拖垮整页), 但它缺了另一半: 失败之后页面照常
渲染, 那个区块只是空的, 而看的人**根本分不出「今天真没有」和「算挂了」**。
日志在服务器上, 没人会去翻。

这一组里分量最重的是 `test_R274_每一处跳过都要登记`: 只要有人加了新的 `except`
却忘了 `_h.skip(...)`, 那一处就悄悄退回了"静默跳过" —— 而那正是这轮要根治的东西。
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path

import pytest

from app.api.today import _Health

TODAY_PY = Path(__file__).resolve().parents[1] / "app" / "api" / "today.py"


def _builder_src() -> str:
    """`_build_overview` 的函数体 —— 自检要覆盖的就是这一段。"""
    s = TODAY_PY.read_text(encoding="utf-8")
    a = s.index("def _build_overview(")
    b = s.index("\n@router.get(\"\")", a)
    return s[a:b]


# ================================================================
# 登记表不许漏 —— 这一条是其余全部结论的前提
# ================================================================

def test_R274_每一处跳过都要登记():
    """扫 `_build_overview` 里每一个 `except`, 后面必须跟着 `_h.skip(...)`。

    漏一处 = 那个区块又变回"挂了也没人知道"。而这种漏是**最容易发生**的:
    加一段新逻辑、顺手包个 try/except 防它拖垮整页 —— 完全合理, 但自检就此有个洞。
    """
    src = _builder_src()
    lines = src.splitlines()
    misses: list[str] = []
    for i, ln in enumerate(lines):
        if not ln.strip().startswith("except "):
            continue
        # 往后看几行(日志 + skip 通常挨着)
        window = "\n".join(lines[i + 1:i + 5])
        if "_h.skip(" not in window:
            misses.append(f"第 {i + 1} 行附近: {ln.strip()}")
    assert not misses, (
        "这些 except 没有登记进自检 —— 那一处的失败在界面上看不见:\n  "
        + "\n  ".join(misses))


def test_R274_登记的key都在名录里():
    """`_h.skip("xxx")` 里的 key 必须在 `SITES` 中有中文名和档次 ——
    否则界面上会冒出一个英文 key, 而人不知道那是哪一块。"""
    used = set(re.findall(r'_h\.skip\("([a-z_]+)"', _builder_src()))
    assert used, "一处都没登记?"
    unknown = sorted(used - set(_Health.SITES))
    assert not unknown, f"这些 key 没在 _Health.SITES 里登记: {unknown}"


def test_R274_名录里不许有没人用的key():
    """反向也要守: 删掉一段逻辑却留着名录项, 名录就开始说假话。"""
    used = set(re.findall(r'_h\.skip\("([a-z_]+)"', _builder_src()))
    stale = sorted(set(_Health.SITES) - used)
    assert not stale, f"这些 key 名录里有、代码里没人用: {stale}"


def test_R274_每一项都说清楚是整块缺还是少个标():
    """后果不一样: 整块没了界面上是空的(得醒目), 少个标主体还在(提一句就够)。
    分错档的话, 要么把小事报成大事、要么把大事说得像小事。"""
    for key, (cn, level) in _Health.SITES.items():
        assert cn and not cn.isascii(), f"{key} 没有给人看的中文名"
        assert level in ("block", "detail"), f"{key} 的档次是 {level}"


# ================================================================
# 收集器本身
# ================================================================

def test_R274_没跳过就是健康():
    rep = _Health().report("2026-09-10")
    assert rep["ok"] is True and rep["blocks"] == [] and rep["details"] == []


def test_R274_整块与少个标分开报():
    h = _Health()
    h.skip("meso", "boom")           # block
    h.skip("annotations", "boom")    # detail
    rep = h.report("2026-09-10")
    assert rep["ok"] is False
    assert [r["key"] for r in rep["blocks"]] == ["meso"]
    assert [r["key"] for r in rep["details"]] == ["annotations"]


def test_R274_同一处反复失败只记一条错但要计数():
    """逐只算 ATR 那种循环里, 一次网络抖动能刷出几百条一模一样的。"""
    h = _Health()
    for i in range(300):
        h.skip("atr_load", f"第 {i} 次")
    rep = h.report("2026-09-10")
    row = rep["details"][0]
    assert row["n"] == 300
    assert row["error"] == "第 0 次", "留第一条, 后面的只计数"


def test_R274_错误文本有上限():
    """堆栈之类的长文本会把响应撑大, 而报告只需要够定位。"""
    h = _Health()
    h.skip("meso", "x" * 5000)
    assert len(h.report("2026-09-10")["blocks"][0]["error"]) <= 200


def test_R274_报出数据陈了几天():
    """**另一类问题**: 什么都没报错, 但整页数字是几天前的 —— 收盘后管道没跑就是这样。
    它和"算挂了"一样会让人看着假数据做决定。"""
    old = (date.today() - timedelta(days=3)).isoformat()
    assert _Health().report(old)["stale_days"] == 3
    assert _Health().report(date.today().isoformat())["stale_days"] == 0


def test_R274_日期坏了不抛():
    for bad in (None, "", "不是日期", "2026-13-99"):
        rep = _Health().report(bad)
        assert rep["stale_days"] is None


def test_R274_未登记的key也不抛只是没中文名():
    """名录漏了不该让整页 500 —— 有守卫在测试里拦, 运行时降级就好。"""
    h = _Health()
    h.skip("从没见过的东西", "boom")
    assert h.report("2026-09-10")["details"][0]["cn"] == "从没见过的东西"


# ================================================================
# 接进响应
# ================================================================

def test_R274_health进了总览响应():
    src = TODAY_PY.read_text(encoding="utf-8")
    body = src[src.index("def _build_overview("):]
    body = body[:body.index("\n@router.get(\"\")")]
    assert '"health": _h.report(as_of)' in body


@pytest.mark.parametrize("key", sorted(_Health.SITES))
def test_R274_名录每一项都真的接在代码里(key):
    """逐项点名 —— 整表比对一次会把"少了哪一个"混成一条失败。"""
    assert f'_h.skip("{key}"' in _builder_src()


# ================================================================
# 界面上真的说出来了
# ================================================================

def _page() -> str:
    from tests.frontend_source import code_of
    return code_of("pages/Today.tsx")


def test_R274_页面顶部有自检条():
    page = _page()
    assert "function TodayHealthBar" in page
    assert "{!!d?.health && <TodayHealthBar h={d.health} />}" in page


def test_R274_一切正常时不渲染任何东西():
    """常驻一条「运行正常」的绿条, 看两天就成了背景板 —— 真出问题那天照样被忽略。"""
    page = _page()
    body = page[page.index("function TodayHealthBar"):]
    assert "if (h.ok && !stale) return null" in body


def test_R274_陈数据也要报():
    """**这一条最阴**: 什么都没报错, 页面看起来完全正常, 而你在用几天前的数字做决定。"""
    body = _page()
    body = body[body.index("function TodayHealthBar"):]
    assert "stale" in body and "h.stale_days" in body


def test_R274_整块与少个标在界面上分开说():
    """分不开的话, 要么把小事报成大事、要么把大事说得像小事。"""
    body = _page()
    body = body[body.index("function TodayHealthBar"):]
    assert "h.blocks.length" in body and "h.details.length" in body
    assert "不是「今天没有」" in body, "得说清空是因为算挂了, 不是今天真没有"
