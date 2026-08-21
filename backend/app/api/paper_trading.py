"""[fork 增强] R59 AI 操盘手 HTTP 接口。

一个操作员 = 一个模型。跑一次决策 = 拿这套系统当天的信息问它一次, 把它给的
单子按 A 股规矩撮合入账。所有操作都留痕, 长期看下来就知道这套系统给的信息
够不够一个模型据以赚钱。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.services import paper_trader as pt

router = APIRouter(prefix="/api/paper-trading", tags=["paper-trading"])


def _summary(t: dict, prices: dict[str, float]) -> dict:
    """列表用的投影 —— 不带 orders/nav_history 全量, 那两个会长到几百 KB。"""
    cur = pt.nav(t, prices)
    init = float(t.get("initial_capital") or 0) or 1.0
    hist = t.get("nav_history") or []
    return {
        "id": t.get("id"), "name": t.get("name"), "profile_id": t.get("profile_id"),
        "initial_capital": init, "cash": round(float(t.get("cash") or 0), 2),
        "nav": round(cur, 2), "return_pct": round(cur / init - 1, 4),
        "positions_count": len(t.get("positions") or {}),
        "orders_count": len(t.get("orders") or []),
        "days": len(hist),
        "created_at": t.get("created_at"), "last_run_at": t.get("last_run_at"),
        "last_error": t.get("last_error") or "", "last_note": t.get("last_note") or "",
    }


def _all_prices(repo, traders: list[dict]) -> dict[str, float]:
    from app.services.paper_trader_run import latest_prices
    syms: list[str] = []
    for t in traders:
        syms.extend((t.get("positions") or {}).keys())
    return latest_prices(repo, syms)


@router.get("/traders")
def list_traders(request: Request) -> dict[str, Any]:
    """操作员一览 + 各自的成绩。这就是「谁用同一份信息做得更好」那张表。"""
    rows = pt.list_traders()
    prices = _all_prices(request.app.state.repo, rows)
    return {"traders": [_summary(t, prices) for t in rows]}


class TraderIn(BaseModel):
    """name 应当就是模型名 —— 这张表要回答的是哪个模型做得更好。"""
    name: str = ""
    profile_id: str
    capital: float = Field(pt.DEFAULT_CAPITAL, gt=0)


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
        return pt.create(name=name, profile_id=req.profile_id, capital=req.capital)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/traders/{trader_id}")
def get_trader(trader_id: str, request: Request) -> dict[str, Any]:
    """单个操作员的全部家当: 持仓 / 成交流水 / 净值曲线。

    **只返回这一个操作员的东西** —— 界面上也不该有个地方能一眼看到所有人的
    持仓明细, 那样我自己看完再去调提示词, 就把隔离破坏掉了。
    """
    t = pt.get(trader_id)
    if t is None:
        raise HTTPException(status_code=404, detail="操作员不存在")
    prices = _all_prices(request.app.state.repo, [t])
    positions = []
    for sym, pos in (t.get("positions") or {}).items():
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
        **_summary(t, prices),
        "positions": positions,
        # 新 → 旧: 打开先看到最近做了什么
        "orders": list(reversed(t.get("orders") or []))[:300],
        "nav_history": t.get("nav_history") or [],
    }


@router.post("/traders/{trader_id}/run")
async def run_trader(trader_id: str, request: Request) -> dict[str, Any]:
    """让这个操作员按今天的信息做一次决策。"""
    from app.services import paper_trader_run

    t = pt.get(trader_id)
    if t is None:
        raise HTTPException(status_code=404, detail="操作员不存在")
    try:
        return await paper_trader_run.run_once(request.app.state.repo, t)
    except Exception as exc:  # noqa: BLE001
        # 失败也要记在这个操作员身上 —— 长期观察时"那天没跑成"和"那天没交易"
        # 是两件事, 混在一起会把模型的表现记错。
        t["last_error"] = str(exc)[:300]
        t["last_run_at"] = pt.now_iso()
        pt.save(t)
        raise HTTPException(status_code=502, detail=str(exc)[:300]) from exc


@router.post("/traders/{trader_id}/reset")
def reset_trader(trader_id: str) -> dict[str, Any]:
    t = pt.reset(trader_id)
    if t is None:
        raise HTTPException(status_code=404, detail="操作员不存在")
    return {"ok": True}


@router.delete("/traders/{trader_id}")
def delete_trader(trader_id: str) -> dict[str, Any]:
    if not pt.delete(trader_id):
        raise HTTPException(status_code=404, detail="操作员不存在")
    return {"deleted": trader_id}


@router.get("/traders/{trader_id}/context")
def preview_context(trader_id: str, request: Request) -> dict[str, Any]:
    """看一眼这个操作员**这次会拿到什么信息**。

    这是这个功能的自检入口: 要判断"系统给的信息够不够", 先得看清楚到底给了
    什么。也是核对隔离有没有破的地方 —— 别人的东西一个字都不该出现在这里。
    """
    from app.services import paper_trader_run

    t = pt.get(trader_id)
    if t is None:
        raise HTTPException(status_code=404, detail="操作员不存在")
    return {"context": paper_trader_run.build_context(request.app.state.repo, t),
            "system_prompt": paper_trader_run.SYSTEM_PROMPT}
