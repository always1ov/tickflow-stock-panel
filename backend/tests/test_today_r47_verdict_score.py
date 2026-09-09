"""[fork R47 → R134] Keltner 通道与机会区的关系。

**R134 起这条关系变了, 这个文件因此整体重写。**

R47 时通道的十档文字结论直接加减把握分(+10 ~ -15)。v2 把它换掉了, 换成
**通道位置这个连续量**(``pct_in_channel``, 0=贴下轨 1=贴上轨)直接进"时机"轴
那一维。理由:

  · 十档文字是把连续量先切成几档再打分, 中间白丢了分辨率 —— 0.52 和 0.74
    在文字上都是"通道内", 但一个是刚站上生命线、一个是空间走掉一半;
  · 结论表和分数容易各说各话 —— v1 出现过"结论标写着不该开新仓, 分数照样满分"
    的情况(那正是 R47 想修但没修彻底的问题)。

所以现在: **通道结论只作注记(不加不减), 通道位置进评分。**

另有一条由此产生的**重要后果**要守住: Keltner 短期带以 MA20 为中轴, 所以
``pct ≥ 0.5 ⟺ 收盘 ≥ MA20``。生命线门槛因此会把所有"贴下轨的低吸候选"整个挡在
门外 —— v2 只做站上生命线之后的趋势中继, **不做低吸**。这是用户"跌破生命线的
不看"的直接推论, 必须有测试钉住, 免得日后有人"顺手放宽一点"。
"""
from __future__ import annotations

import pytest

from app.api.today import rank_opportunities, score_opportunities
from app.services import opportunity_score as osc


NAMES = {"600000.SH": "测试"}


def _trend(**kw):
    base = {"state": "UT", "state_cn": "上涨趋势", "side": "多头", "duration": 1,
            "close": 10.0, "as_of": "2026-08-20", "signal": "转多",
            "signal_desc": "突破上关键点 10", "ret_20d": 0.08}
    base.update(kw)
    return base


def _gate_ok(**kw):
    base = {"above_ma20": True, "above_ma20_prev": True, "close": 10.0,
            "ma120": 8.0, "ma120_rising": True}
    base.update(kw)
    return base


def _one(extras, trends=None):
    ranked, gates = score_opportunities(trends or {"600000.SH": _trend()}, {}, NAMES,
                                        bench_ret=0.02, extras=extras)
    return (ranked[0] if ranked else None), gates


# ------------------------------------------------------- 通道位置进评分


@pytest.mark.parametrize("pct,tag", [(0.55, "刚站上生命线"), (0.75, "走掉一半"),
                                     (1.05, "破上轨")])
def test_channel_position_drives_the_position_dim(pct, tag):
    o, _ = _one({"600000.SH": {"gate": _gate_ok(), "channel_pct": pct}})
    # [R230] 两轴退回三维度: 通道位置现在独占「位置成本」这一档
    assert o["dims"]["position"] is not None, tag
    assert o["channel_pct"] == pytest.approx(pct)


def test_cheaper_position_outranks_the_expensive_one():
    """刚站上生命线 > 已经贴上轨。贴上轨是追高, 不是苗头。"""
    cheap, _ = _one({"600000.SH": {"gate": _gate_ok(), "channel_pct": 0.55}})
    dear, _ = _one({"600000.SH": {"gate": _gate_ok(), "channel_pct": 1.05}})
    assert cheap["score"] > dear["score"]


def test_position_is_continuous_not_bucketed():
    """0.52 与 0.74 在十档文字里都叫"通道内", 分数必须能分开它们。"""
    a, _ = _one({"600000.SH": {"gate": _gate_ok(), "channel_pct": 0.52}})
    b, _ = _one({"600000.SH": {"gate": _gate_ok(), "channel_pct": 0.74}})
    assert a["score"] != b["score"]


# ------------------------------------------------------- 通道结论只作注记


# 直接取实现里的那张表 —— 抄一份副本, 日后加一档结论测试就悄悄漏掉它
from app.api.today import _NOTE_VERDICT_TONE

VERDICT_CODES = sorted(_NOTE_VERDICT_TONE)


@pytest.mark.parametrize("code", VERDICT_CODES)
def test_verdict_never_moves_the_score(code):
    """十档结论一分不加一分不减 —— 位置那一维已经由通道位置本身负责了。"""
    base, _ = _one({"600000.SH": {"gate": _gate_ok(), "channel_pct": 0.6}})
    with_v, _ = _one({"600000.SH": {
        "gate": _gate_ok(), "channel_pct": 0.6,
        "verdict": {"code": code, "title": "某结论", "detail": "某说明"}}})
    assert with_v["score"] == base["score"], f"{code} 不该动分数"


@pytest.mark.parametrize("code", VERDICT_CODES)
def test_verdict_shows_up_as_an_annotation(code):
    o, _ = _one({"600000.SH": {
        "gate": _gate_ok(), "channel_pct": 0.6,
        "verdict": {"code": code, "title": "某结论", "detail": "某说明"}}})
    notes = {n["key"]: n for n in o["notes"]}
    assert "verdict" in notes and notes["verdict"]["label"] == "某结论"
    assert o["verdict"]["code"] == code


def test_bearish_verdicts_are_toned_bad_and_bullish_ones_good():
    """注记要带方向 —— 界面靠 tone 上色, 全是灰的等于没说。"""
    def tone(code):
        o, _ = _one({"600000.SH": {"gate": _gate_ok(), "channel_pct": 0.6,
                                   "verdict": {"code": code, "title": "T"}}})
        return {n["key"]: n["tone"] for n in o["notes"]}["verdict"]
    assert tone("top_all_bands") == "bad"
    assert tone("dip_in_uptrend") == "good"


def test_why_never_mixes_annotations_into_the_score_reasons():
    """理由只讲三维度自己的事 —— 混进通道结论/主线, 用户就分不清哪句影响了排名。"""
    o, _ = _one({"600000.SH": {
        "gate": _gate_ok(), "channel_pct": 0.6,
        "verdict": {"code": "top_all_bands", "title": "三档都到上沿", "detail": "别追"},
        "mainline": {"member": "机器人", "rank": 1, "limit_up_count": 9, "also": []}}})
    joined = "".join(o["why"])
    assert "三档都到上沿" not in joined and "机器人" not in joined


# ------------------------------------------------------- 生命线门槛的后果


def test_lifeline_gate_excludes_every_dip_candidate():
    """贴下轨 ⟹ 收盘在 MA20 之下 ⟹ 被生命线门槛挡掉。

    v2 只做站上生命线之后的趋势中继, **不做低吸** —— 这是"跌破生命线的不看"
    的直接推论, 不是遗漏。谁要放宽这条, 得先改掉用户那句话。
    """
    ranked, gates = score_opportunities(
        {"600000.SH": _trend()}, {}, NAMES, bench_ret=0.02,
        extras={"600000.SH": {
            "gate": _gate_ok(above_ma20=False), "channel_pct": 0.05,
            "verdict": {"code": "dip_in_uptrend", "title": "强势票深调"}}})
    assert ranked == []
    assert gates["blocked"][osc.GATE_LIFELINE] == 1
    assert gates["blocked_total"] == 1 and gates["candidates"] == 1


def test_gate_blocked_candidates_are_counted_not_silently_dropped():
    """"今天 N 只被门槛挡掉"本身就是市场状态, 藏起来会被读成系统没干活。"""
    trends = {"600000.SH": _trend(), "600001.SH": _trend(state="DT", side="空头")}
    names = {"600000.SH": "甲", "600001.SH": "乙"}
    ranked, gates = score_opportunities(trends, {}, names, extras={
        "600000.SH": {"gate": _gate_ok(), "channel_pct": 0.6},
        "600001.SH": {"gate": _gate_ok(), "channel_pct": 0.6},
    })
    assert [o["symbol"] for o in ranked] == ["600000.SH"]
    assert gates["blocked"] == {osc.GATE_TREND: 1}
    assert (gates["candidates"], gates["passed"]) == (2, 1)


def test_ai_breakout_candidates_go_through_the_same_gates():
    """v1 里"逼近突破"那一路完全不检查趋势状态 —— 这是 v2 门槛最主要的边际作用。"""
    signals = {"600000.SH": {"signal": "buy", "confidence": 80, "close": 10.0,
                             "watch_points": [{"direction": "up", "price": 10.1,
                                               "action": "买入"}]}}
    ranked, gates = score_opportunities(
        {"600000.SH": _trend(state="DT", side="空头", signal=None)}, signals, NAMES,
        extras={"600000.SH": {"gate": _gate_ok(), "channel_pct": 0.6}})
    assert ranked == [] and gates["blocked"] == {osc.GATE_TREND: 1}


def test_rank_opportunities_still_returns_the_old_two_tuple():
    """对外签名不变 —— 换的是打分, 不是接口。"""
    shown, filtered = rank_opportunities(
        {"600000.SH": _trend()}, {}, NAMES, min_hist_pct=0, max_show=10,
        bench_ret=0.02, extras={"600000.SH": {"gate": _gate_ok(), "channel_pct": 0.6}})
    assert len(shown) == 1 and filtered == 0
    assert isinstance(shown[0]["why"], str)      # 显示列表里 why 已拼成一句
