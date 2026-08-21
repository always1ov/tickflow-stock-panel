"""[fork 增强] R39 研究工作流的状态机与账本。

工作流会在后台无人看管地跑好几个小时, 所以最要紧的不变量是"它一定会停":
达标停、次数用完停、时间到停、连着出错停。任何一条漏掉, 用户睡一觉起来
机器已经烧了一整夜。
"""
from __future__ import annotations

import asyncio

import pytest

from app.services import workflow as wf_mod


@pytest.fixture
def store(tmp_path, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    return wf_mod


def _wf(store, **budget):
    return store.create(kind="backtest", config={"asset_type": "stock"},
                        budget={"max_attempts": 3, "rounds_per_attempt": 2,
                                "max_hours": 1, **budget}, now_ts=1000.0)


# ---------- 预算 ----------

def test_budget_is_clamped_into_range(store):
    b = store.normalize_budget({"max_attempts": 9999, "rounds_per_attempt": 0,
                                "max_hours": -5}, now_ts=0)
    assert b["max_attempts"] == store.MAX_ATTEMPTS_CAP
    assert b["rounds_per_attempt"] == 1
    assert b["max_hours"] == 0.1


def test_budget_stores_absolute_deadline_not_duration(store):
    """存时长的话每次重启都等于重新计时, 一个"最多 6 小时"能跑好几天。"""
    b = store.normalize_budget({"max_hours": 2}, now_ts=1000.0)
    assert b["deadline_ts"] == pytest.approx(1000.0 + 7200)


def test_budget_survives_garbage(store):
    b = store.normalize_budget({"max_attempts": "很多", "max_hours": None}, now_ts=0)
    assert b["max_attempts"] == store.DEFAULT_MAX_ATTEMPTS
    assert b["max_hours"] == store.DEFAULT_MAX_HOURS


# ---------- 一定会停 ----------

def test_stops_the_moment_it_passes(store):
    """达标优先于一切预算 —— 已经跑出结果了还接着抽, 只会让账更难看。"""
    w = _wf(store)
    w["best"] = {"passed": True, "sharpe": 1.2}
    go, reason = store.should_continue(w, now_ts=1000.0)
    assert go is False and reason == store.STOP_SATISFIED


def test_stops_when_attempts_run_out(store):
    w = _wf(store)
    w["ledger"]["attempts"] = 3
    go, reason = store.should_continue(w, now_ts=1000.0)
    assert go is False and reason == store.STOP_ATTEMPTS


def test_stops_when_deadline_passes(store):
    w = _wf(store)
    go, reason = store.should_continue(w, now_ts=1000.0 + 3600 + 1)
    assert go is False and reason == store.STOP_DEADLINE


def test_stops_after_consecutive_errors(store):
    """AI 没配好/额度用完时不能让它空转一整夜。"""
    w = _wf(store)
    for _ in range(store.MAX_CONSECUTIVE_ERRORS):
        store.note_error(w, "未配置 AI")
    go, reason = store.should_continue(w, now_ts=1000.0)
    assert go is False and reason == store.STOP_ERROR


def test_a_good_round_clears_the_error_streak(store):
    """偶发一次超时不该把额度算进"连击"里。"""
    w = _wf(store)
    store.note_error(w, "超时")
    store.note_error(w, "超时")
    store.note_round(w)
    assert w["ledger"]["errors_in_a_row"] == 0
    assert store.should_continue(w, now_ts=1000.0)[0] is True


def test_closed_workflow_never_restarts(store):
    w = _wf(store)
    store.finish(w, store.STOP_MANUAL)
    assert store.should_continue(w, now_ts=1000.0)[0] is False


# ---------- 跨重开挑最好的 ----------

def test_passing_beats_higher_sharpe(store):
    best = store.merge_best({"passed": False, "sharpe": 9.0}, {"passed": True, "sharpe": 0.6})
    assert best["passed"] is True


def test_higher_sharpe_wins_within_the_same_tier(store):
    best = store.merge_best({"passed": True, "sharpe": 0.6}, {"passed": True, "sharpe": 1.4})
    assert best["sharpe"] == 1.4


def test_merge_best_survives_none_sharpe(store):
    """回测没有成交时夏普是 None, 拿它跟数字比会炸。"""
    assert store.merge_best({"passed": False, "sharpe": None},
                            {"passed": False, "sharpe": 0.2})["sharpe"] == 0.2
    assert store.merge_best(None, {"passed": False, "sharpe": None})["sharpe"] is None
    assert store.merge_best({"passed": True, "sharpe": 1.0}, None)["sharpe"] == 1.0


# ---------- 抽卡账本 ----------

def test_overfit_note_scales_with_how_much_was_tried(store):
    few = store.overfit_note(1, 3)
    many = store.overfit_note(9, 54)
    assert "3 轮" in few
    assert "54 轮" in many and "没有信息量" in many
    assert "终检窗口" in few and "终检窗口" in many, "两种情况都要把人指回唯一算数的那个数字"


def test_finish_writes_the_ledger_conclusion(store):
    w = _wf(store)
    w["ledger"]["rounds"] = 7
    w["ledger"]["attempts"] = 2
    store.finish(w, store.STOP_ATTEMPTS)
    assert w["status"] == store.STATUS_EXHAUSTED
    assert w["stop_reason_cn"] == "重开次数用完了"
    assert "7 轮" in w["overfit_note"]
    assert w["finished_at"]


# ---------- 持久化 ----------

def test_create_list_get_roundtrip(store):
    w = _wf(store)
    assert store.get(w["workflow_id"])["kind"] == "backtest"
    assert [x["workflow_id"] for x in store.list_workflows()] == [w["workflow_id"]]
    assert len(store.running_workflows()) == 1


def test_stop_is_idempotent(store):
    w = _wf(store)
    store.stop(w["workflow_id"])
    first = store.get(w["workflow_id"])["finished_at"]
    store.stop(w["workflow_id"])
    assert store.get(w["workflow_id"])["finished_at"] == first, "重复中止不该改写收工时间"


def test_unknown_kind_is_rejected(store):
    with pytest.raises(ValueError):
        store.create(kind="占卜", config={})


# ---------- 推进 ----------

class _Driver:
    """打桩执行器: 按脚本一格一格返回, 不真跑任何东西。"""

    def __init__(self, script):
        self.script = list(script)
        self.calls = 0

    async def advance(self, wf):
        self.calls += 1
        return self.script.pop(0) if self.script else {"action": "running"}


def _tick(w, driver, now_ts=1000.0):
    """墙钟注入 —— 否则预算里那个绝对截止时刻永远已经过期, 每一格都直接收工。"""
    return asyncio.run(wf_mod.tick(w, drivers={"backtest": driver}, now_ts=now_ts))


def test_tick_counts_rounds(store):
    w = _wf(store)
    d = _Driver([{"action": "round_done", "best": {"passed": False, "sharpe": 0.3}}])
    w = _tick(w, d)
    assert w["ledger"]["rounds"] == 1
    assert w["best"]["sharpe"] == 0.3
    assert w["status"] == store.STATUS_RUNNING


def test_tick_closes_immediately_on_a_passing_result(store):
    """达标那一格就该收工, 不能再多抽一次。"""
    w = _wf(store)
    d = _Driver([{"action": "attempt_done", "outcome": "satisfied",
                  "best": {"passed": True, "sharpe": 1.1}}])
    w = _tick(w, d)
    assert w["status"] == store.STATUS_SATISFIED
    assert w["stop_reason"] == store.STOP_SATISFIED
    assert w["overfit_note"], "收工必须带上抽了多少次的账"


def test_tick_archives_each_attempt(store):
    w = _wf(store)
    w = _tick(w, _Driver([{"action": "attempt_done", "outcome": "exhausted",
                           "best": {"passed": False, "sharpe": 0.1},
                           "detail": {"rounds": 2}}]))
    assert w["attempts"][0]["outcome"] == "exhausted"
    assert w["attempts"][0]["rounds"] == 2
    assert w["current"] is None, "归档后要清空, 好开下一次"


def test_tick_stops_after_the_attempt_budget(store):
    """无人看管的东西必须自己停下来。"""
    w = _wf(store)
    d = _Driver([])
    for _ in range(10):
        w["ledger"]["attempts"] = min(3, w["ledger"]["attempts"] + 1)
        w = _tick(w, d)
        if w["status"] != store.STATUS_RUNNING:
            break
    assert w["status"] == store.STATUS_EXHAUSTED


def test_driver_exception_does_not_kill_the_workflow(store):
    class _Boom:
        async def advance(self, wf):
            raise RuntimeError("回测炸了")

    w = _tick(_wf(store), _Boom())
    assert w["status"] == store.STATUS_RUNNING, "一次异常只记一次连击, 不是立刻判死"
    assert "回测炸了" in w["ledger"]["last_error"]


def test_repeated_driver_exceptions_eventually_stop_it(store):
    class _Boom:
        async def advance(self, wf):
            raise RuntimeError("AI 额度用完了")

    w = _wf(store)
    for _ in range(store.MAX_CONSECUTIVE_ERRORS + 1):
        w = _tick(w, _Boom())
    assert w["status"] == store.STATUS_FAILED


def test_missing_driver_closes_instead_of_looping(store):
    w = asyncio.run(wf_mod.tick(_wf(store), drivers={}, now_ts=1000.0))
    assert w["status"] == store.STATUS_FAILED
    assert "执行器" in w["ledger"]["last_error"]


def test_progress_text_reads_like_a_human_wrote_it(store):
    w = _wf(store)
    w["ledger"].update({"attempts": 2, "rounds": 5})
    assert store.progress_text(w) == "第 2/3 次重开 · 累计 5 轮"
    store.finish(w, store.STOP_SATISFIED)
    assert "跑出达标结果了" in store.progress_text(w)
