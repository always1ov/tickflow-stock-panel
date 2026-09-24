"""[R491 · fork 增强] 按个股另存的日 K 副本 —— 取一只票的全部历史只开一个文件。

用户: 「按个股另存一份日K副本, 做吧」。

## 为什么要有它

日 K 按**交易日**分区(`kline_daily_enriched/date=YYYY-MM-DD/part.parquet`, 每个文件是全市场)。
取一只票从上市到今天 = 把一千来个日文件**逐个打开**挑出这一只(R490 实测 ~300 ms, 随历史
年数线性变长)。R490 的内存缓存只管「同一只票第二次打开」, 每只票**第一次**打开还是要扫一遍。

这里把「这一只票的 6 列日 K」另存一个文件: 第一次打开时顺手写下, 以后读它一个文件 +
最近十来个日文件就够了。

## 副本里有什么、没有什么

    .symbol_daily_cache/<stock|index|etf>/<代码>.parquet      6 列(日期、开高低收、成交量)
    .symbol_daily_cache/<stock|index|etf>/<代码>.json         截止日 + 建它时库里的分区数

  · **建副本时最近 10 个交易日不进副本**, 每次现读 —— 盘中实时落盘、盘后管道补收盘价、
    修复过期分区, 改的都是最近几天, 这几天永远以分区为准。截止日建好就不再挪, 之后每进
    一天就多现读一个日文件(最多 7 天后重建, 现读的最多十几个文件);
  · 盘中实时那一根照旧用仓库的最新缓存覆盖(与 `get_daily` 快路径同一个处理), 所以
    **拼出来的结果与原来直接扫分区逐位一致**, 只是快。

## 什么时候作废重建(判据是内容, 不是修改时间)

盘后管道只要有一只票除权, 就会把**所有**日文件重写一遍 —— 按修改时间判断, 副本每天都会作废,
等于没做。所以这里抽查内容:

  1. **截止日之前的分区数变了**(补历史、补缺口、修复删掉了某一天) → 重建;
  2. **抽查两根**: 副本的第一根和最后一根, 各自现读那一天的分区对照 6 个数。复权价一变
     (除权因子进来, 前复权改前面、后复权改后面), 首尾至少有一根对不上 → 重建;
  3. **最多用 7 天**, 到期重建一次, 兜住上面两条都抽不到的中间某天被改。

副本坏了、读不了、写不了, 一律退回原来的直接扫分区 —— 它只是加速, 不是数据源。
这是 `data_dir` 下的派生缓存, 整个目录删掉也没关系, 下次打开自动重建。
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
import uuid
from datetime import date
from pathlib import Path

import polars as pl

from app.parquet import scan_enriched_parquet
from app.polars_guard import guarded_collect

logger = logging.getLogger(__name__)

CACHE_DIRNAME = ".symbol_daily_cache"
TAIL_DAYS = 10
MAX_AGE_SECONDS = 7 * 86400
FORMAT_VERSION = 1

_SOURCE_DIRS = {
    "stock": "kline_daily_enriched",
    "index": "kline_index_enriched",
    "etf": "kline_etf_enriched",
}
# 代码要拼进文件名: 首字符必须是字母数字(挡 `.` `..`), 整串匹配(`$` 会放过结尾换行)
_SAFE_SYMBOL = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,31}")
_locks_guard = threading.Lock()
_locks: dict[tuple[str, str, str], threading.Lock] = {}


def _partitions(src: Path) -> list[tuple[date, Path]]:
    """按日期升序列出分区: (交易日, 分区目录)。只看目录名, 不打开文件。"""
    out: list[tuple[date, Path]] = []
    try:
        entries = list(os.scandir(src))
    except OSError:
        return out
    for e in entries:
        if not e.name.startswith("date=") or not e.is_dir():
            continue
        try:
            out.append((date.fromisoformat(e.name[5:]), Path(e.path)))
        except ValueError:
            continue
    out.sort(key=lambda x: x[0])
    return out


def _files(dirs: list[Path]) -> list[str]:
    files: list[str] = []
    for d in dirs:
        files.extend(sorted(str(p) for p in d.glob("*.parquet")))
    return files


def _scan(files: list[str], symbol: str, cols: list[str]) -> pl.DataFrame:
    """与仓库 `_scan_*_symbol` 同一个读法(同 schema、同类型放宽), 只是文件由这里点名。"""
    if not files:
        return pl.DataFrame()
    lf = scan_enriched_parquet(files, cast_options=pl.ScanCastOptions(integer_cast="allow-float"))
    lf = lf.filter(pl.col("symbol") == symbol).sort("date")
    names = lf.collect_schema().names()
    return guarded_collect(lf.select([c for c in cols if c in names]))


def _write_atomic(df: pl.DataFrame, meta: dict, pq: Path, js: Path) -> None:
    pq.parent.mkdir(parents=True, exist_ok=True)
    tag = uuid.uuid4().hex
    tmp_pq, tmp_js = pq.with_name(f".{pq.name}.{tag}.tmp"), js.with_name(f".{js.name}.{tag}.tmp")
    try:
        df.write_parquet(tmp_pq)
        tmp_js.write_text(json.dumps(meta), encoding="utf-8")
        # 先换数据再换说明: 中途崩了, 说明对不上新数据, 下次抽查必不过, 自然重建
        os.replace(tmp_pq, pq)
        os.replace(tmp_js, js)
    finally:
        tmp_pq.unlink(missing_ok=True)
        tmp_js.unlink(missing_ok=True)


def _anchor_ok(copy: pl.DataFrame, parts: dict[date, Path], symbol: str, cols: list[str]) -> bool:
    """副本首尾两根, 各自现读那一天的分区, 6 个数逐个相等才算没被改过。"""
    if copy.is_empty():
        return True
    for i in {0, copy.height - 1}:
        row = copy[i]
        d = row["date"][0]
        pdir = parts.get(d)
        if pdir is None:
            return False
        live = _scan(_files([pdir]), symbol, cols)
        if live.height != 1 or not live.equals(row):
            return False
    return True


def read(data_dir: Path, asset_type: str, symbol: str, end: date, cols: list[str]) -> pl.DataFrame | None:
    """这只票截至 `end` 的日 K(按分区原样, 未叠盘中最新那一根)。

    返回 None = 这里帮不上忙(未知资产类型、代码不像代码、没有分区目录、读写出错),
    调用方退回原来的直接扫分区。
    """
    src_name = _SOURCE_DIRS.get(asset_type)
    if src_name is None or not _SAFE_SYMBOL.fullmatch(symbol):
        return None
    parts = _partitions(Path(data_dir) / src_name)
    if not parts:
        return None
    try:
        return _read(Path(data_dir), asset_type, symbol, end, cols, parts)
    except Exception as e:  # noqa: BLE001 —— 副本只是加速, 出任何错都退回原路
        logger.warning("个股日K副本不可用, 退回扫分区 %s %s: %s", asset_type, symbol, e)
        return None


def _read(data_dir: Path, asset_type: str, symbol: str, end: date, cols: list[str],
          parts: list[tuple[date, Path]]) -> pl.DataFrame:
    # 分区不够多就不建副本, 全部现读(本来也不慢)
    if len(parts) <= TAIL_DAYS:
        return _scan(_files([p for d, p in parts if d <= end]), symbol, cols)
    base = Path(data_dir) / CACHE_DIRNAME / asset_type
    pq, js = base / f"{symbol}.parquet", base / f"{symbol}.json"

    key = (str(data_dir), asset_type, symbol)
    with _locks_guard:
        lock = _locks.setdefault(key, threading.Lock())
    with lock:                         # 同一只票同时来两个请求, 只建一次
        loaded = _load_valid(pq, js, parts, symbol, cols)
        if loaded is None:
            cutoff = parts[-TAIL_DAYS - 1][0]          # 截止日: 倒数第 TAIL_DAYS+1 个分区
            head = [p for d, p in parts if d <= cutoff]
            copy = _scan(_files(head), symbol, cols)
            meta = {"v": FORMAT_VERSION, "cutoff": cutoff.isoformat(), "n": len(head),
                    "cols": cols, "built": time.time()}
            try:
                _write_atomic(copy, meta, pq, js)
            except OSError as e:       # 写不了(只读盘、满了)不影响这一次的结果
                logger.warning("个股日K副本写入失败 %s: %s", pq, e)
        else:
            copy, cutoff = loaded

    # 截止日之后的全部现读: 建副本那天的最近 10 天 + 之后每天新进来的(最多 7 天)
    tail = _scan(_files([p for d, p in parts if cutoff < d <= end]), symbol, cols)
    if end < cutoff:
        copy = copy.filter(pl.col("date") <= end)
    if tail.is_empty():
        return copy
    if copy.is_empty():
        return tail
    return pl.concat([copy, tail], how="vertical_relaxed")


def _load_valid(pq: Path, js: Path, parts: list[tuple[date, Path]],
                symbol: str, cols: list[str]) -> tuple[pl.DataFrame, date] | None:
    """副本还能用就返回 (副本, 它的截止日), 否则 None(→ 重建)。

    截止日是**建的那天**定下的, 之后库里每进一天它不跟着挪 —— 否则副本天天作废。
    多出来的那几天由调用方从分区现读。截止日之后的分区怎么变(新进、被删、被修)都与
    副本无关, 它们本来就是现读的。
    """
    try:
        meta = json.loads(js.read_text(encoding="utf-8"))
        cutoff = date.fromisoformat(meta["cutoff"])
    except (OSError, ValueError, TypeError, KeyError):
        return None
    head = [(d, p) for d, p in parts if d <= cutoff]
    if (
        not isinstance(meta, dict)
        or meta.get("v") != FORMAT_VERSION
        or meta.get("n") != len(head)               # 截止日之前补了历史 / 补了缺口 / 删了某天
        or meta.get("cols") != cols
        or not isinstance(meta.get("built"), (int, float))
        or time.time() - meta["built"] > MAX_AGE_SECONDS
    ):
        return None
    try:
        copy = pl.read_parquet(pq)
    except Exception:  # noqa: BLE001
        return None
    if copy.columns != [c for c in cols if c in copy.columns]:
        return None
    if not _anchor_ok(copy, dict(head), symbol, copy.columns):
        return None
    return copy, cutoff
