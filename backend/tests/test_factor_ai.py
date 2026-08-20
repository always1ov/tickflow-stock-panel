"""[fork 增强] R32 因子批量筛选的 AI 解读: 规则层短名单 + 解析。"""
import pytest

from app.services import factor_ai as fa


def item(name, group="动量", ic=0.03, ir=0.4, win=0.58, **over):
    base = {
        "factor_name": name, "label": name, "group": group,
        "ic_mean": ic, "ir": ir, "ic_win_rate": win,
        "long_short_return": 0.12, "long_short_max_drawdown": -0.2, "error": None,
    }
    base.update(over)
    return base


# ---------- 可用度分 ----------

def test_score_rewards_ic_ir_and_direction():
    strong = fa.usable_score(item("a", ic=0.05, ir=0.5, win=0.65))
    weak = fa.usable_score(item("b", ic=0.02, ir=0.1, win=0.57))
    assert strong is not None and weak is not None
    assert strong > weak and strong <= 100


def test_negative_ic_is_kept_reverse_factors_still_work():
    """反向因子取负号照样能用, 不该因为符号被埋没。"""
    assert fa.usable_score(item("rev", ic=-0.05, ir=-0.5, win=0.35)) is not None


def test_score_rejects_no_discrimination():
    assert fa.usable_score(item("flat", ic=0.001)) is None, "|IC| 太小 = 没区分度"
    assert fa.usable_score(item("nan", ic=None)) is None


def test_score_rejects_coin_flip_direction():
    """双边死区: 反向因子胜率天然低于 50%, 不能用单边下限误杀。"""
    assert fa.usable_score(item("coin", ic=0.04, win=0.50)) is None, "胜率贴 50% = 方向随机"
    assert fa.usable_score(item("coin2", ic=0.04, win=0.53)) is None, "死区内一律出局"
    assert fa.usable_score(item("rev", ic=-0.04, win=0.40)) is not None, "反向因子要留住"


def test_score_rejects_errored_rows():
    assert fa.usable_score(item("bad", error="数据不足")) is None
    assert fa.usable_score("不是字典") is None


def test_score_tolerates_missing_ir_and_win():
    """IR/胜率缺失不该直接判死 —— IC 够强就还有参考价值。"""
    s = fa.usable_score(item("partial", ic=0.05, ir=None, win=None))
    assert s is not None and s > 0


# ---------- 短名单: 同组去重 ----------

def test_shortlist_caps_per_group():
    items = [item(f"ma{i}", group="均线偏离", ic=0.05 - i * 0.001) for i in range(6)]
    got = fa.shortlist(items)
    assert len(got) == fa.PER_GROUP_CAP, "同组高度相关, 全放进去是虚假多样性"
    assert [g["factor"] for g in got] == ["ma0", "ma1"], "留可用度最高的两个"


def test_shortlist_spans_groups_and_sorts_by_score():
    items = [
        item("mom", group="动量", ic=0.03, ir=0.3, win=0.56),
        item("vol", group="量价", ic=0.06, ir=0.6, win=0.66),
        item("rsi", group="超买超卖", ic=0.045, ir=0.45, win=0.60),
    ]
    got = fa.shortlist(items)
    assert [g["factor"] for g in got] == ["vol", "rsi", "mom"], "按可用度降序"
    assert len({g["group"] for g in got}) == 3


def test_shortlist_respects_size_cap():
    items = [item(f"f{i}", group=f"g{i}", ic=0.05) for i in range(30)]
    assert len(fa.shortlist(items, size=5)) == 5


def test_shortlist_empty_when_nothing_usable():
    assert fa.shortlist([item("flat", ic=0.0005)]) == []
    assert fa.shortlist([]) == []


def test_dropped_summary_explains_the_funnel():
    """界面要能回答'61 个里为什么只剩几个'。"""
    items = ([item(f"ma{i}", group="均线偏离") for i in range(5)]
             + [item("bad", error="数据不足"), item("flat", ic=0.0001)])
    picked = fa.shortlist(items)
    st = fa.dropped_summary(items, picked)
    assert st["总数"] == 7 and st["算失败"] == 1
    assert st["有区分度"] == 5 and st["进短名单"] == 2
    assert st["同组去重剔除"] == 3


# ---------- 送审 payload ----------

def test_payload_carries_sample_and_funnel():
    picked = fa.shortlist([item("mom")])
    p = fa.build_payload(picked, {"n_symbols": 4800, "n_dates": 243, "rebalance": "week"},
                         fa.dropped_summary([item("mom")], picked))
    assert p["样本"]["标的数"] == 4800 and p["样本"]["交易日数"] == 243
    assert p["规则层筛选情况"]["总数"] == 1
    assert p["候选因子(已按可用度排序, 同组最多留 2 个)"][0]["factor"] == "mom"


# ---------- 解析 ----------

VALID = {"momentum_20d", "turnover_rate", "ma20_bias"}


def test_parse_reading_drops_fabricated_factors():
    text = ('{"summary": "整体偏动量", '
            '"picks": [{"factor": "momentum_20d", "reason": "IC 0.05 且 IR 0.6"}, '
            '{"factor": "编造的", "reason": "假的"}], '
            '"redundant": [{"keep": "ma20_bias", "drop": ["编造的", "turnover_rate"], '
            '"reason": "同组"}], "next_step": "拿这两个去挖掘"}')
    out = fa.parse_reading(text, VALID)
    assert [p["factor"] for p in out["picks"]] == ["momentum_20d"]
    assert out["redundant"][0]["drop"] == ["turnover_rate"], "编造的 id 从 drop 里剔掉"
    assert out["next_step"] == "拿这两个去挖掘"


def test_parse_reading_tolerates_think_block_and_fence():
    text = ('<think>先看 IC…</think>\n```json\n'
            '{"summary": "只有量价这一类有效", "picks": '
            '[{"factor": "turnover_rate", "reason": "胜率 0.62"}]}\n```')
    out = fa.parse_reading(text, VALID)
    assert out["picks"][0]["factor"] == "turnover_rate"
    assert out["summary"].startswith("只有量价")


def test_parse_reading_drops_redundant_group_without_valid_drops():
    text = ('{"summary": "行", "picks": [{"factor": "ma20_bias", "reason": "稳"}], '
            '"redundant": [{"keep": "ma20_bias", "drop": ["ma20_bias"]}]}')
    out = fa.parse_reading(text, VALID)
    assert out["redundant"] == [], "keep 和 drop 同一个 id 是无效分组"


def test_parse_reading_dedupes_picks():
    text = ('{"summary": "行", "picks": [{"factor": "ma20_bias", "reason": "a"}, '
            '{"factor": "ma20_bias", "reason": "b"}]}')
    assert len(fa.parse_reading(text, VALID)["picks"]) == 1


def test_parse_reading_raises_on_garbage():
    with pytest.raises(ValueError):
        fa.parse_reading("模型今天不想说话", VALID)


# ================================================================
# [R33] AI 代跑: 用户不会填表, AI 来填来跑来判断
# ================================================================

CATALOG = [{"id": f, "name": f} for f in
           ["momentum_20d", "ma20_bias", "turnover_rate", "rsi_14", "atr_rel"]]
CAT_IDS = {c["id"] for c in CATALOG}


def test_plan_payload_carries_history_for_feedback():
    """上一轮跑了什么、结果如何、AI 当时怎么说, 全带上 —— 这就是反馈闭环。"""
    rounds = [{"round": 1, "config": {"rebalance": "weekly"},
               "shortlist": [{"factor": "momentum_20d", "可用度": 80}],
               "stats": {"总数": 61}, "note": "先广撒网"}]
    p = fa.build_plan_payload(factor_catalog=CATALOG, rounds=rounds, max_rounds=5)
    assert p["本轮是第几轮"] == 2
    assert p["历史轮次"][0]["你当时的判断"] == "先广撒网"
    assert p["历史轮次"][0]["跑出的因子表现(已按可用度排序)"][0]["factor"] == "momentum_20d"


def test_parse_plan_clamps_and_drops_fabricated():
    text = ('{"satisfied": false, "note": "先试量价", '
            '"next": {"factor_names": ["turnover_rate", "编造的", "rsi_14"], '
            '"rebalance": "乱填", "n_groups": 99}}')
    plan = fa.parse_plan(text, CAT_IDS)
    assert plan["next"]["factor_names"] == ["turnover_rate", "rsi_14"], "编造的丢掉"
    assert plan["next"]["rebalance"] == "weekly", "非法调仓回落"
    assert plan["next"]["n_groups"] == 10, "越界夹紧"


def test_parse_plan_satisfied_carries_conclusion():
    text = ('{"satisfied": true, "note": "够了", '
            '"conclusion": "量价类有效, 建议拿去挖掘做组合", "next": null}')
    plan = fa.parse_plan(text, CAT_IDS)
    assert plan["satisfied"] is True
    assert "挖掘" in plan["conclusion"]
    assert plan["next"] is None


def test_parse_plan_tolerates_think_block():
    text = ('<think>先看看清单…</think>\n```json\n'
            '{"satisfied": false, "note": "换一批", '
            '"next": {"factor_names": ["ma20_bias"], "n_groups": 3}}\n```')
    plan = fa.parse_plan(text, CAT_IDS)
    assert plan["next"]["n_groups"] == 3 and plan["next"]["rebalance"] == "weekly"


def test_parse_plan_drops_plan_when_all_factors_fabricated():
    text = '{"satisfied": false, "note": "换", "next": {"factor_names": ["假的"]}}'
    assert fa.parse_plan(text, CAT_IDS)["next"] is None


def test_parse_plan_raises_on_garbage():
    with pytest.raises(ValueError):
        fa.parse_plan("模型今天不想说话", CAT_IDS)


def test_round_digest_reuses_rule_layer():
    """每轮摘要复用规则层短名单与漏斗, 不另起一套口径。"""
    res = {"results": [item("mom", ic=0.05), item("bad", error="X"), item("flat", ic=0.0001)]}
    d = fa.round_digest(res)
    assert [r["factor"] for r in d["shortlist"]] == ["mom"]
    assert d["stats"]["算失败"] == 1 and d["stats"]["总数"] == 3


def test_plan_stop_reason():
    assert fa.plan_stop_reason([], 5) is None
    assert fa.plan_stop_reason([{"satisfied": False}], 5) is None
    assert fa.plan_stop_reason([{"satisfied": True}], 5) == "satisfied"
    assert fa.plan_stop_reason([{"satisfied": False}] * 5, 5) == "exhausted"
