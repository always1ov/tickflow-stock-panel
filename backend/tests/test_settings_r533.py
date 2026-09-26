"""[fork R533] 设置页: 竖向菜单换成页头分栏(与 Minds / 模拟盘 / 监控中心同一份 PageTabs), 栏名去掉重复的「设置」。

用户: 「设置页面也要整改」, 看过方案图后「确认」。七个面板的内容一个没动; `?tab=` 键名一个没改(老书签与深链照旧)。
"""
from __future__ import annotations

from tests.frontend_source import code_of

PAGE = "pages/Settings.tsx"


def test_R533_走共用分栏条_不再有竖向菜单():
    code = code_of(PAGE)
    assert "usePageTab(SETTINGS_TABS, 'data-sources')" in code
    assert "<PageTabs tabs={SETTINGS_TABS}" in code
    for gone in ("PanelLeftClose", "tf-settings-nav-collapsed", "收起菜单", "<nav"):
        assert gone not in code, f"竖向菜单残余: {gone}"


def test_R533_栏名与顺序():
    code = code_of(PAGE)
    order = ["'data-sources': { title: '数据源'", "monitoring: { title: '实时监控'", "ai: { title: 'AI'",
             "menus: { title: '菜单'", "'ext-pages': { title: '扩展页面'", "timeout: { title: '网络'",
             "system: { title: '系统'"]
    idx = [code.index(o) for o in order]
    assert idx == sorted(idx), "栏的顺序变了(菜单要挨着扩展页面)"


def test_R533_键名没改_深链照旧():
    """老书签、别页「去设置」的跳转都认这几个键 —— 改栏名不许连键一起改。"""
    code = code_of(PAGE)
    for key in ("'data-sources'", "monitoring:", "ai:", "menus:", "'ext-pages'", "timeout:", "system:"):
        assert key in code
    router = code_of("router.tsx")
    for link in ("/settings?tab=data-sources", "/settings?tab=ai", "/settings?tab=queries"):
        assert link in router


def test_R533_切栏瞬时_副标题与重复标题撤掉():
    code = code_of(PAGE)
    assert "motion" not in code, "切栏又加回动效了(高频操作不加动效)"
    assert "管理账户" not in code, "副标题说的「账户」这里根本没有"
    system = code_of("pages/settings/System.tsx")
    assert 'title="系统设置"' not in system, "系统栏里又印了一遍大标题"
