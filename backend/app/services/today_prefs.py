"""[fork 增强] 今日总览偏好 —— 机会区筛选门槛(用户可随时改)。

存于 ``data/user_data/today_prefs.json``。只管"买入机会显示多少、多严",
卖出/风险提醒永远不受这里影响。
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)

DEFAULTS = {
    "min_score": 60, "max_show": 10,
    # [R12] 仓位建议: 单票仓位上限(%)与目标日波动率(%); ATR 波幅超过目标时按比例压缩
    "max_single": 20, "target_vol": 3,
}
_MIN_SCORE_RANGE = (0, 100)
_MAX_SHOW_RANGE = (1, 50)
_MAX_SINGLE_RANGE = (5, 100)
_TARGET_VOL_RANGE = (1, 10)


def _store_path() -> Path:
    p = settings.data_dir / "user_data" / "today_prefs.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _clamp(value, lo: int, hi: int, fallback: int) -> int:
    try:
        return max(lo, min(hi, int(round(float(value)))))
    except (TypeError, ValueError):
        return fallback


def load() -> dict:
    """读取偏好, 缺字段/损坏时回落到默认值。"""
    p = _store_path()
    if not p.exists():
        return dict(DEFAULTS)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("bad prefs")
    except Exception as e:  # noqa: BLE001
        logger.warning("load today prefs failed: %s", e)
        return dict(DEFAULTS)
    return {
        "min_score": _clamp(data.get("min_score"), *_MIN_SCORE_RANGE, DEFAULTS["min_score"]),
        "max_show": _clamp(data.get("max_show"), *_MAX_SHOW_RANGE, DEFAULTS["max_show"]),
        "max_single": _clamp(data.get("max_single"), *_MAX_SINGLE_RANGE, DEFAULTS["max_single"]),
        "target_vol": _clamp(data.get("target_vol"), *_TARGET_VOL_RANGE, DEFAULTS["target_vol"]),
    }


def save(min_score=None, max_show=None, max_single=None, target_vol=None) -> dict:
    """更新偏好(只改传入的字段), 返回生效后的完整偏好。"""
    cur = load()
    if min_score is not None:
        cur["min_score"] = _clamp(min_score, *_MIN_SCORE_RANGE, cur["min_score"])
    if max_show is not None:
        cur["max_show"] = _clamp(max_show, *_MAX_SHOW_RANGE, cur["max_show"])
    if max_single is not None:
        cur["max_single"] = _clamp(max_single, *_MAX_SINGLE_RANGE, cur["max_single"])
    if target_vol is not None:
        cur["target_vol"] = _clamp(target_vol, *_TARGET_VOL_RANGE, cur["target_vol"])
    _store_path().write_text(json.dumps(cur, indent=2, ensure_ascii=False), encoding="utf-8")
    return cur
