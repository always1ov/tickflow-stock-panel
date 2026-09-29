"""[fork 增强] R562 虚拟账户「跟六态转折」—— 转折模拟盘搬进虚拟账户之后的判定层。

用户: 「以虚拟账户为基础, 移植功能或者升级虚拟账户功能的模块。后面我是要删掉模拟盘的」。

R327 的转折模拟盘是**回放**: 每次打开从日线重算几年, 不落盘。这一层把同一套
规则接到作者的虚拟账户(`strategy/paper.py`, 只追加的成交台账)上, 变成一条
「从开户那天往后真跑」的账。账务 —— 撮合、费用、T+1、涨跌停、除权、净值 ——
**全部用作者那一套**, 这里只决定「今晚挂什么单」。

## 规则(与 R327 逐条对上)

    信号   六态转折日 D —— **收盘确认**的转折, 判据只此一处: flip_trades.trend_days
    执行   **D+1 开盘价**(次日开盘单, 作者的盘后结算撮合)
    方向   转多 → 买入; 转空 → 清仓。不做空
    仓位   等权, 同时最多 N 只; 每笔目标 = 当日净值 ÷ N
    顺序   先卖后买
    满仓   不顺延 —— 位置是被别的票占着, 不是市场不让成交
    封板   没成交就顺延重挂, 方向反了作废

## 为什么是次日开盘, 不是转折当天收盘

用户定案(R562): 「已转折·次日开盘」。转折要等收盘价定下来才算得出, 一条从今天
往后记的账没法按同一根收盘价成交; 14:55 按盘中越线抢跑则违反 R329「一定要根据
转折才能出手」—— 盘中越线**不是**出手理由(见 flip_today 模块 docstring)。
次日开盘与复盘页那份战绩(flip_trades, R287)同一口径。

纯函数: 不读盘、不碰账本。取数与下单在 `flip_follow_run`。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.services.flip_trades import BEAR, BULL
from app.strategy import paper

KIND = "flip"                  # 作者自动跟单规则的 match_kind
MATCH_ID = "six_state"
DEFAULT_MAX_POSITIONS = 10
MAX_POSITIONS_CAP = 50         # 与作者持仓标的数上限同值

# 转折账户的费率 —— 与 R59/R327 那套逐值相同(用户定案: 转折账户用自己的费率)。
# 印花税万 5 是 2023-08 起的现行税率。
FEES = {"commission_pct": 0.0002, "stamp_tax_pct": 0.0005, "slippage_bps": 5.0}

ACT_BUY = "buy"
ACT_SELL = "sell"

# 没能动手的原因码 —— 界面上逐条翻译, 空栏必须自己解释(与 R327 同一套)
WHY_NO_SLOT = "no_slot"        # 仓位满了
WHY_NO_CASH = "no_cash"        # 钱不够一手
WHY_VOIDED = "voided"          # 一直没成交, 方向反了, 这张单作废
WHY_FAILED = "failed"          # 作者撮合拒了(资金/可卖不足等), 不再重挂


# ── 规则: 作者自动跟单里的一种 ────────────────────────────────────────
# 作者的规则一条管买、一条管卖, 仓位按金额或权益百分比; 这一种一条同时管买卖,
# 仓位是「净值 ÷ N」。字段形状不同, 所以校验与规整走这里, paper_auto 只做分派。
def normalize_rule(rule: dict) -> dict:
    return {
        "id": rule.get("id"),
        "name": (rule.get("name") or "").strip(),
        "match_kind": KIND,
        "match_id": MATCH_ID,
        "max_positions": rule.get("max_positions", DEFAULT_MAX_POSITIONS),
        "order_type": "next_open",
        "enabled": rule.get("enabled", True),
        "created_at": rule.get("created_at"),
    }


def validate_rule(rule: dict) -> None:
    if not (rule.get("name") or "").strip():
        raise ValueError("规则名称不能为空")
    n = rule.get("max_positions")
    if isinstance(n, bool) or not isinstance(n, int) or not 1 <= n <= MAX_POSITIONS_CAP:
        raise ValueError(f"同时持有上限必须是 1~{MAX_POSITIONS_CAP} 的整数")


@dataclass
class Plan:
    sells: list[dict] = field(default_factory=list)     # [{symbol, qty, since}]
    buys: list[dict] = field(default_factory=list)      # [{symbol, qty, since, ref_price}]
    cancels: list[str] = field(default_factory=list)    # 在途单要撤的 symbol
    skipped: list[dict] = field(default_factory=list)   # [{symbol, act, since, reason}]
    intents: dict[str, dict] = field(default_factory=dict)  # 今晚过后仍然有效的信号


def decide(
    *,
    day: str,
    rows: dict[str, dict],
    held: dict[str, int],
    intents: dict[str, dict],
    nav: float,
    cash: float,
    max_positions: int,
    commission_pct: float,
    stamp_tax_pct: float,
    slippage_bps: float,
) -> Plan:
    """一天收盘后, 今晚该挂什么单。

    rows     {symbol: {side, flipped, close}} —— 当天有日 K 的票。close 是**不复权**
             收盘价(作者账本的口径), 只用来估算股数。没行情(停牌)的票不在里面
    held     {symbol: 持仓股数}
    intents  上一晚留下的、仍然有效的信号 {symbol: {act, since, order_id?, qty?, est?}}
             order_id 非空 = 单子还在途(pending); 为空 = 封板/停牌没成交, 今晚重挂
    """
    n = max(1, min(int(max_positions or DEFAULT_MAX_POSITIONS), MAX_POSITIONS_CAP))
    plan = Plan()
    slip = float(slippage_bps)

    # ── 今天要处理的信号 = 之前还没办成的 + 今天新转折的 ──────────────────
    want: dict[str, dict] = {}
    for sym, it in sorted(intents.items()):
        row = rows.get(sym)
        if row is None:
            plan.intents[sym] = dict(it)          # 今天没行情 —— 原样留着, 明天再看
            continue
        still = (it["act"] == ACT_BUY and row["side"] == BULL) or \
                (it["act"] == ACT_SELL and row["side"] == BEAR)
        if not still:
            # 方向反了 → 作废(R304 同一条规矩); 在途的单一并撤掉
            if it.get("order_id"):
                plan.cancels.append(sym)
            plan.skipped.append(_skip(sym, it, WHY_VOIDED))
            continue
        want[sym] = dict(it)
    for sym, row in sorted(rows.items()):
        if not row.get("flipped"):
            continue
        act = ACT_BUY if row["side"] == BULL else ACT_SELL
        if sym in want and want[sym]["act"] == act:
            continue                              # 同方向的单已经在办, 不重复
        want[sym] = {"act": act, "since": day}

    # ── 先卖 ──────────────────────────────────────────────────────────
    selling: set[str] = set()
    proceeds = 0.0
    for sym in sorted(want):
        it = want[sym]
        if it["act"] != ACT_SELL:
            continue
        qty = int(it.get("qty") or 0) if it.get("order_id") else int(held.get(sym, 0))
        if qty <= 0:
            continue                              # 没拿着却转空 —— 本来就空仓
        if it.get("order_id"):
            plan.intents[sym] = it                # 在途, 不重复挂
        else:
            plan.sells.append({"symbol": sym, "qty": qty, "since": it["since"]})
            plan.intents[sym] = {"act": ACT_SELL, "since": it["since"], "qty": qty}
        selling.add(sym)
        px = (rows.get(sym) or {}).get("close")
        if px:
            fill = paper.apply_slippage(float(px), ACT_SELL, slip)
            proceeds += qty * fill - paper.sell_fee(qty, fill, commission_pct, stamp_tax_pct)

    # ── 再买 ──────────────────────────────────────────────────────────
    # 目标金额按**当日净值**均分 —— 赚了之后新仓位跟着变大, 这才是复利(R327 同一条)。
    # 能花的钱 = 现金 + 今晚卖单的估算回款 − 在途买单的估算占用: 作者的结算按下单
    # 先后撮合, 卖单先挂, 明早先成交, 钱先回来。
    holding = {s for s, q in held.items() if q > 0} - selling
    inflight = {s for s, it in want.items() if it["act"] == ACT_BUY and it.get("order_id")}
    budget_cash = float(cash) + proceeds - sum(float(want[s].get("est") or 0) for s in inflight)
    target = float(nav) / n
    new_buys = 0
    for sym in sorted(want):
        it = want[sym]
        if it["act"] != ACT_BUY:
            continue
        if sym in inflight:
            plan.intents[sym] = it
            continue
        if held.get(sym, 0) > 0:
            continue                              # 已经拿着, 这张买单没意义
        if len(holding) + len(inflight) + new_buys >= n:
            # 仓位满**不顺延**: 顺延的话哪天腾出位置就冷不丁买进一只信号早已过期的票
            plan.skipped.append(_skip(sym, it, WHY_NO_SLOT))
            continue
        px = float(rows[sym]["close"])
        qty, est = _affordable(min(target, budget_cash), px, budget_cash, commission_pct, slip)
        if qty < paper.LOT_SIZE:
            plan.skipped.append(_skip(sym, it, WHY_NO_CASH))
            continue
        plan.buys.append({"symbol": sym, "qty": qty, "since": it["since"], "ref_price": px})
        plan.intents[sym] = {"act": ACT_BUY, "since": it["since"], "qty": qty, "est": round(est, 2)}
        budget_cash -= est
        new_buys += 1
    return plan


def _skip(sym: str, it: dict, reason: str) -> dict:
    return {"symbol": sym, "act": it["act"], "since": it["since"], "reason": reason}


def _affordable(budget: float, price: float, cash: float, commission_pct: float,
                slippage_bps: float) -> tuple[int, float]:
    """这笔钱买得起几手、估算要花多少 —— 手续费(含作者的最低 5 元)也留出来。"""
    fill = paper.apply_slippage(price, ACT_BUY, slippage_bps)
    if fill <= 0 or budget <= 0:
        return 0, 0.0
    shares = paper.normalize_qty(int(budget / (fill * (1 + commission_pct))))
    while shares >= paper.LOT_SIZE:
        est = fill * shares + paper.buy_fee(shares, fill, commission_pct)
        if est <= cash:
            return shares, est
        shares -= paper.LOT_SIZE
    return 0, 0.0


# 界面上那段规则说明 —— **从后端出, 不在前端誊抄一份**(R203 / R327 同一条理由:
# 誊抄的那份哪天口径改了就开始说假话, 而且不会有任何东西报错)。
RULES = {
    "signal": "六态转折日 —— 当天收盘把状态从多头翻到空头, 或反过来。只认收盘确认的转折",
    "execute": "转折当晚自动挂单, **次一交易日开盘价**成交",
    "direction": [
        "转多(上涨趋势 / 自然回升 / 次级回升)→ 买入",
        "转空(下跌趋势 / 自然回撤 / 次级回撤)→ 清仓",
    ],
    "sizing": "等权 —— 每笔目标金额 = 当日净值 ÷ 同时持有上限",
    "order": "同一晚先卖后买; 仓位满了不排队, 这只就放弃",
    "sealed": "开盘封板没成交 → 方向没变就当晚重挂, 转折反向才作废",
    "universe": "自选股。手上拿着的票从自选删掉, 照样等到转空才卖",
    "crossing": "盘中越线**不是**出手理由 —— 收盘还在线外, 当晚才会挂单",
}
