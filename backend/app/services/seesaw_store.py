"""[fork 增强] R28 板块跷跷板的 30 天留档。

跷跷板是个"看轮次"的东西 —— 单看今天没意义, 得知道这对板块最近来回切了几轮、
上一轮是哪天换的手, 短期观察才有参照。所以每次识别都留一条, 滚动保留 30 天。

存 ``user_data/seesaw_history.json``: {"entries": [最旧 → 最新]}
每条 {as_of, created_at, source, kind, pairs, ai}; 同一天重复识别按 (as_of, kind) 覆盖,
不会把一天刷成好几条。
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)

MAX_ENTRIES = 30  # 30 天 —— 用户要的短期观察窗口


def _path() -> Path:
    p = settings.data_dir / "user_data" / "seesaw_history.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _read_all() -> list[dict]:
    p = _path()
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        logger.warning("load seesaw history failed: %s", e)
        return []
    entries = data.get("entries") if isinstance(data, dict) else None
    return [e for e in entries or [] if isinstance(e, dict)]


def load_history(*, kind: str | None = None, limit: int = MAX_ENTRIES) -> list[dict]:
    """按时间倒序返回历史(最新在前)。"""
    rows = _read_all()
    if kind:
        rows = [e for e in rows if e.get("kind") == kind]
    return list(reversed(rows))[:limit]


def load_latest(*, kind: str | None = None) -> dict | None:
    rows = load_history(kind=kind, limit=1)
    return rows[0] if rows else None


def save(result: dict, *, source: str = "manual") -> dict:
    """追加一条识别结果; 同 (as_of, kind) 覆盖, 超出 30 条丢最旧的。"""
    entry = {
        "as_of": result.get("as_of"),
        "kind": result.get("kind") or "concept",
        # 序列体积大且历史用不上(要回看直接重算), 留档只存结论列
        "pairs": [{k: v for k, v in p.items() if not k.startswith("series_")}
                  for p in (result.get("pairs") or [])],
        "ai": result.get("ai") or None,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": source,
    }
    # [R72] 读-改-写上锁 + 原子落盘(CONTRIBUTING §6.2): 定时和手动可能同时保存
    from app.services.json_store import atomic_write_json, lock_for
    with lock_for(_path()):
        rows = [e for e in _read_all()
                if not (e.get("as_of") == entry["as_of"] and e.get("kind") == entry["kind"])]
        rows.append(entry)
        rows = rows[-MAX_ENTRIES:]
        try:
            atomic_write_json(_path(), {"entries": rows})
        except Exception as e:  # noqa: BLE001
            logger.warning("save seesaw history failed: %s", e)
    return entry
