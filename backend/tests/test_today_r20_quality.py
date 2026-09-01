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


# ---------- 量价与胜率在 v2 里的位置 ----------
#
# [R134] 这一段整体重写。R20 时量比与历史胜率都是加减分(±8/±12);
# v2 把它们分开了:
#   · 量比 → 留在评分里, 但改成**区间型曲线**(峰在 1.3~2.5)。
#     量比 5 不再比 2 高 —— 那种量往往出现在一波的末端而不是起点。
#   · 历史胜率 → 退出评分, 只作注记。单票历史转强常不足 10 次, n 这么小的
#     胜率噪声远大于信号, 拿它去动名次是在把噪声写进排序。


def _rank(extras, **kw):
    names = {"a": "甲", "b": "乙"}
    trends = {"a": _trend(), "b": _trend()}
    base = {"gate": {"above_ma20": True, "above_ma20_prev": True,
                     "close": 10.0, "ma120": 8.0, "ma120_rising": True},
            "channel_pct": 0.6}
    merged = {k: {**base, **v} for k, v in extras.items()}
    for s in ("a", "b"):
        merged.setdefault(s, dict(base))
    shown, _ = rank_opportunities(trends, {}, names, min_score=0, max_show=10,
                                  extras=merged, **kw)
    return {o["symbol"]: o for o in shown}


def test_volume_surge_beats_shrink():
    """同样的信号: 有增量的分数必须高于缩量的, 且理由写明量比。"""
    out = _rank({"a": {"vol_ratio": 2.1}, "b": {"vol_ratio": 0.5}})
    assert out["a"]["score"] > out["b"]["score"]
    assert "量比 2.10" in out["a"]["why"]
    assert "没量" in out["b"]["why"]


def test_volume_ratio_is_range_optimal():
    """v1 是"越大越加"; v2 里量比 5.0 必须低于 2.0 —— 那不是苗头, 是已经发生了。"""
    out = _rank({"a": {"vol_ratio": 2.0}, "b": {"vol_ratio": 5.0}})
    assert out["a"]["score"] > out["b"]["score"]
    assert "已经走了一段" in out["b"]["why"]


def test_historical_win_rate_no_longer_moves_the_score():
    """n 常不足 10 次, 这种胜率噪声远大于信号 —— 不该动名次。"""
    out = _rank({"a": {"win": {"rate": 0.7, "n": 6}}, "b": {"win": {"rate": 0.35, "n": 6}}})
    assert out["a"]["score"] == out["b"]["score"]


def test_historical_win_rate_is_still_shown_as_an_annotation():
    """不计分不等于不展示 —— 用户要的是"看到它时知道些什么"。"""
    out = _rank({"a": {"win": {"rate": 0.7, "n": 6}}})
    note = {n["key"]: n for n in out["a"]["notes"]}["win"]
    assert "70%" in note["label"] and note["tone"] == "good"
    assert "10 次" in note["text"], "样本量小的告诫必须跟着一起显示"


def test_low_win_rate_annotation_is_toned_bad():
    out = _rank({"a": {"win": {"rate": 0.3, "n": 8}}})
    assert {n["key"]: n["tone"] for n in out["a"]["notes"]}["win"] == "bad"


def test_annotations_stay_out_of_the_scoring_reasons():
    out = _rank({"a": {"win": {"rate": 0.7, "n": 6}}})
    assert "胜率" not in out["a"]["why"]


def test_no_extras_still_scores_both_the_same():
    out = _rank({})
    assert out["a"]["score"] == out["b"]["score"]
    assert "量比" not in out["a"]["why"]
