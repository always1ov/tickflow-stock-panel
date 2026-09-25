"""[fork R512] 模拟盘分成五栏 —— 与 Minds 同一套分栏条。

用户指着 Minds 的分栏(笔记 4 / 洞见 / 交易计划 / 对话): 「模拟盘的内容分类整理成图片这样的表达方式」,
看过五栏的效果图后: 「按照推荐实现」(栏里的卡片标题改成与栏同名)。

钉的是: 两页共用一份分栏条; 切栏不加动效; 默认落在今日信号; 自检条与报错横幅在所有栏之上;
栏名后的数与信号栏里说的是同一个判据; 分栏后变成假话的那句说明改掉了。
版面顺序、成绩一栏无条件渲染、规则不再折叠这几条, 在 test_flip_fusion / test_flip_layout_r498 里改了钉法。
"""
from __future__ import annotations

from tests.frontend_source import code_of

FLIP = "pages/FlipPaper.tsx"
TABS = "components/PageTabs.tsx"


def _jsx() -> str:
    code = code_of(FLIP)
    return code[code.index('return (\n    <div className="flex h-full flex-col">'):]


def test_R512_分栏条一处实现_两页共用():
    for page, name in ((FLIP, "FLIP_TABS"), ("pages/Minds.tsx", "MINDS_TABS")):
        src = code_of(page)
        assert f"<PageTabs tabs={{{name}}}" in src, f"{page} 没用共用的分栏条"
        assert "SEG_ITEM" not in src and "searchParams.get('tab')" not in src, f"{page} 自己又写了一份分栏"


def test_R512_切栏是瞬时的_不加动效():
    """AGENTS.md 动效硬规则第 4 条: 高频操作不加动画。分栏条只许有颜色过渡(来自 SEG_ITEM)。"""
    t = code_of(TABS)
    for banned in ("motion", "animate-", "transition-all", "transition-transform", "layoutId"):
        assert banned not in t, f"分栏条里出现了 {banned}"
    assert "setSearchParams(next, { replace: true })" in t, "切栏在堆浏览器历史"


def test_R512_五栏的名字与默认栏():
    code = code_of(FLIP)
    for key, title in (("signals", "今日信号"), ("holdings", "持仓"), ("results", "成绩"),
                       ("orders", "流水"), ("rules", "规则")):
        assert f"  {key}: {{ title: '{title}'" in code, f"{key} 那一栏名字不对"
    assert "usePageTab(FLIP_TABS, 'signals')" in code


def test_R512_栏里卡片标题与栏同名():
    code = code_of(FLIP)
    for title in ('title="今日信号"', 'title="持仓"', '<SectionHead title="成绩"', 'title="流水"', '<SectionHead title="规则"'):
        assert title in code, f"卡片标题没跟栏名统一: {title}"


def test_R512_自检条与报错横幅在所有栏之上():
    """它们说的是「你正在看的数字靠不靠得住」—— 切到哪一栏都得先看见。"""
    jsx = _jsx()
    first_tab = jsx.index("{tab === 'signals'")
    for banner in ("<TodayHealthBar", "跑不动:", "REASON_CN[d.reason]"):
        assert jsx.index(banner) < first_tab, f"{banner} 被收进了某一栏"


def test_R512_栏名后的数与信号栏同一个判据_要动手为零不挂():
    code = code_of(FLIP)
    assert "const isActionable = (r: FlipTodaySignal) => r.stage === 'flipped' && !!r.act" in code
    assert "live.filter(isActionable).length" in code, "信号栏的「N 笔要动手」没用同一个判据"
    assert "d.today.filter(isActionable).length" in code, "分栏上的数没用同一个判据"
    assert "signals: actCount > 0 ? actCount : null" in code, "要动手是 0 时挂了个 0 —— 没事是常态"


def test_R512_参数条那句说明不再指向上面():
    """分栏之后板块与门槛不在成绩上面了, 「上面那排」变成假话。
    [R515] 那句说明从参数条旁撤下(用户: 「模拟盘的只需要展示最重要的」), 只留在「回溯」框的提示里。"""
    code = code_of(FLIP)
    assert "上面那排板块与门槛" not in code and "「今日信号」栏里的板块与门槛" not in code
    assert 'title="回溯几年。板块与门槛只改打分的标注, 不进这条曲线"' in code, "那句话连提示里都没了"


