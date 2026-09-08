"""[fork R134/R189] 买入机会评分: 四道门槛 + 质地 × 时机两轴。

这组测试守的是这套分数之所以存在的那几条 —— 一旦回退就变回 v1:
  1. 分数不再饱和(v1 理论上限 151 夹到 100, 榜首一片并列);
  2. 因子是**区间最优**不是单调递增(量比 5.0 必须低于 1.6, 位置贴上轨必须低于刚站上生命线);
  3. 门槛是硬的(逆势/破生命线/长期下跌/反复失败直接出局), 但**数据缺失一律放行**;
  4. [R189] 两轴用**几何平均**合成 —— 一边好一边差, 不许平均成"中等"。
"""
from __future__ import annotations

import pytest

from app.services import opportunity_score as osc


# 八条全过 + 蓄势磨了三个月 + 通道几何 —— 两轴的因子都喂满, _s() 才算"全覆盖"
_TPL_FULL = {"passed": 8, "known": 8, "total": 8}
_RHY_FULL = {"level": "building", "basing": {"days": 90}}
# [R195] 趋势已确立(短长分离 2.4 个 ATR)且适度加速 —— 两个新因子都在甜区
_GEO_FULL = {"spread": 2.4, "accel": {"a1": 0.10}}


def _bands_with_geo() -> dict:
    """走 score_opportunities 那条路时, extras["bands"] 里要有 geo。
    造真的上下轨让 keltner_geometry 自己反推, 不手拼 geo —— 手拼的话测的是
    假输入, 反推那条恒等式就没被覆盖到。"""
    from app.indicators import keltner as _k
    from app.indicators import keltner_geometry as _kg
    close, atr = 10.0, 0.5
    ma = {"s": 9.8, "m": 9.4, "l": 8.6}      # 多头排列, 短长相隔 2.4 个 ATR
    b = {key: _k.assess(close=close, ma=ma[key], atr=atr, n=_kg.K[key])
         for key in ("s", "m", "l")}
    geo = _kg.geometry(b, close)
    assert geo, "造的上下轨推不出几何, 测试前提就错了"
    return dict(b, geo=geo)


def _s(**kw):
    base = dict(duration=1, state="UT", rs_pct=6.0, vol_ratio=1.6,
                turnover_rate=5.0, channel_pct=0.56,
                template=_TPL_FULL, rhythm=_RHY_FULL, geo=_GEO_FULL)
    base.update(kw)
    return osc.score_candidate(**base)


# ------------------------------------------------------- 门槛


def _gate(**kw):
    base = dict(state="UT", above_ma20=True, above_ma20_prev=True,
                close=12.0, ma120=10.0, ma120_rising=True)
    base.update(kw)
    return osc.check_gates(**base)


# ---- [R189] G4 红绿节拍 ----


def test_repeatedly_failing_rhythm_is_vetoed():
    """「同一个位置撞五次没过去」是唯一一种次数越多越该躲的形态 ——
    靠打分压不住(次数正是它最多), 只能否决。"""
    assert osc.GATE_RHYTHM in _gate(rhythm_level="failing")["failed"]


@pytest.mark.parametrize("level", [None, "none", "choppy", "building"])
def test_only_failing_is_vetoed_never_the_others(level):
    """**没有"必须蓄势"门槛**: 一路上涨从没磨过底的强势股压根没有循环,
    不该被挡在外面。蓄势是加分项, 不是准入条件。"""
    assert _gate(rhythm_level=level) == {"ok": True, "failed": []}


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
    # [R195] 已经走完的那只同时是在减速的 —— 量比 5.0、贴上轨、跑赢 45 个点的票
    # 十有八九处在拉升末端。原来两只共用同一份几何, 新因子对二者一样, 白白
    # 稀释了差距; 让它带上自己的加速度才是这个例子该有的样子。
    ran = _s(duration=1, vol_ratio=5.0, channel_pct=1.05, rs_pct=45.0,
             geo={"spread": 5.5, "accel": {"a1": -0.22}})["score"]
    # [R189] 门限由 30 降到 25: 两只票的**质地一样**(同一份模板与节拍), 差别
    # 全在时机轴上, 而几何平均对单轴摆幅的响应是开方的 —— 这是它换来"不许
    # 互相补贴"的代价, 不是区分度丢了。25 分仍然是隔着好几个名次的距离。
    assert fresh - ran >= 25, f"区分度不足: {fresh} vs {ran}"


def test_score_stays_in_range_across_extremes():
    for d in (1, 3, 20):
        for vr in (0.1, 1.6, 12.0):
            for cp in (-0.2, 0.55, 1.8):
                s = _s(duration=d, vol_ratio=vr, channel_pct=cp)["score"]
                assert 0 <= s <= 100


def test_no_clamp_is_needed():
    """满分只能靠两根轴的每个因子都到峰值拿到, 不是靠加项堆出来后被夹平。"""
    best = osc.score_candidate(duration=1, state="UT", rs_pct=14.0, vol_ratio=1.8,
                               turnover_rate=5.0, channel_pct=0.58,
                               template=_TPL_FULL, rhythm=_RHY_FULL,
                               geo={"spread": 2.5, "accel": {"a1": 0.12}})
    assert best["score"] == 100
    assert all(v is not None and v >= 99 for v in best["axes"].values())


# ------------------------------------------------------- 缺数据的处理


def test_missing_factor_renormalizes_inside_the_axis():
    """缺换手率不该按 0 分算 —— 那是因为"我们没读到"去惩罚这只票。"""
    with_turn = _s(turnover_rate=5.0)
    without = _s(turnover_rate=None)
    # 别的时机因子都在峰值, 所以去掉换手率后时机轴该仍然很高, 而不是掉一截
    assert without["axes"]["timing"] > 90
    assert without["coverage"]["timing"] == round(1 - osc.TIMING_WEIGHTS["turnover"], 2)
    assert with_turn["coverage"]["timing"] == 1.0


def test_whole_axis_missing_falls_back_to_the_other_one():
    """整根轴取不到时退回另一根 —— 不能把"没读到质地"当成"质地 0",
    那会让缺数据的票直接从榜上消失。"""
    r = osc.score_candidate(duration=1, state=None, rs_pct=None, vol_ratio=1.6,
                            turnover_rate=5.0, channel_pct=0.56, geo=None)
    assert r["axes"]["quality"] is None
    assert r["partial"] is True          # 界面必须说清楚这一档没算进去
    # [R201] 分数仍由活着的那根轴给出, 只是按覆盖率打了个折(见 confidence())。
    # 关键是它**没有变成 0** —— 那才叫"缺数据的票凭空消失"。
    assert r["score"] > 0
    assert r["score"] == round(r["axes"]["timing"] * r["confidence"])
    assert 0.8 < r["confidence"] < 1.0, "整根轴缺席只该温和打折, 不该腰斩"


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
    assert sum(osc.QUALITY_WEIGHTS.values()) == pytest.approx(1.0)
    assert sum(osc.TIMING_WEIGHTS.values()) == pytest.approx(1.0)


# ------------------------------------------------------- [R189] 两根轴
#
# 这一组守的是本次重构的**全部理由**。没有它们, 两轴退回加权平均就是一次
# 无声的回归 —— 分数还在 0~100, 排序看着也正常, 只是"好票遇上坏时点"重新
# 变得看不见了。


def test_the_two_axes_move_independently():
    """质地慢变、时机快变 —— 只改信号第几天, 质地必须一动不动。"""
    day1 = _s(duration=1)
    day9 = _s(duration=9)
    assert day1["axes"]["quality"] == day9["axes"]["quality"]
    assert day9["axes"]["timing"] < day1["axes"]["timing"]


def test_geometric_mean_refuses_to_average_a_lopsided_pair():
    """好票+坏时点 不该和 平庸票+平庸时点 打平 —— 那正是三维度加权的毛病。"""
    lopsided = osc.score_candidate(
        duration=12, state="UT", rs_pct=14.0, vol_ratio=4.5, turnover_rate=22.0,
        channel_pct=1.15, template=_TPL_FULL, rhythm=_RHY_FULL,
        geo={"spread": 2.4, "accel": {"a1": -0.18}})
    q, t = lopsided["axes"]["quality"], lopsided["axes"]["timing"]
    assert q > 90 and t < 40, f"造的例子不对: 质地 {q} 时机 {t}"
    # 算术平均会给 (95+35)/2 ≈ 65; 几何平均给 √(95×35) ≈ 58 —— 必须更低
    assert lopsided["score"] < (q + t) / 2 - 4


def test_one_axis_near_zero_kills_the_score():
    """任一边趋近 0, 合成分也趋近 0 —— 不许互相补贴。"""
    r = osc.score_candidate(duration=20, state="UT", rs_pct=14.0, vol_ratio=0.1,
                            turnover_rate=0.1, channel_pct=1.8,
                            template=_TPL_FULL, rhythm=_RHY_FULL,
                            geo={"spread": 2.4, "accel": {"a1": -0.28}})
    assert r["axes"]["quality"] > 90
    assert r["score"] < 40, f"时机烂到底了还有 {r['score']} 分"


def test_score_is_the_geometric_mean_exactly():
    r = _s()
    q, t = r["axes"]["quality"], r["axes"]["timing"]
    assert r["score"] == round((q * t) ** 0.5), "合成公式被改成别的了"


# ------------------------------------------------------- [R189] 质地的两个新因子


def test_building_beats_choppy_but_does_not_run_the_show():
    """「蓄势该加多少分」的答案就在这两条断言之间:
    够让同档次的票分出先后(> 2 分), 不够让它一个人把票抬进前排(< 12 分)。"""
    building = _s(rhythm={"level": "building", "basing": {"days": 90}})["score"]
    choppy = _s(rhythm={"level": "choppy", "basing": {"days": 90}})["score"]
    assert 2 <= building - choppy <= 12, f"蓄势的边际是 {building - choppy} 分"


def test_never_having_based_is_not_a_penalty():
    """一路上涨从没跌出过多头的强势股 cycles=0、磨底 0 天 —— 给它低分等于
    惩罚"没磨过底", 方向就反了。"""
    never = _s(rhythm={"level": "none", "basing": {"days": 0}})["score"]
    choppy = _s(rhythm={"level": "choppy", "basing": {"days": 90}})["score"]
    assert never >= choppy - 1


def test_template_needs_all_eight_known_or_it_sits_out():
    """次新股 3 条全过缩放成满分 = 凭空造出来的质地。判不全就缺席。"""
    partial_tpl = _s(template={"passed": 3, "known": 3, "total": 8})
    assert partial_tpl["factors"]["template"] is None
    assert partial_tpl["partial"] is True


def test_template_curve_is_convex_at_the_top():
    """8/8 与 7/8 的差要比 4/8 与 3/8 的大 —— 模板的意义在"全部满足"。"""
    top = osc.template_score({"passed": 8, "known": 8}) - osc.template_score({"passed": 7, "known": 8})
    mid = osc.template_score({"passed": 4, "known": 8}) - osc.template_score({"passed": 3, "known": 8})
    assert top > mid


def test_more_template_criteria_never_scores_lower():
    scores = [osc.template_score({"passed": n, "known": 8}) for n in range(9)]
    assert scores == sorted(scores)


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


def test_ties_break_on_quality_not_on_alphabet():
    """同分时按代码字典序是个无意义的顺序, 而用户会照着名次从上往下看。

    [R189] 第二级兜底由「趋势强度」改成「质地」: 把握分是质地×时机的几何平均,
    乘积打平时该先看质地好的那只 —— 时机会重来, 质地不会。
    """
    from app.api.today import score_opportunities
    base_t = {"state": "UT", "state_cn": "上涨趋势", "side": "多头", "duration": 2,
              "close": 10.0, "as_of": "2026-08-31", "signal": "转多",
              "signal_desc": "突破", "ret_20d": 0.08}
    closes = [10.0 * (1.004 ** i) for i in range(290)]
    gate = {"above_ma20": True, "above_ma20_prev": True, "close": 10.0,
            "ma120": 8.0, "ma120_rising": True, "closes": closes, "ret_120d": 0.30}
    ex = {"gate": gate, "channel_pct": 0.6, "vol_ratio": 1.6, "turnover": 4.0}
    # 两只时机完全一样, 只有磨底长短不同 —— 分数四舍五入后打平, 质地不同。
    # 代码字典序上 A 在前, 但 Z 磨得更久(质地更高), 必须排在 A 前面。
    trends = {
        "AAA.SH": dict(base_t, rhythm={"level": "building", "basing": {"days": 72}}),
        "ZZZ.SH": dict(base_t, rhythm={"level": "building", "basing": {"days": 90}}),
    }
    ranked, _ = score_opportunities(
        trends, {}, {"AAA.SH": "甲", "ZZZ.SH": "乙"}, bench_ret=0.02,
        extras={"AAA.SH": ex, "ZZZ.SH": ex}, bench_ret_120d=0.05)
    m = {o["symbol"]: o for o in ranked}
    assert m["AAA.SH"]["score"] == m["ZZZ.SH"]["score"], "造的例子没打平, 这条兜底测不到"
    assert m["ZZZ.SH"]["axes"]["quality"] > m["AAA.SH"]["axes"]["quality"]
    assert [o["symbol"] for o in ranked] == ["ZZZ.SH", "AAA.SH"]


def test_incomplete_candidates_are_flagged_and_lose_ties():
    """缺因子的那只必须被标出来 —— 界面据此说"这一档没算进去"。"""
    from app.api.today import score_opportunities
    base_t = {"state": "UT", "state_cn": "上涨趋势", "side": "多头", "duration": 2,
              "close": 10.0, "as_of": "2026-08-31", "signal": "转多",
              "signal_desc": "突破", "ret_20d": 0.08,
              "rhythm": {"level": "building", "basing": {"days": 90}}}
    closes = [10.0 * (1.004 ** i) for i in range(290)]
    gate = {"above_ma20": True, "above_ma20_prev": True, "close": 10.0,
            "ma120": 8.0, "ma120_rising": True, "closes": closes, "ret_120d": 0.30}
    # [R195] 通道读数(含几何层)也要喂, 否则两只都会因为缺 spread/accel 而 partial
    bands = _bands_with_geo()
    ranked, _ = score_opportunities(
        trends := {"AAA.SH": dict(base_t), "ZZZ.SH": dict(base_t)}, {},
        {"AAA.SH": "甲", "ZZZ.SH": "乙"}, bench_ret=0.02, extras={
            # A 缺量能那两个因子; Z 全齐
            "AAA.SH": {"gate": gate, "channel_pct": 0.6, "bands": bands},
            "ZZZ.SH": {"gate": gate, "channel_pct": 0.6, "vol_ratio": 1.6,
                       "turnover": 4.0, "bands": bands},
        }, bench_ret_120d=0.05)
    assert trends  # 只是让 walrus 的意图明显: 两只用的是同一份趋势
    m = {o["symbol"]: o for o in ranked}
    assert m["AAA.SH"]["partial"] is True
    assert m["ZZZ.SH"]["partial"] is False
    # 真打平时数据齐全的在前(不打平就各按分数走, 那是对的)
    if m["AAA.SH"]["score"] == m["ZZZ.SH"]["score"]:
        assert [o["symbol"] for o in ranked][0] == "ZZZ.SH"


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


# ================================================================
# [R201] 置信系数 —— 「缺数据不该反而排在前面」
#
# 这一组守的是一个**实测出来的**缺陷, 不是假想: v2 里同样条件下, 只有
# state+fresh 两个因子的票拿 100 分排第 1, 而十个因子全齐的同类票只有 82。
# `partial` 那个标记只在同分时参与排序, 挡不住这件事。


def _sparse():
    """只有六态和新鲜度 —— 别的一概读不到。"""
    return osc.score_candidate(duration=1, state="UT", rs_pct=None, vol_ratio=None,
                               turnover_rate=None, channel_pct=None,
                               template=None, rhythm=None, geo=None, runs=None)


def test_数据稀薄的票不再排在因子齐全的同类票前面():
    sparse = _sparse()
    full = osc.score_candidate(duration=1, state="UT", rs_pct=4.0, vol_ratio=1.5,
                               turnover_rate=3.0, channel_pct=0.60,
                               template={"passed": 6, "known": 8, "total": 8},
                               rhythm={"level": "none", "basing": {"days": 10}},
                               geo={"spread": 1.5, "accel": {"a1": 0.05}},
                               runs={"compress_days": 8})
    # 稀薄那只两根轴都是满分(因为只剩两个满分因子), 齐全那只反而不是
    assert sparse["axes"]["quality"] == 100.0 and sparse["axes"]["timing"] == 100.0
    assert full["axes"]["quality"] < 100.0
    # 可它就是不该排在前面 —— v2 里 100 vs 82, 现在必须反过来
    assert sparse["score"] < full["score"], (
        f"稀薄 {sparse['score']} 仍然压过齐全 {full['score']}")


def test_两轴齐全时置信系数恰好是一不引入任何偏移():
    r = _s()
    assert r["coverage"] == {"quality": 1.0, "timing": 1.0}
    assert r["confidence"] == 1.0
    assert r["score"] == round((r["axes"]["quality"] * r["axes"]["timing"]) ** 0.5)


def test_缺一个因子只是温和打折不是惩罚():
    """「不因为我们没读到就惩罚这只票」那条纪律必须还在 —— 缺一个因子
    掉的分要小到无感, 只有缺掉大半时才该显著掉队。"""
    one_missing = osc.confidence(1.0, 1 - osc.TIMING_WEIGHTS["turnover"])
    assert one_missing > 0.97, f"缺一个因子就扣 {(1-one_missing)*100:.0f}% —— 太狠"
    almost_nothing = osc.confidence(0.1275, 0.2635)
    assert almost_nothing < 0.5, "只剩两个因子还几乎不打折, 那就没修到"


def test_置信系数单调不减且封顶在一():
    prev = -1.0
    for c in (0.05, 0.2, 0.4, 0.6, 0.8, 0.95, 1.0):
        got = osc.confidence(c, c)
        assert got >= prev, "覆盖率更高反而置信更低, 方向反了"
        assert 0.0 <= got <= 1.0
        prev = got
    assert osc.confidence(1.0, 1.0) == 1.0
    assert osc.confidence(0.0, 0.0) == 0.0


def test_整根轴缺席时只按活着的那根算():
    """否则"质地整根读不到"的票会被乘成 0 分凭空消失 —— 那是另一个方向的错。"""
    only_timing = osc.confidence(0.0, 1.0)
    assert only_timing == 1.0, "活着那根是满的, 就不该因为另一根缺席而打折"


def test_满分仍然拿得到():
    """置信系数不能把天花板压下来 —— 因子都到峰值且都读到了就是 100。"""
    best = osc.score_candidate(duration=1, state="UT", rs_pct=14.0, vol_ratio=1.8,
                               turnover_rate=5.0, channel_pct=0.58,
                               template=_TPL_FULL, rhythm=_RHY_FULL,
                               geo={"spread": 2.5, "accel": {"a1": 0.12}})
    assert best["confidence"] == 1.0 and best["score"] == 100


# ---------------------------------------------- [R201] 候选路 C 的新鲜度


def test_憋着劲那一路拿到的是中性新鲜度而不是高分():
    """路 C 比"逼近触发价"更早一步: 那边价格已经贴到买点了, 这边连方向都
    还没出来。所以它只该拿中性那一档, 不能靠"我最早"排到前面去。"""
    r = osc.score_candidate(duration=None, state="UT", rs_pct=6.0, vol_ratio=1.6,
                            turnover_rate=5.0, channel_pct=0.56, coiling=True)
    assert r["factors"]["fresh"] == osc.FRESH_COILING
    assert r["fresh_from"] == "coiling"
    assert osc.FRESH_COILING < osc.FRESH_NEAR_BREAKOUT < 100


def test_有信号时信号的新鲜度优先于憋着劲():
    """两条路都成立时该按信号算 —— 信号是更确定的那个。"""
    r = osc.score_candidate(duration=1, state="UT", rs_pct=6.0, vol_ratio=1.6,
                            turnover_rate=5.0, channel_pct=0.56, coiling=True)
    assert r["fresh_from"] == "signal" and r["factors"]["fresh"] == 100


# ---------------------------------------------- [R201] 中性锚点


def test_所有无信息的取值都锚在中性五十():
    """v2 里"没读到/没发生"的默认值散在 55~60, 于是每只票的底子都被垫高了
    一截, 合成分整体上移、区分度更窄。统一锚到 50: 无信息就是无信息。"""
    assert osc._piecewise(0.0, osc.RS_CURVE) == 50            # 与大盘同步
    assert osc._piecewise(0.0, osc.ACCEL_CURVE) == 50         # 速度没变
    assert osc._piecewise(0.5, osc.SPREAD_CURVE) == 50        # 方向还没出来
    assert osc.RHYTHM_SCORE["none"] == 50                     # 没有循环
    assert osc.BASING_DAYS_NEUTRAL == 50
    assert osc._piecewise(0.0, osc.BASING_DAYS_CURVE) == 50
    # 震荡是**负面信息**, 必须低于"无信息"; 蓄势必须高于
    assert osc.RHYTHM_SCORE["choppy"] < 50 < osc.RHYTHM_SCORE["building"]
