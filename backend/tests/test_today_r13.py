"""[fork 增强] R13: 相对强度进把握分 + 持仓操作档位。"""
from app.api.today import holding_stance, rank_opportunities


def _trend(signal, duration, ret_20d=None, close=10.0):
    return {"state": "UT", "state_cn": "上涨趋势", "side": "多头",
            "duration": duration, "close": close, "as_of": "2026-08-15",
            "signal": signal, "signal_desc": f"突破上关键点 {close}",
            "ret_20d": ret_20d}


# ---------- 相对强度 ----------

def test_outperformer_beats_laggard():
    """同样的信号, 跑赢大盘的分数必须高于跑输大盘的。"""
    names = {"win": "跑赢", "lose": "跑输"}
    trends = {
        "win": _trend("转多", 2, ret_20d=0.12),
        "lose": _trend("转多", 2, ret_20d=-0.04),
    }
    shown, _ = rank_opportunities(trends, {}, names, bench_ret=0.02)
    scores = {o["symbol"]: o for o in shown}
    assert scores["win"]["score"] > scores["lose"]["score"]
    assert "跑赢大盘" in scores["win"]["why"]
    assert "跑输大盘" in scores["lose"]["why"]


def test_rs_skipped_without_benchmark():
    """没有大盘数据时不加不扣, 也不在理由里提大盘。"""
    names = {"a": "甲"}
    with_bench, _ = rank_opportunities(
        {"a": _trend("转多", 2, ret_20d=0.12)}, {}, names, bench_ret=None)
    assert "大盘" not in with_bench[0]["why"]


def test_rs_skipped_without_stock_return():
    names = {"a": "甲"}
    shown, _ = rank_opportunities(
        {"a": _trend("转多", 2, ret_20d=None)}, {}, names, bench_ret=0.02)
    assert "大盘" not in shown[0]["why"]


# ---------- 持仓操作档位 ----------
# [R435] AI 信号停用: 「AI 转看空 → 减仓」与「加仓」档一起撤了, holding_stance 不再收 AI 参数。

def test_exit_trumps_everything():
    stance, why = holding_stance(True, -0.10, "多头")
    assert stance == "离场"
    assert "纪律" in why


def test_bear_trend_means_reduce():
    stance, _ = holding_stance(False, -0.10, "空头")
    assert stance == "减仓"


def test_hugging_exit_line_means_reduce():
    stance, _ = holding_stance(False, -0.01, "多头")
    assert stance == "减仓"


def test_R435_不再出加仓():
    """原来「趋势刚走强 + AI 看多 + 离出场线够远」给加仓; AI 撤了之后这一档不出现
    (用户选的「加仓档不再出现」)。"""
    for dist in (-0.08, -0.20, None):
        assert holding_stance(False, dist, "多头")[0] == "持有"


def test_default_is_hold():
    assert holding_stance(False, -0.10, "多头")[0] == "持有"
