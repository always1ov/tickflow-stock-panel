"""[fork 增强] R313 六态里那两档没被实现的细分: SR 次级回升 / SREA 次级回撤。

用户: 「补上那两态, 但只是显示, 不触发转折不参与评分, 反正就只显示,
不能影响当前系统任何逻辑。」

## 背景: 六态实际只跑得出四态

作者内置的 `indicators/livermore.py` 里, `compute()` 的状态赋值点只有五处,
产出的只有 **UT / NR / NREA / DT**。`SR` 与 `SREA` 只出现在条件判断里
(`st in ("NR", "SR")`), 状态机永远进不去 —— 实测 16 个具名场景 × 13 个阈值、
40,547 个状态日, 这两个码一次都没出现过。

## 这一层是**标注**, 不是状态机

**一个字都不改作者那份。** 这里只做一件事: 拿他给出的 `steps`, 事后标出
「这一天其实是更细的哪一档」。

  · 输入: `compute()` 的 `steps`(只读)
  · 输出: 与 steps 等长的列表, 值是 `"SR"` / `"SREA"` / `None`
          (`None` = 这一天没有更细的档, 就是作者给的那一档)

所以:

  · **`state` 一个字节不变** —— 多空归属、`BULLISH`、打分的趋势硬门槛全不受影响;
  · **不触发转折** —— `flipped` 是作者给的, 这一层碰都不碰。细分档在一段 NR
    中途由 SR 变回 NR 是常事(反弹终于超过上一段了), 那**不是转折**,
    把它算成转折会凭空多出一堆买卖信号;
  · **不参与评分** —— `opportunity_score` 只认 `state`, 这里产出的字段它不认识。

## 判据取自仓库自己的名词表, 不从外部搬定义

`services/glossary.py` 里对这两档的原话:

    SR   「下跌途中的反弹, 而且**力度比「自然回升」还弱**」
    SREA 「上涨途中的一次回落, 而且**还没跌破前一个低点**」

照着这两句话落成可计算的判据:

    在 NR 里   本段反弹的高点 ≤ 上一段回升的高点   → SR    (这次比上次弱)
    在 NREA 里 本段回落的低点 ≥ 上一段回撤的低点   → SREA  (还没跌破)

两条同时满足名词表那条强弱轴 `UT > NR > SR > SREA > NREA > DT` ——
更弱的反弹排在 NR 之下, 更浅的回撤排在 NREA 之上; 也就是利弗莫尔
「secondary = 没能超过同向上一个极值」的原意。

**没有上一段可比时不标。** 第一段回升/回撤没有参照物, 这时给 `None`
而不是猜一个 —— "算不出来"与"判定为普通档"是两件事(R246/R248 那个坑)。

## 因果性

逐日推进, 第 i 天只用到第 i 天(含)之前**已经走完**的同向段。不看未来。
`test_R313_没有前视` 用前缀对比钉死这一条。
"""
from __future__ import annotations

SR = "SR"
SREA = "SREA"

# 只有这两个中间档才有更细的分法。UT/DT 是两端, 没有"次级上涨趋势"这回事。
_RALLY = "NR"
_REACT = "NREA"


def substates(steps: list[dict]) -> list[str | None]:
    """给作者的 `steps` 逐日标出细分档。**只标不改** —— 入参只读。

    返回与 `steps` 等长的列表: `"SR"` / `"SREA"` / `None`。
    """
    out: list[str | None] = []
    # 上一段**已经走完**的同向段的极值。None = 还没有可比的上一段。
    prev_rally_high: float | None = None
    prev_react_low: float | None = None
    # 当前这一段的状态与它走完时的极值 —— 段一结束就结算进上面两个。
    cur_state: str | None = None
    cur_high: float | None = None
    cur_low: float | None = None

    for st in steps:
        state = st.get("state")
        if state != cur_state:
            # 上一段到此结束, 结算它的极值(只结算这两个有细分的档)
            if cur_state == _RALLY and cur_high is not None:
                prev_rally_high = cur_high
            elif cur_state == _REACT and cur_low is not None:
                prev_react_low = cur_low
            cur_state, cur_high, cur_low = state, None, None

        hi, lo = _num(st.get("leg_high")), _num(st.get("leg_low"))
        if hi is not None:
            cur_high = hi if cur_high is None else max(cur_high, hi)
        if lo is not None:
            cur_low = lo if cur_low is None else min(cur_low, lo)

        out.append(_label(state, cur_high, cur_low, prev_rally_high, prev_react_low))
    return out


def _label(state: str | None, cur_high: float | None, cur_low: float | None,
           prev_rally_high: float | None, prev_react_low: float | None) -> str | None:
    """这一天的细分档。没有可比的上一段就返回 None —— 不猜。"""
    if state == _RALLY:
        if prev_rally_high is None or cur_high is None:
            return None
        # 「力度比上一次回升还弱」 —— 没能超过上一段的高点
        return SR if cur_high <= prev_rally_high else None
    if state == _REACT:
        if prev_react_low is None or cur_low is None:
            return None
        # 「还没跌破前一个低点」
        return SREA if cur_low >= prev_react_low else None
    return None


def _num(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
