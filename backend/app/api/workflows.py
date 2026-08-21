"""[fork 增强] R39 研究工作流 HTTP API。

一键开一个会自己跑的工作流(挖掘 or 回测), 之后不用管它 —— 关页面照跑。
手动路径完全没动: 这里只是又一个调用方, 走的是同一批 step / run 入口。
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Annotated, Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from app.services import workflow

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/workflows", tags=["workflows"])


class WorkflowCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["mining", "backtest"]
    config: dict[str, Any] = Field(default_factory=dict)
    max_attempts: int = Field(workflow.DEFAULT_MAX_ATTEMPTS, ge=1, le=workflow.MAX_ATTEMPTS_CAP)
    rounds_per_attempt: int = Field(workflow.DEFAULT_ROUNDS_PER_ATTEMPT, ge=1,
                                    le=workflow.MAX_ROUNDS_CAP)
    max_hours: float = Field(workflow.DEFAULT_MAX_HOURS, gt=0, le=workflow.MAX_HOURS_CAP)


def _project(wf: dict) -> dict:
    """给前端的投影: 附上一行进度文案, 省得每个界面各算一遍。"""
    return dict(wf, progress_text=workflow.progress_text(wf))


@router.get("")
def list_workflows(
    kind: Annotated[Literal["mining", "backtest"] | None, Query()] = None,
) -> dict[str, Any]:
    items = workflow.list_workflows()
    if kind:
        items = [w for w in items if w.get("kind") == kind]
    return {"items": [_project(w) for w in items]}


@router.get("/{workflow_id}")
def get_workflow(workflow_id: str) -> dict[str, Any]:
    wf = workflow.get(workflow_id)
    if wf is None:
        raise HTTPException(status_code=404, detail="工作流不存在")
    return _project(wf)


@router.post("")
def create_workflow(payload: WorkflowCreateRequest, request: Request) -> dict[str, Any]:
    """开一个工作流。挖掘的窗口切分与数据预检在这里就做掉 —— 建的时候就该知道
    数据够不够, 而不是让它在后台默默失败三次才告诉你。"""
    config = dict(payload.config)
    if payload.kind == "mining":
        _preflight_mining(config, request)
    else:
        _preflight_backtest(config, request)

    wf = workflow.create(kind=payload.kind, config=config, budget={
        "max_attempts": payload.max_attempts,
        "rounds_per_attempt": payload.rounds_per_attempt,
        "max_hours": payload.max_hours,
    })
    return _project(wf)


@router.post("/{workflow_id}/stop")
def stop_workflow(workflow_id: str) -> dict[str, Any]:
    wf = workflow.stop(workflow_id)
    if wf is None:
        raise HTTPException(status_code=404, detail="工作流不存在")
    return _project(wf)


@router.post("/{workflow_id}/tick")
async def tick_workflow(workflow_id: str, request: Request) -> dict[str, Any]:
    """手动催一格。后台节拍器本来就会推, 这个入口是给"我现在就想看它动一下"用的,
    也让工作流在节拍器没起来的环境里仍然可用。"""
    from app.services import workflow_drivers

    wf = workflow.get(workflow_id)
    if wf is None:
        raise HTTPException(status_code=404, detail="工作流不存在")
    updated = await workflow.tick(wf, drivers=workflow_drivers.build_drivers(request.app.state))
    return _project(updated)


def _preflight_mining(config: dict, request: Request) -> None:
    from app.api.mining import build_autopilot_session
    from app.services import mining_autopilot_store

    # [R53] 另一半闸: 手动会话还开着时不给起工作流。挖掘一次只跑得动一路
    # (heavy_job_limiter 容量 2, 一个挖掘 run 独占两格) —— 起了也是排队,
    # 而且工作流会以为自己那一轮跑得特别慢。开会话那一侧的对称检查在
    # api/mining.py 的 _reject_if_workflow_owns_mining。
    open_manual = [s for s in mining_autopilot_store.list_sessions()
                   if s.get("status") == "open" and not s.get("owner_workflow_id")]
    if open_manual:
        raise HTTPException(
            status_code=409,
            detail=(f"你还有一个手动的自动挖掘会话开着({open_manual[0]['session_id']})。"
                    "挖掘一次只跑得动一路, 现在起工作流只会让两边互相排队。"
                    "把那个会话中止(或等它收工)再开工作流。"))

    start, end = _dates(config)
    try:
        # 真开一个会话当预检 —— 开得出来就说明数据够。开出来的这个直接交给
        # 第一次重开用, 不浪费。
        session = build_autopilot_session(
            repo=request.app.state.repo,
            asset_type=str(config.get("asset_type") or "stock"),
            start=start, end=end,
            holdout_days=int(config.get("holdout_days") or 365),
            budget_profile=str(config.get("budget_profile") or "balanced"),
            max_iterations=int(config.get("rounds_per_attempt") or 6),
            factor_names=config.get("factor_names") or [])
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"开不了挖掘会话: {exc}") from exc
    # 预检建出来的会话不留给工作流用(工作流第一拍会自己开), 这里删掉免得留孤儿
    mining_autopilot_store.set_status(session["session_id"], "stopped",
                                      fail_reason="仅用于建工作流时的数据预检")
    config["start"], config["end"] = str(start), str(end)


def _preflight_backtest(config: dict, request: Request) -> None:
    engine = getattr(request.app.state, "strategy_engine", None)
    if engine is None:
        raise HTTPException(status_code=503, detail="策略引擎未初始化")
    asset_type = str(config.get("asset_type") or "stock")
    usable = [m for m in engine.list_strategies()
              if not m.get("research_only")
              and asset_type in (m.get("asset_types") or ["stock"])]
    if not usable:
        raise HTTPException(status_code=400, detail=f"{asset_type} 没有可用策略")
    _, end = _dates(config)
    config["end"] = str(end)


def _dates(config: dict) -> tuple[date, date]:
    def parse(key: str, default: date) -> date:
        v = config.get(key)
        if not v:
            return default
        try:
            return date.fromisoformat(str(v)[:10])
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"{key} 不是合法日期") from exc

    end = parse("end", date.today())
    # 默认往前五年。用 timedelta 而不是换年份 —— 2 月 29 日换年份会直接抛 ValueError
    start = parse("start", end - timedelta(days=365 * 5))
    if start >= end:
        raise HTTPException(status_code=400, detail="开始日期要早于结束日期")
    return start, end
