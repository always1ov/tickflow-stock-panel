"""[fork 增强] R214 全组合矛盾核对 —— 「结论」这一格永远不许同时叫买又叫卖。

用户: 「有矛盾, 马上逼近上沿了又叫买, 到上沿了又叫卖……我觉得你没处理好
组合表的所有情况」。

R212 只修了被用户撞见的那一格(到上沿 + 多头)。这份测试把**整张组合表**穷举
一遍, 让"还有没有别的格子也在打架"这件事由机器回答, 而不是等下一次被撞见:

    5 种短期位置 × 5 中期 × 5 长期 = 125 种通道组合
    × 7 种趋势(六态 + 读不到)
    × 持有 / 空仓
    × 4 种 AI 信号(买 / 卖 / 观望 / 无)   [R435 撤: AI 信号停用, 这一维只剩「无」]
    = 1750 例(R435 之前 7000)

穷举跑出来两个真问题, 都已修:

  ① `stock_playbook._conflicts` 的规则②(趋势 vs 通道位置)**从写下那天起
     一次都没触发过** —— 它读 `verdict["side"]`(取值 "high"/"low", 指的是
     贴上轨还是下轨), 却拿 `"sell"`/`"buy"` 去比。偏买偏卖在 verdict 里叫
     `tone`。条件恒假, 全枚举命中 0 次。

  ② `watchlist_urgency._band_call` 的「到下沿 + 多头 = 买」漏看了另外两档:
     三档全在下沿时作者的 `verdict` 说的是「下跌途中 —— 别抄」, 而这里还在
     说「相对便宜」。R212 修的是漏看趋势, 这次漏看的是漏看通道结构。

**这份测试的形状本身是有意的。** R210 那个「候选路 C 是死代码」的教训是:
纯函数测试证明不了接线, 单点用例证明不了全表。所以这里守的是两条**性质**,
而不是若干个具体输入输出:

    性质 A: 任何一格里, 两行结论的方向不许相反(除非那一格已经判成
            「先别动」或「按纪律走」—— 那两档就是专门用来说打架的)。
    性质 B: 每一条打架规则都必须在全枚举里**至少触发一次**。
            一条永远不触发的规则和没写是一回事, 而且看起来还像写了。
"""
import itertools

import pytest

from app.indicators import keltner as K
from app.services import stock_playbook as pb
from app.services import watchlist_urgency as U

POSES = (K.POS_ABOVE, K.POS_NEAR_UPPER, K.POS_INSIDE, K.POS_NEAR_LOWER, K.POS_BELOW)
STATE_CN = {"UT": "上涨趋势", "NR": "自然回升", "SR": "次级回升",
            "SREA": "次级回撤", "NREA": "自然回撤", "DT": "下跌趋势"}
STATES = (*STATE_CN, None)
# [R435] AI 信号停用, 「怎么办」不再收它的意见 —— 这一维只剩「没有」
SIGNALS = (None,)


def _bands(s, m, l):
    return {k: {"pos": p, "pos_cn": K.POS_CN[p], "upper": 11.0, "lower": 9.0}
            for k, p in (("s", s), ("m", m), ("l", l))}


def _trend(state):
    if state is None:
        return None
    return {"state": state, "state_cn": STATE_CN[state], "duration": 5,
            "side": "多头" if state in K.__dict__.get("_BULLISH", ("UT", "NR", "SR")) else "空头"}


# 「贵不贵」那一行(verdict.tone)的方向。+1 偏买, -1 偏卖, 0 不表态。
_VERDICT_DIR = {"buy": 1, "sell": -1, "avoid": -1, "hold": 0, "watch": 0}

# 「怎么办」那一行(来自 urgency)的方向。**按 kind + side 查表, 不按文案猜** ——
# 文案会改, 语义不该改; 表里少一个键就直接 KeyError, 那正是想要的:
# 新增一档判定时, 这张表逼你回答"它到底是叫买还是叫卖"。
_URGENCY_DIR = {
    ("exit_broken", U.SIDE_SELL): -1,
    ("exit_near", U.SIDE_SELL): -1,
    ("flip_down_near", U.SIDE_SELL): -1,
    ("flip_down_near", U.SIDE_INFO): 0,
    ("flip_up_near", U.SIDE_BUY): 1,
    ("flipped", U.SIDE_BUY): 1,
    ("flipped", U.SIDE_SELL): -1,
    ("band_up", U.SIDE_SELL): -1,
    ("band_down", U.SIDE_BUY): 1,
    ("none", U.SIDE_INFO): 0,
}


def _urgency_dir(urg, state):
    """到轨那两档的 INFO 要按趋势细分 —— 它的文案是带倾向的。

    「到上沿 + 多头 = 别拿到轨当卖出理由」实质上是**偏多**(叫你别减);
    「到下沿 + 空头 = 别拿到下沿当抄底理由」实质上是**偏空**(叫你别买)。
    徽标上不写买卖两个字, 但用户读到的就是一个方向, 所以这里照方向算。
    """
    key = (urg["kind"], urg["side"])
    if key in _URGENCY_DIR:
        return _URGENCY_DIR[key]
    assert key in (("band_up", U.SIDE_INFO), ("band_down", U.SIDE_INFO)), \
        f"没见过的判定档 {key} —— 新增判定必须在这张方向表里表态"
    if state is None:
        return 0
    bull = state in ("UT", "NR", "SR")
    # 大级别也到轨 / 通道结构与趋势相反时, _band_call 会退回真中性,
    # 那几句文案不含倾向 —— 靠 action 里的关键词区分。
    act = urg["action"]
    if urg["kind"] == "band_up":
        return 1 if (bull and "不必因为" in act) else 0
    return -1 if (not bull and "别拿" in act) else 0


def _cases():
    for s, m, l in itertools.product(POSES, repeat=3):
        bands = _bands(s, m, l)
        vd = K.verdict(bands)
        for state, held, sig in itertools.product(STATES, (False, True), SIGNALS):
            trend = _trend(state)
            urg = U.assess(position={"held": held}, trend=trend,
                           exit_line={"triggered": False}, bands=bands)
            play = pb.playbook(position={"held": held}, trend=trend,
                               exit_line={"triggered": False}, urgency=urg,
                               verdict=vd, phase=None, event=None)
            yield (s, m, l), state, held, sig, vd, urg, play


# ---------- 性质 A: 一格里不许同时叫买又叫卖 ----------

def test_全组合枚举里没有未标记的买卖矛盾():
    bad = []
    n = 0
    for combo, state, held, sig, vd, urg, play in _cases():
        n += 1
        if not vd:
            continue
        v_dir = _VERDICT_DIR[vd["tone"]]
        u_dir = _urgency_dir(urg, state)
        if not v_dir or not u_dir or v_dir == u_dir:
            continue
        # 打架是允许的 —— 但必须**说出来**: 要么这一格已经判成「先别动」,
        # 要么纪律层(「按纪律走」)盖过了一切。
        if play["level"] in (pb.CONFLICT, pb.EXIT):
            continue
        bad.append((combo, state, held, sig, vd["code"], vd["tone"],
                    urg["kind"], urg["side"], play["level"], play["headline"]))
    assert n == 5 * 5 * 5 * 7 * 2 * len(SIGNALS), f"枚举规模不对: {n}"
    assert not bad, (
        f"{len(bad)}/{n} 例「贵不贵」与「怎么办」方向相反却没判成打架, "
        f"前 3 例: {bad[:3]}")


def test_方向相反时一定进先别动档():
    """反过来验一次: 构造一个明确相反的组合, 必须命中 CONFLICT。

    三档全在下沿(下跌途中·别碰) + 六态还挂着上涨趋势 —— 这正是穷举跑出来的
    那一类, R214 之前它显示的是「到下沿·买」。
    """
    bands = _bands(K.POS_NEAR_LOWER, K.POS_NEAR_LOWER, K.POS_NEAR_LOWER)
    vd = K.verdict(bands)
    assert vd["code"] == "falling_all_bands" and vd["tone"] == "avoid"
    trend = _trend("UT")
    urg = U.assess(position={"held": False}, trend=trend,
                   exit_line={"triggered": False}, bands=bands)
    # ① urgency 自己先不许再叫买
    assert urg["side"] == U.SIDE_INFO, urg
    assert "别拿它当低吸理由" in urg["action"]
    # ② 收敛层要把这件事说出来
    play = pb.playbook(position={"held": False}, trend=trend,
                       exit_line={"triggered": False}, urgency=urg,
                       verdict=vd, phase=None, event=None)
    assert play["level"] == pb.CONFLICT
    assert "通道结构比六态先转向" in play["conflicts"][0]


def test_只有短期到下沿时仍然给买方向():
    """别把 R214 的收紧做过头 —— 常规回调该给的买点线索还得给。"""
    bands = _bands(K.POS_NEAR_LOWER, K.POS_INSIDE, K.POS_INSIDE)
    assert K.verdict(bands)["code"] == "low_short_only"
    urg = U.assess(position={"held": False}, trend=_trend("UT"),
                   exit_line={"triggered": False}, bands=bands)
    assert urg["side"] == U.SIDE_BUY
    assert "甩人下车" in urg["action"]


def test_只有短期到上沿的强势票不报打架():
    """趋势票沿着上轨走是常态 —— 这一类天天发生, 报打架就等于把这一档变噪音。"""
    bands = _bands(K.POS_ABOVE, K.POS_INSIDE, K.POS_INSIDE)
    vd = K.verdict(bands)
    assert vd["code"] == "high_short_only" and vd["tone"] == "hold"
    play = pb.playbook(position={"held": True}, trend=_trend("UT"),
                       exit_line={"triggered": False},
                       urgency=U.assess(position={"held": True}, trend=_trend("UT"),
                                        exit_line={"triggered": False}, bands=bands),
                       verdict=vd, phase=None, event=None)
    assert play["level"] != pb.CONFLICT
    assert play["conflicts"] == []


# ---------- 性质 B: 每条打架规则都得真的触发过 ----------

# [R435] ① 趋势 vs AI、③ 阶段 vs AI 两条随 AI 信号撤了
_RULE_MARKERS = {
    "②趋势 vs 通道位置": "位置上",
    "④持有+走过头+趋势没坏": "加仓与减仓的理由同时成立",
}


def test_每条打架规则都至少触发过一次():
    """一条永远不触发的规则, 和没写是一回事 —— 而且看起来还像写了。

    这正是 ① 号 bug 藏了整整一轮的原因: 规则在那儿、注释在那儿、测试也在那儿
    (测的是别的规则), 就是从来没跑过。R210 的路 C 也是同一种病。
    """
    fired = {k: 0 for k in _RULE_MARKERS}
    phases = ("overextended", "stalling", "declining", None)
    for s, m, l in itertools.product(POSES, repeat=3):
        vd = K.verdict(_bands(s, m, l))
        for state, sig, ph, held in itertools.product(STATES, SIGNALS, phases, (False, True)):
            cf = pb._conflicts(held=held, trend=_trend(state), verdict=vd,
                               phase={"code": ph, "cn": ph} if ph else None)
            for name, marker in _RULE_MARKERS.items():
                if any(marker in x for x in cf):
                    fired[name] += 1
    never = [k for k, v in fired.items() if v == 0]
    assert not never, f"这些打架规则一次都没触发过(等于没写): {never};命中统计 {fired}"


def test_规则二读的是tone不是side():
    """把 ① 号 bug 钉死: verdict 的偏买偏卖在 `tone`, `side` 是上轨还是下轨。"""
    sides = {(K.verdict(_bands(*c)) or {}).get("side")
             for c in itertools.product(POSES, repeat=3)} - {None}
    assert sides == {K.SIDE_HIGH, K.SIDE_LOW}, sides
    assert not (sides & {"buy", "sell"}), \
        "verdict['side'] 里没有 buy/sell —— 拿它比 'sell' 的条件恒假"
    # 趋势往上 + 位置说该止盈 → 必须报打架
    vd = K.verdict(_bands(K.POS_ABOVE, K.POS_ABOVE, K.POS_INSIDE))
    assert vd["code"] == "top_confirmed" and vd["tone"] == "sell"
    cf = pb._conflicts(held=False, trend=_trend("UT"), verdict=vd,
                       phase=None)
    assert any("贵了" in x for x in cf), cf
    # 趋势往下 + 位置说便宜 → 也必须报
    vd2 = K.verdict(_bands(K.POS_NEAR_LOWER, K.POS_NEAR_LOWER, K.POS_INSIDE))
    assert vd2["tone"] == "buy"
    cf2 = pb._conflicts(held=False, trend=_trend("DT"), verdict=vd2,
                        phase=None)
    assert any("便宜不等于该买" in x for x in cf2), cf2


def test_avoid语气也算偏卖且说的是自己的话():
    """原来的写法连 `avoid`(下跌途中·别碰) 都漏了 —— 它比 sell 还硬。

    但它**不能和 sell 共用一句话**: 「下跌途中」不是"贵", 是通道整体在往下走。
    共用会说出「位置上已经是『下跌途中』—— 贵了」这种不通的句子。
    """
    vd = K.verdict(_bands(K.POS_BELOW, K.POS_BELOW, K.POS_BELOW))
    assert vd["tone"] == "avoid"
    cf = pb._conflicts(held=False, trend=_trend("NR"), verdict=vd,
                       phase=None)
    assert any("通道结构比六态先转向" in x for x in cf), cf
    assert not any("贵了" in x for x in cf), cf


# ---------- 不表态的语气照旧不算打架 ----------

@pytest.mark.parametrize("tone", ["hold", "watch"])
def test_不表态的语气不算打架(tone):
    vd = {"tone": tone, "title": "随便", "side": K.SIDE_HIGH}
    for state in STATE_CN:
        assert not [x for x in pb._conflicts(held=False, trend=_trend(state),
                                             verdict=vd, phase=None)
                    if "位置上" in x]
