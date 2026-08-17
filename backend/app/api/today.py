"""[fork 增强] 今日总览 API —— 决策汇聚层。

把系统各模块的既有产出(六态趋势/AI 信号预案/持仓出场线/监控触发记录)按
"需要行动的紧迫度"聚合成一屏:行动区 → 机会区 → 市场天气 → 持仓体检。
纯聚合零新计算源;仓位姿态为规则判定可复现;AI 导读为可选一次调用。

端点:
  GET  /api/today        聚合总览
  GET/PUT /api/today/prefs  机会区筛选门槛
  POST /api/today/ai     AI 导读+优选合一(未配 AI 返回 error)
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date, timedelta

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/today", tags=["today"])

# 出场线"逼近"阈值(距离 3% 以内进入行动区)
_NEAR_EXIT_PCT = -0.03
# 机会区: 现价距上方突破预案价 2% 以内
_NEAR_BREAKOUT_PCT = 0.02
# 机会区筛选: 把握分低于此值不显示; 最多显示条数
_OPP_MIN_SCORE = 60
_OPP_MAX_SHOW = 10
# 信号新鲜度加减分: 刚出现窗口最佳, 拖到第 4-5 天已错过入场时机
_FRESH_BONUS = {1: 15, 2: 10, 3: 0, 4: -12, 5: -22}
# [R12] 姿态 → 总仓位基调(占总资金比例上限, 展示用基调而非强制)
POSTURE_CAPS = {"进攻": 0.8, "谨慎": 0.5, "防守": 0.2, "观察": 0.3}
# 把握分 → 单票仓位系数(相对单票上限; 取自 AI-TIS PRD 6.4 的映射思路)
_SCORE_COEF = [(80, 1.0), (60, 0.7), (40, 0.3), (20, 0.1)]


def suggest_position(score: int, atr_pct: float | None,
                     max_single: float, target_vol: float) -> dict | None:
    """把握分 + 波动率 → 单票建议仓位(占总资金比例)。纯函数。

    仓位 = 单票上限 × 把握分系数 × 波动率压缩系数(只降不升, PRD 6.5),
    向下取整到半成; 低于半成给"仅观察仓"。atr_pct 缺失时跳过波动率项。
    """
    coef = 0.0
    for lo, c in _SCORE_COEF:
        if score >= lo:
            coef = c
            break
    if coef <= 0:
        return None
    vol_factor = 1.0
    if atr_pct and atr_pct > 0:
        vol_factor = min(1.0, target_vol / atr_pct)
    frac = max_single * coef * vol_factor
    frac = int(frac / 0.05) * 0.05  # 向下取整到半成, 宁少勿多
    why = f"单票上限{max_single * 10:.0f}成 × 把握系数{coef:.0%}"
    if vol_factor < 1.0:
        why += f" × 波动压缩{vol_factor:.0%}(日波幅 {atr_pct:.1%} 超目标 {target_vol:.0%})"
    if frac < 0.05:
        return {"fraction": 0.0, "text": "仅观察仓", "why": why + " → 不足半成"}
    cheng = frac * 10
    text = f"建议 ≤{cheng:g}成"
    return {"fraction": round(frac, 2), "text": text, "why": why}


def rank_opportunities(
    trends: dict[str, dict], signals: dict[str, dict], names: dict[str, str],
    min_score: int = _OPP_MIN_SCORE, max_show: int = _OPP_MAX_SHOW,
    bench_ret: float | None = None,
) -> tuple[list[dict], int]:
    """给买入机会打"把握分"并筛选, 返回 (显示列表, 被滤掉条数)。

    门槛 min_score / max_show 由用户偏好传入(见 services.today_prefs), 默认值即常量。

    纯函数, 无 IO —— 打分口径:
      · 趋势刚转强底分最高, 按信号出现第几天加减(第 1-2 天最佳, 第 4 天起判定
        为已过入场窗口而扣分), 这样"陈年老信号"不会因置信度高就一直占着榜首;
      · AI 信号同向加分、反向重扣(自相矛盾的机会宁可不看);
      · [R13] 相对强度: 传入大盘 20 日收益(bench_ret)时, 跑赢大盘加分、
        跑输扣分 —— 跑输大盘的"突破"多半是补涨陷阱;
      · 逼近买入触发价的按距离与置信度打分, 一到价就能行动的最优先。
    低于 min_score 或排在 max_show 之后的都不显示, 只报数量。
    """
    opp_by_sym: dict[str, dict] = {}

    def add(sym: str, kind: str, score: int, text: str, why: list[str],
            pivot: float | None = None) -> None:
        cur = opp_by_sym.get(sym)
        if cur is None:
            opp_by_sym[sym] = {
                "kind": kind, "symbol": sym, "name": names.get(sym, sym),
                "score": score, "why": why, "text": text, "pivot": pivot,
            }
            return
        if score > cur["score"]:  # 同票命中多个来源: 取更高分的表述, 理由合并
            cur["score"], cur["kind"], cur["text"], cur["pivot"] = score, kind, text, pivot
        cur["why"] += [w for w in why if w not in cur["why"]]

    for sym, t in trends.items():
        if t.get("signal") not in ("转多", "回升"):
            continue
        dur = int(t.get("duration") or 1)
        score = (70 if t["signal"] == "转多" else 55) + _FRESH_BONUS.get(dur, -30)
        note = "(刚出现,入场窗口最佳)" if dur <= 2 else "(已过最佳入场时机)" if dur >= 4 else ""
        why = [f"{t['signal']}第 {dur} 天{note}"]
        sig = signals.get(sym) or {}
        conf = sig.get("confidence")
        if sig.get("signal") == "buy":
            score += round(int(conf or 50) * 0.2)
            why.append(f"AI 也看多(把握 {conf})" if conf is not None else "AI 也看多")
        elif sig.get("signal") == "sell":
            score -= 40
            why.append("但 AI 看空,信号互相矛盾")
        r20 = t.get("ret_20d")
        if bench_ret is not None and r20 is not None:
            rs = r20 - bench_ret
            if rs >= 0.05:
                score += 8
                why.append(f"近20日跑赢大盘 {rs * 100:.0f} 个点")
            elif rs < -0.05:
                score -= 15
                why.append(f"近20日跑输大盘 {abs(rs) * 100:.0f} 个点,比市场还弱")
            elif rs < 0:
                score -= 8
                why.append("近20日略跑输大盘")
        try:
            t_pivot = float(t["up_pivot"]) if t.get("up_pivot") else None
        except (TypeError, ValueError):
            t_pivot = None
        add(sym, "trend_signal", score,
            f"{t['signal']}:{t['signal_desc']}(第 {dur} 天)", why, t_pivot)

    for sym, sig in signals.items():
        if sym not in names or sig.get("signal") != "buy":
            continue
        t = trends.get(sym)
        close = (t or {}).get("close") or sig.get("close")
        for p in sig.get("watch_points") or []:
            if p.get("direction") != "up" or not close:
                continue
            try:
                price = float(p["price"])
            except (TypeError, ValueError, KeyError):
                continue
            gap = (price - close) / close
            if 0 <= gap <= _NEAR_BREAKOUT_PCT:
                conf = sig.get("confidence")
                score = 62 + round(int(conf or 50) * 0.25) + (8 if gap <= 0.005 else 0)
                why = [f"现价距买入触发价仅 {gap * 100:.1f}%,一到价就能按预案行动"]
                if conf is not None:
                    why.append(f"AI 看多(把握 {conf})")
                add(sym, "near_breakout", score,
                    f"AI 看多,现价 {close:.2f} 距触发价 {price:.2f} 仅 {gap * 100:.1f}%"
                    f" — 到价{p.get('action') or '关注'}", why, price)
                break

    for o in opp_by_sym.values():
        o["score"] = max(0, min(100, o["score"]))
    ranked = sorted(opp_by_sym.values(), key=lambda o: (-o["score"], o["symbol"]))
    shown = [dict(o, why=" · ".join(o["why"]))
             for o in ranked if o["score"] >= min_score][:max_show]
    return shown, len(ranked) - len(shown)


def build_pyramid_plan(fraction: float, pivot: float | None,
                       probe_pct: int, confirm_pct: int, days: int) -> str | None:
    """[R15] 金字塔建仓路径(利弗莫尔式): 终点仓位拆成 试仓 → 确认加 → 上满。

    每一步由价格确认驱动而非时间驱动: 试仓买"对不对", 站稳加仓买"稳不稳",
    回踩不破上满买"强不强"; 跌回关键点下方清掉试仓、整个计划作废 ——
    快速上满有约束, 假突破最多损失一个试仓。
    目标不足 1 成时不拆步(一步到位没必要分批), 返回 None。纯函数。
    """
    if fraction < 0.1:
        return None
    confirm_pct = max(confirm_pct, probe_pct + 10)

    def half_cheng(x: float) -> float:  # 向下取整到半成
        return int(x / 0.05) * 0.05

    def cheng(x: float) -> str:
        return f"{x * 10:g}成"

    probe = max(0.05, half_cheng(fraction * probe_pct / 100))
    confirm = max(probe + 0.05, half_cheng(fraction * confirm_pct / 100))
    px = f" {pivot:.2f} " if pivot else "突破价"
    if confirm >= fraction:  # 目标较小, 两步走
        return (f"先试 {cheng(probe)} → 站稳{px}{days} 日上满 {cheng(fraction)};"
                f"收盘跌回{px}下方,清掉试仓、计划作废")
    return (f"先试 {cheng(probe)} → 站稳{px}{days} 日加至 {cheng(confirm)}"
            f" → 回踩不破上满 {cheng(fraction)};收盘跌回{px}下方,清掉试仓、计划作废")


def holding_stance(exit_triggered: bool, distance_pct: float | None,
                   trend_side: str | None, ai_signal: str | None,
                   trend_signal: str | None) -> tuple[str, str]:
    """[R13] 持仓操作档位: 离场/减仓/加仓/持有(规则版, 只用已有字段)。

    离场纪律由出场线/生命线兜底(最高优先); 减仓是"趋势或 AI 转坏但还没破线"
    的中间档; 加仓要求趋势多头 + AI 看多 + 离出场线还有安全距离, 三者缺一不可。
    """
    if exit_triggered:
        return "离场", "已跌破出场线,按纪律执行,不猜反弹"
    if trend_side == "空头":
        return "减仓", "持有票已处于空头趋势,先降低暴露"
    if ai_signal == "sell":
        return "减仓", "AI 转看空,与持仓方向矛盾"
    if distance_pct is not None and distance_pct >= -0.015:
        return "减仓", "距出场线不足 1.5%,提前减一部分比破线再动手从容"
    if (trend_side == "多头" and ai_signal == "buy"
            and trend_signal in ("转多", "回升")
            and (distance_pct is None or distance_pct < -0.05)):
        return "加仓", "趋势刚走强 + AI 看多 + 离出场线还有安全距离"
    return "持有", "无触发条件,按既定计划持有"


def _build_overview(repo) -> dict:
    from app.services import positions as positions_svc
    from app.services import stock_signal, today_prefs, watchlist
    from app.services.livermore_service import trends_for_symbols
    from app.services.position_exit import exit_lines_for_positions

    entries = watchlist.list_symbols()
    syms_raw = [str(e.get("symbol", "")).upper() for e in entries if e.get("symbol")]
    # 自选表只存代码; 中文名走 instruments 统一名称入口(股票+ETF+指数), 查不到再退回代码
    name_map = repo.get_name_map(syms_raw)
    names = {s: str(name_map.get(s) or s) for s in syms_raw}
    syms = sorted(names)

    # [R16] 自选实时: 叠加层有数据时, 当天实时价参与六态判定与所有距离计算(盘中口径);
    # 开关关闭则为空 dict, 一切保持收盘口径, 行为与从前完全一致
    from app.services.live_quotes import as_live_entries, watchlist_live_map
    live = watchlist_live_map(repo)
    trends = trends_for_symbols(repo, syms, live=as_live_entries(live)) if syms else {}
    signals = stock_signal.load_all()
    pos_all = positions_svc.load_all()
    exit_lines = exit_lines_for_positions(repo)
    # 出场线的现价/距离改用实时价(纪律判定 triggered/fatal 仍是收盘口径, 不动)
    for sym, ex in exit_lines.items():
        lv = live.get(sym)
        if lv and ex.get("line"):
            ex["close"] = lv["close"]
            ex["distance_pct"] = round((ex["line"] - lv["close"]) / lv["close"], 4)

    # ---- ① 行动区 ----
    actions: list[dict] = []
    for sym, ex in exit_lines.items():
        nm = names.get(sym, sym)
        if ex["stage"] == "fatal":
            life_cn = "生命线(20日线)" if ex.get("lifeline_src") == "ma20" else "生命线"
            actions.append({
                "kind": "lifeline_broken", "severity": "high", "symbol": sym, "name": nm,
                "text": f"已跌破{life_cn} {ex['line']:.2f}!按纪律无条件清仓离场 —— 这票不看了",
            })
        elif ex["triggered"]:
            actions.append({
                "kind": "exit_triggered", "severity": "high", "symbol": sym, "name": nm,
                "text": f"已跌破{ex['line_cn']} {ex['line']:.2f}({ex['stage_cn']}),可考虑{ex['action']}",
            })
        elif ex["distance_pct"] >= _NEAR_EXIT_PCT:
            actions.append({
                "kind": "exit_near", "severity": "mid", "symbol": sym, "name": nm,
                "text": f"距{ex['line_cn']} {ex['line']:.2f} 仅 {abs(ex['distance_pct']) * 100:.1f}%,跌破则{ex['action']}",
            })
    for sym, pos in pos_all.items():
        t = trends.get(sym)
        if pos.get("held") and t and t["state"] == "DT":
            actions.append({
                "kind": "trend_break", "severity": "high", "symbol": sym, "name": names.get(sym, sym),
                "text": f"持有票已转入下跌趋势(第 {t['duration']} 天,{t['action']})",
            })
    # 近 24h 监控触发记录(含出场线规则与用户自建提醒)
    try:
        from app.services import alert_store
        events = alert_store.list_recent(repo.store.data_dir, days=1, limit=50)
        for ev in events[:10]:
            sym = str(ev.get("symbol", "")).upper()
            msg = str(ev.get("message") or ev.get("name") or "").strip()
            if msg:
                actions.append({
                    "kind": "alert", "severity": "mid", "symbol": sym,
                    "name": names.get(sym, sym or "—"),
                    "text": f"监控触发:{msg}",
                })
    except Exception as e:  # noqa: BLE001
        logger.debug("today alerts skipped: %s", e)
    sev_rank = {"high": 0, "mid": 1}
    actions.sort(key=lambda a: sev_rank.get(a["severity"], 9))

    # ---- ② 机会区(门槛可由用户调; 卖出提醒都在行动区, 永不过滤) ----
    # [R11/R13] 大盘模式提前取: 姿态合成与相对强度都要用; 失败只降级不拦路
    market = None
    try:
        from app.services.market_mode import get_market_mode
        market = get_market_mode(repo)
    except Exception as e:  # noqa: BLE001
        logger.warning("today market mode skipped: %s", e)
    bench_ret = ((market or {}).get("metrics") or {}).get("ret_20d")
    prefs = today_prefs.load()
    opportunities, opp_filtered = rank_opportunities(
        trends, signals, names, prefs["min_score"], prefs["max_show"], bench_ret)
    # [R18] 盘中口径标注: 实时价参与了判定的趋势类新信号是"临时信号",
    # 收盘价可能收回去 —— 标记出来, 前端提示"待收盘确认", 防止盘中追假信号
    if live:
        for o in opportunities:
            if o["kind"] == "trend_signal" and o["symbol"] in live:
                o["intraday"] = True

    # ---- ③ 市场天气(自选口径)----
    bull = sum(1 for t in trends.values() if t["side"] == "多头")
    bear = len(trends) - bull
    new_bull = sum(1 for t in trends.values() if t.get("signal") in ("转多", "回升"))
    new_bear = sum(1 for t in trends.values() if t.get("signal") in ("转空", "回撤"))
    ratio = bull / len(trends) if trends else 0.0
    if len(trends) < 5:
        posture, posture_reason = "观察", "自选股票太少,暂不下结论"
    elif ratio >= 0.7 and new_bear <= max(1, len(trends) // 20):
        posture, posture_reason = "进攻", f"{ratio:.0%} 的自选在涨势中,今天刚转弱的只有 {new_bear} 只,大环境偏暖"
    elif ratio <= 0.4 or new_bear > new_bull * 2:
        posture, posture_reason = "防守", f"在涨势中的自选只剩 {ratio:.0%},今天转弱的({new_bear} 只)明显多于转强的({new_bull} 只),大环境偏冷"
    else:
        posture, posture_reason = "谨慎", f"{ratio:.0%} 的自选在涨势中,但今天转强({new_bull} 只)和转弱({new_bear} 只)的数量差不多,涨跌方向还不明朗"

    # [缺口②] 全市场宽度: 复用市场环境(regime)历史的涨跌家数, 普跌日压制进攻姿态。
    # regime 未跑批/数据过旧时静默跳过, 不新增任何计算源。
    market_breadth = None
    try:
        from app.services.regime_builder import load_regime_history
        rh = load_regime_history(repo.store.data_dir)
        if not rh.is_empty() and {"date", "up_count", "down_count"} <= set(rh.columns):
            last = rh.sort("date").tail(1)
            b_date = str(last["date"][0])
            up_n, dn_n = int(last["up_count"][0]), int(last["down_count"][0])
            fresh = (date.today() - date.fromisoformat(b_date[:10])).days <= 7
            if fresh and (up_n + dn_n) > 0:
                market_breadth = {"date": b_date[:10], "up": up_n, "down": dn_n, "capped": False}
                if dn_n > up_n * 2 and posture == "进攻":
                    posture = "谨慎"
                    posture_reason += f";全市场 {up_n}涨/{dn_n}跌,普跌日不冒进"
                    market_breadth["capped"] = True
    except Exception as e:  # noqa: BLE001
        logger.debug("today market breadth skipped: %s", e)

    # [R11] 大盘红绿灯: 最终姿态与自选广度取更保守者(market 已在机会区前取好)
    breadth_posture, breadth_reason = posture, posture_reason
    if market:
        from app.services.market_mode import combine_posture
        posture = combine_posture(market["mode"], breadth_posture)
        posture_reason = f"大盘:{market['reason']};自选:{breadth_reason}"
    if market_breadth and not market_breadth["capped"]:
        posture_reason += f";全市场 {market_breadth['up']}涨/{market_breadth['down']}跌"

    # ---- ④ 持仓体检 ----
    holdings: list[dict] = []
    for sym, pos in pos_all.items():
        if not pos.get("held") or sym not in names:
            continue
        t = trends.get(sym)
        ex = exit_lines.get(sym)
        sig = signals.get(sym)
        close = (ex or {}).get("close") or (t or {}).get("close")
        cost = pos.get("cost")
        stance, stance_why = holding_stance(
            (ex or {}).get("triggered", False), (ex or {}).get("distance_pct"),
            (t or {}).get("side"), (sig or {}).get("signal"), (t or {}).get("signal"))
        holdings.append({
            "symbol": sym, "name": names.get(sym, sym),
            "close": close, "cost": cost,
            "pnl_pct": round((close - cost) / cost, 4) if close and cost else None,
            "stage_cn": (ex or {}).get("stage_cn"),
            "line": (ex or {}).get("line"),
            "line_cn": (ex or {}).get("line_cn"),
            "distance_pct": (ex or {}).get("distance_pct"),
            "exit_triggered": (ex or {}).get("triggered", False),
            "trend_cn": (t or {}).get("state_cn"),
            "trend_duration": (t or {}).get("duration"),
            "trend_side": (t or {}).get("side"),
            "signal": (sig or {}).get("signal"),
            "stance": stance, "stance_why": stance_why,
            "weight": pos.get("weight"),
        })
    holdings.sort(key=lambda h: (not h["exit_triggered"], h["distance_pct"] if h["distance_pct"] is not None else -9))

    as_of = max((t["as_of"] for t in trends.values()), default=None)

    # [R13] 组合汇总: 逐票之上的整体视角
    portfolio = None
    if holdings:
        pnls = [h["pnl_pct"] for h in holdings if h["pnl_pct"] is not None]
        portfolio = {
            "count": len(holdings),
            "avg_pnl": round(sum(pnls) / len(pnls), 4) if pnls else None,
            "triggered": sum(1 for h in holdings if h["exit_triggered"]),
            "near_exit": sum(1 for h in holdings
                             if not h["exit_triggered"] and h["distance_pct"] is not None
                             and h["distance_pct"] >= _NEAR_EXIT_PCT),
            "bearish": sum(1 for h in holdings if h["trend_side"] == "空头"),
            "total_weight": None, "nav": None, "drawdown": None,
            "posture_cap": POSTURE_CAPS.get(posture, 0.3),
        }
        # [缺口③④] 填了仓位比例才有组合层视角: 总仓位 vs 姿态基调 + 净值回撤纪律
        weighted = [h for h in holdings if h.get("weight")]
        if weighted:
            total_weight = round(sum(h["weight"] for h in weighted), 1)
            nav = 1.0 + sum(h["weight"] / 100 * (h["pnl_pct"] or 0) for h in weighted)
            portfolio["total_weight"] = total_weight
            try:
                from app.services import portfolio_history
                snap = portfolio_history.update(as_of or str(date.today()), nav)
                portfolio["nav"] = snap["nav"]
                portfolio["drawdown"] = snap["drawdown"]
                dd_limit = prefs["max_drawdown"] / 100
                if snap["drawdown"] >= dd_limit:
                    actions.append({
                        "kind": "portfolio_drawdown", "severity": "high",
                        "symbol": "", "name": "组合整体",
                        "text": f"组合净值从高点回撤 {snap['drawdown'] * 100:.1f}%,已过纪律线 {prefs['max_drawdown']}%"
                                f" —— 按纪律整体降仓,至少降到防守档(≤2成),别跟亏损讲道理",
                    })
            except Exception as e:  # noqa: BLE001
                logger.warning("portfolio history skipped: %s", e)
            cap = POSTURE_CAPS.get(posture, 0.3)
            if total_weight / 100 > cap + 0.001:
                actions.append({
                    "kind": "over_allocated", "severity": "mid",
                    "symbol": "", "name": "组合整体",
                    "text": f"当前总仓位 {total_weight / 10:.1f}成,超过{posture}姿态的基调上限 {cap * 10:.0f}成"
                            f" —— 建议把差额 {(total_weight / 100 - cap) * 10:.1f}成 减下来",
                })
            sev_rank = {"high": 0, "mid": 1}
            actions.sort(key=lambda a: sev_rank.get(a["severity"], 9))

    # [R12] 仓位建议: 姿态定总仓位基调, 把握分×波动率定单票建议(仅展示, 不是指令)
    for o in opportunities:
        atr_pct = None
        try:
            df = repo.get_daily_asset(
                repo.resolve_asset_type(o["symbol"]), o["symbol"],
                date.today() - timedelta(days=30), date.today(),
                columns=["date", "close", "atr_14"],
            )
            if not df.is_empty() and "atr_14" in df.columns and "close" in df.columns:
                last = df.sort("date").tail(1)
                c, a = last["close"][0], last["atr_14"][0]
                if c and a:
                    atr_pct = float(a) / float(c)
        except Exception as e:  # noqa: BLE001
            logger.debug("today atr load skipped for %s: %s", o["symbol"], e)
        o["advice"] = suggest_position(
            o["score"], atr_pct, prefs["max_single"] / 100, prefs["target_vol"] / 100)
        # [R15] 建仓路径: 有仓位建议才有路径; 关键点价位来自六态上关键点/AI 触发价
        if o["advice"]:
            o["advice"]["plan"] = build_pyramid_plan(
                o["advice"]["fraction"], o.get("pivot"),
                prefs["pyramid_probe"], prefs["pyramid_confirm"], prefs["pyramid_days"])

    return {
        "as_of": as_of,
        "watchlist_total": len(syms),
        "trend_total": len(trends),
        "live": bool(live),
        "live_count": len(live),
        "actions": actions,
        "opportunities": opportunities,
        "opportunities_filtered": opp_filtered,
        "prefs": prefs,
        "position_hint": {
            "posture_cap": POSTURE_CAPS.get(posture, 0.3),
            "max_single": prefs["max_single"], "target_vol": prefs["target_vol"],
        },
        "weather": {
            "bull": bull, "bear": bear, "new_bull": new_bull, "new_bear": new_bear,
            "posture": posture, "posture_reason": posture_reason,
            "breadth_posture": breadth_posture,
            "market": market,
            "market_breadth": market_breadth,
        },
        "holdings": holdings,
        "portfolio": portfolio,
    }


@router.get("")
def get_today(request: Request):
    """今日总览聚合(行动区/机会区/市场天气/持仓体检)。"""
    return _build_overview(request.app.state.repo)


class PrefsModel(BaseModel):
    """机会区筛选门槛(两项都可选, 只改传入的)。"""

    min_score: int | None = Field(default=None, ge=0, le=100)
    max_show: int | None = Field(default=None, ge=1, le=50)
    max_single: int | None = Field(default=None, ge=5, le=100)
    target_vol: int | None = Field(default=None, ge=1, le=10)
    max_drawdown: int | None = Field(default=None, ge=3, le=30)
    pyramid_probe: int | None = Field(default=None, ge=10, le=60)
    pyramid_confirm: int | None = Field(default=None, ge=40, le=90)
    pyramid_days: int | None = Field(default=None, ge=1, le=5)


@router.get("/prefs")
def get_prefs():
    """读取当前筛选门槛。"""
    from app.services import today_prefs
    return today_prefs.load()


@router.put("/prefs")
def put_prefs(body: PrefsModel):
    """修改筛选门槛, 立即对下次总览生效。"""
    from app.services import today_prefs
    return today_prefs.save(min_score=body.min_score, max_show=body.max_show,
                            max_single=body.max_single, target_vol=body.target_vol,
                            max_drawdown=body.max_drawdown,
                            pyramid_probe=body.pyramid_probe,
                            pyramid_confirm=body.pyramid_confirm,
                            pyramid_days=body.pyramid_days)


_AI_SYSTEM = """你是用户的盘前参谋,有 15 年 A 股一线交易经验。输入分两部分:今日总览 JSON(市场天气/需要行动/持仓体检),和每只候选买入机会的真实日 K 数据。一次调用完成两件事:先做任务二(优选),再基于优选结果写任务一(导读),两者结论必须一致。

## 任务二: 优选(picks)

对每只候选,**看它的日 K 数据做独立判断**,再横向对比,选出 1-3 只。判断依据只能是量价本身:

1. **突破的量能质量**:突破当天有没有放量?量比多少?缩量突破是假突破,放量才是真金
2. **突破后的持续性**:突破后回踩了没有?回踩守住关键位是好事,直接掉回去就是失败突破
3. **当前位置的风险**:现价离突破点多远?已经拉开一大截的,现在追等于给前面的人抬轿;紧贴突破点的才有好的风险收益比
4. **上方阻力空间**:离上方压力位还有多少空间?空间太小的机会不值得占用仓位
5. **K 线形态质量**:是干净利落的放量长阳,还是上影线很长、量价背离、连续跳空的透支形态

硬性要求:
- **不许拿"规则分高""AI 看多""信号共振"当理由** —— 这些是筛选前就知道的,把它们复述一遍等于没分析。理由必须来自你在 K 线数据里**实际看到的东西**,带上具体数字(量比、涨幅、距离、价位)
- **规则分只是粗筛门票,不是排序依据**。分低但量价扎实的可以选,分高但量能虚、位置差的要果断放弃
- 几只都不理想就少选甚至不选(picks 给空数组)。**宁缺毋滥,空仓等待也是决策**
- 每只理由 ≤35 字,大白话,让不懂术语的人看懂

## 任务一: 导读(brief)

用 3-4 句大白话写一段盘前导读:先说仓位姿态与原因;再点名最需要处理的 1-2 件事(带具体价位;行动区为空就明说今天无需操作);最后落到你在任务二选出的头号机会,说清为什么是它、等什么触发条件(picks 为空就如实说今天没有值得出手的)。每句话都落到具体标的或数字,不写空话;不用"胶着""博弈""多空拉锯"这类行话;正文不要标题、列表或格式标记。

## 输出

只输出一个 JSON 对象,不要任何其他文字:
{"brief": "导读正文", "picks": [{"symbol": "代码", "reason": "基于量价的具体理由"}]}

仅供用户个人参考,不构成投资建议。"""

# 优选送审的候选上限与每只的日 K 窗口(控制单次调用成本)
_SELECT_MAX_CANDIDATES = 8
_SELECT_KLINE_DAYS = 20
# 横向对比够用的精简列(比四维分析窄, 8 只 × 20 根仍在可控 token 内)
_SELECT_COLS = [
    "date", "open", "high", "low", "close", "change_pct",
    "volume", "vol_ratio_5d", "turnover_rate",
    "ma5", "ma10", "ma20", "ma60", "macd_hist", "rsi_14", "atr_14",
]


def _candidate_market_data(repo, cands: list[dict]) -> list[dict]:
    """给每只候选附上真实日 K 与关键价位, 供 AI 做量价层面的横向对比。

    取不到数据的候选仍然保留(标注 kline_error), 让 AI 知道它无从判断而不是凭空编。
    """
    from app.indicators.levels import compute_levels, summarize_levels
    from app.services.stock_analyzer import _clean_rows, _load_kline

    out: list[dict] = []
    for c in cands:
        item = {
            "symbol": c["symbol"], "name": c["name"],
            "规则分": c["score"], "规则依据": c["why"], "信号摘要": c["text"],
        }
        try:
            df = _load_kline(repo, c["symbol"])
            if df.is_empty():
                item["kline_error"] = "暂无日 K 数据"
            else:
                close = float(df.tail(1)["close"][0]) if "close" in df.columns else None
                item["关键价位"] = summarize_levels(compute_levels(df), close)
                item[f"最近{_SELECT_KLINE_DAYS}日K"] = _clean_rows(
                    df.tail(_SELECT_KLINE_DAYS), _SELECT_COLS)
        except Exception as e:  # noqa: BLE001
            logger.warning("select kline load failed for %s: %s", c["symbol"], e)
            item["kline_error"] = "行情读取失败"
        out.append(item)
    return out


@router.post("/ai")
async def today_ai(request: Request):
    """AI 导读+优选合一: 一次调用生成盘前导读, 并基于真实量价从候选里精选 1-3 只。

    未配 AI 返回 error 而非 500。导读末尾提的机会即优选结果, 两者不会互相矛盾。
    """
    from app.services.ai_provider import ai_configured, generate_ai_text
    if not ai_configured():
        return {"error": "未配置 AI"}
    repo = request.app.state.repo
    data = _build_overview(repo)
    cands = data["opportunities"][:_SELECT_MAX_CANDIDATES]
    # 总览瘦身: 候选明细单独带 K 线送审, 机会区在总览里只留给导读定位用的短句
    overview = {k: v for k, v in data.items() if k != "opportunities"}
    overview["机会区摘要"] = [
        {"symbol": c["symbol"], "name": c["name"], "text": c["text"],
         "建议仓位": (c.get("advice") or {}).get("text"),
         "建仓路径": (c.get("advice") or {}).get("plan")} for c in cands]
    payload = {
        "今日总览": overview,
        "候选买入机会(含真实日K)": _candidate_market_data(repo, cands) if cands else [],
    }
    try:
        text = await generate_ai_text(
            [
                {"role": "system", "content": _AI_SYSTEM},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            temperature=0.2,
            max_tokens=800,
        )
        m = re.search(r"\{.*\}", text or "", re.S)
        obj = json.loads(m.group(0)) if m else {}
        valid = {c["symbol"] for c in cands}
        picks = []
        for p in (obj.get("picks") or [])[:3]:
            s = str(p.get("symbol", "")).upper()
            if s in valid:
                picks.append({"symbol": s, "reason": str(p.get("reason") or "").strip()[:60]})
        return {
            "brief": str(obj.get("brief") or "").strip(),
            "picks": picks,
            "analyzed": len(cands),
        }
    except Exception as e:  # noqa: BLE001
        logger.warning("today ai failed: %s", e)
        return {"error": f"AI 调用失败: {e}"}
