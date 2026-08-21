"""[fork 增强] R59 AI 操盘手 HTTP 接口。

一个操作员 = 一个模型。跑一次决策 = 拿这套系统当天的信息问它一次, 把它给的
单子按 A 股规矩撮合入账。所有操作都留痕, 长期看下来就知道这套系统给的信息
够不够一个模型据以赚钱。
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.services import paper_trader as pt

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/paper-trading", tags=["paper-trading"])


def _book_summary(t: dict, scope: str, prices: dict[str, float]) -> dict:
    bk = pt.book(t, scope)
    # 收益率各按各本账自己的本金算 —— 两本设成不同的数也照样可比
    init = float(bk.get("initial_capital") or 0) or 1.0
    cur = pt.nav(bk, prices)
    return {
        "scope": scope, "scope_cn": pt.SCOPE_CN[scope],
        "initial_capital": init,
        "cash": round(float(bk.get("cash") or 0), 2),
        "nav": round(cur, 2), "return_pct": round(cur / init - 1, 4),
        "positions_count": len(bk.get("positions") or {}),
        "orders_count": len(bk.get("orders") or []),
        "days": len(bk.get("nav_history") or []),
        "last_run_at": bk.get("last_run_at"),
        "last_error": bk.get("last_error") or "",
        "last_note": bk.get("last_note") or "",
    }


def _summary(t: dict, prices: dict[str, float]) -> dict:
    """列表用的投影 —— 不带 orders/nav_history 全量, 那两个会长到几百 KB。

    两本账并排返回: 这一页要回答的就是"同一个模型, 全市场 vs 我的自选,
    哪边走得好" —— 分开两次请求会让人下意识只看其中一边。
    """
    return {
        "id": t.get("id"), "name": t.get("name"), "profile_id": t.get("profile_id"),
        "created_at": t.get("created_at"),
        "max_positions": pt.clamp_max_positions(t.get("max_positions")),
        "schedule": t.get("schedule") or {"enabled": False, "hour": 15, "minute": 30},
        "books": [_book_summary(t, sc, prices) for sc in pt.SCOPES],
    }


def _all_prices(repo, traders: list[dict]) -> dict[str, float]:
    from app.services.paper_trader_run import latest_prices
    syms: list[str] = []
    for t in traders:
        for sc in pt.SCOPES:
            syms.extend((pt.book(t, sc).get("positions") or {}).keys())
    return latest_prices(repo, syms)


@router.get("/traders")
def list_traders(request: Request) -> dict[str, Any]:
    """操作员一览 + 各自的成绩。这就是「谁用同一份信息做得更好」那张表。"""
    rows = pt.list_traders()
    prices = _all_prices(request.app.state.repo, rows)
    return {"traders": [_summary(t, prices) for t in rows]}


class TraderIn(BaseModel):
    """name 应当就是模型名 —— 这张表要回答的是哪个模型做得更好。

    capital 是**两本账各自**的初始资金(开的时候给同一个数, 之后可以分别改)。
    """
    name: str = ""
    profile_id: str
    capital: float = Field(pt.DEFAULT_CAPITAL, gt=0)
    max_positions: int = Field(pt.DEFAULT_MAX_POSITIONS, ge=1, le=pt.MAX_POSITIONS_CAP)


@router.post("/traders")
def create_trader(req: TraderIn) -> dict[str, Any]:
    from app import secrets_store

    profiles = {p["id"]: p for p in secrets_store.list_ai_profiles()}
    prof = profiles.get(req.profile_id)
    if prof is None:
        raise HTTPException(status_code=400, detail="选的 AI 档位不存在, 先去设置里配一个")
    # 名字缺省用模型名 —— 这张表比的就是模型
    name = req.name.strip() or prof.get("model") or prof.get("label") or req.profile_id
    try:
        return pt.create(name=name, profile_id=req.profile_id, capital=req.capital,
                         max_positions=req.max_positions)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _scope_or_400(scope: str) -> str:
    if scope not in pt.SCOPES:
        raise HTTPException(status_code=400, detail=f"分组只能是 {'/'.join(pt.SCOPES)}")
    return scope


@router.get("/traders/{trader_id}/books/{scope}")
def get_book(trader_id: str, scope: str, request: Request) -> dict[str, Any]:
    """单个操作员的全部家当: 持仓 / 成交流水 / 净值曲线。

    **只返回这一个操作员的东西** —— 界面上也不该有个地方能一眼看到所有人的
    持仓明细, 那样我自己看完再去调提示词, 就把隔离破坏掉了。
    """
    _scope_or_400(scope)
    t = pt.get(trader_id)
    if t is None:
        raise HTTPException(status_code=404, detail="操作员不存在")
    bk = pt.book(t, scope)
    prices = _all_prices(request.app.state.repo, [t])
    positions = []
    for sym, pos in (bk.get("positions") or {}).items():
        px = prices.get(sym)
        cost = float(pos.get("cost") or 0)
        positions.append({
            "symbol": sym, "shares": int(pos.get("shares") or 0), "cost": cost,
            "price": px, "opened_on": pos.get("opened_on"),
            "pnl_pct": (round(px / cost - 1, 4) if px and cost else None),
            "market_value": round((px or 0) * int(pos.get("shares") or 0), 2),
        })
    positions.sort(key=lambda p: -(p["market_value"] or 0))
    return {
        "id": t.get("id"), "name": t.get("name"),
        "max_positions": pt.clamp_max_positions(t.get("max_positions")),
        **_book_summary(t, scope, prices),
        "positions": positions,
        # 新 → 旧: 打开先看到最近做了什么
        "orders": list(reversed(bk.get("orders") or []))[:300],
        "nav_history": bk.get("nav_history") or [],
    }


@router.post("/traders/{trader_id}/books/{scope}/run")
async def run_book(trader_id: str, scope: str, request: Request) -> dict[str, Any]:
    """让这个操作员的某一本账按今天的信息做一次决策。"""
    from app.services import paper_trader_run

    _scope_or_400(scope)
    t = pt.get(trader_id)
    if t is None:
        raise HTTPException(status_code=404, detail="操作员不存在")
    try:
        return await paper_trader_run.run_once(request.app.state.repo, t, scope)
    except Exception as exc:  # noqa: BLE001
        # 失败也要记在这本账上 —— 长期观察时"那天没跑成"和"那天没交易"是两件事,
        # 混在一起会把模型的表现记错。
        bk = pt.book(t, scope)
        bk["last_error"] = str(exc)[:300]
        bk["last_run_at"] = pt.now_iso()
        pt.save(t)
        raise HTTPException(status_code=502, detail=str(exc)[:300]) from exc


@router.post("/traders/{trader_id}/books/{scope}/lifeline")
def run_lifeline(trader_id: str, scope: str, request: Request) -> dict[str, Any]:
    """[R61] 生命线检查 —— 这一路**不问 AI**。

    跌破 20 日线是硬纪律, 让模型有机会"再看看"就等于把纪律变成建议。
    这也是整个操盘手里唯一允许用实时价的地方: 等到收盘再处理往往已经又跌一截。
    """
    from app.services import paper_trader_run
    from app.services.live_quotes import watchlist_live_map

    _scope_or_400(scope)
    t = pt.get(trader_id)
    if t is None:
        raise HTTPException(status_code=404, detail="操作员不存在")
    live = watchlist_live_map(request.app.state.repo)
    forced = paper_trader_run.check_lifelines(request.app.state.repo, t, scope, live=live)
    return {"forced": forced, "count": len(forced)}


class TraderSettingsIn(BaseModel):
    """[R63] 操作员级设置。持仓只数上限对两本账一视同仁 —— 两本要对照,
    这个数就得对齐, 分开设会让"谁做得好"变成"谁被允许更分散"。"""
    max_positions: int = Field(pt.DEFAULT_MAX_POSITIONS, ge=1, le=pt.MAX_POSITIONS_CAP)


@router.put("/traders/{trader_id}/settings")
def set_trader_settings(trader_id: str, req: TraderSettingsIn) -> dict[str, Any]:
    # [R68] 走 mutate 而不是 get→改→save: 改设置的请求会成串地来(输入框每动
    # 一下算一次), 各自捧着一份旧副本回写的话, 后写的那个会把前一个盖掉
    def _do(t: dict) -> None:
        t["max_positions"] = pt.clamp_max_positions(req.max_positions)

    t, _ = pt.mutate(trader_id, _do)
    if t is None:
        raise HTTPException(status_code=404, detail="操作员不存在")
    return {"ok": True, "max_positions": t["max_positions"]}


class BookCapitalIn(BaseModel):
    """[R63] 单本账的本金。两本各自可设 —— 比如全市场那本给多一点看分散效果。"""
    initial_capital: float = Field(..., gt=0)


@router.put("/traders/{trader_id}/books/{scope}/capital")
def set_book_capital(trader_id: str, scope: str, req: BookCapitalIn) -> dict[str, Any]:
    """改本金。**同时把这本账重置到起跑线** —— 中途换本金而不重来的话,
    收益率的分母变了但历史成交还在, 那条曲线就再也读不懂了。
    """
    _scope_or_400(scope)

    def _do(t: dict) -> None:
        pt.book(t, scope)                   # 确保迁移过
        t["books"][scope] = pt.new_book(float(req.initial_capital))

    t, _ = pt.mutate(trader_id, _do)
    if t is None:
        raise HTTPException(status_code=404, detail="操作员不存在")
    return {"ok": True, "scope": scope, "initial_capital": float(req.initial_capital)}


class ScheduleIn(BaseModel):
    """[R61] 定时: 每天几点自己跑一次。建议收盘后 —— 收盘价出来了才有得算。"""
    enabled: bool = False
    hour: int = Field(15, ge=0, le=23)
    minute: int = Field(30, ge=0, le=59)


@router.put("/traders/{trader_id}/schedule")
def set_schedule(trader_id: str, req: ScheduleIn, request: Request) -> dict[str, Any]:
    def _do(t: dict) -> None:
        t["schedule"] = req.model_dump()

    t, _ = pt.mutate(trader_id, _do)
    if t is None:
        raise HTTPException(status_code=404, detail="操作员不存在")
    _reinstall_schedules(request)
    return {"ok": True, "schedule": t["schedule"]}


def _reinstall_schedules(request: Request) -> None:
    """改完定时立刻重装 —— 不重装的话要等下次重启才生效, 而"我明明关了它还在跑"
    是最难自证的那类问题(还在持续烧 AI 额度)。"""
    scheduler = getattr(request.app.state, "scheduler", None)
    if scheduler is None:
        return
    try:
        from app.services import paper_trader_schedule
        paper_trader_schedule.install(scheduler, request.app.state.repo)
    except Exception:  # noqa: BLE001
        logger.warning("重装操盘手定时失败", exc_info=True)


@router.post("/traders/{trader_id}/reset")
def reset_trader(trader_id: str, scope: str | None = None) -> dict[str, Any]:
    """不给 scope 就是两本账一起重置。"""
    if scope is not None:
        _scope_or_400(scope)
    t = pt.reset(trader_id, scope)
    if t is None:
        raise HTTPException(status_code=404, detail="操作员不存在")
    return {"ok": True}


@router.delete("/traders/{trader_id}")
def delete_trader(trader_id: str, request: Request) -> dict[str, Any]:
    if not pt.delete(trader_id):
        raise HTTPException(status_code=404, detail="操作员不存在")
    # 人删了定时也要摘掉, 否则它继续按点跑一个已经不存在的操作员
    _reinstall_schedules(request)
    return {"deleted": trader_id}


@router.get("/traders/{trader_id}/books/{scope}/context")
def preview_context(trader_id: str, scope: str, request: Request) -> dict[str, Any]:
    """看一眼这个操作员**这次会拿到什么信息**。

    这是这个功能的自检入口: 要判断"系统给的信息够不够", 先得看清楚到底给了
    什么。也是核对隔离有没有破的地方 —— 别人的东西一个字都不该出现在这里。
    """
    from app.services import paper_trader_run

    _scope_or_400(scope)
    t = pt.get(trader_id)
    if t is None:
        raise HTTPException(status_code=404, detail="操作员不存在")
    return {"context": paper_trader_run.build_context(request.app.state.repo, t, scope),
            "system_prompt": paper_trader_run.SYSTEM_PROMPT}
