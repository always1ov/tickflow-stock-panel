"""[fork R528] 图表上画的那条布林线 —— 26 日, ±2σ。**只此一处产地。**

用户: 「帮我改成 26 日布林线, 名称也是对应的表达」。

为什么不直接把 enriched 表里的 `boll_upper` / `boll_lower` 改成 26 日:
那两列是 20 日的, **作者内置策略「布林突破」「Keltner 回归」读的就是它们**, 因子库的
`boll_position` / `boll_width`、回测矩阵、盘中增量、监控命中消息也全挂在上面。改那两列
等于隔着一层改了作者策略的输入(AGENTS.md 硬约束 3), 还得把回测矩阵、增量路径一起
挪到 26 才不会两套口径打架。用户要改的是**图表指标里的布林轨**, 就只改图表:

  · 关键价位图(个股分析弹窗)的布林上/中/下轨曲线与价位列表 —— `api/stock_analysis.py`、`indicators/levels.py`
  · 日K图(个股 / 指数)主图叠加的 BOLL —— `api/kline.py` 给每行附 `boll26_*`

两处都从这里取, 参数只写在这里。界面上叫「26日布林」(用户定的写法, R529), 与 20 日那组
(自选 / 策略结果表的「20日布林上轨」列)分得开 —— 同一个词两个数是这仓库反复在治的病。
"""
from __future__ import annotations

import math

import polars as pl

#: 图表布林线的周期与倍数 —— 改这里, 三处一起变
BOLL_CHART_WINDOW = 26
BOLL_CHART_K = 2.0

#: 界面上的名字(单一产地; 前端 CURVE_DEFS / LEVEL_GROUPS 与这里对齐, 由 test_boll26_chart 钉着)
BOLL_CHART_LABEL = f"{BOLL_CHART_WINDOW}日布林"
BOLL_CHART_UPPER = f"{BOLL_CHART_WINDOW}日布林上轨"
BOLL_CHART_MID = f"{BOLL_CHART_WINDOW}日布林中轨"
BOLL_CHART_LOWER = f"{BOLL_CHART_WINDOW}日布林下轨"


def bollinger_series(close: pl.Series, window: int = BOLL_CHART_WINDOW, k: float = BOLL_CHART_K) -> dict[str, pl.Series]:
    """整条序列: 中轨 = 收盘 N 日均线, 上下轨 = 中轨 ± k × N 日样本标准差(ddof=1, 与 enriched 那组同口径)。

    窗口不满的位置为 null(polars rolling_* 的默认), 前端画曲线时跳过。
    """
    c = close.cast(pl.Float64)
    mid = c.rolling_mean(window)
    std = c.rolling_std(window)
    return {"mid": mid, "upper": mid + k * std, "lower": mid - k * std}


def attach_bollinger(rows: list[dict], window: int = BOLL_CHART_WINDOW, k: float = BOLL_CHART_K) -> None:
    """给 K 线行(dict 列表, 按日期升序)就地附上 `boll26_upper` / `boll26_mid` / `boll26_lower`。

    纯 Python 滚动 —— 日K接口在注入今日实时蜡烛**之后**才调它, 这样今天那根的布林值
    也是按最新收盘算的, 不用再去 enriched 表里找一个 20 日的旧值凑数。
    """
    closes: list[float | None] = []
    for r in rows:
        v = r.get("close")
        try:
            f = float(v) if v is not None else None
        except (TypeError, ValueError):
            f = None
        closes.append(f if f is not None and math.isfinite(f) else None)

    keys = (f"boll{window}_upper", f"boll{window}_mid", f"boll{window}_lower")
    for i, r in enumerate(rows):
        win = closes[i - window + 1:i + 1] if i + 1 >= window else None
        if not win or any(x is None for x in win):
            for key in keys:
                r[key] = None
            continue
        mean = sum(win) / window
        var = sum((x - mean) ** 2 for x in win) / (window - 1)
        std = math.sqrt(var) if var > 0 else 0.0
        r[keys[0]] = round(mean + k * std, 4)
        r[keys[1]] = round(mean, 4)
        r[keys[2]] = round(mean - k * std, 4)
