"""[fork 增强] R40 机会区的板块过滤。

用户: "有时候我只想看主板的或者某个板的"。

这里最要紧的一条不变量: 过滤必须发生在 max_show 截断**之前**。
先截 10 条再让前端挑主板的话, 被截掉的主板票就永远看不到了 ——
用户看到的"主板机会"是残缺的, 而且他不会知道。
"""
from __future__ import annotations

import pytest

from app.api.today import rank_opportunities
from app.price_limits import (
    BOARD_BEIJING,
    BOARD_GROWTH,
    BOARD_SH_MAIN,
    BOARD_STAR,
    BOARD_SZ_MAIN,
    BOARDS,
    board_of,
)


# ---------- 板块归属 ----------

@pytest.mark.parametrize("symbol,expected", [
    ("600722.SH", BOARD_SH_MAIN),
    ("601398.SH", BOARD_SH_MAIN),
    ("603083.SH", BOARD_SH_MAIN),
    ("000001.SZ", BOARD_SZ_MAIN),
    ("002415.SZ", BOARD_SZ_MAIN),   # 原中小板 2021 年并入深主板, 不单列
    ("300570.SZ", BOARD_GROWTH),
    ("301privacy".upper() + ".SZ", BOARD_GROWTH),
    ("688037.SH", BOARD_STAR),
    ("689009.SH", BOARD_STAR),      # CDR 也算科创板
    ("830799.BJ", BOARD_BEIJING),
    ("430047.BJ", BOARD_BEIJING),
])
def test_board_of_classifies_by_prefix_then_exchange(symbol, expected):
    assert board_of(symbol) == expected


def test_growth_and_star_are_not_swallowed_by_the_exchange_suffix():
    """300/688 同时带 .SZ/.SH 后缀 —— 先判后缀会把 20cm 的票全算成主板。"""
    assert board_of("300570.SZ") != BOARD_SZ_MAIN
    assert board_of("688037.SH") != BOARD_SH_MAIN


def test_board_of_survives_junk():
    assert board_of("") == "其他"
    assert board_of(None) == "其他"
    assert board_of("600722.sh") == BOARD_SH_MAIN, "小写后缀也要认"


def test_market_overview_shares_the_same_classifier():
    """板块决定涨跌停幅度, 两处各判一套迟早对不上。"""
    from app.services.market_overview_builder import _board

    for sym in ("600722.SH", "300570.SZ", "688037.SH", "830799.BJ", "000001.SZ"):
        assert _board(sym) == board_of(sym)


# ---------- 机会区过滤 ----------

def _trend(signal="转多", duration=1):
    return {"signal": signal, "signal_desc": "刚转强", "duration": duration,
            "state": "UT", "close": 10.0, "ret_20d": 0.1}


def _universe():
    """六只票铺满四个板 —— 主板 3 只故意排在后面, 用来验证截断顺序。"""
    syms = ["300570.SZ", "688037.SH", "688313.SH",
            "600722.SH", "600869.SH", "000001.SZ"]
    trends = {s: _trend() for s in syms}
    names = {s: s for s in syms}
    return trends, names


def test_no_filter_returns_every_board():
    trends, names = _universe()
    shown, _ = rank_opportunities(trends, {}, names, min_score=0, max_show=50)
    assert {o["board"] for o in shown} == {BOARD_GROWTH, BOARD_STAR, BOARD_SH_MAIN, BOARD_SZ_MAIN}


def test_every_opportunity_carries_its_board():
    trends, names = _universe()
    shown, _ = rank_opportunities(trends, {}, names, min_score=0, max_show=50)
    assert all(o["board"] for o in shown), "界面要按板块标色, 每条都得带"


def test_filter_keeps_only_the_asked_boards():
    trends, names = _universe()
    shown, _ = rank_opportunities(trends, {}, names, min_score=0, max_show=50,
                                  boards=[BOARD_SH_MAIN])
    assert {o["symbol"] for o in shown} == {"600722.SH", "600869.SH"}


def test_filter_accepts_several_boards():
    trends, names = _universe()
    shown, _ = rank_opportunities(trends, {}, names, min_score=0, max_show=50,
                                  boards=[BOARD_SH_MAIN, BOARD_SZ_MAIN])
    assert {o["board"] for o in shown} == {BOARD_SH_MAIN, BOARD_SZ_MAIN}
    assert len(shown) == 3


def test_filter_runs_before_the_max_show_cut(monkeypatch):
    """核心不变量。max_show=2 时, 主板过滤必须先把非主板剔掉, 再取前 2 条 ——
    否则前 2 条全是创业板/科创板, 主板机会一条都看不到。"""
    trends, names = _universe()
    unfiltered, _ = rank_opportunities(trends, {}, names, min_score=0, max_show=2)
    assert not any(o["board"] == BOARD_SH_MAIN for o in unfiltered), "前提: 前两条不是主板"

    shown, _ = rank_opportunities(trends, {}, names, min_score=0, max_show=2,
                                  boards=[BOARD_SH_MAIN])
    assert len(shown) == 2
    assert all(o["board"] == BOARD_SH_MAIN for o in shown)


def test_empty_board_list_means_no_filter():
    trends, names = _universe()
    a, _ = rank_opportunities(trends, {}, names, min_score=0, max_show=50, boards=[])
    b, _ = rank_opportunities(trends, {}, names, min_score=0, max_show=50, boards=None)
    assert len(a) == len(b) == 6


def test_filtered_count_still_means_below_threshold(monkeypatch):
    """"已滤掉 N 只"说的是没过把握分门槛的, 不该把板块滤掉的也算进去 ——
    不然用户切到主板会看到一个莫名其妙变大的数字。"""
    trends, names = _universe()
    trends["600869.SH"] = _trend(duration=5)  # 陈年信号, 分数低
    _, filtered = rank_opportunities(trends, {}, names, min_score=60, max_show=50,
                                     boards=[BOARD_SH_MAIN])
    # 要守的是"板块过滤不会把 filtered 撑大" —— 只统计**这个板块内**没过门槛的。
    # 具体数字随打分改动会变([R201] 置信折扣让原料稀薄的合成候选整体下移),
    # 关键是它必须远小于被板块滤掉的那一大批。
    _, all_filtered = rank_opportunities(trends, {}, names, min_score=60, max_show=50)
    assert filtered < all_filtered, "板块过滤掉的不该被算进「没过门槛」"
    assert filtered <= 2


def test_unknown_board_name_filters_everything_out():
    """乱传板块名不该静默变成"不过滤" —— 那会让人以为筛选生效了。"""
    trends, names = _universe()
    shown, _ = rank_opportunities(trends, {}, names, min_score=0, max_show=50,
                                  boards=["纳斯达克"])
    assert shown == []


# ---------- 偏好落盘 ----------

@pytest.fixture
def prefs(tmp_path, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    from app.services import today_prefs
    return today_prefs


def test_default_is_watch_everything(prefs):
    assert prefs.load()["boards"] == []


def test_save_and_load_roundtrip(prefs):
    assert prefs.save(boards=[BOARD_GROWTH, BOARD_SH_MAIN])["boards"] == [BOARD_SH_MAIN, BOARD_GROWTH]
    assert prefs.load()["boards"] == [BOARD_SH_MAIN, BOARD_GROWTH], "按 BOARDS 的展示顺序存"


def test_unknown_boards_are_dropped(prefs):
    assert prefs.save(boards=[BOARD_STAR, "纳斯达克"])["boards"] == [BOARD_STAR]


def test_selecting_all_is_stored_as_no_filter(prefs):
    """全选存成空列表, 否则以后加了新板块, 旧的"当时全选"会变成排除新板块。"""
    assert prefs.save(boards=list(BOARDS))["boards"] == []


def test_only_junk_falls_back_instead_of_hiding_everything(prefs):
    prefs.save(boards=[BOARD_STAR])
    assert prefs.save(boards=["火星板"])["boards"] == [BOARD_STAR], "全是垃圾时保持原样, 不清空"


def test_none_leaves_it_alone(prefs):
    prefs.save(boards=[BOARD_GROWTH])
    assert prefs.save(min_score=70)["boards"] == [BOARD_GROWTH]
