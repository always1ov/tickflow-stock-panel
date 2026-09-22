"""[fork R415] 量化MACD —— 钉住「逐行复刻」这件事本身。

用户:「必须完美复刻」「我这个是量化指标, 和仓库系统里面的不一样的」。

复刻最容易出的错, 屏幕上都看不出来(柱子照样有红有绿):

  · **EMA 初值 / 预热**: 递推指标从哪一根开始算会影响之后的值 —— 窗口一短,
    最左边那几十根就和通达信对不上, 而看着一样"像 MACD"。
  · **把 `:=` 的行也画出来**: 原文的 `MACD:=2*(DIFF-DEA),STICK` 在通达信里不画,
    画了就多出一套红绿柱, 整张图变成另一个指标。
  · **黄柱高度 / 图标位置抄错**: DEA/4、柱2、DEA*1.1 这三个数是原文写死的。
  · **误读了仓库现成的 MACD 列**: 那是另一套东西(用户明说了), 本指标必须自己算。
"""
from __future__ import annotations

import random
from datetime import timedelta
from types import SimpleNamespace

import pandas as pd
import polars as pl
import pytest

from app.indicators import quant_macd as qm


def _series(n: int = 600, seed: int = 7) -> tuple[list[float], list[float]]:
    """带平盘日的随机游走 —— 平盘日专门用来走 `CLOSE=REF(CLOSE,1)` 那条分支。"""
    rnd = random.Random(seed)
    c, v = [10.0], [1e6]
    for _ in range(n - 1):
        step = 0.0 if rnd.random() < 0.08 else rnd.gauss(0, 0.2)
        c.append(round(max(1.0, c[-1] + step), 2))
        v.append(float(rnd.randint(200_000, 3_000_000)))
    return c, v


def _reference(close: list[float], vol: list[float]) -> dict[str, pd.Series]:
    """**独立参照**: 照原文逐行、用 pandas 的常规翻译写一遍, 不看被测模块。

    这是业界最常见的翻译方式(`ewm(span=N, adjust=False)`、`rolling(N).mean()`、
    `SUM(X,0)=cumsum`)。它和被测模块只在**预热期**有差别(NaN 当 False 往下算
    vs 无效值传播), 过了预热期两者必须逐位一致 —— 两种独立写法对上, 才算复刻对了。
    """
    c, v = pd.Series(close), pd.Series(vol)
    diff = c.ewm(span=12, adjust=False).mean() - c.ewm(span=26, adjust=False).mean()
    dea = diff.ewm(span=9, adjust=False).mean()
    rc = c.shift(1)
    va = pd.Series([vv if cc > rr else -vv for cc, rr, vv in zip(c, rc, v)])
    obv1 = pd.Series([0.0 if cc == rr else x for cc, rr, x in zip(c, rc, va)]).cumsum()
    obv2 = obv1.ewm(span=3, adjust=False).mean() - obv1.rolling(9).mean()
    obv3 = obv2.where(obv2 > 0, 0.0).ewm(span=3, adjust=False).mean()
    mac3 = c.rolling(3).mean()
    res = (obv3 > obv3.shift(1)) & (mac3 > mac3.shift(1))
    gx = (diff > dea) & (diff.shift(1) <= dea.shift(1))
    dx = (dea > diff) & (dea.shift(1) <= diff.shift(1))
    z2 = dea.where(dea < diff, 0.0)
    return {"diff": diff, "dea": dea, "res": res, "gx": gx, "dx": dx,
            "z2": z2}


WARM = 120   # 预热期之后才比 —— 两种写法只在这之前允许不同


# ── 与独立参照逐根比对 ─────────────────────────────────────
def test_R415_与独立的逐行翻译逐根一致():
    close, vol = _series()
    got = qm.compute(close, vol)
    ref = _reference(close, vol)
    for i in range(WARM, len(close)):
        assert got.diff[i] == pytest.approx(ref["diff"][i], abs=1e-12)
        assert got.dea[i] == pytest.approx(ref["dea"][i], abs=1e-12)
        # 黄柱: 条件与高度都对
        if ref["res"][i]:
            assert got.yellow[i] == pytest.approx(ref["dea"][i] / 4, abs=1e-12), i
        else:
            assert got.yellow[i] is None, f"第 {i} 根不该有黄柱"
        # 两个图标: 出现在哪一根、画在多高
        if ref["gx"][i]:
            assert got.gold_icon[i] == pytest.approx(ref["z2"][i], abs=1e-12)
        else:
            assert got.gold_icon[i] is None
        if ref["dx"][i]:
            assert got.dead_icon[i] == pytest.approx(ref["dea"][i] * 1.1, abs=1e-12)
        else:
            assert got.dead_icon[i] is None


def test_R415_这份数据真的覆盖了每一种情形():
    """上一条要真的测到东西: 黄柱、金叉、死叉、平盘日都得出现过。"""
    close, vol = _series()
    got = qm.compute(close, vol)
    tail = slice(WARM, None)
    assert any(x is not None for x in got.yellow[tail]), "没有黄柱"
    assert any(x is not None for x in got.gold_icon[tail]), "没有金叉"
    assert any(x is not None for x in got.dead_icon[tail]), "没有死叉"
    assert any(close[i] == close[i - 1] for i in range(WARM, len(close))), "没有平盘日"
    assert any((d or 0) < 0 for d in got.dea[tail]) and any((d or 0) > 0 for d in got.dea[tail])


# ── 预热: 显示出来的每一根与从头算一致 ────────────────────────
def test_R415_只要预热够长_从哪一根开始算都一样():
    """**这条就是「完美复刻」在数值上的保证。**

    通达信从上市第一根算起; 本仓库取约 1000 根。这里用 3000 根模拟"从上市算",
    再只取最后 1000 根重算, 比最后 400 根(= 端点默认返回的根数)。
    EMA 的起点差异按 (1-α)^n 衰减, 600 根之后必须低于 1e-9 —— 做不到就说明
    预热不够, 图上最左边那段和通达信不一样。
    """
    close, vol = _series(3000, seed=11)
    full = qm.compute(close, vol)
    part = qm.compute(close[-1000:], vol[-1000:])
    for k in range(1, 401):
        assert part.diff[-k] == pytest.approx(full.diff[-k], abs=1e-9)
        assert part.dea[-k] == pytest.approx(full.dea[-k], abs=1e-9)
        assert (part.yellow[-k] is None) == (full.yellow[-k] is None), \
            f"倒数第 {k} 根黄柱有无不一致 —— OBV 这一支受了起点影响"
        assert (part.gold_icon[-k] is None) == (full.gold_icon[-k] is None)
        assert (part.dead_icon[-k] is None) == (full.dead_icon[-k] is None)


def test_R415_端点取的历史够长():
    """上一条证了 1000 根够; 这条钉住端点真的取了这么多(1500 个自然日 ≈ 1000 根)。"""
    from app.api import stock_analysis
    assert stock_analysis._QMACD_WARMUP_DAYS >= 1400


# ── 原文里写死的几个数 ─────────────────────────────────────
def test_R415_EMA初值是第一根_递推照通达信公式():
    """通达信 EMA: 首根 Y=X, 之后 Y=(2X+(N-1)Y')/(N+1)。"""
    out = qm.EMA([10.0, 13.0, 7.0], 3)
    assert out[0] == 10.0
    assert out[1] == pytest.approx((2 * 13 + 2 * 10) / 4)
    assert out[2] == pytest.approx((2 * 7 + 2 * out[1]) / 4)


def test_R415_MA不足N根无效_不是当成0():
    assert qm.MA([1.0, 2.0, 3.0, 4.0], 3) == [None, None, 2.0, 3.0]


def test_R415_CROSS是本根上穿且上一根不大于():
    a = [1.0, 2.0, 3.0, 2.0, 2.0, 3.0]
    b = [2.0, 2.0, 2.0, 2.0, 2.0, 2.0]
    # 第 2 根: 3>2 且上一根 2<=2 → 上穿; 第 5 根: 3>2 且上一根 2<=2 → 上穿
    assert qm.CROSS(a, b) == [False, False, True, False, False, True]


def test_R415_黄柱画在DEA的四分之一():
    close, vol = _series()
    got = qm.compute(close, vol)
    for y, d in zip(got.yellow, got.dea):
        if y is not None:
            assert y == pytest.approx(d / 4)


def test_R415_死叉图标画在DEA的1点1倍_金叉图标画在柱2():
    close, vol = _series()
    got = qm.compute(close, vol)
    for i, (g, x, d, f) in enumerate(zip(got.gold_icon, got.dead_icon, got.dea, got.diff)):
        if x is not None:
            assert x == pytest.approx(d * 1.1), i
        if g is not None:
            # 柱2 = IF(DEA<DIFF, DEA, 0) —— 金叉那根 DIFF>DEA, 所以就是 DEA
            assert g == pytest.approx(d if d < f else 0.0), i


def test_R415_中间变量不输出():
    """原文里 `MACD:=`、`柱1:=`、`OBV3:=` 这些都是 `:=` —— 通达信里不画。

    **只要结果里冒出一个 macd/柱1 的字段, 前端就可能把它画出来**, 整张图就多一套
    红绿柱、变成另一个指标。所以输出的字段必须正好是画得出来的那五样。
    """
    fields = set(qm.QuantMacd.__dataclass_fields__)
    assert fields == {"diff", "dea", "yellow", "gold_icon", "dead_icon"}, fields


# ── 两个"不影响"的性质 ────────────────────────────────────
def test_R415_成交量单位不影响结果():
    """手 / 股 差 100 倍 —— OBV3 只用于比大小, 正数倍缩放不改变任何一根。"""
    close, vol = _series()
    a = qm.compute(close, vol)
    b = qm.compute(close, [x * 100 for x in vol])
    assert a.yellow == b.yellow


def test_R415_实时那根缺量时不编数_只是那根不出黄柱():
    close, vol = _series(300)
    vol2 = vol[:-1] + [None]
    got = qm.compute(close, vol2)
    assert got.yellow[-1] is None
    # DIFF/DEA 不看量, 照算
    assert got.diff[-1] is not None and got.dea[-1] is not None


# ── 端点 ────────────────────────────────────────────────────
def _client(monkeypatch, df: pl.DataFrame, overlay: pl.DataFrame | None = None):
    from fastapi.testclient import TestClient

    from app import config as app_config
    from app.main import app

    monkeypatch.setattr(app_config.settings, "auth_disabled", True)
    app.state.repo = SimpleNamespace(
        get_daily_asset=lambda *_a, **_k: df,
        resolve_asset_type=lambda _s: "stock",
        get_watchlist_live=lambda *_a, **_k: overlay if overlay is not None else pl.DataFrame(),
        get_enriched_latest_asset=lambda *_a, **_k: (pl.DataFrame(), None),
    )
    app.state.quote_service = None
    return TestClient(app)


def _daily(n: int = 400) -> pl.DataFrame:
    from app.market_time import cn_today
    close, vol = _series(n, seed=3)
    end = cn_today() - timedelta(days=1)
    dates = [end - timedelta(days=n - 1 - i) for i in range(n)]
    return pl.DataFrame({"date": dates, "close": close, "volume": vol})


def test_R415_端点不读仓库现成的MACD列(monkeypatch):
    """用户:「我这个是量化指标, 和仓库系统里面的不一样的」。

    做法: 给一份带着**乱写的** macd_dif / macd_dea 列的日 K —— 如果端点偷偷读了
    它们, 结果就会跟着变。
    """
    df = _daily()
    clean = _client(monkeypatch, df).get("/api/stock-analysis/quant-macd?symbol=000001.SZ").json()
    dirty_df = df.with_columns(pl.lit(999.0).alias("macd_dif"),
                               pl.lit(-999.0).alias("macd_dea"),
                               pl.lit(0.0).alias("macd_hist"))
    dirty = _client(monkeypatch, dirty_df).get("/api/stock-analysis/quant-macd?symbol=000001.SZ").json()
    assert clean["diff"] == dirty["diff"] and clean["dea"] == dirty["dea"]


def test_R415_端点带上盘中实时那一根(monkeypatch):
    """图上最右那根蜡烛带着盘中实时价; 副图最右那根必须是同一根数据。"""
    from app.market_time import cn_today
    df = _daily()
    today = cn_today()
    overlay = pl.DataFrame({
        "symbol": ["000001.SZ"], "date": [str(today)],
        "open": [10.0], "high": [10.5], "low": [9.8], "close": [10.3], "volume": [1.5e6],
    })
    d = _client(monkeypatch, df, overlay).get(
        "/api/stock-analysis/quant-macd?symbol=000001.SZ").json()
    assert d["dates"][-1] == str(today), "实时那一根没进来"
    assert len(d["dates"]) == len(d["diff"]) == len(d["yellow"])


def test_R415_端点只返回最近几根_但用全部历史预热(monkeypatch):
    d = _client(monkeypatch, _daily(900)).get(
        "/api/stock-analysis/quant-macd?symbol=000001.SZ&bars=50").json()
    assert len(d["dates"]) == 50
    close, vol = _series(900, seed=3)
    full = qm.compute(close, vol)
    assert d["diff"][-1] == pytest.approx(full.diff[-1], abs=1e-6)
    assert not any(k in d for k in ("macd", "hist", "obv3")), "中间变量漏到了响应里"


def test_R415_空数据不抛异常(monkeypatch):
    d = _client(monkeypatch, pl.DataFrame()).get(
        "/api/stock-analysis/quant-macd?symbol=000001.SZ").json()
    assert d["dates"] == [] and d["diff"] == []
