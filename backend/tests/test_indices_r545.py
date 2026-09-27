"""[fork R545] 指数页整改: 四只指数挪到顶上一排、手机上日K与分时上下叠、副标题说人话。

用户: 「剩下的所有页面都需要整改」, 看过指数方案图后「确认」。只改表达, 指数/日K/分时/同步一个没动。
"""
from __future__ import annotations

from tests.frontend_source import code_of

PAGE = "pages/Indices.tsx"


def test_R545_四只指数在顶上一排_图表吃满():
    page = code_of(PAGE)
    assert "grid grid-cols-2 gap-2 lg:grid-cols-4" in page
    assert "lg:grid-cols-[15rem_1fr]" not in page and "<aside" not in page


def test_R545_手机上两张图上下叠():
    page = code_of(PAGE)
    assert "flex flex-col gap-3 md:flex-row md:items-start" in page
    assert "useMediaQuery('(max-width: 767px)')" in page
    assert "height={620}" not in page, "图高又写死了, 手机上不会变矮"


def test_R545_副标题不写给开发者():
    page = code_of(PAGE)
    assert "kline_index_" not in page and "实时缓存" not in page
    assert "四只核心指数的日K与分时" in page
