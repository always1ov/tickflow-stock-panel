"""异动监控 API — 竞价/盘中/偏移三类异动。

- /intraday: 盘中量价信号聚合 (enriched 当日信号列, 零新增采集)
- /overview: 偏移异动边缘总览 (交易所异动规则口径的接近度)
- /auction-scan: [fork R110] 竞价一进二 (昨日首板 × 当下竞价快照评分)
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from app.services.abnormal_moves import build_intraday, build_overview

router = APIRouter(prefix="/api/abnormal", tags=["abnormal"])


@router.get("/intraday")
def abnormal_intraday(
    request: Request,
    limit: int = Query(500, ge=1, le=2000),
):
    """盘中异动: 涨停/炸板/跌停翘板/跌停/新高/新低/放量 信号命中行。"""
    repo = request.app.state.repo
    return build_intraday(repo, limit=limit)


@router.get("/overview")
def abnormal_overview(
    request: Request,
    min_closeness: float = Query(0.5, ge=0.0, le=1.0),
    limit: int = Query(200, ge=1, le=1000),
):
    """异动边缘总览: 规则表 + 各窗口实时偏离 + 接近度排序。

    min_closeness: 0.5=观察 / 0.7=边缘 / 1.0=已触发。
    """
    repo = request.app.state.repo
    quote_service = getattr(request.app.state, "quote_service", None)
    return build_overview(repo, quote_service, min_closeness=min_closeness, limit=limit)


# ===== [fork 增强] R110 竞价一进二扫描 =====

@router.get("/auction-scan")
def auction_scan(request: Request, refresh: bool = False) -> dict:
    """竞价一进二候选: 昨日首板 × 当下竞价快照评分。

    refresh=False(默认): 读当日已落盘的扫描结果, 没有则返回空态(不打数据源);
    refresh=True: 现拉一次全市场快照重算并落盘 —— 竞价数据无历史接口,
    盘前 9:15-9:25 点一次才有当天的数据, 之后即为当日定格。
    """
    from datetime import date as _date

    from app.services import auction_scan as svc

    repo = request.app.state.repo
    data_dir = repo.store.data_dir
    today = _date.today()

    if not refresh:
        cached = svc.load_scan(data_dir, today)
        if cached:
            return {**cached, "cached": True, "dates": svc.list_scan_dates(data_dir)}
        return {
            "as_of": None, "candidates": [], "cached": False,
            "dates": svc.list_scan_dates(data_dir),
            "hint": "今天还没扫描过 —— 9:15~9:25 竞价阶段点「扫描」才能取到竞价数据",
        }

    # 现拉全市场快照: 走实时数据源抽象(与行情服务同一条链, 不直连 SDK)
    rows: list[dict] = []
    try:
        from app.data_providers import custom as custom_sources
        from app.services import preferences
        provider_name = preferences.get_realtime_data_provider()
        if provider_name != "tickflow" and custom_sources.provider_has_dataset(provider_name, "realtime"):
            rows = custom_sources.get_provider(provider_name).get_realtime() or []
        else:
            qs = getattr(request.app.state, "quote_service", None)
            if qs is not None:
                df = qs.get_quotes_compat()
                rows = df.to_dicts() if df is not None and not df.is_empty() else []
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"取全市场快照失败: {e}") from e

    if not rows:
        raise HTTPException(status_code=503, detail="全市场快照为空 —— 检查实时数据源是否可用")

    payload = svc.scan(repo, rows)
    svc.save_scan(data_dir, payload, today)
    return {**payload, "cached": False, "dates": svc.list_scan_dates(data_dir)}
