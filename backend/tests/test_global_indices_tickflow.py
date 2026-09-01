"""[R149] 韩国综合删除 + 纳指首选走 TickFlow。

用户定案两件事: 「韩国指数删掉」「纳指就用 tickflow 看看能不能解决」。

这组测试的重点不在"TickFlow 能出数"(那取决于用户账号档位, 本地测不了),
而在**放它进来不会让现状变差**: 档位不给、网络不通、清单里没有、报价空 ——
四种失败都必须静静回落到 sina/腾讯, 与 R149 之前的行为完全一致。
"""
from __future__ import annotations

import time
from datetime import datetime

import pytest

from app.services import global_indices as gi

_TZ = gi._QUOTE_TZ


def _bj(now: float, minutes_ago: float) -> str:
    return datetime.fromtimestamp(now - minutes_ago * 60, _TZ).strftime("%Y-%m-%d,%H:%M:%S")


@pytest.fixture(autouse=True)
def _reset_tickflow_state():
    """TickFlow 支路的缓存是模块级的 —— 每个用例都从干净状态开始。"""
    gi._tf_at = 0.0
    gi._tf_payloads = {}
    gi._tf_symbol = {}
    gi._tf_symbol_at = 0.0
    gi._tf_last_error = None
    gi._set_cache({}, 0.0, ())
    yield
    gi._tf_at = 0.0
    gi._tf_payloads = {}
    gi._tf_symbol = {}
    gi._tf_symbol_at = 0.0
    gi._set_cache({}, 0.0, ())


class _FakeExchanges:
    def __init__(self, instruments, err=None):
        self._instruments = instruments
        self._err = err
        self.calls = 0

    def get_instruments(self, region, instrument_type=None):
        self.calls += 1
        if self._err:
            raise self._err
        return self._instruments


class _FakeQuotes:
    def __init__(self, quotes, err=None):
        self._quotes = quotes
        self._err = err
        self.calls = 0
        self.last_symbols = None

    def get(self, *, symbols=None, universes=None):
        self.calls += 1
        self.last_symbols = symbols
        if self._err:
            raise self._err
        return self._quotes


class _FakeClient:
    def __init__(self, instruments=(), quotes=(), inst_err=None, quote_err=None):
        self.exchanges = _FakeExchanges(list(instruments), inst_err)
        self.quotes = _FakeQuotes(list(quotes), quote_err)


def _install(monkeypatch, client):
    import app.tickflow.client as tf_client
    monkeypatch.setattr(tf_client, "get_client", lambda: client)
    return client


# ---------------------------------------------------------------- 韩国删干净


def test_kospi_preset_is_gone():
    assert "kospi" not in gi._BY_KEY
    assert gi.DEFAULT_KEYS == ["nasdaq"]
    assert all(p.key != "kospi" for p in gi.PRESETS)


def test_stale_kospi_selection_falls_back_to_defaults():
    """老配置里只剩已删除的 kospi 时不能落成一张卡都没有(沿用 R116 的回落)。"""
    from app.api import global_indices as api
    from app.services import preferences
    preferences.save({"global_index_keys": ["kospi"]})
    try:
        assert api._selected_keys() == gi.DEFAULT_KEYS
    finally:
        preferences.save({"global_index_keys": []})


# ---------------------------------------------------------------- 代码解析


def test_resolve_finds_symbol_from_instrument_list():
    """不猜 `IXIC.US` 还是 `.IXIC.US` —— 去清单里按代码根找到什么用什么。"""
    client = _FakeClient(instruments=[
        {"symbol": "SPX.US", "name": "S&P 500"},
        {"symbol": ".IXIC.US", "name": "NASDAQ Composite"},
    ])
    got = gi._tickflow_resolve(client, ["IXIC"], time.time())
    assert got == {"IXIC": ".IXIC.US"}


def test_resolve_falls_back_to_name_match():
    """代码根对不上时退到名称匹配 —— 对方换个写法也能自己跟上。"""
    client = _FakeClient(instruments=[
        {"symbol": "USNDQ.US", "name": "纳斯达克综合指数"},
    ])
    got = gi._tickflow_resolve(client, ["IXIC"], time.time())
    assert got == {"IXIC": "USNDQ.US"}


def test_resolve_caches_negative_result():
    """"这个档位没有美股指数"是个稳定事实, 不该每 20 秒再问一遍。"""
    client = _FakeClient(instruments=[{"symbol": "SPX.US", "name": "S&P 500"}])
    now = time.time()
    assert gi._tickflow_resolve(client, ["IXIC"], now) == {"IXIC": None}
    assert gi._tickflow_resolve(client, ["IXIC"], now + 5) == {"IXIC": None}
    assert client.exchanges.calls == 1


def test_resolve_survives_instrument_listing_error():
    client = _FakeClient(inst_err=RuntimeError("403 forbidden"))
    assert gi._tickflow_resolve(client, ["IXIC"], time.time()) == {"IXIC": None}


# ---------------------------------------------------------------- 报价与解析


def test_parse_tickflow_computes_change_from_prev_close():
    """SDK 只给 last_price/prev_close, 涨跌自己减。"""
    got = gi._parse(gi._Src("tickflow", "IXIC"),
                    {"symbol": ".IXIC.US", "last_price": 22599.1, "prev_close": 22484.07,
                     "timestamp": int(time.time() * 1000)})
    assert got is not None
    assert got["last"] == pytest.approx(22599.1)
    assert got["change"] == pytest.approx(115.03, abs=0.01)
    assert got["change_pct"] == pytest.approx(0.005116, abs=1e-5)
    assert got["quote_at"] is not None


def test_parse_tickflow_without_prev_close_reports_price_only():
    """宁可把涨跌留空, 也不编一个 0%。"""
    got = gi._parse(gi._Src("tickflow", "IXIC"),
                    {"last_price": 22599.1, "prev_close": 0})
    assert got is not None
    assert got["change"] is None and got["change_pct"] is None


def test_tickflow_timestamp_is_milliseconds():
    now = time.time()
    ts = gi._tickflow_quote_ts({"timestamp": int((now - 90) * 1000)}, now)
    assert ts is not None and abs((now - ts) - 90) < 5
    # 秒当毫秒传(少了三个零)会算出 1970 年 —— 范围守卫必须挡掉
    assert gi._tickflow_quote_ts({"timestamp": int(now)}, now) is None


# ---------------------------------------------------------------- 不许让现状变差


@pytest.mark.parametrize("client_kwargs, why", [
    ({"instruments": []}, "档位清单里没有美股指数"),
    ({"inst_err": RuntimeError("403")}, "列合约被拒"),
    ({"instruments": [{"symbol": ".IXIC.US", "name": "NASDAQ Composite"}],
      "quote_err": RuntimeError("no permission")}, "能列不能取报价"),
    ({"instruments": [{"symbol": ".IXIC.US", "name": "NASDAQ Composite"}],
      "quotes": []}, "报价回了空"),
])
def test_tickflow_failures_fall_back_to_free_sources(monkeypatch, client_kwargs, why):
    """四种失败都必须静静回落到 sina/腾讯 —— 这是敢把 TickFlow 排第一的前提。"""
    _install(monkeypatch, _FakeClient(**client_kwargs))
    now = time.time()
    raw = dict(_fetch_free(now))
    raw.update({("tickflow", "IXIC"): gi._fetch_tickflow(["IXIC"]).get("IXIC", {})})
    got = gi.pick_candidate(gi._BY_KEY["nasdaq"], raw, now, in_session=True)
    assert got is not None, why
    assert got["source"] == "sina", why
    assert got["last"] == pytest.approx(22484.07), why


def _fetch_free(now: float) -> dict:
    return {("sina", "int_nasdaq"): f"纳斯达克,22484.07,98.50,0.44,{_bj(now, 1)}"}


def test_tickflow_wins_when_it_is_freshest(monkeypatch):
    """能出数且最新时就该用它 —— 这才是"用 tickflow 试试"的意义。"""
    _install(monkeypatch, _FakeClient(
        instruments=[{"symbol": ".IXIC.US", "name": "NASDAQ Composite"}],
        quotes=[{"symbol": ".IXIC.US", "last_price": 22599.1, "prev_close": 22484.07,
                 "timestamp": int(time.time() * 1000)}],
    ))
    now = time.time()
    raw = dict(_fetch_free(now))
    raw[("sina", "int_nasdaq")] = f"纳斯达克,22484.07,98.50,0.44,{_bj(now, 200)}"
    raw[("tickflow", "IXIC")] = gi._fetch_tickflow(["IXIC"])["IXIC"]
    got = gi.pick_candidate(gi._BY_KEY["nasdaq"], raw, now, in_session=True)
    assert got is not None
    assert got["source"] == "tickflow"
    assert got["last"] == pytest.approx(22599.1)
    assert got["stale"] is False


def test_tickflow_loses_when_it_is_the_stale_one(monkeypatch):
    """规则始终是"挑最新", 不是"偏袒 TickFlow" —— 它卡住时照样让位。"""
    now = time.time()
    _install(monkeypatch, _FakeClient(
        instruments=[{"symbol": ".IXIC.US", "name": "NASDAQ Composite"}],
        quotes=[{"symbol": ".IXIC.US", "last_price": 22000.0, "prev_close": 21900.0,
                 "timestamp": int((now - 5 * 3600) * 1000)}],
    ))
    raw = dict(_fetch_free(now))
    raw[("tickflow", "IXIC")] = gi._fetch_tickflow(["IXIC"])["IXIC"]
    got = gi.pick_candidate(gi._BY_KEY["nasdaq"], raw, now, in_session=True)
    assert got is not None and got["source"] == "sina"


# ---------------------------------------------------------------- 配额纪律


def test_tickflow_throttled_to_min_interval(monkeypatch):
    """20 秒最小间隔: 前端 8 秒轮一次, 不能就真去打三次 TickFlow。"""
    client = _install(monkeypatch, _FakeClient(
        instruments=[{"symbol": ".IXIC.US", "name": "NASDAQ Composite"}],
        quotes=[{"symbol": ".IXIC.US", "last_price": 22599.1, "prev_close": 22484.07,
                 "timestamp": int(time.time() * 1000)}],
    ))
    first = gi._fetch_tickflow(["IXIC"])
    assert first and client.quotes.calls == 1
    again = gi._fetch_tickflow(["IXIC"])
    assert again == first          # 间隔内复用上次结果
    assert client.quotes.calls == 1


def test_tickflow_not_called_off_session(monkeypatch):
    """休市时那个数是静止的 —— 一次配额都不该花在它上面。"""
    client = _install(monkeypatch, _FakeClient(
        instruments=[{"symbol": ".IXIC.US", "name": "NASDAQ Composite"}],
        quotes=[{"symbol": ".IXIC.US", "last_price": 22599.1, "prev_close": 22484.07,
                 "timestamp": int(time.time() * 1000)}],
    ))
    monkeypatch.setattr(gi, "_in_session", lambda p, now=None: False)
    seen: list[str] = []

    def _spy(sources):
        seen.extend(s.vendor for s in sources)
        return _fetch_free(time.time())

    monkeypatch.setattr(gi, "_fetch_all", _spy)
    gi.get_quotes(["nasdaq"])
    assert "tickflow" not in seen
    assert client.quotes.calls == 0


def test_tickflow_is_asked_during_session(monkeypatch):
    """反过来: 盘中必须真的问它, 否则这次改动等于没做。"""
    _install(monkeypatch, _FakeClient(
        instruments=[{"symbol": ".IXIC.US", "name": "NASDAQ Composite"}],
        quotes=[{"symbol": ".IXIC.US", "last_price": 22599.1, "prev_close": 22484.07,
                 "timestamp": int(time.time() * 1000)}],
    ))
    monkeypatch.setattr(gi, "_in_session", lambda p, now=None: True)
    seen: list[str] = []

    def _spy(sources):
        seen.extend(s.vendor for s in sources)
        return _fetch_free(time.time())

    monkeypatch.setattr(gi, "_fetch_all", _spy)
    gi.get_quotes(["nasdaq"])
    assert "tickflow" in seen
