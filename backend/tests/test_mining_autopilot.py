"""[fork 增强] R31 AI 自动挖掘: 窗口切分 / 结果摘要 / 计划解析 / 会话留档。"""
from datetime import date

import pytest

from app.services import mining_autopilot as ap

FACTORS = {"momentum_20d", "ma20_bias", "turnover_rate", "volume_ratio", "amplitude"}


# ---------- 窗口切分: 终检段必须真的锁出来 ----------

def test_split_windows_carves_holdout_off_the_tail():
    w = ap.split_windows(date(2021, 1, 1), date(2026, 8, 20), holdout_days=365)
    assert w["holdout_end"] == date(2026, 8, 20)
    assert w["holdout_start"] == date(2025, 8, 21)
    assert w["search_end"] == date(2025, 8, 20), "搜索窗口必须在终检段开始前一天截止"
    assert w["search_start"] == date(2021, 1, 1)


def test_split_windows_never_overlaps():
    w = ap.split_windows(date(2019, 1, 1), date(2026, 8, 20))
    assert w["search_end"] < w["holdout_start"], "两段不得有一天重叠 —— 重叠就等于泄题"


def test_split_windows_rejects_too_short_search():
    with pytest.raises(ValueError, match="搜索窗口"):
        ap.split_windows(date(2025, 1, 1), date(2026, 8, 20), holdout_days=365)


def test_split_windows_rejects_inverted_range():
    with pytest.raises(ValueError):
        ap.split_windows(date(2026, 8, 20), date(2026, 1, 1))


def test_split_windows_floors_holdout():
    w = ap.split_windows(date(2018, 1, 1), date(2026, 8, 20), holdout_days=5)
    assert (w["holdout_end"] - w["holdout_start"]).days + 1 == ap.MIN_HOLDOUT_DAYS


# [docs/mining.md §自动运行] 自动挖掘只允许 balanced / strict
def test_split_windows_rejects_exploratory_profile():
    with pytest.raises(ValueError, match="档位"):
        ap.split_windows(date(2018, 1, 1), date(2026, 8, 20), budget_profile="exploratory")


def test_split_windows_search_floor_is_profile_aware():
    """strict 需要的历史比 balanced 长得多, 同一区间可能 balanced 过、strict 不过。"""
    start, end = date(2021, 1, 1), date(2026, 8, 20)
    ap.split_windows(start, end, budget_profile="balanced")   # 不抛
    with pytest.raises(ValueError, match="strict"):
        ap.split_windows(start, end, budget_profile="strict")


# ---------- 赢家解析: 必须走 signature ----------

def test_resolve_pick_matches_signature_first():
    cands = [{"signature": "abc123", "name": "组合A", "达标": True, "样本外Sharpe": 0.6},
             {"signature": "def456", "name": "组合B", "达标": True, "样本外Sharpe": 1.9}]
    assert ap.resolve_pick("abc123", cands)["name"] == "组合A", "按 signature 精确匹配"


def test_resolve_pick_falls_back_to_name_then_rules():
    cands = [{"signature": "abc123", "name": "组合A", "达标": False, "样本外Sharpe": 2.0},
             {"signature": "def456", "name": "组合B", "达标": True, "样本外Sharpe": 0.6}]
    assert ap.resolve_pick("组合A", cands)["signature"] == "abc123", "AI 回了 name 也认"
    got = ap.resolve_pick("编造的signature", cands)
    assert got["signature"] == "def456", "对不上就规则兜底(达标优先), 不凭字面值构造定义"
    assert ap.resolve_pick(None, cands)["signature"] == "def456"
    assert ap.resolve_pick("abc", []) is None


# ---------- 结果摘要 ----------

def _result(**over):
    base = {
        "name": "动量+乖离", "definition": {"factor_names": ["momentum_20d", "ma20_bias"]},
        "gate": {"qualified": False, "reasons": ["requires an OOS Sharpe of at least 0.5"]},
        "oos_sharpe": 0.31, "oos_return": 0.02, "oos_max_drawdown": -0.18,
        "oos_positive_fold_ratio": 0.67, "valid_folds": 3, "oos_n_trades": 120,
    }
    base.update(over)
    return {"candidates": [base]}


def test_summarize_keeps_gate_and_metrics():
    s = ap.summarize_candidates(_result())[0]
    assert s["定义"] == "momentum_20d + ma20_bias"
    assert s["达标"] is False and s["未达标原因"]
    assert s["样本外Sharpe"] == 0.31


def test_summarize_handles_missing_or_broken_result():
    assert ap.summarize_candidates(None) == []
    assert ap.summarize_candidates({}) == []
    assert ap.summarize_candidates({"candidates": ["坏数据"]}) == []


def test_summarize_caps_candidate_count():
    many = {"candidates": [dict(_result()["candidates"][0], name=f"c{i}") for i in range(20)]}
    assert len(ap.summarize_candidates(many, limit=6)) == 6


def test_pick_best_prefers_qualified_then_sharpe():
    cands = [
        {"name": "高分未达标", "达标": False, "样本外Sharpe": 1.8},
        {"name": "达标", "达标": True, "样本外Sharpe": 0.6},
    ]
    assert ap.pick_best(cands)["name"] == "达标", "达标优先于高 Sharpe"
    assert ap.pick_best([]) is None


# ---------- 送审 payload: 历史必须带上(这就是"拿上次结果反馈") ----------

def test_payload_carries_full_iteration_history():
    windows = ap.split_windows(date(2021, 1, 1), date(2026, 8, 20))
    iters = [{"iteration": 1, "config": {"beam_width": 8}, "candidates": [{"name": "a"}],
              "status": "succeeded", "ai": {"verdict": "太弱"}}]
    p = ap.build_payload(factor_catalog=[{"id": "momentum_20d"}], windows=windows,
                         iterations=iters, max_iterations=8, asset_type="stock")
    assert p["本轮是第几轮"] == 2
    assert p["历史轮次"][0]["你当时的判断"] == "太弱"
    assert p["历史轮次"][0]["跑出的候选"] == [{"name": "a"}]
    assert "search_start" not in str(p["终检窗口"]), "终检窗口的日期不能出现在 payload 里"


# ---------- 计划解析 ----------

def test_parse_plan_clamps_and_drops_fabricated_factors():
    text = ('{"satisfied": false, "verdict": "Sharpe 不够", '
            '"next": {"factor_names": ["momentum_20d", "编造的因子", "ma20_bias"], '
            '"budget_profile": "乱填", "max_combination_factors": 99, '
            '"beam_width": 1, "correlation_threshold": 5}, "reason": "换一批"}')
    plan = ap.parse_plan(text, FACTORS)
    assert plan["next"]["factor_names"] == ["momentum_20d", "ma20_bias"], "编造的因子丢掉"
    assert plan["next"]["budget_profile"] == "balanced", "非法档位回落"
    assert plan["next"]["max_combination_factors"] == 4
    assert plan["next"]["beam_width"] == 4, "低于下限夹到 4"
    assert plan["next"]["correlation_threshold"] == 0.95


def test_parse_plan_satisfied_stops_the_loop():
    text = '{"satisfied": true, "verdict": "稳稳达标", "pick": "动量+乖离", "next": null}'
    plan = ap.parse_plan(text, FACTORS)
    assert plan["satisfied"] is True and plan["pick"] == "动量+乖离"
    assert plan["next"] is None


def test_parse_plan_tolerates_think_block_and_fence():
    text = ('<think>让我先看看…</think>\n```json\n'
            '{"satisfied": false, "verdict": "再试一轮", '
            '"next": {"factor_names": ["turnover_rate"]}}\n```')
    plan = ap.parse_plan(text, FACTORS)
    assert plan["next"]["factor_names"] == ["turnover_rate"]


def test_parse_plan_drops_plan_when_all_factors_fabricated():
    text = '{"satisfied": false, "verdict": "换一批", "next": {"factor_names": ["假的"]}}'
    plan = ap.parse_plan(text, FACTORS)
    assert plan["next"] is None, "一个合法因子都不剩就没有下一轮配置"


def test_parse_plan_raises_on_garbage():
    with pytest.raises(ValueError):
        ap.parse_plan("模型今天不想说话", FACTORS)


# ---------- 停止条件与可信度 ----------

def test_stop_reason_satisfied_beats_remaining_budget():
    iters = [{"ai": {"satisfied": True}}]
    assert ap.stop_reason(iters, max_iterations=8) == "satisfied"


def test_stop_reason_exhausted_at_cap():
    iters = [{"ai": {"satisfied": False}}] * 8
    assert ap.stop_reason(iters, max_iterations=8) == "exhausted"


def test_stop_reason_none_when_budget_left():
    assert ap.stop_reason([{"ai": {"satisfied": False}}], max_iterations=8) is None
    assert ap.stop_reason([], max_iterations=8) is None


def test_confidence_note_degrades_with_iterations():
    assert "基本可信" in ap.confidence_note(1)
    assert "以终检结果为准" in ap.confidence_note(3)
    assert "只看终检" in ap.confidence_note(6)
    assert "无参考价值" in ap.confidence_note(12)


# ---------- 会话留档 ----------

@pytest.fixture()
def store(tmp_path, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    from app.services import mining_autopilot_store
    return mining_autopilot_store


def _new(store):
    return store.create(
        asset_type="stock",
        windows=ap.split_windows(date(2021, 1, 1), date(2026, 8, 20)),
        max_iterations=8,
        base_config={"commission_pct": 0.0002},
    )


def test_session_roundtrip_and_dates_are_iso(store):
    s = _new(store)
    got = store.get(s["session_id"])
    assert got["status"] == "open" and got["iterations"] == []
    assert got["search_start"] == "2021-01-01" and got["holdout_end"] == "2026-08-20"


def test_iterations_accumulate_in_order(store):
    s = _new(store)
    store.append_iteration(s["session_id"], {"run_id": "r1", "status": "succeeded",
                                             "candidates": [], "ai": {"verdict": "弱"}})
    store.append_iteration(s["session_id"], {"run_id": "r2", "status": "succeeded",
                                             "candidates": [], "ai": {"verdict": "好点了"}})
    got = store.get(s["session_id"])
    assert [i["iteration"] for i in got["iterations"]] == [1, 2]
    assert got["iterations"][1]["run_id"] == "r2"


def test_set_status_records_winner_and_final_check(store):
    s = _new(store)
    store.set_status(s["session_id"], "satisfied",
                     winner={"name": "动量+乖离"},
                     final_check={"oos_sharpe": 0.42, "qualified": False})
    got = store.get(s["session_id"])
    assert got["status"] == "satisfied"
    assert got["final_check"]["qualified"] is False, "终检不过要如实留档, 不许抹掉"


def test_latest_and_list_newest_first(store):
    a = _new(store)
    b = _new(store)
    assert store.latest()["session_id"] == b["session_id"]
    assert [x["session_id"] for x in store.list_sessions()][:2] == [b["session_id"], a["session_id"]]


def test_sessions_capped(store):
    ids = [_new(store)["session_id"] for _ in range(store.MAX_SESSIONS + 4)]
    kept = [x["session_id"] for x in store.list_sessions(limit=99)]
    assert len(kept) == store.MAX_SESSIONS
    assert ids[-1] in kept and ids[0] not in kept


def test_corrupt_file_returns_empty(store):
    store._path().write_text("{ broken", encoding="utf-8")
    assert store.list_sessions() == [] and store.latest() is None


def test_unknown_session_is_none(store):
    assert store.get("nope") is None
    assert store.append_iteration("nope", {}) is None
    assert store.set_status("nope", "failed") is None
