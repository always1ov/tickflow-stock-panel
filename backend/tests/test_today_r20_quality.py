"""[fork 增强] R20 把握分的量价与历史胜率因子。

初衷: 从自选里挑"最值得关注、胜率最好"的 —— 规则层必须看量(没有量的突破
多半是假突破)和这只票自己的历史信号胜率(同一套信号在不同票上好使程度不同)。
"""
from app.api.today import rank_opportunities
from app.services.livermore_service import _bullish_event_win_rate


def _trend(signal="转多", duration=1, close=10.0):
    return {"state": "UT", "state_cn": "上涨趋势", "side": "多头",
            "duration": duration, "close": close, "as_of": "2026-08-17",
            "signal": signal, "signal_desc": f"突破上关键点 {close}", "ret_20d": None}


# ---------- 历史胜率(纯函数) ----------

def test_win_rate_counts_completed_events_only():
    """3 次历史转强(2 胜 1 负), 最后一次距末尾不足 5 日不计。"""
    states = (["DT"] * 3 + ["UT"] * 10      # 事件1 @3, 5日后 106>100 胜
              + ["DT"] * 3 + ["UT"] * 10    # 事件2 @16, 5日后 94<98 负
              + ["DT"] * 3 + ["UT"] * 10    # 事件3 @29, 5日后 112>104 胜
              + ["DT"] * 2 + ["UT"] * 2)    # 事件4 @44, 距末尾不足5日 → 不计
    closes = ([100.0] * 3 + [100, 102, 103, 105, 104, 106, 107, 108, 109, 110]
              + [99.0] * 3 + [98, 97, 96, 95, 96, 94, 93, 92, 91, 90]
              + [103.0] * 3 + [104, 106, 108, 110, 111, 112, 113, 114, 115, 116]
              + [110.0] * 2 + [111, 112])
    assert len(states) == len(closes)
    win = _bullish_event_win_rate(states, closes, horizon=5)
    assert win == {"rate": round(2 / 3, 3), "n": 3}


def test_win_rate_needs_min_sample():
    """只有 2 次完整事件 → 返回 None, 小样本不给胜率。"""
    states = ["DT"] * 3 + ["UT"] * 10 + ["DT"] * 3 + ["UT"] * 10
    closes = [100.0] * len(states)
    assert _bullish_event_win_rate(states, closes, horizon=5, min_events=3) is None


# ---------- 量价与胜率进把握分 ----------

def _rank(extras):
    names = {"a": "甲", "b": "乙"}
    trends = {"a": _trend(), "b": _trend()}
    shown, _ = rank_opportunities(trends, {}, names, min_score=0, max_show=10,
                                  extras=extras)
    return {o["symbol"]: o for o in shown}


def test_volume_surge_beats_shrink():
    """同样的信号: 放量的分数必须高于缩量的, 且理由写明量比。"""
    out = _rank({"a": {"vol_ratio": 2.1}, "b": {"vol_ratio": 0.5}})
    assert out["a"]["score"] > out["b"]["score"]
    assert "放量突破" in out["a"]["why"]
    assert "假突破风险" in out["b"]["why"]


def test_historical_win_rate_adjusts_score():
    """历史胜率 70% 加分, 35% 压分 —— 信号在谁身上好使, 分数说话。"""
    out = _rank({"a": {"win": {"rate": 0.7, "n": 6}}, "b": {"win": {"rate": 0.35, "n": 6}}})
    assert out["a"]["score"] > out["b"]["score"]
    assert "胜率 70%" in out["a"]["why"]
    assert "不好使" in out["b"]["why"]


def test_mid_win_rate_shown_but_neutral():
    """胜率 50% 不加不扣, 但要展示给用户参考。"""
    base = _rank({})["a"]["score"]
    out = _rank({"a": {"win": {"rate": 0.5, "n": 5}}})
    assert out["a"]["score"] == base
    assert "胜率 50%" in out["a"]["why"]


def test_no_extras_keeps_old_behavior():
    out = _rank({})
    assert out["a"]["score"] == out["b"]["score"]
    assert "量比" not in out["a"]["why"] and "胜率" not in out["a"]["why"]
