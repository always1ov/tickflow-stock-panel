"""[fork 增强 R173] 把把握分的维度注册进作者的因子平台, 让它能被独立检验。

## 这个模块解决什么

把握分(`opportunity_score`)从 R134 起就有一个没解决的问题: **它准不准, 只能靠
R133 台账慢慢攒样本**, 而台账要"每个分桶 ≥10 个样本且前后半段一致"才敢调权重 ——
那是以月计的等待。上游 v0.2.3 带来了因子平台(IC/IR/胜率/相关性去重), 那正是
用来回答"这个数有没有预测力"的工具。

于是这里做一件事: **把把握分的维度以同口径注册成因子**, 让它们走作者的检验管线。

## 三条纪律

1. **评分实现一行不改。** 本模块只 import `opportunity_score` 的曲线常量,
   不改它、不包装它、不替代它。今日总览算分走的还是原来那条路。
2. **口径由代码保证, 不靠我抄得准。** 曲线直接从 `opportunity_score` 引进来 ——
   哪天那边调了曲线, 这边自动跟着变, 不存在"两处数字对不上"这种事。
3. **表达不了的就不注册, 并说明为什么。** 见下。

## 能注册的与不能注册的

把握分有六个输入, 只有四个是 enriched 的**物化列**, 因子平台只认物化列:

| 维度 | 权重 | 输入 | 能否注册 |
| --- | --- | --- | --- |
| 量能确认 | 30% | 量比 `vol_ratio_5d` / 换手率 `turnover_rate` | ✅ 都是物化列 |
| 位置成本 | 25% | Keltner 短期位置(`close`/`ma20`/`atr_14`) | ✅ 三个都是物化列 |
| 趋势强度 | 45% | 新鲜度、六态状态、相对强度 | ❌ **注册不了** |

**趋势维度为什么不行**: 新鲜度与六态状态来自 `livermore_service` 的逐日状态机,
不是 enriched 里的列; 相对强度要减去大盘同期收益, 而因子矩阵里没有指数列。
硬凑一个"近似版"只会让检验结果指向一个并不存在的因子 —— 那比不检验更糟。

**所以这次能检验的是 55% 的权重(量能 30% + 位置 25%), 不是全部。** 这是实话,
不是保守: 剩下 45% 仍然只能靠台账。

## 门槛(G1/G2/G3)也不在这里

三道硬门槛是**否决**不是打分, 因子检验的是连续值的单调性/IC, 对布尔否决没有意义。
门槛该不该松紧, 看的是台账里"被挡掉的那些后来涨没涨", 那是另一件事。
"""
from __future__ import annotations

import logging

import polars as pl

from app.factors.registry import FactorSpec, get_factor, register_factor
from app.services import opportunity_score as osc

logger = logging.getLogger(__name__)

#: 前缀。用 fk_ 而不是 fork_ 是为了在因子库列表里短一点, 且不会和上游任何 id 撞。
PREFIX = "fk_"

#: 因子分组名 —— 在因子库页面里单独成组, 一眼能和作者的内置因子分开。
GROUP = "把握分(fork)"

# ---------------------------------------------------------------- 曲线 → 表达式


def piecewise_expr(x: pl.Expr, curve) -> pl.Expr:
    """把 `opportunity_score._piecewise` 的分段线性插值写成 Polars 表达式。

    与那边逐点一致: 落在两端之外取端点值(**不外推**), 中间线性插值。
    这里不重抄曲线数据, 曲线由调用方从 opportunity_score 直接传进来。
    """
    pts = list(curve)
    out = pl.lit(float(pts[-1][1]))          # 右端之外: 取最后一个点的值
    for (x0, y0), (x1, y1) in reversed(list(zip(pts, pts[1:]))):
        if x1 == x0:
            seg = pl.lit(float(y1))
        else:
            seg = pl.lit(float(y0)) + (x - float(x0)) * float(y1 - y0) / float(x1 - x0)
        out = pl.when(x < float(x1)).then(seg).otherwise(out)
    # 左端之外: 取第一个点的值(上面那层 when 会把 x < x1 的都算进第一段, 所以这里补)
    return pl.when(x <= float(pts[0][0])).then(pl.lit(float(pts[0][1]))).otherwise(out)


def keltner_pos_expr() -> pl.Expr:
    """Keltner 短期通道位置(0 = 贴下轨, 1 = 贴上轨)。

    短期通道 = MA20 ± 2.0×ATR14, 与 `keltner_service` 同一组参数。位置本身可以
    <0 或 >1(破轨), 与那边一致 —— 不夹, 夹了 POS_CURVE 右端那截就没意义了。
    """
    lower = pl.col("ma20") - 2.0 * pl.col("atr_14")
    width = 4.0 * pl.col("atr_14")
    return (
        pl.when(pl.col("atr_14").is_not_null() & (pl.col("atr_14") > 0))
        .then((pl.col("close") - lower) / width)
        .otherwise(None)
    )


# ---------------------------------------------------------------- 因子定义
#
# 每条 = (id 后缀, 中文名, 说明, 依赖的物化列, 预热根数, 表达式工厂)
# 说明里写清"这是把握分的哪一块、权重多少", 因子库里点开就知道它是干什么的。

_DEFS: list[tuple[str, str, str, frozenset[str], int, object]] = [
    ("vol_ratio_score", "把握分·量比得分",
     "量比(vol_ratio_5d)过把握分的倒U曲线; 峰在 1.3~2.5。量能维度内权重 70%",
     frozenset({"vol_ratio_5d"}), 6,
     lambda: piecewise_expr(pl.col("vol_ratio_5d"), osc.VOL_RATIO_CURVE)),

    ("turnover_score", "把握分·换手率得分",
     "换手率(%)过把握分的倒U曲线; 峰在 5% 附近。量能维度内权重 30%",
     frozenset({"turnover_rate"}), 2,
     lambda: piecewise_expr(pl.col("turnover_rate"), osc.TURNOVER_CURVE)),

    ("dim_volume", "把握分·量能确认维度",
     "量比得分×0.7 + 换手率得分×0.3。把握分三维度之一, 总权重 30%",
     frozenset({"vol_ratio_5d", "turnover_rate"}), 6,
     lambda: (
         piecewise_expr(pl.col("vol_ratio_5d"), osc.VOL_RATIO_CURVE)
         * osc.VOLUME_WEIGHTS["vol_ratio"]
         + piecewise_expr(pl.col("turnover_rate"), osc.TURNOVER_CURVE)
         * osc.VOLUME_WEIGHTS["turnover"]
     )),

    ("keltner_pos", "把握分·通道位置(原值)",
     "Keltner 短期通道位置 0~1(MA20±2.0×ATR14); 过曲线之前的**原始输入**",
     frozenset({"close", "ma20", "atr_14"}), 21,
     keltner_pos_expr),

    ("dim_position", "把握分·位置成本维度",
     "通道位置过把握分曲线; 甜区 0.50~0.66(刚站上生命线还没走掉空间)。总权重 25%",
     frozenset({"close", "ma20", "atr_14"}), 21,
     lambda: piecewise_expr(keltner_pos_expr(), osc.POS_CURVE)),
]

#: {因子 id: 表达式工厂}
_EXPRS: dict[str, object] = {}


def register_all() -> list[str]:
    """把上面这些注册进作者的因子注册表。幂等 —— 重复调用不会重复注册。

    返回本次实际注册(或已在册)的 id 列表。任何一条出问题只记 WARNING 跳过 ——
    因子库少一条是小事, 把应用启动搞挂是大事。
    """
    out: list[str] = []
    for suffix, label, desc, deps, warmup, factory in _DEFS:
        fid = PREFIX + suffix
        _EXPRS[fid] = factory
        if get_factor(fid) is not None:
            out.append(fid)
            continue
        try:
            register_factor(FactorSpec(
                id=fid, label=label, group=GROUP, formula_text=desc,
                kind="virtual", dependencies=deps, warmup_bars=warmup,
                # 方向留 none: 按作者的规矩, 方向以最近一次检验的 IC 符号为准,
                # 不预填 —— 预填等于先替检验下了结论。
                direction="none",
                asset_types=frozenset({"stock"}),   # 把握分只用于个股
                # 得分是 0~100 的绝对刻度, 跨股票直接可比
                scale_free=True, stability="stable",
                tags=("fork", "opportunity-score"),
            ))
            out.append(fid)
        except Exception as e:  # noqa: BLE001
            logger.warning("fork 因子 %s 注册失败, 跳过: %s", fid, e)
    return out


def scoring_expr(available: set[str], name: str) -> pl.Expr | None:
    """给 `strategy/scoring.py` 的转接口: 认识就给表达式, 不认识返回 None。

    依赖列不齐时返回 None(与上游其它虚拟因子同样的约定) —— 让调用方按"这个
    因子今天算不出来"处理, 而不是给一个用 null 拼出来的假值。
    """
    if not name.startswith(PREFIX):
        return None
    if not _EXPRS:
        register_all()
    factory = _EXPRS.get(name)
    if factory is None:
        return None
    deps = next((d for s, _, _, d, _, _ in _DEFS if PREFIX + s == name), frozenset())
    if not deps.issubset(available):
        return None
    try:
        return factory()
    except Exception as e:  # noqa: BLE001
        logger.warning("fork 因子 %s 求值失败: %s", name, e)
        return None
