"""[fork 增强] R28 板块跷跷板识别 —— 资金在两条主线之间来回搬的检测。

跷跷板 = A 热的日子 B 冷、B 热的日子 A 冷,资金在两者之间来回切换。
短线上很有用:一边熄火往往就是另一边点火,与其追已经涨完的那条,
不如提前盯住对手盘。

口径: 只用本地已有的主线时序(market_mainline 的日频概念/行业强度分),
不引入任何第三方数据源。规则先算出候选对(零 AI 成本、每天都能看),
AI 只做第二轮甄别与解读(哪几对是真跷跷板、当下轮到谁)。

纯函数在前(可单测), 装配函数在后。
"""
from __future__ import annotations

import json
import logging
from itertools import combinations

import polars as pl

logger = logging.getLogger(__name__)

WINDOW_DAYS = 40        # 观察窗口(交易日): 覆盖 2 个月左右的切换节奏
MIN_ACTIVE_DAYS = 8     # 两边各自至少上榜天数 —— 太冷门的对子是巧合不是跷跷板
MAX_PAIRS = 8           # 展示/送审的候选上限
MIN_SCORE = 45          # 跷跷板分下限, 低于此不认
MIN_CORR = -0.15        # 反向相关硬门槛: 一边稳如老狗、另一边上下窜也会刷出很多"换手",
                        # 但那不是跷跷板 —— 没有反向关系就一票否决

_RECENT_DAYS = 3        # 判定"当下轮到谁"的近端窗口

_AI_SYSTEM = """你是 A 股短线资金流研究员。用户给你若干「板块跷跷板」候选对,
每对都附带最近 40 个交易日的日度强度序列(0 = 当天没上榜, 数值越大越强)。

跷跷板的定义: 资金在两个板块之间来回搬 —— A 强的日子 B 弱, B 强的日子 A 弱,
且这种交替反复出现, 而不是一次性的此消彼长。

你的任务(只做甄别与解读, 不要复述已给的分数):
1. 从候选里挑出 1-3 对真正成立的跷跷板, 说明理由要落到序列本身
   (交替了几轮、每轮大概几天、最近一轮什么时候换的)。
2. 明确当下轮到哪一边, 以及对手盘什么情况下可能接力。
3. 看着像巧合的(比如只是同时都在衰减、或只交替过一次)要剔除, 并说明原因。

只输出 JSON, 不要任何解释文字或代码块标记:
{"summary": "两三句话说清当前市场的跷跷板格局, 大白话, 不用术语",
 "picks": [{"pair": "候选里给的 pair 原文", "verdict": "成立|存疑",
            "leader": "当下占优的一方名称", "note": "为什么成立/存疑 + 接力条件, 60 字内"}]}
"""


# ---------- 纯函数: 序列构建 ----------

def build_strength(df: pl.DataFrame, *, window: int = WINDOW_DAYS) -> tuple[list[str], dict[str, list[float]]]:
    """主线时序 → (日期轴, {主线: 按日对齐的强度序列})。

    缺席日补 0 —— 当天没进榜就是没资金, 这正是跷跷板"一边熄火"的那一半信息,
    补 None 或跳过都会把交替关系抹平。
    """
    if df is None or df.is_empty() or "date" not in df.columns:
        return [], {}
    need = {"date", "member", "score"}
    if not need.issubset(set(df.columns)):
        return [], {}

    dates = sorted({str(d) for d in df["date"].to_list()})[-window:]
    keep = set(dates)
    series: dict[str, dict[str, float]] = {}
    for r in df.iter_rows(named=True):
        d = str(r["date"])
        if d not in keep:
            continue
        m = str(r["member"])
        sc = float(r["score"] or 0.0)
        # 同日同主线理论上唯一; 真出现重复取更强的那条, 不做静默覆盖
        cur = series.setdefault(m, {})
        if sc > cur.get(d, 0.0):
            cur[d] = sc
    return dates, {m: [v.get(d, 0.0) for d in dates] for m, v in series.items()}


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def pearson(a: list[float], b: list[float]) -> float:
    """皮尔逊相关系数; 任一侧为常数(方差 0)时返回 0.0。"""
    n = min(len(a), len(b))
    if n < 3:
        return 0.0
    ma, mb = _mean(a[:n]), _mean(b[:n])
    num = sum((a[i] - ma) * (b[i] - mb) for i in range(n))
    da = sum((a[i] - ma) ** 2 for i in range(n))
    db = sum((b[i] - mb) ** 2 for i in range(n))
    if da <= 0 or db <= 0:
        return 0.0
    return num / (da ** 0.5 * db ** 0.5)


def alternations(a: list[float], b: list[float], *, min_gap: float = 5.0) -> int:
    """领先方切换次数 —— 跷跷板的核心特征(来回, 而不是一次性此消彼长)。

    只在双方强度差超过 min_gap 的日子上判定领先方(差得太小是噪声),
    统计领先方发生变化的次数。
    """
    n = min(len(a), len(b))
    last = 0
    flips = 0
    for i in range(n):
        diff = a[i] - b[i]
        if abs(diff) < min_gap:
            continue
        side = 1 if diff > 0 else -1
        if last and side != last:
            flips += 1
        last = side
    return flips


def _lead_run(a: list[float], b: list[float], *, min_gap: float = 5.0) -> int:
    """当前领先方已连续领先多少天(从最后一天往回数)。"""
    n = min(len(a), len(b))
    run = 0
    side = 0
    for i in range(n - 1, -1, -1):
        diff = a[i] - b[i]
        if abs(diff) < min_gap:
            if side:
                break
            continue
        cur = 1 if diff > 0 else -1
        if side == 0:
            side = cur
        elif cur != side:
            break
        run += 1
    return run


def score_pair(a: list[float], b: list[float]) -> dict:
    """给一对主线打跷跷板分(0-100)。

    三块: 反向相关(最重, 55) + 交替轮数(30) + 双方活跃度(15)。
    只看相关系数会把"同时衰减"误判成跷跷板, 所以交替次数必须单独计分。
    """
    corr = pearson(a, b)
    flips = alternations(a, b)
    act_a = sum(1 for x in a if x > 0)
    act_b = sum(1 for x in b if x > 0)
    n = max(1, min(len(a), len(b)))

    corr_part = max(0.0, -corr) * 55.0
    flip_part = min(1.0, flips / 6.0) * 30.0
    act_part = (min(act_a, act_b) / n) * 15.0
    return {
        "corr": round(corr, 2),
        "flips": flips,
        "active_a": act_a,
        "active_b": act_b,
        "score": round(corr_part + flip_part + act_part),
    }


def detect_pairs(
    dates: list[str],
    series: dict[str, list[float]],
    *,
    min_active: int = MIN_ACTIVE_DAYS,
    max_pairs: int = MAX_PAIRS,
    min_score: int = MIN_SCORE,
    min_corr: float = MIN_CORR,
) -> list[dict]:
    """从强度序列里找出跷跷板候选对, 按分数降序返回。"""
    if not dates or len(series) < 2:
        return []
    # 先按上榜天数筛掉冷门, 再按总强度取前 24 个进两两组合(24 对 = 276 组, 毫秒级)
    live = {m: s for m, s in series.items() if sum(1 for x in s if x > 0) >= min_active}
    ranked = sorted(live.items(), key=lambda kv: sum(kv[1]), reverse=True)[:24]

    out: list[dict] = []
    for (ma, sa), (mb, sb) in combinations(ranked, 2):
        st = score_pair(sa, sb)
        if st["corr"] > min_corr or st["score"] < min_score:
            continue
        recent_a = round(_mean(sa[-_RECENT_DAYS:]), 1)
        recent_b = round(_mean(sb[-_RECENT_DAYS:]), 1)
        leader, laggard = (ma, mb) if recent_a >= recent_b else (mb, ma)
        out.append({
            "pair": f"{ma} ↔ {mb}",
            "a": ma,
            "b": mb,
            **st,
            "recent_a": recent_a,
            "recent_b": recent_b,
            "leader": leader,
            "lead_days": _lead_run(sa, sb),
            "hint": (
                f"最近 {_RECENT_DAYS} 天{leader}占优、{laggard}熄火;"
                f"按来回节奏,{leader}走弱时留意{laggard}接力"
            ),
            "series_a": [round(x, 1) for x in sa],
            "series_b": [round(x, 1) for x in sb],
        })
    out.sort(key=lambda p: p["score"], reverse=True)
    return out[:max_pairs]


# ---------- 纯函数: AI 出入参 ----------

def build_ai_payload(dates: list[str], pairs: list[dict]) -> dict:
    """候选对 → 送审 payload(带真实日度序列, 让 AI 自己看交替节奏)。"""
    return {
        "口径说明": "强度分 0-100, 0 表示当天该板块没进主线榜(没资金)",
        "日期轴": dates,
        "候选跷跷板": [
            {
                "pair": p["pair"],
                "A": p["a"],
                "B": p["b"],
                "A序列": p["series_a"],
                "B序列": p["series_b"],
                "规则分": p["score"],
                "反向相关": p["corr"],
                "交替次数": p["flips"],
            }
            for p in pairs
        ],
    }


def parse_ai_response(text: str, valid_pairs: set[str]) -> dict:
    """解析 AI 返回; 容错各厂商格式(围栏 JSON / 思考块 / 截断)。

    picks 里编造的 pair(不在候选集里)直接丢弃 —— 宁可少给, 不能给假的。
    """
    from app.services.ai_json import extract_json_object

    obj = extract_json_object((text or "").strip()) or {}
    picks = []
    seen: set[str] = set()
    for p in (obj.get("picks") or [])[:3]:
        if not isinstance(p, dict):
            continue
        pair = str(p.get("pair") or "").strip()
        if pair not in valid_pairs or pair in seen:
            continue
        seen.add(pair)
        verdict = str(p.get("verdict") or "").strip()
        picks.append({
            "pair": pair,
            "verdict": verdict if verdict in ("成立", "存疑") else "成立",
            "leader": str(p.get("leader") or "").strip()[:40],
            "note": str(p.get("note") or "").strip()[:200],
        })
    summary = str(obj.get("summary") or "").strip()[:400]
    if not summary and not picks:
        raise ValueError(f"AI 返回无法解析为跷跷板结论(原文开头: {(text or '')[:60]})")
    return {"summary": summary, "picks": picks}


# ---------- 装配 ----------

def compute(data_dir, *, kind: str = "concept", window: int = WINDOW_DAYS) -> dict:
    """规则层: 读主线时序 → 候选跷跷板。零 AI 成本, 每次开页都能算。"""
    from app.services.market_mainline import load_mainline_history

    df = load_mainline_history(data_dir, kind)
    dates, series = build_strength(df, window=window)
    pairs = detect_pairs(dates, series)
    return {
        "as_of": dates[-1] if dates else None,
        "kind": kind,
        "window": len(dates),
        "dates": dates,
        "pairs": pairs,
    }


async def generate(data_dir, *, kind: str = "concept") -> dict:
    """规则候选 + AI 甄别。返回 {as_of, kind, pairs, ai} 或 {error}。"""
    from app.services.ai_provider import ai_configured, generate_ai_text

    base = compute(data_dir, kind=kind)
    if not base["pairs"]:
        return {**base, "error": "近期没有满足条件的跷跷板候选 —— 主线数据不足或板块各走各的"}
    if not ai_configured():
        return {**base, "error": "未配置 AI"}

    payload = build_ai_payload(base["dates"], base["pairs"])
    try:
        text = await generate_ai_text(
            [
                {"role": "system", "content": _AI_SYSTEM},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            temperature=0.2,
            max_tokens=None,  # [上游标准] 分析类调用不限制输出(推理模型思考计入预算)
        )
        ai = parse_ai_response(text, {p["pair"] for p in base["pairs"]})
    except Exception as e:  # noqa: BLE001
        logger.warning("seesaw ai failed: %s", e)
        return {**base, "error": f"AI 调用失败: {e}"}
    return {**base, "ai": ai}
