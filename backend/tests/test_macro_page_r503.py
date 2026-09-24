"""[fork R503] 宏观分析页: 市场环境与情绪周期两组同时铺开, 共用时间范围; 菜单改名。

用户: 「市场环境和情绪周期两组内容不再搞同页切换, 都放在同一个页面一次性同时展示,
但仍共用时间范围。左边菜单市场环境改成宏观分析」。
"""
from __future__ import annotations

import re

from tests.frontend_source import code_of

REGIME = "pages/Regime.tsx"


def test_R503_没有页签了_两组都常驻():
    src = code_of(REGIME)
    assert "setView" not in src and "useState<'regime' | 'phase'>" not in src, "页签又回来了"
    assert "'hidden')" not in src, "有一组还会被藏起来"
    assert "两组内容同页切换" not in src


def test_R503_市场环境有组标题():
    """[R506] 情绪周期整组撤掉之后, 原来「市场环境在前、情绪周期在后」那条顺序没有对象了,
    只剩市场环境这一组; 它的组标题留着(以后再有第二组, 读的人仍然分得清)。"""
    src = code_of(REGIME)
    assert '<GroupTitle id="macro-regime" icon={Activity} title="市场环境"' in src
    assert 'aria-labelledby="macro-regime"' in src
    assert "macro-phase" not in src, "情绪周期那一组又回来了(R506 撤的)"


def test_R503_组标题比卡片标题高一级_标题不许断():
    src = code_of(REGIME)
    g = src[src.index("function GroupTitle("):]
    g = g[:g.index("\n}\n")]
    assert "TYPE.section" in g, "组标题该是 L2, 高于卡片标题 SectionTitle 的 L3"
    assert "shrink-0 whitespace-nowrap" in g and "flex flex-wrap" in g


def test_R503_仍共用一组时间范围():
    """时间范围只有一组(页头), 查询都吃同一个 histRange / days。"""
    src = code_of(REGIME)
    assert len(re.findall(r"useState<RangePreset>", src)) == 1
    assert "api.regimeHistory(histRange.start, histRange.end, histRange.limit)" in src


def test_R503_页名与菜单同名_宏观分析():
    src = code_of(REGIME)
    assert 'title="宏观分析"' in src
    assert "{ to: '/regime', label: '宏观分析', icon: Gauge }" in code_of("components/Layout.tsx")
    assert "{ id: '/regime', label: '宏观分析', type: 'builtin', visible: true }" in code_of("pages/settings/MenuSettings.tsx")
    assert "'/regime': '宏观分析'," in code_of("custom/assistant/AssistantLauncher.tsx")
