"""[fork 增强] R562 虚拟账户「跟六态转折」—— 取数与下单那一半。

判定在 `flip_follow.decide`(纯函数)。这一层负责:

  · 找账户上那条「跟六态转折」规则(作者自动跟单里的一种, 见 paper_auto);
  · 把上一晚留下的信号对一遍作者账本里的订单状态 —— 成交了就办完了,
    封板/停牌没成交就今晚重挂, 被别的原因拒了就不再挂;
  · 备齐每只票当天的多空与转折(判据只此一处: flip_trades.trend_days, 窗口与
    个股页同一个: livermore_service);
  · 把判定结果交给作者的 `paper.create_order` / `cancel_order`。下单、校验、撮合
    **一步都不自己做**。

在盘后管道里、作者的「虚拟账户结算」之后跑(见 jobs/daily_pipeline.py):
当天的净值已经定版, 当天的日 K 已经落盘。

## 自己的状态只有一个小文件

`data/paper/accounts/<id>/flip_follow.json`:

    intents  还没办成的信号 {symbol: {act, since, order_id?, qty?, est?}}
             —— 就是 R327 回放里的 `pending`, 落了盘
    log      没能动手的记录(仓位满 / 钱不够 / 作废 / 被拒), 最近 300 条

成交与持仓的唯一事实源仍是作者的 fills.jsonl; 这里不记任何一笔钱。
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from app.services import flip_follow as ff
from app.services.fs_utils import atomic_write_text
from app.strategy import paper, paper_auto

logger = logging.getLogger(__name__)

STATE_FILE = "flip_follow.json"
LOG_KEEP = 300

# 作者撮合拒单时写的原因里, 这几种是「市场不让成交」—— 与 R327「封板不是放弃,
# 是顺延」同一条: 方向没变就今晚重挂。其余(资金不足、可卖不足、手动撤单)不重挂。
# 措辞来自 paper._fill_order / settle_day, 有守卫钉着(test_flip_follow_run)。
_RETRY_MARKS = ("涨停", "跌停", "无行情")


def _state_path(data_dir: Path, account_id: str) -> Path:
    return paper._root(data_dir, account_id) / STATE_FILE


def load_state(data_dir: Path, account_id: str = paper.DEFAULT_ACCOUNT_ID) -> dict:
    p = _state_path(data_dir, account_id)
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"intents": {}, "log": []}
    except Exception as e:  # noqa: BLE001
        logger.warning("flip follow state unreadable %s: %s", p, e)
        return {"intents": {}, "log": []}
    return {"intents": dict(d.get("intents") or {}), "log": list(d.get("log") or [])}


def _save_state(data_dir: Path, account_id: str, state: dict) -> None:
    state["log"] = state["log"][-LOG_KEEP:]
    atomic_write_text(_state_path(data_dir, account_id),
                      json.dumps(state, ensure_ascii=False, indent=2))


def flip_rule(data_dir: Path, account_id: str = paper.DEFAULT_ACCOUNT_ID) -> dict | None:
    """账户上启用中的「跟六态转折」规则; 没有就是 None。"""
    for r in paper_auto.load_auto_rules(data_dir, account_id, enabled_only=True):
        if r.get("match_kind") == ff.KIND:
            return r
    return None


def _refresh(data_dir: Path, account_id: str, intents: dict, day: str) -> tuple[dict, list[dict]]:
    """上一晚的信号对一遍订单状态。返回 (仍有效的信号, 被拒不再挂的记录)。"""
    live: dict[str, dict] = {}
    failed: list[dict] = []
    for sym, it in intents.items():
        oid = it.get("order_id")
        if not oid:
            live[sym] = it
            continue
        order = paper.get_order(data_dir, oid, account_id)
        status = (order or {}).get("status")
        if status == "pending":
            live[sym] = it
        elif status in ("expired", "cancelled"):
            reason = str(order.get("reason") or "")
            if status == "expired" and any(m in reason for m in _RETRY_MARKS):
                live[sym] = {"act": it["act"], "since": it["since"]}     # 今晚重挂
            else:
                failed.append({"date": day, "symbol": sym, "act": it["act"], "since": it["since"],
                               "reason": ff.WHY_FAILED, "detail": reason or "已撤单"})
        # filled / 订单不见了 → 这个信号办完了
    return live, failed


def follow_day(data_dir: Path, day: str, account_id: str = paper.DEFAULT_ACCOUNT_ID,
               *, rows: dict[str, dict]) -> dict | None:
    """按当天收盘确认的转折, 给这个账户挂今晚的单。没有转折规则就返回 None。

    rows  {symbol: {side, flipped, close}} —— 当天有日 K 的票, close 为不复权价。
          生产由 `load_rows` 备齐; 测试直接喂。
    幂等: 同一天重跑, 在途的单不重复挂(判定层按在途信号去重)。
    """
    rule = flip_rule(data_dir, account_id)
    if rule is None:
        return None
    with paper.PAPER_LOCK:
        acc = paper.get_account(data_dir, account_id)
        if acc is None or acc.get("status") != "active":
            return None
        state = load_state(data_dir, account_id)
        intents, failed = _refresh(data_dir, account_id, state["intents"], day)
        held = {s: int(p["qty"]) for s, p in paper.load_positions(data_dir, account_id).items()
                if int(p.get("qty") or 0) > 0}
        nav_rows = paper.load_nav(data_dir, account_id)
        nav = float(nav_rows[-1]["nav"]) if nav_rows else float(acc["cash"])

        plan = ff.decide(
            day=day, rows=rows, held=held, intents=intents,
            nav=nav, cash=float(acc["cash"]), max_positions=int(rule["max_positions"]),
            commission_pct=float(acc["commission_pct"]),
            stamp_tax_pct=float(acc["stamp_tax_pct"]),
            slippage_bps=float(acc["slippage_bps"]),
        )

        for sym in plan.cancels:
            paper.cancel_order(data_dir, intents[sym]["order_id"], account_id)

        source = f"auto:{rule['id']}"
        placed_sells: list[dict] = []
        placed_buys: list[dict] = []
        # 先卖后买: 作者的结算按下单先后撮合, 卖单先挂 → 明早先成交 → 钱先回来
        for act, items, placed in (("sell", plan.sells, placed_sells), ("buy", plan.buys, placed_buys)):
            for item in items:
                sym = item["symbol"]
                # 买单不带参考价: 作者的下单预检按「现在的现金」估, 满仓换股时卖单的钱
                # 要明早才回来, 带上就会被误拒。撮合时作者会按真实现金再校验一次。
                order, err = paper.create_order(
                    data_dir, sym, act, account_id=account_id, qty=int(item["qty"]),
                    order_type="next_open", source=source,
                )
                if err:
                    plan.intents.pop(sym, None)
                    failed.append({"date": day, "symbol": sym, "act": act, "since": item["since"],
                                   "reason": ff.WHY_FAILED, "detail": err})
                    continue
                plan.intents[sym]["order_id"] = order["id"]
                placed.append(item)

        seen = {(x.get("date"), x.get("symbol"), x.get("reason")) for x in state["log"]}
        for x in [{"date": day, **s} for s in plan.skipped] + failed:
            key = (x["date"], x["symbol"], x["reason"])
            if key not in seen:
                state["log"].append(x)
                seen.add(key)
        state["intents"] = plan.intents
        _save_state(data_dir, account_id, state)

    return {
        "account": account_id,
        "rule": rule["id"],
        "sells": placed_sells,
        "buys": placed_buys,
        "cancels": plan.cancels,
        "skipped": plan.skipped,
        "failed": failed,
    }


def load_rows(repo, data_dir: Path, symbols: list[str], day: str) -> dict[str, dict]:
    """每只票当天的 {side, flipped, close}。当天没日 K(停牌、还没同步)的不在里面。

    多空与转折: 与个股页同一个窗口(livermore_service)、同一个阈值(每只票自己的)、
    同一个判据(flip_trades.trend_days)。close: 作者账本的不复权收盘价。
    """
    from app.indicators.livermore import compute
    from app.services import livermore_service
    from app.services.flip_trades import trend_days

    rows: dict[str, dict] = {}
    windows = livermore_service._windows_for_symbols(repo, symbols)
    for sym, (closes, dates) in windows.items():
        if not dates or dates[-1] != day:
            continue
        try:
            threshold, _src = livermore_service.get_effective_threshold(sym)
            last = trend_days(compute(closes, dates, threshold)["steps"])[-1]
            bar = paper.read_daily_bar(data_dir, sym, repo.resolve_asset_type(sym), day)
        except Exception as e:  # noqa: BLE001
            logger.debug("flip follow row %s failed: %s", sym, e)
            continue
        if not bar or not bar.get("close"):
            continue
        rows[sym] = {"side": last["side"], "flipped": bool(last.get("flipped")),
                     "close": float(bar["close"])}
    return rows


def follow_all(repo, day: str) -> list[dict]:
    """盘后管道入口: 每个带「跟六态转折」规则的账户各跑一遍。"""
    from app.services import watchlist

    data_dir = repo.store.data_dir
    out: list[dict] = []
    for acc_id in paper.list_account_ids(data_dir):
        if flip_rule(data_dir, acc_id) is None:
            continue
        # 标的 = 自选 ∪ 手上拿着的 ∪ 还没办成的 —— 从自选里删掉的票, 手上那份照样要等到转空才卖
        try:
            pool = set(watchlist.symbol_set())
        except Exception as e:  # noqa: BLE001
            logger.warning("flip follow: 读自选失败: %s", e)
            pool = set()
        pool |= {s for s, p in paper.load_positions(data_dir, acc_id).items() if int(p.get("qty") or 0) > 0}
        pool |= set(load_state(data_dir, acc_id)["intents"])
        rows = load_rows(repo, data_dir, sorted(pool), day)
        res = follow_day(data_dir, day, acc_id, rows=rows)
        if res is not None:
            out.append(res)
    return out
