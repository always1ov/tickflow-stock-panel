"""[fork 增强] R121 AI 优选**事实校验** —— 让"AI 说的话"可被数据当场证伪。

背景: 优选的提示词早就要求"理由必须带具体数字(量比、涨幅、距离、价位)",
但没有任何东西**检查这些数字是不是真的**。模型把量比 0.87 说成 1.25、把关键位
2383 写成 2372, 界面照样原样展示 —— 用户会照着这个数字挂单。这是整条链上
最危险的一环: 错的不是判断, 是事实。

做法: 把 AI 理由里的数字抽出来, 拿**送审时喂给它的那份日 K**逐条对账。
  - 涨幅 x%   → 最近几根里有没有对得上的 change_pct
  - 量比 x    → 最近几根里有没有对得上的 vol_ratio_5d
  - 价位 x 元 → 是否落在近 60 日价格区间内(离谱价位 = 用户会照着挂单, 最危险)

判定分三档(宁可标存疑, 不要默默放过):
  ok    —— 抽到的数字全部对得上, 或理由里压根没提数字(不算错, 但会另行提示)
  存疑  —— 有对不上的数字, 或理由是"规则分高/AI 看多"这类复述(提示词明令禁止)
  驳回  —— 价位离谱(超出近 60 日区间 ±15%), 或代码根本不在候选集里

**驳回的 pick 不展示为推荐**。这是有意为之: 一条编造价位的建议, 比没有建议更糟。
"""
from __future__ import annotations

import re

# 数字容差 —— 卡太死会把"约等于"误判成撒谎, 卡太松等于没查
_PCT_TOL = 0.35        # 涨幅: 百分点
_RATIO_TOL = 0.15      # 量比: 绝对值
_PRICE_BAND = 0.15     # 价位: 超出近 60 日区间上下 15% 判离谱
_LOOKBACK_BARS = 6     # 理由里的涨幅/量比允许指向最近几根 K

# 提示词明令禁止的"空理由": 把筛选前就知道的东西复述一遍
_HOLLOW_PATTERNS = (
    (re.compile(r"规则分(高|不低|靠前)|把握分(高|100)"), "复述规则分"),
    (re.compile(r"AI\s*看多|信号共振|多信号"), "复述信号"),
    (re.compile(r"^(主线|龙头|人气)[^,，。]{0,6}$"), "只说主线不说量价"),
)

_PCT_RE = re.compile(r"(?:涨|涨幅|上涨|收涨)\s*([0-9]+(?:\.[0-9]+)?)\s*%")
_RATIO_RE = re.compile(r"量比\s*([0-9]+(?:\.[0-9]+)?)")
_PRICE_RE = re.compile(r"(?<![0-9.%])([0-9]{2,5}(?:\.[0-9]{1,2})?)\s*(?:元|附近|上方|下方|一线|关|守住|站上|回踩)")


def _bars(cand: dict) -> list[dict]:
    """取候选里那份送审日 K(键名带天数, 这里不关心具体是多少天)。"""
    for k, v in cand.items():
        if k.startswith("最近") and k.endswith("日K") and isinstance(v, list):
            return [b for b in v if isinstance(b, dict)]
    return []


def _num(v) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f else None      # NaN → None


def _check_pct(said: float, bars: list[dict]) -> dict:
    """理由里的涨幅能不能在最近几根 K 里找到。"""
    got = [_num(b.get("change_pct")) for b in bars[-_LOOKBACK_BARS:]]
    got = [g for g in got if g is not None]
    if not got:
        return {"kind": "涨幅", "said": said, "actual": None, "ok": None,
                "note": "送审数据里没有涨跌幅, 无法核对"}
    best = min(got, key=lambda g: abs(g - said))
    ok = abs(best - said) <= _PCT_TOL
    return {"kind": "涨幅", "said": said, "actual": round(best, 2), "ok": ok,
            "note": "" if ok else f"最近{len(got)}根里最接近的是 {best:.2f}%"}


def _check_ratio(said: float, bars: list[dict]) -> dict:
    got = [_num(b.get("vol_ratio_5d")) for b in bars[-_LOOKBACK_BARS:]]
    got = [g for g in got if g is not None]
    if not got:
        return {"kind": "量比", "said": said, "actual": None, "ok": None,
                "note": "送审数据里没有量比, 无法核对"}
    best = min(got, key=lambda g: abs(g - said))
    ok = abs(best - said) <= _RATIO_TOL
    return {"kind": "量比", "said": said, "actual": round(best, 2), "ok": ok,
            "note": "" if ok else f"最近{len(got)}根里最接近的是 {best:.2f}"}


def _check_price(said: float, bars: list[dict]) -> dict:
    """价位是否落在近 60 日真实价格区间内。离谱 = 驳回级别。"""
    highs = [_num(b.get("high")) for b in bars]
    lows = [_num(b.get("low")) for b in bars]
    highs = [h for h in highs if h is not None]
    lows = [x for x in lows if x is not None]
    if not highs or not lows:
        return {"kind": "价位", "said": said, "actual": None, "ok": None,
                "note": "送审数据里没有价格, 无法核对"}
    lo, hi = min(lows) * (1 - _PRICE_BAND), max(highs) * (1 + _PRICE_BAND)
    ok = lo <= said <= hi
    return {"kind": "价位", "said": said, "actual": [round(min(lows), 2), round(max(highs), 2)],
            "ok": ok, "fatal": not ok,
            "note": "" if ok else f"该股近期价格区间是 {min(lows):.2f}~{max(highs):.2f}, 这个价位对不上"}


def verify_pick(pick: dict, cand: dict | None) -> dict:
    """校验一条优选。返回 pick 的副本, 附 checks / verdict / verdict_note。"""
    out = dict(pick)
    reason = str(pick.get("reason") or "")
    if cand is None:
        out.update({"checks": [], "verdict": "驳回",
                    "verdict_note": "这个代码不在今天的候选集里 —— AI 选了一只没让它选的票"})
        return out

    bars = _bars(cand)
    checks: list[dict] = []
    for m in _PCT_RE.finditer(reason):
        checks.append(_check_pct(float(m.group(1)), bars))
    for m in _RATIO_RE.finditer(reason):
        checks.append(_check_ratio(float(m.group(1)), bars))
    for m in _PRICE_RE.finditer(reason):
        checks.append(_check_price(float(m.group(1)), bars))

    hollow = [label for pat, label in _HOLLOW_PATTERNS if pat.search(reason)]
    fatal = [c for c in checks if c.get("fatal")]
    wrong = [c for c in checks if c.get("ok") is False]

    # ok is None = 数据缺失, **核不了**。它既不算对也不算错 —— 早期版本把它
    # 归进"已核对", 等于把"没查"说成"查过了", 恰恰是这套东西要杜绝的事。
    passed = [c for c in checks if c.get("ok") is True]
    unknown = [c for c in checks if c.get("ok") is None]

    if fatal:
        verdict, note = "驳回", fatal[0]["note"]
    elif wrong:
        verdict = "存疑"
        note = "；".join(f"说{c['kind']} {c['said']}, {c['note']}" for c in wrong[:2])
    elif hollow:
        verdict, note = "存疑", f"理由{('、'.join(hollow))}, 不是量价证据"
    elif not passed:
        verdict = "待查"
        note = (f"{len(unknown)} 项数字缺少可对账的数据" if unknown
                else "理由里没有可核对的数字")
    else:
        verdict = "已核对"
        note = f"{len(passed)} 项数字与日K一致"
        if unknown:
            note += f"; 另有 {len(unknown)} 项无数据可对"

    # 盘中临时信号必须注明等收盘确认(提示词有要求, 这里做强制检查)
    if cand.get("盘中待收盘确认") and "收盘" not in reason:
        if verdict in {"已核对", "待查"}:
            verdict = "存疑"
        note = (note + "；" if note else "") + "这是盘中临时信号, 理由里没说要等收盘确认"

    out.update({"checks": checks, "verdict": verdict, "verdict_note": note})
    return out


def verify_picks(picks: list[dict], candidates: list[dict]) -> list[dict]:
    """批量校验。candidates 就是送审时那份 `_candidate_market_data` 输出。"""
    by_symbol = {str(c.get("symbol", "")).upper(): c for c in candidates or []}
    return [verify_pick(p, by_symbol.get(str(p.get("symbol", "")).upper()))
            for p in (picks or [])]


def summarize(verified: list[dict]) -> dict:
    """一句话结论, 给界面顶部用。"""
    n = len(verified)
    rejected = [p for p in verified if p.get("verdict") == "驳回"]
    doubtful = [p for p in verified if p.get("verdict") == "存疑"]
    return {
        "total": n,
        "rejected": len(rejected),
        "doubtful": len(doubtful),
        "clean": len([p for p in verified if p.get("verdict") == "已核对"]),
        "text": (
            "今天没有优选" if n == 0
            else f"{len(rejected)} 条因数字对不上被驳回" if rejected
            else f"{len(doubtful)} 条存疑, 已标出" if doubtful
            else "理由中的数字已逐条与日K核对一致"
        ),
    }
