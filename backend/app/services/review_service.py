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


# ==================== [R177] 按「段」而不是按「天」聚合 ====================
#
# 这只票在某个状态下之后普遍怎么走 —— 要回答这个, 单位必须是**段**, 不是天。
#
# 原因是前瞻收益会重叠。一段持续 8 天的「上涨趋势」, 按天算就是 8 个样本, 可
# 这 8 天各自的"之后 5 日"互相共享 4 天, 根本不独立。把它们平均起来, n 看着
# 有 8, 实际信息量只有 1 段多一点 —— 这会让一个很薄的结论显得挺扎实, 恰恰是
# 这套复盘最该避免的事。
#
# 所以: **一段 = 一次**, 收益从段的第一天起算。代价是样本数变得更小更难看,
# 但那个更小的数字才是真的。

def _episodes(rows: list[dict], key_of, closes: list[float],
              offset: int, horizon: int) -> list[dict]:
    """把连续同值的行压成段。返回 [{key, start, days, fwd}]。

    key_of(row) 返回 None 的行不进段, 并且**打断**当前段 —— 中间隔了一段没有
    读数的日子, 前后不该算同一次。
    """
    out: list[dict] = []
    cur_key, cur_start, cur_days = None, 0, 0

    def _flush():
        if cur_key is None:
            return
        out.append({"key": cur_key, "start": rows[cur_start]["date"],
                    "days": cur_days,
                    "fwd": _forward_returns(closes, offset + cur_start, horizon)})

    for i, r in enumerate(rows):
        key = key_of(r)
        if key == cur_key and key is not None:
            cur_days += 1
            continue
        _flush()
        cur_key, cur_start, cur_days = key, i, 1
    _flush()
    return out


def _agg_episodes(eps: list[dict], label_of) -> list[dict]:
    """段 → 每个取值的次数 / 平均持续 / 之后 horizon 日表现。

    末尾不足 horizon 的段不计收益(还不知道结果), 但**仍计次数** —— 那一段
    确实发生过, 只是结果还没出来; 把它从次数里也抹掉会让"这只票出现过几次"
    这个最基本的问题都答错。
    """
    agg: dict = {}
    for e in eps:
        a = agg.setdefault(e["key"], {"key": e["key"], "n": 0, "days": 0,
                                      "scored": 0, "sum": 0.0, "win": 0})
        a["n"] += 1
        a["days"] += e["days"]
        if e["fwd"] is not None:
            a["scored"] += 1
            a["sum"] += e["fwd"]
            a["win"] += 1 if e["fwd"] > 0 else 0
    out = []
    for a in agg.values():
        out.append({
            "key": a["key"],
            "label": label_of(a["key"]),
            "n": a["n"],                                    # 出现过几段
            "avg_days": round(a["days"] / a["n"], 1),       # 平均持续几天
            "scored": a["scored"],                          # 其中几段已知结果
            "avg_fwd": round(a["sum"] / a["scored"], 4) if a["scored"] else None,
            "win": a["win"],
        })
    out.sort(key=lambda x: -x["n"])
    return out


def _trend_outcomes(rows: list[dict], closes: list[float], offset: int) -> list[dict]:
    """[R177] 六态各状态在这只票上出现过几段、之后怎么走。

    「趋势状态」这一列原来只统计了"涨停出现在什么状态下"; 那回答的是另一个
    问题。这里补上真正该问的: **每种状态之后普遍怎么走。**
    """
    eps = _episodes(rows, lambda r: (r.get("trend") or {}).get("state"),
                    closes, offset, FORWARD_DAYS)
    return _agg_episodes(eps, lambda k: STATE_LABELS.get(k, (k, ""))[0])


def _outcomes(rows: list[dict], closes: list[float], offset: int) -> list[dict]:
    """每种结论在这只票上出现过几**段**、之后 FORWARD_DAYS 走成什么样。

    这是复盘真正想问的那个问题 —— 「结论」列说的话, 在**这只票**身上过去
    好不好使。样本小得很(半年内同一档往往只有个位数), 所以只报次数和均值,
    不折算成胜率百分比去装得像统计结论。

    [R177] 从按天改成**按段**。原来一段持续 5 天的"强势深调"会被算成 5 个
    样本, 而这 5 天的前瞻窗口互相重叠 4 天 —— n 被撑大了, 一个很薄的结论
    看着挺扎实。改完之后数字更小, 但那个更小的数字才是真的。
    """
    title_tone: dict[str, tuple[str, str]] = {}
    for r in rows:
        v = r.get("verdict")
        if v:
            title_tone.setdefault(v["code"], (v["title"], v["tone"]))

    eps = _episodes(rows, lambda r: (r.get("verdict") or {}).get("code"),
                    closes, offset, FORWARD_DAYS)
    out = _agg_episodes(eps, lambda k: title_tone.get(k, (k, ""))[0])
    for o in out:
        o["code"] = o["key"]
        o["title"] = o["label"]
        o["tone"] = title_tone.get(o["key"], ("", "info"))[1]
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
        # [R177] 「趋势状态」那一栏的同类统计 —— 原来那栏只有"涨停出在什么状态下",
        # 回答的是另一个问题; 这条补上"每种状态之后普遍怎么走"
        "trend_outcomes": _trend_outcomes(rows, closes, offset),
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
