"""[fork R486] 趋势量化 —— 钉住「逐行复刻」。

用户: 「在量化macd上方加个副图, 先还原做出来再说, 名称就叫趋势量化」。

做法与量化MACD、庄现相同: 另用 pandas 的常规翻译把原文写一遍(不看被测模块),
过了预热期两者必须逐根一致 —— 两种独立写法对上, 才算复刻对了。
"""
from __future__ import annotations

import ast
import random
from datetime import timedelta
from types import SimpleNamespace

import numpy as np
import pandas as pd
import polars as pl
import pytest

from app.indicators import trend_quant as tq


def _ohlcv(n: int = 1500, seed: int = 5):
    """涨一段跌一段交替, 带开盘跳空 —— 让每一种标记都有机会出现。"""
    rnd = random.Random(seed)
    o, h, lo, c, v = [10.0], [10.2], [9.8], [10.0], [1e6]
    for i in range(n - 1):
        drift = 0.03 if (i // 150) % 2 == 0 else -0.025
        op = round(max(1.0, c[-1] * (1 + rnd.gauss(0, 0.012))), 2)
        nc = round(max(1.0, c[-1] + drift + rnd.gauss(0, 0.25)), 2)
        hi = round(max(op, nc) + abs(rnd.gauss(0, 0.12)), 2)
        low = round(max(0.5, min(op, nc) - abs(rnd.gauss(0, 0.12))), 2)
        o.append(op); c.append(nc); h.append(hi); lo.append(low)
        v.append(float(rnd.randint(200_000, 3_000_000)))
    return o, h, lo, c, v


def _sma(s: pd.Series, n: int, m: int) -> pd.Series:
    return s.ewm(alpha=m / n, adjust=False).mean()


def _ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def _reference(o, h, lo, c, v) -> dict[str, pd.Series]:
    """**独立参照**: 原文逐行、pandas 常规翻译。"""
    O, H, L, C, V = (pd.Series(x, dtype=float) for x in (o, h, lo, c, v))
    wave = _ema((C - L.rolling(10, 1).min()) / (H.rolling(25, 1).max() - L.rolling(10, 1).min()) * 4, 4)
    avg = _ema(wave, 3)
    info = (avg >= avg.shift(1)).astype(int)
    strong = ((C > C.rolling(20).mean()) & (C > C.rolling(5).mean())).astype(int)
    weak = ((C < C.rolling(10).mean()) & (C < C.rolling(5).mean())).astype(int)
    vol = (V > V.rolling(5).mean()).astype(int)
    up = (info == 1) & (info.shift(1) == 0) & (info.shift(2) + info.shift(3) == 0)
    dn = (info == 0) & (info.shift(1) == 1) & (info.shift(2) + info.shift(3) == 2)
    jidi = up & (avg < 0.5)
    sheng = up & (strong == 1) & (strong.shift(1) == 0) & (vol == 1)
    ding = (avg > 2) & dn
    xia = dn & (weak == 1) & (avg > 1)

    lc = C.shift(1)
    rsi5 = _sma((C - lc).clip(lower=0), 5, 1) / _sma((C - lc).abs(), 5, 1) * 100
    tr1 = pd.concat([H - L, (H - lc).abs(), (L - lc).abs()], axis=1).max(axis=1, skipna=False) \
        .rolling(10, 1).sum()
    hd, ld = H - H.shift(1), L.shift(1) - L
    dmp = hd.where((hd > 0) & (hd > ld), 0).where(hd.notna() & ld.notna()).rolling(10, 1).sum()
    dmm = ld.where((ld > 0) & (ld > hd), 0).where(hd.notna() & ld.notna()).rolling(10, 1).sum()
    pdi, mdi = dmp * 100 / tr1, dmm * 100 / tr1
    adx = ((mdi - pdi).abs() / (mdi + pdi) * 100).rolling(5).mean()
    wr10 = 100 * (H.rolling(10, 1).max() - C) / (H.rolling(10, 1).max() - L.rolling(10, 1).min())
    best = rsi5 + adx + (rsi5 - wr10)
    pick = ((best > 0) & (best.shift(1) <= 0)).astype(float)
    v5 = _sma(pick, 3, 1); v6 = _sma(v5, 3, 1); v7 = _sma(v6, 3, 1)
    jiancang = (v6 > v7) & (v6.shift(1) <= v7.shift(1)) & (v6 < 40)

    c2 = C.shift(2)
    member = _sma((C - c2).clip(lower=0), 7, 1) / _sma((C - c2).abs(), 7, 1) * 100
    tao = (member < member.shift(1)) & (member > 79)

    jiandi = (O.shift(1) / C.shift(1) > 1.04) & (L.shift(1) <= 688) & (O > C.shift(1)) \
        & (C < O.shift(1)) & (C / O >= 1.01)
    juedi = (C - O >= 0) & (O / L > 1.05) & (L <= L.rolling(20, 1).min())

    l1 = L.shift(1)
    var12 = _sma((L - l1).abs(), 3, 1) / _sma((L - l1).clip(lower=0), 3, 1) * 100
    var13 = _ema(var12 * 10, 3)
    var17 = _ema(pd.Series(np.where(L <= L.rolling(38, 1).min(),
                                    (var13 + var13.rolling(38, 1).max() * 2) / 2, 0.0)), 3) / 618
    return {"avg": avg, "wave": wave, "jidi": jidi, "sheng": sheng, "ding": ding, "xia": xia,
            "jiancang": jiancang, "tao": tao, "jiandi": jiandi, "juedi": juedi, "var17": var17}


WARM = 200


@pytest.fixture(scope="module")
def data():
    o, h, lo, c, v = _ohlcv()
    return (o, h, lo, c, v), tq.compute(o, h, lo, c, v), _reference(o, h, lo, c, v)


def test_R486_平均线与波动线_与独立翻译逐根一致(data):
    _, got, ref = data
    for i in range(WARM, len(got.avg)):
        assert got.avg[i] == pytest.approx(ref["avg"][i], abs=1e-9)
        assert got.wave[i] == pytest.approx(ref["wave"][i], abs=1e-9)


@pytest.mark.parametrize("k", ["jidi", "sheng", "ding", "xia", "jiancang", "tao", "jiandi", "juedi"])
def test_R486_每一种标记_与独立翻译逐根一致(data, k):
    _, got, ref = data
    mine = getattr(got, k)
    diff = [i for i in range(WARM, len(mine)) if mine[i] != bool(ref[k][i])]
    assert not diff, f"「{k}」在这些根上对不上: {diff[:10]}"


def test_R486_这份数据真的覆盖了每一种标记(data):
    _, got, _ = data
    for k in ("jidi", "sheng", "ding", "xia", "jiancang", "tao"):
        assert sum(getattr(got, k)[WARM:]) > 0, f"「{k}」一次都没出现, 上面那条对比测不到它"


def test_R486_见底绝底是罕见形态_另用手搓的K线验(data):
    # 见底: 昨天开 10.6 收 10.0(>4%), 今天开 10.1 > 10.0, 收 10.3 < 10.6, 且 10.3/10.1 ≥ 1.01
    o = [10.0] * 30 + [10.6, 10.1]
    c = [10.0] * 30 + [10.0, 10.3]
    h = [x + 0.1 for x in c[:-2]] + [10.7, 10.4]
    lo = [x - 0.1 for x in c[:-2]] + [9.9, 10.05]
    got = tq.compute(o, h, lo, c, [1e6] * 32)
    assert got.jiandi[-1] and not got.jiandi[-2]
    # 绝底: 收阳, 开盘比最低价高 5% 以上, 且是 20 天最低
    o2 = [10.0] * 30 + [9.6]
    c2 = [10.0] * 30 + [9.7]
    lo2 = [9.9] * 30 + [9.0]
    h2 = [10.1] * 30 + [9.8]
    got2 = tq.compute(o2, h2, lo2, c2, [1e6] * 31)
    assert got2.juedi[-1]


def test_R486_吸筹_白柱与数值(data):
    _, got, ref = data
    for i in range(WARM, len(got.xichou)):
        assert got.xichou_bar[i] == bool(abs(ref["var17"][i]) > 0)
    vals = [x for x in got.xichou[WARM:] if x is not None]
    assert min(vals) >= 0.53 - 1e-9 and max(vals) <= 0.53 + 2.6 + 1e-9, \
        "吸筹 = VAR17/CDXS + 0.53, CDXS = 历史最高/2.6 —— 值必须落在 0.53 ~ 3.13"


def test_R486_吸筹要从第一根算起_历史不全只改高低不改出现的日子():
    o, h, lo, c, v = _ohlcv(1200)
    full = tq.compute(o, h, lo, c, v)
    part = tq.compute(o[600:], h[600:], lo[600:], c[600:], v[600:])
    assert full.xichou_bar[-300:] == part.xichou_bar[-300:], "白柱出现的日子不该依赖历史长短"


def test_R486_只要预热够长_其他标记从哪一根开始算都一样():
    o, h, lo, c, v = _ohlcv(1200)
    full = tq.compute(o, h, lo, c, v)
    part = tq.compute(o[500:], h[500:], lo[500:], c[500:], v[500:])
    for k in ("jidi", "sheng", "ding", "xia", "jiancang", "tao", "jiandi", "juedi"):
        assert getattr(full, k)[-400:] == getattr(part, k)[-400:], k


def test_R486_不引用别的指标模块():
    tree = ast.parse(open(tq.__file__, encoding="utf-8").read())
    mods = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    mods |= {f"{n.module}.{a.name}" for n in ast.walk(tree)
             if isinstance(n, ast.ImportFrom) for a in n.names}
    assert not any(x in m for m in mods for x in ("quant_macd", "zhuang_xian")), sorted(mods)


def test_R486_缺值不抛异常():
    o, h, lo, c, v = _ohlcv(300)
    h[100] = None; v[150] = None; o[200] = None
    tq.compute(o, h, lo, c, v)


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


def _daily(n: int = 1500) -> pl.DataFrame:
    from app.market_time import cn_today
    o, h, lo, c, v = _ohlcv(n)
    end = cn_today() - timedelta(days=1)
    dates = [end - timedelta(days=n - 1 - i) for i in range(n)]
    return pl.DataFrame({"date": dates, "open": o, "high": h, "low": lo, "close": c, "volume": v})


URL = "/api/stock-analysis/trend-quant?symbol=000001.SZ"


def test_R486_端点逐根与模块一致(monkeypatch):
    d = _client(monkeypatch, _daily()).get(URL + "&bars=400").json()
    o, h, lo, c, v = _ohlcv(1500)
    res = tq.compute(o, h, lo, c, v)
    assert len(d["dates"]) == len(d["avg"]) == len(d["wave_prev"]) == 400
    assert d["avg"] == [round(x, 6) for x in res.avg[-400:]]
    assert d["wave_prev"] == [round(x, 6) for x in res.wave[-401:-1]]
    for k in ("jidi", "sheng", "ding", "xia", "jiancang", "tao", "jiandi", "juedi"):
        assert d["marks"][k] == [1 if x else None for x in getattr(res, k)[-400:]], k


def test_R486_端点取全部历史(monkeypatch):
    """吸筹要从第一根算起 —— 端点的起点得早于 A 股开市。"""
    from app.api import stock_analysis as sa
    assert sa._TQ_HISTORY_START.year <= 1990


def test_R486_空数据不抛异常(monkeypatch):
    d = _client(monkeypatch, pl.DataFrame()).get(URL).json()
    assert d["dates"] == [] and d["marks"]["sheng"] == []
