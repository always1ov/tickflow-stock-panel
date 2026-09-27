"""[fork R543] 复盘页整改: 页头与菜单同名、空状态去 emoji、奖牌三色收一、历史栏放宽、铺满。

用户: 「剩下的所有页面都需要整改」, 看过复盘方案图后「确认」。只改表达, 复盘生成/定时/推送/龙虎榜数据一个没动。
R504 撤掉的四样按待办问过用户(无偏好), 代为拍板都不接回 —— 那条守卫(test_review_clean_r504)照旧有效。
"""
from __future__ import annotations

import re

from tests.frontend_source import code_of

PAGE = "pages/Review.tsx"


def test_R543_页头与菜单同名():
    page = code_of(PAGE)
    assert 'title="复盘"' in page and 'title="AI 复盘"' not in page


def test_R543_空状态不用_emoji_方块():
    page = code_of(PAGE)
    assert "报告包含: 一句话定调" in page
    assert not re.search(r"icon: '[\U0001F300-\U0001FAFF☀-➿]", page), "空状态又用回 emoji 图标"


def test_R543_奖牌三色收成一种_不写死调色板():
    page = code_of(PAGE)
    rank = page[page.index("function _rankCls"):page.index("function _DtPill")]
    for hue in ("amber", "zinc", "orange"):
        assert hue not in rank
    assert "emerald" not in page


def test_R543_历史栏放宽_页面铺满():
    page = code_of(PAGE)
    assert "lg:grid-cols-[1fr_21rem]" in page
    assert "max-w-[1600px]" not in page
    assert "bg-gradient-to-r" not in page
