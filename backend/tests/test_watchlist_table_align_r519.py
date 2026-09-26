"""[fork R519] 自选「一张表」: 名称那一格右边的按钮组每行对齐。

用户: 「一张表, 显示全部个股或者未分组的个股, 我滚动个股, 会发现不对齐, 可能是有些分组了, 有些没分组导致了视觉差别」。

根因: 分组选择器按钮的宽度跟着内容走 —— 未分组是 14px 的文件夹图标, 一个组是 8px 的圆点, 叠点更宽,
超过三个组还挂「+N」。这组按钮靠右对齐(ml-auto), 于是它的左边缘每行不同(实测三个位置, 最多差 24px)。
修法: 按钮定宽 32px、内容居中。
"""
from __future__ import annotations

from tests.frontend_source import code_of


def _picker() -> str:
    code = code_of("components/WatchlistGroups.tsx")
    i = code.index("export function WatchlistGroupPicker(")
    return code[i:code.index("createPortal(", i)]


def test_R519_分组按钮定宽_内容居中():
    btn = _picker()
    cls = btn[btn.index('aria-label={`${symbol} 的分组`}') - 1200:btn.index('aria-label={`${symbol} 的分组`}')]
    assert "inline-flex h-5 w-8 shrink-0 items-center justify-center" in cls, "分组按钮又按内容撑宽了 —— 每行的按钮组会对不齐"
    assert "px-1" not in cls, "定宽之后不该再靠左右内边距撑宽"


def test_R519_按钮里最宽的那种装得下():
    """最宽的一种: 三个叠点(8 + 4 + 4 = 16px) + 「+N」—— 32px 放得下; 叠点上限不许放宽。"""
    btn = _picker()
    assert "const dots = memberGroups.slice(0, 3)" in btn, "叠点上限变了, 32px 可能装不下"
    assert "+{memberGroups.length - 3}" in btn
