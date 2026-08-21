"""Persistent factor and strategy mining HTTP API."""
from __future__ import annotations

import asyncio
import json
import math
from collections.abc import AsyncIterator, Mapping, Sequence
from datetime import date
from typing import Annotated, Any, Literal

import polars as pl
from fastapi import APIRouter, Header, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sse_starlette.sse import EventSourceResponse

from app.backtest.factor import FACTOR_COLUMNS
from app.backtest.mining import (
    MAX_BEAM_WIDTH,
    MAX_COMBINATION_SIZE,
    MAX_FINALISTS,
    evaluate_candidate_gate,
)
from app.services import preferences
from app.services.mining_jobs import (
    ACTIVE_RUN_STATUSES,
    RUN_STATUSES,
    SUCCESS_RUN_STATUSES,
    TERMINAL_RUN_STATUSES,
    MiningRunStore,
    MiningRunStoreError,
    MiningRunValidationError,
)
from app.services import mining_autopilot, mining_autopilot_store
from app.services.mining_preflight import (
    mining_availability,
    require_mining_availability,
)
from app.services.mining_schedule import (
    MINING_ALGORITHM_VERSION,
    build_data_fingerprint,
)

router = APIRouter(prefix="/api/backtest/mining", tags=["backtest"])
_FACTOR_IDS = frozenset(str(item["id"]) for item in FACTOR_COLUMNS)
_MAX_ARTIFACT_BYTES = 64 * 1024 * 1024
_SSE_POLL_SECONDS = 0.5
_SSE_HEARTBEAT_SECONDS = 15.0


class MiningStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    factor_names: list[str] = Field(min_length=1, max_length=48)
    strategy_ids: list[str] = Field(default_factory=list, max_length=8)
    symbols: list[str] | None = None
    asset_type: Literal["stock", "etf"] = "stock"
    start: date | None = None
    end: date | None = None
    budget_profile: Literal["exploratory", "balanced", "strict"] = "balanced"
    commission_pct: float = Field(0.0002, ge=0.0, le=0.05, allow_inf_nan=False)
    stamp_tax_pct: float = Field(0.0005, ge=0.0, le=0.05, allow_inf_nan=False)
    slippage_bps: float = Field(5.0, ge=0.0, le=1000.0, allow_inf_nan=False)
    correlation_threshold: float = Field(0.75, gt=0.0, le=1.0, allow_inf_nan=False)
    max_combination_factors: int = Field(4, ge=1, le=MAX_COMBINATION_SIZE)
    beam_width: int = Field(12, ge=1, le=MAX_BEAM_WIDTH)
    max_finalists: int = Field(MAX_FINALISTS, ge=1, le=MAX_FINALISTS)
    force: bool = False

    @field_validator("start", "end", mode="before")
    @classmethod
    def _iso_dates(cls, value: Any) -> Any:
        if isinstance(value, str):
            try:
                return date.fromisoformat(value)
            except ValueError as exc:
                raise ValueError("dates must use ISO YYYY-MM-DD format") from exc
        return value

    @field_validator("factor_names", "strategy_ids")
    @classmethod
    def _unique_ids(cls, values: list[str]) -> list[str]:
        if any(not value or len(value) > 120 for value in values):
            raise ValueError("IDs must contain 1 to 120 characters")
        if len(set(values)) != len(values):
            raise ValueError("IDs must be unique")
        return values

    @field_validator("factor_names")
    @classmethod
    def _known_factors(cls, values: list[str]) -> list[str]:
        unknown = sorted(set(values) - _FACTOR_IDS)
        if unknown:
            raise ValueError(f"unknown mining factors: {unknown}")
        return values

    @field_validator("symbols")
    @classmethod
    def _symbols(cls, values: list[str] | None) -> list[str] | None:
        if values is None:
            return None
        cleaned = [value for value in values if value]
        if len(cleaned) > 10_000:
            raise ValueError("symbols contains more than 10000 entries")
        if len(set(cleaned)) != len(cleaned):
            raise ValueError("symbols must be unique")
        return cleaned or None

    @model_validator(mode="after")
    def _date_range(self) -> MiningStartRequest:
        if self.start is not None and self.end is not None and self.start > self.end:
            raise ValueError("start must not be after end")
        return self


class MiningSchedulePatch(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    mining_schedule_enabled: bool | None = None
    mining_schedule_weekday: int | None = Field(None, ge=0, le=4)
    mining_budget_profile: Literal["balanced", "strict"] | None = None


@router.get("/availability")
def get_availability(
    request: Request,
    asset_type: Annotated[Literal["stock", "etf"], Query()] = "stock",
    budget_profile: Annotated[
        Literal["exploratory", "balanced", "strict"], Query()
    ] = "balanced",
    start: Annotated[date | None, Query()] = None,
    end: Annotated[date | None, Query()] = None,
) -> dict[str, Any]:
    try:
        return mining_availability(
            request.app.state.repo.store.data_dir,
            asset_type=asset_type,
            budget_profile=budget_profile,
            start=start,
            end=end,
        ).to_dict()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/runs")
def list_runs(
    request: Request,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    status: Annotated[list[str] | None, Query()] = None,
) -> dict[str, Any]:
    manager = _manager(request)
    statuses = None
    if status:
        unknown = sorted(set(status) - RUN_STATUSES)
        if unknown:
            raise HTTPException(status_code=400, detail=f"unsupported mining statuses: {unknown}")
        statuses = status
    try:
        manifests = manager.store.list_runs(limit=limit, statuses=statuses)
        return {"items": [_project_run(manager.store, item) for item in manifests]}
    except MiningRunValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except MiningRunStoreError as exc:
        raise HTTPException(status_code=500, detail="failed to read mining runs") from exc


@router.post("/runs")
def start_run(payload: MiningStartRequest, request: Request) -> dict[str, Any]:
    manager = _manager(request)
    worker_request = payload.model_dump(mode="json", exclude={"force"})
    try:
        _validate_selected_strategies(
            request.app.state.strategy_engine,
            payload.strategy_ids,
            payload.asset_type,
        )
        require_mining_availability(
            request.app.state.repo.store.data_dir,
            asset_type=payload.asset_type,
            budget_profile=payload.budget_profile,
            start=payload.start,
            end=payload.end,
        )
        fingerprint = build_data_fingerprint(
            request.app.state.repo,
            request.app.state,
            worker_request,
        )
        existing = None
        if not payload.force:
            from app.services.mining_jobs import (
                ACTIVE_RUN_STATUSES,
                SUCCESS_RUN_STATUSES,
                compute_run_signature,
            )

            signature = compute_run_signature(worker_request, fingerprint)
            existing = manager.store.find_by_signature(
                signature,
                statuses=ACTIVE_RUN_STATUSES | SUCCESS_RUN_STATUSES,
            )
        manifest = manager.start(
            worker_request,
            fingerprint,
            force=payload.force,
            source="manual",
        )
        projected = _project_run(manager.store, manifest)
        projected["reused"] = existing is not None
        return projected
    except (MiningRunValidationError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except MiningRunStoreError as exc:
        raise HTTPException(status_code=500, detail="failed to persist mining run") from exc


@router.get("/runs/{run_id}")
def get_run(run_id: str, request: Request) -> dict[str, Any]:
    store = _manager(request).store
    return _project_run(store, _required_manifest(store, run_id))


@router.post("/runs/{run_id}/cancel")
def cancel_run(run_id: str, request: Request) -> dict[str, Any]:
    manager = _manager(request)
    try:
        return _project_run(manager.store, manager.cancel(run_id))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="mining run not found") from exc
    except MiningRunValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def load_run_result(store: MiningRunStore, run_id: str) -> dict[str, Any] | None:
    """[R39] 读一个已成功 run 的完整结果; 读不到返回 None。

    与 ``get_result`` 同一套读法, 但不抛 HTTP 异常 —— 后台工作流不在请求上下文里,
    拿 HTTPException 当控制流会把它自己也带崩。
    """
    manifest = store.get(run_id)
    if manifest is None or str(manifest["status"]) not in SUCCESS_RUN_STATUSES:
        return None
    try:
        summary = store.read_summary(run_id)
        frames = {
            name: _read_registered_artifact(store, manifest, name)
            for name in ("factors", "correlation", "candidates", "folds")
        }
        return _project_result(manifest, summary, frames)
    except (MiningRunStoreError, OSError, pl.exceptions.PolarsError, ValueError):
        return None


@router.delete("/runs/{run_id}")
def delete_run(run_id: str, request: Request) -> dict[str, Any]:
    """[R55] 删掉一次挖掘运行(连同它的产物目录)。

    跑着的不给删 —— worker 还在往那个目录里写, 删了下一次写入会把目录重建成
    半个残骸, 之后列表里就是一条读不出来的记录。先取消再删。
    """
    manager = _manager(request)
    manifest = manager.store.get(run_id)
    if manifest is None:
        raise HTTPException(status_code=404, detail="run 不存在")
    if manifest.get("status") in ACTIVE_RUN_STATUSES:
        raise HTTPException(status_code=409, detail="这次运行还没结束 —— 先取消再删")
    try:
        manager.store.delete(run_id)
    except MiningRunValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except MiningRunStoreError as exc:
        raise HTTPException(status_code=500, detail="删除失败") from exc
    return {"deleted": run_id}


@router.get("/runs/{run_id}/result")
def get_result(run_id: str, request: Request) -> dict[str, Any]:
    store = _manager(request).store
    manifest = _required_manifest(store, run_id)
    status = str(manifest["status"])
    if status not in SUCCESS_RUN_STATUSES:
        status_code = 409 if status not in TERMINAL_RUN_STATUSES else 422
        raise HTTPException(
            status_code=status_code,
            detail=f"mining result is unavailable for status {status}",
        )
    result = load_run_result(store, run_id)
    if result is None:
        raise HTTPException(
            status_code=500,
            detail="mining result artifacts are unavailable",
        )
    return result


@router.get("/runs/{run_id}/events")
def stream_events(
    run_id: str,
    request: Request,
    last_event_id: str | None = Header(None, alias="Last-Event-ID"),
) -> EventSourceResponse:
    store = _manager(request).store
    _required_manifest(store, run_id)
    cursor = _event_cursor(last_event_id)

    async def generate() -> AsyncIterator[dict[str, str]]:
        nonlocal cursor
        last_emit = asyncio.get_running_loop().time()
        terminal_sent = False
        first_batch = True
        while not await request.is_disconnected():
            events = await asyncio.to_thread(store.read_events, run_id, after_id=cursor)
            if first_batch and events and int(events[0]["id"]) > cursor + 1:
                summary = await asyncio.to_thread(store.read_summary, run_id)
                progress = summary.get("progress")
                if isinstance(progress, Mapping):
                    yield {
                        "id": str(cursor),
                        "event": "progress",
                        "data": json.dumps(progress, ensure_ascii=False, allow_nan=False),
                    }
                    last_emit = asyncio.get_running_loop().time()
            first_batch = False
            for event in events:
                cursor = int(event["id"])
                event_type = "failed" if event.get("type") == "error" else str(event["type"])
                payload = dict(event.get("payload") or {})
                if event_type in TERMINAL_RUN_STATUSES:
                    payload.setdefault("status", event_type)
                    terminal_sent = True
                yield {
                    "id": str(cursor),
                    "event": event_type,
                    "data": json.dumps(payload, ensure_ascii=False, allow_nan=False),
                }
                last_emit = asyncio.get_running_loop().time()
            manifest = await asyncio.to_thread(store.get, run_id)
            if manifest is None:
                return
            status = str(manifest["status"])
            if status in TERMINAL_RUN_STATUSES:
                if not terminal_sent:
                    event_type = "failed" if status == "failed" else status
                    yield {
                        "id": str(cursor),
                        "event": event_type,
                        "data": json.dumps(
                            {"status": status, "message": manifest.get("error")},
                            ensure_ascii=False,
                        ),
                    }
                return
            now = asyncio.get_running_loop().time()
            if now - last_emit >= _SSE_HEARTBEAT_SECONDS:
                yield {"event": "heartbeat", "data": "{}"}
                last_emit = now
            await asyncio.sleep(_SSE_POLL_SECONDS)

    return EventSourceResponse(generate(), ping=_SSE_HEARTBEAT_SECONDS)


@router.post("/runs/{run_id}/candidates/{signature}/promote")
def promote_candidate(run_id: str, signature: str, request: Request) -> dict[str, Any]:
    service = _candidate_service(request)
    try:
        return service.promote(run_id, signature)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="mining run or candidate not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/runs/{run_id}/candidates/{signature}/publish")
def publish_candidate(run_id: str, signature: str, request: Request) -> dict[str, Any]:
    service = _candidate_service(request)
    try:
        return service.publish(run_id, signature)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="mining run or candidate not found") from exc
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/config")
def get_config() -> dict[str, Any]:
    return preferences.get_mining_schedule()


@router.patch("/config")
def update_config(payload: MiningSchedulePatch) -> dict[str, Any]:
    current = preferences.get_mining_schedule()
    updates = payload.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="at least one mining config field is required")
    merged = {**current, **updates}
    try:
        return preferences.set_mining_schedule(
            merged["mining_schedule_enabled"],
            merged["mining_schedule_weekday"],
            merged["mining_budget_profile"],
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _manager(request: Request):
    manager = getattr(request.app.state, "mining_manager", None)
    if manager is None:
        raise HTTPException(status_code=503, detail="mining manager is unavailable")
    return manager


def _candidate_service(request: Request):
    service = getattr(request.app.state, "mining_candidate_service", None)
    if service is not None:
        return service
    from app.backtest.candidates import CandidateStore
    from app.services.mining_candidates import MiningCandidateService

    manager = _manager(request)
    data_dir = request.app.state.repo.store.data_dir
    monitor_engine = getattr(request.app.state, "monitor_engine", None)
    service = MiningCandidateService(
        data_dir,
        manager.store,
        CandidateStore(data_dir),
        request.app.state.strategy_engine,
        monitor_state_invalidator=(
            monitor_engine.invalidate_strategy_state
            if monitor_engine is not None
            else None
        ),
    )
    request.app.state.mining_candidate_service = service
    return service


def _required_manifest(store: MiningRunStore, run_id: str) -> dict[str, Any]:
    try:
        manifest = store.get(run_id)
    except MiningRunValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except MiningRunStoreError as exc:
        raise HTTPException(status_code=500, detail="failed to read mining run") from exc
    if manifest is None:
        raise HTTPException(status_code=404, detail="mining run not found")
    return manifest


def _project_run(store: MiningRunStore, manifest: Mapping[str, Any]) -> dict[str, Any]:
    run_id = str(manifest["run_id"])
    summary = store.read_summary(run_id)
    events = store.read_events(run_id)
    source = next(
        (
            event.get("payload", {}).get("source")
            for event in events
            if event.get("type") == "queued" and event.get("payload", {}).get("source")
        ),
        None,
    )
    if source is None and isinstance(manifest.get("data_fingerprint"), Mapping):
        source = manifest["data_fingerprint"].get("source")
    compact = _summary_projection(summary) if manifest["status"] in SUCCESS_RUN_STATUSES else None
    return {
        "run_id": run_id,
        "signature": manifest["run_signature"],
        "status": manifest["status"],
        "request": manifest.get("request") or {},
        "source": source or "manual",
        "created_at": manifest.get("created_at"),
        "updated_at": manifest.get("updated_at"),
        "started_at": manifest.get("started_at"),
        "finished_at": manifest.get("finished_at"),
        "data_as_of": summary.get("data_as_of"),
        "progress": (
            summary.get("progress")
            if isinstance(summary.get("progress"), Mapping)
            else None
        ),
        "error": manifest.get("error"),
        "summary": compact,
    }


def _request_summary(manifest: Mapping[str, Any]) -> dict[str, Any]:
    request = manifest.get("request") or {}
    factor_names = request.get("factor_names")
    strategy_ids = request.get("strategy_ids")
    return {
        "asset_type": request.get("asset_type") or "stock",
        "budget_profile": request.get("budget_profile") or "balanced",
        "start": request.get("start"),
        "end": request.get("end"),
        "factor_count": len(factor_names) if isinstance(factor_names, list) else 0,
        "strategy_count": len(strategy_ids) if isinstance(strategy_ids, list) else 0,
        "commission_pct": _finite(request.get("commission_pct")),
        "stamp_tax_pct": _finite(request.get("stamp_tax_pct")),
        "slippage_bps": _finite(request.get("slippage_bps")),
        "correlation_threshold": _finite(request.get("correlation_threshold")),
    }


def _summary_projection(summary: Mapping[str, Any]) -> dict[str, Any]:
    worker = summary.get("worker") if isinstance(summary.get("worker"), Mapping) else {}
    return {
        "factor_count": int(summary.get("factor_count") or 0),
        "selected_factor_count": int(summary.get("selected_factor_count") or 0),
        "candidate_count": int(summary.get("candidate_count") or 0),
        "valid_fold_count": int(summary.get("valid_fold_count") or 0),
        "skipped_fold_count": int(summary.get("skipped_fold_count") or 0),
        "confidence": summary.get("confidence") or "low",
        "budget_exhausted": bool(summary.get("budget_exhausted", False)),
        "elapsed_ms": _finite(summary.get("elapsed_ms")),
        "peak_rss_bytes": _optional_int(worker.get("peak_rss_bytes")),
    }


def _read_registered_artifact(
    store: MiningRunStore,
    manifest: Mapping[str, Any],
    name: str,
) -> pl.DataFrame:
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, Mapping) or name not in artifacts:
        raise ValueError(f"mining artifact is not registered: {name}")
    raw_path = artifacts[name]
    if not isinstance(raw_path, str):
        raise ValueError(f"mining artifact registration is invalid: {name}")
    run_dir = store.artifact_path(str(manifest["run_id"]), name).parent  # type: ignore[arg-type]
    registered = (run_dir / raw_path).resolve()
    if not registered.is_relative_to(run_dir.resolve()):
        raise ValueError(f"mining artifact escapes its run directory: {name}")
    if registered.suffix.lower() != ".parquet" or not registered.is_file():
        raise ValueError(f"mining artifact is unavailable: {name}")
    if registered.stat().st_size > _MAX_ARTIFACT_BYTES:
        raise ValueError(f"mining artifact exceeds size limit: {name}")
    return pl.read_parquet(registered)


def _project_result(
    manifest: Mapping[str, Any],
    summary: Mapping[str, Any],
    frames: Mapping[str, pl.DataFrame],
) -> dict[str, Any]:
    factors = [_clean_record(row) for row in frames["factors"].to_dicts()]
    correlation = _project_correlation(frames["correlation"])
    fold_records = [_project_fold(row) for row in frames["folds"].to_dicts()]
    candidates = _project_candidates(frames["candidates"], fold_records)
    selected_signature = candidates[0]["signature"] if candidates else None
    folds = [
        _public_fold(row)
        for row in fold_records
        if row["regime_state"] == "overall"
        and (selected_signature is None or row["candidate_signature"] == selected_signature)
    ]
    regimes = _project_regimes(fold_records, selected_signature)
    worker = summary.get("worker") if isinstance(summary.get("worker"), Mapping) else {}
    threshold = _finite((manifest.get("request") or {}).get("correlation_threshold"))
    correlation["threshold"] = threshold if threshold is not None else 0.75
    return {
        "run_id": manifest["run_id"],
        "methodology_version": summary.get("methodology_version") or "factor_v2",
        "algorithm_version": summary.get("algorithm_version") or MINING_ALGORITHM_VERSION,
        "data_as_of": summary.get("data_as_of"),
        "request_summary": _request_summary(manifest),
        "summary": _summary_projection(summary),
        "factors": factors,
        "correlation": correlation,
        "regimes": regimes,
        "candidates": candidates,
        "folds": folds,
        "telemetry": {
            "elapsed_ms": _finite(summary.get("elapsed_ms")),
            "peak_rss_bytes": _optional_int(worker.get("peak_rss_bytes")),
            "panel_scans": _optional_int(summary.get("panel_scans")),
            "matrix_bytes": _optional_int(summary.get("matrix_bytes")),
            "serialized_result_bytes": _optional_int(worker.get("serialized_result_bytes")),
            "phase_ms": _finite_mapping(summary.get("phase_ms")),
        },
    }


def _project_correlation(frame: pl.DataFrame) -> dict[str, Any]:
    required = {"factor_x", "factor_y", "rho", "pair_count"}
    if not required.issubset(frame.columns):
        raise ValueError("correlation artifact schema is invalid")
    labels = sorted(set(frame["factor_x"].to_list()) | set(frame["factor_y"].to_list()))
    positions = {str(label): index for index, label in enumerate(labels)}
    matrix: list[list[float | None]] = [[None for _ in labels] for _ in labels]
    counts: list[list[int | None]] = [[None for _ in labels] for _ in labels]
    for row in frame.iter_rows(named=True):
        left = positions[str(row["factor_x"])]
        right = positions[str(row["factor_y"])]
        matrix[left][right] = _finite(row["rho"])
        counts[left][right] = _optional_int(row["pair_count"])
    return {"labels": labels, "matrix": matrix, "pair_counts": counts}


def _project_fold(row: Mapping[str, Any]) -> dict[str, Any]:
    projected = _clean_record(row)
    projected["selected_factors"] = _json_string_list(row.get("selected_factors_json"))
    projected["candidate_signature"] = row.get("candidate_signature")
    projected["regime_state"] = str(row.get("regime_state") or "overall")
    projected["n_dates"] = int(row.get("n_dates") or 0)
    return projected


def _public_fold(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: row.get(key)
        for key in (
            "fold", "label", "train_start", "train_end", "test_start", "test_end",
            "selected_factors", "total_return", "sharpe", "max_drawdown", "n_trades",
            "skipped", "reason", "evaluation_kind",
        )
    }


def _project_candidates(
    frame: pl.DataFrame,
    folds: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    required = {"signature", "name", "kind", "factor_names_json", "confidence"}
    if not required.issubset(frame.columns):
        raise ValueError("candidates artifact schema is invalid")
    candidates = []
    for row in frame.to_dicts():
        candidate = _clean_record(row)
        candidate.pop("definition_json", None)
        candidate.pop("factor_names_json", None)
        candidate["factor_names"] = _json_string_list(row.get("factor_names_json"))
        signature = str(row["signature"])
        candidate["folds"] = [
            _public_fold(fold)
            for fold in folds
            if fold["regime_state"] == "overall"
            and fold["candidate_signature"] == signature
        ]
        gate = evaluate_candidate_gate(
            confidence=row.get("confidence"),
            valid_folds=row.get("valid_folds"),
            positive_fold_ratio=row.get("oos_positive_fold_ratio"),
            sharpe=row.get("oos_sharpe"),
            max_drawdown=row.get("oos_max_drawdown"),
            n_trades=row.get("oos_n_trades"),
        )
        candidate["gate"] = {
            "qualified": gate.qualified,
            "reasons": list(gate.reasons),
        }
        candidates.append(candidate)
    candidates.sort(
        key=lambda item: (
            -(item.get("oos_sharpe") if item.get("oos_sharpe") is not None else -math.inf),
            str(item["signature"]),
        )
    )
    return candidates


def _project_regimes(
    folds: Sequence[Mapping[str, Any]],
    signature: str | None,
) -> list[dict[str, Any]]:
    labels = {"overall": "整体", "strong": "强势", "range": "震荡", "weak": "弱势"}
    result = []
    for state in ("overall", "strong", "range", "weak"):
        rows = [
            row
            for row in folds
            if row["regime_state"] == state
            and (signature is None or row["candidate_signature"] == signature)
            and not row.get("skipped")
        ]
        result.append({
            "state": state,
            "label": labels[state],
            "n_dates": sum(int(row.get("n_dates") or 0) for row in rows),
            "total_return": _mean(row.get("total_return") for row in rows),
            "sharpe": _mean(row.get("sharpe") for row in rows),
            "max_drawdown": _minimum(row.get("max_drawdown") for row in rows),
        })
    return result


def _validate_selected_strategies(
    strategy_engine: Any,
    strategy_ids: Sequence[str],
    asset_type: str,
) -> None:
    for strategy_id in strategy_ids:
        strategy = strategy_engine.get(strategy_id)
        if strategy.meta.get("research_only"):
            raise ValueError(f"research template cannot be mined as existing: {strategy_id}")
        if strategy.execution_backend != "matrix_native":
            raise ValueError(f"mining strategy is not matrix-native: {strategy_id}")
        if "1d" not in strategy.meta.get("timeframes", ["1d"]):
            raise ValueError(f"mining strategy is not daily-compatible: {strategy_id}")
        if asset_type not in strategy.meta.get("asset_types", ["stock"]):
            raise ValueError(f"mining strategy does not support {asset_type}: {strategy_id}")


def _event_cursor(value: str | None) -> int:
    if value in (None, ""):
        return 0
    try:
        cursor = int(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Last-Event-ID must be an integer") from exc
    if cursor < 0:
        raise HTTPException(status_code=400, detail="Last-Event-ID must be non-negative")
    return cursor


def _json_string_list(value: Any) -> list[str]:
    if not isinstance(value, str):
        return []
    parsed = json.loads(value)
    if not isinstance(parsed, list) or any(not isinstance(item, str) for item in parsed):
        raise ValueError("artifact JSON list is invalid")
    return parsed


def _clean_record(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        str(key): (_finite(value) if isinstance(value, float) else value)
        for key, value in row.items()
    }


def _finite(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _optional_int(value: Any) -> int | None:
    number = _finite(value)
    return int(number) if number is not None else None


def _finite_mapping(value: Any) -> dict[str, float] | None:
    if not isinstance(value, Mapping):
        return None
    return {
        str(key): number
        for key, item in value.items()
        if (number := _finite(item)) is not None
    }


def _mean(values: Sequence[Any] | Any) -> float | None:
    finite = [number for value in values if (number := _finite(value)) is not None]
    return sum(finite) / len(finite) if finite else None


def _minimum(values: Sequence[Any] | Any) -> float | None:
    finite = [number for value in values if (number := _finite(value)) is not None]
    return min(finite) if finite else None


# ── [fork 增强] R31 AI 自动挖掘: 拿上一轮结果反馈给 AI, 由它重配参数再跑一轮 ──
#
# 单一入口 /step 驱动整个闭环: 手动点一次调一次, 自动模式就是前端定时轮询它。
# 严格串行 —— 任一时刻最多一个挖掘 run(docs/mining.md §任务与资源隔离)。
# 绝不自动发布 —— 选出赢家即停, 等人工确认(§自动运行)。

class AutopilotStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    asset_type: Literal["stock", "etf"] = "stock"
    start: date
    end: date
    holdout_days: int = Field(mining_autopilot.DEFAULT_HOLDOUT_DAYS, ge=90, le=1095)
    budget_profile: Literal["balanced", "strict"] = "balanced"
    max_iterations: int = Field(
        mining_autopilot.DEFAULT_MAX_ITERATIONS, ge=1, le=mining_autopilot.MAX_ITERATIONS_CAP)
    factor_names: list[str] = Field(default_factory=list, max_length=48)
    commission_pct: float = Field(0.0002, ge=0.0, le=0.05, allow_inf_nan=False)
    stamp_tax_pct: float = Field(0.0005, ge=0.0, le=0.05, allow_inf_nan=False)
    slippage_bps: float = Field(5.0, ge=0.0, le=1000.0, allow_inf_nan=False)

    @field_validator("start", "end", mode="before")
    @classmethod
    def _iso(cls, value: Any) -> Any:
        if isinstance(value, str):
            try:
                return date.fromisoformat(value)
            except ValueError as exc:
                raise ValueError("dates must use ISO YYYY-MM-DD format") from exc
        return value


def _factor_catalog() -> list[dict[str, Any]]:
    """喂给 AI 的因子清单(id + 中文名), 不带其他实现细节。"""
    return [{"id": str(f["id"]), "name": str(f.get("label") or f["id"])} for f in FACTOR_COLUMNS]


def _autopilot_session_or_404(session_id: str) -> dict[str, Any]:
    session = mining_autopilot_store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="autopilot session not found")
    return session


def _attach_live_run(manager: Any, session: dict[str, Any]) -> dict[str, Any]:
    """[R38] 给还在跑的那一轮补上 run 的实时进度。

    会话档案只记 queued/running 这种粗状态, 界面上就只能转个圈 —— 用户没法区分
    "排队等槽位"、"正在算第 3 折"和"真卡死了"。这里把 run manifest 里已有的
    progress/started_at 挂到最后一轮上, 让界面能显示阶段、百分比和已跑多久。
    只读, 取不到就不挂(绝不因为进度读失败而让整个会话接口挂掉)。
    """
    iterations = session.get("iterations") or []
    if session.get("status") != "open" or not iterations:
        return session
    last = iterations[-1]
    run_id = last.get("run_id")
    if not run_id or last.get("status") not in ACTIVE_RUN_STATUSES:
        return session
    try:
        manifest = manager.store.get(str(run_id))
        if not manifest:
            return session
        summary = manager.store.read_summary(str(run_id))
        progress = summary.get("progress")
        last["live"] = {
            "status": manifest.get("status"),
            "progress": progress if isinstance(progress, Mapping) else None,
            "queued_at": manifest.get("created_at"),
            "started_at": manifest.get("started_at"),
            "updated_at": manifest.get("updated_at"),
            "error": manifest.get("error"),
        }
    except Exception:  # noqa: BLE001
        return session
    return session


@router.get("/autopilot/sessions")
def autopilot_sessions(request: Request) -> dict[str, Any]:
    manager = _manager(request)
    return {"items": [_attach_live_run(manager, s)
                      for s in mining_autopilot_store.list_sessions()]}


@router.get("/autopilot/sessions/{session_id}")
def autopilot_session(session_id: str, request: Request) -> dict[str, Any]:
    return _attach_live_run(_manager(request), _autopilot_session_or_404(session_id))


@router.post("/autopilot/sessions/{session_id}/stop")
def autopilot_stop(session_id: str, request: Request) -> dict[str, Any]:
    """[R38] 中止会话: 先取消正在跑的那一轮, 再把会话收成 stopped。

    收成独立的 stopped 而不是 failed —— "我按了停"和"它自己崩了"在复盘时是两件事,
    混成一个状态以后看历史会以为这轮挖掘出过问题。
    幂等: 已经收工的会话直接原样返回, 重复点不会把已完成的结果抹掉。
    """
    session = _autopilot_session_or_404(session_id)
    # [R53] 有主的会话停了也白停 —— 工作流会认为这次"重开"结束了, 转头再开一个。
    # 真想让它停下来, 要停的是工作流。
    owner = session.get("owner_workflow_id")
    if owner:
        raise HTTPException(
            status_code=409,
            detail=(f"这个会话由工作流 {owner} 开的。单停会话没用 —— 工作流会当成"
                    "这次重开结束了, 转头再开一个。要停就停那个工作流。"))
    if session.get("status") != "open":
        return {"session": session, "message": "本会话已经收工, 无需中止"}

    manager = _manager(request)
    cancelled_run: str | None = None
    iterations = session.get("iterations") or []
    if iterations and iterations[-1].get("run_id"):
        last = iterations[-1]
        run_id = str(last["run_id"])
        manifest = manager.store.get(run_id)
        if manifest and manifest.get("status") in ACTIVE_RUN_STATUSES:
            try:
                manager.cancel(run_id)
                cancelled_run = run_id
            except (MiningRunStoreError, KeyError, ValueError) as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
        # 会话档案里的这一轮同步落成 cancelled, 否则下次 step 还会以为它在跑
        last["status"] = "cancelled"
        mining_autopilot_store._replace(session)

    updated = mining_autopilot_store.set_status(
        session_id, "stopped",
        fail_reason="你中止了这个会话" + (f"(第 {len(iterations)} 轮挖掘已取消)" if cancelled_run else ""),
    ) or session
    return {"session": _attach_live_run(manager, updated),
            "message": "已中止" + (", 正在跑的那一轮也停了" if cancelled_run else "")}


def build_autopilot_session(
    *, repo, asset_type: str, start: date, end: date, holdout_days: int,
    budget_profile: str, max_iterations: int, factor_names: Sequence[str] = (),
    commission_pct: float = 0.0002, stamp_tax_pct: float = 0.0005,
    slippage_bps: float = 5.0, owner_workflow_id: str | None = None,
) -> dict[str, Any]:
    """[R39] 开一个自动挖掘会话(窗口切分 + 真实交易日预检)。

    端点和后台工作流共用这一条路径 —— 预检口径必须一模一样, 否则手动开能过、
    工作流开却在第一轮才炸。数据不够时抛 ValueError, 消息已是给用户看的中文。
    """
    windows = mining_autopilot.split_windows(
        start, end, holdout_days=holdout_days, budget_profile=budget_profile)

    # 粗筛过了还要按 enriched 真实交易日精确核验(docs §置信度: balanced/strict 需 3 个 outer 折)。
    # 不够时不要直接把 preflight 原文抛给用户 —— 它只会说"有效区间 xx 到 yy 只有 3 根",
    # 而用户明明填了四年区间, 看不懂。换成带真实数字和出路的中文说明。
    data_dir = repo.store.data_dir
    avail_search = mining_availability(
        data_dir, asset_type=asset_type, budget_profile=budget_profile,
        start=windows["search_start"], end=windows["search_end"]).to_dict()
    if not avail_search.get("eligible"):
        avail_all = mining_availability(
            data_dir, asset_type=asset_type, budget_profile=budget_profile).to_dict()
        raise ValueError(mining_autopilot.explain_insufficient_data(
            avail_search=avail_search, avail_all=avail_all,
            windows={k: str(v) for k, v in windows.items()},
            budget_profile=budget_profile, holdout_days=holdout_days))

    factors = [f for f in factor_names if f in _FACTOR_IDS]
    base_config = {
        "asset_type": asset_type,
        "budget_profile": budget_profile,
        # 首轮因子: 用户没指定就把全清单交给 AI 之后的轮次去挑, 首轮先用全量跑个底
        "factor_names": factors or [str(f["id"]) for f in FACTOR_COLUMNS][:48],
        "commission_pct": commission_pct,
        "stamp_tax_pct": stamp_tax_pct,
        "slippage_bps": slippage_bps,
        "correlation_threshold": 0.75,
        "max_combination_factors": 4,
        "beam_width": 12,
    }
    return mining_autopilot_store.create(
        asset_type=asset_type, windows=windows,
        max_iterations=max_iterations, base_config=base_config,
        owner_workflow_id=owner_workflow_id)


async def advance_autopilot_session(
    session: dict[str, Any], *, manager: Any, repo: Any, app_state: Any,
) -> dict[str, Any]:
    """[R39] 把一个自动挖掘会话推进一格。端点与后台工作流共用。

    组装 step 需要的三样东西: 上一轮 run 的状态、它的结果、以及"按这份配置起
    一个 run"的回调。step 本身不碰 HTTP 也不碰 manager, 所以这段装配必须在外面做。
    """
    run_status: str | None = None
    run_result: dict[str, Any] | None = None
    iterations = session.get("iterations") or []
    if iterations and iterations[-1].get("run_id"):
        run_id = str(iterations[-1]["run_id"])
        manifest = manager.store.get(run_id)
        if manifest:
            run_status = str(manifest.get("status") or "")
            if run_status in SUCCESS_RUN_STATUSES:
                run_result = load_run_result(manager.store, run_id)

    def start_run(config: dict[str, Any]) -> str:
        worker_request = {k: v for k, v in config.items()}
        worker_request["start"] = str(config["start"])
        worker_request["end"] = str(config["end"])
        fingerprint = build_data_fingerprint(repo, app_state, worker_request)
        # force=True: 同配置复用旧 run 会让循环原地打转 —— 每轮都要真跑
        manifest = manager.start(worker_request, fingerprint, force=True, source="autopilot")
        return str(manifest["run_id"])

    return await mining_autopilot.step(
        session=session, factor_catalog=_factor_catalog(),
        run_status=run_status, run_result=run_result,
        start_run=start_run, base_config=session["base_config"])


# [R53] 挖掘是重活: heavy_job_limiter 容量 2, 一个挖掘 run 独占两格。所以同时
# 只应该有一路在挖 —— 再开一路不会更快, 它只会静默排队, 界面上看着就是"卡住了"。
#
# 而工作流的一次"重开"本来就是开一个自动挖掘会话, 两者是包含关系不是并列关系:
# 工作流跑着的时候手动再开一个, 等于让同一件事排两次队。这里直接挡掉并说清楚。
def _reject_if_workflow_owns_mining() -> None:
    from app.services import workflow

    running = [w for w in workflow.running_workflows() if w.get("kind") == workflow.KIND_MINING]
    if running:
        wf = running[0]
        raise HTTPException(
            status_code=409,
            detail=(f"挖掘工作流 {wf['workflow_id']} 正在跑, 它自己就在反复开自动挖掘会话。"
                    "同时再开一个不会更快 —— 挖掘一次只能跑一路, 第二个只会排队等着。"
                    "要手动一轮一轮调, 先把上面的工作流停掉。"))


@router.delete("/autopilot/sessions/{session_id}")
def autopilot_delete(session_id: str) -> dict[str, Any]:
    """[R55] 删一个自动挖掘会话留档。

    两种情况不给删: 还开着的(先中止, 否则正在跑的那一轮没人收尾), 以及
    工作流开的(它还要靠这条记录接着往下推)。
    """
    session = _autopilot_session_or_404(session_id)
    if session.get("owner_workflow_id"):
        raise HTTPException(
            status_code=409,
            detail=f"这个会话属于工作流 {session['owner_workflow_id']} —— 要清掉请删那条工作流。")
    if session.get("status") == "open":
        raise HTTPException(status_code=409, detail="这个会话还开着 —— 先中止再删")
    mining_autopilot_store.delete(session_id)
    return {"deleted": session_id}


@router.post("/autopilot/sessions")
def autopilot_start(payload: AutopilotStartRequest, request: Request) -> dict[str, Any]:
    """开一个自动挖掘会话。窗口切分 + 真实交易日预检都在这里把关, 免得第一轮才失败。"""
    _reject_if_workflow_owns_mining()
    try:
        return build_autopilot_session(
            repo=request.app.state.repo,
            asset_type=payload.asset_type, start=payload.start, end=payload.end,
            holdout_days=payload.holdout_days, budget_profile=payload.budget_profile,
            max_iterations=payload.max_iterations, factor_names=payload.factor_names,
            commission_pct=payload.commission_pct, stamp_tax_pct=payload.stamp_tax_pct,
            slippage_bps=payload.slippage_bps)
    except (ValueError, MiningRunValidationError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/autopilot/sessions/{session_id}/step")
async def autopilot_step(session_id: str, request: Request) -> dict[str, Any]:
    """推进一格: 等待中 / 判上一轮并开新一轮 / 收工。手动与自动共用这一个入口。"""
    session = _autopilot_session_or_404(session_id)
    # [R53] 有主的会话只能由它的主人推 —— 界面和工作流后台同时 step 同一个
    # 状态机, 轮次会错乱(两边都以为自己开的是第 N 轮)。
    owner = session.get("owner_workflow_id")
    if owner:
        raise HTTPException(
            status_code=409,
            detail=f"这个会话由工作流 {owner} 在跑, 它会自己往下推。要手动接管请先停掉那个工作流。")
    out = await advance_autopilot_session(
        session,
        manager=_manager(request), repo=request.app.state.repo,
        app_state=request.app.state)
    return {"action": out["action"], "message": out["message"], "session": out["session"]}
