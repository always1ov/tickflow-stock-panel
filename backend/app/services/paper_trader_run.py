"""[fork 增强] R59 操盘手的一次决策 —— 组上下文 → 问模型 → 撮合入账。

这一层最要紧的是两条隔离, 都是结构上的, 不靠提示词客气地要求:

  · **只喂系统里的信息**。上下文全部由服务端从本地数据拼出来, 模型没有工具、
    没有联网出口, 想去查也没有手。每一块都注明来自哪个模块, 复盘时对得上。
  · **操作员之间互相看不见**。``build_context`` 只按传进来的那一个 trader_id
    读持仓与历史, 别人的持仓/成交/理由一个字都不会进来 —— 有测试守着。

模型只需要回一段 JSON。解析不出来就记成"这天没交易"并留原文, 不硬猜 ——
猜错一笔单子比空一天糟得多。
"""
from __future__ import annotations

import logging
from typing import Any

from app.services import paper_trader as pt

logger = logging.getLogger(__name__)

# 给模型看多少条机会 / 多少只自选。超过这个数上下文会长到把关键信息挤掉,
# 而这套系统本来就已经替它排过序了 —— 让它自己在 150 只里翻是浪费。
MAX_OPPORTUNITIES = 12
MAX_HOLDINGS_SHOWN = 30

SYSTEM_PROMPT = """你是一名 A 股模拟盘操作员。

铁律:
1. 只能依据下面这份「今日信息」做决定。你没有联网能力, 也不许凭记忆使用
   任何外部消息(新闻、公告、传闻、行情网站)。信息里没有的, 就当不知道。
2. 你只看得到自己的账户。不存在其他操作员, 也不要猜别人在做什么。
3. A 股规则: 买卖都以 100 股为单位; 当天买入的当天不能卖(T+1); 按收盘价成交。
4. 现金不够就少买或不买。宁可不动, 不要为了交易而交易。

输出**只回一个 JSON 对象**, 不要写别的:
{"note": "一句话说明今天的整体想法",
 "orders": [{"action": "buy|sell", "symbol": "600000.SH", "shares": 100,
             "reason": "为什么这一笔"}]}
今天什么都不做就给 "orders": []。每一笔都必须写 reason —— 这份记录是拿来
复盘这套系统给的信息够不够用的, 没有理由的成交没有价值。"""


def _fmt_pct(v: Any) -> str:
    try:
        return f"{float(v) * 100:.1f}%"
    except (TypeError, ValueError):
        return "—"


def _overview(repo) -> dict:
    from app.api.today import _build_overview
    try:
        return _build_overview(repo)
    except Exception as e:  # noqa: BLE001
        logger.warning("paper trader overview failed: %s", e)
        return {}


def latest_prices(repo, symbols: list[str]) -> dict[str, float]:
    """收盘价。操盘手全程走收盘口径 —— 拿盘中价成交等于给模型一个它复盘时
    看不到的价格, 之后对不上账。"""
    import polars as pl

    want = {str(s).strip().upper() for s in symbols if str(s).strip()}
    if not want:
        return {}
    try:
        df, _as_of = repo.get_enriched_latest()
    except Exception as e:  # noqa: BLE001
        logger.warning("paper trader prices failed: %s", e)
        return {}
    if df is None or df.is_empty() or not {"symbol", "close"} <= set(df.columns):
        return {}
    rows = df.filter(pl.col("symbol").str.to_uppercase().is_in(list(want))) \
             .select("symbol", "close").to_dicts()
    return {str(r["symbol"]).upper(): float(r["close"])
            for r in rows if r.get("close") is not None}


def build_context(repo, trader: dict) -> str:
    """拼给这一个操作员看的今日信息。

    **只读这一个 trader 的账户** —— 别人的持仓、成交、理由一个字都不进来。
    这不是靠提示词守的, 是这个函数根本没去读别人的数据。
    """
    ov = _overview(repo)
    lines: list[str] = []

    as_of = ov.get("as_of") or "—"
    lines.append(f"# 今日信息(数据截至 {as_of}, 全部来自本系统, 收盘口径)")

    w = ov.get("weather") or {}
    if w:
        lines.append("\n## 市场天气(来自 今日总览)")
        lines.append(f"- 建议基调: {w.get('posture', '—')} —— {w.get('posture_reason', '')}")
        if w.get("market"):
            lines.append(f"- 大盘状态: {w['market'].get('mode', '—')}")
        lines.append(f"- 自选里涨势 {w.get('bull', 0)} 只 / 跌势 {w.get('bear', 0)} 只")

    meso = ov.get("meso") or {}
    ml = (meso.get("mainline") or {}).get("rows") if meso else None
    if ml:
        top = "、".join(f"{r['member']}({r['limit_up_count']}家涨停)" for r in ml[:3])
        lines.append(f"- 今日主线: {top}")

    opps = (ov.get("opportunities") or [])[:MAX_OPPORTUNITIES]
    lines.append(f"\n## 值得关注({len(opps)} 条, 来自 今日总览, 按把握分排序)")
    if not opps:
        lines.append("- (今天没有达到门槛的候选)")
    for o in opps:
        bits = [f"{o.get('name')}({o.get('symbol')})", f"把握分 {o.get('score')}"]
        if o.get("board"):
            bits.append(str(o["board"]))
        if o.get("verdict"):
            bits.append(f"通道结论: {o['verdict'].get('title')} —— {o['verdict'].get('action')}")
        lines.append(f"- {' · '.join(bits)}")
        lines.append(f"  {o.get('text', '')}")
        if o.get("why"):
            lines.append(f"  理由: {o['why']}")

    acts = ov.get("actions") or []
    if acts:
        lines.append("\n## 需要行动(来自 今日总览的持仓风险提示)")
        for a in acts[:10]:
            lines.append(f"- [{a.get('severity')}] {a.get('name')}({a.get('symbol')}) {a.get('text')}")

    # ---- 这一个操作员自己的账户 ----
    prices = latest_prices(repo, list((trader.get("positions") or {}).keys()))
    lines.append("\n## 你的账户(只有你自己的)")
    lines.append(f"- 现金: {float(trader.get('cash') or 0):,.0f}")
    lines.append(f"- 初始资金: {float(trader.get('initial_capital') or 0):,.0f}")
    lines.append(f"- 当前总资产: {pt.nav(trader, prices):,.0f}")

    positions = trader.get("positions") or {}
    if not positions:
        lines.append("- 当前空仓")
    else:
        lines.append(f"- 持仓 {len(positions)} 只:")
        for sym, pos in list(positions.items())[:MAX_HOLDINGS_SHOWN]:
            px = prices.get(sym)
            pnl = ((px / float(pos["cost"]) - 1) if px and pos.get("cost") else None)
            lines.append(
                f"  · {sym} {pos.get('shares')} 股 · 成本 {pos.get('cost')} · "
                f"现价 {px if px else '—'} · 浮盈 {_fmt_pct(pnl)} · 建仓日 {pos.get('opened_on', '—')}")

    orders = (trader.get("orders") or [])[-pt.RECENT_ORDERS_IN_CONTEXT:]
    lines.append("\n## 你最近的操作(只有你自己的)")
    if not orders:
        lines.append("- 还没有操作过")
    for o in orders:
        if o.get("rejected"):
            lines.append(f"- {o.get('date')} {o.get('action')} {o.get('symbol')} 被拒: {o['rejected']}")
        else:
            lines.append(f"- {o.get('date')} {o.get('action')} {o.get('symbol')} "
                         f"{o.get('shares')} 股 @ {o.get('price')} · {o.get('reason', '')}")

    lines.append("\n## 现在轮到你")
    lines.append("依据以上信息给出今天的操作。买入的标的必须出现在上面的信息里 —— "
                 "不在这份信息里的股票你无从判断, 不要凭空点名。")
    return "\n".join(lines)


async def run_once(repo, trader: dict) -> dict:
    """跑一次决策并入账。返回 {orders, note, raw, nav}。"""
    from app import secrets_store
    from app.services.ai_provider import _ACTIVE_PROFILE, generate_ai_text

    ov = _overview(repo)
    trade_date = str(ov.get("as_of") or "")
    if not trade_date:
        raise RuntimeError("拿不到交易日 —— 数据还没就绪")

    context = build_context(repo, trader)

    # 指定这个操作员自己的模型档位。不走兜底链: 这张表要比的就是"哪个模型
    # 用同一份信息做得更好", 悄悄换成另一家会把成绩记到错误的名下。
    profile = None
    for p in secrets_store.list_ai_profiles():
        if p["id"] == trader.get("profile_id"):
            profile = p
            break
    if profile is None:
        raise RuntimeError(f"操作员 {trader.get('name')} 绑定的 AI 档位不见了, 请在设置里重新指定")

    token = _ACTIVE_PROFILE.set(profile)
    try:
        text = await generate_ai_text(
            [{"role": "system", "content": SYSTEM_PROMPT},
             {"role": "user", "content": context}],
            temperature=0.3, max_tokens=None, timeout=300.0)
    finally:
        _ACTIVE_PROFILE.reset(token)

    orders, note = pt.parse_orders(text)
    wanted = [o["symbol"] for o in orders]
    prices = latest_prices(repo, wanted + list((trader.get("positions") or {}).keys()))

    filled: list[dict] = []
    for o in orders:
        entry = pt.apply_order(
            trader, action=o["action"], symbol=o["symbol"], shares=o["shares"],
            price=prices.get(o["symbol"], 0.0), trade_date=trade_date, reason=o["reason"])
        filled.append(entry)

    # 净值在成交之后按最新价重记 —— 先记再成交的话当天那一笔看不进曲线
    prices = latest_prices(repo, list((trader.get("positions") or {}).keys()))
    point = pt.mark_nav(trader, prices, trade_date)
    trader["last_run_at"] = pt.now_iso()
    trader["last_error"] = ""
    trader["last_note"] = note
    pt.save(trader)
    return {"date": trade_date, "orders": filled, "note": note,
            "raw": text[:4000], "nav": point}
