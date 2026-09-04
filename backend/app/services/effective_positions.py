"""[fork 增强 R169] 标的级持仓视图 —— 手填标记 ⊕ 批次登记的唯一读入口。

## 为什么需要这一层

仓库里有两套「仓位」, 是**同一件事的两个口径**, 不是重复功能:

- `services/positions.py`(fork): **标的级**, 一只票一条 —— `held` / `cost` /
  `weight`(占总资金 %)。供决策台浮盈、今日总览的组合总仓位与净值回撤、焦点名单
  held 档、出场线(生命线)。
- `strategy/lots.py`(上游): **批次级**, 一只票可有多个批次 —— 每笔买入的
  `cost_price` / `qty` / `buy_date`, 派生止盈止损与到期两条监控规则。作者在模块
  开头写明「只生成监控规则, 不做会计」, 会计属交易口径(上游 issue #230)。

两边唯一真正重合的字段是**成本价**: 用户在批次里填一次, 在决策台又填一次; 加仓后
批次有两条而决策台只有一个数, 要自己算加权平均。这一层就是来消掉这处重复的。

## 合并规则(全部有测试)

1. **手填永远压过派生。** 决策台敲进去的 `cost` / `held` 不会被批次算出来的值
   覆盖 —— 派生值另存 `lot_cost`, 差异算成 `cost_drift_pct` 交给 UI 提示。
2. **批次只填空。** 标了持有但没填成本 → 用批次的**数量加权平均**补上,
   `cost_source` 标成 `lots`。
3. **只在批次里登记过的票也算持仓** —— 否则在批次页记了一笔, 决策台却看不见。
4. **明确标了空仓就是空仓**, 哪怕批次还没删(卖出后忘删批次是常态);
   但 `lot_count` 仍如实报出, 好让界面提示"有批次未清"。
5. **`weight`(仓位%)只能手填** —— 批次不知道总资金, 派生不出来。

## 边界

只在**读**侧合并。写仍然只走 `positions.set_position()` 落 `positions.json`,
批次文件由上游的 `/lots` 端点独占 —— 这条边界是刻意的: 标的级的一个成本价改不回
多个批次, 反向同步在语义上不成立。
"""
from __future__ import annotations

import logging

from app.config import settings

logger = logging.getLogger(__name__)


def _lots_by_symbol() -> dict[str, list[dict]]:
    """{SYMBOL: [批次...]}。读盘失败返回空 —— 决策台/出场线/今日总览都靠这个视图,
    批次出问题不该把持仓也带塌。"""
    from app.strategy import lots as lots_domain

    out: dict[str, list[dict]] = {}
    try:
        raw = lots_domain.load_all(settings.data_dir)
    except Exception as e:  # noqa: BLE001
        logger.warning("load lots failed, 持仓视图降级为纯手填: %s", e)
        return {}
    for lot in raw:
        sym = str(lot.get("symbol") or "").strip().upper()
        if sym:
            out.setdefault(sym, []).append(lot)
    return out


def _aggregate(lots: list[dict]) -> tuple[float | None, float]:
    """(加权平均成本, 总股数)。

    优先按数量加权; 全部批次都没填数量时退回简单平均 —— 作者的校验允许 qty=0
    (只记成本不记数量), 那种批次不该因为权重为 0 被吞掉。数量填了一部分时,
    只用填了的那些算加权, 免得 0 权重把没填数量的批次算没了。
    """
    priced = [x for x in lots if _positive(x.get("cost_price"))]
    if not priced:
        return None, 0.0
    total_qty = sum(float(x.get("qty") or 0) for x in priced)
    with_qty = [x for x in priced if _positive(x.get("qty"))]
    if with_qty:
        qty = sum(float(x["qty"]) for x in with_qty)
        cost = sum(float(x["cost_price"]) * float(x["qty"]) for x in with_qty) / qty
    else:
        cost = sum(float(x["cost_price"]) for x in priced) / len(priced)
    return cost, total_qty


def _positive(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0


def _next_remind(lots: list[dict]) -> str | None:
    """该票最近的一个**未过期**到期日 (YYYY-MM-DD)。全都过期或没设则 None。

    过期的不报: 到期提醒的意义是"还有几天", 已经过去的那条上游的监控引擎自己会处理,
    在持仓体检里再显示一次只是噪音。
    """
    from datetime import date as _date

    today = _date.today().isoformat()
    future = sorted(
        d for d in (str(x.get("remind_date") or "") for x in lots) if d and d >= today
    )
    return future[0] if future else None


def load_all() -> dict[str, dict]:
    """标的级持仓视图 {SYMBOL: {...}}。

    在原 `positions.load_all()` 的字段(`held` / `cost` / `weight` / `updated_at`)
    之上追加, 老字段语义一字不变, 所以所有既有读方换成本函数即可, 无需改用法:

    - `cost_source`: `'manual'` 手填 / `'lots'` 批次派生 / `None` 没有成本
    - `lot_cost`: 批次加权平均(即使手填优先也带出来, 供界面并排显示)
    - `cost_drift_pct`: 手填相对批次派生的偏离 %, 两者都有时才给
    - `lot_count` / `lot_qty`: 该票的批次条数与总股数
    - `next_remind_date`: 该票最近的未过期批次到期日, 供今日总览的持仓体检提示
    """
    from app.services import positions as positions_svc

    manual = positions_svc.load_all()
    by_sym = _lots_by_symbol()

    out: dict[str, dict] = {}
    for sym in set(manual) | set(by_sym):
        entry = manual.get(sym) or {}
        lots = by_sym.get(sym, [])
        lot_cost, lot_qty = _aggregate(lots)

        manual_cost = entry.get("cost")
        if not _positive(manual_cost):
            manual_cost = None

        if manual_cost is not None:
            cost, source = manual_cost, "manual"
        elif lot_cost is not None:
            cost, source = lot_cost, "lots"
        else:
            cost, source = None, None

        # 有手填记录就听手填的 held(标了空仓即空仓, 哪怕批次没删);
        # 只在批次里出现过的票, 有批次即视为持有。
        held = bool(entry.get("held")) if sym in manual else bool(lots)

        drift = None
        if manual_cost is not None and lot_cost:
            drift = (manual_cost - lot_cost) / lot_cost * 100

        out[sym] = {
            **entry,
            "held": held,
            "cost": cost,
            "weight": entry.get("weight"),
            "cost_source": source,
            "lot_cost": lot_cost,
            "cost_drift_pct": drift,
            "lot_count": len(lots),
            "lot_qty": lot_qty,
            "next_remind_date": _next_remind(lots),
        }
    return out
