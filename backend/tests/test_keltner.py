"""[fork 增强] R42 Keltner 三档位置。

两条不变量最要紧:
  1. 决策台的三列和个股分析图表必须是同一组数 —— 两条路径各写一份公式,
     图表说"贴着上轨"、决策台说"通道内"的那天没法查。
  2. 判定顺序: 先看轨外, 再看贴近。已经破上轨的票同时也"在上轨 0.5 ATR 以内",
     反过来判会把突破说成"贴近", 那是两件完全不同的事。
"""
from __future__ import annotations

from types import SimpleNamespace

import polars as pl
import pytest

from app.indicators import keltner as k


# ---------- 通道计算 ----------

def test_band_is_ma_plus_minus_n_atr():
    assert k.band(100, 5, 2.0) == (110.0, 90.0)
    assert k.band(100, 4, 2.5) == (110.0, 90.0)


@pytest.mark.parametrize("bad", [None, "高", float("nan"), float("inf")])
def test_band_rejects_junk(bad):
    assert k.band(bad, 5, 2.0) is None
    assert k.band(100, bad, 2.0) is None


def test_band_rejects_non_positive_atr():
    """ATR 为 0 时上下轨会重合成一条线, 那不是通道。"""
    assert k.band(100, 0, 2.0) is None
    assert k.band(100, -3, 2.0) is None


# ---------- 位置判定 ----------

@pytest.mark.parametrize("close,expected", [
    (112, k.POS_ABOVE),        # 上轨 110 之上
    (108.5, k.POS_NEAR_UPPER),  # 距上轨 1.5, 小于 0.5×ATR(2.5)
    (100, k.POS_INSIDE),
    (91.5, k.POS_NEAR_LOWER),
    (85, k.POS_BELOW),
])
def test_classify_covers_all_five_states(close, expected):
    assert k.classify(close, 110, 90, 5) == expected


def test_breakout_is_not_reported_as_merely_near():
    """破上轨的票必然也在上轨 0.5 ATR 以内 —— 判定顺序反了就会把突破说成贴近。"""
    assert k.classify(110.5, 110, 90, 5) == k.POS_ABOVE
    assert k.classify(89.5, 110, 90, 5) == k.POS_BELOW


def test_exactly_on_the_band_counts_as_inside_not_broken():
    """收盘正好等于轨价不算破 —— 破位要有确定性, 等于不是大于。"""
    assert k.classify(110, 110, 90, 5) == k.POS_NEAR_UPPER
    assert k.classify(90, 110, 90, 5) == k.POS_NEAR_LOWER


def test_near_scales_with_the_stocks_own_volatility():
    """"贴近"用 ATR 而不是百分比: 用百分比的话高波动票永远不贴、低波动票永远贴着。"""
    assert k.classify(105, 110, 90, 2) == k.POS_INSIDE, "波动小: 差 5 块还很远"
    assert k.classify(105, 110, 90, 12) == k.POS_NEAR_UPPER, "波动大: 差 5 块半天就到"


def test_classify_rejects_an_inverted_channel():
    assert k.classify(100, 90, 110, 5) is None


@pytest.mark.parametrize("bad", [None, "x", float("nan")])
def test_classify_rejects_junk(bad):
    assert k.classify(bad, 110, 90, 5) is None
    assert k.classify(100, 110, 90, bad) is None


# ---------- 通道内位置 ----------

def test_pct_maps_lower_to_zero_and_upper_to_one():
    assert k.pct_in_channel(90, 110, 90) == 0.0
    assert k.pct_in_channel(110, 110, 90) == 1.0
    assert k.pct_in_channel(100, 110, 90) == 0.5


def test_pct_goes_outside_zero_to_one_when_price_breaks_out():
    """轨外要能表达出来, 夹到 [0,1] 会让"破上轨"和"贴上轨"看起来一样。"""
    assert k.pct_in_channel(120, 110, 90) > 1.0
    assert k.pct_in_channel(80, 110, 90) < 0.0


# ---------- 完整读数 ----------

def test_assess_returns_everything_the_column_needs():
    got = k.assess(close=108.5, ma=100, atr=5, n=2.0)
    assert got["pos"] == k.POS_NEAR_UPPER and got["pos_cn"] == "贴上轨"
    assert got["upper"] == 110.0 and got["lower"] == 90.0
    assert got["to_upper_atr"] == 0.3, "还差 0.3 个 ATR 到上轨"
    assert got["hint"], "每一档都要有一句能显示给用户的解释"


def test_assess_returns_none_rather_than_a_hollow_shell():
    """算不出来就该缺席, 界面显示"—"; 返回一个 pos=None 的壳子会被当成真数据用。"""
    assert k.assess(close=100, ma=None, atr=5, n=2.0) is None
    assert k.assess(close=100, ma=100, atr=0, n=2.0) is None


def test_hints_are_descriptive_not_instructions():
    """通道位置是事实描述。同一个"破上轨"在趋势票上是强势确认、在震荡票上是超买,
    系统不该替用户下这个判断。"""
    for hint in k.POS_HINT.values():
        assert not any(w in hint for w in ("买入", "卖出", "该买", "该卖", "建议"))


# ---------- 与图表同源 ----------

def test_chart_and_board_share_the_same_parameters():
    """levels.py 的三档必须取自 BANDS —— 两处各写一份迟早对不上。"""
    from app.indicators.levels import KELTNER_BANDS

    assert KELTNER_BANDS is k.BANDS
    assert [(b[1], b[2], b[3]) for b in k.BANDS] == [
        ("ma20", 20, 2.0), ("ma60", 60, 2.5), (None, 120, 3.0)]


def test_chart_band_values_match_the_shared_formula():
    """同一组输入, 图表路径与共用公式必须给出同一个上下轨。"""
    from app.indicators.levels import _keltner_short

    df = pl.DataFrame({
        "close": [100.0] * 25, "ma20": [100.0] * 25, "atr_14": [5.0] * 25,
    })
    got = {row["label"]: row["value"] for row in _keltner_short(df)}
    upper, lower = k.band(100.0, 5.0, 2.0)
    assert got["短期通道上轨"] == round(upper, 2)
    assert got["短期通道下轨"] == round(lower, 2)


# ---------- 批量服务 ----------

class _Repo:
    """最新快照给预计算列, 日 K 只用来算 MA120。"""

    def __init__(self, rows, *, bars=140):
        self._rows = rows
        self._bars = bars
        self.batch_calls = 0

    def get_enriched_latest(self):
        return pl.DataFrame(self._rows), "2026-08-21"

    def get_daily_batch(self, symbols, start, end, columns=None):
        self.batch_calls += 1
        frames = []
        for i, s in enumerate(symbols):
            frames.append(pl.DataFrame({
                "symbol": [s] * self._bars,
                "date": [start] * self._bars,
                "close": [100.0 + i] * self._bars,
            }))
        return pl.concat(frames) if frames else pl.DataFrame()


def _rows():
    return [{"symbol": "600000.SH", "close": 108.5, "atr_14": 5.0, "ma20": 100.0, "ma60": 95.0}]


def test_batch_returns_all_three_bands():
    from app.services import keltner_service

    out = keltner_service.channels_for_symbols(_Repo(_rows()), ["600000.SH"])
    assert set(out["600000.SH"]) == {"s", "m", "l"}
    assert out["600000.SH"]["s"]["pos"] == k.POS_NEAR_UPPER
    assert out["600000.SH"]["s"]["band_cn"] == "短期"


def test_batch_matches_the_single_symbol_formula():
    """决策台与图表同一组数 —— 这是这个功能的全部意义。"""
    from app.services import keltner_service

    out = keltner_service.channels_for_symbols(_Repo(_rows()), ["600000.SH"])["600000.SH"]
    upper, lower = k.band(100.0, 5.0, 2.0)
    assert (out["s"]["upper"], out["s"]["lower"]) == (round(upper, 2), round(lower, 2))


def test_short_history_drops_only_the_long_band():
    """不足 120 根时长期档留空, 不拿 60 根算个假的"120 日均线"出来。"""
    from app.services import keltner_service

    out = keltner_service.channels_for_symbols(_Repo(_rows(), bars=60), ["600000.SH"])
    assert set(out["600000.SH"]) == {"s", "m"}


def test_missing_ma60_column_drops_only_the_mid_band():
    from app.services import keltner_service

    rows = [{"symbol": "600000.SH", "close": 108.5, "atr_14": 5.0, "ma20": 100.0}]
    out = keltner_service.channels_for_symbols(_Repo(rows), ["600000.SH"])
    assert set(out["600000.SH"]) == {"s", "l"}


def test_batch_reads_daily_k_once_not_per_symbol():
    """147 只自选逐只读 120 天会把决策台拖死。"""
    from app.services import keltner_service

    repo = _Repo([dict(_rows()[0], symbol=f"60000{i}.SH") for i in range(8)])
    keltner_service.channels_for_symbols(repo, [f"60000{i}.SH" for i in range(8)])
    assert repo.batch_calls == 1


def test_symbols_are_matched_case_insensitively():
    from app.services import keltner_service

    out = keltner_service.channels_for_symbols(_Repo(_rows()), ["600000.sh"])
    assert "600000.SH" in out


def test_empty_and_broken_inputs_degrade_quietly():
    from app.services import keltner_service

    assert keltner_service.channels_for_symbols(_Repo(_rows()), []) == {}
    assert keltner_service.channels_for_symbols(
        SimpleNamespace(get_enriched_latest=lambda: (pl.DataFrame(), None)), ["600000.SH"]) == {}


def test_unknown_symbol_is_simply_absent():
    from app.services import keltner_service

    assert keltner_service.channels_for_symbols(_Repo(_rows()), ["999999.SZ"]) == {}
