"""[fork R496] 日K衍生缓存登记表 —— 改写日K之后只通知一处, 登记过的缓存各自作废。

用户: 「做第2条」。R493 复查查出过「除权重算后副本没跟着作废」: 缓存散在几处,
改写日K的地方不知道要通知谁。这里钉住三件事:
  1. 通知真的到了该到的缓存, 只作废点名的票、点名的资产类型;
  2. 一份缓存作废失败不连累别的, 也不抛给调用方;
  3. 所有原地改写日K的地方都接了通知(按调用点扫, 不靠人记)。
"""
from __future__ import annotations

import ast
from datetime import date, timedelta
from pathlib import Path

import polars as pl

from app.parquet import ENRICHED_STORAGE_SCHEMA
from app.services import derived_caches as dc
from app.services import ohlcv_history as oh
from app.services import symbol_daily_store as sds

APP = Path(__file__).resolve().parents[1] / "app"


def _store(root: Path, syms=("600000.SH", "600001.SH"), src="kline_daily_enriched") -> None:
    d, n = date(2026, 9, 23), 0
    while n < 30:
        if d.weekday() < 5:
            k = len(syms)
            df = pl.DataFrame({
                "symbol": list(syms), "date": [d] * k, "open": [10.0] * k, "high": [11.0] * k,
                "low": [9.0] * k, "close": [10.0 + n * 0.1] * k, "volume": [1e6] * k, "amount": [1e7] * k,
                "raw_close": [10.0] * k, "raw_high": [11.0] * k, "raw_low": [9.0] * k,
                "turnover_rate": [1.0] * k, "consecutive_limit_ups": [0] * k,
                "consecutive_limit_downs": [0] * k, "quote_ts": [0] * k,
            }).cast(ENRICHED_STORAGE_SCHEMA)
            p = root / src / f"date={d}"
            p.mkdir(parents=True)
            df.write_parquet(p / "part.parquet")
            n += 1
        d -= timedelta(days=1)


class _Repo:
    def __init__(self):
        self.calls = 0

    def get_daily_asset(self, asset_type, symbol, start, end, columns=None):
        self.calls += 1
        return pl.DataFrame({"date": [date(2026, 9, 1)], "open": [1.0], "high": [1.0], "low": [1.0],
                             "close": [1.0], "volume": [1.0]})

    def get_enriched_latest_asset(self, asset_type, refresh=True):
        return pl.DataFrame(), date(2026, 9, 1)


END = date(2026, 9, 24)


def test_R496_登记表四份缓存一处看全():
    names = [c.name for c in dc.REGISTRY]
    assert names == ["带指标日K内存缓存(作者)", "回测矩阵缓存(作者)", "个股日K副本", "两张副图的单票历史内存缓存"]
    assert all(c.lives and c.stale_when for c in dc.REGISTRY)
    assert [c.on_rewrite is not None for c in dc.REGISTRY] == [False, False, True, True], \
        "作者的两份自带代次校验, 不接通知; fork 的两份接通知"


def test_R496_除权重算没有新交易日_两张副图的内存缓存也立刻作废():
    """原来只靠「最新交易日变了 / 10 分钟」—— 除权当天没有新交易日时会用旧复权价最多 10 分钟。"""
    repo = _Repo()
    oh.get_history(repo, "stock", "600000.SH", END)
    oh.get_history(repo, "stock", "600001.SH", END)
    oh.get_history(repo, "etf", "600000.SH", END)
    assert repo.calls == 3
    dc.enriched_rewritten(Path("/nonexistent"), "stock", ["600000.SH"])
    oh.get_history(repo, "stock", "600000.SH", END)
    assert repo.calls == 4, "点名的票要重取"
    oh.get_history(repo, "stock", "600001.SH", END)
    oh.get_history(repo, "etf", "600000.SH", END)
    assert repo.calls == 4, "没点名的票、别的资产类型不受影响"
    dc.enriched_rewritten(Path("/nonexistent"), "stock")
    oh.get_history(repo, "stock", "600001.SH", END)
    oh.get_history(repo, "etf", "600000.SH", END)
    assert repo.calls == 5, "整类作废只作废这一类"


def test_R496_个股副本_点名作废与整类作废(tmp_path):
    _store(tmp_path)
    for s in ("600000.SH", "600001.SH"):
        sds.scan_symbol(tmp_path, "stock", s, date(1990, 1, 1), END, ["date"])
    base = tmp_path / sds.CACHE_DIRNAME / "stock"
    dc.enriched_rewritten(tmp_path, "stock", ["600000.SH"])
    assert sorted(p.stem for p in base.glob("*.parquet")) == ["600001.SH"]
    dc.enriched_rewritten(tmp_path, "etf")
    assert sorted(p.stem for p in base.glob("*.parquet")) == ["600001.SH"], "别的资产类型不碰"
    dc.enriched_rewritten(tmp_path, "stock")
    assert not list(base.glob("*.parquet"))


def test_R496_空名单什么都不做(tmp_path):
    _store(tmp_path)
    sds.scan_symbol(tmp_path, "stock", "600000.SH", date(1990, 1, 1), END, ["date"])
    dc.enriched_rewritten(tmp_path, "stock", [])
    assert (tmp_path / sds.CACHE_DIRNAME / "stock" / "600000.SH.parquet").exists(), \
        "空名单 = 没有票被改写, 不能当成「整类作废」"


def test_R496_正常通知不留错误日志(tmp_path, caplog):
    """作者那两份不接通知, 通知时要跳过, 不能拿 None 去调再被兜底吞掉、留一条假报错。"""
    import logging
    with caplog.at_level(logging.WARNING, logger="app.services.derived_caches"):
        dc.enriched_rewritten(tmp_path, "stock", ["600000.SH"])
        dc.enriched_rewritten(tmp_path, "stock")
    assert caplog.records == []


def test_R496_一份作废失败不连累别的_也不抛给调用方(tmp_path, monkeypatch):
    got = []

    def boom(*_a):
        raise RuntimeError("x")
    caches = (
        dc.DerivedCache("坏的", "-", "-", boom),
        dc.DerivedCache("好的", "-", "-", lambda d, a, s: got.append((a, s))),
    )
    monkeypatch.setattr(dc, "REGISTRY", caches)
    dc.enriched_rewritten(tmp_path, "stock", {"600000.SH"})
    assert got == [("stock", ("600000.SH",))]


# ── 调用点守卫: 原地改写日K的地方都接了通知 ─────────────────────────────
def _calls(tree: ast.AST, name: str) -> int:
    n = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            if (isinstance(f, ast.Name) and f.id == name) or (isinstance(f, ast.Attribute) and f.attr == name):
                n += 1
    return n


def test_R496_调了run_pipeline的文件都接了通知():
    """run_pipeline 是重算带指标日K的唯一入口; 谁调它谁就原地改写了历史。"""
    callers = {}
    for py in APP.rglob("*.py"):
        if py.name == "pipeline.py" and py.parent.name == "indicators":
            continue                                        # 定义它的地方
        tree = ast.parse(py.read_text(encoding="utf-8"))
        if _calls(tree, "run_pipeline"):
            callers[py.relative_to(APP).as_posix()] = _calls(tree, "enriched_rewritten")
    assert set(callers) == {"jobs/daily_pipeline.py", "services/extend_history.py", "api/kline.py"}, \
        f"新的 run_pipeline 调用点, 先确认它要不要通知衍生缓存: {callers}"
    assert all(callers.values()), callers


def test_R496_ETF除权也接了通知():
    tree = ast.parse((APP / "jobs" / "daily_pipeline.py").read_text(encoding="utf-8"))
    assert _calls(tree, "sync_etf_adj_factor") == 1
    assert _calls(tree, "enriched_rewritten") == 3, "股票全量、股票除权、ETF 除权"


def test_R496_只有登记表直接作废副本与内存缓存():
    """作废入口只留一个: 别处直接调 symbol_daily_store.invalidate / ohlcv_history.invalidate
    等于绕开登记表, 下一份新缓存又会漏。"""
    offenders = []
    for py in APP.rglob("*.py"):
        if py.name in {"derived_caches.py", "symbol_daily_store.py", "ohlcv_history.py"}:
            continue
        src = py.read_text(encoding="utf-8")
        if "symbol_daily_store.invalidate(" in src or "ohlcv_history.invalidate(" in src:
            offenders.append(py.relative_to(APP).as_posix())
    assert offenders == []
