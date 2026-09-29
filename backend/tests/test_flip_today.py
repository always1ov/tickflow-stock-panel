"""[R329] 今日信号 —— **只有真转折才能出手**。

用户: 「我只有一个要求, 你怎么设计补充都可以但一定要根据转折才能出手」。

这组守卫里最要紧的是 `test_R329_只有已转折那一档能出手`: 它遍历所有非 flipped
的分支, 断言 `act` 恒为 None。提示语会被改, 这条结构不会被顺手改掉。

[R564] 转折模拟盘并进虚拟账户(跟六态转折)后, 这里只留 `evaluate()` 纯判定这一层的守卫;
钉模拟盘页面(FlipPaper.tsx)与回放接口的那些随页面一起退役, 虚拟账户那一块的守卫在
test_flip_follow_run.py / test_paper_flip_ui_r562.py。
"""
from __future__ import annotations

import pytest

from app.services import flip_today as ft


def _steps(states: list[str], *, flip_down=None, flip_up=None) -> list[dict]:
    """最后一根带触发价; flipped 按前后 state 自己算。"""
    out = []
    prev = None
    for st in states:
        out.append({"state": st, "prev": prev, "flipped": prev != st})
        prev = st
    out[-1]["flip_down"] = flip_down
    out[-1]["flip_up"] = flip_up
    return out


# ── 底线: 只有已转折那一档能出手 ────────────────────────────────────────


def test_R329_只有已转折那一档能出手():
    """**用户唯一的要求。** 穷举所有非 flipped 的产出, act 必须恒为 None。"""
    cases = [
        # 盘中越线(多头跌破 / 空头站上)
        (_steps(["UT", "UT"], flip_down=9.5), True, 10.0, 9.4),
        (_steps(["DT", "DT"], flip_up=10.5), False, 10.0, 10.6),
        # 接近但没到
        (_steps(["UT", "UT"], flip_down=9.8), True, 10.0, 9.9),
        (_steps(["DT", "DT"], flip_up=10.2), False, 10.0, 10.1),
        # 接近, 实时没开
        (_steps(["UT", "UT"], flip_down=9.8), True, 9.9, None),
    ]
    seen = set()
    for steps, held, last, live in cases:
        r = ft.evaluate(steps, held=held, last_close=last, live_close=live)
        assert r is not None, "这几组该有产出, 不然下面的断言是空的"
        assert r["stage"] != ft.STAGE_FLIPPED
        assert r["act"] is None, f"{r['stage']} 这一档不许出手 —— 只有真转折才能动手"
        seen.add(r["stage"])
    assert seen == {ft.STAGE_CROSSING, ft.STAGE_WATCH}, "两档都要覆盖到"


def test_R329_转折了才给动作():
    # 空仓 + 转多 → 买
    r = ft.evaluate(_steps(["DT", "UT"]), held=False, last_close=10.0)
    assert r["stage"] == ft.STAGE_FLIPPED and r["act"] == ft.ACT_BUY
    # 持有 + 转空 → 卖
    r = ft.evaluate(_steps(["UT", "DT"]), held=True, last_close=10.0)
    assert r["stage"] == ft.STAGE_FLIPPED and r["act"] == ft.ACT_SELL


def test_R329_转了但手上已经对上了就不重复动手():
    # 已持有 + 转多 → 不用再买
    r = ft.evaluate(_steps(["NR", "UT"]), held=True, last_close=10.0)
    assert r["stage"] == ft.STAGE_FLIPPED and r["act"] is None
    # 空仓 + 转空 → 本来就没拿, 没得卖
    r = ft.evaluate(_steps(["NR", "DT"]), held=False, last_close=10.0)
    assert r["stage"] == ft.STAGE_FLIPPED and r["act"] is None


@pytest.mark.parametrize("state", ["UT", "NR", "SR"])
def test_R329_三个多头态转入都算买(state):
    r = ft.evaluate(_steps(["DT", state]), held=False, last_close=10.0)
    assert r["act"] == ft.ACT_BUY


@pytest.mark.parametrize("state", ["DT", "NREA", "SREA"])
def test_R329_三个空头态转入都算卖(state):
    r = ft.evaluate(_steps(["UT", state]), held=True, last_close=10.0)
    assert r["act"] == ft.ACT_SELL


# ── 盯哪条线 ────────────────────────────────────────────────────────────


def test_R329_多头盯跌破_空头盯站上_方向不许拿反():
    r = ft.evaluate(_steps(["UT", "UT"], flip_down=9.8, flip_up=99.0),
                    held=True, last_close=10.0)
    assert r["flip_price"] == 9.8, "多头侧盯的是「跌破就转空」那条"
    r = ft.evaluate(_steps(["DT", "DT"], flip_down=1.0, flip_up=10.2),
                    held=False, last_close=10.0)
    assert r["flip_price"] == 10.2, "空头侧盯的是「站上就转多」那条"


def test_R329_没有触发价就不报_不自己算一条():
    assert ft.evaluate(_steps(["UT", "UT"]), held=True, last_close=10.0) is None


def test_R329_离得远的不进名单():
    """离 20% 的票天天在名单里, 等于没有名单。

    [R338] 这条闸**只管没拿着的票** —— 手上拿着的那一侧另有守卫
    (`test_R338_手上的票离触发价再远也要报`), 两条各管各的, 不重叠。
    """
    r = ft.evaluate(_steps(["UT", "UT"], flip_down=8.0), held=False, last_close=10.0)
    assert r is None
    near = ft.evaluate(_steps(["UT", "UT"], flip_down=9.8), held=False, last_close=10.0)
    assert near is not None and near["stage"] == ft.STAGE_WATCH


# ── 实时 ────────────────────────────────────────────────────────────────


def test_R329_实时没开时不出现盘中越线这一档():
    """收盘价越了线却没 flipped —— 状态机自有道理, 不替它下结论。"""
    r = ft.evaluate(_steps(["UT", "UT"], flip_down=9.5), held=True, last_close=9.4)
    assert r is None, "已落盘的价越线但没转折, 这种不报"


def test_R329_实时开着才标_live():
    live = ft.evaluate(_steps(["UT", "UT"], flip_down=9.5), held=True,
                       last_close=10.0, live_close=9.4)
    assert live["stage"] == ft.STAGE_CROSSING and live["live"] is True
    off = ft.evaluate(_steps(["UT", "UT"], flip_down=9.8), held=True, last_close=10.0)
    assert off["live"] is False, "实时没开就得标出来, 别让人以为是现价"


def test_R329_已转折那一档与实时无关():
    """① 是拿已落盘的日 K 算的 —— 实时开没开都是同一个结论。"""
    a = ft.evaluate(_steps(["DT", "UT"]), held=False, last_close=10.0)
    b = ft.evaluate(_steps(["DT", "UT"]), held=False, last_close=10.0, live_close=7.0)
    assert a["act"] == b["act"] == ft.ACT_BUY
    assert a["live"] is False and b["live"] is False


def test_R329_距离按现价算_实时开着时用的是现价():
    r = ft.evaluate(_steps(["UT", "UT"], flip_down=9.8), held=True,
                    last_close=20.0, live_close=10.0)
    assert r["ref_price"] == 10.0, "实时开着就该拿现价比, 不是昨收"
    assert r["gap_pct"] == pytest.approx((9.8 - 10.0) / 10.0)


def test_R329_多空判据来自_flip_trades_不自己造():
    from tests.py_source import code_of
    code = code_of(ft)
    assert "trend_days(steps)" in code
    assert "BULLISH" not in code, "多空归属不许在这里重写一遍"


def test_R329_没数据时返回_None_不编一个():
    assert ft.evaluate([], held=False, last_close=10.0) is None
    assert ft.evaluate(_steps(["UT", "UT"], flip_down=9.8), held=True, last_close=None) is None


# ── 接线与界面 ──────────────────────────────────────────────────────────


def test_R338_手上的票离触发价再远也要报():
    """**这条直接钉用户报的症状。** 拿着的票, 离场线不该因为"还远"就整行消失。"""
    far = _steps(["UT", "UT"], flip_down=5.0)   # 现价 10 → 离清仓线 50%, 远得很
    r = ft.evaluate(far, held=True, last_close=10.0)
    assert r is not None, "手上拿着的票, 卖出线任何时候都要看得见"
    assert r["stage"] == ft.STAGE_WATCH
    assert r["flip_price"] == 5.0, "报的必须是卖出那条线"


def test_R338_没拿着的票那道闸还在():
    """闸是为了"不相干的票别刷屏" —— 不许借这次改动把它顺手拆了。"""
    far = _steps(["DT", "DT"], flip_up=20.0)    # 现价 10 → 离买入线 100%
    assert ft.evaluate(far, held=False, last_close=10.0) is None, \
        "没拿着又离得远的票进名单, 等于没有名单"


def test_R338_手上这段仍然不许出手():
    """**铁律不因为多了一段版面而松动。** 没转折就没有动作, 拿着也一样。"""
    for gap_price in (5.0, 9.9):               # 远的、近的都来一遍
        r = ft.evaluate(_steps(["UT", "UT"], flip_down=gap_price),
                        held=True, last_close=10.0)
        assert r is not None and r["act"] is None, "没转折就不许出手"


def test_R338_每行都带held_否则前端分不开():
    """前端只能按返回值分段。不带 `held`, 「持仓」和「盘中越线」就是一堆。
    [R564] 取数层从模拟盘的 `flip_portfolio_run._today_signals` 换成虚拟账户的
    `flip_follow_run.panel`, 这条立论照旧: 判定用的与报出去的必须是同一个值。"""
    from tests.py_source import body_of
    from app.services import flip_follow_run as run_mod
    code = body_of(run_mod.panel).replace('"', "'")
    assert "'held': is_held" in code, "每行必须带上 held"
    assert "held=is_held" in code, "判定用的和报出去的必须是同一个值, 不许各算一遍"
