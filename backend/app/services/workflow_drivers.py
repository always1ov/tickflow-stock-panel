"""[fork 增强] R39 工作流执行器 —— 真正去跑挖掘 / 跑回测的那一层。

``workflow.py`` 只有状态机和账本, 一格一格往前推;真正"这一格该干什么"由这里
的 driver 决定。分开是为了单测: 测状态机不需要真跑一次回测, 测 driver 时
状态机是现成的。

两个 driver 都遵守同一个约定 —— ``async advance(wf) -> dict``, 返回:
  {"action": "running"}                      本格没跑完, 等下一拍
  {"action": "round_done", "best": {...}}    跑完一轮
  {"action": "attempt_done", "best": {...},  这次重开结束(用满轮数或 AI 说够了)
   "outcome": "...", "detail": {...}}
  {"action": "error", "message": "..."}      这一格出错, 由上层记连击

两个 driver 走的都是手动路径同一批入口(挖掘走 step, 回测走 run_worker_task),
所以工作流跑出来的东西和手动跑出来的是同一套口径, 没有第二套实现。
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, timedelta
from typing import Any

logger = logging.getLogger(__name__)

# 回测单轮的墙钟上限。卡住的一轮不该拖死整个工作流。
BACKTEST_ROUND_TIMEOUT_S = 30 * 60


class MiningDriver:
    """挖掘工作流: 一次"重开"= 一个自动挖掘会话, 会话收工就换一批配置再开一个。"""

    kind = "mining"

    def __init__(self, *, manager: Any, repo: Any, app_state: Any) -> None:
        self._manager = manager
        self._repo = repo
        self._app_state = app_state

    async def advance(self, wf: dict) -> dict:
        from app.api.mining import advance_autopilot_session, build_autopilot_session
        from app.services import mining_autopilot_store

        cfg = wf.get("config") or {}
        cur = wf.get("current") or {}
        sid = cur.get("session_id")

        # 还没开会话 → 开一个(这就是一次"重开")
        if not sid:
            from app.services import workflow

            session = build_autopilot_session(
                repo=self._repo,
                asset_type=str(cfg.get("asset_type") or "stock"),
                start=_as_date(cfg.get("start")), end=_as_date(cfg.get("end")),
                holdout_days=int(cfg.get("holdout_days") or 365),
                budget_profile=str(cfg.get("budget_profile") or "balanced"),
                max_iterations=int((wf.get("budget") or {}).get("rounds_per_attempt") or 6),
                factor_names=cfg.get("factor_names") or [])
            workflow.note_attempt_start(wf, {"session_id": session["session_id"]})
            return {"action": "running"}

        session = mining_autopilot_store.get(str(sid))
        if session is None:
            return {"action": "error", "message": f"会话 {sid} 不见了"}

        out = await advance_autopilot_session(
            session, manager=self._manager, repo=self._repo, app_state=self._app_state)
        action, updated = out.get("action"), out.get("session") or session

        if action == "running":
            return {"action": "running"}
        if action == "iterated":
            return {"action": "round_done"}

        # done / error → 这次重开结束
        return {
            "action": "attempt_done",
            "best": _mining_best(updated),
            "outcome": str(updated.get("status") or action),
            "detail": {"session_id": str(sid), "message": out.get("message")},
        }


class BacktestDriver:
    """回测工作流: 一次"重开"= 一串轮次, 每轮 AI 填一次表、真跑一次回测。

    "AI 自动选按钮选项 + 一键跑"就落在这里 —— 它动的是回测页上那几个下拉框和
    输入框(策略/环境过滤/持仓上限/总仓位/区间/持仓天数/分钱方式), 跑的是
    ``/strategy/run`` 背后同一个 worker, 不是另开一套。
    """

    kind = "backtest"

    def __init__(self, *, engine: Any, data_dir: Any) -> None:
        self._engine = engine
        self._data_dir = data_dir

    def _strategies(self, asset_type: str) -> list[dict]:
        return [
            {"id": str(m["id"]), "name": str(m.get("name") or m["id"]),
             "desc": str(m.get("description") or "")[:120]}
            for m in self._engine.list_strategies()
            if not m.get("research_only") and asset_type in (m.get("asset_types") or ["stock"])
        ]

    async def advance(self, wf: dict) -> dict:
        from app.services import backtest_autopilot as bp
        from app.services import workflow

        cfg = wf.get("config") or {}
        asset_type = str(cfg.get("asset_type") or "stock")
        max_rounds = int((wf.get("budget") or {}).get("rounds_per_attempt") or 6)

        if not wf.get("current"):
            workflow.note_attempt_start(wf, {"rounds": []})
        cur = wf["current"]
        rounds: list[dict] = cur.setdefault("rounds", [])

        strategies = self._strategies(asset_type)
        if not strategies:
            return {"action": "error", "message": "没有可用策略"}

        plan = await bp.next_plan(strategies=strategies, rounds=rounds, max_rounds=max_rounds)
        if plan.get("error"):
            return {"action": "error", "message": str(plan["error"])}

        if plan.get("satisfied"):
            return {
                "action": "attempt_done",
                "best": _backtest_best(bp.best_round(rounds)),
                "outcome": "satisfied",
                "detail": {"rounds": len(rounds),
                           "conclusion": plan.get("conclusion") or plan.get("note")},
            }
        nxt = plan.get("next")
        if not nxt:
            return {"action": "error", "message": "AI 没给出下一轮配置"}

        # 真跑一轮 —— 阻塞的活挪去线程, 别把事件循环钉住
        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(self._run_once, nxt, cfg),
                timeout=BACKTEST_ROUND_TIMEOUT_S)
        except asyncio.TimeoutError:
            return {"action": "error", "message": f"这一轮回测超过 {BACKTEST_ROUND_TIMEOUT_S // 60} 分钟没跑完"}

        digest = bp.digest_result(result)
        entry = {
            "round": len(rounds) + 1, "config": dict(nxt), "digest": digest,
            "passed": bp.meets_bar(digest), "note": plan.get("note"),
        }
        rounds.append(entry)

        if bp.stop_reason(rounds, max_rounds):
            return {
                "action": "attempt_done",
                "best": _backtest_best(bp.best_round(rounds)),
                "outcome": "exhausted",
                "detail": {"rounds": len(rounds)},
            }
        return {"action": "round_done", "best": _backtest_best(entry)}

    def _run_once(self, plan: dict, cfg: dict) -> dict:
        """把 AI 给的配置灌进真正的回测入口。同步阻塞, 由调用方挪到线程里。"""
        from app.backtest.strategy import StrategyBacktestConfig
        from app.backtest.worker import make_worker_task, run_worker_task
        from app.services.heavy_job_limiter import shared_heavy_job_limiter

        end = _as_date(cfg.get("end")) or date.today()
        start = end - timedelta(days=int(plan.get("days") or 730))
        symbols = cfg.get("symbols") or None
        bt = StrategyBacktestConfig(
            strategy_id=str(plan["strategy_id"]),
            symbols=list(symbols) if symbols else None,
            start=start, end=end,
            asset_type=str(cfg.get("asset_type") or "stock"),
            # 账户事实由用户在页面上定, AI 碰不到 —— 工作流原样透传
            commission_pct=float(cfg.get("commission_pct") or 0.0002),
            stamp_tax_pct=float(cfg.get("stamp_tax_pct") or 0.0005),
            slippage_bps=float(cfg.get("slippage_bps") or 5.0),
            initial_capital=float(cfg.get("initial_capital") or 1_000_000),
            matching=str(cfg.get("matching") or "next_open"),
            max_positions=int(plan.get("max_positions") or 10),
            max_exposure_pct=float(plan.get("max_exposure_pct") or 100) / 100,
            position_sizing=str(plan.get("position_sizing") or "equal"),
            holding_days=int(plan.get("holding_days") or 5),
            regime_filter=({"states": plan["regime_states"]}
                           if plan.get("regime_states") else None),
        )
        task = make_worker_task("backtest", self._data_dir, bt)
        with shared_heavy_job_limiter.slot("normal"):
            return run_worker_task(task, lambda _d: None, None)


# ---------- 结果归一 ----------

def _num(v: Any) -> float | None:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _mining_best(session: dict) -> dict | None:
    """挖掘会话的赢家 → 工作流通用的成绩单形状。"""
    w = session.get("winner")
    if not w:
        return None
    return {
        "passed": bool(w.get("达标")),
        "sharpe": _num(w.get("样本外Sharpe")),
        "label": str(w.get("name") or w.get("signature") or "候选"),
        "kind": "mining",
        "run_id": w.get("run_id"),
        "signature": w.get("signature"),
        "session_id": session.get("session_id"),
        "detail": {k: w.get(k) for k in ("最大回撤", "成交笔数", "正收益折占比")},
    }


def _backtest_best(entry: dict | None) -> dict | None:
    if not entry:
        return None
    d = entry.get("digest") or {}
    cfg = entry.get("config") or {}
    return {
        "passed": bool(entry.get("passed")),
        "sharpe": _num(d.get("夏普")),
        "label": str(cfg.get("strategy_id") or "策略"),
        "kind": "backtest",
        "config": cfg,
        "detail": {k: d.get(k) for k in ("总收益", "年化", "最大回撤", "胜率", "交易数")},
    }


def _as_date(v: Any) -> date | None:
    if isinstance(v, date):
        return v
    if not v:
        return None
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


def build_drivers(app_state: Any) -> dict[str, Any]:
    """按当前进程里已经装好的部件组一套 driver。缺件的那种就不提供 —— 上层会
    把对应工作流以"没有执行器"收掉, 而不是每一拍都炸一次。"""
    from app.config import settings

    drivers: dict[str, Any] = {}
    manager = getattr(app_state, "mining_manager", None)
    repo = getattr(app_state, "repo", None)
    if manager is not None and repo is not None:
        drivers["mining"] = MiningDriver(manager=manager, repo=repo, app_state=app_state)
    engine = getattr(app_state, "strategy_engine", None)
    if engine is not None:
        drivers["backtest"] = BacktestDriver(engine=engine, data_dir=settings.data_dir)
    return drivers
