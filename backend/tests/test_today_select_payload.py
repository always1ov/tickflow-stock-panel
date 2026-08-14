"""[fork 增强] AI 优选送审数据: 必须带真实量价, 而不是把规则分复述给 AI。

设计意图: 规则分只是粗筛门票; AI 的价值在于看日 K、量能、关键价位做独立的
横向对比。若送审数据里没有 K 线, AI 只能按分数排序, 这个功能就没有意义。
"""
import polars as pl
import pytest

from app.api import today as today_api


class _FakeRepo:
    def __init__(self, frames):
        self._frames = frames

    def resolve_asset_type(self, symbol):
        return "stock"

    def get_daily_asset(self, asset_type, symbol, start, end):
        return self._frames.get(symbol, pl.DataFrame())


def _kline(n=40, base=10.0):
    """构造一段有量能与均线字段的日 K。"""
    return pl.DataFrame({
        "date": [f"2026-06-{(i % 28) + 1:02d}" for i in range(n)],
        "open": [base + i * 0.1 for i in range(n)],
        "high": [base + i * 0.1 + 0.3 for i in range(n)],
        "low": [base + i * 0.1 - 0.2 for i in range(n)],
        "close": [base + i * 0.1 + 0.1 for i in range(n)],
        "volume": [1_000_000 + i * 10_000 for i in range(n)],
        "change_pct": [0.5 for _ in range(n)],
        "vol_ratio_5d": [1.2 + i * 0.01 for i in range(n)],
        "turnover_rate": [2.0 for _ in range(n)],
        "ma5": [base + i * 0.1 for i in range(n)],
        "ma10": [base + i * 0.09 for i in range(n)],
        "ma20": [base + i * 0.08 for i in range(n)],
        "ma60": [base + i * 0.05 for i in range(n)],
        "macd_hist": [0.02 for _ in range(n)],
        "rsi_14": [55.0 for _ in range(n)],
        "atr_14": [0.3 for _ in range(n)],
    })


@pytest.fixture()
def cands():
    return [
        {"symbol": "000001.SZ", "name": "平安银行", "score": 100,
         "why": "转多第 1 天(刚出现,入场窗口最佳)", "text": "转多:突破上关键点 12.0"},
        {"symbol": "000002.SZ", "name": "万科A", "score": 88,
         "why": "转多第 2 天", "text": "转多:突破上关键点 20.0"},
    ]


def test_payload_carries_real_kline_and_levels(cands):
    repo = _FakeRepo({"000001.SZ": _kline(), "000002.SZ": _kline(base=20.0)})
    payload = today_api._candidate_market_data(repo, cands)

    assert len(payload) == 2
    key = f"最近{today_api._SELECT_KLINE_DAYS}日K"
    for item in payload:
        bars = item[key]
        assert len(bars) == today_api._SELECT_KLINE_DAYS, "必须送最近 N 根日 K"
        # 量能字段是判断突破真假的核心, 不能缺
        assert "volume" in bars[0] and "vol_ratio_5d" in bars[0]
        assert "close" in bars[0] and "ma20" in bars[0]
        assert item["关键价位"], "关键价位摘要不能为空"


def test_payload_keeps_symbol_and_rule_context(cands):
    """规则分仍然带上(作为背景), 但只是候选的一部分, 不是唯一内容。"""
    repo = _FakeRepo({"000001.SZ": _kline(), "000002.SZ": _kline(base=20.0)})
    payload = today_api._candidate_market_data(repo, cands)
    assert payload[0]["symbol"] == "000001.SZ"
    assert payload[0]["规则分"] == 100
    # 关键: 送审内容远不止规则分
    assert set(payload[0]) > {"symbol", "name", "规则分", "规则依据", "信号摘要"}


def test_missing_kline_is_flagged_not_silently_dropped(cands):
    """取不到行情的候选要保留并标注, 让 AI 知道无从判断而不是凭空编。"""
    repo = _FakeRepo({"000001.SZ": _kline()})  # 第二只没有数据
    payload = today_api._candidate_market_data(repo, cands)
    assert len(payload) == 2
    assert payload[1]["kline_error"] == "暂无日 K 数据"


def test_kline_load_failure_is_contained(cands):
    """单只行情读取抛错不能拖垮整次优选。"""
    class _BoomRepo(_FakeRepo):
        def get_daily_asset(self, asset_type, symbol, start, end):
            if symbol == "000002.SZ":
                raise RuntimeError("boom")
            return super().get_daily_asset(asset_type, symbol, start, end)

    payload = today_api._candidate_market_data(_BoomRepo({"000001.SZ": _kline()}), cands)
    assert len(payload) == 2
    assert payload[1]["kline_error"] == "行情读取失败"


def test_prompt_forbids_restating_the_rule_score():
    """提示词必须明确禁止用'规则分高/AI 看多'当理由, 否则 AI 会复述分数。"""
    sys_prompt = today_api._SELECT_SYSTEM
    assert "不许拿" in sys_prompt and "规则分高" in sys_prompt
    assert "粗筛门票" in sys_prompt, "必须说明规则分不是排序依据"
    for kw in ("量比", "回踩", "阻力"):
        assert kw in sys_prompt, f"提示词应引导看量价维度: {kw}"
