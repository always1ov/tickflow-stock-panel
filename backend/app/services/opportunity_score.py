"""[fork 增强] 买入机会评分 —— 硬门槛 + 质地 × 时机 两轴(R134 起, R189 重构)。

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
    第 1 层 质地 × 时机(各 0~100)  → 排第几, 几何平均
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
  · G4 [R189 加, R229 删] 红绿节拍不是"反复失败"。整个红绿节拍规则层已按
    用户要求退役(「红绿节拍移除掉」), 这道门槛随之取消 —— 现在是三道。

三道门槛叠加等价于一句话: **只做上升趋势中继的早期, 不做底部反转。**
这是用户"跌破生命线的不看、长期是下跌趋势的也不看"的必然推论, 是一个
真实且持续存在的机会成本(底部反转第一波必然错过), 不是可以调参消除的。

## R189: 三维度 → 质地 × 时机 两根轴

原来的 trend / volume / position 三个维度是**按数据来源分的**, 于是把两类
性质完全不同的信息混进了同一个数: 慢变的"这只票好不好"和快变的"今天是不是
那一天"。结果就是「结构极好但信号第 8 天」与「结构一般但今天刚放量」拿到
同一个分 —— 而这两种情况该做的事完全不同。

改成按**变化速度**分的两根轴, 并用几何平均合成(详见「两根轴」那一节):

  | 轴   | 因子                            |
  |------|---------------------------------|
  | 质地 | 趋势模板 / 相对强度 / 六态状态  |
  | 时机 | 新鲜度 / 通道位置 / 量比 / 换手 |

  [R229] 这张表回到了 R189 刚定下时的样子。中间这两天进过又退出的三项 ——
  磨底节拍(红绿节拍, 用户要求整层退役)、三线间距与加速度(量化通道延申,
  用户要求从打分里剥离)—— 都不在了。通道延申本身没删, 只是降成注记。

    把握分 = √(质地 × 时机)

几何平均不引入任何新权重, 而且它的含义正是用户那句原话「高概率的有苗头的
东西」: 高概率是质地, 有苗头是时机, 缺一个就不成立, 也不许互相补贴。

时机轴内部的比例是从 v2 旧权重推出来的(排序行为不变); 质地轴是新的。

**三条曲线全是区间最优(倒 U), 不是单调递增** —— 这是"高概率有苗头"这句话
唯一自洽的数学形式:
  · 量比 > 4 不是苗头, 是已经发生了;
  · 通道位置 → 1.0 是贴上轨, 那是追高;
  · 相对强度过于靠前, 往往意味着已经涨了一大段。

## 一个必须写清楚的等价关系

Keltner 短期带以 MA20 为中轴, 所以 **收盘 ≥ MA20 ⟺ pct_in_channel ≥ 0.5**
(恒等, 不是近似)。因此过了 G2 之后, 位置因子的实际取值域只有 [0.5, 1.0+],
有效分辨率是名义的一半 —— 位置因子在时机轴里 32% 的**名义权重**买到的
**实际区分度**低于 32%。这不是 bug(门槛是刻意设的), 但意味着权重表里的
数字是"声明权重"而非"有效权重", 最终要靠台账的分层单调性来定, 不能拍脑袋。

## 缺数据怎么办

某个因子取不到时**在维度内按剩余权重重新归一化**, 而不是记 0 分 ——
记 0 等于因为"我们没读到换手率"去惩罚这只票。整个维度都缺时, 在维度之间
再归一化一次, 并把 `partial` 标出来, 让界面能如实说"这一档没算进去"。

[R201] 归一化之上再乘一个**置信系数**(见 `confidence()`): 归一化保证"不因
缺数据判你坏", 置信系数保证"也不让你因此占便宜"。两条合起来才完整。

## R201: 这一版改了什么, 以及为什么

前面写的都还成立 —— 门槛、两根轴、几何平均、倒 U 曲线一个没动。这一版修的
是**跑起来之后才量得出来的**三件事:

### ① 缺数据反而排在前面(实测)

    只有 state + fresh 两个因子(覆盖率 .13/.26) → 100 分, 排第 1
    十个因子全齐的同类票                        →  82 分, 排在它后面

`_blend` 把缺失因子的权重让给还在的那些, 而缺掉的往往正是**会把分拉低**的
那几个。修法是给合成分乘一个随覆盖率衰减的系数, 详见 `confidence()`。

### ② 「无信息」的默认值散在 55~60, 把所有票的底子垫高了一截

与大盘同步给 55、没有循环给 60、速度没变给 58、刚站上生命线给 90……
每一个单看都有说法, 合起来就是"什么都没发生"的票也有六七十分。统一锚到
**50**: 无信息就是无信息, 正面信息才往上走, 负面信息(震荡 42)才往下走。

### ③ 把握分的绝对值**不适合当筛选旋钮**, 这是数学性质不是 bug

实测 p10~p90 只有 17 分(65~82), 于是 `min_score = 60` 实际只挡掉 1.6% 的
候选 —— 用户以为在调筛选强度, 那个旋钮几乎没作用。

**这不是曲线锚点的锅, 拧曲线也修不好**: 拿满量程均匀分布的随机因子跑
同一套"5 因子加权平均 → 两轴几何平均", p10~p90 也只有 24 分。**平均**这件
事本身就把取值挤向中间, 因子越多挤得越狠。

所以不去硬掰分数, 改成三条:
  · 绝对分保留(台账要它做跨日比较), 但界面上的"今天该看哪几只"改由
    **名次与分位**回答 —— 那两个天然是相对的, 熊市里前 20% 仍然有票。
  · 门槛语义不变, 另加**保底条数**(见 today.FLOOR_ROWS): 够格的不足几条
    时把分最高的几只摆出来并标 `below_bar`, 页面永远不空, 而"今天没有够格
    的票"这个事实也没有被掩盖。
  · 空页最常见的成因其实在**更上游** —— 候选池本身是空的(路 A 要当天转多
    /回升, 路 B 要贴到买点 2% 内, 熊市里可以连着几天一个都没有)。今日总览
    因此加了不依赖当日信号的候选路 C(通道憋着劲/刚走出来), 见 today.py。
"""
from __future__ import annotations

from app.indicators.livermore import BULLISH   # 多头三态 UT/NR/SR, 只引用不做副本

# --------------------------------------------------------------- 门槛

GATE_TREND = "trend_side"        # 六态必须在多头侧
GATE_LIFELINE = "lifeline"       # 收盘必须站上生命线(MA20), 连续两日
GATE_LONG_DOWN = "long_down"     # 不能处在长期下跌趋势里
# [R229] 第四道 `rhythm_failing`(红绿节拍判为"反复失败")在这里删掉了 ——
# 用户: 「红绿节拍移除掉」, 整个规则层退役。质地轴那一侧的说明见 QUALITY_WEIGHTS。

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
# [R201] 候选路 C(通道憋着劲 / 刚走出来)也没有六态信号新鲜度可用, 而且它比
# "逼近触发价"更早一步: 那边至少价格已经贴到买点了, 这边连方向都还没出来。
# 所以给一个更低的固定值, 并同样在 ctx 里标出来源让台账单独检验这条路。
# 55 是**中性**那一档 —— 「不知道新不新鲜」而不是「很新鲜」, 与其它曲线
# 的无信息锚点对齐。
FRESH_COILING = 55.0

# 六态状态强弱。UT 是确认的上涨趋势; NR 是趋势中的自然回升(还没上破关键点);
# SR 更弱(次级回升, 连自然回升的高度都没到)。
STATE_SCORE = {"UT": 100.0, "NR": 78.0, "SR": 58.0}

# 相对强度(个股 20 日收益 - 大盘 20 日收益, 单位: 百分点)。区间型:
# 跑输大盘的"突破"多半是补涨陷阱; 但已经跑赢 40 个点的, 苗头期早过了。
RS_CURVE: Curve = ((-25, 0), (-10, 12), (-3, 35), (0, 50), (6, 84),
                   (14, 100), (25, 78), (40, 42), (70, 15))

# 量比(成交量 / 5 日均量)。峰在 1.3~2.5 —— 有增量但还没到人尽皆知的地步。
# > 4 反而低分: 那种量往往出现在这一波的**末端**而不是起点。
VOL_RATIO_CURVE: Curve = ((0.4, 12), (0.8, 35), (1.0, 55), (1.3, 92), (1.8, 100),
                          (2.5, 92), (3.5, 58), (5.0, 30), (8.0, 12))

# 换手率(%)。太低没人关注也没流动性, 太高是过热。区间宽而平 ——
# 换手率的合理区间随板块与市值差别很大, 曲线做窄了就是在惩罚大市值票。
TURNOVER_CURVE: Curve = ((0.2, 10), (1.0, 38), (2.5, 62), (5.0, 100),
                         (8.0, 88), (12.0, 62), (18.0, 40), (25.0, 22), (40.0, 8))

# Keltner 短期通道位置(0 = 贴下轨, 1 = 贴上轨)。过了 G2 之后实际只会 ≥ 0.5,
# 甜区就在刚站上生命线的那一段 —— 趋势确立了, 但还没把空间走掉。
POS_CURVE: Curve = ((0.40, 30), (0.50, 70), (0.58, 100), (0.66, 92), (0.75, 62),
                    (0.85, 38), (1.00, 18), (1.25, 6))


# --------------------------------------------------------------- 两根轴
#
# [R189] 由「三维度加权」改成「质地 × 时机」两根轴。
#
# 原来 trend / volume / position 三个维度混着两类完全不同的信息:
#
#   · 慢变的 —— 这只票的结构好不好(六态状态、相对强度)。以月计变化。
#   · 快变的 —— 今天是不是那一天(新鲜度、量比、换手、通道位置)。逐日变化。
#
# 混成一个数之后, 「结构极好但信号已经第 8 天」和「结构一般但今天刚放量突破」
# 会拿到同一个分, 而这是两件必须分开处理的事: 前者该等回踩, 后者该看紧一点。
# 用户要的是"抓住重点和买卖点机会" —— 重点是质地, 买卖点是时机, 一个数说不了。
#
# ## 合成为什么用几何平均, 不用加权平均
#
#     把握分 = √(质地 × 时机)
#
# 加权平均要再编一个权重(质地占几成), 而且它允许一边补另一边:
# 质地 95 / 时机 15 会和 质地 55 / 时机 55 打平 —— 前者是"好票但今天不是买点",
# 后者是"平庸的票在平庸的时点", 把它们排成一样是错的。
#
# 几何平均**一个新参数都不引入**, 而且它的含义正好是用户那句原话:
# 「高概率的有苗头的东西」—— 高概率是质地, 有苗头是时机, 缺一个就不成立。
# 任一边趋近 0, 合成分也趋近 0, 没有互相补贴的余地。
#
# ## 轴内权重哪来的
#
# 时机那四个因子的相对比例是从 R134 旧权重**推出来的**, 不是重编的:
# 旧的有效权重 fresh .2475 / vol_ratio .21 / turnover .09 / pos .25, 在这四个
# 之间归一化就是下面的数。也就是说时机轴保持了原系统的排序行为。
# 质地轴则是新的(见 QUALITY_WEIGHTS 上面的说明)。

AXIS_QUALITY = "quality"   # 质地: 这只票的结构 —— 以月计变化
AXIS_TIMING = "timing"     # 时机: 今天是不是那一天 —— 逐日变化

AXIS_CN = {AXIS_QUALITY: "质地", AXIS_TIMING: "时机"}
AXIS_WHAT = {
    AXIS_QUALITY: "这只票的长周期结构好不好(趋势模板 / 相对强度 / 六态 / 三线间距)",
    AXIS_TIMING: "今天是不是那一天(信号新鲜度 / 量比 / 通道位置 / 换手)",
}

# 质地轴的权重。**这是本次唯一新编的一组数**, 理由逐条写在这:
#
#   template .40  八条模板是四个因子里唯一被公开检验过的一组标准, 而且它是
#                 8 条的合成, 分辨率天然最高(0~8 档), 该给最大的一份。
#   base     .25  [R229 已删, 见下]
#   rs       .20  唯一一个"相对市场"的量, 与另外三个都不相关 —— 不相关的因子
#                 便宜, 权重该保住。
#   state    .15  六态是本 fork 的招牌, 但它和模板的均线排列讲的是同一件事的
#                 两种说法, 重叠最多; 而且 G1 门槛已经用它筛过一道了。同一个
#                 事实投两次票, 第二次该轻。
#
# 这几个数和 R134 的 WEIGHTS 一样是**先验**, 等台账攒够样本按分层单调性调。
#
# ## [R229] 量化通道延申从打分里**整个剥离**, 权重回到 R189/R134 那一套
#
# 用户: 「撤销所有量化通道延申有关的东西」「现在的评分系统被改崩了, 很混乱」
# 「反正评分系统最近已经稳定运行一阵子的了, 然后这两天被我大改动」。
#
# 这两天往打分里塞了三样东西, 全部退出:
#
#   [R195] spread(三线间距) 进质地 .15, 原有四项按 0.85 缩
#   [R195] accel(加速度)    进时机 .15, 原有四项按 0.85 缩
#   [R197] compress_days    换掉磨底那一半的判据
#
# 再加上同一轮里按用户要求退役的红绿节拍(base), 质地轴就只剩下 R189 编的
# 那三项, 而且**数字直接写回 R189 的原值**, 不是从 0.34 反推回去的 ——
# 0.40 : 0.20 : 0.15 就是当初定的比例, 中间那趟 ×0.85 从头到尾没有改变过它,
# 现在只是把那层缩放脱掉。时机轴同理, 四个数一字不差地回到 R134 推出来的
# .31 / .32 / .26 / .11。
#
#   template .40  八条模板是唯一被公开检验过的一组标准, 又是 8 条的合成,
#                 分辨率天然最高(0~8 档), 该给最大的一份。
#   rs       .20  唯一一个"相对市场"的量, 与另外两个都不相关 ——
#                 不相关的因子便宜, 权重该保住。
#   state    .15  六态是本 fork 的招牌, 但它和模板的均线排列讲的是同一件事的
#                 两种说法, 重叠最多; 而且 G1 门槛已经用它筛过一道了。
#                 同一个事实投两次票, 第二次该轻。
#
# **通道延申没有被删, 是被降级**: 阶段 / 事件 / 三尺度对齐 / 27 组合速查 /
# 匀速基准 / 频段能量全都还在界面上, 只是从此**一分不加一分不减** —— 与
# AI 信号、主线、胜率、龙虎榜同一条规矩(见 today.py 的 notes 那一栏)。
# 它要重新进分, 得先拿台账证明自己值那个权重, 而不是靠一句"应该有用"。
QUALITY_WEIGHTS = {"template": 0.40, "rs": 0.20, "state": 0.15}

# 时机轴的权重 —— 由 R134 旧有效权重归一化得到, 见上面「轴内权重哪来的」。
# [R195 加, R229 退] accel 让出去的那 .15 收回来, 四项回到原值。
TIMING_WEIGHTS = {"fresh": 0.31, "pos": 0.32, "vol_ratio": 0.26, "turnover": 0.11}

AXIS_FACTORS = {AXIS_QUALITY: QUALITY_WEIGHTS, AXIS_TIMING: TIMING_WEIGHTS}

FACTOR_CN = {
    "template": "趋势模板", "rs": "相对强度", "state": "六态状态",
    "fresh": "新鲜度", "vol_ratio": "量比", "turnover": "换手率", "pos": "通道位置",
}

# [R195 加, R229 删] SPREAD_CURVE / ACCEL_CURVE 与 spread_score() /
# accel_score() 在这里删掉了 —— 量化通道延申已从打分里整个剥离, 见
# QUALITY_WEIGHTS 上面那段。按 R198 的规矩: 不留没人调的死代码。

# 趋势模板通过条数 → 0~100。**上凸**: 8/8 与 7/8 的差距要比 4/8 与 3/8 的大 ——
# 模板的意义在"全部满足", 差一条就还不是那个形态, 差四条只是差得更多而已。
TEMPLATE_CURVE: Curve = ((0, 0), (2, 10), (4, 30), (5, 45), (6, 62), (7, 82), (8, 100))

# 趋势模板要**八条全都判得出来**才计入, 否则这个因子缺席(权重让给另外三个)。
# 不做"按 known 缩放": 一只上市半年的次新股 3 条全过缩放成 8 条满分, 那是
# 凭空造出来的质地。次新股本来就不该由这套模板来评价。
TEMPLATE_MIN_KNOWN = 8


def template_score(tpl: dict | None) -> float | None:
    """趋势模板 → 0~100。八条判不全就返回 None(因子缺席), 见 TEMPLATE_MIN_KNOWN。"""
    if not tpl or (tpl.get("known") or 0) < TEMPLATE_MIN_KNOWN:
        return None
    return _piecewise(float(tpl.get("passed") or 0), TEMPLATE_CURVE)


# --------------------------------------------------------------- 置信系数
#
# [R201] **缺数据不该反而排在前面。**
#
# 这是实测出来的一个真缺陷, 不是推测。同样条件下:
#
#     只有 state + fresh 两个因子(覆盖率 0.13 / 0.26) → 100 分, 排第 1
#     十个因子全齐的同类票                            →  82 分, 排在它后面
#
# 原因是 `_blend` 把缺失因子的权重让给了还在的那些。那条规矩本身是对的
# ——「不因为我们没读到就惩罚这只票」—— 但它有个没被察觉的副作用: 缺掉的
# 往往正是**会把分拉低**的那几个(模板判不全、没有节拍、通道算不出来),
# 于是"读不到"变成了优势。`partial` 那个标记只在**同分**时参与排序,
# 挡不住这件事。
#
# 修法是给合成分乘一个**随覆盖率衰减的系数**, 而不是把缺失当 0 分:
#
#     置信 = (覆盖率_质地 × 覆盖率_时机) ** 0.25
#
# 为什么是四次根: 它要温和到"缺一个因子几乎无感", 又要狠到"只剩两个因子
# 时明显掉队"。实测三档:
#
#     两轴全齐 (1.00 × 1.00) → 1.000   一分不扣
#     缺换手率 (1.00 × 0.91) → 0.977   扣 2 分左右, 无感
#     只剩两个 (0.13 × 0.26) → 0.435   100 分掉到 43 分
#
# 平方根会太狠(缺换手率就扣 5 分, 那又变成惩罚缺数据了), 一次方更狠。
# 四次根是"衰减而不是否决", 与门槛层「缺数据一律放行」是同一条纪律的延续:
# **缺数据不判你坏, 但也不让你因此占便宜。**
CONFIDENCE_EXP = 0.25


def confidence(cov_q: float, cov_t: float) -> float:
    """两轴覆盖率 → 0~1 的置信系数。两根都满时恰好 1.0(不引入任何偏移)。

    **整根轴缺席时只按活着的那根算**, 而不是把它当 0 —— 否则
    "只有时机、质地整根读不到"的票会被乘成 0 分凭空消失, 那正是
    `test_whole_axis_missing_falls_back_to_the_other_one` 守的那条纪律。
    整根缺席这件事已经由 `partial` 与 coverage 如实报给界面了。
    """
    got = [max(0.0, min(1.0, c)) for c in (cov_q, cov_t) if c > 0]
    if not got:
        return 0.0
    prod = 1.0
    for x in got:
        prod *= x
    geo_mean = prod ** (1.0 / len(got))     # 活着那几根轴的平均覆盖率
    return geo_mean ** (CONFIDENCE_EXP * 2)  # 再开平方 —— 两轴齐全时正是四次根


# [R218] 因子开关(R204)删掉了 —— 用户: 「不搞自选了」。
# 连同 `enabled_weights` / `MIN_ENABLED` / `score_candidate(enabled=)` 一起,
# 不留半截。带宽问题的出路在名次与分位(R201), 不在这个旋钮。


def _blend(parts: dict[str, float | None], weights: dict[str, float]) -> tuple[float | None, float]:
    """按权重合成, 缺失的因子把权重让给还在的那些。

    返回 (分数, 实际覆盖到的权重占比)。全缺时返回 (None, 0.0) ——
    调用方据此决定这根轴算不算数, 而不是拿一个假的 0 分往下传。
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
                    near_breakout: bool = False,
                    coiling: bool = False,
                    template: dict | None = None,
                    ) -> dict:
    """质地 × 时机 两轴打分。返回 {score, axes, factors, coverage, partial}。纯函数。

    rs_pct: 个股 20 日收益 − 大盘 20 日收益, 单位**百分点**(如 +6.0 表示跑赢 6 个点)。
    turnover_rate: 换手率, 单位 **%**。
    channel_pct: Keltner 短期通道位置 0~1(轨外会 <0 或 >1)。
    near_breakout: 这只是"逼近触发价"那一路进来的 —— 没有六态信号新鲜度可用。
    coiling:  [R201] 这只是"通道憋着劲/刚走出来"那一路进来的 —— 同样没有信号
              新鲜度, 而且比 near_breakout 更早一步。
    template: trend_template.assess 的返回值(可缺)。
    [R229] `rhythm` / `runs` / `geo` 三个形参删掉了 —— 分别是红绿节拍的返回值、
    磨底那一半的 `compress_days` 来源、以及量化通道延申的几何层。三样都已退出
    打分, 形参留着就等于留一个骗人的接口: 下一个人会以为传进来还有用。
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
    elif coiling:
        # [R201] 路 C: 没有信号也没到买点, 但通道在酝酿。给中性那一档。
        fresh, fresh_from = FRESH_COILING, "coiling"
    else:
        fresh, fresh_from = None, "none"

    factors: dict[str, float | None] = {
        # --- 质地(慢变) ---
        "template": template_score(template),
        "rs": _piecewise(float(rs_pct), RS_CURVE) if rs_pct is not None else None,
        "state": STATE_SCORE.get(state or "") if state else None,
        # --- 时机(快变) ---
        "fresh": fresh,
        "vol_ratio": _piecewise(float(vol_ratio), VOL_RATIO_CURVE) if vol_ratio else None,
        "turnover": (_piecewise(float(turnover_rate), TURNOVER_CURVE)
                     if turnover_rate else None),
        "pos": _piecewise(float(channel_pct), POS_CURVE) if channel_pct is not None else None,
    }

    quality, cov_q = _blend(factors, QUALITY_WEIGHTS)
    timing, cov_t = _blend(factors, TIMING_WEIGHTS)
    axes: dict[str, float | None] = {AXIS_QUALITY: quality, AXIS_TIMING: timing}

    # 几何平均。一根轴整根缺席时退回另一根 —— 不能把"没读到质地"当成"质地 0",
    # 那会让缺数据的票直接从榜上消失, 与门槛层「缺数据放行」是同一条纪律。
    if quality is not None and timing is not None:
        total: float | None = (max(quality, 0.0) * max(timing, 0.0)) ** 0.5
    else:
        total = quality if quality is not None else timing

    conf = confidence(cov_q, cov_t)
    if total is not None:
        total *= conf

    return {
        "score": int(round(total)) if total is not None else 0,
        "axes": {k: (round(v, 1) if v is not None else None) for k, v in axes.items()},
        "factors": {k: (round(v, 1) if v is not None else None) for k, v in factors.items()},
        "coverage": {AXIS_QUALITY: round(cov_q, 2), AXIS_TIMING: round(cov_t, 2)},
        # [R201] 置信系数 —— 排序里"读到了多少"这一层, 见 confidence()
        "confidence": round(conf, 3),
        # 有因子缺席 → 分数是在剩下的因子上算的, 界面必须说清楚, 不能装作满的
        "partial": cov_q < 0.999 or cov_t < 0.999,
        "fresh_from": fresh_from,
    }


# --------------------------------------------------------------- 说人话


def explain(res: dict, *, duration: int | None = None, vol_ratio: float | None = None,
            channel_pct: float | None = None, rs_pct: float | None = None) -> list[str]:
    """把打分结果翻成几句可以直接摆在卡片上的话。

    刻意只讲**这套分数自己**的事(两根轴各强在哪弱在哪), 不掺主线/AI/胜率 ——
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
