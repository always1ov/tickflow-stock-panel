"""[fork R552] 个股弹窗开合动效 —— 动效评审(R550/R551)四条。

用户跑 `/review-animations`, 结论 Block, 用户「修」。
"""
from __future__ import annotations

from tests.frontend_source import code_of


def _dlg() -> str:
    return code_of("components/StockPreviewDialog.tsx")


def test_R552_面板位移不用framer简写():
    code = _dlg()
    # 简写在主线程逐帧算, 打开时正赶上图表挂载, 会掉帧
    assert "scale: 0.95" not in code and "y: 12" not in code, "面板又用回了 scale / y 简写"
    assert "translateY(12px) scale(0.95)" in code
    # 终态收回 none: 非 none 的 transform 会成为 fixed 子元素的包含块
    assert "transitionEnd: { transform: 'none' }" in code


def test_R552_减少动态效果自己判断():
    # framer 的 reducedMotion 只认 x / y / scale 键, 不认 transform 字符串
    code = _dlg()
    assert "useReducedMotion()" in code and "reduceMotion ? 'none'" in code


def test_R552_遮罩与面板同一条曲线_退场更快():
    code = _dlg()
    assert "EASE_OUT_STRONG = [0.23, 1, 0.32, 1]" in code
    assert "transition={{ duration: 0.15 }}" not in code, "遮罩又吃回了 framer 默认的软曲线"
    assert "transition: { duration: 0.15, ease: EASE_OUT_STRONG }" in code, "面板退场没有比入场快"


def test_R552_退场期间不挡点击():
    assert "exit={{ pointerEvents: 'none' }}" in _dlg(), "退场期间遮罩又会吞掉点击"
