"""[fork R553] 全站悬停提示: 原生 `title` 提示换成本系统画的一层。

用户: 「整改所有悬浮」, 看过方案图后「确认」。全站 741 处 `title=` 调用方一处不改,
由入口装的一层事件委托接管(行为测试在 frontend/src/lib/titleTooltip.test.ts)。
"""
from __future__ import annotations

from tests.frontend_source import code_of


def test_R553_入口装上悬停提示层():
    assert "installTitleTooltip()" in code_of("main.tsx"), "入口没装悬停提示层, 全站又回到浏览器原生提示"


def test_R553_动效与接管范围():
    code = code_of("lib/titleTooltip.ts")
    # 只在能悬停的精确指针上接管, 触屏不碰
    assert "(hover: hover) and (pointer: fine)" in code
    # 首次有延迟防误触, 连续移动立即出现
    assert "DELAY_MS = 400" in code and "SKIP_WINDOW_MS = 300" in code
    # 入场只动 opacity / transform, 125ms 有力 ease-out, 不从 0 起
    assert "transition:opacity_125ms_var(--ease-out-strong),transform_125ms_var(--ease-out-strong)" in code
    assert "scale(0.97)" in code and "scale(0)" not in code
    # 离开要把 title 放回(读屏读的是它)
    assert "el.setAttribute('title'" in code
