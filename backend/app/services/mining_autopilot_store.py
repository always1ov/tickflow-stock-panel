"""[fork 增强] R31 AI 自动挖掘会话留档。

"每次点都拿上次的结果"靠这里落地: 每一轮的配置、run_id、跑出的候选、AI 的判断
都按轮次追加进同一个会话, 下次点按钮时整段历史再喂回给 AI。刷新页面不丢。

存 ``user_data/mining_autopilot.json``: {"sessions": [最旧 → 最新]}
只保留最近 MAX_SESSIONS 个会话(挖掘会话重, 留太多没意义也占地方)。
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)

MAX_SESSIONS = 10


def _path() -> Path:
    p = settings.data_dir / "user_data" / "mining_autopilot.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _read_all() -> list[dict]:
    p = _path()
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        logger.warning("load mining autopilot sessions failed: %s", e)
        return []
    rows = data.get("sessions") if isinstance(data, dict) else None
    return [s for s in rows or [] if isinstance(s, dict)]


def _write_all(sessions: list[dict]) -> None:
    try:
        _path().write_text(
            json.dumps({"sessions": sessions[-MAX_SESSIONS:]}, ensure_ascii=False, indent=2),
            encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        logger.warning("save mining autopilot sessions failed: %s", e)


def list_sessions(limit: int = MAX_SESSIONS) -> list[dict]:
    """最新在前。"""
    return list(reversed(_read_all()))[:limit]


def get(session_id: str) -> dict | None:
    for s in _read_all():
        if s.get("session_id") == session_id:
            return s
    return None


def latest() -> dict | None:
    rows = _read_all()
    return rows[-1] if rows else None


def create(*, asset_type: str, windows: dict, max_iterations: int,
           base_config: dict) -> dict:
    """开一个新会话。windows 的 date 统一转 ISO 字符串, 落盘即 JSON 安全。"""
    session = {
        "session_id": uuid.uuid4().hex[:12],
        "asset_type": asset_type,
        "search_start": str(windows["search_start"]),
        "search_end": str(windows["search_end"]),
        "holdout_start": str(windows["holdout_start"]),
        "holdout_end": str(windows["holdout_end"]),
        "max_iterations": int(max_iterations),
        "base_config": base_config,
        "iterations": [],
        "status": "open",
        "winner": None,
        "final_check": None,
        "created_at": _now(),
        "updated_at": _now(),
    }
    rows = _read_all()
    rows.append(session)
    _write_all(rows)
    return session


def _replace(session: dict) -> dict:
    session["updated_at"] = _now()
    rows = [s for s in _read_all() if s.get("session_id") != session.get("session_id")]
    rows.append(session)
    _write_all(rows)
    return session


def append_iteration(session_id: str, entry: dict) -> dict | None:
    """追加一轮。entry: {config, run_id, status, candidates, ai}。"""
    session = get(session_id)
    if session is None:
        return None
    entry = dict(entry)
    entry["iteration"] = len(session["iterations"]) + 1
    entry["created_at"] = _now()
    session["iterations"].append(entry)
    return _replace(session)


def set_status(session_id: str, status: str, **fields: Any) -> dict | None:
    """收尾: status=satisfied/exhausted/failed, 顺带写 winner / final_check。"""
    session = get(session_id)
    if session is None:
        return None
    session["status"] = status
    for k, v in fields.items():
        session[k] = v
    return _replace(session)
