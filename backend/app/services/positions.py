"""自选持仓标记(决策台)—— 用户手动标记每只自选的持有状态与成本价。

存储:`data/user_data/positions.json`,结构 {SYMBOL: {held: bool, cost: float|None, updated_at: iso}}。
纯本地、非敏感,merge-write。供「个股分析 · 自选决策台」纵观对比浮盈用。
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)


def _path() -> Path:
    p = settings.data_dir / "user_data" / "positions.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def load_all() -> dict[str, dict]:
    """返回 {symbol: {held, cost, updated_at}}。读盘失败/为空返回空 dict。"""
    p = _path()
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception as e:  # noqa: BLE001
        logger.warning("load positions failed: %s", e)
        return {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def set_position(symbol: str, held: bool, cost: float | None) -> dict:
    """标记某只自选的持仓:是否持有 + 可选成本价。cost 传 None/空 表示不记成本。"""
    sym = (symbol or "").strip().upper()
    if not sym:
        raise ValueError("symbol required")
    data = load_all()
    try:
        cost_val = float(cost) if cost not in (None, "") else None
    except (TypeError, ValueError):
        cost_val = None
    entry = {"held": bool(held), "cost": cost_val, "updated_at": _now_iso()}
    data[sym] = entry
    _path().write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return entry


def clear_position(symbol: str) -> bool:
    """移除某只自选的持仓标记。"""
    sym = (symbol or "").strip().upper()
    data = load_all()
    if sym in data:
        del data[sym]
        _path().write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        return True
    return False
