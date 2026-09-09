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


def _vr(closes, atrs=None, dates=None, ma20=None, ma60=None, limit=None):
    """[R239] 老的 `verdict_run` 拆成了 `verdict_codes` + `count_trailing`
    (理由见那两个函数的说明: 数的那一步必须归"知道徽标印的是哪一档"的调用方)。

    这个适配器保留原来那个返回形状, 好让下面那些**行为断言**一字不改地继续
    守着 —— 它们守的是口径(中断即重算、含今天、起始日、上限), 与拆不拆无关。

    [R242] 序列里现在**不只有结论码**, 没结论的那些天带的是组合键
    (`combo:…`)。这个适配器守的是**结论**那条路, 与线上一致: 服务层只在
    `verdict` 非空时才去数 `v["days"]`。所以组合键在这里等同于"没有结论"。
    组合键那条路由 `test_没有结论的那一格…` 那几条单独守。
    """
    n = len(closes)
    kw = {} if limit is None else {"limit": limit}
    codes = kg.verdict_codes(closes, atrs or [_ATR] * n, ma20=ma20, ma60=ma60, **kw)
    if not codes or not codes[0] or str(codes[0]).startswith("combo:"):
        return None
    today = codes[0]
    days = kg.count_trailing(codes, today)
    out = {"code": today, "days": days}
    if dates is not None and len(dates) == n:
        out["since"] = str(dates[::-1][days - 1])
    if days >= len(codes):
        out["capped"] = True
    return out



def _code_of(closes: list[float]) -> str | None:
    """按 verdict_run 同一套口径, 算最后一天的结论码 —— 用来造夹具时对答案。"""
    got = _vr(closes, [_ATR] * len(closes))
    return got["code"] if got else None


def _flat_then(tail: list[float], base: float = 10.0) -> list[float]:
    """一段横盘暖机, 再接上给定的尾巴。"""
    return [base] * _WARMUP + tail


def test_刚出现的结论是第一天():
    """单日出现就该是 1, 不是 0 —— 「连着第 0 天」不是人话。"""
    closes = _flat_then([9.4])
    got = _vr(closes, [_ATR] * len(closes))
    assert got is not None, "造的夹具没有触发任何结论, 测试前提就错了"
    assert got["days"] == 1


def test_连着几天同一档就数几天():
    closes = _flat_then([9.4, 9.4, 9.4, 9.4])
    got = _vr(closes, [_ATR] * len(closes))
    assert got is not None
    assert got["days"] == 4, f"数出来是 {got['days']} 天"


def test_中间断一天就重新起算():
    """**这条是整个口径的关键。**

    「调到位了」出现 3 天、隔一天回到通道中部、再出现 2 天 —— 那是**两次独立
    的出现**。报 5 天会让人以为它已经在这个位置磨了一周, 而实际上刚回来两天。
    与 `_tail_run` 同一条纪律。
    """
    interrupted = _flat_then([9.4, 9.4, 9.4, 10.0, 9.4, 9.4])
    got = _vr(interrupted, [_ATR] * len(interrupted))
    assert got is not None
    assert got["days"] == 2, f"断档之后该从 2 起算, 却数成了 {got['days']} 天"


def test_三档都在中部时不给天数而不是给零():
    """底层在这一格返回 None(位置上真的没有可说的)。给 0 会让界面印出
    「— 0天」, 那是个看着像真的假数。"""
    closes = [10.0] * (_WARMUP + 5)
    assert _code_of(closes) is None
    assert _vr(closes, [_ATR] * len(closes)) is None


def test_换了一档结论天数跟着从头起算():
    """从偏买那头一路走到偏卖那头, 天数不能接着上一档继续加。"""
    low = _flat_then([9.4, 9.4, 9.4])
    assert _code_of(low) is not None
    high = low + [10.6, 10.6]
    got = _vr(high, [_ATR] * len(high))
    assert got is not None
    assert got["code"] != _code_of(low), "造的夹具没换档, 这条测不到"
    assert got["days"] == 2


def test_判定仍然走作者那两个函数():
    """[守则] `indicators/keltner.py` 是作者的, 一个字节都不许改。这一层只
    负责**数天数**, 判定必须原样借用 —— 所以 verdict_run 报的 code 一定能在
    作者的 `verdict()` 上复现。"""
    closes = _flat_then([9.4, 9.4])
    got = _vr(closes, [_ATR] * len(closes))
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
    assert _vr([10.0] * 5, [_ATR] * 5) is None       # 太短, 长期档出不来
    assert _vr([10.0] * 5, [_ATR] * 4) is None       # 长度对不上
    assert _vr([10.0] * 300, [0.0] * 300) is None    # ATR 全是 0
    assert kg.verdict_codes(None, None) == []
    assert kg.verdict_codes([], []) == []


def test_暖机不够时不硬凑一个结论():
    """长期档要 120 根。不足就整档缺席 —— 拿 60 根算出来的"120 日均线"是假数,
    据此给出的结论和天数一样是假的。"""
    short = [10.0] * 50 + [9.4]
    assert _vr(short, [_ATR] * len(short)) is None


def test_天数挂在结论对象上而不是另起一个平级字段():
    """[R233] 接线: 决策台/今日总览的 `verdict` 里要能直接读到 `days`。
    分成两个平级字段的话, 界面各处取一个忘一个 —— 这个仓库栽过好几次。"""
    import inspect

    from app.services import keltner_service
    src = inspect.getsource(keltner_service)
    assert "verdict_codes" in src, "批量里没取逐日结论序列"
    assert 'dict(v, days=hist' in src, "天数没有并进 verdict 对象"
    assert "count_trailing(codes, v.get(\"code\"))" in src, (
        "没有拿徽标那一档往回数 —— 那会退回「两条路必须先对上今天」的老坑"
    )
    assert "days_exact" in src, "没标出天数是数出来的还是只能确认到今天"


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
    got = _vr(closes, [_ATR] * len(closes))
    assert got is not None
    assert got["code"] == "watch_low", f"夹具造出来的是 {got['code']}, 这条测不到候选池"
    assert got["days"] > 1, "候选池连着挂了很多天, 却只报了 1 天"


def test_十条结论没有一条被排除在天数之外():
    """[R233] 防的是"只给某几档算天数"这种半吊子实现 —— 那样用户会发现
    有的徽标带天数有的不带, 而且看不出规律。

    盯的是实现本身: `verdict_run` 里不该出现任何按 code 分支的逻辑。
    """
    import inspect

    src = inspect.getsource(kg.verdict_codes) + inspect.getsource(kg.count_trailing)
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
    assert "days=1, days_exact=False" in src, (
        '历史对不上时又变回「整个不给」了 —— 那会让天数从徽标上静默消失'
    )
    # 反向: 不该再出现"两条路必须先对上今天"的前提
    assert 'vr.get("code") == v.get("code")' not in src, (
        "那个必须成立却经常不成立的前提回来了 —— 它会让每一行都变成「已1天?」"
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


def test_R236_只要有结论天数就一定在():
    """用户连着三次报「外面还是没显示」。

    根子上的问题是: 「功能没部署」和「这只票算不出来」在界面上**长得一模
    一样** —— 都是徽标后面什么都没有。而这两种要做的事完全不同。

    所以现在只要有结论, `days` 就一定在: 今天这一档是确定的(徽标上印的
    就是它), 至少 1 天。算不出历史时用 `days_exact=False` 标开, 界面画淡
    并说明"只能确认到今天" —— **不假装自己知道, 但也不消失。**
    """
    import datetime as dt

    import polars as pl

    from app.services import keltner_service as ks

    closes = [10.0] * 200 + [10.0 - 0.025 * i for i in range(1, 101)]
    dates = [dt.date(2025, 1, 1) + dt.timedelta(days=i) for i in range(len(closes))]
    last = len(closes) - 1

    def _ma(w: int) -> float:
        return sum(closes[last + 1 - w:last + 1]) / w

    class _Repo:
        def __init__(self, bars: int) -> None:
            self.bars = bars

        def get_enriched_latest(self):
            return pl.DataFrame({
                "symbol": ["X"], "close": [closes[-1]], "atr_14": [_ATR],
                "ma20": [_ma(20)], "ma60": [_ma(60)],
            }), "d"

        def get_daily_batch(self, *a, **k):
            n = self.bars
            return pl.DataFrame({
                "symbol": ["X"] * n, "date": dates[-n:],
                "close": closes[-n:], "atr_14": [_ATR] * n,
            })

    # 历史够长 → 数得出来
    v = (ks.channels_for_symbols(_Repo(len(closes)), ["X"]).get("X") or {})["verdict"]
    assert v["days"] > 1 and v["days_exact"] is True

    # 暖机不足 120 根 → 仍然给天数, 但标明不精确
    v = (ks.channels_for_symbols(_Repo(60), ["X"]).get("X") or {})["verdict"]
    assert v["days"] == 1, "算不出历史时该退化成「至少 1 天」而不是消失"
    assert v["days_exact"] is False, "不精确却没标出来 —— 那是在假装自己知道"


# ---------------------------------------------------------------- [R237] 起始日

def test_起始日指向这一段的第一个交易日():
    """用户: 「记录进入该状态的起始日期」。

    **天数每天变, 起始日不会变** —— 后者才是能拿去核对的那个数(回 K 线上看
    那天到底发生了什么)。所以两个都要给, 不能只给天数。
    """
    import datetime as dt

    closes = _flat_then([9.4, 9.4, 9.4, 9.4])
    dates = [dt.date(2026, 1, 1) + dt.timedelta(days=i) for i in range(len(closes))]
    got = _vr(closes, [_ATR] * len(closes), dates)
    assert got is not None and got["days"] == 4
    # 4 天的段, 起点就是倒数第 4 根
    assert got["since"] == str(dates[-4])


def test_断档之后起始日跟着重新起算():
    """口径的两半必须一致: 天数从 2 起算, 起始日就不能还指着断档之前那天。"""
    import datetime as dt

    closes = _flat_then([9.4, 9.4, 9.4, 10.0, 9.4, 9.4])
    dates = [dt.date(2026, 1, 1) + dt.timedelta(days=i) for i in range(len(closes))]
    got = _vr(closes, [_ATR] * len(closes), dates)
    assert got is not None and got["days"] == 2
    assert got["since"] == str(dates[-2]), (
        f"天数说 2 天而起始日指着 {got['since']} —— 两个数自相矛盾"
    )


def test_不传日期时只给天数不编一个起始日():
    closes = _flat_then([9.4, 9.4])
    got = _vr(closes, [_ATR] * len(closes))
    assert got is not None and got["days"] == 2
    assert "since" not in got, "没给日期却凭空造了一个起始日"


def test_数满回看上限时标明这是下界():
    """`MAX_LOOKBACK` 天封顶。不标的话「250天」会被读成"正好 250 天"。"""
    # 造法要紧: **线性**缓跌才行。等比下跌时价格越低日跌幅越小, 均线滞后跟着
    # 变小, 走着走着价格就回到三档正中、反而没结论了(第一版夹具就栽在这)。
    closes = [10.0] * 150 + [10.0 - 0.02 * i for i in range(1, 301)]
    got = _vr(closes, [_ATR] * len(closes))
    assert got is not None
    assert got["days"] == 250 == kg.VERDICT_TAIL
    assert got.get("capped") is True, "数到上限了却没标出来这是下界"


def test_没数满时不该乱标下界():
    closes = _flat_then([9.4, 9.4, 9.4])
    got = _vr(closes, [_ATR] * len(closes))
    assert got is not None and got["days"] == 3
    assert "capped" not in got


def test_接口把起始日一起返回():
    """[R237] 端到端: `channels_for_symbols` 的 verdict 里要能直接读到 since。"""
    import datetime as dt

    import polars as pl

    from app.services import keltner_service as ks

    closes = [10.0] * 200 + [10.0 - 0.025 * i for i in range(1, 101)]
    dates = [dt.date(2026, 1, 1) + dt.timedelta(days=i) for i in range(len(closes))]
    last = len(closes) - 1

    def _ma(w: int) -> float:
        return sum(closes[last + 1 - w:last + 1]) / w

    class _Repo:
        def get_enriched_latest(self):
            return pl.DataFrame({
                "symbol": ["X"], "close": [closes[-1]], "atr_14": [_ATR],
                "ma20": [_ma(20)], "ma60": [_ma(60)],
            }), "d"

        def get_daily_batch(self, *a, **k):
            return pl.DataFrame({
                "symbol": ["X"] * len(closes), "date": dates,
                "close": closes, "atr_14": [_ATR] * len(closes),
            })

    v = (ks.channels_for_symbols(_Repo(), ["X"]).get("X") or {})["verdict"]
    assert v.get("since"), f"接口没返回起始日, 拿到的是 {sorted(v)}"
    # 起始日必须落在这一段里: 天数 N ⇒ since 是倒数第 N 个交易日
    assert v["since"] == str(dates[-v["days"]])


def test_徽标上必须写明是_已连着_而不是历史累计():
    """[R238] 用户: 「我不是要历史总数哦」。

    光写「候选池 75天」可以读成两种完全不同的意思:

        已经**连续**处于候选池 75 个交易日   ← 这里算的
        历史上**累计** 75 天是候选池         ← 用户担心的

    一个「已」字就是这句话的全部意思, 不是修饰。而且**必须在徽标上**说清楚
    —— 一列 80 行是用来扫的, 不能指望用户逐个悬停去确认口径(R193 的教训)。

    这条是文案守卫: 将来谁把「已」顺手删掉, 这里会红。
    """
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[2] / "frontend" / "src" / "components"
    for rel in ("stock-analysis/decision-board/cells.tsx", "today/VerdictTag.tsx"):
        p = root / rel
        if not p.exists():
            import pytest as _pytest
            _pytest.skip(f"拿不到 {p}(只跑后端时正常)")
        src = p.read_text(encoding="utf-8")
        assert "v.days" in src, f"{rel} 里找不到时长徽标 —— 改名了? 这条测试要同步更新"
        # **匹配 JSX 里那一段本身**, 不是"附近有没有这个字"。
        # 第一版写的是"往前 200 字里找「已」", 变异测试当场证明它是假的:
        # 把「已」从徽标上删掉, 它照样绿 —— 因为上面注释里就有「已经连着」。
        assert "days_exact === false ? '?'" not in src, (
            f"{rel} 的徽标又带上问号了 —— 用户: 「我要确定性的显示多少天」。"
            f"R239 之后数不出来只剩一种情形(今天刚变), 那时「已1天」就是正确答案。"
        )
        assert "已{v.days}天" in src, (
            f"{rel} 的时长徽标没写「已」—— 「候选池 75天」会被读成历史累计, "
            f"而它说的是「已经连着 75 天」。这两个是完全不同的数。"
        )


def test_短中档吃传进来的均线列而不是自己滚():
    """[R238] 用户: 「数字本身就不对」。

    根子是同一条 MA20 在系统里有过**两套算法**:

        复盘 `_bands_for_row`            预计算列 ma20/ma60 + 自己滚 ma120
        决策台徽标 `channels_for_symbols`  预计算列 ma20/ma60 + 自己滚 ma120
        verdict_run(改之前)              三条全自己滚        ← 只有它不同源

    于是这里数出来的**逐日结论**和用户在复盘里逐日看到的不是一套, 天数当然
    对不上 —— 而两边都印在界面上, 谁也说不清哪个是真的。

    这条用一组**故意与自己滚不一样**的均线来证明: 传了就必须听传进来的。
    """
    closes = _flat_then([9.4, 9.4, 9.4, 9.4])
    n = len(closes)
    atrs = [_ATR] * n

    rolled = _vr(closes, atrs)
    assert rolled is not None

    # 造一组"短中档一直贴在价格上"的均线 —— 价格永远在通道正中, 该判不出结论
    flat20 = list(closes)
    flat60 = list(closes)
    given = _vr(closes, atrs, ma20=flat20, ma60=flat60)
    assert given is None, (
        f"传了均线列却还在自己滚 —— 拿传进来的算该是「三档都在中部」(无结论), "
        f"自己滚会得到 {rolled['code']}"
    )


def test_均线列长度对不上时安静退回自己滚():
    """长度不对 = 这份列不可信, 退回自己滚而不是崩、也不是半用半不用。"""
    closes = _flat_then([9.4, 9.4])
    n = len(closes)
    got = _vr(closes, [_ATR] * n, ma20=[1.0, 2.0], ma60=None)
    assert got is not None and got["days"] == 2


def test_批量里真的把两列均线要出来了():
    """[R238] 接线: 不多要这两列, 上面那条性质就是空的。"""
    import inspect

    from app.services import keltner_service
    src = inspect.getsource(keltner_service.long_trend_map)
    assert '"ma20", "ma60"' in src, "日线批量没要预计算均线列"
    assert "ma20=sub[" in src, "要来了却没传给 verdict_run"


def test_R239_两条路对不上今天时也数得出天数():
    """用户截图: **每一行都是「已1天?」**。

    那不是数据问题, 是我埋的一个**必须成立、却经常不成立的前提** ——
    历史那条路自己判一个"今天", 与徽标那一档一比, 对不上就整个作废。
    而这两条路(enriched 快照 vs 日线批量)的今天本来就常常不一样:
    数据日期差一天、末根不同、复权口径不同……于是全表一起失效。

    现在没有这个前提了: 序列是逐日结论, 数的是"最近连着几天也是徽标这一档"。
    这条造三种对不上的情形, 断言天数照样数得出来。
    """
    import datetime as dt

    import polars as pl

    from app.services import keltner_service as ks

    closes = [10.0] * 200 + [10.0 - 0.025 * i for i in range(1, 101)]
    dates = [dt.date(2026, 1, 1) + dt.timedelta(days=i) for i in range(len(closes))]

    def _roll(w: int) -> list:
        return [None if i + 1 < w else sum(closes[i + 1 - w:i + 1]) / w
                for i in range(len(closes))]

    m20, m60 = _roll(20), _roll(60)
    last = len(closes) - 1

    class _Repo:
        def __init__(self, shift: float = 0.0, drop_last: int = 0) -> None:
            self.shift, self.drop = shift, drop_last

        def get_enriched_latest(self):
            return pl.DataFrame({
                "symbol": ["X"], "close": [closes[-1] + self.shift], "atr_14": [_ATR],
                "ma20": [m20[last]], "ma60": [m60[last]],
            }), "d"

        def get_daily_batch(self, *a, **k):
            n = len(closes) - self.drop
            return pl.DataFrame({
                "symbol": ["X"] * n, "date": dates[:n], "close": closes[:n],
                "atr_14": [_ATR] * n, "ma20": m20[:n], "ma60": m60[:n],
            })

    cases = {
        "两条路完全一致": _Repo(),
        "快照价与日线末根差一点": _Repo(shift=0.02),
        "日线比快照少一根(数据滞后一天)": _Repo(drop_last=1),
    }
    for tag, repo in cases.items():
        v = (ks.channels_for_symbols(repo, ["X"]).get("X") or {}).get("verdict")
        assert v, f"{tag}: 连结论都没有, 这条测不到"
        assert v["days_exact"] is True, (
            f"{tag}: 退化成「已1天?」了 —— 那正是用户全表看到的那个现象"
        )
        assert v["days"] > 1, f"{tag}: 天数是 {v['days']}"
        assert v.get("since"), f"{tag}: 没给起始日"


def test_R241_时长说法全界面统一():
    """用户: 「必须要统一表达, 不能又两种多种表述」。

    这条是我的问题 —— 同一件事当时有六种说法(`3天` / `已12天` /
    `第 11 天` / `已连着 N 个交易日` / `已经这样 N 天` / `连着 N 天`)。
    同一行里六态写「3天」、结论写「已12天」, 读的人得先判断这两个数是不是
    一回事。

    从此只有两个词, 各有一个意思且从不用于同一件事:

        已N天     到今天**还在**这个状态
        持续N天   历史上**那一段**总共多久(已结束)

    这条守着"不许再长出第三种"。
    """
    import pathlib
    import re

    root = pathlib.Path(__file__).resolve().parents[2] / "frontend" / "src" / "components"
    if not root.exists():
        import pytest as _pytest
        _pytest.skip("拿不到前端源码(只跑后端时正常)")

    banned = {
        "第 {": "「第 N 天」—— 换成「已N天」",
        "已连着 ": "「已连着 N 个交易日」—— 换成「已N天」",
        "已经这样 ": "「已经这样 N 天」—— 换成「已N天」",
    }
    files = [
        "stock-analysis/decision-board/cells.tsx",
        "stock-analysis/VerdictHover.tsx",
        "stock-analysis/StockReviewDialog.tsx",
        "today/VerdictTag.tsx",
    ]
    for rel in files:
        p = root / rel
        if not p.exists():
            continue
        # 只看**渲染出去的文本**, 注释里复述历史说法是允许的
        src = "\n".join(ln for ln in p.read_text(encoding="utf-8").splitlines()
                        if not ln.lstrip().startswith(("//", "*", "/*")))
        for bad, why in banned.items():
            assert bad not in src, f"{rel} 又出现了 {why}"

    # 正面: 两个词都还在
    cells = (root / "stock-analysis/decision-board/cells.tsx").read_text(encoding="utf-8")
    assert re.search(r"已\{trend\.duration\}天", cells), "六态徽标没用统一说法"
    assert "已{v.days}天" in cells, "结论徽标没用统一说法"
    review = (root / "stock-analysis/StockReviewDialog.tsx").read_text(encoding="utf-8")
    assert "持续{rows.length}天" in review, "历史段没用「持续N天」"


# ===== [R242] 没有结论的那一格 =====
#
# 用户: 「别搞什么下跌半年, 下跌多少天就表示多少天」。
#
# 结论列的徽标有两种。有结论时印结论标题(「候选池」), 三档都在通道中部时
# 底层判不出结论, 那一格印的是补充层组合注记的标题 —— 而那些标题里带着
# **模糊的时间词**(「半年低位」), 偏偏没有天数。
#
# 所以「状态」的定义扩一档: **徽标上印的是什么, 就数什么**。两种徽标都带
# 「已N天」, 这也才对得上 R241「必须统一表达」那条。


def test_R242_组合键与结论码不会撞():
    """组合键必须一眼能与结论码分开, 否则 `count_trailing` 会把两种状态数到
    一起 —— 「候选池」和「三档都在中部」连在一起报成一段。"""
    from app.indicators.keltner import _VERDICTS

    codes = {str(c) for c in _VERDICTS}
    assert codes, "拿不到作者那张结论表, 这条测不了"
    for c in codes:
        assert not c.startswith("combo:"), (
            f"结论码 {c!r} 撞上了组合键的前缀 —— 换一个前缀"
        )


def test_R242_有结论时状态键就是结论码():
    """扩定义**不许动有结论那一路**。同一份三档, `state_key` 给的必须与作者
    的 `verdict` 一字不差, 否则老徽标的天数会跟着变。"""
    from app.indicators.keltner import verdict as _verdict

    closes = _flat_then([10.0 - 0.025 * i for i in range(1, 101)])
    codes = kg.verdict_codes(closes, [_ATR] * len(closes))
    got = [c for c in codes if c and not c.startswith("combo:")]
    assert got, "这份夹具一天结论都没出, 测不到"
    # 反过来对一次: 有结论的那一天, state_key 必须原样返回那个 code
    bands = {"s": {"pos": "below"}, "m": {"pos": "below"}, "l": {"pos": "below"}}
    v = _verdict(bands)
    assert kg.state_key(bands) == (str(v["code"]) if v else "combo:below|below|below")


def test_R242_三档都在中部时给的是组合键而不是空():
    """这一格原来是 `None`(= 什么都数不了)。现在它是一个**有名字的状态**,
    才数得出「已N天」。"""
    flat = [10.0] * 400
    codes = kg.verdict_codes(flat, [_ATR] * len(flat))
    assert codes[0] is not None, "横盘票的今天成了空 —— 那就又没天数了"
    assert codes[0].startswith("combo:"), (
        f"横盘票该落在组合键上, 拿到的是 {codes[0]!r}"
    )
    assert kg.count_trailing(codes, codes[0]) > 1, "横盘这么久却只数出 1 天"


def test_R242_端到端_没有结论的票也拿得到_state_run():
    """[R235 的教训] 单元测试全绿而链路是断的 —— 走完整条
    `channels_for_symbols`, 断言接口真的返回了 `state_run`。"""
    import datetime as dt

    import polars as pl

    from app.services import keltner_service as ks

    # 一路横盘 —— 价格贴着三条均线, 三档全在通道中部, 底层判不出结论
    closes = [10.0] * 400
    dates = [dt.date(2025, 1, 1) + dt.timedelta(days=i) for i in range(len(closes))]

    class _FakeRepo:
        def get_enriched_latest(self):
            return pl.DataFrame({
                "symbol": ["000001.SZ"], "close": [closes[-1]], "atr_14": [_ATR],
                "ma20": [10.0], "ma60": [10.0],
            }), "2025-10-27"

        def get_daily_batch(self, symbols, start, end, cols):
            return pl.DataFrame({
                "symbol": ["000001.SZ"] * len(closes), "date": dates,
                "close": closes, "atr_14": [_ATR] * len(closes),
            })

    row = ks.channels_for_symbols(_FakeRepo(), ["000001.SZ"]).get("000001.SZ") or {}
    assert not row.get("verdict"), "这份夹具本该判不出结论, 前提就错了"
    run = row.get("state_run")
    assert run, (
        f"没结论的那一格没拿到 state_run —— 徽标上就还是没天数。拿到的是 {sorted(row)}"
    )
    assert run["days"] > 1, f"横盘这么久却报 {run['days']} 天"
    assert run.get("since"), "没给起始日, 悬停里就核对不了"


def test_R242_有结论时不另给一个平级的_state_run():
    """两个天数摆在同一行里, 读的人得先判断哪个是哪个。有结论时天数只有
    `verdict.days` 一份。"""
    import datetime as dt

    import polars as pl

    from app.services import keltner_service as ks

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

    row = ks.channels_for_symbols(_FakeRepo(), ["000001.SZ"]).get("000001.SZ") or {}
    assert row.get("verdict"), "这份夹具本该有结论, 前提就错了"
    assert "state_run" not in row, "有结论时又多给了一个平级天数, 同一行会出现两个数"


def test_R242_没有结论那一格的徽标也写_已N天():
    """两种徽标必须**同一个说法**(R241)。这条盯的是渲染出去的那段文本 ——
    没结论那一格如果自己长出「N天」「持续N天」, 统一表达就又破了。"""
    import pathlib

    p = (pathlib.Path(__file__).resolve().parents[2] / "frontend" / "src"
         / "components" / "stock-analysis" / "decision-board" / "cells.tsx")
    if not p.exists():
        import pytest as _pytest
        _pytest.skip("拿不到前端源码(只跑后端时正常)")
    src = "\n".join(ln for ln in p.read_text(encoding="utf-8").splitlines()
                    if not ln.lstrip().startswith(("//", "*", "/*")))
    assert "已{run.days}天{run.capped" in src, (
        "没结论那一格的徽标没有按统一说法写「已N天」"
    )
