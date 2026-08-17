"""[fork 增强] R16 今日总览实时化: 实时行作为临时收盘参与判定。"""
import polars as pl

from app.api.today import _watchlist_live_map
from app.services.livermore_service import append_live_bar


# ---------- append_live_bar ----------

def test_newer_live_bar_is_appended():
    closes, dates = append_live_bar([10.0, 10.5], ["2026-08-13", "2026-08-14"],
                                    ("2026-08-17", 11.2))
    assert closes[-1] == 11.2
    assert dates[-1] == "2026-08-17"


def test_same_day_live_bar_not_duplicated():
    """收盘后日线已落盘(日期相同)→ 不追加, 不产生重复当日行。"""
    closes, dates = append_live_bar([10.0, 11.2], ["2026-08-14", "2026-08-17"],
                                    ("2026-08-17", 11.3))
    assert closes == [10.0, 11.2]
    assert len(dates) == 2


def test_no_live_entry_is_noop():
    closes, dates = append_live_bar([10.0], ["2026-08-14"], None)
    assert closes == [10.0] and dates == ["2026-08-14"]


def test_bad_live_values_are_ignored():
    assert append_live_bar([10.0], ["2026-08-14"], ("2026-08-17", None))[0] == [10.0]
    assert append_live_bar([10.0], ["2026-08-14"], ("2026-08-17", 0))[0] == [10.0]
    assert append_live_bar([], [], ("2026-08-17", 11.0)) == ([], [])


# ---------- _watchlist_live_map ----------

class _Repo:
    def __init__(self, frames):
        self._frames = frames

    def get_watchlist_live(self, asset_type="stock"):
        return self._frames.get(asset_type, pl.DataFrame())


def test_live_map_merges_stock_and_etf():
    repo = _Repo({
        "stock": pl.DataFrame({"symbol": ["000001.SZ"], "date": ["2026-08-17"], "close": [11.2]}),
        "etf": pl.DataFrame({"symbol": ["510300.SH"], "date": ["2026-08-17"], "close": [4.5]}),
    })
    m = _watchlist_live_map(repo)
    assert m["000001.SZ"]["close"] == 11.2
    assert m["510300.SH"]["close"] == 4.5


def test_live_map_empty_when_overlay_off():
    """实时行情关闭(叠加层为空)→ 空 map, 总览退回收盘口径。"""
    assert _watchlist_live_map(_Repo({})) == {}


def test_live_map_survives_broken_overlay():
    class _Boom:
        def get_watchlist_live(self, asset_type="stock"):
            raise RuntimeError("boom")
    assert _watchlist_live_map(_Boom()) == {}
