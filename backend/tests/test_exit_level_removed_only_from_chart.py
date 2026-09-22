"""[R403] 「持仓止盈」从关键价位图上撤掉 —— **撤的只是那一组线**。

用户: 「持仓止盈可以删除掉了」, 并选定范围「只删图上那一组线」。

## 这一组钉的是两件事, 第二件更要紧

**一、图上真的没有它了。** 前后端两侧都不再有 `exit` 这个价位组。

**二、出场线系统一个字没动。** 这才是这条守卫存在的理由 —— 撤一组线很容易
顺手把底下那套也删了, 而它还在撑着三个活的展示面:

    决策台「止盈线」那一列          GET /api/watchlist/exit-lines
    盘中 exit_*/exitlife_* 监控推送  position_exit.sync_exit_rules
    AI 信号里的持仓上下文(纪律第 7 条) stock_signal.py 自己那一支   [R435: AI 信号停用, 这一面随之没了]

其中**生命线**(跌破 → 无条件清仓)也长在 `position_exit.py` 里。用户的纪律写着
「卖点是止盈线、生命线、六态转弱」—— 把模块删了就等于砍掉其中两条卖出理由,
那是判定层的改变, 不是这一轮该做的事。

**顺带**: 六态(livermore)那一组线原样留着, 用户明确说过「六态的所有一点都不能改」。
"""
from __future__ import annotations

import re
from pathlib import Path

from app.indicators.levels import LEVEL_TYPES
from tests.frontend_source import code_of

BACKEND = Path(__file__).resolve().parent.parent / "app"


def test_R403_图上不再有持仓止盈这一组():
    assert "exit" not in LEVEL_TYPES, "后端还在向图上输出「持仓止盈」这一组"
    src = code_of("components/stock-analysis/AnalysisKChart.tsx")
    groups = re.search(r"LEVEL_GROUPS:[^=]*=\s*\[(.*?)\n\]", src, re.S)
    assert groups, "找不到前端的价位组注册表"
    assert "key: 'exit'" not in groups.group(1), "前端还留着「持仓止盈」的开关"
    # 价位组的联合类型也要跟着收 —— 留着的话后端不发了前端还以为会有
    assert "| 'exit'" not in src, "LevelType 还留着 'exit'"


def test_R403_六态那一组原样留着():
    """用户原话: 「六态的所有一点都不能改」。撤持仓止盈时最容易顺手碰到的就是它
    —— 两组都是 API 层注入的, 挨着写在一起。"""
    assert LEVEL_TYPES.get("livermore") == "六态关键点", "六态关键点这一组被动了"
    api = (BACKEND / "api" / "stock_analysis.py").read_text(encoding="utf-8")
    for label in ("六态跌破转弱", "六态站上转强", "六态上关键点", "六态下关键点"):
        assert label in api, f"六态注入少了一条: {label}"
    src = code_of("components/stock-analysis/AnalysisKChart.tsx")
    assert "key: 'livermore'" in src, "前端的六态开关没了"


def test_R403_出场线系统整套还在():
    """撤线不等于拆系统。这几个是它现在真在撑着的东西, 少一个就是悄悄改了判定。"""
    pe = BACKEND / "services" / "position_exit.py"
    assert pe.exists(), "position_exit.py 被删了 —— 那是拆系统, 不是撤一组线"
    src = pe.read_text(encoding="utf-8")
    for fn in ("def exit_for_symbol", "def exit_lines_for_positions", "def sync_exit_rules"):
        assert fn in src, f"出场线模块少了 {fn}"
    # 生命线 —— 「跌破生命线无条件清仓」是用户纪律里的卖点之一。
    # **钉档位表本身, 不是扫文本**: 扫 "fatal"/"lifeline" 这两个词的话, 注释里
    # 提一句就够绿了(变异测试当场证过: 把两个档位全改名, 那条断言照样过)。
    from app.services.position_exit import STAGE_ACTION, STAGE_CN
    assert STAGE_CN.get("fatal") and STAGE_CN.get("lifeline"), \
        f"生命线那两档不在了: {sorted(STAGE_CN)}"
    assert STAGE_ACTION.get("fatal") == "无条件清仓离场", \
        f"跌破生命线不再是无条件清仓: {STAGE_ACTION.get('fatal')!r}"


def test_R403_三个活的展示面一个没少():
    """决策台那一列 / 盘中推送 / AI 持仓上下文。

    [R435] 第三个(AI 信号里的持仓上下文)随 AI 信号整套停用没了 —— 那是展示面少了一个,
    出场线系统本身一个字没动(下面两条照钉)。名字不改, 免得这条的来历看不出来。"""
    wl = (BACKEND / "api" / "watchlist.py").read_text(encoding="utf-8")
    assert "exit-lines" in wl, "决策台取止盈线的那个端点没了"
    assert "watchlistExitLines" in code_of("lib/api.ts"), "前端不再取出场线"
    assert "exitLines" in code_of("components/stock-analysis/WatchlistDecisionBoard.tsx"), \
        "决策台不再用出场线"
    assert not (BACKEND / "services" / "stock_signal.py").exists(), "[R435] AI 信号已停用"
