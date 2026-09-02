"""[R158] 出手时机: 今天动手 / 收盘再动 / 不动手 —— 每条规则一个用例。"""
from __future__ import annotations

import inspect

import pytest

from app.services import action_timing as at


def _o(**kw) -> dict:
    base = {"symbol": "600000.SH", "trend_state": "UT", "duration": 2, "gap_pct": -2.5,
            "channel_pct": 0.6, "pivot": 10.0, "kinds": ["trend_signal"], "intraday": False,
            "live": None}
    base.update(kw)
    return base


# ---------------------------------------------------------------- 今天动手


def test_fresh_confirmed_uptrend_near_pivot_is_today():
    r = at.decide(_o(), "进攻")
    assert r["code"] == at.TODAY and r["label"] == "今天动手"
    assert "第 2 天" in r["reason"] and "2.5%" in r["reason"]
    assert r["trigger"] == 10.0


def test_cautious_posture_still_today_but_light():
    r = at.decide(_o(), "谨慎")
    assert r["code"] == at.TODAY
    assert "谨慎档" in r["reason"]


def test_day_three_is_last_today_day():
    assert at.decide(_o(duration=3), "进攻")["code"] == at.TODAY
    assert at.decide(_o(duration=4), "进攻")["code"] == at.AFTER_CLOSE


# ---------------------------------------------------------------- 收盘再动


def test_intraday_provisional_signal_waits_for_close():
    r = at.decide(_o(intraday=True), "进攻")
    assert r["code"] == at.AFTER_CLOSE and "盘中临时" in r["reason"]


def test_rally_that_crossed_pivot_intraday_waits_for_close():
    """回升途中盘中刚过关键点 —— 这正是用户要的「收盘后动手」那一档。"""
    r = at.decide(_o(trend_state="NR", gap_pct=3.0, live={"price": 10.2}), "进攻")
    assert r["code"] == at.AFTER_CLOSE
    assert "盘中已过关键点" in r["reason"] and r["trigger"] == 10.0


def test_near_breakout_within_two_percent_waits_for_close():
    r = at.decide(_o(trend_state="NR", kinds=["near_breakout"], gap_pct=1.2), "进攻")
    assert r["code"] == at.AFTER_CLOSE and "还差 1.2%" in r["reason"]


def test_uptrend_pulling_back_intraday_waits_for_close():
    r = at.decide(_o(live={"price": 9.9, "change_pct": -1.0}), "进攻")
    assert r["code"] == at.AFTER_CLOSE and "跌回关键点" in r["reason"]
    r2 = at.decide(_o(live={"price": 10.5, "change_pct": -3.5}), "进攻")
    assert r2["code"] == at.AFTER_CLOSE and "盘中回落" in r2["reason"]


# ---------------------------------------------------------------- 不动手


def test_defensive_market_blocks_everything():
    r = at.decide(_o(), "防守")
    assert r["code"] == at.HOLD_OFF and "防守" in r["reason"]


def test_below_lifeline_intraday_blocks():
    r = at.decide(_o(live={"price": 9.0, "below_lifeline": True, "ma20": 9.5}), "进攻")
    assert r["code"] == at.HOLD_OFF and "生命线" in r["reason"]


@pytest.mark.parametrize("symbol, chg, blocked", [
    ("600000.SH", 7.0, True),    # 主板 10% × 0.7
    ("600000.SH", 6.9, False),
    ("300750.SZ", 13.9, False),  # 创业板 20% × 0.7 = 14
    ("300750.SZ", 14.0, True),
])
def test_intraday_chase_threshold_is_board_aware(symbol, chg, blocked):
    r = at.decide(_o(symbol=symbol, live={"price": 11.0, "change_pct": chg}), "进攻")
    assert (r["code"] == at.HOLD_OFF and "不追" in r["reason"]) is blocked


def test_far_above_pivot_is_chasing():
    r = at.decide(_o(gap_pct=-5.0), "进攻")
    assert r["code"] == at.HOLD_OFF and "追高" in r["reason"]
    assert at.decide(_o(gap_pct=-4.9), "进攻")["code"] == at.TODAY


def test_upper_band_waits_for_pullback():
    r = at.decide(_o(channel_pct=0.85), "进攻")
    assert r["code"] == at.HOLD_OFF and "上轨" in r["reason"]


def test_stale_uptrend_signal():
    r = at.decide(_o(duration=6), "进攻")
    assert r["code"] == at.HOLD_OFF and "已老" in r["reason"]


def test_rally_not_yet_broken_out_holds_off_with_trigger():
    r = at.decide(_o(trend_state="NR", gap_pct=6.99, live={"price": 9.5}), "进攻")
    assert r["code"] == at.HOLD_OFF
    assert "未突破关键点" in r["reason"] and "7.0%" in r["reason"]
    assert r["trigger"] == 10.0


def test_missing_pivot_on_rally():
    r = at.decide(_o(trend_state="SR", pivot=None, gap_pct=None), "进攻")
    assert r["code"] == at.HOLD_OFF


# ---------------------------------------------------------------- 边界与接线


def test_missing_data_does_not_crash_or_fabricate():
    r = at.decide({"symbol": "000001.SZ"}, None)
    assert r["code"] in at.LABELS and r["label"] == at.LABELS[r["code"]]


def test_rule_order_exclusions_win_over_confirmations():
    """同时命中排除项与等收盘项时, 排除项优先 —— 不动手比等待更保守。"""
    r = at.decide(_o(intraday=True, gap_pct=-6.0), "进攻")
    assert r["code"] == at.HOLD_OFF


def test_thresholds_align_with_scoring_curves():
    from app.services import opportunity_score as osc
    fresh = dict(osc.FRESH_CURVE)
    assert fresh[at.FRESH_MAX_DAY] > 50 > fresh[at.FRESH_MAX_DAY + 1], "今天动手的天数上限要落在新鲜度曲线的拐点上"
    pos = dict(osc.POS_CURVE)
    assert pos[at.UPPER_BAND_PCT] <= 50


def test_today_overview_wires_action_timing():
    from app.api import today
    src = inspect.getsource(today._build_overview)
    assert "action_timing.decide(o, posture)" in src
