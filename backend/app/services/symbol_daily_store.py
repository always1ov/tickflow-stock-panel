"""[R491 / R492 · fork 增强] 按个股另存的日 K 副本 —— 取一只票的历史只开一个文件。

用户: 「按个股另存一份日K副本, 做吧」; R492 接进仓库的单票读取, 用户确认: 「做」。

## 为什么要有它

日 K 按**交易日**分区(`kline_daily_enriched/date=YYYY-MM-DD/part.parquet`, 每个文件是全市场)。
取一只票的一段历史 = 把区间里(实际是**全部**, glob 不按目录名剪枝)的日文件**逐个打开**挑出
这一只 —— 1000 个交易日的模拟库上一次 ~200~300 ms, 随历史年数线性变长。个股弹窗里关键价位、
复盘、六态、K 线各取一次, 复盘还取两次(先试列下推, 缺指标列再取一遍全量)。

这里把「这一只票存储的全部列」另存一个文件: 第一次取时顺手写下, 以后读它 + 最近十来个
日文件就够了。

## 只换「去哪儿拿」, 不换「拿到什么」

入口 `scan_symbol` 与仓库的 `_scan_daily_symbol` / `_scan_index_daily_symbol` /
`_scan_etf_daily_symbol` **一一对应**: 同样的 (代码, 起, 止, 列) 进, 同样的行、列、列序、
类型出。副本里是分区原样抄下来的数, 指标、六态、把握分都在拿到数之后才算, 一行不碰。
帮不上忙时返回 None, 仓库照原来扫分区。

## 副本里有什么、没有什么

    .symbol_daily_cache/<stock|index|etf>/<代码>.parquet      存储的全部列(与分区同一 schema)
    .symbol_daily_cache/<stock|index|etf>/<代码>.json         截止日 + 建它时库里的分区数

  · **建副本时最近 10 个交易日不进副本**, 每次现读 —— 盘中实时落盘、盘后管道补收盘价、
    修复过期分区, 改的都是最近几天, 这几天永远以分区为准。截止日建好就不再挪, 之后每进
    一天就多现读一个日文件(最多 7 天后重建, 现读的最多十几个文件);
  · 只取最近 10 天以内的请求根本不碰副本, 直接读那几个日文件。

## 什么时候作废重建(判据是内容, 不是修改时间)

盘后管道只要有一只票除权, 就会把**所有**日文件重写一遍 —— 按修改时间判断, 副本每天都会作废,
等于没做。所以这里抽查内容:

  1. **截止日之前的分区数变了**(补历史、补缺口、修复删掉了某一天) → 重建;
  2. **抽查两根**: 副本的第一根和最后一根, 各自现读那一天的分区对照整行。复权价一变
     (除权因子进来, 前复权改前面、后复权改后面), 首尾至少有一根对不上 → 重建;
  3. **最多用 7 天**, 到期重建一次, 兜住上面两条都抽不到的中间某天被改。

分区目录里出现看不懂的东西(不是 `date=YYYY-MM-DD` 的子目录、散落的 parquet) → 不用副本:
原来的 `**/*.parquet` 会把它们也读进来, 这里不去猜它们该怎么对齐。

副本坏了、读不了、写不了, 一律退回原来的直接扫分区 —— 它只是加速, 不是数据源。
这是 `data_dir` 下的派生缓存, 整个目录删掉也没关系, 下次取时自动重建。每种资产最多留
`MAX_COPIES` 份, 超出删最早建的 —— 自定义策略逐只扫全市场也撑不爆硬盘。
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

from app.parquet import ENRICHED_STORAGE_SCHEMA, scan_enriched_parquet
from app.polars_guard import guarded_collect

logger = logging.getLogger(__name__)

CACHE_DIRNAME = ".symbol_daily_cache"
TAIL_DAYS = 10
MAX_AGE_SECONDS = 7 * 86400
MAX_COPIES = 800
FORMAT_VERSION = 2
STORE_COLS = list(ENRICHED_STORAGE_SCHEMA)

_SOURCE_DIRS = {
    "stock": "kline_daily_enriched",
    "index": "kline_index_enriched",
    "etf": "kline_etf_enriched",
}
# 代码要拼进文件名: 首字符必须是字母数字(挡 `.` `..`), 整串匹配(`$` 会放过结尾换行)
_SAFE_SYMBOL = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,31}")
_locks_guard = threading.Lock()
_locks: dict[tuple[str, str, str], threading.Lock] = {}


def _partitions(src: Path) -> list[tuple[date, Path]] | None:
    """按日期升序列出分区: (交易日, 分区目录)。只看目录名, 不打开文件。

    目录里有看不懂的东西就返回 None(→ 不用副本), 理由见模块说明。
    """
    out: list[tuple[date, Path]] = []
    try:
        entries = list(os.scandir(src))
    except OSError:
        return None
    for e in entries:
        if e.is_dir():
            if not e.name.startswith("date="):
                return None
            try:
                out.append((date.fromisoformat(e.name[5:]), Path(e.path)))
            except ValueError:
                return None
        elif e.name.endswith(".parquet"):
            return None
    out.sort(key=lambda x: x[0])
    return out


def _files(dirs: list[Path]) -> list[str]:
    files: list[str] = []
    for d in dirs:
        files.extend(sorted(str(p) for p in d.rglob("*.parquet")))
    return files


def _empty() -> pl.DataFrame:
    return pl.DataFrame(schema=ENRICHED_STORAGE_SCHEMA)


def _scan(files: list[str], symbol: str) -> pl.DataFrame:
    """与仓库 `_scan_*_symbol` 同一个读法(同 schema、同类型放宽), 只是文件由这里点名。"""
    if not files:
        return _empty()
    lf = scan_enriched_parquet(files, cast_options=pl.ScanCastOptions(integer_cast="allow-float"))
    return guarded_collect(lf.filter(pl.col("symbol") == symbol).sort("date"))


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


def _trim(base: Path) -> None:
    """超过 MAX_COPIES 份就删最早建的, 删到九成(免得每建一份都要删一份)。"""
    try:
        copies = [p for p in base.glob("*.parquet")]
        if len(copies) <= MAX_COPIES:
            return
        copies.sort(key=lambda p: p.stat().st_mtime)
        for p in copies[: len(copies) - MAX_COPIES * 9 // 10]:
            p.unlink(missing_ok=True)
            p.with_suffix(".json").unlink(missing_ok=True)
    except OSError as e:
        logger.debug("个股日K副本清理跳过: %s", e)


def _anchor_ok(copy: pl.DataFrame, parts: dict[date, Path], symbol: str) -> bool:
    """副本首尾两根, 各自现读那一天的分区, 整行逐个相等才算没被改过。"""
    if copy.is_empty():
        return True
    for i in {0, copy.height - 1}:
        row = copy[i]
        pdir = parts.get(row["date"][0])
        if pdir is None:
            return False
        live = _scan(_files([pdir]), symbol)
        if live.height != 1 or not live.equals(row):
            return False
    return True


def scan_symbol(data_dir: Path, asset_type: str, symbol: str, start: date, end: date,
                columns: list[str] | None) -> pl.DataFrame | None:
    """与仓库 `_scan_*_symbol(symbol, start, end, columns)` 同一个结果, 读的是副本。

    返回 None = 这里帮不上忙(未知资产类型、代码不像代码、分区目录不存在或看不懂、读写出错),
    调用方照原来扫分区。
    """
    src_name = _SOURCE_DIRS.get(asset_type)
    if src_name is None or not isinstance(symbol, str) or not _SAFE_SYMBOL.fullmatch(symbol):
        return None
    parts = _partitions(Path(data_dir) / src_name)
    if not parts:
        return None
    try:
        df = _history(Path(data_dir), asset_type, symbol, start, end, parts)
    except Exception as e:  # noqa: BLE001 —— 副本只是加速, 出任何错都退回原路
        logger.warning("个股日K副本不可用, 退回扫分区 %s %s: %s", asset_type, symbol, e)
        return None
    df = df.filter((pl.col("date") >= start) & (pl.col("date") <= end))
    if columns:
        df = df.select([c for c in columns if c in STORE_COLS])
    return df


def _history(data_dir: Path, asset_type: str, symbol: str, start: date, end: date,
             parts: list[tuple[date, Path]]) -> pl.DataFrame:
    """[start, end] 覆盖到的那些行(还没按日期列精确裁剪)。"""
    in_range = [(d, p) for d, p in parts if start <= d <= end]
    # 分区不够多, 或只要最近 10 天以内: 不碰副本, 直接读那几个日文件
    if len(parts) <= TAIL_DAYS or start > parts[-TAIL_DAYS - 1][0]:
        return _scan(_files([p for _, p in in_range]), symbol)

    base = data_dir / CACHE_DIRNAME / asset_type
    pq, js = base / f"{symbol}.parquet", base / f"{symbol}.json"
    key = (str(data_dir), asset_type, symbol)
    with _locks_guard:
        lock = _locks.setdefault(key, threading.Lock())
    with lock:                         # 同一只票同时来两个请求, 只建一次
        loaded = _load_valid(pq, js, parts, symbol)
        if loaded is None:
            cutoff = parts[-TAIL_DAYS - 1][0]          # 截止日: 倒数第 TAIL_DAYS+1 个分区
            head = [p for d, p in parts if d <= cutoff]
            copy = _scan(_files(head), symbol)
            meta = {"v": FORMAT_VERSION, "cutoff": cutoff.isoformat(), "n": len(head),
                    "built": time.time()}
            try:
                _write_atomic(copy, meta, pq, js)
                _trim(base)
            except OSError as e:       # 写不了(只读盘、满了)不影响这一次的结果
                logger.warning("个股日K副本写入失败 %s: %s", pq, e)
        else:
            copy, cutoff = loaded

    # 截止日之后的全部现读: 建副本那天的最近 10 天 + 之后每天新进来的(最多 7 天)
    tail = _scan(_files([p for d, p in in_range if d > cutoff]), symbol)
    return pl.concat([copy, tail])     # 严格拼接: 类型对不上就抛错 → 退回原路


def _load_valid(pq: Path, js: Path, parts: list[tuple[date, Path]],
                symbol: str) -> tuple[pl.DataFrame, date] | None:
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
        meta.get("v") != FORMAT_VERSION
        or meta.get("n") != len(head)               # 截止日之前补了历史 / 补了缺口 / 删了某天
        or not isinstance(meta.get("built"), (int, float))
        or time.time() - meta["built"] > MAX_AGE_SECONDS
    ):
        return None
    try:
        copy = pl.read_parquet(pq)
    except Exception:  # noqa: BLE001
        return None
    if copy.schema != pl.Schema(ENRICHED_STORAGE_SCHEMA):
        return None
    if not _anchor_ok(copy, dict(head), symbol):
        return None
    return copy, cutoff
