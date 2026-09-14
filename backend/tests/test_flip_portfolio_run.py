"""[R327] 转折模拟盘取数层 —— 一趟 IO、用每只票自己的阈值、非股票不丢。"""
from __future__ import annotations

from datetime import date

import polars as pl
import pytest

from app.services import flip_portfolio_run as run_mod


class _Repo:
    """批量接口只认股票; ETF 走逐只, 与真 repo 的行为一致。"""

    def __init__(self, frames: dict[str, pl.DataFrame], etf: set[str] | None = None):
        self.frames = frames
        self.etf = etf or set()
        self.batch_calls = 0
        self.single_calls: list[str] = []

    def resolve_asset_type(self, sym: str) -> str:
        return "etf" if sym in self.etf else "stock"

    def get_daily_batch(self, syms, start, end, columns):
        self.batch_calls += 1
        parts = [self.frames[s].with_columns(pl.lit(s).alias("symbol"))
                 for s in syms if s in self.frames]
        return pl.concat(parts) if parts else pl.DataFrame()

    def get_daily_asset(self, at, sym, start, end, columns=None):
        self.single_calls.append(sym)
        return self.frames.get(sym, pl.DataFrame())


def _bars(closes: list[float], *, lu: list[bool] | None = None) -> pl.DataFrame:
    n = len(closes)
    return pl.DataFrame({
        "date": [date(2026, 1, 1).replace(day=min(i + 1, 28)) for i in range(n)],
        "close": closes,
        "signal_limit_up": lu or [False] * n,
        "signal_limit_down": [False] * n,
    })


@pytest.fixture(autouse=True)
def _no_watchlist_io(monkeypatch):
    monkeypatch.setattr(run_mod.watchlist, "symbol_set", lambda: frozenset({"A", "B"}))
    monkeypatch.setattr(run_mod.watchlist, "list_symbols",
                        lambda: [{"symbol": "A", "name": "甲"}, {"symbol": "B", "name": "乙"}])
    monkeypatch.setattr(run_mod.livermore_service, "get_effective_threshold",
                        lambda s: (0.06, "default"))


def test_R327_股票走一趟批量_不是逐只():
    repo = _Repo({"A": _bars([10.0] * 30), "B": _bars([20.0] * 30)})
    run_mod.run(repo, symbols=["A", "B"])
    assert repo.batch_calls == 1, "两只票该只打一趟批量"
    assert repo.single_calls == [], "股票不该走逐只回退"


def test_R327_非股票逐只回退_不静默丢掉():
    repo = _Repo({"A": _bars([10.0] * 30), "E": _bars([5.0] * 30)}, etf={"E"})
    out = run_mod.run(repo, symbols=["A", "E"])
    assert repo.single_calls == ["E"], "ETF 批量给不了, 必须逐只补"
    assert set(out["symbols"]) == {"A", "E"}
    assert out["missing"] == []


def test_R327_取不到数据的票进_missing_不装作没这只():
    repo = _Repo({"A": _bars([10.0] * 30)})
    out = run_mod.run(repo, symbols=["A", "GONE"])
    assert out["symbols"] == ["A"]
    assert out["missing"] == ["GONE"], "取不到就得说出来, 不能悄悄少一只"


def test_R327_阈值用每只票自己的_不是全局默认(monkeypatch):
    seen: list[str] = []

    def _th(sym: str):
        seen.append(sym)
        return (0.08 if sym == "A" else 0.04), "override"

    monkeypatch.setattr(run_mod.livermore_service, "get_effective_threshold", _th)
    repo = _Repo({"A": _bars([10.0] * 30), "B": _bars([20.0] * 30)})
    run_mod.run(repo, symbols=["A", "B"])
    assert sorted(seen) == ["A", "B"], "每只票都要各问一次自己的阈值"


def test_R327_不给_symbols_就取当前自选():
    repo = _Repo({"A": _bars([10.0] * 30), "B": _bars([20.0] * 30)})
    out = run_mod.run(repo)
    assert set(out["symbols"]) == {"A", "B"}


def test_R327_自选为空时说明原因():
    repo = _Repo({})
    out = run_mod.run(repo, symbols=[])
    assert out["reason"] == "no_watchlist"
    assert out["nav"] == []


def test_R327_涨跌停列缺失时当作能成交_不瞎猜():
    df = _bars([10.0] * 30).drop("signal_limit_up", "signal_limit_down")
    repo = _Repo({"A": df})
    out = run_mod.run(repo, symbols=["A"])
    assert out["reason"] != "no_data"


def test_R327_名称带进流水_不是只有代码():
    repo = _Repo({"A": _bars([10.0, 11.0, 12.0] * 10)})
    out = run_mod.run(repo, symbols=["A"])
    if out["orders"]:
        assert out["orders"][0]["name"] == "甲"


def test_R327_本金与上限原样回显_界面要照口径写出来():
    repo = _Repo({"A": _bars([10.0] * 30)})
    out = run_mod.run(repo, symbols=["A"], capital=250_000, max_positions=7)
    assert out["capital"] == 250_000
    assert out["max_positions"] == 7
