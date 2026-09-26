"""[fork R524] 监控中心整改 —— 三栏分页, 记录一条一行按日分组, 规则一条一行, 焦点名单成栏。

用户: 「监控中心页面也要整改」, 看过方案图后「确认」。
钉的是版式的骨架, 不钉像素: 分栏用共用的 PageTabs; 记录 / 规则是列表不是卡片; 手机上记录不再被规则挤没;
类型筛选只列有记录的; 新到的那条才有动效, 其余静止。
"""
from __future__ import annotations

import re

from tests.frontend_source import code_of

MONITOR = "pages/Monitor.tsx"
FOCUS = "components/monitor/FocusPanel.tsx"


def test_R524_三栏走共用的分栏条():
    code = code_of(MONITOR)
    assert "usePageTab(MONITOR_TABS, 'alerts')" in code
    assert "alerts: { title: '触发记录'" in code
    assert "rules: { title: '监控规则'" in code
    assert "focus: { title: '焦点名单'" in code
    assert "<FocusBar" not in code, "顶上那条推送焦点条还在"
    assert "<FocusPanel />" in code
    # 副标题「实时信号与规则管理」是实现描述, 撤了
    assert "实时信号与规则管理" not in code


def test_R524_记录与规则不再是两栏各自内滚():
    """手机上原来记录栏 flex-1 min-h-0 被规则栏挤成 0 高 —— 整段消失。现在整页一个滚动区, 分栏切换。"""
    code = code_of(MONITOR)
    assert 'lg:w-[400px]' not in code, "右栏 400px 规则栏还在"
    assert '<main className="min-h-0 flex-1 overflow-y-auto px-3 pb-4 pt-3 lg:px-4">' in code
    assert code.count("overflow-auto p-3.5") == 0, "栏内滚动区还在"


def test_R524_记录一条一行按日分组():
    code = code_of(MONITOR)
    assert "dayLabel(ev.ts, now)" in code, "没按日分组"
    assert "'今天 ${md}'".replace("'", "`") in code
    assert "hhmm(ev.ts)" in code, "行里应只印时分, 日期在分组标题上"
    # 严重级别只留一个点, info 灰
    assert "info: 'bg-muted/40'" in code
    # 「规则 …」那行灰字收进徽标悬停
    assert "title={ruleConditionsText(ev, customNames)}" in code
    # 卡片时代的悬停上浮与阴影没了
    assert "hover:-translate-y-px" not in code
    assert "shadow-lg shadow-black/5" not in code


def test_R524_类型筛选只列有记录的类型并带计数():
    code = code_of(MONITOR)
    assert "SOURCE_ORDER.filter(s => (sourceCounts[s] ?? 0) > 0 || s === filter)" in code
    assert "{TYPE_LABEL[s]}<span className=\"text-micro tabular-nums opacity-70\">{sourceCounts[s] ?? 0}</span>" in code


def test_R524_只有新到的那条有动效():
    """进页之后新到的记录: 淡入 + 上移 4px, 200ms, ease-out, 写完整 transform 字符串; 已有的行一律静止。"""
    code = code_of(MONITOR)
    assert "initial={isNew ? { opacity: 0, transform: 'translateY(-4px)' } : false}" in code
    assert "transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}" in code
    # 旧的 1.2 秒五帧闪烁没了
    assert "duration: 1.2" not in code
    assert "delay: Math.min(i * 0.02" not in code


def test_R524_规则一条一行_新建是主按钮():
    code = code_of(MONITOR)
    assert "buttonClass({ variant: 'primary' }, 'h-7 gap-1 px-2.5')" in code
    assert "新建规则" in code
    # 规则行是 li, 不是 motion.div 卡片
    m = re.search(r"function RulesList\(.*?\n\}\n", code, re.S)
    assert m and "<motion.div" not in m.group(0)


def test_R524_焦点名单成栏_名字统一():
    code = code_of(FOCUS)
    assert "export function FocusPanel()" in code
    assert "推送焦点" not in code
    assert "只认焦点名单" in code, "总开关丢了"
    assert "xl:grid-cols-4" in code, "四档四列"
    # 钉住 / 静音 / 观察折叠都还在
    assert "mode: pinned ? null : 'pin'" in code
    assert "mode: muted ? null : 'mute'" in code
    assert "setShowWatch" in code


# ── [R525] 用户拿手机截图指出的三处 ──────────────────────────────

def test_R525_徽标剥掉类型前缀与代码():
    """「持仓出场 · 000657.SZ · 生命线(20日线) 60.30」三段: 第一段是类型, 代码那段跟左边「谁」重复, 徽标只留最后一段。"""
    code = code_of(MONITOR)
    assert "const parts = (ev.rule_name ?? '').split(' · ')" in code
    assert "const rest = parts.slice(1).filter(p => p && p !== ev.symbol)" in code


def test_R525_行业与概念同一个词只印一次():
    code = code_of(MONITOR)
    assert "Array.from(new Set(getExtTags(ev, fields.industry)))" in code
    assert ".filter(t => !industryTags.includes(t))" in code


def test_R525_日期分组条不粘住_手机第二行价与详情同流():
    code = code_of(MONITOR)
    assert "sticky top-0" not in code, "粘住的分组条在手机上压在行文字上"
    # 手机上「价 涨跌 · 规则 · 命中 · 行业/概念」一层壳, 宽屏 display:contents 消失
    assert "pl-[3.25rem] text-xs sm:contents" in code
    assert 'className="contents sm:flex sm:min-w-0 sm:basis-0 sm:grow' in code
