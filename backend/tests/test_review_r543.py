"""[fork R543] 复盘页整改: 页头与菜单同名、空状态去 emoji、奖牌三色收一、历史栏放宽、铺满。

用户: 「剩下的所有页面都需要整改」, 看过复盘方案图后「确认」。只改表达, 复盘生成/定时/推送/龙虎榜数据一个没动。
R504 撤掉的四样按待办问过用户(无偏好), 代为拍板都不接回 —— 那条守卫(test_review_clean_r504)照旧有效。
"""
from __future__ import annotations

import re

from tests.frontend_source import code_of

PAGE = "custom/review/Page.tsx"


def test_R543_页头与菜单同名():
    page = code_of(PAGE)
    assert 'title="复盘"' in page and 'title="AI 复盘"' not in page


def test_R543_空状态不用_emoji_方块():
    # [R791] 空态从 Page.tsx 拆到 ReportReader.tsx(收敛成一行引导, 不再占 28rem)
    page = code_of("custom/review/ReportReader.tsx")
    assert "报告包含: 一句话定调" in page
    assert not re.search(r"icon: '[\U0001F300-\U0001FAFF☀-➿]", page), "空状态又用回 emoji 图标"


def test_R543_奖牌三色收成一种_不写死调色板():
    # [R791] 龙虎榜卡搬到 DragonTigerPanel.tsx(证据带「资金」Tab)
    page = code_of("custom/review/DragonTigerPanel.tsx")
    rank = page[page.index("function _rankCls"):page.index("function _DtPill")]
    for hue in ("amber", "zinc", "orange"):
        assert hue not in rank
    assert "emerald" not in page


def test_R791_右栏历史改底部档案带_页面仍铺满():
    """[R791] 用户「复盘部分需要出个方案大刀阔斧的改」: 21rem 常驻历史栏 → 档案带。

    旧的 R543 守卫钉的是「历史栏放宽到 21rem」, 本版整栏取消, 守卫改为钉新结构:
    四段纵轴各就各位, 且没有回到双栏。
    """
    page = code_of(PAGE)
    assert "lg:grid-cols-[1fr_21rem]" not in page, "右栏历史又回来了"
    for block in ("ReviewStatusBar", "FactsBar", "EvidenceTabs", "ReportReader", "ArchiveStrip"):
        assert block in page, f"复盘页缺少 {block}"
    assert "max-w-[1600px]" not in page
    assert "bg-gradient-to-r" not in page
