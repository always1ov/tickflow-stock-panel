"""[fork 增强] R39 工作流的执行器与 HTTP 入口。

这里守的是"工作流跑出来的东西和手动跑出来的是同一套口径": 回测 driver 必须
把 AI 给的配置真的灌进回测入口, 账户事实(费率/初始资金/撮合)必须原样透传、
AI 碰不到。以及 —— 手动路径一行没动。
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.workflows import router
from app.services import workflow as wf_mod
from app.services.workflow_drivers import BacktestDriver, _backtest_best, _mining_best


class _Engine:
    @staticmethod
    def list_strategies():
        return [
            {"id": "ma_cross", "name": "均线交叉", "asset_types": ["stock"]},
            {"id": "etf_only", "name": "只给ETF", "asset_types": ["etf"]},
            {"id": "lab", "name": "研究用", "asset_types": ["stock"], "research_only": True},
        ]


@pytest.fixture
def env(tmp_path, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    app = FastAPI()
    app.include_router(router)
    app.state.strategy_engine = _Engine()
    app.state.repo = SimpleNamespace(store=SimpleNamespace(data_dir=tmp_path))
    return TestClient(app)


# ---------- 回测执行器 ----------

def _driver(monkeypatch, *, plans, runs):
    """把 AI 与真回测都换成打桩 —— 测编排, 不测回测引擎。"""
    from app.services import backtest_autopilot as bp

    async def fake_plan(**_kw):
        return plans.pop(0)

    monkeypatch.setattr(bp, "next_plan", fake_plan)
    d = BacktestDriver(engine=_Engine(), data_dir="/tmp")
    d._run_once = lambda plan, cfg: runs.pop(0)  # noqa: SLF001
    return d


def _advance(driver, wf):
    return asyncio.run(driver.advance(wf))


def _plan(**over):
    return {"satisfied": False, "note": "试试", "conclusion": None,
            "next": {"strategy_id": "ma_cross", "regime_states": [], "max_positions": 10,
                     "max_exposure_pct": 100, "days": 730, "holding_days": 5,
                     "position_sizing": "equal", **over}}


def _stats(**over):
    return {"stats": {"total_return": 0.4, "annual_return": 0.2, "sharpe": 1.1,
                      "max_drawdown": -0.12, "win_rate": 0.55, "n_trades": 80,
                      "avg_duration": 6, **over}}


def test_backtest_driver_runs_a_round_and_reports_it(env, monkeypatch):
    d = _driver(monkeypatch, plans=[_plan()], runs=[_stats()])
    wf = wf_mod.create(kind="backtest", config={"asset_type": "stock"},
                       budget={"rounds_per_attempt": 3})
    out = _advance(d, wf)
    assert out["action"] == "round_done"
    assert out["best"]["passed"] is True and out["best"]["sharpe"] == 1.1
    assert wf["current"]["rounds"][0]["config"]["strategy_id"] == "ma_cross"


def test_backtest_driver_ends_the_attempt_when_rounds_run_out(env, monkeypatch):
    d = _driver(monkeypatch, plans=[_plan(), _plan()],
                runs=[_stats(n_trades=3), _stats(n_trades=4)])
    wf = wf_mod.create(kind="backtest", config={}, budget={"rounds_per_attempt": 2})
    assert _advance(d, wf)["action"] == "round_done"
    out = _advance(d, wf)
    assert out["action"] == "attempt_done" and out["outcome"] == "exhausted"


def test_backtest_driver_ends_early_when_ai_is_satisfied(env, monkeypatch):
    d = _driver(monkeypatch,
                plans=[_plan(), {"satisfied": True, "note": "够了", "conclusion": "行", "next": None}],
                runs=[_stats()])
    wf = wf_mod.create(kind="backtest", config={}, budget={"rounds_per_attempt": 5})
    _advance(d, wf)
    out = _advance(d, wf)
    assert out["action"] == "attempt_done" and out["outcome"] == "satisfied"
    assert out["detail"]["conclusion"] == "行"


def test_backtest_driver_surfaces_ai_errors_instead_of_crashing(env, monkeypatch):
    d = _driver(monkeypatch, plans=[{"error": "未配置 AI"}], runs=[])
    out = _advance(d, wf_mod.create(kind="backtest", config={}))
    assert out["action"] == "error" and "未配置 AI" in out["message"]


def test_backtest_driver_only_offers_strategies_for_the_asset(env):
    d = BacktestDriver(engine=_Engine(), data_dir="/tmp")
    ids = {s["id"] for s in d._strategies("stock")}  # noqa: SLF001
    assert ids == {"ma_cross"}, "research_only 与不支持该品种的都不该进 AI 的候选清单"


def test_account_facts_are_passed_through_not_invented(env, monkeypatch):
    """费率/初始资金/撮合是用户的账户事实 —— 工作流原样透传, AI 碰不到。"""
    seen = {}
    from app.backtest import strategy as strat_mod

    class _Cfg:
        def __init__(self, **kw):
            seen.update(kw)

    monkeypatch.setattr(strat_mod, "StrategyBacktestConfig", _Cfg)
    monkeypatch.setattr("app.backtest.worker.make_worker_task", lambda *a, **k: object())
    monkeypatch.setattr("app.backtest.worker.run_worker_task", lambda *a, **k: _stats())

    d = BacktestDriver(engine=_Engine(), data_dir="/tmp")
    d._run_once(_plan()["next"], {  # noqa: SLF001
        "asset_type": "stock", "commission_pct": 0.0009, "stamp_tax_pct": 0.001,
        "slippage_bps": 20, "initial_capital": 250000, "matching": "close",
        "end": "2026-01-05",
    })
    assert seen["commission_pct"] == 0.0009
    assert seen["initial_capital"] == 250000
    assert seen["matching"] == "close"
    assert seen["max_exposure_pct"] == 1.0, "百分比要换算成小数, 不然仓位放大 100 倍"
    assert seen["strategy_id"] == "ma_cross"


# ---------- 成绩单归一 ----------

def test_mining_best_reads_the_winner():
    best = _mining_best({"session_id": "s1", "winner": {
        "name": "因子组合", "达标": True, "样本外Sharpe": 0.9, "run_id": "r1"}})
    assert best["passed"] is True and best["sharpe"] == 0.9 and best["kind"] == "mining"


def test_best_helpers_tolerate_missing_numbers():
    assert _mining_best({"winner": None}) is None
    assert _backtest_best(None) is None
    b = _backtest_best({"passed": False, "config": {}, "digest": {"夏普": None}})
    assert b["sharpe"] is None, "没有成交时夏普是 None, 不能硬转成 0"


# ---------- HTTP ----------

def test_create_and_list_a_backtest_workflow(env):
    res = env.post("/api/workflows", json={"kind": "backtest", "config": {"asset_type": "stock"},
                                           "max_attempts": 3, "max_hours": 2})
    assert res.status_code == 200
    wf = res.json()
    assert wf["status"] == "running" and wf["budget"]["max_attempts"] == 3
    assert wf["progress_text"] == "第 0/3 次重开 · 累计 0 轮"
    assert env.get("/api/workflows").json()["items"][0]["workflow_id"] == wf["workflow_id"]


def test_list_can_filter_by_kind(env):
    env.post("/api/workflows", json={"kind": "backtest", "config": {}})
    assert env.get("/api/workflows", params={"kind": "mining"}).json()["items"] == []
    assert len(env.get("/api/workflows", params={"kind": "backtest"}).json()["items"]) == 1


def test_create_allows_an_asset_that_has_strategies(env):
    res = env.post("/api/workflows", json={"kind": "backtest", "config": {"asset_type": "etf"}})
    assert res.status_code == 200


def test_create_rejects_an_asset_with_no_usable_strategy(env):
    """建的时候就该发现没策略可跑, 而不是让它在后台连错三次才停。"""
    env.app.state.strategy_engine = SimpleNamespace(
        list_strategies=lambda: [{"id": "lab", "asset_types": ["stock"], "research_only": True}])
    res = env.post("/api/workflows", json={"kind": "backtest", "config": {"asset_type": "stock"}})
    assert res.status_code == 400 and "没有可用策略" in res.json()["detail"]


def test_create_rejects_a_backwards_date_range(env):
    res = env.post("/api/workflows", json={
        "kind": "backtest", "config": {"start": "2026-01-01", "end": "2025-01-01"}})
    assert res.status_code == 400 and "早于" in res.json()["detail"]


def test_create_rejects_a_bad_date(env):
    res = env.post("/api/workflows", json={
        "kind": "backtest", "config": {"end": "去年"}})
    assert res.status_code == 400


def test_stop_closes_it_and_is_idempotent(env):
    wid = env.post("/api/workflows", json={"kind": "backtest", "config": {}}).json()["workflow_id"]
    first = env.post(f"/api/workflows/{wid}/stop").json()
    assert first["status"] == "stopped" and first["overfit_note"]
    again = env.post(f"/api/workflows/{wid}/stop").json()
    assert again["finished_at"] == first["finished_at"]


def test_unknown_workflow_is_404(env):
    assert env.get("/api/workflows/nope").status_code == 404
    assert env.post("/api/workflows/nope/stop").status_code == 404
    assert env.post("/api/workflows/nope/tick").status_code == 404


def test_manual_tick_advances_without_the_background_runner(env, monkeypatch):
    """节拍器没起来的环境里(比如测试、或启动失败降级), 工作流仍然能用。"""
    from app.services import backtest_autopilot as bp

    async def fake_plan(**_kw):
        return {"error": "未配置 AI"}

    monkeypatch.setattr(bp, "next_plan", fake_plan)
    wid = env.post("/api/workflows", json={"kind": "backtest", "config": {}}).json()["workflow_id"]
    out = env.post(f"/api/workflows/{wid}/tick").json()
    assert out["ledger"]["errors_in_a_row"] == 1
    assert out["status"] == "running", "一次 AI 失败不判死, 连着三次才收"
