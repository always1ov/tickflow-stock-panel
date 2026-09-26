"""[fork R521] 决策台「只看要动的」默认开着, 并且记住。

用户把这个决定交给我(「等我的事件, 你帮我选择最优解拍板」)。取舍与模拟盘同一条: 「没事是常态」——
一百多只自选里天天真该看的就那几只, 先列全部是让人先过一遍噪音再找信号。
钉的是: 默认 true; 存 localStorage; 切开关走同一个 setter; 定位到被它挡住的票时仍会自动关掉(R330/R157 那条没丢)。
"""
from __future__ import annotations

from tests.frontend_source import code_of

BOARD = "components/stock-analysis/WatchlistDecisionBoard.tsx"


def test_R521_默认开着_并且记住():
    code = code_of(BOARD)
    assert "useState(() => storage.boardActionableOnly.get(true))" in code, "默认不是开着 / 没记住"
    assert "storage.boardActionableOnly.set(n)" in code, "切开关没落盘, 刷新就忘"
    assert "boardActionableOnly:  kv<boolean>('board-actionable-only')" in code_of("lib/storage.ts")
    assert "useState(false)" not in next(l for l in code.splitlines() if "actionableOnly" in l and "useState" in l)


def test_R521_定位到被挡住的票仍会自动关掉():
    """搜索 / 从别页跳来定位一只「无事」的票, 默认开着的筛选会把它挡住 —— 那段兜底必须还在, 否则「点了定位没反应」。"""
    code = code_of(BOARD)
    assert "const byAction = actionableOnly && urgency[sym]?.level === 'idle'" in code
    assert "if (byAction) setActionableOnly(false)" in code, "定位时不再自动关掉「只看要动的」"
