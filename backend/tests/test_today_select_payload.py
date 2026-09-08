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
         "why": "转多第 1 天(刚出现,入场窗口最佳)", "text": "转多:突破上关键点 12.0",
         "axes": {"quality": 98.0, "timing": 92},
         "partial": False, "duration": 1, "trend_state_cn": "上涨趋势",
         "vol_ratio": 1.7, "turnover": 2.0, "channel_pct": 0.58,
         "rs_pct": 6.0, "gap_pct": 1.2,
         "notes": [{"key": "mainline", "tone": "info", "label": "主线1·机器人",
                    "text": "今日第 1 主线"}]},
        {"symbol": "000002.SZ", "name": "万科A", "score": 88,
         "why": "转多第 2 天", "text": "转多:突破上关键点 20.0",
         "axes": {"quality": 90, "timing": 80}, "partial": False},
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


def test_payload_carries_the_score_breakdown_not_a_black_box(cands):
    """[R134/R189] 送的不再是一个黑箱"规则分", 而是两轴分解 + 原始输入。

    黑箱分只能被复述("它规则分高"), 分解才能被核对("它说时机 92, K 线上量比
    确实 1.7") —— 而核对正是我们要 AI 做的那件事。

    [R189] 两轴对 AI 尤其重要: 「质地 92 / 时机 41」直接告诉它该说"好票但今天
    不是买点", 而合成后的 61 分说不出这句话。
    """
    repo = _FakeRepo({"000001.SZ": _kline(), "000002.SZ": _kline(base=20.0)})
    payload = today_api._candidate_market_data(repo, cands)
    assert payload[0]["symbol"] == "000001.SZ"
    br = payload[0]["把握分分解"]
    assert br["总分"] == 100
    assert set(br) >= {"总分", "门槛", "质地", "时机", "算法",
                       "partial", "原始输入"}
    assert br["质地"] == 98.0 and br["时机"] == 92
    assert br["原始输入"]["量比"] == 1.7
    # 关键: 送审内容远不止分数
    assert set(payload[0]) > {"symbol", "name", "把握分分解", "规则依据", "信号摘要"}


def test_annotations_are_labelled_as_not_scoring(cands):
    """注记必须自带"不参与把握分"的标签, 否则 AI 会拿主线/胜率当理由。"""
    repo = _FakeRepo({"000001.SZ": _kline(), "000002.SZ": _kline(base=20.0)})
    payload = today_api._candidate_market_data(repo, cands)
    key = next(k for k in payload[0] if k.startswith("注记"))
    assert "不参与把握分" in key
    assert payload[0][key][0]["项"] == "主线1·机器人"


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
    sys_prompt = today_api._AI_SYSTEM
    assert "不许拿" in sys_prompt and "把握分高" in sys_prompt
    assert "粗筛门票" in sys_prompt, "必须说明把握分不是排序依据"
    for kw in ("量比", "回踩", "阻力"):
        assert kw in sys_prompt, f"提示词应引导看量价维度: {kw}"


def test_prompt_explains_the_v2_breakdown_and_that_notes_do_not_score():
    """[R134/R189] AI 拿到的是两轴分解, 提示词必须教它怎么用, 并划清注记的边界。"""
    sys_prompt = today_api._AI_SYSTEM
    for kw in ("质地", "时机", "门槛", "partial",
               # [R189] 两轴分开读才有意义 —— 提示词必须点破"好票但今天不是买点"
               "好票,但今天不是买点"):
        assert kw in sys_prompt, f"提示词缺少 {kw}"
    assert "区间最优" in sys_prompt, "必须说明曲线不是越大越好"
    assert "都不参与把握分" in sys_prompt, "注记的边界必须写死在提示词里"


def test_prompt_merges_brief_and_picks_consistently():
    """导读与优选合一: 提示词要求先优选后导读, 且输出同时含 brief 与 picks。"""
    sys_prompt = today_api._AI_SYSTEM
    assert '"brief"' in sys_prompt and '"picks"' in sys_prompt
    assert "两者结论必须一致" in sys_prompt, "导读末尾的机会必须来自优选结果"
    # 导读侧的通俗化要求不能在合并时丢掉
    assert "胶着" in sys_prompt and "大白话" in sys_prompt


# ------------------------------------------------------- [R147] 用户补充说明


def test_prompt_bounds_what_a_user_note_may_change():
    """补充说明能改关注点与措辞, 改不了输出格式与事实校验。

    这条边界必须写死在提示词里 —— 否则用户随口一句「多选几只」「不用核对」
    就能把 R121 建起来的那套约束绕过去。
    """
    sys_prompt = today_api._AI_SYSTEM
    assert "用户补充说明" in sys_prompt
    assert "它不能改变什么" in sys_prompt
    for must in ("字段与格式一字不改", "宁缺毋滥", "候选池由规则层给定"):
        assert must in sys_prompt, f"提示词缺少边界: {must}"


def test_note_goes_into_the_user_payload_not_the_system_prompt():
    """系统契约必须始终压在用户那句话之上 —— 拼进 system 等于让它可被改写。"""
    import inspect
    src = inspect.getsource(today_api.generate_today_ai)
    assert 'payload["用户补充说明"] = note' in src
    assert "note" not in today_api._AI_SYSTEM.split("### [R147]")[0], \
        "system 提示词的前半段不该出现 note 拼接"


def test_note_is_length_capped_and_optional():
    import inspect
    src = inspect.getsource(today_api.generate_today_ai)
    assert '[:500]' in src, "补充说明要限长, 免得把候选数据挤出上下文"
    sig = inspect.signature(today_api.generate_today_ai)
    assert sig.parameters["note"].default == "", "不填也要能直接分析"
