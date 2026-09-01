"""[fork R121] AI 优选命中率台账: 落条 / 覆盖当天 / 回看收益 / 汇总。"""
from __future__ import annotations

import polars as pl
import pytest

from app.config import settings
from app.services import ai_pick_ledger as led


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    yield


class _Repo:
    """按 symbol 给几根日线, 供回看收益。"""

    def __init__(self, series: dict[str, list[tuple[str, float]]]):
        self.series = series

    def frame(self, symbol):
        rows = self.series.get(symbol, [])
        return pl.DataFrame({"date": [r[0] for r in rows], "close": [r[1] for r in rows]})


@pytest.fixture
def repo(monkeypatch):
    r = _Repo({
        "600110.SH": [("2026-09-01", 10.0), ("2026-09-02", 11.0),
                      ("2026-09-03", 10.5), ("2026-09-04", 12.0),
                      ("2026-09-05", 12.5), ("2026-09-08", 13.0)],
        "002222.SZ": [("2026-09-01", 20.0), ("2026-09-02", 19.0)],
    })
    monkeypatch.setattr("app.services.stock_analyzer._load_kline",
                        lambda repo, symbol: repo.frame(symbol))
    return r


def test_record_and_read_back():
    out = led.record("2026-09-01", [{"symbol": "600110.SH", "reason": "放量", "verdict": "已核对"}],
                     {"600110.SH": 10.0})
    assert out == {"ok": True, "recorded": 1}
    entries = led._read()
    assert len(entries) == 1 and entries[0]["picks"][0]["entry_close"] == 10.0


def test_rejected_picks_are_not_recorded():
    """被校验驳回的根本没当推荐展示过, 不该进台账拉高/拉低胜率。"""
    out = led.record("2026-09-01", [
        {"symbol": "600110.SH", "verdict": "驳回"},
        {"symbol": "002222.SZ", "verdict": "存疑"},
    ], {"600110.SH": 10.0, "002222.SZ": 20.0})
    assert out["recorded"] == 1
    assert led._read()[0]["picks"][0]["symbol"] == "002222.SZ"


def test_same_day_regeneration_overwrites():
    led.record("2026-09-01", [{"symbol": "600110.SH", "verdict": "已核对"}], {"600110.SH": 10.0})
    led.record("2026-09-01", [{"symbol": "002222.SZ", "verdict": "已核对"}], {"002222.SZ": 20.0})
    entries = led._read()
    assert len(entries) == 1 and entries[0]["picks"][0]["symbol"] == "002222.SZ"


def test_record_without_date_is_refused():
    assert led.record(None, [{"symbol": "600110.SH"}], {})["ok"] is False


def test_forward_returns(repo):
    led.record("2026-09-01", [{"symbol": "600110.SH", "verdict": "已核对"}], {"600110.SH": 10.0})
    out = led.evaluate(repo)
    row = out["detail"][0]
    assert row["t1"] == 10.0     # 10.0 → 11.0
    assert row["t3"] == 20.0     # 第三根 12.0
    assert row["t5"] == 30.0     # 第五根 13.0


def test_forward_returns_missing_future_bars(repo):
    """数据还没走够 T+5 时留空, 不许拿最后一根冒充。"""
    led.record("2026-09-01", [{"symbol": "002222.SZ", "verdict": "已核对"}], {"002222.SZ": 20.0})
    row = led.evaluate(repo)["detail"][0]
    assert row["t1"] == -5.0 and row["t3"] is None and row["t5"] is None


def test_stats_win_rate(repo):
    led.record("2026-09-01", [{"symbol": "600110.SH", "verdict": "已核对"}], {"600110.SH": 10.0})
    led.record("2026-09-02", [{"symbol": "002222.SZ", "verdict": "已核对"}], {"002222.SZ": 20.0})
    stats = led.evaluate(repo)["stats"]
    # 600110 的 T+1 是 +10%, 002222 在 2026-09-02 之后没有数据 → 只有 1 个样本
    assert stats["t1"]["n"] == 1 and stats["t1"]["win_rate"] == 100.0
    assert stats["t1"]["avg"] == 10.0


def test_stats_empty_when_nothing_recorded(repo):
    out = led.evaluate(repo)
    assert out["stats"]["t1"] == {"n": 0, "win_rate": None, "avg": None}
    assert out["recorded_days"] == 0


def test_caveat_is_always_present(repo):
    """胜率必须带口径说明 —— 不说清就是误导。"""
    assert "滑点" in led.evaluate(repo)["caveat"]


def test_entries_are_capped(monkeypatch):
    monkeypatch.setattr(led, "MAX_ENTRIES", 3)
    for d in range(1, 6):
        led.record(f"2026-09-0{d}", [{"symbol": "600110.SH", "verdict": "已核对"}], {"600110.SH": 10.0})
    entries = led._read()
    assert len(entries) == 3 and entries[0]["as_of"] == "2026-09-03"
