"""[fork R121] AI 优选事实校验: 数字对账 / 空理由 / 驳回。"""
from __future__ import annotations

import pytest

from app.services import today_ai_verify as v


def _cand(symbol="600110.SH", bars=None, **extra):
    return {
        "symbol": symbol,
        "name": "诺德股份",
        "最近20日K": bars if bars is not None else [
            {"date": "2026-08-28", "close": 11.0, "high": 11.2, "low": 10.8,
             "change_pct": 1.20, "vol_ratio_5d": 0.90},
            {"date": "2026-08-31", "close": 11.8, "high": 12.0, "low": 11.0,
             "change_pct": 7.20, "vol_ratio_5d": 1.25},
            {"date": "2026-09-01", "close": 12.3, "high": 12.4, "low": 11.9,
             "change_pct": 4.20, "vol_ratio_5d": 1.60},
        ],
        **extra,
    }


def _pick(reason, symbol="600110.SH"):
    return {"symbol": symbol, "reason": reason}


# ------------------------------------------------------------ 对得上


def test_matching_numbers_pass():
    got = v.verify_pick(_pick("8月31日涨7.2%、量比1.25，缩量回踩守住"), _cand())
    assert got["verdict"] == "已核对"
    assert [c["ok"] for c in got["checks"] if c["kind"] in {"涨幅", "量比"}] == [True, True]


def test_tolerance_allows_rounding():
    """7.2% 说成 7.0% 属于四舍五入, 不该判撒谎。"""
    assert v.verify_pick(_pick("涨7.0%"), _cand())["verdict"] == "已核对"


# ------------------------------------------------------------ 对不上


def test_wrong_volume_ratio_is_flagged():
    got = v.verify_pick(_pick("放量突破，量比2.8"), _cand())
    assert got["verdict"] == "存疑"
    ratio = [c for c in got["checks"] if c["kind"] == "量比"][0]
    assert ratio["ok"] is False and ratio["actual"] == 1.6
    assert "1.60" in got["verdict_note"]


def test_wrong_change_pct_is_flagged():
    got = v.verify_pick(_pick("昨天涨15.0%"), _cand())
    assert got["verdict"] == "存疑"
    assert any(c["kind"] == "涨幅" and c["ok"] is False for c in got["checks"])


def test_absurd_price_is_rejected():
    """价位编错最危险 —— 用户会照着这个数挂单, 直接驳回。"""
    got = v.verify_pick(_pick("回踩2372元一线仍守住"), _cand())
    assert got["verdict"] == "驳回"
    assert "11" in got["verdict_note"] or "12" in got["verdict_note"]


def test_price_inside_band_passes():
    assert v.verify_pick(_pick("站上12.00元确认"), _cand())["verdict"] == "已核对"


# ------------------------------------------------------------ 空理由 / 越界


@pytest.mark.parametrize("reason", ["规则分高，信号扎实", "AI 看多且信号共振"])
def test_hollow_reasons_are_doubtful(reason):
    """提示词明令禁止复述规则分/信号 —— 复述了就标存疑。"""
    got = v.verify_pick(_pick(reason), _cand())
    assert got["verdict"] == "存疑" and "不是量价证据" in got["verdict_note"]


def test_reason_without_numbers_is_pending():
    got = v.verify_pick(_pick("放量长阳，形态干净"), _cand())
    assert got["verdict"] == "待查" and got["checks"] == []


def test_symbol_outside_candidate_set_is_rejected():
    got = v.verify_pick(_pick("涨7.2%", symbol="000001.SZ"), None)
    assert got["verdict"] == "驳回" and "不在今天的候选集里" in got["verdict_note"]


def test_intraday_signal_must_say_wait_for_close():
    cand = _cand(**{"盘中待收盘确认": True})
    got = v.verify_pick(_pick("涨7.2%、量比1.25"), cand)
    assert got["verdict"] == "存疑" and "等收盘确认" in got["verdict_note"]
    ok = v.verify_pick(_pick("涨7.2%，但要等收盘确认"), cand)
    assert ok["verdict"] == "已核对"


def test_missing_kline_cannot_be_checked():
    got = v.verify_pick(_pick("涨7.2%"), {"symbol": "600110.SH", "kline_error": "暂无日 K 数据"})
    assert got["checks"][0]["ok"] is None and got["verdict"] == "待查"


# ------------------------------------------------------------ 批量 / 汇总


def test_verify_picks_and_summary():
    cands = [_cand()]
    picks = [_pick("涨7.2%、量比1.25"), _pick("量比9.9"), _pick("涨1%", symbol="999999.SH")]
    out = v.verify_picks(picks, cands)
    assert [p["verdict"] for p in out] == ["已核对", "存疑", "驳回"]
    s = v.summarize(out)
    assert s == {"total": 3, "rejected": 1, "doubtful": 1, "clean": 1,
                 "text": "1 条因数字对不上被驳回"}


def test_summary_of_empty_picks():
    assert v.summarize([])["text"] == "今天没有优选"
