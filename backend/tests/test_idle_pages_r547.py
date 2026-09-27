"""[fork R547] 闲置四页整改: 概念分析 / 行业分析内容铺满。

用户: 「剩下的所有页面都需要整改」, 看过闲置四页方案图后「确认」。这四页在「闲置功能」分组, 按「少动」只做一处
全站一致性修正; 看板 / 连板梯队本轮不动(见 FORK_NOTES.R547)。
"""
from __future__ import annotations

import pytest

from tests.frontend_source import code_of


@pytest.mark.parametrize("page", ["pages/ConceptAnalysis.tsx", "pages/IndustryAnalysis.tsx"])
def test_R547_概念行业分析铺满(page):
    assert "mx-auto w-full max-w-[1440px]" not in code_of(page)
