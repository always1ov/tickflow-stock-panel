"""[fork 增强] 持仓出场线 —— ATR 三阶段(止损 / 保本 / 移动止盈)。

对每只「持有 + 已填成本」的自选,规则层每天确定性计算一条出场线:

  阶段①  浮盈 < 1×ATR      止损线 = 成本 − k×ATR(有六态下关键点且更近时取其为准)
  阶段②  1×ATR ≤ 浮盈 < 2×ATR  保本线 = 成本价
  阶段③  浮盈 ≥ 2×ATR      吊灯止盈线 = 持仓以来最高收盘 − k×ATR(棘轮:只上移不下移)

设计要点:
  - 线的锚点是"持仓以来最高价",绝不是"成本×(1+x%)"——市场不知道用户的成本;
    成本只用来判定阶段与保本。
  - 棘轮用"入场以来逐日 (最高收盘 − k×ATR) 的运行最大值"实现,无状态、可复现。
  - k 默认 3.0;20cm 板(创业板/科创板/北交所)3.5。
  - 全部纯规则零 AI:AI 信号只把算好的线作为持仓上下文接收,不允许自己发明价位。
  - "持仓以来"以标记成本那天(positions.updated_at 的日期)为起点,是近似口径。

出场线同步为监控规则(id: exit_<symbol>),复用现有价格监控引擎盘中评估与推送;
线每日只会上移,规则值略滞后只会让触发更保守,不产生误报。
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

import polars as pl

from app.config import settings

logger = logging.getLogger(__name__)

ATR_WINDOW = 14
# 阶段切换阈值(以 ATR 归一化浮盈计)
BREAKEVEN_AT = 1.0   # 浮盈 ≥ 1×ATR 进入保本阶段
TRAIL_AT = 2.0       # 浮盈 ≥ 2×ATR 进入利润保护阶段
_CALENDAR_SPAN_DAYS = 400

STAGE_CN = {"risk": "止损阶段", "breakeven": "保本阶段", "trail": "利润保护阶段",
            "fatal": "生命线跌破", "lifeline": "仅盯生命线"}
STAGE_LINE_CN = {"risk": "止损线", "breakeven": "保本线", "trail": "移动止盈线",
                 "fatal": "生命线"}
STAGE_ACTION = {"risk": "跌破止损", "breakeven": "保本离场", "trail": "止盈了结",
                "fatal": "无条件清仓离场"}


def k_for(symbol: str) -> float:
    """吊灯系数:20cm 高波动板用 3.5,其余 3.0。"""
    code = symbol.split(".")[0]
    if code.startswith(("30", "68")) or symbol.endswith(".BJ"):
        return 3.5
    return 3.0


def _atr_series(highs: list[float | None], lows: list[float | None],
                closes: list[float], n: int = ATR_WINDOW) -> list[float | None]:
    """TR 的 n 日简单均值。high/low 缺失时退化用 |close 差| 兜底。"""
    trs: list[float] = []
    for i, c in enumerate(closes):
        prev = closes[i - 1] if i > 0 else c
        cands = [abs(c - prev)]
        h, lo = highs[i], lows[i]
        if h is not None and lo is not None:
            cands += [h - lo, abs(h - prev), abs(lo - prev)]
        trs.append(max(cands))
    out: list[float | None] = []
    for i in range(len(trs)):
        if i + 1 < n:
            out.append(None)
        else:
            out.append(sum(trs[i - n + 1: i + 1]) / n)
    return out


def compute_exit(
    dates: list[str],
    highs: list[float | None],
    lows: list[float | None],
    closes: list[float],
    cost: float,
    entry_date: str,
    k: float,
    dn_pivot: float | None = None,
) -> dict | None:
    """计算当前出场线。数据升序;entry_date 为 YYYY-MM-DD。数据不足返回 None。

    生命线 = 20 日均线(用户的绝对底线,自动计算,无需手填):收盘跌破必须
    无条件清仓离场,"这票不再看"。优先级最高:跌破 → fatal;未跌破但 20 日线
    高于阶段线 → 生效线抬到生命线(保护线不允许低于底线)。
    """
    has_cost = bool(cost and cost > 0)
    # 生命线 = MA20(收盘口径), 自动计算
    lifeline = sum(closes[-20:]) / 20 if len(closes) >= 20 else None
    lifeline_src = "ma20" if lifeline else None
    has_life = bool(lifeline and lifeline > 0)
    if len(closes) < ATR_WINDOW + 1 or not (has_cost or has_life):
        return None
    life_cn = "生命线(20日线)"
    atr = _atr_series(highs, lows, closes)
    last_atr = atr[-1]
    if not last_atr or last_atr <= 0:
        return None
    last_close = closes[-1]

    # 没记成本 → 跳过阶段机,仅盯生命线(标了持有就自动盯 20 日线)
    if not has_cost:
        stage = "fatal" if last_close < lifeline else "lifeline"
        return {
            "stage": stage,
            "stage_cn": STAGE_CN[stage],
            "line_cn": life_cn,
            "action": STAGE_ACTION["fatal"],
            "lifeline": round(lifeline, 3),
            "lifeline_src": lifeline_src,
            "line": round(lifeline, 3),
            "atr": round(last_atr, 3),
            "profit_atr": None,
            "highest_close": None,
            "k": k,
            "close": round(last_close, 3),
            "distance_pct": round((lifeline - last_close) / last_close, 4),
            "triggered": last_close < lifeline,
            "as_of": dates[-1],
            "entry_date": entry_date,
            "cost": None,
        }

    # 入场起点(找不到 ≥ entry_date 的行 = 今天刚标记,从最后一日起算)
    start = next((i for i, d in enumerate(dates) if d >= entry_date), len(dates) - 1)

    # 持仓以来最高收盘 + 吊灯棘轮(逐日 hh−k×ATR 的运行最大值)
    hh = 0.0
    ratchet: float | None = None
    for i in range(start, len(closes)):
        hh = max(hh, closes[i])
        if atr[i]:
            cand = hh - k * atr[i]
            ratchet = cand if ratchet is None else max(ratchet, cand)

    profit_atr = (last_close - cost) / last_atr
    if profit_atr >= TRAIL_AT and ratchet is not None:
        stage = "trail"
        line = max(ratchet, cost)  # 进入利润保护后至少守住保本
    elif profit_atr >= BREAKEVEN_AT:
        stage = "breakeven"
        line = cost
    else:
        stage = "risk"
        line = cost - k * last_atr
        # 六态下关键点更近(仍在现价下方)时,以趋势否决位为准——两道防线取先触者
        if dn_pivot is not None and last_close > dn_pivot > line:
            line = dn_pivot
    # [生命线] 绝对底线(20日线或手填价), 优先级最高
    line_cn = STAGE_LINE_CN[stage]
    action = STAGE_ACTION[stage]
    if has_life:
        if last_close < lifeline:
            stage = "fatal"
            line = lifeline
            line_cn = life_cn
            action = STAGE_ACTION["fatal"]
        elif lifeline > line:
            # 阶段线低于底线 → 生效线抬到生命线(保护线不允许低于底线)
            line = lifeline
            line_cn = life_cn
            action = "无条件清仓离场"
    return {
        "stage": stage,
        "stage_cn": STAGE_CN[stage],
        "line_cn": line_cn,
        "action": action,
        "lifeline": round(lifeline, 3) if has_life else None,
        "lifeline_src": lifeline_src if has_life else None,
        "line": round(line, 3),
        "atr": round(last_atr, 3),
        "profit_atr": round(profit_atr, 2),
        "highest_close": round(hh, 3) if hh else None,
        "k": k,
        "close": round(last_close, 3),
        "distance_pct": round((line - last_close) / last_close, 4),
        "triggered": last_close < line,
        "as_of": dates[-1],
        "entry_date": dates[start],
        "cost": cost,
    }


# ================================================================
# 批量计算 + 监控规则同步
# ================================================================

def _entry_date_of(pos: dict) -> str:
    try:
        return datetime.fromisoformat(str(pos.get("updated_at", "")).replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return date.today().isoformat()


def _dn_pivots(repo, sym_closes: dict[str, tuple[list[str], list[float]]]) -> dict[str, float | None]:
    """各持仓票的六态下关键点(止损阶段与趋势否决位取先触者)。"""
    from app.indicators.livermore import compute
    from app.services.livermore_service import WINDOW_TRADING_DAYS, get_effective_threshold
    out: dict[str, float | None] = {}
    for sym, (dts, closes) in sym_closes.items():
        try:
            w_closes, w_dts = closes[-WINDOW_TRADING_DAYS:], dts[-WINDOW_TRADING_DAYS:]
            if len(w_closes) < 40:
                out[sym] = None
                continue
            thr, _ = get_effective_threshold(sym)
            out[sym] = compute(w_closes, w_dts, thr)["last"]["dn_pivot"]
        except Exception as e:  # noqa: BLE001
            logger.debug("dn_pivot for %s failed: %s", sym, e)
            out[sym] = None
    return out


def exit_lines_for_positions(repo) -> dict[str, dict]:
    """全部「持有+已填成本」自选的出场线 {SYMBOL: {...}}。"""
    # [R169] 走合并视图: 只在批次页登记过的票也能自动盯上生命线, 无需再去决策台标一次
    from app.services import effective_positions as positions
    # 标了「持有」就纳入: 没填成本也自动盯生命线(20日线)
    pos_all = {s: p for s, p in positions.load_all().items() if p.get("held")}
    if not pos_all:
        return {}
    syms = sorted(pos_all)
    end = date.today()
    start = end - timedelta(days=_CALENDAR_SPAN_DAYS)

    per_sym: dict[str, tuple[list[str], list[float | None], list[float | None], list[float]]] = {}
    stock_syms = [s for s in syms if repo.resolve_asset_type(s) == "stock"]
    try:
        df = repo.get_daily_batch(stock_syms, start, end, ["symbol", "date", "high", "low", "close"]) \
            if stock_syms else pl.DataFrame()
    except Exception as e:  # noqa: BLE001
        logger.warning("exit lines batch daily failed: %s", e)
        df = pl.DataFrame()
    if not df.is_empty():
        for key, part in df.group_by("symbol"):
            sym = str(key[0] if isinstance(key, tuple) else key)
            part = part.drop_nulls(subset=["close"]).sort("date")
            per_sym[sym] = (
                [str(d) for d in part["date"]],
                part["high"].to_list() if "high" in part.columns else [None] * part.height,
                part["low"].to_list() if "low" in part.columns else [None] * part.height,
                [float(c) for c in part["close"]],
            )
    for sym in syms:
        if sym in per_sym:
            continue
        try:
            d1 = repo.get_daily_asset(repo.resolve_asset_type(sym), sym, start, end,
                                      columns=["date", "high", "low", "close"])
            if not d1.is_empty():
                d1 = d1.drop_nulls(subset=["close"]).sort("date")
                per_sym[sym] = (
                    [str(d) for d in d1["date"]],
                    d1["high"].to_list() if "high" in d1.columns else [None] * d1.height,
                    d1["low"].to_list() if "low" in d1.columns else [None] * d1.height,
                    [float(c) for c in d1["close"]],
                )
        except Exception as e:  # noqa: BLE001
            logger.debug("exit line daily for %s failed: %s", sym, e)

    pivots = _dn_pivots(repo, {s: (v[0], v[3]) for s, v in per_sym.items()})
    out: dict[str, dict] = {}
    for sym, pos in pos_all.items():
        data = per_sym.get(sym)
        if not data:
            continue
        dts, highs, lows, closes = data
        res = compute_exit(dts, highs, lows, closes,
                           float(pos["cost"]) if pos.get("cost") else 0.0,
                           _entry_date_of(pos), k_for(sym), pivots.get(sym))
        if res:
            out[sym] = res
    return out


def sync_exit_rules(lines: dict[str, dict], engine=None) -> None:
    """把出场线落成价格监控规则,并清掉已平仓票的旧规则。

    每票最多两条:
      exit_<sym>      生效出场线(阶段线或生命线, 生命线生效时 critical)
      exitlife_<sym>  生命线独立规则(仅当生命线低于生效线时另立, 时刻盯底线,
                      不依赖每日重算; critical)
    复用现有监控引擎盘中评估 + 通知链路;cooldown 1 天。
    """
    from app.strategy import monitor_rules
    data_dir = settings.data_dir
    try:
        existing = {r["id"]: r for r in monitor_rules.load_all(data_dir)
                    if str(r.get("id", "")).startswith(("exit_", "exitlife_"))}
    except Exception as e:  # noqa: BLE001
        logger.warning("load exit rules failed: %s", e)
        existing = {}

    wanted: set[str] = set()
    changed = False

    def upsert(rid: str, name: str, sym: str, line: float, severity: str, message: str) -> None:
        nonlocal changed
        wanted.add(rid)
        old = existing.get(rid)
        # 值没变(±0.001)且已存在 → 不重写,避免无谓 IO
        if old and old.get("conditions") and abs(float(old["conditions"][0].get("value", 0)) - line) < 0.001:
            return
        rule = monitor_rules.normalize({
            "id": rid, "name": name, "type": "price", "scope": "symbols",
            "symbols": [sym],
            "conditions": [{"field": "close", "op": "<=", "value": line}],
            "cooldown_seconds": 86400, "severity": severity, "message": message,
        })
        try:
            monitor_rules.validate(rule)
            monitor_rules.save_one(data_dir, rule)
            changed = True
        except Exception as e:  # noqa: BLE001
            logger.warning("save exit rule %s failed: %s", rid, e)

    for sym, res in lines.items():
        sym_id = sym.lower().replace(".", "_")[:30]
        line = float(res["line"])
        life = float(res["lifeline"]) if res.get("lifeline") else None
        line_is_life = life is not None and abs(line - life) < 0.001
        line_cn = res["line_cn"]
        life_cn = "生命线(20日线)" if res.get("lifeline_src") == "ma20" else "生命线"
        upsert(
            "exit_" + sym_id,
            f"持仓出场 · {sym} · {line_cn} {line:.2f}",
            sym, line,
            "critical" if line_is_life else "warn",
            (f"{sym} 跌破{life_cn} {line:.2f}!按纪律无条件清仓离场,此票不再看"
             if line_is_life else
             f"{sym} 跌破{line_cn} {line:.2f}({res['stage_cn']}),可考虑{res['action']}"),
        )
        # 生命线低于生效线 → 另立一条 critical 独立盯底线
        if life is not None and not line_is_life and life < line:
            upsert(
                "exitlife_" + sym_id,
                f"{life_cn} · {sym} · {life:.2f}",
                sym, life, "critical",
                f"{sym} 跌破{life_cn} {life:.2f}!按纪律无条件清仓离场,此票不再看",
            )

    for rid in set(existing) - wanted:
        try:
            monitor_rules.delete_one(data_dir, rid)
            changed = True
        except Exception as e:  # noqa: BLE001
            logger.warning("delete exit rule %s failed: %s", rid, e)

    if changed and engine is not None:
        try:
            engine.set_rules(monitor_rules.load_all(data_dir))
        except Exception as e:  # noqa: BLE001
            logger.warning("reload monitor engine failed: %s", e)


def exit_for_symbol(repo, symbol: str) -> dict | None:
    """单只出场线(喂 AI 信号 / 关键价位注入用)。未持有或没填成本返回 None。"""
    from app.services import effective_positions as positions   # [R169] 同上, 含批次派生成本
    sym = (symbol or "").strip().upper()
    pos = positions.load_all().get(sym)
    if not pos or not pos.get("held"):
        return None
    end = date.today()
    start = end - timedelta(days=_CALENDAR_SPAN_DAYS)
    df = repo.get_daily_asset(repo.resolve_asset_type(sym), sym, start, end,
                              columns=["date", "high", "low", "close"])
    if df.is_empty():
        return None
    df = df.drop_nulls(subset=["close"]).sort("date")
    dts = [str(d) for d in df["date"]]
    closes = [float(c) for c in df["close"]]
    pivots = _dn_pivots(repo, {sym: (dts, closes)})
    return compute_exit(
        dts,
        df["high"].to_list() if "high" in df.columns else [None] * df.height,
        df["low"].to_list() if "low" in df.columns else [None] * df.height,
        closes, float(pos["cost"]) if pos.get("cost") else 0.0,
        _entry_date_of(pos), k_for(sym), pivots.get(sym),
    )
