"""[fork 增强] R287 「按转折买卖」的分段战绩。

用户: 「我想统计每两个转折之间的收益, 也就是说出现转折我第二天开盘就买或者卖,
这个根据转折后的状态判断」。

口径全在 `flip_trades.simulate` 的 docstring 里, 这里只钉行为。
"""
import pytest

from app.services.flip_trades import simulate, trend_days, verdict_days


def _steps(states: list[str]) -> list[dict]:
    """把状态序列铺成 `compute()` 那种 steps —— 只留这个函数用得着的字段。

    `flipped` 在这里**照 `compute()` 的定义现算**(`prev != state`), 而不是让
    每条测试自己手写一串真假 —— 手写的话测试就变成在描述我想要的翻转位置,
    而不是在描述状态序列。
    """
    out = []
    prev = None
    for i, st in enumerate(states):
        out.append({"i": i, "date": f"d{i:02d}", "state": st, "prev": prev,
                    "flipped": prev != st})
        prev = st
    # [R288] 过一道 `trend_days` —— 仓位(side)现在由适配器算, `simulate` 只读。
    # 这里不绕过它: 绕过就等于测的不是生产上跑的那条路。
    return trend_days(out)


# 一条**手工核算过**的最小路径。NR/NREA 分属多头侧与空头侧, 见 livermore.BULLISH。
#
#   i        0      1     2     3      4      5
#   状态    NREA    NR    NR   NREA   NREA    NR
#   转折           ← 转           ← 转             ← 转(次日已出界, 没得执行)
#   (i=0 的 `flipped` 是真的 —— `compute()` 给开机那天的 prev 是 None ——
#    但那不是转折, 见 `test_R287_开机那天不算转折`)
#   开盘    9.0    9.5  10.0   11.0   12.0   10.0
#   收盘                                      11.0
#
#   转折在 i=1(转入多头) → 次日 i=2 开盘 10.00 买入
#   转折在 i=3(转入空头) → 次日 i=4 开盘 12.00 卖出   → 多头段 +20%
#   转折在 i=5             次日出界, 这个信号还没轮到执行
#   空仓段 12.00 起, 没有下一次执行 → 未完, 按最后一天收盘 11.00 记 -8.33%
_STATES = ["NREA", "NR", "NR", "NREA", "NREA", "NR"]
_OPENS = [9.0, 9.5, 10.0, 11.0, 12.0, 10.0]
_CLOSES = [9.2, 9.8, 10.5, 11.2, 12.4, 11.0]


@pytest.fixture()
def sim():
    return simulate(_steps(_STATES), _OPENS, _CLOSES)


def test_R287_买卖发生在转折的次日开盘():
    """信号是收盘后才知道的 —— 所以最早的执行时机是次日开盘, 不是转折日收盘。

    这条是整件事的地基: 拿转折日**当天**的收盘价进场, 等于假设你在收盘那一刻
    就知道了收盘之后才算得出来的状态。
    """
    s = simulate(_steps(_STATES), _OPENS, _CLOSES)
    buy = s["legs"][0]
    assert buy["enter_date"] == "d02", "买入日不是转折(d01)的次日"
    assert buy["enter_price"] == pytest.approx(10.0), "买的不是次日的开盘价"
    assert buy["flip_date"] == "d01", "没记住是哪一天的转折触发的这一笔"


def test_R287_多头段收益是开盘到开盘(sim):
    buy = sim["legs"][0]
    assert buy["side"] == "多头"
    assert buy["exit_date"] == "d04"
    assert buy["exit_price"] == pytest.approx(12.0)
    assert buy["ret"] == pytest.approx(0.2), "10.00 → 12.00 应当是 +20%"
    assert buy["open_ended"] is False


def test_R287_空仓段照样算但那是躲开的不是赚到的(sim):
    """空头侧不做空(A 股散户也做不了) —— 那一段的涨跌是**你没参与的**。

    但它必须显示: 这套打法值不值, 一半的答案在"躲开了多少"里。
    """
    idle = sim["legs"][1]
    assert idle["side"] == "空头"
    assert idle["enter_price"] == pytest.approx(12.0), "空仓段该从卖出那个价接上"
    # 载荷里的收益一律 4 位小数 —— 界面只显示到 0.1%, 多的位数是假精度
    assert idle["ret"] == pytest.approx(-0.0833, abs=5e-5)


def test_R287_没轮到执行的转折不凭空造一笔(sim):
    """最后那次转折(d05)的次日已经出界。**信号有了、手还没动** ——
    不许拿当天收盘价冒充成交价补一笔进去。"""
    assert all(l["enter_date"] != "d05" for l in sim["legs"])
    assert sim["pending"] == "d05", "该说出来还有一个信号没轮到执行"


def test_R287_未完成的那段标出来且不进胜负统计(sim):
    """与 R177「按段计、只数已兑现」同一条纪律: 还没走完的段不许进胜率。"""
    last = sim["legs"][-1]
    assert last["open_ended"] is True
    assert sim["bull"]["scored"] == 1, "只有一段多头走完了"


def test_R287_跟着做与一直拿着必须同起点同终点(sim):
    """不同区间的两个收益率摆在一起比是没有意义的。

    起点 = 第一笔买入价(10.00), 终点 = 最后一段的结束价(11.00) → 一直拿着 +10%;
    跟着做只叠已完成的多头段 → +20%。
    """
    assert sim["hold"] == pytest.approx(11.0 / 10.0 - 1, rel=1e-6)
    assert sim["follow"] == pytest.approx(0.2)
    assert sim["excess"] == pytest.approx(sim["follow"] - sim["hold"], rel=1e-6)
    assert sim["from_date"] == "d02" and sim["to_date"] == "d05"


def test_R287_买卖次数就是多头段数(sim):
    """用户的交易哲学是「尽可能减少买卖次数」—— 这个数得摆在脸上。"""
    assert sim["trades"] == 1


def test_R287_空数据不炸():
    for bad in ([], _steps([]),):
        got = simulate(bad, [], [])
        assert got["legs"] == [] and got["follow"] is None


def test_R287_开机那天不算转折():
    """`compute()` 给第一天的 `flipped` 是 True(`prev` 是 None), 但那是**状态机
    开机**, 不是转折 —— 昨天没有状态, 谈不上"从什么转成什么"。

    照着它买一笔, 等于把"我们开始观察了"当成一个买入信号。第一条测试跑出来就是
    这个: 多出来的那一笔 d00→d01 让买卖次数变成 2、跟着做变成 +26.3%。
    """
    s = simulate(_steps(_STATES), _OPENS, _CLOSES)
    assert all(l["flip_date"] != "d00" for l in s["legs"]), "开机那天被当成转折了"
    assert s["legs"][0]["enter_date"] == "d02"


# ---------------------------------------------------------------- 执行摩擦
#
# 这一段是**诚实性**要求, 不是锦上添花。截图那只票 120 天里跌停 6 次, 而且好几个
# 跌停日**同时就是转折日** —— 次日开盘要是继续一字跌停, 那一笔根本卖不掉, 而
# 统计照样会拿那个开盘价给你算一个漂亮的"躲开了 10%"。不标出来就是在骗自己。

def test_R287_执行日撞涨停的买入要标出来():
    """转入多头 → 次日开盘买。那天要是涨停, 买单未必成交。"""
    lu = [False] * 6
    lu[2] = True                      # d02 正是第一笔的买入日
    s = simulate(_steps(_STATES), _OPENS, _CLOSES, limit_up=lu)
    assert s["legs"][0]["blocked"] is True, "撞涨停的买入日没标出来"
    assert s["blocked"] == 1


def test_R287_执行日撞跌停的卖出要标出来():
    """转入空头 → 次日开盘卖。那天要是跌停, 卖单未必成交。"""
    ld = [False] * 6
    ld[4] = True                      # d04 是转入空头那一笔的执行日
    s = simulate(_steps(_STATES), _OPENS, _CLOSES, limit_down=ld)
    assert s["legs"][1]["blocked"] is True, "撞跌停的卖出日没标出来"
    assert s["blocked"] == 1


def test_R287_方向要对上不能反着标():
    """买入日撞**跌停**是好事(买得更便宜, 而且跌停敢挂单就能成交), 不该报警;
    卖出日撞**涨停**同理。反着标会把利好读成风险。"""
    lu, ld = [False] * 6, [False] * 6
    ld[2] = True                      # 买入日跌停
    lu[4] = True                      # 卖出日涨停
    s = simulate(_steps(_STATES), _OPENS, _CLOSES, limit_up=lu, limit_down=ld)
    assert s["blocked"] == 0, "买入日跌停 / 卖出日涨停被当成成交不了了"


def test_R287_不给涨跌停就老老实实说不知道():
    s = simulate(_steps(_STATES), _OPENS, _CLOSES)
    assert s["blocked"] == 0
    assert all(l["blocked"] is False for l in s["legs"])


def test_R287_停牌没有开盘价就跳过并说出来():
    """缺开盘价的那次转折**不许**顺延到再下一天成交 —— 那是另一天的价。
    跳过, 并且把日子报出来, 不静默。"""
    opens = list(_OPENS)
    opens[2] = None                   # 第一笔的执行日停牌
    s = simulate(_steps(_STATES), opens, _CLOSES)
    assert s["skipped"] == ["d01"], "该报出是哪次转折没执行成"
    assert all(l["enter_date"] != "d02" for l in s["legs"])


# ---------------------------------------------------------------- 接真状态机
#
# 上面全是手搭的 steps。这一段换成 `compute()` 真跑一遍 —— 手搭的 steps 只能证明
# 算术对, 证明不了**字段名对得上**(`prev` / `flipped` / `date` 都是 compute 给的)。

from app.indicators.livermore import compute  # noqa: E402

# 精心构造: 先连创新高 → 跌破阈值转空 → 反弹转多 → 再跌。走遍多空两侧多次翻转。
_PATH = [10, 10.5, 11, 11.6, 12.2, 12.8, 12.0, 11.6, 11.4, 11.8,
         12.3, 12.6, 13.0, 13.4, 13.1, 12.9, 13.2, 13.6,
         12.7, 12.0, 11.5, 10.8, 10.2, 9.6, 10.3, 10.6, 10.0, 9.4]
# 开盘价 = 前一日收盘 × 1.005 —— 一个**固定**的小跳空, 不是随机数; 这样每一笔的
# 执行价与收盘价必然不同, 「用错了价」会立刻显形。
_PATH_OPENS = [_PATH[0]] + [round(c * 1.005, 4) for c in _PATH[:-1]]
_PATH_DATES = [f"2026-01-{i + 1:02d}" for i in range(len(_PATH))]


@pytest.fixture()
def real():
    steps = trend_days(compute(_PATH, _PATH_DATES, 0.06)["steps"])
    return steps, simulate(steps, _PATH_OPENS, _PATH)


def test_R287_接得上真状态机的字段(real):
    steps, s = real
    assert s["legs"], "接上 compute() 之后一笔都没有 —— 字段名多半对不上"
    by_date = {st["date"]: st for st in steps}
    for l in s["legs"]:
        st = by_date[l["flip_date"]]
        assert st["flipped"] and st["prev"] is not None, (
            f"{l['flip_date']} 不是一次真转折"
        )


def test_R287_段与段之间不许有缝(real):
    """下一段的买入价必须就是这一段的卖出价。

    有缝的话「跟着做」与「一直拿着」量的就不是同一段区间, 两个数摆在一起比
    就是错的 —— 而那个对比正是这一栏唯一的结论。
    """
    _steps_, s = real
    for a, b in zip(s["legs"], s["legs"][1:]):
        assert a["exit_date"] == b["enter_date"], f"{a['exit_date']} 与 {b['enter_date']} 之间有缝"
        assert a["exit_price"] == b["enter_price"]


def test_R287_用的是开盘价不是收盘价(real):
    """开盘价一律比前收高 0.5%, 所以任何一个执行价都不该等于当天收盘价。"""
    _steps_, s = real
    close_by_date = dict(zip(_PATH_DATES, _PATH))
    done = [l for l in s["legs"] if not l["open_ended"]]
    assert done, "场景没搭对: 没有已完成的段"
    for l in done:
        assert l["enter_price"] != close_by_date[l["enter_date"]], (
            f"{l['enter_date']} 用的是收盘价 —— 那是收盘之后才知道的信号拿收盘价成交"
        )


def test_R287_多空两侧都真的走到了(real):
    """否则上面几条都可能是被"全是多头段"喂饱的。"""
    _steps_, s = real
    assert s["bull"]["n"] >= 2 and s["bear"]["n"] >= 2, (
        f"这条路径只走出 多头{s['bull']['n']} 段 / 空头{s['bear']['n']} 段"
    )


def test_R287_一笔都做不成的时候要说得出为什么():
    """空栏必须自己解释。这个仓库反复吃的亏就是"静默地什么都不显示" ——
    读的人分不清是"这段时间确实没转折"还是"数据缺了算不出来"。"""
    flat = _steps(["NR"] * 6)                       # 全程一个状态, 没有转折
    assert simulate(flat, _OPENS, _CLOSES)["reason"] == "no_flip"

    blind = simulate(_steps(_STATES), [None] * 6, _CLOSES)
    assert blind["reason"] == "no_open", "缺开盘价被说成了没转折"

    assert simulate(_steps(_STATES), _OPENS, _CLOSES)["reason"] is None


# ---------------------------------------------------------------- 接进复盘载荷
#
# 上面证明了算术与状态机, 这一段证明**它真的接到了那一页上**, 而且接的是
# 同一份 steps —— 这个仓库最贵的一课就是"看着接上了、其实一直是假"(R274)。

from datetime import date, timedelta  # noqa: E402

import polars as pl  # noqa: E402

from app.services import review_service as rs  # noqa: E402


class _Repo:
    def __init__(self, df):
        self._df = df

    @staticmethod
    def resolve_asset_type(symbol):
        return "stock"

    def get_daily_asset(self, asset_type, symbol, start, end, columns=None):
        df = self._df
        return df.select([c for c in columns if c in df.columns]) if columns else df


def _review_frame(n=260):
    """一条走得动的路径 —— 正弦波推着六态来回翻, 保证窗口里有多次转折。
    开盘价固定比前收高 0.5%, 与上面同一个构造法。"""
    import math
    closes = [100.0 + 0.05 * i + 14.0 * math.sin(i / 11.0) for i in range(n)]
    opens = [closes[0]] + [round(c * 1.005, 4) for c in closes[:-1]]
    d0 = date(2025, 1, 1)
    return pl.DataFrame({
        "date": [d0 + timedelta(days=i) for i in range(n)],
        "open": opens, "close": closes,
    }).with_columns([
        pl.col("close").rolling_mean(20).alias("ma20"),
        pl.col("close").rolling_mean(60).alias("ma60"),
        pl.lit(3.0).alias("atr_14"),
        (pl.col("close") / pl.col("close").shift(1) - 1).alias("change_pct"),
        pl.Series("signal_limit_up", [False] * n),
        pl.Series("signal_limit_down", [False] * n),
        pl.Series("signal_broken_limit_up", [False] * n),
        pl.Series("consecutive_limit_ups", [0] * n),
    ])


@pytest.fixture()
def review():
    return rs.review_for_symbol(_Repo(_review_frame()), "600000.SH", 120)


def test_R287_复盘载荷带上了这一栏(review):
    ft = review["flip_trades"]
    assert ft["reason"] is None and ft["legs"], (
        f"接线没接上: reason={ft['reason']}, {len(ft['legs'])} 段"
    )


def test_R287_每一笔都对得上逐日表里那个转折标记(review):
    """**这是这一栏能不能信的全部**: 屏幕上标着「转折」的那些天, 与统计里那些
    买卖日, 必须是同一批日子。对不上就说明两处各跑了一次状态机。"""
    marked = {r["date"] for r in review["rows"] if (r.get("trend") or {}).get("flipped")}
    assert marked, "场景没搭对: 这 120 天里一次转折都没有"
    for l in review["flip_trades"]["legs"]:
        assert l["flip_date"] in marked, (
            f"{l['flip_date']} 在统计里是转折, 但逐日表没标 —— 两处不同源"
        )


def test_R287_统计只覆盖屏幕上那段窗口(review):
    """暖机段(为了算 MA120 多取的那 130 根)**不许**混进来 —— 混进来的话
    统计说的区间和用户看到的 120 行对不上, 而他没法发现。"""
    ft = review["flip_trades"]
    assert ft["from_date"] >= review["start"], (
        f"第一笔 {ft['from_date']} 落在窗口开始 {review['start']} 之前"
    )
    assert ft["to_date"] <= review["end"]


def test_R287_缺开盘价的票不装作算得出来():
    """老 df 没有 open 列(比如某些指数/ETF) —— 那就明说算不了, 不给空白。"""
    df = _review_frame().drop("open")
    ft = rs.review_for_symbol(_Repo(df), "600000.SH", 120)["flip_trades"]
    assert ft["legs"] == [] and ft["reason"] == "no_open"


def test_R287_复盘只跑一次状态机():
    """`_steps` 抽出来就是为了这个。逐日行与这一栏各 compute 一次的话, 哪天
    有一处漏改就开始各说各话(R286 同一条教训)。"""
    import app.indicators.livermore as lv
    calls = {"n": 0}
    real = lv.compute

    def counted(*a, **kw):
        calls["n"] += 1
        return real(*a, **kw)

    rs_compute = rs.compute
    rs.compute = counted
    try:
        rs.review_for_symbol(_Repo(_review_frame()), "600000.SH", 120)
    finally:
        rs.compute = rs_compute
    assert calls["n"] == 1, f"状态机跑了 {calls['n']} 次"


def test_R287_连着两个多头段只算一次买卖():
    """六态转折 ≠ 买卖。**自然回升 → 上涨趋势也是一次转折, 但两边都在多头侧,
    手上根本不用动** —— 那是继续持有, 不是又买了一次。

    这条是接进复盘之后跑真数据才现形的: 一条路径走出「上涨趋势 / 自然回撤 /
    自然回升 / 上涨趋势 / 自然回撤」五段, 多头段有 3 个, 但真正的建仓只有 2 次
    (第 3、4 段是连着的一次持仓)。用户的哲学是「尽可能减少买卖次数」——
    把 3 摆在他面前就是虚报了一次手续费。
    """
    states = ["NREA",           # 起手空头
              "NR", "NR",       # ← 转多  买入①
              "UT", "UT",       # ← 转折, 但还在多头侧 —— 不动
              "NREA", "NREA",   # ← 转空  卖出
              "NR", "NR",       # ← 转多  买入②
              "DT", "DT"]       # ← 转空  卖出(收掉, 否则末段未完会正好掩盖这个 bug)
    opens = [10, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19]
    s = simulate(_steps(states), opens, [float(o) for o in opens])
    sides = [l["side"] for l in s["legs"]]
    assert sides == ["多头", "多头", "空头", "多头", "空头"], f"场景没搭对: {sides}"
    assert s["trades"] == 2, "连着的两个多头段被当成了两次买卖"


def test_R287_跟着做的复利不受连段影响():
    """把连着的多头段拆开分别复利, 与合成一段直接算, 结果必须一样 ——
    因为下一段的买入价就是上一段的卖出价(见「段与段之间不许有缝」)。
    这条钉住 `trades` 的修法没有顺手改坏收益率。"""
    states = ["NREA", "NR", "NR", "UT", "UT", "NREA", "NREA"]
    opens = [10, 10, 10, 12, 15, 20, 20]
    s = simulate(_steps(states), opens, [float(o) for o in opens])
    done = [l for l in s["legs"] if l["side"] == "多头" and not l["open_ended"]]
    assert len(done) == 2, f"场景没搭对: {len(done)} 个已完成多头段"
    # 10.00 买进, 20.00 卖出 —— 中间那次转折不动手, 所以就是 +100%
    assert s["follow"] == pytest.approx(1.0, abs=5e-4)
    assert s["trades"] == 1


def test_R287_每一段都说得出手上该干什么():
    """段不等于动作。界面上要能分清"这一段起头是买进"和"这一段起头只是又转了
    一次、手不用动" —— 不分清的话, 五段就会被读成五次买卖。
    """
    states = ["NREA", "NR", "NR", "UT", "UT", "NREA", "NREA"]
    opens = [10, 10, 11, 12, 13, 14, 15]
    s = simulate(_steps(states), opens, [float(o) for o in opens])
    assert [l["act"] for l in s["legs"]] == ["买入", "持有", "卖出"]


def test_R287_样本太少要标出来(review):
    """3 段是 R191 给「一侧算不算数」定的门槛, 这一栏沿用同一个数 ——
    **而且是同一处定义**, 不许在 flip_trades 里再写一个 3。"""
    from app.services.review_service import MIN_SIDE_EPISODES
    ft = review["flip_trades"]
    assert ft["thin"] is (ft["bull"]["scored"] < MIN_SIDE_EPISODES)


# ---------------------------------------------------------------- 界面守卫
#
# 后端算对了不等于界面说对了。这一段守的全是**会误导人的说法**。

def _panel() -> str:
    from tests.frontend_source import code_of
    return code_of("components/stock-analysis/FlipTradesPanel.tsx")


def test_R287_这一栏真的挂在趋势状态页上():
    """[R289] 版面重排之后这一栏从整块面板压成了一条 `FlipTradesBar`, 并且
    **提到了头一行** —— 用户: 「在趋势状态里面, 功能按转折买卖部分才是重点」。
    守的东西没变: 它得真的无条件渲染出来。"""
    from tests.frontend_source import code_of
    dlg = code_of("components/stock-analysis/StockReviewDialog.tsx")
    i = dlg.index("function TrendView")
    blk = dlg[dlg.index("return (", i):]
    assert "\n          <FlipTradesBar" in blk, "趋势状态页没有无条件挂上这一栏"
    return
    # **必须钉整行**。只查 `"<FlipTradesPanel" in blk` 是不够的 —— 把它包成
    # `{false && <FlipTradesPanel …/>}` 照样含有这个子串, 变异测试当场就漏了。
    # (R286 那条守卫是同一个形状, 那次是靠别的断言兜住的。)
    # **必须钉成"这一行以它开头"**。只查子串是不够的 —— 包成
    # `{false && <FlipTradesPanel …/>}` 照样含有它, 变异测试当场就漏了。
    # (R288 把 props 拆成多行之后, 这里从整行钉改成行首钉。)
    assert "\n      <FlipTradesPanel" in blk, (
        "组件没有无条件渲染 —— 写好了却挂不上, 正是 R274 那个病"
    )
    # 顺序: 分档依据(OutcomeChips) → 这一栏 → 依据(TrendStatsPanel)
    assert blk.index("<OutcomeChips") < blk.index("<FlipTradesPanel") < blk.index("<TrendStatsPanel"), (
        "位置不对: 它是结论级的, 该在「分档依据」之后、「依据」之前"
    )


def test_R287_口径必须印在界面上():
    """「次日开盘」是这一栏与作者那份跟随收益唯一的差别, 不写出来的话,
    两个页面上两个不同的数就成了无头公案。

    [R288] 口径那句话搬到调用方去了(两个页签各写各的), 所以这里改成两条:
    ① 组件真的把它渲染出来(不是收了个 prop 就扔); ② 调用方真的传了。
    第二条在 `test_R288_两栏的口径各写各的`。
    """
    code = _panel()
    assert "{basis}" in code, "组件收下了口径却没印出来"
    from tests.frontend_source import code_of
    dlg = code_of("components/stock-analysis/StockReviewDialog.tsx")
    assert dlg.count("不做空") == 2, "两个页签都得写清是清仓不是做空"


def test_R287_空仓段不许被说成盈亏():
    """A 股散户做不了空。空头段那个数是"你没参与的涨跌" ——
    写成 +8.2% 并染成红色, 就等于告诉用户那八个点是他赚的。"""
    code = _panel()
    assert "躲开" in code and "踏空" in code, "空仓段没有独立的说法"
    i = code.index("function idleText")
    body = code[i:code.index("\n}", i)]
    assert "chgCls" not in body, "空仓段用上了涨跌红绿 —— 会被读成盈亏"


def test_R287_撞板与未完必须显形():
    code = _panel()
    assert "未必真成交得到这个价" in code, "撞涨跌停的成交没有提示"
    assert "open_ended" in code, "未完成的段没有标记"


def test_R287_空栏要自己解释():
    """分不清"确实没转折"和"算不出来", 是这个仓库反复吃过的亏。"""
    code = _panel()
    for r in ("no_flip", "no_open"):
        assert r in code, f"空栏没有交代 {r} 这一种情况"


def test_R287_买卖次数与段数不许混为一谈():
    """界面上写的必须是 `trades`(建仓次数), 不是 `legs.length`。
    后端那个 bug 就是这么来的 —— 连着的多头段被当成了两次买卖。"""
    code = _panel()
    # [R301] 那一格从行内的「买卖 <b>N</b> 次」变成了格子里的上标签下数值,
    # 锚点跟着换成标签本身。**测的东西一个字没变**: 这一格取的必须是
    # `ft.trades`(建仓次数), 不是 `legs.length`(段数)。
    i = code.index(">买卖<")
    assert "ft.trades" in code[i:i + 220], "「买卖 N 次」用的不是建仓次数"
    assert "legs.length" not in code[i:i + 220], "又拿段数当买卖次数了"


def test_R287_两处跟随收益都写明了各自的口径():
    """作者的阈值网格里也有一份「跟随收益」, 那份是**转折日收盘**进出。
    两个数必然不同(差一个隔夜跳空), 两处都得说清自己是哪一种, 否则用户
    在两个页面上看到两个数只会以为其中一个算错了。见名词表的 NOT_A_CONFLICT。"""
    from tests.frontend_source import code_of
    bar = code_of("components/stock-analysis/TrendStateBar.tsx")
    assert "跟随收益" in bar, "场景没搭对: 阈值网格那份说明不见了"
    # 锚在那段说明**独有**的措辞上 —— 「跟随收益」「买入持有基准」都还出现在
    # 表头与 title 里, 拿它们定位会锚到别处去(这条测试第一版就锚错了)
    i = bar.index("仅多头状态持有的复利收益")
    assert "转折日收盘" in bar[i:i + 300], "阈值网格那份没写明是收盘口径"
    assert "次日开盘" in bar[i:i + 300], "没指出复盘页那份是另一个口径"


def test_R287_跟随比买入持有多赚多少只有一个名字():
    """阈值网格那一列原来叫「超额」, 复盘页这一栏叫「多赚」—— 同一个概念
    (跟随 − 买入持有)两个名字。而且「超额收益」在本仓库另有所指(个股 vs 大盘),
    所以统一到「多赚」而不是「超额」。

    不进名词表是因为**不能禁裸的「超额」** —— `trend_template` 那个才是合法的
    「超额收益」, 一禁就把合法文案判成违规(名词表开头那条取舍)。这里定点守。
    """
    from tests.frontend_source import code_of
    bar = code_of("components/stock-analysis/TrendStateBar.tsx")
    assert ">多赚<" in bar, "阈值网格那一列没改名"
    assert ">超额<" not in bar, "「超额」又回到阈值网格的表头上了"
    assert "多赚" in _panel(), "复盘页这一栏的说法没了"


def test_R287_未完成的多头段不许进跟着做的复利():
    """**这条是变异测试逼出来的。** 原来只有一条测「未完成的段不进胜负统计」,
    而那个场景里未完成的恰好是**空头**段 —— 空头段本来就被 side 过滤掉了,
    于是把 `not open_ended` 这个条件整个删掉, 那条测试照样全绿。

    真正要守的是: 最后一段是**多头**且还没走完时, 那笔浮盈**不许**算进「跟着做」。
    算进去就是拿一个还没兑现的数去吹成绩 —— R177「只数已兑现」的原话。
    """
    states = ["NREA", "NR", "NR", "NR"]
    s = simulate(_steps(states), [9.0, 9.0, 10.0, 10.0], [9.0, 9.0, 10.0, 12.0])
    leg = s["legs"][0]
    assert leg["side"] == "多头" and leg["open_ended"] is True, f"场景没搭对: {leg}"
    assert leg["ret"] == pytest.approx(0.2), "场景没搭对: 这笔浮盈得是非零的"
    assert s["follow"] == 0.0, "还没兑现的浮盈被算进「跟着做」了"
    assert s["trades"] == 1, "手确实下过单 —— 建仓次数该算, 只是结果还不知道"


# ================================================================
# [R288] 通道结论那一栏 —— 同一台发动机, 换一套「什么时候该有仓位」
# ================================================================
#
# 用户: 「通道结论这个部分也能这样搞类似的统计吗」。
#
# 能, 但**比六态多一个难点**: 六态每天非多即空, 而通道结论有三种
# **不是动作**的状态 —— 「拿着」(hold)、「等」(watch)、三档都在中部时压根
# 没有结论。把它们当成卖出, 仓位就会天天翻, 而作者写的原话正是「拿着」「等」。


def _rows(codes: list[str | None]) -> list[dict]:
    """按 code 铺逐日行。tone/title 一律**从作者的表里取**, 不在测试里手写 ——
    手写的话这些测试就变成在描述我以为的档位语气, 而不是真的那一套。"""
    from app.indicators.keltner import _VERDICTS
    out = []
    for i, c in enumerate(codes):
        v = None
        if c:
            title, _a, _d, _s, tone, _r = _VERDICTS[c]
            v = {"code": c, "title": title, "tone": tone}
        out.append({"date": f"d{i:02d}", "verdict": v})
    return out


def test_R288_买档建仓卖档与回避档清仓():
    days = verdict_days(_rows(["bottom_confirmed",   # buy   调整到位
                               "top_all_bands",      # sell  大顶区域
                               "falling_all_bands"]))  # avoid 下跌途中
    assert [d["side"] for d in days] == ["多头", "空头", "空头"]


def test_R288_拿着和等着不是动作要维持仓位():
    """**这一条是整件事最容易做错的地方。**

    「短线冲高」的原话是「拿着, 别在这加仓」;「候选池」是「等短期入场点」;
    「高位回落」是「别追, 等回到下沿再看」。三个都不是"卖出"。
    当成卖出的话, 一只票会在「调整到位 → 短线冲高 → 该止盈了」这种再正常
    不过的路径上被来回买卖两次。
    """
    days = verdict_days(_rows(["bottom_confirmed",   # buy    建仓
                               "high_short_only",    # hold   拿着
                               "watch_low",          # watch  等
                               "watch_high",         # watch  等
                               None,                 # 三档都在中部, 没结论
                               "top_confirmed"]))    # sell   清仓
    assert [d["side"] for d in days] == ["多头"] * 5 + ["空头"], (
        "「拿着」「等着」「没结论」把仓位弄丢了"
    )


def test_R288_起手空仓不许假设手上已经有票():
    days = verdict_days(_rows([None, "high_short_only", "watch_low"]))
    assert [d["side"] for d in days] == ["空头"] * 3, (
        "窗口开头还没等到任何买入信号, 不能当成已经持有"
    )


def test_R288_一次变化就是结论换一档():
    """含**有结论 ↔ 没结论**那两种切换 —— 它们在页签上也是两张不同的卡片。"""
    days = verdict_days(_rows(["watch_low", "watch_low", None, None, "watch_low"]))
    assert [d["flipped"] for d in days] == [False, False, True, False, True]


def test_R288_第一天不算变化():
    """与 `compute()` 开机那天同一个道理: 昨天没有结论, 谈不上"换了一档"。"""
    assert verdict_days(_rows(["top_all_bands"]))[0]["flipped"] is False


def test_R288_跑得通同一台发动机():
    codes = ["falling_all_bands", "bottom_confirmed", "bottom_confirmed",
             "high_short_only", "top_confirmed", "top_confirmed"]
    opens = [10.0, 10.0, 11.0, 12.0, 15.0, 14.0]
    s = simulate(verdict_days(_rows(codes)), opens, opens)
    assert s["reason"] is None and s["legs"], "接不上"
    # d01 变 buy → d02 开盘 11.00 建仓;  d03 变 hold → **不动手, 但是新的一段**;
    # d04 变 sell → d05 开盘 14.00 清仓。所以一个来回是 11.00 → 14.00, 中间
    # 被那次「拿着」切成了两段 —— 这正好也验了跨段复利: (15/11)·(14/15) = 14/11。
    assert [l["act"] for l in s["legs"]] == ["买入", "持有", "卖出"]
    buy = s["legs"][0]
    assert buy["enter_date"] == "d02" and buy["enter_price"] == pytest.approx(11.0)
    assert s["trades"] == 1, "一次来回被数成了两次买卖"
    assert s["follow"] == pytest.approx(14 / 11 - 1, abs=5e-4)


def test_R288_连着两天转折时用的是下单那一刻知道的信号():
    """**前视偏差, R288 这轮才现形。**

    原来 `_leg` 取的是**执行日**那一天的 side —— 而执行日的状态要等它自己收盘
    才知道。转折连着两天出现时, 这就等于:

        d01 收盘 → 转成上涨趋势(多头), 你在 d02 开盘买入
        d02 收盘 → 又转成自然回撤(空头)
        ↑ 代码却拿 d02 收盘后才知道的「空头」去标 d02 开盘那一笔

    结果是方向标反, 而且那一个真实的来回被整段吞掉。**下单那一刻你手上只有
    转折日的信号**, 所以 side 必须取自转折日。

    六态与通道结论**共用这条**: 后者更容易撞上 —— 通道结论天天在变。
    """
    days = _steps(["NREA", "UT", "NREA", "NREA"])
    # d00 的 flipped 是 True(开机那天, prev 为 None), `simulate` 会跳过它
    assert [d["flipped"] for d in days] == [True, True, True, False], "场景没搭对"
    s = simulate(days, [9.0, 9.0, 10.0, 12.0], [9.0, 9.0, 10.0, 12.0])
    first = s["legs"][0]
    assert first["side"] == "多头", (
        "d01 收盘转多、d02 开盘买入, 这一笔却按 d02 收盘后才知道的状态标了方向"
    )
    assert first["act"] == "买入" and first["state_cn"] == "上涨趋势"
    assert first["enter_price"] == pytest.approx(10.0)
    assert first["exit_price"] == pytest.approx(12.0), "买进又卖出的那个来回被吞了"
    assert s["trades"] == 1


def test_R288_复盘载荷两栏都带上了(review):
    for key in ("flip_trades", "verdict_trades"):
        ft = review[key]
        assert ft["reason"] is None and ft["legs"], f"{key} 接线没接上: {ft['reason']}"
        assert "thin" in ft, f"{key} 少了样本量标记"


def test_R288_结论那一栏与页签上的卡片一一对应(review):
    """与 R287 守的同一件事: 统计里那些日子, 必须就是屏幕上那些段的分界。

    「通道结论」页签的卡片是按 `verdict.code` 分段的, 所以每一笔的 `flip_date`
    都得是逐日行里**结论换了一档**的那一天。
    """
    rows = list(reversed(review["rows"]))          # 载荷是新→旧, 这里要按时间
    changed = set()
    prev = None
    for i, r in enumerate(rows):
        code = (r.get("verdict") or {}).get("code")
        if i and code != prev:
            changed.add(r["date"])
        prev = code
    assert changed, "场景没搭对: 这 120 天里结论一次都没变过"
    for l in review["verdict_trades"]["legs"]:
        assert l["flip_date"] in changed, (
            f"{l['flip_date']} 在统计里是一次变化, 但逐日行的结论没换档 —— 两处不同源"
        )


def test_R288_结论那一栏买卖比六态频繁(review):
    """**这本身就是个结论**, 不是巧合: 通道结论天天在变, 六态是趋势级的。

    用户的哲学是「尽可能减少买卖次数」—— 这一栏摆出来最有价值的一件事,
    正是让他看见按结论做要多下多少单。这条钉住两栏确实在量不同的东西
    (真相等的话, 说明两栏接到同一份数据上去了)。
    """
    a, b = review["flip_trades"], review["verdict_trades"]
    assert len(b["legs"]) > len(a["legs"]), (
        f"结论 {len(b['legs'])} 段 / 六态 {len(a['legs'])} 段 —— 两栏多半接串了"
    )


def test_R288_两个页签都挂上了而且都排在正文最前面():
    """同一件事在两个页签上必须在同一个相对位置 —— 一边在最上面、一边在别处的话,
    读的人得重新找一遍。

    [R292] 「全景」面板整个撤了(用户: 「剩下的东西都不需要了」), 所以位置改成
    钉**它排在逐日表 / 卡片流之前**。用户点名这一栏是重点。
    """
    from tests.frontend_source import code_of
    dlg = code_of("components/stock-analysis/StockReviewDialog.tsx")
    # [R293] 两个页签现在**同一个形状**: 摘要压成一条 `FlipTradesBar` 放在头部卡
    # 第一行, 明细并进各自的正文(逐日表 / 段落卡片)。
    # [R295] 通道结论的正文也换成了逐日表(用户: 「通道结论那部分也想要这样的
    # 记录」), 所以两边的正文锚点现在都是 `<table`。
    for fn, tag, body_tag in (("function TrendView", "<FlipTradesBar", "<table"),
                              ("function VerdictView", "<FlipTradesBar", "<table")):
        blk = dlg[dlg.index(fn):]
        blk = blk[:blk.index("\nfunction ", 1)] if "\nfunction " in blk[1:] else blk
        body = blk[blk.index("return ("):]
        assert tag in body, f"{fn} 没挂上这一栏"
        assert body.index(tag) < body.index(body_tag), (
            f"{fn} 里这一栏排到正文后面去了"
        )


def test_R288_两栏的口径各写各的():
    """两栏长得一样, 所以**口径那一句是唯一能分辨它们的东西**, 不许省。"""
    from tests.frontend_source import code_of
    dlg = code_of("components/stock-analysis/StockReviewDialog.tsx")
    # [R292/R293] 两栏的栏目名都搬到了 `HeadRow` 的左栏(三行共用一条左边缘),
    # 所以传给组件的 `title` 都是空的 —— 名字仍然印在屏幕上, 只是换了个地方出。
    assert 'label="按转折买卖"' in dlg, "六态那栏的栏目名没了"
    assert 'label="按结论买卖"' in dlg, "结论那栏的栏目名没了"
    assert "转折次日开盘进出" in dlg, "六态那栏的口径没了"
    # [R302] 结论那栏的口径句缩短了(那 100 字的偏差说明降进「说明」页), 但
    # **口径本身一个字没省** —— 它仍然是唯一能分辨这两栏的东西。
    assert "换档次日开盘进出" in dlg, "结论那栏的口径没了"


def test_R288_按清空模拟这件事要说出来():
    """作者给「该止盈了」写的是「可落袋一部分」、给「大顶区域」写的是
    「动仓位基调」—— 都不是清仓。这里一律按清空算, **比原话重**, 不说就是
    拿一个我自己定的口径冒充作者的判定。

    [R302] **这段话搬到「说明」页了**, 因为它每只票都一样(用户: 「没水平没用的
    内容就不要显示出来了」)。守的规矩一个字没变 —— 它必须**还说得出来**,
    而且正文得**指得到它**, 否则搬家就成了藏起来。所以这条改成两头都钉。
    """
    from tests.frontend_source import code_of
    view = code_of("components/stock-analysis/ReviewHelpView.tsx")
    assert "可落袋一部分" in view and "按清空模拟" in view, "没交代模拟得比原话重"
    assert "拿着" in view and "等着" in view, "没交代这三种状态不动手"
    # 光有这段文字不够 —— 它得真的渲染在「通道结论」那一节里, 而不是躺在
    # 源码某处。锚在那一节的 `Section` 上, 顺序也钉住。
    i = view.index('title="通道结论"')
    assert view.index("按结论买卖的口径", i) > i, "那段话没落在「通道结论」那一节里"
    # **正文必须指得到**: 搬走而不留路标, 与直接删掉没区别。
    dlg = code_of("components/stock-analysis/StockReviewDialog.tsx")
    j = dlg.index('label="按结论买卖"')
    assert "见「说明」" in dlg[j:j + 700], "正文没指向「说明」—— 那段口径就等于被藏了"


def test_R287_组件真的把提醒印出来():
    """`caveat` 与样本量、撞板那几条走同一个 `tradeNotes` 渲染。收了不印,
    等于把该说的话吞掉 —— 这一栏最贵的就是这些"别当真"的提示。

    [R289] 摘要压成一条 `FlipTradesBar` 之后, **这些提醒必须跟着数字留在正文**,
    不许跟背景资料一起收进全景: 把 +143% 摆出来而把「样本太少」藏起来是骗人。
    """
    code = _panel()
    i = code.index("export function tradeNotes")
    blk = code[i:i + 320]
    # [R302] `caveat` 那个入参删了 —— 它装的是**每只票都一样**的口径偏差,
    # 已经搬进「说明」页。这条纪律守的从来是**这只票的**那几条警告:
    # 样本太少 / 撞上涨跌停 / 最后一次还没执行 —— 一条都不许少。
    assert "caveat" not in blk, "口径偏差又塞回这几条「这只票的」警告里了"
    for keep in ("ft.thin", "ft.blocked", "ft.pending", "ft.skipped"):
        assert keep in blk, f"{keep} 那条警告没了 —— 把数字摆出来而把它藏起来是骗人"
    # [R293] 整块面板删了(明细并进两边的正文), 只剩压缩条这一处渲染。
    assert code.count("notes.map(") == 1, (
        f"提醒该有且只有一处渲染, 现在有 {code.count('notes.map(')} 处"
    )
    assert "FlipTradesPanel" not in code, "整块面板又回来了 —— 同一份明细印两处"


# ================================================================
# [R289] 版面重排 —— 背景资料收进「全景」, 每一段并进逐日表
# ================================================================
#
# 用户: 「全景图很多东西我是不看的, 用一个按钮全部藏起来, 点击按钮弹窗展示查看。
# 我只关注最核心的东西 …… 我只要关注趋势、转折、六态状态这些 …… 比如按照转折点
# 买卖和底部部分可以融合到一起显示」。


def _dialog() -> str:
    from tests.frontend_source import code_of
    return code_of("components/stock-analysis/StockReviewDialog.tsx")


def _fn_body(src: str, name: str) -> str:
    blk = src[src.index(name):]
    return blk[:blk.index("\nfunction ", 1)] if "\nfunction " in blk[1:] else blk


def test_R292_状态轴与涨跌停在头部那张卡里():
    """用户: 「120 天里 涨跌停 找个位置也放到图片里面, 状态轴也是」。"""
    body = _fn_body(_dialog(), "function TrendView")
    head = body[body.index("return ("):body.index("<table")]
    assert "<StateTimeline" in head, "状态色带没进头部"
    assert "涨停 {st.limit_ups}" in head, "涨跌停计数没进头部"
    assert "跌停 {st.limit_downs}" in head


def test_R292_头部三行共用一条左栏():
    """用户: 「图片这部分要对齐, 感觉太乱了, 没有边界感」。

    毛病是上一版三段各自 `px-4 pt-N`, 没有框也没有共同的左边缘。现在整块是一张
    有边框的卡, 行与行一条细分割线, **每行左边一栏固定宽度放标签** —— 三行的
    内容于是从同一条竖线开始, 「对齐」有了依据而不是靠 padding 凑。
    """
    body = _fn_body(_dialog(), "function TrendView")
    head = body[body.index("return ("):body.index("<table")]
    assert "{HEAD_CARD}" in head, "头部没有边框与行间分割线 —— 那正是「没有边界感」说的东西"
    assert head.count("<HeadRow") == 3, f"头部该是三行, 现在 {head.count('<HeadRow')} 行"
    # [R294] `HeadRow` 抽到了 `ReviewHeadRow.tsx` —— 三个页签共用一份实现, 于是
    # 「三张卡长得一样」是**结构上保证的**, 不是靠三处各自抄对。
    from tests.frontend_source import code_of
    row = code_of("components/stock-analysis/ReviewHeadRow.tsx")
    assert "w-[4.5rem] shrink-0" in row, "标签栏没有固定宽度 —— 三行对不齐"
    assert "divide-y divide-border/40 rounded-lg border border-border/60" in row, (
        "共用的外框没了"
    )


def test_R292_那些不要的东西真的删干净了():
    """用户: 「剩下的东西都不需要了」。**删是删掉, 不是藏起来** ——
    留着没人调的组件, 下一个人会以为界面上还有那一块(本仓库 R198 的规矩)。
    """
    dlg = _dialog()
    # `EvidencePanel` **不在这张单子上**: 它本来就是默认收起的一条(约 20px),
    # 不是用户嫌的那种压着正文的常驻块 —— 第一版顺手把它也删了, 那是过头。
    # 它由 `test_R269_依据排在正文之前` 正着守着。
    for gone in ("function NowCard", "function SideEdgeChip", "function OutcomeChips",
                 "function TrendStatsPanel", "ReviewOverviewSheet"):
        assert gone not in dlg, f"{gone} 还留在源码里 —— 没人调的死代码"
    from pathlib import Path as _P
    root = _P(__file__).resolve().parents[2] / "frontend" / "src"
    assert not (root / "components" / "stock-analysis" / "ReviewOverviewSheet.tsx").exists(), (
        "全景面板那个文件还在 —— 已经没人 import 它了"
    )
    # 跟着退役的两个 localStorage 键也不许留 —— 留着等于说界面上还有那两个开关
    # 钉 `kv(...)` 里那个**真正的键名**, 不钉变量名 —— 删掉的那两行上面留了一段
    # 说明为什么删, 里面按名字提到了它们(该写)。这条第一版没剥注释就直接扫,
    # 又被自己的注释绊了一次(本仓库这个坑的第 N 次)。
    storage = (root / "lib" / "storage.ts").read_text(encoding="utf-8")
    # 只有「趋势状态」那块折叠区退役了。「通道结论」那条「依据」还在(见上面
    # 那条注释), 它的键当然也得留着 —— 第一版把两个一起列进来, 是同一个过头。
    for key in ("'review-trend-stats-open'",):
        assert f"kv<boolean>({key})" not in storage, (
            f"{key} 还留在 storage 里, 但已经没人读了"
        )


def test_R302_通道结论那一页头一个说的就是今天这一档():
    """**这一页叫「通道结论」, 而它的头部卡里原来根本没有今天那一档结论。**

    查废话时才发现的(用户: 「检查通道结论页面有没有废话」「都围绕位置展开」)——
    要知道今天是「候选池」还是「大顶区域」, 得往下翻到那张 120 行表格的第一行。
    头一位摆的反倒是「阶段」(上升中/横盘中): 那是另一个读数, 而且它和结论
    **在抢同一件事**(R257 为一模一样的毛病把「阶段」从走势列撤过)。

    现在顺序是 **这一档 → 从哪三格来的 → 阶段 → 事件**: 结论第一、它的坐标
    第二、背景往后 —— 这就是"围绕位置展开"。顺序本身就是这条要钉的东西。
    """
    now = _fn_body(_dialog(), "function VerdictView")
    head = now[now.index('label="现在"'):now.index('label={`这 ')]
    assert "d.rows[0]?.verdict" in now, "头部卡拿不到今天那一档"
    # **钉渲染条件, 不只钉字样。** 包成 `{false && …}` 时 `{now.title}` 照样在,
    # 变异当场就漏了 —— 本轮这个坑的第 N 次(R292/R295 都栽过同一手)。
    assert "{!!now && (" in head, "「现在」那一行没按条件渲染今天这一档结论"
    assert "{now.title}" in head, "「现在」那一行没印今天这一档结论"
    assert "{!!now.days && (" in head, "今天这一档连着几天没按条件渲染"
    assert "已{now.days}天" in head, "今天这一档连着几天没印 —— 那是它的另一半"
    for a, b in (("{now.title}", "{here}"), ("{here}", "{ph.cn}"),
                 ("{ph.cn}", "d.channel!.event.cn")):
        assert head.index(a) < head.index(b), (
            f"「现在」那一行的顺序不对: {a} 该排在 {b} 前面(结论 → 坐标 → 阶段 → 事件)"
        )


def test_R302_不随票变的话不许常驻正文():
    """用户: 「没水平没用的内容就不要显示出来了」。

    **判据是"随不随票变"**, 不是"重不重要": 「按结论买卖」的口径偏差(「拿着」
    不动手、卖出侧比作者原话重)重要得很, 但它每只票、每次打开都是同一段, 常驻
    正文只是每张卡顶上挂一块恒定的琥珀色黄字。与 R299 在决策台清 `note` 同一条。

    反面同样要钉: **这只票的**那几条警告(样本太少 / 撞板 / 还没执行)一条都不许
    跟着搬走 —— 把数字摆出来而把"这个数不能当真"藏起来才是真骗人。
    """
    verdict = _fn_body(_dialog(), "function VerdictView")
    head = verdict[:verdict.index('label="现在"')]
    for gone in ("可落袋一部分", "动仓位基调", "按清空模拟", "caveat"):
        assert gone not in head, f"那段恒定的口径偏差又回到正文了: {gone}"
    # 正文那一行仍然得**指得到**它 —— 搬走不留路标等于删掉
    assert "见「说明」" in head, "正文没有指向「说明」的路标"
    # 反面: 这只票的警告一条不少(它们走 tradeNotes, 在 FlipTradesPanel 里)
    code = _panel()
    for keep in ("ft.thin", "ft.blocked", "ft.pending", "ft.skipped"):
        assert keep in code, f"{keep} 那条「这只票的」警告没了"


def test_R301_四个数排成等宽格子():
    """用户: 「内容显示整理好划分好卡片布局, 现在的显示不对齐」。

    **不对齐的根在这一行**: 原来它把三种字号(`text-lg` / `text-sm` /
    `text-[10px]`)、四个长短不一的标签、外加 `basis` 一整句话全塞进同一条
    `flex flex-wrap items-baseline` 里 —— 没有任何两样东西的边是对齐的, 而且
    `text-lg` 那个数把整行撑高, 后面几个数被顶得偏下。

    改成格子之后**标签与标签一条线、数值与数值一条线**。这条正反各钉:
    格子在、而且四个数**同一个字号**(用大一号做强调, 代价正好是把基线打散)。
    """
    code = _panel()
    body = _fn(code, "FlipTradesBar")
    assert "grid" in body and "sm:grid-cols-4" in body, "四个数不是排成格子的"
    # **字号统一**要在整个文件上看: 三个百分比走 `Stat`(那是另一个函数),
    # 「买卖 N 次」那格写在 `FlipTradesBar` 里 —— 只扫一个函数会漏掉另一半
    # (第一版就这么错了, 数出来是 1 不是 4)。
    assert "text-lg" not in code and "text-sm" not in code, (
        "又有一个数用了不一样的字号 —— 这一排的基线会被它打散"
    )
    assert code.count("text-base") == 2, (
        f"同字号的数值有 {code.count('text-base')} 处 —— 该是 Stat 一处 + 「买卖」那格一处"
    )
    # 口径必须**自己一行**: 它跟在四个数后面挤在同一条 flex 里时, 一句话就把
    # 那一行撑到换行, 数值再也排不齐 —— 它是脚注, 不是第五个指标。
    assert body.index("sm:grid-cols-4") < body.index("{basis}"), "口径又挤进那一排数里了"


def test_R301_主角靠加粗不靠更大的字号():
    """反面配对: 别为了"对齐"把「跟着做」也拍平成和别的一样。

    它是用户带着的那个问题的答案, 必须能一眼认出来 —— 靠**排第一 + 着色 +
    加粗**, 而不是靠字号(字号一大, 这一排的基线就散了, 那正是上一条的毛病)。
    """
    code = _panel()
    # **用 `_fn` 取函数体**: 直接切到第一个 `\n}` 会停在解构参数那个 `}` 上,
    # 整个渲染段落根本没被检查到(R295 在这个坑上栽过, 这次当场又栽了一次)。
    stat = _fn(code, "Stat")
    assert "lead && 'font-semibold'" in stat, "主角那一格没有加粗"
    assert "lead ? 'text-secondary'" in stat, "主角那一格的标签没有着色"
    assert "text-lg" not in stat, "又用字号做强调了"
    # 用它的地方也得对上: 只有第一个数是主角
    bar = code[code.index("export function FlipTradesBar"):]
    assert bar.count(" lead\n") == 1, "主角不是恰好一个"


def test_R301_三条子说明共用一条左栏():
    """同一件事在两级上做: `HeadRow` 让三行的正文从同一条竖线开始, `SubRow` 让
    行内那几条子说明也从同一条竖线开始。

    原来它们是各写各的 `<p><span>该盯什么: </span>…</p>` —— 小标签宽度各不相同
    (「该盯什么」三字、「这一格历来」五字), 于是正文的起点一行一个样。
    这正是用户说的「不对齐」在「现在」那一行里的样子。
    """
    from tests.frontend_source import code_of
    head = code_of("components/stock-analysis/ReviewHeadRow.tsx")
    assert "export function SubRow" in head, "没有共用的子条目行"
    body = head[head.index("export function SubRow"):]
    assert "shrink-0" in body and "w-[" in body, "子条目的左栏宽度不是写死的 —— 那就对不齐"

    verdict = _fn_body(_dialog(), "function VerdictView")
    assert verdict.count("<SubRow") == 3, (
        f"「现在」那一行有 {verdict.count('<SubRow')} 条子说明 —— 该是三条"
        "(该盯什么 / 这一格历来 / 组合注记)都走共用件"
    )
    # 反面: 不许再有自己写一遍小标签的
    assert "该盯什么: </span>" not in verdict, "又有一条自己写小标签了"


def test_R301_说明是一页而不是盖上来的一层():
    """这一条追了三版, 每一版都是同一个问题在推:

        R289 「全景」  盖住整个正文的面板 → 用户: 「我点进去全屏了」
        R292 抽屉      从右边推进来占 26rem, 正文那一侧还看得见
        R301 页签      **换掉正文, 不再盖任何东西**

    用户最后一句: 「说明点击后不是弹窗, 和趋势状态一样内容区域显示」。

    **钉的是"它不盖东西"**, 而不是某一版的具体写法 —— 前两版栽的都是同一处:
    一个绝对定位的层, 定位祖先漏了就冒到最外面去(R289 那次就真的全屏了)。
    现在它是普通文档流里的一块, 那类 bug 从结构上不可能再犯。
    """
    from tests.frontend_source import code_of
    view = code_of("components/stock-analysis/ReviewHelpView.tsx")
    for gone in ("absolute", "inset-", "fixed", "z-20", "shadow-2xl"):
        assert gone not in view, f"说明这一页还留着盖上来那一层的写法: {gone}"
    # 正面: 与另外两页同一个骨架 —— 占满剩余高度、自己滚动
    assert "min-h-0 flex-1 overflow-auto" in view, "说明页不是和另外两页一样的正文块"


def test_R292_说明抽屉两个页签共用一处():
    """它讲的是六态与结论**两边**的词, 每个页签各挂一份就是同一份东西的两个副本。

    [R294 → R296] R294 那阵子是**两处**: 组合速查走的是另一个分支(它不等复盘
    请求, 见 R228), 只能自己挂一份。R296 把那一页并掉之后分支没了, 于是回到
    名副其实的一处 —— 两个页签同一个 `help` 开关、同一个抽屉。
    """
    dlg = _dialog()
    assert dlg.count("<ReviewHelpView") == 1, (
        f"说明页挂了 {dlg.count('<ReviewHelpView')} 处 —— 该只有一处"
    )
    # [R300 → R301] 入口也是一处, 而且**就在页签组里**。R300 时它还是个开关
    # (`setHelp`), R301 之后它就是 `tab` 的第三个取值 —— 少一个状态。
    assert dlg.count("setTab('help')") == 1, "说明入口不是一处"
    assert "setHelp" not in dlg, "`help` 那个布尔状态还留着 —— 它已经是 tab 的一个取值了"
    for fn in ("function TrendView", "function VerdictView"):
        body = _fn_body(dlg, fn)
        assert "<ReviewHelpView" not in body, f"说明页挂进了 {fn} 里"
        assert "onHelp" not in body, f"{fn} 里还留着说明入口 —— 它该只在页签那一行"
    # 入口必须和另外两个页签在**同一组**里 —— 用户画的就是这三个挨着的样子
    head = dlg[dlg.index("([['trend', '趋势状态']"):]
    head = head[:head.index("</div>")]
    assert "setTab('help')" in head, "说明入口没和页签在同一组里"


def test_R301_换页签没有过渡也不拦_Esc():
    """[R292 → R301] R292 那两条钉的是**抽屉的动效**(只推 transform/opacity、
    照顾 `motion-reduce`)与**Esc 只关这一层**。抽屉没了, 两条都该反过来:

    · **换页签不该有过渡。** 那 180ms 是"一层推进来"的手势; 页签之间是**换内容**,
      加过渡只会让每次点击都慢一拍(AGENTS.md 的动效判据: 高频动作不加动效)。
    · **Esc 不该被这一页拦。** 它不是"一层"了, Esc 该照旧关掉整个复盘弹窗 ——
      留着那个 `stopPropagation` 的话, 停在说明页时 Esc 会变成什么都不做。
    """
    from tests.frontend_source import code_of
    code = code_of("components/stock-analysis/ReviewHelpView.tsx")
    assert "transition" not in code, "换页签加了过渡 —— 每次点击都慢一拍"
    assert "Escape" not in code and "stopPropagation" not in code, (
        "这一页还在拦 Esc —— 停在说明页时 Esc 就关不掉复盘弹窗了"
    )


# ---------------------------------------------------------------- R290
#
# 用户: 「外面不再是显示"正在转多"这样的的字眼了, 这类词统一改成出现转折后的
# 第几天」。

def test_R290_决策台走势列不再印推断词():
    """「正在转多」是 `ph.align.cn`(三个尺度对齐到第几步)。它与徽标上的六态
    **抢同一件事 —— 方向**(R257 为一模一样的毛病撤过「阶段」), 而且它是个推断;
    换成"转折之后走了几天"是个事实, 还正好回答扫这一列时想问的那句话。

    降进悬停当依据, 不是删掉(R270「收起来, 不删」同一条路子)。
    """
    from tests.frontend_source import code_of
    code = code_of("components/stock-analysis/decision-board/cells.tsx")
    blk = code[code.index("export function ChannelStateCell"):]
    render = blk[blk.index("return ("):]
    assert "{ph.align.cn}" not in render, "走势列还在印「正在转多」那类推断词"
    assert "转折后第 {trend.duration} 天" in render, "没换成「转折后第几天」"
    # 正面: 依据没丢, 还在悬停里
    assert "ph.align.cn" in blk[:blk.index("return (")], "三尺度对齐连悬停里都没了 —— 那是删不是收"


def test_R291_转折那天只说一遍():
    """用户看着截图: 「显示不好看, 想想怎么设计今天就是转折的场景」。

    毛病是**同一件事说了两遍**: 第一行一枚琥珀「转折」小标, 第二行又是一行
    琥珀「转折后第 1 天」, 中间还夹着一个绿色徽标 —— 一个小格子里三种颜色、
    两份同样的意思。

    现在合成一个槽位: 第二行本来就是"离转折多远", 转折当天它自己变成
    「今天转折」。**信息一点没少, 少的是重复。**
    """
    from tests.frontend_source import code_of
    code = code_of("components/stock-analysis/decision-board/cells.tsx")
    blk = code[code.index("export function ChannelStateCell"):]
    render = blk[blk.index("return ("):]
    assert "今天转折" in render, "转折当天没有那句大白话"
    assert "转折后第 {trend.duration} 天" in render, "平常那天的天数没了"
    # 反面: 第一行不许再挂一枚独立的转折小标。
    # **先剥掉 title 属性** —— 悬停里解释「什么叫转折」是应该的, 它不占版面,
    # 不算重复。第一版没剥就直接数, 把两句 title 也数进去了。
    import re
    visible = re.sub(r'title=(?:"[^"]*"|\{(?:[^{}]|\{[^{}]*\})*\})', "", render, flags=re.S)
    assert visible.count("转折") == 2, (
        f"「转折」在可见文案里出现了 {visible.count('转折')} 次(该是 2: "
        f"「今天转折」与「转折后第 N 天」这两个互斥分支) —— 多半又多了一处重复"
    )


def test_R291_两种状态用同一个盒子():
    """行高不许跳。转折那天是芯片、平常是纯文字的话, 一列扫下来第二行的
    基线会一行一个样(R217「固定两行」那条规矩)。所以两种状态共用同一套
    `px-1.5 py-px` 与同样宽的边框, 只是平常那天边框透明。
    """
    from tests.frontend_source import code_of
    code = code_of("components/stock-analysis/decision-board/cells.tsx")
    blk = code[code.index("export function ChannelStateCell"):]
    i = blk.index("今天转折")
    box = blk[i - 700:i]
    assert "inline-flex whitespace-nowrap rounded border px-1.5 py-px" in box, (
        "两种状态没共用同一个盒子 —— 转折那行会比别的行高一截"
    )
    assert "border-transparent" in box, "平常那天的边框没设成透明"


def test_R291_判定仍然只读后端那个字段():
    """R286 立的规矩: `flipped` 是后端给的, 前端不许自己从 `duration` 推。
    这次改的是**长什么样**, 不是**怎么判**。"""
    from tests.frontend_source import code_of
    code = code_of("components/stock-analysis/decision-board/cells.tsx")
    blk = code[code.index("export function ChannelStateCell"):]
    render = blk[blk.index("return ("):]
    assert "trend.flipped ?" in render, "没读后端那个字段"
    for derived in ("duration === 1", "duration == 1", "duration <= 1"):
        assert derived not in render, f"又从 `{derived}` 自己推转折了"


# ================================================================
# [R293] 「通道结论」照着「趋势状态」重排
# ================================================================
#
# 用户: 「通道结论也复刻参考趋势状态改好的排版显示重点内容, 通道结论这部分的
# 关注重点是『调整到位』和这些状态期间的买卖」;「你可以理解为核心是按结论买卖」;
# 「你别搞错了, 趋势状态也是按出现转折买卖而且已经做好了不用再改了, 通道结论
# 才是按结论买卖, 这是两个不同的核心」。


def test_R293_两个页签是两个不同的核心():
    """**这条是用户特意提醒的那句话。**

    趋势状态吃 `flip_trades`(按六态**转折**买卖), 通道结论吃 `verdict_trades`
    (按**结论**换档买卖)。两份数据、两套口径、两个标题 —— 接串了的话两页会显示
    同一个数, 而那正是最难查的一类错(界面看着都对, 只是其中一页在说别人的事)。
    """
    dlg = _dialog()
    trend = _fn_body(dlg, "function TrendView")
    verdict = _fn_body(dlg, "function VerdictView")
    assert "ft={d.flip_trades}" in trend and "ft={d.verdict_trades}" not in trend, (
        "趋势状态那页接错了数据源"
    )
    assert "ft={d.verdict_trades}" in verdict and "ft={d.flip_trades}" not in verdict, (
        "通道结论那页接错了数据源"
    )
    assert 'label="按转折买卖"' in trend and 'label="按结论买卖"' in verdict


def test_R293_两个页签的头部是同一个形状():
    """用户: 「复刻参考趋势状态改好的排版」。同构才谈得上"复刻" ——
    一边是带边框三行卡、另一边是三段裸 flex 的话, 切页签就像换了个软件。
    """
    dlg = _dialog()
    # [R294 → R296] R294 时是三个页签; R296 把「组合速查」并进「通道结论」,
    # 剩两个 —— 规矩没变, 覆盖面跟着少一个。
    bodies = {fn: _fn_body(dlg, fn) for fn in ("function TrendView", "function VerdictView")}
    for fn, head in bodies.items():
        # [R300] 头部到哪儿为止: 原来切到 `<HelpButton>`(它就在头部卡后面),
        # 那个按钮搬进页签组之后改切到**逐日表**——两页的头部都在表之前, 而且
        # 这个界标比按钮稳(表是这一页的正文, 不会再搬家)。
        head = head[:head.index("<table")]
        assert "HEAD_CARD" in head, f"{fn} 的头部不是那张共用的带边框卡"
        assert head.count("<HeadRow") == 3, f"{fn} 的头部该是三行"
        assert "<StateTimeline" in head, f"{fn} 的头部没有状态轴"


def test_R295_每一笔长在换档那一行上():
    """[R293 → R295] 融合的对象换了, 规矩没变: **明细并进正文**, 不单开一张表。

    R293 并进的是段落卡片; R295 用户指着「趋势状态」那张逐日表说「通道结论那
    部分也想要这样的记录」, 于是正文换成同形状的表, 那一笔就并到**换档那一行**
    上 —— 与趋势那边逐字同一套三列。
    """
    verdict = _fn_body(_dialog(), "function VerdictView")
    assert "legsByFlipDate(d.verdict_trades)" in verdict, "没有按换档日建索引"
    assert "<FlipTradeCells leg={legs.get(r.date)} />" in verdict, "换档行上没长出那一笔"
    assert "function SegmentCard" not in _dialog(), (
        "段落卡片还留着 —— 同一条时间轴印两遍, 而且两处不同步没人会发现"
    )


def test_R293_那张独立的每一段表整个删了():
    """留着就是同一份明细印两处 —— 而且两处哪天不同步了没人会发现。"""
    from tests.frontend_source import code_of
    panel = code_of("components/stock-analysis/FlipTradesPanel.tsx")
    for gone in ("function FlipTradesPanel", "function LegTable", "flipLabel", "legNote"):
        assert gone not in panel, f"{gone} 还留着 —— 那块面板该整个撤了"
    assert "<FlipTradesPanel" not in _dialog(), "还有人在挂那块面板"


def test_R293_行内那一笔与逐日表那三格说同一套话():
    """两处是同一份内容换个排版。**空仓段的写法尤其不能各写各的** ——
    一边写「躲开 8%」另一边写「-8%」的话, 后者会被读成亏了 8 个点。
    """
    from tests.frontend_source import code_of
    panel = code_of("components/stock-analysis/FlipTradesPanel.tsx")
    line = panel[panel.index("export function FlipTradeLine"):]
    cells = panel[panel.index("export function FlipTradeCells"):]
    cells = cells[:cells.index("\nexport function ")] if "\nexport function " in cells[1:] else cells
    for shared in ("ACT_CLS[leg.act]", "idleText(leg.ret)", "leg.side === '多头' ? chgCls(leg.ret)"):
        assert shared in line and shared in cells, f"两处的「{shared}」不一致"


def test_R293_这N天那一行按语气分档而不是十档全铺():
    """十个数一行放不下, 而且用户真正要找的是"偏买的那几段"。"""
    verdict = _fn_body(_dialog(), "function VerdictView")
    assert "byTone" in verdict, "没有按语气分档的计数"
    assert "{segments.length} 段结论" in verdict, "没给总段数"


# ================================================================
# [R294] 为什么「组合速查」**不再立一栏「按位置买卖」**
# ================================================================
#
# 用户: 「组合速查也要, 它是按照位置为核心」。
#
# 照前两个页签的样子, 第三栏该是「按三档位置组合换格买卖」。**但那个数会和
# 「按结论买卖」一模一样** —— 而这个仓库最不该做的就是把同一个数印两遍。
#
# 原因是: 方向(该不该持仓)是**逐日**由那一格的语气定的, 而位置组合换格比结论
# 换档更频繁 —— 多出来的那些换格**两边同向**, 于是只是把同一段行情多切了几刀。
# 段与段之间没有缝(下一段的买入价就是上一段的卖出价), 所以复利一乘就telescoping
# 回去了, 建仓次数也不变。
#
# 下面这条**把这件事证出来**, 而不是我拍脑袋说一句。

def _resegment(days: list[dict]) -> list[dict]:
    """在**方向没变**的地方多切几刀 —— 模拟"换格但没换边"的那些天。

    **只在第一次与最后一次真转折之间切。** 第一版没设这个界, 结果多切出来的刀
    落到了首尾之外:
      · 切在第一次真转折**之前** → 整段区间的起点被往前挪, `hold` 换了个基准;
      · 切在最后一段**里面** → 未完成的那一截被切出一半"已完成", 混进了复利。
    两样都不是"多切几刀", 是"换了一段区间"。**第一遍跑出来红了, 红在场景上,
    不在被测的性质上** —— 先怀疑变异/场景本身, 这是本轮的教训。
    """
    # **`i + 1 < len(days)` 这个条件不能少**: 窗口最后一天的转折没轮到执行
    # (它只进 `pending`), 拿它当上界的话, 切点会落到最后那段未完成的段里面 ——
    # 第二遍就红在这儿, 又是场景的问题。
    real = [i for i, d in enumerate(days)
            if d["flipped"] and d.get("prev") is not None and i + 1 < len(days)]
    lo, hi = real[0], real[-1]
    out = []
    for i, d in enumerate(days):
        extra = lo < i < hi and i % 2 == 0 and not d["flipped"]
        out.append({**d, "flipped": d["flipped"] or extra})
    return out


def test_R294_多切几刀不改变成绩(real):
    """**这是「不再立第三栏」的依据。**

    同一条 side 序列, 只要多切的那些刀两边同向, 「跟着做」「一直拿着」「多赚」
    「买卖次数」四个数一个都不会变 —— 变的只有段数。

    **前提是切在首尾之间**(见 `_resegment` 的说明): 切到第一次转折之前会换掉
    区间起点, 切进最后那段未完成的会把一截尾巴变成"已完成"。这两条恰恰也是
    「按位置买卖」与「按结论买卖」唯一会差出来的地方, 差的只是那一头一尾。

    所以「按位置买卖」印出来会与「按结论买卖」逐字相同, 那是同一个数两个名字
    (R284 就为「同一纪律两个数」报过警, 这里是它的镜像)。
    """
    days, base = real
    cut = simulate(_resegment(days), _PATH_OPENS, _PATH)
    assert len(cut["legs"]) > len(base["legs"]), "场景没搭对: 没有真的多切出段来"
    for k in ("follow", "hold", "excess", "trades"):
        assert cut[k] == base[k], (
            f"多切几刀之后 {k} 变了({base[k]} → {cut[k]}) —— "
            f"那说明段与段之间有缝, 「跟着做」和「一直拿着」就不可比了"
        )


def test_R294_只有段数会变(real):
    """反面: 别把上面那条读成"怎么切都一样"。**段数是会变的** ——
    而段数正是「按位置买卖」唯一能多告诉你的东西(换格比换档频繁多少),
    那一句话放在界面上说清楚就够了, 不值得再摆一栏数字。
    """
    days, base = real
    cut = simulate(_resegment(days), _PATH_OPENS, _PATH)
    assert cut["bull"]["n"] + cut["bear"]["n"] > base["bull"]["n"] + base["bear"]["n"]


_COMBO = "components/stock-analysis/decision-board/ComboView.tsx"


def _combo() -> str:
    from tests.frontend_source import code_of
    return code_of(_COMBO)


def _fn(src: str, name: str) -> str:
    """取一个具名函数的函数体 —— 认 `function f` 与 `export function f` 两种写法,
    并且**认得出"它是文件里最后一个函数"**(那时候没有下一个 `function ` 可以切,
    R295 在这个坑上踩过一次)。"""
    i = src.index(f"function {name}")
    rest = src[i + 1:]
    j = rest.find("\nfunction ")
    k = rest.find("\nexport function ")
    cuts = [x for x in (j, k) if x >= 0]
    return rest[:min(cuts)] if cuts else rest


def test_R296_结论是位置的纯函数():
    """**这条是那次融合的依据。**

    合并之前得先证明两页监控的是同一个对象, 否则并页就是把两套判定糊在一起。
    穷举 5³ = 125 种三档位置(每档 上轨之上/贴上轨/通道内/贴下轨/下轨之下),
    看 `combo_code` 收出来的三字码能不能唯一决定 `verdict` 那一句话:

      · 125 种位置收成 27 格 —— 一格不多一格不少
      · **每一格只对应一个结论码, 零冲突** —— 所以「位置」不是独立的一层,
        它是结论的坐标; 那一页原本就是这一页的展开
      · 「中中上」「中中中」「中中下」三格没有结论 —— 其中两格靠 `combo_note`
        说话(R269 钉过), 那正是"大级别到位、等一个入场点"的另一半

    真出现冲突的话, 融合本身就是错的 —— 这条会先红。
    """
    import itertools

    from app.indicators.keltner import (
        POS_ABOVE, POS_BELOW, POS_INSIDE, POS_NEAR_LOWER, POS_NEAR_UPPER, verdict,
    )
    from app.indicators.keltner_geometry import combo_code

    positions = (POS_ABOVE, POS_NEAR_UPPER, POS_INSIDE, POS_NEAR_LOWER, POS_BELOW)
    seen: dict[str, set[str | None]] = {}
    for s, m, l in itertools.product(positions, repeat=3):
        bands = {"s": {"pos": s}, "m": {"pos": m}, "l": {"pos": l}}
        code = combo_code(bands)
        assert code is not None
        v = verdict(bands)
        seen.setdefault(code, set()).add(None if v is None else v["code"])

    assert len(seen) == 27, f"三字码收出来 {len(seen)} 格, 不是 27"
    clash = {k: v for k, v in seen.items() if len(v) > 1}
    assert not clash, f"同一格给出了不同结论 —— 位置不是结论的坐标, 那就不该并页: {clash}"
    assert sorted(k for k, v in seen.items() if v == {None}) == ["中中上", "中中下", "中中中"], (
        "没有结论的格子变了 —— 「中中上」「中中下」靠 combo_note 说话(R269)"
    )


def test_R296_位置并进了通道结论那一页():
    """用户: 「组合速查合并到通道结论里面去, 你看怎么融合」。

    **本来就该合**(`test_R296_结论是位置的纯函数` 穷举 125 种三档位置证过:
    同一个三字码永远给同一个结论, 零冲突)—— 两页监控的是同一个对象的两层。
    融合的分界线沿用 R292 那条: **这只票的常驻在正文, 恒定的参考进抽屉。**

        你在哪一格 / 这一格历来  → 「通道结论」头部卡的「现在」行
        27 格谱系                → 「说明」抽屉里一节
    """
    from tests.frontend_source import code_of
    dlg = _dialog()
    now = _fn_body(dlg, "function VerdictView")
    assert 'label="现在"' in now
    assert "comboHistory(d.rows, here)" in now, "「这一格历来」没并到通道结论页"
    assert "d.channel?.geo?.combo" in now, "「你在哪一格」没并到通道结论页"
    # 反面: 那一页的外壳与页签整个撤了, 不许留成第三个入口
    assert "function ComboView" not in code_of(_COMBO), "组合速查的外壳还留着"
    assert "<ComboView" not in dlg, "还在渲染那一页"
    assert "组合速查" not in dlg, "页签列表里还有「组合速查」"


def test_R296_27格进了说明那一页而不是另外两页():
    """那张表是**恒定的**(与今天这只票无关, R203 起就是个常量端点), 属于查表用的
    参考; 正文那一页讲的是这只票的时间序列。混在一起就是 R292 撤全景图那一遍。

    **那个取舍的交代跟着搬**: R294 在「组合速查」页上印过一句"为什么这一页不摆
    战绩"(换格两边同向, 复利乘回去与按结论买卖逐字相同)。那一页没了, 问题还在 ——
    看 27 格的人照样会问, 所以那句话进抽屉里这一节。
    """
    from tests.frontend_source import code_of
    sheet = code_of("components/stock-analysis/ReviewHelpView.tsx")
    assert '<ComboGroups rows={combo.data.rows} here={here} />' in sheet, "27 格没进抽屉"
    assert "按位置换格买卖的成绩与「按结论买卖」那一栏逐字相同" in sheet, (
        "没有交代为什么不另立一栏「按位置买卖」—— 那个取舍会被当成漏做"
    )
    # 反面: 不许把战绩搬进那一节, 否则就是同一个数印两个名字
    combo = code_of(_COMBO)
    for gone in ("verdict_trades", "flip_trades", "legsByFlipDate", "<FlipTradesBar"):
        assert gone not in combo, f"{gone} 又被搬到 27 格那一节来了"


def test_R296_这一格历来按段不按天():
    """R177 的老规矩: 一段连着 8 天算 1 次。按天算的话那 8 天的前瞻窗口互相
    重叠, 次数会被撑大, 很薄的结论看着挺扎实。"""
    fn = _fn(_combo(), "comboHistory")
    assert "if (prev !== here) segs += 1" in fn, "段数不是按「进出一次算一段」数的"
    # 前瞻取**段末**那天 —— 与「通道结论」那边同一个道理
    assert "!next || next.combo !== here" in fn, "前瞻收益取的不是段末那天"


def test_R294_位置码来自后端不在前端拼():
    """拼法归 `combo_code` 管。前端再拼一份就是同一个规则两处定义(R286)。"""
    combo = _combo()
    assert "r.combo" in combo, "没用后端给的位置码"
    # 反面: 不许在这里用 bands 现拼一个三字码
    for hand in ("'上' :", "? '上'", "join('')"):
        assert hand not in combo, f"像是在前端手拼位置码: {hand}"


def test_R296_没进过这一格与算不出来分得开():
    """[R294 → R296] 规矩一个字没变, 只是搬到了「通道结论」那一页上。

    两句话是两件事: 「头一回」是这只票没走到过, 「定不了」是三档缺了一档算不出
    位置。混成一句的话, 数据缺失会被读成"这是个罕见位置"。
    """
    now = _fn_body(_dialog(), "function VerdictView")
    assert "今天定不了这一格" in now, "三档缺档时没有独立说法"
    assert "这 {d.days} 天里没进过这一格 —— 头一回" in now, "没进过这一格时没有独立说法"
    # **关键那一条**: 「历来」整段必须挂在 `here` 上。挂空的话, 算不出位置的那天
    # 会一路掉进 `segs === 0` 分支, 印出「头一回」—— 正是这条要防的那次误读。
    assert "{!!here && (" in now, "「这一格历来」没有挂在位置码上"


# ================================================================
# [R295] 「结论」列离开趋势表, 通道结论拿到自己的逐日记录表
# ================================================================
#
# 用户指着趋势状态那张表里的结论列: 「删掉这一列」; 又指着那张表本身:
# 「通道结论那部分也想要这样的记录」。**两句是一件事** —— 那一列离开, 是因为
# 它要在自己那一页有一张同样的表。


def test_R296_趋势表里的结论列恢复了():
    """用户: 「趋势状态删除的那一列我需要恢复」。

    R295 我按"它在这张表里是外人"把它删了 —— 用户要它回来, 那就回来。**它的
    价值是横着对上一眼**: 同一行里六态说什么、通道位置说什么, 不必切页签。

    回来时有三处必须一起对上, 少一处就歪:
      ① 排在**成交三格之后** —— 这一页的主线是六态与按转折买卖, 结论是旁证;
      ② 列头逐字叫「通道结论」(R258: 同一层判定只许一个名字);
      ③ 空表那行的 `colSpan` 跟着回到 8。
    """
    trend = _fn_body(_dialog(), "function TrendView")
    assert "<VerdictHover v={r.verdict}" in trend, "「通道结论」那一列没回来"
    assert trend.index("<FlipTradeCells") < trend.index("<VerdictHover"), (
        "结论那一列插进了成交三格前面 —— 旁证不该打断主线"
    )
    assert ">通道结论</th>" in trend and ">结论</th>" not in trend, (
        "列头没叫「通道结论」—— 两张表并排放着会是同一样东西两个名字(R258)"
    )
    assert "colSpan={8}" in trend, "加回一列却没改 colSpan"


def test_R295_通道结论有一张同形状的逐日表():
    """同形状 = 同样七列、同样的转折行内联三格 —— **两页于是能左右对照着看**:
    同一天六态说什么、通道说什么、各自该动手没有。"""
    dlg = _dialog()
    trend = _fn_body(dlg, "function TrendView")
    verdict = _fn_body(dlg, "function VerdictView")
    for both in ("<table className=\"w-full text-xs\">",
                 "<FlipTradeCells leg={legs.get(r.date)} />",
                 "只看"):
        assert both in trend and both in verdict, f"两张表不同形状, 差在: {both}"
    assert "通道结论</th>" in verdict, "结论那一列没进新表"
    assert "六态状态</th>" in trend and "六态状态</th>" not in verdict, "两张表的状态列串了"
    # [R296] 列数不再相等: 趋势那张多一列「通道结论」(用户要它回来), 通道那张
    # 不需要反过来长一列六态 —— 它有自己的结论列。两处 colSpan 各自对上自己。
    assert "colSpan={8}" in trend and "colSpan={7}" in verdict, "空表那行的列数没对上"


def test_R295_换档标记读后端不自己比():
    """什么算一次换档归 `verdict_days` 管(含「有结论 ↔ 没结论」那两种切换)。
    前端拿 `verdict.code` 再比一遍就是同一个规则两处定义(R286 立过)。"""
    verdict = _fn_body(_dialog(), "function VerdictView")
    # 钉**渲染条件**, 不只是钉字段名与字样 —— 包成 `{false && …}` 时两者照样在,
    # 变异测试当场就漏了(本轮同一个坑的第 N 次)。
    assert "{r.verdict_flipped && (" in verdict, "换档标记没有按标记渲染"
    assert "← 换档" in verdict, "换档那天没有标记"
    assert "${r.verdict_flipped ? 'bg-amber-400/[0.05]' : ''}" in verdict, (
        "换档那一行没有底色 —— 一张 120 行的表, 靠底色才扫得出来"
    )
    for derived in ("verdict?.code !==", "verdict.code !==", "prevCode"):
        assert derived not in verdict, f"前端自己比了一遍换档: {derived}"


def test_R295_卡片上的内容一样没丢():
    """**删卡片不是删内容。** 怎么做/为什么/依据 全在结论徽标的悬停里 ——
    与决策台「结论」列悬停看到的是同一张卡, 一处内容两处用。"""
    verdict = _fn_body(_dialog(), "function VerdictView")
    assert "<VerdictHover v={r.verdict}" in verdict, "结论徽标没有完整卡片的悬停"
    assert "悬停看完整卡片" in verdict, "脚注没告诉人去哪儿看完整卡片"
