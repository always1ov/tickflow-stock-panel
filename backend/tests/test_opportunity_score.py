"""[fork R134] 买入机会评分 v2: 三道门槛 + 三维度加权。

这组测试守的是 v2 之所以存在的那几条 —— 它们一旦回退, 系统就变回 v1:
  1. 分数不再饱和(v1 理论上限 151 夹到 100, 榜首一片并列);
  2. 因子是**区间最优**不是单调递增(量比 5.0 必须低于 1.6, 位置贴上轨必须低于刚站上生命线);
  3. 门槛是硬的(逆势/破生命线/长期下跌直接出局), 但**数据缺失一律放行**。
"""
from __future__ import annotations

import pytest

from app.services import opportunity_score as osc


def _s(**kw):
    base = dict(duration=1, state="UT", rs_pct=6.0, vol_ratio=1.6,
                turnover_rate=5.0, channel_pct=0.56)
    base.update(kw)
    return osc.score_candidate(**base)


# ------------------------------------------------------- 门槛


def _gate(**kw):
    base = dict(state="UT", above_ma20=True, above_ma20_prev=True,
                close=12.0, ma120=10.0, ma120_rising=True)
    base.update(kw)
    return osc.check_gates(**base)


def test_ideal_candidate_passes_all_gates():
    assert _gate() == {"ok": True, "failed": []}


@pytest.mark.parametrize("state", ["DT", "NREA", "SREA"])
def test_bearish_states_are_rejected(state):
    """逆势票不该靠高分翻身 —— v1 里"逼近突破"那一路完全不看趋势状态。"""
    assert osc.GATE_TREND in _gate(state=state)["failed"]


@pytest.mark.parametrize("state", ["UT", "NR", "SR"])
def test_bullish_states_pass(state):
    assert osc.GATE_TREND not in _gate(state=state)["failed"]


def test_below_lifeline_is_rejected():
    assert osc.GATE_LIFELINE in _gate(above_ma20=False)["failed"]


def test_lifeline_needs_two_consecutive_days():
    """单日判定会在 MA20 附近反复穿越时把同一只票每天踢进踢出。"""
    assert osc.GATE_LIFELINE in _gate(above_ma20=True, above_ma20_prev=False)["failed"]


def test_lifeline_falls_back_to_today_when_prev_unknown():
    assert _gate(above_ma20=True, above_ma20_prev=None)["ok"] is True


def test_long_downtrend_needs_both_position_and_slope():
    """位置 + 斜率同时成立才算长期下跌。

    只看位置会误杀刚从底部拉起、还没回到 MA120 上方的强势股;
    只看斜率会漏掉高位刚拐头的票。
    """
    both = _gate(close=9.0, ma120=10.0, ma120_rising=False)
    assert osc.GATE_LONG_DOWN in both["failed"]
    # 在 MA120 之下但均线在向上 —— 底部拉起, 放行
    assert osc.GATE_LONG_DOWN not in _gate(close=9.0, ma120=10.0, ma120_rising=True)["failed"]
    # MA120 向下但价格还在其上 —— 高位刚拐头, 这一条不挡(六态/生命线会先接手)
    assert osc.GATE_LONG_DOWN not in _gate(close=11.0, ma120=10.0, ma120_rising=False)["failed"]


def test_missing_data_never_rejects():
    """门槛只挡"明确不该看的", 不挡"我们没读到的"。

    新股不足 120 根算不出 MA120, 不该因此被判长期下跌 —— 那种消失用户查不出来。
    """
    assert osc.check_gates(state=None, above_ma20=None, above_ma20_prev=None,
                           close=None, ma120=None, ma120_rising=None) == {"ok": True, "failed": []}


def test_multiple_gates_can_fail_together():
    out = _gate(state="DT", above_ma20=False, close=9.0, ma120=10.0, ma120_rising=False)
    assert set(out["failed"]) == {osc.GATE_TREND, osc.GATE_LIFELINE, osc.GATE_LONG_DOWN}


def test_every_gate_has_chinese_label_and_reason():
    for code in (osc.GATE_TREND, osc.GATE_LIFELINE, osc.GATE_LONG_DOWN):
        assert osc.GATE_CN.get(code) and osc.GATE_WHY.get(code)


# ------------------------------------------------------- 曲线是区间型, 不是单调


def test_volume_ratio_is_range_optimal_not_monotonic():
    """量比 4 意味着这一波**已经发生**了 —— 那是追高不是苗头。"""
    peak = _s(vol_ratio=1.6)["score"]
    huge = _s(vol_ratio=5.0)["score"]
    tiny = _s(vol_ratio=0.6)["score"]
    assert peak > huge and peak > tiny
    # 曲线本身也要单峰: 5.0 不能比 2.0 高
    assert _s(vol_ratio=2.0)["score"] > huge


def test_position_sweet_spot_is_just_above_lifeline():
    """刚站上生命线 > 贴上轨。贴上轨是追高。"""
    just_above = _s(channel_pct=0.55)["score"]
    upper = _s(channel_pct=1.0)["score"]
    assert just_above > upper


def test_relative_strength_is_range_optimal():
    """跑输大盘是补涨陷阱; 跑赢 45 个点则苗头期早过了。"""
    good = _s(rs_pct=8.0)["score"]
    assert good > _s(rs_pct=-10.0)["score"]
    assert good > _s(rs_pct=50.0)["score"]


def test_freshness_decays_with_duration():
    scores = [_s(duration=d)["score"] for d in (1, 2, 3, 4, 5, 10)]
    assert scores[0] >= scores[1] > scores[2] > scores[3] > scores[4] > scores[5]


def test_stronger_six_state_scores_higher():
    assert _s(state="UT")["score"] > _s(state="NR")["score"] > _s(state="SR")["score"]


# ------------------------------------------------------- 分数不再饱和


def test_already_run_candidate_is_clearly_worse_than_fresh_one():
    """v1 里这两只都会顶到 100 分并列; v2 必须拉开明显差距。"""
    fresh = _s(duration=1, vol_ratio=1.6, channel_pct=0.55, rs_pct=6.0)["score"]
    ran = _s(duration=1, vol_ratio=5.0, channel_pct=1.05, rs_pct=45.0)["score"]
    assert fresh - ran >= 30, f"区分度不足: {fresh} vs {ran}"


def test_score_stays_in_range_across_extremes():
    for d in (1, 3, 20):
        for vr in (0.1, 1.6, 12.0):
            for cp in (-0.2, 0.55, 1.8):
                s = _s(duration=d, vol_ratio=vr, channel_pct=cp)["score"]
                assert 0 <= s <= 100


def test_no_clamp_is_needed():
    """满分只能靠三个维度都到峰值拿到, 不是靠加项堆出来后被夹平。"""
    best = osc.score_candidate(duration=1, state="UT", rs_pct=14.0, vol_ratio=1.8,
                               turnover_rate=5.0, channel_pct=0.58)
    assert best["score"] == 100
    assert all(v is not None and v >= 99 for v in best["dims"].values())


# ------------------------------------------------------- 缺数据的处理


def test_missing_factor_renormalizes_inside_dimension():
    """缺换手率不该按 0 分算 —— 那是因为"我们没读到"去惩罚这只票。"""
    with_turn = _s(turnover_rate=5.0)
    without = _s(turnover_rate=None)
    # 量比同样在峰值, 所以去掉换手率后量能维度应该仍然很高, 而不是掉一半
    assert without["dims"]["volume"] > 85
    assert without["coverage"]["volume"] == pytest.approx(0.7)
    assert with_turn["coverage"]["volume"] == 1.0


def test_whole_dimension_missing_is_flagged_partial():
    r = osc.score_candidate(duration=1, state="UT", rs_pct=6.0, vol_ratio=None,
                            turnover_rate=None, channel_pct=0.56)
    assert r["dims"]["volume"] is None
    assert r["partial"] is True          # 界面必须说清楚这一档没算进去
    assert r["score"] > 0


def test_full_coverage_is_not_partial():
    assert _s()["partial"] is False


def test_near_breakout_gets_freshness_without_a_signal():
    """"逼近触发价"那一路没有六态信号新鲜度可用, 但突破还没发生, 跑道最长。"""
    r = osc.score_candidate(duration=None, state="UT", rs_pct=6.0, vol_ratio=1.6,
                            turnover_rate=5.0, channel_pct=0.56, near_breakout=True)
    assert r["factors"]["fresh"] == osc.FRESH_NEAR_BREAKOUT
    assert r["fresh_from"] == "near_breakout"


def test_near_breakout_takes_the_better_of_two_freshness_sources():
    """既是新信号又正好逼近触发价 —— 不该因信号已第 5 天就把"马上到价"抹掉。"""
    stale_signal = osc.score_candidate(duration=5, state="UT", rs_pct=6.0, vol_ratio=1.6,
                                       turnover_rate=5.0, channel_pct=0.56,
                                       near_breakout=True)
    assert stale_signal["fresh_from"] == "near_breakout"
    day1 = osc.score_candidate(duration=1, state="UT", rs_pct=6.0, vol_ratio=1.6,
                               turnover_rate=5.0, channel_pct=0.56, near_breakout=True)
    assert day1["fresh_from"] == "signal"      # 第 1 天比 near_breakout 更值钱


def test_nothing_at_all_scores_zero_not_crash():
    r = osc.score_candidate(duration=None, state=None, rs_pct=None, vol_ratio=None,
                            turnover_rate=None, channel_pct=None)
    assert r["score"] == 0 and r["partial"] is True


# ------------------------------------------------------- 曲线本身


def test_piecewise_interpolates_and_clamps_at_ends():
    pts = ((0.0, 0.0), (1.0, 10.0), (2.0, 0.0))
    assert osc._piecewise(-5, pts) == 0.0        # 左端外不外推
    assert osc._piecewise(0.5, pts) == 5.0
    assert osc._piecewise(1.5, pts) == 5.0
    assert osc._piecewise(99, pts) == 0.0        # 右端外不外推


@pytest.mark.parametrize("curve", [osc.FRESH_CURVE, osc.RS_CURVE, osc.VOL_RATIO_CURVE,
                                   osc.TURNOVER_CURVE, osc.POS_CURVE])
def test_curves_are_sorted_and_bounded(curve):
    xs = [p[0] for p in curve]
    assert xs == sorted(xs), "控制点必须按 x 升序, 否则插值会读错区间"
    assert all(0 <= p[1] <= 100 for p in curve)


def test_weights_sum_to_one():
    assert sum(osc.WEIGHTS.values()) == pytest.approx(1.0)
    assert sum(osc.TREND_WEIGHTS.values()) == pytest.approx(1.0)
    assert sum(osc.VOLUME_WEIGHTS.values()) == pytest.approx(1.0)


# ------------------------------------------------------- 说人话


def test_explain_only_talks_about_the_score_itself():
    """理由里不能出现主线/AI/胜率 —— 那些是注记, 混进来用户就分不清哪句影响了排名。"""
    lines = osc.explain(_s(), duration=1, vol_ratio=1.6, channel_pct=0.55, rs_pct=6.0)
    assert lines
    joined = "".join(lines)
    for forbidden in ("主线", "AI", "胜率", "龙虎"):
        assert forbidden not in joined


def test_explain_calls_out_the_expensive_position():
    lines = osc.explain(_s(channel_pct=1.0), channel_pct=1.0)
    assert any("最贵" in x for x in lines)


def test_explain_survives_missing_inputs():
    assert osc.explain(_s()) == [] or isinstance(osc.explain(_s()), list)


# ------------------------------------------------------- [R139] 同分时的次序


def test_ties_break_on_data_completeness_then_trend():
    """同分时按代码字典序是个无意义的顺序, 而用户会照着名次从上往下看。"""
    from app.api.today import score_opportunities
    base_t = {"state": "UT", "state_cn": "上涨趋势", "side": "多头", "duration": 2,
              "close": 10.0, "as_of": "2026-08-31", "signal": "转多",
              "signal_desc": "突破", "ret_20d": 0.08}
    gate = {"above_ma20": True, "above_ma20_prev": True, "close": 10.0,
            "ma120": 8.0, "ma120_rising": True}
    # 代码字典序上 A 在前, 但 A 缺量能维度(partial) —— 数据齐全的 Z 必须排前面
    trends = {"AAA.SH": dict(base_t), "ZZZ.SH": dict(base_t)}
    names = {"AAA.SH": "甲", "ZZZ.SH": "乙"}
    ranked, _ = score_opportunities(trends, {}, names, bench_ret=0.02, extras={
        "AAA.SH": {"gate": gate, "channel_pct": 0.6},
        "ZZZ.SH": {"gate": gate, "channel_pct": 0.6, "vol_ratio": 1.6, "turnover": 4.0},
    })
    order = [o["symbol"] for o in ranked]
    if ranked[0]["score"] == ranked[1]["score"]:
        assert order[0] == "ZZZ.SH", "同分时数据齐全的应排在 partial 前面"
    assert ranked[0]["partial"] is False


def test_sort_is_deterministic_across_calls():
    """同一份数据每次刷新顺序必须一致 —— 名次天天跳用户没法用。"""
    from app.api.today import score_opportunities
    t = {"state": "UT", "state_cn": "上涨趋势", "side": "多头", "duration": 2,
         "close": 10.0, "as_of": "2026-08-31", "signal": "转多",
         "signal_desc": "突破", "ret_20d": 0.08}
    gate = {"above_ma20": True, "above_ma20_prev": True, "close": 10.0,
            "ma120": 8.0, "ma120_rising": True}
    trends = {f"{i:06d}.SH": dict(t) for i in range(6)}
    names = {s: s for s in trends}
    ex = {s: {"gate": gate, "channel_pct": 0.6, "vol_ratio": 1.6, "turnover": 4.0}
          for s in trends}
    a = [o["symbol"] for o in score_opportunities(trends, {}, names, 0.02, ex)[0]]
    b = [o["symbol"] for o in score_opportunities(trends, {}, names, 0.02, ex)[0]]
    assert a == b
