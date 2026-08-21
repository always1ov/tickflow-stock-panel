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


# 全市场候选的最低成交额。低于这个数的票, 模拟盘里买得进现实中买不进 ——
# 那种成绩没有参考价值。1 亿是个宽松但能滤掉僵尸股的线。
MIN_AMOUNT = 1e8
# 先按成交额取多少只进通道计算(keltner_service 上限 300)
MARKET_PREFILTER = 300
MAX_MARKET_CANDIDATES = 15


def market_candidates(repo) -> list[dict]:
    """全市场候选 —— **复用系统已有的「结论」层**, 只是把范围从自选换成全市场。

    刻意不另造一套排序: 这一本账存在的意义是和自选那本对照, 两边的判定口径
    必须是同一套, 否则比出来的是"两套规则谁强", 而不是"我这份自选有没有价值"。

    流程: 按成交额粗筛(买得进才算数) → 算三档通道 → 只留偏买那几档结论。
    """
    import polars as pl

    from app.services import keltner_service

    try:
        df, _as_of = repo.get_enriched_latest()
    except Exception as e:  # noqa: BLE001
        logger.warning("market candidates snapshot failed: %s", e)
        return []
    if df is None or df.is_empty() or "symbol" not in df.columns:
        return []

    cols = [c for c in ("symbol", "name", "close", "change_pct", "amount",
                        "consecutive_limit_ups") if c in df.columns]
    if "amount" not in cols or "close" not in cols:
        return []
    sub = df.select(cols).drop_nulls(["symbol", "close", "amount"])
    sub = sub.filter(pl.col("amount") >= MIN_AMOUNT)
    if "name" in sub.columns:
        # ST/退市整理不参与 —— 涨跌停幅度和流动性都是另一套, 混进来污染对照
        sub = sub.filter(~pl.col("name").str.contains("ST|退", literal=False))
    sub = sub.sort("amount", descending=True).head(MARKET_PREFILTER)
    rows = sub.to_dicts()
    if not rows:
        return []

    bands = keltner_service.channels_for_symbols(repo, [r["symbol"] for r in rows])
    out: list[dict] = []
    for r in rows:
        v = (bands.get(str(r["symbol"]).upper()) or {}).get("verdict")
        if not v or v.get("side") != "low":
            continue        # 只要偏买那几档 —— 偏卖的档位不是买入候选
        out.append({**r, "verdict": v})
        if len(out) >= MAX_MARKET_CANDIDATES:
            break
    return out


def build_context(repo, trader: dict, scope: str) -> str:
    """拼给这一个操作员看的今日信息。

    **只读这一个 trader 的账户** —— 别人的持仓、成交、理由一个字都不进来。
    这不是靠提示词守的, 是这个函数根本没去读别人的数据。
    """
    bk = pt.book(trader, scope)
    ov = _overview(repo)
    lines: list[str] = []

    as_of = ov.get("as_of") or "—"
    lines.append(f"# 今日信息(数据截至 {as_of}, 全部来自本系统, 收盘口径)")
    lines.append(f"你这本账的选股范围: **{pt.SCOPE_CN[scope]}** —— "
                 + ("只能买下面「值得关注」里出现的票(那是我圈定的自选)。"
                    if scope == pt.SCOPE_WATCHLIST
                    else "只能买下面「全市场候选」里出现的票。"))

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

    if scope == pt.SCOPE_WATCHLIST:
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
    else:
        cands = market_candidates(repo)
        lines.append(f"\n## 全市场候选({len(cands)} 条, 按成交额粗筛后取通道结论偏买的)")
        if not cands:
            lines.append("- (今天全市场没有符合条件的)")
        for c in cands:
            v = c["verdict"]
            chg = c.get("change_pct")
            bits = [f"{c.get('name') or ''}({c['symbol']})",
                    f"收盘 {c['close']}", f"当日 {_fmt_pct(chg)}",
                    f"成交额 {float(c['amount']) / 1e8:.1f} 亿",
                    f"通道结论: {v.get('title')} —— {v.get('action')}"]
            if c.get("consecutive_limit_ups"):
                bits.append(f"{c['consecutive_limit_ups']} 连板")
            lines.append(f"- {' · '.join(bits)}")
            lines.append(f"  依据: {v.get('bands_text')}")

    # 「需要行动」讲的是**我自己**自选持仓的风险提示, 只对自选那本账有参考意义;
    # 放进全市场那本会把我的持仓信息漏给一个本不该看到它的对照组。
    acts = (ov.get("actions") or []) if scope == pt.SCOPE_WATCHLIST else []
    if acts:
        lines.append("\n## 需要行动(来自 今日总览的持仓风险提示)")
        for a in acts[:10]:
            lines.append(f"- [{a.get('severity')}] {a.get('name')}({a.get('symbol')}) {a.get('text')}")

    # ---- 这一个操作员自己的账户 ----
    prices = latest_prices(repo, list((bk.get("positions") or {}).keys()))
    lines.append(f"\n## 你的账户(只有你自己这本「{pt.SCOPE_CN[scope]}」账)")
    lines.append(f"- 现金: {float(bk.get('cash') or 0):,.0f}")
    lines.append(f"- 初始资金: {float(bk.get('initial_capital') or 0):,.0f}")
    lines.append(f"- 当前总资产: {pt.nav(bk, prices):,.0f}")

    cap_n = pt.clamp_max_positions(trader.get("max_positions"))
    positions = bk.get("positions") or {}
    # 上限写给模型看 —— 不写的话它会开一堆买单, 大半被拒, 那一天的决策就废了一半
    lines.append(f"- 同时最多持有 {cap_n} 只(当前 {len(positions)} 只); "
                 f"到上限后只能加仓已有的, 想买新的得先卖掉一只")
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

    orders = (bk.get("orders") or [])[-pt.RECENT_ORDERS_IN_CONTEXT:]
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


async def run_once(repo, trader: dict, scope: str) -> dict:
    """跑一次决策并入账(只动这一本账)。返回 {orders, note, raw, nav}。"""
    from app import secrets_store
    from app.services.ai_provider import _ACTIVE_PROFILE, generate_ai_text

    ov = _overview(repo)
    trade_date = str(ov.get("as_of") or "")
    if not trade_date:
        raise RuntimeError("拿不到交易日 —— 数据还没就绪")

    bk = pt.book(trader, scope)
    context = build_context(repo, trader, scope)

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
    prices = latest_prices(repo, wanted + list((bk.get("positions") or {}).keys()))

    filled: list[dict] = []
    for o in orders:
        entry = pt.apply_order(
            bk, action=o["action"], symbol=o["symbol"], shares=o["shares"],
            price=prices.get(o["symbol"], 0.0), trade_date=trade_date, reason=o["reason"],
            max_positions=pt.clamp_max_positions(trader.get("max_positions")))
        filled.append(entry)

    # 净值在成交之后按最新价重记 —— 先记再成交的话当天那一笔看不进曲线
    prices = latest_prices(repo, list((bk.get("positions") or {}).keys()))
    point = pt.mark_nav(bk, prices, trade_date)
    bk["last_run_at"] = pt.now_iso()
    bk["last_error"] = ""
    bk["last_note"] = note
    pt.save(trader)
    return {"date": trade_date, "scope": scope, "orders": filled, "note": note,
            "raw": text[:4000], "nav": point}


# ================================================================
# [R61] 生命线实时例外
# ================================================================
#
# 操盘手全程走收盘口径 —— 这是刻意的: 拿盘中价成交等于给模型一个它复盘时
# 看不到的价格, 之后对不上账。
#
# 只有一件事例外: **持仓收盘跌破生命线(20 日线)必须立刻走**。这条不是策略,
# 是纪律 —— 系统里所有出场优先级都把它排在最高(组合回撤 > 生命线 > 止盈线 >
# 六态转弱), 等到收盘再处理往往已经又跌一截。所以这一路允许用实时价。
#
# 与 AI 决策的关系: 这一路**完全不问 AI**。生命线是硬纪律, 让模型有机会
# "再看看"就等于把纪律变成建议 —— 那正是这条线存在要防的事。

LIFELINE_WINDOW = 20
# 实时价只用来触发, 不用来记成交价: 记成交仍按拿到的那个实时价, 但会在
# 记录里标出来, 复盘时一眼能分清这笔是纪律强平还是模型自己的决定。
LIFELINE_REASON = "跌破生命线(20日线), 按纪律无条件清仓"


def _ma20_map(repo, symbols: list[str]) -> dict[str, float]:
    """各持仓的 20 日均线(收盘口径)。生命线本身永远按收盘算 ——
    拿实时价掺进均线里, 这条线自己就会跟着盘中抖。"""
    from datetime import date, timedelta

    want = sorted({str(s).strip().upper() for s in symbols if str(s).strip()})
    if not want:
        return {}
    end = date.today()
    try:
        df = repo.get_daily_batch(want, end - timedelta(days=90), end,
                                  ["symbol", "date", "close"])
    except Exception as e:  # noqa: BLE001
        logger.warning("lifeline ma20 batch failed: %s", e)
        return {}
    if df is None or df.is_empty() or not {"symbol", "date", "close"} <= set(df.columns):
        return {}
    out: dict[str, float] = {}
    for sym, sub in df.drop_nulls("close").sort("date").group_by("symbol"):
        name = str(sym[0] if isinstance(sym, tuple) else sym).upper()
        closes = sub["close"].tail(LIFELINE_WINDOW)
        if len(closes) < LIFELINE_WINDOW:
            continue        # 不足 20 根就没有生命线, 不拿 12 根算个假的出来
        out[name] = float(closes.mean())
    return out


def check_lifelines(repo, trader: dict, scope: str, *, live: dict[str, dict] | None = None,
                    trade_date: str | None = None) -> list[dict]:
    """扫一遍这本账的持仓, 跌破生命线的按纪律清掉。返回强平记录。

    ``live`` 给实时价 {symbol: {close}}; 不给就退回收盘价(收盘后跑定时任务
    就是这条路)。拿不到某只票的价就跳过它 —— 没价不能凭空成交。
    """
    bk = pt.book(trader, scope)
    positions = list((bk.get("positions") or {}).keys())
    if not positions:
        return []

    ma20 = _ma20_map(repo, positions)
    closes = latest_prices(repo, positions)
    live = live or {}
    day = trade_date or _overview(repo).get("as_of") or ""

    out: list[dict] = []
    for sym in positions:
        line = ma20.get(sym)
        if not line:
            continue
        # 触发看实时(有就用), 但生命线本身是收盘口径的均线
        px = float((live.get(sym) or {}).get("close") or 0) or closes.get(sym)
        if not px or px >= line:
            continue
        entry = pt.apply_order(
            bk, action=pt.ACTION_SELL, symbol=sym,
            shares=int((bk["positions"][sym]).get("shares") or 0),
            price=px, trade_date=day,
            reason=f"{LIFELINE_REASON} —— 现价 {px:.2f} < 生命线 {line:.2f}")
        entry["lifeline"] = True
        entry["intraday"] = sym in live
        out.append(entry)

    if out:
        pt.mark_nav(bk, latest_prices(repo, list((bk.get("positions") or {}).keys())), day)
        pt.save(trader)
    return out
