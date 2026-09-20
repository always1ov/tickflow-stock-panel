"""被 max_tokens 掐断的模型输出, 结构化修复。

既有的 `test_ai_json_tolerant.py` 只覆盖了两种**浅层**截断 ——
`{"signal":…,"reason":"放量突破` 和 `{"picks":[{"symbol":…}` —— 它们恰好落在
旧实现那张写死的后缀表 `("", "}", "]}", '"}', '"}]}', "}}")` 里, 所以深一层的
形状一直没人发现: `{"mentions":[{…}]}` 这种**对象套数组套对象**被掐断时要补的是
`}]}`, 而表里没有这一项。

这条路正是「AI 识别文本」在用的: 粘的文章越长、认出的个股越多, `mentions` 数组
越长, 越容易被输出上限掐断 —— 然后整段解析返回空, 用户看到的是「这篇里没认出个股」。
"""
from __future__ import annotations

import json

import pytest

from app.services.ai_json import extract_json_object, repair_truncated_json

MENTIONS = (
    '{"mentions":[{"group":"船舶","name":"中国船舶","code":"600150","starred":true,'
    '"quote":"关注"},{"group":"军工","name":"中航沈飞","code":"600760","starred":false,'
    '"quote":"紧盯"}]}'
)


def test_the_exact_shape_the_old_suffix_table_missed():
    """`}]}` —— 对象没闭 + 数组没闭 + 外层没闭。旧实现在这一种上必然失败。"""
    frag = MENTIONS[: MENTIONS.index('"quote":"关注"') + len('"quote":"关注"')]
    obj = extract_json_object(frag)
    assert obj is not None
    assert obj["mentions"][0]["name"] == "中国船舶"


def test_almost_every_truncation_point_is_recoverable():
    """逐个截断点扫一遍 —— 单条用例抓不到「表里缺了哪一项」这种问题。

    判据用 `parse_mentions` 的真实门槛(至少有 name 或 code), 而不是「mentions 非空」——
    补出一个 `[{}]` 也能让后者为真, 那是自欺。
    """
    unrecoverable = []
    for cut in range(len(MENTIONS) - 1, 20, -1):
        obj = extract_json_object(MENTIONS[:cut])
        members = (obj or {}).get("mentions") or []
        if not any(m.get("name") or m.get("code") for m in members):
            unrecoverable.append(cut)
    # 只允许「第一条个股的名字都还没传完」那一小段救不回来
    assert max(unrecoverable, default=0) < 40, (
        f"第一条已成形之后还救不回来, 说明修复没按结构走: {sorted(unrecoverable)[-5:]}"
    )


def test_completed_members_survive_when_the_tail_is_cut():
    """掐在第二条中间: 第一条必须完整留住, 而不是整段作废。

    第二条只剩一个 `{"group":"军工"}` 是可以的 —— `parse_mentions` 认的是
    name/code, 既没 name 也没 code 的残条会被它跳过, 不会变成一只票。
    """
    frag = MENTIONS[: MENTIONS.index("中航沈飞") + 2]
    obj = extract_json_object(frag)
    assert obj is not None
    first = obj["mentions"][0]
    assert first["name"] == "中国船舶" and first["code"] == "600150"
    assert all(m.get("name") != "中航" for m in obj["mentions"])


@pytest.mark.parametrize("frag,expect_key", [
    ('{"signal": "buy", "confidence": 80, "reason": "放量突破', "signal"),
    ('{"picks": [{"symbol": "600487.SH"}', "picks"),
    ('{"a": {"b": {"c": [1, 2', "a"),
    ('{"a": [{"b": "x\\"y', "a"),
])
def test_shapes_including_the_two_the_repo_already_covered(frag, expect_key):
    obj = extract_json_object(frag)
    assert obj is not None and expect_key in obj


def test_a_value_cut_mid_string_is_dropped_not_completed():
    """半截值不许补成完整值 —— 那是把「中国船舶」变成「中国船」的那条路。

    本模块有简称匹配, 一个残缺的名字照样是非空字符串, 很可能解析成另一只票。
    完整的成员要留住, 被掐断的那个要丢掉。
    """
    obj = extract_json_object('{"signal": "buy", "confidence": 80, "reason": "放量突破')
    assert obj is not None
    assert obj["signal"] == "buy"          # 完整的留住
    assert obj.get("reason") in (None, "")  # 半截的不许带着残值回来

    frag = MENTIONS[: MENTIONS.index("中国船舶") + 3]   # 掐在名字中间
    obj = extract_json_object(frag)
    names = [m.get("name") for m in (obj or {}).get("mentions", [])]
    assert "中国船" not in names, f"半截名字被补成了完整值: {names}"


def test_a_dangling_backslash_never_yields_a_partial_value():
    """悬空反斜杠也是掐在字符串里 —— 同样只许丢, 不许补。"""
    obj = extract_json_object('{"a": "x\\')
    assert obj is None or obj.get("a") in (None, "")


def test_structurally_broken_input_is_refused_rather_than_patched():
    """多一个右括号说明不是被掐断而是坏数据 —— 硬补会拼出语义错误的对象。"""
    assert repair_truncated_json('{"a": 1}}') is None
    assert repair_truncated_json('{"a": [1]]}') is None
    # 这一条才真正钉住 `_scan` 的配对检查: 不做检查的话, `}` 会被当成噪声跳过,
    # 栈里还剩 `{` `[`, 补出来的 `{"a": [1]}` **能解析** —— 一个拼出来的合法对象
    # 比认输更糟, 因为调用方分不出它是不是模型真的说过的话。
    assert repair_truncated_json('{"a": [1}') is None


def test_repair_never_invents_a_member():
    """修复只许丢, 不许造 —— 补出来的成员必须是原文里就完整的那些。"""
    for cut in range(30, len(MENTIONS)):
        obj = extract_json_object(MENTIONS[:cut])
        if not obj:
            continue
        for m in obj.get("mentions", []):
            # 字段可以**缺**(那一半还没传完), 但只要在, 值就必须是原文里的真值。
            # parse_mentions 会跳过既没 name 也没 code 的残条, 所以缺字段无害。
            if "name" in m:
                assert m["name"] in ("中国船舶", "中航沈飞"), m
            if "code" in m:
                assert m["code"] in ("600150", "600760"), m
            if "group" in m:
                assert m["group"] in ("船舶", "军工"), m


def test_complete_json_is_untouched():
    assert extract_json_object(MENTIONS) == json.loads(MENTIONS)
