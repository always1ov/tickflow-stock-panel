"""[fork 增强] R34 策略回测 AI 代跑: 指标摘要 / 达标判定 / 计划解析。"""
import pytest

from app.services import backtest_autopilot as bp

VALID = {"boll_break", "ma_cross", "limit_relay"}


def result(**stats):
    base = {"total_return": 0.35, "annual_return": 0.18, "sharpe": 0.9,
            "max_drawdown": -0.22, "win_rate": 0.55, "n_trades": 84,
            "avg_duration": 6.2}
    base.update(stats)
    return {"stats": base}


# ---------- 指标摘要 ----------

def test_digest_keeps_only_decision_metrics():
    d = bp.digest_result(result())
    assert d["交易数"] == 84 and d["夏普"] == 0.9 and d["最大回撤"] == -0.22
    assert "equity_curve" not in d, "净值曲线之类不该喂给 AI"


def test_digest_handles_missing_and_broken():
    assert bp.digest_result(None)["交易数"] is None
    assert bp.digest_result({})["夏普"] is None
    assert bp.digest_result("坏数据")["总收益"] is None


# ---------- 达标判定: 与提示词同一套标准 ----------

def test_meets_bar_all_conditions():
    assert bp.meets_bar(bp.digest_result(result())) is True


def test_meets_bar_rejects_too_few_trades():
    assert bp.meets_bar(bp.digest_result(result(n_trades=12))) is False, "样本太少没统计意义"


def test_meets_bar_rejects_deep_drawdown():
    assert bp.meets_bar(bp.digest_result(result(max_drawdown=-0.45))) is False


def test_meets_bar_rejects_negative_return_or_weak_sharpe():
    assert bp.meets_bar(bp.digest_result(result(total_return=-0.1))) is False
    assert bp.meets_bar(bp.digest_result(result(sharpe=0.2))) is False


def test_meets_bar_rejects_missing_metrics():
    assert bp.meets_bar(bp.digest_result(result(sharpe=None))) is False
    assert bp.meets_bar({}) is False


# ---------- 送审 payload ----------

def test_payload_carries_history_for_feedback():
    rounds = [{"round": 1, "config": {"strategy_id": "ma_cross"},
               "digest": {"夏普": 0.3}, "passed": False, "note": "先试均线"}]
    p = bp.build_payload(strategies=[{"id": "ma_cross"}], rounds=rounds, max_rounds=5)
    assert p["本轮是第几轮"] == 2
    assert p["历史轮次"][0]["你当时的判断"] == "先试均线"
    assert p["历史轮次"][0]["达标"] is False


# ---------- 计划解析 ----------

def test_parse_plan_clamps_and_drops_fabricated_strategy():
    text = ('{"satisfied": false, "note": "换个策略", '
            '"next": {"strategy_id": "编造的", "max_positions": 999}}')
    assert bp.parse_plan(text, VALID)["next"] is None, "编造的策略 id 不给下一轮"


def test_parse_plan_clamps_numbers_and_filters_regimes():
    text = ('{"satisfied": false, "note": "只做强势", '
            '"next": {"strategy_id": "boll_break", '
            '"regime_states": ["strong", "乱填", "strong", "weak"], '
            '"max_positions": 999, "max_exposure_pct": 5, "days": 99999}}')
    plan = bp.parse_plan(text, VALID)["next"]
    assert plan["regime_states"] == ["strong", "weak"], "非法档位丢弃且去重"
    assert plan["max_positions"] == 30 and plan["max_exposure_pct"] == 20
    assert plan["days"] == 1460


def test_parse_plan_defaults_when_numbers_missing():
    text = '{"satisfied": false, "note": "默认跑", "next": {"strategy_id": "ma_cross"}}'
    plan = bp.parse_plan(text, VALID)["next"]
    assert plan == {"strategy_id": "ma_cross", "regime_states": [],
                    "max_positions": 10, "max_exposure_pct": 100, "days": 730}


def test_parse_plan_satisfied_carries_conclusion():
    text = ('{"satisfied": true, "note": "行了", '
            '"conclusion": "历史回测尚可, 但要去验证 tab 做滚动样本外", "next": null}')
    plan = bp.parse_plan(text, VALID)
    assert plan["satisfied"] and "样本外" in plan["conclusion"]


def test_parse_plan_tolerates_think_block():
    text = ('<think>先看清单…</think>\n```json\n'
            '{"satisfied": false, "note": "试布林", '
            '"next": {"strategy_id": "boll_break"}}\n```')
    assert bp.parse_plan(text, VALID)["next"]["strategy_id"] == "boll_break"


def test_parse_plan_raises_on_garbage():
    with pytest.raises(ValueError):
        bp.parse_plan("模型今天不想说话", VALID)


# ---------- 停止与兜底选优 ----------

def test_stop_reason():
    assert bp.stop_reason([], 5) is None
    assert bp.stop_reason([{"satisfied": False}], 5) is None
    assert bp.stop_reason([{"satisfied": True}], 5) == "satisfied"
    assert bp.stop_reason([{"satisfied": False}] * 5, 5) == "exhausted"


def test_best_round_prefers_passed_then_sharpe():
    rounds = [
        {"round": 1, "passed": False, "digest": {"夏普": 2.5}},
        {"round": 2, "passed": True, "digest": {"夏普": 0.6}},
    ]
    assert bp.best_round(rounds)["round"] == 2, "达标优先于高夏普"
    assert bp.best_round([])is None


def test_best_round_handles_missing_sharpe():
    rounds = [{"round": 1, "passed": False, "digest": {}},
              {"round": 2, "passed": False, "digest": {"夏普": 0.1}}]
    assert bp.best_round(rounds)["round"] == 2
