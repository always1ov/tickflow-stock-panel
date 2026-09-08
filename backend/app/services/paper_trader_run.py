"""[fork 增强] R59 操盘手的一次决策 —— 组上下文 → 问模型 → 撮合入账。

这一层最要紧的是两条隔离, 都是结构上的, 不靠提示词客气地要求:

  · **只喂系统里的信息**。上下文全部由服务端从本地数据拼出来, 模型没有工具、
    没有联网出口, 想去查也没有手。每一块都注明来自哪个模块, 复盘时对得上。
    [R65] 注意界限是"不许用**外部**信息", 不是"少给它看" —— 第一版把这两件
    事混成了一件, 只给了一段候选摘要, 那考的就不是"这套系统够不够用"了。
    现在走两轮: 先看盘挑出最多 MAX_DEEP_DIVE 只, 再把系统里关于那几只的
    东西一次给全(趋势/通道/关键价位/近月走势/已有的 AI 个股分析)。
  · **操作员之间互相看不见**。``build_context`` 只按传进来的那一个 trader_id
    读持仓与历史, 别人的持仓/成交/理由一个字都不会进来 —— 有测试守着。

模型只需要回一段 JSON。解析不出来就记成"这天没交易"并留原文, 不硬猜 ——
猜错一笔单子比空一天糟得多。
"""
from __future__ import annotations

import logging
from typing import Any

from app.services import paper_plan as pp   # [R171] 买入即立止盈/止损/到期
from app.services import paper_trader as pt

logger = logging.getLogger(__name__)

# 给模型看多少条机会 / 多少只自选。超过这个数上下文会长到把关键信息挤掉,
# 而这套系统本来就已经替它排过序了 —— 让它自己在 150 只里翻是浪费。
MAX_OPPORTUNITIES = 12
MAX_HOLDINGS_SHOWN = 30
MAX_DEEP_DIVE = 6          # 一次最多细看几只 —— 再多上下文就被这一段吃光了
KLINE_TAIL_DAYS = 20       # 走势摘要给多少天

# [R66] AI 个股信号多久算旧。信号是缓存的, 别的东西(趋势/通道/价位)每次都现算,
# 只有它会摆着一个过期的判断不动 —— 拿三周前的"买入"当今天的依据是最坏的情况:
# 它读起来和今天刚出的一模一样。
SIGNAL_STALE_DAYS = 3
# 一次决策最多重出几个信号。每个都是一次真实的 AI 调用(要钱要时间), 而且
# 无上限的话, 模型一句"全都刷一遍"就能把一次决策拖成几十次调用。
MAX_REFRESH = 3

# 界限说清楚: 禁的是**外部信息**, 不是"少给你看"。这套系统里的东西全都能用 ——
# 趋势判定、通道结论、关键价位、日 K 走势、已有的 AI 个股分析, 想细看就开口要。
_RULES = """铁律:
1. **信息来源只能是这套系统**。你没有联网能力, 也不许凭记忆使用任何外部消息
   (新闻、公告、传闻、研报、行情网站)。系统没给的事实, 就当不知道。
   但系统里的东西你**都可以用**: 六态趋势、Keltner 三档与结论、十一类关键
   价位、近月日 K 走势、以及这只票已有的 AI 个股分析 —— 想细看哪几只就说,
   会给你。
2. 你只看得到自己这本账。不存在其他操作员, 也不要猜别人在做什么。
3. A 股规则: 买卖都以 100 股为单位; 当天买入的当天不能卖(T+1); 按收盘价成交。
4. 现金不够、或已到持仓只数上限就少买或不买。宁可不动, 不要为了交易而交易。"""

# 第一轮: 先挑要细看的。刻意单独走一轮而不是一次给全 —— 全部候选的完整明细
# 会长到把账户和规则都挤出上下文, 而且大部分是它根本不打算买的票。
LOOK_PROMPT = f"""你是一名 A 股模拟盘操作员, 现在是**看盘**环节。

{_RULES}

先别下单。看完下面的信息, 挑出你想**细看**的股票(最多 {MAX_DEEP_DIVE} 只)——
系统会把它们的趋势、通道、关键价位、近月走势、已有的 AI 分析一次给你。
已持仓的票也可以挑(要判断是否该卖)。

下面每只票的 AI 信号都标了出的时间, 过期的会写「已过期」。觉得哪只的信号旧到
不能用了, 就把它列进 refresh —— 系统会**现场重新跑一次 AI 个股分析**再给你
(最多 {MAX_REFRESH} 只, 每次都是真实开销, 别顺手全填)。

只回一个 JSON:
{{"focus": ["600000.SH", "000001.SZ"],
  "refresh": ["600000.SH"],
  "why": "一句话说明为什么挑这几只"}}
一只都不想细看就给 "focus": []; 不需要重出信号就给 "refresh": []。"""

# [R171] 买入必须带交易计划。借鉴「持仓提醒」的批次: 记一笔买入就按成本价
# ± 止盈/止损% 立好监控线, 填了持有期限就有到期日。
#
# 为什么要逼模型先说清楚: 升级前它每天重新自由决定买卖, 复盘时**没法回答
# "它的计划靠不靠谱"** —— 赚了说是眼光, 亏了说是运气。先立计划再执行, 每笔
# 出场就能归到止盈/止损/到期/生命线/主动卖里的一类, 一段时间下来这个模型是
# 真有章法还是只会画大饼, 表上自己会说话。
_PLAN_RULE = f"""买入的纪律(这是硬的):
- 每一笔买入**必须**同时给出 target_pct(止盈%)、stop_pct(止损%)、
  hold_days(最长持有几天)。系统会按你的成交成本立好三条线。
- **止损线和到期日到了, 系统直接卖, 不会再问你** —— 和跌破生命线一样是纪律。
  所以别写"止损 1%"这种一个跳就打掉的数, 也别写"持有 1 天"。
- **止盈线到了系统只提醒你, 不替你卖** —— 落袋还是让利润奔跑由你自己判断,
  那是策略不是纪律。
- 合理区间: 止盈 {pp.MIN_TARGET_PCT:g}~{pp.MAX_TARGET_PCT:g}%,
  止损 {pp.MIN_STOP_PCT:g}~{pp.MAX_STOP_PCT:g}%,
  持有 {pp.MIN_HOLD_DAYS}~{pp.MAX_HOLD_DAYS} 天(自然日)。超出会被夹到边界。
- 加仓时成本会变, 系统按新成本重算三条线; 不重新给参数就沿用原来的百分比。"""

SYSTEM_PROMPT = f"""你是一名 A 股模拟盘操作员。

{_RULES}

{_PLAN_RULE}

输出**只回一个 JSON 对象**, 不要写别的:
{{"note": "一句话说明今天的整体想法",
 "orders": [{{"action": "buy", "symbol": "600000.SH", "shares": 100,
             "target_pct": 15, "stop_pct": 8, "hold_days": 30,
             "reason": "为什么这一笔, 以及为什么是这三个数"}},
            {{"action": "sell", "symbol": "000001.SZ", "shares": 100,
             "reason": "为什么现在走"}}]}}
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
            # [R171] 把这一笔买入时自己立的三条线摆出来。不摆的话模型看不见自己的
            # 承诺, 于是下一天又凭当天的感觉重新决定 —— 那就回到升级前了。
            plan_txt = pp.plan_line(sym, pos, px)
            if plan_txt:
                lines.append(f"    ({plan_txt.split(': ', 1)[-1]})")

    # [R171] 上一轮纪律检查记下的止盈提醒。止盈不硬执行, 所以必须让它看见 ——
    # 否则"只提醒"就等于没提醒。
    rem = bk.get("plan_reminders") or []
    if rem:
        lines.append("\n## 已到止盈线(系统不替你卖, 走不走你自己定)")
        for r in rem:
            lines.append(f"- {r.get('symbol')}: {r.get('reason')}")

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


def _allowed_symbols(repo, trader: dict, scope: str) -> set[str]:
    """这本账**允许碰**的范围: 本轮候选 + 自己已有的持仓。

    细看也要守这个范围 —— 放它细看一只不在候选里的票, 等于让它出了这本账的
    选股范围, 而两本账能对照的前提就是各自只在自己那个池子里选。
    """
    bk = pt.book(trader, scope)
    out = {str(s).upper() for s in (bk.get("positions") or {})}
    if scope == pt.SCOPE_WATCHLIST:
        for o in (_overview(repo).get("opportunities") or []):
            if o.get("symbol"):
                out.add(str(o["symbol"]).upper())
    else:
        for c in market_candidates(repo):
            out.add(str(c["symbol"]).upper())
    return out


def _pick(data: dict, keys: tuple[str, ...], allowed: set[str], cap: int) -> list[str]:
    for k in keys:
        raw = data.get(k)
        if isinstance(raw, list):
            out: list[str] = []
            for x in raw:
                sym = str(x or "").strip().upper()
                if sym and sym in allowed and sym not in out:
                    out.append(sym)
            return out[:cap]
    return []


def parse_focus(text: str, allowed: set[str]) -> tuple[list[str], list[str]]:
    """从看盘那一轮取出 (想细看的, 想重出信号的)。

    ``allowed`` 是这本账**允许碰**的范围(候选 + 自己的持仓)。范围外的一律丢掉 ——
    模型凭记忆报一只不在候选里的票, 给它明细就等于放它出了这本账的选股范围,
    而那正是两本账对照的前提。refresh 同样受这个范围约束: 那一步会真的花钱
    跑一次 AI, 更不该被一个范围外的代码触发。
    """
    import json as _json
    import re as _re

    m = _re.search(r"\{.*\}", (text or "").strip(), _re.S)
    if not m:
        return [], []
    try:
        data = _json.loads(m.group(0))
    except _json.JSONDecodeError:
        return [], []
    if not isinstance(data, dict):
        return [], []
    focus = _pick(data, ("focus", "symbols"), allowed, MAX_DEEP_DIVE)
    refresh = _pick(data, ("refresh", "renew"), allowed, MAX_REFRESH)
    return focus, refresh


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
    focus: list[str] = []
    want_refresh: list[str] = []
    refreshed: list[dict] = []
    # [R180] 消息面总览 —— 这是真下单的路径, 所以同样带上背景;
    # 但它只进 system 作参考, 价格与规则仍以 context 里的为准(见 news_desk 模块头)。
    try:
        from app.services import news_desk
        _news = news_desk.context_for_ai()
    except Exception as e:  # noqa: BLE001
        logger.debug("paper trader: news desk skipped: %s", e)
        _news = ""
    _sfx = ("\n\n" + _news) if _news else ""
    try:
        # 第 1 轮: 看盘 —— 先挑想细看的几只
        allowed = _allowed_symbols(repo, trader, scope)
        try:
            look = await generate_ai_text(
                [{"role": "system", "content": LOOK_PROMPT + _sfx},
                 {"role": "user", "content": context}],
                temperature=0.2, max_tokens=None, timeout=180.0)
            focus, want_refresh = parse_focus(look, allowed)
        except Exception as e:  # noqa: BLE001
            # 看盘轮失败不该让这一天整个报废 —— 退回只看摘要下单
            logger.warning("paper trader look round failed: %s", e)

        # 触发新数据: 它认为哪只的 AI 信号旧到不能用了, 就现场重出一个。
        # 必须在细看之前 —— 顺序反了的话, 它拿到的还是刚刚判定为过期的那一份。
        if want_refresh:
            refreshed = await refresh_signals(repo, want_refresh)
            # 重出过的自动进细看名单: 它开口要新信号, 就是打算据此做判断
            for r in refreshed:
                if r["ok"] and r["symbol"] not in focus and len(focus) < MAX_DEEP_DIVE:
                    focus.append(r["symbol"])

        # 第 2 轮: 带上细看的明细下单
        detail = ""
        if focus:
            blocks = [symbol_detail(repo, sym) for sym in focus]
            detail = ("\n\n## 你要求细看的(全部来自本系统)\n"
                      + "\n\n".join(b for b in blocks if b))
        text = await generate_ai_text(
            [{"role": "system", "content": SYSTEM_PROMPT + _sfx},
             {"role": "user", "content": context + detail}],
            temperature=0.3, max_tokens=None, timeout=300.0)
    finally:
        _ACTIVE_PROFILE.reset(token)

    orders, note = pt.parse_orders(text)
    wanted = [o["symbol"] for o in orders]
    prices = latest_prices(repo, wanted + list((bk.get("positions") or {}).keys()))

    filled: list[dict] = []
    for o in orders:
        # [R171] 买入带上交易计划 —— derive_plan 按**成交成本**立线, 所以要等
        # apply_order 算完加权成本再重算一次(那一步在 apply_order 里做)。
        # 这里只把模型给的百分比透传过去。
        plan_in = None
        if o["action"] == pt.ACTION_BUY and any(
                k in o for k in ("target_pct", "stop_pct", "hold_days")):
            plan_in = {"target_pct": o.get("target_pct"), "stop_pct": o.get("stop_pct"),
                       "hold_days": o.get("hold_days")}
        entry = pt.apply_order(
            bk, action=o["action"], symbol=o["symbol"], shares=o["shares"],
            price=prices.get(o["symbol"], 0.0), trade_date=trade_date, reason=o["reason"],
            max_positions=pt.clamp_max_positions(trader.get("max_positions")),
            plan=plan_in)
        filled.append(entry)

    # 净值在成交之后按最新价重记 —— 先记再成交的话当天那一笔看不进曲线
    prices = latest_prices(repo, list((bk.get("positions") or {}).keys()))
    point = pt.mark_nav(bk, prices, trade_date)
    bk["last_run_at"] = pt.now_iso()
    bk["last_error"] = ""
    bk["last_note"] = note
    pt.save(trader)
    return {"date": trade_date, "scope": scope, "orders": filled, "note": note,
            "focus": focus, "refreshed": refreshed,
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
            reason=f"{LIFELINE_REASON} —— 现价 {px:.2f} < 生命线 {line:.2f}",
            exit_reason=pt.EXIT_LIFELINE)      # [R171] 与"模型自己的计划"分开归因
        entry["lifeline"] = True
        entry["intraday"] = sym in live
        out.append(entry)

    if out:
        pt.mark_nav(bk, latest_prices(repo, list((bk.get("positions") or {}).keys())), day)
        pt.save(trader)
    return out


# ================================================================
# [R171] 交易计划纪律 —— 买入时立的止损/到期硬执行, 止盈只提醒
# ================================================================
#
# 借鉴「持仓提醒」的批次: 记一笔买入 → 按成本价 ± 止盈/止损% 生成价格监控,
# 填了持有期限就生成到期提醒。那边是真钱、由人拍板, 所以只提醒; 这边没有人,
# 所以要先说清「提醒发给谁」。答案分两档(理由见 paper_plan 模块开头):
#
#   止损 / 到期 → 硬执行, 不问 AI(和生命线同一条道理: 保命的事不给"再看看"的机会)
#   止盈       → 只提醒, 写进下一轮上下文, 由模型自己决定落袋还是继续拿
#
# 与生命线的关系: 生命线是**系统**定的纪律(跌破 20 日线无条件走), 计划是
# **模型自己**买入那一刻立的。两条都硬执行, 但归因分开记 —— 复盘时要能分清
# 这笔是被系统的纪律带走的, 还是它自己的计划兑现了。


def check_plans(repo, trader: dict, scope: str, *,
                trade_date: str | None = None) -> dict:
    """扫一遍这本账的持仓, 触了止损/到期的按纪律卖掉, 到止盈线的只记提醒。

    返回 {"forced": [成交记录...], "reminders": [{symbol, kind, reason}...]}。

    全程**收盘口径** —— 与生命线那一路不同, 这里不接实时价: 计划的三条线是模型
    按收盘成本立的, 拿盘中价去比会在同一天里反复触发又反复回来。
    """
    bk = pt.book(trader, scope)
    positions = bk.get("positions") or {}
    if not positions:
        return {"forced": [], "reminders": []}

    syms = list(positions.keys())
    closes = latest_prices(repo, syms)
    day = trade_date or _overview(repo).get("as_of") or ""

    forced: list[dict] = []
    reminders: list[dict] = []
    for sym in syms:
        pos = positions.get(sym)
        if not isinstance(pos, dict):
            continue
        px = closes.get(sym)
        if not px:
            continue                      # 没价不判, 更不能凭空成交
        hit = pp.check_plan(pos, px, day)
        if not hit:
            continue
        if not hit["enforce"]:
            reminders.append({"symbol": sym, "kind": hit["kind"], "reason": hit["reason"]})
            continue
        # T+1 挡住当天买当天卖: 计划再硬也不能违反交易规则, apply_order 会拒,
        # 拒单同样留痕, 明天再触发一次就是了
        entry = pt.apply_order(
            bk, action=pt.ACTION_SELL, symbol=sym,
            shares=int(pos.get("shares") or 0), price=px, trade_date=day,
            reason=hit["reason"],
            exit_reason=pt.EXIT_STOP if hit["kind"] == pp.KIND_STOP else pt.EXIT_DUE)
        entry["plan_hit"] = hit["kind"]
        forced.append(entry)

    if forced:
        pt.mark_nav(bk, latest_prices(repo, list((bk.get("positions") or {}).keys())), day)
    # 提醒也要落在账上 —— 下一轮 build_context 从这里读, 不然模型看不见
    bk["plan_reminders"] = reminders
    pt.save(trader)
    return {"forced": forced, "reminders": reminders}


# ================================================================
# [R65] 个股细看 —— 系统里关于这一只的全部东西
# ================================================================
#
# 第一版只给了一段候选清单摘要, 那是把"不能上网"错做成了"只能看一小段"。
# 界限本来是: **不能去网上找信息, 但这套系统里的东西全都能用**。
#
# 所以补一条"细看"通道: 模型先从候选里挑几只想深看的, 服务端把系统里关于
# 那几只的东西一次给全 —— 六态趋势与关键价位、Keltner 三档与结论、十一类
# 价位点、出场线/生命线、近月的日 K 走势(带涨停/炸板/跳空标注)、以及这只票
# 已有的 AI 分析报告。这就是人在个股分析页上"看图"能看到的那些, 只不过换成
# 文字 —— 模型读不了图片, 但读得懂"哪根均线在哪、缺口在哪、离压力位还差多少"。
#
# 仍然一个字都不来自外部: 每一项都是本地算出来或本地存着的。



def _kline_story(repo, symbol: str) -> str:
    """近 20 个交易日的走势, 写成一段能读的话。

    这是"看图"的文字版: 涨停/跌停/炸板/跳空/均线关系都标出来 —— 模型读不了
    图片, 但这些正是人看图时真正在读的东西。
    """
    from datetime import date, timedelta

    want = ["date", "close", "open", "high", "low", "change_pct", "ma20", "ma60",
            "signal_limit_up", "signal_limit_down", "signal_broken_limit_up"]
    try:
        at = repo.resolve_asset_type(symbol)
        df = repo.get_daily_asset(at, symbol, date.today() - timedelta(days=120),
                                  date.today(), columns=want)
    except Exception as e:  # noqa: BLE001
        logger.debug("kline story failed for %s: %s", symbol, e)
        return ""
    if df is None or df.is_empty() or "close" not in df.columns:
        return ""
    rows = df.sort("date").tail(KLINE_TAIL_DAYS).to_dicts()
    if not rows:
        return ""

    bits: list[str] = []
    for r in rows:
        tag = ""
        if r.get("signal_limit_up"):
            tag = "涨停"
        elif r.get("signal_limit_down"):
            tag = "跌停"
        elif r.get("signal_broken_limit_up"):
            tag = "炸板"
        chg = r.get("change_pct")
        bits.append(f"{str(r['date'])[5:]} {float(r['close']):.2f}"
                    f"({_fmt_pct(chg)}){tag}")
    last = rows[-1]
    ma_note = []
    for col, name in (("ma20", "20日线"), ("ma60", "60日线")):
        v = last.get(col)
        if v:
            side = "上方" if float(last["close"]) >= float(v) else "下方"
            ma_note.append(f"收盘在{name}({float(v):.2f}){side}")
    highs = [float(r["high"]) for r in rows if r.get("high")]
    lows = [float(r["low"]) for r in rows if r.get("low")]
    span = ""
    if highs and lows:
        span = f"这 {len(rows)} 天区间 {min(lows):.2f} ~ {max(highs):.2f}"
    return " · ".join(x for x in ["  ".join(bits), span, "、".join(ma_note)] if x)


def _recent_report(symbol: str) -> str:
    """这只票已有的 AI 分析报告(个股分析页生成的那些)。

    有就带上一段 —— 那是这套系统对它下过的最完整的一次判断, 不给模型看
    等于让它重新从零判断一遍, 而我要考的恰恰是"系统给的东西够不够用"。
    """
    try:
        from app.services import ai_reports
        rows = [r for r in ai_reports.list_reports()
                if str(r.get("symbol") or "").upper() == symbol.upper()]
    except Exception as e:  # noqa: BLE001
        logger.debug("ai report lookup failed for %s: %s", symbol, e)
        return ""
    if not rows:
        return ""
    r = rows[0]
    text = str(r.get("content") or r.get("text") or r.get("summary") or "").strip()
    if not text:
        return ""
    return f"[{r.get('created_at', '')[:10]}] {text[:1200]}"


def _signal_line(symbol: str) -> tuple[str, bool]:
    """这只票的 AI 信号 + 它有多旧。返回 (文本, 是否过期)。

    **年龄一定要写出来**: 缓存的信号读起来和今天刚出的一模一样, 不标时间的话
    模型没有任何办法知道自己在拿一个三周前的判断当今天的依据。
    """
    from datetime import datetime

    try:
        from app.services import stock_signal
        sig = (stock_signal.load_all() or {}).get(symbol.upper())
    except Exception as e:  # noqa: BLE001
        logger.debug("signal lookup failed for %s: %s", symbol, e)
        return "", False
    if not sig:
        return "- AI 信号: 还没跑过(可以列进 refresh 让系统现出一个)", True

    created = str(sig.get("created_at") or "")
    age_days = None
    try:
        dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
        age_days = (datetime.now(dt.tzinfo) - dt).days
    except (TypeError, ValueError):
        pass
    stale = age_days is None or age_days >= SIGNAL_STALE_DAYS
    age_txt = f"{age_days} 天前" if age_days is not None else "时间不详"
    mark = " 【已过期, 建议 refresh】" if stale else ""
    return (f"- AI 信号: {sig.get('signal')} 把握 {sig.get('confidence')}"
            f" · 出于 {created[:16].replace('T', ' ')}({age_txt}){mark}\n"
            f"  理由: {str(sig.get('reason') or '')[:400]}"), stale


async def refresh_signals(repo, symbols: list[str]) -> list[dict]:
    """现场重出 AI 个股信号 —— 这是操作员唯一能**触发新数据**的动作。

    别的东西(趋势/通道/关键价位/走势)每次都是现算的, 本来就不会旧; 只有 AI
    信号是缓存的, 所以只开这一个口子。串行跑: 并发调同一家模型只会互相限流,
    而且这一步本来就在一次决策的关键路径上, 稳比快重要。

    **重出时把当前档位放掉, 走系统默认的那条 AI 链**。这一点很要紧: AI 信号
    是全局缓存的系统产物(个股分析页上人看到的就是它), 如果用操作员自己的模型
    去生成, 这份"系统数据"就变成了那个模型自己的意见 —— 而且会被别的操作员
    当成系统数据读到, 等于绕开隔离互相影响。用默认链生成, 它才还是"我的系统
    怎么看这只票"。
    """
    from app.services import stock_signal
    from app.services.ai_provider import _ACTIVE_PROFILE

    out: list[dict] = []
    for sym in symbols[:MAX_REFRESH]:
        token = _ACTIVE_PROFILE.set(None)
        try:
            got = await stock_signal.generate_signal(repo, repo.store.data_dir, sym)
            out.append({"symbol": sym, "ok": not got.get("error"),
                        "error": str(got.get("error") or "")[:200]})
        except Exception as e:  # noqa: BLE001
            logger.warning("refresh signal failed for %s: %s", sym, e)
            out.append({"symbol": sym, "ok": False, "error": str(e)[:200]})
        finally:
            _ACTIVE_PROFILE.reset(token)
    return out


def symbol_detail(repo, symbol: str) -> str:
    """系统里关于这一只的全部相关内容, 拼成一段。"""
    sym = str(symbol or "").strip().upper()
    if not sym:
        return ""
    out: list[str] = [f"### {sym}"]

    # 六态趋势 + 关键价位 + 操作建议
    try:
        from app.services import livermore_service
        t = livermore_service.trend_for_symbol(repo, sym)
        if t and not t.get("error"):
            out.append(
                f"- 六态趋势: {t.get('state_cn')}({t.get('side')}) 第 {t.get('duration')} 天, "
                f"自 {t.get('since')}; 收盘 {t.get('close')}")
            flips = [x for x in (
                f"跌破 {t['flip_down']:.2f} 转弱" if t.get("flip_down") else "",
                f"站上 {t['flip_up']:.2f} 转强" if t.get("flip_up") else "") if x]
            if flips:
                out.append(f"- 翻转触发价: {' / '.join(flips)}")
            out.append(f"- 上关键点 {t.get('up_pivot')} / 下关键点 {t.get('dn_pivot')}"
                       f"; 本轮最高收盘 {t.get('leg_high')}")
            if t.get("action"):
                out.append(f"- 系统建议: {t['action']}")
            if t.get("signal"):
                out.append(f"- 近期信号: {t['signal']} —— {t.get('signal_desc', '')}")
    except Exception as e:  # noqa: BLE001
        logger.debug("trend detail failed for %s: %s", sym, e)

    # Keltner 三档 + 结论
    try:
        from app.services import keltner_service
        kc = (keltner_service.channels_for_symbols(repo, [sym]) or {}).get(sym) or {}
        band_bits = [f"{kc[k]['band_cn']}{kc[k]['pos_cn']}"
                     f"({kc[k]['lower']}~{kc[k]['upper']})"
                     for k in ("s", "m", "l") if k in kc]
        if band_bits:
            out.append(f"- 通道三档: {' · '.join(band_bits)}")
        v = kc.get("verdict")
        if v:
            out.append(f"- 通道结论: 【{v['title']}】{v['action']} —— {v['detail']}")
    except Exception as e:  # noqa: BLE001
        logger.debug("keltner detail failed for %s: %s", sym, e)

    # 十一类价位点(与个股分析图上画的是同一批)
    try:
        from datetime import date, timedelta

        from app.indicators.levels import compute_levels, summarize_levels
        at = repo.resolve_asset_type(sym)
        df = repo.get_daily_asset(at, sym, date.today() - timedelta(days=400), date.today())
        if df is not None and not df.is_empty() and "close" in df.columns:
            close = float(df.sort("date").tail(1)["close"][0])
            out.append(f"- 关键价位: {summarize_levels(compute_levels(df), close)}")
    except Exception as e:  # noqa: BLE001
        logger.debug("levels detail failed for %s: %s", sym, e)

    sig_txt, _stale = _signal_line(sym)
    if sig_txt:
        out.append(sig_txt)

    story = _kline_story(repo, sym)
    if story:
        out.append(f"- 近 {KLINE_TAIL_DAYS} 日走势: {story}")

    report = _recent_report(sym)
    if report:
        out.append(f"- 本系统已有的 AI 个股分析: {report}")

    return "\n".join(out)
