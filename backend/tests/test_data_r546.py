"""[fork R546] 数据页整改: 首次提示挪出页头且不闪、内容铺满。

用户: 「剩下的所有页面都需要整改」, 看过数据页方案图后「确认」。只改表达, 同步/范围/修正/扩展/清除一个没动。
"""
from __future__ import annotations

from tests.frontend_source import code_of

PAGE = "pages/Data.tsx"


def test_R546_首次提示不在页头_不闪():
    page = code_of(PAGE)
    assert "首次使用请点击右侧按钮同步数据" not in page
    assert "还没有本地数据 —— 点页头「立即同步」开始第一次同步" in page
    assert "animate-pulse\">首次" not in page


def test_R546_内容铺满():
    page = code_of(PAGE)
    assert "mx-auto w-full max-w-[1100px]" not in page
