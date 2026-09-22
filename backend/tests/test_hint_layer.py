"""[R323] 「?」说明层 + 名词说明的全局入口。

  · `Hint`: 同一份字, 桌面悬停(原生 title)/ 点一下摊开成浮层; 浮层 fixed 定位、
    贴边内挪、下面放不下翻上面、origin 跟着翻; 点别处 / Esc / 滚动收起。
  · 决策台与今日机会表的表头: 说明提成 `HEAD_TIPS`, 悬停与「?」取**同一个键**;
    「?」不许套在排序按钮里(button 套 button 是非法 HTML)。
  · 侧栏「?」打开 `GlossaryDialog`, 它复用 `ReviewHelpView`, 不誊抄第二份词表; lazy。

全部走 `code_of`(剥掉注释再断言)。
"""
from __future__ import annotations

import re

from tests.frontend_source import code_of

HINT = "components/Hint.tsx"
BOARD = "components/stock-analysis/WatchlistDecisionBoard.tsx"
OPP = "components/today/OpportunityTable.tsx"
LAYOUT = "components/Layout.tsx"
GLOSS = "components/GlossaryDialog.tsx"


# ---------- Hint 本体 ----------

def test_R323_浮层_fixed_定位_贴边内挪_放不下翻上面():
    code = code_of(HINT)
    assert "'fixed z-[70]" in code, "浮层必须 fixed —— 它常挂在 overflow 表头里, absolute 会被裁"
    eff = code[code.index("useLayoutEffect"):code.index("useEffect(")]
    assert "vw - p.width - GAP" in eff, "右边贴边要往里挪"
    assert "Math.max(b.left + b.width / 2 - p.width / 2, GAP)" in eff, "左边贴边要往里挪"
    assert "fitsBelow = b.bottom + OFFSET + p.height <= vh - GAP" in eff
    assert "setAbove(!fitsBelow)" in eff
    assert "above ? 'origin-bottom' : 'origin-top'" in code, "翻到上面时 origin 也得翻 —— 浮层从触发器长出来"


def test_R323_点别处_Esc_滚动_都收起():
    code = code_of(HINT)
    # 切到 JSX 开头的 `<>` —— 不能切到 "return (": 清理函数的 `return () =>` 会先撞上
    eff = code[code.index("useEffect("):code.index("<>")]
    assert "document.addEventListener('pointerdown', onDoc)" in eff
    assert "document.addEventListener('keydown', onKey)" in eff
    assert "window.addEventListener('scroll', onScroll, true)" in eff
    assert "if (e.key === 'Escape') setOpen(false)" in eff
    assert "btnRef.current?.contains(t) || popRef.current?.contains(t)" in eff, "点在自己身上不算点别处"
    for ev in ("pointerdown", "keydown", "scroll"):
        assert f"removeEventListener('{ev}'" in eff, f"{ev} 没卸"


def test_R323_同一份字两个出口_开着时不再叠原生_tooltip():
    code = code_of(HINT)
    assert "title={open ? undefined : title}" in code
    pop = code[code.index("role=\"tooltip\""):]
    assert "{title}" in pop, "浮层印的必须是同一份 title"
    assert "whitespace-pre-line" in pop, "说明里的 \\n 要换行"
    assert "e.stopPropagation(); setOpen(o => !o)" in code, "点「?」不能顺带触发表头排序"


def test_R323_浮层动效在_tooltip_那一档():
    code = code_of(HINT)
    pop = code[code.index("role=\"tooltip\""):]
    assert "animate-pop-in" in pop, "180ms pop-in, 在 125~200ms 那档"
    assert "animate-in" not in pop


# ---------- 两张表的表头 ----------

def _ths(rel: str) -> list[str]:
    code = code_of(rel)
    head = code[code.index("<thead"):code.index("</thead>")]
    return re.findall(r"<th\b.*?</th>", head, re.S)


def _hinted(ths: list[str]) -> list[str]:
    return [th for th in ths if "<Hint" in th]


def test_R323_决策台五个有说明的表头_悬停与问号同一个键():
    ths = _hinted(_ths(BOARD))
    # [R425] 5 → 4: 「走势」「位置」两列并成「走势/位置」一列, 两份说明并成 HEAD_TIPS.trendPos 一份
    assert len(ths) == 4, f"决策台该有 4 个带「?」的表头, 现在 {len(ths)}"
    for th in ths:
        keys = set(re.findall(r"title=\{HEAD_TIPS\.(\w+)\}", th))
        assert len(keys) == 1, f"同一个表头里悬停与「?」用了不同的键: {keys}"
        assert th.count("HEAD_TIPS.") == 2, "悬停一处 + 「?」一处, 正好两处"


# [R323 → **R351 退役**] `test_R323_今日机会表四个有说明的表头_悬停与问号同一个键`
# 钉的是今日总览机会表的四个表头。**那张表随页面一起删了**(今日总览的内容已经
# 逐块融进模拟盘), 所以它**没有可守的对象了, 而不是被绕过去了**。
#
# 同一条立论(悬停与「?」必须用同一个键)在决策台那张表上照常有守卫盯着 ——
# 见下面那三条, 它们把 OPP 从循环里去掉后继续跑。
#
# 模拟盘的信号行不是 `<table>`, 没有表头, 因此这条不需要"搬过去"。


def test_R323_表头说明不再内联_全部来自_HEAD_TIPS():
    for rel in (BOARD,):   # [R351] OPP 那张表随今日总览一起删了
        code = code_of(rel)
        head = code[code.index("<thead"):code.index("</thead>")]
        assert "title={'" not in head and 'title="' not in head, f"{rel} 表头里还有内联的说明"
        assert "const HEAD_TIPS = {" in code


def test_R323_问号不许套在排序按钮里():
    for th in _hinted(_ths(BOARD)):   # [R351] OPP 那张表没了
        if "<button" not in th:
            continue
        btn = th[th.index("<button"):th.index("</button>") + len("</button>")]
        assert "<Hint" not in btn, "button 套 button 是非法 HTML, 「?」必须是排序按钮的兄弟"


def test_R323_决策台那张表真的_import_了_Hint():
    # [R351] 原来是「两张表」, 机会表随今日总览一起删了
    for rel in (BOARD,):
        assert "import { Hint } from '@/components/Hint'" in code_of(rel)


# ---------- 全局入口 ----------

def test_R323_侧栏有个问号_打开名词说明():
    code = code_of(LAYOUT)
    assert "const GlossaryDialog = lazy(() => import('@/components/GlossaryDialog'))" in code, \
        "词表连着 27 格速查表, 必须 lazy"
    assert "onClick={() => setGlossaryOpen(true)}" in code
    i = code.index("{glossaryOpen && (")
    blk = code[i:i + 300]
    assert "<Suspense fallback={null}>" in blk
    assert "<GlossaryDialog onClose={() => setGlossaryOpen(false)} />" in blk


def test_R323_名词说明弹窗复用词表页_不誊抄():
    code = code_of(GLOSS)
    assert "import { ReviewHelpView } from '@/components/stock-analysis/ReviewHelpView'" in code
    assert "<ReviewHelpView />" in code
    assert "<Modal" in code, "走共享的 Modal 原语 —— 焦点陷阱、Esc、遮罩关闭都现成"
    # 词条正文不许在这里再写一份: 不自己拉词表、不自己渲染词条
    assert "api.glossary" not in code and "QK.glossary" not in code
    assert ".map(" not in code
