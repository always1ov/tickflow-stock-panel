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
        # [R246] 多要 ma20/ma60 两列: 逐日状态要与复盘、徽标**同源**。
        # 自己滚均线的话逐日结论就和界面另外两处不是一套, 天数对不上。
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
            except Exception as e:  # noqa: BLE001
                logger.debug("channel runs skipped for %s: %s", name, e)

        # [R263] **逐日状态序列挪出那道 120 根的门。**
        #
        # 上面那道 `len(closes) >= WINDOW_LONG` 是给**几何量**(压缩/在轨外/能量)
        # 设的 —— 它们确实要长期档。可逐日状态跟徽标一样, 缺一档照样判得出来
        # (R263 已经让两边对齐了), 卡在那道门里就等于: 新股徽标有结论、天数却
        # 永远是「已1天+」。用户: 「有漏网之鱼不显示天数」。
        #
        # 门槛降到短期档要的 20 根 —— 再少连一档都算不出, 那才是真没得数。
        if has_atr and len(closes) >= kg.WINDOW["s"]:
            try:
                states = kg.state_series(
                    [float(c) for c in closes],
                    [None if a is None else float(a) for a in sub["atr_14"].to_list()],
                    ma20=sub["ma20"].to_list() if "ma20" in sub.columns else None,
                    ma60=sub["ma60"].to_list() if "ma60" in sub.columns else None)
                if states:
                    ent["states"] = states
                    ds = [str(d) for d in sub["date"].to_list()]
                    ent["state_dates"] = ds[::-1][:len(states)]
            except Exception as e:  # noqa: BLE001
                logger.debug("state series skipped for %s: %s", name, e)
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


def _state_run(key: str | None, lm: dict, as_of: str | None) -> dict | None:
    """[R246] `key` 这一档从今天往回连着几天。

    返回 `{"days": N, "since": "YYYY-MM-DD", "capped": bool}`, 数不出来给 None。

    口径: **中断即重算, 不累计。**「候选池」出现 3 天、隔一天、再 2 天,
    报的是 2 天 —— 那是两次独立的出现, 报 5 天会让人以为它在这个位置磨了一周。
    与"在轨外连续几天"、六态的 duration 同一条纪律。含今天(今天成立就是第 1 天)。

    `capped` = 天数是**下界**: 序列到头了, 或再往前那天算不出来(长期档要 120
    根暖机, 更早的日子判不了)。徽标上写 `+`。

    ## [R248] 两条路的「今天」对不上时 —— **保底 1 天, 绝不让数字消失**

    徽标那一档来自 enriched 快照, 逐日序列来自日线批量。两者在最后一根上
    **本来就可能不一样**(复权口径、快照与日线不是同一天收的)。

    R246 这里返回 `None`, 注释里写着「让上层退回今天刚变」—— **那个兜底我根本
    没写**, 于是对不上的行天数整个不显示。用户: 「怎么不显示天数了?」

    这是这个功能第二次栽在同一件事上(R234 也是), 所以规矩写死在这里:
    **徽标上有一档, 就一定有天数。** 徽标印的是今天的真相, 说它「已1天」是
    真话(按历史那条路, 昨天不是这一档); **一个偏保守的数字远好过一个消失的字段** ——
    "算不出来"和"功能没部署"在界面上长得一模一样, 而这两种要做的事完全不同。
    """
    seq = lm.get("states") or []
    dates = lm.get("state_dates") or []
    if not key:
        return None

    # [R256] **序列里到底有没有"今天"?** 拿快照日期与序列最新一根的日期对一下,
    # 三种情形要分开 —— 混成一种就会差一天, 或者整段作废(用户截图里那个
    # 全表「已1天+」)。
    #
    #   ① 同一天, 且序列这一档就是徽标那一档  → 序列的头就是今天, 直接数
    #   ② 同一天, 但序列判成了别的档          → 那一根是今天的另一个读数,
    #                                          跳过它; 今天以**徽标**为准算 1 天
    #   ③ 不是同一天(日线比快照滞后)          → 序列里压根没有今天,
    #                                          今天单算 1 天, 再从序列的头接着数
    same_day = bool(as_of and dates and str(dates[0]) == str(as_of))
    if same_day and seq and seq[0] == key:
        today, start = 0, 0
    elif same_day:
        today, start = 1, 1
    else:
        today, start = 1, 0

    n = 0
    while start + n < len(seq) and seq[start + n] == key:
        n += 1
    days = today + n
    if days <= 0:
        return None

    out: dict = {"days": days}
    if n and len(dates) > start + n - 1:
        out["since"] = str(dates[start + n - 1])
    elif today and as_of:
        out["since"] = str(as_of)          # 今天刚变成这一档
    # 数到判得出结论的尽头 = 天数是下界(序列到头了, 或再往前那天算不出来)
    if start + n >= len(seq) or seq[start + n] is None:
        out["capped"] = True
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
        df, as_of = repo.get_enriched_latest()
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
            row = dict(bands, verdict=v) if v else dict(bands)
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
            # [R246] **最近这一档连着几天。** 用户: 「显示每个个股的通道结论里面
            # 的最近的状态和持续时间」。
            #
            # 拿**徽标上印的那一档**往回数, 而不是要求逐日序列先和快照在"今天"
            # 上达成一致 —— 两条路的今天本来就常常不一样(enriched 快照 vs
            # 日线批量: 数据日期差一天、末根不同), 要求一致会让全表退化成 1 天。
            run = _state_run(kg.state_key(bands), lm, as_of)
            if run:
                if v:
                    v.update(run)          # 天数并进 verdict, 免得界面各处取一个忘一个
                else:
                    row["state_run"] = run  # 没结论那一格印的是组合注记, 同样要天数
            out[sym] = row
    return out
