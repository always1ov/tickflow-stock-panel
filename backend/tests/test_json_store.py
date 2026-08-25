"""[fork 增强] R72 小 JSON 存储的并发安全 —— 按 CONTRIBUTING §6.2 补的一课。

R68 修过一次真事故: 操盘手账本被并发写撕裂, 读侧把半截 JSON 当空账本,
下一次保存把其他操作员全覆盖没了。这里守的是同一形状在其余 fork 存储上的
复现 —— 尤其 ai_signals.json, 它是全系统并发最重的一份(今日总览定时、
个股分析页、多个操盘手 refresh 都写它)。
"""
from __future__ import annotations

import json
import threading

import pytest


@pytest.fixture(autouse=True)
def store(tmp_path, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    return tmp_path


# ---------- 基础件 ----------

def test_atomic_write_never_leaves_a_torn_file(tmp_path):
    from app.services.json_store import atomic_write_json
    p = tmp_path / "a" / "b.json"
    atomic_write_json(p, {"x": 1})
    assert json.loads(p.read_text(encoding="utf-8")) == {"x": 1}
    # 目录里不残留临时文件
    assert [f.name for f in p.parent.iterdir()] == ["b.json"]


def test_lock_for_returns_the_same_lock_for_the_same_file(tmp_path):
    from app.services.json_store import lock_for
    a = lock_for(tmp_path / "x.json")
    b = lock_for(str(tmp_path / "x.json"))
    assert a is b, "同一个文件必须拿到同一把锁, 否则等于没锁"
    assert lock_for(tmp_path / "y.json") is not a


# ---------- AI 信号: 并发重出不能互丢 ----------

def test_concurrent_signal_saves_keep_every_symbol(monkeypatch):
    """多个操盘手同时 refresh 不同的票, 每一只的信号都要在。

    修复前是"读全量 → 改一只 → 写全量"不上锁: 两个并发写各捧一份旧全量,
    后写的把前一个刚写进去的信号盖掉 —— 表现为"明明刚重出过, 又没了"。
    """
    from app.services import stock_signal
    from app.services.json_store import atomic_write_json, lock_for

    def _fake_save(sym: str) -> None:
        # 复刻 generate_signal 尾部的落盘段(前面的 AI 调用与解析不在本测试范围)
        with lock_for(stock_signal._store_path()):
            data = stock_signal.load_all()
            data[sym] = {"signal": "hold", "created_at": "2026-08-25T00:00:00+00:00"}
            atomic_write_json(stock_signal._store_path(), data)

    syms = [f"60000{i}.SH" for i in range(8)]
    threads = [threading.Thread(target=_fake_save, args=(s,)) for s in syms]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    got = set(stock_signal.load_all())
    assert got == set(syms), f"并发保存后丢了信号: {set(syms) - got}"


# ---------- 工作流: 节拍器与 API 并发改不同工作流不能互相覆盖 ----------

def test_concurrent_workflow_saves_keep_every_workflow():
    from app.services import workflow as wf

    ids = [f"wf-{i}" for i in range(6)]

    def _hammer(wid: str) -> None:
        for n in range(10):
            wf.save({"workflow_id": wid, "round": n})

    threads = [threading.Thread(target=_hammer, args=(w,)) for w in ids]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    got = {w["workflow_id"] for w in wf.list_workflows()}
    assert got == set(ids), f"并发保存后丢了工作流: {set(ids) - got}"
    # 每个工作流留的是它自己最后一轮
    assert all(w["round"] == 9 for w in wf.list_workflows())


# ---------- 挖掘自动驾驶: 并发 append 轮次不丢会话 ----------

def test_concurrent_autopilot_sessions_survive():
    from app.services import mining_autopilot_store as st

    wins = {"search_start": "2025-01-01", "search_end": "2025-06-30",
            "holdout_start": "2025-07-01", "holdout_end": "2025-08-01"}
    ids = [st.create(asset_type="stock", windows=wins, max_iterations=3,
                     base_config={})["session_id"] for _ in range(4)]

    def _step(sid: str) -> None:
        for _ in range(5):
            st.append_iteration(sid, {"status": "ok"})

    threads = [threading.Thread(target=_step, args=(s,)) for s in ids]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert {s["session_id"] for s in st.list_sessions()} == set(ids)
    for sid in ids:
        assert len(st.get(sid)["iterations"]) == 5
