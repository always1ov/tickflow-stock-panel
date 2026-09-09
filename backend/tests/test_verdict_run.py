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


def test_候选池这一档同样有天数():
    """用户: 「进入候选多少天也有的吧?」—— 有。

    「候选池」(`watch_low`)是 10 条结论里的一条, `verdict_run` **没有任何
    码的白名单**, 所以它和「调到位了」走的是同一条路。这条测试把它钉死:
    这一档恰恰是最需要天数的 —— 它的含义就是"大级别位置到了、等一个入场点",
    等了 3 天和等了 30 天完全是两回事。

    造法: 短期在通道中部、中期已经到下沿。要让 MA20 追上价格而 MA60 还在
    高位, 需要一段**持续但不陡**的下行 —— 斜率太小中期到不了下沿, 太大
    短期自己也掉出通道就变成别的档了。
    """
    closes = [10.0] * _WARMUP + [10.0 - 0.025 * i for i in range(1, 45)]
    got = kg.verdict_run(closes, [_ATR] * len(closes))
    assert got is not None
    assert got["code"] == "watch_low", f"夹具造出来的是 {got['code']}, 这条测不到候选池"
    assert got["days"] > 1, "候选池连着挂了很多天, 却只报了 1 天"


def test_十条结论没有一条被排除在天数之外():
    """[R233] 防的是"只给某几档算天数"这种半吊子实现 —— 那样用户会发现
    有的徽标带天数有的不带, 而且看不出规律。

    盯的是实现本身: `verdict_run` 里不该出现任何按 code 分支的逻辑。
    """
    import inspect

    src = inspect.getsource(kg.verdict_run)
    from app.indicators.keltner import _VERDICTS
    for code in _VERDICTS:
        assert code not in src, (
            f"verdict_run 里出现了 `{code}` —— 它不该认识任何具体的结论码, "
            f"只该数「今天这个码往回连着几天」"
        )


def test_两条路对不上时今天仍然算一天而不是整个不给():
    """[R234] 用户: 「个股页面的外面并没有显示, 只是点击的里面」。

    `channels_for_symbols` 的三档是拿 enriched 快照里**预计算的** ma20/ma60
    拼的, 而 `verdict_run` 自己滚均线 —— 最后一根本来就可能差一点(停牌行被
    drop_nulls 掉、批量末根与快照末根不是同一天)。

    原来那道「对不上就不给天数」的校验把这种**常见情况**当成了异常, 天数
    静默消失, 界面上没有任何线索。这条盯的是修好之后的行为: 对不上时今天
    仍然算数(徽标上印的就是那个 code), 保底 1 天。
    """
    import inspect

    from app.services import keltner_service
    src = inspect.getsource(keltner_service.channels_for_symbols)
    assert 'days=int(vr["days"]) if same else 1' in src, (
        '两条路对不上时又变回「整个不给」了 —— 那会让天数从徽标上静默消失'
    )
    # 反向: 不该再出现"对不上就跳过"的写法
    assert 'if vr and vr.get("code") == v.get("code")' not in src, (
        "静默失败的那道校验回来了"
    )


# ---------------------------------------------------------------- 整条链

def test_端到端_天数真的出现在接口返回的_verdict_里():
    """[R234] 用户: 「外面还是没显示持续天数时常」。

    前面那些测试**全绿, 链路却是断的** —— R234 那个坑就是这么漏过去的:
    `verdict_run` 自己测得好好的, 而 `channels_for_symbols` 把它的结果丢掉了。
    单元测试盯不到"两个模块之间", 所以这里补一条走完整条链的。

    造一只票喂进 `channels_for_symbols`, 断言**接口真的返回了 days**。
    两个数据源刻意用同一份收盘价算(快照的 ma20/ma60 与历史那条路一致),
    这是最常见的情形; 对不上的情形由上面那条 R234 的测试守。
    """
    import datetime as dt

    import polars as pl

    from app.services import keltner_service as ks

    # 长期横盘后持续缓跌 —— 短期在通道中部而中期到下沿, 落在「候选池」
    closes = [10.0] * 200 + [10.0 - 0.025 * i for i in range(1, 101)]
    dates = [dt.date(2025, 1, 1) + dt.timedelta(days=i) for i in range(len(closes))]
    last = len(closes) - 1

    def _ma(w: int) -> float:
        return sum(closes[last + 1 - w:last + 1]) / w

    class _FakeRepo:
        def get_enriched_latest(self):
            return pl.DataFrame({
                "symbol": ["000001.SZ"], "close": [closes[-1]], "atr_14": [_ATR],
                "ma20": [_ma(20)], "ma60": [_ma(60)],
            }), "2025-10-27"

        def get_daily_batch(self, symbols, start, end, cols):
            return pl.DataFrame({
                "symbol": ["000001.SZ"] * len(closes), "date": dates,
                "close": closes, "atr_14": [_ATR] * len(closes),
            })

    out = ks.channels_for_symbols(_FakeRepo(), ["000001.SZ"])
    v = (out.get("000001.SZ") or {}).get("verdict")
    assert v, "整条链没算出结论, 这条测不到天数"
    assert "days" in v, (
        f"接口返回的 verdict 里没有 days —— 徽标上就不会有天数。"
        f"拿到的是 {sorted(v)}"
    )
    assert v["days"] > 1, f"这只票连着挂了很多天「{v['title']}」, 却只报了 {v['days']} 天"
