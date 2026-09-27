"""[fork R548] 动效评审(R535–R547)四条落地: 开关收成一个产地、滑块用有力的进出曲线、信号库删除确认不闪。

用户跑了 /review-animations, 结论「通过」附四条打磨项, 用户:「解决」。
"""
from __future__ import annotations

import pytest

from tests.frontend_source import code_of

SWITCH = "components/ui/Switch.tsx"

#: 已迁到共用 Switch 的文件 —— 里面不许再手写滑块位移
MIGRATED = [
    "pages/settings/JobTimeoutCard.tsx",
    "pages/settings/AI.tsx",
    "pages/settings/System.tsx",
    "pages/settings/Monitoring.tsx",
    "pages/settings/DataSourceEditor.tsx",
    "pages/Review.tsx",
]


def test_R548_开关动效取值():
    sw = code_of(SWITCH)
    # 滑块: 屏上位移 → 有力的 ease-in-out, 200ms; 轨道: 只变色 → ease, 150ms
    assert "transition-transform duration-expand ease-in-out-strong" in sw
    assert "transition-colors duration-hover [transition-timing-function:ease]" in sw
    assert 'role="switch"' in sw and "aria-checked={checked}" in sw
    # 只动 transform 与颜色
    for bad in ("left-[", "transition-all", "transition-ui"):
        assert bad not in sw


@pytest.mark.parametrize("path", MIGRATED)
def test_R548_设置区不再手写开关(path):
    code = code_of(path)
    assert "translate-x-[18px]" not in code and "translate-x-[14px]" not in code, f"{path} 又手写了一份开关"
    assert "Switch" in code


def test_R548_删除确认不闪():
    assert "animate-pulse" not in code_of("pages/Signals.tsx")
