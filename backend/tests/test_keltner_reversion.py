"""[fork 增强] R43 通道高抛低吸策略。

这是本仓第一个**出场由价格位置驱动**的策略 —— 此前所有内置策略的 exit 都是趋势
破位型, 所以"高抛低吸行不行"在回测里根本无法表达。下面守四件事:

  1. 出场真的是"到上轨"而不是"跌破了才走"(这条是整个策略存在的理由)
  2. 不在触轨当天买 —— 那是接飞刀
  3. 参数与决策台三列、图表同源
  4. 趋势闸默认拦住"下跌趋势里反复抄底"这个均值回归最亏钱的场景
"""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import polars as pl

from app.backtest.matrix import build_market_data_matrix
from app.indicators.keltner import BANDS
from app.strategy.builtin import keltner_reversion as kr


def _panel(closes: list[float], symbol: str = "T") -> pl.DataFrame:
    """单标的日线面板。高低价贴着收盘 —— 本策略只用 close, ATR 由振幅决定,
    这里给一个恒定的小振幅, 让通道宽度可预期。"""
    start = date(2024, 1, 1)
    n = len(closes)
    return pl.DataFrame({
        "symbol": [symbol] * n,
        "date": [start + timedelta(days=i) for i in range(n)],
        "open": closes,
        "high": [c + 1.0 for c in closes],
        "low": [c - 1.0 for c in closes],
        "close": closes,
        "volume": [1_000.0] * n,
    })


def _signals(closes: list[float], params: dict | None = None):
    market = build_market_data_matrix(_panel(closes))
    p = {"band": "s", "trend_filter": False, "exit_at_mid": False}
    p.update(params or {})
    sig = kr.MATRIX_STRATEGY.compute_signals(market, p)
    return market, sig


def _bands(market, n_atr=2.0, ma="ma20"):
    from app.backtest.matrix import matrix_feature

    m = matrix_feature(market, ma)
    atr = matrix_feature(market, "atr_14")
    return m + n_atr * atr, m - n_atr * atr


# ---------- 出场由价格位置驱动(本策略存在的理由) ----------

def test_exit_fires_when_price_reaches_the_upper_band():
    """此前所有内置策略的 exit 都是"跌破了才走"。这条守的是"涨到了就走"。"""
    closes = [100.0] * 60 + [100.0 + i * 3 for i in range(1, 25)]
    market, sig = _signals(closes)
    upper, _ = _bands(market)
    reached = np.flatnonzero(market.close[:, 0] >= upper[:, 0])
    fired = np.flatnonzero(sig.exit[:, 0])
    assert fired.size > 0, "涨到上轨必须出场, 否则就还是趋势破位那一套"
    assert set(fired.tolist()) <= set(reached.tolist())
    assert fired.min() == reached.min(), "第一次触到上轨就该走, 不该等更高"


def test_exit_does_not_fire_merely_because_price_fell():
    """下跌本身不是这个策略的出场理由 —— 那是止损/趋势策略的活。"""
    closes = [100.0] * 60 + [100.0 - i * 2 for i in range(1, 25)]
    market, sig = _signals(closes)
    upper, _ = _bands(market)
    assert not sig.exit[:, 0].any() or (market.close[:, 0] >= upper[:, 0]).any()


def test_exit_at_mid_takes_profit_earlier_than_at_upper():
    """到中轨就走是"更快落袋"的选项, 必须真的比等上轨早。"""
    closes = [100.0] * 60 + [100.0 + i * 3 for i in range(1, 25)]
    _, upper_exit = _signals(closes)
    _, mid_exit = _signals(closes, {"exit_at_mid": True})
    first_upper = np.flatnonzero(upper_exit.exit[:, 0])
    first_mid = np.flatnonzero(mid_exit.exit[:, 0])
    assert first_mid.size and first_upper.size
    assert first_mid.min() <= first_upper.min()


# ---------- 不接飞刀 ----------

def test_entry_requires_reclaiming_the_lower_band_not_touching_it():
    """跌破下轨说明它正在跌, 当天买就是接飞刀 —— 必须等收回通道内。"""
    closes = [100.0] * 60 + [80.0, 78.0, 76.0, 74.0]   # 一路破轨下行, 从不收回
    market, sig = _signals(closes)
    _, lower = _bands(market)
    broke = (market.close[:, 0] <= lower[:, 0]).any()
    assert broke, "前提: 这段确实跌破了下轨"
    assert not sig.entry[:, 0].any(), "一路下跌不该产生任何买入信号"


def test_entry_fires_on_the_bar_that_closes_back_inside():
    closes = [100.0] * 60 + [80.0, 92.0]   # 破轨后一根大幅收回
    market, sig = _signals(closes)
    _, lower = _bands(market)
    hits = np.flatnonzero(sig.entry[:, 0])
    assert hits.size == 1
    i = int(hits[0])
    assert market.close[i, 0] > lower[i, 0], "买在收回通道内那一根"
    assert market.close[i - 1, 0] <= lower[i - 1, 0], "前一根确实在轨下"


def test_no_entry_when_price_never_leaves_the_channel():
    """通道内正常波动不该产生信号 —— 这个策略只在触轨后动手。"""
    closes = [100.0 + (i % 5) * 0.4 for i in range(80)]
    _, sig = _signals(closes)
    assert not sig.entry[:, 0].any()


# ---------- 趋势闸 ----------

def test_trend_filter_blocks_dip_buying_in_a_downtrend():
    """均值回归最亏钱的场景: 下跌趋势里下轨随均线一路下移,
    每次都"触轨企稳"、每次都继续跌。默认必须拦住。"""
    closes = [300.0 - i * 1.5 for i in range(130)] + [75.0, 105.0]
    _, off = _signals(closes, {"trend_filter": False})
    _, on = _signals(closes, {"trend_filter": True})
    assert off.entry[:, 0].any(), "前提: 关掉闸时确实会抄这个底"
    assert not on.entry[:, 0].any(), "开着闸就该拦住 —— 收盘在 MA120 之下"


def test_trend_filter_allows_a_dip_inside_an_uptrend():
    closes = [100.0 + i * 1.2 for i in range(130)]
    closes += [closes[-1] * 0.80, closes[-1] * 0.97]
    _, on = _signals(closes, {"trend_filter": True})
    assert on.entry[:, 0].any(), "长期趋势没坏的回调该照做"


# ---------- 与决策台/图表同源 ----------

def test_bands_come_from_the_shared_constants():
    """三档参数必须取自 indicators.keltner.BANDS —— 策略、决策台三列、
    个股分析图表三处各写一份的话, 回测验证的就不是你在界面上看到的东西。"""
    assert kr._BANDS == {b[0]: (b[1] or f"ma{b[2]}", b[3], b[4]) for b in BANDS}
    assert kr._BANDS["s"] == ("ma20", 2.0, "短期")
    assert kr._BANDS["m"] == ("ma60", 2.5, "中期")
    assert kr._BANDS["l"] == ("ma120", 3.0, "长期")


def test_band_choice_actually_changes_the_channel():
    """三个档位必须真的不同, 否则参数是个摆设。

    上升趋势里 MA20 高于 MA60, 所以短期下轨也高于中期下轨 —— 一次浅回调
    只会跌穿短期下轨, 中期通道根本没被碰到。"""
    up = [100.0 + i * 1.0 for i in range(130)]
    closes = up + [up[-1] * 0.90, up[-1] * 0.97]
    _, short = _signals(closes, {"band": "s"})
    _, mid = _signals(closes, {"band": "m"})
    assert short.entry[:, 0].any(), "浅回调跌穿了短期下轨"
    assert not mid.entry[:, 0].any(), "但没跌到中期下轨 —— 两档必须给出不同结论"


def test_unknown_band_falls_back_to_short_instead_of_crashing():
    _, fallback = _signals([100.0] * 60 + [80.0, 92.0], {"band": "乱填"})
    _, short = _signals([100.0] * 60 + [80.0, 92.0], {"band": "s"})
    assert np.array_equal(fallback.entry, short.entry)


# ---------- 预热与元信息 ----------

def test_warmup_covers_both_the_band_and_the_trend_filter():
    """少给预热会让前若干根算出空值 —— 通道要均线, 趋势闸要 MA120。"""
    assert kr.MATRIX_STRATEGY.required_warmup_bars({"band": "s", "trend_filter": False}) == 40
    assert kr.MATRIX_STRATEGY.required_warmup_bars({"band": "s"}) == 140
    assert kr.MATRIX_STRATEGY.required_warmup_bars({"band": "l"}) == 140


def test_no_signals_before_the_channel_exists():
    """均线/ATR 尚未成形的前若干根一律不出信号, 不拿空值当 0 用。"""
    closes = [100.0] * 5 + [80.0, 92.0]
    _, sig = _signals(closes)
    assert not sig.entry[:, 0].any() and not sig.exit[:, 0].any()


def test_meta_declares_a_position_driven_exit():
    """出场信号名必须体现"到上轨", 复盘时能一眼看出这笔是高抛还是破位。"""
    assert kr.EXIT_SIGNALS == ["signal_keltner_upper_reached"]
    assert kr.ENTRY_SIGNALS == ["signal_keltner_lower_reclaim"]
    assert kr.STOP_LOSS is not None, "均值回归必须有硬止损兜底 —— 企稳判断错了就是接飞刀"
    assert kr.MAX_HOLD_DAYS and kr.MAX_HOLD_DAYS <= 30


def test_strategy_is_discoverable_with_valid_meta():
    assert kr.META["id"] == "keltner_reversion"
    assert "stock" in kr.META["asset_types"], "builtin 必须声明 asset_types"
    ids = {p["id"] for p in kr.META["params"]}
    assert ids == {"band", "trend_filter", "exit_at_mid"}
    band = next(p for p in kr.META["params"] if p["id"] == "band")
    assert {o["value"] for o in band["options"]} == {"s", "m", "l"}
