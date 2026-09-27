"""[fork R544] Minds 整改: 手机上笔记输入框占整行、标签颜色走令牌。

用户: 「剩下的所有页面都需要整改」, 看过 Minds 方案图后「确认」。只改表达, 笔记/总览/对话一个没动。
"""
from __future__ import annotations

from tests.frontend_source import code_of

NOTES = "pages/UsageNotes.tsx"


def test_R544_手机上输入框占整行():
    n = code_of(NOTES)
    assert "flex flex-wrap items-start gap-2 sm:flex-nowrap" in n
    assert "'max-sm:basis-full'" in n


def test_R544_标签颜色走令牌():
    n = code_of(NOTES)
    assert "emerald" not in n and "amber-" not in n
    assert "text-bear" in n and "text-warning" in n
