"""[fork 增强] R198 决策台角上那个感叹号 —— **只讲怎么读, 不讲怎么算**。

用户: 「点击就显示这些东西的含义, 但是**不能告诉别人具体是怎么算出来的**」。
这与把 Keltner 改名成「量化波动通道」是同一个目的: 指标本身是要藏的。

文案是会漂的 —— 下次改一句话时顺手补一个「(即三带交集除以短带宽度)」就泄了。
所以拿测试扫那个文件。这是**前端文件的内容检查**, 放在后端测试里只是因为
本仓库没有前端测试运行器(package.json 里没有 vitest/jest)。
"""
import re
from pathlib import Path

import pytest

GLOSSARY = (Path(__file__).resolve().parents[2] / "frontend" / "src" / "components"
            / "stock-analysis" / "decision-board" / "GlossaryDialog.tsx")


@pytest.fixture(scope="module")
def text() -> str:
    assert GLOSSARY.exists(), f"文件不在了: {GLOSSARY}"
    return GLOSSARY.read_text(encoding="utf-8")


def _body(text: str) -> str:
    """只查真正显示给用户的那部分 —— 文件头的注释是写给维护者的, 允许提到算法。"""
    marker = "const GROUPS"
    i = text.index(marker)
    return text[i:]


# 泄露算法的几类词。分开列是为了失败时一眼看出泄的是哪一类。
FORBIDDEN = {
    "均线周期": ["MA20", "MA60", "MA120", "20 日", "60 日", "120 日", "20日", "60日", "120日"],
    "波动倍数": ["ATR", "2 倍", "2.5 倍", "3 倍"],
    "阈值": ["0.8", "80%", "1.35", "5 个", "2 天", "3 天", "0.05"],
    "构造/公式": ["交集", "除以", "均值", "RMS", "归一化", "滤波", "带通", "傅里叶",
                "Z 变换", "群延迟", "分位", "回归", "标准差", "方差"],
    "指标本名": ["Keltner", "keltner", "利弗莫尔", "Livermore", "Minervini"],
}


@pytest.mark.parametrize("kind", sorted(FORBIDDEN))
def test_文案不泄露算法(text, kind):
    body = _body(text)
    hit = [w for w in FORBIDDEN[kind] if w in body]
    assert not hit, f"「{kind}」泄露了: {hit} —— 这一份只该讲怎么读"


def test_确实讲了怎么读(text):
    """反过来也要守: 光藏不说等于没有这个按钮。每一条都得有「读法」。"""
    body = _body(text)
    assert body.count("read:") >= 10, "条目太少, 这个说明就没用"
    assert body.count("meaning:") == body.count("read:"), "每条都要有含义 + 读法两段"


def test_覆盖了本次新增的那几个词(text):
    body = _body(text)
    for term in ("快慢变化", "三线间距", "离得太远", "已经挤了", "波动主要来自",
                 "突破尝试", "主升浪", "憋着劲", "该动"):
        assert term in body, f"新词「{term}」没有解释"


def test_挂在决策台上(text):
    """写了没挂上等于没写。"""
    board = (GLOSSARY.parent.parent / "WatchlistDecisionBoard.tsx").read_text(encoding="utf-8")
    assert "GlossaryButton" in board


# ================================================================
# [R200] 不能只守感叹号那一份
#
# 只扫 GlossaryDialog 是不够的: 这一轮真的在别处翻出了泄露 —— 决策台悬停里
# 写着「破轨门槛 2 / 2.5 / 3」, 今日总览的 title 里写着「三条带的交集 / 短带
# 宽度」「最高/最低收盘 ≤ 1.35」「(9.5:20:30)」。那几处和感叹号一样是**用户
# 眼睛能看到的**, 藏不藏得住取决于最松的那一处, 不是最严的那一处。
#
# 所以把同一把尺子量到所有出现在屏幕上的通道文案。判据仍是"只查显示部分":
# 每个文件都从各自的第一段可显示内容开始扫, 文件头的注释是写给维护者的。

_FRONT = GLOSSARY.parent.parent          # frontend/src/components/stock-analysis
_SRC = _FRONT.parent.parent              # frontend/src

# 文件 → 从哪个标记之后才算"显示区"
SURFACES = {
    _FRONT / "decision-board" / "cells.tsx": "function geoLines",
    _FRONT / "StockReviewDialog.tsx": "function ChannelPanel",
    _SRC / "components" / "today" / "OpportunityTable.tsx":
        '<span className="text-foreground/90">量化波动通道</span>',
    # [R201] **导出的 HTML 是所有面里最该守的一个** —— 屏幕上的东西只有本人看得到,
    # 导出的文件是拿去发给别人的。而它恰恰是 R200 那一轮漏掉的: 页头说明里
    # 白纸黑字写着「短期 MA20±2ATR / 中期 MA60±2.5ATR / 长期 MA120±3ATR」。
    # 这条规则的教训就是"扫描面要跟着**能外传的东西**走, 不是跟着屏幕走"。
    _SRC / "lib" / "decisionBoardHtmlExport.ts": "export function buildBoardHtml",
}

# 显示区里也躲不开的技术词(它们是数据本身或纯样式), 逐条豁免而不是整类放行。
_ALLOW = ("gain_atr", "compress_avg", "compress_days", "atr", "energy.share",
          "geo.d", "font-mono", "text-muted")


_COMMENT = re.compile(r"/\*.*?\*/|(?<![:'\"])//[^\n]*", re.S)


def _visible(path: Path, marker: str) -> str:
    """显示区 = 标记之后, **去掉注释**。

    注释是写给维护者的, 该讲清楚算法; 去掉它们才分得清"泄给用户"和"写给自己"。
    这也是这组测试第一版的毛病 —— 整段扫下去, JSX 里那些 `{/* ... */}` 的推导
    说明全被当成泄露, 逼着人把注释删掉, 那是把有用的东西删了去迁就测试。
    """
    src = path.read_text(encoding="utf-8")
    assert marker in src, f"{path.name} 里找不到起点标记「{marker}」—— 测试该跟着改"
    body = _COMMENT.sub(" ", src[src.index(marker):])
    # 再滤一次: 只留**带中文的行**。这个仓库里显示给用户的字一律是中文, 而
    # `KeltnerBand` / `KELTNER_CLS` 这类是 TS 类型与样式常量 —— 它们不在屏幕上,
    # 拿泄露去卡它们只会逼人给类型改名, 那是为了测试改代码。
    body = "\n".join(ln for ln in body.splitlines()
                     if any("\u4e00" <= ch <= "\u9fff" for ch in ln))
    for tok in _ALLOW:
        body = body.replace(tok, "")
    return body


@pytest.mark.parametrize("path,marker", sorted(SURFACES.items(), key=lambda kv: kv[0].name))
@pytest.mark.parametrize("kind", ["均线周期", "波动倍数", "阈值", "构造/公式", "指标本名"])
def test_界面上其它通道文案同样不泄露(path: Path, marker: str, kind: str):
    hit = [w for w in FORBIDDEN[kind] if w in _visible(path, marker)]
    assert not hit, f"{path.name} 的「{kind}」泄露了: {hit}"


# ================================================================
# [R200] 大白话 —— 「别用拉开脱开这种词, 不够通俗易懂」
#
# 上面那组守的是"别说太多", 这一组守的是"别说得没人懂"。两件事都会让这些
# 指标白做: 前者暴露, 后者看不明白。

JARGON = ["拉开", "脱开", "粘合", "撕裂", "分离度", "偏离度", "频段",
          "归一化", "带通", "尺度撕裂", "压缩指数"]


@pytest.mark.parametrize("path,marker", sorted(
    {**SURFACES, GLOSSARY: "const GROUPS"}.items(), key=lambda kv: kv[0].name))
def test_界面文案不用行话(path: Path, marker: str):
    hit = [w for w in JARGON if w in _visible(path, marker)]
    assert not hit, f"{path.name} 里还有行话: {hit} —— 换成「挤在一起/走开/间距」这类说法"


def test_后端给界面的那几句话也是大白话():
    """`explain()` / `phase()` / `event()` 的正文是直接摆在界面上的。"""
    from app.indicators import keltner_geometry as kg

    geo = {"accel": {"level": kg.ACCEL_UP, "gain_atr": 1.4, "a1": 0.15},
           "spread": 2.2, "compress": 0.1, "torn": False, "nested": False,
           "stack": kg.STACK_BULL, "d": {"s": 1.2, "m": 2.0, "l": 3.1}}
    runs = {"compress_days": 0, "above_run": 4, "below_run": 0}
    texts = kg.explain(geo)
    ph = kg.phase(geo, runs)
    texts += [ph["cn"], ph["why"], ph["watch"]]
    ev = kg.event(state="UT", duration=3, geo=geo, run=runs)
    texts += [ev["cn"], ev["why"]]
    texts += list(kg.EVENT_CN.values()) + list(kg.PHASE_CN.values())
    texts += [t for pair in kg.COMBO_NOTES.values() for t in pair]
    blob = " ".join(texts)
    hit = [w for w in JARGON if w in blob]
    assert not hit, f"后端文案里还有行话: {hit}"
    # 单位也不点名 —— 与改名成「量化波动通道」同一个目的
    assert "ATR" not in blob, "界面文案里不该出现指标本名的单位"
