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

from app.indicators.keltner import BANDS, assess, verdict

logger = logging.getLogger(__name__)

# MA120 需要 120 个交易日; 日历天按 ~1.6 倍取余量, 再加缓冲
_LOOKBACK_DAYS = 260
_MAX_SYMBOLS = 300


# [R134] MA120 斜率的回看跨度(交易日)。20 日 ≈ 一个月 —— 比它短会被单周波动
# 带得忽上忽下, 比它长则高位刚拐头的票要好几周才认出来。
_SLOPE_LOOKBACK = 20


def long_trend_map(repo, symbols: list[str]) -> dict[str, dict]:
    """[R134] 一次批量日 K 同时算出**生命线**与**长期趋势**, 供买入门槛使用。

    这两件事原本要各读一次盘: 生命线要 MA20 与前一日收盘, 长期趋势要 MA120
    及其斜率。但它们的原料是同一串收盘价 —— MA20 = 最近 20 根的均值,
    MA120 = 最近 120 根的均值, 斜率 = 与 20 根之前那个 MA120 比。所以合并到
    本来就存在的这一次 260 日批量读里, **不新增任何 IO**。

    返回 {SYMBOL: {close, close_prev, ma20, ma20_prev, above_ma20, above_ma20_prev,
                   ma120, ma120_prev, ma120_rising}}。
    算不出来的项缺席而不是给 0 —— 门槛那侧对"缺数据"的处理是放行, 给个假的 0
    会让它变成误杀。
    """
    end = date.today()
    try:
        df = repo.get_daily_batch(symbols, end - timedelta(days=_LOOKBACK_DAYS), end,
                                  ["symbol", "date", "close"])
    except Exception as e:  # noqa: BLE001
        logger.debug("keltner long trend batch failed: %s", e)
        return {}
    if df is None or df.is_empty() or not {"symbol", "date", "close"} <= set(df.columns):
        return {}
    out: dict[str, dict] = {}
    for sym, sub in df.drop_nulls("close").sort("date").group_by("symbol"):
        name = str(sym[0] if isinstance(sym, tuple) else sym).upper()
        closes = sub["close"].to_list()
        ent: dict = {}
        if closes:
            ent["close"] = float(closes[-1])
        if len(closes) >= 2:
            ent["close_prev"] = float(closes[-2])
        if len(closes) >= 20:
            ent["ma20"] = float(sum(closes[-20:]) / 20)
            ent["above_ma20"] = ent["close"] >= ent["ma20"]
        # 前一日的生命线要用**前一日的** MA20, 不是今天的 —— 拿今天的均线去比
        # 昨天的收盘, 得到的是个半新半旧的判定
        if len(closes) >= 21:
            ent["ma20_prev"] = float(sum(closes[-21:-1]) / 20)
            ent["above_ma20_prev"] = ent["close_prev"] >= ent["ma20_prev"]
        # 不足 120 根的直接不给值 —— 拿 60 根算出来的"120 日均线"是个假数
        if len(closes) >= 120:
            ent["ma120"] = float(sum(closes[-120:]) / 120)
        if len(closes) >= 120 + _SLOPE_LOOKBACK:
            prev = float(sum(closes[-120 - _SLOPE_LOOKBACK:-_SLOPE_LOOKBACK]) / 120)
            ent["ma120_prev"] = prev
            ent["ma120_rising"] = ent["ma120"] >= prev
        if ent:
            out[name] = ent
    return out


def _ma120_map(repo, symbols: list[str]) -> dict[str, float]:
    """批量算 MA120。长期档是唯一没有预计算列的一档, 只能自己滚。

    [R134] 现在是 long_trend_map 的一个投影 —— 同一串收盘价既要算通道的
    长期档, 又要算买入门槛的长期趋势, 读两次盘没道理。
    """
    return {k: v["ma120"] for k, v in long_trend_map(repo, symbols).items()
            if v.get("ma120") is not None}


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
            # [R44] 三档组合的结论跟着一起返回 —— 界面不必自己再拼一遍规则,
            # 也保证决策台、今日总览、悬停提示说的是同一句话
            v = verdict(bands)
            out[sym] = dict(bands, verdict=v) if v else bands
    return out
