"""[fork 增强] R43 高抛低吸改由 Keltner 三档通道位置驱动。

原来这套判定用的是 RSI + MA20 乖离(R41), 已整体撤掉 —— 决策台三列、个股分析图表、
回测策略、今日总览四处现在是同一组口径, 你在界面上看到的"贴上轨"和系统据以
建议减仓的"贴上轨"是同一件事。

这个功能唯一的大风险仍然是**卖飞**, 所以下面一半测试在守"什么时候**不该**提示高抛"。
"""
from __future__ import annotations

import pytest

from app.api.today import holding_stance
from app.indicators import keltner as k


def _bands(s, m=None, l=None):  # noqa: E741
    out = {"s": {"pos": s, "pos_cn": k.POS_CN[s]}}
    if m:
        out["m"] = {"pos": m, "pos_cn": k.POS_CN[m]}
    if l:
        out["l"] = {"pos": l, "pos_cn": k.POS_CN[l]}
    return out


def _high(strong=True):
    return k.pressure(_bands(k.POS_ABOVE, k.POS_NEAR_UPPER if strong else k.POS_INSIDE))


def _low(strong=True):
    return k.pressure(_bands(k.POS_BELOW, k.POS_NEAR_LOWER if strong else k.POS_INSIDE))


# ---------- 三档合成 ----------

def test_short_band_sets_the_direction():
    """短期是操作级别 —— 这是你真正要动手的那一档。"""
    assert k.pressure(_bands(k.POS_ABOVE))["side"] == k.SIDE_HIGH
    assert k.pressure(_bands(k.POS_NEAR_UPPER))["side"] == k.SIDE_HIGH
    assert k.pressure(_bands(k.POS_BELOW))["side"] == k.SIDE_LOW
    assert k.pressure(_bands(k.POS_NEAR_LOWER))["side"] == k.SIDE_LOW


def test_inside_the_short_channel_is_no_pressure_at_all():
    assert k.pressure(_bands(k.POS_INSIDE)) is None
    assert k.pressure(_bands(k.POS_INSIDE, k.POS_ABOVE)) is None, "中期不能自己起意"


def test_mid_band_amplifies_but_never_flips():
    """让中期能否决短期的话, 一只中期在通道中部、短期已破上轨的票会被判成"没事",
    而它明明已经短线到位了。"""
    assert k.pressure(_bands(k.POS_ABOVE, k.POS_NEAR_UPPER))["level"] == k.LEVEL_STRONG
    mixed = k.pressure(_bands(k.POS_ABOVE, k.POS_NEAR_LOWER))
    assert mixed["side"] == k.SIDE_HIGH and mixed["level"] == k.LEVEL_MILD


def test_long_band_is_reference_only():
    """半年通道太钝, 拿它决定这周该不该减仓等于用尺子量头发。"""
    only_long = k.pressure(_bands(k.POS_INSIDE, k.POS_INSIDE, k.POS_ABOVE))
    assert only_long is None
    with_long = k.pressure(_bands(k.POS_ABOVE, k.POS_ABOVE, k.POS_ABOVE))
    assert with_long["bands_aligned"] == 3 and "长期" in with_long["text"]


def test_text_names_the_bands_that_actually_agree():
    assert k.pressure(_bands(k.POS_ABOVE, k.POS_INSIDE))["text"] == "短期破上轨"
    assert "中期" in k.pressure(_bands(k.POS_ABOVE, k.POS_ABOVE))["text"]


def test_pressure_survives_missing_input():
    assert k.pressure(None) is None
    assert k.pressure({}) is None
    assert k.pressure({"m": {"pos": k.POS_ABOVE}}) is None, "没有短期档就给不出结论"


def test_helpers():
    assert k.is_high(_high()) and not k.is_high(_low())
    assert k.is_strong(_high(strong=True)) and not k.is_strong(_high(strong=False))
    assert not k.is_high(None) and not k.is_strong(None)


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


def test_upper_band_blocks_a_would_be_add():
    """这条比减仓重要: 原来只看趋势和 AI, 不看价格在通道哪个位置 ——
    那是在最贵的位置加最重的注。只要贴到上沿就挡, 不要求共振。"""
    assert _stance()[0] == "加仓", "前提: 通道内时确实建议加"
    for heat in (_high(strong=True), _high(strong=False)):
        stance, why = _stance(heat=heat)
        assert stance == "持有" and "最贵" in why


def test_lower_band_does_not_block_adding():
    """贴下轨是低吸位置, 不该挡加仓。"""
    assert _stance(heat=_low())[0] == "加仓"


def test_resonant_upper_band_with_profit_suggests_trimming():
    stance, why = _stance(heat=_high(), pnl_pct=0.35, ai_signal=None, trend_signal=None)
    assert stance == "减仓" and "落袋" in why
    assert "趋势没坏" in why, "要说清这是止盈不是止损, 否则用户会以为该清仓"


def test_short_band_alone_does_not_trigger_trimming():
    """只有短期贴上轨太常见 —— 每次都提示等于天天喊减仓。"""
    assert _stance(heat=_high(strong=False), pnl_pct=0.35, ai_signal=None)[0] == "持有"


def test_no_trim_without_meaningful_profit():
    """浮亏还嫌它涨太急, 是自相矛盾。"""
    assert _stance(heat=_high(), pnl_pct=-0.05, ai_signal=None)[0] == "持有"
    assert _stance(heat=_high(), pnl_pct=0.02, ai_signal=None)[0] == "持有"


def test_freshly_turned_strong_is_never_trimmed():
    """主升浪起步就是沿着上轨走的, 这时候减就是卖飞 —— 本功能最大的风险。"""
    for d in (1, 2):
        assert _stance(heat=_high(), pnl_pct=0.40, trend_duration=d,
                       ai_signal=None)[0] == "持有"
    assert _stance(heat=_high(), pnl_pct=0.40, trend_duration=3,
                   ai_signal=None)[0] == "减仓", "过了保护期才谈落袋"


def test_risk_driven_exits_still_outrank_the_upper_band():
    """破线/转空/AI 看空都是"必须处理", 到上轨只是"可以落袋"。
    撞上时说后者会让人误以为只是获利了结。"""
    assert _stance(exit_triggered=True, heat=_high(), pnl_pct=0.4)[0] == "离场"
    for kw in ({"trend_side": "空头"}, {"ai_signal": "sell"}, {"distance_pct": -0.01}):
        stance, why = _stance(heat=_high(), pnl_pct=0.4, **kw)
        assert stance == "减仓"
        assert "落袋" not in why, f"{kw} 的减仓理由不该被通道位置盖掉"


def test_behaviour_is_unchanged_without_band_data():
    """新股/指标列缺失时通道算不出来, 一切回到 R43 之前的判定。"""
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


def test_resonant_upper_band_candidate_is_penalised():
    base = _rank(None)["score"]
    hot = _rank(_high())
    assert hot["score"] == base - 10
    assert "最贵的地方买" in hot["why"]


def test_short_band_alone_is_tagged_but_not_penalised():
    """强势趋势本来就是沿着上轨走的, 一并扣分会把系统推成专挑弱势票。"""
    assert _rank(_high(strong=False))["score"] == _rank(None)["score"]
    assert "贴近通道上沿" in _rank(_high(strong=False))["why"]


def test_lower_band_candidate_is_never_penalised():
    """贴下轨正是低吸要的位置 —— 扣它的分等于跟这个策略对着干。"""
    assert _rank(_low())["score"] == _rank(None)["score"]
    assert "低吸位置" in _rank(_low())["why"]


@pytest.mark.parametrize("heat", [None])
def test_candidates_without_bands_carry_an_explicit_none(heat):
    assert _rank(heat)["heat"] is None, "字段要在, 值为 None —— 前端不必判断键存不存在"
