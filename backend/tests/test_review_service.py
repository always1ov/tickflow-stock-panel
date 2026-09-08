"""[fork 增强] R48 逐日复盘(决策台「趋势」「结论」两列点进去看的那份数据)。

这个功能唯一的价值在于**它和列里显示的是同一套判定**。如果复盘表算的是另一
套口径, 用户翻历史得出的结论就用不到今天的那两列上, 整个功能是负价值。
所以下面的测试几乎全在守"同源":同一个状态机、同一组通道公式、同一个阈值。

另一半守的是别把半截数据当结论: 不足 120 根不给长期档、末尾不足 5 天不进
后验统计。
"""
from __future__ import annotations

import math
from datetime import date, timedelta

import polars as pl
import pytest

from app.indicators import keltner as k
from app.services import review_service as rs


def _series(n=260, *, start=100.0, wave=0.0, drift=0.0):
    """构造 n 根日线。wave 给正弦波动(用来把价格推到通道边上), drift 给趋势。"""
    closes = []
    for i in range(n):
        closes.append(start + drift * i + wave * math.sin(i / 6.0))
    return closes


def _frame(closes, *, limit_up_at=(), with_cols=True):
    n = len(closes)
    d0 = date(2025, 1, 1)
    dates = [d0 + timedelta(days=i) for i in range(n)]
    df = pl.DataFrame({"date": dates, "close": closes})
    df = df.with_columns([
        pl.col("close").rolling_mean(20).alias("ma20"),
        pl.col("close").rolling_mean(60).alias("ma60"),
        pl.lit(3.0).alias("atr_14"),
        (pl.col("close") / pl.col("close").shift(1) - 1).alias("change_pct"),
    ])
    if not with_cols:
        return df
    lu = [i in limit_up_at for i in range(n)]
    streak, run = [], 0
    for f in lu:
        run = run + 1 if f else 0
        streak.append(run)
    return df.with_columns([
        pl.Series("signal_limit_up", lu),
        pl.Series("signal_limit_down", [False] * n),
        pl.Series("signal_broken_limit_up", [False] * n),
        pl.Series("consecutive_limit_ups", streak),
    ])


class _Repo:
    def __init__(self, df):
        self._df = df
        self.asked_columns = None

    @staticmethod
    def resolve_asset_type(symbol):
        return "stock"

    def get_daily_asset(self, asset_type, symbol, start, end, columns=None):
        self.asked_columns = columns
        df = self._df
        if columns:
            df = df.select([c for c in columns if c in df.columns])
        return df


def _review(df, days=120):
    return rs.review_for_symbol(_Repo(df), "600000.SH", days)


# ---------- 与决策台同源 ----------

def test_verdict_matches_the_shared_keltner_rules():
    """复盘表里每一天的结论必须等于把当天的读数交给 keltner.verdict ——
    这里另写一套判定的话, 翻历史得出的经验就套不到今天那一列上。"""
    out = _review(_frame(_series(wave=14.0)))
    checked = 0
    for r in out["rows"]:
        bands = {key: {"pos": b["pos"], "pos_cn": b["pos_cn"]}
                 for key, b in r["bands"].items()}
        expect = k.verdict(bands)
        if expect is None:
            assert r["verdict"] is None
        else:
            assert r["verdict"]["code"] == expect["code"]
            checked += 1
    assert checked > 0, "构造的数据要真的触到轨, 否则这个测试什么都没验"


def test_trend_states_come_from_the_same_state_machine():
    from app.indicators.livermore import compute
    from app.services.livermore_service import get_effective_threshold

    closes = _series(wave=20.0, drift=0.1)
    out = _review(_frame(closes))
    thr, _src = get_effective_threshold("600000.SH")
    dates = [str(date(2025, 1, 1) + timedelta(days=i)) for i in range(len(closes))]
    want = {str(s["date"]): s["state"] for s in compute(closes, dates, thr)["steps"]}
    for r in out["rows"]:
        assert r["trend"]["state"] == want[r["date"]]


def test_the_user_adjusted_threshold_is_respected(monkeypatch):
    """六态阈值是用户可以自己调的。复盘用默认值而列里用调过的值, 两边对不上。"""
    seen = {}

    def _fake(sym):
        seen["sym"] = sym
        return 0.20, "manual"

    monkeypatch.setattr("app.services.livermore_service.get_effective_threshold", _fake)
    out = _review(_frame(_series(wave=20.0)))
    assert out["threshold"] == 0.20 and out["threshold_source"] == "manual"
    assert seen["sym"] == "600000.SH"


def test_band_keys_are_the_three_shared_bands():
    out = _review(_frame(_series(wave=14.0)))
    for r in out["rows"]:
        assert set(r["bands"]) <= set(k.BAND_KEYS)


# ---------- 涨停 ----------

def test_limit_ups_come_from_the_precomputed_column_not_a_local_rule():
    """涨跌停幅度按板块和 ST 状态分档(还有 2026-07-06 那次 ST 规则变更),
    在这里自己按 9.9% 判一遍必然和 pipeline 对不上。"""
    out = _review(_frame(_series(), limit_up_at={200, 201, 202}))
    ups = [r for r in out["rows"] if r["limit_up"]]
    assert len(ups) == 3
    assert out["stats"]["limit_ups"] == 3
    assert out["stats"]["max_streak"] == 3


def test_limit_ups_are_grouped_by_the_trend_state_they_happened_in():
    """复盘最直接的一问: 这只票的涨停是趋势里出的, 还是下跌途中的反抽。"""
    out = _review(_frame(_series(wave=20.0, drift=0.1), limit_up_at={200, 230}))
    got = out["stats"]["limit_up_states"]
    assert sum(x["n"] for x in got) == 2
    assert all(x["state_cn"] for x in got)


def test_missing_limit_columns_degrade_to_false_not_a_crash():
    """指数和 ETF 没有涨停列 —— 这时候该是"没有涨停", 不是 500。"""
    out = _review(_frame(_series(), with_cols=False))
    assert out["stats"]["limit_ups"] == 0
    assert all(r["limit_up"] is False for r in out["rows"])


# ---------- 窗口与暖机 ----------

def test_long_band_is_absent_until_120_bars_are_available():
    """不足 120 根时长期档留空, 不拿 60 根算个假的"120 日均线"出来。"""
    out = _review(_frame(_series(n=100, wave=14.0)), days=100)
    assert all("l" not in r["bands"] for r in out["rows"])


def test_warmup_bars_are_computed_but_not_returned():
    """多取的那段只参与算均线和状态机, 不进结果 —— 否则用户要的是 120 天,
    看到的是 250 天。"""
    out = _review(_frame(_series(n=260)), days=120)
    assert out["days"] == 120 and len(out["rows"]) == 120


def test_rows_are_newest_first():
    """打开就该先看到最近几天, 那才是要复盘的部分。"""
    out = _review(_frame(_series()))
    dates = [r["date"] for r in out["rows"]]
    assert dates == sorted(dates, reverse=True)


@pytest.mark.parametrize("asked,expect", [
    (1, 10),                     # 太短的表看不出节奏, 抬到 10
    (9999, rs.MAX_DAYS),         # 太长的表本身就没法读
    (0, rs.DEFAULT_DAYS),        # 0/None 视为"没指定", 走默认
    (None, rs.DEFAULT_DAYS),
])
def test_days_is_clamped_to_a_sane_range(asked, expect):
    out = _review(_frame(_series(n=400)), days=asked)
    assert out["days"] == expect


# ---------- 后验统计 ----------

def test_outcomes_skip_days_without_a_full_forward_window():
    """末尾不足 5 天的段没法知道后来走成什么样 —— 拿半截数据凑样本会让最近的
    结论看起来总是"刚好没涨"。

    [R177] 改成按段之后这里分成了两个数: 段仍然**计次数**(它确实发生过),
    只是不计收益。把它从次数里也抹掉会答错"这只票出现过几次"。
    """
    out = _review(_frame(_series(wave=14.0)))
    for o in out["outcomes"]:
        assert o["scored"] <= o["n"], "已知结果的段不可能多于总段数"
        if o["scored"] == 0:
            assert o["avg_fwd"] is None, "一段都没兑现就不能给均值"
    # 刻意不要求"必须存在没兑现的段" —— 按段之后这种情况反而少见, 而这正是
    # 改动带来的好处: 只有**最后一段的起点**落在末尾 5 天内才会丢, 按天时是
    # 末尾 5 天全丢。机制本身由 test_review_episodes.py 单独验。


def test_outcomes_report_raw_counts_not_a_dressed_up_win_rate():
    """半年内同一档往往只有个位数样本。报次数和均值可以, 折算成一个
    百分比胜率会让人当成统计结论用。"""
    out = _review(_frame(_series(wave=14.0)))
    for o in out["outcomes"]:
        assert set(o) == {"key", "label", "code", "title", "tone",
                          "n", "avg_days", "scored", "avg_fwd", "win"}
        assert o["n"] >= 1 and 0 <= o["win"] <= o["scored"]
        assert o["avg_fwd"] is None or isinstance(o["avg_fwd"], float)
        # 就是没有胜率字段 —— 个位数样本折算成百分比会被当统计结论用
        assert "win_rate" not in o


def test_outcomes_are_ordered_by_sample_size():
    out = _review(_frame(_series(wave=14.0)))
    ns = [o["n"] for o in out["outcomes"]]
    assert ns == sorted(ns, reverse=True)


# ---------- 退化 ----------

def test_empty_symbol_and_no_data_return_an_error_not_an_empty_shell():
    """返回一堆 0 会被当成"这只票半年没涨停过"; 说不出来就要说不出来。"""
    assert "error" in rs.review_for_symbol(_Repo(pl.DataFrame()), "", 120)
    assert "error" in rs.review_for_symbol(_Repo(pl.DataFrame()), "600000.SH", 120)


def test_repo_failure_is_reported_not_raised():
    class _Broken:
        @staticmethod
        def resolve_asset_type(symbol):
            return "stock"

        @staticmethod
        def get_daily_asset(*a, **kw):
            raise RuntimeError("boom")

    assert "error" in rs.review_for_symbol(_Broken(), "600000.SH", 120)


# ---------- 路由接线 ----------

def _client(repo):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api.stock_analysis import router

    app = FastAPI()
    app.include_router(router)
    app.state.repo = repo
    return TestClient(app)


def test_route_passes_symbol_and_days_through_as_query_params():
    """接线错了(比如把依赖写在装饰器下面)会让 FastAPI 把服务对象当成查询参数,
    表现是 422 而不是报错 —— 这类错只有真发一次请求才看得出来。"""
    r = _client(_Repo(_frame(_series(n=300)))).get(
        "/api/stock-analysis/review", params={"symbol": "600000.SH", "days": 60})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["symbol"] == "600000.SH" and body["days"] == 60
    assert len(body["rows"]) == 60


@pytest.mark.parametrize("params", [
    {"symbol": "600000.SH", "days": 5},        # 低于下限
    {"symbol": "600000.SH", "days": 9999},     # 高于上限
    {},                                        # 缺 symbol
])
def test_route_rejects_out_of_range_input(params):
    """范围在路由上就挡掉, 别让一个 9999 天的请求跑进去扫十年 parquet。"""
    r = _client(_Repo(_frame(_series()))).get("/api/stock-analysis/review", params=params)
    assert r.status_code == 422


def test_blank_symbol_is_a_400_not_a_silent_empty_result():
    r = _client(_Repo(_frame(_series()))).get(
        "/api/stock-analysis/review", params={"symbol": "   "})
    assert r.status_code == 400


# ---------- [R51] 每天的后验 ----------

def test_each_row_carries_its_own_forward_return():
    """结论视图按段展示时要说清这一段兑现没有 —— 只有一个全票平均数
    看不出是哪一次。"""
    out = _review(_frame(_series(wave=14.0)))
    rows = out["rows"]
    by_date = {r["date"]: r for r in rows}
    older = [r for r in rows if r["fwd"] is not None]
    assert older, "除了最近 5 天, 其余都该有结果"
    r = older[0]
    # rows 是新→旧, 所以"之后 5 天"在列表里是更靠前的位置
    i = rows.index(r)
    later = rows[i - rs.FORWARD_DAYS]
    # close 是四舍五入到分的展示值, fwd 走的是原始收盘 —— 容差放到两个分位
    assert r["fwd"] == pytest.approx(later["close"] / r["close"] - 1, abs=1e-3)
    assert all(by_date[x["date"]]["fwd"] is None for x in rows[:rs.FORWARD_DAYS]), \
        "最近 5 天还不知道结果, 不该编一个数出来"


def test_row_forward_returns_agree_with_the_outcome_summary():
    """两处算的是同一件事, 对不上就说明有一处走了另一套口径。

    [R177] 按段之后, 摘要只该用**每段第一天**的 fwd —— 段内其余那些天的
    前瞻窗口和它重叠, 算进去就等于把同一次数了好几遍。
    """
    out = _review(_frame(_series(wave=14.0)))
    old_to_new = list(reversed(out["rows"]))      # rows 是新→旧, 这里要按时间正序

    want: dict[str, list[float]] = {}
    prev = None
    for r in old_to_new:
        code = (r.get("verdict") or {}).get("code")
        if code is not None and code != prev and r["fwd"] is not None:
            want.setdefault(code, []).append(r["fwd"])   # 只取段起点
        prev = code

    for o in out["outcomes"]:
        if o["scored"] == 0:
            continue
        got = want[o["code"]]
        assert o["scored"] == len(got), f"{o['code']}: 段起点数对不上"
        assert o["avg_fwd"] == pytest.approx(sum(got) / len(got), abs=1e-3)
