"""[fork R110] 竞价一进二扫描: 首板筛选口径 / 评分维度 / 落盘。"""
from __future__ import annotations

from datetime import date

import polars as pl
import pytest

from app.services import auction_scan as svc


class _FakeRepo:
    def __init__(self, df: pl.DataFrame, d: date) -> None:
        self._df, self._d = df, d

    def get_enriched_latest(self):
        return self._df, self._d


def _enriched(rows: list[dict]) -> pl.DataFrame:
    base = {
        "symbol": "", "name": "", "close": 10.0, "low": 9.5, "volume": 1e6,
        "amount": 1e7, "turnover_rate": 5.0, "signal_limit_up": True,
        "consecutive_limit_ups": 1,
    }
    return pl.DataFrame([{**base, **r} for r in rows])


def test_first_boards_keeps_only_main_board_non_st():
    df = _enriched([
        {"symbol": "600001.SH", "name": "主板首板"},
        {"symbol": "000002.SZ", "name": "深主板首板"},
        {"symbol": "300003.SZ", "name": "创业板"},        # 双创剔除
        {"symbol": "688004.SH", "name": "科创板"},        # 双创剔除
        {"symbol": "600005.SH", "name": "ST风险"},        # ST 剔除
        {"symbol": "600006.SH", "name": "二板", "consecutive_limit_ups": 2},  # 非首板
        {"symbol": "600007.SH", "name": "没涨停", "signal_limit_up": False},
    ])
    rows, d = svc.first_boards(_FakeRepo(df, date(2026, 8, 31)))
    assert {r["symbol"] for r in rows} == {"600001.SH", "000002.SZ"}
    assert d == date(2026, 8, 31)


def test_auction_pct_score_prefers_moderate_gap():
    """本面板回测: 高开≥5%当日为负 —— 温和高开必须比暴力高开得分高。"""
    moderate, _ = svc._pct_score(4.0)
    aggressive, _ = svc._pct_score(9.8)
    flat, _ = svc._pct_score(0.5)
    assert moderate > aggressive
    assert moderate > flat
    assert svc._pct_score(-2.0)[0] < flat


def test_volume_score_scales_with_ratio():
    high, _ = svc._volume_score(70_000, 1_000_000)   # 7%
    mid, _ = svc._volume_score(35_000, 1_000_000)    # 3.5%
    low, _ = svc._volume_score(5_000, 1_000_000)     # 0.5%
    assert high > mid > low
    assert svc._volume_score(None, 1_000_000)[0] > 0   # 缺数据不为零, 只降权


def test_quality_proxy_flags_one_word_board():
    one_word, note = svc._quality_proxy({"close": 11.0, "low": 11.0, "turnover_rate": 0.4})
    normal, _ = svc._quality_proxy({"close": 11.0, "low": 10.2, "turnover_rate": 8.0})
    assert one_word > normal * 0.9
    assert "一字" in note and "买不到" in note


def test_scan_end_to_end_and_low_open_filtered():
    df = _enriched([
        {"symbol": "600001.SH", "name": "温和高开", "close": 11.0, "low": 10.5, "volume": 1e6},
        {"symbol": "600002.SH", "name": "大幅低开", "close": 11.0, "low": 10.5, "volume": 1e6},
    ])
    quotes = [
        {"symbol": "600001.SH", "last_price": 11.44, "volume": 50_000},   # +4%
        {"symbol": "600002.SH", "last_price": 10.34, "volume": 10_000},   # -6% → 出局
    ]
    res = svc.scan(_FakeRepo(df, date(2026, 8, 31)), quotes)
    assert res["total_first_boards"] == 2
    assert [c["symbol"] for c in res["candidates"]] == ["600001.SH"]
    c = res["candidates"][0]
    assert 0 < c["score"] <= 100
    assert {b["dim"] for b in c["breakdown"]} == {"竞价涨幅", "竞价量能", "封板质量", "市场情绪"}
    # 封板质量为替代口径, 必须对外明示
    assert res["quality_proxy"] is True
    assert any(b.get("proxy") for b in c["breakdown"])


def test_save_and_load_roundtrip(tmp_path):
    payload = {"as_of": "2026-08-31", "candidates": [{"symbol": "600001.SH"}]}
    svc.save_scan(tmp_path, payload, date(2026, 8, 31))
    assert svc.load_scan(tmp_path, date(2026, 8, 31)) == payload
    assert svc.load_scan(tmp_path, date(2026, 8, 30)) is None
    assert svc.list_scan_dates(tmp_path) == ["2026-08-31"]


def test_no_first_boards_returns_explained_empty():
    df = _enriched([{"symbol": "600006.SH", "name": "二板", "consecutive_limit_ups": 2}])
    res = svc.scan(_FakeRepo(df, date(2026, 8, 31)), [])
    assert res["candidates"] == []
    assert "无候选" in res["error"]
