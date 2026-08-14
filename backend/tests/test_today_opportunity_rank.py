"""[fork 增强] 今日总览机会区: 买入机会的把握打分与筛选。

核心约定: 买入机会先打分再显示, 信号越"陈旧"(错过入场窗口)分数越低;
卖出/风险提醒走行动区, 不经过这里的筛选。
"""
from app.api.today import _OPP_MAX_SHOW, _OPP_MIN_SCORE, rank_opportunities


def _trend(signal, duration, close=10.0):
    return {
        "state": "UT", "state_cn": "上涨趋势", "side": "多头",
        "duration": duration, "close": close, "as_of": "2026-08-14",
        "signal": signal, "signal_desc": f"突破上关键点 {close}",
    }


def test_fresh_signal_outranks_stale_one():
    """同为转多: 第 1 天把握分必须高于第 3 天, 第 3 天又高于第 5 天。"""
    names = {"000001.SZ": "平安银行", "000002.SZ": "万科A", "000003.SZ": "国农科技"}
    trends = {
        "000001.SZ": _trend("转多", 1),
        "000002.SZ": _trend("转多", 3),
        "000003.SZ": _trend("转多", 5),
    }
    shown, _ = rank_opportunities(trends, {}, names)
    scores = {o["symbol"]: o["score"] for o in shown}
    assert scores["000001.SZ"] > scores["000002.SZ"]
    assert shown[0]["symbol"] == "000001.SZ"
    assert "入场窗口最佳" in shown[0]["why"]
    # 第 5 天已过入场窗口, 分数低于第 3 天(可能已被滤掉)
    assert scores.get("000003.SZ", 0) < scores["000002.SZ"]


def test_stale_weak_signal_is_filtered_out():
    """第 5 天的回升信号把握不足, 不显示但要报出被滤掉的条数。"""
    names = {"000002.SZ": "万科A"}
    shown, filtered = rank_opportunities({"000002.SZ": _trend("回升", 5)}, {}, names)
    assert shown == []
    assert filtered == 1


def test_ai_agreement_boosts_and_conflict_drops():
    """AI 同向看多加分; AI 看空则大幅扣分, 自相矛盾的机会不显示。"""
    names = {"000001.SZ": "平安银行", "000002.SZ": "万科A"}
    trends = {"000001.SZ": _trend("转多", 2), "000002.SZ": _trend("转多", 2)}
    signals = {
        "000001.SZ": {"signal": "buy", "confidence": 90},
        "000002.SZ": {"signal": "sell", "confidence": 80},
    }
    shown, filtered = rank_opportunities(trends, signals, names)
    assert [o["symbol"] for o in shown] == ["000001.SZ"], "AI 看空的票不该出现在买入机会里"
    assert "AI 也看多" in shown[0]["why"]
    assert filtered == 1


def test_high_confidence_cannot_rescue_stale_signal():
    """关键约定: 信号拖了 5 天, 即使 AI 置信度 95 也不该压过刚转强的票。"""
    names = {"stale": "陈年信号", "fresh": "刚转强"}
    trends = {"stale": _trend("转多", 5), "fresh": _trend("转多", 1)}
    signals = {"stale": {"signal": "buy", "confidence": 95}}
    shown, _ = rank_opportunities(trends, signals, names)
    assert shown[0]["symbol"] == "fresh"


def test_near_breakout_scored_by_distance():
    """已经贴着买入触发价的, 比还差 2% 的分数高。"""
    names = {"near": "贴价", "far": "还差些"}
    signals = {
        "near": {"signal": "buy", "confidence": 70, "close": 100.0,
                 "watch_points": [{"direction": "up", "price": 100.3, "action": "突破关注买入"}]},
        "far": {"signal": "buy", "confidence": 70, "close": 100.0,
                "watch_points": [{"direction": "up", "price": 101.9, "action": "突破关注买入"}]},
    }
    shown, _ = rank_opportunities({}, signals, names)
    scores = {o["symbol"]: o["score"] for o in shown}
    assert scores["near"] > scores["far"]
    assert "一到价就能按预案行动" in shown[0]["why"]


def test_show_cap_and_filtered_count():
    """机会再多也只显示前 N 条, 其余计入被滤掉的数量。"""
    names = {f"S{i:03d}": f"票{i}" for i in range(20)}
    trends = {s: _trend("转多", 1) for s in names}
    shown, filtered = rank_opportunities(trends, {}, names)
    assert len(shown) == _OPP_MAX_SHOW
    assert filtered == len(names) - _OPP_MAX_SHOW
    assert all(o["score"] >= _OPP_MIN_SCORE for o in shown)


def test_scores_are_clamped_to_0_100():
    names = {"a": "甲", "b": "乙"}
    trends = {"a": _trend("转多", 1), "b": _trend("回升", 9)}
    signals = {"a": {"signal": "buy", "confidence": 100},
               "b": {"signal": "sell", "confidence": 100}}
    shown, _ = rank_opportunities(trends, signals, names)
    assert all(0 <= o["score"] <= 100 for o in shown)
