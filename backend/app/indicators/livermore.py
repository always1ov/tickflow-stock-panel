"""[fork 增强] 利弗莫尔六态状态机(Livermore Market Key)—— 纯函数,无 IO。

六个状态(文案沿用引入代码包的原版表达):
  UT   上涨趋势 Upward Trend      NR   自然回升 Natural Rally
  SR   次级回升 Secondary Rally   SREA 次级回撤 Secondary Reaction
  NREA 自然回撤 Natural Reaction  DT   下跌趋势 Downward Trend

判定只用日线收盘价("只认收盘"信条):自高点回撤超过阈值(默认 6%)进入回撤态,
自低点回升超过阈值进入回升态;突破上关键点确认上涨趋势,跌破下关键点确认下跌趋势。
状态机同时维护上/下两个关键点(pivot),即趋势被确认/否决的价格。

另含阈值网格回测:同一段收盘价按多个阈值各跑一遍状态机,输出翻转次数/假信号率/
跟随收益等指标,供「回测调参」选择每只票的合适阈值(6% 对 20cm 高波动票偏敏感,
对低波动票偏迟钝)。
"""
from __future__ import annotations

import math
from typing import Any

STATE_LABELS: dict[str, tuple[str, str]] = {
    "UT": ("上涨趋势", "Upward Trend"),
    "NR": ("自然回升", "Natural Rally"),
    "SR": ("次级回升", "Secondary Rally"),
    "SREA": ("次级回撤", "Secondary Reaction"),
    "NREA": ("自然回撤", "Natural Reaction"),
    "DT": ("下跌趋势", "Downward Trend"),
}

STATE_ACTION: dict[str, str] = {
    "UT": "顺势持有多头 / 突破关键点可金字塔加仓",
    "NR": "观望,等待上破上一关键点确认转多",
    "SR": "不动作",
    "SREA": "不动作",
    "NREA": "观望,等待下破上一关键点确认转空",
    "DT": "顺势持有空头 / 跌破关键点可加空",
}


def action_text(state: str | None, up_pivot: float | None, dn_pivot: float | None) -> str:
    """操作建议代入具体关键点价位(语义沿用 STATE_ACTION 原版,拒绝"上一关键点"式模糊指代)。

    关键点缺失时回退原版模板文案。
    """
    up = f"{up_pivot:.2f}" if up_pivot is not None else None
    dn = f"{dn_pivot:.2f}" if dn_pivot is not None else None
    if state == "UT":
        return f"顺势持有多头 / 突破 {up} 可金字塔加仓" if up else STATE_ACTION["UT"]
    if state == "NR":
        return f"观望,上破 {up} 确认转多" if up else STATE_ACTION["NR"]
    if state == "SR":
        return f"不动作(上破 {up} 才确认转多)" if up else STATE_ACTION["SR"]
    if state == "SREA":
        return f"不动作(下破 {dn} 才确认转空)" if dn else STATE_ACTION["SREA"]
    if state == "NREA":
        return f"观望,下破 {dn} 确认转空" if dn else STATE_ACTION["NREA"]
    if state == "DT":
        return f"顺势持有空头 / 跌破 {dn} 可加空" if dn else STATE_ACTION["DT"]
    return ""

# 多头 = 上涨趋势 + 自然回升 + 次级回升;其余为空头(与代码包 BULLISH 口径一致)
BULLISH = frozenset({"UT", "NR", "SR"})

DEFAULT_THRESHOLD = 0.06

# 回测阈值网格:3% ~ 15%,步长 1%
GRID_THRESHOLDS = [round(0.03 + 0.01 * i, 2) for i in range(13)]


def compute(closes: list[float], dates: list[str], threshold: float = DEFAULT_THRESHOLD) -> dict:
    """跑六态状态机。closes/dates 等长、按时间升序。

    返回 {steps, last, duration, since, entered_from, threshold}:
      steps: 每日 {i, date, close, prev, state, up_pivot, dn_pivot, flipped}
      last:  最后一日 step
      duration/since/entered_from: 当前状态持续天数 / 起始日期 / 由哪个状态转入
    """
    st: str | None = None
    up_piv: float | None = None
    dn_piv: float | None = None
    hi = closes[0]
    lo = closes[0]
    steps: list[dict[str, Any]] = []

    for i, p in enumerate(closes):
        prev = st
        if st in ("NR", "SR", "UT", None):
            hi = max(hi, p)
        if st in ("NREA", "SREA", "DT", None):
            lo = min(lo, p)
        if st in ("UT", "NR", "SR", None):
            if p <= hi * (1 - threshold):
                up_piv = hi
                lo = p
                st = "DT" if (dn_piv is not None and p < dn_piv) else "NREA"
            else:
                if st in ("NR", "SR") and up_piv is not None and p > up_piv:
                    st = "UT"
                    up_piv = p
                    hi = p
                elif st == "UT":
                    up_piv = max(up_piv if up_piv is not None else p, p)
                elif st is None:
                    st = "NR"
        if st in ("DT", "NREA", "SREA"):
            if p >= lo * (1 + threshold):
                dn_piv = lo
                hi = p
                st = "UT" if (up_piv is not None and p > up_piv) else "NR"
            else:
                if st in ("NREA", "SREA") and dn_piv is not None and p < dn_piv:
                    st = "DT"
                    dn_piv = p
                    lo = p
                elif st == "DT":
                    dn_piv = min(dn_piv if dn_piv is not None else p, p)
        steps.append({
            "i": i,
            "date": dates[i] if dates else str(i),
            "close": round(p, 4),
            "prev": prev,
            "state": st,
            "up_pivot": round(up_piv, 4) if up_piv is not None else None,
            "dn_pivot": round(dn_piv, 4) if dn_piv is not None else None,
            "flipped": prev != st,
        })

    last = steps[-1]
    start = last["i"]
    for k in range(len(steps) - 1, -1, -1):
        if steps[k]["state"] == last["state"]:
            start = steps[k]["i"]
        else:
            break
    return {
        "steps": steps,
        "last": last,
        "duration": last["i"] - start + 1,
        "since": steps[start]["date"],
        "entered_from": steps[start]["prev"],
        "threshold": threshold,
    }


def signal_kind(result: dict) -> tuple[str, str] | None:
    """近期状态转换信号(文案沿用代码包 signalKind):转多/转空/回升/回撤。"""
    st = result["last"]["state"]
    frm = result["entered_from"]
    up_piv = result["last"]["up_pivot"]
    dn_piv = result["last"]["dn_pivot"]
    if st == "UT":
        return ("转多", f"突破上关键点 {up_piv},确认上涨趋势")
    if st == "DT":
        return ("转空", f"跌破下关键点 {dn_piv},确认下跌趋势")
    if st == "NR" and frm in ("DT", "NREA", "SREA"):
        return ("回升", f"自低点回升(关键点 {up_piv if up_piv is not None else '—'}),待突破确认")
    if st == "NREA" and frm in ("UT", "NR", "SR"):
        return ("回撤", f"自高点回撤(关键点 {dn_piv if dn_piv is not None else '—'}),待跌破确认")
    return None


def side_segments(steps: list[dict]) -> list[dict]:
    """把逐日状态压成多头/空头连续段 [{side, start_i, end_i, start_date, end_date}]。"""
    segs: list[dict] = []
    for s in steps:
        if s["state"] is None:
            continue
        side = "bull" if s["state"] in BULLISH else "bear"
        if segs and segs[-1]["side"] == side:
            segs[-1]["end_i"] = s["i"]
            segs[-1]["end_date"] = s["date"]
        else:
            segs.append({"side": side, "start_i": s["i"], "end_i": s["i"],
                         "start_date": s["date"], "end_date": s["date"]})
    return segs


# ================================================================
# 阈值网格回测
# ================================================================

def _strategy_return(closes: list[float], steps: list[dict], lo: int, hi: int) -> float:
    """[lo, hi) 区间内"昨收多头则持有到今收"的复利收益。"""
    eq = 1.0
    for i in range(max(lo, 1), hi):
        prev = steps[i - 1]["state"]
        if prev is not None and prev in BULLISH:
            eq *= closes[i] / closes[i - 1]
    return eq - 1.0


def backtest_thresholds(
    closes: list[float],
    dates: list[str],
    thresholds: list[float] | None = None,
) -> list[dict]:
    """对同一段收盘价按阈值网格逐一回测。每行:

    threshold        阈值
    flips            多空翻转次数(抖动程度)
    seg_count        多空段总数;bull_segs 多头段数(样本量)
    false_rate       假信号率 = 收益<=0 的多头段占比(0~1;无多头段为 None)
    avg_seg_days     多空段平均持续天数
    strategy_return  跟随策略收益(仅多头状态持有)
    buyhold_return   买入持有收益(基准)
    excess           跟随 - 买入持有
    first_half / second_half  前后两半段各自的跟随收益(过拟合一致性检查)
    """
    n = len(closes)
    buyhold = closes[-1] / closes[0] - 1.0
    rows: list[dict] = []
    for t in (thresholds or GRID_THRESHOLDS):
        res = compute(closes, dates, t)
        steps = res["steps"]
        segs = side_segments(steps)
        flips = max(0, len(segs) - 1)
        bull_segs = [s for s in segs if s["side"] == "bull"]
        # 多头段收益:确认日收盘进,翻转日收盘出(段结束次日即翻转确认日)
        bull_rets = []
        for s in bull_segs:
            exit_i = min(s["end_i"] + 1, n - 1)
            bull_rets.append(closes[exit_i] / closes[s["start_i"]] - 1.0)
        false_rate = (sum(1 for r in bull_rets if r <= 0) / len(bull_rets)) if bull_rets else None
        avg_days = (sum(s["end_i"] - s["start_i"] + 1 for s in segs) / len(segs)) if segs else 0.0
        strat = _strategy_return(closes, steps, 0, n)
        mid = n // 2
        rows.append({
            "threshold": t,
            "flips": flips,
            "seg_count": len(segs),
            "bull_segs": len(bull_segs),
            "false_rate": round(false_rate, 4) if false_rate is not None else None,
            "avg_seg_days": round(avg_days, 1),
            "strategy_return": round(strat, 4),
            "buyhold_return": round(buyhold, 4),
            "excess": round(strat - buyhold, 4),
            "first_half": round(_strategy_return(closes, steps, 0, mid), 4),
            "second_half": round(_strategy_return(closes, steps, mid, n), 4),
        })
    return rows


def rule_suggest(rows: list[dict]) -> dict:
    """规则版阈值建议(无 AI 也可用):

    评分 = 邻域平滑后的超额收益 - 假信号率惩罚。取平滑是为了选"表现平台期"
    的稳健值而非孤立尖峰;前后半段任一为大幅负收益的降权。样本不足(多头段
    普遍 <2)时不硬荐,回落默认值并明说。
    """
    usable = [r for r in rows if r["bull_segs"] >= 1]
    if not usable or all(r["bull_segs"] < 2 for r in rows):
        return {
            "threshold": DEFAULT_THRESHOLD,
            "reason": "窗口内趋势段样本不足,不足以支撑调参,建议保持默认阈值 6%",
            "sample_insufficient": True,
        }

    def smoothed_excess(idx: int) -> float:
        vals = [rows[j]["excess"] for j in (idx - 1, idx, idx + 1)
                if 0 <= j < len(rows) and rows[j]["bull_segs"] >= 1]
        return sum(vals) / len(vals) if vals else -math.inf

    best_i, best_score = None, -math.inf
    for i, r in enumerate(rows):
        if r["bull_segs"] < 1:
            continue
        score = smoothed_excess(i)
        if r["false_rate"] is not None:
            score -= 0.5 * r["false_rate"]
        # 前后半段一致性:任一半段亏损 >5% 说明该阈值不稳定
        if min(r["first_half"], r["second_half"]) < -0.05:
            score -= 0.10
        if score > best_score:
            best_i, best_score = i, score
    r = rows[best_i]
    return {
        "threshold": r["threshold"],
        "reason": (
            f"{r['threshold']:.0%} 阈值下超额收益 {r['excess']:+.1%}(邻域平滑后最优),"
            f"翻转 {r['flips']} 次,假信号率 "
            f"{('—' if r['false_rate'] is None else format(r['false_rate'], '.0%'))},"
            f"前/后半段收益 {r['first_half']:+.1%} / {r['second_half']:+.1%}"
        ),
        "sample_insufficient": False,
    }
