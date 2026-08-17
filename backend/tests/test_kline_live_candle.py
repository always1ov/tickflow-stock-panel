"""[fork 增强] K线当日实时蜡烛注入: 免费自选档走实时叠加层。"""
import sys
import types
from datetime import date, timedelta
from types import SimpleNamespace

import polars as pl

# 本测试环境未装 TickFlow SDK; kline 模块的导入链会触及它, 打桩绕过(不影响被测逻辑)
if "tickflow" not in sys.modules:
    _stub = types.ModuleType("tickflow")
    _stub.AsyncTickFlow = object
    _stub.TickFlow = object
    sys.modules["tickflow"] = _stub

from app.api.kline import _maybe_inject_live_candle  # noqa: E402


def _request(overlay: pl.DataFrame | None, quote_service=None):
    repo = SimpleNamespace(
        get_watchlist_live=lambda asset_type="stock": overlay if overlay is not None else pl.DataFrame(),
        get_enriched_latest_asset=lambda asset: (pl.DataFrame(), None),
    )
    state = SimpleNamespace(repo=repo, quote_service=quote_service)
    return SimpleNamespace(app=SimpleNamespace(state=state))


def _overlay(d: date, close=11.9):
    return pl.DataFrame({
        "symbol": ["600722.SH"], "date": [str(d)],
        "open": [11.3], "high": [12.0], "low": [11.2], "close": [close],
        "volume": [990_000], "amount": [1.1e7], "change_pct": [0.055],
        "ma5": [11.5], "ma20": [10.9],
    })


def test_overlay_row_becomes_today_candle():
    """免费档: 叠加层有当日行 → 追加为今日实时蜡烛(is_live), 指标一并带上。"""
    rows = [{"date": "2026-08-14", "close": 11.28}]
    out = _maybe_inject_live_candle(_request(_overlay(date.today())), "600722.SH", rows)
    assert len(out) == 2
    live = out[-1]
    assert live["date"] == str(date.today())
    assert live["close"] == 11.9
    assert live["is_live"] is True
    assert live["ma5"] == 11.5, "叠加层的指标字段要带进蜡烛"


def test_stale_overlay_date_is_not_injected():
    """叠加层还是上一交易日的行(周末/未开实时)→ 不注入, 防重复蜡烛。"""
    rows = [{"date": "2026-08-14", "close": 11.28}]
    out = _maybe_inject_live_candle(
        _request(_overlay(date.today() - timedelta(days=3))), "600722.SH", rows)
    assert out == rows


def test_no_overlay_no_quote_service_keeps_rows():
    rows = [{"date": "2026-08-14", "close": 11.28}]
    out = _maybe_inject_live_candle(_request(None), "600722.SH", rows)
    assert out == rows


def test_existing_today_row_is_overwritten_not_duplicated():
    """收盘后日线已落盘, 叠加层仍在 → 覆盖今日行而不是再加一根。"""
    today = str(date.today())
    rows = [{"date": "2026-08-14", "close": 11.28}, {"date": today, "close": 11.5}]
    out = _maybe_inject_live_candle(_request(_overlay(date.today())), "600722.SH", rows)
    assert len(out) == 2
    assert out[-1]["close"] == 11.9
