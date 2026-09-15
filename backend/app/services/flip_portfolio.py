"""[fork 增强] R327 转折模拟盘 —— 一个组合, 只按六态转折买卖。

用户: 「模拟盘页面大整改, 完全不需要我原来的了, 重新设计, 每天收盘价按照转折
买卖, 所有票只看趋势状态的转折」。

替掉的是 R59 那套「AI 操盘手」—— 让模型自己读盘做决定。那套要回答的是"模型拿
这些信息够不够", 这一套要回答的是完全不同的一个问题:

    **我这套六态判定, 一个人真按它做, 长期是赚是亏?**

里面没有 AI、没有提示词、没有任何一处"看情况"。每一天做什么, 只由当天收盘价
算出来的状态决定 —— 同样的自选、同样的阈值, 谁跑都是同一条曲线, 可复现。

## 规则(界面上必须原样写出来)

    信号   六态转折日 D —— 当天收盘把状态从多头翻到空头, 或反过来
    执行   **D 当天的收盘价**
    方向   转折后在多头侧(上涨趋势 / 自然回升 / 次级回升)→ 买入
           转折后在空头侧(下跌趋势 / 自然回撤 / 次级回撤)→ 清仓
    仓位   等权, 同时最多 N 只; 每笔目标金额 = **当日净值** / N
    标的   自选股, 自选变了模拟盘跟着变
    不做空 空头段就是空仓。A 股散户也做不了

## 「当天收盘价成交」这件事, 前提必须写在脸上

转折要等收盘价定下来才算得出, 拿同一根收盘价成交, 字面上就是用了收盘之后才
知道的信息。**这套之所以仍然成立, 靠的是作者那两个前瞻触发价**: `compute()`
每天给出 `flip_up` / `flip_down` —— 「收盘站上这个价就转多」「收盘跌破这个价
就转空」, 它们在**开盘前**就已经定死。盘中盯着价格接近哪一条, 14:55 挂单就能
按接近收盘的价格成交。

所以这里的假设不是"我能预知收盘", 而是**"我能在尾盘按收盘价附近成交"**。这两
件事差很远, 界面上写的是后者。滑点照扣 —— 尾盘挂单不可能刚好打在收盘价上。

同一套信号还有一份**次日开盘价**的口径, 在 `flip_trades.py`(R287), 复盘页那些
战绩数字就是它算的。两份都留着, 它们回答的是两个问题: 这里问"尾盘做能拿到
什么", 那里问"第二天做能拿到什么"。差额就是隔夜跳空。

## 每天谁多谁空, 判据只此一处

直接问 `flip_trades.trend_days()` —— 复盘页用的就是它。**不在这里重写一遍
`state in BULLISH`**: 同一件事两处判断, 哪天口径改了必然漂, 而且不会有任何东西
报错(AGENTS.md 规则 12)。

## 但「成交不了」这一条**必须另写**, 不能复用那边的

`flip_trades._sealed` 判的是「**开盘价**成交不了」, 判据是「收盘在板上 **且**
开盘不低于收盘」—— 那个 `and` 是为开盘价成交服务的: 盘中打开过、尾盘才封回去
的票, 它的**开盘价**是能成交的。

而这里是**尾盘成交**, 同一只票的结论正好相反 —— 尾盘那一刻板封着, 你就是挂不
进去, 盘中打开过并不能帮你。所以这边的判据只看一件事: **收盘价在板上**。

  买入日收盘涨停 → 封单排着, 买不进
  卖出日收盘跌停 → 砸不出去, 卖不掉

方向必须对上: 买入日撞跌停、卖出日撞涨停都是好事(买得更便宜、卖得更贵),
标成风险会把利好读成利空 —— 这一条与那边同理。

**封板不是放弃, 是顺延。** 记下这个信号, 之后每天再试, 一直到能成交为止; 中途
这只票要是反向转折了, 这张单就作废(R304 对次日开盘那条路定的规矩, 同一条)。

## 撮合按 A 股的规矩

100 股一手、T+1(当天买的不能当天卖)、佣金印花税滑点。三个常量沿用 R59 那套
—— 换一套费率, 跑出来的曲线就没法和过去的记录比。

**卖在买前。** 当天既有票转空又有票转多时, 先把该清的清掉再买 —— 反过来是手上
明明有一笔该卖的钱, 却按"没这笔钱"在做买入决定, 那天的仓位建立在错的账面上。
这与 R61 定时任务「先清后决策」是同一条理由。

纯函数: 不读盘、不调网、不碰 repo。输入是已经对齐好的每票序列。
"""
from __future__ import annotations

import logging
from typing import Any

from app.services.flip_trades import BEAR, BULL, trend_days

logger = logging.getLogger(__name__)

LOT = 100                      # A 股一手
DEFAULT_CAPITAL = 1_000_000.0
DEFAULT_MAX_POSITIONS = 10
MAX_POSITIONS_CAP = 50

# 撮合成本 —— 与 R59 那套逐值相同, 换一套曲线就没法和过去比
COMMISSION = 0.0002            # 双边
STAMP_TAX = 0.0005             # 卖出单边
SLIPPAGE_BPS = 5.0

ACT_BUY = "buy"
ACT_SELL = "sell"

# skipped 的原因码 —— 界面上逐条翻译, **空栏必须自己解释**
WHY_SEALED = "sealed"          # 收盘封板, 挂不进去(已顺延, 还在等)
WHY_NO_SLOT = "no_slot"        # 仓位满了
WHY_NO_CASH = "no_cash"        # 钱不够一手
WHY_VOIDED = "voided"          # 一直封到反向转折, 这张单作废


def sealed_at_close(limited: bool) -> bool:
    """尾盘按收盘价成交时, 这一天挂不挂得进去。

    只看一件事: **收盘价在板上**。见模块 docstring 里「必须另写」那一节 ——
    与 `flip_trades._sealed`(开盘价口径, 要 `开盘 ≥ 收盘`)是两个判据,
    因为成交时点不同, 结论会正好相反。
    """
    return bool(limited)


def _fill(price: float, act: str) -> float:
    """滑点: 买贵一点、卖便宜一点。两边都按有利方向算等于凭空多赚。"""
    slip = SLIPPAGE_BPS / 10_000.0
    return price * (1 + slip) if act == ACT_BUY else price * (1 - slip)


def _fee(amount: float, act: str) -> float:
    return amount * (COMMISSION + STAMP_TAX) if act == ACT_SELL else amount * COMMISSION


def _f(v) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if f != f or f <= 0 else f      # NaN 与非正价都当缺


def simulate(
    series: dict[str, dict],
    *,
    capital: float = DEFAULT_CAPITAL,
    max_positions: int = DEFAULT_MAX_POSITIONS,
) -> dict:
    """跑一遍转折模拟盘。口径见模块 docstring。

    series  {symbol: {"name": str, "steps": [...], "dates": [...],
                      "closes": [...], "limit_up": [...], "limit_down": [...]}}
            `steps` 吃 ``livermore.compute()`` 的输出(原样, 不必先转仓位);
            其余序列与 steps 等长。涨跌停标志不给就一律当能成交, **不瞎猜**。

    返回::

        nav        逐日 [{date, nav, cash, market_value, positions, ret}]
        orders     成交流水 [{date, symbol, name, act, shares, price, amount,
                             fee, state_cn, reason, delayed}]
        positions  最后一天还拿着的
        stats      {days, orders, buys, sells, round_trips, win, win_rate,
                    total_ret, max_drawdown, best, worst}
        skipped    没能按信号动手的 [{date, symbol, name, reason}]
        pending    还在等成交的信号(封板顺延中)
        as_of      最后一个交易日
        reason     一天都跑不了时的原因; 跑得了就是 None
    """
    max_positions = max(1, min(int(max_positions or DEFAULT_MAX_POSITIONS), MAX_POSITIONS_CAP))
    capital = float(capital) if capital and capital > 0 else DEFAULT_CAPITAL

    by_symbol, names, calendar = _flatten(series)
    if not by_symbol or not calendar:
        return _empty(capital, "no_data")

    cash = capital
    holdings: dict[str, dict] = {}          # symbol -> {shares, cost_amount}
    orders: list[dict] = []
    nav_rows: list[dict] = []
    skipped: list[dict] = []
    round_trips: list[float] = []
    last_price: dict[str, float] = {}
    # 封板顺延中的信号: symbol -> {"act": ..., "since": 信号日}
    pending: dict[str, dict] = {}

    for day in calendar:
        bought_today: set[str] = set()
        today = {s: t[day] for s, t in by_symbol.items() if day in t}
        for sym, row in today.items():
            if row["close"] is not None:
                last_price[sym] = row["close"]

        # 今天要处理的信号 = 今天新转折的 + 之前封板还在等的。
        # 顺延那些**先于**今天的新信号处理: 它们等得更久。
        want: dict[str, dict] = {}
        for sym, p in list(pending.items()):
            row = today.get(sym)
            if row is None:
                continue
            # 方向反了 → 这张单作废(R304 同一条规矩)
            still = (p["act"] == ACT_BUY and row["side"] == BULL) or \
                    (p["act"] == ACT_SELL and row["side"] == BEAR)
            if not still:
                pending.pop(sym, None)
                skipped.append({"date": day, "symbol": sym,
                                "name": names.get(sym, sym), "reason": WHY_VOIDED})
                continue
            want[sym] = {"act": p["act"], "since": p["since"]}
        for sym, row in today.items():
            if not row["flipped"]:
                continue
            act = ACT_BUY if row["side"] == BULL else ACT_SELL
            want[sym] = {"act": act, "since": day}

        # ── 先卖 ────────────────────────────────────────────────────
        for sym in sorted(want):
            if want[sym]["act"] != ACT_SELL:
                continue          # 买单不归这一趟管 —— **这里不许 pop**:
                                  # 下面那趟买入循环刚设的顺延单会被误删
            if sym not in holdings:
                pending.pop(sym, None)        # 没持仓却要卖 —— 这信号没意义
                continue
            row, px = today.get(sym), (today.get(sym) or {}).get("close")
            if row is None or px is None:
                continue
            if sym in bought_today:
                continue                                  # T+1
            if sealed_at_close(row["limit_down"]):
                pending[sym] = {"act": ACT_SELL, "since": want[sym]["since"]}
                skipped.append({"date": day, "symbol": sym,
                                "name": names.get(sym, sym), "reason": WHY_SEALED})
                continue
            pos = holdings.pop(sym)
            pending.pop(sym, None)
            fill = _fill(px, ACT_SELL)
            amount = fill * pos["shares"]
            fee = _fee(amount, ACT_SELL)
            cash += amount - fee
            round_trips.append(amount - fee - pos["cost_amount"])
            orders.append(_order(day, sym, names, ACT_SELL, pos["shares"], fill,
                                 amount, fee, row, "转空头", want[sym]["since"]))

        # ── 再买 ────────────────────────────────────────────────────
        # 目标金额按**当日净值**均分, 不是按初始本金 —— 赚了之后新仓位跟着变大,
        # 这才是复利; 按本金均分的话账户越赚单笔占比越小, 曲线会被自己压平。
        nav_now = cash + sum(p["shares"] * last_price.get(s, 0.0) for s, p in holdings.items())
        target = nav_now / max_positions
        for sym in sorted(want):
            if want[sym]["act"] != ACT_BUY:
                continue          # 卖单不归这一趟管 —— **这里不许 pop**:
                                  # 上面那趟卖出循环刚设的顺延单会被误删。
                                  # 第一版就栽在这儿: 跌停卖不掉记了 pending,
                                  # 转头被这一行抹掉, 于是永远卖不出去
            if sym in holdings:
                pending.pop(sym, None)        # 已经持有, 这张买单没意义
                continue
            row = today.get(sym)
            px = (row or {}).get("close")
            if row is None or px is None:
                continue
            if len(holdings) >= max_positions:
                # 仓位满**不顺延**: 位置是被别的票占着, 不是市场不让成交。
                # 顺延的话这张单会一直排队, 哪天腾出位置就冷不丁买进一只
                # 当初的信号早已过期的票。
                pending.pop(sym, None)
                skipped.append({"date": day, "symbol": sym,
                                "name": names.get(sym, sym), "reason": WHY_NO_SLOT})
                continue
            if sealed_at_close(row["limit_up"]):
                pending[sym] = {"act": ACT_BUY, "since": want[sym]["since"]}
                skipped.append({"date": day, "symbol": sym,
                                "name": names.get(sym, sym), "reason": WHY_SEALED})
                continue
            fill = _fill(px, ACT_BUY)
            shares = _affordable(min(target, cash), fill, cash)
            if shares < LOT:
                pending.pop(sym, None)
                skipped.append({"date": day, "symbol": sym,
                                "name": names.get(sym, sym), "reason": WHY_NO_CASH})
                continue
            amount = fill * shares
            fee = _fee(amount, ACT_BUY)
            cash -= amount + fee
            holdings[sym] = {"shares": shares, "cost_amount": amount + fee}
            bought_today.add(sym)
            pending.pop(sym, None)
            orders.append(_order(day, sym, names, ACT_BUY, shares, fill,
                                 amount, fee, row, "转多头", want[sym]["since"]))

        mv = sum(p["shares"] * last_price.get(s, 0.0) for s, p in holdings.items())
        nav = cash + mv
        prev = nav_rows[-1]["nav"] if nav_rows else capital
        nav_rows.append({
            "date": day, "nav": round(nav, 2), "cash": round(cash, 2),
            "market_value": round(mv, 2), "positions": len(holdings),
            "ret": round(nav / prev - 1, 6) if prev else 0.0,
        })

    return {
        "nav": nav_rows,
        "orders": orders,
        "positions": _positions(holdings, names, last_price),
        "stats": _stats(nav_rows, orders, round_trips, capital),
        "monthly": _monthly(nav_rows, capital),
        "skipped": skipped,
        "pending": [{"symbol": s, "name": names.get(s, s), **p} for s, p in sorted(pending.items())],
        "as_of": calendar[-1],
        "reason": None if orders else "no_flip",
    }


def _flatten(series: dict[str, dict]) -> tuple[dict[str, dict[str, dict]], dict[str, str], list[str]]:
    """把每票摊平成 {symbol: {date: 当天的一切}}, 并取日历**并集**。

    并集而不是某一只的长度: 各票上市日不同、停牌日不同, 拿其中一只当日历会把
    别的票截断或者错位。
    """
    by_symbol: dict[str, dict[str, dict]] = {}
    names: dict[str, str] = {}
    all_dates: set[str] = set()
    for sym, d in (series or {}).items():
        steps = d.get("steps") or []
        if not steps:
            continue
        days = trend_days(steps)            # ← 多空判据只此一处, 不重写
        dates = [str(x) for x in (d.get("dates") or [])]
        closes = list(d.get("closes") or [])
        lu = list(d.get("limit_up") or [])
        ld = list(d.get("limit_down") or [])
        n = min(len(days), len(dates), len(closes))
        if n == 0:
            continue
        names[sym] = str(d.get("name") or sym)
        table: dict[str, dict] = {}
        for i in range(n):
            table[dates[i]] = {
                "side": days[i].get("side"),
                "flipped": bool(days[i].get("flipped")),
                "state_cn": days[i].get("state_cn"),
                "close": _f(closes[i]),
                "limit_up": bool(lu[i]) if i < len(lu) else False,
                "limit_down": bool(ld[i]) if i < len(ld) else False,
            }
            all_dates.add(dates[i])
        by_symbol[sym] = table
    return by_symbol, names, sorted(all_dates)


def _affordable(budget: float, fill: float, cash: float) -> int:
    """这笔钱买得起几手 —— 手续费也要留出来, 否则会买到现金变负。"""
    if fill <= 0:
        return 0
    shares = int(budget / (fill * (1 + COMMISSION)) // LOT) * LOT
    while shares >= LOT:
        amount = fill * shares
        if amount + _fee(amount, ACT_BUY) <= cash:
            return shares
        shares -= LOT
    return 0


def _order(day: str, sym: str, names: dict, act: str, shares: int, fill: float,
           amount: float, fee: float, row: dict, reason: str, since: str) -> dict:
    return {
        "date": day, "symbol": sym, "name": names.get(sym, sym), "act": act,
        "shares": shares, "price": round(fill, 4), "amount": round(amount, 2),
        "fee": round(fee, 2), "state_cn": row.get("state_cn"), "reason": reason,
        # 封板顺延过几天才成交 —— 0 表示信号当天就成交了(正常情形)
        "signal_date": since, "delayed": since != day,
    }


def _positions(holdings: dict, names: dict, last_price: dict) -> list[dict]:
    out = []
    for sym in sorted(holdings):
        pos = holdings[sym]
        last = last_price.get(sym, 0.0)
        mv = pos["shares"] * last
        cost = pos["cost_amount"]
        out.append({
            "symbol": sym, "name": names.get(sym, sym), "shares": pos["shares"],
            "cost": round(cost / pos["shares"], 4) if pos["shares"] else None,
            "last": round(last, 4), "market_value": round(mv, 2),
            "pnl": round(mv - cost, 2),
            "pnl_pct": round(mv / cost - 1, 6) if cost else None,
        })
    return out


def _monthly(nav_rows: list[dict], capital: float) -> list[dict]:
    """[R357] 逐月收益 —— **每个月单独算, 月与月之间不重叠**。

    用户: 「最好是每个月的收益单独计算」。

    ## 它替掉的是什么

    R332 给的是「近一月 / 近三月」两个**滚动窗口**(最近 20 / 60 个交易日)。
    那两格有个绕不过去的毛病: **近三月把近一月整个包在里面**。九月赚了 10%、
    七八月各亏 4%, 两格印出来是「近一月 +10% / 近三月 +2%」—— 读的人没有任何
    办法从这两个数里还原出七月和八月各自发生了什么。而"哪个月在亏"正是按月
    看的全部意义。

    改成自然月之后每个数只属于它自己那一段, 12 个格子横着一排, 亏的月份自己
    跳出来。

    ## 基准取上个月最后一天, 不是本月第一天

    收益算的是这一段**期间**的变化。拿本月第一个交易日的净值当基准, 会把那天
    自己的涨跌吃掉 —— 一个月的第一天涨 3%, 这个月就凭空少 3%。R332 那个滚动
    窗口当初栽过同一个坑, 注释里写着"起点取该窗口第一个交易日的前一天"。

    第一个月没有上个月可取, 基准就是**本金** —— 与 `nav_rows` 里逐日 `ret`
    第一天的算法同一条(那里也是 `prev = ... if nav_rows else capital`)。

    ## 首尾两个月一律标 `partial`

    回测窗口的起点是 `today - N 天`, **一个任意的日期** —— 它落在月中是常态,
    于是第一个月天然是个残月。最后一个月则是还没走完。

    这不是"可能"而是**结构上如此**, 所以不去猜也不设阈值(「首个交易日在 5 号
    之前就算整月」那种判法要靠交易日历, 而这一层根本没有日历)。宁可把恰好
    完整的那一次也标上 —— 代价是一句多余的提示, 而反过来漏标的代价是**拿半个
    月的 +2% 去和整月的 +2% 比**。

    `days` 一并给出, 让界面能说清这个月到底只有几天。
    """
    if not nav_rows:
        return []
    out: list[dict] = []
    base = capital
    for row in nav_rows:
        month = str(row["date"])[:7]          # YYYY-MM-DD → YYYY-MM
        if not out or out[-1]["month"] != month:
            out.append({"month": month, "_base": base, "nav": row["nav"], "days": 1})
        else:
            out[-1]["nav"] = row["nav"]
            out[-1]["days"] += 1
        # 下一个月的基准 = 这个月最后一天的净值。逐行覆盖, 走完自然是月末那个值。
        base = row["nav"]

    for i, m in enumerate(out):
        b = m.pop("_base")
        m["ret"] = round(m["nav"] / b - 1, 6) if b else 0.0
        m["partial"] = i == 0 or i == len(out) - 1
    return out


def _stats(nav_rows: list[dict], orders: list[dict], round_trips: list[float],
           capital: float) -> dict:
    if not nav_rows:
        return {"days": 0, "orders": 0, "buys": 0, "sells": 0, "round_trips": 0,
                "win": 0, "win_rate": None, "total_ret": 0.0, "max_drawdown": 0.0,
                "best": None, "worst": None}
    peak = capital
    mdd = 0.0
    for r in nav_rows:
        peak = max(peak, r["nav"])
        if peak:
            mdd = min(mdd, r["nav"] / peak - 1)
    wins = [x for x in round_trips if x > 0]
    return {
        "days": len(nav_rows),
        "orders": len(orders),
        "buys": sum(1 for o in orders if o["act"] == ACT_BUY),
        "sells": sum(1 for o in orders if o["act"] == ACT_SELL),
        # 一次完整买卖才算一轮。**还拿着的不算** —— 与 R177「只数已兑现」同一条
        "round_trips": len(round_trips),
        "win": len(wins),
        "win_rate": round(len(wins) / len(round_trips), 4) if round_trips else None,
        "total_ret": round(nav_rows[-1]["nav"] / capital - 1, 6),
        "max_drawdown": round(mdd, 6),
        "best": round(max(round_trips), 2) if round_trips else None,
        "worst": round(min(round_trips), 2) if round_trips else None,
    }


def _empty(capital: float, reason: str) -> dict[str, Any]:
    return {"nav": [], "orders": [], "positions": [],
            "stats": _stats([], [], [], capital), "monthly": [],
            "skipped": [], "pending": [],
            "as_of": None, "reason": reason}
