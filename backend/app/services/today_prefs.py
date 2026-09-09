"""[fork 增强] 今日总览偏好 —— 机会区筛选门槛(用户可随时改)。

存于 ``data/user_data/today_prefs.json``。只管"买入机会显示多少、多严",
卖出/风险提醒永远不受这里影响。
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from app.config import settings
from app.price_limits import BOARDS

logger = logging.getLogger(__name__)

DEFAULTS = {
    "min_score": 60, "max_show": 10,
    # [R12] 仓位建议: 单票仓位上限(%)与目标日波动率(%); ATR 波幅超过目标时按比例压缩
    "max_single": 20, "target_vol": 3,
    # [缺口④] 组合回撤纪律线(%): 组合净值从高点回撤超过此值 → 行动区置顶降仓提醒
    "max_drawdown": 10,
    # [R15] 金字塔建仓路径(利弗莫尔式, 由价格确认驱动):
    # 试仓占目标仓位 % → 站稳 N 日加至 % → 回踩不破上满
    "pyramid_probe": 35, "pyramid_confirm": 70, "pyramid_days": 2,
    # [R40] 板块过滤: 空 = 全看。只影响买入机会区, 卖出/风险提醒永远不受影响。
    "boards": [],
    # [R204] 参与打分的因子。**空 = 全开**(与 boards 同一个约定: 全选等价于
    # 不过滤, 统一存成空, 免得以后加了新因子时"当时全选"的旧配置反而把新因子
    # 排除在外)。用户可以关掉几个来把把握分的区分度拉开 —— 十个因子平均出来
    # 的分天生挤在中间一段, 少平均几个带宽就回来了。
}
_MIN_SCORE_RANGE = (0, 100)
_MAX_SHOW_RANGE = (1, 50)
_MAX_SINGLE_RANGE = (5, 100)
_TARGET_VOL_RANGE = (1, 10)
_MAX_DRAWDOWN_RANGE = (3, 30)
_PYRAMID_PROBE_RANGE = (10, 60)
_PYRAMID_CONFIRM_RANGE = (40, 90)
_PYRAMID_DAYS_RANGE = (1, 5)
_VALID_BOARDS = frozenset(BOARDS)


def _boards(value, fallback: list[str]) -> list[str]:
    """板块清单归一: 丢掉不认识的名字, 去重且保持 BOARDS 的展示顺序。

    全选等价于不过滤 —— 统一存成空列表, 免得以后 BOARDS 加了新板块时,
    一个"当时全选"的旧配置反而变成了排除新板块。
    """
    if value is None:
        return list(fallback)
    if not isinstance(value, (list, tuple, set)):
        return list(fallback)
    raw = {str(v) for v in value}
    picked = raw & _VALID_BOARDS
    if not picked:
        # 传了东西但一个都不认识 → 保持原样。静默变成"全看"会让人以为筛选生效了
        return [] if not raw else list(fallback)
    if picked == _VALID_BOARDS:
        return []
    return [b for b in BOARDS if b in picked]


# [R218] `_factors()` 随因子勾选面板一起删掉, 见 pages/Today.tsx 的说明。


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
        "max_drawdown": _clamp(data.get("max_drawdown"), *_MAX_DRAWDOWN_RANGE, DEFAULTS["max_drawdown"]),
        "pyramid_probe": _clamp(data.get("pyramid_probe"), *_PYRAMID_PROBE_RANGE, DEFAULTS["pyramid_probe"]),
        "pyramid_confirm": _clamp(data.get("pyramid_confirm"), *_PYRAMID_CONFIRM_RANGE, DEFAULTS["pyramid_confirm"]),
        "pyramid_days": _clamp(data.get("pyramid_days"), *_PYRAMID_DAYS_RANGE, DEFAULTS["pyramid_days"]),
        "boards": _boards(data.get("boards"), DEFAULTS["boards"]),
    }


def save(min_score=None, max_show=None, max_single=None, target_vol=None,
         max_drawdown=None, pyramid_probe=None, pyramid_confirm=None,
         pyramid_days=None, boards=None) -> dict:
    """更新偏好(只改传入的字段), 返回生效后的完整偏好。"""
    # [R72] 读-改-写上锁 + 原子落盘(CONTRIBUTING §6.2)
    from app.services.json_store import lock_for
    with lock_for(_store_path()):
        return _save_locked(min_score, max_show, max_single, target_vol,
                            max_drawdown, pyramid_probe, pyramid_confirm,
                            pyramid_days, boards)


def _save_locked(min_score, max_show, max_single, target_vol, max_drawdown,
                 pyramid_probe, pyramid_confirm, pyramid_days, boards) -> dict:
    cur = load()
    if min_score is not None:
        cur["min_score"] = _clamp(min_score, *_MIN_SCORE_RANGE, cur["min_score"])
    if max_show is not None:
        cur["max_show"] = _clamp(max_show, *_MAX_SHOW_RANGE, cur["max_show"])
    if max_single is not None:
        cur["max_single"] = _clamp(max_single, *_MAX_SINGLE_RANGE, cur["max_single"])
    if target_vol is not None:
        cur["target_vol"] = _clamp(target_vol, *_TARGET_VOL_RANGE, cur["target_vol"])
    if max_drawdown is not None:
        cur["max_drawdown"] = _clamp(max_drawdown, *_MAX_DRAWDOWN_RANGE, cur["max_drawdown"])
    if pyramid_probe is not None:
        cur["pyramid_probe"] = _clamp(pyramid_probe, *_PYRAMID_PROBE_RANGE, cur["pyramid_probe"])
    if pyramid_confirm is not None:
        cur["pyramid_confirm"] = _clamp(pyramid_confirm, *_PYRAMID_CONFIRM_RANGE, cur["pyramid_confirm"])
    if pyramid_days is not None:
        cur["pyramid_days"] = _clamp(pyramid_days, *_PYRAMID_DAYS_RANGE, cur["pyramid_days"])
    if boards is not None:
        cur["boards"] = _boards(boards, cur["boards"])
    from app.services.json_store import atomic_write_json
    atomic_write_json(_store_path(), cur)
    return cur
