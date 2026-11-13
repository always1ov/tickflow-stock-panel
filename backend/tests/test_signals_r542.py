"""[fork R542] 信号库整改: 分栏进页头并记在 ?tab=、去掉卡片外框、铺满、手机条件不乱折。

用户: 「剩下的所有页面都需要整改」, 看过信号库方案图后「确认」。只改表达, 信号定义/条件/启停/删除一个没动。
"""
from __future__ import annotations

from tests.frontend_source import code_of

PAGE = "custom/signals/extension.tsx"


def test_R542_单一视图_不再需要分栏():
    # [R568 同步上游 v0.3.6] 信号全面去内置化: 「内置信号」清单已不存在
    # (BUILTIN_SIGNAL_DEFINITIONS 已删), 所以 R542 的 custom/builtin 分栏
    # 天然失去意义, 上游把页面改成单视图 PageHeader + 卡片网格。
    # 这里改守「仍是页头 + 没有旧的内联分段控件」, 不再要求 PageTabs。
    page = code_of(PAGE)
    assert "<PageHeader" in page
    assert "useState<SignalSection>" not in page
    assert "SEG_ITEM" not in page


def test_R542_不设宽度上限_不再卡片套卡片():
    page = code_of(PAGE)
    assert "max-w-6xl" not in page
    assert 'rounded-card border border-border bg-surface p-4">\n          <div className="grid' not in page
    assert "md:grid-cols-2 xl:grid-cols-3" in page


def test_R542_条件顺着一行流_启用色走令牌():
    page = code_of(PAGE)
    assert "flex flex-wrap items-baseline gap-x-1.5 text-xs text-secondary" in page
    assert "emerald" not in page


def test_R542_深链照旧():
    # 触发动作里「去信号库」的深链: 默认栏就是自定义信号, 高亮锚点还在
    assert "/signals?highlight=signals" in code_of("components/signals/SignalTriggerActions.tsx")
    assert 'anchor="signals"' in code_of(PAGE)
