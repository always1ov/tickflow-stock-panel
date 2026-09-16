"""FastAPI 入口。

启动顺序有依赖, 不是随便排的 —— 每个 `_init_*` / `_start_*` 辅助函数都注明了它
"必须排在谁之后", 改动顺序前先读那一行注释。装配全部走具名步骤, 便于单点排查
"哪个服务没起来": 启动日志里每步都有对应的一行 INFO/WARNING。
"""
from __future__ import annotations

import logging
import os
import sys
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from app import __version__
from app.api import (
    abnormal,
    alerts,
    analysis,
    backtest,
    data,
    ext_data,
    external_page,  # [fork 增强] R117 外部网页抓取模式(独立模块)
    factors,
    financials,
    flip_paper,  # [fork 增强] R327 转折模拟盘
    focus,  # [fork 增强] R159 推送焦点名单
    indices,
    intraday,
    kline,
    lots,
    market_recap,
    mining,
    monitor_rules,
    overview,
    pipeline,
    regime,
    rps,
    screener,
    sector_rotation,
    signals,
    stock_analysis,
    strategy,
    today,  # [fork 增强] 今日总览
    usage_notes,  # [fork 增强] R93 使用观察笔记
    watchlist,
)
from app.api import auth as auth_api
from app.api import settings as settings_api
from app.api.routes import router as core_router
from app.config import settings
from app.enriched_generation import EnrichedGenerationUnavailableError
from app.extensions.loader import (
    configure_backend_extensions,
    current_extension_context,
    start_backend_extensions,
)
from app.jobs import daily_pipeline
from app.services.matrix_prewarm_owner import MatrixCachePrewarmOwner
from app.services.mining_process_lock import MiningProcessLock
from app.services.quote_service import QuoteService
from app.tickflow import client as tf_client
from app.tickflow.capabilities import CapabilityDenied
from app.tickflow.policy import detect_capabilities
from app.tickflow.repository import DataStore, KlineRepository

logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# 容器环境标记: 存在即认为跑在容器内, 用于判定 data_dir 是否为持久化挂载点。
_DOCKERENV_PATH = Path("/.dockerenv")

# 停机缺口自检的延迟秒数: 避开启动高峰, 又要在用户开始操作前跑完。
_INTEGRITY_CHECK_DELAY_SECONDS = 30.0
# matrix 缓存预热线程的退出等待上限 (秒)。
# 用 int 而非 5.0: 该值会经 %s 打进停机告警日志,整型渲染为 "5",
# 保持与重构前 "did not stop within 5 seconds" 的日志文本一致,
# 避免按该字符串做的日志检索/告警匹配失配。shutdown(timeout=5) 与 5.0 等价。
_MATRIX_PREWARM_SHUTDOWN_TIMEOUT = 5

# 追加文件日志: uvicorn (含 --reload 开发模式) 默认只有 StreamHandler, 同步/管道等
# 运行时日志仅出现在 dev 终端, 关掉或滚屏后即丢失, 排查「同步后日志没落」时无处可查。
# 落盘到 data/backend.log 与桌面版 (desktop.py:_setup_logging → desktop.log) 行为对齐,
# 事后可查。桌面版 (frozen) 已由 desktop.py 写 desktop.log, 此处跳过避免重复落盘。
# RotatingFileHandler 防止长期运行/频繁 reload 导致文件无限增长。
if not getattr(sys, "frozen", False):
    try:
        from logging.handlers import RotatingFileHandler

        _log_path = settings.data_dir / "backend.log"
        _log_path.parent.mkdir(parents=True, exist_ok=True)
        _file_handler = RotatingFileHandler(
            _log_path, maxBytes=10 * 1024 * 1024, backupCount=3,
            mode="a", encoding="utf-8", errors="replace",
        )
        _file_handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
        )
        logging.getLogger().addHandler(_file_handler)
    except Exception as _e:  # noqa: BLE001
        logger.warning("文件日志初始化失败, 仅输出到终端: %s", _e)


# ================================================================
# 启动步骤
# ================================================================


def _log_startup_banner() -> None:
    """打印版本与数据源模式; 免登录模式另外大字警告。"""
    logger.info(
        "牛来 v%s starting (mode=%s)",
        __version__, tf_client.current_mode(),
    )

    # [fork 增强] R82: 免登录模式的大字警告 — 让「谁都能进」这件事在日志里藏不住。
    if settings.auth_disabled:
        logger.warning(
            "=" * 72 + "\n"
            "!! AUTH_DISABLED=1 — 访问认证已完全关闭(免登录裸奔模式) !!\n"
            "!! 任何能连到本服务端口的人都可以: 读取明文 API key、清空数据、 !!\n"
            "!! 修改自选/策略/操盘手仓位。请确保前面另有访问控制(如 CF Access)。 !!\n"
            "!! 恢复认证: 删除 AUTH_DISABLED 环境变量后重启。 !!\n"
            + "=" * 72
        )


def _bootstrap_auth() -> None:
    """首次启动: 若配置了 AUTH_PASSWORD 环境变量且未设过密码, 用它初始化。

    公网部署免 SSH 端口转发; 已设过密码则不覆盖 (改密码走 UI)。
    """
    try:
        from app.services import auth as auth_service

        auth_service.bootstrap_from_env()
    except Exception as e:  # noqa: BLE001
        logger.warning("auth bootstrap failed: %s", e)


def _load_custom_factors(store: DataStore) -> None:
    """载入自定义/复合因子注册表 (P3); 单个失败只跳过该因子 (fail-隔离)。"""
    from app.factors.store import load_into_registry

    try:
        loaded_factors = load_into_registry(store.data_dir)
        if loaded_factors:
            logger.info("custom factors loaded: %s", len(loaded_factors))
    except Exception as exc:  # noqa: BLE001
        logger.warning("custom factors load failed: %s", exc)


def _init_mining_manager(app: FastAPI, store: DataStore):
    """恢复被中断的挖掘任务, 并把管理器挂到 app.state。"""
    from app.services.mining_manager import MiningJobManager

    mining_manager = MiningJobManager(store.data_dir)
    recovered = mining_manager.recover_interrupted()
    app.state.mining_manager = mining_manager
    if recovered:
        logger.warning("recovered %d interrupted mining runs", recovered)
    return mining_manager


def _prime_matrix_generation(repo: KlineRepository) -> None:
    """在接受回测请求前固定 managed generation, 避免首批并发 worker 各自创建版本。"""
    if not settings.backtest_matrix_disk_cache_enabled:
        return
    try:
        repo.get_matrix_data_generation("stock")
    except EnrichedGenerationUnavailableError as exc:
        logger.warning("enriched generation requires a full rebuild: %s", exc)


def _arm_indicators_warmup_flag(app: FastAPI, repo: KlineRepository) -> None:
    """指标异步预热标志: enriched 缓存在后台线程构建, 完成后置 True。"""
    app.state.indicators_ready = False
    repo._on_warmup_done = lambda: setattr(app.state, "indicators_ready", True)  # noqa: SLF001


def _load_custom_data_sources() -> None:
    """自定义数据源配置(可选): 失败只记录错误, 不影响 TickFlow 基准路径。"""
    try:
        from app.data_providers import custom as custom_sources

        custom_sources.load_all()
        logger.info("custom data sources loaded: %d", len(custom_sources.list_sources()))
    except Exception as e:  # noqa: BLE001
        logger.warning("custom data sources init failed: %s", e)


def _check_data_dir_persistence(app: FastAPI) -> None:
    """[fork 增强] 数据持久化自检。

    容器内 data_dir 不是挂载点 → 数据写在容器层, 重建容器(拉新镜像)会丢全部数据。
    数据页据此显示红色警告横幅。仅容器环境判定(/.dockerenv); bind mount 与
    named volume 都是挂载点。
    """
    app.state.data_dir_persistent = True
    try:
        if _DOCKERENV_PATH.exists():
            app.state.data_dir_persistent = os.path.ismount(str(settings.data_dir))
            if not app.state.data_dir_persistent:
                logger.warning(
                    "数据目录 %s 未挂载持久化卷! 容器重建将丢失全部数据 — "
                    "请在 compose 的 volumes 挂载该路径", settings.data_dir)
    except Exception as e:  # noqa: BLE001
        logger.debug("data dir persistence check skipped: %s", e)


def _init_quote_service(app: FastAPI, repo: KlineRepository) -> QuoteService:
    """全局行情服务。

    顺序是有原因的: QuoteService 需要访问 strategy_monitor 等单例, 所以先建
    quote_service (set_repo/boot_check), 再创建 strategy_monitor 挂 app.state,
    最后才 set_app_state 把整个 state 注入进去。
    """
    qs = QuoteService()
    app.state.quote_service = qs
    qs.set_repo(repo)
    qs.boot_check()

    from app.strategy.monitor import StrategyMonitorService

    strategy_monitor = StrategyMonitorService()
    app.state.strategy_monitor = strategy_monitor
    qs.set_app_state(app.state)
    return qs


def _init_depth_service(app: FastAPI, repo: KlineRepository):
    """五档盘口 sealed 服务(真假涨停/跌停, 独立旁路线)。"""
    from app.services.depth_service import DepthService

    depth_service = DepthService()
    depth_service.set_repo(repo)
    depth_service.set_app_state(app.state)
    app.state.depth_service = depth_service
    return depth_service


def _start_scheduler(app: FastAPI, repo: KlineRepository, capset) -> None:
    """启动调度器(若 enriched 数据为空, 首次启动可手动 POST /api/pipeline/run)。"""
    try:
        daily_pipeline.set_app_state(app.state)  # 供 depth_finalize job 访问 depth_service
        scheduler = daily_pipeline.start_scheduler(repo, capset)
        app.state.scheduler = scheduler
        # [R327] R61 那套「操盘手定时」删掉了 —— AI 操盘手整个换成了转折模拟盘,
        # 而后者是**纯函数**: 打开页面当场从日线重算, 没有需要每天推进的状态,
        # 也就没有可定时的东西。
    except Exception as e:  # noqa: BLE001
        logger.warning("scheduler not started: %s", e)
        app.state.scheduler = None


def _boot_depth_sealed(depth_service) -> None:
    """depth sealed: 启动补跑(当天文件不存在) + 盘中轮询(有能力时)。"""
    try:
        depth_service.boot_check()
        depth_service.start_polling()
    except Exception as e:  # noqa: BLE001
        logger.warning("depth_service init failed: %s", e)


def _start_minute_refresh(app: FastAPI, repo: KlineRepository) -> None:
    """盘中分钟增量刷新 (Expert 专有): 线程常驻, 开关/时段/能力门控在循环内每轮判断。"""
    try:
        from app.services.minute_refresh import MinuteRefreshService

        minute_refresh = MinuteRefreshService(repo)
        minute_refresh.set_app_state(app.state)
        app.state.minute_refresh = minute_refresh
        minute_refresh.start()
    except Exception as e:
        logger.warning("minute_refresh init failed: %s", e)


def _schedule_boot_integrity_check(app: FastAPI) -> None:
    """停机缺口自检: 延迟后台扫描。

    发现最近交易日的盘中快照/缺口时自动创建修复任务 (盘中停机→次日开实时场景,
    不修则坏数据被"只刷今天"分支永久留存)。
    """
    try:
        from app.services.data_integrity import boot_integrity_check

        timer = threading.Timer(
            _INTEGRITY_CHECK_DELAY_SECONDS, boot_integrity_check, args=(app.state,),
        )
        timer.daemon = True  # 不阻塞进程退出
        timer.start()
    except Exception as e:  # noqa: BLE001
        logger.warning("integrity boot check scheduling failed: %s", e)


def _init_wecom_bot(app: FastAPI) -> None:
    """企业微信智能机器人长连接(可选通道, 失败不阻断启动)。"""
    try:
        from app.services.wecom_bot_service import WecomBotService

        wecom_bot_service = WecomBotService()
        wecom_bot_service.set_app_state(app.state)
        app.state.wecom_bot_service = wecom_bot_service
        wecom_bot_service.boot_check()
    except Exception as e:  # noqa: BLE001
        logger.warning("wecom_bot_service init failed: %s", e)


async def _ensure_ext_presets(store: DataStore) -> None:
    """内置扩展表 (概念/行业): 先创建 config (含拉取配置), 默认开启定时拉取。

    必须在 pull_scheduler.refresh() 之前执行, 否则全新部署时 scheduler 读不到
    刚创建的预设, 定时任务不会启动。
    """
    try:
        from app.services.ext_presets import ensure_builtin_presets

        await ensure_builtin_presets(store.data_dir)
    except Exception as e:  # noqa: BLE001
        logger.warning("内置扩展表初始化失败 (不影响启动): %s", e)


def _start_pull_scheduler(app: FastAPI, store: DataStore) -> None:
    """扩展数据定时拉取: 在预设配置就绪后启动, 自动调度 enabled 的预设。"""
    from app.services.ext_pull import pull_scheduler

    pull_scheduler.start(store.data_dir)
    pull_scheduler.refresh(store.data_dir)
    app.state.pull_scheduler = pull_scheduler


def _start_financial_scheduler(app: FastAPI, store: DataStore, capset) -> None:
    """财务数据 (需 Expert 套餐): 仅初始化调度器供 /api/financials/sync/* 手动同步。

    不启动自动调度 —— 用户在「财务分析」页点「同步」手动拉取。
    """
    from app.services.financial_sync import financial_scheduler

    financial_scheduler.start(store.data_dir, capset)
    app.state.financial_scheduler = financial_scheduler


def _start_watchdog(app: FastAPI, repo: KlineRepository) -> None:
    """自愈看门狗: 探测 polars 闸与写锁, 僵死时退出交由 supervisor 拉起 (兜底层)。"""
    from app.watchdog import start_watchdog

    app.state.watchdog = start_watchdog(app.state, repo)


def _strategy_search_dirs(store: DataStore) -> list[Path]:
    """策略搜索路径: 内置 + 用户自定义 + AI 生成 + 复合。"""
    return [
        Path(__file__).resolve().parent / "strategy" / "builtin",
        store.data_dir / "strategies" / "custom",
        store.data_dir / "strategies" / "ai",
        store.data_dir / "strategies" / "composite",
    ]


def _init_strategy_engine(app: FastAPI, store: DataStore, repo: KlineRepository):
    """策略引擎 + 两个选股服务 (A 股 / ETF)。

    返回 `(strategy_engine, screener_svc, etf_screener_svc)`: 两个 screener 的
    历史窗口加载器随后要复用到监控引擎, 让声明 filter_history 的策略也能跑实时监控。

    [R325] 签名补上 `repo`: R318 并进来的那次拆分, 调用处写的是三个参数、定义只收
    两个 —— **应用一启动就 TypeError, 整个后端起不来**, 而 3900 条测试没有一条跑
    lifespan, 所以全绿。现在 `tests/test_main_lifespan_wiring.py` 逐个核对每一步
    的调用与定义的参数个数。
    """
    from app.services.screener import ScreenerService
    from app.strategy import config as strategy_config
    from app.strategy.engine import StrategyEngine

    screener_svc = ScreenerService(repo=repo)
    etf_screener_svc = ScreenerService(repo=repo, asset_type="etf")
    strategy_engine = StrategyEngine(
        strategy_dirs=_strategy_search_dirs(store),
        override_loader=lambda sid: strategy_config.load_override(store.data_dir, sid),
    )
    app.state.strategy_engine = strategy_engine
    logger.info("strategy engine loaded: %d strategies", len(strategy_engine.list_strategies()))
    return strategy_engine, screener_svc, etf_screener_svc


def _install_matrix_prewarm(repo: KlineRepository, strategy_engine) -> MatrixCachePrewarmOwner:
    """回测 matrix 缓存预热: 挂到 enriched 刷新完成回调上, 后台独占跑一次。"""
    owner = MatrixCachePrewarmOwner()

    def _schedule() -> None:
        if (
            not settings.backtest_matrix_disk_cache_enabled
            or not settings.backtest_matrix_cache_prewarm
        ):
            return

        def _prewarm() -> None:
            from app.backtest.engine import BacktestEngine
            from app.backtest.matrix import MatrixPrewarmCancelledError
            from app.backtest.strategy import prewarm_matrix_cache
            from app.services.heavy_job_limiter import (
                HeavyJobCancelledError,
                shared_heavy_job_limiter,
            )

            try:
                latest = repo.latest_enriched_date("stock")
                if latest is None:
                    logger.info("matrix cache prewarm skipped: no stock enriched data")
                    return

                with shared_heavy_job_limiter.slot(
                    "exclusive",
                    cancel_event=owner.cancel_event,
                ):
                    result = prewarm_matrix_cache(
                        BacktestEngine(repo),
                        strategy_engine,
                        asset_type="stock",
                        latest_date=latest,
                        years=settings.backtest_matrix_cache_prewarm_years,
                        cancel_event=owner.cancel_event,
                    )
                logger.info("matrix cache prewarm done: %s", result)
            except (HeavyJobCancelledError, MatrixPrewarmCancelledError):
                logger.info("matrix cache prewarm cancelled")
            except Exception:  # noqa: BLE001
                logger.exception("matrix cache prewarm failed")

        if not owner.schedule(_prewarm):
            logger.info("matrix cache prewarm already running or shutting down, skip")

    repo._on_refresh_done = _schedule  # noqa: SLF001
    if repo.enriched_ready:
        _schedule()
    return owner


def _init_monitor_engine(app: FastAPI, store: DataStore, repo: KlineRepository, strategy_engine,
                         screener_svc, etf_screener_svc) -> None:
    """通用监控规则引擎: 启动时 reload 规则到内存态 (修复重启后告警失效)。"""
    from app.services import preferences
    from app.services.sector_monitor import SectorMonitorService
    from app.strategy import monitor_rules as mr_store
    from app.strategy.monitor import MonitorRuleEngine

    monitor_engine = MonitorRuleEngine()
    sector_monitor_service = SectorMonitorService(repo)
    monitor_engine.set_strategy_engine(strategy_engine)
    monitor_engine.set_data_dir(store.data_dir)
    monitor_engine.set_sector_monitor_service(sector_monitor_service)
    # 复用 ScreenerService 的历史窗口加载器 (三级缓存, 启动预计算命中 ~0ms),
    # 让声明 filter_history 的策略 (如反包) 也能在实时监控里跑选股 → 盘中触发通知。
    monitor_engine.set_history_loader(screener_svc._load_enriched_history)
    # ETF 版历史加载器: asset_type=etf 的 strategy 型规则用 (读 kline_etf_enriched)。
    monitor_engine.set_history_loader_etf(etf_screener_svc._load_enriched_history)

    # 自动迁移: 把旧 strategy_monitor_ids 同步为 type=strategy 规则 (统一到监控页)
    try:
        if preferences.get_strategy_monitor_enabled():
            ids = preferences.get_strategy_monitor_ids()
            if ids:
                names = {s["id"]: s["name"] for s in strategy_engine.list_strategies()}
                mr_store.migrate_strategy_monitors(store.data_dir, ids, names)
                logger.info("strategy monitor migrated: %d strategies", len(ids))
    except Exception as e:  # noqa: BLE001
        logger.warning("strategy monitor migration failed: %s", e)

    try:
        rules = mr_store.load_all(store.data_dir)
        monitor_engine.set_rules(rules)
        logger.info("monitor engine loaded: %d rules", monitor_engine.rule_count)
    except Exception as e:  # noqa: BLE001
        logger.warning("monitor engine load failed: %s", e)
    app.state.monitor_engine = monitor_engine
    app.state.sector_monitor_service = sector_monitor_service


def _start_backend_extensions(app: FastAPI, store: DataStore, repo: KlineRepository) -> None:
    """源码内二次开发启动钩子: 仅暴露稳定只读上下文, 单个扩展失败不影响核心启动。"""
    start_backend_extensions(
        current_extension_context(data_dir=store.data_dir, repository=repo),
        app.state.extension_registry,
    )


async def _shutdown_services(app: FastAPI, repo: KlineRepository, matrix_prewarm_owner) -> None:
    """按启动的逆序停机。每步都容忍缺失 (某个服务没起来时不能拖住整个退出)。

    不变量(改动前务必读懂):

    1. **逆序**。本函数的执行顺序必须与 `_application_lifespan` 中的启动顺序
       相反,否则会出现"依赖方先死、被依赖方还在跑"的窗口。当前为:
       watchdog → matrix 预热 → 挖掘管理器 → 调度器 → pull_scheduler →
       financial_scheduler → quote_service → depth_service → wecom_bot_service →
       minute_refresh。新增服务时请同步在这里插到对应位置。
    2. **容错**。每个服务都走 `getattr(app.state, 名, None)` + 判空:服务没起来
       就跳过,绝不抛错。停机路径上抛异常会掩盖真正的退出原因。
    3. **每步独立**。不要在这里做跨服务的联动关闭,让每个服务自己负责自己的线程。
    """
    # 先摘掉 enriched 刷新回调,避免停机途中还有后台重算在改 repo 状态。
    repo._on_refresh_done = None  # noqa: SLF001

    watchdog = getattr(app.state, "watchdog", None)
    if watchdog:
        await watchdog.stop()

    if not matrix_prewarm_owner.shutdown(timeout=_MATRIX_PREWARM_SHUTDOWN_TIMEOUT):
        logger.warning(
            "matrix cache prewarm did not stop within %s seconds",
            _MATRIX_PREWARM_SHUTDOWN_TIMEOUT,
        )

    mining_manager = getattr(app.state, "mining_manager", None)
    if mining_manager:
        mining_manager.shutdown()
    if app.state.scheduler:
        app.state.scheduler.shutdown(wait=False)

    # 停机的"表格段":顺序即上面不变量 1 描述的逆序。
    # 想加新服务时,在元组里补一行 (app.state 上的属性名, 停止方法名) 即可。
    for attr, method in (
        ("pull_scheduler", "stop"),
        ("financial_scheduler", "stop"),
        ("quote_service", "stop"),
        ("depth_service", "stop_polling"),
        ("wecom_bot_service", "stop"),
        ("minute_refresh", "stop"),
    ):
        service = getattr(app.state, attr, None)
        if service:
            getattr(service, method)()

    logger.info("shutdown")


# ================================================================
# 生命周期
# ================================================================


@asynccontextmanager
async def _application_lifespan(app: FastAPI):
    # ── 阶段 0:日志与鉴权 ─────────────────────────────────────────
    # 必须最先。免登录模式的大字警告、"是否已设过密码"的判定都放在最前,
    # 这样后面任何一步抛错时,日志里已经能看出当前处于哪种鉴权模式。
    _log_startup_banner()
    _bootstrap_auth()

    # ── 阶段 1:数据层(唯一基座)──────────────────────────────────
    # 后续每一个服务都直接或间接依赖 store / repo,所以这两行必须排在全部
    # _init_* / _start_* 之前;引用同时挂到 app.state 供路由与后台任务取用。
    store = DataStore()
    repo = KlineRepository(store)
    app.state.datastore = store
    app.state.repo = repo

    # ── 阶段 2:数据层之上的初始化 ─────────────────────────────────
    # 只依赖 store / repo;彼此之间无顺序约束,但都在能力探测之前。
    _load_custom_factors(store)
    _init_mining_manager(app, store)
    _prime_matrix_generation(repo)
    _arm_indicators_warmup_flag(app, repo)
    # Polars 缓存预热 — enriched 的重计算 (107万行 compute_indicators) 推后台,
    # instruments/index/ETF 仍同步 (毫秒级)。应用立即 ready, 指标算完后自动替换。
    repo.refresh_cache(background=True)
    _load_custom_data_sources()
    _check_data_dir_persistence(app)

    # ── 阶段 3:能力探测 ───────────────────────────────────────────
    # 硬约束:必须晚于 _load_custom_data_sources()。自定义数据源先注册,
    # 能力探测才能把它的数据集能力补进 capset。
    capset = detect_capabilities()
    app.state.capabilities = capset
    logger.info("ready; %d capabilities active", len(capset.all()))

    # ── 阶段 4:独立后台服务(互不依赖,可任意顺序)────────────────
    # 这些服务只依赖 store / repo / capset,彼此之间没有先后关系;
    # 单独调换其中任意两行的顺序都不会改变行为。
    _init_quote_service(app, repo)
    depth_service = _init_depth_service(app, repo)
    _start_scheduler(app, repo, capset)
    _boot_depth_sealed(depth_service)
    _start_minute_refresh(app, repo)
    _schedule_boot_integrity_check(app)
    _init_wecom_bot(app)
    await _ensure_ext_presets(store)
    _start_pull_scheduler(app, store)
    _start_financial_scheduler(app, store, capset)
    _start_watchdog(app, repo)

    # ── 阶段 5:策略引擎 → matrix 预热 → 监控 → 二次开发 ────────────
    # 顺序有硬约束,不可重排:
    #   1) _init_strategy_engine 产出 screener 服务(A股 + ETF 两个实例);
    #   2) 监控引擎需要 screener 的 _load_enriched_history 作历史加载器,
    #      所以必须晚于第 1 步;
    #   3) matrix 预热要挂到 enriched 刷新完成回调上,故排在策略引擎之后;
    #   4) 二次开发钩子最后跑,它只拿稳定只读上下文,失败也不影响核心启动。
    strategy_engine, screener_svc, etf_screener_svc = _init_strategy_engine(app, store, repo)
    matrix_prewarm_owner = _install_matrix_prewarm(repo, strategy_engine)
    _init_monitor_engine(app, store, repo, strategy_engine, screener_svc, etf_screener_svc)
    _start_backend_extensions(app, store, repo)

    try:
        yield
    finally:
        await _shutdown_services(app, repo, matrix_prewarm_owner)


@asynccontextmanager
async def lifespan(app: FastAPI):
    mining_process_lock = MiningProcessLock(settings.data_dir)
    mining_process_lock.acquire()
    try:
        async with _application_lifespan(app):
            yield
    finally:
        mining_process_lock.release()


app = FastAPI(
    title="牛来",
    version=__version__,
    description="A 股选股 + 回测面板 — TickFlow 适配",
    lifespan=lifespan,
)

# CORS: 允许局域网访问 (自托管场景, 放开所有来源)
# 注: allow_credentials=True 与 allow_origins=['*'] 不能共存 (浏览器规范),
# 本项目认证走 header (API Key), 不依赖 cookie, 故关闭 credentials 换取通配来源。
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ================================================================
# 访问认证中间件
# ================================================================
# 拦截所有 /api/ 请求, 三种状态:
#   1. 未设密码 + 本机/内网 → 放行(让本机用户访问面板 + 调 /api/auth/setup 设密码)
#   2. 未设密码 + 公网       → 拒绝(403, 防裸奔也防抢占; 引导本机设密码)
#   3. 已设密码              → 检查 session, 无效则 401(前端跳登录)
# 白名单: /api/auth/* (设密码/登录本身)、/health 等探活。
_AUTH_WHITELIST_PREFIX = ("/api/auth/",)
# [fork R367] `"/api/health"` 从这里删掉了 —— **那个端点根本不存在**。
# 探活的真实路径只有 `/health`(`app/api/routes.py` 里的 `@router.get("/health")`,
# 而 `core_router` 是不带 prefix 挂上去的), Dockerfile 的 healthcheck 打的也是它。
#
# 白名单里多一条不存在的路径**不会报任何错**, 它只是永远不会被命中 —— 而它会
# 骗人: 排查线上问题时照着这里去开 `/api/health`, 拿到的是 SPA 兜底的 index.html,
# 于是把"端点不存在"误读成"路由没配上", 往完全错的方向查。这次就是这么栽的。
_AUTH_WHITELIST_EXACT = ("/health", "/openapi.json", "/docs", "/redoc")


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path
    # 仅 /api/ 走认证; 静态资源(前端页面/assets)放行, 由前端处理跳转
    if not path.startswith("/api/"):
        return await call_next(request)
    # [fork 增强] R82: AUTH_DISABLED=1 → 免登录全放行(公网也放)。风险自负, 启动日志有大字警告。
    if settings.auth_disabled:
        return await call_next(request)
    # 白名单放行(设密码/登录/探活本身不拦)
    if path.startswith(_AUTH_WHITELIST_PREFIX) or path in _AUTH_WHITELIST_EXACT:
        return await call_next(request)

    from app.services import auth as auth_service

    # 情况 1+2: 未设密码
    if not auth_service.is_configured():
        # 本机/内网 → 放行(服务器主人可访问, 并去 /login 设密码)
        if auth_api._is_local_network(auth_api._client_ip(request)):
            return await call_next(request)
        # 公网 → 拒绝。不裸奔, 也不给公网设密码的机会(防抢占)
        return JSONResponse(
            status_code=403,
            content={
                "detail": "面板尚未初始化访问密码,请通过 SSH/本机浏览器访问以设置密码",
                "code": "NOT_INITIALIZED",
            },
        )

    # 情况 3: 已设密码, 检查会话
    token = request.cookies.get(auth_api.COOKIE_NAME)
    if token and auth_service.is_valid_session(token):
        return await call_next(request)
    # 未登录: 401(前端跳登录页)
    return JSONResponse(status_code=401, content={"detail": "未登录或会话已过期"})


def _register_routers(app: FastAPI) -> None:
    """注册全部路由。顺序不代表优先级, 但 `/health` 等核心路由在最前。

    ([fork R367] 这句原本写的是 `/api/health` —— 同样是个不存在的路径, 与上面
    白名单那条是同一个笔误的两处落点。)
    """
    app.include_router(core_router)
    app.include_router(auth_api.router)
    app.include_router(kline.router)
    app.include_router(watchlist.router)
    app.include_router(screener.router)
    app.include_router(backtest.router)
    app.include_router(factors.router)
    app.include_router(mining.router)
    app.include_router(flip_paper.router)  # [fork 增强] R327 转折模拟盘
    app.include_router(intraday.router)
    app.include_router(indices.router)
    app.include_router(overview.router)
    app.include_router(today.router)  # [fork 增强] 今日总览
    app.include_router(usage_notes.router)  # [fork 增强] R93 使用观察笔记
    app.include_router(focus.router)  # [fork 增强] R159 推送焦点名单
    app.include_router(external_page.router)  # [fork 增强] R117 外部网页抓取模式
    app.include_router(abnormal.router)
    app.include_router(regime.router)
    app.include_router(analysis.router)
    app.include_router(pipeline.router)
    app.include_router(data.router)
    app.include_router(ext_data.router)
    app.include_router(financials.router)
    app.include_router(stock_analysis.router)
    app.include_router(market_recap.router)
    app.include_router(settings_api.router)
    app.include_router(strategy.router)
    app.include_router(signals.router)
    app.include_router(monitor_rules.router)
    app.include_router(lots.router)
    app.include_router(alerts.router)
    app.include_router(rps.router)
    # [R326 同步上游] v0.2.4 新增: 盘中板块轮动监控。上游那版是**裸调用**,
    # 这里跟着 R318 的规矩进函数体 —— 路由注册只此一处, 不再有第二个注册点。
    app.include_router(sector_rotation.router)


_register_routers(app)

# 二次开发路由与小粒度策略在所有核心路由后注册, 禁止覆盖核心路径。
extension_registry, extension_load_errors = configure_backend_extensions(app)
app.state.extension_registry = extension_registry
app.state.extension_load_errors = extension_load_errors


# 能力门控异常 → 403(而非默认 500)
# 业务代码用 capset.require(Cap.X) 断言能力, 缺失时抛 CapabilityDenied;
# 若不注册 handler 会冒泡成 500 Internal Server Error, 对前端不友好且语义错误。
@app.exception_handler(CapabilityDenied)
async def capability_denied_handler(request: Request, exc: CapabilityDenied) -> JSONResponse:
    return JSONResponse(
        status_code=403,
        content={"detail": str(exc), "suggestion": exc.suggestion},
    )


# [R327] R68 那个「操盘手账本读不出来 → 503 而且不写」的 handler 删掉了。
# 它守的是一条具体的路: 账本读失败时若按空账本继续跑, 下一次保存会把其他
# 操作员覆盖掉。**转折模拟盘不落盘**(每次请求当场重算), 没有账本, 也就没有
# 这条路 —— 留着一个引用已删模块的 handler 只会让 import 炸掉。


# 生产期静态文件(前端 dist)
_static = Path(settings.static_dir)
if _static.exists():
    if (_static / "assets").exists():
        # [fork R153] 带 hash 的产物: 一年 immutable 缓存 + 构建期预压缩直出。
        # 见 app/static_assets.py。API 路径不受影响。
        from app.static_assets import HashedAssets

        app.mount("/assets", HashedAssets(directory=_static / "assets"), name="assets")

    # [fork R366] dist **根目录**下那几个真文件要按原样发出去, 不能落进下面的
    # SPA 兜底。
    #
    # `/assets/**` 有自己的挂载, 而 `sw.js` / `manifest.webmanifest` / 那几个
    # 图标 / `favicon.svg` 都在 dist 根 —— 它们原本会被兜底回一份 index.html,
    # 于是:
    #
    #   · `navigator.serviceWorker.register('/sw.js')` 拿到 text/html, 注册失败
    #   · `/manifest.webmanifest` 解析失败 → **整个"添加到主屏"就没了**
    #   · 图标全是 HTML
    #
    # 而这一串**一个错都不会报到眼前**: 页面照常打开, 只是装不成 app。
    # (favicon 其实早就在吃这个亏, 只是浏览器悄悄退回默认图标, 没人注意。)
    _root_static = _static.resolve()

    def _serve_root_file(rel: str) -> FileResponse | None:
        """dist 根目录下的真文件 —— 没有就返回 None, 交给 SPA 兜底。"""
        if not rel or rel.startswith("/") or "\\" in rel:
            return None
        try:
            target = (_root_static / rel).resolve()
            target.relative_to(_root_static)      # 越界(../)直接不认
        except (ValueError, OSError):
            return None
        # index.html 仍然走兜底那条路 —— 它的缓存头是特意设的
        if not target.is_file() or target.name == "index.html":
            return None
        # **sw.js 不许被缓存住**: 它自己就是更新机制, 缓存住等于把旧逻辑钉死。
        cache = ("no-cache" if target.name == "sw.js"
                 else "public, max-age=3600")
        return FileResponse(target, headers={"Cache-Control": cache})

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa_fallback(full_path: str):
        """dist 根目录下的真文件按原样发; 其余回退到 index.html — React Router 接管。

        index.html 禁止缓存 (Cache-Control: no-store), 确保浏览器每次拿到
        最新版本引用的 JS/CSS 文件名 (assets 带 hash, 可长缓存)。
        """
        hit = _serve_root_file(full_path)
        if hit is not None:
            return hit
        index = _static / "index.html"
        if index.exists():
            return FileResponse(
                index,
                headers={"Cache-Control": "no-store, must-revalidate"},
            )
        return {"error": "frontend not built"}
