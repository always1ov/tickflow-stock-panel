"""[fork 增强] R37 今日总览中观层: 主线归属 + 中观快照。

守住三条设计约定:
  1. 不在主线内不扣分(主线由涨停梯队推出, 扣分等于系统性偏向妖股)
  2. 主线数据陈旧就不打分(停更几天后的"当前主线"是上周的主线)
  3. 一票多概念时取名次最靠前的当主归属, 其余进 also(只报一条会像漏看)
"""
from datetime import date

import polars as pl
import pytest

from app.services.today_mainline import (
    _amount_label,
    amount_snapshot,
    format_amount,
    latest_mainlines,
    mainline_bonus,
    tag_symbols,
)


def _hist(rows: list[dict]) -> pl.DataFrame:
    return pl.DataFrame(rows, schema={
        "date": pl.Date, "member": pl.Utf8, "rank": pl.Int64, "score": pl.Float64,
        "limit_up_count": pl.Int64, "max_boards": pl.Int64, "leader_symbol": pl.Utf8,
    })


def _row(d: date, member: str, rank: int, **kw) -> dict:
    return {
        "date": d, "member": member, "rank": rank,
        "score": kw.get("score", 100.0 - rank * 10),
        "limit_up_count": kw.get("limit_up_count", 10 - rank),
        "max_boards": kw.get("max_boards", 5),
        "leader_symbol": kw.get("leader_symbol", "SH600000"),
    }


# ---------- latest_mainlines ----------

def test_takes_only_the_last_day():
    """主线时序是全历史; 今日总览要的是最后一天, 不是全表前几名。"""
    df = _hist([
        _row(date(2026, 8, 18), "旧主线", 1),
        _row(date(2026, 8, 20), "新主线", 1),
        _row(date(2026, 8, 20), "新主线二", 2),
    ])
    got = latest_mainlines(df, today=date(2026, 8, 20))
    assert got["date"] == "2026-08-20"
    assert [r["member"] for r in got["rows"]] == ["新主线", "新主线二"]


def test_rows_are_capped_and_rank_ordered():
    df = _hist([_row(date(2026, 8, 20), f"概念{i}", i) for i in range(6, 0, -1)])
    got = latest_mainlines(df, top_n=3, today=date(2026, 8, 20))
    assert [r["rank"] for r in got["rows"]] == [1, 2, 3]


def test_stale_when_batch_stopped_updating():
    """跑批停了几天, "当前主线"其实是上周的 —— 必须标出来, 调用方据此不打分。"""
    df = _hist([_row(date(2026, 8, 1), "上周的主线", 1)])
    got = latest_mainlines(df, today=date(2026, 8, 20))
    assert got["stale"] is True and got["age_days"] == 19
    # 仍然返回内容: 用户问"为什么没有主线"时要能答上来, 不能静默消失
    assert got["rows"][0]["member"] == "上周的主线"


def test_weekend_gap_is_not_stale():
    """周五收盘 + 周末 + 一个节假日不该被当成停更。"""
    df = _hist([_row(date(2026, 8, 14), "主线", 1)])
    assert latest_mainlines(df, today=date(2026, 8, 20))["stale"] is False


def test_accepts_string_dates():
    """parquet 里 date 可能是字符串, 不该因为 dtype 就整块降级。"""
    df = pl.DataFrame({"date": ["2026-08-20"], "member": ["概念"], "rank": [1],
                       "score": [90.0], "limit_up_count": [8], "max_boards": [4],
                       "leader_symbol": ["SH600000"]})
    got = latest_mainlines(df, today=date(2026, 8, 20))
    assert got["date"] == "2026-08-20"


def test_missing_or_broken_input_degrades_quietly():
    assert latest_mainlines(None) is None
    assert latest_mainlines(pl.DataFrame()) is None
    # 缺 rank 列(旧 schema): 不能抛, 只能降级
    assert latest_mainlines(pl.DataFrame({"date": ["2026-08-20"], "member": ["x"]})) is None


def test_blank_member_rows_are_dropped():
    df = _hist([_row(date(2026, 8, 20), "  ", 1), _row(date(2026, 8, 20), "真主线", 2)])
    got = latest_mainlines(df, today=date(2026, 8, 20))
    assert [r["member"] for r in got["rows"]] == ["真主线"]


# ---------- tag_symbols ----------

def _map(pairs: list[tuple[str, str]]) -> pl.DataFrame:
    return pl.DataFrame({"_sym_up": [p[0] for p in pairs], "concept": [p[1] for p in pairs]},
                        schema={"_sym_up": pl.Utf8, "concept": pl.Utf8})


def test_tags_only_symbols_in_a_mainline():
    rows = [{"member": "机器人", "rank": 1, "limit_up_count": 9}]
    got = tag_symbols(_map([("SH600000", "机器人"), ("SZ000001", "白酒")]),
                      ["SH600000", "SZ000001"], rows)
    assert set(got) == {"SH600000"}
    assert got["SH600000"]["rank"] == 1


def test_multi_concept_symbol_takes_best_rank():
    """一票同属多条主线时取名次最靠前的当主归属, 其余进 also。"""
    rows = [{"member": "机器人", "rank": 3, "limit_up_count": 5},
            {"member": "减速器", "rank": 1, "limit_up_count": 9}]
    got = tag_symbols(_map([("SH600000", "机器人"), ("SH600000", "减速器")]),
                      ["SH600000"], rows)
    assert got["SH600000"]["member"] == "减速器"
    assert got["SH600000"]["also"] == ["机器人"]


def test_symbol_matching_is_case_insensitive():
    rows = [{"member": "机器人", "rank": 1, "limit_up_count": 9}]
    got = tag_symbols(_map([("SH600000", "机器人")]), ["sh600000"], rows)
    assert "SH600000" in got


def test_duplicate_map_rows_do_not_duplicate_also():
    """概念映射来自多个 ext 数据源, 同一对可能出现多次。"""
    rows = [{"member": "机器人", "rank": 1, "limit_up_count": 9},
            {"member": "减速器", "rank": 2, "limit_up_count": 6}]
    pairs = [("SH600000", "机器人"), ("SH600000", "机器人"), ("SH600000", "减速器")]
    got = tag_symbols(_map(pairs), ["SH600000"], rows)
    assert got["SH600000"]["also"] == ["减速器"]


def test_tag_edge_cases():
    rows = [{"member": "机器人", "rank": 1, "limit_up_count": 9}]
    assert tag_symbols(None, ["SH600000"], rows) == {}
    assert tag_symbols(_map([("SH600000", "机器人")]), [], rows) == {}
    assert tag_symbols(_map([("SH600000", "机器人")]), ["SH600000"], []) == {}
    # 缺列的映射表不能抛
    assert tag_symbols(pl.DataFrame({"x": [1]}), ["SH600000"], rows) == {}


# ---------- mainline_bonus ----------

def test_absence_is_never_a_penalty():
    """核心约定: 不在主线内 = 没有加成, 不是扣分。"""
    assert mainline_bonus(None) == 0


def test_bonus_decreases_with_rank_but_stays_modest():
    b1, b3, b5 = mainline_bonus(1), mainline_bonus(3), mainline_bonus(9)
    assert b1 > b3 > b5 > 0
    # 加成不该盖过趋势本身(转多底分 70)与量价项 —— 第一主线里的烂形态
    # 不能因为归属就排到第三主线里的好形态前面
    assert b1 <= 15


def test_bonus_tolerates_garbage():
    assert mainline_bonus("乱填") == 0


# ---------- amount_snapshot ----------

def test_percentile_excludes_today_from_the_denominator():
    """把今天算进分母会让分位天然偏低(自己不可能小于自己)。"""
    vals = [100.0] * 30 + [200.0]
    snap = amount_snapshot(vals)
    assert snap["pct_rank"] == 1.0


def test_low_volume_day_ranks_near_zero():
    vals = [200.0] * 30 + [50.0]
    assert amount_snapshot(vals)["pct_rank"] == 0.0
    assert amount_snapshot(vals)["label"] == "地量"


def test_small_sample_reports_value_without_a_fake_percentile():
    snap = amount_snapshot([1e12, 1.1e12, 1.2e12])
    assert snap["total"] == 1.2e12
    assert snap["pct_rank"] is None and snap["label"] is None


def test_window_limits_the_lookback():
    """只比最近 window 天: 三年前的天量不该一直压着今天的分位。"""
    vals = [999.0] * 300 + [100.0] * 30 + [150.0]
    snap = amount_snapshot(vals, window=31)
    assert snap["pct_rank"] == 1.0


def test_zero_and_none_rows_are_dropped():
    """跑批半途写入的空行不能被当成"地量日"。"""
    snap = amount_snapshot([None, 0.0, 100.0] + [100.0] * 25 + [300.0])
    assert snap["pct_rank"] == 1.0


def test_amount_snapshot_edge_cases():
    assert amount_snapshot([]) is None
    assert amount_snapshot([None, None]) is None
    assert amount_snapshot([1e12])["pct_rank"] is None


@pytest.mark.parametrize("v,want", [
    (1.234e12, "1.23 万亿"),
    (9.87e11, "9,870 亿"),
    (5e8, "5 亿"),
    (3e4, "3 万"),
])
def test_format_amount(v, want):
    assert format_amount(v) == want


def test_amount_labels_cover_the_whole_range():
    got = [_amount_label(p) for p in (0.0, 0.1, 0.3, 0.5, 0.7, 0.9, 1.0)]
    assert got == ["地量", "地量", "量能偏冷", "量能中性", "量能偏暖", "显著放量", "显著放量"]


# ---------- 接进把握分 ----------

def _trend(close=10.0, duration=1):
    return {"state": "UT", "state_cn": "上涨趋势", "side": "多头", "duration": duration,
            "close": close, "as_of": "2026-08-20", "signal": "转多",
            "signal_desc": f"突破上关键点 {close}", "ret_20d": None}


def _rank(extras, signals=None, duration=1):
    from app.api.today import rank_opportunities
    trends = {"A": _trend(duration=duration), "B": _trend(duration=duration)}
    shown, _ = rank_opportunities(trends, signals or {}, {"A": "甲", "B": "乙"},
                                  min_score=0, max_show=10, extras=extras)
    return {o["symbol"]: o for o in shown}


def test_mainline_is_an_annotation_not_a_bonus():
    """[R134] 主线退出评分, 只作注记。

    理由不是"主线没用", 是**不可回测**: 主线由涨停梯队推出, 口径随情绪周期
    漂移, 没有稳定的历史定义 —— 拿它去动名次, 名次就带上了一个说不清的东西。
    展示照旧: 用户要的是"看到它时知道些什么"。
    """
    got = _rank({"A": {"mainline": {"member": "机器人", "rank": 1,
                                    "limit_up_count": 9, "also": []}}})
    assert got["A"]["score"] == got["B"]["score"], "主线不该动分数"
    assert "机器人" not in got["A"]["why"], "注记不许混进评分理由"
    note = {n["key"]: n for n in got["A"]["notes"]}["mainline"]
    assert "机器人" in note["label"] and "9 家涨停" in note["text"]
    assert got["A"]["mainline"]["rank"] == 1


def test_absence_does_not_lower_the_score():
    """乙不在任何主线里, 分数必须和完全没有主线数据时一模一样。"""
    with_data = _rank({"A": {"mainline": {"member": "机器人", "rank": 1,
                                          "limit_up_count": 9, "also": []}}})
    without = _rank({})
    assert with_data["B"]["score"] == without["B"]["score"]


def test_mainline_note_appears_once_when_a_symbol_hits_both_sources():
    """同一只票既是趋势转强又逼近 AI 触发价时, 主线注记只能出现一条。"""
    signals = {"A": {"signal": "buy", "confidence": 30, "close": 10.0,
                     "watch_points": [{"direction": "up", "price": 10.1,
                                       "action": "买入"}]}}
    ml = {"A": {"mainline": {"member": "机器人", "rank": 1,
                             "limit_up_count": 9, "also": []}}}
    both = _rank(ml, signals, duration=3)["A"]
    assert sum(1 for n in both["notes"] if n["key"] == "mainline") == 1
    assert set(both["kinds"]) == {"trend_signal", "near_breakout"}