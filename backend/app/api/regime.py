"""市场环境(regime) API — 时序查询 + 手动重算。

装配逻辑在 app.services.regime_builder(纯函数), API 层薄壳 + TTL 缓存。
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import date
from typing import Annotated, Any

import polars as pl
from fastapi import APIRouter, Query, Request

from app.services import regime_builder

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/regime", tags=["regime"])

_CACHE_TTL = 5.0
_cache: dict[str, Any] | None = None
_cache_ts: float = 0.0
_cache_lock = threading.Lock()


def invalidate_regime_cache() -> None:
    """清空 regime 查询缓存。批算/重算后调用。"""
    global _cache, _cache_ts
    with _cache_lock:
        _cache = None
        _cache_ts = 0.0


def _data_dir(request: Request) -> Any:
    return request.app.state.repo.store.data_dir


def _df_to_records(df) -> list[dict]:
    """polars DataFrame → JSON 安全的 list[dict](date 转 ISO 字符串)。"""
    if df is None or df.is_empty():
        return []
    records = []
    for r in df.to_dicts():
        if "date" in r and r["date"] is not None:
            r["date"] = str(r["date"])
        records.append(r)
    return records


@router.get("/history")
def regime_history(
    request: Request,
    start: date | None = Query(None),
    end: date | None = Query(None),
    limit: int = Query(120, ge=1, le=1000),
):
    """历史环境时序(含状态/指标)。默认最近 N 天。"""
    global _cache, _cache_ts
    cache_key = f"hist|{start}|{end}|{limit}"
    with _cache_lock:
        if (
            _cache is not None
            and _cache.get("key") == cache_key
            and (time.time() - _cache_ts) < _CACHE_TTL
        ):
            return _cache["data"]

    df = regime_builder.load_regime_history(_data_dir(request))
    if df.is_empty():
        result: dict = {"rows": [], "total": 0}
    else:
        if start:
            df = df.filter(pl_col_date(df, ">=", start))
        if end:
            df = df.filter(pl_col_date(df, "<=", end))
        # limit 仅在"最近 N 天"模式(未传 start/end)生效;
        # 日期范围模式(传了 start/end, 如"全部")应返回完整范围, 不截断。
        if start is None and end is None:
            df = df.sort("date", descending=True).head(limit)
        df = df.sort("date")
        rows = _df_to_records(df)
        result = {"rows": rows, "total": len(rows)}

    with _cache_lock:
        _cache = {"key": cache_key, "data": result}
        _cache_ts = time.time()
    return result


def pl_col_date(df, op: str, value: date):
    """polars 日期过滤辅助(避免重复 import)。"""
    import polars as pl

    col = pl.col("date")
    return col >= value if op == ">=" else col <= value


@router.get("/latest")
def regime_latest(request: Request):
    """最新一日环境(轻量)。"""
    df = regime_builder.load_regime_history(_data_dir(request))
    if df.is_empty():
        return {"row": None}
    latest = df.sort("date", descending=True).head(1)
    rows = _df_to_records(latest)
    return {"row": rows[0] if rows else None}


@router.get("/states")
def regime_states(
    request: Request,
    days: int = Query(60, ge=1, le=1000),
):
    """状态分布统计(各状态天数/占比)。"""
    df = regime_builder.load_regime_history(_data_dir(request))
    if df.is_empty():
        return {"distribution": [], "days": 0}
    df = df.sort("date", descending=True).head(days)
    total = df.height
    counts = df.group_by("state").len().sort("len", descending=True)
    distribution = [
        {
            "state": r["state"],
            "label": regime_builder.STATE_LABELS.get(r["state"], r["state"]),
            "count": r["len"],
            "pct": round(r["len"] / total * 100, 1) if total else 0,
        }
        for r in counts.to_dicts()
    ]
    return {"distribution": distribution, "days": total}


@router.get("/coverage")
def regime_coverage(request: Request):
    """regime 数据覆盖元信息(供数据画像)。"""
    return regime_builder.get_regime_coverage(_data_dir(request))


@router.post("/recompute")
def regime_recompute(request: Request, start: date | None = None, end: date | None = None):
    """手动触发重算(全量或指定区间)。管理员操作。

    - 不传 start: 强制全量重算(enriched 最早日 ~ 今天), 覆盖所有已有行。
      与 daily_pipeline 的增量补差(compute_regime_incremental)不同 —— 此接口面向
      人工「我要重新算一遍」的预期, 必须真正重算而非增量补缺口。
    - 传 start: 仅重算 [start, end] 区间。
    - 重算后统一重标情绪周期阶段(refresh_phase_labels)并回填主线
      (概念+行业, 概念成分为当前快照回看历史, 早年有归属漂移)。
    """
    repo = request.app.state.repo
    data_dir = _data_dir(request)
    end = end or date.today()
    # [fork 增强] 分段兜错: 核心重算失败带真实原因返回(而非裸 500);
    # 阶段重标/主线回填是附加步骤, 单独失败降级为 warning, 不拖垮核心结果
    try:
        if start is None:
            # 全量: 从 enriched 最早日强制重算到今天
            earliest = regime_builder.earliest_enriched_date(repo)
            if earliest is None:
                invalidate_regime_cache()
                return {"ok": True, "computed": 0}
            start = earliest
        new_rows = regime_builder.run_regime_batch(repo, start=start, end=end)
        if not new_rows.is_empty():
            regime_builder.upsert_regime_history(data_dir, new_rows)
    except Exception as e:  # noqa: BLE001
        logger.exception("regime recompute failed [%s ~ %s]", start, end)
        invalidate_regime_cache()
        return {"ok": False, "error": f"环境重算失败: {type(e).__name__}: {e}"}

    warnings: list[str] = []
    phase_days = 0
    try:
        phase_days = regime_builder.refresh_phase_labels(data_dir)
    except Exception as e:  # noqa: BLE001
        logger.exception("phase relabel failed")
        warnings.append(f"情绪周期阶段重标失败: {type(e).__name__}: {e}")

    mainline_rows = 0
    try:
        from app.services import market_mainline
        for kind in ("concept", "industry"):
            rows = market_mainline.compute_mainline_range(repo, data_dir, start, end, kind=kind)
            if not rows.is_empty():
                market_mainline.upsert_mainline_history(data_dir, rows)
                mainline_rows += rows.height
    except Exception as e:  # noqa: BLE001
        logger.exception("mainline backfill failed")
        warnings.append(f"主线回填失败: {type(e).__name__}: {e}")

    invalidate_regime_cache()
    return {
        "ok": True,
        "computed": new_rows.height if not new_rows.is_empty() else 0,
        "phase_days": phase_days,
        "mainline_rows": mainline_rows,
        "warnings": warnings or None,
    }


@router.get("/phase/live")
def regime_phase_live(request: Request):
    """[fork 增强] 盘中实时阶段 —— 付费全市场实时档专属, 免费档如实返回不可用。

    口径: 全市场实时 enriched 快照聚合当日涨停生态(首板/2板+/最高板/封板率,
    晋级率用昨日定稿涨停家数做分母)→ 构造当日临时行 → 与 <今日 的定稿序列
    拼接, 跑与盘后完全相同的 classify_phase_series → 当日"盘中临时阶段"。
    收盘定稿为准, 前端须标注盘中口径。免费档/实时未开/快照未就绪时返回
    available=False + 原因, 不影响任何既有功能。
    """
    import polars as pl

    from app.market_time import cn_today
    from app.tickflow.capabilities import Cap

    capset = getattr(request.app.state, "capabilities", None)
    if capset is None or not capset.has(Cap.QUOTE_POOL):
        return {"available": False, "reason": "盘中实时阶段需 Starter+(全市场实时行情)"}
    qs = getattr(request.app.state, "quote_service", None)
    if qs is None:
        return {"available": False, "reason": "行情服务未启动"}
    try:
        df_today, snap_date = qs.get_enriched_today()
    except Exception as e:  # noqa: BLE001
        return {"available": False, "reason": f"实时快照读取失败: {e}"}
    today = cn_today()
    if df_today is None or df_today.is_empty() or snap_date != today:
        return {"available": False, "reason": "今日全市场实时快照未就绪(需开启实时行情)"}
    if "consecutive_limit_ups" not in df_today.columns:
        return {"available": False, "reason": "实时快照缺少连板数据列"}

    clu = df_today["consecutive_limit_ups"].fill_null(0)
    first_board = int((clu == 1).sum())
    ge2_count = int((clu >= 2).sum())
    max_consecutive = int(clu.max() or 0)
    seal_rate = None
    if {"signal_limit_up", "signal_broken_limit_up"} <= set(df_today.columns):
        sealed = int(df_today["signal_limit_up"].fill_null(False).sum())
        broken = int(df_today["signal_broken_limit_up"].fill_null(False).sum())
        if sealed + broken > 0:
            seal_rate = round(sealed / (sealed + broken), 4)

    hist = regime_builder.load_regime_history(_data_dir(request))
    required = {"date", "max_consecutive", "first_board", "ge2_count", "promo_rate", "seal_rate"}
    if hist.is_empty() or not required.issubset(hist.columns):
        return {"available": False, "reason": "阶段历史不足(先在市场环境页重算一次)"}
    base = hist.sort("date").filter(pl.col("date") < today)
    if base.is_empty():
        return {"available": False, "reason": "阶段历史不足"}
    prev = base.tail(1).to_dicts()[0]
    y_limit = int(prev.get("first_board") or 0) + int(prev.get("ge2_count") or 0)
    promo_rate = round(ge2_count / y_limit, 4) if y_limit > 0 else None

    metrics = {
        "first_board": first_board, "ge2_count": ge2_count,
        "max_consecutive": max_consecutive,
        "seal_rate": seal_rate, "promo_rate": promo_rate,
    }
    try:
        from app.services.market_phase import PHASE_LABELS, classify_phase_series
        cols = sorted(required)
        live_row = pl.DataFrame({
            "date": [today], "max_consecutive": [max_consecutive],
            "first_board": [first_board], "ge2_count": [ge2_count],
            "promo_rate": [promo_rate], "seal_rate": [seal_rate],
        })
        seq = pl.concat([base.select(cols), live_row.select(cols)], how="vertical_relaxed")
        labeled = classify_phase_series(seq)
        phase = labeled.sort("date").tail(1)["phase"][0]
    except Exception as e:  # noqa: BLE001
        logger.warning("live phase classify failed: %s", e)
        return {"available": False, "reason": f"盘中阶段判定失败: {e}"}
    return {"available": True, "as_of": str(today), "intraday": True,
            "phase": phase, "phase_label": PHASE_LABELS.get(phase, phase),
            "metrics": metrics}


@router.get("/phases")
def regime_phases(
    request: Request,
    start: date | None = None,
    end: date | None = None,
):
    """情绪周期阶段段列表: 连续同阶段合段, 附段内均值指标与主导主线。

    直接回答「什么阶段走什么主升」: 主升/高潮段的主导主线即该段行情主线。
    主线按段内进入当日 top5 的天数与累计分排序, 取前 3。
    """
    from app.services.market_mainline import load_mainline_history
    from app.services.market_phase import PHASE_LABELS

    data_dir = _data_dir(request)
    df = regime_builder.load_regime_history(data_dir)
    if df.is_empty() or "phase" not in df.columns:
        return {"segments": [], "total": 0}
    if start:
        df = df.filter(pl_col_date(df, ">=", start))
    if end:
        df = df.filter(pl_col_date(df, "<=", end))
    df = df.sort("date")
    if df.is_empty():
        return {"segments": [], "total": 0}

    mainline = load_mainline_history(data_dir, "concept")

    segments: list[dict] = []
    cur: dict | None = None
    for r in df.iter_rows(named=True):
        phase = r.get("phase")
        if cur is None or cur["phase"] != phase:
            cur = {
                "phase": phase,
                "label": PHASE_LABELS.get(phase, phase),
                "start": str(r["date"]),
                "end": str(r["date"]),
                "days": 0,
                "_height": 0.0,
                "_first_board": 0.0,
                "_ge2": 0.0,
                "_promo_sum": 0.0,
                "_promo_n": 0,
                "_seal": 0.0,
            }
            segments.append(cur)
        cur["end"] = str(r["date"])
        cur["days"] += 1
        cur["_height"] += float(r.get("max_consecutive") or 0)
        cur["_first_board"] += float(r.get("first_board") or 0)
        cur["_ge2"] += float(r.get("ge2_count") or 0)
        promo = r.get("promo_rate")
        if promo is not None:
            cur["_promo_sum"] += float(promo)
            cur["_promo_n"] += 1
        cur["_seal"] += float(r.get("seal_rate") or 0)

    for seg in segments:
        n = seg["days"]
        seg["avg_height"] = round(seg.pop("_height") / n, 1)
        seg["avg_first_board"] = round(seg.pop("_first_board") / n, 1)
        seg["avg_ge2"] = round(seg.pop("_ge2") / n, 1)
        seg["avg_promo"] = (
            round(seg.pop("_promo_sum") / seg["_promo_n"], 3) if seg["_promo_n"] else None
        )
        seg.pop("_promo_n")
        seg["avg_seal_rate"] = round(seg.pop("_seal") / n, 3)
        seg["top_mainlines"] = _segment_mainlines(
            mainline, date.fromisoformat(seg["start"]), date.fromisoformat(seg["end"])
        )

    return {"segments": segments, "total": len(segments)}


def _segment_mainlines(mainline: pl.DataFrame, start: date, end: date, top: int = 3) -> list[dict]:
    """段内主导主线: 按进入当日 top5 的天数与累计分排序。"""
    if mainline.is_empty():
        return []
    seg = mainline.filter(
        (pl.col("date") >= start) & (pl.col("date") <= end) & (pl.col("rank") <= 5)
    )
    if seg.is_empty():
        return []
    ranked = (
        seg.group_by("member")
        .agg(
            pl.col("date").n_unique().alias("top5_days"),
            pl.col("score").sum().alias("score_sum"),
            pl.col("max_boards").max().alias("max_boards"),
            pl.col("leader_symbol").first().alias("leader_symbol"),
        )
        .sort(["top5_days", "score_sum"], descending=[True, True])
        .head(top)
    )
    return [
        {
            "member": r["member"],
            "top5_days": r["top5_days"],
            "score_sum": round(r["score_sum"], 1),
            "max_boards": r["max_boards"],
            "leader_symbol": r["leader_symbol"],
        }
        for r in ranked.to_dicts()
    ]


@router.post("/mainline/recompute")
def mainline_recompute(request: Request):
    """全量重算主线(概念+行业), 应用当前过滤配置。窄扫描, 秒级。

    修改过滤配置(preferences mainline-filter)后调用本接口生效,
    无需触发较重的 regime 全量重算。
    """
    from app.services import market_mainline

    repo = request.app.state.repo
    data_dir = _data_dir(request)
    earliest = regime_builder.earliest_enriched_date(repo)
    if earliest is None:
        return {"ok": True, "rows": 0}
    rows = 0
    for kind in ("concept", "industry"):
        computed = market_mainline.compute_mainline_range(
            repo, data_dir, earliest, date.today(), kind=kind
        )
        if not computed.is_empty():
            market_mainline.upsert_mainline_history(data_dir, computed)
            rows += computed.height
    return {"ok": True, "rows": rows}


@router.get("/mainline")
def regime_mainline(
    request: Request,
    start: date | None = None,
    end: date | None = None,
    top: Annotated[int, Query(ge=1, le=30)] = 10,
    kind: Annotated[str, Query(pattern="^(concept|industry)$")] = "concept",
):
    """每日主线排行(截 rank<=top) + 窗口内持续性汇总。

    membership_note 说明概念成分口径(当前快照回看历史)。
    """
    from app.services.market_mainline import MEMBERSHIP_NOTE, load_mainline_history

    try:
        from app.services import preferences

        filter_cfg = preferences.get_mainline_filter_config()
    except Exception:
        filter_cfg = {"min_members": 4, "max_members": 600, "blacklist": []}
    df = load_mainline_history(_data_dir(request), kind)
    if df.is_empty():
        return {"rows": [], "leaders": [], "membership_note": MEMBERSHIP_NOTE, "filter": filter_cfg}
    if start:
        df = df.filter(pl_col_date(df, ">=", start))
    if end:
        df = df.filter(pl_col_date(df, "<=", end))
    df = df.sort(["date", "rank"])
    rows_df = df.filter(pl.col("rank") <= top)
    leaders = (
        df.filter(pl.col("rank") == 1)
        .group_by("member")
        .agg(
            pl.col("date").n_unique().alias("top1_days"),
            pl.col("score").mean().round(1).alias("avg_score"),
            pl.col("max_boards").max().alias("max_boards"),
        )
        .sort(["top1_days", "avg_score"], descending=[True, True])
        .head(10)
    )
    return {
        "rows": _df_to_records(rows_df),
        "leaders": leaders.to_dicts(),
        "membership_note": MEMBERSHIP_NOTE,
        "filter": filter_cfg,
    }
