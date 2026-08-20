"""[fork 增强] R38 自动挖掘的中止与实时进度。

用户实测反馈: 挖掘跑了很久, 界面只有一个转圈图标, 分不清"排队等槽位"、
"正在算"和"真卡死了"; 而且一旦跑起来就没有任何办法停下来。

这里守两件事:
  1. 会话接口要把正在跑那一轮的 run 进度带出来(排队/阶段/百分比/起跑时刻)
  2. 中止要真的把 run 掐掉, 并且把会话收成 stopped —— 不是 failed
"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

import polars as pl
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.mining import router
from app.services import mining_autopilot, mining_autopilot_store
from app.services.mining_jobs import MiningRunStore

BASE = {"asset_type": "stock", "factor_names": ["turnover_rate"], "budget_profile": "balanced"}


class _Repo:
    def __init__(self, data_dir) -> None:
        self.store = SimpleNamespace(data_dir=data_dir)

    @staticmethod
    def get_matrix_data_generation(asset_type="stock"):
        return f"generation-{asset_type}"

    @staticmethod
    def latest_enriched_date(asset_type="stock"):
        del asset_type
        return date(2026, 1, 9)

    @staticmethod
    def get_instruments_asset(asset_type):
        del asset_type
        return pl.DataFrame({"symbol": ["000001.SZ"], "name": ["测试"]})


class _Manager:
    """记下 cancel 被调过没有 —— 中止的核心就是这一下有没有真的发出去。"""

    def __init__(self, data_dir) -> None:
        self.store = MiningRunStore(data_dir)
        self.cancelled: list[str] = []

    def cancel(self, run_id):
        manifest = self.store.get(run_id)
        if manifest is None:
            raise KeyError(run_id)
        self.cancelled.append(run_id)
        return self.store.transition_status(run_id, "cancelled")


@pytest.fixture
def env(tmp_path, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    for i in range(219):
        d = date(2022, 8, 15) + timedelta(days=i)
        part = Path(tmp_path) / "kline_daily_enriched" / f"date={d.isoformat()}"
        part.mkdir(parents=True, exist_ok=True)
        (part / "part.parquet").touch()
    app = FastAPI()
    app.include_router(router)
    app.state.repo = _Repo(tmp_path)
    app.state.mining_manager = _Manager(tmp_path)
    app.state.strategy_engine = SimpleNamespace()
    return TestClient(app), app.state.mining_manager


def _session_with_run(manager, *, status: str = "running", progress: dict | None = None) -> dict:
    """造一个"第 1 轮正在跑"的会话, 并让 run manifest 落到给定状态。"""
    session = mining_autopilot_store.create(
        asset_type="stock",
        windows=mining_autopilot.split_windows(date(2021, 1, 1), date(2026, 8, 20)),
        max_iterations=3, base_config=BASE)
    manifest = manager.store.create(
        {"factor_names": ["turnover_rate"], "strategy_ids": [], "asset_type": "stock",
         "budget_profile": "balanced", "correlation_threshold": 0.75},
        {"generation": "test"}, run_id="run-live")
    run_id = manifest["run_id"]
    manager.store.append_event(run_id, "queued", {"status": "queued", "source": "autopilot"})
    if status != "queued":
        manager.store.transition_status(run_id, "running")
        manager.store.append_event(run_id, "running", {"status": "running"})
    if progress is not None:
        manager.store.write_summary(run_id, {"progress": progress})
    mining_autopilot_store.append_iteration(
        session["session_id"],
        {"config": dict(BASE), "run_id": run_id,
         "status": "queued" if status == "queued" else "running",
         "candidates": [], "ai": None})
    return mining_autopilot_store.get(session["session_id"])


# ---------- 实时进度 ----------

def test_running_iteration_carries_live_progress(env):
    """转圈图标之外必须给得出"在算什么、算到哪了" —— 否则没法判断是不是卡了。"""
    client, manager = env
    s = _session_with_run(manager, progress={"phase": "outer_fold", "label": "第 3/8 折", "percent": 37.5})
    body = client.get("/api/backtest/mining/autopilot/sessions").json()
    live = body["items"][0]["iterations"][-1]["live"]
    assert live["status"] == "running"
    assert live["progress"]["percent"] == 37.5
    assert live["progress"]["label"] == "第 3/8 折"
    assert live["started_at"], "起跑时刻要有, 界面靠它算已跑多久"
    assert s["status"] == "open"


def test_queued_run_is_distinguishable_from_running(env):
    """排队等槽位和正在算长得一样的话, 用户只会以为它死了。"""
    client, manager = env
    _session_with_run(manager, status="queued")
    body = client.get("/api/backtest/mining/autopilot/sessions").json()
    live = body["items"][0]["iterations"][-1]["live"]
    assert live["status"] == "queued"
    assert live["queued_at"], "排队中要能显示已经等了多久"


def test_progress_missing_does_not_break_the_endpoint(env):
    """worker 还没吐过进度是常态, 不能因此让整个会话列表挂掉。"""
    client, manager = env
    _session_with_run(manager, progress=None)
    body = client.get("/api/backtest/mining/autopilot/sessions").json()
    assert body["items"][0]["iterations"][-1]["live"]["progress"] is None


def test_finished_iteration_gets_no_live_block(env):
    """跑完的轮次不该再挂实时块 —— 那是每次请求都白读一遍 manifest。"""
    client, manager = env
    s = _session_with_run(manager)
    s["iterations"][-1]["status"] = "succeeded"
    mining_autopilot_store._replace(s)
    body = client.get("/api/backtest/mining/autopilot/sessions").json()
    assert "live" not in body["items"][0]["iterations"][-1]


# ---------- 中止 ----------

def test_stop_cancels_the_running_run_and_closes_session(env):
    client, manager = env
    s = _session_with_run(manager)
    sid = s["session_id"]
    res = client.post(f"/api/backtest/mining/autopilot/sessions/{sid}/stop").json()
    assert manager.cancelled == ["run-live"], "没把正在跑的 run 掐掉, 中止就是假的"
    assert res["session"]["status"] == "stopped"
    assert manager.store.get("run-live")["status"] == "cancelled"


def test_stop_marks_the_iteration_cancelled_so_step_does_not_wait_forever(env):
    """会话档案里那一轮不同步落成 cancelled 的话, 下次 step 还以为它在跑。"""
    client, manager = env
    s = _session_with_run(manager)
    client.post(f"/api/backtest/mining/autopilot/sessions/{s['session_id']}/stop")
    stored = mining_autopilot_store.get(s["session_id"])
    assert stored["iterations"][-1]["status"] == "cancelled"


def test_stop_is_idempotent_and_preserves_a_finished_session(env):
    """重复点不能把已经跑出来的结果抹掉。"""
    client, manager = env
    s = _session_with_run(manager)
    sid = s["session_id"]
    mining_autopilot_store.set_status(sid, "satisfied", winner={"name": "赢家"})
    res = client.post(f"/api/backtest/mining/autopilot/sessions/{sid}/stop").json()
    assert res["session"]["status"] == "satisfied"
    assert res["session"]["winner"] == {"name": "赢家"}
    assert manager.cancelled == [], "已收工的会话不该再去 cancel 一个 run"


def test_stop_without_an_active_run_still_closes_the_session(env):
    """AI 正在想下一轮配置(没有 run 在跑)时点中止, 也得能停。"""
    client, manager = env
    session = mining_autopilot_store.create(
        asset_type="stock",
        windows=mining_autopilot.split_windows(date(2021, 1, 1), date(2026, 8, 20)),
        max_iterations=3, base_config=BASE)
    res = client.post(
        f"/api/backtest/mining/autopilot/sessions/{session['session_id']}/stop").json()
    assert res["session"]["status"] == "stopped"
    assert manager.cancelled == []


def test_stop_on_unknown_session_is_404(env):
    client, _ = env
    assert client.post("/api/backtest/mining/autopilot/sessions/nope/stop").status_code == 404
