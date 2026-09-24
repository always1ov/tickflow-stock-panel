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

  0. **盘后管道重算过的票当场作废**(R493): 除权因子变了的那几只, 管道重算完就删它们的副本;
     全量重建则整类作废。这是「这只票自己的复权价变了就重建」的正面兑现, 下面几条是兜底;
  1. **截止日之前的分区数变了**(补历史、补缺口、修复删掉了某一天) → 重建;
  2. **抽查首尾**: 副本第一根与最后一根那两天, 现读分区里这只票的**全部行**对照
     (复权价一变, 前复权改前面、后复权改后面, 首尾至少一头对不上);
  3. **抽查两头外侧**(R493): 第一根的前一个交易日、以及截止日(若副本最后一根早于它),
     分区里这只票必须**没有行** —— 往已有日文件里补了这只票更早的历史、或补了停牌后
     那段, 分区数不变、首尾也没变, 只有这里看得出来;
  4. **最多用 7 天**, 到期重建一次, 兜住以上都抽不到的中间某段被改。

截止日前一根都没有的票(还没同步历史的、刚上市十来天的、查错代码的)**不留空副本** ——
空副本无从抽查, 历史补进来之后会被当成「没变」。这类票每次照原来扫分区。

管道正在发布(发布标记未就绪)时不建也不用副本, 照原来扫分区 —— 免得把一半新一半旧的
状态存下来。盘中实时落盘也走同一个发布标记, 但只占换文件那几毫秒: 撞上了先等一小会儿
(最多 0.2 秒), 就绪了照常用副本, 见 `_publishing`。

## 盘中(R494 梳理)

  · 实时只写「今天」分区, 它永远在现读的那十来天里, 副本本身不受盘中影响;
  · 今天那根的数: 磁盘上是最近一轮实时落盘的值; 股票再由仓库用最新行情缓存覆盖
    (`get_daily` 快路径, 与原来同一段代码); 两张副图与 K 线接口还会叠
    `_maybe_inject_live_candle` 的实时蜡烛 —— 三层都与原来一样, 副本没有插手;
  · 盘中建副本照常: 截止日取倒数第 11 个分区, 今天那个分区自然落在截止日之后。

分区目录里出现看不懂的东西(不是 `date=YYYY-MM-DD` 的子目录、散落的 parquet) → 不用副本:
原来的 `**/*.parquet` 会把它们也读进来, 这里不去猜它们该怎么对齐。

副本坏了、读不了、写不了, 一律退回原来的直接扫分区 —— 它只是加速, 不是数据源。
盘后管道跑完会在后台把持仓与自选的副本提前建好(R495, 见文件末尾 `start_warmup`)。
这是 `data_dir` 下的派生缓存, 整个目录删掉也没关系, 下次取时自动重建; 「清空本地数据」
会一并删掉它。每种资产最多留 `MAX_COPIES` 份, 超出删**最久没用**的(读到一次就刷新一次
修改时间) —— 自定义策略逐只扫全市场也撑不爆硬盘, 也挤不掉天天在看的那几只。

「与原路逐位相同」依赖一个写入端保证的前提: 分区目录名就是行里的 `date`(仓库
`_write_daily_partition` 按 `date` 列 partition_by 落盘, 没有别的写法)。最近几天按目录名
挑文件, 若有人手工把某天的行塞进别的日期目录, 这里与原路会差那几行。
"""
from __future__ import annotations

import contextlib
import contextvars
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

from app.enriched_generation import enriched_publication_incomplete
from app.parquet import ENRICHED_STORAGE_SCHEMA, scan_enriched_parquet
from app.polars_guard import guarded_collect

logger = logging.getLogger(__name__)

CACHE_DIRNAME = ".symbol_daily_cache"
TAIL_DAYS = 10
MAX_AGE_SECONDS = 7 * 86400
MAX_COPIES = 800
ORPHAN_SECONDS = 3600
PUBLISH_WAIT_SECONDS = 0.2
FORMAT_VERSION = 3
STORE_COLS = list(ENRICHED_STORAGE_SCHEMA)

# 与仓库 `_enriched_glob` 等三处同名; 这三个目录名在整个后端(管道、视图、清空数据)都写死,
# 改名本身就是一次全局迁移, 这里不另起一层间接
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


# 盘后预热在后台车道读(R495), 页面请求照旧走 interactive —— 预热不许挤占看盘
_priority: contextvars.ContextVar[str] = contextvars.ContextVar("symbol_daily_priority", default="interactive")


def _scan(files: list[str], symbol: str) -> pl.DataFrame:
    """与仓库 `_scan_*_symbol` 同一个读法(同 schema、同类型放宽), 只是文件由这里点名。"""
    if not files:
        return _empty()
    lf = scan_enriched_parquet(files, cast_options=pl.ScanCastOptions(integer_cast="allow-float"))
    return guarded_collect(lf.filter(pl.col("symbol") == symbol).sort("date"),
                           priority=_priority.get())  # type: ignore[arg-type]


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
    """超过 MAX_COPIES 份就删最久没用的(修改时间 = 最后一次读到), 删到九成(免得每建一份
    都要删一份)。顺手清掉崩溃留下的临时文件和没有数据文件的说明。"""
    try:
        now = time.time()
        for p in base.glob(".*.tmp"):
            if now - p.stat().st_mtime > ORPHAN_SECONDS:
                p.unlink(missing_ok=True)
        for js in base.glob("*.json"):
            if not js.with_suffix(".parquet").exists():
                js.unlink(missing_ok=True)
        copies = list(base.glob("*.parquet"))
        if len(copies) <= MAX_COPIES:
            return
        copies.sort(key=lambda p: p.stat().st_mtime)
        for p in copies[: len(copies) - MAX_COPIES * 9 // 10]:
            p.unlink(missing_ok=True)
            p.with_suffix(".json").unlink(missing_ok=True)
    except OSError as e:
        logger.debug("个股日K副本清理跳过: %s", e)


def invalidate(data_dir: Path, asset_type: str, symbols: list[str] | None = None) -> None:
    """[R493] 盘后管道重算过的票: 删它们的副本。symbols=None → 这一类整个作废(全量重建)。

    只删不建, 下次有人取时再建; 删失败只记日志 —— 抽查照样兜得住。
    """
    base = Path(data_dir) / CACHE_DIRNAME / asset_type
    if not base.exists():
        return
    try:
        if symbols is None:
            targets = list(base.glob("*.parquet"))
        else:
            targets = [base / f"{s}.parquet" for s in symbols
                       if isinstance(s, str) and _SAFE_SYMBOL.fullmatch(s)]
        for pq in targets:
            pq.unlink(missing_ok=True)
            pq.with_suffix(".json").unlink(missing_ok=True)
    except OSError as e:
        logger.warning("个股日K副本作废失败 %s: %s", asset_type, e)


def _anchor_ok(saved: pl.DataFrame, head: list[tuple[date, Path]], symbol: str) -> bool:
    """抽查: 首尾两天分区里这只票的全部行与副本相同; 两头外侧那两天分区里没有这只票。"""
    if saved.is_empty():
        return False                   # 空副本无从抽查, 不认(建的时候也不会留)
    by_date = dict(head)
    dates = [d for d, _ in head]
    first, last = saved["date"][0], saved["date"][-1]
    for d in {first, last}:
        pdir = by_date.get(d)
        if pdir is None:
            return False
        if not _scan(_files([pdir]), symbol).equals(saved.filter(pl.col("date") == d)):
            return False
    i = dates.index(first) if first in by_date else 0
    outside = ([dates[i - 1]] if i > 0 else []) + ([dates[-1]] if dates[-1] > last else [])
    return all(_scan(_files([by_date[d]]), symbol).is_empty() for d in outside)


def scan_symbol(data_dir: Path, asset_type: str, symbol: str, start: date, end: date,
                columns: list[str] | None) -> pl.DataFrame | None:
    """与仓库 `_scan_*_symbol(symbol, start, end, columns)` 同一个结果, 读的是副本。

    返回 None = 这里帮不上忙(未知资产类型、代码不像代码、分区目录不存在或看不懂、读写出错),
    调用方照原来扫分区。
    """
    src_name = _SOURCE_DIRS.get(asset_type)
    if src_name is None or not isinstance(symbol, str) or not _SAFE_SYMBOL.fullmatch(symbol):
        return None
    if _publishing(Path(data_dir), asset_type):
        return None                    # 管道正在发布: 照原来扫, 不把半新半旧存下来
    parts = _partitions(Path(data_dir) / src_name)
    if not parts:
        return None
    try:
        df = _history(Path(data_dir), asset_type, symbol, start, end, parts)
        df = df.filter((pl.col("date") >= start) & (pl.col("date") <= end))
        if columns:
            df = df.select([c for c in columns if c in STORE_COLS])
        return df
    except Exception as e:  # noqa: BLE001 —— 副本只是加速, 出任何错都退回原路
        logger.warning("个股日K副本不可用, 退回扫分区 %s %s: %s", asset_type, symbol, e)
        return None


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
    # 单票锁: 只挡同一只票的并发请求(single-flight, 第二个等第一个建完直接读, 否则它也得
    # 把全部日文件扫一遍); 别的票不受影响。CONTRIBUTING §6.2 防的是全局锁里扫盘拖住所有人
    with lock:
        loaded = _load_valid(pq, js, parts, symbol)
        if loaded is None:
            cutoff = parts[-TAIL_DAYS - 1][0]          # 截止日: 倒数第 TAIL_DAYS+1 个分区
            head = [p for d, p in parts if d <= cutoff]
            saved = _scan(_files(head), symbol)
            meta = {"format": FORMAT_VERSION, "cutoff": cutoff.isoformat(),
                    "partitions": len(head), "built": time.time()}
            try:
                if saved.is_empty():
                    # 截止日前没有这只票: 不留空副本(见模块说明), 旧的也删掉
                    pq.unlink(missing_ok=True)
                    js.unlink(missing_ok=True)
                elif _publishing(data_dir, asset_type):
                    pass                                # 建的途中管道开始发布: 这份不存
                else:
                    _write_atomic(saved, meta, pq, js)
                    _trim(base)
            except OSError as e:       # 写不了(只读盘、满了)不影响这一次的结果
                logger.warning("个股日K副本写入失败 %s: %s", pq, e)
        else:
            saved, cutoff = loaded
            with contextlib.suppress(OSError):
                os.utime(pq)                            # 记一次「最近用过」, 淘汰按它排

    # 截止日之后的全部现读: 建副本那天的最近 10 天 + 之后每天新进来的(最多 7 天)
    tail = _scan(_files([p for d, p in in_range if d > cutoff]), symbol)
    return pl.concat([saved, tail])    # 严格拼接: 类型对不上就抛错 → 退回原路


def _publishing(data_dir: Path, asset_type: str) -> bool:
    """发布标记未就绪 = 有人正在改分区。先等一小会儿再下结论(R494):

    盘中实时每轮(默认 6 秒, 最快 1 秒)覆写「今天」分区, 标记只在换文件那几毫秒处于发布中;
    盘后管道重算历史是**整轮一次发布**, 一挂就是几分钟。等 PUBLISH_WAIT_SECONDS 还没就绪
    的才当作管道在跑 —— 实时落盘撞上了就等它几毫秒, 不必为此退回扫全部日文件。
    指数没有发布标记(仓库只给股票和 ETF 发), 标记文件不存在即视为就绪。
    """
    deadline = time.monotonic() + PUBLISH_WAIT_SECONDS
    while enriched_publication_incomplete(data_dir, asset_type):
        if time.monotonic() >= deadline:
            return True
        time.sleep(0.01)
    return False


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
        meta.get("format") != FORMAT_VERSION
        or meta.get("partitions") != len(head)      # 截止日之前补了历史 / 补了缺口 / 删了某天
        or not isinstance(meta.get("built"), (int, float))
        or time.time() - meta["built"] > MAX_AGE_SECONDS
    ):
        return None
    try:
        saved = pl.read_parquet(pq)
    except Exception:  # noqa: BLE001
        return None
    # 列、类型不对也在这里被拦: 抽查拿现读的整行比, 列一不同就不相等
    if not head or not _anchor_ok(saved, head, symbol):
        return None
    return saved, cutoff


# ── [R495] 盘后预热: 持仓与自选的副本提前建好, 打开就快 ────────────────────────
#
# 用户: 「做第1条盘后预热」。副本本来是「谁先打开谁建」, 每只票第一次打开要多等一次全扫
# (模拟库 ~0.5 秒); 除权作废的、用满 7 天到期的, 也是下一次打开时才重建。盘后管道跑完
# 顺手在后台把持仓和自选挨个建好, 第二天打开就是读副本。
#
#   · 建出来的与打开时建的是同一份(同一个 scan_symbol), 预热只是把时间挪到盘后;
#   · 后台车道读(polars_guard 的 background), 页面请求优先;
#   · 一次只建一只, 两只之间歇一下; 管道又开始发布(scan_symbol 等满仍在发布而让位)
#     就整轮停下, 不和管道抢;
#   · 最多预热 MAX_COPIES 的一半, 不把副本池里别的票全挤出去;
#   · 同一时刻只跑一轮; 后台守护线程, 不拦进程退出。

WARM_PAUSE_SECONDS = 0.05
_warm_lock = threading.Lock()


def warm(data_dir: Path, symbols: list[str], resolve_asset_type, end: date,
         stop: threading.Event | None = None) -> dict:
    """按给定顺序挨个把副本建好(已有效的只抽查不重建)。返回 {建好/跳过/停下的原因}。"""
    done, skipped = 0, 0
    reason = "完成"
    token = _priority.set("background")
    try:
        for sym in symbols[: MAX_COPIES // 2]:
            if stop is not None and stop.is_set():
                reason = "收到停止"
                break
            try:
                asset = resolve_asset_type(sym)
            except Exception:  # noqa: BLE001
                asset = None
            got = scan_symbol(data_dir, asset, sym, date(1990, 1, 1), end, ["date"])
            if got is None:
                if _publishing(Path(data_dir), asset):
                    reason = "管道正在发布, 让位"
                    break
                skipped += 1                       # 认不出资产类型 / 代码不像代码 / 库里没这类数据
            else:
                done += 1
            time.sleep(WARM_PAUSE_SECONDS)
    finally:
        _priority.reset(token)
    return {"done": done, "skipped": skipped, "reason": reason}


def _warm_targets() -> list[str]:
    """持仓在前, 自选在后, 去重保序。任何一处读失败都只少那一部分, 不抛。"""
    out: list[str] = []
    try:
        from app.services import effective_positions
        out += sorted(s for s, p in effective_positions.load_all().items() if p.get("held"))
    except Exception as e:  # noqa: BLE001
        logger.warning("预热取持仓失败: %s", e)
    try:
        from app.tickflow.pools import get_pool
        out += list(get_pool("watchlist"))
    except Exception as e:  # noqa: BLE001
        logger.warning("预热取自选失败: %s", e)
    targets: list[str] = []
    for x in out:
        sym = x.strip().upper() if isinstance(x, str) else ""
        if sym and sym not in targets:
            targets.append(sym)
    return targets


def start_warmup(repo, end: date | None = None) -> bool:
    """盘后管道跑完调用: 后台起一轮预热, 立刻返回。已有一轮在跑就不再起(返回 False)。"""
    if not _warm_lock.acquire(blocking=False):
        return False
    from app.market_time import cn_today

    def run() -> None:
        try:
            t0 = time.monotonic()
            targets = _warm_targets()
            res = warm(repo.store.data_dir, targets, repo.resolve_asset_type, end or cn_today())
            logger.info("个股日K副本盘后预热: %d 只建好/有效, %d 只跳过, 共 %d 只, %.1f 秒, %s",
                        res["done"], res["skipped"], len(targets), time.monotonic() - t0, res["reason"])
        except Exception:  # noqa: BLE001 —— 预热失败只是明天第一次打开慢一点
            logger.exception("个股日K副本盘后预热失败")
        finally:
            _warm_lock.release()

    threading.Thread(target=run, name="symbol-daily-warmup", daemon=True).start()
    return True
