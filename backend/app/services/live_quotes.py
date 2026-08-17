"""[fork 增强] 自选实时价映射 —— 实时叠加层的统一读取入口。

今日总览 / 决策台趋势列 / 出场线距离共用: {symbol: {date, close}}。
实时行情开关关闭或尚未拉到数据时返回空 dict, 调用方自动退回收盘口径。
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def watchlist_live_map(repo) -> dict[str, dict]:
    """读自选实时叠加层(股票+ETF)→ {symbol: {date, close}}。任何失败返回空。"""
    out: dict[str, dict] = {}
    for asset in ("stock", "etf"):
        try:
            df = repo.get_watchlist_live(asset)
        except Exception as e:  # noqa: BLE001
            logger.debug("watchlist live overlay skipped (%s): %s", asset, e)
            continue
        if df is None or df.is_empty() or not {"symbol", "close"} <= set(df.columns):
            continue
        cols = [c for c in ("symbol", "date", "close") if c in df.columns]
        for row in df.select(cols).to_dicts():
            sym = str(row.get("symbol") or "").upper()
            close = row.get("close")
            if sym and close:
                out[sym] = {"date": str(row.get("date") or ""), "close": float(close)}
    return out


def as_live_entries(live: dict[str, dict]) -> dict[str, tuple[str, float]]:
    """转成 livermore trends 接口的 live 参数形态 {symbol: (date, close)}。"""
    return {s: (v["date"], v["close"]) for s, v in live.items()}
