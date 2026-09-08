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
import time
from datetime import date, timedelta

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/today", tags=["today"])

# 出场线"逼近"阈值(距离 3% 以内进入行动区)
_NEAR_EXIT_PCT = -0.03

# [R179] 行动区四档。原来只有 high/mid 两档, 于是「跌破生命线·无条件清仓」和
# 「持有票转入下跌趋势」并列 —— 前者是**无条件**的, 后者要看情况, 不是一个量级;
# 谁排在上面全靠 dict 迭代顺序, 等于没定。
#
#   fatal 无条件清仓(跌破生命线) —— 这一档只放"不用想, 照做"的
#   high  该处理了(跌破止损线 / 转下跌趋势 / 组合回撤过纪律线)
#   mid   要盯着(逼近出场线 / 超配)
#   low   **已经发生过的事**(监控触发记录), 不是此刻的状态, 永远排最后
SEVERITY_RANK = {"fatal": 0, "high": 1, "mid": 2, "low": 3}
# 监控触发最多列几条 —— 它是历史记录, 不该把此刻要处理的挤下去
_MAX_ALERT_ACTIONS = 3
# 机会区: 现价距上方突破预案价 2% 以内
_NEAR_BREAKOUT_PCT = 0.02
# 机会区筛选: 把握分低于此值不显示; 最多显示条数
# [R134] 上限 10 → 15: v2 的分数不再饱和(v1 榜首一片并列 100), 名次真的分得开了,
# 多看 5 条才有意义; 用户也明确要"只显示前 15 个"。
_OPP_MIN_SCORE = 60
_OPP_MAX_SHOW = 15
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


def score_opportunities(
    trends: dict[str, dict], signals: dict[str, dict], names: dict[str, str],
    bench_ret: float | None = None,
    extras: dict[str, dict] | None = None,
    bench_ret_120d: float | None = None,
) -> tuple[list[dict], dict]:
    """[R134] 买入机会评分 v2。返回 (完整排序列表, 门槛体检)。

    门槛体检 = {"candidates": 进门槛前有几只, "passed": 过了几只,
                "blocked_total": 被挡几只, "blocked": {门槛代码: 被这条挡了几只}}。
    ``blocked`` 各项之和会大于 ``blocked_total`` —— 一只票可以同时踩中好几条。

    打分口径整体搬到 ``services.opportunity_score``(硬门槛 + 质地 × 时机两轴),
    这里只负责三件事: **收候选、喂数据、挂注记**。这样做的理由是打分必须能
    脱离 HTTP 层单测与回测 —— v1 的加减分散在这个函数里, 想验证一条曲线就得
    先造一整份总览。

    候选两路(与 v1 相同, 换的是打分不是选材):
      · 六态发出 转多/回升 信号
      · AI 看多且现价距上方触发价 2% 以内(逼近突破)

    **注记不参与打分**(extras 里的 win/mainline/verdict 与 AI 信号):
    它们照常挂在候选上给界面显示, 但一分不加一分不减。这是与 v1 最大的分野 ——
    用户要的是"评分系统专职做好自己的工作", 而这几项要么不可回测(主线口径随
    情绪周期漂移)、要么样本太小(单票历史突破常不足 10 次)、要么是模型对自己
    输出的自评(AI 置信度), 拿它们去动名次等于把噪声写进排序。

    extras[sym] 认得的键:
      vol_ratio / turnover  量能维度的两个因子
      channel_pct           Keltner 短期通道位置(位置维度)
      gate                  keltner_service.long_trend_map 的一行(生命线 + 长期趋势;
                            [R189] with_closes=True 时还带 closes 与 ret_120d,
                            趋势模板要拿它算 MA150/MA200 与 52 周高低点)
      win / mainline / verdict / dragon  纯注记
    """
    from app.services import opportunity_score as osc
    from app.services import trend_template as _tt

    ex = extras or {}
    cands: dict[str, dict] = {}

    def _cand(sym: str) -> dict:
        c = cands.get(sym)
        if c is None:
            c = cands[sym] = {"symbol": sym, "name": names.get(sym, sym),
                              "kinds": [], "near_breakout": False,
                              "duration": None, "pivot": None, "text": ""}
        return c

    # ---- 候选路 A: 六态转强 ----
    for sym, t in trends.items():
        if t.get("signal") not in ("转多", "回升"):
            continue
        dur = int(t.get("duration") or 1)
        c = _cand(sym)
        c["kinds"].append("trend_signal")
        c["duration"] = dur
        c["text"] = f"{t['signal']}:{t.get('signal_desc', '')}(第 {dur} 天)"
        # [R30] 建仓计划的锚用「进入当前状态那天的关键点」, 不用会随新高上移的
        # up_pivot —— 否则"站稳 X 上满 / 跌回 X 作废"里的 X 天天变, 事后无从复盘
        try:
            raw = t.get("entry_pivot") or t.get("up_pivot")
            c["pivot"] = float(raw) if raw else None
        except (TypeError, ValueError):
            c["pivot"] = None

    # ---- 候选路 B: 逼近买入触发价 ----
    for sym, sig in signals.items():
        if sym not in names or sig.get("signal") != "buy":
            continue
        close = (trends.get(sym) or {}).get("close") or sig.get("close")
        for p in sig.get("watch_points") or []:
            if p.get("direction") != "up" or not close:
                continue
            try:
                price = float(p["price"])
            except (TypeError, ValueError, KeyError):
                continue
            gap = (price - close) / close
            if 0 <= gap <= _NEAR_BREAKOUT_PCT:
                c = _cand(sym)
                c["kinds"].append("near_breakout")
                c["near_breakout"] = True
                if c["pivot"] is None:
                    c["pivot"] = price
                if not c["text"]:
                    c["text"] = (f"现价 {close:.2f} 距触发价 {price:.2f} 仅 "
                                 f"{gap * 100:.1f}% — 到价{p.get('action') or '关注'}")
                break

    # ---- 门槛 → 打分 → 注记 ----
    from app.price_limits import board_of

    out: list[dict] = []
    blocked: dict[str, int] = {}
    blocked_total = 0
    for sym, c in cands.items():
        t = trends.get(sym) or {}
        e = ex.get(sym) or {}
        g = e.get("gate") or {}
        gates = osc.check_gates(
            state=t.get("state"),
            above_ma20=g.get("above_ma20"), above_ma20_prev=g.get("above_ma20_prev"),
            close=g.get("close") if g.get("close") is not None else t.get("close"),
            ma120=g.get("ma120"), ma120_rising=g.get("ma120_rising"),
            # [R189] G4 红绿节拍。R188 起 _trend_payload 就带着它了, 白捡
            rhythm_level=(t.get("rhythm") or {}).get("level"))
        if not gates["ok"]:
            # 被挡下的只计数不进列表。计数要报给界面 —— "今天 40 只候选被门槛
            # 挡掉 28 只"本身就是市场状态, 藏起来用户会以为系统没干活
            blocked_total += 1
            for code in gates["failed"]:
                blocked[code] = blocked.get(code, 0) + 1
            continue

        r20 = t.get("ret_20d")
        rs_pct = ((r20 - bench_ret) * 100
                  if bench_ret is not None and r20 is not None else None)
        vr = e.get("vol_ratio")
        vr = float(vr) if isinstance(vr, (int, float)) and vr else None
        turn = e.get("turnover")
        turn = float(turn) if isinstance(turn, (int, float)) and turn else None
        cpct = e.get("channel_pct")
        cpct = float(cpct) if isinstance(cpct, (int, float)) else None

        # [R189] 趋势模板。原料全在 gate 那一行里(与生命线/长期趋势同一次批量
        # 读), 唯一要现算的是第 8 条的半年超额收益。
        tpl = None
        closes_long = g.get("closes")
        if closes_long:
            r120 = g.get("ret_120d")
            rs6 = (r120 - bench_ret_120d
                   if r120 is not None and bench_ret_120d is not None else None)
            try:
                tpl = _tt.assess(closes_long, rs6)
            except Exception as e:  # noqa: BLE001
                logger.debug("trend template skipped for %s: %s", sym, e)

        res = osc.score_candidate(
            duration=c["duration"], state=t.get("state"), rs_pct=rs_pct,
            vol_ratio=vr, turnover_rate=turn, channel_pct=cpct,
            near_breakout=c["near_breakout"],
            template=tpl, rhythm=t.get("rhythm"))

        close = t.get("close") or (signals.get(sym) or {}).get("close")
        try:
            close = float(close) if close else None
        except (TypeError, ValueError):
            close = None
        gap_pct = None
        if c["pivot"] and close:
            try:
                gap_pct = round((float(c["pivot"]) - close) / close * 100, 2)
            except (TypeError, ValueError, ZeroDivisionError):
                gap_pct = None

        o = {
            "symbol": sym, "name": c["name"],
            # 主 kind 取先命中的那一路, 供界面沿用既有图标; kinds 保留全部
            "kind": c["kinds"][0] if c["kinds"] else "trend_signal",
            "kinds": c["kinds"],
            "score": res["score"],
            "axes": res["axes"], "factors": res["factors"],
            "coverage": res["coverage"], "partial": res["partial"],
            "fresh_from": res["fresh_from"],
            "text": c["text"], "pivot": c["pivot"], "close": close,
            "gap_pct": gap_pct, "vol_ratio": vr, "turnover": turn,
            "channel_pct": round(cpct, 3) if cpct is not None else None,
            "duration": c["duration"],
            "trend_state": t.get("state"), "trend_state_cn": t.get("state_cn"),
            "rs_pct": round(rs_pct, 1) if rs_pct is not None else None,
            "board": board_of(sym),
            "why": osc.explain(res, duration=c["duration"], vol_ratio=vr,
                               channel_pct=cpct, rs_pct=rs_pct),
            # [R189] 质地那两个新因子的原始事实 —— 分数是结论, 这里给依据。
            # 与 notes 一样只是展示, 但它们**确实进了分**, 所以摆在 notes 之外。
            "template": ({"passed": tpl["passed"], "known": tpl["known"],
                          "total": tpl["total"], "text": _tt.summary(tpl),
                          "criteria": tpl["criteria"]} if tpl else None),
            "rhythm": t.get("rhythm"),
            "notes": _annotations(sym, e, signals.get(sym) or {}),
            # [R137] 盘中视图。**和 score/dims 完全并列, 一分不进评分** ——
            # 决策基准冻在收盘口径(盘中一动不动), 盘中的变化单独摆一份给人盯。
            "live": e.get("live"),
            "mainline": e.get("mainline"),
            "verdict": e.get("verdict"),
            # 台账口径: 因子拆解现在就是三个维度分, 不再是一串加减项
            "ctx": {
                "dur": c["duration"], "state": t.get("state"),
                "vol_ratio": vr, "turnover": turn, "channel_pct": cpct,
                "rs": round(rs_pct, 2) if rs_pct is not None else None,
                "gap_pct": gap_pct, "partial": res["partial"],
                "fresh_from": res["fresh_from"], "kinds": ",".join(c["kinds"]),
                "intraday": bool(t.get("intraday")),
                # [R175] 注记标签也落台账。这几样是"在界面上说了句话、但一分不
                # 参与打分"的东西 —— 恰恰因为不参与打分, 它们从来没被验证过。
                # 只存能分组的那个键(code/名次), 不存整个对象: 台账是要按天攒
                # 几个月的, 每行多塞一个 dict 到后面就是几 MB 的差别。
                #
                # 时效提醒: 这些字段**补不了历史**。今天不记, 三个月后想回头看
                # "通道结论说强势深调之后普遍怎么走", 就还是没有数据可看。
                "verdict": (e.get("verdict") or {}).get("code"),
                "mainline_rank": (e.get("mainline") or {}).get("rank"),
                "win_rate": (e.get("win") or {}).get("rate"),
                # 没上榜的存 None 让 ctx 的过滤把它丢掉 —— 绝大多数行都没上榜,
                # 存一堆 false 只是白占盘; 分组时"缺这个键"就是没上榜。
                "dragon": True if e.get("dragon") else None,
                # [R188] 红绿节拍与磨底时长。**只存能分组的那两个键**, 不存整个
                # rhythm 对象 —— 台账要按天攒几个月, 每行多塞一个 dict 到后面
                # 就是几 MB。天数不落, 因为它每天都在变、不适合做分组维度。
                "rhythm": (t.get("rhythm") or {}).get("level"),
                "basing_days": ((t.get("rhythm") or {}).get("basing") or {}).get("days"),
                # [R189] 趋势模板过了几条。只在八条全判得出时落 —— 判不全的
                # 那个 passed 和判得全的不是同一把尺子, 混在一档里统计会骗人。
                "tpl_passed": (tpl["passed"] if tpl and tpl.get("complete") else None),
            },
        }
        out.append(o)

    # [R139] 排序 = 把握分降序。同分时的次序以前是按代码字典序 —— 那是个
    # **无意义**的顺序, 而用户会照着名次从上往下看。改成两级有含义的兜底:
    #   ① 数据齐全的排在 partial 前面(同样 78 分, 因子都算出来的那只更可信);
    #   ② [R189] 再比**质地** —— 同分意味着质地×时机的乘积相同, 而在乘积相同
    #      时该先看质地好的那只: 时机会重来, 质地不会。
    # 最后才用代码保证确定性(同一份数据每次刷新顺序不变)。
    out.sort(key=lambda o: (-o["score"], bool(o["partial"]),
                            -(o["axes"].get("quality") or 0), o["symbol"]))
    return out, {"candidates": len(cands), "passed": len(out),
                 "blocked_total": blocked_total, "blocked": blocked}


# [R134] 注记 —— 挂在候选上给人看, **一分不加一分不减**。
#
# 每条都带 tone: good/bad/info, 界面据此上色。刻意不给"权重"这类字段: 一旦有了
# 权重, 下一步就会有人把它加回分数里, 那就又变回 v1 那个八项加减的黑箱了。
_NOTE_VERDICT_TONE = {
    "dip_in_uptrend": "good", "bottom_confirmed": "good", "low_short_only": "good",
    "watch_low": "info", "watch_high": "bad", "high_short_only": "bad",
    "top_confirmed": "bad", "top_all_bands": "bad",
    "bounce_in_downtrend": "bad", "falling_all_bands": "bad",
}


def _annotations(sym: str, e: dict, sig: dict) -> list[dict]:
    """把不参与打分的佐证整理成一串标签。纯函数。"""
    out: list[dict] = []

    # AI 信号: 只做佐证, 但**方向相反时要显眼**。v1 把它算成 -40 分等于把票
    # 藏起来; 藏起来用户就不知道有过这个冲突, 更谈不上自己判断。
    if sig.get("signal") == "sell":
        out.append({"key": "ai", "tone": "bad", "label": "AI 看空",
                    "text": "规则看多但 AI 看空 —— 结论互相矛盾, 自己定夺"})
    elif sig.get("signal") == "buy":
        conf = sig.get("confidence")
        out.append({"key": "ai", "tone": "info",
                    "label": f"AI 看多 {conf}" if conf is not None else "AI 看多",
                    "text": "仅作佐证, 不参与把握分"})

    ml = e.get("mainline")
    if ml:
        also = ml.get("also") or []
        out.append({"key": "mainline", "tone": "info",
                    "label": f"主线{ml.get('rank')}·{ml.get('member')}",
                    "text": f"今日第 {ml.get('rank')} 主线「{ml.get('member')}」"
                            f"({ml.get('limit_up_count')} 家涨停)"
                            + (f",同时还在{'、'.join(also)}" if also else "")})

    win = e.get("win")
    if win:
        wr, wn = win.get("rate"), win.get("n")
        tone = "good" if (wr or 0) >= 0.6 else "bad" if (wr or 1) <= 0.4 else "info"
        out.append({"key": "win", "tone": tone,
                    "label": f"历史胜率 {wr:.0%}({wn})",
                    "text": "同一套六态在这只票上历史转强后 5 日为正的比例; "
                            f"{wn} 次样本, 少于 10 次参考价值有限"})

    vd = e.get("verdict")
    if vd:
        out.append({"key": "verdict", "tone": _NOTE_VERDICT_TONE.get(vd.get("code"), "info"),
                    "label": vd.get("title") or "通道结论",
                    "text": vd.get("detail") or vd.get("hint") or ""})

    # [R135] 这两项 R134 时只写了展示分支没接数据源, 界面上永远不出现。
    # 数据都来自既有产出(策略页的 run_all 缓存 / 龙虎榜按日缓存), 不新增计算。
    hits = e.get("strategy_hits")
    if hits:
        from app.services.today_annotations import strategy_note
        out.append(strategy_note(list(hits)))

    dragon = e.get("dragon")
    if isinstance(dragon, dict):
        from app.services.today_annotations import dragon_note
        out.append(dragon_note(dragon))
    return out


def _gate_labels() -> dict[str, dict]:
    """门槛的中文名与理由 —— 界面直接用, 不在前端再抄一份。"""
    from app.services import opportunity_score as osc
    return {code: {"cn": osc.GATE_CN[code], "why": osc.GATE_WHY[code]}
            for code in (osc.GATE_TREND, osc.GATE_LIFELINE, osc.GATE_LONG_DOWN)}


def _gate_text(info: dict) -> str:
    """[R134] 门槛漏斗的一句话版本, 中观层直接显示。

    这句话回答的是"今天这个市场值不值得出手" —— 候选很多但过门槛的很少,
    说明信号在遍地开花而趋势结构没跟上, 那种日子最容易追在半山腰。
    """
    from app.services import opportunity_score as osc
    total = int(info.get("candidates") or 0)
    passed = int(info.get("passed") or 0)
    if not total:
        return "今天没有新信号候选"
    blocked = info.get("blocked") or {}
    if not blocked:
        return f"{total} 只候选全部通过三道门槛"
    top = sorted(blocked.items(), key=lambda kv: -kv[1])
    parts = "、".join(f"{osc.GATE_CN.get(k, k)} {v} 只" for k, v in top)
    return f"{total} 只候选过门槛 {passed} 只;挡下的原因:{parts}"


def filter_opportunities(
    ranked: list[dict],
    min_score: int = _OPP_MIN_SCORE, max_show: int = _OPP_MAX_SHOW,
    boards: list[str] | None = None,
) -> tuple[list[dict], int]:
    """完整排序列表 → (显示列表, 被门槛滤掉条数)。

    门槛 min_score / max_show 由用户偏好传入(见 services.today_prefs), 默认值即常量。
    低于 min_score 或排在 max_show 之后的都不显示, 只报数量。

    [R40] boards 非空时只保留这些板块的机会。**过滤必须发生在 max_show 截断之前** ——
    先截 10 条再由前端挑出主板的话, 会漏掉那些被截掉的主板票, 看到的"主板机会"
    是残缺的。被板块滤掉的不计入"已滤掉 N 只"(那个数字说的是没过门槛的)。
    """
    if boards:
        keep = set(boards)
        ranked = [o for o in ranked if o.get("board") in keep]
    shown = [dict(o, why=" · ".join(o["why"]))
             for o in ranked if o["score"] >= min_score][:max_show]
    return shown, len(ranked) - len(shown)


def rank_opportunities(
    trends: dict[str, dict], signals: dict[str, dict], names: dict[str, str],
    min_score: int = _OPP_MIN_SCORE, max_show: int = _OPP_MAX_SHOW,
    bench_ret: float | None = None,
    extras: dict[str, dict] | None = None,
    boards: list[str] | None = None,
) -> tuple[list[dict], int]:
    """打分 + 筛选一步到位, 返回 (显示列表, 被滤掉条数)。

    [R133] 拆分后的薄封装。[R134] 打分换成 v2 后签名保持不变 —— 门槛淘汰计数
    在这里被丢掉, 需要它的调用方直接用 score_opportunities。
    """
    ranked, _gates = score_opportunities(trends, signals, names, bench_ret, extras)
    return filter_opportunities(ranked, min_score, max_show, boards)


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


# [R47] 通道结论 → 买入候选的把握分增减。
#
# 这里打分的对象是**买入候选**, 所以问的是"这个通道位置让这一笔更值还是更不值"。
# 同一个结论对持仓和对买入的含义相反 —— 持仓到上沿是止盈时机, 买入到上沿是追高,
# 所以不能复用 holding_stance 那套。
#
# 幅度对齐既有因子(量比 ±8/12、胜率 ±8/12、相对强度 +8/-15、主线 +5~12),
# 不让通道位置一项压过量价本身。
_VERDICT_SCORE = {
    # 越便宜越该买
    "dip_in_uptrend": (10, "强势票深调, 是这套里最好的低吸位置"),
    "bottom_confirmed": (8, "短中期都到下沿, 低吸分量足"),
    "low_short_only": (4, "短期回调到下沿"),
    "watch_low": (2, "中期已到下沿, 短期还没给入场点"),
    # 越贵越不该追
    "watch_high": (-5, "中期在上沿、短期已回落, 追进去两头不靠"),
    "high_short_only": (-6, "短期已冲到上沿, 这时候买是在最贵的地方"),
    "top_confirmed": (-12, "短中期都到上沿, 这个位置追进去是在最贵的地方买"),
    "top_all_bands": (-15, "三档都到上沿, 大顶区域不该开新仓"),
    # 陷阱: 出了买信号, 但位置说这是反弹/下跌途中
    "bounce_in_downtrend": (-15, "长期还在下沿, 这是跌深了反弹而非突破 —— 买信号在这里最不可信"),
    "falling_all_bands": (-15, "三档都在下沿的下跌途中, 越抄越套"),
}


# [R43] 高抛要"已经涨上来了"才谈落袋 —— 浮亏还嫌它涨太急, 是纯粹的自相矛盾
_HEAT_TRIM_MIN_PNL = 0.10
# 刚转强的头两天不因贴上轨减仓: 主升浪起步就是沿着上轨走的, 这时候减就是卖飞
_HEAT_GRACE_DAYS = 2


def holding_stance(exit_triggered: bool, distance_pct: float | None,
                   trend_side: str | None, ai_signal: str | None,
                   trend_signal: str | None,
                   heat: dict | None = None, pnl_pct: float | None = None,
                   trend_duration: int | None = None) -> tuple[str, str]:
    """[R13] 持仓操作档位: 离场/减仓/加仓/持有(规则版, 只用已有字段)。

    离场纪律由出场线/生命线兜底(最高优先); 减仓是"趋势或 AI 转坏但还没破线"
    的中间档; 加仓要求趋势多头 + AI 看多 + 离出场线还有安全距离, 三者缺一不可。

    [R43] 高抛低吸由 **Keltner 通道位置**驱动(heat = ``keltner.pressure`` 的结果),
    与决策台的三档列、个股分析图表同一组口径。接进来做两件事, 顺序都有讲究:

    · **挡加仓**(这条比减仓重要)。原来只要"趋势多头 + AI 看多 + 离线够远"就建议加,
      不看价格已经冲到通道哪个位置 —— 那是在最贵的位置加最多的钱。贴/破上轨时不加。
    · **补一档止盈减仓**, 但排在所有风险驱动的减仓**之后**: 破线/转空/AI 看空
      都是"必须处理", 到上轨只是"可以落袋"。两者撞上时要说前者, 说后者会让人
      误以为只是获利了结。
      并且要求短中期共振(``is_strong``)才减 —— 只有短期贴上轨的情况太常见,
      每次都提示等于天天喊减仓。
      另加两道闸: 有像样浮盈才谈(``_HEAT_TRIM_MIN_PNL``), 刚转强的头两天不谈
      (``_HEAT_GRACE_DAYS``) —— 这两条都是为了防"卖飞", 那是这个功能唯一的大风险。
    """
    from app.indicators import keltner

    if exit_triggered:
        return "离场", "已跌破出场线,按纪律执行,不猜反弹"
    if trend_side == "空头":
        return "减仓", "持有票已处于空头趋势,先降低暴露"
    if ai_signal == "sell":
        return "减仓", "AI 转看空,与持仓方向矛盾"
    if distance_pct is not None and distance_pct >= -0.015:
        return "减仓", "距出场线不足 1.5%,提前减一部分比破线再动手从容"

    high = keltner.is_high(heat)
    fresh = trend_duration is not None and trend_duration <= _HEAT_GRACE_DAYS
    if (high and keltner.is_strong(heat) and not fresh
            and pnl_pct is not None and pnl_pct >= _HEAT_TRIM_MIN_PNL):
        return "减仓", (f"已到通道上沿({heat['text']})、浮盈 {pnl_pct:.0%} ——"
                        f"可落袋一部分。趋势没坏, 剩下的继续按出场线拿")

    if (trend_side == "多头" and ai_signal == "buy"
            and trend_signal in ("转多", "回升")
            and (distance_pct is None or distance_pct < -0.05)):
        if high:
            return "持有", (f"本来够加仓条件, 但已经贴到通道上沿({heat['text']})——"
                            f"这个位置加仓是在最贵的地方下最重的注, 等回踩再说")
        return "加仓", "趋势刚走强 + AI 看多 + 离出场线还有安全距离"
    return "持有", "无触发条件,按既定计划持有"


class _Stages:
    """[R156] 总览各阶段计时。结果随响应带出(``perf`` 字段)并在超过阈值时记日志 ——
    「今日总览慢」这种反馈, 没有分段数字就只能猜。"""

    SLOW_MS = 1500

    def __init__(self) -> None:
        self.t0 = self.t = time.perf_counter()
        self.rows: dict[str, int] = {}

    def mark(self, name: str) -> None:
        now = time.perf_counter()
        self.rows[name] = round((now - self.t) * 1000)
        self.t = now

    def done(self) -> dict:
        total = round((time.perf_counter() - self.t0) * 1000)
        if total >= self.SLOW_MS:
            slowest = sorted(self.rows.items(), key=lambda kv: -kv[1])[:4]
            logger.info("today overview %d ms; 最慢: %s", total,
                        ", ".join(f"{k} {v}ms" for k, v in slowest))
        return {"total_ms": total, "stages_ms": self.rows}


def _build_overview(repo, engine=None) -> dict:
    """[R135] engine 为 StrategyEngine, 只用来把「策略命中」这个**注记**读出来
    (读策略页已写好的缓存, 不跑策略)。不传就没有那个标, 其余一切不变。"""
    # [R169] 持仓改读合并视图(手填 ⊕ 批次): 字段与语义一字不变, 只是没手填成本时
    # 会用批次的加权平均补上。评分/门槛/注记全部原样, 本行之外没有任何改动。
    from app.services import effective_positions as positions_svc
    from app.services import stock_signal, today_prefs, watchlist
    from app.services.livermore_service import trends_for_symbols
    from app.services.position_exit import exit_lines_for_positions

    _st = _Stages()
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
    _st.mark("trends+exit_lines")
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
                "kind": "lifeline_broken", "severity": "fatal", "symbol": sym, "name": nm,
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
            # [R18] 结论类走收盘: 盘中临时判定降级为预警, 收盘定稿才是纪律指令
            if t.get("intraday"):
                actions.append({
                    "kind": "trend_break", "severity": "mid", "symbol": sym,
                    "name": names.get(sym, sym),
                    "text": f"持有票盘中处于下跌趋势(盘中口径,收盘确认后升级为纪律指令)",
                })
            else:
                actions.append({
                    "kind": "trend_break", "severity": "high", "symbol": sym,
                    "name": names.get(sym, sym),
                    "text": f"持有票已转入下跌趋势(第 {t['duration']} 天,{t['action']})",
                })
    # 近 24h 监控触发记录(含出场线规则与用户自建提醒)
    try:
        from app.services import alert_store
        events = alert_store.list_recent(repo.store.data_dir, days=1, limit=50)
        # [R179] 监控触发降为 low 档并限 3 条。
        #
        # 这些是**近 24h 已经发生过的事**, 而行动区其余各项说的是**此刻的状态**。
        # 两者混在一列里, 原来最多灌 10 条 —— 设了几个点位提醒的用户, 行动区就被
        # 历史记录占满, 真正要处理的那条反而被挤下去。降档 + 限流 + 溢出如实报数,
        # 完整列表在告警页, 这里只留个提示。
        shown = [ev for ev in events
                 if str(ev.get("message") or ev.get("name") or "").strip()]
        for ev in shown[:_MAX_ALERT_ACTIONS]:
            sym = str(ev.get("symbol", "")).upper()
            msg = str(ev.get("message") or ev.get("name") or "").strip()
            actions.append({
                "kind": "alert", "severity": "low", "symbol": sym,
                "name": names.get(sym, sym or "—"),
                "text": f"监控触发:{msg}",
            })
        if len(shown) > _MAX_ALERT_ACTIONS:
            actions.append({
                "kind": "alert_more", "severity": "low", "symbol": "", "name": "监控",
                "text": f"近 24 小时还有 {len(shown) - _MAX_ALERT_ACTIONS} 条触发未列出 —— 去告警页看完整记录",
            })
    except Exception as e:  # noqa: BLE001
        logger.debug("today alerts skipped: %s", e)
    sev_rank = SEVERITY_RANK
    actions.sort(key=lambda a: sev_rank.get(a["severity"], 9))

    _st.mark("actions")

    # ---- ② 机会区(门槛可由用户调; 卖出提醒都在行动区, 永不过滤) ----
    # [R11/R13] 大盘模式提前取: 姿态合成与相对强度都要用; 失败只降级不拦路
    market = None
    try:
        from app.services.market_mode import get_market_mode
        market = get_market_mode(repo)
    except Exception as e:  # noqa: BLE001
        logger.warning("today market mode skipped: %s", e)
    bench_ret = ((market or {}).get("metrics") or {}).get("ret_20d")
    # [R189] 趋势模板第 8 条要的基准一侧(半年超额收益)
    bench_ret_120d = ((market or {}).get("metrics") or {}).get("ret_120d")
    prefs = today_prefs.load()
    _st.mark("market_mode")

    # [R43] 高抛低吸由 Keltner 三档通道位置决定 —— 与决策台三列、个股分析图表
    # 同一组口径。走批量服务, 持仓 + 候选加起来可能上百只, 逐只算会拖死总览。
    # 收盘口径: 通道要 ATR 与均线, 实时叠加层只有价格, 拿实时价比昨天的通道
    # 会得到半新半旧的判定(结论层本来就该走收盘)。
    heat_map: dict[str, dict] = {}
    verdict_map: dict[str, dict] = {}
    bands_map: dict[str, dict] = {}
    try:
        from app.indicators import keltner
        from app.services import keltner_service
        want = sorted({*(s for s, p in pos_all.items() if p.get("held")), *trends})
        if want:
            bands_map = keltner_service.channels_for_symbols(repo, want)
            for sym, bands in bands_map.items():
                # 两者分开算, 不能让 verdict 挂在 pressure 下面:
                # pressure 要求短期到轨(它驱动持仓的挡加仓/止盈减仓),
                # verdict 还覆盖「候选池」那档(短期在中部、中期已到下沿) ——
                # 那正是低吸候选该有的样子, 挂在 pressure 下面就永远到不了机会区。
                pres = keltner.pressure(bands)
                if pres:
                    heat_map[sym] = pres
                v = keltner.verdict(bands)
                if v:
                    verdict_map[sym] = v
    except Exception as e:  # noqa: BLE001
        logger.debug("today keltner skipped: %s", e)

    _st.mark("keltner")

    # [R134] 候选集要**同时覆盖两路**: 六态转强的, 和 AI 看多(逼近突破)的。
    # v1 只给前者算量能, 于是后者的量能维度整个缺席, 而缺维度会在维度间重归一化
    # —— 结果是"数据越少分越高"。这是个必须堵死的口子, 不是可选优化。
    extras: dict[str, dict] = {}
    ai_buy_syms = [s for s, sig in signals.items()
                   if s in names and sig.get("signal") == "buy"]
    cand_syms = sorted({
        *(s for s, t in trends.items() if t.get("signal") in ("转多", "回升")),
        *ai_buy_syms,
    })[:80]
    if cand_syms:
        # [R137] **盘后与盘中分成两份, 不再互相覆盖。**
        #
        # 原来这里把实时叠加层叠在盘后快照之上, 于是盘中量比一变, 把握分就跟着
        # 变 —— 而位置和门槛还是昨收, 得到的分数既不是收盘口径也不是实时口径。
        # 用户的用法是"决策看收盘、盘中一直盯着", 那就该是:
        #   · vol_map / turn_map  只取**盘后快照** → 喂给评分, 盘中一动不动
        #   · live_rows           只取**实时叠加层** → 单独一份盘中视图, 不进评分
        vol_map: dict[str, float] = {}
        turn_map: dict[str, float] = {}
        live_rows: dict[str, dict] = {}
        try:
            import polars as pl
            _LIVE_COLS = ("symbol", "close", "change_pct", "vol_ratio_5d", "turnover_rate")
            df_e, _ed = repo.get_enriched_latest()
            if df_e is not None and not df_e.is_empty() and "symbol" in df_e.columns:
                cols = [c for c in ("symbol", "vol_ratio_5d", "turnover_rate")
                        if c in df_e.columns]
                if len(cols) >= 2:
                    for r in df_e.filter(pl.col("symbol").is_in(cand_syms)).select(cols).to_dicts():
                        sym_u = str(r["symbol"]).upper()
                        if r.get("vol_ratio_5d"):
                            vol_map[sym_u] = float(r["vol_ratio_5d"])
                        if r.get("turnover_rate"):
                            turn_map[sym_u] = float(r["turnover_rate"])
            for asset in ("stock", "etf"):
                dfl = repo.get_watchlist_live(asset)
                if dfl is None or dfl.is_empty() or "symbol" not in dfl.columns:
                    continue
                cols = [c for c in _LIVE_COLS if c in dfl.columns]
                for r in dfl.filter(pl.col("symbol").is_in(cand_syms)).select(cols).to_dicts():
                    live_rows[str(r["symbol"]).upper()] = r
        except Exception as e:  # noqa: BLE001
            logger.debug("today vol factor skipped: %s", e)
        _st.mark("snapshot+live")
        # [R134] 门槛原料: 生命线(MA20 含前一日)与长期趋势(MA120 及斜率)。
        # 与 Keltner 长期档共用同一次批量读, 不新增 IO。
        gate_map: dict[str, dict] = {}
        try:
            from app.services import keltner_service as _ks
            # [R189] with_closes: 窗口拉长到 420 天并带回收盘序列, 趋势模板要
            # MA150/MA200 与 52 周高低点。只有候选这一小撮走这条路。
            gate_map = _ks.long_trend_map(repo, cand_syms, with_closes=True)
        except Exception as e:  # noqa: BLE001
            logger.warning("today gate data skipped: %s", e)
        _st.mark("gates")
        for s in cand_syms:
            ent = {}
            if s in turn_map:
                ent["turnover"] = turn_map[s]
            if s in gate_map:
                ent["gate"] = gate_map[s]
            # 位置维度直接用 Keltner 短期档的通道位置(与决策台、图表同一口径)
            spct = ((bands_map.get(s) or {}).get("s") or {}).get("pct")
            if isinstance(spct, (int, float)):
                ent["channel_pct"] = float(spct)
            # [R137] 盘中视图: 拿现价去比**昨天那条**通道与生命线。给的是方向性
            # 预警不是结论 —— 结论等收盘(PRD §7.5)。一分不进评分。
            lr = live_rows.get(s)
            if lr:
                from app.services.today_annotations import live_view
                lv = live_view(lr.get("close"),
                               change_pct=lr.get("change_pct"),
                               vol_ratio=lr.get("vol_ratio_5d"),
                               bands=bands_map.get(s),
                               ma20=(gate_map.get(s) or {}).get("ma20"))
                if lv:
                    ent["live"] = lv
            extras[s] = ent
        # [R156] 历史胜率改走批量: 原来逐只调 bullish_win_rate_for_symbol, 每只一趟
        # 320 日历日 parquet 扫描, 候选上限 80 只 = 80 趟扫盘 —— 这是总览接口
        # 最大的一块耗时。现在一次批量读 + 按(票, 末日, 阈值)记忆, 结果一字不差。
        wins: dict[str, dict] = {}
        try:
            from app.services.livermore_service import bullish_win_rates_for_symbols
            wins = bullish_win_rates_for_symbols(repo, cand_syms)
        except Exception as e:  # noqa: BLE001
            logger.debug("today win rate skipped: %s", e)
        for s in cand_syms:
            ent = extras.setdefault(s, {})
            if s in vol_map:
                ent["vol_ratio"] = vol_map[s]
            if s in wins:
                ent["win"] = wins[s]
        _st.mark("win_rate")

    # [R47] 通道结论: 给全部自选打标, 不只 cand_syms。[R134] 它现在是**注记**,
    # 不再进把握分 —— 位置那一维改用 Keltner 短期通道位置这个连续量,
    # 比十档文字结论细得多, 也不必再担心"结论表和分数各说各话"。
    for sym, v in verdict_map.items():
        extras.setdefault(sym, {})["verdict"] = v

    # [R135] 另外两个注记数据源。与主线同层: 都是"给全部自选打标, 不参与打分"。
    # 两者都只读既有产出 —— 策略命中读策略页 run_all 写的缓存, 龙虎榜读按日缓存;
    # 在总览接口里现算 27 个内置策略是几秒级开销, 为一个不计分的展示标不值得。
    try:
        from app.services import today_annotations
        data_as_of = max((t.get("as_of") for t in trends.values() if t.get("as_of")),
                         default=None)
        for s_, hits in today_annotations.strategy_hits(repo, engine, data_as_of).items():
            if s_ in names:
                extras.setdefault(s_, {})["strategy_hits"] = hits
        for s_, info in today_annotations.dragon_tiger_map(repo).items():
            if s_ in names:
                extras.setdefault(s_, {})["dragon"] = info
    except Exception as e:  # noqa: BLE001 —— 注记取不到只是少个标, 不该拖垮总览
        logger.debug("today annotations skipped: %s", e)

    _st.mark("annotations")

    # [R37] 中观层: 主线归属 + 中观快照。给全部自选打标(不止趋势候选) ——
    # 逼近突破那一路的候选来自 AI 信号, 不在 cand_syms 里, 也该享受同一份加成。
    meso = None
    try:
        from app.services import today_mainline
        meso = today_mainline.build_meso(repo)
        for s, tag in today_mainline.tags_for(repo, syms, (meso or {}).get("mainline")).items():
            extras.setdefault(s, {})["mainline"] = tag
    except Exception as e:  # noqa: BLE001
        logger.debug("today meso skipped: %s", e)

    _st.mark("meso")

    # [R133] 先拿到**完整**排序列表, 再按门槛截断。台账记完整的那份 ——
    # 只记显示出来的 10 条, 等于只用样本里最好的一段去证明样本好。
    ranked_all, gate_info = score_opportunities(trends, signals, names, bench_ret, extras,
                                               bench_ret_120d=bench_ret_120d)
    opportunities, opp_filtered = filter_opportunities(
        ranked_all, prefs["min_score"], prefs["max_show"], prefs.get("boards"))
    # [R18] 盘中口径标注: 实时价确实参与了判定的趋势类新信号是"临时信号",
    # 收盘价可能收回去 —— 标记出来, 前端提示"待收盘确认", 防止盘中追假信号
    for o in opportunities:
        if o["kind"] == "trend_signal" and (trends.get(o["symbol"]) or {}).get("intraday"):
            o["intraday"] = True

    _st.mark("score")

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
        # 理由已含基准指数名(如"沪深300 收盘…"), 此处不再重复"大盘"前缀
        posture_reason = f"{market['reason']};自选:{breadth_reason}"
    if market_breadth and not market_breadth["capped"]:
        posture_reason += f";全市场 {market_breadth['up']}涨/{market_breadth['down']}跌"

    # [R158] 出手时机: 每只机会一句结论 —— 今天动手 / 收盘再动 / 不动手。
    # 纯注记, 与 R134 的分工一致: 一分不进评分, 不改名次。姿态要等上面合成完才能用,
    # 所以放在这里而不是打分处。规则见 services/action_timing.py。
    try:
        from app.services import action_timing
        for o in opportunities:
            o["action"] = action_timing.decide(o, posture)
    except Exception as e:  # noqa: BLE001 —— 结论取不到只是少一列, 不拖垮总览
        logger.debug("today action timing skipped: %s", e)

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
        heat = heat_map.get(sym)
        pnl_now = (close - cost) / cost if close and cost else None
        stance, stance_why = holding_stance(
            (ex or {}).get("triggered", False), (ex or {}).get("distance_pct"),
            (t or {}).get("side"), (sig or {}).get("signal"), (t or {}).get("signal"),
            heat=heat, pnl_pct=pnl_now, trend_duration=(t or {}).get("duration"))
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
            "heat": heat,
            "bands": bands_map.get(sym),
            "weight": pos.get("weight"),
            # [R169] 批次登记的附加信息(纯展示字段, 不参与任何评分/门槛/姿态判定):
            # 成本是手填还是批次派生、有几笔批次、最近一个未过期的到期日。
            "cost_source": pos.get("cost_source"),
            "lot_count": pos.get("lot_count", 0),
            "lot_remind_date": pos.get("next_remind_date"),
        })
    holdings.sort(key=lambda h: (not h["exit_triggered"], h["distance_pct"] if h["distance_pct"] is not None else -9))

    as_of = max((t["as_of"] for t in trends.values()), default=None)

    _st.mark("weather+holdings")

    # [R133] 落一份当日候选池快照 —— 这套把握分有没有区分度, 只能靠事后记录回答。
    # 判"定稿"看数据不看时钟: 只要没有任何一只用了实时价参与判定, 这份快照的
    # close 就是 as_of 那天的真收盘, 可以当收益起点; 盘中(实时行情开着)则不记,
    # 免得把实时价当成收盘价算出一份假收益。
    try:
        from app.services import score_ledger
        if as_of and not any(t.get("intraday") for t in trends.values()):
            score_ledger.record_day(as_of, ranked_all,
                                    {o["symbol"] for o in opportunities}, True)
    except Exception as e:  # noqa: BLE001 —— 记账失败绝不能影响总览
        logger.debug("score ledger record skipped: %s", e)

    _st.mark("ledger")

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
            sev_rank = SEVERITY_RANK
            actions.sort(key=lambda a: sev_rank.get(a["severity"], 9))

    _st.mark("portfolio")

    # [R156] ATR 先从 enriched 最新快照取 —— 它与 Keltner 用的是同一份、已在内存,
    # 且本来就带 atr_14/close。原来每只机会都单独 get_daily_asset 扫一趟 30 天盘,
    # 十来只就是十来趟。快照里没有的(ETF/指数)才回退到逐只读, 结果口径不变。
    atr_map: dict[str, float] = {}
    try:
        import polars as pl
        df_snap, _ = repo.get_enriched_latest()
        if (df_snap is not None and not df_snap.is_empty()
                and {"symbol", "close", "atr_14"} <= set(df_snap.columns)):
            want_syms = [o["symbol"] for o in opportunities]
            rows_snap = (df_snap
                         .filter(pl.col("symbol").str.to_uppercase().is_in(want_syms))
                         .select(["symbol", "close", "atr_14"]).to_dicts())
            for r in rows_snap:
                c, a = r.get("close"), r.get("atr_14")
                if c and a:
                    atr_map[str(r["symbol"]).upper()] = float(a) / float(c)
    except Exception as e:  # noqa: BLE001
        logger.debug("today atr snapshot skipped: %s", e)

    # [R12] 仓位建议: 姿态定总仓位基调, 把握分×波动率定单票建议(仅展示, 不是指令)
    for o in opportunities:
        atr_pct = atr_map.get(o["symbol"])
        try:
            if atr_pct is None:
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

    _st.mark("advice")

    # [R159] 落一份推送焦点快照: 持有 + 今天显示出来的机会 = 值得推送的那几只。
    # 内容不变不写盘; 失败只记 debug —— 名单是辅助, 不能拖垮总览。
    try:
        from app.services import focus_list
        # [R161] bands_map: 短期贴/破上下轨的也进焦点(用户常盯的高抛低吸候选)
        focus_list.save_snapshot(as_of, holdings, opportunities, bands_map)
    except Exception as e:  # noqa: BLE001
        logger.debug("focus snapshot skipped: %s", e)
    perf = _st.done()

    return {
        "as_of": as_of,
        # [R156] 各阶段耗时(ms)。用户说"慢"时打开 /api/today 看这一栏, 不用猜
        "perf": perf,
        "watchlist_total": len(syms),
        "trend_total": len(trends),
        "live": bool(live),
        "live_count": len(live),
        "actions": actions,
        "opportunities": opportunities,
        "opportunities_filtered": opp_filtered,
        # [R134] 门槛体检: 今天有多少候选被哪条硬门槛挡下。
        # 这不是调试信息 —— "40 只候选被挡掉 28 只"本身就是市场状态的读数,
        # 藏起来的话, 熊市里机会区空空如也会被读成"系统没干活"。
        "gates": {**gate_info, "labels": _gate_labels(),
                  "text": _gate_text(gate_info)},
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
        "meso": meso,
        "holdings": holdings,
        "portfolio": portfolio,
    }


@router.get("")
def get_today(request: Request):
    """今日总览聚合(行动区/机会区/市场天气/持仓体检)。

    [R27] 顺带带出已缓存的 AI 导读·优选(ai 字段), 前端进页面即常驻显示,
    不必每次手点; 缓存过期(数据日已推进)时前端据 as_of 提示。
    """
    data = _build_overview(request.app.state.repo,
                           getattr(request.app.state, 'strategy_engine', None))
    try:
        from app.services import today_ai_store
        data["ai"] = today_ai_store.load()
    except Exception as e:  # noqa: BLE001
        logger.debug("today ai cache skipped: %s", e)
        data["ai"] = None
    return data


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
    # [R40] 板块过滤; 传 [] 或全选都等于不过滤
    boards: list[str] | None = Field(default=None, max_length=12)


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
                            pyramid_days=body.pyramid_days,
                            boards=body.boards)


_AI_SYSTEM = """你是用户的盘前参谋,有 15 年 A 股一线交易经验。输入分两部分:今日总览 JSON(市场天气/需要行动/持仓体检),和每只候选买入机会的真实日 K 数据。一次调用完成两件事:先做任务二(优选),再基于优选结果写任务一(导读),两者结论必须一致。

## 任务二: 优选(picks)

对每只候选,**看它的日 K 数据做独立判断**,再横向对比,选出 1-3 只。判断依据只能是量价本身:

1. **突破的量能质量**:突破当天有没有放量?量比多少?缩量突破是假突破,放量才是真金
2. **突破后的持续性**:突破后回踩了没有?回踩守住关键位是好事,直接掉回去就是失败突破
3. **当前位置的风险**:现价离突破点多远?已经拉开一大截的,现在追等于给前面的人抬轿;紧贴突破点的才有好的风险收益比
4. **上方阻力空间**:离上方压力位还有多少空间?空间太小的机会不值得占用仓位
5. **K 线形态质量**:是干净利落的放量长阳,还是上影线很长、量价背离、连续跳空的透支形态

### 你会看到的「质地 × 时机 两轴分解」怎么用

每只候选带一份 `把握分分解`,那是规则层的自评,结构固定:

- **门槛**:这只票已经通过四道硬门槛(六态在多头侧 / 收盘站上生命线 MA20 且连续两日 / 不在长期下跌趋势里 / 红绿节拍不是「反复失败」)。**没过门槛的票压根不会送到你面前**,所以不必再核这四件事。
- **质地**(0~100):这只票的长周期结构 —— 趋势模板八条过了几条、磨底磨了多久磨得好不好、相对大盘强弱、六态状态。**它以月计变化**,今天和上周基本是同一个数。
- **时机**(0~100):今天是不是那一天 —— 信号第几天、量比、通道位置、换手率。**它逐日变化**。这几条曲线都是**区间最优**不是越大越好 —— 量比峰值在 1.3~2.5(超过 4 说明这波已经走完了),通道位置甜区在 0.50~0.65(刚站上生命线,越接近 1.0 越是追高)。
- **总分 = √(质地 × 时机)**。所以两根轴要**分开读**,这正是分解存在的理由:
  - 质地高、时机低 → 「好票,但今天不是买点」。该说的是等什么(回踩到哪、放量到什么程度),不是现在追。
  - 质地低、时机高 → 「今天是有动静,但这票本身结构不行」。该说的是为什么不值得占仓位。
  - 两个都高才是「高概率的有苗头的东西」。
- `partial: true` 表示某个因子**没有数据**,那一份权重是靠剩下的因子顶上来的 —— 这种候选的总分偏乐观,同分时优先选 partial 为 false 的。

用法是: **把分解当"规则层看到了什么"的摘要,然后自己去日 K 里验证它对不对**。分解和 K 线打架时以 K 线为准,并在理由里点出来。

### 佐证字段(`注记`)一律不能单独当理由

`注记` 里的主线归属、AI 信号、历史胜率、通道结论,**都不参与把握分**,它们只是背景。硬性规定:

- 量价不扎实的票,在第一主线里也不选;
- `AI 看空` 的注记意味着另一套模型与规则层结论相反 —— 这时你要**特别仔细地**看 K 线,若仍选中,理由里必须写明你在数据里看到了什么才敢反驳它;
- 历史胜率的样本量常常只有几次,不能当依据。

硬性要求:
- **不许拿"把握分高""AI 看多""信号共振"当理由** —— 这些是筛选前就知道的,把它们复述一遍等于没分析。理由必须来自你在 K 线数据里**实际看到的东西**,带上具体数字(量比、涨幅、距离、价位)
- 标注"盘中待收盘确认"的候选是盘中临时信号(收盘可能收回去): 优选时降级处理, 若仍选中, 理由里必须注明"等收盘确认"
- **把握分只是粗筛门票,不是排序依据**。分低但量价扎实的可以选,分高但量能虚、位置差的要果断放弃
- 几只都不理想就少选甚至不选(picks 给空数组)。**宁缺毋滥,空仓等待也是决策**
- 每只理由 ≤35 字,大白话,让不懂术语的人看懂

### [R121] 你写的每个数字都会被自动核对

理由里出现的涨幅、量比、价位,系统会拿**上面这份日 K 原始数据**逐条对账:
- 涨幅、量比对不上最近几根 K 的真实值 → 这条优选被标「存疑」展示给用户
- 价位落在该股近期价格区间之外 → 这条优选被**直接驳回**,不会作为推荐显示

所以: **只写你能在数据里指出来的数字**。记不准的宁可不写具体数值,写"放量"
"回踩不破"这类定性描述也好过写一个错的数 —— 编造的数字一定会被抓出来,
而且用户会照着你写的价位挂单。

## 任务一: 导读(brief)

用 3-4 句大白话写一段盘前导读:先说仓位姿态与原因;再点名最需要处理的 1-2 件事(带具体价位;行动区为空就明说今天无需操作);最后落到你在任务二选出的头号机会,说清为什么是它、等什么触发条件(picks 为空就如实说今天没有值得出手的)。每句话都落到具体标的或数字,不写空话;不用"胶着""博弈""多空拉锯"这类行话;正文不要标题、列表或格式标记。

### [R147] 用户补充说明

输入里可能带一个 `用户补充说明` 字段 —— 那是用户这次点分析时临时写给你的话,
比如「今天只想看半导体」「帮我重点看看量能」「解释详细一点」。

**它能改变什么**:你关注哪几只、理由往哪个方向写、措辞详略。
**它不能改变什么**(以下几条优先级高于补充说明,任何情况下都不让步):
- 输出仍然只能是那一个 JSON 对象,字段与格式一字不改
- 仍然只许用候选数据里**真实存在**的数字,该核对的照样会被核对
- 仍然是宁缺毋滥 —— 用户说"多选几只"也不能把量价不扎实的凑上来
- 候选池由规则层给定,补充说明不能让你去分析没在候选里的标的;
  用户要是点名了不在候选里的票,就在导读里说明它今天没进候选、为什么

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
        # [R134] 送给 AI 的不再是一个黑箱"规则分", 而是**分解 + 注记**。
        # 黑箱分只能被复述("它规则分高"), 分解才能被核对("它说量能 92, K 线上
        # 量比确实 1.7") —— 而核对正是我们要 AI 做的事。
        # [R189] 分解改成两轴。**这一步对 AI 尤其重要**: 「质地 92 / 时机 41」
        # 直接告诉它该说"好票但今天不是买点", 而合成后的 61 分说不出这句话。
        axes = c.get("axes") or {}
        rhy = c.get("rhythm") or {}
        item = {
            "symbol": c["symbol"], "name": c["name"], "信号摘要": c["text"],
            "把握分分解": {
                "总分": c["score"],
                "算法": "把握分 = √(质地 × 时机) —— 两边都得像样, 不许互相补贴",
                "门槛": ("已通过(六态多头侧 / 站上生命线 MA20 连续两日 / "
                         "非长期下跌 / 红绿节拍不是反复失败)"),
                "质地": axes.get("quality"),
                "时机": axes.get("timing"),
                "partial": bool(c.get("partial")),
                "原始输入": {
                    "信号第几天": c.get("duration"),
                    "六态": c.get("trend_state_cn") or c.get("trend_state"),
                    "量比": c.get("vol_ratio"),
                    "换手率%": c.get("turnover"),
                    "通道位置": c.get("channel_pct"),
                    "相对大盘20日": c.get("rs_pct"),
                    "距触发价%": c.get("gap_pct"),
                    "趋势模板": (c.get("template") or {}).get("text"),
                    "磨底天数": (rhy.get("basing") or {}).get("days"),
                    "节拍": rhy.get("label"),
                },
            },
            "规则依据": c["why"],
        }
        notes = c.get("notes") or []
        if notes:
            item["注记(不参与把握分, 只作背景)"] = [
                {"项": n.get("label"), "倾向": n.get("tone"), "说明": n.get("text")}
                for n in notes
            ]
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


def parse_ai_brief_response(text: str | None, valid_symbols: set[str]) -> dict:
    """[R22] 解析 AI 导读·优选输出, 保证永远给出可展示的结果。

    依次尝试: 整体 JSON → 文中最大 JSON 块 → 截断修复(补右花括号) →
    全部失败时把原文清理后当导读正文返回 —— 模型不守格式/被截断时,
    用户至少能看到它写了什么, 而不是'点了没反应'。纯函数。
    """
    from app.services.ai_json import extract_json_object
    raw = (text or "").strip()
    obj = extract_json_object(raw) or {}
    picks = []
    for p in (obj.get("picks") or [])[:3]:
        if not isinstance(p, dict):
            continue
        s = str(p.get("symbol", "")).upper()
        if s in valid_symbols:
            picks.append({"symbol": s, "reason": str(p.get("reason") or "").strip()[:60]})
    brief = str(obj.get("brief") or "").strip()
    if not brief and not picks:
        # 完全没解析出结构 → 原文兜底(剥掉代码围栏), 绝不空手而归
        fallback = re.sub(r"```[a-zA-Z]*|```", "", raw).strip()
        brief = fallback[:600] if fallback else ""
        if not brief:
            return {"error": "AI 返回了空内容, 请重试(或到设置页检查 AI 配置)"}
    return {"brief": brief, "picks": picks}


async def generate_today_ai(repo, data: dict, note: str = "") -> dict:
    """[R27] 生成导读+优选(纯逻辑, 不落盘)。手动端点与定时任务共用。

    data 为 _build_overview 的结果; 返回 {brief, picks, analyzed} 或 {error}。

    [R147] note 是用户这次临时写的补充说明(可空)。它**只进 user 消息**,
    不拼进 system 提示词 —— 系统契约(输出格式、事实校验、宁缺毋滥)必须始终
    压在用户这句话之上; 拼进 system 等于让用户随手一句话就能改掉这些约束。
    """
    from app.services.ai_provider import ai_configured, generate_ai_text
    if not ai_configured():
        return {"error": "未配置 AI"}
    cands = data["opportunities"][:_SELECT_MAX_CANDIDATES]
    # 总览瘦身: 候选明细单独带 K 线送审, 机会区在总览里只留给导读定位用的短句
    overview = {k: v for k, v in data.items() if k != "opportunities"}
    overview["机会区摘要"] = [
        {"symbol": c["symbol"], "name": c["name"], "text": c["text"],
         "建议仓位": (c.get("advice") or {}).get("text"),
         "建仓路径": (c.get("advice") or {}).get("plan"),
         # [R18] 盘中临时信号如实告知 AI, 优选时应降级处理而非当定稿推荐
         "盘中待收盘确认": bool(c.get("intraday"))} for c in cands]
    # [R121] 送审的这份候选数据同时是**校验的账本** —— 校验只拿它对账,
    # 不另外去读一次行情: 要检验的正是"AI 有没有忠实使用我们喂给它的数据"。
    payload_cands = _candidate_market_data(repo, cands) if cands else []
    payload = {
        "今日总览": overview,
        "候选买入机会(含真实日K)": payload_cands,
    }
    note = (note or "").strip()[:500]
    if note:
        payload["用户补充说明"] = note
    # [R180] 带上消息面总览。取不到/过期/关掉都返回空串, 那就跟改造前一样。
    # 放在 system 而不是 payload 里: 它是**背景**不是数据, 混进那份 JSON 会被
    # 当成和 K 线同级的事实, 而它未经核实。
    try:
        from app.services import news_desk
        _news = news_desk.context_for_ai()
    except Exception as e:  # noqa: BLE001
        logger.debug("today ai: news desk skipped: %s", e)
        _news = ""
    try:
        text = await generate_ai_text(
            [
                {"role": "system", "content": _AI_SYSTEM + ("\n\n" + _news if _news else "")},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            temperature=0.2,
            max_tokens=None,  # [上游标准] 分析类调用不限制输出(推理模型思考计入预算)
        )
        out = parse_ai_brief_response(text, {c["symbol"] for c in cands})
        out["analyzed"] = len(cands)
        out["note"] = note        # 存下来: 事后看这份结论时要知道当时问了什么
        # [R121] 事实校验: 拿刚才喂给它的那份日K, 逐条对账理由里的数字。
        # 驳回的 pick 仍然回给前端(要让用户看见"它编了什么"), 但会被标成驳回,
        # 界面不当推荐展示, 也不进命中率台账。
        from app.services import today_ai_verify
        out["picks"] = today_ai_verify.verify_picks(out.get("picks") or [], payload_cands)
        out["verify"] = today_ai_verify.summarize(out["picks"])
        # 名字补上 —— 台账与界面都要显示中文名, 别让用户对着代码猜
        name_by_symbol = {c["symbol"]: c["name"] for c in cands}
        for p in out["picks"]:
            p.setdefault("name", name_by_symbol.get(p.get("symbol"), ""))
        return out
    except Exception as e:  # noqa: BLE001
        logger.warning("today ai failed: %s", e)
        return {"error": f"AI 调用失败: {e}"}


class TodayAiIn(BaseModel):
    """[R147] 这次分析的可选补充说明。整体可省 —— 不填直接点按钮就是原来的行为。"""

    model_config = {"extra": "forbid"}

    note: str | None = Field(default=None, max_length=500)


@router.post("/ai")
async def today_ai(request: Request, body: TodayAiIn | None = None):
    """AI 导读+优选合一: 一次调用生成盘前导读, 并基于真实量价从候选里精选 1-3 只。

    未配 AI 返回 error 而非 500。生成成功即落盘缓存(刷新页面仍在, 见 today_ai_store)。

    [R147] body 可省。带 note 时把用户这次临时写的话一起送进去 ——
    见 _AI_SYSTEM 里那段: 它能改关注点与措辞, 改不了输出格式与事实校验。
    """
    repo = request.app.state.repo
    data = _build_overview(repo, getattr(request.app.state, "strategy_engine", None))
    out = await generate_today_ai(repo, data, (body.note if body else None) or "")
    if not out.get("error"):
        from app.services import ai_pick_ledger, today_ai_store
        saved = today_ai_store.save(out, as_of=data.get("as_of"), source="manual")
        out["created_at"] = saved["created_at"]
        out["source"] = saved["source"]
        # [R121] 落一条命中率台账 —— 只记未被驳回的, 起点用当日收盘价
        try:
            closes = _pick_entry_closes(repo, out.get("picks") or [])
            ai_pick_ledger.record(data.get("as_of"), out.get("picks") or [], closes)
        except Exception as e:  # noqa: BLE001 —— 台账失败不该影响优选本身
            logger.warning("record ai pick ledger failed: %s", e)
    return out


def _pick_entry_closes(repo, picks: list[dict]) -> dict[str, float]:
    """优选标的的当日收盘价 —— 台账收益的起点。取不到就不记那一只。"""
    from app.services.stock_analyzer import _load_kline
    out: dict[str, float] = {}
    for p in picks:
        sym = str(p.get("symbol") or "").upper()
        if not sym or sym in out:
            continue
        try:
            df = _load_kline(repo, sym)
            if not df.is_empty() and "close" in df.columns:
                out[sym] = float(df.tail(1)["close"][0])
        except Exception as e:  # noqa: BLE001
            logger.debug("entry close unavailable for %s: %s", sym, e)
    return out


@router.get("/ai/track-record")
def ai_track_record(request: Request):
    """[R121] AI 优选的历史命中率 —— 「靠不靠谱」唯一的硬证据。

    纯事后统计: 不参与选股, 也不回喂给提示词(否则这个数就不干净了)。
    """
    from app.services import ai_pick_ledger
    return ai_pick_ledger.evaluate(request.app.state.repo)


@router.get("/score-ledger")
def score_ledger_stats(request: Request):
    """[R133] 规则层把握分体检: 分层胜率 / 排名段 / 因子归因 / 同期基准。

    与 AI 命中率台账互补 —— 那个只看 AI 挑的 1-3 只(有选择偏差),
    这个看**完整候选池**, 才能回答"把握分本身有没有区分度"。
    """
    from app.services import ai_pick_ledger, score_ledger
    repo = request.app.state.repo
    out = score_ledger.evaluate(repo)
    try:
        ai_stats = ai_pick_ledger.evaluate(repo).get("stats")
    except Exception as e:  # noqa: BLE001
        logger.debug("score ledger ai stats skipped: %s", e)
        ai_stats = None
    # 服务端就把可粘贴的摘要拼好: 用户点一下复制就能整段交给外部做调参,
    # 不必自己从几张表里抄数字(抄错了结论就跟着错)
    out["summary_md"] = score_ledger.build_summary_md(out, ai_stats)
    # [R175] 已经存下来的那条提炼(可能是昨天的)。**这里只读不生成** ——
    # 生成走下面那个显式端点, 免得打开一次弹窗就烧一次 AI。
    try:
        from app.services import pattern_digest
        out["digest"] = pattern_digest.latest()
    except Exception as e:  # noqa: BLE001
        logger.debug("pattern digest read skipped: %s", e)
        out["digest"] = None
    return out


@router.post("/score-ledger/digest")
async def score_ledger_digest(request: Request):
    """[R175] 让 AI 把「回头看」那张表念成人话。

    今天已经跑过就直接返回存档 —— 同一批数据问两次 AI 会给两套说法,
    而"今天和昨天说的不一样"会被读成行情变了, 其实只是采样噪声。
    """
    from app.services import pattern_digest, score_ledger
    out = score_ledger.evaluate(request.app.state.repo)
    entry = await pattern_digest.refresh_if_stale(out)
    if entry is None:
        raise HTTPException(status_code=400,
                            detail="提炼失败: 未配置 AI, 或台账还没有可统计的标签数据")
    return entry


@router.get("/score-ledger/digest/history")
def score_ledger_digest_history(limit: int = 30):
    """[R175] 回看 AI 过去都说过什么 —— 它准不准, 也只能用记录回答。"""
    from app.services import pattern_digest
    return {"entries": pattern_digest.history(limit)}


@router.get("/score-ledger/export")
def score_ledger_export(request: Request):
    """[R133] 整本台账导出成一行一候选的扁平 CSV —— 调参用的原料。"""
    from fastapi.responses import Response
    from app.services import score_ledger
    csv_text = score_ledger.export_csv(request.app.state.repo)
    stamp = date.today().isoformat()
    return Response(
        # BOM: Excel 认它才不会把中文名列显示成乱码
        content="﻿" + csv_text,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition":
                 f'attachment; filename="score_ledger_{stamp}.csv"'},
    )
