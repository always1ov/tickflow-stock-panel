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
    # [R549] 轨道同时过渡颜色(150ms ease)与按压缩放(160ms 有力 ease-out), 取值见 test_R549_按压缩放有过渡
    assert "background-color_150ms_ease" in sw
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


def test_R549_按压缩放有过渡():
    # 全站 :active → scale(0.97); 轨道原来只过渡颜色, 缩放瞬间跳变
    sw = code_of(SWITCH)
    assert "[transition:background-color_150ms_ease,transform_160ms_var(--ease-out-strong)]" in sw


def test_R549_开关不嵌在按钮里():
    # 数据源编辑器的数据集行: 开关原来嵌在整行 <button> 里, 按下开关整行跟着缩
    code = code_of("pages/settings/DataSourceEditor.tsx")
    assert "function Toggle" not in code
    row = code[code.index("onClick={() => setActiveTab(key)}"):]
    assert row.index("</button>") < row.index("<Switch"), "开关又塞回行按钮里了"
