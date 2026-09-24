"""[R490 · fork 增强] 单票日 K 历史缓存 —— 给关键价位图的两张副图(量化MACD、趋势量化)共用。

用户: 「优化一下性能计算什么的, 现在加载出来要等很久, 想个好方案」。

## 慢在哪(实测, 1000 个交易日 × 5000 只的模拟库, 见 FORK_NOTES.R490)

日 K 按**交易日**分区(`kline_daily_enriched/date=YYYY-MM-DD/part.parquet`, 每个文件是
全市场)。取一只票的历史 = 把区间里**每一天的文件都打开扫一遍**:

    扫 1000 个日文件挑出这一只              ~300 ms   ← 大头, 随历史年数线性变长
    没指定列 → 顺带把全套技术指标重算一遍      ~90 ms
    趋势量化 + 庄现 + 量化MACD 本身的计算      ~45 ms

而且**每开一次弹窗、盘中每来一次实时行情**两张副图都各扫一遍, 从来不复用。

## 这里做的三件事

1. **只读 6 列**(日期、开高低收、成交量) —— 走仓库的列下推快路径, 不重算指标;
2. **同一只票只扫一次**: 放进内存, 直到库里的最新交易日变了或过了 10 分钟才重扫;
3. **两张副图共用、同一时刻只让一个请求去扫**(single-flight): 另一个等它扫完直接拿。

[R491/R492] 内存里没有时照旧向仓库取; 仓库的单票读取自 R492 起先读按个股另存的日 K 副本
(`symbol_daily_store`), 所以每只票**第一次**打开也快了。盘中最新一根的覆盖仍由仓库自己做,
这里不再另抄一份。

盘中实时那一根**不进缓存**: 调用方拿到缓存后照旧自己叠 `_maybe_inject_live_candle`,
所以盘中看到的最右一根永远是最新的。缓存里存的是一份拷贝, 调用方改不坏它。
"""
from __future__ import annotations

import threading
import time
from collections import OrderedDict
from datetime import date
from typing import Any

import polars as pl

COLS = ["date", "open", "high", "low", "close", "volume"]
# 早于 A 股开市 = 「库里有多少取多少」(趋势量化的「吸筹」要从上市第一根算起)
HISTORY_START = date(1990, 1, 1)
TTL_SECONDS = 600
MAX_SYMBOLS = 64

_lock = threading.Lock()
_cache: OrderedDict[tuple, tuple[Any, float, pl.DataFrame]] = OrderedDict()
_inflight: dict[tuple, threading.Lock] = {}


def _data_version(repo, asset_type: str) -> Any:
    """库里最新的交易日 —— 盘后管道写进新的一天, 它就变, 缓存随之作废。取不到就是 None
    (那就只靠 10 分钟过期兜底)。**不触发重算**(refresh=False), 免得把慢路径拉回来。"""
    try:
        return repo.get_enriched_latest_asset(asset_type, refresh=False)[1]
    except Exception:  # noqa: BLE001
        return None


def get_history(repo, asset_type: str, symbol: str, end: date) -> pl.DataFrame:
    """这只票从上市到 `end` 的日 K(6 列, 按日期升序)。命中缓存时不碰磁盘。"""
    key = (id(repo), asset_type, symbol, end)
    version = _data_version(repo, asset_type)
    now = time.monotonic()
    with _lock:
        hit = _cache.get(key)
        if hit and hit[0] == version and now - hit[1] < TTL_SECONDS:
            _cache.move_to_end(key)
            return hit[2].clone()
        flight = _inflight.setdefault(key, threading.Lock())
    with flight:                                   # 同一只票同时来两个请求: 第二个在这等
        with _lock:
            hit = _cache.get(key)
            if hit and hit[0] == version and time.monotonic() - hit[1] < TTL_SECONDS:
                return hit[2].clone()
        df = repo.get_daily_asset(asset_type, symbol, HISTORY_START, end, COLS)
        if not df.is_empty() and "date" in df.columns:
            df = df.sort("date")
        with _lock:
            _cache[key] = (version, time.monotonic(), df)
            _cache.move_to_end(key)
            while len(_cache) > MAX_SYMBOLS:
                _cache.popitem(last=False)
            _inflight.pop(key, None)
        return df.clone()


def invalidate(asset_type: str, symbols=None) -> None:
    """[R496] 日K历史被改写(除权重算等): 点名的票作废; symbols=None → 这一类整个作废。

    由 `derived_caches.enriched_rewritten` 调用。原来只靠「最新交易日变了 / 10 分钟」,
    除权重算而没有新交易日时, 两张副图会用旧复权价最多 10 分钟。
    """
    wanted = None if symbols is None else set(symbols)
    with _lock:
        for key in [k for k in _cache if k[1] == asset_type and (wanted is None or k[2] in wanted)]:
            del _cache[key]


def clear() -> None:
    """测试用: 各用例换一个假仓库, 不能读到上一个用例缓存的数据。"""
    with _lock:
        _cache.clear()
        _inflight.clear()
