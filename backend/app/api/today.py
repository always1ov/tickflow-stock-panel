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


def rank_opportunities(
    trends: dict[str, dict], signals: dict[str, dict], names: dict[str, str],
    min_score: int = _OPP_MIN_SCORE, max_show: int = _OPP_MAX_SHOW,
) -> tuple[list[dict], int]:
    """给买入机会打"把握分"并筛选, 返回 (显示列表, 被滤掉条数)。

    门槛 min_score / max_show 由用户偏好传入(见 services.today_prefs), 默认值即常量。

    纯函数, 无 IO —— 打分口径:
      · 趋势刚转强底分最高, 按信号出现第几天加减(第 1-2 天最佳, 第 4 天起判定
        为已过入场窗口而扣分), 这样"陈年老信号"不会因置信度高就一直占着榜首;
      · AI 信号同向加分、反向重扣(自相矛盾的机会宁可不看);
      · 逼近买入触发价的按距离与置信度打分, 一到价就能行动的最优先。
    低于 min_score 或排在 max_show 之后的都不显示, 只报数量。
    """
    opp_by_sym: dict[str, dict] = {}

    def add(sym: str, kind: str, score: int, text: str, why: list[str]) -> None:
        cur = opp_by_sym.get(sym)
        if cur is None:
            opp_by_sym[sym] = {
                "kind": kind, "symbol": sym, "name": names.get(sym, sym),
                "score": score, "why": why, "text": text,
            }
            return
        if score > cur["score"]:  # 同票命中多个来源: 取更高分的表述, 理由合并
            cur["score"], cur["kind"], cur["text"] = score, kind, text
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
        add(sym, "trend_signal", score,
            f"{t['signal']}:{t['signal_desc']}(第 {dur} 天)", why)

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
                    f" — 到价{p.get('action') or '关注'}", why)
                break

    for o in opp_by_sym.values():
        o["score"] = max(0, min(100, o["score"]))
    ranked = sorted(opp_by_sym.values(), key=lambda o: (-o["score"], o["symbol"]))
    shown = [dict(o, why=" · ".join(o["why"]))
             for o in ranked if o["score"] >= min_score][:max_show]
    return shown, len(ranked) - len(shown)


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

    trends = trends_for_symbols(repo, syms) if syms else {}
    signals = stock_signal.load_all()
    pos_all = positions_svc.load_all()
    exit_lines = exit_lines_for_positions(repo)

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
    prefs = today_prefs.load()
    opportunities, opp_filtered = rank_opportunities(
        trends, signals, names, prefs["min_score"], prefs["max_show"])

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

    # [R11] 大盘红绿灯: 基准指数(沪深300)模式判定, 最终姿态与自选广度取更保守者。
    # 失败只降级不拦路 —— 指数数据缺失时保持纯广度姿态。
    breadth_posture, breadth_reason = posture, posture_reason
    market = None
    try:
        from app.services.market_mode import combine_posture, get_market_mode
        market = get_market_mode(repo)
        posture = combine_posture(market["mode"], breadth_posture)
        posture_reason = f"大盘:{market['reason']};自选:{breadth_reason}"
    except Exception as e:  # noqa: BLE001
        logger.warning("today market mode skipped: %s", e)

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
        "opportunities_filtered": opp_filtered,
        "prefs": prefs,
        "weather": {
            "bull": bull, "bear": bear, "new_bull": new_bull, "new_bear": new_bear,
            "posture": posture, "posture_reason": posture_reason,
            "breadth_posture": breadth_posture,
            "market": market,
        },
        "holdings": holdings,
    }


@router.get("")
def get_today(request: Request):
    """今日总览聚合(行动区/机会区/市场天气/持仓体检)。"""
    return _build_overview(request.app.state.repo)


class PrefsModel(BaseModel):
    """机会区筛选门槛(两项都可选, 只改传入的)。"""

    min_score: int | None = Field(default=None, ge=0, le=100)
    max_show: int | None = Field(default=None, ge=1, le=50)


@router.get("/prefs")
def get_prefs():
    """读取当前筛选门槛。"""
    from app.services import today_prefs
    return today_prefs.load()


@router.put("/prefs")
def put_prefs(body: PrefsModel):
    """修改筛选门槛, 立即对下次总览生效。"""
    from app.services import today_prefs
    return today_prefs.save(min_score=body.min_score, max_show=body.max_show)


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
        {"symbol": c["symbol"], "name": c["name"], "text": c["text"]} for c in cands]
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
