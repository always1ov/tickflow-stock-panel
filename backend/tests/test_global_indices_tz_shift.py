"""[R150] 行情时刻的时区口径补正 —— 修「恒定延迟720分」。

用户实测: 纳指卡片一直显示「延迟720分」。720 分 = 12 小时整, 而北京与美东
夏令时正好差 12 小时 —— 这是"那家发的是当地时间, 而 R148 一律按北京时间解析"
的签名, 不是真的延迟。真卡住的数不长这样: 它的年龄会随时间连续变大。

这组测试的重心是那条**守卫**: 补正只有在能把时刻拉回"确实新鲜"时才采纳。
不然这个修复就会把 R148 好不容易抓出来的真故障一起抹掉 —— 那比原来的 bug
更糟, 因为界面会重新变得看起来一切正常。
"""
from __future__ import annotations

import time
from datetime import datetime

import pytest

from app.services import global_indices as gi

_TZ = gi._QUOTE_TZ
_H = 3600.0


def _sina(now: float, stamp_at: float) -> str:
    """一行新浪 int_ 行情, 时刻字面量取自 stamp_at(按北京时间格式化)。"""
    txt = datetime.fromtimestamp(stamp_at, _TZ).strftime("%Y-%m-%d,%H:%M:%S")
    return f"纳斯达克,22484.07,98.50,0.44,{txt}"


# ---------------------------------------------------------------- 补正本身


def test_shift_recovers_us_eastern_timestamp():
    """本 bug 的直接回归: 字面量落后 12 小时整 → 补正回来, 不再报延迟。"""
    now = time.time()
    got, shift = gi._shift_quote_at(now - 12 * _H, now, (0.0, 12.0, 13.0))
    assert shift == 12.0
    assert abs(now - got) < 60


def test_shift_picks_winter_offset_when_that_is_the_fit():
    """冬令时差 13 小时 —— 同一套候选里挑得出对的那个。"""
    now = time.time()
    got, shift = gi._shift_quote_at(now - 13 * _H, now, (0.0, 12.0, 13.0))
    assert shift == 13.0
    assert abs(now - got) < 60


def test_no_shift_when_timestamp_is_already_beijing():
    """本来就是北京时间的源不许被动 —— 补正是修口径, 不是无脑往前推。"""
    now = time.time()
    got, shift = gi._shift_quote_at(now - 90, now, (0.0, 12.0, 13.0))
    assert shift == 0.0
    assert got == pytest.approx(now - 90)


# ---------------------------------------------------------------- 守卫: 不许抹掉真故障


def test_genuinely_stale_quote_is_not_shifted_away():
    """卡在 18 小时前的数: 补 12/13 小时之后还差 5~6 小时, 什么也没解释 ——
    不采纳, 老实报 18 小时。这条是整个修复的安全底线。"""
    now = time.time()
    got, shift = gi._shift_quote_at(now - 18 * _H, now, (0.0, 12.0, 13.0))
    assert shift == 0.0
    assert (now - got) == pytest.approx(18 * _H, abs=1)


def test_shift_not_applied_when_it_overshoots_into_the_future():
    """补过头(补完落在未来)的候选一律不要, 免得挑错冬夏令时反而制造负年龄。"""
    now = time.time()
    got, shift = gi._shift_quote_at(now - 1 * _H, now, (0.0, 12.0))
    assert shift == 0.0
    assert (now - got) == pytest.approx(_H, abs=1)


def test_frozen_quote_only_escapes_briefly():
    """真冻在 12 小时前的极端巧合: 此刻会被误判成新鲜, 但时间一走(超过新鲜
    区间)补正就不再成立, 卡片马上变回延迟 —— 骗不了多久。"""
    frozen_at = time.time() - 12 * _H
    at_the_coincidence = frozen_at + 12 * _H
    _, shift = gi._shift_quote_at(frozen_at, at_the_coincidence, (0.0, 12.0, 13.0))
    assert shift == 12.0                       # 这一刻确实分不出来
    later = at_the_coincidence + gi.STALE_IN_SESSION_S + 60
    _, shift_later = gi._shift_quote_at(frozen_at, later, (0.0, 12.0, 13.0))
    assert shift_later == 0.0                  # 十分钟后就露馅了


def test_none_timestamp_stays_none():
    assert gi._shift_quote_at(None, time.time(), (0.0, 12.0)) == (None, 0.0)


def test_default_preset_has_only_identity_shift():
    """没声明的指数不该被动 —— 补正是逐个市场显式开的, 不是全局默认。"""
    p = gi._Preset("x", (gi._Src("sina", "c"),), "X")
    assert p.tz_shifts_h == (0.0,)


# ---------------------------------------------------------------- 端到端


def test_pick_candidate_no_longer_reports_false_delay():
    """用户看到的那一幕: 源发美东时间, 卡片显示「延迟720分」→ 修完不再延迟。"""
    now = time.time()
    raw = {("sina", "int_nasdaq"): _sina(now, now - 12 * _H)}
    got = gi.pick_candidate(gi._BY_KEY["nasdaq"], raw, now, in_session=True)
    assert got is not None
    assert got["stale"] is False
    assert got["tz_shift_h"] == 12.0
    assert got["quote_age_s"] < 300


def test_pick_candidate_still_reports_a_real_freeze():
    """R148 抓的那类真故障必须还抓得住 —— 这次修复不能把它一起抹掉。"""
    now = time.time()
    raw = {("sina", "int_nasdaq"): _sina(now, now - 18 * _H)}
    got = gi.pick_candidate(gi._BY_KEY["nasdaq"], raw, now, in_session=True)
    assert got is not None
    assert got["stale"] is True
    assert got["tz_shift_h"] == 0.0
    assert got["quote_age_s"] == pytest.approx(18 * _H, abs=60)


def test_shift_applied_before_freshness_race():
    """补正必须发生在比新鲜度**之前** —— 否则发当地时间的源会被恒定误判成
    落后 12 小时, 在候选里永远排最后, 等于白改。"""
    now = time.time()
    raw = {
        # 新浪发美东时间, 实际就是此刻
        ("sina", "int_nasdaq"): _sina(now, now - 12 * _H),
        # 腾讯发北京时间, 但确实落后 20 分钟
        ("tencent", "usIXIC"): "~".join(
            ["200", "纳斯达克", "IXIC", "22000.0"] + [""] * 26
            + [datetime.fromtimestamp(now - 1200, _TZ).strftime("%Y%m%d%H%M%S"),
               "10", "0.05"]
        ),
    }
    got = gi.pick_candidate(gi._BY_KEY["nasdaq"], raw, now, in_session=True)
    assert got is not None
    assert got["source"] == "sina"
    assert got["last"] == pytest.approx(22484.07)


def test_debug_reports_both_raw_and_shifted():
    """「卡片说不延迟了」必须是一句能复核的话 —— 诊断里补正前后都要有。"""
    now = time.time()

    def fake_fetch(sources):
        return {("sina", "int_nasdaq"): _sina(now, now - 12 * _H)}

    import app.services.global_indices as mod
    orig = mod._fetch_all
    mod._fetch_all = fake_fetch
    try:
        out = mod.debug_fetch(["nasdaq"])
    finally:
        mod._fetch_all = orig
    one = out["parsed"]["nasdaq"]["sina:int_nasdaq"]
    assert one["tz_shift_h"] == 12.0
    assert one["raw_age_s"] == pytest.approx(12 * 3600, abs=120)
    assert one["age_s"] < 300
    assert one["quote_at_raw_text"] and one["quote_at_text"]
    assert out["tz_shifts_h"]["nasdaq"] == [0.0, 12.0, 13.0]
