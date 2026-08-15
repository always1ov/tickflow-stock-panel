"""[fork 增强] 大盘红绿灯 —— 基准指数的市场模式判定(牛市/中性/防御思路的 A 股适配)。

灵感来自 AI-TIS PRD 的三模式体系, 适配为:
  进攻: 指数在 MA200 之上且在 MA50 之上
  谨慎: 指数跌破 MA50 但守住 MA200
  防守: 指数收盘 < MA200, 或近一年动量 < 0(任一成立, 一票否决, 立即生效)
黏性: 非防守方向的模式切换需连续 CONFIRM_DAYS 个交易日成立才落地,
期间保持原模式并标注"待确认"——避免单日假突破导致模式天天翻脸。

纯规则零 AI; 状态持久于 ``user_data/market_mode.json``; 指数数据走独立
kline_index parquet(repo.get_index_daily), 不触碰选股与策略链路。
"""
from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)

# 基准指数: 沪深300; 数据缺失时按序回退(上证指数几乎必有)
BENCHMARKS = ["000300.SH", "000001.SH"]
# 完整判定所需最少交易日(MA200); 年动量窗口
MIN_BARS = 200
MOMENTUM_BARS = 240
# 非防守切换需连续成立的交易日数(防守不受此限, 立即生效)
CONFIRM_DAYS = 2

MODE_RANK = {"防守": 0, "谨慎": 1, "观察": 2, "进攻": 3}


def _store_path() -> Path:
    p = settings.data_dir / "user_data" / "market_mode.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _load_state() -> dict:
    p = _store_path()
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception as e:  # noqa: BLE001
        logger.warning("load market mode state failed: %s", e)
        return {}


def _save_state(state: dict) -> None:
    try:
        _store_path().write_text(
            json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        logger.warning("save market mode state failed: %s", e)


def raw_mode(closes: list[float]) -> dict:
    """按当日数据算"原始模式"(不含黏性)。closes 按日期升序, 最后一个为最新收盘。

    返回 {mode, reason, metrics}; 数据不足时 mode="观察" 并明说。
    """
    n = len(closes)
    if n < MIN_BARS:
        return {
            "mode": "观察",
            "reason": f"指数历史仅 {n} 个交易日(需 {MIN_BARS}),先按观察处理 —— 到指数页同步更长日K后生效",
            "metrics": {},
        }
    close = closes[-1]
    ma50 = sum(closes[-50:]) / 50
    ma200 = sum(closes[-200:]) / 200
    mom_window = min(n, MOMENTUM_BARS)
    momentum = close / closes[-mom_window] - 1
    metrics = {
        "close": round(close, 2), "ma50": round(ma50, 2), "ma200": round(ma200, 2),
        "momentum_12m": round(momentum, 4),
        # [R13] 近 20 交易日收益, 供个股相对强度对比
        "ret_20d": round(close / closes[-21] - 1, 4) if closes[-21] else None,
    }
    # 防守一票否决
    if close < ma200:
        return {"mode": "防守",
                "reason": f"大盘收盘 {close:.0f} 已跌破年线 {ma200:.0f},大环境转坏",
                "metrics": metrics}
    if momentum < 0:
        return {"mode": "防守",
                "reason": f"大盘比一年前还低({momentum:+.1%}),长期方向向下",
                "metrics": metrics}
    if close > ma50:
        return {"mode": "进攻",
                "reason": f"大盘站在年线 {ma200:.0f} 和 50日线 {ma50:.0f} 之上,环境健康",
                "metrics": metrics}
    return {"mode": "谨慎",
            "reason": f"大盘跌破 50日线 {ma50:.0f} 但仍守住年线 {ma200:.0f},短期转弱",
            "metrics": metrics}


def apply_stickiness(raw: dict, state: dict, as_of: str) -> dict:
    """把黏性规则套在原始模式上, 返回生效模式并更新 state(调用方负责持久化)。

    - 防守: 立即生效, 不等确认
    - 其他模式: 与当前生效模式不同时, 需连续 CONFIRM_DAYS 个交易日成立;
      未满期间保持原模式, 标注 pending
    - 同一交易日重复调用不重复累计天数
    """
    effective = state.get("mode")
    rm = raw["mode"]
    if rm == "防守" or effective is None:
        state.update({"mode": rm, "raw_mode": rm, "raw_streak": 1, "as_of": as_of})
        return {"mode": rm, "reason": raw["reason"], "pending": None,
                "metrics": raw["metrics"]}
    if rm == effective:
        state.update({"raw_mode": rm, "raw_streak": 1, "as_of": as_of})
        return {"mode": rm, "reason": raw["reason"], "pending": None,
                "metrics": raw["metrics"]}
    # 原始模式与生效模式不同 → 累计确认天数(仅在新交易日推进)
    streak = int(state.get("raw_streak") or 0) if state.get("raw_mode") == rm else 0
    if state.get("as_of") != as_of:
        streak += 1
    elif streak == 0:
        streak = 1
    state.update({"raw_mode": rm, "raw_streak": streak, "as_of": as_of})
    if streak >= CONFIRM_DAYS:
        state["mode"] = rm
        return {"mode": rm, "reason": raw["reason"], "pending": None,
                "metrics": raw["metrics"]}
    return {
        "mode": effective,
        "reason": f"暂维持{effective}: 新状态「{rm}」出现第 {streak} 天,连续 {CONFIRM_DAYS} 天才切换(防单日假信号)",
        "pending": {"mode": rm, "streak": streak, "need": CONFIRM_DAYS,
                    "raw_reason": raw["reason"]},
        "metrics": raw["metrics"],
    }


def get_market_mode(repo) -> dict:
    """读取基准指数日K → 判定生效模式(含黏性)。任何失败退化为观察, 不抛异常。

    返回 {benchmark, benchmark_name, mode, reason, pending, metrics, as_of}。
    """
    closes: list[float] = []
    used = None
    as_of = None
    end = date.today()
    start = end - timedelta(days=520)  # 日历日, 覆盖约 350 个交易日
    for sym in BENCHMARKS:
        try:
            df = repo.get_index_daily(sym, start, end, columns=["date", "close"])
        except Exception as e:  # noqa: BLE001
            logger.warning("market mode: load %s failed: %s", sym, e)
            continue
        if df.is_empty() or "close" not in df.columns:
            continue
        df = df.sort("date")
        closes = [float(c) for c in df["close"].to_list() if c is not None]
        if closes:
            used = sym
            as_of = str(df["date"].to_list()[-1])
            break
    if not closes:
        return {
            "benchmark": None, "benchmark_name": None, "mode": "观察",
            "reason": "读不到基准指数日K(沪深300/上证指数),先按观察处理 —— 到指数页同步指数日K后生效",
            "pending": None, "metrics": {}, "as_of": None,
        }
    raw = raw_mode(closes)
    state = _load_state()
    out = apply_stickiness(raw, state, as_of or "")
    _save_state(state)
    names = {"000300.SH": "沪深300", "000001.SH": "上证指数"}
    out.update({"benchmark": used, "benchmark_name": names.get(used, used), "as_of": as_of})
    return out


def combine_posture(market_mode_cn: str, breadth_posture: str) -> str:
    """最终姿态 = 大盘模式与自选广度取更保守者(排名小者)。"""
    a = MODE_RANK.get(market_mode_cn, 2)
    b = MODE_RANK.get(breadth_posture, 2)
    return market_mode_cn if a <= b else breadth_posture
