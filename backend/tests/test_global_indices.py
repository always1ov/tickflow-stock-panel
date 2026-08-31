"""[fork R99] 全球指数独立模块: 解析 / TTL 合并 / 失败回旧值。"""
from __future__ import annotations

import pytest

from app.services import global_indices as gi


@pytest.fixture(autouse=True)
def _reset_cache():
    gi._set_cache({}, 0.0, ())
    yield
    gi._set_cache({}, 0.0, ())


_KOSPI = gi._BY_KEY["kospi"]
_HSI = gi._BY_KEY["hsi"]


def test_parse_int_format():
    row = gi._parse_line(_KOSPI, "韩国KOSPI,3200.12,-12.34,-0.38")
    assert row is not None
    assert row["key"] == "kospi" and row["name"] == "韩国综合"
    assert row["last"] == 3200.12
    assert row["change"] == -12.34
    assert row["change_pct"] == pytest.approx(-0.0038)  # 百分数→小数制


def test_parse_hk_format():
    payload = "HSI,恒生指数,25100.0,25000.0,25200.0,24900.0,25050.5,50.5,0.20,x,y"
    row = gi._parse_line(_HSI, payload)
    assert row is not None
    assert row["last"] == 25050.5 and row["change_pct"] == pytest.approx(0.002)


def test_parse_garbage_returns_none():
    assert gi._parse_line(_KOSPI, "") is None
    assert gi._parse_line(_KOSPI, "只有名字") is None
    assert gi._parse_line(_KOSPI, "名字,不是数,x,y") is None


def test_fetch_response_parsing_and_ttl(monkeypatch):
    calls = {"n": 0}

    def fake_fetch(codes):
        calls["n"] += 1
        return {"int_kospi": "韩国KOSPI,3200.12,-12.34,-0.38"}

    monkeypatch.setattr(gi, "_fetch", fake_fetch)
    rows = gi.get_quotes(["kospi"])
    assert len(rows) == 1 and rows[0]["last"] == 3200.12
    # TTL 内第二次请求不打上游
    rows2 = gi.get_quotes(["kospi"])
    assert calls["n"] == 1 and rows2[0]["key"] == "kospi"


def test_upstream_failure_keeps_stale_value(monkeypatch):
    import time as _t
    monkeypatch.setattr(gi, "_fetch", lambda codes: {"int_kospi": "K,100.0,1.0,1.0"})
    assert gi.get_quotes(["kospi"])[0]["last"] == 100.0
    # 缓存过期 + 上游挂 → 回旧值
    monkeypatch.setattr(gi, "_cache_at", _t.time() - gi._TTL_S - 1)
    def boom(codes):
        raise RuntimeError("net down")
    monkeypatch.setattr(gi, "_fetch", boom)
    rows = gi.get_quotes(["kospi"])
    assert rows and rows[0]["last"] == 100.0


def test_unknown_keys_ignored():
    assert gi.get_quotes(["nope"]) == []
