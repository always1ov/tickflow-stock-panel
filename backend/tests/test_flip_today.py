"""[R329] 今日信号 —— **只有真转折才能出手**。

用户: 「我只有一个要求, 你怎么设计补充都可以但一定要根据转折才能出手」。

这组守卫里最要紧的是 `test_R329_只有已转折那一档能出手`: 它遍历所有非 flipped
的分支, 断言 `act` 恒为 None。提示语会被改, 这条结构不会被顺手改掉。
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
    """离 20% 的票天天在名单里, 等于没有名单。"""
    r = ft.evaluate(_steps(["UT", "UT"], flip_down=8.0), held=True, last_close=10.0)
    assert r is None
    near = ft.evaluate(_steps(["UT", "UT"], flip_down=9.8), held=True, last_close=10.0)
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
def test_R329_取数层按急迫程度排序_能出手的在最前():
    from app.services import flip_portfolio_run as run_mod
    series = {
        "W": {"steps": _steps(["UT", "UT"], flip_down=9.9), "closes": [10.0, 10.0]},
        "F": {"steps": _steps(["DT", "UT"]), "closes": [10.0, 10.0]},
        "C": {"steps": _steps(["UT", "UT"], flip_down=9.5), "closes": [10.0, 10.0]},
    }

    class _R:
        def get_watchlist_live(self, asset):
            import polars as pl
            return pl.DataFrame({"symbol": ["C"], "date": ["2026-01-02"], "close": [9.4]})

    out = run_mod._today_signals(_R(), series, [], {s: s for s in series})
    assert [r["stage"] for r in out] == ["flipped", "crossing", "watch"], \
        "能出手的必须排最前 —— 版面顺序就是急迫程度"
    assert out[0]["act"] == "buy"
    assert out[1]["act"] is None and out[2]["act"] is None


def test_R329_持仓取自模拟盘自己的账_不是真钱持仓():
    from tests.py_source import body_of
    from app.services import flip_portfolio_run as run_mod
    code = body_of(run_mod._today_signals)
    # `ast.unparse` 会把引号规范化成单引号 —— 断言不该对引号敏感
    assert "held = {p['symbol'] for p in positions}" in code.replace('"', "'"), \
        "持仓必须来自传进来的模拟盘持仓, 不许另去读真实持仓"
    for bad in ("effective_positions", "positions.load", "watchlist_positions"):
        assert bad not in code, f"混进真钱持仓就成了另一个问题的答案: {bad}"


def test_R329_界面上后两档不渲染动作位():
    """**不是灰掉, 是根本不渲染** —— 灰掉的徽标仍在暗示这里本来有个动作。"""
    from tests.frontend_source import code_of
    code = code_of("pages/FlipPaper.tsx")
    blk = code[code.index("function SignalRow"):]
    blk = blk[:blk.index("\n}")]
    assert "const actionable = r.stage === 'flipped' && !!r.act" in blk, \
        "能不能动手只由这一条决定"
    assert "actionable ? (" in blk
    # 动作徽标(买入/清仓)必须在 actionable 那一支里
    head = blk[:blk.index(") : (")]
    assert "'买入'" in head and "'清仓'" in head
    tail = blk[blk.index(") : ("):]
    assert "买入" not in tail and "清仓" not in tail, "另一支里不许出现动作词"


def test_R329_今日信号排在页面最前():
    from tests.frontend_source import code_of
    code = code_of("pages/FlipPaper.tsx")
    body = code[code.index("{d && !d.reason && ("):]
    i_today = body.index("<TodaySignals")
    i_summary = body.index("<Summary")
    assert i_today < i_summary, "今天要动手的东西必须排在回测结论前面"
