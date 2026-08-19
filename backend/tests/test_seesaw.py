"""[fork 增强] R28 板块跷跷板识别 + 30 天留档。"""
from datetime import date, timedelta

import polars as pl
import pytest

from app.services import seesaw


def _mainline_df(rows):
    """rows: [(date, member, score)] → 主线时序 DataFrame。"""
    return pl.DataFrame(
        {"date": [r[0] for r in rows], "member": [r[1] for r in rows],
         "score": [float(r[2]) for r in rows]}
    )


def _dates(n, start=date(2026, 6, 1)):
    return [(start + timedelta(days=i)).isoformat() for i in range(n)]


def _seesaw_rows(n=20, a="光模块", b="创新药"):
    """构造标准跷跷板: 每 3 天换一次手, 一边热时另一边为 0。"""
    rows = []
    for i, d in enumerate(_dates(n)):
        if (i // 3) % 2 == 0:
            rows.append((d, a, 80))
            rows.append((d, b, 5))
        else:
            rows.append((d, a, 5))
            rows.append((d, b, 80))
    return rows


# ---------- 序列构建 ----------

def test_build_strength_fills_absent_days_with_zero():
    d1, d2 = _dates(2)
    df = _mainline_df([(d1, "光模块", 80), (d2, "创新药", 60)])
    dates, series = seesaw.build_strength(df)
    assert dates == [d1, d2]
    assert series["光模块"] == [80.0, 0.0], "缺席日必须补 0 —— 熄火本身就是信息"
    assert series["创新药"] == [0.0, 60.0]


def test_build_strength_windows_to_latest_days():
    all_dates = _dates(60)
    df = _mainline_df([(d, "光模块", 50) for d in all_dates])
    dates, series = seesaw.build_strength(df, window=10)
    assert len(dates) == 10 and dates[-1] == all_dates[-1], "只保留最近 N 天"
    assert len(series["光模块"]) == 10


def test_build_strength_empty_inputs():
    assert seesaw.build_strength(pl.DataFrame()) == ([], {})
    assert seesaw.build_strength(pl.DataFrame({"date": ["2026-06-01"]})) == ([], {})


# ---------- 统计量 ----------

def test_pearson_perfect_inverse():
    assert seesaw.pearson([1, 2, 3, 4], [4, 3, 2, 1]) == pytest.approx(-1.0)


def test_pearson_constant_series_is_zero():
    assert seesaw.pearson([5, 5, 5, 5], [1, 2, 3, 4]) == 0.0


def test_alternations_counts_lead_switches():
    a = [80, 80, 5, 5, 80, 80]
    b = [5, 5, 80, 80, 5, 5]
    assert seesaw.alternations(a, b) == 2, "领先方换了两次手"


def test_alternations_ignores_noise_level_gaps():
    a = [50, 51, 50, 49]
    b = [49, 50, 51, 50]
    assert seesaw.alternations(a, b) == 0, "差距在噪声内不算换手"


def test_score_pair_rewards_real_seesaw_over_codecline():
    rows = _seesaw_rows()
    dates, series = seesaw.build_strength(_mainline_df(rows))
    real = seesaw.score_pair(series["光模块"], series["创新药"])
    # 同步衰减: 两边一起从高走低 —— 相关为正, 不该被当成跷跷板
    decay = seesaw.score_pair([80, 70, 60, 50, 40], [78, 68, 58, 48, 38])
    assert real["score"] > 70 and real["flips"] >= 4
    assert decay["score"] < seesaw.MIN_SCORE
    assert len(dates) == 20


# ---------- 候选筛选 ----------

def test_detect_pairs_finds_the_seesaw():
    dates, series = seesaw.build_strength(_mainline_df(_seesaw_rows()))
    pairs = seesaw.detect_pairs(dates, series)
    assert len(pairs) == 1
    p = pairs[0]
    assert {p["a"], p["b"]} == {"光模块", "创新药"}
    assert p["leader"] in ("光模块", "创新药")
    assert p["lead_days"] >= 1 and p["hint"]
    assert len(p["series_a"]) == len(dates)


def test_detect_pairs_drops_cold_members():
    rows = _seesaw_rows()
    rows += [(d, "冷门", 90) for d in _dates(2)]  # 只上榜 2 天
    dates, series = seesaw.build_strength(_mainline_df(rows))
    pairs = seesaw.detect_pairs(dates, series)
    assert all("冷门" not in (p["a"], p["b"]) for p in pairs), "上榜天数不足的不参与配对"


def test_detect_pairs_rejects_flat_member_with_many_flips():
    """一边常年不动、另一边上下窜 —— 会刷出很多"换手"但没有反向关系, 不是跷跷板。"""
    rows = _seesaw_rows()
    rows += [(d, "军工", 50) for d in _dates(20)]  # 全程 50 分, 与谁都不反向
    dates, series = seesaw.build_strength(_mainline_df(rows))
    pairs = seesaw.detect_pairs(dates, series)
    assert len(pairs) == 1 and {pairs[0]["a"], pairs[0]["b"]} == {"光模块", "创新药"}


def test_detect_pairs_empty_when_no_data():
    assert seesaw.detect_pairs([], {}) == []
    assert seesaw.detect_pairs(_dates(1), {"A": [1.0]}) == []


# ---------- AI 出入参 ----------

def test_build_ai_payload_carries_real_series():
    dates, series = seesaw.build_strength(_mainline_df(_seesaw_rows()))
    pairs = seesaw.detect_pairs(dates, series)
    payload = seesaw.build_ai_payload(dates, pairs)
    assert payload["日期轴"] == dates
    assert payload["候选跷跷板"][0]["A序列"] == pairs[0]["series_a"]


def test_parse_ai_response_tolerates_fence_and_think_block():
    text = (
        "<think>先看序列…</think>\n```json\n"
        '{"summary": "资金在两条线之间来回搬。",'
        ' "picks": [{"pair": "光模块 ↔ 创新药", "verdict": "成立",'
        ' "leader": "光模块", "note": "交替四轮"}]}\n```'
    )
    out = seesaw.parse_ai_response(text, {"光模块 ↔ 创新药"})
    assert out["summary"].startswith("资金")
    assert out["picks"][0]["verdict"] == "成立"


def test_parse_ai_response_drops_fabricated_pairs():
    text = '{"summary": "看好", "picks": [{"pair": "编的 ↔ 假的", "verdict": "成立"}]}'
    out = seesaw.parse_ai_response(text, {"光模块 ↔ 创新药"})
    assert out["picks"] == [], "候选集里没有的对子一律丢弃"


def test_parse_ai_response_raises_on_garbage():
    with pytest.raises(ValueError):
        seesaw.parse_ai_response("模型今天不想说话", {"光模块 ↔ 创新药"})


# ---------- 30 天留档 ----------

@pytest.fixture()
def store(tmp_path, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    from app.services import seesaw_store
    return seesaw_store


def test_history_empty_at_first(store):
    assert store.load_history() == [] and store.load_latest() is None


def test_save_strips_series_and_returns_latest(store):
    store.save({"as_of": "2026-08-19", "kind": "concept",
                "pairs": [{"pair": "A ↔ B", "score": 80, "series_a": [1, 2], "series_b": [2, 1]}],
                "ai": {"summary": "在来回", "picks": []}})
    latest = store.load_latest()
    assert latest["as_of"] == "2026-08-19"
    assert "series_a" not in latest["pairs"][0], "序列不入档 —— 要回看直接重算"
    assert latest["ai"]["summary"] == "在来回"


def test_same_day_overwrites_not_duplicates(store):
    store.save({"as_of": "2026-08-19", "kind": "concept", "pairs": [], "ai": {"summary": "旧"}})
    store.save({"as_of": "2026-08-19", "kind": "concept", "pairs": [], "ai": {"summary": "新"}})
    hist = store.load_history()
    assert len(hist) == 1 and hist[0]["ai"]["summary"] == "新"


def test_history_keeps_30_days_newest_first(store):
    days = _dates(35, date(2026, 7, 1))
    for d in days:
        store.save({"as_of": d, "kind": "concept", "pairs": [], "ai": None})
    hist = store.load_history()
    assert len(hist) == 30, "滚动保留 30 天"
    assert hist[0]["as_of"] == days[-1], "最新在前"
    assert hist[-1]["as_of"] == days[5], "最旧的 5 条被挤掉"


def test_history_filters_by_kind(store):
    store.save({"as_of": "2026-08-19", "kind": "concept", "pairs": [], "ai": None})
    store.save({"as_of": "2026-08-19", "kind": "industry", "pairs": [], "ai": None})
    assert len(store.load_history(kind="concept")) == 1
    assert store.load_latest(kind="industry")["kind"] == "industry"


def test_corrupt_history_file_returns_empty(store):
    store._path().write_text("{ broken", encoding="utf-8")
    assert store.load_history() == []
