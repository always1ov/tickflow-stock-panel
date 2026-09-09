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


# ================================================================
# [R230] 守住这次回退本身
#
# 上面 38 条是 R134 当年的原文, 一字未改 —— 它们能全绿本身就是"打分模块确实
# 还原到那一版"的最强证据。下面这几条盯的是**别处**: 那六次改动往打分里塞过
# 的东西, 有没有从别的门缝里溜回来。
#
# 为什么盯接口而不盯数值: 数值测试在有人把因子加回来、而曲线恰好中性时照样
# 通过; 接口一旦回来, 这几条立刻红。


def test_打分模块与_R134_那一版逐字节相同():
    """这条是整次回退的总闸。

    用户: 「完整回退到上一个版本的评分系统」。追溯下来那一版是 R134
    (`973b148`, 2026-09-01), 之后整整七天没人动过, 直到 R189 开始连改六次。
    「完整」两个字的验收标准只有一个: **文件和当时那一份一模一样。**
    """
    import pathlib
    import subprocess
    src = pathlib.Path(osc.__file__)
    repo = src.parents[3]           # backend/app/services/x.py → 仓库根
    got = subprocess.run(
        ["git", "-C", str(repo), "show", "973b148:backend/app/services/opportunity_score.py"],
        capture_output=True, text=True)
    if got.returncode != 0:
        import pytest as _pytest
        _pytest.skip("拿不到 973b148(浅克隆), 这条只在完整仓库里有意义")
    assert src.read_text(encoding="utf-8") == got.stdout, (
        "opportunity_score.py 与 R134 那一份不再相同 —— 要么是有意改口径"
        "(那就更新这条测试并升 SCORING_VERSION), 要么是有人又往里加东西了")


def test_两轴与置信系数没有溜回来():
    """R189 的两轴、R201 的置信系数都是"这两天"的产物, 回退后不该还在。"""
    assert not hasattr(osc, "AXIS_QUALITY") and not hasattr(osc, "AXIS_TIMING")
    assert not hasattr(osc, "QUALITY_WEIGHTS") and not hasattr(osc, "TIMING_WEIGHTS")
    assert not hasattr(osc, "confidence")
    assert "confidence" not in osc.score_candidate(
        duration=1, state="UT", rs_pct=6.0, vol_ratio=1.6,
        turnover_rate=5.0, channel_pct=0.56)


def test_六次改动塞进来的因子一个都不在():
    """趋势模板(R189) / 红绿节拍(R189) / 三线间距·加速度(R195) /
    压缩天数(R197) / 路 C 的中性新鲜度(R201) —— 全部不该出现在打分里。

    它们**没有从系统里消失**, 只是降成了注记(界面照样显示, 一分不加一分不减)。
    这条盯的是"不进分"这件事。
    """
    import inspect
    params = set(inspect.signature(osc.score_candidate).parameters)
    for name in ("template", "rhythm", "geo", "runs", "coiling"):
        assert name not in params, f"`{name}` 又回到打分入口了"
    for name in ("template_score", "base_score", "spread_score", "accel_score",
                 "TEMPLATE_CURVE", "SPREAD_CURVE", "ACCEL_CURVE",
                 "RHYTHM_SCORE", "FRESH_COILING"):
        assert not hasattr(osc, name), f"`{name}` 又回到打分模块里了"
    assert set(osc.FACTOR_CN) == {"fresh", "state", "rs", "vol_ratio",
                                  "turnover", "pos"}, "因子只该有 R134 那六个"


def test_台账版本跟着回到二():
    """打分代码逐字节还原, 那算出来的就是同一个数, 该和 09-01~09-08 那七天的
    记录归在同一把尺子下 —— 换个新版本号等于白扔掉那七天的真实样本。"""
    from app.services import score_ledger as sl
    assert sl.SCORING_VERSION == 2
    assert set(sl.FACTOR_LABELS) == {"trend", "volume", "position"}


def test_候选路只剩最初那两条():
    """路 C(通道酝酿)是 R201 跟着通道延申一起加的, 判据就是 `phase()`,
    随这次回退一起撤掉。路 A / 路 B 是 2026-08-14 今日总览第一版就有的。"""
    from app.api import today
    assert not hasattr(today, "coiling_phase")
    assert not hasattr(today, "coiling_candidates")
    assert not hasattr(today, "_COILING_PHASES")
