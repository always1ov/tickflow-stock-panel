"""[fork 增强] R59 AI 操盘手 —— 让模型自己用这套系统的信息模拟炒股。

目的不是"让 AI 帮我赚钱", 而是**拿它当这套系统的体检**: 如果一个模型只拿本
系统给出的信息就能长期跑出正收益, 说明这些信息确实够用; 跑不出来, 差在哪一
块就是下一步该改的地方。所以每一笔都要留痕 —— 当时看到了什么、为什么这么做。

三条硬约束, 都不是靠提示词客气地"要求"模型遵守, 而是结构上做不到:

1. **只能用系统里的信息**。模型拿到的是一段服务端拼好的纯文本, 没有任何
   工具、没有联网出口 —— 它想去查也没有手。上下文里每一项都注明来自本系统
   的哪个模块, 复盘时能对得上。

2. **操作员之间互相看不见**。上下文按 trader_id 组装, 只读这一个操作员自己的
   持仓与历史; 别人的持仓、成交、理由一个字都不会进来。这条有测试守着 ——
   靠"提示词里叮嘱一句"是守不住的。

3. **撮合按 A 股的规矩**。100 股一手、T+1 当天买的不能卖、按收盘价成交、
   算佣金印花税滑点。放宽任何一条, 跑出来的收益都不能拿来判断系统好不好。

操作员的名字**就是模型名**: 这个表最终要回答的是"哪个模型用这套信息做得更好",
名字里带别的东西只会让人看走眼。
"""
from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

MAX_TRADERS = 8
# 每个操作员留多少条成交 / 多少天净值。留太少就看不出长期效果, 而这个功能
# 的全部意义就在"长期"。
MAX_ORDERS = 2000
MAX_NAV_POINTS = 1000
# 喂回给模型的自己的历史: 太长会挤掉当天的盘面信息, 太短它就记不住自己在做什么
RECENT_ORDERS_IN_CONTEXT = 20

DEFAULT_CAPITAL = 1_000_000.0
LOT = 100                     # A 股一手

# 成本口径与回测页默认值对齐 —— 两处不一样的话, 操盘手的成绩没法和回测比
DEFAULT_COMMISSION = 0.0002   # 双边
DEFAULT_STAMP_TAX = 0.0005    # 卖出单边
DEFAULT_SLIPPAGE_BPS = 5.0

ACTION_BUY = "buy"
ACTION_SELL = "sell"
ACTION_HOLD = "hold"

# [R61] 每个操作员带两本账, 各自独立: 一本在全市场里挑, 一本只在自选里挑。
#
# 这不是"两个功能", 而是这套系统最想问的那个问题的对照组: **我这份自选到底
# 有没有价值**。同一个模型、同一天、同一套信息口径, 一边只能从我圈的票里选,
# 一边可以从全市场选 —— 长期跑下来两条净值曲线的差, 就是我选股这件事的价值。
# 所以两本账必须严格分开: 共用现金或共用持仓, 这个对照就废了。
SCOPE_MARKET = "market"
SCOPE_WATCHLIST = "watchlist"
SCOPES = (SCOPE_MARKET, SCOPE_WATCHLIST)
SCOPE_CN = {SCOPE_MARKET: "全市场", SCOPE_WATCHLIST: "我的自选"}


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _path() -> Path:
    from app.config import settings
    p = settings.data_dir / "user_data" / "paper_traders.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _read() -> dict:
    p = _path()
    if not p.exists():
        return {"traders": []}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        logger.warning("paper_traders.json malformed: %s", e)
        return {"traders": []}
    return data if isinstance(data, dict) else {"traders": []}


def _write(data: dict) -> None:
    _path().write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


# ================================================================
# 账本
# ================================================================

def list_traders() -> list[dict]:
    return [t for t in _read().get("traders") or [] if isinstance(t, dict)]


def get(trader_id: str) -> dict | None:
    for t in list_traders():
        if t.get("id") == trader_id:
            return t
    return None


def create(*, name: str, profile_id: str, capital: float = DEFAULT_CAPITAL) -> dict:
    """开一个操作员。name 应当就是模型名 —— 这张表要回答的是哪个模型做得更好。"""
    rows = list_traders()
    if len(rows) >= MAX_TRADERS:
        raise ValueError(f"最多 {MAX_TRADERS} 个操作员")
    cap = float(capital or DEFAULT_CAPITAL)
    if cap <= 0:
        raise ValueError("初始资金要大于 0")
    trader = {
        "id": uuid.uuid4().hex[:12],
        "name": str(name or "").strip() or profile_id,
        "profile_id": str(profile_id or ""),
        "initial_capital": cap,
        # 两本账各自一份初始资金 —— 要比的是同样的钱在两个选股范围里怎么走,
        # 分一份钱给两边会让两条曲线互相牵制, 那就不是对照了
        "books": {sc: new_book(cap) for sc in SCOPES},
        # [R61] 定时: 每天几点自己跑一次。收盘后跑才有当天的收盘价可用。
        "schedule": {"enabled": False, "hour": 15, "minute": 30},
        "enabled": True,
        "created_at": now_iso(),
    }
    rows.append(trader)
    _write({"traders": rows})
    return trader


def new_book(capital: float) -> dict:
    return {"cash": float(capital), "positions": {}, "orders": [], "nav_history": [],
            "last_run_at": None, "last_error": "", "last_note": ""}


def book(trader: dict, scope: str) -> dict:
    """取某一本账。老数据(只有一本平铺的账)在这里就地迁移进 watchlist ——
    之前那版的上下文本来就是自选口径, 记到全市场那本会把成绩安到错误的对照组上。"""
    if scope not in SCOPES:
        raise ValueError(f"未知分组 {scope}")
    books = trader.get("books")
    if not isinstance(books, dict):
        cap = float(trader.get("initial_capital") or DEFAULT_CAPITAL)
        legacy = {
            "cash": float(trader.get("cash", cap)),
            "positions": trader.get("positions") or {},
            "orders": trader.get("orders") or [],
            "nav_history": trader.get("nav_history") or [],
            "last_run_at": trader.get("last_run_at"),
            "last_error": trader.get("last_error") or "",
            "last_note": trader.get("last_note") or "",
        }
        books = {SCOPE_WATCHLIST: legacy, SCOPE_MARKET: new_book(cap)}
        trader["books"] = books
        for k in ("cash", "positions", "orders", "nav_history",
                  "last_run_at", "last_error", "last_note"):
            trader.pop(k, None)
    if scope not in books:
        books[scope] = new_book(float(trader.get("initial_capital") or DEFAULT_CAPITAL))
    return books[scope]


def save(trader: dict) -> dict:
    rows = [t for t in list_traders() if t.get("id") != trader.get("id")]
    for b in (trader.get("books") or {}).values():
        b["orders"] = (b.get("orders") or [])[-MAX_ORDERS:]
        b["nav_history"] = (b.get("nav_history") or [])[-MAX_NAV_POINTS:]
    rows.append(trader)
    rows.sort(key=lambda t: str(t.get("created_at") or ""))
    _write({"traders": rows})
    return trader


def delete(trader_id: str) -> bool:
    rows = list_traders()
    keep = [t for t in rows if t.get("id") != trader_id]
    if len(keep) == len(rows):
        return False
    _write({"traders": keep})
    return True


def reset(trader_id: str, scope: str | None = None) -> dict | None:
    """清空持仓与历史, 回到初始资金。

    单独给一个"重置"而不是让人删了重建: 删掉的话名字、模型、初始资金都要
    重填一遍, 而重新起跑正是这个功能的常规操作(改了系统就想再看一轮)。
    """
    t = get(trader_id)
    if t is None:
        return None
    cap = float(t["initial_capital"])
    if scope is None:
        t["books"] = {sc: new_book(cap) for sc in SCOPES}
    else:
        book(t, scope)          # 先确保迁移过
        t["books"][scope] = new_book(cap)
    return save(t)


# ================================================================
# 撮合
# ================================================================

def _cost_buy(amount: float) -> float:
    return amount * DEFAULT_COMMISSION


def _cost_sell(amount: float) -> float:
    return amount * (DEFAULT_COMMISSION + DEFAULT_STAMP_TAX)


def _fill_price(price: float, side: str) -> float:
    """滑点: 买贵一点、卖便宜一点。两边都按有利方向算等于凭空多赚。"""
    slip = DEFAULT_SLIPPAGE_BPS / 10_000.0
    return price * (1 + slip) if side == ACTION_BUY else price * (1 - slip)


def market_value(bk: dict, prices: dict[str, float]) -> float:
    """bk 是一本账(见 book())—— 撮合与净值全部按账本算, 两本互不相干。"""
    total = 0.0
    for sym, pos in (bk.get("positions") or {}).items():
        px = prices.get(sym)
        if px:
            total += float(px) * int(pos.get("shares") or 0)
    return total


def nav(bk: dict, prices: dict[str, float]) -> float:
    return float(bk.get("cash") or 0.0) + market_value(bk, prices)


def apply_order(bk: dict, *, action: str, symbol: str, shares: int,
                price: float, trade_date: str, reason: str = "") -> dict:
    """执行一笔并记账。返回这一笔的成交记录(被拒时带 rejected 原因)。

    拒单也要留痕 —— "AI 想买但钱不够"和"AI 没想买"是两件完全不同的事,
    只记成交的话复盘时看到的是一个安静的空窗期。
    """
    sym = str(symbol or "").strip().upper()
    entry: dict[str, Any] = {
        "ts": now_iso(), "date": trade_date, "action": action, "symbol": sym,
        "shares": int(shares or 0), "price": round(float(price or 0), 3),
        "reason": str(reason or "")[:300],
    }

    def _reject(why: str) -> dict:
        entry["rejected"] = why
        entry["shares"] = 0
        (bk.setdefault("orders", [])).append(entry)
        return entry

    if action not in (ACTION_BUY, ACTION_SELL):
        return _reject(f"未知操作 {action}")
    if not sym or not price or price <= 0:
        return _reject("没有可用价格")

    lots = int(shares or 0) // LOT * LOT
    if lots <= 0:
        return _reject(f"不足一手({LOT} 股)")

    positions = bk.setdefault("positions", {})
    if action == ACTION_BUY:
        px = _fill_price(price, ACTION_BUY)
        amount = px * lots
        need = amount + _cost_buy(amount)
        if need > float(bk.get("cash") or 0):
            return _reject("现金不够")
        bk["cash"] = float(bk["cash"]) - need
        pos = positions.setdefault(sym, {"shares": 0, "cost": 0.0, "opened_on": trade_date})
        total_cost = float(pos["cost"]) * int(pos["shares"]) + amount
        pos["shares"] = int(pos["shares"]) + lots
        pos["cost"] = round(total_cost / pos["shares"], 4)
        # 当天买入 → T+1 的锚。加仓也要刷新: 新加的那部分当天同样不能卖
        pos["opened_on"] = trade_date
        entry["price"] = round(px, 3)
        entry["shares"] = lots
        entry["amount"] = round(amount, 2)
        return _append(bk, entry)

    pos = positions.get(sym)
    if not pos or int(pos.get("shares") or 0) <= 0:
        return _reject("没有这只票的持仓")
    # T+1: 当天买入的当天不能卖。放宽这条会让模型学会做 T, 而那在 A 股做不到,
    # 跑出来的收益也就没法拿来判断系统好不好。
    if str(pos.get("opened_on") or "") == trade_date:
        return _reject("T+1: 当天买入的不能当天卖")
    lots = min(lots, int(pos["shares"]))
    px = _fill_price(price, ACTION_SELL)
    amount = px * lots
    bk["cash"] = float(bk.get("cash") or 0) + amount - _cost_sell(amount)
    pos["shares"] = int(pos["shares"]) - lots
    if pos["shares"] <= 0:
        positions.pop(sym, None)
    entry["price"] = round(px, 3)
    entry["shares"] = lots
    entry["amount"] = round(amount, 2)
    return _append(bk, entry)


def _append(bk: dict, entry: dict) -> dict:
    (bk.setdefault("orders", [])).append(entry)
    return entry


def mark_nav(bk: dict, prices: dict[str, float], trade_date: str) -> dict:
    """记一个净值点。同一天重复记只更新, 不追加 —— 一天多条会把净值曲线画花。"""
    mv = market_value(bk, prices)
    point = {"date": trade_date, "nav": round(float(bk.get("cash") or 0) + mv, 2),
             "cash": round(float(bk.get("cash") or 0), 2), "market_value": round(mv, 2)}
    hist = bk.setdefault("nav_history", [])
    for i, p in enumerate(hist):
        if p.get("date") == trade_date:
            hist[i] = point
            return point
    hist.append(point)
    return point


# ================================================================
# AI 给的单子 → 结构化
# ================================================================

_JSON_BLOCK = re.compile(r"\{.*\}|\[.*\]", re.S)


def parse_orders(text: str) -> tuple[list[dict], str]:
    """从模型输出里取出单子。返回 (orders, note)。

    模型经常在 JSON 前后写一段话, 或者用 ```json 包起来 —— 这些都要能吃下,
    因为"格式没对上"而丢掉一整天的决策, 会让长期观察出现莫名其妙的空窗。
    解析不出来就返回空单, 由上层记成一次"没交易"并保留原文。
    """
    raw = (text or "").strip()
    if not raw:
        return [], ""
    body = raw
    if "```" in body:
        parts = [p for p in body.split("```") if p.strip()]
        for p in parts:
            cleaned = p.strip()
            if cleaned.lower().startswith("json"):
                cleaned = cleaned[4:].strip()
            if cleaned.startswith(("{", "[")):
                body = cleaned
                break
    m = _JSON_BLOCK.search(body)
    if not m:
        return [], raw[:300]
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return [], raw[:300]

    note = ""
    rows: Any = data
    if isinstance(data, dict):
        note = str(data.get("note") or data.get("comment") or "")[:300]
        rows = data.get("orders") or data.get("trades") or []
    if not isinstance(rows, list):
        return [], note or raw[:300]

    out: list[dict] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        action = str(r.get("action") or r.get("side") or "").strip().lower()
        if action in ("买入", "买"):
            action = ACTION_BUY
        elif action in ("卖出", "卖"):
            action = ACTION_SELL
        if action == ACTION_HOLD:
            continue
        if action not in (ACTION_BUY, ACTION_SELL):
            continue
        sym = str(r.get("symbol") or r.get("code") or "").strip().upper()
        if not sym:
            continue
        try:
            shares = int(float(r.get("shares") or r.get("qty") or 0))
        except (TypeError, ValueError):
            continue
        out.append({"action": action, "symbol": sym, "shares": shares,
                    "reason": str(r.get("reason") or r.get("why") or "")[:300]})
    return out, note
