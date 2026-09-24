"""[fork R490] 单票日 K 历史缓存 —— 钉住「快」靠的那几件事, 以及「快了但没变」。

用户: 「优化一下性能计算什么的, 现在加载出来要等很久」。实测大头是每个请求都把全部
交易日分区扫一遍、还顺带重算全套指标; 两张副图各扫一遍, 盘中每个实时行情再扫一遍。
"""
from __future__ import annotations

import threading
import time
from datetime import date, timedelta

import polars as pl

from app.services import ohlcv_history as oh


class _Repo:
    """数着被扫了几次的假仓库。"""

    def __init__(self, df: pl.DataFrame, version=date(2026, 9, 1), delay: float = 0.0):
        self.df, self.version, self.delay = df, version, delay
        self.calls: list[tuple] = []

    def get_daily_asset(self, asset_type, symbol, start, end, columns=None):
        self.calls.append((asset_type, symbol, start, end, tuple(columns or ())))
        if self.delay:
            time.sleep(self.delay)
        return self.df.select([c for c in (columns or self.df.columns) if c in self.df.columns])

    def get_enriched_latest_asset(self, asset_type, refresh=True):
        return pl.DataFrame(), self.version

    def resolve_asset_type(self, _s):
        return "stock"


def _df(n: int = 300) -> pl.DataFrame:
    d0 = date(2025, 1, 1)
    c = [10 + (i % 17) * 0.1 for i in range(n)]
    return pl.DataFrame({
        "date": [d0 + timedelta(days=i) for i in range(n)],
        "open": c, "high": [x + 0.2 for x in c], "low": [x - 0.2 for x in c], "close": c,
        "volume": [1e6] * n, "turnover_rate": [1.0] * n, "ma20": [0.0] * n,
    })


END = date(2026, 9, 24)


def test_R490_同一只票只扫一次():
    repo = _Repo(_df())
    a = oh.get_history(repo, "stock", "600000.SH", END)
    b = oh.get_history(repo, "stock", "600000.SH", END)
    assert len(repo.calls) == 1, repo.calls
    assert a.equals(b)


def test_R490_只读六列_从1990年起():
    repo = _Repo(_df())
    df = oh.get_history(repo, "stock", "600000.SH", END)
    assert repo.calls[0][2] == date(1990, 1, 1)
    assert repo.calls[0][4] == tuple(oh.COLS), "没走列下推, 会顺带重算全套指标"
    assert df.columns == oh.COLS


def test_R490_库里进了新的一天就重扫():
    repo = _Repo(_df())
    oh.get_history(repo, "stock", "600000.SH", END)
    repo.version = date(2026, 9, 2)
    oh.get_history(repo, "stock", "600000.SH", END)
    assert len(repo.calls) == 2


def test_R490_超过十分钟就重扫(monkeypatch):
    repo = _Repo(_df())
    t = [1000.0]
    monkeypatch.setattr(oh.time, "monotonic", lambda: t[0])
    oh.get_history(repo, "stock", "600000.SH", END)
    t[0] += oh.TTL_SECONDS - 1
    oh.get_history(repo, "stock", "600000.SH", END)
    assert len(repo.calls) == 1
    t[0] += 2
    oh.get_history(repo, "stock", "600000.SH", END)
    assert len(repo.calls) == 2


def test_R490_同时来两个请求_只扫一次():
    """两张副图几乎同时发请求: 第二个要等第一个扫完直接拿, 不能各扫一遍。"""
    repo = _Repo(_df(), delay=0.3)
    out: list[pl.DataFrame] = []
    ts = [threading.Thread(target=lambda: out.append(oh.get_history(repo, "stock", "600000.SH", END)))
          for _ in range(4)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert len(repo.calls) == 1 and len(out) == 4


def test_R490_拿到的是拷贝_调用方改不坏缓存():
    repo = _Repo(_df())
    a = oh.get_history(repo, "stock", "600000.SH", END)
    a = a.with_columns(pl.lit(0.0).alias("close"))
    b = oh.get_history(repo, "stock", "600000.SH", END)
    assert b["close"].to_list() == _df()["close"].to_list()


def test_R490_不同的票各存各的_超过上限淘汰最久没用的(monkeypatch):
    monkeypatch.setattr(oh, "MAX_SYMBOLS", 2)
    repo = _Repo(_df())
    for s in ("A", "B", "C"):
        oh.get_history(repo, "stock", s, END)
    oh.get_history(repo, "stock", "A", END)        # A 已被挤掉, 重扫
    assert [c[1] for c in repo.calls] == ["A", "B", "C", "A"]


# ── 端点 ────────────────────────────────────────────────────
def _client(monkeypatch, repo):
    from fastapi.testclient import TestClient

    from app import config as app_config
    from app.main import app

    monkeypatch.setattr(app_config.settings, "auth_disabled", True)
    repo.get_watchlist_live = lambda *_a, **_k: pl.DataFrame()
    app.state.repo = repo
    app.state.quote_service = None
    return TestClient(app)


def test_R490_两张副图共用一次扫描_再开一次也不扫(monkeypatch):
    from app.market_time import cn_today
    n = 900
    d0 = cn_today() - timedelta(days=n)
    base = _df(n).with_columns(pl.Series("date", [d0 + timedelta(days=i) for i in range(n)]))
    repo = _Repo(base)
    cli = _client(monkeypatch, repo)
    a = cli.get("/api/stock-analysis/quant-macd?symbol=600000.SH").json()
    b = cli.get("/api/stock-analysis/trend-quant?symbol=600000.SH").json()
    cli.get("/api/stock-analysis/quant-macd?symbol=600000.SH")
    cli.get("/api/stock-analysis/trend-quant?symbol=600000.SH")
    assert len(repo.calls) == 1, repo.calls
    assert a["dates"] and b["dates"]


def test_R490_量化MACD只用最近1500天_与原来按区间取的行一模一样(monkeypatch):
    """缓存里是全部历史, 量化MACD 切出最近 1500 天 —— 切出来的必须正是原来直接取的那段。"""
    from app.api import stock_analysis as sa
    from app.indicators import quant_macd as qm
    from app.market_time import cn_today
    n = 2500
    d0 = cn_today() - timedelta(days=n)
    base = _df(n).with_columns(pl.Series("date", [d0 + timedelta(days=i) for i in range(n)]))
    d = _client(monkeypatch, _Repo(base)).get(
        "/api/stock-analysis/quant-macd?symbol=600000.SH&bars=2000").json()
    window = base.filter(pl.col("date") >= cn_today() - timedelta(days=sa._QMACD_WARMUP_DAYS))
    want = qm.compute(window["close"].to_list(), window["volume"].to_list())
    assert d["dates"][0] == str(window["date"][0]), "量化MACD 的预热起点变了"
    assert d["diff"][-1] == round(want.diff[-1], 6)


def test_R490_缓存键带着仓库对象_换了仓库不串数据(monkeypatch):
    r1, r2 = _Repo(_df()), _Repo(_df().with_columns(pl.lit(99.0).alias("close")))
    assert oh.get_history(r1, "stock", "X", END)["close"][0] != \
        oh.get_history(r2, "stock", "X", END)["close"][0]
