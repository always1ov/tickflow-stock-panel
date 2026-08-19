"""[fork 增强] 今日总览 AI 导读·优选的结果缓存。

此前结果只存在前端组件 state 里, 刷新页面就没了 —— 每天要重点一次很反直觉,
定时自动生成也无处落地。改为落盘: 前端进页面即读缓存常驻显示,
手动点或定时任务生成时覆盖当天的记录。

存 ``user_data/today_ai.json``: {as_of, brief, picks, analyzed, created_at, source}
只保留最新一份(这是"今天的导读", 历史价值低; 复盘那套才是留档场景)。
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)


def _path() -> Path:
    p = settings.data_dir / "user_data" / "today_ai.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def load() -> dict | None:
    """读取缓存的导读·优选; 无/损坏返回 None。"""
    p = _path()
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) and data.get("brief") is not None else None
    except Exception as e:  # noqa: BLE001
        logger.warning("load today ai cache failed: %s", e)
        return None


def save(result: dict, *, as_of: str | None, source: str = "manual") -> dict:
    """写入缓存。source: manual=手动点击 / scheduled=定时任务。"""
    entry = {
        "as_of": as_of,
        "brief": result.get("brief") or "",
        "picks": result.get("picks") or [],
        "analyzed": result.get("analyzed") or 0,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": source,
    }
    try:
        _path().write_text(json.dumps(entry, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        logger.warning("save today ai cache failed: %s", e)
    return entry
