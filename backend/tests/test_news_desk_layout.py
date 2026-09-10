"""[R266] 消息面版面 —— 长文一律收起, 超出了才给展开。

用户: 「消息面页面重新排版, 太占用空间了, 显示的时候也看不全」。改之前这一页把
AI 综合出来的一大段和每条笔记都**全量铺开**渲染: 一进页面整屏被总览吃光, 输入框
和卡片墙全被顶到屏外; 卡片墙里一条长记录撑出上千像素的卡片, 旁边那条只有一句话。

这一组钉住三件事: ①三处长文都过折叠 ②给不给「展开」按内容真实溢出决定而不是猜
字数 ③收起是**藏起来不是砍掉**, 展开必须能看到全文。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from tests.frontend_source import code_lines, read_src

FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "src"


def _src(rel: str) -> str:
    return read_src(rel)


def _code_lines(text: str) -> str:
    return code_lines(text)


@pytest.fixture
def page() -> str:
    return _code_lines(_src("pages/UsageNotes.tsx"))


@pytest.fixture
def comp() -> str:
    return _code_lines(_src("components/CollapsibleText.tsx"))


# ================================================================
# 三处长文都得过折叠
# ================================================================

def test_总览不再全量铺开(page):
    """**这是用户抱怨的主因** —— 一段 AI 综合几十行, 一进页面就把整屏吃光。"""
    assert "<CollapsibleText" in page
    assert "lines={SUMMARY_LINES}" in page
    assert 'text-[12px] leading-relaxed text-foreground/90">\n                {summary.text}' not in page


def test_笔记正文与凝练都过折叠(page):
    """卡片墙里一条长记录会撑出上千像素, 旁边那条只有一句话 —— 高度差到没法看。"""
    assert page.count("lines={NOTE_LINES}") == 2, "凝练与原始正文两条路都得收起"
    assert "{note.digest}" in page and "{note.content}" in page


def test_收起行数是给正文留的余量而不是砍到一行(page):
    """收到一行等于逼人每条都点展开, 那不是排版是刁难。"""
    import re
    summary = int(re.search(r"const SUMMARY_LINES = (\d+)", _src("pages/UsageNotes.tsx")).group(1))
    note = int(re.search(r"const NOTE_LINES = (\d+)", _src("pages/UsageNotes.tsx")).group(1))
    assert 4 <= summary <= 10, f"总览收起 {summary} 行不合适"
    assert 4 <= note <= 12, f"卡片收起 {note} 行不合适"


def test_展开的原文小框也有上限(page):
    """整份研报的文字贴进来, 没上限照样把卡片顶穿。"""
    assert "max-h-48 overflow-y-auto" in page


def test_新增框空着时只占一行(page):
    """textarea 的 rows 默认是 2, min-h 只管下限 —— 不写死就白占一行高。"""
    assert "rows={1}" in page


# ================================================================
# 给不给按钮 —— 量真实溢出, 不猜字数
# ================================================================

def test_按真实溢出决定给不给展开(comp):
    """列宽会变(一列/两列/三列), 同一段话在窄列里行数翻倍。

    按字数猜必然在某个宽度上判错: 要么内容被截断却没有展开入口(**就是"看不全"**),
    要么没截断还挂个没用的按钮。
    """
    assert "scrollHeight" in comp
    assert "setOverflowing" in comp
    assert ".length >" not in comp, "不许退回按字数猜"


def test_列宽变了要重新量(comp):
    """两列变三列、窄屏变一列, 行数跟着变 —— 只量一次会一直沿用旧结论。"""
    assert "ResizeObserver" in comp
    assert "ro.observe" in comp and "ro.disconnect" in comp


def test_没溢出就不给按钮也不上遮罩(comp):
    assert "{overflowing && (" in comp, "没溢出不该出现展开按钮"
    assert "overflowing ? {" in comp, "没溢出不该给文字上淡出遮罩"


def test_展开着也能判出溢出(comp):
    """展开时 clientHeight 就是全高, 拿它比永远比不出溢出, 按钮会当场消失 ——
    人就再也收不回去了。所以要拿收起高度去比。"""
    assert "lineHeightPx * lines" in comp
    assert "el.scrollHeight > el.clientHeight" not in comp


def test_遮罩不依赖底色(comp):
    """这一页三处底色各不相同(卡片/紫色总览块/原文小框), 盖底色渐变就得每处传一个
    对应颜色, 传错就露馅。对文字本身做遮罩, 一处写法处处对。"""
    assert "maskImage" in comp and "WebkitMaskImage" in comp
    assert "from-surface" not in comp


# ================================================================
# 收起是藏起来, 不是砍掉
# ================================================================

def test_收起用的是高度而不是截字符串(comp):
    """截字符串就真的丢内容了 —— 这一页的正文之后要进综合、进决策, 得能翻回原样。"""
    assert "maxHeight" in comp
    assert ".slice(" not in comp and "substring" not in comp


def test_收起不用line_clamp(comp):
    """正文是 whitespace-pre-wrap(AI 凝练带换行缩进), line-clamp 要把元素变成
    -webkit-box, 和 pre-wrap 一起用在各浏览器上表现不一致。"""
    assert "line-clamp" not in comp


# ================================================================
# 展开状态记住 + 附带内容跟着展开走
# ================================================================

def test_总览展开状态记在本地(page):
    """默认收起是对的, 但看惯了展开的人不该每次进页面都重点一次。"""
    assert "storage.newsDeskSummaryOpen" in page
    assert "newsDeskSummaryOpen" in _code_lines(_src("lib/storage.ts"))


def test_那段边界说明只在展开时出现(page):
    """收起时是在扫一眼, 两行小字白占地方; 真要细读总览时才需要看见这条界限。"""
    assert "{(summaryOpen || !summary?.text) && (" in page


def test_没有总览时那段界限照样要说(page):
    """还没生成总览的空状态下, 「不会覆盖规则层」这条边界仍然得写明白 ——
    那是这个功能的前提, 不是展开后的补充说明。"""
    assert "!summary?.text" in page
    assert "不会覆盖价格与规则层的事实" in _src("pages/UsageNotes.tsx")
