"""[fork 增强] 跨厂家模型的 JSON 输出容错解析。

用户会在不同厂家模型间切换(OpenAI 兼容口径下格式纪律参差不齐): 有的包
markdown 围栏、有的前后带解说文字、有的被 max_tokens 掐断尾巴。所有"要求
模型输出一个 JSON 对象"的调用点统一走这里, 不再各自写脆弱的一次性 loads。
"""
from __future__ import annotations

import json
import re


def extract_json_object(text: str | None) -> dict | None:
    """尽力从模型输出中抽出一个 JSON 对象; 全部尝试失败返回 None。

    依次尝试: 原文直接解析 → 文中最大花括号块 → 截断修复(从首个 '{' 起,
    逐级补右括号/引号, 抢救被 max_tokens 掐断的输出)。纯函数。
    """
    raw = (text or "").strip()
    if not raw:
        return None
    candidates = [raw]
    m = re.search(r"\{.*\}", raw, re.S)
    if m:
        candidates.append(m.group(0))
    start = raw.find("{")
    if start >= 0:
        frag = raw[start:].rstrip("`").rstrip()
        for suffix in ("", "}", "]}", '"}', '"}]}', "}}"):
            candidates.append(frag + suffix)
    for cand in candidates:
        try:
            obj = json.loads(cand)
        except Exception:  # noqa: BLE001
            continue
        if isinstance(obj, dict):
            return obj
    return None
