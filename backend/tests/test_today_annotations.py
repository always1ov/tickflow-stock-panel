"""[fork R135] 机会区的两个注记数据源: 策略命中 与 龙虎榜。

R134 建了注记层但这两项**只写了展示分支没接数据源**, 界面上永远不出现。
这组测试守的是补上之后的三条纪律:
  1. 只读既有产出, 不在总览接口里现算(27 个内置策略 × 全市场矩阵是几秒级开销,
     为一个不参与打分的展示标付这个代价没道理);
  2. 数据陈旧就不显示 —— 昨天的策略命中摆在今天的候选旁边是误导;
  3. 只算内置策略(用户: "不用管我自建的策略, 参与的只用内置策略")。
"""
from __future__ import annotations

import pytest

from app.services import today_annotations as ta


class _Repo:
    def __init__(self, tmp_path):
        self.store = type("S", (), {"data_dir": tmp_path})()


class _Engine:
    """list_strategies 的最小替身: 内置 / 自建 / AI / 研究模板各一。"""

    def list_strategies(self, *, include_research: bool = False):  # noqa: ARG002
        return [
            {"id": "ma_golden_cross", "name": "MA 金叉", "source": "builtin"},
            {"id": "trend_breakout", "name": "趋势突破", "source": "builtin"},
            {"id": "my_own", "name": "我自己写的", "source": "custom"},
            {"id": "ai_gen_1", "name": "AI 生成的", "source": "ai"},
            {"id": "factor_rank_research", "name": "因子研究",
             "source": "builtin", "research_only": True},
        ]


@pytest.fixture
def repo(tmp_path):
    return _Repo(tmp_path)


def _write_cache(monkeypatch, payload):
    monkeypatch.setattr("app.services.strategy_cache.read_cache", lambda _d: payload)


# ------------------------------------------------------- 策略命中


def test_hits_are_inverted_to_symbol_keyed(monkeypatch, repo):
    _write_cache(monkeypatch, {
        "as_of": "2026-08-31",
        "today_ever_matched": {"ma_golden_cross": ["600000.SH", "000001.SZ"],
                               "trend_breakout": ["600000.SH"]},
    })
    out = ta.strategy_hits(repo, _Engine(), "2026-08-31")
    assert out["600000.SH"] == ["MA 金叉", "趋势突破"]
    assert out["000001.SZ"] == ["MA 金叉"]


def test_only_builtin_strategies_count(monkeypatch, repo):
    """用户: "不用管我自建的策略, 参与的只用内置策略"。

    自建/AI 生成的数量与口径都不受控, 混进来会让"命中 5 个策略"失去可比性。
    """
    _write_cache(monkeypatch, {
        "as_of": "2026-08-31",
        "today_ever_matched": {"ma_golden_cross": ["600000.SH"],
                               "my_own": ["600000.SH"],
                               "ai_gen_1": ["600000.SH"]},
    })
    assert ta.strategy_hits(repo, _Engine(), "2026-08-31")["600000.SH"] == ["MA 金叉"]


def test_research_templates_are_excluded(monkeypatch, repo):
    _write_cache(monkeypatch, {
        "as_of": "2026-08-31",
        "today_ever_matched": {"factor_rank_research": ["600000.SH"]},
    })
    assert ta.strategy_hits(repo, _Engine(), "2026-08-31") == {}


def test_stale_cache_yields_nothing(monkeypatch, repo):
    """昨天的命中摆在今天的候选旁边是误导 —— 宁可不显示。"""
    _write_cache(monkeypatch, {
        "as_of": "2026-08-28",
        "today_ever_matched": {"ma_golden_cross": ["600000.SH"]},
    })
    assert ta.strategy_hits(repo, _Engine(), "2026-08-31") == {}


def test_missing_cache_or_engine_is_silent(monkeypatch, repo):
    _write_cache(monkeypatch, None)
    assert ta.strategy_hits(repo, _Engine(), "2026-08-31") == {}
    _write_cache(monkeypatch, {"as_of": "2026-08-31", "today_ever_matched": {}})
    assert ta.strategy_hits(repo, None, "2026-08-31") == {}
    assert ta.strategy_hits(repo, _Engine(), None) == {}


def test_hits_are_capped_per_symbol(monkeypatch, repo):
    many = {f"s{i}": ["600000.SH"] for i in range(10)}
    _write_cache(monkeypatch, {"as_of": "2026-08-31", "today_ever_matched": many})
    engine = type("E", (), {"list_strategies": lambda self, **kw: [
        {"id": f"s{i}", "name": f"策略{i}", "source": "builtin"} for i in range(10)]})()
    assert len(ta.strategy_hits(repo, engine, "2026-08-31")["600000.SH"]) == ta.MAX_HITS_PER_SYMBOL


def test_cache_read_failure_does_not_raise(monkeypatch, repo):
    def _boom(_d):
        raise RuntimeError("boom")
    monkeypatch.setattr("app.services.strategy_cache.read_cache", _boom)
    assert ta.strategy_hits(repo, _Engine(), "2026-08-31") == {}


# ------------------------------------------------------- 策略命中的注记文案


def test_strategy_note_never_implies_more_is_better():
    """命中多不等于更强 —— 内置策略里均线/突破/量价几类高度重叠, 一只放量突破
    的票天然同时命中三四个, 那是策略集自身的冗余。所以 tone 恒为中性。"""
    for n in (1, 4):
        note = ta.strategy_note([f"策略{i}" for i in range(n)])
        assert note["tone"] == "info"
    assert "不参与把握分" in ta.strategy_note(["MA 金叉"])["text"]
    assert "不含自建" in ta.strategy_note(["MA 金叉"])["text"]


# ------------------------------------------------------- 龙虎榜


def _dt(monkeypatch, payload):
    monkeypatch.setattr("app.services.dragon_tiger.get_dragon_tiger",
                        lambda _d, target=None: payload)


def test_dragon_map_reads_the_all_board_only(monkeypatch, repo):
    """机构榜与游资榜是「全部」榜的子集, 三榜合并只会让同一只票出现三次。"""
    _dt(monkeypatch, {"state": "ok", "trade_date": "2026-08-31",
                      "all": {"stock_items": [
                          {"thscode": "600000.SH", "net_value": 1.2e8, "org_net_value": 3e7}]},
                      "org": {"stock_items": [{"thscode": "600000.SH"}]}})
    out = ta.dragon_tiger_map(repo)
    assert list(out) == ["600000.SH"]
    assert out["600000.SH"]["net_value"] == 1.2e8


@pytest.mark.parametrize("state", ["no_data", "source_unavailable"])
def test_dragon_map_empty_when_unpublished(monkeypatch, repo, state):
    _dt(monkeypatch, {"state": state})
    assert ta.dragon_tiger_map(repo) == {}


def test_dragon_map_marks_fallback_as_stale(monkeypatch, repo):
    """回退到上一期时必须标出是哪天的 —— 不标就成了"今天上榜了"。"""
    _dt(monkeypatch, {"state": "fallback_prev", "trade_date": "2026-08-28",
                      "all": {"stock_items": [{"thscode": "600000.SH", "net_value": 1e8}]}})
    assert ta.dragon_tiger_map(repo)["600000.SH"]["stale_date"] == "2026-08-28"


def test_dragon_failure_does_not_raise(monkeypatch, repo):
    def _boom(_d, target=None):
        raise RuntimeError("boom")
    monkeypatch.setattr("app.services.dragon_tiger.get_dragon_tiger", _boom)
    assert ta.dragon_tiger_map(repo) == {}


# ------------------------------------------------------- 龙虎榜的注记文案


def test_dragon_note_direction_drives_the_tone():
    """净卖出上榜不是利好 —— 只报"在榜"等于把方向抹掉了。"""
    assert ta.dragon_note({"net_value": 1.2e8})["tone"] == "good"
    assert ta.dragon_note({"net_value": -8e7})["tone"] == "bad"
    assert ta.dragon_note({"net_value": None})["tone"] == "info"


def test_dragon_note_formats_amounts_readably():
    assert "亿" in ta.dragon_note({"net_value": 1.2e8})["label"]
    assert "万" in ta.dragon_note({"net_value": 3e6})["label"]


def test_dragon_note_surfaces_staleness_in_text():
    note = ta.dragon_note({"net_value": 1e8, "stale_date": "2026-08-28"})
    assert "尚未发布" in note["text"] and "2026-08-28" in note["text"]


def test_dragon_note_says_it_does_not_score():
    assert "不参与把握分" in ta.dragon_note({"net_value": 1e8})["text"]


# ------------------------------------------------------- 接进候选的注记链路


def test_annotations_reach_the_candidate_and_never_move_the_score():
    from app.api.today import score_opportunities
    trends = {"600000.SH": {"state": "UT", "state_cn": "上涨趋势", "side": "多头",
                            "duration": 1, "close": 10.0, "as_of": "2026-08-31",
                            "signal": "转多", "signal_desc": "突破", "ret_20d": 0.08}}
    names = {"600000.SH": "测试"}
    gate = {"above_ma20": True, "above_ma20_prev": True, "close": 10.0,
            "ma120": 8.0, "ma120_rising": True}
    plain, _ = score_opportunities(trends, {}, names, bench_ret=0.02,
                                   extras={"600000.SH": {"gate": gate, "channel_pct": 0.6}})
    noted, _ = score_opportunities(trends, {}, names, bench_ret=0.02, extras={"600000.SH": {
        "gate": gate, "channel_pct": 0.6,
        "strategy_hits": ["MA 金叉", "趋势突破"],
        "dragon": {"net_value": 1.5e8, "org_net_value": 4e7},
    }})
    assert noted[0]["score"] == plain[0]["score"], "注记一分不加一分不减"
    keys = {n["key"] for n in noted[0]["notes"]}
    assert {"strategy", "dragon"} <= keys
    joined = "".join(noted[0]["why"])
    assert "策略" not in joined and "龙虎" not in joined, "注记不许混进评分理由"
