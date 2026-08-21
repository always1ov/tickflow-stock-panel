"""[fork 增强] R43 Keltner 通道高抛低吸 — 触下轨企稳买入, 到上轨止盈。

这是本仓第一个**出场由价格位置驱动**的策略。此前所有内置策略的 exit 都是趋势
破位型(`ma20_breakdown` / `ma_dead`) —— 哪怕入场是低吸类(超跌反弹/回踩均线),
出场依然是"跌破了才走", 所以跑出来是「低吸进 + 破位出」, 不是「低吸进 + 高抛出」。
决策台的三档通道列(R42)能让人**看见**贴不贴轨, 但回测里没有对应的出场信号,
"高抛低吸到底行不行"就没法验证。这个策略把那条路补上。

口径与决策台三列、个股分析图表共用 ``indicators.keltner.BANDS`` 的同一组参数
(短 MA20±2ATR / 中 MA60±2.5ATR / 长 MA120±3ATR), 不另写一份。

两条设计取舍:

1. **不在触轨当天买, 等收回通道内**。价格跌破下轨说明它正在下跌, 当天买是接飞刀;
   等收盘重新站回下轨之上才算企稳。代价是少赚最低那一段, 换来的是不去猜底。
2. **默认带长期趋势闸**。均值回归最亏钱的场景是"在下跌趋势里反复抄底" —— 通道
   下轨会随着均线一路下移, 每次都"触轨企稳"、每次都继续跌。默认要求收盘仍在
   MA120 之上, 只在长期没坏的票上做低吸。想验证纯信号的可以关掉。
"""

import numpy as np

from app.backtest.matrix import (
    MarketDataMatrix,
    SignalMatrix,
    make_signal_matrix,
    matrix_feature,
)
from app.backtest.matrix import (
    valid_shift as shift,
)
from app.indicators.keltner import BANDS

# {档位 key: (均线特征名, ATR 倍数, 中文名)} —— 与 R42 决策台三列同源
_BANDS = {b[0]: (b[1] or f"ma{b[2]}", b[3], b[4]) for b in BANDS}
_WARMUP = {b[0]: b[2] for b in BANDS}

META = {
    "id": "keltner_reversion",
    "name": "通道高抛低吸",
    "description": "触 Keltner 下轨后收回通道内买入, 涨到上轨止盈; 默认只做长期趋势未坏的票",
    "tags": ["均值回归", "高抛低吸", "Keltner"],
    "asset_types": ["stock", "etf"],
    "timeframes": ["1d"],
    "params": [
        {
            "id": "band",
            "label": "用哪一档通道",
            "type": "select",
            "default": "s",
            "options": [
                {"value": "s", "label": "短期 MA20±2ATR(约一个月)"},
                {"value": "m", "label": "中期 MA60±2.5ATR(一个季度)"},
                {"value": "l", "label": "长期 MA120±3ATR(半年)"},
            ],
        },
        {
            "id": "trend_filter",
            "label": "只做长期趋势未坏的(收盘在 MA120 之上)",
            "type": "bool",
            "default": True,
        },
        {
            "id": "exit_at_mid",
            "label": "到中轨就走(而不是等到上轨)",
            "type": "bool",
            "default": False,
        },
    ],
    # 打分只用来在同一天多只候选里排序, 不参与买卖判定。
    # 越靠近下轨的排越前 —— boll_position 低 = 价格在带内偏下。
    "scoring": {"boll_position": -0.6, "vol_ratio_5d": 0.4},
    "order_by": "score",
    "descending": True,
    "limit": 100,
}

EXECUTION_BACKEND = "matrix_native"
ENTRY_SIGNALS = ["signal_keltner_lower_reclaim"]
EXIT_SIGNALS = ["signal_keltner_upper_reached"]
# 企稳判断错了就是接飞刀 —— 均值回归必须有硬止损兜底
STOP_LOSS = -0.08
# 一次通道往返该在一个月内走完; 拖过头说明这次回归没发生
MAX_HOLD_DAYS = 20


class KeltnerReversionMatrixStrategy:
    def required_fields(self) -> frozenset[str]:
        return frozenset({"close"})

    def required_warmup_bars(self, params: dict) -> int:
        # 通道要均线, 趋势闸要 MA120 —— 取两者更长的那个, 少了会在前若干根上算出空值
        need = _WARMUP.get(str(params.get("band", "s")), 20)
        if params.get("trend_filter", True):
            need = max(need, 120)
        return need + 20

    def compute_signals(self, market: MarketDataMatrix, params: dict) -> SignalMatrix:
        key = str(params.get("band", "s"))
        ma_name, n_atr, _cn = _BANDS.get(key, _BANDS["s"])

        ma = matrix_feature(market, ma_name)
        atr = matrix_feature(market, "atr_14")
        upper = ma + n_atr * atr
        lower = ma - n_atr * atr
        close = market.close

        # 低吸: 上一根还在下轨或之下, 这一根收回下轨之上 = 触轨后企稳。
        # 不在触轨当天买 —— 跌破下轨说明它正在跌, 当天买是接飞刀。
        entry = (shift(close, 1) <= shift(lower, 1)) & (close > lower)
        if params.get("trend_filter", True):
            # 下跌趋势里下轨随均线一路下移, 每次都"触轨企稳"、每次都继续跌 ——
            # 均值回归最亏钱的就是这个场景
            entry &= close > matrix_feature(market, "ma120")

        # 高抛: 到上轨止盈(或按需改成到中轨就落袋, 更快但赚得少)
        exit_ = close >= (ma if params.get("exit_at_mid", False) else upper)

        # 通道算不出来的前若干根(均线/ATR 尚未成形)一律不出信号
        valid = np.isfinite(upper) & np.isfinite(lower) & (atr > 0)
        entry &= valid
        exit_ &= valid

        return make_signal_matrix(
            market.shape,
            entry=entry.astype(np.uint8),
            exit=exit_.astype(np.uint8),
            entry_signal_code=np.where(entry, 0, -1).astype(np.int16),
            exit_signal_code=np.where(exit_, 0, -1).astype(np.int16),
            entry_signal_ids=("signal_keltner_lower_reclaim",),
            exit_signal_ids=("signal_keltner_upper_reached",),
        )


MATRIX_STRATEGY = KeltnerReversionMatrixStrategy()
