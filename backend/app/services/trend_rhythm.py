"""[fork 增强] R187 红绿节拍 —— 反复进多头又跌出, 到底是蓄势还是反复失败。

用户: 「一个票经过多次进入上升趋势后又跌出, 反复这样, 就意味着多头力量变强,
应该对这个票加分」「红绿红绿红绿这样力量变强就有可能一直上涨吃到主升浪」。

## 为什么不能只数次数

「反复进多头又跌出」**同时对应两种完全相反的形态**, 而它们的**次数一模一样**:

  蓄势      每次回撤的低点抬高、回撤变浅、红段变长 —— 压力在被消化
  反复失败  同一个位置撞了五次没过去、低点走平或下移 —— 卖方每次都赢

只数次数的话, 「撞五次没过去」拿到的分会比「真蓄势试了两次」还高 ——
**恰好把最该躲开的票排到最前面**。所以这里数的不是次数, 是**次数 × 几何形状**。

## 怎么量

把六态序列按 BULLISH(红) / 非 BULLISH(绿) 压成交替的段, 每个「循环」= 一个红段
+ 跟着的一个绿段。跨循环看四件事:

  低点抬高    每个绿段的最低收盘逐次抬高       ← **否决项**
  高点抬高    每个红段的最高收盘逐次抬高
  红段变长    红天数占循环天数的比例逐次提升   ← 「力量变强」最直观的表达
  回撤变浅    绿段相对前一个红段高点的跌幅逐次变小

低点不抬高就直接不算蓄势 —— 低点在下移的"反复", 是下台阶不是夯实。

## 输出的是**档位**不是分数

`building` 蓄势 / `choppy` 震荡 / `failing` 反复失败 / `none` 样本不足。

刻意不给连续分数: 这东西还没被验证过, 给个分数就会有人(包括我)想把它加进
把握分, 而把握分的三个权重本身还在等台账验证。先当**注记**用、先落台账看它
有没有区分度 —— 这是本仓库 R133/R134 已经立过的规矩。

## 与既有三维度的性质差别

把握分的三个维度(趋势强度/量能/位置)全是**当下快照**, 这个是**历史过程**。
两种时间尺度硬揉进同一个加权里, 归因会变得没法读 —— 这也是它先不进分数的
理由之一。

**可从历史 K 线回算**(livermore.compute 给的是完整 steps), 所以不像 R175 的
通道结论那样有"不记就补不了"的时间性 —— 台账可以直接拿历史跑, 不用等三个月。
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

BUILDING = "building"   # 蓄势: 红绿交替且几何形状向好
CHOPPY = "choppy"       # 震荡: 交替够多但形状说明不了问题
FAILING = "failing"     # 反复失败: 低点没抬高
NONE = "none"           # 样本不足: 循环不够, 谈不上"反复"

LEVELS = (BUILDING, CHOPPY, FAILING, NONE)
LEVEL_CN = {BUILDING: "蓄势", CHOPPY: "震荡", FAILING: "反复失败", NONE: "—"}

# 至少要几个完整循环才谈得上"反复"。2 个是下限 —— 一次红绿只是一次回撤,
# 谈不上"反复"; 但要求 3 个又会把很多刚开始夯实的票挡在外面。
MIN_CYCLES = 2
# 段太短不算一次真的进出。三天以下多半是噪声穿越, 数进去会把一次正常波动
# 拆成好几个"循环", 把次数灌水。
MIN_RUN_DAYS = 3


def _runs(steps: list[dict]) -> list[dict]:
    """六态序列 → 交替的红/绿段。

    过短的段直接**并进前一段**而不是丢弃 —— 丢弃会让前后两个同色段接不上,
    凭空多出一个循环; 并进去才是"这几天的穿越不算数"的正确表达。
    """
    from app.indicators.livermore import BULLISH

    raw: list[dict] = []
    for s in steps:
        st = s.get("state")
        if st is None:
            continue
        side = "red" if st in BULLISH else "green"
        c = s.get("close")
        if c is None:
            continue
        if raw and raw[-1]["side"] == side:
            r = raw[-1]
            r["days"] += 1
            r["hi"] = max(r["hi"], float(c))
            r["lo"] = min(r["lo"], float(c))
            r["end"] = s.get("date")
        else:
            raw.append({"side": side, "days": 1, "hi": float(c), "lo": float(c),
                        "start": s.get("date"), "end": s.get("date")})

    # 合并过短的段
    out: list[dict] = []
    for r in raw:
        if out and r["days"] < MIN_RUN_DAYS and len(out) >= 1:
            prev = out[-1]
            prev["days"] += r["days"]
            prev["hi"] = max(prev["hi"], r["hi"])
            prev["lo"] = min(prev["lo"], r["lo"])
            prev["end"] = r["end"]
            continue
        if out and out[-1]["side"] == r["side"]:
            prev = out[-1]
            prev["days"] += r["days"]
            prev["hi"] = max(prev["hi"], r["hi"])
            prev["lo"] = min(prev["lo"], r["lo"])
            prev["end"] = r["end"]
            continue
        out.append(dict(r))
    return out


def _cycles(runs: list[dict]) -> list[dict]:
    """段序列 → 循环。一个循环 = 一个红段 + 紧跟的一个绿段。

    从第一个红段开始配对; 末尾落单的红段(还没跌出去)不算一个完整循环,
    但它是"当前正在走的这一段", 调用方要另外知道。
    """
    cyc: list[dict] = []
    i = 0
    while i < len(runs) - 1:
        if runs[i]["side"] != "red":
            i += 1
            continue
        red, green = runs[i], runs[i + 1]
        if green["side"] != "green":
            i += 1
            continue
        depth = (red["hi"] - green["lo"]) / red["hi"] if red["hi"] else None
        total = red["days"] + green["days"]
        cyc.append({
            "red_high": red["hi"],
            "green_low": green["lo"],
            "red_days": red["days"],
            "green_days": green["days"],
            # 红段占这一循环的比例 —— 「红越来越长、绿越来越短」就是它在上升
            "red_share": round(red["days"] / total, 3) if total else None,
            "dip_pct": round(depth, 4) if depth is not None else None,
            "start": red["start"], "end": green["end"],
        })
        i += 2
    return cyc


def _rising(vals: list[float | None], *, strict: bool = False) -> bool | None:
    """逐次抬高吗。None 太多就返回 None(说不出来), 不硬给一个 False。"""
    xs = [v for v in vals if v is not None]
    if len(xs) < 2:
        return None
    return all(xs[i + 1] > xs[i] for i in range(len(xs) - 1)) if strict else \
        all(xs[i + 1] >= xs[i] * 0.999 for i in range(len(xs) - 1))


def _falling(vals: list[float | None]) -> bool | None:
    xs = [v for v in vals if v is not None]
    if len(xs) < 2:
        return None
    return all(xs[i + 1] <= xs[i] * 1.001 for i in range(len(xs) - 1))


# ======================== 磨底磨了多久 ========================
#
# 用户追加的一句把问题收窄了: 「其实我是想知道一个票磨底磨了多久」。
# 上面那套算的是**磨得好不好**(蓄势 / 反复失败), 这里算的是**磨了多久** ——
# 两个凑一起才完整: 「磨了 87 天, 而且是蓄势」才说明这个底既够久、又磨对了。
#
# 定义: 从今天往回数, 最长的一段时间, 使得这段里 最高收盘/最低收盘 ≤ BOX_RATIO。
# 一旦往回多走一天就撑破这个比例, 说明那天之前价格在另一个高度上 —— 箱体到此为止。
#
# 为什么用收盘而不是最高最低价: 与全系统一致(六态、通道、生命线全是收盘口径)。
# 盘中插针不该把一个走了三个月的箱体判成不存在。

# 箱体高度上限。1.35 = 上下沿差 35% 以内还算"横着的"。
# A 股波动大, 定得太紧(比如 1.15)的话几乎没有票算在磨底; 太松(1.6)则一段
# 下跌途中的反弹也会被算成箱体。
BOX_RATIO = 1.35
# 少于这么多天不叫"磨" —— 两周的横盘是正常呼吸, 不是磨底。
MIN_BASING_DAYS = 20


def basing(steps: list[dict] | None) -> dict:
    """磨底磨了多久。返回 {days, high, low, range_pct, since, is_basing}。

    `days` 永远给出真实测得的长度(哪怕只有几天), `is_basing` 才是"够不够格
    叫磨底"的判定 —— 把两者分开, 界面可以显示「横了 12 天(还不算磨底)」,
    而不是一个含糊的 0。
    """
    xs = [s for s in (steps or []) if s.get("close") is not None]
    if not xs:
        return {"days": 0, "high": None, "low": None, "range_pct": None,
                "since": None, "is_basing": False}

    hi = lo = float(xs[-1]["close"])
    idx = len(xs) - 1
    for k in range(len(xs) - 1, -1, -1):
        c = float(xs[k]["close"])
        nh, nl = max(hi, c), min(lo, c)
        if nl > 0 and nh / nl > BOX_RATIO:
            break          # 再往回就撑破箱体了, 到此为止
        hi, lo, idx = nh, nl, k

    days = len(xs) - idx
    return {
        "days": days,
        "high": round(hi, 3),
        "low": round(lo, 3),
        "range_pct": round(hi / lo - 1, 4) if lo else None,
        "since": xs[idx].get("date"),
        "is_basing": days >= MIN_BASING_DAYS,
    }


def assess(steps: list[dict] | None) -> dict:
    """六态 steps → 红绿节拍判定。纯函数, 不读盘不调网。

    返回 {level, label, cycles, low_rising, high_rising, red_share_rising,
          dip_shallower, reason}
    """
    runs = _runs(steps or [])
    cyc = _cycles(runs)
    n = len(cyc)

    base = {
        # 磨了多久 —— 与"磨得好不好"并列给出, 两个一起才说明问题
        "basing": basing(steps),
        "cycles": n,
        "low_rising": None, "high_rising": None,
        "red_share_rising": None, "dip_shallower": None,
    }
    if n < MIN_CYCLES:
        return {**base, "level": NONE, "label": LEVEL_CN[NONE],
                "reason": f"只有 {n} 个完整红绿循环, 还谈不上「反复」"}

    low_rising = _rising([c["green_low"] for c in cyc], strict=True)
    high_rising = _rising([c["red_high"] for c in cyc])
    share_rising = _rising([c["red_share"] for c in cyc])
    shallower = _falling([c["dip_pct"] for c in cyc])
    got = {**base, "cycles": n, "low_rising": low_rising, "high_rising": high_rising,
           "red_share_rising": share_rising, "dip_shallower": shallower}

    # **否决项**: 低点不抬高的"反复"是下台阶, 不是夯实
    if low_rising is False:
        return {**got, "level": FAILING, "label": LEVEL_CN[FAILING],
                "reason": f"{n} 轮红绿, 但每次回撤的低点没有抬高 —— "
                          f"同一批卖方每次都赢, 这是下台阶不是夯实"}

    strengthening = [x for x in (share_rising, shallower, high_rising) if x]
    if low_rising and len(strengthening) >= 1:
        bits = []
        if share_rising:
            bits.append("红段越来越长")
        if shallower:
            bits.append("回撤越来越浅")
        if high_rising:
            bits.append("高点抬高")
        return {**got, "level": BUILDING, "label": LEVEL_CN[BUILDING],
                "reason": f"{n} 轮红绿, 低点逐次抬高" + (", " + "、".join(bits) if bits else "")}

    return {**got, "level": CHOPPY, "label": LEVEL_CN[CHOPPY],
            "reason": f"{n} 轮红绿, 但几何形状说明不了方向 —— 低点没明显下移, "
                      f"也没看出多头在增强"}


def assess_for_symbol(repo, symbol: str) -> dict:
    """按标的算。取不到数据返回 NONE 档而不是抛 —— 这是个注记, 不该拖垮调用方。

    **走 livermore_service 自己那条取数路** (`_load_symbol_window` + 用户可能
    调过的阈值), 这样这里算出的红绿段与决策台「趋势」列、复盘弹窗看到的是
    同一套状态序列 —— 两处对不上的话, 用户没法拿界面去核对这个判定。
    """
    try:
        from app.indicators.livermore import compute
        from app.services import livermore_service as ls

        closes, dates = ls._load_symbol_window(repo, symbol)
        if len(closes) < 30:
            return {**assess(None), "reason": "历史不足 30 根, 看不出节拍"}
        thr, _src = ls.get_effective_threshold(symbol)
        return assess(compute(closes, dates, thr).get("steps"))
    except Exception as e:  # noqa: BLE001
        logger.debug("trend rhythm skipped for %s: %s", symbol, e)
        return {**assess(None), "reason": "数据不足"}
