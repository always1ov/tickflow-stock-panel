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


# [R203] 匀速基准 —— 这一层推导早就写在模块头里, 却从来没算出来过。
#
# 匀速上涨时 d_n ∝ (n−1)/2, 于是有一条**精确**的参照线:
#
#     d短 : d中 : d长  =  9.5 : 29.5 : 59.5  =  1 : 3.105 : 6.263
#
# 偏离这条线的部分就是加速度的**比值形式**。它与打分用的差值形式
# (a1 = v1 − v2) 是同一件事的两种写法, 但比值这一版**在界面上好讲得多**:
#
#     「短期偏离 1.2 倍日常波动, 按匀速中期该到 3.7, 实际只有 2.1
#       —— 中期跟不上, 这波在减速」
#
# 这句话是可以自己核对的, 而 a1 = −0.08 不是。所以打分照旧走差值(比值在
# d短 跨零时会翻转解释), 界面这一层走比值。
#
# 用 d 而不是 pct: 两者只差一个线性映射, 但 d 三档同尺, 比值才有意义。
_BASE_TOL = 0.15          # 实际 / 应该 落在 ±15% 内算"跟得上"
_BASE_MIN_D = 0.30        # |d短| 小于这个数时比值会炸, 不给结论


def baseline(d: dict[str, float] | None) -> dict | None:
    """匀速基准对照。返回 None 表示"这只票现在问不出这个问题"。

    短期偏离太小时(价格就贴在短期中线上)比值的分母趋近 0, 任何比值都没有
    意义 —— 那时不给结论, 而不是给一个看着像真的假数。
    """
    if not d or any(k_ not in d for k_ in ("s", "m", "l")):
        return None
    ds = float(d["s"])
    if abs(ds) < _BASE_MIN_D:
        return None
    exp_m, exp_l = ds * STEADY_RATIO_MID, ds * STEADY_RATIO_LONG
    act_m, act_l = float(d["m"]), float(d["l"])
    # 比值按**符号方向**读: 上涨途中 ds > 0, 实际小于应该 = 中期跟不上 = 减速。
    # ds < 0(下跌途中)时方向整个翻过来, 所以统一除以 exp 再看大小。
    ratio = act_m / exp_m if exp_m else None
    if ratio is None:
        return None
    if ratio > 1 + _BASE_TOL:
        level, cn = "lag", "跟不上"
        why = "中期比匀速该有的位置还远 —— 这一段是慢慢走上来的, 近期反而在收劲"
    elif ratio < 1 - _BASE_TOL:
        level, cn = "lead", "冲在前面"
        why = "短期已经甩开中期该有的位置 —— 最近这一段明显比之前快"
    else:
        level, cn = "onpace", "跟得上"
        why = "短、中期的位置正好落在匀速那条线上 —— 速度没变"
    return {
        "expect_m": round(exp_m, 2), "expect_l": round(exp_l, 2),
        "actual_m": round(act_m, 2), "actual_l": round(act_l, 2),
        "ratio": round(ratio, 2), "level": level, "level_cn": cn, "why": why,
    }


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
        # [R203] 匀速基准对照 —— 加速度的比值形式, 界面上好讲、可自己核对
        "baseline": baseline(d),
        "spread": round(spread, 3),
        "torn": abs(spread) >= TORN_ATR,
        "nested": abs(spread) <= NESTED_ATR,
        "stack": _stack(ma_s, ma_m, ma_l),
        "combo": combo_code(bands),
    }


def explain(g: dict | None, runs: dict | None = None,
            energy: dict | None = None) -> list[dict]:
    """把几何量翻成**一行一条**的读数: 名称 · 数值 · 这个数意味着什么。

    返回 [{label, value, why}, ...]。

    ## [R212] 为什么是这个形状

    这一块改过三版, 每一版都错在同一个地方的不同侧面:

      v1  只给数字(`+1.4` `-1.3` `10%` `中下中`)。用户: 「用数字看不懂」——
          对的: 要先知道"多少算大"才读得出好坏, 而那正是不该逼人记的东西。
      v2  只给状态词(`比之前快` `走到中段` `完全分开`)。用户: 「仍旧看不懂,
          获取不到结论性信息」—— 也对: 「走到中段」**然后呢**? 状态词还是状态,
          该做的那步合成仍然留给了用户。
      v3  用户自己给了答案: 「你干脆保持数据, 然后在后面加一行解释」。

    所以三样一起给, 缺一不可:
        **数值**  能核对(这是它区别于一句空话的地方)
        **名称**  知道这个数在说什么
        **解释**  这个数**意味着什么** —— 「所以呢」的那一半

    格子放不下第三样, 所以这一块不再是格子墙, 是一张三列的表。

    ## 边界

    **只描述, 不下买卖判断** —— 同一个"走得越来越快"在趋势初期是启动、在末端
    是赶顶, 那是「怎么办」那一层的事。这里的"意味着什么"说的是**这个数本身在
    说什么**, 不是"你今天该不该动手"。

    用词照旧守 R200 两条: 不用行话; 不说出指标本名与参数(单位写「倍日常波动」)。
    """
    if not g:
        return []
    out: list[dict] = []
    r = runs or {}

    def add(label, value, why):
        out.append({"label": label, "value": value, "why": why})

    # ---- 快慢 ----
    ac = g.get("accel") or {}
    lvl, gain = ac.get("level"), ac.get("gain_atr")
    if gain is not None:
        val = f"{'+' if gain >= 0 else '−'}{abs(gain):.1f} 倍波动"
        if lvl == ACCEL_UP:
            add("最近快慢", val,
                f"这十天比前一段多走了 {abs(gain):.1f} 倍日常波动 —— 还在加力。"
                "但不是越大越好: 冲得太猛往往出现在一波的末尾, 不是起点")
        elif lvl == ACCEL_DOWN:
            add("最近快慢", val,
                f"这十天比前一段少走了 {abs(gain):.1f} 倍日常波动 —— 推力在退。"
                "趋势本身还没坏, 但该开始想「什么情况下我就走」")
        else:
            add("最近快慢", val,
                "这十天和之前那一段走得一样快 —— 没有新的力量进来, 也没有在退。"
                "单看这一条不构成任何理由")

    # ---- 三线间距 ----
    sp = g.get("spread")
    if sp is not None:
        up = sp >= 0
        who = "短线高出长线" if up else "短线低于长线"
        val = f"{sp:+.1f} 倍波动"
        a = abs(sp)
        if a >= TORN_ATR:
            add("三线间距", val,
                f"{who} {a:.1f} 倍日常波动 —— 差到这个程度, 短线看和长线看已经"
                "没有一个共同认可的合理价了。"
                + ("这个位置再追进去性价比很低" if up else
                   "跌到这个程度往往还要磨一段, 别急着抄"))
        elif a >= SPREAD_MATURE:
            add("三线间距", val,
                f"{who} {a:.1f} 倍日常波动 —— 这一段已经走了很长。"
                + ("再追的性价比在下降" if up else "反弹起来会比较猛, 但那多半只是反弹"))
        elif a >= SPREAD_LAUNCH:
            add("三线间距", val,
                f"{who} {a:.1f} 倍日常波动 —— 方向已经立住了, 这一段是行情的主体")
        else:
            add("三线间距", val,
                f"{who}才 {a:.1f} 倍日常波动 —— 两边贴得很近, **方向还没真正出来**。"
                "这时候猜方向没有胜算")

    # ---- 三种看法还剩多少重合 ----
    o = g.get("compress")
    if o is not None:
        lv = g.get("compress_level")
        add("三种看法", f"还重合 {o:.0%}",
            "短、中、长三种看法认的价几乎完全重合 —— **没有分歧就没有趋势**, "
            "现在是横盘状态" if lv == "tight" else
            "三种看法认的价已经基本不重合 —— 分歧就是趋势, 方向是明确的" if lv == "loose" else
            "三种看法还有一部分重合 —— 方向在出来的路上, 但还不算立住")

    # ---- 挤了几天 + 这季平均: 两个数必须一起解释 ----
    cd, avg = r.get("compress_days"), r.get("compress_avg")
    if cd is not None:
        add("连着挤了", f"{cd} 天",
            f"到今天为止连着 {cd} 天三种看法都认同一个价 —— 憋得越久, "
            "走出来那一下通常越干脆" if cd else
            "今天三种看法并不一致 —— 不在憋着劲的状态里")
    if avg is not None:
        both = f"(连着 {cd} 天)" if cd is not None else ""
        add("这季平均", f"重合 {avg:.0%}",
            f"这个季度平均有 {avg:.0%} 的时候三种看法是一致的。" + (
                f"而现在连着的天数是 0{both} —— **刚刚才走出来**, 这是最值得盯的一种"
                if avg >= 0.6 and not cd else
                f"现在也正挤着{both} —— 长期横盘, 在等一个方向"
                if avg >= 0.6 else
                f"现在却正挤着{both} —— 反复散开又挤回去, 别把它当成蓄势"
                if cd else
                "多数时候是分开的 —— 这只票一直在走趋势, 不是横盘股"))

    # ---- 波动主要来自哪 ----
    if energy and energy.get("dominant"):
        dom = energy["dominant"]
        add("波动来自", energy.get("dominant_cn") or "",
            "主要是几天里的短促跳动 —— 更像消息和情绪在推, 趋势本身的力量不强。"
            "这种来得快去得也快" if dom == "s" else
            "主要来自一波行情的主体 —— 正走在主升段上, 这是趋势最扎实的一段"
            if dom == "m" else
            "主要来自更早就在的老趋势 —— 劲都在过去, 近期反而平静, 动能在衰减")

    # ---- 三档各自在哪 ----
    combo = g.get("combo")
    if combo and len(combo) == 3:
        at = [f"{t}到{v}沿" for t, v in zip(("短期", "中期", "长期"), combo) if v != "中"]
        add("三档位置", combo,
            "三档都在自己通道的中部 —— 位置上没有可说的, 该听趋势和信号的"
            if not at else
            "、".join(at) + " —— " + (
                "三档同向, 三种尺度看法一致 —— 这种最扎实"
                if len(set(combo)) == 1 else
                "三档并不同步, 短期的动作还没被中长期确认"))
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
    EV_TREND_ACCEL: "趋势中提速",
    EV_MAIN_ADVANCE: "主升浪特征",
    EV_EXHAUSTING: "涨势没劲",
    EV_BOUNCE_CAP: "反弹遇阻",
    EV_PULLBACK_END: "回撤结束",
    EV_BREAKDOWN_TRY: "破位第一天",
    EV_BREAKDOWN_HOLD: "破位站稳",
    EV_SHAKEOUT: "强势甩人",
    EV_COILING: "憋着劲",
    EV_NONE: "没什么事",
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

    # ---- 在短期上沿之外 ----
    if up >= 1:
        if not bull:
            return mk(EV_BOUNCE_CAP,
                      f"趋势本身是往下的({state}), 这次冲到上沿只是反弹撞到头 —— 不是突破",
                      False)
        if state == "UT":
            m = MAIN_ADVANCE
            if (g.get("stack") == m["stack"]
                    and (g.get("spread") or 0) >= m["min_spread"]
                    and up >= m["min_above_run"]
                    and (a1 is not None and a1 >= m["min_a1"])):
                return mk(EV_MAIN_ADVANCE,
                          f"正在上涨 + 三条线朝上排好 + 首尾已经差了 {g.get('spread'):.1f} 倍日常波动"
                          f" + 连着 {up} 天站在上沿之外 + 没有变慢 —— 五个条件全中",
                          True)
            if up >= EXHAUST_RUN and a1 is not None and a1 < -ACCEL_FLAT:
                return mk(EV_EXHAUSTING,
                          f"已经连着 {up} 天在上沿之外, 可是最近走得比前一段慢了 —— 涨势在没劲",
                          True)
            return mk(EV_TREND_ACCEL,
                      "上涨趋势已经确认, 冲出上沿是趋势里的正常提速 —— 沿着上沿走是常态, "
                      "不必因为「到高位了」就减",
                      up >= CONFIRM_DAYS)
        # NR/SR: 回升途中冲出上沿 —— 这才是真正意义上的"突破"
        if up >= CONFIRM_DAYS:
            return mk(EV_BREAKOUT_HOLD,
                      f"回升途中冲出上沿, 而且连着守住了 {up} 天 —— 站稳了",
                      True)
        return mk(EV_BREAKOUT_TRY,
                  "回升途中第一天冲出上沿 —— 只是刚冲出去, 收盘守不住就是假的",
                  False)

    # ---- 在短期下沿之外 ----
    if dn >= 1:
        if bull:
            return mk(EV_SHAKEOUT,
                      f"趋势还是往上的({state}), 跌破下沿更像是甩人下车 —— 关键看长期那条还在不在上边",
                      dn >= CONFIRM_DAYS)
        if dn >= CONFIRM_DAYS:
            return mk(EV_BREAKDOWN_HOLD, f"往下的趋势里连着 {dn} 天掉在下沿之外 —— 是真跌破了", True)
        return mk(EV_BREAKDOWN_TRY, "第一天掉到下沿之外 —— 还不算数, 明天才知道", False)

    # ---- 没到沿: 回撤刚结束 / 挤在一起 ----
    if state in ("NREA", "SREA") and duration == 1:
        return mk(EV_PULLBACK_END, "今天刚从回撤里转出来 —— 回到强势那一边的第一天", False)
    if cd >= CONFIRM_DAYS and (g.get("compress") or 0) >= COMPRESS_TIGHT:
        return mk(EV_COILING,
                  f"三条线挤在一起已经 {cd} 天(短、中、长认的是同一个价) —— 憋着劲, 方向还没出来",
                  False)
    return mk(EV_NONE, "既没碰到上下沿, 三条线也没挤在一起", False)


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
              "结论说的是「大级别还早」, 但这一格的中期档在下沿 —— 短线刚拉起来而"
              "中线还远远压在价格上方, 这更像下跌途中的反抽, 不是趋势票沿着上沿走。"),
    "上下上": ("中期在下沿、长期在上沿",
              "三档互相打架的一格(中线的位置最高)。结论按「只有短期到上沿」处理, "
              "但这一格既不是常见的趋势中继, 也不是干净的反抽。"),
    "中上下": ("长期还在下沿",
              "结论说的是「高位回落」, 但这一格的长期档在下沿 —— 它根本不在高位, "
              "是深跌之后的反弹走到季度阻力就停住了。"),
    "中下上": ("长期仍在上沿",
              "同为「候选池」, 但这一格的长期档还在上沿 —— 长线看价格还高高在上, 中线"
              "这一档却已经调到位了, 比普通候选池更值得盯。"),
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
        # [R211] R200 那轮改大白话时漏了这里 —— 它是后端直接送到界面上的
        # 一个词, 不在任何被扫描的文件里。「高频/中频/低频」正是那轮要清掉的行话。
        "dominant_cn": {"s": "几天的短波动", "m": "一波行情的主体",
                        "l": "长期老趋势"}[dom],
    }


# ================================================================
# [R199] 阶段判定 —— 把几何量变成"现在处在哪一段"
#
# 用户: 「通道结论这部分也思考一下, 如何排版和内容的显示才能更有价值,
#        而不是展示单纯的数据, 对我有指导性意义」。
#
# 压缩度、分离度、加速度**单看每一个都答不了"我该怎么办"**: 压缩 0.9 是好是坏?
# 分离度 2.4 呢? 要三个一起读才有意义 —— 而"一起读"这件事恰恰是可以算的。
#
# 一条趋势的生命周期在这三个量上有固定的次序:
#
#     粘合(压缩高) → 脱开(压缩掉) → 分离扩大 → 分离到头 → 再粘合
#     加速度:  ≈0        转正         正         转负
#
# 所以三个量的**组合**就是阶段坐标。这一层只回答"在哪一段", 不回答"买不买" ——
# 后者要配上六态方向与把握分, 那是别人的活。

PH_COILING = "coiling"          # 蓄势待变
PH_LAUNCHING = "launching"      # 启动初期
PH_ADVANCING = "advancing"      # 趋势推进
PH_STALLING = "stalling"        # 末段钝化
PH_OVEREXTENDED = "overextended"  # 极端拉伸
PH_DECLINING = "declining"      # 下行途中
PH_UNCLEAR = "unclear"          # 说不清

# [R207] 阶段名。用户: 「一路往下走、间距 -1.7 匀速 这类描述太含糊」。
#
# 原来那批名字(「一路往上走」「走得过头了」)是大白话没错, 但**没说清是什么在走、
# 往哪走**。在一张几十行的表里, 「一路往下走」既可能被读成"这只票在跌", 也可能
# 被读成"某个指标在降"。改成带方向的短判断: 上升中 / 下跌中 / 涨过头 / 跌过头。
#
# **「走得过头了」还藏着一个真错误**: 它由 |间距| ≥ 5 触发, 所以一只**深跌**
# 的票也会落到这一档, 却配着「追进去的性价比很低」这种只对涨过头成立的话。
# 现在按 spread 的符号分成两档, 文案各说各的。
PHASE_CN = {
    PH_COILING: "横盘中", PH_LAUNCHING: "刚启动",
    PH_ADVANCING: "上升中", PH_STALLING: "涨势转弱",
    PH_OVEREXTENDED: "走过头", PH_DECLINING: "下跌中",
    PH_UNCLEAR: "看不出",
}
# 走过头的两个方向 —— 同一个 code, 两套说法
PHASE_OVEREXTENDED_CN = {"up": "涨过头", "down": "跌过头"}
# [R215] 均线结构还朝上, 但价格已经跌到三条线之下 —— 同一个 code, 另一套说法。
# 用户: 「下跌中贴下轨的怎么会是涨势转弱, 正常吗」。不正常, 见 phase() 的注释。
PHASE_STALLING_DONE_CN = "涨势已走完"

# 分离度的两个刻度: 越过 LAUNCH 算真的脱开了, 越过 MATURE 算走了一大段。
# 与 opportunity_score 的 SPREAD_CURVE 甜区(1.5~3)对齐, 不另立一套。
SPREAD_LAUNCH = 1.0
SPREAD_MATURE = 3.0


def phase(geo: dict | None, runs: dict | None = None) -> dict | None:
    """三个几何量 → 阶段 + 一句该注意什么。纯函数。

    返回 {code, cn, why, watch}。`watch` 是"这一段该盯什么", 不是买卖指令 ——
    同一个阶段对持仓和对空仓要做的事不同, 那要配上仓位才说得了。
    """
    if not geo:
        return None
    sp = geo.get("spread")
    a1 = (geo.get("accel") or {}).get("a1")
    o = geo.get("compress")
    cd = (runs or {}).get("compress_days") or 0
    if sp is None:
        return None
    up = a1 is not None and a1 > ACCEL_FLAT
    down = a1 is not None and a1 < -ACCEL_FLAT

    # [R209] 除了阶段名, 再给两个**不带数字**的读数: 走到哪一步了、还有没有劲。
    #
    # 用户: 「通道态势这一列得重新做, 看不懂这样的表述」。上一版那一列摆的是
    # 「短线低 1.7 倍波动 / 速度没变」—— **那还是测量值**, 而且「倍日常波动」
    # 这个单位再准确, 扫表的人也换算不出它意味着什么。
    #
    # 换成两个人话档位: 三线间距落在哪一档(刚起步/走到中段/走了很长/走过头),
    # 快慢落在哪一档(还在加速/速度平稳/正在放慢)。**数字全部退到悬停**。
    # 门槛直接用打分那一层已经在用的 SPREAD_LAUNCH / SPREAD_MATURE / TORN_ATR,
    # 不另编一套 —— 界面上说「走了很长」的那一刻, 打分那边也正好在扣分。
    def _maturity() -> str:
        a = abs(sp)
        if a >= TORN_ATR:
            return "走过头了"
        if a >= SPREAD_MATURE:
            return "走了很长"
        if a >= SPREAD_LAUNCH:
            return "走到中段"
        return "刚起步"

    def _pace() -> str:
        if up:
            return "还在加速"
        if down:
            return "正在放慢"
        return "速度平稳"

    def mk(code, why, watch, cn=None):
        return {"code": code, "cn": cn or PHASE_CN[code], "why": why, "watch": watch,
                "maturity_cn": _maturity(), "pace_cn": _pace()}

    # ---------------------------------------------------------------- [R215]
    #
    # 用户: 「下跌中贴下轨的怎么会是涨势转弱, 正常吗」——(截图: 下跌趋势 7 天 /
    # 涨势转弱·走到中段 / 正在放慢)。**不正常。** 穷举之后是三类毛病, 同一个根:
    #
    #     这个函数只读了 spread(短线中枢 vs 长线中枢)和快慢, 措辞却在替
    #     **另外两件它压根没看的事**打包票 —— 三条线是不是真排成了一列,
    #     以及**价格现在在哪儿**。
    #
    # ① 「涨势转弱」说的是"有一段涨势, 正在转弱"。而用户那只票的价格早就跌到
    #    三条线之下、六态也已经空了 7 天 —— 转弱这件事**已经完成了**, 现在是
    #    "涨完了在跌"。只看中枢间距看不出来, 因为中枢是滞后的: 均线还没交叉,
    #    价格已经走完了。→ 价格在三条线之下时换一套说法(「涨势已走完」)。
    # ② 「三条线稳稳朝上散开」/「三条线朝下散开」—— spread 只比了短和长两条,
    #    **中线在哪儿它没看过**。中线没排在中间时这句话就是假的。穷举里
    #    644 例。→ 排列不干净就不许说"散开", 改说实话。
    # ③ 「刚启动」和「看不出」两个阶段**一次都出不来**: `NESTED_ATR` 恰好
    #    等于 `SPREAD_LAUNCH`(都是 1.0), 于是"挤在一起"那一档把"刚走出来"
    #    该占的区间整个吃掉了。这跟 R210 的路 C、R214 的规则② 是同一种病 ——
    #    写在那儿、看着像在用、其实永远走不到。而 `today.py` 的
    #    `_COILING_PHASES` 里正列着 launching, 等于候选路 C 又瘸了一半。
    #    → 不动任何阈值(SPREAD_LAUNCH 与打分层共用, 一动就改口径), 改成在
    #      "挤在一起"这一档**里面**再按重合度与快慢分一层: 还高度重合 = 横盘中;
    #      重合已经松开且在加速 = 刚启动; 松开却在减速 = 看不出(多半要缩回去)。
    #
    # 三条都只改**措辞与分档**, 一个阈值都没动, 打分口径零影响。
    d = geo.get("d") or {}
    _dv = [d.get(k_) for k_ in ("s", "m", "l")]
    below_all = all(v is not None and v < 0 for v in _dv)
    above_all = all(v is not None and v > 0 for v in _dv)
    stack = geo.get("stack")

    def _fan(bullish: bool) -> str:
        """「散开」这句话只有在三条线真排成一列时才能说。"""
        if bullish:
            return "三条线稳稳朝上散开" if stack == STACK_BULL else \
                "不过中线还没排到中间 —— 三条线还没理顺"
        return "三条线朝下散开" if stack == STACK_BEAR else \
            "不过中线还没排到中间 —— 三条线还没理顺"

    if geo.get("torn"):
        # [R207] 分方向。同一个 |间距| ≥ 5, 涨上去和跌下来该说的话完全相反 ——
        # 原来两种情况共用「追进去的性价比很低」, 对一只已经崩下去的票是错的。
        if sp > 0:
            return mk(PH_OVEREXTENDED,
                      f"短线已经高出长线 {sp:.1f} 倍日常波动 —— 涨得太远, "
                      f"短线看和长线看已经没有一个共同认可的合理价",
                      "这个位置再争论「贵不贵」没有意义 —— 按短线看是贵, 按长线看还没到。"
                      "先想清楚你做的是哪一段; 现在追进去性价比很低",
                      cn=PHASE_OVEREXTENDED_CN["up"])
        return mk(PH_OVEREXTENDED,
                  f"短线已经低于长线 {abs(sp):.1f} 倍日常波动 —— 跌得太深, "
                  f"短线看和长线看已经没有一个共同认可的合理价",
                  "别急着抄 —— 跌到这个程度往往还要磨一段。等三条线重新靠拢、"
                  "或者短线先站回长线上方, 再谈买点",
                  cn=PHASE_OVEREXTENDED_CN["down"])
    if sp <= -SPREAD_LAUNCH:
        # [R215] ② 排列不干净就不说"散开"; ③ 价格已经翻回三条线之上时说清楚
        #        这是跌势里的反弹 —— 与作者 verdict 的「超跌反弹」同一件事。
        return mk(PH_DECLINING,
                  f"短线低于长线 {abs(sp):.1f} 倍日常波动, {_fan(False)} —— 方向朝下"
                  + ("。不过眼下价格已经翻到三条线之上 —— 这是跌势里的反弹, 不是转势"
                     if above_all else ""),
                  "别用「跌到下边那条线就该反弹」去抄底 —— 往下走的时候, 那条线也在跟着往下挪")
    if geo.get("nested") or (o is not None and o >= COMPRESS_TIGHT):
        # [R215] ③ 「挤在一起」这一档里面再分一层。原来它整档吞掉,
        #        「刚启动」「看不出」两个阶段一次都出不来。
        #        分层只用现成的重合度门槛与快慢档, 不新立阈值。
        tight = o is None or o >= COMPRESS_TIGHT
        extra = f", 已经这样 {cd} 天" if cd else ""
        if tight:
            return mk(PH_COILING,
                      f"短线和长线只差 {abs(sp):.1f} 倍日常波动, 挤在一起{extra} —— "
                      f"短、中、长三种看法几乎认同一个价, 方向还没出来",
                      "盯着它往哪边先走出去。这种挤在一起的状态通常不会持续太久, "
                      "但在走出去之前猜方向没有胜算")
        if up:
            return mk(PH_LAUNCHING,
                      f"三种看法开始不重合了, 短线{'高出' if sp >= 0 else '低于'}长线 "
                      f"{abs(sp):.1f} 倍日常波动, 而且越走越快 —— 刚从横着的状态里走出来",
                      "刚分开的这一段最关键 —— 接着能不能继续走开, 决定了这次是真启动还是又缩回去")
        return mk(PH_UNCLEAR,
                  f"三种看法刚开始不重合, 短线{'高出' if sp >= 0 else '低于'}长线 "
                  f"{abs(sp):.1f} 倍日常波动, 但速度没跟上",
                  "分是分开了, 可是没有力气跟上, 这种最容易缩回去 —— 等它给个方向再说")
    if down:
        # [R215] ① 用户撞见的那一格。「涨势转弱」在说"有一段涨势, 正在转弱";
        #        可价格要是已经跌到三条线之下, 转弱这件事**已经完成了**。
        #        中枢是滞后的 —— 均线还没交叉, 价格早走完了。换一套说法。
        if below_all:
            return mk(PH_STALLING,
                      f"中枢还是短线高出长线 {abs(sp):.1f} 倍日常波动, "
                      f"但价格已经跌到三条线之下 —— 均线还没掉头, 价格先走完了",
                      "别把它当「还在涨、只是慢下来」—— 该问的已经不是加不加仓, "
                      "而是这一段还剩多少利润没落袋",
                      cn=PHASE_STALLING_DONE_CN)
        if sp >= SPREAD_MATURE:
            return mk(PH_STALLING,
                      f"短线已经高出长线 {sp:.1f} 倍日常波动, 而最近走得比之前慢了 —— 劲在往回收",
                      "趋势本身还没坏, 但推力在减弱。该开始想「什么情况下我就走」, 而不是再加")
        return mk(PH_STALLING,
                  f"短线{'高出' if sp >= 0 else '低于'}长线 {abs(sp):.1f} 倍日常波动, "
                  f"最近走得比之前慢了",
                  "力气在往回收, 这个时候别加仓")
    if below_all:
        # 中枢还在朝上散开, 价格却已经在三条线之下 —— 罕见, 但话得说对。
        return mk(PH_STALLING,
                  f"中枢还在往上散开(短线高出长线 {sp:.1f} 倍日常波动), "
                  f"可价格已经跌到三条线之下 —— 线还没反应过来",
                  "线好看是因为它慢。以价格为准, 别照着线加仓",
                  cn=PHASE_STALLING_DONE_CN)
    return mk(PH_ADVANCING,
              f"短线高出长线 {sp:.1f} 倍日常波动, {_fan(True)}"
              + (", 而且还在提速" if up else ", 速度平稳"),
              "这一段是行情的主体。真正要盯的是什么时候开始走慢 —— 那才是转折的先兆")


# ================================================================
# [R203] 27 种组合速查表 —— 「系统结论」与「几何含义」并排
#
# 用户: 「我要看到系统结论和几何含义、偏离基准加速度等等」。
#
# ## 为什么是**生成**的, 不是誊抄的
#
# 结论那一列直接调作者的 `keltner.verdict()` 拿, 传进去的是只带 `pos` 的
# 最小 bands。这样做的意义不只是省事:
#
#   · 誊抄一份 27 行的对照表, 底层哪天改了措辞, 这张表就开始说假话, 而且
#     **没有任何东西会报错** —— 那种漂移是最难发现的一类。
#   · 生成的表天然与底层同步。底层一个字没动(它是禁止动的), 这里只是读它。
#
# 「几何含义」那一列同样是**推出来的**: 由三档各自在上沿/中部/下沿这件事
# 直接构造, 不是每格手写一句。手写 27 句的问题和誊抄一样 —— 迟早对不上。
# 只有那 11 格底层说得不够贴切的, 才另外挂 COMBO_NOTES 的补充(见上)。
#
# ## 用词
#
# 守 R200 那两条: 不用行话(高频/中频/低频、O、粘合), 不点破均线周期与倍数。
# 用户给的那张草表里写着「O=0」「MA120 ≫ C」「全频段过热」—— 那三样都不能
# 进界面: 前两个是公式, 第三个是行话。

_POS_CN = {"上": "上沿", "中": "中部", "下": "下沿"}
_SCALE_CN = ("短期", "中期", "长期")


def _combo_shape(code: str) -> str:
    """三档位置 → 一句「谁在哪」。纯描述, 不下判断。"""
    return "、".join(f"{s}在{_POS_CN[c]}" for s, c in zip(_SCALE_CN, code))


def _combo_read(code: str) -> str:
    """三档位置 → 一句「这意味着什么」。

    只有六种形态需要分别说, 其余按"谁和谁一致"归并 —— 归并是有依据的:
    三档共用同一把尺子, 所以真正的信息只在**它们一致不一致**上。
    """
    s, m, l = code
    if s == m == l == "上":
        return "三种看法同时说贵 —— 上面已经没有回旋余地, 这个位置买是在最贵的地方"
    if s == m == l == "下":
        return "三种看法同时说便宜 —— 可能是到底了, 也可能是还在跌, 光看位置分不出来"
    if s == m == l == "中":
        return "价格落在三条通道都认可的区间里 —— 这一格是真的没有信息, 该听趋势和信号的"
    if s == "上" and l == "下":
        return "短期最贵而长期最便宜 —— 是深跌之后的反弹, 不是趋势转好, 最容易被读成突破"
    if s == "下" and l == "上":
        return "短期最便宜而长期最贵 —— 上升途中的深蹲, 和真跌破长得像但大周期还站着"
    if s == "上" and m == "中" and l == "中":
        return "只有短期冲高, 中长期都没动 —— 多半是一次性冲击, 不是状态变了"
    if s == "下" and m == "中" and l == "中":
        return "只有短期回落, 中长期都没动 —— 常规回调, 大周期还没受影响"
    if s == "中" and m == "中":
        # l 必然不是「中」(三个都中已经在上面返回了)
        return (f"短期和中期都已经回到中部, 只有长期还在{_POS_CN[l]} —— "
                + ("大周期位置不低, 但一个月和一个季度都休整完了"
                   if l == "上" else "大周期跌了不少, 而中短期已经企稳"))
    if s == "上":
        return "短期已经到上沿, 中长期还没同时确认 —— 冲高成不成还要看后面跟不跟"
    if s == "下":
        return "短期已经到下沿, 中长期还没同时确认 —— 调到不到位还要看后面跟不跟"
    if m == l:
        return f"短期已经回到中部, 而中长期都在{_POS_CN[m]} —— 大周期的位置还在, 短期先休整完了"
    return "三档互相打架, 各说各的 —— 这种格子先别急着定性, 等它们对齐"


def combo_table() -> list[dict]:
    """27 种组合的完整速查表。纯函数, 无输入无取数, 结果可缓存。

    每行:
        combo        三字码, 如「上中下」
        shape        谁在哪(短期在上沿、中期在中部……)
        read         这意味着什么
        verdict      作者那一层的结论 {title, code, tone, action, detail} 或 None
        note         这一格底层说得不够贴切时的补充 {title, detail} 或 None
    """
    from app.indicators.keltner import POS_ABOVE, POS_BELOW, POS_INSIDE, verdict

    pos_map = {"上": POS_ABOVE, "中": POS_INSIDE, "下": POS_BELOW}
    out: list[dict] = []
    for s in "上中下":
        for m in "上中下":
            for l_ in "上中下":
                code = s + m + l_
                bands = {k_: {"pos": pos_map[c]}
                         for k_, c in zip(("s", "m", "l"), code)}
                v = verdict(bands)
                got = COMBO_NOTES.get(code)
                out.append({
                    "combo": code,
                    "shape": _combo_shape(code),
                    "read": _combo_read(code),
                    "verdict": (None if not v else
                                {"title": v["title"], "code": v["code"],
                                 "tone": v["tone"], "action": v["action"],
                                 "detail": v["detail"]}),
                    "note": (None if not got else {"title": got[0], "detail": got[1]}),
                })
    return out
