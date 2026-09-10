"""[fork 增强] R292 「说明」词条 —— 六态六档 + 通道结论十档各是什么意思。

用户: 「把全景按钮改成说明或者帮助按钮, 里面是解释每个六态状态、结论状态是
什么意思」。

这一组守两件事: **词条跟着底层走**(不是誊抄), 以及**不许讲怎么算**。
"""
import pytest

from app.services import glossary


def test_R292_六态六档一个不少():
    """少一档就意味着界面上会出现一个查不到的词 —— 而这个抽屉存在的全部理由
    就是"看到不认识的词能查到"。"""
    from app.indicators.livermore import STATE_LABELS
    got = {t["code"] for t in glossary.trend_terms()}
    assert got == set(STATE_LABELS), f"六态词条与底层对不上: 少了 {set(STATE_LABELS) - got}"


def test_R292_名字与该干什么直接取自底层():
    """**不许誊抄。** 底层改了措辞, 这里必须跟着改 —— 誊抄一份的话它会开始
    说假话, 而且没有任何东西会报错(R203 的 27 格速查表当初就是为这个理由
    做成端点的)。"""
    from app.indicators.livermore import STATE_ACTION, STATE_LABELS
    for t in glossary.trend_terms():
        cn, en = STATE_LABELS[t["code"]]
        assert t["title"] == cn and t["en"] == en, f"{t['code']} 的名字对不上底层"
        assert t["action"] == STATE_ACTION[t["code"]], f"{t['code']} 的「怎么做」对不上底层"


def test_R292_每一档都有一句是什么意思():
    """作者给的是名字与该干什么, **中间缺的正是"这个词在说什么"** ——
    而那一层恰恰是点开「说明」要找的。缺一句就等于这个抽屉白开。"""
    for t in glossary.trend_terms():
        assert len(t["meaning"]) >= 12, f"{t['title']} 的释义太短, 等于没写"


def test_R292_六档按强弱排而不是字典序():
    """顺序本身也是信息: 这六个词是一条连续的强弱轴, 不是六个并列的标签。
    多头三档在前、空头三档在后, 界面上一列扫下来就看得出这件事。"""
    sides = [t["side"] for t in glossary.trend_terms()]
    assert sides == ["多头"] * 3 + ["空头"] * 3, f"没按强弱排: {sides}"


def test_R292_结论十档整条取自作者的表():
    """这一侧**一个字都不改写** —— 标题/怎么做/为什么全是作者的原话。"""
    from app.indicators.keltner import _VERDICTS
    rows = glossary.verdict_terms()
    assert len(rows) == len(_VERDICTS), "结论词条与底层档数对不上"
    for r in rows:
        title, action, detail, _side, tone, rank = _VERDICTS[r["code"]]
        assert (r["title"], r["action"], r["meaning"], r["tone"], r["rank"]) == (
            title, action, detail, tone, rank), f"{r['code']} 与底层对不上"


def test_R292_结论按作者定的偏买偏卖次序排():
    """`rank` 是作者定的(「越大越偏卖」), 界面别处的排序也直接用它 ——
    这里不另编一套, 否则同一批档位在两个地方是两个顺序。"""
    ranks = [r["rank"] for r in glossary.verdict_terms()]
    assert ranks == sorted(ranks), f"没按 rank 排: {ranks}"


def test_R292_端点吐的就是这两份():
    from app.api.stock_analysis import get_glossary
    got = get_glossary()
    assert got["trend"] == glossary.trend_terms()
    assert got["verdict"] == glossary.verdict_terms()


@pytest.mark.parametrize("code", ["UT", "DT"])
def test_R292_最强与最弱那两档说得出方向(code):
    """抽屉是给"想不起来这个词什么意思"的人看的 —— 最该说清的就是这两头。"""
    t = next(x for x in glossary.trend_terms() if x["code"] == code)
    assert ("向上" in t["meaning"]) is (code == "UT")
    assert ("向下" in t["meaning"]) is (code == "DT")
