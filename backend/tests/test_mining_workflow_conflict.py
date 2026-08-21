"""[fork 增强] R53 工作流与「AI 自动挖掘」不能同时在挖。

两者不是并列关系: 工作流的一次"重开"**就是**开一个自动挖掘会话(见
``workflow_drivers.MiningDriver``)。但界面上它们是两块并排的面板, 什么都拦不住
用户在工作流跑着的时候再手动开一个 —— 于是有两处真会出事:

  1. **两路一起挖**。挖掘是重活, heavy_job_limiter 容量 2 而一个挖掘 run 独占
     两格。再开一路不会更快, 它只会静默排队 —— 界面上看着就是"跑了很久没动静",
     正是之前那个"是不是卡死了"的来源。
  2. **两边推同一个状态机**。工作流开的会话照样出现在自动挖掘面板里(面板默认
     跟随最新会话), 用户对它按「AI 再调一轮」, 就和后台节拍同时 step 同一个
     会话, 轮次会错乱 —— 两边都以为自己开的是第 N 轮。

所以: 有挖掘工作流在跑时不给手动开会话; 有主的会话不给手动推进/中止。
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
from app.services import mining_autopilot, mining_autopilot_store, workflow

BASE = {"asset_type": "stock", "factor_names": ["turnover_rate"], "budget_profile": "balanced"}
_START = {"asset_type": "stock", "start": "2022-08-15", "end": "2026-01-09",
          "holdout_days": 365, "budget_profile": "balanced", "max_iterations": 3}


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
def client(tmp_path, monkeypatch):
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
    app.state.mining_manager = SimpleNamespace(store=SimpleNamespace(get=lambda _r: None))
    app.state.strategy_engine = SimpleNamespace()
    return TestClient(app)


def _session(owner: str | None = None) -> dict:
    return mining_autopilot_store.create(
        asset_type="stock",
        windows=mining_autopilot.split_windows(date(2021, 1, 1), date(2026, 8, 20)),
        max_iterations=3, base_config=BASE, owner_workflow_id=owner)


# ---------- 工作流跑着时不给手动开 ----------

def test_cannot_start_a_manual_session_while_a_mining_workflow_runs(client):
    workflow.create(kind=workflow.KIND_MINING, config={"asset_type": "stock"})
    r = client.post("/api/backtest/mining/autopilot/sessions", json=_START)
    assert r.status_code == 409
    detail = r.json()["detail"]
    # 光说"不行"没用 —— 要说清为什么(不会更快, 只会排队)和怎么办(先停工作流)
    assert "排队" in detail and "停掉" in detail


# 下面两条只关心**这道闸有没有误伤**, 所以断言的是"不是 409"而不是 200 ——
# 这个测试环境的 enriched 日历撑不起一个合格的搜索窗口, 放行之后照样会被数据
# 预检拦成 400。把它写成 200 等于让这条测试去守别人的事。

def test_a_stopped_workflow_no_longer_blocks_manual_mining(client):
    wf = workflow.create(kind=workflow.KIND_MINING, config={"asset_type": "stock"})
    workflow.stop(wf["workflow_id"])
    assert client.post("/api/backtest/mining/autopilot/sessions", json=_START).status_code != 409


def test_a_backtest_workflow_does_not_block_mining(client):
    """回测工作流不碰挖掘那条路 —— 挡它是无谓地把人挡在门外。"""
    workflow.create(kind=workflow.KIND_BACKTEST, config={"symbol": "000001.SZ"})
    assert client.post("/api/backtest/mining/autopilot/sessions", json=_START).status_code != 409


# ---------- 有主的会话只能由主人推 ----------

def test_workflow_owned_session_rejects_manual_step(client):
    """界面和后台节拍同时 step 同一个状态机, 两边都会以为自己开的是第 N 轮。"""
    s = _session(owner="wf-abc")
    r = client.post(f"/api/backtest/mining/autopilot/sessions/{s['session_id']}/step")
    assert r.status_code == 409
    assert "wf-abc" in r.json()["detail"]


def test_workflow_owned_session_rejects_manual_stop(client):
    """单停会话没用 —— 工作流会当成这次重开结束了, 转头再开一个。"""
    s = _session(owner="wf-abc")
    r = client.post(f"/api/backtest/mining/autopilot/sessions/{s['session_id']}/stop")
    assert r.status_code == 409
    assert "停那个工作流" in r.json()["detail"]


def test_an_ownerless_session_is_still_fully_manual(client):
    """手动开的会话一切照旧 —— 这次改动不该动手动那条路。"""
    s = _session()
    assert s["owner_workflow_id"] is None
    r = client.post(f"/api/backtest/mining/autopilot/sessions/{s['session_id']}/stop")
    assert r.status_code == 200


def test_the_owner_is_visible_to_the_ui(client):
    """界面要据此禁用手动按钮并说明是谁在跑, 所以这个字段必须出现在列表响应里。"""
    _session(owner="wf-abc")
    items = client.get("/api/backtest/mining/autopilot/sessions").json()["items"]
    assert items and items[0]["owner_workflow_id"] == "wf-abc"


# ---------- driver 确实会认领 ----------

def test_the_mining_driver_claims_the_session_it_opens():
    """认领这一步漏了的话, 上面所有拦截都形同虚设 —— 工作流开的会话看起来
    和手动开的一模一样。"""
    import inspect

    from app.services.workflow_drivers import MiningDriver

    src = inspect.getsource(MiningDriver.advance)
    assert "owner_workflow_id=str(wf[\"workflow_id\"])" in src


# ---------- 另一半: 手动会话开着时不给起工作流 ----------

def _wf_client(tmp_path):
    from fastapi import FastAPI

    from app.api.workflows import router as wf_router
    app = FastAPI()
    app.include_router(wf_router)
    app.state.repo = _Repo(tmp_path)
    return TestClient(app)


_WF_BODY = {"kind": "mining", "config": {"asset_type": "stock",
            "start": "2022-08-15", "end": "2026-01-09"}}


def test_cannot_start_a_mining_workflow_while_a_manual_session_is_open(tmp_path, monkeypatch):
    """闸要两边都装。只挡一边的话, 换个顺序照样能把两路挖掘同时开起来。"""
    from app.config import settings
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    _session()
    r = _wf_client(tmp_path).post("/api/workflows", json=_WF_BODY)
    assert r.status_code == 409
    assert "一次只跑得动一路" in r.json()["detail"]


def test_a_finished_manual_session_does_not_block_the_workflow(tmp_path, monkeypatch):
    """收工的会话不占坑 —— 否则跑过一次之后就再也起不了工作流了。"""
    from app.config import settings
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    s = _session()
    mining_autopilot_store.set_status(s["session_id"], "stopped")
    assert _wf_client(tmp_path).post("/api/workflows", json=_WF_BODY).status_code != 409


def test_a_workflow_owned_session_does_not_block_a_new_workflow(tmp_path, monkeypatch):
    """有主的会话不算"手动会话" —— 它本来就是工作流自己开的, 拿它挡工作流
    等于让工作流把自己锁死(重启接着跑那条路会第一时间撞上)。"""
    from app.config import settings
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    _session(owner="wf-abc")
    assert _wf_client(tmp_path).post("/api/workflows", json=_WF_BODY).status_code != 409
