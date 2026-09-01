"""[fork 增强] R134 买入机会评分 v2 —— 三道硬门槛 + 三维度加权。

## 为什么重写

v1(R12 起累积到 R47)是"底分 + 八项加减"。它有三个结构性毛病, 用户在界面上
直接看得见:

  1. **分数饱和。** 理论上限 70+15+20+8+8+8+12+10 = 151, 夹到 100 ——
     榜首一片 100 分, 前几名之间没有任何区分度(用户截图里两只并列 100)。
  2. **因子全是单调的。** 量比越大越加、相对强度越强越加。可"量比 4.0"
     意味着这一波**已经发生**了, 那是追高不是苗头; 与用户要的
     "高概率的有苗头的东西"方向相反。
  3. **没有硬门槛。** 跌破生命线、长期下跌趋势的票, 只要别的因子够猛照样上榜
     (通道结论最多扣 15 分)。用户明确说这两种"不看"。

## v2 的结构

    第 0 层 门槛(硬否决, 不打分)   → 有没有资格被看
    第 1 层 三维度加权(0~100)      → 排第几
    第 2 层 注记(展示, 不参与打分) → 看到它时该知道些什么

**门槛**(全部纯价格, 无前视, 可回测):

  · G1 六态在多头侧(UT/NR/SR) —— 逆势票不该靠高分翻身进前排。
    对"逼近突破"那一路尤其关键: v1 里那条路**完全不检查趋势状态**。
  · G2 站上生命线(收盘 ≥ MA20, R9 口径), 且**连续两日**成立 ——
    单日判定会在 MA20 附近反复穿越时把同一只票每天踢进踢出。
  · G3 非长期下跌(不满足"收盘 < MA120 且 MA120 向下") ——
    位置 + 斜率两个条件同时成立才算长期下跌, 与 market_mode 判指数同源。
    只用位置的话, 一只刚从底部拉起、还没回到 MA120 上方的强势股会被误杀;
    只用斜率的话, 高位刚拐头的票会被漏掉。

三道门槛叠加等价于一句话: **只做上升趋势中继的早期, 不做底部反转。**
这是用户"跌破生命线的不看、长期是下跌趋势的也不看"的必然推论, 是一个
真实且持续存在的机会成本(底部反转第一波必然错过), 不是可以调参消除的。

**三维度**(权重见 WEIGHTS; 起始值是先验, 等 R133 台账攒够样本后按分层单调性调):

  | 维度     | 权重 | 因子                                   |
  |----------|------|----------------------------------------|
  | 趋势强度 | 45%  | 新鲜度(主导) / 六态状态 / 相对强度     |
  | 量能确认 | 30%  | 量比(主导) / 换手率                     |
  | 位置成本 | 25%  | Keltner 短期通道位置                    |

**三条曲线全是区间最优(倒 U), 不是单调递增** —— 这是"高概率有苗头"这句话
唯一自洽的数学形式:
  · 量比 > 4 不是苗头, 是已经发生了;
  · 通道位置 → 1.0 是贴上轨, 那是追高;
  · 相对强度过于靠前, 往往意味着已经涨了一大段。

## 一个必须写清楚的等价关系

Keltner 短期带以 MA20 为中轴, 所以 **收盘 ≥ MA20 ⟺ pct_in_channel ≥ 0.5**
(恒等, 不是近似)。因此过了 G2 之后, 位置因子的实际取值域只有 [0.5, 1.0+],
有效分辨率是名义的一半 —— 位置维度 25% 的**名义权重**买到的**实际区分度**
低于 25%。这不是 bug(门槛是刻意设的), 但意味着 WEIGHTS 里的数字是"声明权重"
而非"有效权重", 最终要靠台账的分层单调性来定, 不能靠拍脑袋。

## 缺数据怎么办

某个因子取不到时**在维度内按剩余权重重新归一化**, 而不是记 0 分 ——
记 0 等于因为"我们没读到换手率"去惩罚这只票。整个维度都缺时, 在维度之间
再归一化一次, 并把 `partial` 标出来, 让界面能如实说"这一档没算进去"。
"""
from __future__ import annotations

from app.indicators.livermore import BULLISH   # 多头三态 UT/NR/SR, 只引用不做副本

# --------------------------------------------------------------- 门槛

GATE_TREND = "trend_side"        # 六态必须在多头侧
GATE_LIFELINE = "lifeline"       # 收盘必须站上生命线(MA20), 连续两日
GATE_LONG_DOWN = "long_down"     # 不能处在长期下跌趋势里

GATE_CN = {
    GATE_TREND: "逆势(六态在空头侧)",
    GATE_LIFELINE: "跌破生命线(MA20)",
    GATE_LONG_DOWN: "长期下跌趋势",
}
GATE_WHY = {
    GATE_TREND: "六态在空头侧 —— 逆势的「突破」多半是反弹",
    GATE_LIFELINE: "收盘在 MA20 之下 —— 生命线都没站上, 谈不上趋势中继",
    GATE_LONG_DOWN: "收盘在 MA120 之下且 MA120 向下 —— 长期方向还没转",
}


def check_gates(*, state: str | None, above_ma20: bool | None,
                above_ma20_prev: bool | None, close: float | None,
                ma120: float | None, ma120_rising: bool | None) -> dict:
    """三道硬门槛。返回 {"ok": bool, "failed": [code...]}。纯函数。

    **数据缺失一律放行**, 不当作不通过 —— 门槛的职责是"挡掉明确不该看的",
    不是"挡掉我们没读到的"。新股不足 120 根算不出 MA120, 不该因此被判长期下跌。
    宁可让一只该挡的漏过去(后面还有分数和注记), 也不能让一只好票因为
    一次读取失败而凭空消失, 那种消失用户永远查不出来。
    """
    failed: list[str] = []
    if state is not None and state not in BULLISH:
        failed.append(GATE_TREND)
    # 连续两日: 今天必须站上; 昨天取不到时只按今天判(不因缺一天数据就否决)
    if above_ma20 is False or (above_ma20 is True and above_ma20_prev is False):
        failed.append(GATE_LIFELINE)
    if (close is not None and ma120 is not None
            and ma120_rising is False and close < ma120):
        failed.append(GATE_LONG_DOWN)
    return {"ok": not failed, "failed": failed}


# --------------------------------------------------------------- 归一化曲线
#
# 全部写成分段线性的控制点, 而不是一堆 if/elif 阈值。理由有二:
#   1. 阈值式打分在边界上是阶跃的 —— 量比 1.49 和 1.51 差 8 分, 名次天天翻,
#      而这两个数在盘面上没有任何区别;
#   2. 控制点形式的曲线只有几个自由度, 台账回来之后调的是"峰值在哪、多宽",
#      不是逐档拧数字 —— 自由度少, 过拟合的空间就小(CONTRIBUTING R5)。

Curve = tuple[tuple[float, float], ...]


def _piecewise(x: float, pts: Curve) -> float:
    """分段线性插值。x 落在两端之外时取端点值(不外推)。"""
    if x <= pts[0][0]:
        return pts[0][1]
    if x >= pts[-1][0]:
        return pts[-1][1]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x0 <= x <= x1:
            if x1 == x0:
                return y1
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return pts[-1][1]


# 新鲜度: 信号出现第几天。峰在第 1-2 天, 第 4 天起判为已过入场窗口。
# 「第 1 天最高还是第 2 天最高」是个**经验问题**, 不该由先验写死 —— 这里给
# 第 1、2 天几乎相同的分, 等台账能分辨了再压出真正的峰。
FRESH_CURVE: Curve = ((1, 100), (2, 98), (3, 72), (4, 46), (5, 30), (8, 12), (20, 5))
# 「逼近触发价」那一路没有六态信号新鲜度可用: 突破还没发生, 跑道最长但也
# 最未经确认。给一个相当于第 2 天略低的固定值, 并在 ctx 里标出来源, 让台账
# 日后能单独检验这条路值不值这个分。
FRESH_NEAR_BREAKOUT = 82.0

# 六态状态强弱。UT 是确认的上涨趋势; NR 是趋势中的自然回升(还没上破关键点);
# SR 更弱(次级回升, 连自然回升的高度都没到)。
STATE_SCORE = {"UT": 100.0, "NR": 78.0, "SR": 58.0}

# 相对强度(个股 20 日收益 - 大盘 20 日收益, 单位: 百分点)。区间型:
# 跑输大盘的"突破"多半是补涨陷阱; 但已经跑赢 40 个点的, 苗头期早过了。
RS_CURVE: Curve = ((-25, 0), (-10, 18), (-3, 42), (0, 55), (6, 88),
                   (14, 100), (25, 82), (40, 48), (70, 20))

# 量比(成交量 / 5 日均量)。峰在 1.3~2.5 —— 有增量但还没到人尽皆知的地步。
# > 4 反而低分: 那种量往往出现在这一波的**末端**而不是起点。
VOL_RATIO_CURVE: Curve = ((0.4, 12), (0.8, 35), (1.0, 55), (1.3, 92), (1.8, 100),
                          (2.5, 92), (3.5, 58), (5.0, 30), (8.0, 12))

# 换手率(%)。太低没人关注也没流动性, 太高是过热。区间宽而平 ——
# 换手率的合理区间随板块与市值差别很大, 曲线做窄了就是在惩罚大市值票。
TURNOVER_CURVE: Curve = ((0.2, 12), (1.0, 45), (2.5, 80), (5.0, 100),
                         (10.0, 85), (16.0, 58), (25.0, 30), (40.0, 12))

# Keltner 短期通道位置(0 = 贴下轨, 1 = 贴上轨)。过了 G2 之后实际只会 ≥ 0.5,
# 甜区就在刚站上生命线的那一段 —— 趋势确立了, 但还没把空间走掉。
POS_CURVE: Curve = ((0.40, 40), (0.50, 90), (0.58, 100), (0.66, 94), (0.75, 72),
                    (0.85, 50), (1.00, 26), (1.25, 10))


# --------------------------------------------------------------- 维度与权重

DIM_TREND = "trend"
DIM_VOLUME = "volume"
DIM_POSITION = "position"

DIM_CN = {DIM_TREND: "趋势强度", DIM_VOLUME: "量能确认", DIM_POSITION: "位置成本"}

# 维度权重。**声明权重 ≠ 有效权重** —— 三个维度之间有残余相关(见模块头),
# 真实区分度要等 R133 台账的分层单调性回来才定得下来。
WEIGHTS = {DIM_TREND: 0.45, DIM_VOLUME: 0.30, DIM_POSITION: 0.25}

# 维度内部的因子权重
TREND_WEIGHTS = {"fresh": 0.55, "state": 0.25, "rs": 0.20}
VOLUME_WEIGHTS = {"vol_ratio": 0.70, "turnover": 0.30}
POSITION_WEIGHTS = {"pos": 1.0}

FACTOR_CN = {
    "fresh": "新鲜度", "state": "六态状态", "rs": "相对强度",
    "vol_ratio": "量比", "turnover": "换手率", "pos": "通道位置",
}


def _blend(parts: dict[str, float | None], weights: dict[str, float]) -> tuple[float | None, float]:
    """按权重合成, 缺失的因子把权重让给还在的那些。

    返回 (分数, 实际覆盖到的权重占比)。全缺时返回 (None, 0.0) ——
    调用方据此决定这个维度算不算数, 而不是拿一个假的 0 分往下传。
    """
    got = {k: v for k, v in parts.items() if v is not None and k in weights}
    if not got:
        return None, 0.0
    total_w = sum(weights[k] for k in got)
    if total_w <= 0:
        return None, 0.0
    return sum(got[k] * weights[k] for k in got) / total_w, total_w / sum(weights.values())


def score_candidate(*, duration: int | None, state: str | None,
                    rs_pct: float | None, vol_ratio: float | None,
                    turnover_rate: float | None, channel_pct: float | None,
                    near_breakout: bool = False) -> dict:
    """三维度打分。返回 {score, dims, factors, coverage, partial}。纯函数。

    rs_pct: 个股 20 日收益 - 大盘 20 日收益, 单位**百分点**(如 +6.0 表示跑赢 6 个点)。
    turnover_rate: 换手率, 单位 **%**。
    channel_pct: Keltner 短期通道位置 0~1(轨外会 <0 或 >1)。
    near_breakout: 这只是"逼近触发价"那一路进来的 —— 没有六态信号新鲜度可用。
    """
    fresh: float | None
    fresh_from: str
    if duration is not None and duration >= 1:
        fresh, fresh_from = _piecewise(float(duration), FRESH_CURVE), "signal"
        if near_breakout:
            # 两条路都成立时取更高的那个: 既是新信号又正好逼近触发价, 是更好的
            # 情形, 不该因为信号已经第 4 天了就把"马上到价"这件事一起抹掉
            if FRESH_NEAR_BREAKOUT > fresh:
                fresh, fresh_from = FRESH_NEAR_BREAKOUT, "near_breakout"
    elif near_breakout:
        fresh, fresh_from = FRESH_NEAR_BREAKOUT, "near_breakout"
    else:
        fresh, fresh_from = None, "none"

    factors: dict[str, float | None] = {
        "fresh": fresh,
        "state": STATE_SCORE.get(state or "") if state else None,
        "rs": _piecewise(float(rs_pct), RS_CURVE) if rs_pct is not None else None,
        "vol_ratio": _piecewise(float(vol_ratio), VOL_RATIO_CURVE) if vol_ratio else None,
        "turnover": (_piecewise(float(turnover_rate), TURNOVER_CURVE)
                     if turnover_rate else None),
        "pos": _piecewise(float(channel_pct), POS_CURVE) if channel_pct is not None else None,
    }

    trend, cov_t = _blend(factors, TREND_WEIGHTS)
    volume, cov_v = _blend(factors, VOLUME_WEIGHTS)
    position, cov_p = _blend(factors, POSITION_WEIGHTS)
    dims: dict[str, float | None] = {
        DIM_TREND: trend, DIM_VOLUME: volume, DIM_POSITION: position}
    coverage = {DIM_TREND: cov_t, DIM_VOLUME: cov_v, DIM_POSITION: cov_p}

    total, dim_cov = _blend(dims, WEIGHTS)     # 整个维度缺席时在维度之间再归一化
    return {
        "score": int(round(total)) if total is not None else 0,
        "dims": {k: (round(v, 1) if v is not None else None) for k, v in dims.items()},
        "factors": {k: (round(v, 1) if v is not None else None) for k, v in factors.items()},
        "coverage": {k: round(v, 2) for k, v in coverage.items()},
        # 有维度缺席 → 分数是在剩下的维度上算的, 界面必须说清楚, 不能装作满的
        "partial": dim_cov < 0.999,
        "fresh_from": fresh_from,
    }


# --------------------------------------------------------------- 说人话


def explain(res: dict, *, duration: int | None = None, vol_ratio: float | None = None,
            channel_pct: float | None = None, rs_pct: float | None = None) -> list[str]:
    """把打分结果翻成几句可以直接摆在卡片上的话。

    刻意只讲**这套分数自己**的事(三维度各强在哪弱在哪), 不掺主线/AI/胜率 ——
    那些是注记, 归注记那一栏说。混在一起用户就分不清哪句话影响了排名。
    """
    out: list[str] = []
    f = res.get("factors") or {}
    if duration is not None and (f.get("fresh") or 0) >= 90:
        out.append(f"信号第 {duration} 天,入场窗口最佳")
    elif duration is not None and duration >= 4:
        out.append(f"信号已第 {duration} 天,过了最佳入场窗口")
    elif res.get("fresh_from") == "near_breakout":
        out.append("突破还没发生,跑道最长但也最未经确认")

    if vol_ratio is not None:
        if (f.get("vol_ratio") or 0) >= 88:
            out.append(f"量比 {vol_ratio:.2f},有增量但还没到人尽皆知")
        elif vol_ratio >= 3.5:
            out.append(f"量比 {vol_ratio:.2f} 偏大,这波多半已经走了一段")
        elif vol_ratio < 0.9:
            out.append(f"量比 {vol_ratio:.2f},没量,突破成色存疑")

    if channel_pct is not None:
        if (f.get("pos") or 0) >= 90:
            out.append(f"刚站上生命线(通道 {channel_pct:.0%}),位置便宜")
        elif channel_pct >= 0.95:
            out.append(f"已到通道上沿({channel_pct:.0%}),这个位置买是在最贵的地方")
        elif channel_pct >= 0.78:
            out.append(f"通道 {channel_pct:.0%},空间已经走掉一半")

    # 相对强度占趋势维度 20%, 是个真在做功的因子 —— 门槛设低一点, 让用户看得见
    if rs_pct is not None:
        if rs_pct < -3:
            out.append(f"近 20 日跑输大盘 {abs(rs_pct):.0f} 个点,比市场还弱")
        elif rs_pct >= 25:
            out.append(f"近 20 日跑赢大盘 {rs_pct:.0f} 个点,涨幅已经不小")
        elif rs_pct >= 4:
            out.append(f"近 20 日跑赢大盘 {rs_pct:.0f} 个点")
    return out
