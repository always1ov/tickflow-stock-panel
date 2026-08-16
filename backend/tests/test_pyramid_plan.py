"""[fork 增强] R15 金字塔建仓路径: 试仓 → 确认加 → 上满, 价格确认驱动。"""
from app.api.today import build_pyramid_plan


def test_default_three_step_plan():
    """目标 2 成, 默认 35%/70%/2日: 试 0.5成 → 站稳加至 1成 → 上满 2成。"""
    plan = build_pyramid_plan(0.2, 62.98, 35, 70, 2)
    assert "先试 0.5成" in plan
    assert "站稳 62.98 2 日加至 1成" in plan
    assert "上满 2成" in plan
    assert "计划作废" in plan, "必须写明失败出口 —— 跌回关键点清试仓"


def test_small_target_collapses_to_two_steps():
    """目标只有 1 成时: 两步走, 不硬拆三步。"""
    plan = build_pyramid_plan(0.1, 10.5, 35, 70, 2)
    assert "上满 1成" in plan
    assert "加至" not in plan


def test_tiny_target_has_no_plan():
    """不足 1 成(观察仓/半成)没必要分批。"""
    assert build_pyramid_plan(0.05, 10.5, 35, 70, 2) is None
    assert build_pyramid_plan(0.0, 10.5, 35, 70, 2) is None


def test_missing_pivot_uses_generic_wording():
    plan = build_pyramid_plan(0.2, None, 35, 70, 2)
    assert "突破价" in plan


def test_confirm_always_above_probe():
    """确认档被调到不高于试仓档时, 自动抬高 —— 路径永远递增。"""
    plan = build_pyramid_plan(0.2, 100.0, 60, 40, 2)
    assert "先试 1成" in plan  # 0.2×60%=0.12 → 1成
    # 确认档被强制抬到 probe+10% 以上, 且不低于试仓+半成
    assert "加至 1成 " not in plan


def test_days_setting_lands_in_text():
    plan = build_pyramid_plan(0.2, 50.0, 35, 70, 3)
    assert "3 日" in plan
