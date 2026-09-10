"""[fork 增强] R287 「按转折买卖」的分段战绩。

用户: 「我想统计每两个转折之间的收益, 也就是说出现转折我第二天开盘就买或者卖,
这个根据转折后的状态判断」。

口径全在 `flip_trades.simulate` 的 docstring 里, 这里只钉行为。
"""
import pytest

from app.services.flip_trades import simulate


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
    return out


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
    steps = compute(_PATH, _PATH_DATES, 0.06)["steps"]
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
    from tests.frontend_source import code_of
    dlg = code_of("components/stock-analysis/StockReviewDialog.tsx")
    i = dlg.index("function TrendView")
    blk = dlg[dlg.index("return (", i):]
    # **必须钉整行**。只查 `"<FlipTradesPanel" in blk` 是不够的 —— 把它包成
    # `{false && <FlipTradesPanel …/>}` 照样含有这个子串, 变异测试当场就漏了。
    # (R286 那条守卫是同一个形状, 那次是靠别的断言兜住的。)
    assert "\n      <FlipTradesPanel ft={d.flip_trades} />" in blk, (
        "组件没有无条件渲染 —— 写好了却挂不上, 正是 R274 那个病"
    )
    # 顺序: 分档依据(OutcomeChips) → 这一栏 → 依据(TrendStatsPanel)
    assert blk.index("<OutcomeChips") < blk.index("<FlipTradesPanel") < blk.index("<TrendStatsPanel"), (
        "位置不对: 它是结论级的, 该在「分档依据」之后、「依据」之前"
    )


def test_R287_口径必须印在界面上():
    """「次日开盘」是这一栏与作者那份跟随收益唯一的差别, 不写出来的话,
    两个页面上两个不同的数就成了无头公案。"""
    code = _panel()
    assert "转折次日开盘进出" in code, "没写清是次日开盘成交"
    assert "不做空" in code, "没写清空头段是清仓不是做空"


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
    i = code.index("买卖 <b")
    assert "ft.trades" in code[i:i + 200], "「买卖 N 次」用的不是建仓次数"


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
