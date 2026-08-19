"""盘后管道 + 盘前维表同步。

调度:
  09:10 盘前 — 同步个股维表 instruments (全量覆盖)
  15:30 盘后 — 日K同步 + 增量除权因子 + enriched 计算 + 刷新视图

盘后同步策略:
  日 K: QuoteService 交易时段已实时落盘 → 有数据时跳过 batch,首次拉 1 年区间
  除权因子: 从已有数据最新日期的下一天开始增量获取,避免重复拉取和计算
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

import polars as pl
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.indicators.pipeline import run_pipeline
from app.config import settings
from app.services import index_sync, instrument_sync, kline_sync, preferences as _prefs
from app.tickflow.capabilities import Cap, CapabilitySet
from app.tickflow.pools import DEMO_SYMBOLS, get_pool
from app.tickflow.repository import KlineRepository

logger = logging.getLogger(__name__)

ProgressCb = Callable[..., None]


class PipelineStageError(RuntimeError):
    """管道有阶段软失败(数据可能陈旧)时抛出, 让上层 job_store 把任务标记为 failed。

    这些阶段单独 try/except 吞掉异常以不中断整条管道, 但一旦失败即代表对应数据陈旧。
    抛出前进度协议已走完(done/100), 故前端进度条正常收尾, 仅终态如实反映为 failed ——
    不再"部分失败却报成功"。
    """

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("盘后管道部分阶段失败: " + "; ".join(errors))


def _noop(stage: str, pct: int, msg: str, **kwargs) -> None:  # noqa: ARG001
    pass


def _invalidate(table: str | None = None) -> None:
    """stage 写完调用,让 /api/data/status 只重算被影响的那张表。"""
    from app.api.data import invalidate_data_cache
    invalidate_data_cache(table)


def _resolve_universe(capset: CapabilitySet, repo=None) -> list[str]:
    """解析标的池 — 以 CN_Equity_A (沪深京A股 ~5522只) 为主。

    有 batch 能力 → 直接拉 CN_Equity_A universe
    其他用户 → 用 instruments parquet + watchlist 兜底

    repo 传入时过滤自选兜底里的指数 symbol (指数日K走独立 kline_index_* 存储,
    进股票池会污染 kline_daily/kline_minute)。ETF 刻意保留 (既有行为)。
    """
    if capset.has(Cap.KLINE_DAILY_BATCH):
        try:
            all_a = get_pool("CN_Equity_A", refresh=True)
            if all_a:
                return sorted(all_a)
        except Exception as e:  # noqa: BLE001
            logger.warning("CN_Equity_A pool unavailable, fallback: %s", e)

    # Free 用户兜底: instruments parquet + watchlist + demo
    base: set[str] = set(DEMO_SYMBOLS)
    base.update(get_pool("watchlist"))
    d = Path(settings.data_dir)
    inst_path = d / "instruments" / "instruments.parquet"
    if inst_path.exists():
        try:
            inst = pl.read_parquet(inst_path, columns=["symbol"])
            base.update(inst["symbol"].to_list())
        except Exception as e:  # noqa: BLE001
            logger.warning("instruments supplement failed: %s", e)
    # 过滤自选兜底里的指数 symbol (指数日K走独立 kline_index_* 存储,
    # 进股票池会污染 kline_daily/kline_minute)。ETF 刻意保留 (既有行为)。
    if repo is not None:
        base -= set(repo.get_index_symbol_set())
    return sorted(base)


def run_instruments_sync(repo: KlineRepository) -> dict:
    """盘前同步个股维表。

    维表含当日涨跌停价 (limit_up/down), 同步完成后刷新 enriched 内存缓存,
    确保跨天后连板梯队/选股等读到的是基于最新维表的数据 (而非前一交易日残留)。
    """
    rows = instrument_sync.sync_instruments(repo.store.data_dir)
    _refresh_instruments_view(repo)
    _invalidate("instruments")
    # 维表更新后重建 enriched 缓存 (clear + refresh, 与设置页「清理并刷新」同等效果)
    if rows > 0:
        repo.clear_cache()
        repo.refresh_cache()
    return {"instruments_rows": rows}


def run_now(
    repo: KlineRepository,
    capset: CapabilitySet,
    on_progress: ProgressCb | None = None,
    override_start_date: _date | None = None,
) -> dict:
    """立即执行一次盘后管道,支持进度回调。

    跳过的 stage **不 emit**,避免前端把"无 capability"的卡片错误标记为 active/done。
    result 里带 skipped_stages 列表供前端展示。

    override_start_date: 传入时强制走 batch 拉取分支,用该日期作为日K/除权/指数的
        拉取起点(到今天),用于「数据修正/补数据」场景。None 时走原有自动判定逻辑。
    """
    emit = on_progress or _noop
    skipped: list[str] = []
    # 阶段软失败累积: 下列阶段 try/except 吞异常以不中断管道, 但失败即代表数据可能陈旧。
    # 管道末尾若非空则抛 PipelineStageError, 让任务终态如实标记为 failed(而非误报成功)。
    stage_errors: list[str] = []

    # Step 0: 先同步个股维表, 再解析标的池 — 确保标的池基于最新 instruments
    emit("sync_instruments", 2, "同步个股维表…")
    inst_rows = instrument_sync.sync_instruments(repo.store.data_dir)
    if inst_rows > 0:
        _refresh_instruments_view(repo)
    emit("sync_instruments", 8, f"个股维表同步完成,{inst_rows} 只标的")
    _invalidate("instruments")

    emit("resolve_universe", 9, "解析标的池…")
    universe = _resolve_universe(capset, repo)
    emit("resolve_universe", 10, f"标的池规模:{len(universe)} 只")

    # Step 1: 日 K 同步
    #   override_start_date 传入 → 强制 batch 拉取 [override_start_date ~ today] (数据修正)
    #   付费档 + 今天有数据 → 实时行情接口拉一次覆写（1请求全市场）
    #   有历史数据 → batch K-line API 补齐缺口
    #   无任何数据 → batch K-line API 拉首次 1 年
    from datetime import date as _date, timedelta as _td, datetime as _dt
    latest_daily = repo.latest_daily_date()
    today = _date.today()
    today_exists = latest_daily and latest_daily >= today

    # 历史稀疏检测: 全局 max(date) 会被部分写入(自选实时快照落的当日行 / 被中断的
    # 首次拉取)拉高, 让下方"补缺口"分支误以为已是最新, 起点=今天 → 一年历史永远
    # 不会回补(涨跌幅/指标全算不出)。近一年正常应有 ~240 个交易日分区, 远低于此
    # (<120)即判定存在历史大洞 → 强制走首次拉取分支从一年前重拉(merge-upsert 幂等)。
    history_sparse = False
    if latest_daily and not override_start_date:
        try:
            _res = repo.execute_one(
                "SELECT count(DISTINCT date) FROM kline_daily WHERE date >= ?",
                [(today - _td(days=365)).isoformat()],
            )
            _n_dates = int(_res[0]) if _res and _res[0] is not None else 0
            if _n_dates < 120:
                history_sparse = True
                logger.warning(
                    "日K历史稀疏: 近一年仅 %d 个交易日分区(正常约 240), 判定存在历史缺口, 将从一年前重拉",
                    _n_dates)
        except Exception as e:  # noqa: BLE001
            logger.warning("history sparse detection failed: %s", e)
    new_daily_days = 0
    # 日K范围拉取的起点(分支3补缺口/分支4首次/数据修正); 实时增量/跳过时为 None。
    # 供 Step 1.5 除权因子回溯范围对齐: 范围拉取→用日K范围, 非范围→最近N天兜底。
    daily_range_start: _date | None = None

    # A 股日K拉取开关(默认开);关闭时跳过日K同步,保留已有数据。
    # 数据修正(override_start_date)时即使关闭开关也强制拉取 — 修正就是来补数据的。
    pull_a_share = _prefs.get_pipeline_pull_a_share()
    if not pull_a_share and not override_start_date:
        emit("sync_daily", 45, "已跳过 A 股日K同步(拉取内容未勾选)")
        logger.info("sync_daily: skipped (pipeline_pull_a_share=False)")
    elif override_start_date:
        # 数据修正: 强制用传入日期作起点 batch 拉取, 忽略实时行情覆写分支。
        start_date = override_start_date
        daily_range_start = start_date
        emit("sync_daily", 12, f"获取日K [{start_date} ~ {today}]…")
        logger.info("sync_daily: [%s ~ %s] repair/override", start_date, today)

        def _daily_chunk_progress(cur: int, tot: int) -> None:
            emit("sync_daily", 12 + int(33 * cur / tot),
                 f"日K 批次 {cur}/{tot}", stage_pct=int(100 * cur / tot), skip_log=True)
        written_daily = kline_sync.sync_and_persist_daily_batch(
            universe, repo, capset,
            start_date=_dt.combine(start_date, _dt.min.time()),
            end_date=_dt.combine(today, _dt.min.time()),
            on_chunk_done=_daily_chunk_progress,
        )
        gap_days = (today - start_date).days
        new_daily_days = gap_days
        emit("sync_daily", 45, f"日K 完成,覆盖 {gap_days} 天")
        logger.info("sync_daily: [%s ~ %s] done, %d days", start_date, today, gap_days)
    elif today_exists and not history_sparse and capset.has(Cap.QUOTE_POOL) and _prefs.get_daily_data_provider() == "tickflow":
        # 付费档:今天有数据(QuoteService 已落盘)→ 实时行情覆写,确保最新。
        # free/none 档无 quote.pool 能力,即便今天已有数据(如从 expert 降级),
        # 也降级到下方 batch 路径刷新,避免调用无权限的实时行情接口。
        emit("sync_daily", 12, f"获取日K [{today} ~ {today}] 实时行情…")
        written_daily = kline_sync.sync_daily_by_quotes(repo)
        new_daily_days = 1
        emit("sync_daily", 45, f"日K 完成,{written_daily} 只标的")
        logger.info("sync_daily: [%s ~ %s] live quotes, %d symbols", today, today, written_daily)
    elif latest_daily and not history_sparse:
        # 有历史 → batch 补齐缺口。
        # 也覆盖"今天已有数据但无实时行情权限(free/none)"的降级场景:
        #   此时 start_date = latest_daily = today,batch 刷新当天日K。
        start_date = latest_daily
        daily_range_start = start_date
        emit("sync_daily", 12, f"获取日K [{start_date} ~ {today}]…")
        logger.info("sync_daily: [%s ~ %s] %s", start_date, today,
                    "refresh today" if today_exists else "gap fill")

        def _daily_chunk_progress(cur: int, tot: int) -> None:
            emit("sync_daily", 12 + int(33 * cur / tot),
                 f"日K 批次 {cur}/{tot}", stage_pct=int(100 * cur / tot), skip_log=True)
        written_daily = kline_sync.sync_and_persist_daily_batch(
            universe, repo, capset,
            start_date=_dt.combine(start_date, _dt.min.time()),
            end_date=_dt.combine(today, _dt.min.time()),
            on_chunk_done=_daily_chunk_progress,
        )
        gap_days = (today - start_date).days
        new_daily_days = gap_days
        emit("sync_daily", 45, f"日K 完成,覆盖 {gap_days} 天")
        logger.info("sync_daily: [%s ~ %s] done, %d days", start_date, today, gap_days)
    else:
        # 首次(无任何数据) 或 历史稀疏(近一年分区远少于正常, 存在大洞) → batch 拉 1 年
        start_date = today - _td(days=365)
        daily_range_start = start_date
        _why = "检测到历史缺口,重拉一年" if history_sparse else "首次拉取"
        emit("sync_daily", 12, f"获取日K [{start_date} ~ {today}]({_why})…")
        logger.info("sync_daily: [%s ~ %s] %s", start_date, today,
                    "sparse backfill" if history_sparse else "initial fetch")

        def _daily_chunk_progress(cur: int, tot: int) -> None:
            emit("sync_daily", 12 + int(33 * cur / tot),
                 f"日K 批次 {cur}/{tot}", stage_pct=int(100 * cur / tot), skip_log=True)
        written_daily = kline_sync.sync_and_persist_daily_batch(
            universe, repo, capset,
            start_date=_dt.combine(start_date, _dt.min.time()),
            end_date=_dt.combine(today, _dt.min.time()),
            on_chunk_done=_daily_chunk_progress,
        )
        new_daily_days = 365
        emit("sync_daily", 45, "日K 完成")
        logger.info("sync_daily: [%s ~ %s] done", start_date, today)
    _invalidate("daily")

    # 单标的新鲜度: 全局 max(date) 会被任一有今日数据的标的"拉高", 掩盖停牌/复牌/
    # 一直拉失败而掉队的个股缺口(全局判据只刷"今天", 永不回补掉队标的的历史缺口)。
    # 这里检测并**可见化**(WARNING + 计入结果), 让掉队标的不再隐形。
    # (自动回补暂不做 —— 需带退市判定, 否则对已退市标的每轮空拉浪费 API 额度。)
    lagging_symbols: list[str] = []
    if pull_a_share and latest_daily:
        try:
            lagging_symbols = repo.symbols_lagging(today, min_gap_days=3)
            if lagging_symbols:
                logger.warning("日K新鲜度: %d 只标的落后 >3 日 (停牌/退市/拉取失败; 样例: %s)",
                               len(lagging_symbols), lagging_symbols[:10])
        except Exception as e:  # noqa: BLE001
            logger.warning("laggard detection failed: %s", e)
            stage_errors.append(f"laggard detection: {e}")

    # Step 1.5: 同步除权因子 — 范围与日K拉取方式对齐(TickFlow 路径, 需 Starter+;
    # 免费档无该能力时跳过, 复权指标按不复权价计算)
    written_adj = 0
    affected_symbols: list[str] = []
    if capset.has(Cap.ADJ_FACTOR):
        from datetime import datetime, timedelta
        adj_end = datetime.now()
        if daily_range_start is not None:
            adj_start = datetime.combine(daily_range_start, datetime.min.time())
        else:
            # 兜底拉最近 15 天: 覆盖春节/国庆最长约10天长假 + 故障恢复缓冲;
            # sync_adj_factor 内部 merge+unique 幂等, 多拉无副作用。
            adj_start = adj_end - timedelta(days=15)
        adj_start_str = adj_start.strftime("%Y-%m-%d")
        adj_end_str = adj_end.strftime("%Y-%m-%d")
        emit("sync_adj", 50, f"获取除权因子 [{adj_start_str} ~ {adj_end_str}]…")
        logger.info("sync_adj: [%s ~ %s] start", adj_start_str, adj_end_str)

        def _adj_chunk_progress(cur: int, tot: int) -> None:
            emit("sync_adj", 50 + int(10 * cur / tot),
                 f"除权因子批次 {cur}/{tot}", stage_pct=int(100 * cur / tot), skip_log=True)
        written_adj, affected_symbols = kline_sync.sync_adj_factor(
            universe, repo, capset,
            start_time=adj_start, end_time=adj_end,
            on_chunk_done=_adj_chunk_progress,
        )
        if affected_symbols:
            _refresh_single_view(repo, "adj_factor")
            emit("sync_adj", 60, f"除权因子完成,新增 {len(affected_symbols)} 只个股")
        else:
            emit("sync_adj", 60, "除权因子完成,无新增")
        _invalidate("adj_factor")
    else:
        skipped.append("sync_adj")
        logger.info("sync_adj skipped: no ADJ_FACTOR capability")

    # Step 2: 计算 enriched
    #   判断策略:
    #     - 首次 (enriched 目录不存在) → 全量
    #     - 往前扩展历史 (新日期 < enriched 已有最早日期) → 全量
    #       前面的除权因子会改变累积因子链,影响后面所有日期的复权价格
    #     - 往后新增日期 (新日期 > enriched 已有最晚日期)
    #       → 增量补新区块(所有标的) + 受除权影响个股全日期重算
    #     - 无新日期 + 有新除权因子 → 增量: 只重算受影响个股的全部日期
    #     - 无新日期 + 无变化 → 跳过
    enriched_dir = repo.store.data_dir / "kline_daily_enriched"
    enriched_exists = enriched_dir.exists() and any(enriched_dir.glob("date=*"))
    daily_dir = repo.store.data_dir / "kline_daily"
    daily_days = len(list(daily_dir.glob("date=*"))) if daily_dir.exists() else 0
    prev_enriched_days = len(list(enriched_dir.glob("date=*"))) if enriched_exists else 0

    # 判断新日期方向: 找 daily 和 enriched 的日期集合做比较
    forward_incremental = False
    backward_extension = False

    if daily_days > prev_enriched_days and enriched_exists:
        daily_dates = sorted(d.stem.split("=")[1] for d in daily_dir.glob("date=*"))
        enriched_dates = sorted(d.stem.split("=")[1] for d in enriched_dir.glob("date=*"))
        earliest_enriched = enriched_dates[0]
        latest_enriched = enriched_dates[-1]
        new_dates = set(daily_dates) - set(enriched_dates)
        if new_dates:
            # 有新日期早于 enriched 最早日期 → 往前扩展
            if any(d < earliest_enriched for d in new_dates):
                backward_extension = True
            # 有新日期晚于 enriched 最晚日期 → 往后新增
            if any(d > latest_enriched for d in new_dates):
                forward_incremental = True

    def _enriched_batch_progress(cur: int, tot: int) -> None:
        emit("compute_enriched", 65 + int(23 * cur / tot),
             f"计算指标 批次 {cur}/{tot}", stage_pct=int(100 * cur / tot), skip_log=True)

    if not enriched_exists or backward_extension:
        # 首次 或 往前扩展 → 全量
        emit("compute_enriched", 65, "全量计算 enriched…")
        logger.info("compute_enriched: full rebuild (first=%s, backward=%s, daily=%d, enriched=%d)",
                    not enriched_exists, backward_extension, daily_days, prev_enriched_days)
        written_enriched = run_pipeline(on_batch_done=_enriched_batch_progress)
        new_enriched_days = len(list(enriched_dir.glob("date=*")))
        emit("compute_enriched", 88, f"enriched 完成,覆盖 {new_enriched_days} 天")
        logger.info("compute_enriched: full rebuild done, %d days", new_enriched_days)
    elif forward_incremental:
        # 往后新增日期: 增量补新区块 + 受影响个股全日期重算
        symbols_to_recompute = list(set(affected_symbols)) if affected_symbols else []
        emit("compute_enriched", 65,
             f"增量计算 enriched (新日期 + {len(symbols_to_recompute)} 只个股重算)…"
             if symbols_to_recompute else "增量计算 enriched (新日期)…")
        logger.info("compute_enriched: forward incremental, %d symbols to recompute",
                    len(symbols_to_recompute))
        written_enriched = run_pipeline(
            new_dates_only=True,
            symbols=symbols_to_recompute or None,
            on_batch_done=_enriched_batch_progress,
        )
        new_enriched_days = len(list(enriched_dir.glob("date=*")))
        emit("compute_enriched", 88, f"enriched 完成,覆盖 {new_enriched_days} 天")
        logger.info("compute_enriched: forward incremental done, %d days", new_enriched_days)
    elif affected_symbols:
        # 无新日期,仅除权因子变更 → 只重算受影响个股的全部日期
        emit("compute_enriched", 65, f"增量计算 enriched ({len(affected_symbols)} 只个股)…")
        logger.info("compute_enriched: adj_factor incremental, %d symbols", len(affected_symbols))
        written_enriched = run_pipeline(symbols=affected_symbols, on_batch_done=_enriched_batch_progress)
        emit("compute_enriched", 88, f"enriched 完成,{len(affected_symbols)} 只个股")
    else:
        written_enriched = 0
        logger.info("compute_enriched: skip (no new daily, no adj_factor changes)")
    _refresh_single_view(repo, "kline_enriched")
    _invalidate("enriched")

    # Step 2.3: 指数 / ETF 同步 — 物理分开存储；ETF 可复权，指数不复权。
    written_index_daily = 0
    written_etf_daily = 0
    index_count = 0
    etf_count = 0
    etf_adj_symbols = 0
    pull_index = _prefs.get_pipeline_pull_index()
    pull_etf = _prefs.get_pipeline_pull_etf()

    if capset.has(Cap.KLINE_DAILY_BATCH) and (pull_index or pull_etf):
        _types = []
        if pull_index:
            _types.append("指数")
        if pull_etf:
            _types.append("ETF")
        emit("sync_index", 88, f"同步{'+'.join(_types)}日K…")
        # 子阶段进度分配: 88.0(开始) → 89.0(完成), 指数占前半, ETF 占后半
        try:
            if pull_index:
                emit("sync_index", 88, "同步指数维表…")
                index_count = index_sync.sync_index_instruments(repo, pull_index=True, pull_etf=False)
                emit("sync_index", 88, f"指数维表完成,{index_count} 只")
                index_dir = repo.store.data_dir / "kline_index_enriched"
                index_dates = sorted(
                    d.name[5:] for d in index_dir.glob("date=*")
                    if d.is_dir() and d.name.startswith("date=")
                ) if index_dir.exists() else []
                # 数据修正模式下用传入起点; 否则用本地指数最新日期补到今天
                if override_start_date:
                    index_start = override_start_date
                else:
                    index_start = _date.fromisoformat(index_dates[-1]) if index_dates else today - _td(days=365)

                def _index_chunk(cur: int, tot: int) -> None:
                    emit("sync_index", 88, f"指数日K批次 {cur}/{tot}",
                         stage_pct=int(100 * cur / tot) if tot else 100, skip_log=cur < tot)

                written_index_daily = index_sync.sync_and_persist_index_daily(
                    repo,
                    capset,
                    start_date=_dt.combine(index_start, _dt.min.time()),
                    end_date=_dt.combine(today, _dt.min.time()),
                    on_chunk_done=_index_chunk,
                )
                emit("sync_index", 88, f"指数日K完成,{written_index_daily} 行")
                _invalidate("index_instruments")
                _invalidate("index_daily")
                _invalidate("index_enriched")

            if pull_etf:
                emit("sync_index", 88, "同步 ETF 维表…")
                etf_count = index_sync.sync_etf_instruments(repo)
                emit("sync_index", 88, f"ETF 维表完成,{etf_count} 只")
                etf_symbols: list[str] = []
                etf_inst = repo.get_etf_instruments()
                if not etf_inst.is_empty() and "symbol" in etf_inst.columns:
                    etf_symbols = sorted(set(etf_inst["symbol"].to_list()))
                if etf_symbols and capset.has(Cap.ADJ_FACTOR):
                    try:
                        emit("sync_index", 88, "同步 ETF 除权因子…")
                        from datetime import datetime, timedelta
                        adj_end = datetime.now()
                        adj_path = repo.store.data_dir / "adj_factor_etf" / "all.parquet"
                        fallback_start = adj_end - timedelta(days=30)
                        adj_start = fallback_start
                        if adj_path.exists():
                            max_date = pl.scan_parquet(adj_path).select(pl.col("trade_date").max()).collect().item()
                            if max_date is not None:
                                if isinstance(max_date, str):
                                    adj_start = datetime.combine(_date.fromisoformat(max_date), datetime.min.time())
                                elif isinstance(max_date, datetime):
                                    adj_start = datetime.combine(max_date.date(), datetime.min.time())
                                else:
                                    adj_start = datetime.combine(max_date, datetime.min.time())
                        _, affected_etfs = index_sync.sync_etf_adj_factor(
                            etf_symbols,
                            repo,
                            capset,
                            start_time=adj_start,
                            end_time=adj_end,
                        )
                        etf_adj_symbols = len(affected_etfs)
                        emit("sync_index", 88, f"ETF 除权因子完成,{etf_adj_symbols} 只")
                    except Exception as e:  # noqa: BLE001
                        logger.warning("ETF adj_factor skipped: %s", e)
                        stage_errors.append(f"ETF adj_factor: {e}")
                etf_dir = repo.store.data_dir / "kline_etf_enriched"
                etf_dates = sorted(
                    d.name[5:] for d in etf_dir.glob("date=*")
                    if d.is_dir() and d.name.startswith("date=")
                ) if etf_dir.exists() else []
                etf_start = _date.fromisoformat(etf_dates[-1]) if etf_dates else today - _td(days=365)

                def _etf_chunk(cur: int, tot: int) -> None:
                    emit("sync_index", 88, f"ETF 日K批次 {cur}/{tot}",
                         stage_pct=int(100 * cur / tot) if tot else 100, skip_log=cur < tot)

                written_etf_daily = index_sync.sync_and_persist_etf_daily(
                    repo,
                    capset,
                    start_date=_dt.combine(etf_start, _dt.min.time()),
                    end_date=_dt.combine(today, _dt.min.time()),
                    on_chunk_done=_etf_chunk,
                )
                emit("sync_index", 88, f"ETF 日K完成,{written_etf_daily} 行")
                _invalidate("etf_instruments")
                _invalidate("etf_daily")

            repo.refresh_index_views()
            emit(
                "sync_index",
                89,
                f"同步完成,指数 {index_count} 只/{written_index_daily} 行, ETF {etf_count} 只/{written_etf_daily} 行"
                + (f", ETF复权 {etf_adj_symbols} 只" if etf_adj_symbols else ""),
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("sync_index/etf failed: %s", e)
            emit("sync_index", 89, f"指数/ETF同步失败:{e}")
            stage_errors.append(f"index/etf sync: {e}")
    else:
        skipped.append("sync_index")

    # Step 2.5: 分钟 K 同步(可选) — 未启用或无 capability 时静默跳过(不 emit)
    from app.services import preferences
    minute_on = preferences.get_minute_sync_enabled()
    minute_days = preferences.get_minute_sync_days()
    written_minute = 0
    if minute_on and capset.has(Cap.KLINE_MINUTE_BATCH):
        minute_start = today - _td(days=minute_days)
        emit("sync_minute", 90, f"获取分钟K [{minute_start} ~ {today}]…")
        logger.info("sync_minute: [%s ~ %s] start", minute_start, today)
        minute_symbols = _resolve_minute_symbols(capset, repo)
        def _minute_chunk_progress(cur: int, tot: int, seg_label: str = "") -> None:
            emit("sync_minute", 90 + int(3 * cur / tot),
                 f"分钟K 批次 {cur}/{tot}" + (f" [{seg_label}]" if seg_label else ""),
                 stage_pct=int(100 * cur / tot), skip_log=True)
        written_minute = kline_sync.sync_and_persist_minute(
            minute_symbols, repo, capset, days=minute_days,
            on_chunk_done=_minute_chunk_progress,
        )
        minute_dir = repo.store.data_dir / "kline_minute"
        minute_cover_days = len(list(minute_dir.glob("date=*"))) if minute_dir.exists() else 0
        emit("sync_minute", 93, f"分钟K完成,覆盖 {minute_cover_days} 天")
        logger.info("sync_minute: [%s ~ %s] done, %d days", minute_start, today, minute_cover_days)
        _invalidate("minute")
    else:
        skipped.append("sync_minute")
        if minute_on:
            logger.info("sync_minute skipped: no KLINE_MINUTE_BATCH capability")
        else:
            logger.info("sync_minute skipped: user disabled")

    # Step 2.6: 市场环境(regime) 增量计算 — enriched 已就绪后聚合环境指标。
    # 双检测(缺口+stale), 自动补算遗漏/被覆写的日。软失败: 不阻断主管道。
    # 默认关闭: regime 是本地聚合计算(非拉取), 首次/regime 表为空时需全量回填
    # 多日, 内存与耗时较高。用户可在数据页「市场环境」卡片设置里开启自动计算,
    # 或直接在该页面点「重算」手动触发(不受此开关影响)。
    regime_days = 0
    from app.services import preferences as _prefs_regime
    if not _prefs_regime.get_pipeline_regime_enabled():
        skipped.append("regime")
        logger.info("compute_regime skipped: user disabled (pipeline_regime_enabled=False)")
    else:
        try:
            emit("compute_regime", 90, "计算市场环境…")
            from app.services import regime_builder
            from app.api.regime import invalidate_regime_cache
            new_regime = regime_builder.compute_regime_incremental(repo, repo.store.data_dir)
            regime_days = new_regime.height if not new_regime.is_empty() else 0
            if regime_days:
                invalidate_regime_cache()
                logger.info("compute_regime: %d days", regime_days)
            emit("compute_regime", 92, f"市场环境 {regime_days} 天")
            # 阶段切换推送监控通知 (软失败, 不影响管道): 末两日阶段不同 = 今日发生切换。
            # 切入退潮/冰点为风险信号, 用 warn 级别; 其余 info。
            if regime_days:
                try:
                    _push_phase_change_alert(repo.store.data_dir)
                except Exception as e:
                    logger.warning("phase change alert failed (soft): %s", e)
        except Exception as e:  # noqa: BLE001
            logger.warning("compute_regime failed (soft): %s", e)
            stage_errors.append(f"compute_regime: {e}")
            skipped.append("regime")

    # Step 2.7: 市场主线(概念/行业涨停梯队聚合) 增量计算 — regime 同开关。
    # 只窄扫连板 >=1 的行, 增量通常 1 天, 开销可忽略。软失败: 不阻断主管道。
    mainline_rows = 0
    if not _prefs_regime.get_pipeline_regime_enabled():
        skipped.append("mainline")
    else:
        try:
            emit("compute_mainline", 93, "计算市场主线…")
            from app.services import market_mainline
            for _kind in ("concept", "industry"):
                rows = market_mainline.compute_mainline_incremental(
                    repo, repo.store.data_dir, kind=_kind
                )
                mainline_rows += rows.height if not rows.is_empty() else 0
            if mainline_rows:
                logger.info("compute_mainline: %d rows", mainline_rows)
            emit("compute_mainline", 94, f"市场主线 {mainline_rows} 行")
        except Exception as e:
            logger.warning("compute_mainline failed (soft): %s", e)
            stage_errors.append(f"compute_mainline: {e}")
            skipped.append("mainline")

    # Step 3: 刷新视图
    emit("refresh_views", 95, "刷新 DuckDB 视图…")
    _refresh_views(repo)

    # 盘后完整性检测: 交易日收盘后同步, 但今日全市场日线未出齐(免费源如 BaoStock
    # 一般 17:30~20:00 才发布当日数据) → 明示"稍后再手动同步", 不再静默显示"成功"
    # 却让梯队/概念等停在昨天而用户不知原因。阈值 = max(100, 标的池一半), 只拦
    # "基本没出数"(如仅自选实时那几只), 不误伤停牌等正常缺口。
    today_daily_rows = 0
    today_incomplete = False
    try:
        from datetime import time as _dtime
        from app.market_time import cn_now, cn_today
        _now = cn_now()
        # 下限 15:00(A股收盘): 收盘后跑的管道都该检测。此前写 15:30 会让
        # 15:10 调度的管道(15:2x 跑完)恰好躲过检测 —— 不提示也不触发当晚重试
        if pull_a_share and _now.weekday() < 5 and _now.time() >= _dtime(15, 0):
            row = repo.execute_one(
                "SELECT count(*) FROM kline_daily WHERE date = CAST(? AS DATE)",
                [str(cn_today())],
            )
            today_daily_rows = int(row[0]) if row and row[0] else 0
            today_incomplete = today_daily_rows < max(100, len(universe) // 2)
    except Exception as e:  # noqa: BLE001
        logger.debug("今日日线完整性检测跳过: %s", e)

    if today_incomplete:
        emit("done", 100,
             f"完成 · ⚠ 今日全市场日线尚未出齐(仅 {today_daily_rows}/{len(universe)} 只)。"
             f"数据源一般 17:30~20:00 发布当日数据, 届时再点「立即同步」即可补到今天")
    else:
        emit("done", 100, "完成")
    _invalidate(None)  # 兜底:全清

    # [fork 增强] 用最新日线刷新持仓出场线并同步监控规则(线只会上移, 失败不影响管道)
    try:
        from app.services import position_exit
        position_exit.sync_exit_rules(position_exit.exit_lines_for_positions(repo))
    except Exception as e:  # noqa: BLE001
        logger.debug("持仓出场线刷新跳过: %s", e)

    result = {
        "universe_size": len(universe),
        "today_daily_rows": today_daily_rows,
        "today_daily_incomplete": today_incomplete,
        "daily_days": new_daily_days,
        "adj_factor_symbols": len(affected_symbols),
        "enriched_days": written_enriched,
        "index_count": index_count,
        "index_daily_rows": written_index_daily,
        "etf_count": etf_count,
        "etf_daily_rows": written_etf_daily,
        "etf_adj_factor_symbols": etf_adj_symbols,
        "minute_rows": written_minute,
        "regime_days": regime_days,
        "mainline_rows": mainline_rows,
        "lagging_symbols": len(lagging_symbols),
        "skipped_stages": skipped,
        "stage_errors": stage_errors,
    }

    # 有阶段软失败: 进度协议已走完(done/100, 前端进度条正常收尾), 但数据可能陈旧,
    # 抛出让上层 job_store 把终态标记为 failed —— 不再"部分失败却报成功"。
    if stage_errors:
        raise PipelineStageError(stage_errors)

    return result


def _refresh_views(repo: KlineRepository) -> None:
    """刷新所有 DuckDB 视图 —— 委托给 repository 的唯一权威实现 rebuild_views()。"""
    repo.rebuild_views()


def _refresh_single_view(repo: KlineRepository, name: str) -> None:
    """刷新单个 DuckDB 视图。"""
    d = repo.store.data_dir.as_posix()
    paths = {
        "kline_daily": f"{d}/kline_daily/**/*.parquet",
        "kline_enriched": f"{d}/kline_daily_enriched/**/*.parquet",
        "kline_index_daily": f"{d}/kline_index_daily/**/*.parquet",
        "kline_index_enriched": f"{d}/kline_index_enriched/**/*.parquet",
        "kline_etf_daily": f"{d}/kline_etf_daily/**/*.parquet",
        "kline_etf_enriched": f"{d}/kline_etf_enriched/**/*.parquet",
        "kline_etf_minute": f"{d}/kline_etf_minute/**/*.parquet",
        "kline_minute": f"{d}/kline_minute/**/*.parquet",
        "adj_factor": f"{d}/adj_factor/**/*.parquet",
        "adj_factor_etf": f"{d}/adj_factor_etf/**/*.parquet",
        "instruments": f"{d}/instruments/**/*.parquet",
        "instruments_index": f"{d}/instruments_index/**/*.parquet",
        "instruments_etf": f"{d}/instruments_etf/**/*.parquet",
    }
    path = paths.get(name)
    if not path:
        return
    try:
        repo.db.execute(
            f"CREATE OR REPLACE VIEW {name} AS "
            f"SELECT * FROM read_parquet('{path}', union_by_name=true)"
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("refresh view %s failed: %s", name, e)


def _resolve_minute_symbols(capset: CapabilitySet, repo=None) -> list[str]:
    """分钟 K 同步标的 — 与日K共用同一标的池。"""
    return _resolve_universe(capset, repo)


def _refresh_instruments_view(repo: KlineRepository) -> None:
    """单独刷新 instruments 视图。"""
    d = repo.store.data_dir.as_posix()
    try:
        repo.db.execute(
            f"CREATE OR REPLACE VIEW instruments AS "
            f"SELECT * FROM read_parquet('{d}/instruments/**/*.parquet', union_by_name=true)"
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("refresh instruments view failed: %s", e)


def _push_phase_change_alert(data_dir) -> None:
    """情绪周期阶段切换 → 推送监控通知(SSE toast + 监控中心)。

    阶段切换(如 退潮→冰点)是重要的市场信号, 原先只有打开市场环境页才能看到。
    复用 quote_service.push_alerts 广播通道; 未发生切换静默返回。
    """
    from app.services.market_phase import PHASE_LABELS
    from app.services.regime_builder import latest_phase_transition

    tr = latest_phase_transition(data_dir)
    if not tr:
        return
    prev, cur, d = tr
    msg = f"情绪周期阶段切换: {PHASE_LABELS.get(prev, prev)} → {PHASE_LABELS.get(cur, cur)} ({d})"
    severity = "warn" if cur in ("ebb", "ice") else "info"
    app_state = _get_app_state()
    qs = getattr(app_state, "quote_service", None) if app_state else None
    if qs:
        qs.push_alerts([{
            "source": "market",
            "type": "phase_change",
            "message": msg,
            "severity": severity,
        }])
    logger.info("phase change alert: %s (severity=%s)", msg, severity)


def _run_tracked(fn, job_label: str) -> bool:
    """调度触发时包装 JobStore 跟踪，确保同步历史有记录。

    单飞: 若已有活跃(pending∨running)任务(手动同步中), 本次调度直接跳过, 不并发。
    重任务执行槽: 再挡一层僵尸并发(reap 后线程仍活时不得并行写 parquet)。
    返回 True 仅表示任务已成功并且执行槽已释放。
    """
    from app.services.pipeline_jobs import job_store, release_run_slot, try_acquire_run_slot

    job_id, is_new = job_store.create()
    if not is_new:
        logger.info("scheduled %s 跳过: 已有活跃任务在运行 (job_id=%s)", job_label, job_id)
        return False
    if not try_acquire_run_slot():
        logger.warning("scheduled %s 跳过: 重任务执行槽被占用(疑似上次任务卡死)", job_label)
        job_store.fail(job_id, f"scheduled {job_label} skipped: 已有数据任务在运行")
        return False

    def progress(stage: str, pct: int, msg: str, stage_pct: int | None = None,
                 skip_log: bool = False) -> None:
        # 协作式取消: 用户点了取消(或被判死)→ 在最近的批次边界立即退出
        from app.services.pipeline_jobs import JobCancelled
        if job_store.is_cancelled(job_id):
            raise JobCancelled(job_id)
        job_store.progress(job_id, stage, pct, msg, stage_pct=stage_pct, skip_log=skip_log)

    succeeded = False
    try:
        job_store.start(job_id)
        result = fn(on_progress=progress)
        job_store.succeed(job_id, result)
        succeeded = True
        logger.info("scheduled %s completed: job_id=%s", job_label, job_id)
    except Exception as e:
        from app.services.pipeline_jobs import JobCancelled
        if isinstance(e, JobCancelled):
            # 已在 cancel 端点标记 failed; 已写入的增量保留, 下次调度自动续
            logger.info("scheduled %s cancelled by user: job_id=%s", job_label, job_id)
        else:
            logger.exception("scheduled %s failed: job_id=%s", job_label, job_id)
            job_store.fail(job_id, f"scheduled {job_label} failed")
    finally:
        release_run_slot()
    return succeeded


def _scheduled_pipeline_task(pipeline_fn) -> None:
    """Run weekly mining only after the tracked daily pipeline has fully succeeded."""
    if not _run_tracked(pipeline_fn, "daily_pipeline"):
        return
    try:
        from app.services.mining_schedule import run_weekly_mining

        result = run_weekly_mining(_get_app_state())
        logger.info("scheduled mining result: %s", result)
    except Exception:
        logger.exception("scheduled mining enqueue failed; daily pipeline remains succeeded")


# ================================================================
# 定时复盘 (AI 大盘复盘报告)
# ================================================================

REVIEW_JOB_ID = "scheduled_review"


async def _run_scheduled_review(repo) -> None:
    """定时复盘 job: 流式生成复盘 → 实时推 SSE(开着页面可见) → 落盘归档 → 推飞书。

    与手动「生成复盘」体验一致: 流式事件经 quote_service.push_review_event →
    /api/intraday/stream 的 review_progress 事件 → 前端 reviewStore, 用户开着复盘页
    即可看到报告边生成边显示, 切走再回来也能看到生成中/已生成。
    LLM 偶发断流(peer closed connection)时自动重试最多 2 次。
    任何异常都吞掉只记日志, 绝不影响调度器主循环。
    """
    import json

    try:
        from app.services import market_recap_reports
        from app import secrets_store as ss

        # AI Key 未配置时跳过(避免每日报错刷日志)
        if not ss.get_ai_key():
            logger.info("scheduled review skipped: AI key not configured")
            return

        app_state = _get_app_state()
        quote_service = getattr(app_state, "quote_service", None) if app_state else None
        depth_service = getattr(app_state, "depth_service", None) if app_state else None

        content, meta = await _stream_review_with_retry(repo, quote_service, depth_service)
        if not content:
            logger.warning("scheduled review produced no content (meta=%s)", meta)
            # 通知前端进入 error 态(若有页面在听)
            if quote_service:
                quote_service.push_review_event(json.dumps(
                    {"type": "error", "message": "复盘生成失败,请稍后手动重试"},
                    ensure_ascii=False))
            return

        # 落盘: 与手动生成完全相同的归档格式
        market_recap_reports.save_report({
            "as_of": meta.get("as_of"),
            "focus": "",
            "content": content,
            "summary": meta.get("summary", ""),
            "emotion_score": meta.get("emotion_score"),
            "emotion_label": meta.get("emotion_label", ""),
            "mode": "today",  # 定时复盘固定走当日模式
        })
        logger.info("scheduled review saved: as_of=%s", meta.get("as_of"))

        # 通知前端: 生成完成且已归档(archived=true 让前端只刷新列表, 不重复归档)
        if quote_service:
            quote_service.push_review_event(json.dumps(
                {"type": "done", "archived": True}, ensure_ascii=False))

        # 推送到飞书(可选): 运行时读取配置, 用户改设置下次触发即生效。
        # 失败静默降级, 不影响已归档的报告。
        _maybe_push_review(content, meta)
    except Exception as e:  # noqa: BLE001
        logger.exception("scheduled review failed: %s", e)
        # 兜底: 异常时通知前端停止「生成中」状态, 避免页面卡在 streaming
        try:
            app_state = _get_app_state()
            qs = getattr(app_state, "quote_service", None) if app_state else None
            if qs:
                import json as _json
                qs.push_review_event(_json.dumps(
                    {"type": "error", "message": "复盘生成异常,请稍后手动重试"},
                    ensure_ascii=False))
        except Exception:  # noqa: BLE001
            pass


async def _stream_review_with_retry(repo, quote_service, depth_service) -> tuple[str, dict]:
    """流式生成复盘, 每个事件推 SSE + 累积内容。LLM 断流时最多重试 2 次。

    返回 (content, meta)。重试时推一个 retry 事件让前端清空已累积内容重新开始。
    成功(收到 done/无 error)或耗尽重试后返回。
    """
    import asyncio
    import json
    from app.services.market_recap import recap_market_stream

    max_attempts = 3  # 初次 + 2 次重试
    last_meta: dict = {}
    content_parts: list[str] = []

    for attempt in range(1, max_attempts + 1):
        content_parts = []  # 每次重试重新累积
        failed = False
        try:
            async for evt_json in recap_market_stream(repo, quote_service, depth_service):
                evt = json.loads(evt_json)
                t = evt.get("type")

                # 推给前端(让开着页面的用户实时看到, 与手动一致)
                if quote_service:
                    quote_service.push_review_event(evt_json)

                if t == "meta":
                    last_meta = evt
                elif t == "delta" and evt.get("content"):
                    content_parts.append(evt["content"])
                elif t == "error":
                    failed = True
                    logger.warning("scheduled review stream error (attempt %d/%d): %s",
                                   attempt, max_attempts, evt.get("message"))
                    break  # 触发重试
                elif t == "done":
                    # 正常完成
                    return "".join(content_parts), last_meta
            # 流自然结束(无 done 事件)且有内容, 视为成功
            if content_parts and not failed:
                return "".join(content_parts), last_meta
        except Exception as e:  # noqa: BLE001
            # LLM 断流等异常(httpx.RemoteProtocolError)落到这里
            failed = True
            logger.warning("scheduled review stream exception (attempt %d/%d): %s",
                           attempt, max_attempts, e)

        # 失败: 决定是否重试
        if attempt < max_attempts:
            logger.info("scheduled review retrying in 3s (attempt %d → %d)", attempt, attempt + 1)
            # 通知前端: 即将重试, 清空已累积内容重新开始
            if quote_service:
                quote_service.push_review_event(json.dumps(
                    {"type": "retry", "attempt": attempt + 1}, ensure_ascii=False))
            await asyncio.sleep(3)

    # 耗尽重试, 返回已累积内容(可能为空)和最后 meta
    return "".join(content_parts), last_meta


def _maybe_push_review(content: str, meta: dict) -> None:
    """复盘报告归档后, 按 review_push_channels 选定的外部工具逐个推送完整报告。

    定时生成与手动生成共用本函数 (手动归档端点 POST /api/market-recap/reports 也会调用)。
    channels 为空则不推送; 'feishu' 复用监控中心的全局飞书 Webhook 通道。
    推送失败静默降级 (Webhook 是辅助通道), 不影响已归档的报告。
    """
    try:
        from app.services import preferences, webhook_adapter

        channels = preferences.get_review_push_channels()
        if not channels:
            return

        emotion = f"{meta.get('emotion_label') or ''}".strip()
        as_of = meta.get("as_of") or ""
        subtitle = as_of + (f" · 情绪 {emotion}" if emotion else "")

        for ch in channels:
            if ch == "feishu":
                url = preferences.get_feishu_webhook_url()
                if not url:
                    logger.info("review push(feishu) skipped: webhook not configured")
                    continue
                secret = preferences.get_feishu_webhook_secret()
                ok = webhook_adapter.send_feishu_card(
                    url, "每日复盘", subtitle, content, secret
                )
                logger.info("review push(feishu) %s", "sent" if ok else "failed")
            elif ch == "wecom":
                url = preferences.get_wecom_webhook_url()
                if not url:
                    logger.info("review push(wecom) skipped: webhook not configured")
                    continue
                # 企业微信 markdown 标题已含一级标题, subtitle 拼到正文首行
                full_body = (f"**{subtitle}**\n\n{content}" if subtitle else content)
                ok = webhook_adapter.send_wecom_markdown(
                    url, "每日复盘", full_body
                )
                logger.info("review push(wecom) %s", "sent" if ok else "failed")
            elif ch == "dingtalk":
                url = preferences.get_dingtalk_webhook_url()
                if not url:
                    logger.info("review push(dingtalk) skipped: webhook not configured")
                    continue
                keyword = preferences.get_dingtalk_keyword()
                full_body = (f"**{subtitle}**\n\n{content}" if subtitle else content)
                ok = webhook_adapter.send_dingtalk_markdown(
                    url, "每日复盘", full_body, keyword
                )
                logger.info("review push(dingtalk) %s", "sent" if ok else "failed")
            # 未来更多渠道在此追加分支
    except Exception as e:  # noqa: BLE001
        logger.warning("review push error: %s", e)


def _register_review_job(scheduler, repo, hour: int, minute: int) -> None:
    """注册/更新定时复盘 job(工作日 mon-fri, Asia/Shanghai)。

    供 start_scheduler(启动时) 和 settings API(改时间时) 共用。
    用 replace_existing=True, 重复注册只更新 trigger。

    注意: _run_scheduled_review 是协程函数, 必须把函数对象本身(配合 args)传给
    add_job, 而非用 lambda 包裹 —— 否则 APScheduler 会把 lambda 当同步函数在线程池
    执行, 仅得到一个未 await 的协程对象, 复盘实际不会运行。
    """
    scheduler.add_job(
        _run_scheduled_review,
        args=[repo],
        trigger=CronTrigger(day_of_week="mon-fri",
                            hour=hour, minute=minute,
                            timezone="Asia/Shanghai"),
        id=REVIEW_JOB_ID,
        misfire_grace_time=7200,  # 复盘非关键, 允许 2 小时内补跑
        replace_existing=True,
    )


# ================================================================
# [R27] 定时 AI: 今日总览导读·优选 / 个股信号批量
# ================================================================

TODAY_AI_JOB_ID = "scheduled_today_ai"
SIGNAL_AI_JOB_ID = "scheduled_signal_ai"


async def _run_scheduled_today_ai(repo) -> None:
    """定时生成今日总览 AI 导读·优选并落盘。异常只记日志, 不影响调度器。"""
    try:
        from app import secrets_store as ss
        if not ss.get_ai_key():
            logger.info("scheduled today-ai skipped: AI key not configured")
            return
        from app.api.today import _build_overview, generate_today_ai
        from app.services import today_ai_store

        data = _build_overview(repo)
        out = await generate_today_ai(repo, data)
        if out.get("error"):
            logger.warning("scheduled today-ai failed: %s", out["error"])
            return
        today_ai_store.save(out, as_of=data.get("as_of"), source="scheduled")
        logger.info("scheduled today-ai done: %d picks", len(out.get("picks") or []))
    except Exception:
        logger.exception("scheduled today-ai crashed")


async def _run_scheduled_signal_ai(repo) -> None:
    """定时批量刷新个股 AI 信号。逐只串行 + 固定间隔, 避免打满 AI 接口。"""
    import asyncio

    try:
        from app import secrets_store as ss
        if not ss.get_ai_key():
            logger.info("scheduled signal-ai skipped: AI key not configured")
            return
        from app.services import positions as positions_svc
        from app.services import preferences as prefs
        from app.services import stock_signal, watchlist

        cfg = prefs.get_signal_ai_schedule()
        syms = [str(e.get("symbol") or "").upper() for e in watchlist.list_symbols()]
        syms = [s for s in syms if s]
        if cfg["scope"] == "held":
            held = {s for s, p in positions_svc.load_all().items() if p.get("held")}
            syms = [s for s in syms if s in held]
        if not syms:
            logger.info("scheduled signal-ai: no symbols in scope=%s", cfg["scope"])
            return
        gap = cfg["gap_seconds"]
        ok = failed = 0
        for i, sym in enumerate(syms):
            try:
                res = await stock_signal.generate_signal(repo, repo.store.data_dir, sym)
                if res.get("error"):
                    failed += 1
                    logger.debug("scheduled signal-ai %s: %s", sym, res["error"])
                else:
                    ok += 1
            except Exception as e:  # noqa: BLE001
                failed += 1
                logger.debug("scheduled signal-ai %s crashed: %s", sym, e)
            if i < len(syms) - 1:
                await asyncio.sleep(gap)
        logger.info("scheduled signal-ai done: %d ok, %d failed (scope=%s)",
                    ok, failed, cfg["scope"])
    except Exception:
        logger.exception("scheduled signal-ai crashed")


def _register_today_ai_job(scheduler, repo, hour: int, minute: int) -> None:
    """注册/更新今日总览 AI 定时 job(协程函数直接传入, 不可用 lambda 包)。"""
    scheduler.add_job(
        _run_scheduled_today_ai, args=[repo],
        trigger=CronTrigger(day_of_week="mon-fri", hour=hour, minute=minute,
                            timezone="Asia/Shanghai"),
        id=TODAY_AI_JOB_ID, misfire_grace_time=7200, replace_existing=True,
    )


def _register_signal_ai_job(scheduler, repo, hour: int, minute: int) -> None:
    """注册/更新个股 AI 信号批量定时 job。"""
    scheduler.add_job(
        _run_scheduled_signal_ai, args=[repo],
        trigger=CronTrigger(day_of_week="mon-fri", hour=hour, minute=minute,
                            timezone="Asia/Shanghai"),
        id=SIGNAL_AI_JOB_ID, misfire_grace_time=7200, replace_existing=True,
    )


def start_scheduler(repo: KlineRepository, capset: CapabilitySet) -> AsyncIOScheduler:
    """启动调度器。

    工作日 09:10 — 同步个股维表
    工作日 HH:MM — 盘后管道（时间由用户偏好决定，默认 15:30）
    """
    from app.services import preferences
    sched = preferences.get_pipeline_schedule()
    inst_sched = preferences.get_instruments_schedule()

    scheduler = AsyncIOScheduler(timezone="Asia/Shanghai")

    # 盘前: 同步 instruments（时间由偏好决定）
    def _instruments_task(on_progress=None):
        emit = on_progress or _noop
        emit("sync_instruments", 0, "同步个股维表…")
        result = run_instruments_sync(repo)
        emit("done", 100, f"个股维表同步完成,{result.get('instruments_rows', 0)} 只标的")
        return result

    scheduler.add_job(
        lambda: _run_tracked(_instruments_task, "instruments_sync"),
        trigger=CronTrigger(day_of_week="mon-fri",
                            hour=inst_sched["hour"], minute=inst_sched["minute"],
                            timezone="Asia/Shanghai"),
        id="pre_market_instruments",
        misfire_grace_time=1800,
        replace_existing=True,
    )

    # 盘后: 日 K + enriched（时间由偏好决定）
    def _pipeline_then_refresh(on_progress=None):
        # 与手动触发 (/api/pipeline/run) 对齐: 管道落盘后重建 Polars 内存缓存,
        # 否则 live_agg 的昨日连板数等基准列会停留在旧交易日, 次日开盘连板梯队
        # 整体少算一档 (仅手动触发或重启才会刷缓存, cron 调度路径此前漏了这步)。
        # 用 app.state 上的**实时** capset(周期重探会热更新它), 而非启动时捕获的
        # 旧 capset —— 否则 Key 中途过期/续费后, 调度管道仍按旧档位打端点。
        app_state = _get_app_state()
        capset_live = getattr(app_state, "capabilities", None) or capset
        # 管道运行期间暂停实时行情取数, 防止覆写同一批 parquet 竞态
        qs = getattr(app_state, "quote_service", None)
        try:
            if qs:
                with qs.paused():
                    result = run_now(repo, capset_live, on_progress=on_progress)
            else:
                result = run_now(repo, capset_live, on_progress=on_progress)
        finally:
            # 即便有阶段软失败(run_now 末尾抛 PipelineStageError), 已落盘的日K/enriched
            # 仍需刷进内存缓存, 否则 live_agg 基准列停留在旧交易日。放 finally 保证部分
            # 成功也生效; 随后异常继续上抛, 由 _run_tracked 标记任务 failed。
            repo.refresh_cache()
        return result

    # [R21] 当日数据未出齐 → 当晚自动重试: 数据源一般 17:30~20:00 才发布当日全量,
    # 盘后管道跑得早(默认 15:30)时日K/enriched 抓不全, 此前只提示"稍后手动同步",
    # 下一次自动跑要等次日 —— 现在检测到未出齐就每 90 分钟自动重跑(当晚最多 3 次),
    # 补齐即停; 连板梯队/概念/行业等指标层消费方当晚自动追上, 无需人工守着点同步。
    _RETRY_DELAY_MIN = 90
    _RETRY_MAX = 3

    def _pipeline_with_retry(on_progress=None, _attempt: int = 0):
        result = _pipeline_then_refresh(on_progress=on_progress)
        try:
            if result and result.get("today_daily_incomplete"):
                if _attempt < _RETRY_MAX:
                    from datetime import timedelta

                    from app.market_time import cn_now
                    run_at = cn_now() + timedelta(minutes=_RETRY_DELAY_MIN)
                    nxt = _attempt + 1
                    scheduler.add_job(
                        lambda: _run_tracked(
                            lambda on_progress=None: _pipeline_with_retry(on_progress, nxt),
                            "daily_pipeline"),
                        trigger="date", run_date=run_at,
                        id="daily_pipeline_incomplete_retry",
                        misfire_grace_time=3600,
                        replace_existing=True,
                    )
                    logger.info("今日日线未出齐, 已安排 %s 自动重试(第 %d/%d 次)",
                                run_at.strftime("%H:%M"), nxt, _RETRY_MAX)
                else:
                    logger.warning("今日日线重试 %d 次仍未出齐, 交由次日调度补齐", _RETRY_MAX)
        except Exception as e:  # noqa: BLE001
            logger.warning("安排未出齐自动重试失败(不影响本次结果): %s", e)
        return result

    scheduler.add_job(
        # [合并] 上游的 _scheduled_pipeline_task(管道成功后跑每周因子挖掘)
        # 包住我们的 _pipeline_with_retry(当日未出齐当晚自动重试)
        lambda: _scheduled_pipeline_task(_pipeline_with_retry),
        trigger=CronTrigger(day_of_week="mon-fri",
                            hour=sched["hour"], minute=sched["minute"],
                            timezone="Asia/Shanghai"),
        id="daily_pipeline",
        misfire_grace_time=3600,
        replace_existing=True,
    )

    # 盘后: 五档盘口 sealed 定版(时间由偏好决定, 默认15:02, 范围15:01~18:00)
    depth_sched = preferences.get_depth_finalize_time()

    def _depth_finalize():
        depth_svc = getattr(_get_app_state(), "depth_service", None) if _get_app_state() else None
        if depth_svc:
            depth_svc.finalize()

    scheduler.add_job(
        _depth_finalize,
        trigger=CronTrigger(day_of_week="mon-fri",
                            hour=depth_sched["hour"], minute=depth_sched["minute"],
                            timezone="Asia/Shanghai"),
        id="depth_finalize",
        misfire_grace_time=3600,
        replace_existing=True,
    )

    # 周期性能力重探: 付费 Key 中途过期/续费无需重启即可被发现。
    # 只热更新 app.state.capabilities(API 端点、盘后管道 _pipeline_then_refresh 均读它);
    # 档位变化记 WARNING, 让「Key 失效」在日志/前端可见, 不再静默按旧档位打 403 端点。
    def _reprobe_capabilities():
        from app.tickflow.policy import detect_capabilities, tier_label
        app_state = _get_app_state()
        if app_state is None:
            return
        try:
            old = getattr(app_state, "capabilities", None)
            old_n = len(old.all()) if old else -1
            new_capset = detect_capabilities(force=True)
            app_state.capabilities = new_capset
            new_n = len(new_capset.all())
            if old_n != new_n:
                logger.warning(
                    "能力集变化: %d → %d capabilities (档位=%s)。Key 过期/续费或端点波动, "
                    "已热更新 app.state.capabilities。", old_n, new_n, tier_label(),
                )
        except Exception as e:  # noqa: BLE001
            logger.warning("周期能力重探失败(保留现有能力集): %s", e)

    scheduler.add_job(
        _reprobe_capabilities,
        trigger=IntervalTrigger(minutes=60),
        id="reprobe_capabilities",
        misfire_grace_time=600,
        replace_existing=True,
    )

    # 定时复盘 (AI 大盘复盘报告): 工作日到点自动生成并归档。
    # 默认关闭 —— 仅当用户在复盘页开启时才注册 job。
    # 复用 recap_market_once(非流式) + market_recap_reports.save_report(落盘)。
    # quote_service / depth_service 通过 _get_app_state() 延迟取用。
    review_sched = preferences.get_review_schedule()
    if review_sched["enabled"]:
        _register_review_job(scheduler, repo, review_sched["hour"], review_sched["minute"])
        logger.info("scheduled_review enabled @%02d:%02d mon-fri",
                    review_sched["hour"], review_sched["minute"])

    # [R27] 今日总览 AI 导读·优选 / 个股 AI 信号批量: 到点自动跑, 结果落盘常驻。
    # 默认关闭, 用户在页面开启后才注册。
    today_ai_sched = preferences.get_today_ai_schedule()
    if today_ai_sched["enabled"]:
        _register_today_ai_job(scheduler, repo, today_ai_sched["hour"], today_ai_sched["minute"])
        logger.info("scheduled_today_ai enabled @%02d:%02d mon-fri",
                    today_ai_sched["hour"], today_ai_sched["minute"])
    signal_sched = preferences.get_signal_ai_schedule()
    if signal_sched["enabled"]:
        _register_signal_ai_job(scheduler, repo, signal_sched["hour"], signal_sched["minute"])
        logger.info("scheduled_signal_ai enabled @%02d:%02d mon-fri (scope=%s gap=%ss)",
                    signal_sched["hour"], signal_sched["minute"],
                    signal_sched["scope"], signal_sched["gap_seconds"])

    scheduler.start()
    logger.info("scheduler started; instruments@%02d:%02d, pipeline@%02d:%02d, depth@%02d:%02d mon-fri",
                inst_sched["hour"], inst_sched["minute"], sched["hour"], sched["minute"],
                depth_sched["hour"], depth_sched["minute"])
    return scheduler


# app_state 延迟引用(start_scheduler 在 lifespan 早期调用, app.state 可能还没就绪)
_app_state_ref = None


def set_app_state(app_state) -> None:
    """lifespan 注册 app.state 引用, 供 scheduled job 访问 depth_service 等单例。"""
    global _app_state_ref
    _app_state_ref = app_state


def _get_app_state():
    return _app_state_ref
