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


def test_R329_今日信号排在主列第一块():
    """[R329 → **R358 缩水**] 原来钉的是「今天要动手的东西排在回测结论前面」。

    **那一半被用户当面推翻了, 不是被我绕过去。** R358 用户: 「净值走势图和这两行
    收益都融合到页面开头的第一个卡片里面」, 追问后明确是「我是想合并到筛选的卡片
    里面」—— 而筛选那张卡本来就在今日信号**上面**。所以现在成绩确实排在了今天
    要动手的东西前面, 这是用户点的名。

    剩下这一半仍然成立而且仍然要钉: 今日信号是**主列的第一块**, 持仓 / 成交 /
    没做成 / 规则都排在它后面。成绩并进了页头那张控制卡, 不占主列的位置。
    """
    from tests.frontend_source import code_of
    code = code_of("pages/FlipPaper.tsx")
    body = code[code.index("{d && !d.reason && ("):]
    i_today = body.index("<TodaySignals")
    for later in ("<Holdings", "<Orders", "<Skipped"):
        assert i_today < body.index(later), f"今日信号被 {later} 挤到后面去了"


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


# ── [R332 → R357] 注重当下: 从滚动窗口改成逐月 ──────────────────────────
#
# 用户: 「最好是每个月的收益单独计算, 也不需要回溯那么多, 没多大意义,
# 极少我手动去选择的时候看长期」。
#
# **R332 那三条守卫退役, 但它们的立论有两条原样搬了过来**:
#   ① 当下那一块排在整段成绩之前(用户每天打开先问「最近怎么样」)
#   ② 不为它另打一次接口
# 退役掉的是第三条「天数不够就空着」—— 滚动窗口凑不满 20/60 天才需要空着,
# 而自然月天然有长有短, 对应的问题变成了「这个月是不是残月」, 见下面那条。


def test_R357_逐月排在整段成绩之前():
    """用户每天打开最先要问的是「最近哪个月在亏」, 不是整段总收益。"""
    blk = _page()
    sm = blk[blk.index("function Summary({ d }"):blk.index("function Stat({ label")]
    assert sm.strip()
    assert sm.index("<MonthStrip months={d.monthly} />") < sm.index('label="总收益"'), \
        "逐月那一条必须排在整段成绩前面"


def test_R357_逐月的数来自后端_前端不自己再切一遍():
    """[R332 立论照搬] 不另打一次接口; **另加一条**: 也不另算一遍。

    基准取上月末、首尾标残月 —— 这两条口径在 `flip_portfolio._monthly` 里,
    有守卫钉着。前端再实现一份的话, 哪天基准口径改了必然漂, 而且**不会有任何
    东西报错**(AGENTS.md 规则 12)。
    """
    blk = _page()
    strip = blk[blk.index("function MonthStrip({ months }"):blk.index("function Summary({ d }")]
    assert strip.strip()
    assert "api." not in strip and "useQuery" not in strip, "不许为这一条另打一次接口"
    for math in ("/ base - 1", ".slice(0, 7)", "getMonth()"):
        assert math not in strip, f"前端自己又切了一遍曲线: {math}"
    # R332 那个滚动窗口的实现整个没了 —— 不是留着不用
    assert "function windowRet" not in blk, "滚动窗口那份实现还留着"
    assert "近一月" not in blk and "近三月" not in blk, "重叠的那两格还在"


def test_R357_残月要标出来():
    """**空栏必须自己解释**这条纪律换了个对象: 残月不该拿去和整月比。

    回测窗口的起点是「今天 - N 天」, 落在月中是常态; 最后一个月还没走完。
    一个半月的 +2% 和整月的 +2% 并排摆着, 不标就是在骗人。
    """
    blk = _page()
    strip = blk[blk.index("function MonthStrip({ months }"):blk.index("function Summary({ d }")]
    assert strip.strip()
    # **标记必须看得见, 不能只在 tooltip 里。**
    #
    # 第一版写的是 `assert "m.partial" in strip and "残月" in strip` —— 变异电池
    # 当场打绿: 把那个 ✕ 徽标整个删掉, `m.partial` 仍然在几个 `opacity-60` 的
    # 类名里、「残月」仍然在 `title` 与那段 Hint 里, 断言被它们喂饱, 而**屏幕上
    # 已经没有任何东西**告诉人这是残月了(得悬停才知道)。锚太宽 = 没有锚, 第八次。
    #
    # 改钉结构: `m.partial` 必须**条件渲染出一个元素**(`&& <`), 而不只是换个
    # 类名 —— 后者只是淡一点, 淡一点不等于说清楚了。
    cell = strip[strip.index("months.map((m) =>"):]
    assert cell.strip()
    assert "{m.partial && <" in cell, \
        "残月只剩淡化或 tooltip —— 不悬停就看不见它是残月"
    assert "残月" in cell, "没有一处用人话说出「残月」"
    assert "m.days" in strip, "没说这个月到底有几个交易日"
    # 数字与柱子也跟着淡下去 —— 徽标说明"它是残月", 淡化让它在一排里**不抢眼**,
    # 两件事都做才算"不拿它去和整月比"。涨跌两根柱子各一处。
    assert cell.count("m.partial && 'opacity-50'") == 2, "残月的柱子没淡化"


def test_R357_柱高按最大月度波动归一_不是固定刻度():
    """一个 ±2% 的年份, 拿固定刻度画会所有柱子都贴着底, 什么也看不出来。"""
    blk = _page()
    strip = blk[blk.index("function MonthStrip({ months }"):blk.index("function Summary({ d }")]
    assert strip.strip()
    assert "Math.max(...months.map((m) => Math.abs(m.ret))" in strip, "没有归一"
    # **涨的那根和跌的那根都得按同一个 peak 量。** 只断言「出现过一次 peak」的话,
    # 把其中一根改成固定刻度守卫照样绿 —— 而那比两根都固定还糟: 上下两半不同尺,
    # 一个 +3% 的柱子可能画得比 -8% 的还高。变异电池打绿过一次。
    assert strip.count("/ peak) * 100") == 2, \
        "涨跌两根柱子必须按同一个 peak 量, 少一根就是上下两半不同尺"


def test_R357_收上限之后存着的旧值要钳一道():
    """**输入框的 max 救不了它。**

    上限从 10 收到 3, 而 R353 把回溯落了 localStorage —— 之前填过 5 年的人存里
    躺着一个 5, 打开页面直接送进 queryKey, 换回一个 422。输入框那道钳位只在
    人去改那个框时才发生, 而这个人根本没打算改它。
    """
    blk = _page()
    assert "function clampYears" in blk, "读出来没钳"
    assert "clampYears(storage.flipYears.get(" in blk, \
        "钳位没接在读出来的那一刻 —— 那就等于没钳"
    # **函数体也要钉。** 只钉"有这个函数、也调了"的话, 把里面掏空成 `return n`
    # 守卫照样绿 —— 一个只有壳子的钳位函数, 比没有更坏: 它看上去已经处理过了。
    fn = blk[blk.index("function clampYears"):]
    fn = fn[:fn.index("\n}\n")]
    assert "Math.min(YEARS_MAX, Math.max(YEARS_MIN, n))" in fn, "钳位只剩个壳子"
    assert "return YEARS_DEFAULT" in fn, "填了非数字时没有退路, 会把 NaN 送进 queryKey"


def test_R357_默认回溯一年_正好十二个月格():
    from app.services import flip_portfolio_run
    assert flip_portfolio_run.DEFAULT_YEARS == 1
    blk = _page()
    assert "const YEARS_DEFAULT = 1" in blk
    assert "clampYears(storage.flipYears.get(YEARS_DEFAULT))" in blk, \
        "前端默认值与后端 DEFAULT_YEARS 对不上"


def test_R353_三个参数都能自己填_不是档位():
    """[R339 → R353] 用户: 「这里我要能配置而不是选择或者默认」。

    **档位这个概念取消了。** R339 我把它砍成「半年/1/2/3 年」四档并为此写了守卫;
    这次用户要的是直接填 —— 于是边界改由输入框的 `min`/`max` 表达, 与后端对齐,
    而不是由一份我挑的清单表达。

    R339 那条论证(窗口短了样本量不成立)**仍然成立, 而且更要紧** —— 既然现在能
    填任意值, 那句话更得让人看见: 完整买卖少于 10 轮时胜率标黄并写明, 见 `Summary`,
    由 `test_R339_样本量不够时胜率自己说出来` 守着。
    """
    blk = _page()
    assert "const YEAR_OPTIONS" not in blk and "const CAPITAL_OPTIONS" not in blk \
        and "const POSITION_OPTIONS" not in blk, "还留着写死的档位清单"
    assert "<select" not in blk, "还在用下拉选择"
    for field in ('<NumberField label="本金"', '<NumberField label="最多持有"',
                  '<NumberField label="回溯"'):
        assert field in blk, f"这一项没改成可输入: {field}"


def test_R354_数字输入框不许被喂格式化过的字符串():
    """**这一条直接钉用户报的那个空框。**

    第一版给 `NumberField` 开了个 `fmt` 钩子, 本金那格传的是千分位的 `money()` ——
    于是 `value` 收到 `"1,000,000"`, 而 **`<input type="number">` 认不了带逗号的
    字符串, 直接渲染成一个空框**。值一直在(查询照常按 100 万跑), 只是**看上去
    像没填** —— tsc 与 eslint 都不会说一个字。

    教训不是"把逗号去掉"而是**别给数字输入框留格式化的口子**: 数字要好读就换单位,
    不是往框里塞排版。
    """
    blk = _page()
    fn = blk[blk.index("function NumberField"):]
    fn = fn[:fn.index("\n}\n")]
    assert "value={draft ?? String(value)}" in fn, "value 必须是原始数字的字符串"
    assert "fmt" not in fn, "又给数字输入框开了格式化的口子"
    assert "money(" not in fn, "千分位函数不许出现在数字输入框里"


def test_R354_本金以万计_对得上真实量级():
    """用户: 「我实际本金不超 100 万, 要合适我真实情况」。

    按元填的话 100 万写成 `1000000` —— 七位数在一个小框里既难读也难改, 而上限
    原来给到 1 亿, 与真实量级差两个数量级。
    """
    blk = _page()
    assert 'suffix="万"' in blk, "本金那格没标单位"
    assert "min={1} max={1000} step={5}" in blk, "区间/步进没对上散户的量级"
    # 换算只在这一处, 存的与送后端的仍然是元
    assert "value={Math.round(capital / 10_000)}" in blk
    assert "onChange={(v) => putCapital(v * 10_000)}" in blk
    assert "max={100_000_000}" not in blk, "1 亿那个上限还在"


def test_R353_边界与后端逐个对齐():
    """前端钳到同一个区间, **不是等后端 422** —— 那种报错只会说
    「Input should be less than or equal to 50」, 读的人不知道该填多少。"""
    blk = _page()
    assert "min={1} max={50}" in blk, "最多持有的上界要对上 MAX_POSITIONS_CAP"
    # [R357] 回溯的两个界改走常量, 不再是字面量 —— 因为**同一对数字现在有三处
    # 要对上**: 输入框、`clampYears`、后端。写死在输入框上时, 改了后端而漏改
    # 前端只会在用户填到边界那天才暴露。
    assert "min={YEARS_MIN} max={YEARS_MAX}" in blk, "回溯的上下界没走常量"
    assert "const YEARS_MIN = 0.5" in blk and "const YEARS_MAX = 3" in blk

    from app.api import flip_paper
    from app.services import flip_portfolio
    assert flip_portfolio.MAX_POSITIONS_CAP == 50
    assert flip_paper.MIN_YEARS == 0.5 and flip_paper.MAX_YEARS == 3


def test_R353_失焦才提交_不许边敲边跑():
    """**这三个值都进 `queryKey`。** 直接绑 `onChange` 的话, 敲「100000」这七个
    字符会依次触发七次请求 —— 而每次请求是全部自选的六态 + 一整轮回测。
    """
    blk = _page()
    fn = blk[blk.index("function NumberField"):]
    fn = fn[:fn.index("\n}\n")]
    assert "const [draft, setDraft]" in fn, "没有本地草稿 —— 那就是边敲边提交"
    assert "onBlur={commit}" in fn, "失焦要提交"
    assert "if (e.key === 'Enter')" in fn, "回车要提交"
    # onChange 只许写草稿, 不许直接调用方
    onchange = next(l for l in fn.splitlines() if "onChange={(e) =>" in l)
    assert "setDraft(e.target.value)" in onchange and "onChange(" not in onchange.replace("onChange={(e) =>", ""), \
        "onChange 里直接提交了 —— 每敲一个字符跑一次全量回测"


def test_R353_越界钳到边界_而不是报错或清空():
    """「填了 999 只就钳成 50」比弹一句「超出范围」再清空有用得多 ——
    **让人看见它被钳到哪儿**。不是数字就退回当前值, 不留一个空框。"""
    blk = _page()
    fn = blk[blk.index("function NumberField"):]
    fn = fn[:fn.index("\n}\n")]
    assert "Math.min(max, Math.max(min, n))" in fn, "没有钳位"
    assert "if (!Number.isFinite(n)) return" in fn, "填了非数字没有退回当前值"


def test_R353_填过的值要记住():
    """每次打开都退回默认值, 等于没配过。"""
    blk = _page()
    for key in ("storage.flipCapital.get(1_000_000)",
                "storage.flipMaxPositions.get(10)",
                # [R357] 回溯这一个多套了一层 `clampYears` —— 收上限之后存里可能
                # 躺着旧值。钳位不影响"记住"这条: 填过的仍然读得回来。
                "storage.flipYears.get(YEARS_DEFAULT)"):
        assert key in blk, f"没从本地读回: {key}"
    for put in ("storage.flipCapital.set(v)", "storage.flipMaxPositions.set(v)",
                "storage.flipYears.set(v)"):
        assert put in blk, f"改了没落盘: {put}"


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


def test_R355_手上这段可折叠_但折叠条自己就是摘要():
    """[R338 → R355] 用户: 「这部分也想能折叠展开」。

    **R338 我为这一段写过「不许折叠」**, 理由是: 买入天天长出来, 卖出只在真触发
    那天冒一次, 折起来就等于又回到只剩买入。用户当面推翻 —— 那条理由没有错,
    但它不该替用户决定版面。

    所以守卫**不是删掉而是换了个钉法**: 折叠可以, 但**折叠条必须把卖出侧的读数
    带上**(拿着几只 / 其中几只贴到离场线)。收起来之后那一行仍然在说「你手上有
    10 只, 2 只快到线了」—— **那才是 R338 真正要保的东西, 而不是"不许折"**。

    顺带记一笔: R338 那条守卫写的是 `assert "watchOpen" not in seg`, 钉的是
    **某一个变量名**而不是"不可折叠"这条性质 —— 我这次用 `mineOpen` 接上折叠,
    它**照样是绿的**。钉名字不钉性质, 又一次。
    """
    blk = _today_block()
    seg = blk[blk.index("{mine.length > 0 && ("):blk.index("{idle.length > 0 && (")]
    assert "onClick={toggleMine}" in seg, "没有折叠开关"
    assert "{mineOpen && (" in seg, "展开区没受开关控制"
    # **折叠条上必须有这两个数** —— 收起来之后卖出侧全靠它们
    assert "{mine.length} 只" in seg, "折叠条上没说拿着几只"
    assert "{mineNear} 只贴近离场线" in seg, "折叠条上没说几只快到线了 —— 收起来卖出侧就消失了"
    assert "mineSorted.map((r) => <SignalRow" in seg


def test_R355_默认展开_且状态记住():
    """它是卖出那一侧唯一天天有位置的东西, 默认收起等于把 R338 做的事撤回去。"""
    blk = _today_block()
    assert "storage.flipMineOpen.get(true)" in blk, "默认要展开"
    assert "storage.flipMineOpen.set(!v)" in blk, "改了要落盘, 否则刷新就忘"


def test_R355_贴近离场线的判据只有一处():
    """条上说 2 只、展开却只有 1 行标黄 —— 两处各写一份必然这样。"""
    blk = _today_block()
    line = next(l for l in blk.splitlines() if "const mineNear" in l)
    assert "<= NEAR_EXIT" in line, "折叠条上那个计数没走 NEAR_EXIT 那条判据"
    row = _signal_row()
    assert "<= NEAR_EXIT" in row, "行上那一档也得是同一条"


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
