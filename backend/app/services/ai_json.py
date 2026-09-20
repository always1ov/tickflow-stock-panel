"""[fork 增强] 跨厂家模型的 JSON 输出容错解析。

用户会在不同厂家模型间切换(OpenAI 兼容口径下格式纪律参差不齐): 有的包
markdown 围栏、有的前后带解说文字、有的被 max_tokens 掐断尾巴。所有"要求
模型输出一个 JSON 对象"的调用点统一走这里, 不再各自写脆弱的一次性 loads。
"""
from __future__ import annotations

import json
import re


def _scan(frag: str) -> tuple[list[str], bool] | None:
    """扫一遍片段, 返回 (未闭合的括号栈, 是否停在字符串内)。

    括号配对本身就错了 (多一个右括号) 说明这不是被掐断而是坏数据, 返回 None ——
    硬补只会拼出一个语义错误的对象, 那比认输更糟。
    """
    stack: list[str] = []
    in_str = False
    esc = False
    for ch in frag:
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch in "{[":
            stack.append(ch)
        elif ch in "}]":
            want = "{" if ch == "}" else "["
            if not stack or stack[-1] != want:
                return None
            stack.pop()
    return stack, in_str


def _innermost_cut(frag: str) -> int:
    """砍掉**最内层容器里最后一个成员**之后, 片段应保留的长度; 砍不动返回 -1。

    只看最内层那一层的逗号 —— 拿整段里「最后一个逗号」会砍错层: `{"a": [{"b": "x`
    的最后一个逗号可能在外层, 甚至一个都没有, 那样就只能整段认输。这里的规则是
    「先丢最内层的最后一个成员; 这层只剩这一个残缺成员, 就把这层清空」, 于是
    `{"a": [{"b": "x` 退成 `{"a": [{`, 再补成 `{"a": [{}]}`, 外层的结构留住了。
    """
    in_str = False
    esc = False
    opens: list[int] = []      # 每层容器开括号的位置
    commas: list[int] = []     # 每层容器内**本层**最后一个逗号的位置
    for i, ch in enumerate(frag):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch in "{[":
            opens.append(i)
            commas.append(-1)
        elif ch in "}]":
            if not opens:
                return -1
            opens.pop()
            commas.pop()
        elif ch == "," and commas:
            commas[-1] = i
    if not opens:
        return -1
    return commas[-1] if commas[-1] >= 0 else opens[-1] + 1


def repair_truncated_json(frag: str, *, max_attempts: int = 64) -> str | None:
    """把被掐断的 JSON 片段补成可解析的对象文本; 补不出来返回 None。

    [安全审查 run-1 之后的排查] 这里原本是一张**写死的后缀候选表**
    `("", "}", "]}", '"}', '"}]}', "}}")`, 而 docstring 声称「逐级补右括号/引号」。
    那句话没兑现: 表里缺了 `}]}` —— 也就是「对象没闭 + 数组没闭 + 外层没闭」,
    正是 `{"mentions":[{…}]}` 这种**对象套数组套对象**被掐断时最常见的形状。
    实测 87 字符的完整输出, 66 个截断点里有 46 个救不回来。既有测试只覆盖了
    `{"signal":…,"reason":"放量突破` 和 `{"picks":[{"symbol":…}` 两种**浅层**
    形状, 都恰好落在那张表里, 所以深一层的那种一直没人发现。

    改成按结构补: 扫一遍拿到括号栈, 砍掉末尾那个残缺的成员, 再按栈反序补上
    `}` / `]`。一次补不成就往回再砍一个成员重试(见 `_innermost_cut`: 只砍最内层
    那一层) —— 掐断点越靠前, 丢掉的成员越多, 但前面已经完整的那些能留住。
    """
    cleaned = frag
    for _ in range(max_attempts):
        scanned = _scan(cleaned)
        if scanned is None:
            return None
        stack, in_str = scanned
        if in_str:
            # 掐在字符串中间: **丢掉这个成员, 不要把半截值补成完整值**。
            # 补上引号能多救一条, 但救回来的是个残缺的标识符 —— 「中国船舶」被
            # 掐成「中国船」照样是个非空字符串, 而本模块是有简称匹配的, 半截名字
            # 很可能解析成另一只票。宁可少一条, 不可错一只。
            cut = _innermost_cut(cleaned)
            if cut < 0 or cut >= len(cleaned):
                return None
            cleaned = cleaned[:cut]
            continue
        # 末尾那个悬空的 `,` / `:` 不必单独处理: 补出来的 candidate 会解析失败,
        # 下面的重试正好沿着那个逗号往回砍一格, 结果一样。多写一道反而是死代码。
        body = cleaned.rstrip()
        candidate = body + "".join("}" if ch == "{" else "]" for ch in reversed(stack))
        try:
            obj = json.loads(candidate)
        except Exception:  # noqa: BLE001
            pass
        else:
            if isinstance(obj, dict):
                return candidate
        cut = _innermost_cut(body)
        if cut < 0 or cut >= len(body):
            return None
        cleaned = body[:cut]
    return None


def extract_json_object(text: str | None) -> dict | None:
    """尽力从模型输出中抽出一个 JSON 对象; 全部尝试失败返回 None。

    依次尝试: 原文直接解析 → 文中最大花括号块 → 结构化截断修复
    (见 `repair_truncated_json`, 抢救被 max_tokens 掐断的输出)。纯函数。
    """
    raw = (text or "").strip()
    if not raw:
        return None
    # 思考型模型(<think>…</think>)先剥掉推理段 —— 里面的英文散文/花括号会干扰抽取;
    # <think> 未闭合说明输出在思考段内就被 max_tokens 掐断, 后面没有正文可救
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.S).strip()
    if "<think>" in raw:
        raw = raw.split("<think>", 1)[0].strip()
    if not raw:
        return None
    candidates = [raw]
    m = re.search(r"\{.*\}", raw, re.S)
    if m:
        candidates.append(m.group(0))
    start = raw.find("{")
    if start >= 0:
        frag = raw[start:].rstrip("`").rstrip()
        candidates.append(frag)
        repaired = repair_truncated_json(frag)
        if repaired is not None:
            candidates.append(repaired)
    for cand in candidates:
        try:
            obj = json.loads(cand)
        except Exception:  # noqa: BLE001
            continue
        if isinstance(obj, dict):
            return obj
    return None
