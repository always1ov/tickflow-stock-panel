"""[fork R485] 庄现 —— 钉住「逐行复刻」和「冻结、与量化MACD 互不相干」两件事。

用户: 「移植到量化macd里面, 当作辅助指标不在动了, 就算我以后微调量化macd也不动这些了」。
[R488] 又: 「把狗头剥离量化macd, 放到趋势量化里面去」—— 画在趋势量化上, 数据由 /trend-quant 带。

最容易坏的三种方式, 屏幕上都看不出来(狗头照样一个个冒出来):

  · **翻译错了一处**(SMA 的递推、REVERSE、那个错开 10 根的 60 日线条件)—— 出现的
    日子整体漂移, 但看着一样"像回事";
  · **悄悄接回了 quant_macd**: 以后调量化MACD, 庄现跟着变, 正是用户说不要的;
  · **有人"顺手优化"了公式**: 冻结基线把固定输入下的出现位置钉死, 改了必红。
"""
from __future__ import annotations

import random
from datetime import timedelta
from types import SimpleNamespace

import pandas as pd
import polars as pl

from app.indicators import zhuang_xian as zx
from tests.frontend_source import code_lines, read_src


def _ohlc(n: int = 600, seed: int = 11) -> tuple[list[float], list[float], list[float]]:
    """涨一段、跌一段交替的随机游走 —— 既有上升途中的回调(该出), 也有下跌里的反弹(该挡)。"""
    rnd = random.Random(seed)
    c, h, lo = [10.0], [10.2], [9.8]
    for i in range(n - 1):
        drift = 0.03 if (i // 120) % 2 == 0 else -0.02
        nc = round(max(1.0, c[-1] + drift + rnd.gauss(0, 0.25)), 2)
        c.append(nc)
        h.append(round(nc + abs(rnd.gauss(0, 0.12)), 2))
        lo.append(round(nc - abs(rnd.gauss(0, 0.12)), 2))
    return h, lo, c


def _reference(high, low, close) -> tuple[pd.Series, pd.Series]:
    """**独立参照**: 照原文逐行、用 pandas 的常规翻译写一遍, 不看被测模块。

    通达信 SMA(X,N,M) 就是 α=M/N 的指数平滑(首根取 X), 即 `ewm(alpha=M/N, adjust=False)`。
    返回 (信号, 只看 J 上穿、不带 60 日线条件的信号) —— 后者用来证明那个条件真的在挡。
    """
    h, lo, c = pd.Series(high), pd.Series(low), pd.Series(close)
    llv = lo.rolling(9, min_periods=1).min()
    hhv = h.rolling(9, min_periods=1).max()
    rsv2 = (c - llv) / (hhv - llv) * 100
    k = rsv2.ewm(alpha=0.5, adjust=False).mean()
    d = k.ewm(alpha=0.5, adjust=False).mean()
    j = 3 * k - 2 * d
    j1 = -j
    cross = (j > j1) & (j.shift(1) <= j1.shift(1))
    aa1 = c.shift(10) > c.rolling(60).mean().shift(10)
    return cross & aa1, cross


WARM = 80   # 60 日线 + 错开 10 根之后才比


def test_R485_与独立的逐行翻译逐根一致():
    h, lo, c = _ohlc()
    got = zx.compute(h, lo, c)
    ref, _ = _reference(h, lo, c)
    for i in range(WARM, len(c)):
        assert got[i] == bool(ref[i]), f"第 {i} 根: 模块 {got[i]}, 参照 {bool(ref[i])}"


def test_R485_这份数据真的覆盖了该出和该挡两种情形():
    h, lo, c = _ohlc()
    got = zx.compute(h, lo, c)
    _, cross = _reference(h, lo, c)
    assert sum(got[WARM:]) >= 5, "庄现太少, 上面那条对比测不到东西"
    blocked = [i for i in range(WARM, len(c)) if cross[i] and not got[i]]
    assert blocked, "J 上穿都没被 60 日线条件挡过 —— 那个条件等于没测"


def test_R485_冻结基线_固定输入下出现的日子一根不许变():
    """**改这里之前先想清楚**: 用户要的是「以后不动」。这份基线红了, 说明庄现的出现
    位置变了 —— 要么是有人改了公式(不该), 要么是有意的改动(那就连同理由一起改基线)。"""
    h, lo, c = _ohlc()
    got = [i for i, x in enumerate(zx.compute(h, lo, c)) if x]
    assert got == [107, 149, 151, 162, 338, 371, 387, 439, 445, 490, 503, 514]


def test_R485_REVERSE就是取负_CROSS是本根上穿且上一根不大于():
    assert zx.CROSS([-1.0, 1.0], [1.0, -1.0]) == [False, True]
    assert zx.CROSS([0.0, 1.0], [0.0, -1.0]) == [False, True]      # 上一根相等也算
    assert zx.CROSS([1.0, 2.0], [0.0, 0.0]) == [False, False]       # 一直在上方不算
    assert zx.CROSS([None, 1.0], [0.0, 0.0]) == [False, False]


def test_R485_SMA照通达信的递推_首根取原值():
    assert zx.SMA([4.0, 8.0, 0.0], 2, 1) == [4.0, 6.0, 3.0]


def test_R485_连续一字没有高低差时不出信号_不除出无穷大():
    n = 120
    h = lo = c = [10.0] * n
    assert not any(zx.compute(list(h), list(lo), list(c)))


def test_R485_缺高低价的那一根不出信号_也不抛异常():
    h, lo, c = _ohlc(200)
    h[150] = None
    got = zx.compute(h, lo, c)
    assert got[150] is False


# ── 冻结: 与量化MACD 互不相干 ────────────────────────────────
def test_R485_后端模块不引用量化MACD():
    import ast
    tree = ast.parse(open(zx.__file__, encoding="utf-8").read())
    mods = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    mods |= {f"{n.module}.{a.name}" for n in ast.walk(tree)
             if isinstance(n, ast.ImportFrom) for a in n.names}
    # 只看真正的 import —— 说明文字里提到 quant_macd 是在解释为什么不用它
    assert not any("quant_macd" in m for m in mods), \
        f"庄现又依赖量化MACD 了 —— 以后调量化MACD 它会跟着变: {sorted(mods)}"


def test_R485_前端画法不引用任何一张副图_也不读它们的数值():
    """[R488] 狗头挪到了趋势量化, 同样不许读趋势量化的数值 —— 位置只看哪一天。"""
    code = code_lines(read_src("lib/zhuangXianSeries.ts"))
    assert "quantMacdSeries" not in code and "trendQuantSeries" not in code
    for w in (".diff", ".dea", "gold_icon", "dead_icon", "yellow",
              ".avg", ".wave", "xichou", "marks"):
        assert w not in code, f"狗头的画法读了副图的「{w}」—— 位置会跟着那张副图变"


def test_R488_狗头画在趋势量化_不在量化MACD():
    """用户: 「把狗头剥离量化macd, 放到趋势量化里面去」。"""
    chart = code_lines(read_src("components/stock-analysis/AnalysisKChart.tsx"))
    assert "zhuangXianIndexes(dates, trendQuant)" in chart
    assert "zhuangXianSeries(zhuang, { xAxisIndex: 2, yAxisIndex: 2 })" in chart
    assert "zhuangXianIndexes(dates, quantMacd)" not in chart


def test_R485_界面上不用粉色():
    """全站禁粉(AGENTS.md 第 15 条)。通达信原文里庄现是洋红, 这里换成了柴犬的颜色。"""
    code = code_lines(read_src("lib/zhuangXianSeries.ts"))
    assert "FF00FF" not in code.upper() and "MAGENTA" not in code.upper()


# ── 端点 ────────────────────────────────────────────────────
def _client(monkeypatch, df: pl.DataFrame):
    from fastapi.testclient import TestClient

    from app import config as app_config
    from app.main import app

    monkeypatch.setattr(app_config.settings, "auth_disabled", True)
    app.state.repo = SimpleNamespace(
        get_daily_asset=lambda *_a, **_k: df,
        resolve_asset_type=lambda _s: "stock",
        get_watchlist_live=lambda *_a, **_k: pl.DataFrame(),
        get_enriched_latest_asset=lambda *_a, **_k: (pl.DataFrame(), None),
    )
    app.state.quote_service = None
    return TestClient(app)


def _daily(n: int = 600) -> pl.DataFrame:
    from app.market_time import cn_today
    h, lo, c = _ohlc(n)
    end = cn_today() - timedelta(days=1)
    dates = [end - timedelta(days=n - 1 - i) for i in range(n)]
    return pl.DataFrame({"date": dates, "high": h, "low": lo, "close": c,
                         "volume": [1e6] * n})


# [R488] 庄现改由趋势量化的接口带过来; 量化MACD 的接口回到 R485 之前, 不再有这个字段
URL = "/api/stock-analysis/trend-quant?symbol=000001.SZ"


def test_R485_端点带上庄现_与模块逐根一致(monkeypatch):
    d = _client(monkeypatch, _daily()).get(URL + "&bars=400").json()
    assert len(d["zhuang"]) == len(d["dates"]) == 400
    h, lo, c = _ohlc(600)
    want = [1 if x else None for x in zx.compute(h, lo, c)][-400:]
    assert d["zhuang"] == want
    assert any(v == 1 for v in d["zhuang"])


def test_R485_趋势量化和量化MACD的算法怎么变_庄现都不跟着变(monkeypatch):
    """用户那句话的字面意思: 把所在副图的计算整个换成胡乱的结果, 庄现必须一根不差。"""
    from app.indicators import quant_macd as qm
    from app.indicators import trend_quant as tq
    before = _client(monkeypatch, _daily()).get(URL).json()["zhuang"]

    def junk_tq(o, h, lo, c, v):
        n = len(c)
        return tq.TrendQuant(wave=[9.0] * n, avg=[9.0] * n, stick_up=[None] * n,
                             jidi=[True] * n, sheng=[True] * n, ding=[True] * n, xia=[True] * n,
                             jiancang=[True] * n, tao=[True] * n, jiandi=[True] * n,
                             juedi=[True] * n, xichou=[None] * n, xichou_bar=[False] * n)

    monkeypatch.setattr(tq, "compute", junk_tq)
    monkeypatch.setattr(qm, "compute", lambda close, vol: None)
    after = _client(monkeypatch, _daily()).get(URL).json()["zhuang"]
    assert after == before


def test_R488_量化MACD的接口不再带庄现(monkeypatch):
    d = _client(monkeypatch, _daily()).get(
        "/api/stock-analysis/quant-macd?symbol=000001.SZ").json()
    assert "zhuang" not in d


def test_R485_日K里没有高低价也不抛异常_只是不出庄现(monkeypatch):
    df = _daily().drop(["high", "low"])
    d = _client(monkeypatch, df).get(URL).json()
    assert d["zhuang"] and all(v is None for v in d["zhuang"])


def test_R485_空数据也带着这个字段(monkeypatch):
    d = _client(monkeypatch, pl.DataFrame()).get(URL).json()
    assert d["zhuang"] == []
