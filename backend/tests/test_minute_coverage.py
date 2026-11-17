"""[R788] 分钟覆盖查询: 最新分钟分区标的数 / 最新日K标的数。"""
from __future__ import annotations

from types import SimpleNamespace

import polars as pl

from app.api import data as data_api


def _write(root, table: str, day: str, symbols: list[str]) -> None:
    part = root / table / f"date={day}"
    part.mkdir(parents=True)
    pl.DataFrame({"symbol": symbols}).write_parquet(part / "part.parquet")


def _request(data_dir):
    repo = SimpleNamespace(store=SimpleNamespace(data_dir=data_dir))
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(repo=repo)))


def test_minute_coverage_uses_latest_partition(tmp_path):
    _write(tmp_path, "kline_daily", "2026-11-16", [f"{i:06d}.SZ" for i in range(10)])
    _write(tmp_path, "kline_minute", "2026-11-13", ["000001.SZ", "000002.SZ"])
    _write(tmp_path, "kline_minute", "2026-11-16", ["000001.SZ"])

    assert data_api.minute_coverage(_request(tmp_path)) == {
        "date": "2026-11-16",
        "covered": 1,
        "universe": 10,
        "ratio": 0.1,
    }


def test_minute_coverage_without_partitions(tmp_path):
    assert data_api.minute_coverage(_request(tmp_path)) == {
        "date": None,
        "covered": 0,
        "universe": 0,
        "ratio": None,
    }
