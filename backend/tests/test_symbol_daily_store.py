"""[fork R491] 按个股另存的日 K 副本 —— 钉住「快」靠的那几件事, 以及「快了但结果没变」。

用户: 「按个股另存一份日K副本, 做吧」。每只票第一次打开要把一千来个日文件逐个打开,
副本把它变成一个文件 + 最近十来个日文件。风险全在「副本过期了还在用」, 所以大半用例
是在各种改库的方式下, 断言拿到的还是库里此刻的数。
"""
from __future__ import annotations

import threading
import time
from datetime import date, timedelta
from pathlib import Path

import polars as pl
import pytest

from app.parquet import ENRICHED_STORAGE_SCHEMA
from app.services import ohlcv_history as oh
from app.services import symbol_daily_store as sds

SYMS = ["600000.SH", "600001.SH", "000002.SZ"]


def _days(n: int, last: date = date(2026, 9, 23)) -> list[date]:
    out, d = [], last
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d -= timedelta(days=1)
    return out[::-1]


def _write_day(root: Path, d: date, syms=SYMS, bump: float = 0.0, src="kline_daily_enriched") -> None:
    n = len(syms)
    base = [10.0 + i + (d.toordinal() % 13) * 0.1 + bump for i in range(n)]
    df = pl.DataFrame({
        "symbol": syms, "date": [d] * n,
        "open": base, "high": [x + 0.3 for x in base], "low": [x - 0.3 for x in base], "close": base,
        "volume": [1e6 + i for i in range(n)], "amount": [1e7] * n,
        "raw_close": base, "raw_high": base, "raw_low": base, "turnover_rate": [1.0] * n,
        "consecutive_limit_ups": [0] * n, "consecutive_limit_downs": [0] * n, "quote_ts": [0] * n,
    }).cast(ENRICHED_STORAGE_SCHEMA)
    p = root / src / f"date={d}"
    p.mkdir(parents=True, exist_ok=True)
    df.write_parquet(p / "part.parquet")


@pytest.fixture
def store(tmp_path):
    days = _days(40)
    for d in days:
        _write_day(tmp_path, d)
    return tmp_path, days


def _direct(root: Path, sym: str, end: date, src="kline_daily_enriched") -> pl.DataFrame:
    """原路: 扫全部日文件。"""
    files = sorted(str(p) for p in (root / src).glob("date=*/*.parquet"))
    return sds._scan(files, sym, oh.COLS).filter(pl.col("date") <= end)


class _Counter:
    """数一次读取打开了几个日文件。"""

    def __init__(self, monkeypatch):
        self.files = 0
        real = sds._scan

        def scan(files, symbol, cols):
            self.files += len(files)
            return real(files, symbol, cols)
        monkeypatch.setattr(sds, "_scan", scan)


END = date(2026, 9, 24)


def test_R491_第一次建副本_以后只开副本加最近十来个日文件(store, monkeypatch):
    root, days = store
    c = _Counter(monkeypatch)
    a = sds.read(root, "stock", "600000.SH", END, oh.COLS)
    assert c.files == len(days), "第一次: 截止日前的建副本 + 最近 10 天现读, 合起来正好全部"
    assert (root / sds.CACHE_DIRNAME / "stock" / "600000.SH.parquet").exists()
    c.files = 0
    b = sds.read(root, "stock", "600000.SH", END, oh.COLS)
    assert c.files == sds.TAIL_DAYS + 2, "以后: 最近 10 天 + 抽查首尾两天"
    assert a.equals(b) and a.equals(_direct(root, "600000.SH", END))


def test_R491_与直接扫分区逐位一致_每只票(store):
    root, _ = store
    for s in SYMS:
        sds.read(root, "stock", s, END, oh.COLS)            # 建
        assert sds.read(root, "stock", s, END, oh.COLS).equals(_direct(root, s, END)), s


def test_R491_新进一天_截止日不挪_新的一天照样读到(store, monkeypatch):
    root, days = store
    sds.read(root, "stock", "600000.SH", END, oh.COLS)
    meta0 = (root / sds.CACHE_DIRNAME / "stock" / "600000.SH.json").read_text()
    new_day = date(2026, 9, 24)
    _write_day(root, new_day)
    c = _Counter(monkeypatch)
    got = sds.read(root, "stock", "600000.SH", date(2026, 9, 25), oh.COLS)
    assert (root / sds.CACHE_DIRNAME / "stock" / "600000.SH.json").read_text() == meta0, \
        "每进一天截止日就挪 = 副本天天作废, 等于没做"
    assert c.files == sds.TAIL_DAYS + 1 + 2
    assert got["date"][-1] == new_day
    assert got.equals(_direct(root, "600000.SH", date(2026, 9, 25)))


def test_R491_除权后全部日文件重写_复权价变了就重建(store):
    """管道遇到除权会把这只票的全部日期重算重写 —— 副本必须跟上, 不能拿旧价。"""
    root, days = store
    sds.read(root, "stock", "600000.SH", END, oh.COLS)
    for d in days:
        _write_day(root, d, bump=-1.5)                     # 前复权: 以前的价整体下移
    got = sds.read(root, "stock", "600000.SH", END, oh.COLS)
    assert got.equals(_direct(root, "600000.SH", END))


@pytest.mark.parametrize("which", ["first", "last"])
def test_R491_抽查首尾_任一根对不上就重建(store, which):
    """前复权改前面(首根对不上), 后复权改后面(截止日那根对不上), 两头都得抽。"""
    root, days = store
    sds.read(root, "stock", "600000.SH", END, oh.COLS)
    cutoff = days[-sds.TAIL_DAYS - 1]
    _write_day(root, days[0] if which == "first" else cutoff, bump=0.07)
    assert sds.read(root, "stock", "600000.SH", END, oh.COLS).equals(_direct(root, "600000.SH", END))


def test_R491_补历史_补缺口_删一天_分区数一变就重建(store):
    root, days = store
    sds.read(root, "stock", "600000.SH", END, oh.COLS)
    _write_day(root, days[0] - timedelta(days=7))           # 往前补历史
    assert sds.read(root, "stock", "600000.SH", END, oh.COLS).equals(_direct(root, "600000.SH", END))
    import shutil
    shutil.rmtree(root / "kline_daily_enriched" / f"date={days[5]}")   # 中间删掉一天
    assert sds.read(root, "stock", "600000.SH", END, oh.COLS).equals(_direct(root, "600000.SH", END))


def test_R491_中间某天被改_抽查抽不到_最多7天后重建(store, monkeypatch):
    root, days = store
    sds.read(root, "stock", "600000.SH", END, oh.COLS)
    _write_day(root, days[10], bump=0.5)
    stale = sds.read(root, "stock", "600000.SH", END, oh.COLS)
    assert not stale.equals(_direct(root, "600000.SH", END)), "这正是抽查的盲区, 只靠到期兜底"
    t = time.time()
    monkeypatch.setattr(sds.time, "time", lambda: t + sds.MAX_AGE_SECONDS + 1)
    assert sds.read(root, "stock", "600000.SH", END, oh.COLS).equals(_direct(root, "600000.SH", END))


def test_R491_最近几天的分区被删_副本不受影响_结果照样对(store):
    import shutil
    root, days = store
    sds.read(root, "stock", "600000.SH", END, oh.COLS)
    for d in days[-3:]:
        shutil.rmtree(root / "kline_daily_enriched" / f"date={d}")
    assert sds.read(root, "stock", "600000.SH", END, oh.COLS).equals(_direct(root, "600000.SH", END))


def test_R491_副本坏了_照样拿到对的数(store):
    root, _ = store
    sds.read(root, "stock", "600000.SH", END, oh.COLS)
    (root / sds.CACHE_DIRNAME / "stock" / "600000.SH.parquet").write_bytes(b"garbage")
    assert sds.read(root, "stock", "600000.SH", END, oh.COLS).equals(_direct(root, "600000.SH", END))
    (root / sds.CACHE_DIRNAME / "stock" / "600000.SH.json").write_text("{not json")
    assert sds.read(root, "stock", "600000.SH", END, oh.COLS).equals(_direct(root, "600000.SH", END))


def test_R491_读副本时出了意外_返回None交给原路(store, monkeypatch):
    root, _ = store

    def boom(*_a, **_k):
        raise RuntimeError("polars 出错")
    monkeypatch.setattr(sds, "_scan", boom)
    assert sds.read(root, "stock", "600000.SH", END, oh.COLS) is None


def test_R491_写不了盘_这一次照样拿到对的数(store, monkeypatch):
    root, _ = store

    def boom(*_a, **_k):
        raise OSError("read-only")
    monkeypatch.setattr(sds, "_write_atomic", boom)
    assert sds.read(root, "stock", "600000.SH", END, oh.COLS).equals(_direct(root, "600000.SH", END))


def test_R491_分区不够多不建副本(tmp_path):
    for d in _days(sds.TAIL_DAYS):
        _write_day(tmp_path, d)
    got = sds.read(tmp_path, "stock", "600000.SH", END, oh.COLS)
    assert got.equals(_direct(tmp_path, "600000.SH", END))
    assert not (tmp_path / sds.CACHE_DIRNAME).exists()


def test_R491_帮不上忙就返回None_调用方走原路(store):
    root, _ = store
    assert sds.read(root, "futures", "600000.SH", END, oh.COLS) is None
    from tests.test_path_identifier_guards import TRAVERSAL_IDS
    for bad in [*TRAVERSAL_IDS, "600000.SH\n", "600000.SH/../x"]:
        assert sds.read(root, "stock", bad, END, oh.COLS) is None, repr(bad)
    assert sds.read(root, "index", "000001.SH", END, oh.COLS) is None   # 没有指数分区目录


def test_R491_早于截止日的end_只给到end(store):
    root, days = store
    sds.read(root, "stock", "600000.SH", END, oh.COLS)
    e = days[5]
    assert sds.read(root, "stock", "600000.SH", e, oh.COLS).equals(_direct(root, "600000.SH", e))


def test_R491_同时来四个请求_只建一次(store, monkeypatch):
    root, _ = store
    n = [0]
    real = sds._write_atomic

    def slow(*a, **k):
        n[0] += 1
        time.sleep(0.2)
        return real(*a, **k)
    monkeypatch.setattr(sds, "_write_atomic", slow)
    out: list = []
    ts = [threading.Thread(target=lambda: out.append(sds.read(root, "stock", "600000.SH", END, oh.COLS)))
          for _ in range(4)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert n[0] == 1 and len(out) == 4 and all(o.equals(out[0]) for o in out)


@pytest.mark.parametrize("asset,src", [("index", "kline_index_enriched"), ("etf", "kline_etf_enriched")])
def test_R491_指数与ETF各读各的目录(tmp_path, asset, src):
    for d in _days(30):
        _write_day(tmp_path, d, syms=["510300.SH"], src=src)
    sds.read(tmp_path, asset, "510300.SH", END, oh.COLS)
    got = sds.read(tmp_path, asset, "510300.SH", END, oh.COLS)
    assert got.equals(_direct(tmp_path, "510300.SH", END, src=src))
    assert (tmp_path / sds.CACHE_DIRNAME / asset / "510300.SH.parquet").exists()


# ── 接进 ohlcv_history 之后: 与仓库原路逐位一致, 包括盘中最新那一根的覆盖 ──────────
def _repo(root: Path):
    from app.tickflow.repository import DataStore, KlineRepository
    return KlineRepository(DataStore(data_dir=root))


def test_R491_接进历史缓存_与仓库原路逐位一致_含最新一根的覆盖(store, monkeypatch):
    root, days = store
    repo = _repo(root)
    last = days[-1]
    latest = _direct(root, "600000.SH", last).filter(pl.col("date") == last).with_columns(
        pl.lit("600000.SH").alias("symbol"), pl.lit(99.9).alias("close"))
    monkeypatch.setattr(repo, "get_enriched_latest", lambda: (latest, last))
    want = repo.get_daily_asset("stock", "600000.SH", oh.HISTORY_START, END, oh.COLS).sort("date")
    assert want.filter(pl.col("date") == last)["close"][0] == 99.9, "原路本身要带覆盖, 这条用例才有意义"
    for _ in range(2):                                       # 建副本一次, 读副本一次
        oh.clear()
        got = oh.get_history(repo, "stock", "600000.SH", END)
        assert got.equals(want)


def test_R491_副本里没有这只票_交给仓库原路(store, monkeypatch):
    root, _ = store
    repo = _repo(root)
    calls = []
    real = repo.get_daily_asset
    monkeypatch.setattr(repo, "get_daily_asset", lambda *a, **k: calls.append(a) or real(*a, **k))
    oh.get_history(repo, "stock", "999999.SH", END)
    assert calls, "空结果要交给原路 (ETF 还有旧版存在指数目录里的兜底)"
