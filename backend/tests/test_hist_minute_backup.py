"""分时备用接口: 独立配置 / 单只单日兜底 / 校验 / 落盘台账 / 删除清除 / 批量守卫。"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import polars as pl
import pytest

from app.api import kline as kline_api
from app.data_providers.custom.mapper import infer_minute_field_map, map_rows
from app.services import hist_minute_backup as backup

DAY = date(2026, 11, 13)
SYMBOL = "600000.SH"


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(backup.settings, "data_dir", tmp_path)
    backup.clear_caches()
    backup._reset_config()
    yield
    backup.clear_caches()
    backup._reset_config()


def _bars(n: int = 240, day: date = DAY, symbol: str = "600000.SH") -> pl.DataFrame:
    """真实交易时段内的 n 根分钟K (09:30-11:29 + 13:00-14:59)。"""
    stamps: list[datetime] = []
    cursor = datetime(day.year, day.month, day.day, 9, 30)
    for _ in range(min(n, 120)):
        stamps.append(cursor)
        cursor += timedelta(minutes=1)
    cursor = datetime(day.year, day.month, day.day, 13, 0)
    while len(stamps) < n:
        stamps.append(cursor)
        cursor += timedelta(minutes=1)
    return pl.DataFrame({
        "symbol": [symbol] * n,
        "datetime": stamps,
        "open": [10.0] * n,
        "high": [10.1] * n,
        "low": [9.9] * n,
        "close": [10.0] * n,
        "volume": [100.0] * n,
        "amount": [1000.0] * n,
    })


def _install_frame(monkeypatch, df: pl.DataFrame | None = None) -> MagicMock:
    request = MagicMock(return_value=df if df is not None else _bars())
    monkeypatch.setattr(backup, "request_frame", request)
    return request


def _save_config(**overrides):
    body = {
        "url": "https://example.test/hist_minute?code=600519&date=20260101&key=k",
        "method": "GET",
        "symbol_param": "code",
        "date_param": "date",
        "response_path": "",
        "field_map": {},
        "params": {},
        "timeout": 30,
        **overrides,
    }
    return backup.save_source_config(body)


def test_save_and_load_config_roundtrip():
    saved = _save_config(field_map={"t": "datetime"})
    assert saved["symbol_param"] == "code"
    assert saved["date_param"] == "date"
    loaded = backup.load_source_config()
    assert loaded is not None
    assert loaded["field_map"] == {"t": "datetime"}
    assert backup.config_path().exists()


def test_save_rejects_non_http_url():
    with pytest.raises(ValueError):
        _save_config(url="ftp://example.test/x")


def test_delete_config_removes_file():
    _save_config()
    backup.delete_source_config()
    assert backup.load_source_config() is None
    assert not backup.config_path().exists()


def test_fetch_without_config_returns_empty():
    df, display = backup.fetch(SYMBOL, DAY, "stock")
    assert df.is_empty() and display is None


@pytest.mark.parametrize(
    ("symbol", "expected"),
    [
        ("000001.SH", "SH000001"),
        ("399001.SZ", "SZ399001"),
        ("600000.SH", "600000"),
        ("000001.SZ", "000001"),
        ("830799.BJ", "830799"),
        ("SH000001", "SH000001"),
        ("600000", "600000"),
    ],
)
def test_symbol_prefix_conversion(symbol, expected):
    assert backup._upstream_symbol(symbol) == expected


def test_build_url_replaces_code_and_date():
    cfg = backup._normalize_config({
        "url": "https://example.test/hist?code=600519&date=20260101&key=k&freq=1m",
    })
    url, body = backup._build_url(cfg, "000001.SH", DAY)
    assert "code=SH000001" in url
    assert "date=20261113" in url
    assert "key=k" in url and "freq=1m" in url
    assert "600519" not in url and "20260101" not in url
    assert body["code"] == "SH000001" and body["date"] == "20261113"


def test_build_url_supports_placeholders():
    cfg = backup._normalize_config({
        "url": "https://example.test/{symbol}/minute/{date}",
    })
    url, _ = backup._build_url(cfg, "600000.SH", DAY)
    assert "/600000/minute/20261113" in url


def test_points_payload_becomes_ohlc_frame():
    payload = {
        "data": {
            "code": "600519",
            "date": "20261113",
            "points": [
                {"t": "09:30", "p": 1404.0, "vol": 150, "amt": 21060000},
                {"t": "09:31", "p": 1400.5, "vol": 200, "amt": 28000000},
            ],
        },
    }
    df = backup._points_frame(payload, SYMBOL, DAY)
    assert df is not None and df.height == 2
    row = df.row(0, named=True)
    assert row["open"] == row["high"] == row["low"] == row["close"] == 1404.0
    assert row["volume"] == 150.0 and row["amount"] == 21060000.0
    assert row["datetime"] == datetime(2026, 11, 13, 9, 30)


def test_points_payload_absent_returns_none():
    assert backup._points_frame({"data": {"code": "x"}}, SYMBOL, DAY) is None


def test_fetch_persists_minute_partition_and_ledger(monkeypatch):
    _save_config()
    request = _install_frame(monkeypatch)

    df, display = backup.fetch(SYMBOL, DAY, "stock")

    assert display == "分时备用接口"
    assert df.height == 240
    assert request.call_args.args[1] == SYMBOL

    partition = backup.settings.data_dir / "kline_minute" / f"date={DAY}" / "part.parquet"
    assert partition.exists()
    assert backup.written_by(SYMBOL, DAY, "stock") == "分时备用接口"


def test_invalid_rows_are_not_persisted_or_recorded(monkeypatch):
    _save_config()
    zero_price = _bars().with_columns(pl.lit(0.0).alias("close"))
    _install_frame(monkeypatch, zero_price)

    df, display = backup.fetch(SYMBOL, DAY, "stock")

    assert df.is_empty() and display is None
    assert not (backup.settings.data_dir / "kline_minute").exists()
    assert not backup._ledger_path().exists()


def test_short_history_is_rejected(monkeypatch):
    _save_config()
    _install_frame(monkeypatch, _bars(60))
    df, display = backup.fetch(SYMBOL, DAY, "stock")
    assert df.is_empty() and display is None


def test_fetch_failure_is_cached_and_swallowed(monkeypatch):
    _save_config()
    request = MagicMock(side_effect=RuntimeError("upstream 500"))
    monkeypatch.setattr(backup, "request_frame", request)

    df, display = backup.fetch(SYMBOL, DAY, "stock")

    assert df.is_empty() and display is None
    assert request.call_count == 1
    # 失败结果被缓存, 期间不重复打上游
    backup.fetch(SYMBOL, DAY, "stock")
    assert request.call_count == 1


def test_purge_removes_only_rows_written_by_backup(monkeypatch):
    _save_config()
    _install_frame(monkeypatch)
    backup.fetch(SYMBOL, DAY, "stock")

    # 主源写入的另一只标的不应被清除
    from app.services.kline_sync import _write_minute_partition

    other = _bars(symbol="000002.SZ")
    _write_minute_partition(other, backup._minute_dir("stock"))

    removed = backup.purge()

    assert removed == 240
    kept = pl.read_parquet(
        backup.settings.data_dir / "kline_minute" / f"date={DAY}" / "part.parquet"
    )
    assert kept["symbol"].unique().to_list() == ["000002.SZ"]
    assert not backup._ledger_path().exists()
    assert backup.written_by(SYMBOL, DAY, "stock") is None


def test_purge_without_ledger_is_noop():
    assert backup.purge() == 0


def test_infer_minute_field_map_covers_common_aliases():
    mapping = infer_minute_field_map(["Time", "Open", "High", "Low", "Close", "Vol", "Amt"])
    assert set(mapping.values()) == {
        "datetime", "open", "high", "low", "close", "volume", "amount",
    }
    rows = [{"Time": "2026-11-13 09:30:00", "Open": 1, "High": 2, "Low": 0.5, "Close": 1.5, "Vol": 9}]
    df = map_rows(rows, {}, infer=True)
    assert {"datetime", "open", "high", "low", "close", "volume"} <= set(df.columns)


def test_endpoint_helper_falls_back_only_when_primary_empty(monkeypatch):
    repo = MagicMock()
    monkeypatch.setattr(
        kline_api.kline_sync, "fetch_minute_single", lambda *a, **k: pl.DataFrame(),
    )
    expected = _bars()
    monkeypatch.setattr(
        kline_api.hist_minute_backup,
        "fetch",
        lambda *a, **k: (expected, "分时备用接口"),
    )
    df, display = kline_api._fetch_minute_with_backup(
        repo, SYMBOL, DAY, "stock", MagicMock(), False,
    )
    assert df.height == 240
    assert display == "分时备用接口"

    primary = _bars()
    monkeypatch.setattr(
        kline_api.kline_sync, "fetch_minute_single", lambda *a, **k: primary,
    )
    df, display = kline_api._fetch_minute_with_backup(
        repo, SYMBOL, DAY, "stock", MagicMock(), False,
    )
    assert df.height == 240 and display is None


def test_batch_paths_never_reference_hist_minute():
    """硬约束: 批量/定时同步路径不得引用备用接口, 否则会全市场拉取。"""
    root = Path(__file__).resolve().parents[1] / "app"
    for rel in ("services/minute_refresh.py", "jobs/daily_pipeline.py"):
        assert "hist_minute" not in (root / rel).read_text(encoding="utf-8"), rel
