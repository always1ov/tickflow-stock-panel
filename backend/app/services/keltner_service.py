"""[fork 增强] R42 决策台的 Keltner 三档位置(批量)。

个股分析的图表是按单只标的算通道的(``indicators.levels``)。决策台要给整张自选表
加三列, 逐只调那条路径等于把 147 次 120 天的读盘串起来 —— 这里改成两次批量读:

  1. enriched 最新快照 → close / atr_14 / ma20 / ma60(都是预计算列)
  2. 一次批量日 K → 只为算 MA120(唯一没有预计算列的那一档)

公式与图表共用 ``indicators.keltner``, 不重写一份。

口径说明: 走**收盘**。盘中实时叠加层只有价格没有 ATR/均线, 拿实时价去比昨天的
通道会得到一个半新半旧的判定 —— 结论层本来就该走收盘(PRD §7.5)。
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

import polars as pl

from app.indicators.keltner import BANDS, assess

logger = logging.getLogger(__name__)

# MA120 需要 120 个交易日; 日历天按 ~1.6 倍取余量, 再加缓冲
_LOOKBACK_DAYS = 260
_MAX_SYMBOLS = 300


def _ma120_map(repo, symbols: list[str]) -> dict[str, float]:
    """批量算 MA120。长期档是唯一没有预计算列的一档, 只能自己滚。

    不足 120 根的标的直接不给值 —— 拿 60 根算出来的"120 日均线"是个假数,
    宁可这一档留空。
    """
    end = date.today()
    try:
        df = repo.get_daily_batch(symbols, end - timedelta(days=_LOOKBACK_DAYS), end,
                                  ["symbol", "date", "close"])
    except Exception as e:  # noqa: BLE001
        logger.debug("keltner ma120 batch failed: %s", e)
        return {}
    if df is None or df.is_empty() or not {"symbol", "date", "close"} <= set(df.columns):
        return {}
    out: dict[str, float] = {}
    for sym, sub in df.drop_nulls("close").sort("date").group_by("symbol"):
        name = str(sym[0] if isinstance(sym, tuple) else sym).upper()
        closes = sub["close"].tail(120)
        if len(closes) < 120:
            continue
        out[name] = float(closes.mean())
    return out


def channels_for_symbols(repo, symbols: list[str]) -> dict[str, dict]:
    """{SYMBOL: {"s": {...}, "m": {...}, "l": {...}}}。

    某一档算不出来(均线列缺失/新股不够长)时该档缺席, 不放一个空壳进去 ——
    界面据此显示"—", 比显示一个看着像真的 0 强。
    """
    syms = sorted({str(s).strip().upper() for s in symbols if str(s).strip()})[:_MAX_SYMBOLS]
    if not syms:
        return {}

    try:
        df, _as_of = repo.get_enriched_latest()
    except Exception as e:  # noqa: BLE001
        logger.warning("keltner enriched snapshot unavailable: %s", e)
        return {}
    if df is None or df.is_empty() or "symbol" not in df.columns:
        return {}

    want = [c for c in ("symbol", "close", "atr_14", "ma20", "ma60") if c in df.columns]
    if not {"symbol", "close", "atr_14"} <= set(want):
        return {}
    rows = df.filter(pl.col("symbol").str.to_uppercase().is_in(syms)).select(want).to_dicts()
    if not rows:
        return {}

    need_long = any(b[1] is None for b in BANDS)
    ma120 = _ma120_map(repo, [str(r["symbol"]).upper() for r in rows]) if need_long else {}

    out: dict[str, dict] = {}
    for r in rows:
        sym = str(r["symbol"]).upper()
        atr, close = r.get("atr_14"), r.get("close")
        bands: dict[str, dict] = {}
        for key, ma_col, _window, n, cn in BANDS:
            ma = ma120.get(sym) if ma_col is None else r.get(ma_col)
            got = assess(close=close, ma=ma, atr=atr, n=n)
            if got:
                bands[key] = dict(got, band_cn=cn)
        if bands:
            out[sym] = bands
    return out
