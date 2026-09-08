"""[fork 增强] R195 三档 Keltner 的几何量 —— 速度 / 加速度 / 压缩 / 排列。

三条带共用同一个 ATR14 分母(带宽都是 `k×ATR`), 所以三档读数是**同一个量的
三次采样**, 可以直接做加减。这个模块把那些加减做出来。

## 统一坐标

    d_n = (收盘 − MA_n) / ATR        价格偏离该周期均线多少个 ATR

通道位置只是它的线性映射: `pct_n = 0.5 + d_n / (2·k_n)`, k = 2 / 2.5 / 3。
于是五档位置在 ATR 尺上是硬阈值 —— 短期破轨要 2 个 ATR, 中期 2.5, 长期 3。
**三档门槛不同**, 所以"三档同时破轨"不是三个独立事件, 而是递增门槛的嵌套。

## 一阶: 三档之差就是速度

均线是滞后算子。对局部线性的价格路径, `MA_n ≈ (n−1)/2 天前的价格`, 所以
收盘与三条均线是价格在**滞后 0 / 9.5 / 29.5 / 59.5 天**处的四次采样,
相邻两档之差就是那一段的平均速度:

    v1 = (C − MA20)  / 9.5      最近约 10 天
    v2 = (MA20 − MA60) / 20     10~30 天前
    v3 = (MA60 − MA120)/ 30     30~60 天前

三者全部除以 ATR, 单位统一成 **ATR/天** —— 不同价位、不同波动的票之间才可比。

推论: `d20 < d60 < d120` 等价于均线多头排列。**三个通道位置的大小顺序就是
均线排列**, 这两件事是同一件事的两种写法。

## 二阶: 加速度

    a1 = v1 − v2        近期加速度
    a2 = v2 − v3        前期加速度

匀速时 a1 = 0 是**精确成立**的(不是近似): 匀速 v 下 C−MA20 = 9.5v 而
MA20−MA60 = 20v, 两边除以各自的天数都得回 v。

等价的比值形式是 `d60 / d20` 与 **3.105**(= 59/19) 比大小, 但比值在 d20
跨零时会翻转解释, 所以这里用差值 —— 符号永远表示"最近是不是更快"。

档位门槛 `ACCEL_FLAT` 是量出来的, 不是拍的: 合成日线上 |a1| 的中位数约
0.12 ATR/天, 取 0.05(相当于 10 天累积半个 ATR)时"匀速"约占两成, 两侧各四成。

## 敏感度: 三档其实是一个频率分解

同一个价格变化, 三档反应的比例完全不同:

  · **单日冲击**(跳空、消息): Δpct 之比 = 1 : 0.80 : 0.67 —— 短期最敏感
  · **持续趋势**(匀速 n 天): (pct−0.5) 之比 = 1 : 2.48 : 4.18 —— 长期最敏感

所以短期档是高通(抓突发)、长期档是低通(抓状态)。**三档读数之间的不一致
本身就是这波行情的频率成分**: 短期动而中长不动 = 一次性冲击; 三档齐动 =
真的换了状态。

## 重叠: 压缩指数

单个时点上三条带是**区间**, 交集是长度不是面积。交集只取决于均线间距(按 ATR 计):

    压缩指数 O = 三带交集长度 / 短带宽度(4·ATR) ∈ [0, 1]

  · O = 1   短带完全包在另外两条里 —— 三个尺度对"合理价"没有分歧, 即**均线粘合**
  · O = 0   至少两条带脱开 —— 强趋势
  · 短-长带在 |MA20−MA120| ≥ 5·ATR 时**完全没有共同价格区间**: 不存在一个价格
    同时对"一个月视角"和"半年视角"都算正常。这个状态单独命名为**尺度撕裂**。

O 在 0 处饱和, 再强的趋势也是 0。要继续分辨得直接看带符号的 `spread`。

## 为什么打分用 spread 而不是 O

**O 没有方向** —— 下跌趋势的 O 同样是 0。带符号的

    spread = (MA20 − MA120) / ATR

一个数就同时表达了方向与分离度: >0 多头排列且分开, <0 空头排列且分开,
≈0 粘合。而 O 与 |spread| 单调对应(`O = clamp(5−|spread|, 0, 4)/4`), 所以
O 只留给界面显示, 打分走 spread。

## 边界

全部是纯函数, 输入是 `keltner.channels_for_symbols` 已经算好的三档读数 ——
**一次新的取数都不加**。MA 与 ATR 从上下轨反推(`MA=(u+l)/2`,
`ATR=(u−l)/(2k)`), 这是恒等式不是估计。
"""
from __future__ import annotations

from app.indicators.keltner import BANDS, POS_ABOVE, POS_BELOW, POS_NEAR_LOWER, POS_NEAR_UPPER

# 均线的有效滞后天数: MA_n 约等于 (n−1)/2 天前的价格
LAG = {"s": 9.5, "m": 29.5, "l": 59.5}
# 各档的 ATR 倍数(与 keltner.BANDS 同源, 不复制常量)
K = {key: k for key, _ma, _n, k, _cn in BANDS}
# 三档的窗口长度
WINDOW = {key: n for key, _ma, n, _k, _cn in BANDS}

# 速度分段的天数跨度: v1 覆盖最近 9.5 天, v2 覆盖 9.5~29.5, v3 覆盖 29.5~59.5
SPAN1 = LAG["s"]                    # 9.5
SPAN2 = LAG["m"] - LAG["s"]         # 20.0
SPAN3 = LAG["l"] - LAG["m"]         # 30.0

# 匀速参照比 d60/d20 = 59/19。留作对照与测试用 —— 打分走差值不走比值。
STEADY_RATIO_MID = (WINDOW["m"] - 1) / (WINDOW["s"] - 1)
STEADY_RATIO_LONG = (WINDOW["l"] - 1) / (WINDOW["s"] - 1)

# |a1| 小于它算匀速。0.05 ATR/天 = 10 天累积半个 ATR —— 见模块头「档位门槛是量出来的」
ACCEL_FLAT = 0.05

ACCEL_UP = "accel"       # 加速
ACCEL_STEADY = "steady"  # 匀速
ACCEL_DOWN = "decel"     # 减速
ACCEL_CN = {ACCEL_UP: "加速", ACCEL_STEADY: "匀速", ACCEL_DOWN: "减速"}

# 短带与长带完全脱开的临界: |MA20−MA120| ≥ k_s + k_l = 5 个 ATR
TORN_ATR = K["s"] + K["l"]
# 短带被长带完全包住的临界: |MA20−MA120| ≤ k_l − k_s = 1 个 ATR
NESTED_ATR = K["l"] - K["s"]

# 压缩指数的三档。0.8 以上基本是"短带还包在里面"(粘合), 0.05 以下是"已经脱开"。
COMPRESS_TIGHT = 0.80
COMPRESS_LOOSE = 0.05
STACK_BULL = "bull"      # 多头排列 MA20 > MA60 > MA120
STACK_BEAR = "bear"      # 空头排列
STACK_MIXED = "mixed"    # 交叉中


def _f(v) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f and abs(f) != float("inf") else None


def _ma_atr(band: dict | None, key: str) -> tuple[float | None, float | None]:
    """从上下轨反推均线与 ATR。**是恒等式不是估计**: 轨 = MA ± k·ATR。"""
    if not band:
        return None, None
    u, low = _f(band.get("upper")), _f(band.get("lower"))
    if u is None or low is None or u <= low:
        return None, None
    return (u + low) / 2, (u - low) / (2 * K[key])


def _band_interval(band: dict | None) -> tuple[float, float] | None:
    if not band:
        return None
    u, low = _f(band.get("upper")), _f(band.get("lower"))
    return (low, u) if (u is not None and low is not None and u > low) else None


def compress(bands: dict | None) -> float | None:
    """压缩指数 O ∈ [0,1] = 三带交集长度 / 短带宽度。三档缺一不算。"""
    ivs = [_band_interval((bands or {}).get(k_)) for k_ in ("s", "m", "l")]
    if any(v is None for v in ivs):
        return None
    lo = max(v[0] for v in ivs)          # type: ignore[index]
    hi = min(v[1] for v in ivs)          # type: ignore[index]
    short = ivs[0]
    width = short[1] - short[0]          # type: ignore[index]
    if width <= 0:
        return None
    return max(0.0, min(1.0, (hi - lo) / width))


def _accel_level(a1: float | None) -> str | None:
    if a1 is None:
        return None
    if a1 > ACCEL_FLAT:
        return ACCEL_UP
    if a1 < -ACCEL_FLAT:
        return ACCEL_DOWN
    return ACCEL_STEADY


def _stack(ma_s, ma_m, ma_l) -> str | None:
    if ma_s is None or ma_m is None or ma_l is None:
        return None
    if ma_s > ma_m > ma_l:
        return STACK_BULL
    if ma_s < ma_m < ma_l:
        return STACK_BEAR
    return STACK_MIXED


# 三档位置收成 上/中/下 三值 —— 27 种组合的坐标
_UP = (POS_ABOVE, POS_NEAR_UPPER)
_DOWN = (POS_BELOW, POS_NEAR_LOWER)


def combo_code(bands: dict | None) -> str | None:
    """三档位置压成三字码, 如 '上中下'。这是 27 种组合表的行号。"""
    out = []
    for key in ("s", "m", "l"):
        pos = ((bands or {}).get(key) or {}).get("pos")
        if pos is None:
            return None
        out.append("上" if pos in _UP else "下" if pos in _DOWN else "中")
    return "".join(out)


def geometry(bands: dict | None, close) -> dict | None:
    """三档读数 → 全部几何量。纯函数, 零新增取数。

    返回 None 的唯一情形是三档缺任何一档 —— 半档数据推不出速度, 更推不出加速度,
    给个半成品会让界面显示一个看着像真的假数。
    """
    c = _f(close)
    if c is None or not bands:
        return None
    ma_s, atr_s = _ma_atr(bands.get("s"), "s")
    ma_m, _ = _ma_atr(bands.get("m"), "m")
    ma_l, _ = _ma_atr(bands.get("l"), "l")
    if None in (ma_s, ma_m, ma_l) or not atr_s or atr_s <= 0:
        return None
    a = atr_s   # 三档同一个 ATR14, 取短期档那份即可

    d = {"s": (c - ma_s) / a, "m": (c - ma_m) / a, "l": (c - ma_l) / a}
    # 速度: 各段的平均斜率, 单位 ATR/天
    v1 = (c - ma_s) / SPAN1 / a
    v2 = (ma_s - ma_m) / SPAN2 / a
    v3 = (ma_m - ma_l) / SPAN3 / a
    a1, a2 = v1 - v2, v2 - v3
    spread = (ma_s - ma_l) / a
    o = compress(bands)
    level = _accel_level(a1)

    return {
        # --- 原料 ---
        "atr": round(a, 4),
        "ma": {k_: round(v, 3) for k_, v in (("s", ma_s), ("m", ma_m), ("l", ma_l))},
        "d": {k_: round(v, 3) for k_, v in d.items()},
        # --- 一阶: 速度(ATR/天) ---
        "v": {"v1": round(v1, 4), "v2": round(v2, 4), "v3": round(v3, 4)},
        # --- 二阶: 加速度 ---
        "accel": {
            "a1": round(a1, 4),
            "a2": round(a2, 4),
            # 近 10 天因为加速多走(少走)了几个 ATR —— 比 ATR/天 好读
            "gain_atr": round(a1 * SPAN1, 2),
            "level": level,
            "level_cn": ACCEL_CN.get(level or "", ""),
        },
        # --- 重叠 ---
        "compress": None if o is None else round(o, 3),
        "compress_level": (None if o is None else
                           "tight" if o >= COMPRESS_TIGHT else
                           "loose" if o <= COMPRESS_LOOSE else "mid"),
        # --- 排列与分离 ---
        "spread": round(spread, 3),
        "torn": abs(spread) >= TORN_ATR,
        "nested": abs(spread) <= NESTED_ATR,
        "stack": _stack(ma_s, ma_m, ma_l),
        "combo": combo_code(bands),
    }


def explain(g: dict | None) -> list[str]:
    """把几何量翻成几句能直接摆在界面上的话。**只描述, 不下买卖判断** ——
    同一个"加速"在趋势初期是启动、在末端是赶顶, 那是趋势状态与把握分的事。
    """
    if not g:
        return []
    out: list[str] = []
    ac = g.get("accel") or {}
    lvl, gain = ac.get("level"), ac.get("gain_atr")
    if lvl == ACCEL_UP:
        out.append(f"加速中 —— 近 10 天比之前那一段多走了 {gain:.1f} 个 ATR")
    elif lvl == ACCEL_DOWN:
        out.append(f"在减速 —— 近 10 天比之前那一段少走了 {abs(gain):.1f} 个 ATR")
    else:
        out.append("匀速 —— 近 10 天与之前那一段的速度基本一致")

    sp, o = g.get("spread"), g.get("compress")
    if g.get("torn"):
        out.append(f"尺度撕裂: 短带与长带相隔 {abs(sp):.1f} 个 ATR, 已完全没有共同价格区间"
                   " —— 任何价格在一个尺度上超买时, 在另一个尺度上都是超卖")
    elif g.get("nested"):
        out.append(f"均线粘合: 短带完全包在长带里(相隔仅 {abs(sp):.1f} 个 ATR)"
                   " —— 三个尺度对合理价没有分歧, 这是磨底/盘整的形态")
    elif o is not None:
        out.append(f"三尺度重叠 {o:.0%}"
                   + (f", 均线{'多头' if sp > 0 else '空头'}排列相隔 {abs(sp):.1f} 个 ATR"
                      if g.get("stack") in (STACK_BULL, STACK_BEAR) else ", 均线正在交叉"))

    d = g.get("d") or {}
    if all(k_ in d for k_ in ("s", "m", "l")):
        out.append(f"偏离度 短 {d['s']:+.1f} / 中 {d['m']:+.1f} / 长 {d['l']:+.1f} 个 ATR"
                   f"(破轨门槛依次是 {K['s']:.0f} / {K['m']:.1f} / {K['l']:.0f})")
    return out


# ================================================================
# [R195] 历史序列: 压缩持续天数 / 在轨外连续天数
#
# ## 为什么压缩指数不能直接替代磨底
#
# 用户问「既然定义了压缩指数, 就不需要之前做的磨底指标了吧」。**不能直接替代,
# 因为两者量的是不同维度**:
#
#     磨底(trend_rhythm.basing)  给的是「磨了**多久**」—— 天生是历史量
#     压缩指数 O                 给的是「今天**多紧**」—— 天生是瞬时量
#
# 一只票可以今天 O=1(均线完全粘合)但只粘了 5 天; 也可以横了 200 天却因为波动率
# 极低, 均线其实分得开。只拿 O 去回答「磨了多久」会答错。
#
# ## 但 O 的**判据**确实比原来的好, 该换
#
# 原磨底判据是「最高收盘/最低收盘 ≤ 1.35」——**绝对幅度**。一只 ATR 3% 的票和
# 一只 ATR 1% 的票, 同样 35% 的箱体意义完全不同: 前者只是正常波动, 后者是死死
# 摁住。O 用 ATR 归一化, 这一点是对的。
#
# 所以正确的合并方式是: **保留「多久」这个问题, 换掉回答它的判据** ——
#
#     磨底时长 = 连续 O ≥ COMPRESS_TIGHT 的天数
#
# 一个指标同时给出时长与紧度, 不再是两套并列的东西。

# 连续几天在轨外算"站稳"。2 天是最低限 —— 1 天是突破(可能假), 2 天是守住了。
CONFIRM_DAYS = 2
# 算压缩持续天数时最多往回看多少根 —— 再长的"粘合"已经不影响当下判断
MAX_LOOKBACK = 250


def _rolling_mean(vals: list[float], n: int) -> list[float | None]:
    """前缀和滚动均值。不足 n 根的位置给 None(不拿短窗凑数)。"""
    out: list[float | None] = [None] * len(vals)
    if n <= 0 or len(vals) < n:
        return out
    run = sum(vals[:n])
    out[n - 1] = run / n
    for i in range(n, len(vals)):
        run += vals[i] - vals[i - n]
        out[i] = run / n
    return out


def series(closes: list[float] | None, atrs: list[float] | None) -> list[dict]:
    """逐日几何量。返回与输入等长的列表, 算不出来的位置是 {}。

    closes / atrs 升序对齐(atrs 走 pipeline 的 atr_14 列)。三条均线在这里自己滚
    —— 长期档本来就没有预计算列, 顺手把另外两条也滚了, 省得两处口径不一致。
    """
    cs = [_f(c) for c in (closes or [])]
    as_ = [_f(a) for a in (atrs or [])]
    n = len(cs)
    if n == 0 or len(as_) != n or any(c is None for c in cs):
        return []
    vals: list[float] = [c for c in cs]  # type: ignore[misc]
    ma = {k_: _rolling_mean(vals, WINDOW[k_]) for k_ in ("s", "m", "l")}
    out: list[dict] = []
    for i in range(n):
        a = as_[i]
        m_s, m_m, m_l = ma["s"][i], ma["m"][i], ma["l"][i]
        if a is None or a <= 0 or None in (m_s, m_m, m_l):
            out.append({})
            continue
        c = vals[i]
        # 三带交集 / 短带宽度 —— 与 compress() 同一个式子, 只是这里没有现成的轨
        lo = max(m_s - K["s"] * a, m_m - K["m"] * a, m_l - K["l"] * a)
        hi = min(m_s + K["s"] * a, m_m + K["m"] * a, m_l + K["l"] * a)
        o = max(0.0, min(1.0, (hi - lo) / (2 * K["s"] * a)))
        out.append({
            "o": o,
            "d_s": (c - m_s) / a,
            "spread": (m_s - m_l) / a,
            "close": c,
            "atr": a,
        })
    return out


def _tail_run(rows: list[dict], ok) -> int:
    """从最后一根往回数, 连续满足 ok 的天数。中间断一天就停。"""
    run = 0
    for r in reversed(rows[-MAX_LOOKBACK:]):
        if not r or not ok(r):
            break
        run += 1
    return run


def runs(rows: list[dict]) -> dict:
    """从今天往回数的三种连续天数 + 压缩期的箱体。

    · compress_days  连续 O ≥ COMPRESS_TIGHT —— **这是新的「磨底磨了多久」**
    · above_run      连续收盘在短期上轨之上 —— 1 天是突破, ≥2 天是站稳
    · below_run      连续收盘在短期下轨之下
    """
    rows = [r for r in rows if r is not None]
    if not rows:
        return {"compress_days": 0, "above_run": 0, "below_run": 0,
                "box_high": None, "box_low": None, "box_range_atr": None}
    cd = _tail_run(rows, lambda r: r.get("o", 0.0) >= COMPRESS_TIGHT)
    up = _tail_run(rows, lambda r: r.get("d_s", 0.0) > K["s"])
    dn = _tail_run(rows, lambda r: r.get("d_s", 0.0) < -K["s"])
    box_hi = box_lo = box_rng = None
    if cd >= 1:
        seg = [r["close"] for r in rows[-cd:] if "close" in r]
        if seg:
            box_hi, box_lo = max(seg), min(seg)
            # 箱体宽度用**当天 ATR**表达, 与 O 同一把尺 —— 「箱体 12%」在不同
            # 波动的票之间没有可比性, 「箱体 3 个 ATR」才有
            atr_now = rows[-1].get("atr")
            if atr_now:
                box_rng = round((box_hi - box_lo) / atr_now, 2)
    return {"compress_days": cd, "above_run": up, "below_run": dn,
            "box_high": box_hi, "box_low": box_lo, "box_range_atr": box_rng}


# ================================================================
# [R195] 六态 × 通道 × 时间 → 事件
#
# 用户: 「我的系统还有六态趋势, 单纯看组合无法判断趋势。我说的趋势是比如,
#        K 线穿过短期上轨算站稳了还是突破了? 还是说这就算进入了主升浪?」
#
# **这个困惑是对的, 而且上面那些几何量一个都答不了它。** 原因是问题里混着三个
# 互相独立的维度, 少任何一个都答不成:
#
#     位置  在哪儿?        ← Keltner 三档     回答"贵不贵"
#     方向  什么状态?      ← 六态             回答"趋势确立没有"
#     确认  第几天?        ← 在轨外连续天数   回答"站稳没有"
#
# 「破上轨」本身只是一句**统计陈述**: 收盘比 20 日均线高出 2 个 ATR。它不含
# 任何方向信息 —— 同一个"破上轨":
#
#     在 UT(已确认上涨趋势)里  = 趋势内加速, 沿上轨走是常态, 不该因此卖
#     在 DT(下跌趋势)里        = 反弹撞到阻力, 根本不是突破
#     在 NR/SR(回升)里         = **突破尝试**, 方向还没确认
#     在 NREA/SREA(回撤)里     = 回撤结束, 回到强势侧
#
# 而「突破」与「站稳」的区别**根本不在位置上, 在时间上**:
#
#     突破 = 在轨外第 1 天(可能是假突破)
#     站稳 = 连续 ≥ CONFIRM_DAYS 天守在轨外
#
# 「主升浪」则要五个条件同时成立才配这么叫, 见 MAIN_ADVANCE 的定义 ——
# 给一个可回测的定义, 而不是一种感觉。

EV_BREAKOUT_TRY = "breakout_try"      # 突破尝试(第 1 天, 未确认)
EV_BREAKOUT_HOLD = "breakout_hold"    # 突破站稳
EV_TREND_ACCEL = "trend_accel"        # 趋势内加速
EV_MAIN_ADVANCE = "main_advance"      # 主升浪特征
EV_EXHAUSTING = "exhausting"          # 末端钝化
EV_BOUNCE_CAP = "bounce_cap"          # 反弹遇阻(空头侧破上轨)
EV_PULLBACK_END = "pullback_end"      # 回撤结束
EV_BREAKDOWN_TRY = "breakdown_try"    # 破位第 1 天
EV_BREAKDOWN_HOLD = "breakdown_hold"  # 破位站稳(空头侧)
EV_SHAKEOUT = "shakeout"              # 强势洗盘(多头侧破下轨)
EV_COILING = "coiling"                # 压缩待变(粘合中, 没到轨)
EV_NONE = "none"                      # 没有可命名的事件

EVENT_CN = {
    EV_BREAKOUT_TRY: "突破尝试",
    EV_BREAKOUT_HOLD: "突破站稳",
    EV_TREND_ACCEL: "趋势内加速",
    EV_MAIN_ADVANCE: "主升浪特征",
    EV_EXHAUSTING: "末端钝化",
    EV_BOUNCE_CAP: "反弹遇阻",
    EV_PULLBACK_END: "回撤结束",
    EV_BREAKDOWN_TRY: "破位第一天",
    EV_BREAKDOWN_HOLD: "破位站稳",
    EV_SHAKEOUT: "强势洗盘",
    EV_COILING: "压缩待变",
    EV_NONE: "无事件",
}

# 主升浪的五个条件 —— 写成常量是为了能被测试逐条钉住, 也为了以后调的时候
# 知道自己在调哪一条。
MAIN_ADVANCE = {
    "state": "UT",            # ① 六态已确认为上涨趋势
    "stack": STACK_BULL,      # ② 均线多头排列
    "min_spread": 2.0,        # ③ 短长均线已分离 ≥ 2 个 ATR(不是粘合状态)
    "min_above_run": 3,       # ④ 连续 3 天以上守在短期上轨之上
    "min_a1": 0.0,            # ⑤ 没有在减速
}
# 连续这么多天在上轨外还在减速 = 末端钝化
EXHAUST_RUN = 5

_BULL_STATES = ("UT", "NR", "SR")


def event(*, state: str | None, duration: int | None, geo: dict | None,
          run: dict | None) -> dict:
    """六态 × 通道 × 时间 → 一个明确的事件名。纯函数。

    state / duration: 六态状态与它走到第几天(livermore)。
    geo:  geometry() 的返回值。
    run:  runs() 的返回值(在轨外连续天数、压缩天数)。

    返回 {code, cn, why, confirmed}。`confirmed=False` 表示"还没站稳",
    界面必须把这个区别显示出来 —— 突破与站稳是两件事, 混在一起就是在鼓励追高。
    """
    g, r = geo or {}, run or {}
    up, dn = int(r.get("above_run") or 0), int(r.get("below_run") or 0)
    cd = int(r.get("compress_days") or 0)
    a1 = (g.get("accel") or {}).get("a1")
    bull = state in _BULL_STATES

    def mk(code, why, confirmed):
        return {"code": code, "cn": EVENT_CN[code], "why": why, "confirmed": confirmed}

    # ---- 在短期上轨之外 ----
    if up >= 1:
        if not bull:
            return mk(EV_BOUNCE_CAP,
                      f"六态在空头侧({state}), 破上轨只是反弹撞到阻力 —— 不是突破",
                      False)
        if state == "UT":
            m = MAIN_ADVANCE
            if (g.get("stack") == m["stack"]
                    and (g.get("spread") or 0) >= m["min_spread"]
                    and up >= m["min_above_run"]
                    and (a1 is not None and a1 >= m["min_a1"])):
                return mk(EV_MAIN_ADVANCE,
                          f"上涨趋势 + 均线多头排列 + 短长已分离 {g.get('spread'):.1f} 个 ATR"
                          f" + 连续 {up} 天守在上轨之上 + 未减速 —— 五条全中",
                          True)
            if up >= EXHAUST_RUN and a1 is not None and a1 < -ACCEL_FLAT:
                return mk(EV_EXHAUSTING,
                          f"已连续 {up} 天在上轨外, 但近 10 天在减速 —— 涨势在钝化",
                          True)
            return mk(EV_TREND_ACCEL,
                      f"趋势已确认(UT), 破上轨是趋势内加速 —— 沿上轨走是常态, 不必因此减",
                      up >= CONFIRM_DAYS)
        # NR/SR: 回升途中冲出上轨 —— 这才是真正意义上的"突破"
        if up >= CONFIRM_DAYS:
            return mk(EV_BREAKOUT_HOLD,
                      f"回升({state})途中冲出上轨并连续守住 {up} 天 —— 突破站稳",
                      True)
        return mk(EV_BREAKOUT_TRY,
                  f"回升({state})途中第 1 天冲出上轨 —— 突破尝试, 收盘守不住就是假突破",
                  False)

    # ---- 在短期下轨之外 ----
    if dn >= 1:
        if bull:
            return mk(EV_SHAKEOUT,
                      f"六态仍在多头侧({state}), 跌破下轨更像强势洗盘 —— 看长期档还在不在上沿",
                      dn >= CONFIRM_DAYS)
        if dn >= CONFIRM_DAYS:
            return mk(EV_BREAKDOWN_HOLD, f"空头侧连续 {dn} 天在下轨之下 —— 破位站稳", True)
        return mk(EV_BREAKDOWN_TRY, "空头侧第 1 天跌破下轨 —— 还没确认", False)

    # ---- 没到轨: 回撤刚结束 / 压缩待变 ----
    if state in ("NREA", "SREA") and duration == 1:
        return mk(EV_PULLBACK_END, "今日刚从回撤转出 —— 回到强势侧的第一天", False)
    if cd >= CONFIRM_DAYS and (g.get("compress") or 0) >= COMPRESS_TIGHT:
        return mk(EV_COILING,
                  f"均线粘合已 {cd} 天(三尺度对合理价没有分歧) —— 压缩待变, 方向未定",
                  False)
    return mk(EV_NONE, "既没到轨, 也不在粘合状态", False)


# ================================================================
# [R195] 27 种组合的补充注记
#
# 用户: 「原本系统的『Keltner 短期/中期/长期』禁止动, 这是根本, 不能改动。
#        这一套组合是它的补充。」
#
# 所以这一层**只读不写**: `keltner.verdict()` 那 10 条结论一个字不改, 这里在它
# 之外补一句"这一格具体是哪种组合"。
#
# 补的是什么: 三档位置收成 上/中/下 共 27 种组合, 而底层 10 条结论要覆盖它们,
# 必然有**一对多**。其中 9 种的组合特征与结论的措辞不完全贴合, 2 种压根落在
# 结论之外。这一层把那 11 种单独说清楚 —— 结论照旧显示, 注记摆在它旁边。
#
# 判断"贴不贴合"的依据只有一条: **结论的正文里有没有说错这一格的事实。**
# 例如 high_short_only 的正文写着"大级别还早", 而组合「上中上」的长期档就在
# 上沿 —— 那不是措辞粗糙, 是把事实说反了。

# 组合 → (补充标题, 补充说明)。**只列需要补的**; 其余 16 种底层结论已经说准了,
# 不该再多一句话去占地方。
COMBO_NOTES: dict[str, tuple[str, str]] = {
    # ---- 底层结论完全没有覆盖到的两种 ----
    "中中上": ("半年高位",
              "只有长期档到上沿, 中短期都已回到通道中部 —— 半年尺度位置不低, "
              "但一个月与一个季度都休整完了。底层结论在这一格是空的。"),
    "中中下": ("半年低位",
              "只有长期档到下沿, 中短期都已回到通道中部 —— 半年尺度跌了不少, "
              "中短期已经企稳, 是潜在的底部构筑。底层结论在这一格是空的。"),
    # ---- 结论正文与这一格的事实对不上的九种 ----
    "上中上": ("长期档同样在上沿",
              "结论说的是「只有短期到上沿, 大级别还早」, 但这一格的长期档就在上沿 ——"
              " 半年尺度本来就在高位, 这一冲是趋势中继的再加速。"),
    "上下中": ("中期还在下沿",
              "结论说的是「大级别还早」, 但这一格的中期档在下沿 —— 20 日线刚拉起来"
              "而 60 日线远在价格之上, 这更像下跌途中的反抽而不是趋势票沿上轨走。"),
    "上下上": ("中期在下沿、长期在上沿",
              "三档互相矛盾的一格(60 日线最高)。结论按「只有短期到上沿」处理, "
              "但这一格既不是常态的趋势中继, 也不是干净的反抽。"),
    "中上下": ("长期还在下沿",
              "结论说的是「高位回落」, 但这一格的长期档在下沿 —— 它根本不在高位, "
              "是深跌之后的反弹走到季度阻力就停住了。"),
    "中下上": ("长期仍在上沿",
              "同为「候选池」, 但这一格的长期档还在上沿 —— 价格仍远高于半年均线而"
              "季度这一档已经调到位, 比普通候选池更值得盯。"),
    "下上中": ("中期还在上沿",
              "结论说的是「常规回调」, 但这一格的中期档在上沿 —— 从季度高位一口气"
              "蹲到短期下轨, 一点也不常规。是洗盘还是变盘, 这一天分不出来。"),
    "下上下": ("中期在上沿、长期在下沿",
              "三档互相矛盾的一格。结论按「只有短期到下沿」处理, 但中期还在上沿, "
              "这是急跌而非常规回调。"),
    "下中下": ("长期档同样在下沿",
              "结论说的是「趋势没坏就是低吸候选」, 但这一格的长期档在下沿 —— "
              "半年尺度本来就在低位, 趋势可能本来就不在。"),
    "上上下": ("短中到上沿而长期在下沿",
              "底层已判「超跌反弹」, 方向是对的; 补一句量级: 短中两档都到了上沿, "
              "这是反弹里比较猛的一种, 也因此更容易被读成突破。"),
}

# 底层结论说得已经很准、不需要补充的那些 —— 列出来是为了让"没有注记"这件事
# 是**明确的结论**而不是"忘了写"。
COMBO_CLEAN = frozenset({
    "上上上", "上上中", "上中下", "上中中", "上下下",
    "中上上", "中上中", "中中中", "中下中", "中下下",
    "下上上", "下中上", "下下上", "下中中", "下下中", "下下下",
})


def combo_note(bands: dict | None) -> dict | None:
    """这一格组合需不需要补一句。**不改底层结论, 只在旁边加注。**

    返回 {combo, title, detail} 或 None(底层说准了, 不必多话)。
    """
    code = combo_code(bands)
    if not code:
        return None
    got = COMBO_NOTES.get(code)
    if not got:
        return None
    return {"combo": code, "title": got[0], "detail": got[1]}


# ================================================================
# [R197] O 的时间积分 与 频段能量分布
#
# 这两样是把前面两条"只写在文档里"的推导真正算出来。

# 平均压缩度的回看窗口。取 60 —— 与中期档同一个尺度, 问的是"一个季度里
# 三个尺度平均有多一致"。
COMPRESS_WINDOW = 60


def compress_avg(rows: list[dict], window: int = COMPRESS_WINDOW) -> float | None:
    """**O 的时间积分**(除以窗口长度) = 这段时间的平均压缩度。

    与 `runs().compress_days` 量的不是同一件事, 两个都要:

        compress_days  今天往回**连续**粘合了几天 —— 会被中间一天的脱开清零
        compress_avg   这一段里**平均**有多粘 —— 中间脱开几天只是把均值拉低一点

    一只票可以 compress_days=0(昨天刚脱开)而 compress_avg=0.9(整个季度几乎都
    粘着), 那是"刚刚启动"; 也可以 compress_days=15 而 compress_avg=0.3, 那是
    "反复脱开又粘回来"。两个数分开看才知道是哪一种。

    单时点上三条带是**区间**, 交集是长度; 一段时间上它们扫出的是带状区域,
    交集的**面积 ÷ 窗口长度**就是这个均值 —— 用户问的"重叠面积"落到实处就是它。
    """
    vals = [r["o"] for r in (rows or [])[-window:] if r and r.get("o") is not None]
    if not vals:
        return None
    return sum(vals) / len(vals)


# 频段能量的回看窗口。要够长才能让 RMS 稳定, 又不能长到跨越两个 regime。
ENERGY_WINDOW = 60

# 纯趋势下三个带通的**期望幅度之比** = 各自覆盖的天数 (9.5 : 20 : 30)。
# 这是基线, 不是结论 —— 见 band_energy 的 docstring。
ENERGY_REF = (SPAN1, SPAN2, SPAN3)


def band_energy(closes: list[float] | None, atrs: list[float] | None,
                window: int = ENERGY_WINDOW) -> dict | None:
    """**频段能量分布** —— 这只票现在的波动主要来自哪个周期。

    三档通道本质上是一组带通滤波器(均线是线性相位 FIR, 相邻两档之差就是带通):

        C − MA20     周期 < 20 天    高频(消息、跳空、日内情绪)
        MA20 − MA60  周期 20~60 天   中频(一波行情的主体)
        MA60 − MA120 周期 60~120 天  低频(趋势/阶段)

    **必须扣掉趋势基线, 否则这个指标恒定说"低频占优"。** 匀速趋势下三者的
    幅度天然正比于各自覆盖的天数(9.5 : 20 : 30), 直接算占比会永远得到
    0.16 : 0.34 : 0.50 —— 那是均线的定义, 不是这只票的特征。所以先各自除以
    ENERGY_REF 再归一化: **纯趋势下三份恰好都是 1/3**, 偏离 1/3 的部分才是信息。

      短频 > 1/3   噪声/冲击成分超出趋势能解释的范围 —— 这一波是消息驱动
      中频 > 1/3   一个月到一个季度这一段的动能最足 —— 典型的主升段
      低频 > 1/3   近期反而平静, 能量都在老趋势里 —— 动能在衰减

    返回 {share: {s,m,l}, dominant, dominant_cn, rms: {...}}。
    """
    cs = [_f(c) for c in (closes or [])]
    as_ = [_f(a) for a in (atrs or [])]
    n = len(cs)
    if n < WINDOW["l"] + 5 or len(as_) != n or any(c is None for c in cs):
        return None
    vals: list[float] = [c for c in cs]  # type: ignore[misc]
    ma = {k_: _rolling_mean(vals, WINDOW[k_]) for k_ in ("s", "m", "l")}

    acc = {"s": [], "m": [], "l": []}
    for i in range(max(0, n - window), n):
        a = as_[i]
        m_s, m_m, m_l = ma["s"][i], ma["m"][i], ma["l"][i]
        if a is None or a <= 0 or None in (m_s, m_m, m_l):
            continue
        acc["s"].append(abs(vals[i] - m_s) / a)     # 高通
        acc["m"].append(abs(m_s - m_m) / a)         # 带通 20~60
        acc["l"].append(abs(m_m - m_l) / a)         # 带通 60~120
    if len(acc["s"]) < 10:
        return None

    def rms(xs: list[float]) -> float:
        return (sum(x * x for x in xs) / len(xs)) ** 0.5

    raw = {k_: rms(v) for k_, v in acc.items()}
    # 扣掉趋势基线 —— 这一步是整个指标成立的前提
    norm = {k_: raw[k_] / ref for k_, ref in zip(("s", "m", "l"), ENERGY_REF)}
    tot = sum(norm.values())
    if tot <= 0:
        return None
    share = {k_: v / tot for k_, v in norm.items()}
    dom = max(share, key=lambda k_: share[k_])
    return {
        "share": {k_: round(v, 3) for k_, v in share.items()},
        "rms": {k_: round(v, 3) for k_, v in raw.items()},
        "dominant": dom,
        "dominant_cn": {"s": "高频(消息驱动)", "m": "中频(行情主体)",
                        "l": "低频(老趋势)"}[dom],
    }
