"""[fork 增强] R55 挖掘/回测的历史记录可删。

三处历史原来都只进不出: 工作流(两页共用)、自动挖掘会话、挖掘运行。攒久了列表
全是没用的失败记录, 而挖掘运行还各自带一个产物目录, 是真占盘。

删除这件事只有一条规则要守: **正在跑的不给删**。三处的原因是同一个 ——
删的是记录, 跑的那一路并不知道, 于是:
  · 工作流: 后台节拍下一拍又把它写回来, 看上去就是"删不掉";
  · 会话: 正在跑的那一轮没人收尾;
  · 运行: worker 还在往那个目录里写, 删掉后它会把目录重建成半个残骸,
    之后列表里就是一条读不出来的记录。
所以三处都是"先停/先取消, 再删", 两步分开也更难误删正在出成绩的那条。
"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

import polars as pl
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.services import mining_autopilot, mining_autopilot_store, workflow
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


@pytest.fixture
def env(tmp_path, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    for i in range(219):
        d = date(2022, 8, 15) + timedelta(days=i)
        part = Path(tmp_path) / "kline_daily_enriched" / f"date={d.isoformat()}"
        part.mkdir(parents=True, exist_ok=True)
        (part / "part.parquet").touch()

    from app.api.mining import router as mining_router
    from app.api.workflows import router as wf_router
    app = FastAPI()
    app.include_router(mining_router)
    app.include_router(wf_router)
    app.state.repo = _Repo(tmp_path)
    app.state.mining_manager = SimpleNamespace(store=MiningRunStore(tmp_path))
    app.state.strategy_engine = SimpleNamespace()
    return TestClient(app), app.state.mining_manager.store


def _session(owner: str | None = None, status: str = "stopped") -> dict:
    s = mining_autopilot_store.create(
        asset_type="stock",
        windows=mining_autopilot.split_windows(date(2021, 1, 1), date(2026, 8, 20)),
        max_iterations=3, base_config=BASE, owner_workflow_id=owner)
    if status != "open":
        mining_autopilot_store.set_status(s["session_id"], status)
    return mining_autopilot_store.get(s["session_id"])


def _run(store: MiningRunStore, *, status: str = "succeeded") -> str:
    m = store.create({"factor_names": ["turnover_rate"], "strategy_ids": [], "asset_type": "stock",
                      "budget_profile": "balanced", "correlation_threshold": 0.75},
                     {"generation": "test"})
    run_id = str(m["run_id"])
    if status != "queued":
        store.transition_status(run_id, "running")
    if status not in ("queued", "running"):
        store.transition_status(run_id, status)
    return run_id


# ---------- 工作流 ----------

def test_delete_removes_a_finished_workflow(env):
    client, _ = env
    wf = workflow.create(kind=workflow.KIND_MINING, config={"asset_type": "stock"})
    workflow.stop(wf["workflow_id"])
    assert client.delete(f"/api/workflows/{wf['workflow_id']}").status_code == 200
    assert workflow.get(wf["workflow_id"]) is None


def test_a_running_workflow_cannot_be_deleted(env):
    """后台节拍还在推它 —— 记录删了下一拍又写回来, 表现是"删不掉"。"""
    client, _ = env
    wf = workflow.create(kind=workflow.KIND_MINING, config={"asset_type": "stock"})
    r = client.delete(f"/api/workflows/{wf['workflow_id']}")
    assert r.status_code == 409 and "先中止" in r.json()["detail"]
    assert workflow.get(wf["workflow_id"]) is not None, "拒绝之后记录必须原样还在"


def test_deleting_a_missing_workflow_is_a_404(env):
    client, _ = env
    assert client.delete("/api/workflows/nope").status_code == 404


def test_deleting_one_workflow_leaves_the_others(env):
    client, _ = env
    keep = workflow.create(kind=workflow.KIND_BACKTEST, config={})
    drop = workflow.create(kind=workflow.KIND_MINING, config={})
    workflow.stop(drop["workflow_id"])
    client.delete(f"/api/workflows/{drop['workflow_id']}")
    assert workflow.get(keep["workflow_id"]) is not None


# ---------- 自动挖掘会话 ----------

def test_delete_removes_a_finished_session(env):
    client, _ = env
    s = _session()
    assert client.delete(f"/api/backtest/mining/autopilot/sessions/{s['session_id']}").status_code == 200
    assert mining_autopilot_store.get(s["session_id"]) is None


def test_an_open_session_cannot_be_deleted(env):
    """正在跑的那一轮没人收尾 —— 先中止。"""
    client, _ = env
    s = _session(status="open")
    r = client.delete(f"/api/backtest/mining/autopilot/sessions/{s['session_id']}")
    assert r.status_code == 409 and "先中止" in r.json()["detail"]
    assert mining_autopilot_store.get(s["session_id"]) is not None


def test_a_workflow_owned_session_cannot_be_deleted_on_its_own(env):
    """[R53] 它是工作流的一次"重开", 工作流还要靠这条记录接着推。"""
    client, _ = env
    s = _session(owner="wf-abc", status="stopped")
    r = client.delete(f"/api/backtest/mining/autopilot/sessions/{s['session_id']}")
    assert r.status_code == 409 and "wf-abc" in r.json()["detail"]


def test_deleting_a_missing_session_is_a_404(env):
    client, _ = env
    assert client.delete("/api/backtest/mining/autopilot/sessions/nope").status_code == 404


# ---------- 挖掘运行 ----------

def test_delete_removes_the_run_and_its_whole_directory(env):
    """产物目录才是真占盘的那部分 —— 只摘掉 manifest 等于假删。"""
    client, store = env
    run_id = _run(store)
    run_dir = store.runs_root / run_id
    assert run_dir.exists()
    assert client.delete(f"/api/backtest/mining/runs/{run_id}").status_code == 200
    assert not run_dir.exists()
    assert store.get(run_id) is None


@pytest.mark.parametrize("status", ["queued", "running"])
def test_an_active_run_cannot_be_deleted(env, status):
    """worker 还在往那个目录里写 —— 删掉后它会把目录重建成半个残骸,
    之后列表里就是一条读不出来的记录。"""
    client, store = env
    run_id = _run(store, status=status)
    r = client.delete(f"/api/backtest/mining/runs/{run_id}")
    assert r.status_code == 409 and "先取消" in r.json()["detail"]
    assert store.get(run_id) is not None


def test_deleted_runs_leave_the_listing_readable(env):
    """删完之后 list_runs 还得扫得动 —— 留下半个目录的话这里会炸或者少一条。"""
    client, store = env
    keep, drop = _run(store), _run(store)
    client.delete(f"/api/backtest/mining/runs/{drop}")
    ids = [r["run_id"] for r in store.list_runs(limit=50)]
    assert ids == [keep]


def test_deleting_a_missing_run_is_a_404(env):
    client, _ = env
    assert client.delete("/api/backtest/mining/runs/deadbeefdeadbeef").status_code == 404


def test_a_bogus_run_id_cannot_reach_outside_the_runs_root(env):
    """run_id 直接拼进路径, 删除是破坏性操作 —— 这条越界检查必须有。"""
    client, store = env
    before = list(store.runs_root.parent.iterdir())
    r = client.delete("/api/backtest/mining/runs/..%2F..%2Fetc")
    assert r.status_code in (400, 404)
    assert list(store.runs_root.parent.iterdir()) == before
