"""[fork R528] 图表上的布林线是 26 日 ±2σ, 只此一处产地; enriched 的 20 日那组一个字节没动。

用户: 「帮我改成 26 日布林线, 名称也是对应的表达」。
不动 `boll_upper` / `boll_lower`: 作者内置策略「布林突破」「Keltner 回归」读的就是这两列(硬约束 3),
因子库、回测矩阵、盘中增量、监控命中消息也全挂在上面。只改图表: 关键价位图的曲线与价位列表, 日K图的 BOLL 叠加。
"""
from __future__ import annotations

import math
import statistics

import polars as pl

from app.indicators import bollinger as B
from app.indicators.pipeline import ENRICHED_COLUMNS
from tests.frontend_source import code_of


def _closes(n: int = 60) -> list[float]:
    return [100 + 3 * math.sin(i / 3) + (i % 7) * 0.4 for i in range(n)]


def test_R528_参数只写在一处_26日_2倍():
    assert B.BOLL_CHART_WINDOW == 26
    assert B.BOLL_CHART_K == 2.0
    assert B.BOLL_CHART_LABEL == "布林(26日)"
    assert (B.BOLL_CHART_UPPER, B.BOLL_CHART_MID, B.BOLL_CHART_LOWER) == ("布林上轨(26日)", "布林中轨(26日)", "布林下轨(26日)")


def test_R528_序列与逐行两条路算出同一个数():
    """关键价位图走 polars 序列, 日K接口走纯 Python 逐行 —— 两条路必须给同一个数(样本标准差, ddof=1)。"""
    closes = _closes()
    ser = B.bollinger_series(pl.Series(closes))
    rows = [{"close": c} for c in closes]
    B.attach_bollinger(rows)
    for i in range(len(closes)):
        if i < 25:
            assert ser["upper"][i] is None and rows[i]["boll26_upper"] is None, "窗口不满 26 根得是空"
            continue
        win = closes[i - 25:i + 1]
        mean = sum(win) / 26
        std = statistics.stdev(win)
        assert abs(ser["mid"][i] - mean) < 1e-9
        assert abs(ser["upper"][i] - (mean + 2 * std)) < 1e-9
        assert abs(rows[i]["boll26_upper"] - (mean + 2 * std)) < 1e-3
        assert abs(rows[i]["boll26_mid"] - mean) < 1e-3
        assert abs(rows[i]["boll26_lower"] - (mean - 2 * std)) < 1e-3


def test_R528_enriched的20日布林一个字节没动():
    """作者策略读的那两列还是 20 日: 依赖表、Pass 1、增量路径、标签, 四处都还写着 20。"""
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1] / "app" / "indicators" / "pipeline.py").read_text(encoding="utf-8")
    assert '"boll_upper": {"ma20", "_boll_std"}' in src
    assert 'pl.col("close").rolling_std(20).over("symbol").alias("_boll_std")' in src
    assert "boll_ma = boll_sum / 20" in src
    assert '"boll_upper":              "布林带上轨 MA20+2σ"' in src
    assert "boll_upper" in ENRICHED_COLUMNS and "boll26_upper" not in ENRICHED_COLUMNS, "26 日那组不该进 enriched 表"


def test_R528_三个消费点都从同一处取():
    from pathlib import Path
    app = Path(__file__).resolve().parents[1] / "app"
    sa = (app / "api" / "stock_analysis.py").read_text(encoding="utf-8")
    lv = (app / "indicators" / "levels.py").read_text(encoding="utf-8")
    kl = (app / "api" / "kline.py").read_text(encoding="utf-8")
    ix = (app / "api" / "indices.py").read_text(encoding="utf-8")
    assert "boll = bollinger_series(close)" in sa and 'df["boll_upper"]' not in sa, "关键价位图的曲线还在读 20 日列"
    assert "boll = bollinger_series(df[\"close\"])" in lv and '"label": BOLL_CHART_UPPER' in lv, "价位列表还在读 20 日列 / 名字没走产地"
    assert '"boll": BOLL_CHART_LABEL' in lv
    for name, src in (("kline", kl), ("indices", ix)):
        assert src.count("attach_bollinger(rows)") == 2, f"{name}: 两条返回路径(enriched / live)都要附 26 日布林"
        assert "timedelta(days=60)" in src, f"{name}: 没多读历史垫窗口, 图表开头 25 根会是空"


def test_R528_前端画的是26日_名字带周期_20日那组也带周期():
    ak = code_of("components/stock-analysis/AnalysisKChart.tsx")
    assert "label: '布林(26日)'" in ak
    for lbl in ("布林上轨(26日)", "布林中轨(26日)", "布林下轨(26日)"):
        assert f"endLabel: '{lbl}'" in ak
    for rel in ("components/StockDailyKChart.tsx", "pages/Indices.tsx"):
        code = code_of(rel)
        assert "r.boll26_upper" in code and "r.boll26_mid" in code and "r.boll26_lower" in code, f"{rel} 还在读 20 日列"
    ec = code_of("components/EChartsCandlestick.tsx")
    assert "label: 'BOLL(26)'" in ec
    assert "bollLine('boll_mid', '#14B8A6', 'BOLL中')" in ec, "中轨不再是 MA20, 得自己画"
    assert "Number(d.ma20).toFixed(2)}/${Number(d.boll_lower)" not in ec, "悬停里的中轨还在印 MA20"
    # 20 日那组(表格列 / 条件字段)名字带 (20日), 与图表的 26 日分得开
    for rel in ("lib/watchlist-columns.ts", "lib/screener-columns.ts", "lib/signals.ts",
                "pages/backtest/StrategyBacktest.tsx", "components/screener/StrategySettingsDialog.tsx"):
        code = code_of(rel)
        assert "'布林上轨(20日)'" in code and "'布林下轨(20日)'" in code, f"{rel}: 20 日那组没带周期"
        assert "'布林上轨'" not in code, f"{rel}: 还有不带周期的「布林上轨」"
