"""[R562] 虚拟账户「跟六态转折」页面那一块 —— 钉住两条定案。

1. 「没能动手」的记录(仓位满 / 钱不够 / 作废 / 被拒)后端照记、接口照发, **页面不显示** ——
   用户在 R499 说过「有信号没做成的就不要放出来了」。
2. 盘中越线的卡片**不带动作徽标**(R329 / R513): 越线不是出手理由, 连徽标的位置都不留。
3. 虚拟账户页不再有全属性过渡(动效硬规则第 1 条) —— R562 顺手把作者的三处改掉了。
"""
from __future__ import annotations

import re
from pathlib import Path

FE = Path(__file__).resolve().parents[2] / "frontend" / "src"
CARD = (FE / "components" / "paper" / "FlipFollowCard.tsx").read_text(encoding="utf-8")
PAPER = (FE / "pages" / "Paper.tsx").read_text(encoding="utf-8")


def _fn(src: str, name: str) -> str:
    i = src.index(f"function {name}(")
    j = src.find("\nfunction ", i + 1)
    return src[i:j if j > 0 else None]


def test_没能动手的记录不上页面():
    assert not re.search(r"\bd\??\.log\b", CARD), "R499: 有信号没做成的不放出来"


def test_盘中越线卡片没有动作徽标():
    card = _fn(CARD, "CrossingCard")
    for x in ("TrendingUp", "TrendingDown", "'买入'", "'清仓'"):
        assert x not in card, f"越线不是出手理由, 卡片上不该有 {x}"


def test_虚拟账户页没有全属性过渡():
    assert "transition-all" not in PAPER
