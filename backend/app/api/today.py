"""[fork 增强] 今日总览 API —— 决策汇聚层。

把系统各模块的既有产出(六态趋势/AI 信号预案/持仓出场线/监控触发记录)按
"需要行动的紧迫度"聚合成一屏:行动区 → 机会区 → 市场天气 → 持仓体检。
纯聚合零新计算源;仓位姿态为规则判定可复现;AI 导读为可选一次调用。

端点:
  GET  /api/today        聚合总览
  POST /api/today/brief  AI 三句话导读(未配 AI 返回 error)
"""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Request

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/today", tags=["today"])

# 出场线"逼近"阈值(距离 3% 以内进入行动区)
_NEAR_EXIT_PCT = -0.03
# 机会区: 现价距上方突破预案价 2% 以内
_NEAR_BREAKOUT_PCT = 0.02


def _build_overview(repo) -> dict:
    from app.services import positions as positions_svc
    from app.services import stock_signal, watchlist
    from app.services.livermore_service import trends_for_symbols
    from app.services.position_exit import exit_lines_for_positions

    entries = watchlist.list_symbols()
    names = {str(e.get("symbol", "")).upper(): str(e.get("name") or e.get("symbol", ""))
             for e in entries}
    syms = sorted(names)

    trends = trends_for_symbols(repo, syms) if syms else {}
    signals = stock_signal.load_all()
    pos_all = positions_svc.load_all()
    exit_lines = exit_lines_for_positions(repo)

    # ---- ① 行动区 ----
    actions: list[dict] = []
    for sym, ex in exit_lines.items():
        nm = names.get(sym, sym)
        if ex["triggered"]:
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

    # ---- ② 机会区 ----
    opportunities: list[dict] = []
    for sym, t in trends.items():
        if t.get("signal") in ("转多", "回升"):
            opportunities.append({
                "kind": "trend_signal", "symbol": sym, "name": names.get(sym, sym),
                "text": f"{t['signal']}:{t['signal_desc']}(第 {t['duration']} 天)",
            })
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
                opportunities.append({
                    "kind": "near_breakout", "symbol": sym, "name": names.get(sym, sym),
                    "text": f"AI 看多,现价 {close:.2f} 距触发价 {price:.2f} 仅 {gap * 100:.1f}%"
                            f" — 到价{p.get('action') or '关注'}",
                })
                break

    # ---- ③ 市场天气(自选口径)----
    bull = sum(1 for t in trends.values() if t["side"] == "多头")
    bear = len(trends) - bull
    new_bull = sum(1 for t in trends.values() if t.get("signal") in ("转多", "回升"))
    new_bear = sum(1 for t in trends.values() if t.get("signal") in ("转空", "回撤"))
    ratio = bull / len(trends) if trends else 0.0
    if len(trends) < 5:
        posture, posture_reason = "观察", "自选样本不足,暂不判定姿态"
    elif ratio >= 0.7 and new_bear <= max(1, len(trends) // 20):
        posture, posture_reason = "进攻", f"多头占比 {ratio:.0%},新转空仅 {new_bear} 只"
    elif ratio <= 0.4 or new_bear > new_bull * 2:
        posture, posture_reason = "防守", f"多头占比 {ratio:.0%},新转空 {new_bear} 只 > 新转多 {new_bull} 只"
    else:
        posture, posture_reason = "谨慎", f"多头占比 {ratio:.0%},多空转换胶着(新转多 {new_bull} / 新转空 {new_bear})"

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
        })
    holdings.sort(key=lambda h: (not h["exit_triggered"], h["distance_pct"] if h["distance_pct"] is not None else -9))

    as_of = max((t["as_of"] for t in trends.values()), default=None)
    return {
        "as_of": as_of,
        "watchlist_total": len(syms),
        "trend_total": len(trends),
        "actions": actions,
        "opportunities": opportunities,
        "weather": {
            "bull": bull, "bear": bear, "new_bull": new_bull, "new_bear": new_bear,
            "posture": posture, "posture_reason": posture_reason,
        },
        "holdings": holdings,
    }


@router.get("")
def get_today(request: Request):
    """今日总览聚合(行动区/机会区/市场天气/持仓体检)。"""
    return _build_overview(request.app.state.repo)


_BRIEF_SYSTEM = (
    "你是用户的盘前助理。基于给定的今日总览 JSON(行动区/机会区/市场天气/持仓体检),"
    "用 3-4 句中文写一段导读:先说仓位姿态与原因,再点名最需要处理的 1-2 件事(带具体价位),"
    "最后提最值得盯的 1 个机会。不写空话,每句话都要落到具体标的或数字。"
    "只输出导读正文,不要标题、列表或任何格式标记。仅供个人参考。"
)


@router.post("/brief")
async def today_brief(request: Request):
    """AI 三句话导读(可选;未配 AI 返回 error 而非 500)。"""
    from app.services.ai_provider import ai_configured, generate_ai_text
    if not ai_configured():
        return {"error": "未配置 AI"}
    data = _build_overview(request.app.state.repo)
    try:
        text = await generate_ai_text(
            [
                {"role": "system", "content": _BRIEF_SYSTEM},
                {"role": "user", "content": json.dumps(data, ensure_ascii=False)},
            ],
            temperature=0.3,
            max_tokens=300,
        )
        return {"brief": (text or "").strip()}
    except Exception as e:  # noqa: BLE001
        logger.warning("today brief failed: %s", e)
        return {"error": f"AI 调用失败: {e}"}
