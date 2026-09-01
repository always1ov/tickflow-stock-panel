"""[R148] 全球指数: 按行情自带时刻挑候选。

起因是用户报「晚上美股开盘了, 可是纳指不会动」。真因不是不刷新(前端 8s 轮询,
服务端 TTL 5s, 每次都真的问了上游), 而是**挑候选的规则**: 原来"第一个能解析出
数的候选就用", 而一家把上次收盘价一直挂着不动也算"能解析出数" —— 于是永远
轮不到后面真在跳的那家。这组测试钉住新规则。
"""
from __future__ import annotations

import time
from datetime import datetime

import pytest

from app.services import global_indices as gi

_TZ = gi._QUOTE_TZ


def _bj(now: float, minutes_ago: float) -> str:
    """now 之前 N 分钟的北京时间, 格式化成新浪那种 '日期,时间' 两格。"""
    dt = datetime.fromtimestamp(now - minutes_ago * 60, _TZ)
    return dt.strftime("%Y-%m-%d,%H:%M:%S")


def _compact(now: float, minutes_ago: float) -> str:
    dt = datetime.fromtimestamp(now - minutes_ago * 60, _TZ)
    return dt.strftime("%Y%m%d%H%M%S")


# ---------------------------------------------------------------- 时刻解析


def test_quote_ts_reads_sina_split_date_and_time():
    now = time.time()
    fields = f"纳斯达克,22484.07,98.50,0.44,{_bj(now, 3)}".split(",")
    ts = gi._quote_ts(fields, now)
    assert ts is not None
    assert abs((now - ts) - 180) < 90


def test_quote_ts_reads_tencent_compact_stamp():
    now = time.time()
    fields = ["200", "纳斯达克", "IXIC", "22484.07"] + [""] * 26 + [_compact(now, 2)]
    ts = gi._quote_ts(fields, now)
    assert ts is not None
    assert abs((now - ts) - 120) < 90


def test_quote_ts_none_when_no_timestamp():
    """腾讯 s_ 精简版根本不给时刻 —— 说不出来就返回 None, 不许瞎猜。"""
    assert gi._quote_ts("200~纳斯达克~IXIC~22484.07~98.5~0.44".split("~"), time.time()) is None


def test_quote_ts_rejects_absurd_timestamps():
    """时区/口径猜错时会算出离谱的时刻 —— 一律当读不出, 不参与新鲜度比较。"""
    now = time.time()
    far_future = datetime.fromtimestamp(now + 86400, _TZ).strftime("%Y-%m-%d,%H:%M:%S")
    assert gi._quote_ts(far_future.split(","), now) is None
    ancient = datetime.fromtimestamp(now - 40 * 86400, _TZ).strftime("%Y-%m-%d,%H:%M:%S")
    assert gi._quote_ts(ancient.split(","), now) is None


# ---------------------------------------------------------------- 挑候选


def _nasdaq() -> gi._Preset:
    return gi._BY_KEY["nasdaq"]


def test_in_session_prefers_fresher_source_over_first_ranked():
    """本 bug 的回归测试: 排第一的新浪卡在 5 小时前, 腾讯是 1 分钟前 → 用腾讯。"""
    now = time.time()
    raw = {
        ("sina", "int_nasdaq"): f"纳斯达克,22484.07,98.50,0.44,{_bj(now, 300)}",
        ("tencent", "usIXIC"): "~".join(
            ["200", "纳斯达克", "IXIC", "22599.10"] + [""] * 26
            + [_compact(now, 1), "101.2", "0.45"]
        ),
    }
    got = gi.pick_candidate(_nasdaq(), raw, now, in_session=True)
    assert got is not None
    assert got["source"] == "tencent"
    assert got["last"] == pytest.approx(22599.10)
    assert got["stale"] is False


def test_in_session_keeps_first_ranked_when_it_is_the_freshest():
    """新浪自己就是最新的时不许被无故换掉 —— 规则是"挑最新", 不是"躲开新浪"。"""
    now = time.time()
    raw = {
        ("sina", "int_nasdaq"): f"纳斯达克,22484.07,98.50,0.44,{_bj(now, 1)}",
        ("tencent", "usIXIC"): "~".join(
            ["200", "纳斯达克", "IXIC", "22599.10"] + [""] * 26
            + [_compact(now, 90), "101.2", "0.45"]
        ),
    }
    got = gi.pick_candidate(_nasdaq(), raw, now, in_session=True)
    assert got is not None
    assert got["source"] == "sina"


def test_in_session_timestamped_beats_untimestamped():
    """能自证新鲜的, 排在无法自证的前面(哪怕后者在候选表里更靠前)。"""
    now = time.time()
    p = gi._Preset("x", (gi._Src("tencent", "s_usIXIC"), gi._Src("sina", "int_nasdaq")), "X", 0, 24)
    raw = {
        ("tencent", "s_usIXIC"): "200~纳斯达克~IXIC~22111.00~10~0.05",
        ("sina", "int_nasdaq"): f"纳斯达克,22484.07,98.50,0.44,{_bj(now, 2)}",
    }
    got = gi.pick_candidate(p, raw, now, in_session=True)
    assert got is not None and got["source"] == "sina"


def test_off_session_falls_back_to_declared_order():
    """休市时人人静止, 比新鲜度没有意义 —— 回到候选表排名。"""
    now = time.time()
    raw = {
        ("sina", "int_nasdaq"): f"纳斯达克,22484.07,98.50,0.44,{_bj(now, 600)}",
        ("tencent", "usIXIC"): "~".join(
            ["200", "纳斯达克", "IXIC", "22599.10"] + [""] * 26
            + [_compact(now, 1), "101.2", "0.45"]
        ),
    }
    got = gi.pick_candidate(_nasdaq(), raw, now, in_session=False)
    assert got is not None and got["source"] == "sina"
    assert got["stale"] is False   # 休市静止是正常的, 不是故障


def test_stale_flag_set_when_all_sources_frozen_in_session():
    """所有源都卡住时不能假装没事 —— 值照给, 但明确标成延迟数据。"""
    now = time.time()
    raw = {("sina", "int_nasdaq"): f"纳斯达克,22484.07,98.50,0.44,{_bj(now, 240)}"}
    got = gi.pick_candidate(_nasdaq(), raw, now, in_session=True)
    assert got is not None
    assert got["stale"] is True
    assert got["quote_age_s"] == pytest.approx(240 * 60, abs=90)


def test_untimestamped_only_reports_unknown_age_not_fake_fresh():
    """唯一可用的源不给时刻时, quote_age_s 必须是 None ——
    绝不能拿抓取时刻冒充行情时刻, 那正是原来把故障藏起来的做法。"""
    now = time.time()
    p = gi._Preset("x", (gi._Src("tencent", "s_usIXIC"),), "X", 0, 24)
    raw = {("tencent", "s_usIXIC"): "200~纳斯达克~IXIC~22111.00~10~0.05"}
    got = gi.pick_candidate(p, raw, now, in_session=True)
    assert got is not None
    assert got["quote_age_s"] is None
    assert got["stale"] is False        # 说不出来 ≠ 断定它坏了
    assert got["updated_at"] == now     # 抓取时刻仍照实记, 只是不再被当成行情时刻


def test_no_candidate_parses_returns_none():
    now = time.time()
    assert gi.pick_candidate(_nasdaq(), {}, now, in_session=True) is None


def test_get_quotes_uses_freshest(monkeypatch):
    """端到端: get_quotes 走的就是这条规则(且缓存不会把旧的挑法带回来)。"""
    now = time.time()
    payloads = {
        ("sina", "int_nasdaq"): f"纳斯达克,22484.07,98.50,0.44,{_bj(now, 300)}",
        ("tencent", "usIXIC"): "~".join(
            ["200", "纳斯达克", "IXIC", "22599.10"] + [""] * 26
            + [_compact(now, 1), "101.2", "0.45"]
        ),
    }
    monkeypatch.setattr(gi, "_fetch_all", lambda sources: dict(payloads))
    monkeypatch.setattr(gi, "_in_session", lambda p, now=None: True)
    gi._set_cache({}, 0.0, ())
    rows = gi.get_quotes(["nasdaq"])
    assert len(rows) == 1
    assert rows[0]["source"] == "tencent"
    assert rows[0]["last"] == pytest.approx(22599.10)
    gi._set_cache({}, 0.0, ())
