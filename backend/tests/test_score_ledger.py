"""[fork R133] 规则层把握分台账: 落快照 / 补收益 / 分层单调 / 因子归因 / 导出。

守的是三件容易悄悄坏掉的事:
  1. 记的必须是**完整候选池**(含被门槛滤掉的) —— 只记显示出来的那几条,
     等于只用样本里最好的一段去证明样本好, 台账就白建了;
  2. 没走够 N 根 K 的收益必须留空, 不许拿最后一根冒充;
  3. 盘中快照(close 是实时价)不能覆盖收盘定稿, 也不能进统计。
"""
from __future__ import annotations

from datetime import date

import polars as pl
import pytest

from app.api.today import filter_opportunities, rank_opportunities, score_opportunities
from app.config import settings
from app.services import score_ledger as sl


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    sl._written.clear()          # 进程级去重集合在测试之间必须清干净
    yield
    sl._written.clear()


class _Repo:
    def __init__(self, series: dict[str, list[tuple[str, float]]]):
        self.series = series

    def resolve_asset_type(self, symbol):  # noqa: ARG002
        return "stock"

    def get_daily_asset(self, asset_type, symbol, start, end, columns=None):  # noqa: ARG002
        rows = [r for r in self.series.get(symbol, [])
                if start <= date.fromisoformat(r[0]) <= end]
        if not rows:
            return pl.DataFrame()
        return pl.DataFrame({"date": [r[0] for r in rows], "close": [r[1] for r in rows]})


@pytest.fixture
def repo():
    return _Repo({
        # 一路涨: T+1 +10%, T+3 +20%, T+5 +30%
        "600110.SH": [("2026-08-17", 10.0), ("2026-08-18", 11.0), ("2026-08-19", 10.5),
                      ("2026-08-20", 12.0), ("2026-08-21", 12.5), ("2026-08-24", 13.0)],
        # 只有一根后续 K: T+1 有, T+3/T+5 必须留空
        "002222.SZ": [("2026-08-17", 20.0), ("2026-08-18", 19.0)],
        "000300.SH": [("2026-08-17", 4000.0), ("2026-08-18", 4040.0), ("2026-08-19", 4020.0),
                      ("2026-08-20", 4080.0), ("2026-08-21", 4100.0), ("2026-08-24", 4200.0)],
    })


def _cand(sym, score, *, rank_hint=0, factors=None, close=10.0, shown=True):  # noqa: ARG001
    return {"symbol": sym, "name": sym, "score": score, "kind": "trend_signal",
            "board": "主板", "close": close, "why": ["x"],
            "factors": factors or {"base": 70, "fresh": 15}, "ctx": {"dur": 1}}


# ------------------------------------------------------- 打分拆分后行为不变


def _trend(signal="转多", dur=1, **kw):
    return {"signal": signal, "duration": dur, "signal_desc": "描述",
            "state": "UT", "side": "多头", "as_of": "2026-08-17", "close": 10.0, **kw}


def test_split_keeps_rank_opportunities_identical():
    """拆成 score+filter 之后, 老接口必须逐字段等于原来的结果。"""
    trends = {f"60000{i}.SH": _trend(dur=i) for i in range(1, 6)}
    names = {s: s for s in trends}
    shown, filtered = rank_opportunities(trends, {}, names)
    again, f2 = filter_opportunities(score_opportunities(trends, {}, names), 60, 10)
    assert [o["symbol"] for o in shown] == [o["symbol"] for o in again]
    assert filtered == f2


def test_score_opportunities_keeps_sub_threshold_candidates():
    """完整列表必须含被门槛滤掉的票 —— 台账要的正是它们。"""
    trends = {"600001.SH": _trend(dur=1), "600002.SH": _trend("回升", dur=5)}
    names = {s: s for s in trends}
    full = score_opportunities(trends, {}, names)
    shown, _ = rank_opportunities(trends, {}, names)
    assert len(full) == 2 and len(shown) == 1
    assert min(o["score"] for o in full) < 60


def test_factors_sum_back_to_score():
    """因子拆解必须能加回总分, 否则归因表说的不是这套分数。"""
    trends = {"600001.SH": _trend(dur=1, ret_20d=0.20)}
    full = score_opportunities(trends, {}, {"600001.SH": "测试"}, bench_ret=0.02,
                               extras={"600001.SH": {"vol_ratio": 2.0}})
    o = full[0]
    assert sum(o["factors"].values()) == o["score"]
    assert o["factors"]["fresh"] == 15 and o["factors"]["vol"] == 8 and o["factors"]["rs"] == 8


def test_clamp_is_recorded_when_score_saturates():
    """理论分 >100 被夹平这件事本身就是结论, 必须留痕。"""
    trends = {"600001.SH": _trend(dur=1, ret_20d=0.20)}
    full = score_opportunities(
        trends, {"600001.SH": {"signal": "buy", "confidence": 90}}, {"600001.SH": "测试"},
        bench_ret=0.02,
        extras={"600001.SH": {"vol_ratio": 2.0, "win": {"rate": 0.8, "n": 10},
                              "mainline": {"rank": 1, "member": "AI", "limit_up_count": 5}}})
    o = full[0]
    assert o["score"] == 100
    assert o["factors"]["clamp"] < 0 and o["ctx"]["raw_score"] > 100


# ------------------------------------------------------- 记录


def test_record_keeps_rank_and_shown_flag():
    ranked = [_cand("600110.SH", 90), _cand("002222.SZ", 55)]
    out = sl.record_day("2026-08-17", ranked, {"600110.SH"}, True)
    assert out["recorded"] == 2
    rows = sl._read()[0]["rows"]
    assert rows[0]["rank"] == 1 and rows[0]["shown"] is True
    assert rows[1]["rank"] == 2 and rows[1]["shown"] is False


def test_record_is_written_once_per_process():
    """总览接口每次打开都会调 —— 没有去重会把整本台账反复重写。"""
    ranked = [_cand("600110.SH", 90)]
    assert sl.record_day("2026-08-17", ranked, set(), True)["recorded"] == 1
    assert sl.record_day("2026-08-17", ranked, set(), True)["recorded"] == 0


def test_intraday_never_overwrites_finalized():
    sl.record_day("2026-08-17", [_cand("600110.SH", 90, close=10.0)], set(), True)
    sl._written.clear()          # 模拟重启后盘中又来一次
    sl.record_day("2026-08-17", [_cand("002222.SZ", 88, close=99.0)], set(), False)
    rows = sl._read()[0]["rows"]
    assert len(rows) == 1 and rows[0]["symbol"] == "600110.SH"


def test_record_without_date_or_rows_is_refused():
    assert sl.record_day(None, [_cand("600110.SH", 90)], set(), True)["ok"] is False
    assert sl.record_day("2026-08-17", [], set(), True)["ok"] is False


def test_rows_are_capped(monkeypatch):
    monkeypatch.setattr(sl, "MAX_ROWS", 2)
    sl.record_day("2026-08-17", [_cand(f"60000{i}.SH", 90 - i) for i in range(5)], set(), True)
    assert len(sl._read()[0]["rows"]) == 2


def test_days_are_capped(monkeypatch):
    monkeypatch.setattr(sl, "MAX_DAYS", 2)
    for d in range(1, 5):
        sl.record_day(f"2026-09-0{d}", [_cand("600110.SH", 90)], set(), True)
    days = sl._read()
    assert len(days) == 2 and days[0]["as_of"] == "2026-09-03"


# ------------------------------------------------------- 收益回看


def test_forward_returns_are_filled_and_persisted(repo):
    sl.record_day("2026-08-17", [_cand("600110.SH", 90, close=10.0)], {"600110.SH"}, True)
    sl.evaluate(repo)
    r = sl._read()[0]["rows"][0]["r"]
    assert r == {"t1": 10.0, "t3": 20.0, "t5": 30.0}    # 落了盘, 下次不必重算


def test_immature_horizons_stay_empty(repo):
    """只走了一根后续 K —— T+3/T+5 必须缺着, 不许拿最后一根冒充。"""
    sl.record_day("2026-08-17", [_cand("002222.SZ", 90, close=20.0)], set(), True)
    sl.evaluate(repo)
    r = sl._read()[0]["rows"][0]["r"]
    assert r == {"t1": -5.0} and "t5" not in r


def test_intraday_rows_are_excluded_from_stats(repo):
    sl.record_day("2026-08-17", [_cand("600110.SH", 90, close=10.0)], set(), False)
    out = sl.evaluate(repo)
    assert out["recorded_days"] == 0 and out["all"]["t1"]["n"] == 0


# ------------------------------------------------------- 统计


def _seed_two_buckets(repo):
    """高分档全是赢家, 低分档全是输家 —— 单调性应判定成立。"""
    sl.record_day("2026-08-17", [
        _cand("600110.SH", 95, close=10.0),      # +10% / +20% / +30%
        _cand("002222.SZ", 65, close=20.0),      # -5%
    ], {"600110.SH"}, True)


def test_buckets_and_ranks(repo):
    _seed_two_buckets(repo)
    out = sl.evaluate(repo)
    hi = next(b for b in out["buckets"] if b["label"] == "90-100")
    lo = next(b for b in out["buckets"] if b["label"] == "60-69")
    assert hi["stats"]["t1"]["win_rate"] == 100.0
    assert lo["stats"]["t1"]["win_rate"] == 0.0
    top1 = next(r for r in out["ranks"] if r["cut"] == 1)
    assert top1["count"] == 1 and top1["stats"]["t1"]["win_rate"] == 100.0


def test_monotonic_note_needs_enough_samples(repo):
    _seed_two_buckets(repo)
    note = sl.evaluate(repo)["monotonic"]
    assert note["ok"] is None and "看不出" in note["text"]


def test_monotonic_note_flags_inversion(repo):
    """高分档反而更差时必须明说不单调 —— 这是"分数没用"的直接证据。"""
    buckets = [
        {"label": "60-69", "stats": {"t5": {"n": 20, "win_rate": 70.0, "avg": 3.0}}},
        {"label": "90-100", "stats": {"t5": {"n": 20, "win_rate": 40.0, "avg": -1.0}}},
    ]
    note = sl._monotonic_note(buckets)
    assert note["ok"] is False and "不单调" in note["text"]


def test_factor_attribution_splits_three_ways(repo):
    sl.record_day("2026-08-17", [
        _cand("600110.SH", 90, close=10.0, factors={"base": 70, "vol": 8}),
        _cand("002222.SZ", 70, close=20.0, factors={"base": 70, "vol": -12}),
    ], set(), True)
    out = sl.evaluate(repo)
    vol = next(f for f in out["factors"] if f["key"] == "vol")
    assert vol["plus"]["count"] == 1 and vol["minus"]["count"] == 1
    assert vol["plus"]["stats"]["t1"]["win_rate"] == 100.0
    assert vol["minus"]["stats"]["t1"]["win_rate"] == 0.0


def test_baseline_uses_same_dates_and_horizons(repo):
    """没有同期基准, "胜率 55%" 说明不了任何问题。"""
    sl.record_day("2026-08-17", [_cand("600110.SH", 90, close=10.0)], set(), True)
    bl = sl.evaluate(repo)["baseline"]
    assert bl["symbol"] == "000300.SH"
    assert bl["stats"]["t1"]["n"] == 1 and bl["stats"]["t1"]["avg"] == 1.0   # 4000→4040


def test_caveat_is_always_present(repo):
    assert "滑点" in sl.evaluate(repo)["caveat"]


# ------------------------------------------------------- 导出


def test_export_csv_is_flat_and_complete(repo):
    sl.record_day("2026-08-17", [
        _cand("600110.SH", 90, close=10.0, factors={"base": 70, "fresh": 15, "vol": 8}),
        _cand("002222.SZ", 55, close=20.0),
    ], {"600110.SH"}, True)
    text = sl.export_csv(repo)
    lines = [ln for ln in text.splitlines() if ln.strip()]
    assert lines[0].split(",") == sl.CSV_HEADER
    assert len(lines) == 3                       # 表头 + 2 行
    assert "f_vol" in lines[0] and "ret_t5" in lines[0]
    body = lines[1]
    assert body.startswith("2026-08-17,600110.SH")
    assert body.endswith("10.0,20.0,30.0")       # 导出时顺手补上的收益


def test_export_csv_on_empty_ledger_still_has_header(repo):
    assert sl.export_csv(repo).splitlines()[0].split(",") == sl.CSV_HEADER


def test_summary_md_carries_everything_needed_to_tune(repo):
    """一键复制的那段必须自带口径/样本量/基准 —— 缺一样, 外部就会读出错误结论。"""
    _seed_two_buckets(repo)
    md = sl.build_summary_md(sl.evaluate(repo), {"t5": {"n": 3, "win_rate": 66.7, "avg": 2.0}})
    for must in ("分层单调性", "因子归因", "按名次", "同期基准", "滑点", "n="):
        assert must in md, f"摘要缺少 {must}"
    assert "AI 优选(R121 台账)" in md
