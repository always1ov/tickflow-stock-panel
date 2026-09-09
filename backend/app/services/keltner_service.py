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

from app.indicators import keltner_geometry as kg
from app.indicators.keltner import BANDS, assess, verdict

logger = logging.getLogger(__name__)

# MA120 需要 120 个交易日; 日历天按 ~1.6 倍取余量, 再加缓冲
_LOOKBACK_DAYS = 260
_MAX_SYMBOLS = 300


# [R134] MA120 斜率的回看跨度(交易日)。20 日 ≈ 一个月 —— 比它短会被单周波动
# 带得忽上忽下, 比它长则高位刚拐头的票要好几周才认出来。
_SLOPE_LOOKBACK = 20

# [R189] 趋势模板那条路的窗口。要算 MA200 的一个月斜率(222 个交易日)与 52 周
# 高低点(250 个交易日), 取最长的 250 根再留出停牌与节假日的富余 —— 420 个
# 自然日约 285 个交易日。只有 with_closes=True 时才用这个跨度。
_LOOKBACK_DAYS_LONG = 420

# 算历史序列至少要够长期档滚一遍
WINDOW_LONG = 120


def long_trend_map(repo, symbols: list[str], *, with_closes: bool = False) -> dict[str, dict]:
    """[R134] 一次批量日 K 同时算出**生命线**与**长期趋势**, 供买入门槛使用。

    这两件事原本要各读一次盘: 生命线要 MA20 与前一日收盘, 长期趋势要 MA120
    及其斜率。但它们的原料是同一串收盘价 —— MA20 = 最近 20 根的均值,
    MA120 = 最近 120 根的均值, 斜率 = 与 20 根之前那个 MA120 比。所以合并到
    本来就存在的这一次 260 日批量读里, **不新增任何 IO**。

    返回 {SYMBOL: {close, close_prev, ma20, ma20_prev, above_ma20, above_ma20_prev,
                   ma120, ma120_prev, ma120_rising}}。
    算不出来的项缺席而不是给 0 —— 门槛那侧对"缺数据"的处理是放行, 给个假的 0
    会让它变成误杀。

    [R189] `with_closes=True` 时**把窗口拉长到 _LOOKBACK_DAYS_LONG 并在每行附上
    收盘价序列**, 供趋势模板算 MA150/MA200 与 52 周高低点。默认关着:
    这个函数还被 Keltner 长期档(全自选逐日调用)复用, 那条路只要 MA120,
    多读半年的行、多背一份序列都是白花的。
    """
    end = date.today()
    span = _LOOKBACK_DAYS_LONG if with_closes else _LOOKBACK_DAYS
    try:
        # [R195] 多要一列 atr_14 —— 压缩指数与"在轨外连续几天"要按 ATR 归一化算
        # 历史序列。**这一次批量读本来就在发生**(长期档的 MA120 没有预计算列,
        # 全自选每天都要走这里滚一遍), 多带一列几乎不花钱; 另起一条取数路才贵。
        # [R238] 多要 ma20/ma60 两列。**不是为了省计算, 是为了同源** ——
        # 复盘与决策台徽标都吃这两个预计算列, 逐日结论自己滚均线的话数出来的
        # 逐日结论就和界面上另外两处不是一套, 天数对不上(用户: 「数字本身就
        # 不对」)。长档没有预计算列, 仍然自己滚。
        df = repo.get_daily_batch(symbols, end - timedelta(days=span), end,
                                  ["symbol", "date", "close", "atr_14",
                                   "ma20", "ma60"])
    except Exception as e:  # noqa: BLE001
        logger.debug("keltner long trend batch failed: %s", e)
        return {}
    if df is None or df.is_empty() or not {"symbol", "date", "close"} <= set(df.columns):
        return {}
    has_atr = "atr_14" in df.columns
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
        # [R195] 通道几何的历史序列 → 压缩持续天数(新的"磨底磨了多久")与
        # 在轨外连续天数(区分"突破"与"站稳")。O(n) 前缀和, 不新增取数。
        # 取不到 atr_14 就整块缺席 —— 半截数据推不出压缩指数。
        if has_atr and len(closes) >= WINDOW_LONG:
            try:
                atrs = [None if a is None else float(a) for a in sub["atr_14"].to_list()]
                cl = [float(c) for c in closes]
                rows = kg.series(cl, atrs)
                if rows:
                    r = kg.runs(rows)
                    # [R197] O 的时间积分(平均压缩度)。与 compress_days 量的不是
                    # 同一件事: 前者会被中间一天的脱开清零, 后者只是被拉低一点。
                    # 一只 compress_days=0 而 compress_avg=0.9 的票是"刚刚启动"。
                    r["compress_avg"] = kg.compress_avg(rows)
                    ent["runs"] = r
                    # [R197] 频段能量分布 —— 这只票的波动主要来自哪个周期。
                    # 同一份序列, 不额外取数。
                    e = kg.band_energy(cl, atrs)
                    if e:
                        ent["energy"] = e
                    # [R239] 交出**逐日结论序列**(新→旧)而不是在这里数完。
                    # 数的那一步归 channels_for_symbols —— 只有它知道徽标上
                    # 印的是哪一档。理由见 kg.verdict_codes 的说明。
                    codes = kg.verdict_codes(
                        cl, atrs,
                        ma20=sub["ma20"].to_list() if "ma20" in sub.columns else None,
                        ma60=sub["ma60"].to_list() if "ma60" in sub.columns else None)
                    if codes:
                        ent["verdict_codes"] = codes
                        ds = [str(d) for d in sub["date"].to_list()]
                        ent["verdict_dates"] = ds[::-1][:len(codes)]
            except Exception as e:  # noqa: BLE001
                logger.debug("channel runs skipped for %s: %s", name, e)
        if with_closes:
            # 趋势模板要自己按 50/150/200 滚均线、按 250 根取 52 周高低,
            # 所以给序列而不是给几个算好的数 —— 口径归 trend_template 一处管。
            ent["closes"] = [float(c) for c in closes]
            # 近 6 个月超额收益的个股一侧(基准一侧在 market_mode)。
            # 120 个交易日 ≈ 半年, 与 market_mode 的 ret_120d 同一口径。
            if len(closes) >= 121 and closes[-121]:
                ent["ret_120d"] = float(closes[-1]) / float(closes[-121]) - 1
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
    # [R195] 直接用整份 long_trend_map 而不是它的 ma120 投影 —— 同一次批量读里
    # 已经把通道几何的历史序列(runs)算好了, 丢掉再算一遍没道理。
    long_map = long_trend_map(repo, [str(r["symbol"]).upper() for r in rows]) if need_long else {}
    ma120 = {k_: v["ma120"] for k_, v in long_map.items() if v.get("ma120") is not None}

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
            if v:
                # [R233] 结论徽标要能说"这一档已经连着几天了" —— 天数与结论是
                # 同一件事的两半, 挂在 verdict 里而不是另起一个平级字段,
                # 免得界面各处取一个忘一个。
                #
                # [R239] **拿徽标上这一档往回数**, 而不是要求两条路先在
                # "今天"上达成一致。两条路的今天本来就常常不一样(enriched
                # 快照 vs 日线批量), 那是个必须成立却经常不成立的前提, 结果
                # 是全表每一行都退化成 1 天。
                lm = long_map.get(sym) or {}
                codes = lm.get("verdict_codes") or []
                hist = kg.count_trailing(codes, v.get("code"))
                if hist:
                    v = dict(v, days=hist, days_exact=True)
                    ds = lm.get("verdict_dates") or []
                    if len(ds) >= hist:
                        v["since"] = ds[hist - 1]
                    if hist >= len(codes):
                        v["capped"] = True
                else:
                    # 历史里最近一根就不是这一档 —— 通常就是今天刚变。
                    v = dict(v, days=1, days_exact=False)
            row = dict(bands, verdict=v) if v else dict(bands)
            if not v:
                # [R242] **没有结论的那一格也要有天数。** 用户: 「别搞什么下跌
                # 半年, 下跌多少天就表示多少天」—— 那一格徽标印的是组合注记
                # 标题(「半年低位」), 一个模糊的时间词, 偏偏没有天数。
                # 结论列每一个徽标都该带「已N天」, 这才叫统一表达。
                lm = long_map.get(sym) or {}
                codes = lm.get("verdict_codes") or []
                key = kg.state_key(bands)
                hist = kg.count_trailing(codes, key)
                if hist:
                    run = {"days": hist}
                    ds = lm.get("verdict_dates") or []
                    if len(ds) >= hist:
                        run["since"] = ds[hist - 1]
                    if hist >= len(codes):
                        run["capped"] = True
                    row["state_run"] = run
            # [R195] 几何量(速度/加速度/压缩/排列)。**零新增取数** —— 全部从
            # 已经算好的三档上下轨反推(轨 = MA ± k·ATR 是恒等式)。
            geo = kg.geometry(bands, close)
            if geo:
                row["geo"] = geo
            lm = long_map.get(sym) or {}
            if lm.get("runs"):
                row["runs"] = lm["runs"]
            if lm.get("energy"):
                row["energy"] = lm["energy"]
            out[sym] = row
    return out
