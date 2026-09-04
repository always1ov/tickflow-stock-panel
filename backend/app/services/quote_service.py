"""全局实时行情服务。

集中管理全市场行情拉取 + enriched 缓存，供盘中选股、自选股等所有模块复用。

架构:
  - 后台线程轮询 TickFlow get_by_universes(["CN_Equity_A", "CN_ETF"]) + 核心指数按码拉取
    (自定义源走 provider.get_realtime() + 可选 get_realtime_indices() 指数补充)
  - 拉取行情 → 写 kline_daily (不复权) + 增量计算 enriched → 写盘 + 更新缓存
  - _enriched_cache 是唯一的盘中数据源 (OHLCV + 全套技术指标)
  - _live_agg_cache 是递推状态 (只加载一次, 盘中不变)

数据流 (每轮 ~15s):
  1. API 拉取 → raw_records (临时变量)
  2. raw_records → 写 kline_daily (不复权原始价格)
  3. raw_records → 更新 _enriched_cache 的 OHLCV
  4. 增量计算 enriched 指标 (~50ms)
  5. 写 kline_daily_enriched + 替换 _enriched_cache
  6. 通知 SSE

生命周期:
  - 服务启动时读取 preferences，若 enabled 则自动启动线程
  - 运行中可通过 API 切换开关
  - 关闭时停止线程
"""
from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import date, datetime, time as dt_time

import polars as pl

from app.market_time import cn_now, cn_today
from app.parquet import scan_daily_parquet
from app.services.index_const import CORE_INDEX_SYMBOLS
from app.strategy.intraday_signals import IntradaySignalEvaluator
from app.strategy.monitor import format_alert_quote

# 告警来源 → 中文标签 (webhook 标题 / 系统通知标题共用)
SOURCE_LABELS = {
    "strategy": "策略", "signal": "信号", "price": "价格",
    "market": "异动", "ladder": "连板梯队", "sector": "板块",
    "volume_delta": "放量", "abnormal": "异动", "date": "日期提醒",
}


def _body_with_quote(body: str, ev: dict) -> str:
    """推送正文尾部补上触发时的现价/涨跌幅 (日期提醒无行情, 自然为空)。

    默认告警的 message 已由引擎拼过引语 (monitor._default_message), 这里仅在正文
    尚未带引语时追加, 避免「现价」出现两遍 (自定义 message 的规则则补上这一句)。
    """
    quote_tail = format_alert_quote(ev.get("price"), ev.get("change_pct"))
    if not quote_tail or body.endswith(quote_tail):
        return body
    return f"{body} · {quote_tail}"

logger = logging.getLogger(__name__)

# Webhook(飞书等)投递专用线程池 —— 与行情轮询线程隔离。
# send_feishu 内置重试(最坏 ~3×5s 超时 + 退避), 若在 _poll_loop 上同步投递,
# webhook 慢/宕机会逐条累加, 拖垮整条实时行情+告警轮询。这里 fire-and-forget,
# 失败由 webhook_adapter 记 WARNING(可见), 但绝不阻塞热路径。
_WEBHOOK_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="feishu-webhook")


class QuoteSubscriber:
    """一个 SSE 连接对应一个订阅者: 独立事件 + 独立队列。

    此前四个通道共用服务级 Event + pending 列表, pop 是「取走」语义:
    多客户端 (多标签页/多设备) 时告警只会被先醒来的连接消费, 其余永远
    收不到; 共享 Event 的 clear/wait 也存在互相吞信号的竞态。
    改为每连接独立订阅者后, 事件对所有客户端广播。
    """

    def __init__(self, max_alerts: int = 1000, max_reviews: int = 200) -> None:
        self._event = threading.Event()
        self._lock = threading.Lock()
        self._max_alerts = max_alerts
        self._max_reviews = max_reviews
        self._quote_updated = False
        self._strategy_results_updated = False
        self._depth_updated = False
        self._alerts: list[dict] = []
        self._reviews: list[str] = []

    # ── 消费侧 (SSE generator 线程) ──────────────────────
    def wait(self, timeout: float = 5.0) -> bool:
        """阻塞等待任一通道有新信号。"""
        return self._event.wait(timeout=timeout)

    def pop(self) -> dict:
        """原子取走全部待推送内容并复位事件。"""
        with self._lock:
            out = {
                "quote_updated": self._quote_updated,
                "strategy_results_updated": self._strategy_results_updated,
                "depth_updated": self._depth_updated,
                "alerts": self._alerts,
                "reviews": self._reviews,
            }
            self._quote_updated = False
            self._strategy_results_updated = False
            self._depth_updated = False
            self._alerts = []
            self._reviews = []
            self._event.clear()
            return out

    # ── 生产侧 (行情轮询 / depth / 复盘线程) ─────────────
    def push_alerts(self, alerts: list[dict]) -> None:
        with self._lock:
            self._alerts.extend(alerts)
            if len(self._alerts) > self._max_alerts:  # 背压: 丢弃最旧
                self._alerts = self._alerts[-self._max_alerts:]
            self._event.set()

    def push_review(self, event_json: str) -> None:
        with self._lock:
            self._reviews.append(event_json)
            if len(self._reviews) > self._max_reviews:
                self._reviews = self._reviews[-self._max_reviews:]
            self._event.set()

    def clear_alerts(self) -> None:
        with self._lock:
            self._alerts = []
            if (
                not self._quote_updated
                and not self._strategy_results_updated
                and not self._depth_updated
                and not self._reviews
            ):
                self._event.clear()

    def notify_quote(self) -> None:
        with self._lock:
            self._quote_updated = True
            self._event.set()

    def notify_strategy_results(self) -> None:
        with self._lock:
            self._strategy_results_updated = True
            self._event.set()

    def notify_depth(self) -> None:
        with self._lock:
            self._depth_updated = True
            self._event.set()


# 落盘节流间隔: last_fetch_ms 仅在进程重启后用于显示"最后获取时间"(运行中读内存值),
# 每 30s 持久化一次足够, 避免 expert 档每秒一轮的全量 preferences 重写磁盘。
_LAST_FETCH_WRITE_INTERVAL_MS = 30_000.0
_last_fetch_written_at_ms: float = 0.0


def _persist_last_fetch(fetched_at_ms: float) -> None:
    """把"最后获取"时间戳持久化到 preferences, 使进程重启后仍可显示。

    放在锁外调用 (IO); 失败不影响主流程 (内存值已更新, 下次 fetch 再写)。
    距上次成功落盘不足 30s 时跳过 (节流只影响落盘频率, 内存值不受影响)。
    """
    global _last_fetch_written_at_ms
    if (fetched_at_ms - _last_fetch_written_at_ms) < _LAST_FETCH_WRITE_INTERVAL_MS:
        return
    try:
        from app.services import preferences
        preferences.save({"last_fetch_ms": round(fetched_at_ms, 0)})
        _last_fetch_written_at_ms = fetched_at_ms
    except Exception as e:  # noqa: BLE001
        logger.debug("last_fetch_ms 持久化失败 (不影响行情): %s", e)


def _monitor_name_map(repo) -> dict[str, str]:
    """监控回填用的 symbol → name 映射 (股票 + ETF + 指数, 股票优先)。

    走 repo.get_name_map() 的进程内 memo (三份 instruments 维表刷新时失效),
    避免每轮监控对 ~7000 行维表 iter_rows 重建。过滤空名称与旧行为一致。
    """
    return {s: n for s, n in repo.get_name_map().items() if n}


class QuoteService:
    """全局实时行情服务 — 单例。"""

    # 档位 → 最小轮询间隔 (秒) — TickFlow 档位限速保护, 仅实时源为 tickflow 时适用
    TIER_MIN_INTERVAL = {
        "expert": 1.0,
        "pro": 3.0,
        "starter": 6.0,
        "free": 6.0,
    }
    # 插件/自定义源: 不受 TickFlow 档位保护约束, 通用下限 1s (默认间隔仍为 DEFAULT_INTERVAL)
    CUSTOM_PROVIDER_MIN_INTERVAL = 1.0
    DEFAULT_INTERVAL = 6.0
    MAX_INTERVAL = 60.0

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # 串行化行情拉取: 手动 POST /refresh 与后台轮询线程可能并发调用
        # _fetch_quotes, 两者同时写同一批 parquet/缓存会互相覆盖
        self._fetch_lock = threading.Lock()
        # [R74] 单票按需刷新的冷却表 {symbol: monotonic 时刻}
        self._single_refresh_at: dict[str, float] = {}
        # [R76] 后台轮询本轮占用的 key 下标 —— 单票刷新避开它们挑空闲的
        self._busy_key_idx: set[int] = set()
        # [R77] 弹窗单票实时的独立缓存 {symbol: row} —— 刻意不进自选叠加层:
        # 那层被监控/自选页/今日总览当"自选·当天·轮询喂"的快照消费
        self._single_live: dict[str, dict] = {}
        self._running = False
        self._enabled = False      # 全局开关 (持久化到 preferences)
        # 暂停态: 盘后管道/数据修正运行期间临时暂停取数, 防止与管道写同一批 parquet 竞态。
        # 与 _enabled 不同 — pause 不改 preferences、不 stop 线程, 仅让轮询循环跳过取数;
        # 进程重启后 _paused 归零, 从 preferences 恢复真实开关态, 无"假关闭"副作用。
        self._paused = False
        self._interval = self.DEFAULT_INTERVAL
        self._thread: threading.Thread | None = None
        # [R118] 自动开关: 独立守护线程, 与轮询线程无关(开关关着时轮询线程压根
        # 不存在, 所以不能把这段逻辑塞进 _poll_loop)。**边沿触发** ——
        # 只在"应开/应关"翻转的那一刻动手, 中间用户手动改了就一直听用户的,
        # 到下一个边界(次日开盘/当日收盘)才回到自动节奏。
        self._auto_thread: threading.Thread | None = None
        self._auto_last_desired: bool | None = None
        self._auto_pref_last: bool | None = None
        self._repo = None          # 延迟注入, 避免循环导入
        # SSE 订阅者集合: 每个 /stream 连接一个 QuoteSubscriber, 事件广播到所有订阅者
        self._subscribers: set[QuoteSubscriber] = set()
        self._strategy_monitor = None            # 延迟注入
        self._app_state = None                   # 延迟注入 (FastAPI app.state)
        # 异动边缘规则上次评估时间戳 (秒)。异动快照历史部分有 60s 缓存,
        # 但每次构建仍有全市场循环, 轮询线程里限频到 30s 一次。
        self._abnormal_last_eval = 0.0

        # 拉取元信息 (给 SSE / status 用)
        self._fetch_time: float = 0.0       # perf_counter (用于计算 quote_age_ms)
        self._fetch_ms: float = 0.0         # 拉取耗时 (毫秒)
        # _fetched_at 持久化到 preferences: 进程重启后仍能显示"最后获取"时间,
        # 不因关闭开关/重启而归零 (数据页卡片常驻显示, 方便判断上次拉取时刻)。
        try:
            from app.services import preferences as _prefs
            self._fetched_at: float = float(_prefs.load().get("last_fetch_ms", 0.0))
        except Exception:  # noqa: BLE001
            self._fetched_at = 0.0      # 拉取完成的 Unix 时间戳 (毫秒)
        self._symbol_count: int = 0
        self._index_symbol_count: int = 0
        self._etf_symbol_count: int = 0
        self._index_quotes_cache: pl.DataFrame | None = None
        self._intraday_signal_evaluator = IntradaySignalEvaluator()
        self._intraday_signal_bucket: dict[str, str] = {}
        # 午休/收盘最终同步状态: 到边界后必须成功拉取一版行情, 再进入休盘态。
        self._final_sync_done: set[tuple[date, str]] = set()
        self._final_sync_failed: dict[tuple[date, str], str] = {}
        self._holiday_active = False  # 交易日探针当前是否判休市 (日志去重)
        # 轮询放量 (volume_delta 规则): 上一轮全市场股票快照的 (累计成交量[手], 累计成交额[元]|None)。
        # 每轮全量快照后更新; 跨交易日清空; 免费/自选轮询不会写入这里。
        # [fork R81] 成交额缺失记 None (金额口径 fail-closed, 不用 0 伪造增量)。
        self._prev_stock_volume: dict[str, tuple[float, float | None]] | None = None
        self._prev_volume_fetched_at: float | None = None   # epoch 毫秒
        self._prev_volume_date: date | None = None
        self._volume_delta: dict[str, tuple[float, float | None]] = {}
        self._volume_delta_span_s: float = 0.0

    # ================================================================
    # 生命周期
    # ================================================================

    def start(self, interval: float = 0.0) -> None:
        """启动后台行情轮询线程。"""
        if self._running:
            return
        if interval <= 0:
            from app.services import preferences
            interval = preferences.get_realtime_quote_interval()
        self._interval = self._clamp_interval(interval)
        self._running = True
        self._enabled = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()
        self._save_enabled(True)
        logger.info("行情服务已启动, 轮询间隔 %.1fs", self._interval)

    def stop(self) -> None:
        """停止后台行情轮询线程。"""
        self._running = False
        self._enabled = False
        if self._thread:
            self._thread.join(timeout=10)
            self._thread = None
        self._save_enabled(False)
        # [R76] 轮询停了, 所有 key 都算空闲 —— 单票刷新可以随便挑
        self._busy_key_idx = set()
        logger.info("行情服务已停止")

    def enable(self) -> bool:
        """开启自动行情 (不立即启动线程，等下一个交易时段)。

        none 档无实时行情权限,拒绝开启并返回 False;
        free 档开启自选股实时,starter+ 开启全市场实时。返回值表示是否真正开启。
        """
        if not self.is_realtime_allowed():
            logger.warning("实时行情开启被拒:当前档位(none)无实时行情权限")
            return False
        self._enabled = True
        self._save_enabled(True)
        if not self._running:
            from app.services import preferences
            self._interval = self._clamp_interval(preferences.get_realtime_quote_interval())
            self._running = True
            self._thread = threading.Thread(target=self._poll_loop, daemon=True)
            self._thread.start()
        logger.info("行情服务已启用, 轮询间隔 %.1fs", self._interval)
        return True

    def disable(self) -> None:
        """关闭自动行情。

        [R16 修补] 同时清空自选实时叠加层: 否则残留的当日实时行会让今日总览/
        决策台/K线在开关已关的情况下仍显示"实时中"与盘中口径标记 —— 用户关掉
        开关的语义就是"回到收盘口径", 叠加层必须一起归零。
        """
        self.stop()
        try:
            if self._repo is not None:
                self._repo.clear_watchlist_live()
        except Exception as e:  # noqa: BLE001
            logger.warning("清空自选实时叠加层失败: %s", e)
        logger.info("行情服务已关闭")

    # ================================================================
    # 临时暂停 (盘后管道/数据修正期间, 防止写盘竞态)
    # ================================================================

    def pause(self) -> None:
        """临时暂停行情轮询取数 (不关闭线程、不改 preferences)。

        用于盘后管道/数据修正运行期间, 防止实时行情覆写管道正在写的 parquet。
        与 stop() 的区别: 线程继续存活但跳过 _fetch_quotes; preferences 开关态不变,
        管道结束调用 resume() 即恢复。线程级检查, 即时生效, 无 join 等待。
        """
        self._paused = True
        logger.info("行情轮询已临时暂停 (管道/修正运行中)")

    def resume(self) -> None:
        """恢复暂停的行情轮询取数 (对应 pause)。"""
        self._paused = False
        logger.info("行情轮询已恢复")

    def is_paused(self) -> bool:
        """是否处于临时暂停态 (管道运行期间)。"""
        return self._paused

    @contextmanager
    def paused(self):
        """上下文管理器: 进入时暂停轮询取数, 退出时(含异常)自动恢复。

        供盘后管道/数据修正复用:
            with quote_service.paused():
                run_pipeline(...)
        无论正常结束还是异常/crash, finally 都会 resume (除非进程直接被 kill)。
        """
        self.pause()
        try:
            yield
        finally:
            self.resume()

    def boot_check(self) -> None:
        """启动时检查 preferences，若 enabled 则自动启动。

        none 档无实时行情权限:即使 preferences 标记为 enabled,
        也不启动,并同步 preferences 为关闭(避免 UI 误显示已开启)。
        """
        from app.services import preferences
        if not self.is_realtime_allowed():
            if preferences.get_realtime_quotes_enabled():
                self._save_enabled(False)
            logger.info("实时行情未启动:当前档位(none)无实时行情权限")
            return
        if preferences.get_realtime_quotes_enabled():
            self.start()
        self.start_auto_supervisor()   # [R118] 无论开关当前是开是关都要跑

    # ================================================================
    # [R118] 自动开关(对齐交易日/交易时段)
    # ================================================================

    _AUTO_TICK_S = 30.0

    def start_auto_supervisor(self) -> None:
        """启动自动开关守护线程(幂等)。自动没打开时它每拍就是空转。"""
        if self._auto_thread and self._auto_thread.is_alive():
            return
        self._auto_thread = threading.Thread(
            target=self._auto_loop, name="realtime-auto", daemon=True)
        self._auto_thread.start()

    def notify_auto_pref_changed(self) -> None:
        """自动开关刚被用户改动 —— 清掉边沿记忆, 让下一拍立刻按当前时段生效。"""
        self._auto_last_desired = None
        self._auto_pref_last = None

    def _auto_loop(self) -> None:
        while True:
            try:
                self._auto_tick()
            except Exception as e:  # noqa: BLE001 —— 自动开关出错不该拖垮进程
                logger.warning("实时行情自动开关异常: %s", e)
            time.sleep(self._AUTO_TICK_S)

    def _has_local_data(self) -> bool:
        """本地有没有数据底座。

        [同步上游 ed2f81c] 作者给「手动开启实时行情」加了首用门禁(日K/enriched
        均空时 409)。那道门禁在 API 层, 自动开关走的是服务层 `enable()`, 绕得过去
        —— 空库下自动开只是空转耗配额, 所以这里按同一口径自己再判一次。
        取不到 repo(还没注入)时放行, 维持原行为。
        """
        if self._repo is None:
            return True
        try:
            return not (self._repo.latest_daily_date() is None
                        and self._repo.latest_enriched_date() is None)
        except Exception:  # noqa: BLE001 —— 判据取不到就别拦
            return True

    def _final_sync_pending(self) -> bool:
        """今天的收盘定版还没成功(有就别急着关, 那一版快照是当日数据的收尾)。"""
        key = self._final_sync_key("close_final")
        return bool(key and key not in self._final_sync_done)

    def _auto_tick(self) -> None:
        from app.market_time import cn_now
        from app.services import preferences, realtime_schedule, trading_day

        auto_on = preferences.get_realtime_auto()
        if auto_on != self._auto_pref_last:
            # 刚被打开/关闭 → 重新认边沿, 打开的那一刻就按当前时段生效
            self._auto_pref_last = auto_on
            self._auto_last_desired = None
        if not auto_on:
            return
        if not self.is_realtime_allowed():
            return      # none 档没有实时权限, 自动开也开不出来, 静默空转
        if not self._has_local_data():
            return      # [同步上游 ed2f81c] 首用门禁同口径

        now = cn_now()
        desired = realtime_schedule.desired_state(now, trading_day.is_trading_day(now))
        # 该关了但收盘定版还没成功 → 宽限到 15:40, 让它把最后一版拉完
        if not desired and self._auto_last_desired is True \
                and realtime_schedule.in_grace_window(now) and self._final_sync_pending():
            logger.debug("收盘定版未完成, 自动关闭延后")
            return
        if desired == self._auto_last_desired:
            return      # 边沿没变: 中间用户手动怎么改都不覆盖

        self._auto_last_desired = desired
        if desired:
            if not self._enabled:
                self.enable()
                logger.info("实时行情自动开启(%s)", realtime_schedule.window_label())
        elif self._enabled:
            # 用 stop() 而不是 disable(): disable 会连自选实时叠加层一起清空
            # ([R16] 那是"用户要回到收盘口径"的语义)。自动关只是"这一天的行情
            # 时段结束了", 当天已拉到的实时价要留着给今日总览/决策台用,
            # 等盘后管道把官方收盘价落盘后自然被覆盖。
            self.stop()
            logger.info("实时行情自动关闭(收盘)")

    def set_repo(self, repo) -> None:
        """注入 KlineRepository, 用于实时落盘。"""
        self._repo = repo

    def set_app_state(self, app_state) -> None:
        """注入 FastAPI app.state, 用于获取 strategy_monitor 等单例。"""
        self._app_state = app_state

    def set_interval(self, interval: float) -> float:
        """运行时更新轮询间隔（立即生效）。"""
        clamped = self._clamp_interval(interval)
        self._interval = clamped
        from app.services import preferences
        preferences.set_realtime_quote_interval(clamped)
        logger.info("轮询间隔已更新为 %.1fs", clamped)
        return clamped

    def get_min_interval(self) -> float:
        """返回当前档位允许的最小间隔。"""
        return self._tier_min_interval()

    # ================================================================
    # SSE 订阅管理 — 每个 /stream 连接一个订阅者, 事件广播
    # ================================================================

    def subscribe(self) -> QuoteSubscriber:
        """注册一个 SSE 订阅者 (连接建立时调用)。"""
        sub = QuoteSubscriber()
        with self._lock:
            self._subscribers.add(sub)
        return sub

    def unsubscribe(self, sub: QuoteSubscriber) -> None:
        """注销订阅者 (连接断开时调用)。"""
        with self._lock:
            self._subscribers.discard(sub)

    def _snapshot_subscribers(self) -> list[QuoteSubscriber]:
        with self._lock:
            return list(self._subscribers)

    def _broadcast_quote_updated(self) -> None:
        # 实时行情刷新后清空总览聚合缓存, 使看板 (overview-market) 在 SSE 触发的
        # 重取中拿到最新指数/聚合值。与 _broadcast 同时进行, 与侧栏 /intraday/indices
        # (无缓存, 直读实时缓存) 行为对齐, 避免看板落后于侧栏。
        # 延迟导入规避 services <-> api 层循环依赖。
        from app.api.overview import invalidate_overview_cache

        invalidate_overview_cache()
        for sub in self._snapshot_subscribers():
            sub.notify_quote()

    def notify_strategy_results_updated(self) -> None:
        """策略监控完成实时结果更新后调用，仅刷新策略页结果缓存。"""
        for sub in self._snapshot_subscribers():
            sub.notify_strategy_results()

    def notify_depth_updated(self) -> None:
        """五档盘口修正完成后调用: 通知 SSE 推送 depth_updated, 触发连板梯队刷新。

        与行情/告警通道独立 — 只刷新连板梯队, 不连带刷新 watchlist 等。
        """
        for sub in self._snapshot_subscribers():
            sub.notify_depth()

    def _broadcast_alerts(self, alerts: list[dict]) -> None:
        for sub in self._snapshot_subscribers():
            sub.push_alerts(alerts)

    def push_alerts(self, alerts: list[dict]) -> None:
        self._broadcast_alerts(alerts)

    def clear_pending_alerts(self) -> None:
        for sub in self._snapshot_subscribers():
            sub.clear_alerts()

    def push_review_event(self, event_json: str) -> None:
        """广播一条复盘进度事件(JSON 字符串), 唤醒所有 SSE generator。

        事件格式与 recap_market_stream 的产出一致(meta/delta/error/done),
        前端 reviewStore 直接消费。背压在订阅者队列内做 (丢弃最旧)。
        """
        for sub in self._snapshot_subscribers():
            sub.push_review(event_json)

    # ================================================================
    # 档位感知间隔限制
    # ================================================================

    @staticmethod
    def _current_tier() -> str:
        """获取当前档位名（小写）。"""
        from app.tickflow.policy import tier_label
        return tier_label().split()[0].split("+")[0].strip().lower()

    @classmethod
    def realtime_mode(cls) -> str:
        """当前实时行情模式: none / watchlist / full_market。

        [fork] 上游 v0.2.2 起免费档=无实时(理由是 fuyao 免费全市场已覆盖);
        本 fork 保留免费档自选实时(watchlist) —— 多 key 轮换池(R30/R35)喂
        自选叠加层与监控引擎, 是本 fork 的主干功能, 不随上游下线。
        """
        from app.services import preferences
        if preferences.get_realtime_data_provider() != "tickflow":
            return "full_market"
        tier = cls._current_tier()
        if tier == "none":
            return "none"
        if tier == "free":
            return "watchlist"
        return "full_market"

    @classmethod
    def is_realtime_allowed(cls) -> bool:
        """当前档位是否允许使用实时行情。"""
        return cls.realtime_mode() != "none"

    @classmethod
    def _tier_min_interval(cls) -> float:
        # 实时源路由到插件/自定义源时, TickFlow 档位限速不适用 (中立能力原则):
        # 下限放宽到通用 1s, 默认/已保存间隔不变
        from app.services import preferences
        if preferences.get_realtime_data_provider() != "tickflow":
            return cls.CUSTOM_PROVIDER_MIN_INTERVAL
        tier = cls._current_tier()
        return cls.TIER_MIN_INTERVAL.get(tier, cls.DEFAULT_INTERVAL)

    def _clamp_interval(self, interval: float) -> float:
        return max(self._tier_min_interval(), min(self.MAX_INTERVAL, interval))

    # ================================================================
    # 行情数据访问
    # ================================================================

    def get_enriched_today(self) -> tuple[pl.DataFrame, date | None]:
        """返回今天 enriched 数据 + 日期 (线程安全)。

        所有页面统一通过此方法获取实时行情 + 技术指标。
        """
        if not self._repo:
            return pl.DataFrame(), None
        return self._repo.get_enriched_latest()

    def get_quotes_compat(self) -> pl.DataFrame:
        """兼容接口: 返回行情 DataFrame (用于盘中选股等需要 last_price/prev_close 的场景)。

        从 _enriched_cache 取 today 的数据, 只选行情基础列, 补上 last_price 别名。
        不返回指标列, 避免 JOIN live_agg 时列名冲突。
        """
        df, _ = self.get_enriched_today()
        if df.is_empty():
            return df

        # 只取盘中选股需要的行情基础列
        keep = [c for c in [
            "symbol", "close", "open", "high", "low", "volume", "amount",
            "prev_close", "change_pct", "change_amount", "amplitude", "turnover_rate",
        ] if c in df.columns]
        df = df.select(keep)

        # enriched 的 close 等价于 last_price
        if "close" in df.columns and "last_price" not in df.columns:
            df = df.with_columns(pl.col("close").alias("last_price"))
        return df

    def get_index_quotes(self, symbols: list[str] | None = None) -> pl.DataFrame:
        """返回实时指数行情缓存。不会触发 TickFlow 请求。"""
        with self._lock:
            df = self._index_quotes_cache.clone() if self._index_quotes_cache is not None else pl.DataFrame()
        if df.is_empty():
            return df
        if symbols:
            return df.filter(pl.col("symbol").is_in(symbols))
        return df

    def status(self) -> dict:
        """返回行情服务状态。"""
        age = (time.perf_counter() - self._fetch_time) * 1000 if self._fetch_time else -1
        mode = self.realtime_mode()
        phase = self._market_phase()
        final_key = self._final_sync_key(phase)
        final_done = bool(final_key and final_key in self._final_sync_done)
        final_failed = self._final_sync_failed.get(final_key) if final_key else None
        return {
            "enabled": self._enabled,
            "running": self._running,
            "paused": self._paused,
            "mode": mode,
            "realtime_allowed": mode != "none",
            "interval_s": self._interval,
            "symbol_count": self._symbol_count,
            "index_symbol_count": self._index_symbol_count,
            "etf_symbol_count": self._etf_symbol_count,
            "quote_age_ms": round(age, 0) if age >= 0 else None,
            # 交易时段 = 连续竞价; polling_window 另行返回,避免午休/收盘缓冲误显示为交易中。
            "is_trading_hours": self._is_continuous_trading(),
            "is_polling_window": self._should_poll_for_phase(phase),
            "market_phase": phase,
            "final_sync_done": final_done,
            "final_sync_failed": final_failed,
            "last_fetch_ms": round(self._fetched_at, 0) if self._fetched_at else None,
        }

    def refresh(self) -> dict:
        """手动触发一次行情拉取。"""
        self._fetch_quotes()
        return self.status()

    def refresh_full(self, max_rounds: int = 12) -> dict:
        """[R19] 全量立即刷新: 连续拉取直到轮转窗口把全部自选覆盖一遍(有界)。

        自选 ≤ 每轮容量时一轮即全量; 超过时按轮转推进, 以偏移量回绕判定覆盖完成。
        每轮内部自带按 key 限速(sleep_between_batches), 压缩的是轮询等待不是限速,
        请求总量与后台轮询跑同样轮数完全一致。max_rounds 防免费额度极小 +
        自选极大时的长阻塞(此时返回 full_coverage=False, 前端如实提示)。
        """
        covered_all = False
        rounds = 0
        for _ in range(max(1, max_rounds)):
            before = getattr(self, "_rt_rotate_offset", 0)
            self._fetch_quotes()
            rounds += 1
            after = getattr(self, "_rt_rotate_offset", 0)
            if after == before == 0:
                covered_all = True  # 一轮全量(自选未超容量 / 全市场档)
                break
            if after <= before:
                covered_all = True  # 轮转越过起点 → 所有自选都刷过一遍
                break
        st = self.status()
        st["full_coverage"] = covered_all
        st["rounds"] = rounds
        return st

    # ================================================================
    # 后台轮询
    # ================================================================

    def _poll_loop(self) -> None:
        while self._running and self._enabled:
            try:
                # 管道/数据修正运行期间临时暂停取数, 防止与管道写同一批 parquet 竞态。
                # 线程继续存活 + 分片 sleep, resume() 后即时恢复, 无需重启线程。
                if not self._paused:
                    phase = self._market_phase()
                    if self._should_fetch_for_phase(phase):
                        is_final = phase in {"morning_final", "close_final"}
                        ok = self._fetch_quotes(final=is_final)
                        if is_final:
                            key = self._final_sync_key(phase)
                            if key and ok:
                                self._final_sync_done.add(key)
                                self._final_sync_failed.pop(key, None)
                                logger.info("%s 最终行情同步完成, 进入休盘态", "午休" if phase == "morning_final" else "收盘")
                            elif key:
                                self._final_sync_failed[key] = "fetch_failed"
                                logger.warning("%s 最终行情同步失败, 将继续重试", "午休" if phase == "morning_final" else "收盘")
                    else:
                        logger.debug("非轮询阶段(%s), 跳过行情轮询", phase)
            except Exception as e:  # noqa: BLE001
                logger.warning("行情轮询异常: %s", e)

            waited = 0.0
            while self._running and self._enabled and waited < self._interval:
                time.sleep(0.5)
                waited += 0.5

    def refresh_single(self, symbol: str) -> bool:
        """[fork 增强] R74 单票按需实时: 现拉这一只的行情并写进自选实时叠加层。

        个股分析弹窗要"点开就是最新"。结果进**独立的单票缓存**(R77),
        只喂弹窗那一族消费者(日K注入 / 六态 live 映射) —— 不碰自选叠加层
        和 kline_daily, 那些共享层有"只含自选、只含当天、只由轮询喂"的
        契约, 混进弹窗随手点的票会把监控/策略的评估快照弄脏。

        - 只走 TickFlow(本 fork 铁律: 不引入第三方数据源); 无 key 静默返回 False,
          页面退回收盘口径, 不报错。
        - 每票 15s 冷却: 反复开关弹窗不烧配额(免费档 quotes.get 也计次)。
        """
        sym = str(symbol or "").strip().upper()
        if not sym or self._repo is None:
            return False
        if not self._claim_single_refresh(sym):
            return True     # 冷却期内: 叠加层里就是刚拉过的, 视为已最新
        return self._pull_single(sym)

    def refresh_single_background(self, symbol: str) -> str:
        """[R76] 弹窗用的非阻塞入口: 立刻返回, 拉取扔进后台线程。

        R74 把拉取放在了日K响应路径上 —— 弹窗要白等一次网络才出图。改成:
        响应马上回旧数据, 后台线程拉完写进叠加层, 前端过一两秒再取一次,
        蜡烛自己冒出来。返回值给前端定节奏:
          - "started": 刚认领, 后台在拉 —— 前端稍后应再取一次
          - "fresh":   冷却期内, 叠加层就是新的 —— 不用再取
          - "off":     没 key / 没 repo —— 没有实时这回事, 别再来问
        """
        sym = str(symbol or "").strip().upper()
        if not sym or self._repo is None:
            return "off"
        from app.tickflow.client import get_realtime_client_pool
        if not get_realtime_client_pool():
            return "off"
        if not self._claim_single_refresh(sym):
            return "fresh"
        t = threading.Thread(target=self._pull_single, args=(sym,),
                             name=f"single-refresh-{sym}", daemon=True)
        t.start()
        return "started"

    def _claim_single_refresh(self, sym: str) -> bool:
        """认领一次单票刷新(15s 冷却)。True=拿到, False=冷却期内。

        认领即占位 —— 之后失败也不退回, 免得坏 key 被连点打成请求风暴。"""
        now = time.monotonic()
        with self._fetch_lock:
            if now - self._single_refresh_at.get(sym, 0.0) < 15.0:
                return False
            self._single_refresh_at[sym] = now
            if len(self._single_refresh_at) > 500:
                self._single_refresh_at = dict(
                    sorted(self._single_refresh_at.items(), key=lambda kv: kv[1])[-200:])
            return True

    def _pick_single_client(self, pool: list):
        """[R76] 挑一个**空闲**的 key 干这单活。

        后台轮询每轮会占用池里的一部分 key(R35 错峰); 单票刷新再去挤同一个
        key, 撞上的就是限流等待 —— 这正是"弹窗变慢"的另一半原因。优先挑
        本轮没被轮询占用的 key; 全忙(或没开实时)时随机挑一个摊开负载。"""
        import random
        busy = getattr(self, "_busy_key_idx", None) or set()
        idle = [c for i, c in enumerate(pool) if i not in busy]
        return random.choice(idle or pool)

    def _pull_single(self, sym: str) -> bool:
        """真正的拉取(可能在后台线程里跑)。任何失败只 False 不抛。

        [R77] 结果**只进独立的单票缓存**, 不再写任何共享层。R74/R76 曾把它
        灌进自选实时叠加层 + merge 进 kline_daily —— 但那两层的隐含契约是
        "只含自选、只含当天、只由轮询喂": 监控引擎在自选档直接拿叠加层当
        股票评估快照(还把日期强制标成今天), 自选页/今日总览也读它 ——
        随手点开过弹窗的票混着可能过期的价进去后, 异动监控和策略评估的
        就是一份垃圾快照。磁盘那份更糟: _build_daily 把日期无条件标 cn_today,
        非交易时段点弹窗会写出"幽灵交易日"分区。单票的日期从行情自带的
        quote_ts 推真实交易日; 推不出宁可放弃, 不造日期。
        """
        from datetime import datetime as _dt

        from app.market_time import CN_TZ
        from app.tickflow.client import get_realtime_client_pool
        pool = get_realtime_client_pool()
        if not pool:
            return False
        try:
            resp = self._pick_single_client(pool).quotes.get(symbols=[sym]) or []
        except Exception as e:
            logger.debug("单票实时拉取失败 %s: %s", sym, e)
            return False
        records = self._quotes_to_records(resp)
        rec = next((r for r in records if str(r.get("symbol") or "").upper() == sym), None)
        if rec is None and records:
            rec = records[0]
        if rec is None:
            return False
        close = rec.get("last_price")
        ts = rec.get("timestamp")
        if not close or close <= 0 or not ts:
            return False
        try:
            trade_date = _dt.fromtimestamp(float(ts) / 1000.0, CN_TZ).date()
        except (TypeError, ValueError, OSError):
            return False
        row = {
            "symbol": sym,
            "date": str(trade_date),
            "open": rec.get("open") or close,
            "high": rec.get("high") or close,
            "low": rec.get("low") or close,
            "close": close,
            "volume": rec.get("volume"),
            "amount": rec.get("amount"),
            "prev_close": rec.get("prev_close"),
            "change_pct": rec.get("change_pct"),   # 小数制, 与 enriched 口径一致
            "quote_ts": ts,
        }
        with self._fetch_lock:
            self._single_live[sym] = row
            if len(self._single_live) > 200:
                self._single_live.pop(next(iter(self._single_live)))
        return True

    def get_single_live(self, symbol: str) -> dict | None:
        """[R77] 弹窗单票缓存里这只票的最新行(带真实 date)。没有返回 None。

        只给弹窗那一族消费者用(日K注入 / 六态趋势的 live 映射) —— 监控、
        自选页、今日总览等共享层消费者**不该**读这里。
        """
        return self._single_live.get(str(symbol or "").strip().upper())

    def _fetch_quotes(self, *, final: bool = False) -> bool:
        """按当前档位拉取行情。加锁串行化 (后台轮询 vs 手动 refresh)。返回本轮是否成功更新。"""
        with self._fetch_lock:
            before = self._fetched_at
            if final:
                logger.info("最终行情同步开始")
            if self.realtime_mode() == "watchlist":
                self._fetch_watchlist_quotes()
            else:
                self._fetch_full_market_quotes()
            return self._fetched_at > before

    def _fetch_full_market_quotes(self) -> None:
        """拉取全市场行情 → 写 daily + 计算 enriched + 更新缓存。"""
        from app.services import preferences

        provider_name = preferences.get_realtime_data_provider()
        if provider_name != "tickflow":
            from app.data_providers import custom as custom_sources
            if custom_sources.provider_has_dataset(provider_name, "realtime"):
                try:
                    t0 = time.perf_counter()
                    now_ts = time.perf_counter()
                    provider = custom_sources.get_provider(provider_name)
                    records = provider.get_realtime()
                    # 指数补充: A 股快照通常不含指数。插件可选实现
                    # get_realtime_indices(symbols) 用独立端点补拉 (如 fuyao 指数快照);
                    # 未实现的源指数缓存为空, 由日K兜底接管。
                    fetch_indices = getattr(provider, "get_realtime_indices", None)
                    if callable(fetch_indices):
                        wanted = sorted(set(CORE_INDEX_SYMBOLS) | self._collect_monitor_index_symbols())
                        try:
                            records = records + (fetch_indices(wanted) or [])
                        except Exception as e:  # noqa: BLE001
                            logger.warning("自定义源指数行情拉取失败: %s", e)
                except Exception as e:  # noqa: BLE001
                    logger.warning("自定义实时行情拉取失败: %s", e)
                    return
                self._process_full_market_records(records, t0=t0, now_ts=now_ts)
                return
            # 自定义源未配置 realtime → 回退 TickFlow

        from app.tickflow.client import get_paid_realtime_client

        tf = get_paid_realtime_client()
        if tf is None:
            logger.warning("实时行情拉取失败:未配置付费服务器 API Key")
            return
        t0 = time.perf_counter()
        now_ts = time.perf_counter()

        try:
            from app.services import preferences
            all_index_symbols = set(self._repo.get_index_symbol_set()) if self._repo else set()
            core_index_symbols = set(CORE_INDEX_SYMBOLS)
            all_index_symbols.update(core_index_symbols)
            # 指数监控规则标的并入显式拉取 (quotes.get 按码覆盖)
            monitor_index_symbols = self._collect_monitor_index_symbols()
            all_index_symbols.update(monitor_index_symbols)
            all_etf_symbols = set()
            if self._repo:
                etf_inst = self._repo.get_etf_instruments()
                if not etf_inst.is_empty() and "symbol" in etf_inst.columns:
                    all_etf_symbols = set(etf_inst["symbol"].cast(pl.Utf8).to_list())

            universes: list[str] = []
            if preferences.get_realtime_pull_stock():
                universes.append("CN_Equity_A")
            if preferences.get_realtime_pull_etf() and all_etf_symbols:
                universes.append("CN_ETF")

            resp = []
            if universes:
                _u0 = time.perf_counter()
                logger.info("拉取全市场行情 (universes=%s, SDK超时=30s×重试3)", universes)
                resp.extend(tf.quotes.get_by_universes(universes=universes) or [])
                logger.info("全市场行情拉取完成: %d 条 (%.2fs)", len(resp), time.perf_counter() - _u0)
            # 指数: 固定核心四只 + 监控规则标的, 按码显式拉取
            _core_syms = sorted(core_index_symbols | monitor_index_symbols)
            if _core_syms:
                _i0 = time.perf_counter()
                resp.extend(tf.quotes.get(symbols=_core_syms) or [])
                logger.info("核心指数行情拉取完成: %d 只 (%.2fs)", len(_core_syms), time.perf_counter() - _i0)
        except Exception as e:  # noqa: BLE001
            logger.warning("行情拉取失败 (%.2fs): %s", time.perf_counter() - t0, e)
            return

        if not resp:
            logger.warning("行情数据为空")
            return

        # ---- 解析 API 响应 (临时变量, 用完丢弃) ----
        records = []
        for q in resp:
            ext = q.get("ext") or {}
            last_price = q.get("last_price")
            prev_close = q.get("prev_close")
            change_amount = ext.get("change_amount")
            change_pct = ext.get("change_pct")
            if change_amount is None and last_price is not None and prev_close is not None:
                change_amount = float(last_price) - float(prev_close)
            if change_pct is None and change_amount is not None and prev_close not in (None, 0):
                # 与 API ext.change_pct 同为小数制 (0.0366 = 3.66%),
                # enriched 全项目约定小数 (见 pipeline.py), 此处不可乘 100
                change_pct = float(change_amount) / float(prev_close)
            records.append({
                "symbol": q.get("symbol"),
                "name": q.get("name") or ext.get("name"),
                "last_price": last_price,
                "prev_close": prev_close,
                "open": q.get("open"),
                "high": q.get("high"),
                "low": q.get("low"),
                "volume": q.get("volume"),
                "amount": q.get("amount"),
                "change_pct": change_pct,
                "change_amount": change_amount,
                "amplitude": ext.get("amplitude"),
                "turnover_rate": ext.get("turnover_rate"),
                "timestamp": q.get("timestamp"),
                "session": q.get("session"),
            })

        self._process_full_market_records(records, t0=t0, now_ts=now_ts)

    def _process_full_market_records(self, records: list[dict], *, t0: float, now_ts: float) -> None:
        """把全市场 records 写盘并增量计算 enriched。"""
        from app.services import preferences
        all_index_symbols = set(self._repo.get_index_symbol_set()) if self._repo else set()
        core_index_symbols = set(CORE_INDEX_SYMBOLS)
        all_index_symbols.update(core_index_symbols)
        all_etf_symbols = set()
        if self._repo:
            etf_inst = self._repo.get_etf_instruments()
            if not etf_inst.is_empty() and "symbol" in etf_inst.columns:
                all_etf_symbols = set(etf_inst["symbol"].cast(pl.Utf8).to_list())

        if not records:
            logger.warning("行情数据为空")
            return

        index_records = [r for r in records if r.get("symbol") in all_index_symbols]
        etf_records = [r for r in records if r.get("symbol") in all_etf_symbols]
        stock_records = [
            r for r in records
            if r.get("symbol") not in all_index_symbols and r.get("symbol") not in all_etf_symbols
        ]

        fetch_ms = (time.perf_counter() - t0) * 1000
        fetched_at = time.time() * 1000

        # ---- 更新元信息 ----
        with self._lock:
            self._fetch_time = now_ts
            self._fetch_ms = fetch_ms
            self._fetched_at = fetched_at
            self._symbol_count = len(stock_records)
            self._index_symbol_count = len(index_records)
            self._etf_symbol_count = len(etf_records)
            self._index_quotes_cache = self._build_index_quotes(index_records)

        _persist_last_fetch(fetched_at)
        logger.info("行情刷新: %d 只股票, %d 只ETF, %d 只指数, 耗时 %.0fms", len(stock_records), len(etf_records), len(index_records), fetch_ms)

        # 轮询放量状态更新 (volume_delta 规则的差值来源)
        self._update_volume_delta(stock_records, fetched_at)

        # ---- 写 kline_daily (不复权原始价格, 只有 OHLCV) ----
        daily_df = self._build_daily(stock_records)
        if not daily_df.is_empty() and self._repo:
            try:
                self._repo.flush_live_daily(daily_df)
            except Exception as e:  # noqa: BLE001
                logger.warning("日K写盘失败: %s", e)

        etf_daily_df = self._build_daily(etf_records)
        if not etf_daily_df.is_empty() and self._repo:
            try:
                self._repo.flush_live_daily_asset("etf", etf_daily_df)
            except Exception as e:  # noqa: BLE001
                logger.warning("ETF 日K写盘失败: %s", e)

        # ---- 构建 API 直接值的补充表 (不写 daily, 只用于 enriched 计算) ----
        quote_extra = self._build_quote_extra(stock_records)
        etf_quote_extra = self._build_quote_extra(etf_records)

        # ---- 增量计算 enriched + 写盘 + 更新缓存 ----
        if not daily_df.is_empty() and self._repo:
            self._flush_live_enriched(daily_df, quote_extra, asset_type="stock")
        if not etf_daily_df.is_empty() and self._repo:
            self._flush_live_enriched(etf_daily_df, etf_quote_extra, asset_type="etf")
        # ---- 指数: 仅有指数监控规则时才写盘 (无规则零成本) ----
        # 指数为按码显式拉取 (部分标的) → merge 不截断分区
        engine = getattr(self._app_state, "monitor_engine", None) if self._app_state else None
        if engine and engine.has_asset_rules("index") and self._repo:
            index_daily_df = self._build_daily(index_records)
            if not index_daily_df.is_empty():
                try:
                    self._repo.merge_live_daily_asset("index", index_daily_df)
                except Exception as e:  # noqa: BLE001
                    logger.warning("指数日K写盘失败: %s", e)
                self._flush_live_enriched(index_daily_df, self._build_quote_extra(index_records), asset_type="index", merge=True)

        # ---- 通知 SSE ----
        self._broadcast_quote_updated()

        # ---- 策略监控 + 告警评估 ----
        self._evaluate_monitors(daily_df, quote_extra)

    @staticmethod
    def _quotes_to_records(resp: list[dict]) -> list[dict]:
        """TickFlow quotes.get 响应 → 统一 record 形状(与自定义源 get_realtime 对齐)。"""
        records = []
        for q in resp:
            ext = q.get("ext") or {}
            last_price = q.get("last_price")
            prev_close = q.get("prev_close")
            change_amount = ext.get("change_amount")
            change_pct = ext.get("change_pct")
            if change_amount is None and last_price is not None and prev_close is not None:
                change_amount = float(last_price) - float(prev_close)
            if change_pct is None and change_amount is not None and prev_close not in (None, 0):
                # 小数制, 与 ext.change_pct / enriched 口径一致 (不乘 100)
                change_pct = float(change_amount) / float(prev_close)
            records.append({
                "symbol": q.get("symbol"),
                "name": q.get("name") or ext.get("name"),
                "last_price": last_price,
                "prev_close": prev_close,
                "open": q.get("open"),
                "high": q.get("high"),
                "low": q.get("low"),
                "volume": q.get("volume"),
                "amount": q.get("amount"),
                "change_pct": change_pct,
                "change_amount": change_amount,
                "amplitude": ext.get("amplitude"),
                "turnover_rate": ext.get("turnover_rate"),
                "timestamp": q.get("timestamp"),
                "session": q.get("session"),
            })
        return records

    def _fetch_watchlist_quotes(self) -> None:
        """Free 档自选股实时: 按 capability batch 上限分批拉取。"""
        from app.services import preferences
        from app.tickflow.client import get_realtime_client_pool
        from app.tickflow.capabilities import Cap
        from app.tickflow.policy import detect_capabilities
        from app.tickflow.rate_limits import (
            chunked, resolve_limit, select_keys, shuffled_key_order, sleep_between_batches,
            spread_delays,
        )

        symbols = preferences.get_realtime_watchlist_symbols()
        # 指数监控规则标的并入轮询 (与股票共享 batch 额度)
        engine = getattr(self._app_state, "monitor_engine", None) if self._app_state else None
        if engine:
            for _r in list(engine.rules.values()):
                if _r.get("enabled", True) and _r.get("asset_type") == "index" and _r.get("scope") == "symbols":
                    for _s in _r.get("symbols", []):
                        if _s and _s not in symbols:
                            symbols.append(_s)
        if not symbols:
            logger.info("自选实时未配置标的, 跳过行情拉取")
            return

        pool = get_realtime_client_pool()
        if not pool:
            logger.warning("自选实时拉取失败:未配置付费服务器 API Key")
            return

        # 按 capability batch 上限分批: 股票+指数共享额度, 超过上限会导致整轮失败
        capset = detect_capabilities()
        lim = resolve_limit(capset, Cap.QUOTE_BY_SYMBOL, default_batch=5)

        # 每轮容量 cap = batch × key数(5×N)。自选超过容量时, 用「轮转窗口」覆盖全部:
        # 每轮拉 cap 只, 下一轮从上次结尾接着拉, ⌈总数/cap⌉ 轮内所有自选都刷新一遍。
        # 代价是每只的实时刷新周期变为 ⌈总数/cap⌉ × 轮询间隔(多 key、大自选时的取舍)。
        # 自选 ≤ cap 时窗口即全部, 退化为每轮全刷(与原行为一致)。
        # [R35] 每轮随机只启用一部分 key(偏好 realtime_keys_per_round, 0=全部) ——
        # 给额度留白, 并让单个 key 失效时只影响它被抽中的轮次。
        active_idx = select_keys(len(pool), preferences.get_realtime_keys_per_round())
        active_pool = [pool[i] for i in active_idx] or pool
        # [R76] 记下本轮被轮询占用的 key, 单票按需刷新(弹窗)会避开它们挑空闲的
        self._busy_key_idx = set(active_idx) if active_idx else set(range(len(pool)))
        n_keys = len(active_pool)
        cap = lim.batch * n_keys
        total = len(symbols)
        if total > cap:
            offset = getattr(self, "_rt_rotate_offset", 0) % total
            window = (symbols[offset:] + symbols[:offset])[:cap]
            self._rt_rotate_offset = (offset + cap) % total
        else:
            window = symbols
            self._rt_rotate_offset = 0
        batches = chunked(window, lim.batch)

        # 免费多 key 池化: 把每组(≤5 只)轮流分给池中不同的 key,突破单免费 key 的
        # 5 只上限(总额度 5×key数)。单 key 时 pool 只有 1 个,退化为原逻辑。
        #
        # [R35] 不再让所有 key 背靠背打成一个突发, 而是把这一轮摊开在窗口内并加抖动:
        #   - 刷新变成连续滚动, 不是"一跳一跳"整块更新
        #   - 一次网络抖动只毁掉一批(5 只), 不再整轮一起失败
        #   - key 与批次的映射每轮重洗, 免得某个 key 出问题时永远是同几只受害
        # 抖动只会让间隔变大不会变小, 同一 key 的调用间隔仍 >= 60/rpm, 额度约束不变。
        delays = spread_delays(len(batches), n_keys, lim.rpm)
        key_order = shuffled_key_order(n_keys, len(batches))
        t0 = time.perf_counter()
        now_ts = time.perf_counter()
        resp = []
        for i, batch in enumerate(batches):
            # 按「每个 key 自己的第几次调用」限速(i // n_keys),而非全局批次序号 ——
            # 不同 key 之间额度独立,不该互相拖慢;只有同一 key 的连续调用才需间隔。
            sleep_between_batches(i // n_keys, lim.rpm)
            if delays[i] > 0:
                time.sleep(delays[i])
            key_idx = key_order[i]
            client = active_pool[key_idx]
            try:
                resp.extend(client.quotes.get(symbols=batch) or [])
            except Exception as e:  # noqa: BLE001
                logger.warning("自选实时批次 %d/%d 拉取失败(key #%d, 本轮启用 %d/%d): %s",
                               i + 1, len(batches), active_idx[key_idx] + 1 if active_idx else key_idx + 1,
                               n_keys, len(pool), e)

        if not resp:
            logger.warning("自选实时行情数据为空")
            return

        records = self._quotes_to_records(resp)

        index_set = self._repo.get_index_symbol_set() if self._repo else set()
        etf_set = self._repo.get_etf_symbol_set() if self._repo else set()
        index_records, etf_records, stock_records = self._split_records_by_asset(records, index_set, etf_set)

        fetch_ms = (time.perf_counter() - t0) * 1000
        fetched_at = time.time() * 1000
        with self._lock:
            self._fetch_time = now_ts
            self._fetch_ms = fetch_ms
            self._fetched_at = fetched_at
            self._symbol_count = len(stock_records)
            self._index_symbol_count = len(index_records)
            self._etf_symbol_count = len(etf_records)
            self._index_quotes_cache = self._build_index_quotes(index_records) if index_records else None

        _persist_last_fetch(fetched_at)
        logger.info("自选实时刷新: %d 只股票, %d 只ETF, %d 只指数, 耗时 %.0fms",
                    len(stock_records), len(etf_records), len(index_records), fetch_ms)

        daily_df = self._build_daily(stock_records)
        quote_extra = self._build_quote_extra(stock_records)
        if not daily_df.is_empty() and self._repo:
            try:
                self._repo.merge_live_daily_asset("stock", daily_df)
            except Exception as e:  # noqa: BLE001
                logger.warning("自选实时日K写盘失败: %s", e)
            # overlay=True: 自选实时只进「自选实时叠加层」, 不碰全市场盘后快照 (_enriched_cache)。
            # 于是看板/概念/行业/连板/策略统一显示上一完整交易日(盘后)全市场; 自选页/决策台/
            # 自选监控把这层叠加上去拿到自选的实时值。(旧实现把只含自选的 enriched 覆盖进全市场
            # 快照, 导致这些全市场页面坍缩成只剩自选。)
            self._flush_live_enriched(daily_df, quote_extra, asset_type="stock", overlay=True)

        # ETF/指数进自选前5时按各自资产落盘, 不污染股票表
        etf_daily_df = self._build_daily(etf_records)
        if not etf_daily_df.is_empty() and self._repo:
            try:
                self._repo.merge_live_daily_asset("etf", etf_daily_df)
            except Exception as e:  # noqa: BLE001
                logger.warning("自选实时 ETF 日K写盘失败: %s", e)
            self._flush_live_enriched(etf_daily_df, self._build_quote_extra(etf_records), asset_type="etf", merge=True)
        index_daily_df = self._build_daily(index_records)
        if not index_daily_df.is_empty() and self._repo:
            try:
                self._repo.merge_live_daily_asset("index", index_daily_df)
            except Exception as e:  # noqa: BLE001
                logger.warning("自选实时指数日K写盘失败: %s", e)
            self._flush_live_enriched(index_daily_df, self._build_quote_extra(index_records), asset_type="index", merge=True)

        self._broadcast_quote_updated()
        self._evaluate_monitors(daily_df, quote_extra)

    # ================================================================
    # 工具
    # ================================================================

    def _collect_monitor_index_symbols(self) -> set[str]:
        """启用中的指数监控规则标的 (asset_type=index & scope=symbols)。"""
        engine = getattr(self._app_state, "monitor_engine", None) if self._app_state else None
        if not engine:
            return set()
        out: set[str] = set()
        for _r in list(engine.rules.values()):
            if _r.get("enabled", True) and _r.get("asset_type") == "index" and _r.get("scope") == "symbols":
                out.update(s for s in _r.get("symbols", []) if s)
        return out

    @staticmethod
    def _split_records_by_asset(
        records: list[dict], index_set: set[str], etf_set: set[str],
    ) -> tuple[list[dict], list[dict], list[dict]]:
        """把行情 records 按资产拆成 (index, etf, stock)。判定顺序与 resolve_asset_type 一致: 先 ETF 后指数。"""
        index_records: list[dict] = []
        etf_records: list[dict] = []
        stock_records: list[dict] = []
        for r in records:
            sym = r.get("symbol")
            if sym in etf_set:
                etf_records.append(r)
            elif sym in index_set:
                index_records.append(r)
            else:
                stock_records.append(r)
        return index_records, etf_records, stock_records

    @staticmethod
    def _build_daily(records: list[dict]) -> pl.DataFrame:
        """将 API records 转为日K格式 DataFrame (OHLCV + quote_ts, 写 kline_daily 用)。"""
        if not records:
            return pl.DataFrame()
        df = pl.DataFrame(records)
        cols_map = {
            "symbol": "symbol",
            "last_price": "close",
            "open": "open",
            "high": "high",
            "low": "low",
            "volume": "volume",
            "amount": "amount",
            "timestamp": "quote_ts",
        }
        select_exprs = []
        for src, dst in cols_map.items():
            if src in df.columns:
                select_exprs.append(pl.col(src).cast(pl.Int64, strict=False).alias(dst)
                                     if dst == "quote_ts" else pl.col(src).alias(dst))
        if not select_exprs:
            return pl.DataFrame()
        result = df.select(select_exprs).with_columns(
            pl.lit(cn_today()).cast(pl.Date).alias("date"),
        )
        # 停牌/尚无集合竞价的记录 open/high 均为 0。必须在下方用 close 填充前
        # 过滤, 否则零成交行会被伪装成有效日K, 并在 batch 同步后作为实时残留
        # 反复触发历史完整性修复。
        from app.indicators.pipeline import filter_halt_days
        result = filter_halt_days(result)
        # 修复: API 在非交易时段可能返回 open/high/low=0 或 null,
        # 导致蜡烛从 0 开始。用 close 填充这些异常值。
        for col in ("open", "high", "low"):
            if col in result.columns:
                result = result.with_columns(
                    pl.when((pl.col(col) == 0) | pl.col(col).is_null())
                    .then(pl.col("close"))
                    .otherwise(pl.col(col))
                    .alias(col)
                )
        return result

    @staticmethod
    def _build_quote_extra(records: list[dict]) -> pl.DataFrame:
        """构建 API 直接提供的补充字段 (不写 daily, 只传给 enriched 计算)。

        包含: prev_close, change_pct, change_amount, amplitude, turnover_rate。
        """
        if not records:
            return pl.DataFrame()
        df = pl.DataFrame(records)
        keep = [c for c in [
            "symbol", "prev_close", "change_pct", "change_amount",
            "amplitude", "turnover_rate",
        ] if c in df.columns]
        if not keep or "symbol" not in keep:
            return pl.DataFrame()
        out = df.select(keep)
        # 实时 API 的 turnover_rate 入口契约为小数制(0.05 = 5%).
        # enriched 内部统一存百分数值(5 = 5%), 后续页面/筛选直接展示和比较。
        if "turnover_rate" in out.columns:
            out = out.with_columns((pl.col("turnover_rate").cast(pl.Float64, strict=False) * 100).alias("turnover_rate"))
        return out

    @staticmethod
    def _build_index_quotes(records: list[dict]) -> pl.DataFrame:
        """构建指数实时行情缓存，不落股票 parquet。

        注意: API 返回的 change_pct/amplitude 是小数 (0.0366 = 3.66%),
        统一转成百分比输出, 与 _fallback_index_quotes_from_daily 口径一致
        (前端指数侧不×100, 直接 toFixed(2)% 展示)。
        """
        if not records:
            return pl.DataFrame()
        df = pl.DataFrame(records)
        keep = [c for c in [
            "symbol", "name", "last_price", "prev_close", "open", "high", "low",
            "volume", "amount", "change_pct", "change_amount", "amplitude", "timestamp", "session",
        ] if c in df.columns]
        if not keep or "symbol" not in keep:
            return pl.DataFrame()
        df = df.select(keep)
        # 自定义源可能不提供 change_pct/change_amount, 按 last_price/prev_close 补算
        # (TickFlow 路径在 _fetch_full_market_quotes 已算好, 此处只补缺失的)
        if "change_pct" not in df.columns and "last_price" in df.columns and "prev_close" in df.columns:
            # prev_close=0 → inf (非合法 JSON), prev_close=null → null; 用 when 守护
            df = df.with_columns(
                pl.when(pl.col("prev_close") != 0)
                .then((pl.col("last_price") - pl.col("prev_close")) / pl.col("prev_close"))
                .otherwise(None)
                .alias("change_pct")
            )
        if "change_amount" not in df.columns and "last_price" in df.columns and "prev_close" in df.columns:
            df = df.with_columns(
                (pl.col("last_price") - pl.col("prev_close")).alias("change_amount")
            )
        # change_pct / amplitude: 小数 → 百分比 (统一指数展示口径)
        for col in ("change_pct", "amplitude"):
            if col in df.columns:
                df = df.with_columns((pl.col(col).cast(pl.Float64) * 100).alias(col))
        if "last_price" in df.columns and "close" not in df.columns:
            df = df.with_columns(pl.col("last_price").alias("close"))
        return df

    @staticmethod
    def _market_phase() -> str:
        """A股行情轮询阶段(北京时间)。

        final 阶段用于午休/收盘定版: 需要至少成功拉取一版边界后的行情, 才算进入休盘。
        """
        now = cn_now()
        if now.weekday() >= 5:
            return "closed"
        t = now.time()
        if dt_time(9, 15) <= t < dt_time(9, 30):
            return "preopen"
        if dt_time(9, 30) <= t < dt_time(11, 30):
            return "morning"
        if dt_time(11, 30) <= t < dt_time(12, 55):
            return "morning_final"
        if dt_time(12, 55) <= t < dt_time(13, 0):
            return "pre_afternoon"
        if dt_time(13, 0) <= t < dt_time(15, 0):
            return "afternoon"
        if t >= dt_time(15, 0):
            return "close_final"
        return "closed"

    @staticmethod
    def _final_sync_key(phase: str) -> tuple[date, str] | None:
        if phase == "morning_final":
            return (cn_today(), "morning")
        if phase == "close_final":
            return (cn_today(), "close")
        return None

    def _holiday_gate(self) -> bool:
        """交易日探针门控: 确定休市 → False (停止轮询, 含 final 定版)。

        探针未知 (None, 未配置 fuyao 且 tickflow 不可用/开盘缓冲窗内) → True,
        维持周几近似现状行为。探针是纯读, 不落盘; 休市结论带 TTL 定期复探,
        误判自愈。首次判定变化打一条日志, 避免每拍刷屏。
        """
        from app.services import trading_day

        holiday = trading_day.is_trading_day() is False
        if holiday != self._holiday_active:
            self._holiday_active = holiday
            if holiday:
                logger.info("交易日探针判定休市, 行情轮询暂停 (30 分钟复探)")
        return not holiday

    def _should_poll_for_phase(self, phase: str) -> bool:
        """是否处于会主动拉行情的阶段。final 阶段成功后即停止。

        节假日 (工作日但休市) 由交易日探针剔除 — 周几门控覆盖不到的部分。
        """
        if not self._holiday_gate():
            return False
        if phase in {"preopen", "morning", "pre_afternoon", "afternoon"}:
            return True
        key = self._final_sync_key(phase)
        return bool(key and key not in self._final_sync_done)

    def _should_fetch_for_phase(self, phase: str) -> bool:
        return self._should_poll_for_phase(phase)

    def _is_trading_hours(self) -> bool:
        """行情轮询窗口(兼容旧调用): 包含盘前预热和未完成的午休/收盘定版。"""
        return self._should_poll_for_phase(self._market_phase())

    @staticmethod
    def _is_continuous_trading() -> bool:
        """A股连续竞价时段(北京时间): 9:30-11:30 / 13:00-15:00, 仅工作日。

        比 _is_trading_hours 严格: 排除 9:15-9:30 集合竞价(指示价, 非成交价)、
        午间与 15:00 后收盘缓冲。监控评估只在此窗口进行, 不对竞价/收盘后的陈旧价告警。
        (节假日由 _evaluate_monitors 里的「快照日期=当日」新鲜度判据兜底, 无需交易日历。)
        """
        now = cn_now()
        t = now.time()
        morning = dt_time(9, 30) <= t <= dt_time(11, 30)
        afternoon = dt_time(13, 0) <= t <= dt_time(15, 0)
        return now.weekday() < 5 and (morning or afternoon)

    @staticmethod
    def _save_enabled(enabled: bool) -> None:
        from app.services import preferences
        preferences.save({"realtime_quotes_enabled": enabled})

    # ================================================================
    # 策略监控
    # ================================================================

    def _evaluate_monitors(self, daily_df: pl.DataFrame, quote_extra: pl.DataFrame | None) -> None:
        """行情更新后评估统一监控规则引擎,并刷新策略结果缓存。"""
        try:
            # 仅在「交易日 + 连续竞价时段」评估监控 —— 避开集合竞价指示价、盘前/收盘后
            # 缓冲。轮询窗口(_is_trading_hours)更宽是为盘前预热/收盘捕捉, 但告警不应
            # 基于这些非连续竞价价格。
            if not self._is_continuous_trading():
                return
            # 获取 enriched 数据 (刚算好的)
            enriched_today, enriched_date = self.get_enriched_today()
            # 自选实时档 (watchlist): 全市场快照是上一交易日(盘后), 自选的实时行在叠加层里。
            # 监控要基于自选实时值, 故此档用叠加层(当天)作为股票评估快照 —— 只含自选, 但正是
            # 该档唯一有实时数据的标的; 全市场规则在盘后价上静态(不会误触发陈旧价)。
            if self._repo is not None and self.realtime_mode() == "watchlist":
                ov = self._repo.get_watchlist_live("stock")
                if not ov.is_empty():
                    enriched_today, enriched_date = ov, cn_today()
            # 股票快照就绪 = 非空 + 日期为当日。未就绪时仅跳过股票轮,
            # ETF/指数轮有各自的空表+日期守卫, 不受影响 (纯指数行情/自选场景可独立评估)。
            stock_ready = (not enriched_today.is_empty()) and (enriched_date == cn_today())
            if not stock_ready:
                logger.debug("股票快照未就绪(空=%s, 日期=%s), 跳过股票轮",
                             enriched_today.is_empty(), enriched_date)

            all_alerts: list[dict] = []
            rule_events: list[dict] = []
            engine = None

            # 通用监控规则评估 (统一引擎: signal/price/market/strategy)
            if self._app_state:
                engine = getattr(self._app_state, "monitor_engine", None)
                if engine and engine.rule_count > 0:
                    # 预构建 symbol → name 映射 (enriched 已 drop name 列, 引擎触发时回填用)。
                    # 股票 + ETF + 指数三表合并走 _monitor_name_map -> repo.get_name_map()
                    # 的进程内 memo, 避免每轮监控对 ~7000 行维表 iter_rows 重建。
                    try:
                        name_map = _monitor_name_map(self._app_state.repo)
                        if name_map:
                            engine.set_name_map(name_map)
                    except Exception as e:  # noqa: BLE001
                        logger.debug("name_map 构建失败 (不影响监控): %s", e)
                    # 股票轮: 快照未就绪时跳过 (ladder 封单也依赖股票快照日期, 一并跳过)
                    if stock_ready:
                        eval_df = enriched_today
                        if engine.has_rule_type("ladder"):
                            eval_df = self._inject_sealed_vol(enriched_today, enriched_date)
                        if engine.has_rule_type("volume_delta"):
                            eval_df = self._inject_volume_delta(eval_df)
                        eval_df = self._inject_intraday_signals(eval_df, engine, "stock")
                        rule_events = engine.evaluate(eval_df, asset_type="stock")
                        if engine.consume_strategy_result_updates():
                            self.notify_strategy_results_updated()
                    if engine.has_rule_type("sector"):
                        rule_events += engine.evaluate_sectors(
                            enriched_today if stock_ready else pl.DataFrame(),
                            self.get_index_quotes(),
                        )
                    # 异动边缘规则轮: 快照 (enriched 偏离列 + 实时叠加) 由
                    # abnormal_moves.build_overview 统一构建, 引擎只做边缘触发判定。
                    # 30s 限频 —— 快照历史部分 60s 缓存, 无需跟行情轮询同频重算。
                    if engine.has_rule_type("abnormal") and self._repo is not None:
                        _now_ts = time.time()
                        if _now_ts - self._abnormal_last_eval >= 30.0:
                            self._abnormal_last_eval = _now_ts
                            try:
                                from app.services import abnormal_moves
                                _overview = abnormal_moves.build_overview(
                                    self._repo, self,
                                    min_closeness=engine.min_abnormal_closeness(),
                                    limit=1000,
                                )
                                rule_events += engine.evaluate_abnormal(_overview.get("rows") or [])
                            except Exception as e:  # noqa: BLE001
                                logger.warning("异动监控规则评估失败 (不影响其他告警): %s", e)
                    # 日期提醒轮: 纯日历、无行情, 已在盘中; 引擎内按天 cooldown 保证每天一次
                    if engine.has_rule_type("date"):
                        try:
                            rule_events = rule_events + engine.evaluate_date_rules()
                        except Exception as e:  # noqa: BLE001
                            logger.warning("日期提醒评估失败 (不影响其他告警): %s", e)
                    # ETF 规则轮: 股票快照不含 ETF, 用 ETF enriched 快照单独评估。
                    # 独立 try —— ETF 轮任何异常都不得丢弃本轮已算出的股票告警。
                    # refresh=False —— 不在轮询线程上触发 ETF 冷缓存的同步重算 (缓存由 ETF 实时
                    # flush 焐热; 未焐热说明无 ETF 实时数据, 跳过本轮 ETF 评估)。
                    if engine.has_asset_rules("etf") and self._repo is not None:
                        try:
                            etf_enriched, _ = self._repo.get_enriched_latest_asset("etf", refresh=False)
                            if not etf_enriched.is_empty():
                                etf_enriched = self._inject_intraday_signals(etf_enriched, engine, "etf")
                                rule_events = rule_events + engine.evaluate(
                                    etf_enriched, asset_type="etf", reset_strategy_results=False,
                                )
                        except Exception as e:  # noqa: BLE001
                            logger.warning("ETF 监控评估失败 (不影响股票告警): %s", e)
                    # 指数规则轮: 复刻 ETF 轮。快照由指数实时 flush 焐热;
                    # refresh=False 冷缓存不同步重算; 显式日期守卫防陈旧 parquet 误告警
                    # (ETF 轮靠空表隐式跳过, 指数轮更显式, 行为等价)。
                    if engine.has_asset_rules("index") and self._repo is not None:
                        try:
                            index_enriched, index_date = self._repo.get_enriched_latest_asset("index", refresh=False)
                            if not index_enriched.is_empty() and index_date == cn_today():
                                index_enriched = self._inject_intraday_signals(index_enriched, engine, "index")
                                rule_events = rule_events + engine.evaluate(
                                    index_enriched, asset_type="index", reset_strategy_results=False,
                                )
                        except Exception as e:  # noqa: BLE001
                            logger.warning("指数监控评估失败 (不影响股票/ETF 告警): %s", e)
                    if rule_events:
                        rule_events = self._format_extension_notifications(rule_events)
                        # [fork R160] 焦点标记: 每条告警算一次"这只票在不在焦点名单",
                        # 结果盖章在事件上(focus_muted), 落盘 / SSE / 系统通知 / Webhook
                        # 四条出口读同一个章 —— 用户说"开了跌破生命线就一堆推送", 光拦
                        # 外部渠道不够, 所有会打断人的通道都得认这个章。任何异常 = 不静音。
                        try:
                            from app.services import focus_list
                            _rules = engine.rules if engine is not None else {}
                            for ev in rule_events:
                                _rule = _rules.get(ev.get("rule_id"))
                                ev["focus_muted"] = not focus_list.should_push(ev.get("symbol") or "", _rule)
                        except Exception as e:  # noqa: BLE001
                            logger.debug("focus stamp skipped: %s", e)
                        # 落盘到 alerts.jsonl
                        try:
                            from app.services import alert_store
                            alert_store.append_many(
                                self._app_state.repo.store.data_dir, rule_events,
                            )
                        except Exception as e:  # noqa: BLE001
                            logger.warning("告警落盘失败: %s", e)
                        # 转为 SSE 推送格式 (兼容旧 alert schema)
                        for ev in rule_events:
                            alert = {
                                "source": ev["source"],
                                "type": ev["type"],
                                "rule_id": ev.get("rule_id"),
                                "strategy_id": ev.get("strategy_id") if ev["source"] == "strategy" else None,
                                "symbol": ev["symbol"],
                                "name": ev["name"],
                                "message": ev["message"],
                                "price": ev["price"],
                                "change_pct": ev["change_pct"],
                                "signals": ev["signals"],
                                "severity": ev.get("severity", "info"),
                                "conditions": ev.get("conditions") or [],
                                "logic": ev.get("logic") or "and",
                                "focus_muted": bool(ev.get("focus_muted")),   # [R160]
                            }
                            for key in (
                                "sector_kind", "sector_key", "sector_name",
                                "sector_source_field", "sector_value", "sector_level",
                                "window_change_pct", "coverage_ratio", "valid_count",
                                "total_count", "up_count", "down_count", "leader",
                                "abnormal_window", "abnormal_value", "abnormal_threshold",
                                "abnormal_closeness", "volume_delta", "volume_delta_span",
                                "volume_delta_amount",
                            ):
                                if key in ev:
                                    alert[key] = ev[key]
                            all_alerts.append(alert)

            # 策略页实时回显: 不写文件 (实时行情每轮更新 enriched, 写文件会被 read_cache
            # 的 mtime 校验判过期, 反复读不到)。监控引擎本轮已算出的结果存在内存
            # (latest_strategy_results), 由 /api/screener/cached 端点直接叠加读取。

            # 广播到所有 SSE 订阅者 (背压保护在订阅者队列内做)
            if all_alerts:
                # 按 symbol 富化行业/概念 ext 字段, 使 toast + 触发记录统一展示板块标签。
                self._enrich_alerts_ext(all_alerts)
                self._broadcast_alerts(all_alerts)
                logger.info("监控评估完成: %d 条通知", len(all_alerts))

                # 系统通知 (可选通道, 由 preferences 开关控制)。
                # cooldown 去重已在 MonitorRuleEngine 做过, 这里只负责转发。
                self._maybe_send_system_notifications(all_alerts)

            # Webhook 推送 (飞书等外部 IM, 由规则 webhook_channels 指定渠道)。
            # 紧随系统通知, 同样静默降级不阻断主流程。
            if rule_events:
                self._maybe_send_webhook(rule_events, engine)

        except Exception as e:  # noqa: BLE001
            logger.warning("监控评估失败: %s", e)

    def _format_extension_notifications(self, events: list[dict]) -> list[dict]:
        """Apply optional copy formatters after evaluation and before every output channel."""
        registry = (
            getattr(self._app_state, "extension_registry", None)
            if self._app_state is not None
            else None
        )
        if registry is None or not registry.has_notification_formatters:
            return events

        from app.extensions.contracts import (
            BACKEND_EXTENSION_API_VERSION,
            NotificationFormatContext,
        )

        formatted_events: list[dict] = []
        for event in events:
            formatted = dict(event)
            context = NotificationFormatContext(
                api_version=BACKEND_EXTENSION_API_VERSION,
            )
            for registered in registry.notification_formatters():
                try:
                    message = registered.implementation.format_message(dict(formatted), context)
                    if not isinstance(message, str):
                        raise TypeError("notification formatter must return str")
                    formatted["message"] = message
                except Exception as exc:
                    logger.warning(
                        "notification formatter failed %s: %s",
                        registered.implementation_id,
                        exc,
                    )
            formatted_events.append(formatted)
        return formatted_events

    def _enrich_alerts_ext(self, alerts: list[dict]) -> None:
        """就地给告警事件按 symbol 追加行业/概念 ext 字段。

        读 preferences.get_monitor_ext_fields() 取字段配置, 用 screener._load_ext_value_maps
        (带 parquet mtime 缓存) 富化。富化失败静默降级 (告警照常推送, 只是没标签)。
        每条事件新增 {configId}__{fieldName} 键 (与 watchlist/screener 输出约定一致)。
        """
        if not alerts or not self._app_state or self._repo is None:
            return
        try:
            from app.services import preferences
            fields = preferences.get_monitor_ext_fields()
            # 新结构 {field, maxTags, hiddenIndices}, 后端只需 .field
            parts = []
            for key in ("concept", "industry"):
                item = fields.get(key)
                if isinstance(item, dict) and item.get("field"):
                    parts.append(item["field"])
                elif isinstance(item, str) and item:
                    parts.append(item)  # 兼容旧格式
            if not parts:
                return
            ext_columns = ",".join(parts)
            from app.api.screener import _load_ext_value_maps
            value_maps = _load_ext_value_maps(self._repo, ext_columns)
            if not value_maps:
                return
            for ev in alerts:
                sym = ev.get("symbol")
                if not sym:
                    continue
                for out_col, vmap in value_maps.items():
                    ev[out_col] = vmap.get(str(sym))
        except Exception as e:  # noqa: BLE001
            logger.debug("告警 ext 富化失败 (不影响推送): %s", e)

    def _inject_intraday_signals(self, enriched: pl.DataFrame, engine, asset_type: str) -> pl.DataFrame:
        """每分钟为分时信号规则批量获取一次数据并注入临时布尔列。"""
        get_symbols = getattr(engine, "intraday_signal_symbols", None)
        if not callable(get_symbols):
            return enriched
        symbols = get_symbols(asset_type)
        if not symbols:
            return enriched

        now = cn_now()
        bucket = now.strftime("%Y%m%d%H%M")
        if self._intraday_signal_bucket.get(asset_type) == bucket:
            return self._intraday_signal_evaluator.inject(enriched, [])
        self._intraday_signal_bucket[asset_type] = bucket

        from app.services.kline_sync import (
            fetch_intraday_monitor_batch,
            intraday_monitor_support,
        )

        capset = getattr(self._app_state, "capabilities", None)

        # 全量分钟健康时股票读本地分区 (服务按间隔持续落盘, 与 API 同一列契约),
        # 免去每分钟 bucket 一次的全量 API 拉取; ETF 不在服务 universe 内,
        # 本地读空/异常回落原 API 路径 (含能力与上限检查)
        minute_df = pl.DataFrame()
        if asset_type == "stock":
            svc = getattr(self._app_state, "minute_refresh", None) if self._app_state else None
            if svc is not None and svc.is_healthy() and self._repo is not None:
                try:
                    minute_df = self._repo.get_minute_batch(sorted(symbols), cn_today())
                except Exception as e:  # 本地读异常回落 API
                    logger.warning("分时信号本地读失败, 回退 API 路径: %s", e)
                    minute_df = pl.DataFrame()
        if minute_df.is_empty():
            support = intraday_monitor_support(capset)
            if not support["available"] or len(symbols) > int(support["max_symbols"]):
                return self._intraday_signal_evaluator.inject(enriched, [])
            minute_df = fetch_intraday_monitor_batch(sorted(symbols), capset, now=now)
        prev_close: dict[str, float] = {}
        available_cols = set(enriched.columns)
        for row in enriched.filter(pl.col("symbol").is_in(sorted(symbols))).iter_rows(named=True):
            symbol = str(row.get("symbol") or "")
            reference = row.get("prev_close") if "prev_close" in available_cols else None
            if reference is None and "close" in available_cols and "change_pct" in available_cols:
                close = row.get("close")
                change_pct = row.get("change_pct")
                if close is not None and change_pct is not None and float(change_pct) > -1:
                    reference = float(close) / (1.0 + float(change_pct))
            if symbol and reference is not None:
                prev_close[symbol] = float(reference)

        signals = self._intraday_signal_evaluator.evaluate(
            minute_df,
            symbols=symbols,
            prev_close=prev_close,
            asset_type=asset_type,
            now=now,
        )
        return self._intraday_signal_evaluator.inject(enriched, signals)

    @staticmethod
    def _continuous_session_start_ms() -> float:
        """当前连续竞价时段的起点 (北京时间 9:30 或 13:00) 的 epoch 毫秒。"""
        now = cn_now()
        start_time = dt_time(13, 0) if now.time() >= dt_time(13, 0) else dt_time(9, 30)
        return datetime.combine(now.date(), start_time, tzinfo=now.tzinfo).timestamp() * 1000.0

    def _update_volume_delta(self, stock_records: list[dict], fetched_at_ms: float) -> None:
        """全市场相邻两次快照的股票累计成交量差值 (手), 供 volume_delta 规则。

        - prev 每轮都更新 (含非连续竞价时段); 差值只在连续竞价时段内计算
        - 开盘保护: prev 早于本时段起点 (9:30/13:00) 时本轮差值无效 -- 避免
          9:25 集合竞价撮合量 / 午休缺口被当成"突然放量"
        - cur < prev (数据源重置/口径跳变) 的个股丢弃差值; 跨交易日清空
        - [fork R81] 额外: 跨轮距超 3×interval 时整轮作废 (暂停恢复不产伪差值);
          成交额缺失记 None 而非 0 (金额口径 fail-closed)
        """
        today = cn_today()
        if self._prev_volume_date != today:
            self._prev_stock_volume = None
            self._prev_volume_fetched_at = None
            self._prev_volume_date = today
            self._volume_delta = {}

        current: dict[str, tuple[float, float | None]] = {}
        for record in stock_records:
            symbol = record.get("symbol")
            volume = record.get("volume")
            amount = record.get("amount")
            if not symbol or isinstance(volume, bool) or not isinstance(volume, (int, float)):
                continue
            current[str(symbol)] = (
                float(volume),
                float(amount) if not isinstance(amount, bool) and isinstance(amount, (int, float)) else None,
            )

        previous = self._prev_stock_volume
        previous_ts = self._prev_volume_fetched_at
        span_s = (fetched_at_ms - previous_ts) / 1000.0 if previous_ts is not None else 0.0
        max_span_s = max(float(getattr(self, "_interval", self.DEFAULT_INTERVAL)) * 3, 30.0)
        if (
            previous is not None
            and previous_ts is not None
            and self._is_continuous_trading()
            and previous_ts >= self._continuous_session_start_ms()
            and 0 < span_s <= max_span_s
        ):
            delta: dict[str, tuple[float, float | None]] = {}
            for symbol, (volume, amount) in current.items():
                if symbol not in previous:
                    continue
                previous_volume, previous_amount = previous[symbol]
                volume_delta = volume - previous_volume
                if volume_delta <= 0:
                    continue
                amount_delta = None
                if amount is not None and previous_amount is not None and amount >= previous_amount:
                    amount_delta = amount - previous_amount
                delta[symbol] = (volume_delta, amount_delta)
            self._volume_delta = delta
            self._volume_delta_span_s = span_s
        else:
            self._volume_delta = {}
            self._volume_delta_span_s = 0.0

        self._prev_stock_volume = current
        self._prev_volume_fetched_at = fetched_at_ms

    def _inject_volume_delta(self, enriched_today: pl.DataFrame) -> pl.DataFrame:
        """把最近一轮有效快照差值作为临时列注入 enriched 副本。"""
        try:
            if not self._volume_delta:
                return enriched_today
            delta_df = pl.DataFrame({
                "symbol": list(self._volume_delta),
                "_volume_delta": [value[0] for value in self._volume_delta.values()],
                "_volume_delta_amount": [value[1] for value in self._volume_delta.values()],
                "_volume_delta_span": [self._volume_delta_span_s] * len(self._volume_delta),
            })
            temporary_columns = (
                "_volume_delta", "_volume_delta_amount", "_volume_delta_span",
            )
            drop_columns = [column for column in temporary_columns if column in enriched_today.columns]
            source = enriched_today.drop(drop_columns) if drop_columns else enriched_today
            return source.join(delta_df, on="symbol", how="left")
        except Exception as exc:  # noqa: BLE001
            logger.debug("快照差值注入失败 (volume_delta 规则将不触发): %s", exc)
            return enriched_today

    def _inject_sealed_vol(self, enriched_today: pl.DataFrame, enriched_date) -> pl.DataFrame:
        """从 depth_service 取封单量, 作为临时列 _sealed_vol 注入 enriched 副本。

        涨停封单(买一量) + 跌停封单(卖一量)合并, 供 ladder 规则评估。
        depth 未就绪时返回原 df (不注入, ladder 规则安全降级不触发)。
        """
        try:
            depth_svc = getattr(self._app_state, "depth_service", None)
            if not depth_svc:
                return enriched_today
            # enriched_date 可能是 date 或字符串, 统一为 date
            from datetime import date as date_cls
            target_date = enriched_date if isinstance(enriched_date, date_cls) else date_cls.fromisoformat(str(enriched_date))
            # 取涨停 + 跌停封单, 合并 {symbol: vol}
            up_map = depth_svc.get_sealed_map(target_date, is_down=False)
            down_map = depth_svc.get_sealed_map(target_date, is_down=True)
            sealed: dict[str, int] = {}
            for m in (up_map, down_map):
                for sym, info in m.items():
                    vol = (info or {}).get("vol")
                    if vol and vol > 0:
                        sealed[sym] = vol  # 后者覆盖前者 (同 symbol 不可能在涨跌停都封单)
            if not sealed:
                return enriched_today
            # 构造 (symbol, _sealed_vol) DataFrame, join 到 enriched 副本
            sealed_df = pl.DataFrame({
                "symbol": list(sealed.keys()),
                "_sealed_vol": list(sealed.values()),
            })
            # 若已有残留列先移除 (避免重复 join 报错)
            df = enriched_today.drop("_sealed_vol") if "_sealed_vol" in enriched_today.columns else enriched_today
            return df.join(sealed_df, on="symbol", how="left")
        except Exception as e:  # noqa: BLE001
            logger.debug("封单注入失败 (ladder 规则将不触发): %s", e)
            return enriched_today

    def _maybe_send_webhook(self, rule_events: list[dict], engine) -> None:
        """把告警通过 Webhook 推送到外部 IM (由规则 webhook_channels 指定渠道)。

        - 飞书 / 企业微信任一已配置即生效 (两个都没配才跳过)
        - 仅推送 webhook_channels 非空的规则触发的告警, 且只投递被勾选的渠道
        - 失败静默, 不阻断主流程
        - 去重: 复用 MonitorRuleEngine 的 cooldown, 此处不重复去重

        注意: 用 rule_events (含 rule_id) 而非重建后的 all_alerts,
        以便反查引擎规则判断是否启用推送。
        """
        try:
            from app.services import preferences
            from app.services import webhook_adapter

            feishu_url = preferences.get_feishu_webhook_url()
            feishu_secret = preferences.get_feishu_webhook_secret()
            wecom_url = preferences.get_wecom_webhook_url()
            dingtalk_url = preferences.get_dingtalk_webhook_url()
            dingtalk_keyword = preferences.get_dingtalk_keyword()
            # 所有通道都没配置才跳过
            if not feishu_url and not wecom_url and not dingtalk_url:
                return

            # 反查规则, 过滤出启用推送的事件
            rules = engine.rules if engine is not None else {}
            enqueued = 0
            muted = 0
            for ev in rule_events:
                rule = rules.get(ev.get("rule_id"))
                # webhook_channels 指定命中的渠道 (['feishu'] / ['wecom'] / ['feishu','wecom'] / []).
                # 空列表 = 该规则不推送。仅推送「渠道已选 + 对应地址已配置」的组合。
                channels = rule.get("webhook_channels") if rule else None
                if not channels:
                    continue
                # [fork R159] 推送门: 总开关开着时, 广域规则只推焦点名单(持有/计划中/钉住);
                # 用户单独给这只票设的规则(scope=symbols)永远放行。任何不确定都放行。
                if ev.get("focus_muted"):        # [R160] 章已在评估处盖好, 这里只认章
                    muted += 1
                    continue
                if "focus_muted" not in ev:      # 没盖到章(异常路径)才现算一次
                    try:
                        from app.services import focus_list
                        if not focus_list.should_push(ev.get("symbol") or "", rule):
                            muted += 1
                            continue
                    except Exception:  # noqa: BLE001
                        pass
                source = ev.get("source", "")
                source_label = SOURCE_LABELS.get(source, source or "通知")
                symbol = ev.get("symbol") or ""
                name = ev.get("name") or ""
                message = ev.get("message") or ""
                title = source_label
                body = f"{symbol} {name} {message}".strip() if symbol else (message or name)
                # 补上触发时的现价/涨跌幅, 让推送可执行 (止损到底触发在哪个价位)
                body = _body_with_quote(body, ev)
                # 提交到独立线程池, 不阻塞行情轮询线程 (webhook 慢/重试不拖累实时行情+告警)。
                # 按渠道独立投递: 飞书 / 企业微信谁被勾选且已配置就推谁。
                # 应用内 alerts.jsonl 记录与 SSE 已在前面完成, 不依赖 webhook 成败,
                # 失败由 webhook_adapter 记 WARNING(可见)。
                if feishu_url and "feishu" in channels:
                    _WEBHOOK_EXECUTOR.submit(webhook_adapter.send_feishu, feishu_url, title, body, feishu_secret)
                    enqueued += 1
                if wecom_url and "wecom" in channels:
                    _WEBHOOK_EXECUTOR.submit(webhook_adapter.send_wecom, wecom_url, title, body)
                    enqueued += 1
                if dingtalk_url and "dingtalk" in channels:
                    _WEBHOOK_EXECUTOR.submit(webhook_adapter.send_dingtalk, dingtalk_url, title, body, dingtalk_keyword)
                    enqueued += 1
            if enqueued or muted:
                logger.info("Webhook 已提交 %d 条, 焦点名单静音 %d 条 (异步投递, 按渠道独立投递, 失败记 WARNING)",
                            enqueued, muted)
        except Exception as e:  # noqa: BLE001
            logger.warning("Webhook 提交异常 (不影响告警主流程): %s", e)

    def _maybe_send_system_notifications(self, all_alerts: list[dict]) -> None:
        """把告警转发到操作系统通知中心 (由 preferences 开关控制)。

        - 开关关闭: 直接返回
        - 开关开启: 逐条发系统通知; 失败静默, 不阻断主流程
        - 去重: 复用 MonitorRuleEngine 的 cooldown, 此处不重复去重
        - 批量策略事件 (symbol="") 聚合为一条通知, 避免刷屏
        """
        try:
            from app.services import preferences
            from app.services import notify_adapter

            if not preferences.get_system_notify_enabled():
                return

            for ev in all_alerts:
                if ev.get("focus_muted"):   # [R160] 焦点外的不打系统通知
                    continue
                # 通知标题: 用 source 分类 (策略/信号/价格/异动)
                source = ev.get("source", "")
                source_label = SOURCE_LABELS.get(source, source or "通知")

                name = ev.get("name") or ""
                symbol = ev.get("symbol") or ""
                message = ev.get("message") or ""

                # 正文: 优先用现成 message, 拼上 symbol/name 让用户一眼定位
                if symbol:
                    body = f"{symbol} {name} {message}".strip()
                else:
                    body = message or name
                # 补上触发时的现价/涨跌幅 (日期提醒无行情, 自然为空)
                body = _body_with_quote(body, ev)

                title = f"TickFlow · {source_label}"
                notify_adapter.notify(title, body)
        except Exception as e:  # noqa: BLE001
            logger.debug("系统通知发送异常 (不影响告警主流程): %s", e)

    @staticmethod
    def _get_strategy_monitor():
        """获取 StrategyMonitorService — 不再使用, 改用 _app_state 注入。"""
        return None

    # ================================================================
    # enriched 增量计算
    # ================================================================

    def _flush_live_enriched(self, daily_df: pl.DataFrame, quote_extra: pl.DataFrame = None, asset_type: str = "stock", merge: bool = False, overlay: bool = False) -> None:
        """增量计算今天的 enriched: 用昨天的递推状态 + 今天 OHLCV → 只算今天 5500 行。

        quote_extra: API 直接提供的补充字段 (prev_close, change_pct 等),
                     不写 daily, 直接传给 compute_enriched_today 避免重复计算。
        """
        try:
            today = cn_today()
            t0 = time.perf_counter()

            # ---- 尝试增量路径 ----
            live_agg = self._repo.get_live_agg() if asset_type == "stock" else pl.DataFrame()
            prev_enriched, prev_date = (
                self._repo.get_enriched_latest()
                if asset_type == "stock"
                else self._repo.get_enriched_latest_asset(asset_type)
            )

            use_incremental = (
                asset_type == "stock"
                and not live_agg.is_empty()
                and not prev_enriched.is_empty()
                and prev_date is not None
            )

            if use_incremental:
                from app.indicators.pipeline import compute_enriched_today
                from app.market_time import trading_minutes_elapsed_from_ts, trading_minutes_elapsed
                instruments = self._repo.get_instruments()
                # 将 API 直接提供的补充字段 JOIN 到 daily_df
                today_ohlcv = daily_df
                if quote_extra is not None and not quote_extra.is_empty():
                    today_ohlcv = daily_df.join(quote_extra, on="symbol", how="left")
                # 量比时间折算: 优先用行情 quote_ts (真实成交时间), 缺失则兜底服务端时间
                elapsed_minutes: float | None = None
                if "quote_ts" in daily_df.columns and not daily_df.is_empty():
                    valid_ts = daily_df["quote_ts"].drop_nulls()
                    if not valid_ts.is_empty():
                        elapsed_minutes = trading_minutes_elapsed_from_ts(valid_ts.median())
                if elapsed_minutes is None:
                    elapsed_minutes = trading_minutes_elapsed()
                enriched_today = compute_enriched_today(
                    live_agg=live_agg,
                    prev_enriched=prev_enriched,
                    today_ohlcv=today_ohlcv,
                    instruments=instruments,
                    elapsed_minutes=elapsed_minutes,
                )
                if enriched_today.is_empty():
                    logger.warning("增量计算结果为空, 回退到全量计算")
                    use_incremental = False

            # ---- 全量回退路径 ----
            if not use_incremental:
                from datetime import timedelta
                from app.indicators.pipeline import compute_enriched

                logger.info("enriched 全量计算 (live_agg=%s, 上次日期=%s)",
                            "ok" if not live_agg.is_empty() else "空", prev_date)

                cutoff = today - timedelta(days=90)
                table = {"etf": "kline_etf_daily", "index": "kline_index_daily"}.get(asset_type, "kline_daily")
                daily_glob = str(self._repo.store.data_dir / table / "**" / "*.parquet")
                ohlcv_cols = ["symbol", "date", "open", "high", "low", "close", "volume", "amount", "quote_ts"]
                hist_df = (
                    scan_daily_parquet(daily_glob)
                    .filter(pl.col("date") >= cutoff)
                    .sort(["symbol", "date"])
                    .collect()
                )
                if hist_df.is_empty():
                    return

                hist_cols = [c for c in ohlcv_cols if c in hist_df.columns]
                hist_df = hist_df.select(hist_cols).filter(pl.col("date") != today)
                daily_ohlcv = daily_df.select([c for c in ohlcv_cols if c in daily_df.columns])
                full_df = pl.concat([hist_df, daily_ohlcv], how="diagonal_relaxed")
                full_df = full_df.sort(["symbol", "date"])

                factor_dir = {"stock": "adj_factor", "etf": "adj_factor_etf"}.get(asset_type)
                factor_path = self._repo.store.data_dir / factor_dir / "all.parquet" if factor_dir else None
                factors = pl.DataFrame()
                if factor_path and factor_path.exists():
                    try:
                        factors = pl.read_parquet(factor_path)
                    except Exception:
                        pass
                instruments = self._repo.get_instruments() if asset_type == "stock" else None

                enriched_full = compute_enriched(
                    full_df,
                    factors=factors,
                    instruments=instruments,
                    historical_shares=(
                        self._repo.get_historical_shares()
                        if asset_type == "stock"
                        else None
                    ),
                )
                # momentum_3d 不在指标全集里, 但 deviate_3d 需要; 多日帧上 shift 补算
                enriched_full = enriched_full.sort(["symbol", "date"]).with_columns(
                    (pl.col("close") / pl.col("close").shift(3).over("symbol") - 1).alias("momentum_3d")
                )
                enriched_today = enriched_full.filter(pl.col("date") == today)

            if enriched_today.is_empty():
                return

            # 异动偏离列: 盘中路径不经过 _refresh_enriched 冷刷新,
            # 需在此附着 (基准 = 历史帧 + 指数实时外推), 否则盘中异动列表为空
            if asset_type == "stock":
                from app.indicators.pipeline import attach_deviation_columns_today
                try:
                    index_quotes = self.get_index_quotes()
                except Exception:
                    index_quotes = None
                enriched_today = attach_deviation_columns_today(
                    enriched_today, self._repo.store.data_dir, index_quotes
                )

            # ---- 写盘 + 更新缓存 ----
            if overlay:
                # 自选实时叠加层: 不碰全市场盘后快照 (_enriched_cache), 只存自选实时行,
                # 供自选页/决策台/自选监控叠加。全市场页面(看板/概念/行业/连板/策略)因此
                # 统一读到上一完整交易日(盘后)全市场, 与自选实时互不干扰。
                self._repo.update_watchlist_live(asset_type, enriched_today)
            elif merge:
                self._repo.merge_live_enriched_asset(asset_type, enriched_today)
            else:
                self._repo.flush_live_enriched_asset(asset_type, enriched_today)

            elapsed = time.perf_counter() - t0
            mode_label = "增量" if use_incremental else "全量"
            logger.info("enriched %s: %d 只, %s, 耗时 %.0fms",
                        mode_label, len(enriched_today), today, elapsed * 1000)
        except Exception as e:  # noqa: BLE001
            logger.warning("enriched 计算失败: %s", e)
