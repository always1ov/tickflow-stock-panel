"""[fork 增强] R12 仓位建议: 把握分系数 × 波动率压缩 → 单票建议仓位。"""
from app.api.today import POSTURE_CAPS, suggest_position


def test_high_score_low_vol_gets_full_cap():
    """把握分 ≥80 且波动不超标 → 给到单票上限, 向下取整到半成。"""
    r = suggest_position(90, atr_pct=0.02, max_single=0.2, target_vol=0.03)
    assert r["fraction"] == 0.2
    assert r["text"] == "建议 ≤2成"


def test_score_ladder_decreases_position():
    """分数档位: ≥80 满额 > 60-79 七折 > 40-59 三成。"""
    full = suggest_position(85, None, 0.2, 0.03)["fraction"]
    mid = suggest_position(70, None, 0.2, 0.03)["fraction"]
    low = suggest_position(45, None, 0.2, 0.03)["fraction"]
    assert full > mid > low
    assert mid == 0.1  # 0.2×0.7=0.14 → 向下取整到半成
    assert low == 0.05


def test_volatility_only_compresses_never_amplifies():
    """低波动票不许放大仓位(PRD 6.5 约束: 调整系数 ≤1)。"""
    calm = suggest_position(90, atr_pct=0.01, max_single=0.2, target_vol=0.03)
    assert calm["fraction"] == 0.2, "波动低于目标也只能拿到上限, 不能加杠杆"
    wild = suggest_position(90, atr_pct=0.06, max_single=0.2, target_vol=0.03)
    assert wild["fraction"] == 0.1  # 0.2×(3/6)=0.1
    assert "波动压缩" in wild["why"]


def test_rounding_is_conservative():
    """取整只向下(宁少勿多): 1.4成 → 1成。"""
    r = suggest_position(70, atr_pct=0.03, max_single=0.2, target_vol=0.03)
    assert r["fraction"] == 0.1  # 0.14 → 0.10


def test_tiny_position_becomes_watch_only():
    r = suggest_position(45, atr_pct=0.08, max_single=0.1, target_vol=0.03)
    assert r["fraction"] == 0.0
    assert r["text"] == "仅观察仓"


def test_score_below_20_gives_none():
    assert suggest_position(15, 0.02, 0.2, 0.03) is None


def test_missing_atr_skips_vol_adjustment():
    r = suggest_position(85, None, 0.2, 0.03)
    assert r["fraction"] == 0.2
    assert "波动压缩" not in r["why"]


def test_posture_caps_are_ordered():
    """总仓位基调: 进攻 > 谨慎/观察 > 防守。"""
    assert POSTURE_CAPS["进攻"] > POSTURE_CAPS["谨慎"] > POSTURE_CAPS["防守"]
    assert POSTURE_CAPS["观察"] <= POSTURE_CAPS["谨慎"]
