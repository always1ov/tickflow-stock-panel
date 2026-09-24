"""[fork R491 / R492] 按个股另存的日 K 副本 —— 钉住「快」靠的那几件事, 以及「快了但结果没变」。

用户: 「按个股另存一份日K副本, 做吧」; R492 接进仓库的单票读取, 用户确认「做」, 且只关心
「作者的内置指标、我的评分系统、六态有没有被改变」。所以这里的主线断言只有一句:
**同样的 (代码, 起, 止, 列) 进去, 走副本与走原来的扫分区, 出来的表逐位相同** ——
指标、把握分、六态都是拿到这张表之后才算的。

风险全在「副本过期了还在用」, 所以大半用例是在各种改库的方式下断言拿到的还是库里此刻的数。
"""
from __future__ import annotations

import json
import shutil
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
END = date(2026, 9, 24)
OHLCV = ["date", "open", "high", "low", "close", "volume"]


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
        "raw_close": base, "raw_high": base, "raw_low": base, "turnover_rate": [[1.0, None, float("nan")][i % 3] for i in range(n)],
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


def _repo(root: Path):
    from app.tickflow.repository import DataStore, KlineRepository
    return KlineRepository(DataStore(data_dir=root))


_ORIG = {"stock": "_scan_daily_symbol", "index": "_scan_index_daily_symbol", "etf": "_scan_etf_daily_symbol"}


def _orig(root: Path, asset: str, sym: str, start: date, end: date, cols=None) -> pl.DataFrame:
    """原路: 仓库自己那套扫全部日文件(把副本关掉)。"""
    real = sds.scan_symbol
    sds.scan_symbol = lambda *_a, **_k: None
    try:
        return getattr(_repo(root), _ORIG[asset])(sym, start, end, cols)
    finally:
        sds.scan_symbol = real


def _via(root, sym="600000.SH", start=date(1990, 1, 1), end=END, cols=OHLCV, asset="stock"):
    return sds.scan_symbol(root, asset, sym, start, end, cols)


def _same(root, sym="600000.SH", start=date(1990, 1, 1), end=END, cols=OHLCV, asset="stock") -> bool:
    got = _via(root, sym, start, end, cols, asset)
    want = _orig(root, asset, sym, start, end, cols)
    return got is not None and got.schema == want.schema and got.equals(want)


class _Counter:
    """数一次读取打开了几个日文件。"""

    def __init__(self, monkeypatch):
        self.files = 0
        real = sds._scan

        def scan(files, symbol):
            self.files += len(files)
            return real(files, symbol)
        monkeypatch.setattr(sds, "_scan", scan)


# ── 主线: 与原来扫分区逐位相同 ─────────────────────────────────────
_RANGES = [
    (date(1990, 1, 1), END), (date(2026, 8, 1), END), (date(2026, 9, 1), date(2026, 9, 10)),
    (date(2026, 9, 16), END),                      # 只在最近 10 天以内: 不碰副本
    (END, END + timedelta(days=5)),                # 区间里一个分区都没有
    (date(2000, 1, 1), date(2001, 1, 1)),          # 早于库里第一天
]
_COLSETS = [None, OHLCV, ["date", "close"], ["close", "date", "turnover_rate"],
            ["date", "ma20", "close"], ["date", "change_pct"]]


@pytest.mark.parametrize("start,end", _RANGES)
@pytest.mark.parametrize("cols", _COLSETS)
def test_R492_同样的输入_副本与原路逐位相同_行列列序类型(store, start, end, cols):
    root, _ = store
    for s in [*SYMS, "999999.SH"]:
        assert _same(root, s, start, end, cols), (s, start, end, cols)       # 第一次: 建副本
        assert _same(root, s, start, end, cols), (s, start, end, cols)       # 以后: 读副本


def test_R491_第一次建副本_以后只开副本加最近十来个日文件(store, monkeypatch):
    root, days = store
    c = _Counter(monkeypatch)
    _via(root)
    assert c.files == len(days), "第一次: 截止日前的建副本 + 最近 10 天现读, 合起来正好全部"
    assert (root / sds.CACHE_DIRNAME / "stock" / "600000.SH.parquet").exists()
    c.files = 0
    _via(root)
    assert c.files == sds.TAIL_DAYS + 2, "以后: 最近 10 天 + 抽查首尾两天"


def test_R492_只要最近十天以内_不碰副本(store, monkeypatch):
    root, days = store
    c = _Counter(monkeypatch)
    _via(root, start=days[-5])
    assert c.files == 5
    assert not (root / sds.CACHE_DIRNAME).exists()


def test_R491_新进一天_截止日不挪_新的一天照样读到(store, monkeypatch):
    root, _ = store
    _via(root)
    js = root / sds.CACHE_DIRNAME / "stock" / "600000.SH.json"
    meta0 = js.read_text()
    new_day = date(2026, 9, 24)
    _write_day(root, new_day)
    c = _Counter(monkeypatch)
    got = _via(root, end=date(2026, 9, 25))
    assert js.read_text() == meta0, "每进一天截止日就挪 = 副本天天作废, 等于没做"
    assert c.files == sds.TAIL_DAYS + 1 + 2
    assert got["date"][-1] == new_day
    assert _same(root, end=date(2026, 9, 25))


def test_R491_除权后全部日文件重写_复权价变了就重建(store):
    """管道遇到除权会把这只票的全部日期重算重写 —— 副本必须跟上, 不能拿旧价。"""
    root, days = store
    _via(root)
    for d in days:
        _write_day(root, d, bump=-1.5)                     # 前复权: 以前的价整体下移
    assert _same(root)


@pytest.mark.parametrize("which", ["first", "last"])
def test_R491_抽查首尾_任一根对不上就重建(store, which):
    """前复权改前面(首根对不上), 后复权改后面(截止日那根对不上), 两头都得抽。"""
    root, days = store
    _via(root)
    cutoff = days[-sds.TAIL_DAYS - 1]
    _write_day(root, days[0] if which == "first" else cutoff, bump=0.07)
    assert _same(root)


def test_R492_抽查的是整行_只改了成交额也重建(store):
    root, days = store
    _via(root, cols=None)
    p = root / "kline_daily_enriched" / f"date={days[0]}" / "part.parquet"
    pl.read_parquet(p).with_columns(pl.col("amount") * 2).write_parquet(p)
    assert _same(root, cols=None)


def test_R491_补历史_补缺口_删一天_分区数一变就重建(store):
    root, days = store
    _via(root)
    _write_day(root, days[0] - timedelta(days=7))           # 往前补历史
    assert _same(root)
    shutil.rmtree(root / "kline_daily_enriched" / f"date={days[5]}")   # 中间删掉一天
    assert _same(root)


def test_R491_中间某天被改_抽查抽不到_最多7天后重建(store, monkeypatch):
    root, days = store
    _via(root)
    _write_day(root, days[10], bump=0.5)
    assert not _same(root), "这正是抽查的盲区, 只靠到期兜底"
    t = time.time()
    monkeypatch.setattr(sds.time, "time", lambda: t + sds.MAX_AGE_SECONDS + 1)
    assert _same(root)


def test_R491_最近几天的分区被删_副本不受影响_结果照样对(store):
    root, days = store
    _via(root)
    for d in days[-3:]:
        shutil.rmtree(root / "kline_daily_enriched" / f"date={d}")
    assert _same(root)


def test_R491_副本坏了_照样拿到对的数(store):
    root, _ = store
    _via(root)
    (root / sds.CACHE_DIRNAME / "stock" / "600000.SH.parquet").write_bytes(b"garbage")
    assert _same(root)
    (root / sds.CACHE_DIRNAME / "stock" / "600000.SH.json").write_text("{not json")
    assert _same(root)


def test_R492_旧版6列副本_自动按新格式重建(store):
    """R491 的副本只有 6 列; 升级后第一次读就重建成全部列, 不会拿 6 列去冒充。"""
    root, days = store
    base = root / sds.CACHE_DIRNAME / "stock"
    base.mkdir(parents=True)
    _orig(root, "stock", "600000.SH", date(1990, 1, 1), days[-11], OHLCV).write_parquet(base / "600000.SH.parquet")
    (base / "600000.SH.json").write_text(json.dumps(
        {"v": 1, "cutoff": days[-11].isoformat(), "n": 30, "cols": OHLCV, "built": time.time()}))
    assert _same(root, cols=None)
    assert json.loads((base / "600000.SH.json").read_text())["format"] == sds.FORMAT_VERSION


def test_R492_副本列对不上_即使说明是新的也重建(store):
    root, _ = store
    _via(root)
    pq = root / sds.CACHE_DIRNAME / "stock" / "600000.SH.parquet"
    pl.read_parquet(pq).drop("amount").write_parquet(pq)
    assert _same(root, cols=None)


def test_R491_写不了盘_这一次照样拿到对的数(store, monkeypatch):
    root, _ = store

    def boom(*_a, **_k):
        raise OSError("read-only")
    monkeypatch.setattr(sds, "_write_atomic", boom)
    assert _same(root)


def test_R491_读副本时出了意外_返回None交给原路(store, monkeypatch):
    root, _ = store

    def boom(*_a, **_k):
        raise RuntimeError("polars 出错")
    monkeypatch.setattr(sds, "_scan", boom)
    assert _via(root) is None


def test_R491_分区不够多不建副本(tmp_path):
    for d in _days(sds.TAIL_DAYS):
        _write_day(tmp_path, d)
    assert _same(tmp_path)
    assert not (tmp_path / sds.CACHE_DIRNAME).exists()


def test_R491_帮不上忙就返回None_调用方走原路(store):
    from tests.test_path_identifier_guards import TRAVERSAL_IDS
    root, _ = store
    assert _via(root, asset="futures") is None
    assert _via(root, "000001.SH", asset="index") is None             # 没有指数分区目录
    for bad in [*TRAVERSAL_IDS, "600000.SH\n", "600000.SH/../x", None]:
        assert _via(root, bad) is None, repr(bad)


@pytest.mark.parametrize("stray", ["dir", "file"])
def test_R492_分区目录里有看不懂的东西_不用副本(store, stray):
    """原来的 `**/*.parquet` 会把散落的文件也读进来 —— 副本不去猜怎么对齐, 直接让位。"""
    root, _ = store
    src = root / "kline_daily_enriched"
    if stray == "dir":
        (src / "backup").mkdir()
    else:
        pl.DataFrame({"x": [1]}).write_parquet(src / "stray.parquet")
    assert _via(root) is None


def test_R492_副本最多留MAX_COPIES份_超出删最早建的(store, monkeypatch):
    root, _ = store
    monkeypatch.setattr(sds, "MAX_COPIES", 2)
    for s in SYMS:
        _via(root, s)
        time.sleep(0.01)
    left = sorted(p.stem for p in (root / sds.CACHE_DIRNAME / "stock").glob("*.parquet"))
    assert len(left) <= 2 and "000002.SZ" in left, left
    assert len(list((root / sds.CACHE_DIRNAME / "stock").glob("*.json"))) == len(left)
    assert all(_same(root, s) for s in SYMS)


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
    ts = [threading.Thread(target=lambda: out.append(_via(root))) for _ in range(4)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert n[0] == 1 and len(out) == 4 and all(o.equals(out[0]) for o in out)


@pytest.mark.parametrize("asset,src", [("index", "kline_index_enriched"), ("etf", "kline_etf_enriched")])
def test_R491_指数与ETF各读各的目录(tmp_path, asset, src):
    for d in _days(30):
        _write_day(tmp_path, d, syms=["510300.SH"], src=src)
    for cols in (None, OHLCV):
        assert _same(tmp_path, "510300.SH", cols=cols, asset=asset)
        assert _same(tmp_path, "510300.SH", cols=cols, asset=asset)
    assert (tmp_path / sds.CACHE_DIRNAME / asset / "510300.SH.parquet").exists()


# ── 接进仓库之后: 仓库对外的读法与原来逐位一致(含最新一根的覆盖、全套指标重算) ──────
def _both(root, monkeypatch, call):
    """同一个调用, 走副本一次(建)、再一次(读), 与把副本关掉的原路比。"""
    repo = _repo(root)
    got1, got2 = call(repo), call(repo)
    monkeypatch.setattr(sds, "scan_symbol", lambda *_a, **_k: None)
    want = call(_repo(root))
    monkeypatch.undo()
    return got1, got2, want


def test_R492_仓库get_daily_列下推快路径_含最新一根覆盖(store, monkeypatch):
    root, days = store
    last = days[-1]
    latest = _orig(root, "stock", "600000.SH", last, last).with_columns(pl.lit(99.9).alias("close"))

    def call(repo):
        repo.get_enriched_latest = lambda: (latest, last)
        return repo.get_daily("600000.SH", date(1990, 1, 1), END, OHLCV)
    got1, got2, want = _both(root, monkeypatch, call)
    assert want.filter(pl.col("date") == last)["close"][0] == 99.9, "原路本身要带覆盖, 这条用例才有意义"
    assert got1.equals(want) and got2.equals(want)


def test_R492_仓库get_daily_不指定列_全套指标照原样重算(store, monkeypatch):
    root, _ = store

    def call(repo):
        repo.get_enriched_latest = lambda: (pl.DataFrame(), None)
        return repo.get_daily("600000.SH", date(2026, 7, 1), END)
    got1, got2, want = _both(root, monkeypatch, call)
    assert "ma20" in want.columns and want.height > 0
    assert got1.equals(want) and got2.equals(want)


@pytest.mark.parametrize("asset,src", [("index", "kline_index_enriched"), ("etf", "kline_etf_enriched")])
def test_R492_仓库指数与ETF读法(tmp_path, monkeypatch, asset, src):
    for d in _days(40):
        _write_day(tmp_path, d, syms=["510300.SH"], src=src)
    fn = "get_index_daily" if asset == "index" else "get_etf_daily"
    for cols in (None, ["date", "close"]):
        got1, got2, want = _both(tmp_path, monkeypatch,
                                 lambda r, c=cols: getattr(r, fn)("510300.SH", date(2026, 6, 1), END, c))
        assert want.height > 0 and got1.equals(want) and got2.equals(want), cols


def test_R492_历史缓存走仓库_与原路逐位一致(store, monkeypatch):
    """两张副图(R490 的内存缓存)不再自己抄一份覆盖逻辑, 直接用仓库 —— 结果不变。"""
    root, days = store
    last = days[-1]
    latest = _orig(root, "stock", "600000.SH", last, last).with_columns(pl.lit(88.8).alias("close"))

    def call(repo):
        repo.get_enriched_latest = lambda: (latest, last)
        oh.clear()
        return oh.get_history(repo, "stock", "600000.SH", END)
    got1, got2, want = _both(root, monkeypatch, call)
    assert want["close"][-1] == 88.8
    assert got1.equals(want) and got2.equals(want)


def test_R492_三种资产目录同时在_各读各的_不串(tmp_path, monkeypatch):
    """同一个代码在股票、指数、ETF 三个目录里各有一份不同的数 —— 仓库的三个读法各拿各的。"""
    for i, src in enumerate(("kline_daily_enriched", "kline_index_enriched", "kline_etf_enriched")):
        for d in _days(30):
            _write_day(tmp_path, d, syms=["510300.SH"], bump=i * 100.0, src=src)
    for fn in ("_scan_daily_symbol", "_scan_index_daily_symbol", "_scan_etf_daily_symbol"):
        got1, got2, want = _both(tmp_path, monkeypatch,
                                 lambda r, f=fn: getattr(r, f)("510300.SH", date(1990, 1, 1), END, None))
        assert want.height > 0 and got1.equals(want) and got2.equals(want), fn


def test_R493_截止日前没有这只票_不留空副本_历史补进来立刻看得到(store):
    """审查发现: 空副本无从抽查, 历史补进已有日文件后分区数不变, 原来会连着 7 天只给最近几根。"""
    root, days = store
    assert _same(root, "600009.SH")
    assert not (root / sds.CACHE_DIRNAME / "stock" / "600009.SH.parquet").exists()
    for d in days:
        _write_day(root, d, syms=[*SYMS, "600009.SH"])
    assert _same(root, "600009.SH")
    assert _via(root, "600009.SH").height == len(days)


def test_R493_往已有日文件里补这只票更早的历史_立刻看得到(store):
    """首尾两根、分区数都没变 —— 只有「第一根的前一天现在有这只票了」看得出来。"""
    root, days = store
    for d in days[15:]:
        _write_day(root, d, syms=[*SYMS, "600009.SH"])
    _via(root, "600009.SH")
    for d in days[5:15]:
        _write_day(root, d, syms=[*SYMS, "600009.SH"])
    assert _same(root, "600009.SH")


def test_R493_停牌后那段补进来_截止日有了这只票_立刻看得到(store):
    root, days = store
    for d in days[:20]:
        _write_day(root, d, syms=[*SYMS, "600009.SH"])
    _via(root, "600009.SH")                                # 副本最后一根早于截止日
    for d in days[20:]:
        _write_day(root, d, syms=[*SYMS, "600009.SH"])
    assert _same(root, "600009.SH")


def test_R493_抽查那天分区里有重复行_不会次次重建(store, monkeypatch):
    root, days = store
    p = root / "kline_daily_enriched" / f"date={days[0]}" / "part.parquet"
    df = pl.read_parquet(p)
    pl.concat([df, df.filter(pl.col("symbol") == "600000.SH")]).write_parquet(p)
    _via(root)
    n = [0]
    real = sds._write_atomic
    monkeypatch.setattr(sds, "_write_atomic", lambda *a, **k: (n.__setitem__(0, n[0] + 1), real(*a, **k)))
    for _ in range(3):
        assert _same(root)
    assert n[0] == 0, "重复行原路也照样返回, 副本与它一致就该认"


@pytest.mark.parametrize("asset,src", [("stock", "kline_daily_enriched"), ("etf", "kline_etf_enriched")])
def test_R493_管道正在发布_不建也不用副本(tmp_path, monkeypatch, asset, src):
    for d in _days(30):
        _write_day(tmp_path, d, src=src)
    _via(tmp_path, asset=asset)
    seen = []
    monkeypatch.setattr(sds, "enriched_publication_incomplete",
                        lambda _d, a="stock": seen.append(a) or True)
    assert _via(tmp_path, asset=asset) is None
    assert set(seen) == {asset}, "股票和 ETF 各看各的发布标记"


def test_R494_盘中实时落盘撞上发布标记_等几毫秒照常用副本(store, monkeypatch):
    """实时每轮只在换文件那几毫秒处于发布中 —— 不该为此退回扫全部日文件。"""
    root, _ = store
    _via(root)
    left = [3]                                             # 前 3 次看是「发布中」, 随后就绪

    def flag(*_a, **_k):
        left[0] -= 1
        return left[0] >= 0
    monkeypatch.setattr(sds, "enriched_publication_incomplete", flag)
    c = _Counter(monkeypatch)
    got = _via(root)
    assert got is not None and got.equals(_orig(root, "stock", "600000.SH", date(1990, 1, 1), END, OHLCV))
    assert c.files == sds.TAIL_DAYS + 2, "走的是副本(最近 10 天 + 抽查首尾两天; 这只票天天有, 两头外侧不用查)"


def test_R494_管道整轮发布_等满也不就绪_退回原路且不久等(store, monkeypatch):
    root, _ = store
    _via(root)
    monkeypatch.setattr(sds, "enriched_publication_incomplete", lambda *_a, **_k: True)
    t = time.monotonic()
    assert _via(root) is None
    assert time.monotonic() - t < sds.PUBLISH_WAIT_SECONDS + 0.15


def test_R493_空副本即使说明是新的也不认_历史补进来照样看得到(store):
    """空副本现在不会建出来; 但磁盘上万一有一份(旧版本、手工拷来的), 也不能被当成「没变」。"""
    root, days = store
    base = root / sds.CACHE_DIRNAME / "stock"
    base.mkdir(parents=True)
    sds._empty().write_parquet(base / "600009.SH.parquet")
    (base / "600009.SH.json").write_text(json.dumps(
        {"format": sds.FORMAT_VERSION, "cutoff": days[-11].isoformat(), "partitions": 30,
         "built": time.time()}))
    for d in days:
        _write_day(root, d, syms=[*SYMS, "600009.SH"])
    assert _same(root, "600009.SH")


def test_R493_抽查那天的全部行都对照_不只第一行(store):
    root, days = store
    p = root / "kline_daily_enriched" / f"date={days[0]}" / "part.parquet"
    df = pl.read_parquet(p)
    dup = df.filter(pl.col("symbol") == "600000.SH")
    pl.concat([df, dup]).write_parquet(p)
    _via(root)
    pl.concat([df, dup.with_columns(pl.col("close") + 1)]).write_parquet(p)   # 只改了第二行
    assert _same(root)


def test_R493_建的途中管道开始发布_这份不存(store, monkeypatch):
    root, _ = store
    calls = [0]

    def flag(*_a, **_k):
        calls[0] += 1
        return calls[0] > 1                                # 进门时没在发布, 建完再看已经在发布
    monkeypatch.setattr(sds, "enriched_publication_incomplete", flag)
    assert _via(root) is not None
    assert not (root / sds.CACHE_DIRNAME / "stock" / "600000.SH.parquet").exists()


def test_R493_重复的列名_退回原路而不是把异常抛出仓库(store):
    root, _ = store
    assert _via(root, cols=["close", "close"]) is None
    assert _orig(root, "stock", "600000.SH", date(1990, 1, 1), END, ["close", "close"]).is_empty()


def test_R493_管道作废_点名的票和整类(store):
    root, _ = store
    for s in SYMS:
        _via(root, s)
    base = root / sds.CACHE_DIRNAME / "stock"
    outside = root / sds.CACHE_DIRNAME / "x.parquet"
    outside.write_text("不许被删")
    sds.invalidate(root, "stock", ["600000.SH", "../x", None])
    assert outside.exists(), "代码要拼进路径, 不像代码的一律不碰"
    assert sorted(p.stem for p in base.glob("*.parquet")) == ["000002.SZ", "600001.SH"]
    assert not (base / "600000.SH.json").exists()
    sds.invalidate(root, "stock")
    assert not list(base.glob("*.parquet")) and not list(base.glob("*.json"))
    sds.invalidate(root, "etf")                            # 没建过也不报错
    assert _same(root)


def test_R493_淘汰按最近用过_常看的不被挤掉(tmp_path, monkeypatch):
    syms = ["600000.SH", "600001.SH", "600002.SH", "600003.SH"]
    for d in _days(30):
        _write_day(tmp_path, d, syms=syms)
    monkeypatch.setattr(sds, "MAX_COPIES", 3)
    base = tmp_path / sds.CACHE_DIRNAME / "stock"
    for s in syms[:3]:
        _via(tmp_path, s)
        time.sleep(0.02)
    _via(tmp_path, "600000.SH")                            # 最早建的, 但刚用过
    time.sleep(0.02)
    _via(tmp_path, "600003.SH")                            # 第 4 份 → 删到 2 份
    assert sorted(p.stem for p in base.glob("*.parquet")) == ["600000.SH", "600003.SH"]


def test_R493_崩溃留下的临时文件和孤儿说明_建副本时顺手清掉(store):
    root, _ = store
    base = root / sds.CACHE_DIRNAME / "stock"
    base.mkdir(parents=True)
    old_tmp, new_tmp = base / ".x.parquet.abc.tmp", base / ".y.parquet.def.tmp"
    orphan = base / "600777.SH.json"
    for f in (old_tmp, new_tmp, orphan):
        f.write_text("x")
    t = time.time() - sds.ORPHAN_SECONDS - 10
    import os
    os.utime(old_tmp, (t, t))
    _via(root)
    assert not old_tmp.exists() and not orphan.exists()
    assert new_tmp.exists(), "刚建的临时文件可能正被别的进程写, 不能删"


def test_R493_管道与清空数据都接上了副本(tmp_path):
    """这两处在作者文件里, 同步上游时最容易被整段覆盖掉 —— 钉住它们还在。"""
    src = Path(__file__).resolve().parents[1] / "app"
    pipe = (src / "jobs" / "daily_pipeline.py").read_text(encoding="utf-8")
    assert 'symbol_daily_store.invalidate(repo.store.data_dir, "stock")' in pipe
    assert 'symbol_daily_store.invalidate(repo.store.data_dir, "stock", list(affected_symbols))' in pipe
    assert 'symbol_daily_store.invalidate(repo.store.data_dir, "etf", list(affected_etfs))' in pipe
    data = (src / "api" / "data.py").read_text(encoding="utf-8")
    assert data.count('".symbol_daily_cache"') == 2, "清空要删它, 占用统计要算它"


def test_R492_截止日之后只读区间里的日文件(store, monkeypatch):
    root, days = store
    _via(root)
    c = _Counter(monkeypatch)
    _via(root, end=days[-5])
    assert c.files == (sds.TAIL_DAYS - 4) + 2, "区间外的最近几天不该打开"
