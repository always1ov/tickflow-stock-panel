"""[R329] 今日信号 —— **只有真转折才能出手**。

用户: 「我只有一个要求, 你怎么设计补充都可以但一定要根据转折才能出手」。

这组守卫里最要紧的是 `test_R329_只有已转折那一档能出手`: 它遍历所有非 flipped
的分支, 断言 `act` 恒为 None。提示语会被改, 这条结构不会被顺手改掉。
"""
from __future__ import annotations

import pytest

from app.services import flip_today as ft


def _steps(states: list[str], *, flip_down=None, flip_up=None) -> list[dict]:
    """最后一根带触发价; flipped 按前后 state 自己算。"""
    out = []
    prev = None
    for st in states:
        out.append({"state": st, "prev": prev, "flipped": prev != st})
        prev = st
    out[-1]["flip_down"] = flip_down
    out[-1]["flip_up"] = flip_up
    return out


# ── 底线: 只有已转折那一档能出手 ────────────────────────────────────────
def test_R329_只有已转折那一档能出手():
    """**用户唯一的要求。** 穷举所有非 flipped 的产出, act 必须恒为 None。"""
    cases = [
        # 盘中越线(多头跌破 / 空头站上)
        (_steps(["UT", "UT"], flip_down=9.5), True, 10.0, 9.4),
        (_steps(["DT", "DT"], flip_up=10.5), False, 10.0, 10.6),
        # 接近但没到
        (_steps(["UT", "UT"], flip_down=9.8), True, 10.0, 9.9),
        (_steps(["DT", "DT"], flip_up=10.2), False, 10.0, 10.1),
        # 接近, 实时没开
        (_steps(["UT", "UT"], flip_down=9.8), True, 9.9, None),
    ]
    seen = set()
    for steps, held, last, live in cases:
        r = ft.evaluate(steps, held=held, last_close=last, live_close=live)
        assert r is not None, "这几组该有产出, 不然下面的断言是空的"
        assert r["stage"] != ft.STAGE_FLIPPED
        assert r["act"] is None, f"{r['stage']} 这一档不许出手 —— 只有真转折才能动手"
        seen.add(r["stage"])
    assert seen == {ft.STAGE_CROSSING, ft.STAGE_WATCH}, "两档都要覆盖到"


def test_R329_转折了才给动作():
    # 空仓 + 转多 → 买
    r = ft.evaluate(_steps(["DT", "UT"]), held=False, last_close=10.0)
    assert r["stage"] == ft.STAGE_FLIPPED and r["act"] == ft.ACT_BUY
    # 持有 + 转空 → 卖
    r = ft.evaluate(_steps(["UT", "DT"]), held=True, last_close=10.0)
    assert r["stage"] == ft.STAGE_FLIPPED and r["act"] == ft.ACT_SELL


def test_R329_转了但手上已经对上了就不重复动手():
    # 已持有 + 转多 → 不用再买
    r = ft.evaluate(_steps(["NR", "UT"]), held=True, last_close=10.0)
    assert r["stage"] == ft.STAGE_FLIPPED and r["act"] is None
    # 空仓 + 转空 → 本来就没拿, 没得卖
    r = ft.evaluate(_steps(["NR", "DT"]), held=False, last_close=10.0)
    assert r["stage"] == ft.STAGE_FLIPPED and r["act"] is None


@pytest.mark.parametrize("state", ["UT", "NR", "SR"])
def test_R329_三个多头态转入都算买(state):
    r = ft.evaluate(_steps(["DT", state]), held=False, last_close=10.0)
    assert r["act"] == ft.ACT_BUY


@pytest.mark.parametrize("state", ["DT", "NREA", "SREA"])
def test_R329_三个空头态转入都算卖(state):
    r = ft.evaluate(_steps(["UT", state]), held=True, last_close=10.0)
    assert r["act"] == ft.ACT_SELL


# ── 盯哪条线 ────────────────────────────────────────────────────────────
def test_R329_多头盯跌破_空头盯站上_方向不许拿反():
    r = ft.evaluate(_steps(["UT", "UT"], flip_down=9.8, flip_up=99.0),
                    held=True, last_close=10.0)
    assert r["flip_price"] == 9.8, "多头侧盯的是「跌破就转空」那条"
    r = ft.evaluate(_steps(["DT", "DT"], flip_down=1.0, flip_up=10.2),
                    held=False, last_close=10.0)
    assert r["flip_price"] == 10.2, "空头侧盯的是「站上就转多」那条"


def test_R329_没有触发价就不报_不自己算一条():
    assert ft.evaluate(_steps(["UT", "UT"]), held=True, last_close=10.0) is None


def test_R329_离得远的不进名单():
    """离 20% 的票天天在名单里, 等于没有名单。

    [R338] 这条闸**只管没拿着的票** —— 手上拿着的那一侧另有守卫
    (`test_R338_手上的票离触发价再远也要报`), 两条各管各的, 不重叠。
    """
    r = ft.evaluate(_steps(["UT", "UT"], flip_down=8.0), held=False, last_close=10.0)
    assert r is None
    near = ft.evaluate(_steps(["UT", "UT"], flip_down=9.8), held=False, last_close=10.0)
    assert near is not None and near["stage"] == ft.STAGE_WATCH


# ── 实时 ────────────────────────────────────────────────────────────────
def test_R329_实时没开时不出现盘中越线这一档():
    """收盘价越了线却没 flipped —— 状态机自有道理, 不替它下结论。"""
    r = ft.evaluate(_steps(["UT", "UT"], flip_down=9.5), held=True, last_close=9.4)
    assert r is None, "已落盘的价越线但没转折, 这种不报"


def test_R329_实时开着才标_live():
    live = ft.evaluate(_steps(["UT", "UT"], flip_down=9.5), held=True,
                       last_close=10.0, live_close=9.4)
    assert live["stage"] == ft.STAGE_CROSSING and live["live"] is True
    off = ft.evaluate(_steps(["UT", "UT"], flip_down=9.8), held=True, last_close=10.0)
    assert off["live"] is False, "实时没开就得标出来, 别让人以为是现价"


def test_R329_已转折那一档与实时无关():
    """① 是拿已落盘的日 K 算的 —— 实时开没开都是同一个结论。"""
    a = ft.evaluate(_steps(["DT", "UT"]), held=False, last_close=10.0)
    b = ft.evaluate(_steps(["DT", "UT"]), held=False, last_close=10.0, live_close=7.0)
    assert a["act"] == b["act"] == ft.ACT_BUY
    assert a["live"] is False and b["live"] is False


def test_R329_距离按现价算_实时开着时用的是现价():
    r = ft.evaluate(_steps(["UT", "UT"], flip_down=9.8), held=True,
                    last_close=20.0, live_close=10.0)
    assert r["ref_price"] == 10.0, "实时开着就该拿现价比, 不是昨收"
    assert r["gap_pct"] == pytest.approx((9.8 - 10.0) / 10.0)


def test_R329_多空判据来自_flip_trades_不自己造():
    from tests.py_source import code_of
    code = code_of(ft)
    assert "trend_days(steps)" in code
    assert "BULLISH" not in code, "多空归属不许在这里重写一遍"


def test_R329_没数据时返回_None_不编一个():
    assert ft.evaluate([], held=False, last_close=10.0) is None
    assert ft.evaluate(_steps(["UT", "UT"], flip_down=9.8), held=True, last_close=None) is None


# ── 接线与界面 ──────────────────────────────────────────────────────────
def test_R329_取数层按急迫程度排序_能出手的在最前():
    from app.services import flip_portfolio_run as run_mod
    series = {
        "W": {"steps": _steps(["UT", "UT"], flip_down=9.9), "closes": [10.0, 10.0]},
        "F": {"steps": _steps(["DT", "UT"]), "closes": [10.0, 10.0]},
        "C": {"steps": _steps(["UT", "UT"], flip_down=9.5), "closes": [10.0, 10.0]},
    }

    class _R:
        def get_watchlist_live(self, asset):
            import polars as pl
            return pl.DataFrame({"symbol": ["C"], "date": ["2026-01-02"], "close": [9.4]})

    out = run_mod._today_signals(_R(), series, [], {s: s for s in series})
    assert [r["stage"] for r in out] == ["flipped", "crossing", "watch"], \
        "能出手的必须排最前 —— 版面顺序就是急迫程度"
    assert out[0]["act"] == "buy"
    assert out[1]["act"] is None and out[2]["act"] is None


def test_R329_持仓取自模拟盘自己的账_不是真钱持仓():
    from tests.py_source import body_of
    from app.services import flip_portfolio_run as run_mod
    code = body_of(run_mod._today_signals)
    # `ast.unparse` 会把引号规范化成单引号 —— 断言不该对引号敏感
    assert "held = {p['symbol'] for p in positions}" in code.replace('"', "'"), \
        "持仓必须来自传进来的模拟盘持仓, 不许另去读真实持仓"
    for bad in ("effective_positions", "positions.load", "watchlist_positions"):
        assert bad not in code, f"混进真钱持仓就成了另一个问题的答案: {bad}"


def test_R329_界面上后两档不渲染动作位():
    """**不是灰掉, 是根本不渲染** —— 灰掉的徽标仍在暗示这里本来有个动作。"""
    blk = _signal_row()
    assert "const actionable = r.stage === 'flipped' && !!r.act" in blk, \
        "能不能动手只由这一条决定"
    assert "actionable ? (" in blk
    # 动作徽标(买入/清仓)必须在 actionable 那一支里。
    #
    # **钉的是徽标那个三元, 不是"清仓"这两个字。** [R338] 之后另一支里有一句
    # 「离清仓线还有 N%」—— 那是在说距离, 不是一个可点的动作; 拿裸字符串去扫
    # 会把它误判成"动作词漏进来了", 于是逼着把话说得不像人话。区分办法是**带
    # 引号的字面量**: 徽标里的 `'清仓'` 是 JS 字符串, 正文里的清仓是 JSX 文本。
    badge = "r.act === 'buy' ? '买入' : '清仓'"
    head = blk[:blk.index(") : (")]
    assert badge in head, "动作徽标必须长在 actionable 这一支里"
    tail = blk[blk.index(") : ("):]
    assert badge not in tail, "另一支里不许出现动作徽标"
    assert "'买入'" not in tail and "'清仓'" not in tail, \
        "另一支里不许出现动作词的字面量(正文里说距离可以, 渲染成动作不行)"


def test_R329_今日信号排在页面最前():
    from tests.frontend_source import code_of
    code = code_of("pages/FlipPaper.tsx")
    body = code[code.index("{d && !d.reason && ("):]
    i_today = body.index("<TodaySignals")
    i_summary = body.index("<Summary")
    assert i_today < i_summary, "今天要动手的东西必须排在回测结论前面"


# ── [R331] 折叠 ────────────────────────────────────────────────────────
def _page() -> str:
    from tests.frontend_source import code_of
    return code_of("pages/FlipPaper.tsx")


def _flip_src() -> str:
    from tests.frontend_source import read_src
    return read_src("pages/FlipPaper.tsx")


def _signal_row() -> str:
    """`SignalRow` 的函数体。

    **不按 `"\\n}"` 截。** 剥注释后, 跨行的 `{/* … */}` 收尾会留下一个裸 `}`,
    于是函数在中间被截断, 后半段的断言全部落空**却照样是绿的** —— 这个仓库里
    「断言被自己的注释喂饱」已经是第六次, 这次换了个马甲: 注释不是喂饱断言,
    是把断言要看的那段**整个切掉了**。改成截到下一个顶层 `function`。
    """
    code = _page()
    blk = code[code.index("function SignalRow"):]
    nxt = blk.find("\nfunction ", 1)
    return blk if nxt < 0 else blk[:nxt]


def _today_block() -> str:
    code = _page()
    blk = code[code.index("function TodaySignals"):]
    return blk[:blk.index("function SignalRow")]


def test_R331_要动手的永远不进折叠区():
    """**折叠是为了让信号更显眼, 把信号自己折起来就本末倒置了。**"""
    blk = _today_block()
    # [R338] 判据收成了一个 isLive, 常驻/折叠都建立在它之上 —— 论点没变,
    # 反而更强: 以前是正反各写一遍, 现在正反同源, 想漂都漂不了。
    pred = next(l for l in blk.splitlines() if "const isLive =" in l)
    assert "r.stage === 'flipped' && !!r.act" in pred, "要动手的必须进常驻区"
    assert "const rest = rows.filter((r) => !isLive(r))" in blk, \
        "折叠那一侧必须是常驻区的补集 —— 两套各写一份判据必然漂"
    # 常驻区渲染在折叠开关**之前**, 且不受 watchOpen 控制
    # [R342] 常驻区渲染的是排过序的 `ordered`(只重排不增删), 锚跟着走
    i_live = blk.index("{ordered.map((r) => <SignalRow")
    i_toggle = blk.index("onClick={toggleWatch}")
    assert i_live < i_toggle
    head = blk[:i_toggle]
    assert "watchOpen &&" not in head, "常驻区不许被折叠状态控制"


def test_R331_盘中越线也常驻_它今天就可能成交():
    blk = _today_block()
    pred = next(l for l in blk.splitlines() if "const isLive =" in l)
    assert "r.stage === 'crossing'" in pred, (
        "盘中越线收盘还站着就成交 —— 今天就要盯, 不该被折起来")


def test_R331_折叠状态记在本地_刷新后还在():
    blk = _today_block()
    assert "storage.flipTodayWatchOpen.get(false)" in blk, "默认收起"
    assert "storage.flipTodayWatchOpen.set(!v)" in blk, "改了要落盘, 否则刷新就忘"


def test_R331_展开区限高自己滚():
    """盯着的票可能几十只 —— 让它把整页顶长等于没折叠。"""
    blk = _today_block()
    open_blk = blk[blk.index("{watchOpen && ("):]
    assert "max-h-64" in open_blk and "overflow-y-auto" in open_blk


def test_R331_没有要动手的时候明说_不是留一片空白():
    blk = _today_block()
    assert "{ordered.length === 0 && (" in blk
    assert "管住手" in blk, "空着不说话, 读的人分不清是没有还是没算出来"


def test_R331_折叠按钮报出条数():
    blk = _today_block()
    assert "{idle.length} 只" in blk, "不写条数的话, 用户不知道展开会看到什么"


# ── [R332] 注重当下 ────────────────────────────────────────────────────
def test_R332_近期读数排在长期成绩之前():
    """用户每天打开最先要问的是「我最近做得怎么样」, 不是两年总收益。"""
    blk = _page()
    blk = blk[blk.index("function Summary({ d }"):blk.index("function Stat({ label")]
    i_now = blk.index("label=\"近一月\"")
    i_long = blk.index("label=\"总收益\"")
    assert i_now < i_long, "当下那一排必须排在长期那一排前面"
    for k in ("近一月", "近三月", "现在拿着", "最后一天"):
        assert k in blk, f"当下那一排少了「{k}」"


def test_R332_近期收益是同一条曲线切一段_不另跑一次回测():
    blk = _page()
    assert "function windowRet(nav" in blk
    fn = blk[blk.index("function windowRet(nav"):blk.index("function Summary({ d }")]
    assert "nav[nav.length - 1].nav / base - 1" in fn
    assert "api." not in fn and "useQuery" not in fn, "不许为这两格另打一次接口"
    # 起点取窗口第一天的**前一天** —— 否则会把那天自己的涨跌吃掉
    assert "nav.length - 1 - days" in fn


def test_R332_天数不够时空着_不拿全程凑数():
    blk = _page()
    sm = blk[blk.index("function Summary({ d }"):blk.index("function Stat({ label")]
    assert "enough >= 21 ? pct(m1) : '—'" in sm
    assert "enough >= 61 ? pct(m3) : '—'" in sm
    assert "不够一个月" in sm and "不够三个月" in sm, (
        "空栏必须自己解释 —— 「算不出来」与「没赚到」是两件事")


def test_R339_回溯档位_最长三年_带短周期():
    """**这条是 R332 那条守卫的替代品, 不是它的延续。**

    R332 我写的是「回溯参数没被动过 —— 它给的是样本量, 不该为了看当下砍短」。
    论点本身没错, 但它**替用户做了决定**; R339 用户当面推翻:「回溯时间太长了,
    只看近三年和短周期」。所以守卫改成钉新口径, 而"样本量不够"那件事改由**界面
    自己说**(轮数少于 10 时胜率标黄), 不再靠一条测试替他拦着。
    """
    blk = _page()
    assert "const YEAR_OPTIONS = [0.5, 1, 2, 3]" in blk, "最长三年, 且要有短周期档"
    assert "5]" not in blk.split("YEAR_OPTIONS")[1][:40], "5 年那一档已经砍掉"
    # 「0.5 年」没人这么讲话
    assert "const fmtYears = (v: number) => (v < 1 ? `${Math.round(v * 12)} 个月`" in blk
    assert "fmt={fmtYears}" in blk, "选择器必须用这个写法, 不许各写一份"


def test_R339_后端接受半年():
    """前端给得出来、后端收不下, 就是个下拉框点了没反应。

    **不用 `inspect.signature(...).annotation` 比对** —— 这两个模块都开了
    `from __future__ import annotations`, 注解全是字符串, `is float` 永远为假
    (写第一版时就这么翻了车); 要拿 `get_type_hints` 真解出来才算数。
    """
    from typing import get_type_hints

    from app.api import flip_paper
    from app.services import flip_portfolio_run as run_mod

    assert flip_paper.MIN_YEARS <= 0.5, "下限没放开, 半年会被 422 拒掉"
    for fn in (flip_paper.get_flip_paper, run_mod.run, run_mod._load_batch):
        assert get_type_hints(fn)["years"] is float, \
            f"{fn.__name__} 的 years 还是 int —— 半年会被截断或拒掉"


def test_R339_取数窗口按小数年算得通():
    """`years` 只被拿去算取多少天日线 —— 小数必须一路算得通, 不许中途退化成整数。"""
    from app.services import flip_portfolio_run as run_mod

    seen: dict = {}

    class _Repo:
        def resolve_asset_type(self, sym): return "stock"
        def get_daily_batch(self, syms, start, end, columns):
            seen["span"] = (end - start).days
            import polars as pl
            return pl.DataFrame()
        def get_daily_asset(self, *a, **k):
            import polars as pl
            return pl.DataFrame()

    run_mod._load_batch(_Repo(), ["A"], 0.5)
    half = seen["span"]
    run_mod._load_batch(_Repo(), ["A"], 3)
    three = seen["span"]
    assert half < three, "半年取的天数必须真的比三年少"
    # 半年 ≈ 125 交易日 + 60 根热身, 换算成日历日再加 30 —— 别退化成"按 0 年算"
    assert half > 300, f"半年窗口只取了 {half} 天, 小数大概率在半路被截成 0"


def test_R332_净值图默认框最近一段_但整段拖得回去():
    blk = _page()
    fn = blk[blk.index("function NavChart({ d }"):blk.index("function Holdings({ d")]
    assert "dataZoom" in fn, "没有 dataZoom 就回不到全程"
    assert "total > 120 ? ((total - 120) / total) * 100 : 0" in fn, \
        "不足 120 天时该显示整段, 不是硬砍"
    assert "type: 'slider' as const" in fn, "只有 inside 的话用户不知道可以拖"
    assert "d.nav.map((p) => p.nav)" in fn, "曲线本身仍是整段数据, 只是视野落在当下"


# ── [R338] 有买入就要有卖出 ─────────────────────────────────────────────
#
# 用户看着一屏 6 个「买入」、0 个「卖出」说: 「有买入就要有卖出」。
#
# **判据没坏** —— 转空要卖的分支一直在, 上面 `test_R329_三个空头态转入都算卖`
# 一直是绿的。坏的是**版面让卖出没有位置**:
#
#   · 买入的候选是全部自选(几十上百只), 卖出的候选只有手上那几只 —— 天生不对等;
#   · 手上那几只**离卖出线还有多远**, 被 WATCH_WITHIN 那道 5% 的闸挡掉了整行,
#     挡不掉的又被折进「只是盯着」, 跟几十只不相干的票混在一起, 行上连"我拿着
#     这只"都不标。
#
# 于是卖出只在真触发的那一天冒出来一次, 其余每天看上去都只有买入。
# 这一组守卫钉的就是"卖出这一侧天天有位置"。


def test_R338_手上的票离触发价再远也要报():
    """**这条直接钉用户报的症状。** 拿着的票, 离场线不该因为"还远"就整行消失。"""
    far = _steps(["UT", "UT"], flip_down=5.0)   # 现价 10 → 离清仓线 50%, 远得很
    r = ft.evaluate(far, held=True, last_close=10.0)
    assert r is not None, "手上拿着的票, 卖出线任何时候都要看得见"
    assert r["stage"] == ft.STAGE_WATCH
    assert r["flip_price"] == 5.0, "报的必须是卖出那条线"


def test_R338_没拿着的票那道闸还在():
    """闸是为了"不相干的票别刷屏" —— 不许借这次改动把它顺手拆了。"""
    far = _steps(["DT", "DT"], flip_up=20.0)    # 现价 10 → 离买入线 100%
    assert ft.evaluate(far, held=False, last_close=10.0) is None, \
        "没拿着又离得远的票进名单, 等于没有名单"


def test_R338_手上这段仍然不许出手():
    """**铁律不因为多了一段版面而松动。** 没转折就没有动作, 拿着也一样。"""
    for gap_price in (5.0, 9.9):               # 远的、近的都来一遍
        r = ft.evaluate(_steps(["UT", "UT"], flip_down=gap_price),
                        held=True, last_close=10.0)
        assert r is not None and r["act"] is None, "没转折就不许出手"


def test_R338_每行都带held_否则前端分不开():
    """前端只能按返回值分段。不带 `held`, 「我拿着的」和「不相干的」就是一堆。"""
    from tests.py_source import body_of
    from app.services import flip_portfolio_run as run_mod
    code = body_of(run_mod._today_signals).replace('"', "'")
    assert "'held': is_held" in code, "每行必须带上 held"
    assert "held=is_held" in code, "判定用的和报出去的必须是同一个值, 不许各算一遍"


def test_R338_手上这段常驻_不进折叠区():
    """买入天天在最上面, 卖出这一侧也必须天天有位置 —— 折起来就等于没有。"""
    blk = _today_block()
    assert "const mine = rest.filter((r) => r.held)" in blk
    assert "const idle = rest.filter((r) => !r.held)" in blk
    # 折叠开关只作用在 idle 上; mine 那一段渲染时不许跟 watchOpen 沾边
    seg = blk[blk.index("{mine.length > 0 && ("):blk.index("{idle.length > 0 && (")]
    assert "watchOpen" not in seg, "手上这段一旦能被折起来, 就又回到只剩买入"
    assert "mineSorted.map((r) => <SignalRow" in seg


def test_R338_三段分流只由一个判据说了算():
    """正着写一遍反着再写一遍, 改一边漏一边 —— 而且不报错。"""
    blk = _today_block()
    assert "const isLive = (r: FlipTodaySignal) =>" in blk, "常驻的判据只准有一处"
    assert "const live = rows.filter(isLive)" in blk
    assert "const rest = rows.filter((r) => !isLive(r))" in blk, \
        "另外两段必须建立在 isLive 的补集上, 不许另写一份条件"


def test_R338_持有与盯着在界面上分得开():
    """"我拿着它"与"我在看它"是两件事, 一眼要能分开。"""
    blk = _signal_row()
    assert "r.held ? (" in blk and "持有" in blk
    assert "离清仓线还有" in blk, "拿着的票问的是什么时候卖, 不是什么时候买"


# ── [R339] 卖出要醒目 ───────────────────────────────────────────────────
#
# 用户: 「卖出也要上色, 这样看起来醒目」。在这之前**买和卖共用同一个灰蓝底**
# (`bg-accent/[0.06]`) —— 徽标是分了红绿, 但一行里最先被看见的是整条底色,
# 而底色对买和卖说的是同一句话。


def test_R339_买和卖不许共用一个底色():
    """一行里最先被看见的是底色, 不是徽标上那两个字。"""
    blk = _signal_row()
    assert "bg-accent/[0.06]" not in blk, "买卖共用一个底色 = 扫一眼分不出今天是买是卖"
    assert "buy && 'border-l-bull bg-bull/[0.07]'" in blk
    assert "sell && 'border-l-bear bg-bear/[0.10]'" in blk
    # 方向是从 act 来的, 不许另立一套
    assert "const sell = actionable && r.act === 'sell'" in blk
    assert "const buy = actionable && r.act === 'buy'" in blk


def test_R339_贴着清仓线的持仓也上色():
    """卖出这一侧该醒目的不只是「今天要卖」, 还有「明后天很可能要卖」。"""
    blk = _signal_row()
    assert "const NEAR_EXIT = 0.02" in _page()
    assert "Math.abs(r.gap_pct) <= NEAR_EXIT" in blk
    assert "nearExit && 'border-l-warning bg-warning/[0.07]'" in blk
    # 只有**拿着的**才吃这一档 —— 不相干的票离它的买入线近, 与"要卖"无关
    assert "r.held && r.gap_pct != null" in blk


def test_R339_上色不是出手理由():
    """**铁律。** 上了色照样不许长出动作徽标 —— 颜色是提醒, 不是信号。"""
    blk = _signal_row()
    # nearExit 必须建立在「不是 actionable」之上; 它一旦能独立成立就是新出手口径
    assert "const nearExit = !actionable && r.held" in blk
    badge = "r.act === 'buy' ? '买入' : '清仓'"
    tail = blk[blk.index(") : ("):]
    assert badge not in tail, "上色那一支里不许出现动作徽标"


def test_R339_样本量不够时胜率自己说出来():
    """**禁止造假。** 窗口能选到半年了, 3 轮算出来的 67% 不是"不好看", 是不成立。"""
    blk = _page()
    sm = blk[blk.index("function Summary({ d }"):blk.index("function Stat({ label")]
    assert "s.round_trips > 0 && s.round_trips < 10 ? 'warn' : undefined" in sm, \
        "轮数少必须标出来 —— 一个光秃秃的百分比读的人不会自己去想它背后有几轮"
    assert "样本太少不当数" in sm
    st = blk[blk.index("function Stat({ label"):]
    assert "tone === 'warn' && 'text-warning'" in st, "warn 这一档得真有颜色"


# ── [R342] 把握分排序 ───────────────────────────────────────────────────
#
# 用户: 「值得关注应用了评分系统的, 拿今天动手是否可以排个序?」
#
# **界线必须说死**:
#     谁能出手 —— 只看六态转折。一分不看, 一票不多, 一票不少。
#     先做哪个 —— 用打分排。
#
# 第二件在这之前根本没人回答: 后端那句 `out.sort(...)` 末位键是 `r["symbol"]`,
# 而已转折那一档 `gap_pct` 恒为 None, 于是 6 笔买入的先后**实际是按代码字母序**。


def test_R342_排序只重排不增删():
    """**这一条是整组的地基。** 分是用来排先后的, 不是用来筛名单的。"""
    blk = _today_block()
    # [R344] 排序收成一个 `byRank`, 四档共用 —— 各写一遍必然漂
    assert "const ordered = byRank(live)" in blk, "排序的输入是 live 本身"
    assert "live.filter" not in blk.split("const ordered")[1].split("\n")[0], \
        "不许在排序那一行顺手过滤"
    # 没进候选池的排末尾, 但仍在名单里
    assert "?? Number.MAX_SAFE_INTEGER" in blk, \
        "拿不到名次的票必须排末尾而不是被丢掉"


def test_R342_分不参与能不能动手():
    """**铁律。** 把握分只碰顺序, 不许碰 `isLive` 那个判据。"""
    blk = _today_block()
    pred = next(l for l in blk.splitlines() if "const isLive =" in l)
    for word in ("conviction", "rank", "score", "把握"):
        assert word not in pred, f"出手判据里混进了打分: {word}"
    # [R344] 打分现在对四档都生效了, 这条界线因此更要紧: 它只管档内先后, 不管分档
    assert "const mine = rest.filter((r) => r.held)" in blk, "分档判据被动过"


def test_R342_slice先拷一份_不就地改props():
    """`sort` 是就地改。直接对 filter 的产物排没事, 但对 props 数组排会改到上游。"""
    blk = _today_block()
    line = next(l for l in blk.splitlines() if "const byRank" in l)
    assert ".slice().sort(" in line, "少了 slice() —— sort 会就地改"


def test_R342_排序依据摆在界面上_不做暗箱():
    """顺序是谁排的不说, 读的人不知道该不该照着做。"""
    blk = _today_block()
    assert "'按把握分排序'" in blk, "页头没说这个顺序是按什么排的"
    row = _signal_row()
    # [R345] 行上那个徽标换成了整格移植过来的 `ScoreCell`(名次 + 分 + 三条维度条)
    assert "<ScoreCell o={c} rank={c.rank}" in row, "行上要看得见名次 —— 排序依据不做暗箱"
    assert "它**不是动作**" in _flip_src(), "必须写明分不是出手依据"


def test_R342_没进候选池的票照样在名单里():
    """转折了就是转折了 —— 打分够不够是另一个问题, 不该让它从名单上消失。"""
    row = _signal_row()
    assert "候选池" in row
    assert "该动手还是要动手" in row, "得说清它为什么没名次, 以及这不影响动手"


def test_R342_把握分那一格不是动作():
    """名次徽标长在动作徽标旁边, **不许变成第二个可点的动作**。"""
    row = _signal_row()
    # [R350] 版面改成网格后, 原来那个右界(状态文字那个 span 的 className)变了。
    # 改用**这个三元自己的收尾**当右界 —— 它跟着这一格走, 不跟旁边的样式走。
    a = row.index("{c?.rank != null ? (")
    seg = row[a:row.index(") : <span />}", a)]
    for word in ("'买入'", "'清仓'", "onClick"):
        assert word not in seg, f"名次那一格出现了动作: {word}"
    # [R345] 移植过来的那一格本身也不许带动作
    from tests.frontend_source import code_of
    cell = code_of("components/today/ScoreCell.tsx")
    for word in ("'买入'", "'清仓'", "onClick"):
        assert word not in cell, f"ScoreCell 里出现了动作: {word}"
