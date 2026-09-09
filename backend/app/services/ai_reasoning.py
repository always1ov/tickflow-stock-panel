"""[fork 增强] R232 剥离模型返回里的「思考过程」, 只留正文。

用户: 「所有 ai 的返回结果要检查是否有 <think> 开头这样分析过程也返回了,
反正目前 minimax 会有返回分析过程, 要剥离只保留正文」。

## 为什么不能交给提示词

"别输出思考过程"这种话对推理型模型是无效的 —— 那段内容是模型的输出格式,
不是它听不听话的问题。MiniMax 一类会把推理直接内联在 `content` 里包在
`<think>…</think>` 中(区别于 DeepSeek 系: 那些放在独立的 `reasoning_content`
字段, `ai_provider` 已经单独处理过, 见 R22)。

所以剥离必须做在**收到文本的那一刻**, 而且要做在唯一的两个出口上:

    generate_ai_text   非流式 —— 信号 / 今日总览优选 / 消息面凝练 / 台账提炼 …
    stream_ai_text     流式   —— 个股分析 / 复盘 / 财报 / 概念轮动 / 策略生成

漏掉任何一个, 那一条链路的用户就会看到一整段"嗯,让我先看看这只票的均线…"。

## 两条必须守住的安全线

**① 剥完不能是空的。** 模型被 max_tokens 掐断时, 很可能只输出了 `<think>` 开头
的一半推理、正文一个字都没有。这时候把它剥成空字符串, 用户看到的是"点了没反应"
—— 比看到推理过程更糟, 而且完全查不出原因。所以: **剥完为空就退回原文**。
这与 `ai_provider` 里 R22 那段(content 空则取 reasoning_content)是同一条纪律。

**② 流式不能把标签切两半。** `<think>` 六个字符可以正好跨在两个 chunk 之间,
`"…<thi"` + `"nk>…"`。天真的逐块 replace 会漏掉它, 于是前端先闪出半个标签、
再把整段推理照原样打上屏。`StreamStripper` 因此是**有状态**的: 尾部凡是可能
构成标签前缀的字符一律扣住不发, 等下一块到了再判。
"""
from __future__ import annotations

import re

# 认哪些标签。各家写法不一, 但都是这几个词的变体; 大小写不敏感。
# `think` 放前面只是可读性, 正则是并联的, 不分先后。
_TAGS = ("think", "thinking", "reasoning", "reflection")
_NAMES = "|".join(_TAGS)

# 成对出现的整段: <think> … </think>
_BLOCK_RE = re.compile(rf"<\s*({_NAMES})\s*>.*?<\s*/\s*\1\s*>", re.I | re.S)
# 落单的开标签(模型被掐断, 只开没合)—— 连同它后面的全部内容一起丢
_OPEN_TAIL_RE = re.compile(rf"<\s*({_NAMES})\s*>.*", re.I | re.S)
# 落单的闭标签(有些模型开标签根本不输出, 直接以 </think> 收尾)——
# 它前面那一坨就是推理, 一并丢
_CLOSE_HEAD_RE = re.compile(rf".*?<\s*/\s*({_NAMES})\s*>", re.I | re.S)

# 流式用: 尾巴上任何"可能正在长成一个标签"的片段。扣住不发, 等下一块。
_PARTIAL_TAIL_RE = re.compile(r"<[a-zA-Z/\s]{0,12}$")


def strip_reasoning(text: str | None) -> str:
    """剥掉思考段, 返回正文。**剥完为空时退回原文** —— 见模块头的安全线①。

    纯函数。传 None 或空串返回空串。
    """
    if not text:
        return ""
    original = text

    # 顺序要紧: 先消成对的整段, 剩下的落单标签才好判。
    # 反过来先处理落单闭标签的话, `<think>A</think>正文` 会被 _CLOSE_HEAD_RE
    # 从头吃到 `</think>`, 结果碰巧也对; 但 `正文一<think>推理</think>正文二`
    # 就会把"正文一"一起吃掉。所以必须成对优先。
    out = _BLOCK_RE.sub("", text)
    # 还剩闭标签 = 开标签没输出, 它前面是推理
    if re.search(rf"<\s*/\s*({_NAMES})\s*>", out, re.I):
        out = _CLOSE_HEAD_RE.sub("", out, count=1)
    # 还剩开标签 = 被掐断了, 后面全是推理
    out = _OPEN_TAIL_RE.sub("", out)

    out = out.strip()
    if out:
        return out
    # 安全线①: 整段都是推理(多半是被 max_tokens 掐断)。给原文, 别给空白 ——
    # 用户看到推理还能判断"是 token 不够", 看到空白只会以为点了没反应。
    return original.strip()


class StreamStripper:
    """流式版本。逐块喂 `feed()`, 结束时**务必**调一次 `flush()`。

    状态只有两个: 在不在思考段里、尾巴上扣着多少还没敢发的字符。

    >>> s = StreamStripper()
    >>> s.feed("<thi") + s.feed("nk>推理</think>正") + s.feed("文") + s.flush()
    '正文'
    """

    # 思考段里只需扣住"闭标签可能被切开"那点尾巴。取 64 而不是紧贴
    # `</think>` 的 8 —— 标签里允许有空格(`</ reflection >`), 留足余量不花钱。
    _TAIL_KEEP = 64
    # 但**还没发过任何正文**时不能只留尾巴: 那时这段推理就是 flush 的兜底内容
    # (安全线①), 只留 64 字用户看到的是半句话。攒到这个上限为止 ——
    # 推理本身受 max_tokens 约束, 几 KB 顶天, 不会撑爆。
    _FALLBACK_KEEP = 4000

    __slots__ = ("_inside", "_buf", "_emitted")

    def __init__(self) -> None:
        self._inside = False
        self._buf = ""
        self._emitted = False

    def feed(self, chunk: str | None) -> str:
        """吃一块, 吐出这一块里可以安全下发的正文(可能是空串)。"""
        if not chunk:
            return ""
        self._buf += chunk
        out: list[str] = []

        while self._buf:
            if self._inside:
                m = re.search(rf"<\s*/\s*({_NAMES})\s*>", self._buf, re.I)
                if not m:
                    # 还在思考段里。闭标签可能正跨在块边界上, 尾巴必须留。
                    # 留多长看有没有发过正文 —— 见 _TAIL_KEEP / _FALLBACK_KEEP。
                    keep = self._TAIL_KEEP if self._emitted else self._FALLBACK_KEEP
                    self._buf = self._buf[-keep:]
                    break
                self._buf = self._buf[m.end():]
                self._inside = False
                continue

            m = re.search(rf"<\s*({_NAMES})\s*>", self._buf, re.I)
            if m:
                out.append(self._buf[: m.start()])
                self._buf = self._buf[m.end():]
                self._inside = True
                continue

            # 段外, 且没有完整开标签。尾部若像半个标签就扣住, 其余放行。
            hold = _PARTIAL_TAIL_RE.search(self._buf)
            cut = hold.start() if hold else len(self._buf)
            out.append(self._buf[:cut])
            self._buf = self._buf[cut:]
            break

        text = "".join(out)
        if text:
            self._emitted = True
        return text

    def flush(self) -> str:
        """流结束。吐出扣着的尾巴。

        安全线①的流式版: 从头到尾一个正文字符都没发出去, 说明这次回答整段
        都是推理(多半被掐断)。这时把扣着的内容原样交出去, 而不是让用户对着
        一片空白 —— 与 `strip_reasoning` 同一条纪律。
        """
        tail, self._buf = self._buf, ""
        if self._inside:
            return "" if self._emitted else tail.strip()
        return tail
