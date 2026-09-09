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
from app.services import opportunity_score as osc
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


def _cand(sym, score, *, axes=None, close=10.0, factors=None):
    return {"symbol": sym, "name": sym, "score": score, "kind": "trend_signal",
            "board": "主板", "close": close, "why": ["x"],
            "axes": axes or {"quality": 90, "timing": 85},
            "factors": factors or {"fresh": 100, "vol_ratio": 92},
            "ctx": {"dur": 1}}


# ------------------------------------------------------- 打分拆分后行为不变


# [R189] 质地轴的两个新因子。不喂的话每只候选都是 partial, 下面几条"全覆盖"
# 的断言就永远测不到 —— 所以默认喂满, 要测缺数据的用例自己去掉。
_RHYTHM_OK = {"level": "building", "basing": {"days": 90}}
# 一段真的上升序列, 长到八条模板都判得出来(要 250 根算 52 周 + 222 根算年线斜率)
_CLOSES_OK = [10.0 * (1.004 ** i) for i in range(290)]


def _trend(signal="转多", dur=1, **kw):
    return {"signal": signal, "duration": dur, "signal_desc": "描述",
            "state": "UT", "side": "多头", "as_of": "2026-08-17", "close": 10.0,
            "rhythm": dict(_RHYTHM_OK), **kw}


_GATE_OK = {"above_ma20": True, "above_ma20_prev": True,
            "close": 10.0, "ma120": 8.0, "ma120_rising": True,
            "closes": _CLOSES_OK, "ret_120d": 0.30}


def _bands_ok() -> dict:
    """[R195] 三档读数 + 几何层。造真的上下轨让几何自己反推, 不手拼。"""
    from app.indicators import keltner as _k
    from app.indicators import keltner_geometry as _kg
    close, atr = 10.0, 0.5
    ma = {"s": 9.8, "m": 9.4, "l": 8.6}
    b = {key: _k.assess(close=close, ma=ma[key], atr=atr, n=_kg.K[key])
         for key in ("s", "m", "l")}
    return dict(b, geo=_kg.geometry(b, close))


def _ex(syms, **extra):
    return {s: {"gate": dict(_GATE_OK), "channel_pct": 0.6,
                "bands": _bands_ok(), **extra} for s in syms}


def test_split_keeps_rank_opportunities_identical():
    """拆成 score+filter 之后, 老接口必须逐字段等于原来的结果。"""
    trends = {f"60000{i}.SH": _trend(dur=i) for i in range(1, 6)}
    names = {s: s for s in trends}
    ex = _ex(names)
    shown, filtered = rank_opportunities(trends, {}, names, extras=ex)
    ranked, _gates = score_opportunities(trends, {}, names, extras=ex)
    again, f2 = filter_opportunities(ranked, 60, 15)
    assert [o["symbol"] for o in shown] == [o["symbol"] for o in again]
    assert filtered == f2


def test_score_opportunities_keeps_sub_threshold_candidates():
    """完整列表必须含被门槛滤掉的票 —— 台账要的正是它们。"""
    trends = {"600001.SH": _trend(dur=1), "600002.SH": _trend("回升", dur=12)}
    names = {s: s for s in trends}
    ex = {"600001.SH": {"gate": dict(_GATE_OK), "channel_pct": 0.58,
                        "vol_ratio": 1.8, "turnover": 5.0},
          # 弱候选: 陈年信号 + 缩量 + 已贴上轨, 三维全差
          "600002.SH": {"gate": dict(_GATE_OK), "channel_pct": 0.98,
                        "vol_ratio": 0.5, "turnover": 0.3}}
    full, _ = score_opportunities(trends, {}, names, extras=ex)
    shown, _ = rank_opportunities(trends, {}, names, extras=ex)
    assert len(full) == 2
    # [R201] 保底会把没过门槛的那只也摆出来, 但**打上 below_bar** ——
    # 台账要的"完整列表"与界面要的"哪几只够格"仍然分得干干净净。
    assert len(shown) == 2
    assert min(o["score"] for o in full) < 60
    # [R220] 门槛按历史分位判, 而分位来自台账 —— 这里台账是空的, 所以门槛
    # 整个失效、谁也不标 below_bar。要验 below_bar 的语义, 得自己喂分位:
    from app.api.today import filter_opportunities
    rows = [dict(o, hist_pct=80.0 if i == 0 else 10.0) for i, o in enumerate(full)]
    shown2, filtered2 = filter_opportunities(rows, min_hist_pct=50, max_show=50)
    assert [o["below_bar"] for o in shown2] == [False, True]
    assert filtered2 == 1


def test_axes_blend_back_to_the_score():
    """[R189] 两根轴必须能按几何平均合回总分, 否则归因表说的不是这套分数。"""
    names = {"600001.SH": "测试"}
    full, _ = score_opportunities({"600001.SH": _trend(dur=1, ret_20d=0.20)}, {}, names,
                                  bench_ret=0.02,
                                  extras=_ex(names, vol_ratio=1.8, turnover=5.0),
                                  bench_ret_120d=0.05)
    o = full[0]
    expect = (o["axes"]["quality"] * o["axes"]["timing"]) ** 0.5
    assert o["score"] == round(expect)
    assert o["partial"] is False


def test_no_clamp_is_needed_in_v2():
    """v1 的理论上限 151 被夹到 100, 榜首一片并列; v2 满分只能靠三维都到峰值。"""
    names = {"600001.SH": "测试"}
    full, _ = score_opportunities(
        # [R201] 满分要求两根轴的因子都读到 —— 红绿节拍也得喂上, 否则质地
        # 覆盖率不满, 置信系数会把满分削掉一角(那正是本版要的行为)。
        {"600001.SH": dict(_trend(dur=1, ret_20d=0.16),
                           rhythm={"level": "building", "basing": {"days": 120}})},
        {"600001.SH": {"signal": "buy", "confidence": 90}}, names, bench_ret=0.02,
        extras={"600001.SH": {"gate": dict(_GATE_OK), "channel_pct": 0.58,
                              "vol_ratio": 1.8, "turnover": 5.0,
                              # [R201] 满分现在还要求"因子都读到了"(置信系数),
                              # 缺通道几何就不是满分 —— 那正是这一版要修的
                              # 「缺数据反而排在前面」。
                              "bands": {"geo": {"spread": 2.5,
                                                "accel": {"a1": 0.12}},
                                        "runs": {"compress_days": 120}},
                              "win": {"rate": 0.8, "n": 10},
                              "mainline": {"rank": 1, "member": "AI",
                                           "limit_up_count": 5, "also": []}}})
    o = full[0]
    # 两根轴都到了峰值 —— v1 那种"加到 151 再夹回 100"的事不存在了
    assert o["axes"]["quality"] == 100.0 and o["axes"]["timing"] == 100.0
    # [R201] 但这份夹具的 closes 判不出完整八条模板, 质地覆盖率不满, 于是
    # 置信系数把满分削掉一角 —— **这正是本版要的行为**: 读不全就不给满分,
    # 否则"读不到"会变成优势(实测过: 只有两个因子的票拿 100 排第一)。
    from app.services import opportunity_score as _osc
    cov = o["coverage"]
    assert cov["quality"] < 1.0 and cov["timing"] == 1.0
    assert o["score"] == round(100 * _osc.confidence(cov["quality"], cov["timing"]))
    assert o["score"] < 100
    assert "clamp" not in (o.get("factors") or {})
    # 注记堆满也不会把分数推过 100 —— 它们压根不参与
    assert len(o["notes"]) >= 3


def test_partial_coverage_is_recorded_for_the_ledger():
    """整个维度缺席时台账要留痕, 否则事后分不清"分低"和"没数据"。"""
    names = {"600001.SH": "测试"}
    full, _ = score_opportunities({"600001.SH": _trend(dur=1)}, {}, names,
                                  extras={"600001.SH": {"gate": dict(_GATE_OK)}})
    o = full[0]
    assert o["partial"] is True
    assert o["ctx"]["partial"] is True


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


def test_axis_attribution_splits_high_mid_low_and_missing(repo):
    """[R134] 归因从"加分组/扣分组"改成"高分组/低分组" —— 轴分是 0~100 的
    连续量, 没有正负, 硬套 v1 的三分法会把整批记录都归进"加分组"。
    [R189] 两根轴走的是同一套归因代码, 换的只是记哪几个键。"""
    sl.record_day("2026-08-17", [
        # 涨的那只: 两轴都高
        _cand("600110.SH", 90, close=10.0, axes={"quality": 95, "timing": 92}),
        # 跌的那只: 时机低、质地中等、**时机缺席**分不到高低组
        _cand("002222.SZ", 70, close=20.0, axes={"quality": 60, "timing": 20}),
        _cand("000001.SZ", 65, close=20.0, axes={"quality": 60, "timing": None}),
    ], set(), True)
    out = sl.evaluate(repo)
    timing = next(f for f in out["factors"] if f["key"] == "timing")
    assert timing["plus"]["count"] == 1 and timing["minus"]["count"] == 1
    assert timing["plus"]["stats"]["t1"]["win_rate"] == 100.0
    assert timing["minus"]["stats"]["t1"]["win_rate"] == 0.0
    assert timing["none"]["count"] == 1, "缺席那一列是数据覆盖率的体检, 不能丢"
    quality = next(f for f in out["factors"] if f["key"] == "quality")
    assert quality["mid"]["count"] == 2


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
        _cand("600110.SH", 90, close=10.0),
        _cand("002222.SZ", 55, close=20.0),
    ], {"600110.SH"}, True)
    text = sl.export_csv(repo)
    lines = [ln for ln in text.splitlines() if ln.strip()]
    assert lines[0].split(",") == sl.CSV_HEADER
    assert len(lines) == 3                       # 表头 + 2 行
    assert "dim_timing" in lines[0] and "sub_vol_ratio" in lines[0]
    assert "scoring_version" in lines[0] and "ret_t5" in lines[0]
    body = lines[1]
    assert body.startswith(f"2026-08-17,{sl.SCORING_VERSION},600110.SH")  # 口径版本紧跟日期
    assert body.endswith("10.0,20.0,30.0")       # 导出时顺手补上的收益


def test_export_csv_on_empty_ledger_still_has_header(repo):
    assert sl.export_csv(repo).splitlines()[0].split(",") == sl.CSV_HEADER


def test_summary_md_carries_everything_needed_to_tune(repo):
    """一键复制的那段必须自带口径/样本量/基准 —— 缺一样, 外部就会读出错误结论。"""
    _seed_two_buckets(repo)
    md = sl.build_summary_md(sl.evaluate(repo), {"t5": {"n": 3, "win_rate": 66.7, "avg": 2.0}})
    for must in ("分层单调性", "维度归因", "按名次", "同期基准", "滑点", "n=",
                 "打分口径 v"):
        assert must in md, f"摘要缺少 {must}"
    assert "AI 优选(R121 台账)" in md


# ------------------------------------------------------- [R136] 记账路径必须齐全


def test_pipeline_takes_a_ledger_snapshot_after_data_lands():
    """台账原来只有两条记账路径: 用户打开页面, 或定时导读跑起来。

    两条都靠不住 —— 没开页面、没配 AI 的那天就永久少一天样本, 而事后统计漏掉的
    补不回来。数据管道是唯一保证每个数据日都被走到的地方, 必须在那里也记一次。
    """
    import inspect
    from app.jobs import daily_pipeline as dp
    src = inspect.getsource(dp.run_now)
    assert "_build_overview" in src, "数据管道结尾必须走一次总览以落台账快照"
    assert "not fatal" in src or "logger.exception" in src, "记账失败不能判管道失败"


def test_scheduled_today_ai_also_builds_the_overview():
    import inspect
    from app.jobs import daily_pipeline as dp
    assert "_build_overview" in inspect.getsource(dp._run_scheduled_today_ai)
