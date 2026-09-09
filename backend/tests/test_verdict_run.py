"""[R233] 通道结论「已经连着挂了几天」。

用户: 「『候选、调到位了』也是要显示这个状态持续多少天了」。

六态徽标一直带着「上涨趋势 15 天」, 而它旁边的通道结论只有一个 4 字标签,
于是「调到位了」看不出是**今天刚到位**还是**已经这样磨了三周** —— 这两件事
要做的动作完全不同: 第一天是"刚出现的机会", 第 20 天更像"它就是不涨"。

这一组盯三件事:

  ① 天数是**真的数出来的**, 不是拍的;
  ② **中间断一天就重新起算** —— 说成累计出现天数会把这一档持续了多久说多;
  ③ 判定一个字都没自己写 —— 仍然走作者的 `assess` / `verdict`。
"""
from __future__ import annotations

from app.indicators import keltner as k
from app.indicators import keltner_geometry as kg

_ATR = 0.25
_WARMUP = 200          # 够长期档(120)暖机


def _code_of(closes: list[float]) -> str | None:
    """按 verdict_run 同一套口径, 算最后一天的结论码 —— 用来造夹具时对答案。"""
    got = kg.verdict_run(closes, [_ATR] * len(closes))
    return got["code"] if got else None


def _flat_then(tail: list[float], base: float = 10.0) -> list[float]:
    """一段横盘暖机, 再接上给定的尾巴。"""
    return [base] * _WARMUP + tail


def test_刚出现的结论是第一天():
    """单日出现就该是 1, 不是 0 —— 「连着第 0 天」不是人话。"""
    closes = _flat_then([9.4])
    got = kg.verdict_run(closes, [_ATR] * len(closes))
    assert got is not None, "造的夹具没有触发任何结论, 测试前提就错了"
    assert got["days"] == 1


def test_连着几天同一档就数几天():
    closes = _flat_then([9.4, 9.4, 9.4, 9.4])
    got = kg.verdict_run(closes, [_ATR] * len(closes))
    assert got is not None
    assert got["days"] == 4, f"数出来是 {got['days']} 天"


def test_中间断一天就重新起算():
    """**这条是整个口径的关键。**

    「调到位了」出现 3 天、隔一天回到通道中部、再出现 2 天 —— 那是**两次独立
    的出现**。报 5 天会让人以为它已经在这个位置磨了一周, 而实际上刚回来两天。
    与 `_tail_run` 同一条纪律。
    """
    interrupted = _flat_then([9.4, 9.4, 9.4, 10.0, 9.4, 9.4])
    got = kg.verdict_run(interrupted, [_ATR] * len(interrupted))
    assert got is not None
    assert got["days"] == 2, f"断档之后该从 2 起算, 却数成了 {got['days']} 天"


def test_三档都在中部时不给天数而不是给零():
    """底层在这一格返回 None(位置上真的没有可说的)。给 0 会让界面印出
    「— 0天」, 那是个看着像真的假数。"""
    closes = [10.0] * (_WARMUP + 5)
    assert _code_of(closes) is None
    assert kg.verdict_run(closes, [_ATR] * len(closes)) is None


def test_换了一档结论天数跟着从头起算():
    """从偏买那头一路走到偏卖那头, 天数不能接着上一档继续加。"""
    low = _flat_then([9.4, 9.4, 9.4])
    assert _code_of(low) is not None
    high = low + [10.6, 10.6]
    got = kg.verdict_run(high, [_ATR] * len(high))
    assert got is not None
    assert got["code"] != _code_of(low), "造的夹具没换档, 这条测不到"
    assert got["days"] == 2


def test_判定仍然走作者那两个函数():
    """[守则] `indicators/keltner.py` 是作者的, 一个字节都不许改。这一层只
    负责**数天数**, 判定必须原样借用 —— 所以 verdict_run 报的 code 一定能在
    作者的 `verdict()` 上复现。"""
    closes = _flat_then([9.4, 9.4])
    got = kg.verdict_run(closes, [_ATR] * len(closes))
    assert got is not None

    # 按作者的路子重算最后一天
    n = len(closes)
    bands = {}
    for key in ("s", "m", "l"):
        w = kg.WINDOW[key]
        ma = sum(closes[n - w:]) / w
        bands[key] = k.assess(close=closes[-1], ma=ma, atr=_ATR, n=kg.K[key])
    assert got["code"] == k.verdict(bands)["code"]


def test_数据不齐时安静返回空而不是崩():
    assert kg.verdict_run(None, None) is None
    assert kg.verdict_run([], []) is None
    assert kg.verdict_run([10.0] * 5, [_ATR] * 4) is None       # 长度对不上
    assert kg.verdict_run([10.0] * 300, [0.0] * 300) is None    # ATR 全是 0


def test_暖机不够时不硬凑一个结论():
    """长期档要 120 根。不足就整档缺席 —— 拿 60 根算出来的"120 日均线"是假数,
    据此给出的结论和天数一样是假的。"""
    short = [10.0] * 50 + [9.4]
    assert kg.verdict_run(short, [_ATR] * len(short)) is None


def test_天数挂在结论对象上而不是另起一个平级字段():
    """[R233] 接线: 决策台/今日总览的 `verdict` 里要能直接读到 `days`。
    分成两个平级字段的话, 界面各处取一个忘一个 —— 这个仓库栽过好几次。"""
    import inspect

    from app.services import keltner_service
    src = inspect.getsource(keltner_service)
    assert "verdict_run" in src, "批量里没算天数"
    assert 'dict(v, days=' in src, "天数没有并进 verdict 对象"
    assert 'vr.get("code") == v.get("code")' in src, (
        "没核对码一致 —— 历史窗口与当日快照万一算出不同的结论码, "
        "会把别人的天数安在这一档上"
    )
