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
    # [R134] 新鲜度是趋势维度里权重最大的一项, 它必须能自己拉开差距
    assert shown[0]["factors"]["fresh"] > shown[1]["factors"]["fresh"]
    # 第 5 天已过入场窗口, 分数低于第 3 天(可能已被滤掉)
    assert scores.get("000003.SZ", 0) < scores["000002.SZ"]


def test_stale_weak_signal_is_filtered_out():
    """第 5 天的回升信号把握不足, 不显示但要报出被滤掉的条数。"""
    names = {"000002.SZ": "万科A"}
    shown, filtered = rank_opportunities({"000002.SZ": _trend("回升", 5)}, {}, names)
    assert shown == []
    assert filtered == 1


def test_ai_signal_no_longer_moves_the_score():
    """[R134] AI 置信度退出评分, 只作注记。

    它是模型对自己输出的自评, 不可回测, 而且会过时(用户明确提过"别搞过时信息")。
    v1 里 AI 看空扣 40 分, 效果等于把票藏起来 —— 藏起来用户就不知道有过这个冲突,
    更谈不上自己定夺。现在改成: 分数不动, 但矛盾要**显眼地**摆出来。
    """
    names = {"000001.SZ": "平安银行", "000002.SZ": "万科A"}
    trends = {"000001.SZ": _trend("转多", 2), "000002.SZ": _trend("转多", 2)}
    signals = {
        "000001.SZ": {"signal": "buy", "confidence": 90},
        "000002.SZ": {"signal": "sell", "confidence": 80},
    }
    shown, _ = rank_opportunities(trends, signals, names)
    by = {o["symbol"]: o for o in shown}
    assert set(by) == {"000001.SZ", "000002.SZ"}, "看空的票不再被悄悄藏起来"
    assert by["000001.SZ"]["score"] == by["000002.SZ"]["score"]
    bear_note = {n["key"]: n for n in by["000002.SZ"]["notes"]}["ai"]
    assert bear_note["tone"] == "bad" and "矛盾" in bear_note["text"]
    assert "AI" not in "".join(by["000001.SZ"]["why"]), "注记不许混进评分理由"


def test_high_confidence_cannot_rescue_stale_signal():
    """关键约定: 信号拖了 5 天, 即使 AI 置信度 95 也不该压过刚转强的票。"""
    names = {"stale": "陈年信号", "fresh": "刚转强"}
    trends = {"stale": _trend("转多", 5), "fresh": _trend("转多", 1)}
    signals = {"stale": {"signal": "buy", "confidence": 95}}
    shown, _ = rank_opportunities(trends, signals, names)
    assert shown[0]["symbol"] == "fresh"


def test_near_breakout_distance_no_longer_scores_but_is_still_exposed():
    """[R134] 距触发价退出评分 —— 它与通道位置指向同一件事(离上方阻力多远),
    两个一起放是把同一份信息计价两次。改成结构化字段摆在列上给人看。
    """
    names = {"near": "贴价", "far": "还差些"}
    signals = {
        "near": {"signal": "buy", "confidence": 70, "close": 100.0,
                 "watch_points": [{"direction": "up", "price": 100.3, "action": "突破关注买入"}]},
        "far": {"signal": "buy", "confidence": 70, "close": 100.0,
                "watch_points": [{"direction": "up", "price": 101.9, "action": "突破关注买入"}]},
    }
    shown, _ = rank_opportunities({}, signals, names, min_score=0)
    by = {o["symbol"]: o for o in shown}
    assert by["near"]["score"] == by["far"]["score"]
    assert by["near"]["gap_pct"] == 0.3 and by["far"]["gap_pct"] == 1.9
    assert by["near"]["fresh_from"] == "near_breakout"


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
