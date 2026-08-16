"""[fork 增强] 组合净值快照 —— 记录高点、算回撤, 触发"纪律性降仓"提醒。

净值口径: 1 + Σ(仓位比例 × 浮盈), 即"相对成本的账户净值估算"。只对填了
仓位比例(weight)的持仓有意义; 没填时整个模块静默不参与。
存储 ``user_data/portfolio_history.json``: [{date, nav}], 同日刷新覆盖当日值,
上限 750 条(约三年交易日)。回撤 = 1 - 当前净值 / 历史最高净值。
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)

_MAX_ENTRIES = 750


def _store_path() -> Path:
    p = settings.data_dir / "user_data" / "portfolio_history.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _load() -> list[dict]:
    p = _store_path()
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception as e:  # noqa: BLE001
        logger.warning("load portfolio history failed: %s", e)
        return []


def update(as_of: str, nav: float) -> dict:
    """记录/覆盖 as_of 当日净值, 返回 {nav, peak, drawdown}。写盘失败只警告不抛。"""
    entries = _load()
    if entries and entries[-1].get("date") == as_of:
        entries[-1]["nav"] = nav
    else:
        entries.append({"date": as_of, "nav": nav})
        entries = entries[-_MAX_ENTRIES:]
    try:
        _store_path().write_text(
            json.dumps(entries, ensure_ascii=False), encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        logger.warning("save portfolio history failed: %s", e)
    peak = max((e.get("nav") or 0) for e in entries)
    drawdown = round(1 - nav / peak, 4) if peak > 0 else 0.0
    return {"nav": round(nav, 4), "peak": round(peak, 4), "drawdown": max(0.0, drawdown)}
