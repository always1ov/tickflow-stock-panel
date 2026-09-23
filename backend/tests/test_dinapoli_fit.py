"""[fork R412] 粗细档回测 —— 钉住它评的是「线画得准不准」, 而且没被线数蒙过去。

这个回测最容易发生的两种坏法, 屏幕上都看不出来:

  · **被线数蒙过去。** 细档画更多线, 蒙中的概率天然更高 —— 任何不除线数的
    排序都会必然推荐最细那一档, 而那不是调参, 是过拟合的标准形态。
  · **偷看未来。** 拿最后一根的 ATR 去量三年前那一段, 或者把"到目前为止的
    最低点"当成回踩已经走完 —— 两种都会让数字好看, 而且不报错。
"""
from __future__ import annotations

import polars as pl
import pytest

from app.indicators import dinapoli_fit as fit
from app.indicators.dinapoli import GRAINS


def _df(closes: list[float], atr: float | list[float] = 0.5) -> pl.DataFrame:
    n = len(closes)
    atrs = [atr] * n if isinstance(atr, (int, float)) else atr
    return pl.DataFrame({
        "high": [c + 0.2 for c in closes], "low": [c - 0.2 for c in closes],
        "close": closes, "atr_14": atrs,
    })


# 一段上攻 + 一次回踩 + 再一段上攻 + 再一次回踩 —— 两个可评估样本
TWO_WAVES = (
    [10.0] * 30
    + [9.6, 10.6, 11.6, 11.2, 12.2, 13.1, 12.6, 12.2, 13.1, 14.1, 15.0, 15.6]
    + [14.6, 13.8, 13.2, 12.9, 13.4]                      # 回踩一
    + [14.2, 15.1, 16.0, 16.4, 17.2, 18.0, 18.6, 19.2, 19.8]
    + [18.4, 17.2, 16.4, 15.9, 16.3, 16.8]                # 回踩二
)


# ── 回踩窗口 ────────────────────────────────────────────────
def test_R412_回踩窗口在价格站回聚焦点时结束():
    highs = [10, 11, 12, 11, 10, 9, 13, 14]
    lows = [9, 10, 11, 10, 9, 8, 12, 13]
    # 上攻结束在下标 2(focus=12), 之后 9 是最低, 到下标 6 高点 13 > 12 结束
    assert fit.pullback_low(highs, lows, 2, 12.0, None) == 8


def test_R412_下一段上攻开始也算窗口结束():
    highs = [10, 11, 12, 11, 10, 9, 10, 11]
    lows = [9, 10, 11, 10, 9, 8, 9, 10]
    # 下一段从 6 开始 → 只看 3..5, 最低 8
    assert fit.pullback_low(highs, lows, 2, 99.0, 6) == 8


def test_R412_窗口太短就不算数_否则回踩还没跌完():
    """**这条挡的是最要命的一种偷看**: 最后一段的回撤往往才走了一两根,
    拿"到目前为止的最低点"当答案, 算出来会系统性偏高。"""
    highs = [10, 11, 12, 11]
    lows = [9, 10, 11, 10]
    assert fit.pullback_low(highs, lows, 2, 99.0, None) is None


def test_R412_最后一段通常进不了样本():
    """数据在上攻途中或刚回踩一两根就结束 —— 那一段的答案还没出来。"""
    closes = [10.0] * 30 + [10.0 + i * 0.6 for i in range(1, 16)]
    fits = fit.backtest_grains(_df(closes))
    assert all(f.samples == 0 for f in fits), \
        f"没走完的那一段被算进样本了: {[f.to_dict() for f in fits]}"


# ── 指标本身 ────────────────────────────────────────────────
def test_R412_三档都能跑出样本():
    fits = fit.backtest_grains(_df(TWO_WAVES))
    assert {f.grain for f in fits} == set(GRAINS)
    assert any(f.samples > 0 for f in fits), "一个样本都没有, 后面的断言测不到东西"


def test_R412_命中率与线数都如实算():
    for f in fit.backtest_grains(_df(TWO_WAVES)):
        if not f.samples:
            continue
        assert 0.0 <= (f.hit_rate or 0) <= 1.0
        assert f.hits <= f.samples
        assert (f.avg_lines or 0) > 0
        # 每条线的贡献就是这两个数的商 —— 不许是另一个公式
        assert f.per_line == pytest.approx((f.hit_rate or 0) / (f.avg_lines or 1))


def test_R412_密集带命中率的分母是算得出带的段数():
    """没有密集带的段本来就没做出这个预测, 拿它当"没中"是把两件事混了。"""
    f = fit.GrainFit(grain="mid", k=3, samples=10, zones=4, zone_hits=2)
    assert f.zone_rate == pytest.approx(0.5)       # 2/4, 不是 2/10


def test_R412_空数据不抛异常_三档都在():
    fits = fit.backtest_grains(pl.DataFrame())
    assert len(fits) == len(GRAINS)
    assert all(f.samples == 0 and f.hit_rate is None for f in fits)


# ── 建议规则 ────────────────────────────────────────────────
def test_R412_样本不够就不给建议():
    fits = [fit.GrainFit(grain=g, k=k, samples=2, hits=2, total_lines=10)
            for g, k in GRAINS.items()]
    r = fit.advise(fits)
    assert r["grain"] is None
    assert "样本太少" in r["reason"]


def test_R412_命中率差不多时选线更少的那一档():
    """**这条就是防"线多蒙中"的那一下。**

    细档命中率高 6 个百分点, 但线多了一倍 —— 规则要选粗档。
    """
    fits = [
        fit.GrainFit(grain="coarse", k=5, samples=10, hits=7, total_lines=60),
        fit.GrainFit(grain="fine", k=2, samples=10, hits=8, total_lines=140),
    ]
    assert fit.advise(fits)["grain"] == "coarse"


def test_R412_命中率差得多时还是选准的那一档():
    """规则不是"永远选线最少的" —— 差距够大时准确度说了算。"""
    fits = [
        fit.GrainFit(grain="coarse", k=5, samples=10, hits=3, total_lines=60),
        fit.GrainFit(grain="fine", k=2, samples=10, hits=9, total_lines=140),
    ]
    assert fit.advise(fits)["grain"] == "fine"


def test_R412_建议里说清楚凭什么这么选():
    fits = [
        fit.GrainFit(grain="coarse", k=5, samples=10, hits=7, total_lines=60),
        fit.GrainFit(grain="fine", k=2, samples=10, hits=8, total_lines=140),
    ]
    reason = fit.advise(fits)["reason"]
    assert "百分点" in reason and "条" in reason, f"理由太空: {reason}"


def test_R412_建议里不出现买卖字样():
    """这一层仍然是「只有位置, 没有动作」—— 它建议的是画多细, 不是做不做。"""
    fits = [fit.GrainFit(grain=g, k=k, samples=10, hits=6, total_lines=60)
            for g, k in GRAINS.items()]
    for r in (fit.advise(fits), fit.advise([])):
        for w in ("买", "卖", "进场", "离场", "止盈", "止损", "建仓"):
            assert w not in r["reason"], f"「{w}」出现在建议里: {r['reason']}"


# ── 不用未来数据 ────────────────────────────────────────────
def test_R412_最后一根的ATR改不了早年那几段的结果():
    """拿今天的波动率去量三年前那一段, 等于把未来泄露回过去。

    做法: 让**最后一根**的 ATR 大得离谱, 两次结果必须一样。[R483] 容差改成按聚焦点的
    百分比之后, 这条从"容差取对了哪一根"变成"没有任何一个量从最后一根漏回去"。
    """
    n = len(TWO_WAVES)
    normal = fit.backtest_grains(_df(TWO_WAVES, 0.5))
    spiked = [0.5] * (n - 1) + [50.0]
    after = fit.backtest_grains(_df(TWO_WAVES, spiked))
    assert [f.to_dict() for f in normal] == [f.to_dict() for f in after], \
        "最后一根的 ATR 改了结果 —— 容差取的是最后一根, 那是未来数据"


# ── 端点接线 ────────────────────────────────────────────────
def test_R412_端点通_且结果里一个收益字段都没有(monkeypatch):
    """**这条钉的是这个回测的性质, 不是它的接线。**

    要算收益就得先编一条买卖规则(在哪条回踩位买、在哪卖), 而这一整组东西的
    口径从 R405 起就是「只有位置, 没有动作」。**只要结果里冒出一个收益字段,
    就说明有人从后门把判定层接回来了** —— 而那在屏幕上只会表现为"多了一列数"。
    """
    from types import SimpleNamespace

    from fastapi.testclient import TestClient

    from app import config as app_config
    from app.main import app

    monkeypatch.setattr(app_config.settings, "auth_disabled", True)
    app.state.repo = SimpleNamespace(
        get_daily_asset=lambda *_a, **_k: _df(TWO_WAVES),
        resolve_asset_type=lambda _s: "stock",
    )
    r = TestClient(app).post("/api/stock-analysis/fib2/grain-backtest",
                             json={"symbol": "000001.SZ", "use_ai": False})
    assert r.status_code == 200, r.text
    d = r.json()
    assert {x["grain"] for x in d["grid"]} == set(GRAINS)
    assert "rule_suggestion" in d and "reason" in d["rule_suggestion"]
    assert d["ai"] is None, "use_ai=False 还是调了 AI"

    banned = ("return", "profit", "pnl", "sharpe", "drawdown", "收益", "盈亏", "胜率")
    blob = str(d)
    for w in banned:
        assert w not in blob, f"回测结果里出现了「{w}」—— 这一组不该有收益这回事"


def test_R412_没有数据时如实报错不硬算(monkeypatch):
    from types import SimpleNamespace

    from fastapi.testclient import TestClient

    from app import config as app_config
    from app.main import app

    monkeypatch.setattr(app_config.settings, "auth_disabled", True)
    app.state.repo = SimpleNamespace(
        get_daily_asset=lambda *_a, **_k: pl.DataFrame(),
        resolve_asset_type=lambda _s: "stock",
    )
    d = TestClient(app).post("/api/stock-analysis/fib2/grain-backtest",
                             json={"symbol": "000001.SZ", "use_ai": False}).json()
    assert d.get("error"), f"空数据没报错: {d}"


# ── 评的就是图上那一组 ──────────────────────────────────────
def test_R483_评的就是图上那一组线_用对照图那一段验():
    """[R483] 原来这里另有一套切段和挑锚(R473 之前的画法), 画法改了七轮它一轮没跟 ——
    粗细档建议评的一直是图上已经不画的线。拿中际旭创对照图那一段接一次回踩 + 再创新高,
    974.99 那一段被评估的必须正好是对照图上那五条, 而回踩停在 925 要算「中」、也在密集带里。"""
    from tests.test_fib2_reference import F3_ON_CHART, F5_ON_CHART, FOCUS, _chart_df

    ref = _chart_df()
    tail = [(925.0, 931.0, 925.0, 928.0), (929.0, 950.0, 928.0, 948.0),
            (948.0, 990.0, 945.0, 985.0), (985.0, 1000.0, 980.0, 995.0)]
    df = pl.concat([ref, pl.DataFrame({
        "open": [r[0] for r in tail], "high": [r[1] for r in tail],
        "low": [r[2] for r in tail], "close": [r[3] for r in tail],
        "atr_14": [45.0] * len(tail)})])
    for grain, k in GRAINS.items():
        case = next((c for c in fit._cases(df, k) if c.focus == FOCUS), None)
        assert case is not None, f"[{grain}] 974.99 那一段没进样本"
        got = sorted(round(x["value"], 2) for x in case.levels)
        assert got == sorted(F3_ON_CHART | F5_ON_CHART), f"[{grain}] 评的线是 {got}"
        assert case.low == 918.5, f"[{grain}] 回踩低点 {case.low}"
    f = fit.evaluate_grain(df, "mid", GRAINS["mid"])
    assert f.hits >= 1 and f.zone_hits >= 1, f.to_dict()
