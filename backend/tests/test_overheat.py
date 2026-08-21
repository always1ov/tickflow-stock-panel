"""[fork 增强] R41 短期过热的测量与决策接入。

这个功能唯一的大风险是**卖飞** —— 主升浪起步 RSI 冲高是常态, 一律判过热就减仓,
等于系统性地在最好的行情里下车。所以下面一半的测试是在守"什么时候**不该**报过热"。
"""
from __future__ import annotations

import pytest

from app.api.today import holding_stance
from app.services import overheat


# ---------- 测量 ----------

def _hot():
    """RSI 78、离 MA20 四个 ATR —— 明确的冲过头。"""
    return overheat.assess(rsi=78, close=124.0, ma20=100.0, atr=6.0)


def test_hot_needs_both_overbought_and_far_from_the_mean():
    h = _hot()
    assert h["level"] == overheat.LEVEL_HOT
    assert h["rsi"] == 78.0 and h["dev_atr"] == 4.0


def test_high_rsi_alone_is_not_overheated():
    """一轮像样的主升浪 RSI 常年 70 以上 —— 只看 RSI 会把健康趋势大批误伤。"""
    assert overheat.assess(rsi=82, close=101.0, ma20=100.0, atr=6.0) is None


def test_far_from_the_mean_alone_is_not_overheated():
    """慢牛可以长期在均线上方运行而不超买。"""
    assert overheat.assess(rsi=55, close=130.0, ma20=100.0, atr=6.0) is None


def test_warm_is_a_separate_softer_level():
    h = overheat.assess(rsi=71, close=115.0, ma20=100.0, atr=6.0)
    assert h["level"] == overheat.LEVEL_WARM and h["level_cn"] == "偏热"


def test_atr_normalisation_scales_to_the_stock_itself():
    """同样 24% 的乖离: 高波动票很正常, 低波动票才是异常。
    用固定百分比阈值会把 20cm 的票系统性地全判成过热。"""
    calm = overheat.assess(rsi=78, close=124.0, ma20=100.0, atr=3.0)
    wild = overheat.assess(rsi=78, close=124.0, ma20=100.0, atr=12.0)
    wilder = overheat.assess(rsi=78, close=124.0, ma20=100.0, atr=20.0)
    assert calm["level"] == overheat.LEVEL_HOT, "波动小的票, 这个幅度确实过头了"
    assert wild["level"] == overheat.LEVEL_WARM, "波动大一些, 同样幅度自动降一档"
    assert wilder is None, "波动足够大时这就是它的日常, 完全不该报"


def test_below_the_mean_is_never_overheated():
    assert overheat.assess(rsi=78, close=90.0, ma20=100.0, atr=6.0) is None
    assert overheat.deviation_atr(90.0, 100.0, 6.0) < 0


@pytest.mark.parametrize("bad", [None, "很高", float("nan"), float("inf")])
def test_missing_or_junk_inputs_return_none_not_a_wrong_verdict(bad):
    assert overheat.assess(rsi=bad, close=124.0, ma20=100.0, atr=6.0) is None
    assert overheat.assess(rsi=78, close=124.0, ma20=bad, atr=6.0) is None


def test_zero_atr_does_not_divide_by_zero():
    assert overheat.assess(rsi=78, close=124.0, ma20=100.0, atr=0) is None


def test_text_carries_the_real_numbers():
    """标签必须能被用户复核 —— 只显示"过热"两个字等于要人盲信。"""
    assert "RSI 78" in _hot()["text"] and "4.0 个 ATR" in _hot()["text"]


def test_extract_reads_an_enriched_row():
    assert overheat.extract(
        {"rsi_14": 78, "close": 124.0, "ma20": 100.0, "atr_14": 6.0})["level"] == "hot"
    assert overheat.extract({"close": 124.0}) is None, "列缺失时安静跳过"


def test_is_hot_only_counts_the_top_level():
    assert overheat.is_hot(_hot()) is True
    assert overheat.is_hot(overheat.assess(rsi=71, close=115.0, ma20=100.0, atr=6.0)) is False
    assert overheat.is_hot(None) is False


# ---------- 决策接入 ----------

def _stance(**kw):
    base = dict(exit_triggered=False, distance_pct=-0.20, trend_side="多头",
                ai_signal="buy", trend_signal="转多", heat=None,
                pnl_pct=None, trend_duration=10)
    base.update(kw)
    return holding_stance(
        base["exit_triggered"], base["distance_pct"], base["trend_side"],
        base["ai_signal"], base["trend_signal"],
        heat=base["heat"], pnl_pct=base["pnl_pct"],
        trend_duration=base["trend_duration"])


def test_overheat_blocks_a_would_be_add():
    """这条比减仓重要: 原来只看趋势和 AI, 不看价格冲到哪了 ——
    那是在最贵的位置加最重的注。"""
    assert _stance()[0] == "加仓", "前提: 不过热时确实建议加"
    stance, why = _stance(heat=_hot())
    assert stance == "持有" and "最贵" in why


def test_overheat_with_real_profit_suggests_trimming():
    stance, why = _stance(heat=_hot(), pnl_pct=0.35, ai_signal=None, trend_signal=None)
    assert stance == "减仓" and "落袋" in why
    assert "趋势没坏" in why, "要说清这是止盈不是止损, 否则用户会以为该清仓"


def test_no_trim_without_meaningful_profit():
    """浮亏还嫌它涨太急, 是自相矛盾。"""
    assert _stance(heat=_hot(), pnl_pct=-0.05, ai_signal=None)[0] == "持有"
    assert _stance(heat=_hot(), pnl_pct=0.02, ai_signal=None)[0] == "持有"


def test_freshly_turned_strong_is_never_trimmed_for_being_hot():
    """主升浪第 1-2 天 RSI 冲高是常态, 这时候减就是卖飞 —— 本功能最大的风险。"""
    for d in (1, 2):
        assert _stance(heat=_hot(), pnl_pct=0.40, trend_duration=d,
                       ai_signal=None)[0] == "持有"
    assert _stance(heat=_hot(), pnl_pct=0.40, trend_duration=3,
                   ai_signal=None)[0] == "减仓", "过了保护期才谈落袋"


def test_warm_never_changes_the_stance():
    warm = overheat.assess(rsi=71, close=115.0, ma20=100.0, atr=6.0)
    assert _stance(heat=warm)[0] == "加仓", "偏热只标注, 不改档位"
    assert _stance(heat=warm, pnl_pct=0.4, ai_signal=None)[0] == "持有"


def test_risk_driven_exits_still_outrank_overheat():
    """破线/转空/AI 看空都是"必须处理", 过热只是"可以落袋"。
    撞上时说后者会让人误以为只是获利了结。"""
    assert _stance(exit_triggered=True, heat=_hot(), pnl_pct=0.4)[0] == "离场"
    for kw in ({"trend_side": "空头"}, {"ai_signal": "sell"}, {"distance_pct": -0.01}):
        stance, why = _stance(heat=_hot(), pnl_pct=0.4, **kw)
        assert stance == "减仓"
        assert "落袋" not in why, f"{kw} 的减仓理由不该被过热盖掉"


def test_behaviour_is_unchanged_when_heat_is_absent():
    """没有过热数据(旧数据/指标列缺失)时, 一切与 R41 之前逐字一致。"""
    assert _stance()[0] == "加仓"
    assert _stance(ai_signal=None)[0] == "持有"
    assert _stance(exit_triggered=True)[0] == "离场"
    assert holding_stance(False, -0.2, "多头", "buy", "转多")[0] == "加仓"


# ---------- 机会区打分 ----------

def _rank(heat):
    from app.api.today import rank_opportunities

    trends = {"600000.SH": {"signal": "转多", "signal_desc": "刚转强", "duration": 1,
                            "state": "UT", "close": 10.0}}
    extras = {"600000.SH": {"heat": heat}} if heat else None
    shown, _ = rank_opportunities(trends, {}, {"600000.SH": "测试"},
                                  min_score=0, max_show=5, extras=extras)
    return shown[0]


def test_overheated_candidate_is_penalised_and_told_why():
    base = _rank(None)["score"]
    hot = _rank(_hot())
    assert hot["score"] == base - 10
    assert "最贵的地方买" in hot["why"]
    assert hot["heat"]["level"] == "hot"


def test_warm_candidate_is_tagged_but_not_penalised():
    """强势趋势里 RSI 偏高是常态, 一并扣分会把系统推成专挑弱势票。"""
    warm = overheat.assess(rsi=71, close=115.0, ma20=100.0, atr=6.0)
    assert _rank(warm)["score"] == _rank(None)["score"]
    assert "节奏偏急" in _rank(warm)["why"]


def test_candidates_without_heat_carry_an_explicit_none():
    assert _rank(None)["heat"] is None, "字段要在, 值为 None —— 前端不必判断键存不存在"
