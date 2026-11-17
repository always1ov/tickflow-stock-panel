"""[R790] 看板分区接口 — 四个子接口共享同一份聚合结果, 只做切片。

验证:
- 各子接口键集合与全量接口一致地来自同一次装配;
- as_of 透传到装配函数(历史复盘);
- 非法 kind 由 FastAPI 参数校验拒绝(422)。
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import overview


def _payload(as_of: str = "2026-01-05") -> dict:
    row = {"symbol": "600000.SH", "name": "浦发银行", "close": 10.0, "change_pct": 0.1}
    return {
        "as_of": as_of,
        "quote_status": {"running": False, "mode": "none"},
        "indices": [{"symbol": "000001.SH", "name": "上证指数", "last_price": 3200.0, "change_pct": 0.5}],
        "breadth": {"total": 3, "up": 2, "down": 1, "flat": 0, "up_pct": 66.7, "down_pct": 33.3},
        "amount": {"total": 100.0, "avg": 33.3},
        "boards": [{"board": "沪主板", "count": 3, "up": 2, "down": 1, "up_pct": 66.7, "amount": 100.0}],
        "limit": {"limit_up": 1, "broken": 0, "failed": 0, "limit_down": 0, "max_boards": 1, "tiers": []},
        "distribution": [{"label": "0~2%", "count": 2, "pct": 66.7}],
        "trend": {"above_ma5": 2, "above_ma20": 2, "above_ma60": 1, "above_ma5_pct": 66.7,
                  "above_ma20_pct": 66.7, "above_ma60_pct": 33.3, "new_high": 1, "new_low": 0},
        "activity": {"avg_turnover": 1.2, "high_turnover": 1, "high_vol_ratio": 20.0, "vol_ratio": 1.1},
        "radar": [{"key": "breadth", "label": "广度", "value": 60}],
        "emotion": {"score": 58, "label": "中性"},
        "top_gainers": [row],
        "top_losers": [],
        "turnover_leaders": [row],
        "active_leaders": [],
        "concept_rank": {"leading": [{"name": "机器人", "count": 2, "avg_pct": 0.03,
                                     "up_count": 2, "down_count": 0, "amount": 10.0}],
                          "lagging": []},
        "industry_rank": {"leading": [], "lagging": []},
    }


@pytest.fixture
def built_calls(monkeypatch) -> list[str | None]:
    """替换全量装配, 记录 as_of 透传情况 (缓存键随 as_of 变化, 用例间清空)。"""
    calls: list[str | None] = []

    def fake_build(_request, as_of=None):
        calls.append(as_of.isoformat() if as_of else None)
        return _payload()

    overview.invalidate_overview_cache()
    monkeypatch.setattr(overview, "_build_overview", fake_build)
    yield calls
    overview.invalidate_overview_cache()


@pytest.fixture
def client(built_calls) -> TestClient:
    app = FastAPI()
    app.include_router(overview.router)
    return TestClient(app)


def test_core_slice(client):
    r = client.get("/api/overview/market/core")
    assert r.status_code == 200
    assert set(r.json()) == {"as_of", "quote_status", "indices", "emotion"}
    assert r.json()["indices"][0]["symbol"] == "000001.SH"


def test_breadth_slice(client):
    r = client.get("/api/overview/market/breadth")
    assert r.status_code == 200
    assert set(r.json()) == {
        "as_of", "breadth", "amount", "boards", "distribution",
        "trend", "activity", "radar", "limit",
    }
    assert r.json()["limit"]["max_boards"] == 1


def test_ranks_slice_and_kind(client):
    r = client.get("/api/overview/market/ranks", params={"kind": "gain"})
    assert r.status_code == 200
    assert r.json()["kind"] == "gain"
    assert [row["symbol"] for row in r.json()["rows"]] == ["600000.SH"]

    r = client.get("/api/overview/market/ranks", params={"kind": "amount"})
    assert r.json()["rows"][0]["symbol"] == "600000.SH"

    assert client.get("/api/overview/market/ranks", params={"kind": "bad"}).status_code == 422


def test_heat_slice_and_kind(client):
    r = client.get("/api/overview/market/heat", params={"kind": "concept"})
    assert r.status_code == 200
    assert r.json()["leading"][0]["name"] == "机器人"
    assert r.json()["lagging"] == []

    r = client.get("/api/overview/market/heat", params={"kind": "industry"})
    assert r.json()["leading"] == []

    assert client.get("/api/overview/market/heat", params={"kind": "bad"}).status_code == 422


def test_as_of_passthrough_and_shared_build(client, built_calls):
    client.get("/api/overview/market/core", params={"as_of": "2025-12-31"})
    client.get("/api/overview/market/breadth", params={"as_of": "2025-12-31"})
    client.get("/api/overview/market/ranks", params={"kind": "loss", "as_of": "2025-12-31"})
    assert built_calls == ["2025-12-31"]  # 同一 as_of 只装配一次


def test_legacy_full_endpoint_unchanged(client):
    r = client.get("/api/overview/market")
    assert r.status_code == 200
    assert r.json() == _payload()
