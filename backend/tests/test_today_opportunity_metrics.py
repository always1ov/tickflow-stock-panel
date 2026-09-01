"""[fork R123] 机会区结构化指标: 量比 / 距触发价, 从 why 散文里拎出来成列。"""
from __future__ import annotations

from app.api.today import rank_opportunities


def _trends(close=10.0, pivot=10.5):
    return {"600110.SH": {
        "signal": "转多", "signal_desc": "突破上关键点", "duration": 1,
        "close": close, "entry_pivot": pivot, "ret_20d": 0.05,
    }}


_NAMES = {"600110.SH": "诺德股份"}


def _one(**kw):
    shown, _ = rank_opportunities(names=_NAMES, min_score=0, max_show=10, **kw)
    return shown[0]


def test_vol_ratio_and_gap_are_exposed():
    o = _one(trends=_trends(close=10.0, pivot=10.5), signals={},
             extras={"600110.SH": {"vol_ratio": 1.73}})
    assert o["vol_ratio"] == 1.73
    assert o["gap_pct"] == 5.0        # 10.0 → 10.5 还差 5 个点


def test_gap_is_negative_once_price_is_through():
    """已经越过触发价 → 负数, 界面据此区分"还没到"与"已越过"。"""
    o = _one(trends=_trends(close=11.0, pivot=10.5), signals={}, extras={})
    assert o["gap_pct"] == -4.55


def test_missing_inputs_stay_none_not_zero():
    """取不到就留空 —— 0 会被读成"正好到触发价", 是有含义的数字, 不能拿来填空。"""
    o = _one(trends={"600110.SH": {"signal": "转多", "signal_desc": "突破", "duration": 1}},
             signals={}, extras={})
    assert o["vol_ratio"] is None and o["gap_pct"] is None


def test_vol_ratio_zero_is_treated_as_missing():
    o = _one(trends=_trends(), signals={}, extras={"600110.SH": {"vol_ratio": 0}})
    assert o["vol_ratio"] is None


def test_near_breakout_source_also_gets_metrics():
    """逼近突破那一路(signals)也要有这两个字段, 不能只有趋势那一路有。"""
    shown, _ = rank_opportunities(
        names=_NAMES, trends={}, min_score=0, max_show=10,
        extras={"600110.SH": {"vol_ratio": 2.1}},
        signals={"600110.SH": {
            "signal": "buy", "confidence": 70, "close": 10.0,
            "watch_points": [{"direction": "up", "price": 10.2, "action": "买入"}],
        }},
    )
    o = shown[0]
    assert o["vol_ratio"] == 2.1 and o["gap_pct"] == 2.0
