"""[R156] 今日总览提速: 历史胜率批量化 + ATR 走快照 + 分段计时。

用户报「今日总览加载显示得好慢」。本地没有数据集无法压测, 但从代码上能证明的
一条: 候选上限 80 只, 每只单独扫一趟 320 日历日 parquet 算胜率 —— 80 趟扫盘。
这组测试钉三件事: ①批量结果与逐只结果**一字不差**; ②批量只读一趟盘;
③总览响应带分段耗时, 下次"慢"有数可看。
"""
from __future__ import annotations

import inspect
import math
from datetime import date, timedelta

import polars as pl
import pytest

from app.services import livermore_service as lv


def _series(seed: int, n: int = 300) -> list[float]:
    """大幅锯齿: 每 25 天翻一次方向, 幅度 ±15% —— 保证六态里有多次多头进入事件。"""
    closes, px, up = [], 10.0 + seed, True
    for i in range(n):
        if i % 25 == 0:
            up = not up
        px *= (1 + 0.006) if up else (1 - 0.006)
        px *= 1 + 0.002 * math.sin(i * 0.7 + seed)   # 一点噪声, 别太规整
        closes.append(round(px, 3))
    return closes


def _frame(symbols: list[str]) -> pl.DataFrame:
    end = date.today()
    rows = []
    for k, sym in enumerate(symbols):
        closes = _series(k)
        for i, c in enumerate(closes):
            rows.append({"symbol": sym, "date": end - timedelta(days=len(closes) - i),
                         "close": c})
    return pl.DataFrame(rows)


class _Repo:
    def __init__(self, symbols):
        self.df = _frame(symbols)
        self.batch_calls = 0
        self.single_calls = 0

    def resolve_asset_type(self, symbol):  # noqa: ARG002
        return "stock"

    def get_daily_batch(self, symbols, start, end, columns=None):  # noqa: ARG002
        self.batch_calls += 1
        df = self.df.filter(pl.col("symbol").is_in(symbols))
        return df.select(columns) if columns else df

    def get_daily_asset(self, asset_type, symbol, start, end, columns=None):  # noqa: ARG002
        self.single_calls += 1
        df = self.df.filter(pl.col("symbol") == symbol)
        return df.select(columns) if columns else df


@pytest.fixture(autouse=True)
def _clear_cache():
    lv._WIN_CACHE.clear()
    yield
    lv._WIN_CACHE.clear()


SYMS = ["600000.SH", "000001.SZ", "300750.SZ"]


def test_batch_equals_per_symbol():
    """批量与逐只是同一个纯函数、同一窗口、同一阈值 —— 结果必须逐票相等。"""
    repo = _Repo(SYMS)
    single = {s: lv.bullish_win_rate_for_symbol(repo, s) for s in SYMS}
    lv._WIN_CACHE.clear()
    batch = lv.bullish_win_rates_for_symbols(repo, SYMS)
    for s in SYMS:
        assert batch.get(s) == single[s], s
    # 用例本身得有意义: 至少一只票算得出胜率
    assert any(v is not None for v in single.values())


def test_batch_reads_once_not_n_times():
    repo = _Repo(SYMS)
    lv.bullish_win_rates_for_symbols(repo, SYMS)
    assert repo.batch_calls == 1
    assert repo.single_calls == 0          # 股票不走逐只路径


def test_batch_result_is_memoized_per_symbol_and_day(monkeypatch):
    repo = _Repo(SYMS)
    first = lv.bullish_win_rates_for_symbols(repo, SYMS)
    # 第二次连 compute 都不该跑
    monkeypatch.setattr(lv, "compute", lambda *a, **k: (_ for _ in ()).throw(AssertionError("compute called")))
    again = lv.bullish_win_rates_for_symbols(repo, SYMS)
    assert again == first


def test_non_stock_falls_back_to_single_path():
    class _Mixed(_Repo):
        def resolve_asset_type(self, symbol):
            return "etf" if symbol.startswith("510") else "stock"

    syms = ["600000.SH", "510300.SH"]
    repo = _Mixed(syms)
    lv.bullish_win_rates_for_symbols(repo, syms)
    assert repo.batch_calls == 1
    assert repo.single_calls == 1          # 只有 ETF 那一只走逐只


def test_unknown_or_short_symbols_are_skipped():
    repo = _Repo(SYMS)
    out = lv.bullish_win_rates_for_symbols(repo, ["NOPE.SH", *SYMS])
    assert "NOPE.SH" not in out


# ---------------------------------------------------------------- 总览侧


def test_overview_uses_batch_win_rate_not_per_symbol_loop():
    from app.api import today
    src = inspect.getsource(today._build_overview)
    assert "bullish_win_rates_for_symbols" in src
    assert "bullish_win_rate_for_symbol(" not in src, "不许再长回逐只扫盘的循环"


def test_overview_reads_atr_from_snapshot_first():
    from app.api import today
    src = inspect.getsource(today._build_overview)
    assert "atr_map" in src and "get_enriched_latest" in src


def test_stages_reports_total_and_per_stage(monkeypatch):
    from app.api.today import _Stages
    st = _Stages()
    st.mark("a")
    st.mark("b")
    perf = st.done()
    assert set(perf) == {"total_ms", "stages_ms"}
    assert set(perf["stages_ms"]) == {"a", "b"}
    assert perf["total_ms"] >= max(perf["stages_ms"].values())


def test_overview_response_carries_perf():
    from app.api import today
    src = inspect.getsource(today._build_overview)
    assert '"perf": perf' in src
