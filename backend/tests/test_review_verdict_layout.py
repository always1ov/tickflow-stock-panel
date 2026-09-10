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


def test_R269_依据走的是共用折叠件(dlg):
    """[R270] 「收起时不渲染」这条保证挪进了 `ReviewDisclosure`(见
    `test_R270_共用件收起时不渲染`), 这里只钉住依据确实走了那个件 ——
    自己另写一套开合就绕过了那条保证。"""
    ev = dlg[dlg.index("function EvidencePanel"):dlg.index("function VerdictView")]
    assert "<ReviewDisclosure" in ev
    assert "{open && (" not in ev, "别在这里另写一套开合"


# ================================================================
# [R270] 另外两个页签同一个病, 同一个治法
# ================================================================
#
# 用户: 「这三个都是要处理排版抓住重点, 都同样的问题, 尤其是组合速查好多内容都是
# 展示和个股当前状态没关系的, 相当于很多说明了」。
#
#   趋势状态   四张 text-2xl 的涨跌停计数卡 + 封板率 + 涨停出现在 —— 三百多像素
#              横在结论与逐日表之间, 而代码注释自己就写着「以下是依据(测量)」
#   组合速查   26 行别的格子长什么样 —— 查表用的参考资料, 与这只票今天无关

COMBO = "components/stock-analysis/decision-board/ComboView.tsx"


@pytest.fixture(scope="module")
def combo() -> str:
    return code_of(COMBO)


@pytest.fixture(scope="module")
def disclosure() -> str:
    return code_of("components/stock-analysis/ReviewDisclosure.tsx")


def test_R270_三处折叠只有一份实现(dlg, combo, disclosure):
    """同一段折叠逻辑抄三遍 —— 这个仓库刚为「抄了四遍的 _code_lines」付过一次代价。"""
    assert "export function ReviewDisclosure" in disclosure
    assert "<ReviewDisclosure" in dlg and "<ReviewDisclosure" in combo
    # 三处都不许各写各的开合按钮
    assert dlg.count("aria-expanded={open}") == 0, "折叠按钮该只在共用件里"
    assert combo.count("aria-expanded={open}") == 0


def test_R270_共用件收起时不渲染(disclosure):
    """收的正是长表格与二十多行卡片 —— `hidden` 藏起来照样进 DOM、照样参与布局。"""
    assert "{open && <div" in disclosure
    assert "hidden" not in disclosure


def test_R270_趋势的涨跌停统计默认收起(dlg):
    assert "function TrendStatsPanel" in dlg
    assert "storage.reviewTrendStatsOpen.get(false)" in dlg


def test_R270_六态灵不灵压成芯片(dlg):
    """和通道那侧同一个判断: 样本够时是个判断, 不够时连判断都不是 ——
    两种情况都没理由占一整块。"""
    assert "function SideEdgeChip" in dlg
    assert "function SideEdgeCard" not in dlg, "旧的整块卡片没拆掉"


def test_R270_六态的完整说明收进依据没丢(dlg):
    """芯片只放得下结论。说明可以收起, 不能丢 —— 那是"为什么这么判"。"""
    panel = dlg[dlg.index("function TrendStatsPanel"):dlg.index("function TrendView")]
    assert "{d.side_edge.text}" in panel


def test_R270_逐日表拿到剩余全部高度(dlg):
    """头部省下来的空间要真的给到正文, 否则这次改动等于没改。"""
    view = dlg[dlg.index("function TrendView"):dlg.index("function VerdictHeader")]
    assert "min-h-0 flex-1 overflow-auto" in view


def test_R270_趋势页签顺序也是结论在前(dlg):
    """一眼定调 → 复盘正题 → 依据 → 逐日表。"""
    view = dlg[dlg.index("function TrendView"):dlg.index("function VerdictHeader")]
    assert view.index("<NowCard") < view.index("<OutcomeChips") < view.index("<TrendStatsPanel")


def test_R270_组合速查其余格子默认收起(combo):
    """**用户点名的那一处**: 除了「你现在在这一格」, 剩下二十多行讲的是别的格子。"""
    assert "storage.reviewComboRestOpen.get(false)" in combo
    assert "其余 ${rest.length} 格" in combo


def test_R270_收起时用一行给出贵贱定位(combo):
    """R225 当初摆开 26 格是有道理的(有了对照才知道自己在贵贱谱系哪一端), 但
    **那个对照只需要一句话**。收起后没有这一行, 就真的丢信息了。"""
    assert "function whichGroup" in combo
    assert "落在「{mineGroup.cn}」这一段" in combo


def test_R270_算不出组合时也不留白(combo):
    """geo 缺失时 mine 是 null —— 原来整块「你现在在这一格」直接不出现,
    人看到的是一张没头没尾的对照表。"""
    assert "这只票今天算不出三档组合" in combo


def test_R270_三个页签的展开状态各记各的(dlg, combo):
    """常看读数的人和常查 27 格的人不是同一种用法, 混成一个开关谁都不合适。"""
    keys = code_of("lib/storage.ts")
    for k in ("reviewEvidenceOpen", "reviewTrendStatsOpen", "reviewComboRestOpen"):
        assert k in keys, f"{k} 没注册"
    assert "reviewTrendStatsOpen" in dlg and "reviewEvidenceOpen" in dlg
    assert "reviewComboRestOpen" in combo
