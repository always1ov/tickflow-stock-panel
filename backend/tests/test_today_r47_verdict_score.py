"""[fork 增强] R47 「值得关注」的把握分结合 Keltner 三档结论。

R43 那版只看 pressure 的 side/level, 有两个洞:

  1. 它要求**短期档到轨**才有读数, 于是「候选池」那一档(短期还在中部、
     中期已到下沿)整个看不见 —— 而那恰恰是低吸候选最典型的样子。
  2. 它只分"上沿/下沿"乘"强/弱"四格, 分不出"强势深调"和"下跌途中"。
     两者短中期读数一模一样, 长期档一翻含义完全相反: 一个是这套里最好的
     买点, 一个是越抄越套。给同一个分是把最好的和最坏的混在一起。

所以打分改挂 verdict 的 code。下面的测试守三件事: 十条结论各自的方向、
矛盾组合必须分得开、以及打分发生在**两个候选来源合并之后**(趋势转强与
逼近突破都要按各自的通道位置加减, 不能只有前者算)。
"""
from __future__ import annotations

import pytest

from app.api.today import _VERDICT_SCORE, rank_opportunities
from app.indicators import keltner as k


def _bands(s, m=None, l=None):  # noqa: E741
    out = {"s": {"pos": s, "pos_cn": k.POS_CN[s]}}
    if m:
        out["m"] = {"pos": m, "pos_cn": k.POS_CN[m]}
    if l:
        out["l"] = {"pos": l, "pos_cn": k.POS_CN[l]}
    return out


def _rank(verdict):
    trends = {"600000.SH": {"signal": "转多", "signal_desc": "刚转强", "duration": 1,
                            "state": "UT", "close": 10.0}}
    extras = {"600000.SH": {"verdict": verdict}} if verdict else None
    shown, _ = rank_opportunities(trends, {}, {"600000.SH": "测试"},
                                  min_score=0, max_show=5, extras=extras)
    return shown[0]


def _score(bands):
    return _rank(k.verdict(_bands(*bands)))["score"]


# ---------- 打分表本身 ----------

def test_every_verdict_code_has_a_score():
    """漏一条就会静默按 0 处理 —— 那只票的通道位置等于白算了。"""
    assert set(_VERDICT_SCORE) == set(k._VERDICTS), "结论码与打分表必须一一对应"
    for code, (delta, reason) in _VERDICT_SCORE.items():
        assert isinstance(delta, int) and delta != 0, f"{code} 要么加要么减, 不该是 0"
        assert reason, f"{code} 要说清为什么 —— 把握分的每一项都要写进理由里"


def test_buy_side_verdicts_add_and_high_side_subtract():
    """方向不能反: 到下沿是这个策略要找的位置, 到上沿是追高。"""
    for code in ("dip_in_uptrend", "bottom_confirmed", "low_short_only", "watch_low"):
        assert _VERDICT_SCORE[code][0] > 0, code
    for code in ("watch_high", "high_short_only", "top_confirmed", "top_all_bands"):
        assert _VERDICT_SCORE[code][0] < 0, code


def test_the_two_traps_are_penalised_as_hard_as_a_big_top():
    """"超跌反弹"和"下跌途中"都是出了买信号但位置不该买 —— 信号越像越危险,
    扣分不能比大顶轻。"""
    worst = _VERDICT_SCORE["top_all_bands"][0]
    assert _VERDICT_SCORE["bounce_in_downtrend"][0] <= worst
    assert _VERDICT_SCORE["falling_all_bands"][0] <= worst


def test_channel_position_never_outweighs_price_and_volume():
    """幅度对齐既有因子(量比 ±12、胜率 ±12、相对强度 -15) —— 通道位置是
    一项参考, 让它单独决定排名就本末倒置了。"""
    assert max(abs(d) for d, _ in _VERDICT_SCORE.values()) <= 15


# ---------- 进把握分 ----------

def test_no_verdict_leaves_the_score_untouched():
    """三档都在中部时确实没信息 —— 没信息不等于坏消息, 不该扣分。
    (与"不在主线内不扣分"同一条原则。)"""
    assert k.verdict(_bands(k.POS_INSIDE, k.POS_INSIDE, k.POS_INSIDE)) is None
    assert _score((k.POS_INSIDE, k.POS_INSIDE, k.POS_INSIDE)) == _rank(None)["score"]


@pytest.mark.parametrize("bands,code", [
    ((k.POS_BELOW, k.POS_INSIDE, k.POS_ABOVE), "dip_in_uptrend"),
    ((k.POS_BELOW, k.POS_BELOW, k.POS_INSIDE), "bottom_confirmed"),
    ((k.POS_NEAR_LOWER, k.POS_INSIDE, k.POS_INSIDE), "low_short_only"),
    ((k.POS_INSIDE, k.POS_BELOW, None), "watch_low"),
    ((k.POS_INSIDE, k.POS_NEAR_UPPER, None), "watch_high"),
    ((k.POS_ABOVE, k.POS_INSIDE, k.POS_INSIDE), "high_short_only"),
    ((k.POS_ABOVE, k.POS_NEAR_UPPER, k.POS_INSIDE), "top_confirmed"),
    ((k.POS_ABOVE, k.POS_ABOVE, k.POS_ABOVE), "top_all_bands"),
    ((k.POS_ABOVE, k.POS_INSIDE, k.POS_BELOW), "bounce_in_downtrend"),
    ((k.POS_BELOW, k.POS_BELOW, k.POS_BELOW), "falling_all_bands"),
])
def test_each_verdict_moves_the_score_by_its_own_delta(bands, code):
    """十条都要真的落到分上 —— 打分表写了但没接进去是最容易发生的事。"""
    base = _rank(None)["score"]
    o = _rank(k.verdict(_bands(*bands)))
    assert o["score"] == base + _VERDICT_SCORE[code][0]
    assert _VERDICT_SCORE[code][1] in o["why"], "扣了分就要在理由里说清为什么"


def test_the_verdict_title_leads_the_reason():
    """理由里先给结论名, 再给解释 —— 用户扫一眼就知道是哪一档。"""
    o = _rank(k.verdict(_bands(k.POS_BELOW, k.POS_INSIDE, k.POS_ABOVE)))
    assert "强势深调:" in o["why"]


def test_penalties_read_as_a_caveat_not_an_endorsement():
    """减分项前面带"但" —— 不然一句"到位了"跟在利好后面像是在夸它。"""
    o = _rank(k.verdict(_bands(k.POS_ABOVE, k.POS_ABOVE, k.POS_ABOVE)))
    assert "但大顶区域:" in o["why"]


def test_best_dip_outranks_the_trap_that_looks_just_like_it():
    """短中期读数一样、只有长期档相反 —— 这两条必须差得足够远, 否则
    "强势深调"和"下跌途中"会挨在一起出现在同一屏。"""
    good = _score((k.POS_BELOW, k.POS_BELOW, k.POS_ABOVE))   # dip_in_uptrend
    bad = _score((k.POS_BELOW, k.POS_BELOW, k.POS_BELOW))    # falling_all_bands
    assert good - bad == 25


def test_the_watch_pool_can_reach_the_opportunity_list():
    """R43 那版够不到这一档(pressure 要求短期到轨), 低吸候选整批看不见。"""
    assert _score((k.POS_INSIDE, k.POS_BELOW)) > _rank(None)["score"]


# ---------- 字段落到 payload ----------

def test_candidates_always_carry_the_verdict_key():
    assert _rank(None)["verdict"] is None, "字段要在, 值为 None —— 前端不必判断键存不存在"
    v = k.verdict(_bands(k.POS_BELOW))
    assert _rank(v)["verdict"] == v, "界面显示的和打分用的必须是同一份"


def _rank_near_breakout(verdict):
    """「逼近突破」那一路的候选来自 AI 信号, 完全不经过趋势判定。"""
    signals = {"600000.SH": {"signal": "buy", "confidence": 60, "close": 10.0,
                             "watch_points": [{"direction": "up", "price": 10.1,
                                               "action": "买入"}]}}
    extras = {"600000.SH": {"verdict": verdict}} if verdict else None
    shown, _ = rank_opportunities({}, signals, {"600000.SH": "测试"},
                                  min_score=0, max_show=5, extras=extras)
    return shown[0]


def test_ai_breakout_candidates_are_scored_by_the_channel_too():
    """打分挂在两个来源合并之后。只挂趋势那一路的话, 一只在大顶区域的 AI 候选
    照样满分排在最前, 而它的结论标就在旁边写着"不该开新仓" —— 标签与排序自相矛盾。
    (R37 的主线加成为同一个理由挪到了合并之后。)"""
    base = _rank_near_breakout(None)
    assert base["kind"] == "near_breakout", "这一路确实不经过趋势判定"
    top = _rank_near_breakout(k.verdict(_bands(k.POS_ABOVE, k.POS_ABOVE, k.POS_ABOVE)))
    assert top["score"] == base["score"] + _VERDICT_SCORE["top_all_bands"][0]
    assert "大顶区域" in top["why"]


def test_score_stays_within_bounds_after_the_channel_adjustment():
    """夹到 [0,100] 要在所有加减之后 —— 先夹再减会让 99 分和 100 分的票
    扣完变成同一分。"""
    for bands in ((k.POS_ABOVE, k.POS_ABOVE, k.POS_ABOVE),
                  (k.POS_BELOW, k.POS_INSIDE, k.POS_ABOVE)):
        assert 0 <= _score(bands) <= 100
