"""[fork R522] 策略页整改 —— 策略卡统一成一颗芯片, 工具条收成一行, 实现细节不再展示。

用户: 「策略页面也要整改」, 看过方案图后「确认」。
钉的是: 只有一种卡片(芯片)且芯片上不印「内置」; 周期筛选与卡片尺寸两组开关没了; 三处实现细节文案没了;
四个管理按钮只留图标但读屏读得到; 手机上芯片两列、结果头能换行。
"""
from __future__ import annotations

from tests.frontend_source import code_of

PAGE = "pages/Screener.tsx"
CARD = "components/screener/StrategyCard.tsx"


def test_R522_只有一种卡片_描述进悬停_内置不印():
    card = code_of(CARD)
    for gone in ("CARD_STYLES", "loadCardSize", "cardSize", "'large'", "'normal'"):
        assert gone not in card, f"四档尺寸又回来了: {gone}"
    assert "title={description || undefined}" in card, "描述没进悬停 —— 那条信息就这么没了"
    assert "builtin" not in card.split("BADGE_CLS_MAP")[1].split("}")[0], "「内置」又印回每颗芯片上了"
    assert "SRC_MAP: Record<string, string> = { custom: '自定义', ai: 'AI', composite: '叠加' }" in card
    assert "screenerCardSize" not in code_of("lib/storage.ts"), "只为四档服务的偏好还在"


def test_R522_工具条一行_两组开关撤了_管理按钮只留图标():
    page = code_of(PAGE)
    head = page[page.index("<PageHeader"):page.index('<div className="px-3 pb-4 pt-3 lg:px-4 space-y-3">')]
    assert "setTfFilter" not in page and "'日线' : '分钟'" not in head, "周期筛选那组开关又回来了"
    assert "setCardSize" not in page and "'紧凑'" not in head, "卡片尺寸那组开关又回来了"
    for label in ("重载", "叠加策略", "创建策略 · AI"):
        assert f'<span className="sr-only">{label}</span>' in head, f"「{label}」不该再印文字, 但读屏要读得到"
    assert "subtitle=" not in head, "副标题(实现细节)又回来了"


def test_R522_三处实现细节不再展示():
    page = code_of(PAGE)
    assert "毫秒级 SQL" not in page
    assert "result.elapsed_ms.toFixed" not in page, "耗时又印出来了"
    assert "策略\n" not in page.split("命中 <span")[1][:400] or "displayPool.length} 策略" not in page, "「· N 策略 · 共 M 只」又回来了"
    assert "displayPool.reduce((sum, id) => sum + (hitCounts[id] ?? 0), 0)" not in page


def test_R522_手机_芯片两列_结果头能换行():
    card = code_of(CARD)
    assert "export const CARD_WRAP_CLS = 'grid grid-cols-2 gap-1.5 sm:flex sm:flex-wrap'" in card
    page = code_of(PAGE)
    assert 'className="flex flex-wrap items-center justify-between gap-y-2"' in page, "结果头放不下时按钮不换行 —— 标题会被挤成竖排"
    assert "whitespace-nowrap', TYPE.card)" in page


def test_R522_芯片不加装饰性动效():
    """芯片上的入场动画是原来就有的(0.12s, 与旧卡片同一份); 不许再加别的。"""
    card = code_of(CARD)
    for banned in ("transition-all", "hover:scale", "translate", "animate-bounce"):
        assert banned not in card, f"芯片上出现了 {banned}"
    assert card.count("animate-ping") == 1, "只允许监控开着时那一圈"
