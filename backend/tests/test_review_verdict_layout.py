"""[R269] 复盘·通道结论栏的版面 —— 结论在上, 依据收起, 正文占满。

用户: 「排版不合理, 要抓住重点, 下面的都看不到了, 重新设计这个部分的前端显示」。

改之前这一栏从上到下是四个各自带边框的常驻区块 —— 阶段卡、位置结论卡、七行依据表、
分档芯片 —— 加起来约 550px; 而**一个复盘面板的正文是下面那串历史段落**, 它只分到
一屏的零头, 一次露一张半卡片。主次弄反了。

这一组钉三件事:
  ① 头部只留「一眼定调 + 该盯什么」, 不再是三个独立区块
  ② 读数与说明收进「依据」且**默认收起** —— 那张表自己都写着「上面两条结论就是从
     这些读数出来的」, 依据不该压在结论和正文中间
  ③ **收起不等于删掉** —— 依据里那三样(名称/数值/解释)是 R212 改了三版才定下来的,
     一个字都不许丢
"""
from __future__ import annotations

import pytest

from tests.frontend_source import code_of, read_src

REL = "components/stock-analysis/StockReviewDialog.tsx"


@pytest.fixture(scope="module")
def dlg() -> str:
    return code_of(REL)


# ================================================================
# ① 头部压成一块
# ================================================================

def test_R269_头部合并成一块判定条(dlg):
    """三个各自带边框的区块 = 三份内外边距 + 三条边框, 光边距就吃掉近百像素。"""
    assert "function VerdictHeader" in dlg
    for gone in ("function PhaseCard", "function VerdictEdgeCard", "function ChannelPanel"):
        assert gone not in dlg, f"{gone} 还在 —— 旧的独立区块没拆干净"


def test_R269_该盯什么必须常驻(dlg):
    """**这一栏唯一的行动指引。** 别的都能收起, 它不行 ——
    收起来这一栏就只剩「现在处在下跌中」这种定性词, 没有一条能照着做的。"""
    head = dlg[dlg.index("function VerdictHeader"):dlg.index("function EvidencePanel")]
    assert "该盯什么" in head and "{ph.watch}" in head


def test_R269_位置结论压成一枚芯片(dlg):
    """样本够时它是个判断(偏买/偏卖差多少), 样本不够时它连判断都不是 ——
    两种情况都没有理由占一整块。"""
    head = dlg[dlg.index("function VerdictHeader"):dlg.index("function EvidencePanel")]
    assert "位置结论" in head
    assert "{edge.label}" in head
    assert "edge.level !== 'thin'" in head, "样本不够时不该还摆着两边的胜率"


# ================================================================
# ② 依据默认收起
# ================================================================

def test_R269_依据默认收起(dlg):
    """**这是用户抱怨的主因**: 七行读数横在结论和正文中间。"""
    assert "function EvidencePanel" in dlg
    assert "storage.reviewEvidenceOpen.get(false)" in dlg, "默认必须是收起"


def test_R269_依据展开状态记在本地(dlg):
    assert "storage.reviewEvidenceOpen.set" in dlg
    assert "reviewEvidenceOpen" in code_of("lib/storage.ts")


def test_R269_依据排在正文之前但在分档芯片之后(dlg):
    """顺序即优先级: 一眼定调 → 复盘正题(各档好不好使) → 依据 → 历史段落。
    依据摆在芯片前面, 就又变回"读数横在中间"了。"""
    view = dlg[dlg.index("function VerdictView"):]
    assert view.index("<VerdictHeader") < view.index("<OutcomeChips") < view.index("<EvidencePanel")


def test_R269_正文区拿到剩余全部高度(dlg):
    """头部省下来的空间要真的给到段落列表, 否则这次改动等于没改。"""
    view = dlg[dlg.index("function VerdictView"):]
    assert "flex-1 overflow-auto" in view


# ================================================================
# ③ 收起不等于删掉 —— R212 那三样一个字不许丢
# ================================================================

def test_R269_依据里那三样都还在(dlg):
    """名称(这个数在说什么) + 数值(能核对) + 解释(所以呢)。

    R212 记着这一块改过三版: 只给数字看不懂, 只给状态词"然后呢"答不了,
    最后用户自己定的是"保持数据, 后面加一行解释"。R269 只挪位置, 不动内容。
    """
    ev = dlg[dlg.index("function EvidencePanel"):dlg.index("function VerdictView")]
    assert "{r.label}" in ev and "{r.value}" in ev and "{r.why}" in ev


def test_R269_阶段成因与位置结论说明下沉但没丢(dlg):
    """原来它们分别在两张卡上常驻。收进依据可以, 丢掉不行 ——
    「为什么判成下跌中」是要能翻出来核对的。"""
    ev = dlg[dlg.index("function EvidencePanel"):dlg.index("function VerdictView")]
    assert "{phase.why}" in ev
    assert "{edge.text}" in ev


def test_R269_组合注记还在(dlg):
    """27 格组合的那条注记是判定的一部分, 不能在重排里蒸发。"""
    assert "combo_note" in dlg


def test_R269_收起时不渲染而不是靠样式藏(dlg):
    """`hidden` 藏起来的话, 七行表照样进 DOM、照样参与布局计算 ——
    版面是省下来了, 但长列表里这种"藏着的重排"是卡顿的常见来源。"""
    ev = dlg[dlg.index("function EvidencePanel"):dlg.index("function VerdictView")]
    assert "{open && (" in ev
