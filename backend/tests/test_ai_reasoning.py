"""[R232] 剥离模型返回里的思考过程 —— 只留正文。

用户: 「所有 ai 的返回结果要检查是否有 <think> 开头这样分析过程也返回了,
反正目前 minimax 会有返回分析过程, 要剥离只保留正文」。

这一组盯三件事, 按重要性排:

  ① **剥完不能是空的。** 模型被 max_tokens 掐断时常常只输出了半段推理、
     正文一个字没有。剥成空白 = 用户看到"点了没反应", 比看到推理更糟,
     而且完全查不出原因。
  ② **流式不能把标签切两半。** `<think>` 可以正好跨在两个 chunk 之间。
  ③ 正常情况剥得干净, 而且**不误伤正文里的尖括号**。
"""
from __future__ import annotations

import pytest

from app.services.ai_reasoning import StreamStripper, strip_reasoning


# ---------------------------------------------------------------- 非流式

def test_剥掉开头的思考段只留正文():
    """MiniMax 最常见的样子: 整段推理顶在最前面。"""
    got = strip_reasoning("<think>先看均线,再看量能,最后给结论。</think>\n买入,理由是放量突破。")
    assert got == "买入,理由是放量突破。"


def test_思考段夹在中间时前后正文都要留下():
    """这条防的是一个具体写法错误: 若先处理落单闭标签, `正文一<think>…</think>正文二`
    会被从头吃到 `</think>`, 把「正文一」一起吞掉。所以成对的必须先消。"""
    got = strip_reasoning("结论在前。<think>中间想了想</think>补充在后。")
    assert got == "结论在前。补充在后。"


@pytest.mark.parametrize("tag", ["think", "thinking", "reasoning", "reflection"])
def test_几种常见标签名都认(tag: str):
    assert strip_reasoning(f"<{tag}>推理</{tag}>正文") == "正文"


def test_大小写与多余空格都认():
    assert strip_reasoning("<  THINK >推理</ Think  >正文") == "正文"


def test_只有闭标签也认_有些模型开标签根本不输出():
    assert strip_reasoning("嗯我想想……</think>结论是买入") == "结论是买入"


def test_被掐断只剩半段推理时退回原文而不是空白():
    """**安全线①。** 返回空串会让用户看到"点了没反应" —— 比看到推理更糟,
    因为那样连"是 token 不够"都判断不出来。"""
    truncated = "<think>这只票的 MA20 在 12.3,而当前价 13.1,所以"
    assert strip_reasoning(truncated) == truncated.strip()


def test_整段都是成对思考段没有正文时也退回原文():
    got = strip_reasoning("<think>想了很久但什么也没说</think>")
    assert "想了很久" in got, "剥成空白会让用户以为点了没反应"


def test_没有思考段时原样返回():
    assert strip_reasoning("买入,理由是放量突破。") == "买入,理由是放量突破。"


def test_不误伤正文里的尖括号():
    """K 线数据、比较符号、HTML 片段都可能带尖括号, 不能因为长得像标签就被吃掉。"""
    text = "当 MA5 < MA20 且成交量 > 1.5 倍时减仓;<b>重点</b>看量能。"
    assert strip_reasoning(text) == text


def test_空输入不炸():
    assert strip_reasoning(None) == ""
    assert strip_reasoning("") == ""


# ---------------------------------------------------------------- 流式

def _run(chunks: list[str]) -> str:
    s = StreamStripper()
    return "".join(s.feed(c) for c in chunks) + s.flush()


def test_流式基本剥离():
    assert _run(["<think>推理</think>", "买入"]) == "买入"


@pytest.mark.parametrize("cut", range(1, 7))
def test_开标签被切在任意位置都要抓住(cut: int):
    """**安全线②。** `<think>` 六个字符, 逐个切点全试一遍 ——
    天真的逐块 replace 在这里必然漏, 前端就会闪出半个标签再打上整段推理。"""
    whole = "<think>推理过程</think>正文"
    assert _run([whole[:cut], whole[cut:]]) == "正文"


@pytest.mark.parametrize("cut", range(1, 9))
def test_闭标签被切在任意位置都要抓住(cut: int):
    head, close, tail = "<think>推理", "</think>", "正文"
    whole = head + close + tail
    i = len(head)
    assert _run([whole[: i + cut], whole[i + cut:]]) == "正文"


def test_一个字符一个字符地喂也对():
    """最坏情况: 每个 chunk 只有一个字。"""
    whole = "<think>想一想</think>结论:买入"
    assert _run(list(whole)) == "结论:买入"


def test_思考段跨很多块时中间不漏字():
    chunks = ["<think>", "第一段推理", "第二段推理", "第三段推理", "</think>", "最终结论"]
    assert _run(chunks) == "最终结论"


def test_流式被掐断在思考段里时把推理交出来而不是空白():
    """安全线①的流式版 —— 从头到尾没发出过正文, 就别让用户对着一片空白。"""
    got = _run(["<think>算到一半就没了"])
    assert "算到一半" in got


def test_已经发过正文之后再被掐断在思考段里就不必补推理了():
    """正文已经到用户眼前了, 这时再把半截推理追加上去纯属噪声。"""
    got = _run(["结论:买入。", "<think>接着又想了点别的但没说完"])
    assert got == "结论:买入。"


def test_流式不误伤正文里的尖括号():
    assert _run(["当 MA5 < MA20 ", "且量 > 1.5 倍时减仓"]) == "当 MA5 < MA20 且量 > 1.5 倍时减仓"


def test_结尾像半个标签的正文最终要被吐出来():
    """扣住是为了等下一块; 流结束了就必须交出来, 否则用户丢字。"""
    assert _run(["结论:买入 <"]) == "结论:买入 <"


def test_正文与思考段交替出现():
    chunks = ["开头。", "<think>想", "一想</think>", "中间。", "<think>再想</think>", "结尾。"]
    assert _run(chunks) == "开头。中间。结尾。"


# ---------------------------------------------------------------- 接线

def test_两个出口都接上了剥离():
    """[R232] 只剥一个出口必然漏: 非流式管信号/优选/凝练/提炼, 流式管
    个股分析/复盘/财报/轮动/策略生成。这条盯的是**接线**, 不是算法。"""
    import inspect

    from app.services import ai_provider
    src = inspect.getsource(ai_provider)
    gen = src[src.index("async def generate_ai_text"): src.index("async def stream_ai_text")]
    assert "strip_reasoning" in gen, "非流式出口没接剥离 —— 信号/优选会带上思考过程"
    stream = src[src.index("async def stream_ai_text"):]
    assert "StreamStripper" in stream, "流式出口没接剥离 —— 个股分析/复盘会带上思考过程"


def test_闭标签带空格且跨块也要抓住():
    """`</ reflection >` 这种写法比 `</think>` 长得多 —— 思考段里扣住的尾巴
    必须留够, 不然闭标签被切开就再也合不上, 后面的正文全被当成推理丢掉。"""
    whole = "<reflection>推理" + "填充" * 60 + "</ reflection >正文"
    i = whole.index("</ reflection >") + 5
    assert _run([whole[:i], whole[i:]]) == "正文"


def test_长推理被掐断时兜底给的是整段而不是最后几十个字():
    """安全线①的细节: 只留 64 字尾巴的话, 用户看到的是半句话, 判断不出
    "是 token 不够"。没发过正文时要把攒下的推理整段交出来。"""
    long_reasoning = "<think>" + "".join(f"第{i}步推理。" for i in range(1, 40))
    chunks = [long_reasoning[i: i + 7] for i in range(0, len(long_reasoning), 7)]
    got = _run(chunks)
    assert "第1步推理" in got, f"开头丢了, 只剩尾巴: {got[:40]!r}"
    assert "第39步推理" in got
