"""[fork 增强] R198 决策台角上那个感叹号 —— **只讲怎么读, 不讲怎么算**。

用户: 「点击就显示这些东西的含义, 但是**不能告诉别人具体是怎么算出来的**」。
这与把 Keltner 改名成「量化波动通道」是同一个目的: 指标本身是要藏的。

文案是会漂的 —— 下次改一句话时顺手补一个「(即三带交集除以短带宽度)」就泄了。
所以拿测试扫那个文件。这是**前端文件的内容检查**, 放在后端测试里只是因为
本仓库没有前端测试运行器(package.json 里没有 vitest/jest)。
"""
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
    for term in ("加速度", "分离度", "尺度撕裂", "粘合", "主导频段",
                 "突破尝试", "主升浪", "压缩待变", "该动"):
        assert term in body, f"新词「{term}」没有解释"


def test_挂在决策台上(text):
    """写了没挂上等于没写。"""
    board = (GLOSSARY.parent.parent / "WatchlistDecisionBoard.tsx").read_text(encoding="utf-8")
    assert "GlossaryButton" in board
