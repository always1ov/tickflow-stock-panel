"""[fork 增强] R183 模拟盘的**批次视图**与绩效指标。

用户: 「我的批次改造成模拟盘, 全权交给 AI 打理…AI 操盘手现有的数据也要录入」
「要把操盘手的持仓写进批次表」「真实成本和我持仓是分离的, 这个部分是专门给 AI
自己操作的」+ 参考 MarketPulse 的模拟盘结构。

## 为什么是**派生视图**而不是写进作者的 lots.json

作者的 `strategy/lots.py` 每条批次会**派生两条监控规则**(止盈止损 + 到期提醒),
而且整份 lots 会经 `effective_positions` 流进决策台的成本/浮盈、今日总览的持仓
体检、以及出场线。把 AI 的模拟持仓写进去会有两个后果:

  1. 你会收到**模拟持仓**的止损推送 —— 几十只持仓就是上百条规则;
  2. 决策台上「成本/浮盈/止盈线」会变成模拟盘的数字, 而那几列是管真钱用的。

用户已明确真实持仓与这块是分离的, 所以更不该让它们混。于是这里**只做形状转换**:
持仓的唯一真相仍在 `paper_trader` 的账本里, 这一层把它读成批次的样子给界面用。
好处是**没有同步漂移** —— 复制一份到另一个文件, 迟早会出现两边对不上的那天。

作者的 lots 领域层因此**一行未改**, 上游同步零冲突。

## 指标口径参考 MarketPulse

那个项目的 `Metrics` 有一套完整的: 总收益/年化/最大回撤/夏普/胜率/盈亏比/
平均持有/曝光度, 以及**买入持有基准**。本系统原来只显示总资产、持仓/现金、
交易天数 —— 没有基准就不知道赚的是能力还是行情, 没有回撤就不知道过程多难受。
这里补上能从既有数据(nav_history)算出来的那几个, 算不出的**不编**。
"""
from __future__ import annotations

import logging
from datetime import datetime

logger = logging.getLogger(__name__)


# ======================== 批次视图 ========================

def _lot_id(trader_id: str, scope: str, symbol: str) -> str:
    """派生 id。带上 trader 与 scope —— 同一只票在不同操作员/不同账本里是不同批次。"""
    return f"paper_{trader_id}_{scope}_{symbol}".replace(".", "_")[:38]


def lots_for_book(trader_id: str, scope: str, bk: dict,
                  prices: dict[str, float] | None = None) -> list[dict]:
    """一本账的持仓 → 批次形状。

    字段名照抄作者的批次(`cost_price` / `qty` / `buy_date`), 界面上就是批次表;
    另外补几个模拟盘特有的(现价/市值/浮盈), 那是批次表本来没有、但模拟盘必须
    看得见的东西。
    """
    prices = prices or {}
    out: list[dict] = []
    for sym, pos in (bk.get("positions") or {}).items():
        shares = int(pos.get("shares") or 0)
        if shares <= 0:
            continue
        cost = float(pos.get("cost") or 0)
        px = prices.get(sym)
        mv = float(px) * shares if px else None
        out.append({
            "id": _lot_id(trader_id, scope, sym),
            "symbol": sym,
            # ↓ 与作者批次同名同义, 界面可以照批次表渲染
            "cost_price": round(cost, 4),
            "qty": shares,
            "buy_date": pos.get("opened_on"),
            # ↓ 模拟盘特有: 批次表原来不算会计, 这里要看盈亏
            "price": round(float(px), 3) if px else None,
            "market_value": round(mv, 2) if mv is not None else None,
            "pnl_pct": round(float(px) / cost - 1, 4) if (px and cost) else None,
            "trader_id": trader_id,
            "scope": scope,
        })
    # 市值大的排前面 —— 一屏看下去先看到占比重的那几只
    out.sort(key=lambda r: -(r.get("market_value") or 0))
    return out


# ======================== 绩效指标 ========================

def _max_drawdown(navs: list[float]) -> float | None:
    """最大回撤(正数, 0.12 = 回撤过 12%)。

    只用净值序列算, 不需要逐笔成交 —— 这是 nav_history 现成能给的。
    少于两个点给 None 而不是 0: **0 会被读成"从没回撤过"**, 那是假的。
    """
    if len(navs) < 2:
        return None
    peak = navs[0]
    worst = 0.0
    for v in navs:
        peak = max(peak, v)
        if peak > 0:
            worst = max(worst, (peak - v) / peak)
    return round(worst, 4)


def _sharpe(navs: list[float]) -> float | None:
    """夏普(按日、无风险利率取 0、年化 √252)。

    样本太少不给 —— 5 个点算出来的夏普是噪声, 摆出来只会误导。
    """
    if len(navs) < 20:
        return None
    rets = [navs[i] / navs[i - 1] - 1 for i in range(1, len(navs)) if navs[i - 1]]
    if len(rets) < 19:
        return None
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
    sd = var ** 0.5
    if sd <= 0:
        return None
    return round(mean / sd * (252 ** 0.5), 2)


def metrics_for_book(bk: dict, *, benchmark: list[dict] | None = None) -> dict:
    """一本账的绩效。**算不出的给 None, 绝不用 0 顶替。**

    benchmark: [{date, nav}] 同期基准净值(已归一到与本账同一个起点)。
               没有就不报基准 —— 一个没有对照的收益率说明不了任何事情,
               但编一个基准比没有更糟。
    """
    hist = [p for p in (bk.get("nav_history") or []) if p.get("nav")]
    navs = [float(p["nav"]) for p in hist]
    cap = float(bk.get("initial_capital") or 0)
    cur = navs[-1] if navs else (float(bk.get("cash") or 0))

    total_return = round(cur / cap - 1, 4) if cap else None
    days = len(navs)

    out = {
        "days": days,
        "total_return": total_return,
        "max_drawdown": _max_drawdown(navs),
        "sharpe": _sharpe(navs),
        # 曝光度: 有持仓的交易日占比 —— 空仓躺着不动跑平也不叫本事
        "exposure": (round(sum(1 for p in hist if float(p.get("market_value") or 0) > 0)
                           / days, 3) if days else None),
        "benchmark_return": None,
        "excess_return": None,
    }
    if benchmark and cap:
        bn = [float(p["nav"]) for p in benchmark if p.get("nav")]
        if len(bn) >= 2 and bn[0]:
            out["benchmark_return"] = round(bn[-1] / bn[0] - 1, 4)
            if total_return is not None:
                out["excess_return"] = round(total_return - out["benchmark_return"], 4)
    return out


# 净值曲线最多给前端多少个点。原始 nav_history 上限 1000, 每点四个字段;
# 画一条 200px 高的小曲线用不了那么多, 而列表接口是**多个操作员 × 两本账**
# 一起返回的, 不收着点会把响应撑到几百 KB —— 那正是 _summary 当初刻意不带
# nav_history 全量的原因。
MAX_CURVE_POINTS = 260


def nav_curve(bk: dict) -> list[dict]:
    """净值曲线。只出 date/nav 两个字段, 并且只取最近 MAX_CURVE_POINTS 个点。

    **不做等距抽稀** —— 抽稀会把最大回撤的那个谷底抹掉, 而那正是这条曲线
    最该让人看见的地方。宁可只画最近一段, 也不要画一条被削平的全程。
    """
    hist = [p for p in (bk.get("nav_history") or []) if p.get("nav")]
    return [{"date": str(p.get("date") or ""), "nav": round(float(p["nav"]), 2)}
            for p in hist[-MAX_CURVE_POINTS:]]


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")
