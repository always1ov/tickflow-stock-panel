"""[fork 增强] 今日总览的"中观层": 主线归属 + 中观快照。

三层推导 `大盘 → 主线 → 个股` 里, 系统原本只有第一层(市场天气/大盘红绿灯)
和第三层(六态趋势 + AI 信号), 中间那层是空的 —— 于是"这只票凭什么值得买"
永远只能答到"它自己形态好", 答不了"它站没站在今天最强的那条线上"。

本模块把两份**已有**的日频时序接进今日总览, 不新增任何计算源:
  · market_mainline  涨停梯队聚合出的每日主线排行(概念口径)
  · regime_builder   全市场涨跌家数与两市成交额

刻意不做的两件事:
  1. **不因"不在主线内"扣分。** 主线是从涨停梯队推出来的, 只覆盖市场里最
     躁动的那一小撮。一只慢牛票所在概念可以整年零涨停, 扣它的分等于系统性
     偏向妖股。所以只加分不减分 —— 在主线里是加成, 不在只是没有加成。
  2. **数据陈旧就不给分。** 主线依赖涨停梯队跑批, 停更几天后"当前主线"其实
     是上周的主线。超过 MAX_AGE_DAYS 只展示并标记 stale, 不参与打分。

口径限制随 market_mainline.MEMBERSHIP_NOTE 一并返回: 概念成分是当前快照回看
历史, 越近越准。今日总览用的就是最近一天, 属于该口径最可靠的一端。
"""
from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import date, datetime

import polars as pl

logger = logging.getLogger(__name__)

# 进入"当前主线"的名次上限。取 5 是因为主升阶段真正有梯队的概念通常就 3-5 条,
# 放宽到 10 会把只有 3 家涨停的边缘概念也叫成"主线", 加成就不值钱了。
TOP_N = 5
# 主线数据最多容忍几个自然日没更新(跨周末 + 一个节假日)
MAX_AGE_DAYS = 7
# 成交额分位的回看窗口(交易日)。250 ≈ 一年
AMOUNT_WINDOW = 250
# 给出分位至少要有的样本数, 少于此只报绝对值
_MIN_AMOUNT_SAMPLE = 20

# 名次 → 把握分加成。差距做小(12/10/8/5): 主线归属是"锦上添花"的佐证,
# 不该盖过趋势本身与量价 —— 第一主线里的烂形态不该排在第三主线里的好形态前面。
_RANK_BONUS = {1: 12, 2: 10, 3: 8}
_TAIL_BONUS = 5


def _as_date(v: object) -> date | None:
    """把 polars/字符串/日期对象统一成 date; 认不出返回 None。"""
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v)[:10])
    except (TypeError, ValueError):
        return None


def latest_mainlines(hist: pl.DataFrame | None, *, top_n: int = TOP_N,
                     today: date | None = None,
                     max_age_days: int = MAX_AGE_DAYS) -> dict | None:
    """取主线时序里最后一天的前 top_n 条。纯函数(只读传入的 df)。

    返回 {"date", "age_days", "stale", "rows"}; 数据不可用返回 None。
    stale=True 时调用方应只展示不打分 —— 停更几天后的"当前主线"是上周的主线。
    """
    if hist is None or hist.is_empty():
        return None
    if not {"date", "member", "rank"} <= set(hist.columns):
        return None
    d = _as_date(hist["date"].max())
    if d is None:
        return None
    age = ((today or date.today()) - d).days
    sub = hist.filter(pl.col("date") == hist["date"].max()).sort("rank")
    rows = []
    for r in sub.head(max(1, top_n)).to_dicts():
        member = str(r.get("member") or "").strip()
        if not member:
            continue
        leader = r.get("leader_symbol")
        rows.append({
            "member": member,
            "rank": int(r["rank"]),
            "score": round(float(r["score"]), 1) if r.get("score") is not None else None,
            "limit_up_count": int(r.get("limit_up_count") or 0),
            "max_boards": int(r.get("max_boards") or 0),
            "leader_symbol": str(leader).upper() if leader else None,
        })
    if not rows:
        return None
    return {"date": d.isoformat(), "age_days": age,
            "stale": age > max_age_days, "rows": rows}


def tag_symbols(map_df: pl.DataFrame | None, syms: Sequence[str],
                rows: Sequence[dict], *, kind: str = "concept") -> dict[str, dict]:
    """给候选票打上主线归属, 返回 {SYMBOL: {member, rank, limit_up_count, also}}。

    一只票常同时属于多个概念(如"人形机器人"+"减速器"), 取名次最靠前的那条当
    主归属, 其余放进 also 供 tooltip 展示 —— 只报一条会让用户以为系统漏看了。
    纯函数。
    """
    if map_df is None or map_df.is_empty() or not rows or not syms:
        return {}
    if not {"_sym_up", kind} <= set(map_df.columns):
        return {}
    by_member = {r["member"]: r for r in rows}
    syms_up = sorted({str(s).upper() for s in syms if s})
    if not syms_up:
        return {}
    sub = map_df.filter(
        pl.col("_sym_up").is_in(syms_up) & pl.col(kind).is_in(sorted(by_member))
    )
    if sub.is_empty():
        return {}
    hits: dict[str, list[dict]] = {}
    for r in sub.select(["_sym_up", kind]).unique().to_dicts():
        info = by_member.get(str(r[kind]))
        if info:
            hits.setdefault(str(r["_sym_up"]), []).append(info)
    out: dict[str, dict] = {}
    for sym, ms in hits.items():
        ms = sorted(ms, key=lambda x: x["rank"])
        best = ms[0]
        out[sym] = {
            "member": best["member"],
            "rank": best["rank"],
            "limit_up_count": best["limit_up_count"],
            "also": [m["member"] for m in ms[1:3]],
        }
    return out


def mainline_bonus(rank: int | None) -> int:
    """名次 → 把握分加成。纯函数。"""
    if rank is None:
        return 0
    try:
        return _RANK_BONUS.get(int(rank), _TAIL_BONUS)
    except (TypeError, ValueError):
        return 0


def format_amount(v: float) -> str:
    """成交额(元)转中文单位。"""
    v = float(v)
    if v >= 1e12:
        return f"{v / 1e12:.2f} 万亿"
    if v >= 1e8:
        return f"{v / 1e8:,.0f} 亿"
    if v >= 1e4:
        return f"{v / 1e4:,.0f} 万"
    return f"{v:,.0f}"


def _amount_label(pct: float) -> str:
    if pct >= 0.85:
        return "显著放量"
    if pct >= 0.6:
        return "量能偏暖"
    if pct <= 0.15:
        return "地量"
    if pct <= 0.4:
        return "量能偏冷"
    return "量能中性"


def amount_snapshot(amounts: Sequence[float | None], *,
                    window: int = AMOUNT_WINDOW) -> dict | None:
    """最新两市成交额 + 它在近 window 个交易日中的分位。纯函数。

    amounts 按日期升序, 末位为最新。分位是"历史上有多少天比今天小",
    只拿末位之前的样本比 —— 把今天算进分母会让分位天然偏低。
    样本不足 _MIN_AMOUNT_SAMPLE 时只报绝对值, 不硬凑一个没意义的分位。
    """
    vals = [float(a) for a in amounts if a is not None and float(a) > 0]
    if not vals:
        return None
    latest = vals[-1]
    hist = vals[-window:][:-1]
    snap: dict = {"total": latest, "text": format_amount(latest),
                  "pct_rank": None, "label": None, "sample": len(hist)}
    if len(hist) >= _MIN_AMOUNT_SAMPLE:
        pct = sum(1 for v in hist if v < latest) / len(hist)
        snap["pct_rank"] = round(pct, 3)
        snap["label"] = _amount_label(pct)
    return snap


# ---------------------------------------------------------------- IO 组装

def build_meso(repo, *, today: date | None = None, kind: str = "concept") -> dict | None:
    """组装中观快照: 成交额分位 + 涨跌家数 + 当前主线前 TOP_N。

    任一子块缺失只是那块为 None, 不拖垮整个快照 —— 主线跑批没跑过的用户
    仍然该看到成交额与涨跌家数。全都取不到才返回 None。
    """
    from app.services.market_mainline import MEMBERSHIP_NOTE, load_mainline_history

    mainline = None
    try:
        hist = load_mainline_history(repo.store.data_dir, kind=kind)
        mainline = latest_mainlines(hist, today=today)
    except Exception as e:  # noqa: BLE001
        logger.debug("today meso mainline skipped: %s", e)

    amount = None
    breadth = None
    try:
        from app.services.regime_builder import load_regime_history
        rh = load_regime_history(repo.store.data_dir)
        if not rh.is_empty() and "date" in rh.columns:
            rh = rh.sort("date")
            if "total_amount" in rh.columns:
                amount = amount_snapshot(rh["total_amount"].to_list())
                if amount:
                    amount["date"] = str(rh["date"].to_list()[-1])[:10]
            if {"up_count", "down_count"} <= set(rh.columns):
                last = rh.tail(1).to_dicts()[0]
                up_n, dn_n = int(last["up_count"] or 0), int(last["down_count"] or 0)
                if up_n + dn_n > 0:
                    breadth = {"up": up_n, "down": dn_n,
                               "date": str(last["date"])[:10]}
    except Exception as e:  # noqa: BLE001
        logger.debug("today meso regime skipped: %s", e)

    if not (mainline or amount or breadth):
        return None
    return {
        "amount": amount,
        "breadth": breadth,
        "mainline": mainline,
        "membership_note": MEMBERSHIP_NOTE,
    }


def tags_for(repo, syms: Sequence[str], mainline: dict | None, *,
             kind: str = "concept") -> dict[str, dict]:
    """候选票 → 主线归属。mainline 为空或已陈旧时返回 {} (陈旧数据不打分)。"""
    if not mainline or mainline.get("stale") or not syms:
        return {}
    try:
        from app.services.rps_rotation import _load_concept_map_df
        map_df, _ = _load_concept_map_df(repo, kind)
        return tag_symbols(map_df, syms, mainline["rows"], kind=kind)
    except Exception as e:  # noqa: BLE001
        logger.debug("today mainline tags skipped: %s", e)
        return {}
