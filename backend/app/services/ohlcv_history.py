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

[R491] 内存里没有时, 先读按个股另存的日 K 副本(`symbol_daily_store`, 一个文件 + 最近
十来个日文件), 读不到才照原来扫全部日文件 —— 每只票**第一次**打开也快了。

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

from app.services import symbol_daily_store

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


def _from_symbol_copy(repo, asset_type: str, symbol: str, end: date) -> pl.DataFrame | None:
    """[R491] 先读按个股另存的副本(一个文件 + 最近十来个日文件), 读不到返回 None 走原路。

    盘中最新那一根的覆盖**照抄** `KlineRepository.get_daily` 列下推快路径的那几行:
    用仓库最新缓存里这只票的那一行替换同一天的行。指数不覆盖、ETF 不覆盖 —— 与
    `get_index_daily` / `get_etf_daily` 快路径一致。结果与 `get_daily_asset(..., COLS)` 逐位相同。
    """
    data_dir = getattr(getattr(repo, "store", None), "data_dir", None)
    if data_dir is None:                           # 测试替身之类没有磁盘的仓库
        return None
    df = symbol_daily_store.read(data_dir, asset_type, symbol, end, COLS)
    if df is None or df.is_empty() or not all(c in df.columns for c in COLS):
        return None                                # 空的交给原路(ETF 还有旧版存在指数目录的兜底)
    if asset_type == "stock":
        cached, cache_date = repo.get_enriched_latest()
        if cached is not None and not cached.is_empty() and cache_date:
            if HISTORY_START <= cache_date <= end:
                cached_part = repo._filter_cached(cached, symbol, COLS)
                if not cached_part.is_empty():
                    df = df.filter(pl.col("date") != cache_date)
                    common_cols = [c for c in df.columns if c in cached_part.columns]
                    df = pl.concat([df.select(common_cols), cached_part.select(common_cols)])
    return df


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
        df = _from_symbol_copy(repo, asset_type, symbol, end)
        if df is None:
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


def clear() -> None:
    """测试用: 各用例换一个假仓库, 不能读到上一个用例缓存的数据。"""
    with _lock:
        _cache.clear()
        _inflight.clear()
