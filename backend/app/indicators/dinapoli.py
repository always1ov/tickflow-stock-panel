"""[R405 · fork 增强] 斐波那契二型 —— 帝纳波利点位的**点位层**。

用户给了一份《帝纳波利点位交易法 · 判定与显示规格》, 并把需求收敛成一句:
「我更想只当一个指标多重判断共振…放在关键价位里面当个指标」。

## 这里只做「在哪」, 不做「做不做 / 何时走」

规格全文是一套完整交易系统(方向过滤、进场方式、状态机、分批止盈、提前离场)。
**这个模块一条都不做**, 只算画在图上的那些位置:

    推进段 → 聚焦点 FOCUS → 反应点 R_k → 每对算 38.2% / 61.8% 两条回撤
    → 挤在一起的几条 = 强支撑区 → 区下方最近一条 = 失效位
    → 由 A/B/C 三点推出的 目标一 / 二 / 三

**不输出任何动作**: 没有买卖、没有仓位、没有提醒, 也不进把握分
(几何量自 R229 起整层不进把握分, 界面上那句话得一直是真的)。
「这些线和六态/量化通道撞不撞」由用户自己看 —— 用户原话: 「是否共振我自己
人工判断, 不打算代码判断」。

## 与「斐波那契一型」的区别

一型(`levels._fibonacci_levels`)取近 120 日里**一个**波段(窗口内最高配最低),
画 0.236~0.786 五条。二型锚在**推进段的最高点**上, 配**最多 5 个反应点**,
每一对都算两条 —— 所以会有十条上下, 而**它的价值恰恰在于哪几条挤在一起**。
一型只有一个波段, 天然不会有重合。

## 最软的一环是摆点

规格第 1 节自己写明:「原书对『有意义的摆点』没有硬公式, 这里用分形摆点补定
规则, **是全套系统中最需要校准的部分**」。FOCUS 认错一根, 上面所有回撤线和
目标全是错的。所以这个模块的每一步都拆成了能单独喂数据的纯函数, 配手工算过
的用例(见 `tests/test_dinapoli_pivots.py`)—— 这一层不稳, 上面全白搭。

## 参数

固定的是原书规定(0.382/0.618 回撤、0.618/1.0/1.618 扩展), 永不改。
带默认值的四个是规格作者替原书补的, 先按规格初值跑, 看图不对再调。
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any

import polars as pl

logger = logging.getLogger(__name__)

# ── 固定参数(原书规定, 不做优化)──────────────────────────────
RETR_SHALLOW = 0.382      # 浅回撤
RETR_DEEP = 0.618         # 深回撤
EXP_COP = 0.618           # 目标一
EXP_OP = 1.000            # 目标二
EXP_XOP = 1.618           # 目标三
DMA_LEN, DMA_SHIFT = 3, 3  # 短期均线 = SMA(C,3) 往后移 3 根

# ── 默认参数(规格替原书补的初值, 可调)────────────────────────
PIVOT_K = 3               # 左右各看几根才算一个拐点
THRUST_MIN = 8            # 连续几根站在短期均线上方才算一波推进
THRUST_MIN_ATR = 3.0      # 这波的幅度至少几倍 ATR(过滤磨盘)
MAX_REACTIONS = 5         # 往回最多取几个反应点
TOL_ATR = 0.5             # 聚类容差 = 几倍 ATR
STOP_BUFFER_ATR = 0.1     # 失效位在参照价位下方再让几倍 ATR

# ── 粗细三档 ─────────────────────────────────────────────────
# 原书对「什么算一个有意义的回调」**没有硬公式**(规格第 1 节自陈), 这四个数是
# 规格作者替它补的。既然是人为补定的, 就不该藏在配置里当"待优化参数" ——
# 这个指标不出买卖信号, 没有可回测的目标函数, 也就**没有"校准"这回事**。
# 它是个**粗细旋钮**: 调大只认大级别回调(线少而稳), 调小小回调也算(线多而密),
# 哪一档合适得用眼睛定。所以后端一次把三档都算出来, 图上直接切。
GRAINS: dict[str, int] = {"coarse": 5, "mid": PIVOT_K, "fine": 2}

# ── 配色(规格 §12)──────────────────────────────────────────
# 「每种颜色全站只表达一种含义」。这一组里有三种意思不同的线, 不能一个色涂到底:
#   回撤位 = 可能停下来的位置(金)   目标 = 往上推算的位置(蓝)
#   失效位 = 跌破这组就不成立(灰)
# K 线是红涨绿跌, 所以价位线一律不用红绿 —— 这条是规格明写的, 也是本仓库的既定口径。
C_RETR = "#A77A1C"
C_TARGET = "#2F6FDB"
C_INVALID = "#8A8578"


@dataclass
class Fib2:
    """一次计算的全部产物。**都是位置, 没有一个是动作。**"""
    focus: float | None = None
    focus_bar: int | None = None
    thrust: tuple[int, int] | None = None      # 推进段 [起, 止] 的下标
    reactions: list[int] = field(default_factory=list)   # 反应点下标, 由近到远
    levels: list[dict] = field(default_factory=list)     # 回撤位(含 k / 深浅)
    targets: list[dict] = field(default_factory=list)    # 目标一/二/三
    zone: dict | None = None                   # 强支撑区 {low, high, strength}
    invalid_at: float | None = None            # 失效位
    first_pullback_bar: int | None = None      # 首次回踩
    dma3: list[float | None] = field(default_factory=list)

    def is_empty(self) -> bool:
        return self.focus is None


# ================================================================
# 基础序列
# ================================================================

def displaced_sma(values: list[float], length: int, shift: int) -> list[float | None]:
    """位移均线: `SMA(values, length)` 整体往后移 `shift` 根。

    **平移之后, 未来 `shift` 根的值在今天就已经知道了** —— 这不是未来函数,
    恰恰相反: 它用的全是已经收盘的数据, 只是画到了右边。规格第 6 节点明这一点,
    也是图上那条短期均线能往右探出去几根的原因。
    """
    n = len(values)
    out: list[float | None] = [None] * n
    if length <= 0 or n < length:
        return out
    run = 0.0
    for i, v in enumerate(values):
        run += v
        if i >= length:
            run -= values[i - length]
        if i >= length - 1:
            j = i + shift
            if j < n:
                out[j] = run / length
    return out


def future_dma(values: list[float], length: int, shift: int) -> list[float]:
    """平移之后**露到最后一根之外**的那几个值 —— 就是图上「未来」区那一段。"""
    n = len(values)
    if length <= 0 or n < length:
        return []
    out: list[float] = []
    for j in range(n, n + shift):
        i = j - shift
        if i < length - 1:
            continue
        out.append(sum(values[i - length + 1:i + 1]) / length)
    return out


# ================================================================
# 摆点 —— 这一层最软, 单独拆出来好验
# ================================================================

def pivot_lows(lows: list[float], k: int = PIVOT_K) -> list[int]:
    """分形低点: `L[i] == min(L[i-k .. i+k])`。

    **两端各留 k 根不判** —— 左边不够比, 右边还没走完。规格第 6 节:摆点要延迟
    k 根才确认, 这正是"不用未来数据"的体现:下标 i 的点位在 i+k 那根收盘后
    才算数, 而我们只在历史上回看, 所以天然满足。
    """
    n = len(lows)
    out: list[int] = []
    for i in range(k, n - k):
        window = lows[i - k:i + k + 1]
        if lows[i] == min(window):
            out.append(i)
    return out


def pivot_highs(highs: list[float], k: int = PIVOT_K) -> list[int]:
    """分形高点, 与 `pivot_lows` 镜像。"""
    n = len(highs)
    out: list[int] = []
    for i in range(k, n - k):
        window = highs[i - k:i + k + 1]
        if highs[i] == max(window):
            out.append(i)
    return out


# ================================================================
# 推进段
# ================================================================

def thrust_segments(
    closes: list[float], dma: list[float | None], highs: list[float],
    lows: list[float], atr: list[float | None],
    *, min_len: int = THRUST_MIN, min_atr: float = THRUST_MIN_ATR,
) -> list[tuple[int, int]]:
    """所有满足条件的上涨推进段 `[s, e]`(下标闭区间)。

    三个条件全要:
      · 区间内每一根都 `C > DMA3x3`
      · 长度 >= `min_len`
      · `max(H[s..e]) - min(L[s-1..e]) >= min_atr × ATR[e]` —— **过滤磨盘**:
        横着走的一串小阳线也能连着站在均线上方, 但它不是一波推进。
    """
    out: list[tuple[int, int]] = []
    n = min(len(closes), len(dma))
    s: int | None = None
    for i in range(n):
        above = dma[i] is not None and closes[i] > dma[i]
        if above and s is None:
            s = i
        elif not above and s is not None:
            _emit(out, s, i - 1, highs, lows, atr, min_len, min_atr)
            s = None
    if s is not None:
        _emit(out, s, n - 1, highs, lows, atr, min_len, min_atr)
    return out


def _emit(out, s, e, highs, lows, atr, min_len, min_atr) -> None:
    if e - s + 1 < min_len:
        return
    a = atr[e] if e < len(atr) else None
    if a is None or not math.isfinite(a) or a <= 0:
        return
    top = max(highs[s:e + 1])
    # 起点往前带一根 —— 一波推进的底在"站上均线的前一根"上, 不在第一根阳线上
    bot = min(lows[max(0, s - 1):e + 1])
    if top - bot >= min_atr * a:
        out.append((s, e))


# ================================================================
# 聚焦点与反应点
# ================================================================

def focus_of(highs: list[float], seg: tuple[int, int]) -> tuple[float, int]:
    """推进段里的最高点 —— 所有回撤都从它往下量。"""
    s, e = seg
    hi = max(highs[s:e + 1])
    return hi, s + highs[s:e + 1].index(hi)


def reactions_before(
    lows: list[float], focus_bar: int, *, k: int = PIVOT_K,
    max_count: int = MAX_REACTIONS, min_gap: float = 0.0,
) -> list[int]:
    """FOCUS 之前的反应点, **由近到远**。

    除了"是个分形低点", 还要满足 `L[R] == min(L[R .. focus_bar])` ——
    **其后没有被更低的点覆盖过**。这一条是帝纳波利挑反应点的关键:被后来
    更低的低点盖住的那个, 已经不是这一段的起点了, 拿它量回撤没有意义。

    `min_gap` —— **价位上离得太近的反应点只留一个**。这一条是冒烟时补上的:
    一段横盘(A 股的平台、一字板太常见了)里每一根都是分形低点、而且全都满足
    "其后没有更低", 于是五个反应点挤在同一个价位上, 量出五条**完全一样**的
    回撤线, 聚类一看"五条重合"就报了个 `strength=5` 的强支撑区 ——
    **那是同一条线数了五遍, 不是五段行情指到同一处**, 而后者才是这个读数的
    全部意义。传 0 则不去重(供单元测试逐条验行为)。
    """
    cands = [i for i in pivot_lows(lows, k) if i < focus_bar]
    out: list[int] = []
    for i in reversed(cands):                      # 由近到远
        if lows[i] != min(lows[i:focus_bar + 1]):
            continue
        if min_gap > 0 and any(abs(lows[i] - lows[j]) <= min_gap for j in out):
            continue                               # 价位上与已选的挤在一起
        out.append(i)
        if len(out) >= max_count:
            break
    return out


# ================================================================
# 回撤位 / 目标位 / 聚类 / 失效位
# ================================================================

def retracements(focus: float, lows: list[float], reactions: list[int]) -> list[dict]:
    """每个反应点配 FOCUS 算一对:浅回撤 38.2%、深回撤 61.8%。"""
    out: list[dict] = []
    for rank, bar in enumerate(reactions, start=1):
        span = focus - lows[bar]
        if span <= 0:
            continue
        out.append({"k": rank, "bar": bar, "kind": "shallow",
                    "value": focus - RETR_SHALLOW * span})
        out.append({"k": rank, "bar": bar, "kind": "deep",
                    "value": focus - RETR_DEEP * span})
    return out


def targets_from(a: float, b: float, c: float) -> list[dict]:
    """三点推目标: `C + ratio × (B − A)`。

    A = 主波段起点(最近那个反应点的低), B = FOCUS, C = 回撤以来的最低点。
    **锚在 C 上而不是锚在 FOCUS 上** —— 回撤越深, 目标越低, 这是这套算法
    自带的保守性, 不要"优化"掉。
    """
    span = b - a
    if span <= 0:
        return []
    return [
        {"key": "COP", "name": "目标一", "value": c + EXP_COP * span},
        {"key": "OP", "name": "目标二", "value": c + EXP_OP * span},
        {"key": "XOP", "name": "目标三", "value": c + EXP_XOP * span},
    ]


def cluster_zone(levels: list[dict], tol: float) -> dict | None:
    """挤在一起的几条回撤线 = 强支撑区。

    只有**来自不同反应点**的线凑在一起才算数 —— 同一个反应点的浅/深两条
    天然离得远, 而真正有意义的是"两段不同的行情量出了同一个位置"。

    排序按规格 3.3: 先看重合了几条, 再看离现价近不近; 取第一个。
    **这就是界面上那句「N 条回撤重合」的来源** —— 它是帝纳波利自己定义强支撑区
    的方式, 不是"跟别的指标共振"(那个由用户自己看)。
    """
    if not levels or tol <= 0:
        return None
    groups: list[list[dict]] = []
    for lv in sorted(levels, key=lambda x: x["value"]):
        if groups and abs(lv["value"] - groups[-1][-1]["value"]) <= tol:
            groups[-1].append(lv)
        else:
            groups.append([lv])
    best: list[dict] | None = None
    for g in groups:
        if len({x["k"] for x in g}) < 2:           # 必须来自不同反应点
            continue
        if best is None or len(g) > len(best):
            best = g
    if best is None:
        return None
    return {"low": min(x["value"] for x in best),
            "high": max(x["value"] for x in best),
            "strength": len(best),
            "members": [{"k": x["k"], "kind": x["kind"]} for x in best]}


def invalidation_price(levels: list[dict], zone_low: float, tol: float,
                       atr: float, fallback: float) -> float:
    """失效位 —— 强支撑区**下方最近的那条**回撤线, 再让 0.1×ATR。

    叫「失效位」不叫「止损」是有意的: 系统里已经有止损线/生命线了(出场线那一套),
    而这条线说的是**「跌破它, 这组回撤就不成立了」**, 是几何结论不是操作指令。
    """
    lower = [x["value"] for x in levels if x["value"] < zone_low - tol]
    base = max(lower) if lower else fallback
    return base - STOP_BUFFER_ATR * atr


def first_pullback_after(closes: list[float], dma: list[float | None],
                         thrust_end: int) -> int | None:
    """推进段结束后**第一次收盘跌回短期均线下方**的那一根 —— 图上的「首次回踩」。"""
    for i in range(thrust_end + 1, min(len(closes), len(dma))):
        if dma[i] is not None and closes[i] <= dma[i]:
            return i
    return None


# ================================================================
# 总入口
# ================================================================

def compute(df: pl.DataFrame, *, pivot_k: int = PIVOT_K) -> Fib2:
    """从日 K 算出全部位置。任何一步缺数据就返回空, 不抛异常。

    `pivot_k` = 粗细档(见 `GRAINS`)。**只影响摆点认得多细**, 推进段和短期均线
    与它无关 —— 所以三档共用同一段上攻、同一个首次回踩, 只有回撤线和强支撑区
    会变多变少。
    """
    need = {"high", "low", "close"}
    if df.is_empty() or not need.issubset(df.columns) or df.height < 30:
        return Fib2()
    try:
        return _compute(df, pivot_k)
    except Exception as e:                          # noqa: BLE001
        logger.warning("dinapoli compute failed: %s", e)
        return Fib2()


def _compute(df: pl.DataFrame, pivot_k: int = PIVOT_K) -> Fib2:
    closes = [float(x) for x in df["close"].to_list()]
    highs = [float(x) for x in df["high"].to_list()]
    lows = [float(x) for x in df["low"].to_list()]
    atr = ([None if x is None else float(x) for x in df["atr_14"].to_list()]
           if "atr_14" in df.columns else [None] * len(closes))

    dma = displaced_sma(closes, DMA_LEN, DMA_SHIFT)
    segs = thrust_segments(closes, dma, highs, lows, atr)
    if not segs:
        return Fib2(dma3=dma)

    seg = segs[-1]                                  # 最近一波推进
    focus, focus_bar = focus_of(highs, seg)

    # 容差先算出来 —— 反应点去重和点位聚类用的是同一把尺子, 本来就该一致
    last_atr = next((a for a in reversed(atr) if a and math.isfinite(a) and a > 0), None)
    tol = TOL_ATR * last_atr if last_atr else focus * 0.005

    reacts = reactions_before(lows, focus_bar, k=pivot_k, min_gap=tol)
    if not reacts:
        return Fib2(dma3=dma, thrust=seg, focus=focus, focus_bar=focus_bar)

    lv = retracements(focus, lows, reacts)
    zone = cluster_zone(lv, tol)

    a = lows[reacts[0]]                             # 主波段起点
    c_pt = min(lows[focus_bar:]) if focus_bar < len(lows) else lows[-1]
    tgts = targets_from(a, focus, c_pt)

    invalid = None
    if zone and last_atr:
        invalid = invalidation_price(lv, zone["low"], tol, last_atr, a)

    return Fib2(
        focus=focus, focus_bar=focus_bar, thrust=seg, reactions=reacts,
        levels=lv, targets=tgts, zone=zone, invalid_at=invalid,
        first_pullback_bar=first_pullback_after(closes, dma, seg[1]),
        dma3=dma,
    )


def to_levels(res: Fib2, close: float | None) -> list[dict]:
    """转成关键价位那一层认识的横线格式(与其余 12 组同构)。

    界面用词按规格第 12 节的对照表走白话: 浅回撤 / 深回撤 / 目标一二三 /
    失效位 —— 原术语(F3、F5、COP、OP、XOP)只留在代码和注释里。
    """
    from app.indicators.levels import _side                      # 复用同一套口径

    out: list[dict] = []
    if res.is_empty() or not close:
        return out
    seen: set[float] = set()

    def add(v: float, label: str, strength: str, color: str) -> None:
        r = round(float(v), 2)
        if r in seen or not math.isfinite(r) or r <= 0:
            return
        seen.add(r)
        out.append({"value": r, "label": label, "type": "fib2",
                    "side": _side(r, close), "strength": strength, "color": color})

    for x in res.levels:
        cn = "浅回撤" if x["kind"] == "shallow" else "深回撤"
        add(x["value"], f"{cn} R{x['k']}", "medium", C_RETR)
    for t in res.targets:
        add(t["value"], t["name"], "medium", C_TARGET)
    if res.invalid_at is not None:
        add(res.invalid_at, "失效位", "strong", C_INVALID)
    return out
