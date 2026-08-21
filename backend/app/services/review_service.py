"""[fork 增强] R48 单只个股的逐日复盘。

决策台的「趋势」和「结论」两列只显示**今天**的读数。要判断这两列到底靠不靠谱,
得能翻回去看: 上次它说"强势深调"是哪天、之后走了什么、这只票的涨停都出现在
什么状态下。这个模块就是把那段历史一次算出来。

三样东西按同一条时间轴对齐:
  · 六态趋势状态 —— 走 ``indicators.livermore.compute`` 的 steps, 与决策台
    「趋势」列同一个状态机、同一个阈值(含用户自己调过的那个)。
  · Keltner 三档位置与结论 —— 走 ``indicators.keltner``, 与决策台三列、
    「结论」列、个股分析图表同一组公式, 只是把输入换成当天的均线/ATR。
  · 涨停 / 跌停 / 炸板 / 连板数 —— 直接取 enriched 的预计算列, 不自己判
    (涨跌停幅度按板块和 ST 状态分档, 那套判定在 pipeline 里已经很细了)。

口径提醒(界面要显示出来): 均线与 ATR 都是按**当前**复权因子回算的。之后除权
的话, 同一天今天算出来的通道会和当天实际看到的略有出入 —— 复盘看的是形态与
节奏, 不是当时屏幕的像素级还原。
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

import polars as pl

from app.indicators import keltner as k
from app.indicators.livermore import BULLISH, STATE_LABELS, compute

logger = logging.getLogger(__name__)

# 默认回看多少个交易日。半年够看完一轮完整的趋势切换, 再长的话表格本身就没法读了。
DEFAULT_DAYS = 120
MAX_DAYS = 250

# 长期档要 120 根做暖机, 六态状态机也需要一段历史才稳定 —— 多取的这部分只参与
# 计算, 不进结果。
_WARMUP_BARS = 130
# 交易日 → 日历日的换算余量(节假日 + 停牌)
_CALENDAR_RATIO = 1.7

# 结论出现之后看几天 —— 与历史胜率那套(livermore_service 的 horizon=5)对齐,
# 一周左右正好是这些位置结论该兑现的尺度。
FORWARD_DAYS = 5

_WANT_COLS = ("date", "close", "change_pct", "ma20", "ma60", "atr_14",
              "signal_limit_up", "signal_limit_down", "signal_broken_limit_up",
              "consecutive_limit_ups")


def _load(repo, symbol: str, days: int) -> pl.DataFrame:
    end = date.today()
    span = int((days + _WARMUP_BARS) * _CALENDAR_RATIO) + 30
    try:
        at = repo.resolve_asset_type(symbol)
    except Exception:  # noqa: BLE001
        at = "stock"
    try:
        df = repo.get_daily_asset(at, symbol, end - timedelta(days=span), end,
                                  columns=list(_WANT_COLS))
    except Exception as e:  # noqa: BLE001
        logger.warning("review daily load failed for %s: %s", symbol, e)
        return pl.DataFrame()
    if df is None or df.is_empty() or not {"date", "close"} <= set(df.columns):
        return pl.DataFrame()
    return df.drop_nulls("close").sort("date")


def _ma120(df: pl.DataFrame) -> list[float | None]:
    """长期档是唯一没有预计算列的一档。不足 120 根的那些天留 None ——
    拿 60 根算出来的"120 日均线"是个假数, 宁可这一档缺席。"""
    s = df["close"].rolling_mean(120)
    return [None if v is None else float(v) for v in s]


def _trend_by_date(df: pl.DataFrame, threshold: float) -> dict[str, dict]:
    """逐日六态状态 + 该状态到当天已经走了第几天。"""
    closes = [float(c) for c in df["close"]]
    dates = [str(d) for d in df["date"]]
    if len(closes) < 2:
        return {}
    try:
        steps = compute(closes, dates, threshold)["steps"]
    except Exception as e:  # noqa: BLE001
        logger.debug("review trend compute failed: %s", e)
        return {}
    out: dict[str, dict] = {}
    run = 0
    prev_state = None
    for st in steps:
        state = st.get("state")
        run = run + 1 if state == prev_state else 1
        prev_state = state
        cn, en = STATE_LABELS.get(state, (state or "—", ""))
        out[str(st["date"])] = {
            "state": state, "state_cn": cn, "state_en": en,
            "side": "多头" if state in BULLISH else "空头",
            "day": run,
            # 转折那天单独标出来 —— 复盘时最想找的就是这些天
            "flipped": bool(st.get("flipped")),
        }
    return out


def _bands_for_row(close, ma20, ma60, ma120, atr) -> dict:
    """当天的三档通道读数。与决策台走同一个 ``assess``, 只是输入换成当天的值。"""
    bands: dict[str, dict] = {}
    mas = {"ma20": ma20, "ma60": ma60, None: ma120}
    for key, ma_col, _window, n, cn in k.BANDS:
        got = k.assess(close=close, ma=mas.get(ma_col), atr=atr, n=n)
        if got:
            bands[key] = dict(got, band_cn=cn)
    return bands


def _forward_returns(closes: list[float], i: int, horizon: int) -> float | None:
    j = i + horizon
    if j >= len(closes) or not closes[i]:
        return None
    return closes[j] / closes[i] - 1


def _outcomes(rows: list[dict], closes: list[float], offset: int) -> list[dict]:
    """每种结论在这只票上出现过几次、之后 FORWARD_DAYS 走成什么样。

    这是复盘真正想问的那个问题 —— 「结论」列说的话, 在**这只票**身上过去
    好不好使。样本小得很(半年内同一档往往只有个位数), 所以只报次数和均值,
    不折算成胜率百分比去装得像统计结论。
    """
    agg: dict[str, dict] = {}
    for n, r in enumerate(rows):
        v = r.get("verdict")
        if not v:
            continue
        fwd = _forward_returns(closes, offset + n, FORWARD_DAYS)
        if fwd is None:
            continue    # 末尾不足 FORWARD_DAYS 的不计, 不拿半截数据凑样本
        a = agg.setdefault(v["code"], {"code": v["code"], "title": v["title"],
                                       "tone": v["tone"], "n": 0, "sum": 0.0, "win": 0})
        a["n"] += 1
        a["sum"] += fwd
        a["win"] += 1 if fwd > 0 else 0
    out = []
    for a in agg.values():
        out.append({"code": a["code"], "title": a["title"], "tone": a["tone"],
                    "n": a["n"], "avg_fwd": round(a["sum"] / a["n"], 4),
                    "win": a["win"]})
    out.sort(key=lambda x: -x["n"])
    return out


def _b(v) -> bool:
    return bool(v) if v is not None else False


def review_for_symbol(repo, symbol: str, days: int = DEFAULT_DAYS) -> dict:
    """逐日复盘: 趋势状态 / 三档通道结论 / 涨停, 按同一条时间轴对齐。

    行按**新→旧**返回 —— 打开就该先看到最近几天, 那才是要复盘的部分。
    """
    sym = (symbol or "").strip().upper()
    if not sym:
        return {"symbol": sym, "error": "symbol 不能为空"}
    days = max(10, min(int(days or DEFAULT_DAYS), MAX_DAYS))

    df = _load(repo, sym, days)
    if df.is_empty():
        return {"symbol": sym, "error": "日 K 数据不足, 无法复盘"}

    from app.services.livermore_service import get_effective_threshold
    thr, thr_src = get_effective_threshold(sym)
    trend_map = _trend_by_date(df, thr)

    cols = set(df.columns)
    ma120 = _ma120(df)
    closes = [float(c) for c in df["close"]]
    n_total = len(closes)
    offset = max(0, n_total - days)

    def col(name: str) -> list:
        return list(df[name]) if name in cols else [None] * n_total

    dates = [str(d) for d in df["date"]]
    ma20s, ma60s, atrs = col("ma20"), col("ma60"), col("atr_14")
    chg = col("change_pct")
    lu, ld, bl = col("signal_limit_up"), col("signal_limit_down"), col("signal_broken_limit_up")
    streak = col("consecutive_limit_ups")

    rows: list[dict] = []
    for i in range(offset, n_total):
        bands = _bands_for_row(closes[i], ma20s[i], ma60s[i], ma120[i], atrs[i])
        v = k.verdict(bands) if bands else None
        # [R51] 每天单独带上"之后 FORWARD_DAYS 走成什么样"。结论视图按段展示时要
        # 说清这一段结论出现后到底兑现没有 —— 只有一个全票平均数看不出是哪一次。
        fwd = _forward_returns(closes, i, FORWARD_DAYS)
        rows.append({
            "date": dates[i],
            "close": round(closes[i], 2),
            "change_pct": None if chg[i] is None else round(float(chg[i]), 4),
            "limit_up": _b(lu[i]),
            "limit_down": _b(ld[i]),
            "broken_limit_up": _b(bl[i]),
            "limit_streak": int(streak[i] or 0),
            "trend": trend_map.get(dates[i]),
            # 三档只带位置文字 —— 逐日全套读数会让这个响应大到没必要
            "bands": {key: {"pos": b["pos"], "pos_cn": b["pos_cn"]}
                      for key, b in bands.items()},
            "verdict": v,
            # 末尾不足 FORWARD_DAYS 的那几天为 None —— 还不知道结果, 不拿半截数据凑
            "fwd": None if fwd is None else round(fwd, 4),
        })

    limit_ups = sum(1 for r in rows if r["limit_up"])
    out_rows = list(reversed(rows))
    return {
        "symbol": sym,
        "days": len(rows),
        "start": rows[0]["date"] if rows else None,
        "end": rows[-1]["date"] if rows else None,
        "threshold": thr,
        "threshold_source": thr_src,
        "forward_days": FORWARD_DAYS,
        "stats": {
            "limit_ups": limit_ups,
            "limit_downs": sum(1 for r in rows if r["limit_down"]),
            "broken_limit_ups": sum(1 for r in rows if r["broken_limit_up"]),
            "max_streak": max((r["limit_streak"] for r in rows), default=0),
            # 涨停都出现在什么趋势状态下 —— 复盘时最直接的一条: 这只票的涨停
            # 是趋势里出的, 还是下跌途中的反抽
            "limit_up_states": _limit_up_states(rows),
        },
        "outcomes": _outcomes(rows, closes, offset),
        "rows": out_rows,
    }


def _limit_up_states(rows: list[dict]) -> list[dict]:
    agg: dict[str, int] = {}
    for r in rows:
        if not r["limit_up"]:
            continue
        t = (r.get("trend") or {}).get("state_cn") or "—"
        agg[t] = agg.get(t, 0) + 1
    return [{"state_cn": s, "n": n} for s, n in
            sorted(agg.items(), key=lambda kv: -kv[1])]
