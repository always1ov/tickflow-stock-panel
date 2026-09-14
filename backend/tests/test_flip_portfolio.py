"""[R327] 转折模拟盘 —— 组合层按六态转折买卖。

这套的全部价值在于「可复现、按规则、不掺任何判断」, 所以守卫要钉的不是"跑得动",
而是每一条规则**真的在起作用**:

  · 只在转折日动手, 不转折的日子一动不动
  · 多头侧买、空头侧清, 不做空
  · 当天收盘价成交(不是次日开盘 —— 那是 flip_trades 那条路)
  · 卖在买前
  · T+1
  · 等权按**当日净值**均分(不是本金)
  · 一手 100 股、费用扣对、现金不为负
  · 收盘封板挂不进去 → 顺延, 反向转折就作废
  · 多空判据不自己造, 来自 flip_trades.trend_days
"""
from __future__ import annotations

import pytest

from app.services import flip_portfolio as fp


# ── 造数据: 直接给 state 序列, 让 livermore 的 BULLISH 口径自己去判 ──────
def _mk(states: list[str], closes: list[float], *, name: str = "测试",
        limit_up: list[bool] | None = None, limit_down: list[bool] | None = None,
        dates: list[str] | None = None) -> dict:
    """steps 只放 compute() 真正会给的字段, flipped 按前后 state 自己算。"""
    steps = []
    prev = None
    for st in states:
        steps.append({"state": st, "prev": prev, "flipped": prev != st})
        prev = st
    n = len(states)
    return {
        "name": name,
        "steps": steps,
        "dates": dates or [f"2026-01-{i + 1:02d}" for i in range(n)],
        "closes": closes,
        "limit_up": limit_up or [False] * n,
        "limit_down": limit_down or [False] * n,
    }


def _acts(res: dict, sym: str | None = None) -> list[tuple]:
    return [(o["date"], o["symbol"], o["act"], o["shares"])
            for o in res["orders"] if sym is None or o["symbol"] == sym]


# ── 最基本的一条: 只在转折日动手 ────────────────────────────────────────
def test_R327_只在转折日动手():
    # 第 0 天就是 UT(prev=None → flipped), 之后一路 UT 不再转折
    res = fp.simulate({"A": _mk(["UT"] * 5, [10.0] * 5)}, capital=100_000, max_positions=1)
    assert len(res["orders"]) == 1, "一路不转折, 只该有开头那一笔"
    assert res["orders"][0]["act"] == fp.ACT_BUY


def test_R327_多头侧买空头侧清_不做空():
    # UT(买) → DT(清) → UT(再买)
    states = ["UT", "UT", "DT", "DT", "UT"]
    res = fp.simulate({"A": _mk(states, [10, 11, 9, 8, 9])}, capital=100_000, max_positions=1)
    acts = [o["act"] for o in res["orders"]]
    assert acts == [fp.ACT_BUY, fp.ACT_SELL, fp.ACT_BUY]
    # 空头段一股都不该持有 —— 不做空
    day3 = next(r for r in res["nav"] if r["date"] == "2026-01-04")
    assert day3["positions"] == 0
    assert day3["market_value"] == 0


@pytest.mark.parametrize("state", ["UT", "NR", "SR"])
def test_R327_三个多头态都买(state):
    res = fp.simulate({"A": _mk([state, state], [10, 10])}, capital=100_000, max_positions=1)
    assert [o["act"] for o in res["orders"]] == [fp.ACT_BUY]


@pytest.mark.parametrize("state", ["DT", "NREA", "SREA"])
def test_R327_三个空头态都不买(state):
    res = fp.simulate({"A": _mk([state, state], [10, 10])}, capital=100_000, max_positions=1)
    assert res["orders"] == [], f"{state} 在空头侧, 不该建仓"


# ── 成交价: 当天收盘, 不是次日开盘 ──────────────────────────────────────
def test_R327_按当天收盘价成交_不是次日():
    """这是与 flip_trades(次日开盘)最根本的分界, 钉死它。"""
    res = fp.simulate({"A": _mk(["UT", "UT"], [10.0, 99.0])}, capital=100_000, max_positions=1)
    o = res["orders"][0]
    assert o["date"] == "2026-01-01", "信号日当天成交"
    # 10.0 加买入滑点, 与次日那根 99 毫无关系
    assert o["price"] == pytest.approx(10.0 * (1 + fp.SLIPPAGE_BPS / 10_000), rel=1e-9)


def test_R327_滑点买贵卖便宜():
    res = fp.simulate({"A": _mk(["UT", "DT"], [10.0, 10.0])}, capital=100_000, max_positions=1)
    buy, sell = res["orders"]
    assert buy["price"] > 10.0, "买要贵一点"
    assert sell["price"] < 10.0, "卖要便宜一点"


# ── 撮合规矩 ────────────────────────────────────────────────────────────
def test_R327_整手成交且现金不为负():
    res = fp.simulate({"A": _mk(["UT"], [7.77])}, capital=10_000, max_positions=1)
    o = res["orders"][0]
    assert o["shares"] % fp.LOT == 0 and o["shares"] > 0
    assert all(r["cash"] >= 0 for r in res["nav"]), "现金不许为负"


def test_R327_费用两边都扣且卖出多一道印花税():
    res = fp.simulate({"A": _mk(["UT", "DT"], [10.0, 10.0])}, capital=100_000, max_positions=1)
    buy, sell = res["orders"]
    # amount 与 fee 都是落库前 round(2) 过的, 比的是分, 不是浮点尾数
    assert buy["fee"] == pytest.approx(buy["amount"] * fp.COMMISSION, abs=0.01)
    assert sell["fee"] == pytest.approx(
        sell["amount"] * (fp.COMMISSION + fp.STAMP_TAX), abs=0.01)
    assert sell["fee"] > buy["fee"], "卖出多一道印花税"


def test_R327_T加1_当天买的当天不许卖():
    """同一天既转多又转空在真实数据里出不来, 但规则就是规则, 不靠碰巧满足。"""
    a = _mk(["UT"], [10.0])
    a["steps"][0]["flipped"] = True
    res = fp.simulate({"A": a}, capital=100_000, max_positions=1)
    same_day = [o for o in res["orders"] if o["date"] == "2026-01-01"]
    assert [o["act"] for o in same_day] == [fp.ACT_BUY], "当天只该有买, 不该有卖"


# ── 卖在买前 ────────────────────────────────────────────────────────────
def test_R327_卖在买前_腾出的现金当天就能用():
    """A 转空清仓、B 同日转多。只有先卖, B 才买得到足额的一份。"""
    day = ["2026-01-01", "2026-01-02"]
    a = _mk(["UT", "DT"], [10.0, 10.0], name="A", dates=day)
    b = _mk(["DT", "UT"], [10.0, 10.0], name="B", dates=day)
    res = fp.simulate({"A": a, "B": b}, capital=100_000, max_positions=1)
    d2 = [o for o in res["orders"] if o["date"] == "2026-01-02"]
    assert [o["act"] for o in d2] == [fp.ACT_SELL, fp.ACT_BUY], "必须先卖后买"
    assert d2[1]["symbol"] == "B", "腾出的位置给 B"


def test_R327_卖出循环在买入循环之前_源码顺序钉死():
    """**行为测试钉不住顺序。**

    上面那条只能证明"这组输入下先卖后买"。把两个循环真的对调, 它在别的输入下
    才会露馅 —— 变异电池当场演示过: 改一行注释它照样绿。所以这里直接钉源码:
    `simulate` 里卖出那一趟必须排在买入那一趟前面。
    """
    import ast
    import inspect
    tree = ast.parse(inspect.getsource(fp.simulate).lstrip())
    fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef))
    order = []
    for node in ast.walk(fn):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr == "append" and isinstance(node.func.value, ast.Name) \
                and node.func.value.id == "orders":
            # 每次 orders.append 的第一个实参是 _order(day, sym, names, ACT_X, ...)
            arg = node.args[0] if node.args else None
            if isinstance(arg, ast.Call):
                for a in arg.args:
                    if isinstance(a, ast.Name) and a.id in ("ACT_BUY", "ACT_SELL"):
                        order.append((a.id, a.lineno))
    assert len(order) == 2, f"simulate 里该正好有一处买、一处下单记账, 实际 {order}"
    by_line = [k for k, _ in sorted(order, key=lambda x: x[1])]
    assert by_line == ["ACT_SELL", "ACT_BUY"], (
        f"卖出必须写在买入之前, 现在是 {by_line} —— 反过来就是拿错的账面做买入决定")


# ── 等权与上限 ──────────────────────────────────────────────────────────
def test_R327_等权按当日净值均分_不是按本金():
    """先让账户赚一大笔, 再看新仓位有没有跟着变大 —— 按本金分的话不会变。

    **上限要开得足够大**: 等权目标再大也受现金约束, 两只票分一半本金的话
    A 一涨现金就见底, 测出来的是"钱不够"而不是"目标算错了"。第一版就栽在
    这儿 —— 用 max_positions=2 跑, 目标 123K 而手上只有 50K 现金。
    """
    day = [f"2026-01-{i:02d}" for i in range(1, 5)]
    # 十份里 A 只占一份(1 万), 剩 9 万现金; A 涨 10 倍后净值 19 万, 目标 1.9 万
    a = _mk(["UT", "UT", "UT", "UT"], [10.0, 10.0, 100.0, 100.0], name="A", dates=day)
    b = _mk(["DT", "DT", "DT", "UT"], [10.0, 10.0, 10.0, 10.0], name="B", dates=day)
    res = fp.simulate({"A": a, "B": b}, capital=100_000, max_positions=10)
    nav_before_b = next(r for r in res["nav"] if r["date"] == "2026-01-03")["nav"]
    b_buy = next(o for o in res["orders"] if o["symbol"] == "B")
    assert nav_before_b > 150_000, "先确认账户真的赚了, 不然这条测不到东西"
    # 按本金分只会是 10,000; 按当日净值分该接近 19,000
    assert b_buy["amount"] > 10_000 * 1.5, (
        f"净值涨到 {nav_before_b} 之后新仓位该跟着变大, 实际只买了 {b_buy['amount']}")
    assert b_buy["amount"] <= nav_before_b / 10 * 1.01


def test_R327_满仓之后不再买_且记下原因():
    day = ["2026-01-01"]
    series = {s: _mk(["UT"], [10.0], name=s, dates=day) for s in ("A", "B", "C")}
    res = fp.simulate(series, capital=100_000, max_positions=2)
    assert len(res["orders"]) == 2
    assert [s["reason"] for s in res["skipped"]] == [fp.WHY_NO_SLOT]


def test_R327_仓位满不顺延():
    """位置是被别的票占着, 不是市场不让成交 —— 顺延的话哪天腾出位置会冷不丁
    买进一只信号早就过期的票。"""
    day = ["2026-01-01", "2026-01-02"]
    a = _mk(["UT", "UT"], [10.0, 10.0], name="A", dates=day)
    b = _mk(["UT", "UT"], [10.0, 10.0], name="B", dates=day)
    res = fp.simulate({"A": a, "B": b}, capital=100_000, max_positions=1)
    assert [o["symbol"] for o in res["orders"]] == ["A"]
    assert res["pending"] == [], "仓位满不许进 pending"


def test_R327_上限被_clamp():
    res = fp.simulate({"A": _mk(["UT"], [10.0])}, capital=100_000,
                      max_positions=fp.MAX_POSITIONS_CAP + 999)
    assert res["stats"]["orders"] == 1        # 没炸就行, clamp 生效
    res0 = fp.simulate({"A": _mk(["UT"], [10.0])}, capital=100_000, max_positions=0)
    assert res0["stats"]["orders"] == 1, "0 也要 clamp 成至少 1"


# ── 封板顺延 ────────────────────────────────────────────────────────────
def test_R327_收盘涨停买不进_顺延到能成交那天():
    day = ["2026-01-01", "2026-01-02"]
    a = _mk(["UT", "UT"], [10.0, 11.0], dates=day, limit_up=[True, False])
    res = fp.simulate({"A": a}, capital=100_000, max_positions=1)
    assert [o["date"] for o in res["orders"]] == ["2026-01-02"], "封板那天不该成交"
    assert res["orders"][0]["delayed"] is True
    assert res["orders"][0]["signal_date"] == "2026-01-01", "信号日要留痕"
    assert [s["reason"] for s in res["skipped"]] == [fp.WHY_SEALED]


def test_R327_收盘跌停卖不掉_顺延():
    day = ["2026-01-01", "2026-01-02", "2026-01-03"]
    a = _mk(["UT", "DT", "DT"], [10.0, 9.0, 8.0], dates=day,
            limit_down=[False, True, False])
    res = fp.simulate({"A": a}, capital=100_000, max_positions=1)
    sells = [o for o in res["orders"] if o["act"] == fp.ACT_SELL]
    assert [o["date"] for o in sells] == ["2026-01-03"], "跌停封死那天卖不掉"


def test_R327_一直封到反向转折_这张单作废():
    day = ["2026-01-01", "2026-01-02", "2026-01-03"]
    # 第 1 天转多但涨停封死, 第 2 天仍涨停, 第 3 天转空 → 买单作废
    a = _mk(["UT", "UT", "DT"], [10.0, 11.0, 9.0], dates=day,
            limit_up=[True, True, False])
    res = fp.simulate({"A": a}, capital=100_000, max_positions=1)
    assert res["orders"] == [], "从头到尾没买进去, 也就没得卖"
    assert fp.WHY_VOIDED in [s["reason"] for s in res["skipped"]]
    assert res["pending"] == []


def test_R327_买入日撞跌停照买_方向要对上():
    """买入日跌停是**买得更便宜**, 标成风险会把利好读成利空。"""
    a = _mk(["UT"], [10.0], limit_down=[True])
    res = fp.simulate({"A": a}, capital=100_000, max_positions=1)
    assert len(res["orders"]) == 1, "买入日撞的是跌停, 不该挡"


def test_R327_卖出日撞涨停照卖():
    a = _mk(["UT", "DT"], [10.0, 11.0], limit_up=[False, True])
    res = fp.simulate({"A": a}, capital=100_000, max_positions=1)
    assert [o["act"] for o in res["orders"]] == [fp.ACT_BUY, fp.ACT_SELL]


def test_R327_不给涨跌停标志就一律当能成交_不瞎猜():
    a = _mk(["UT"], [10.0])
    a.pop("limit_up"); a.pop("limit_down")
    res = fp.simulate({"A": a}, capital=100_000, max_positions=1)
    assert len(res["orders"]) == 1


# ── 判据来源 ────────────────────────────────────────────────────────────
def test_R327_多空判据来自_flip_trades_不自己造():
    """**只看函数体, 不看整个模块。**

    第一版拿 `inspect.getsource(fp)` 整个模块去查 "BULLISH" 不许出现 —— 结果
    被模块 docstring 里那句「不在这里重写一遍 `state in BULLISH`」喂饱, 断言
    立刻红。同一个坑这仓库栽过五次(见 tests/frontend_source.py 的说明):
    **断言查的标识符, 正好也写在解释它的文字里。** 剥掉文档, 只看代码。
    """
    import ast
    import inspect
    tree = ast.parse(inspect.getsource(fp))
    bodies = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            body = list(node.body)
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                body = body[1:]          # 掐掉 docstring
            bodies.append("\n".join(ast.unparse(n) for n in body))
    code = "\n".join(bodies)
    assert "trend_days(steps)" in code, "每日多空必须问 flip_trades 要"
    assert "BULLISH" not in code, "多空归属不许在这里重写一遍"


def test_R327_成交不了的判据与开盘价那条路分开():
    """`flip_trades._sealed` 要 `开盘 ≥ 收盘`, 这边尾盘成交只看收盘在不在板上 ——
    盘中打开过、尾盘封回去的票, 两条路的结论正好相反。"""
    assert fp.sealed_at_close(True) is True
    assert fp.sealed_at_close(False) is False
    import inspect
    assert "_sealed" not in inspect.getsource(fp.simulate), "不许复用开盘价那条判据"


# ── 净值与统计 ──────────────────────────────────────────────────────────
def test_R327_净值逐日等于现金加市值():
    day = [f"2026-01-{i:02d}" for i in range(1, 6)]
    a = _mk(["UT", "UT", "DT", "DT", "UT"], [10, 12, 11, 9, 10], dates=day)
    res = fp.simulate({"A": a}, capital=100_000, max_positions=1)
    for r in res["nav"]:
        assert r["nav"] == pytest.approx(r["cash"] + r["market_value"], abs=0.02)


def test_R327_胜负只数已兑现的那几轮():
    day = [f"2026-01-{i:02d}" for i in range(1, 5)]
    # 一轮完整赚钱的买卖 + 一个还拿着的多头段
    a = _mk(["UT", "DT", "UT", "UT"], [10, 12, 11, 20], dates=day)
    res = fp.simulate({"A": a}, capital=100_000, max_positions=1)
    assert res["stats"]["round_trips"] == 1, "还拿着的那段不算一轮"
    assert res["stats"]["win"] == 1
    assert len(res["positions"]) == 1, "最后还拿着一只"
    # 一轮的盈亏必须是**真的那一笔**, 不是随手记的常数 —— 10 元买 12 元卖,
    # 扣掉两头费用与滑点之后仍该接近 +2/10 的量级
    assert res["stats"]["best"] is not None
    assert res["stats"]["best"] == pytest.approx(res["stats"]["worst"]), "只有一轮"
    sells = [o for o in res["orders"] if o["act"] == fp.ACT_SELL]
    buys = [o for o in res["orders"] if o["act"] == fp.ACT_BUY]
    expect = (sells[0]["amount"] - sells[0]["fee"]) - (buys[0]["amount"] + buys[0]["fee"])
    assert res["stats"]["best"] == pytest.approx(expect, abs=0.05), (
        "这一轮的盈亏要等于卖出净得减买入净付, 不许是个凑出来的数")


def test_R327_还拿着的不许混进胜负():
    """全程只买不卖 —— 一轮都没兑现, 胜负栏必须是空的而不是 0 胜 0 负混进一笔。"""
    res = fp.simulate({"A": _mk(["UT", "UT", "UT"], [10, 20, 30])},
                      capital=100_000, max_positions=1)
    assert res["stats"]["round_trips"] == 0
    assert res["stats"]["win_rate"] is None, "一轮都没有时胜率是「算不出来」, 不是 0"
    assert len(res["positions"]) == 1
    assert res["stats"]["total_ret"] > 0, "但净值该涨 —— 浮盈照样计入"


def test_R327_一天都跑不了时说明原因_不留空栏():
    assert fp.simulate({}, capital=100_000)["reason"] == "no_data"
    # 全程空头 → 一笔都没做成
    res = fp.simulate({"A": _mk(["DT", "DT"], [10, 9])}, capital=100_000)
    assert res["reason"] == "no_flip"
    assert res["stats"]["total_ret"] == 0.0


def test_R327_各票日历取并集_上市日不同不会错位():
    a = _mk(["UT", "UT"], [10, 10], name="A", dates=["2026-01-05", "2026-01-06"])
    b = _mk(["UT", "UT"], [20, 20], name="B", dates=["2026-01-01", "2026-01-02"])
    res = fp.simulate({"A": a, "B": b}, capital=100_000, max_positions=2)
    assert [r["date"] for r in res["nav"]] == [
        "2026-01-01", "2026-01-02", "2026-01-05", "2026-01-06"]
    # B 先上市先买, A 上市那天才轮到 A
    assert [(o["date"], o["symbol"]) for o in res["orders"]] == [
        ("2026-01-01", "B"), ("2026-01-05", "A")]


def test_R327_同样的输入跑两遍逐值相同():
    """可复现是这套东西的立身之本 —— 有任何一处依赖字典序或随机都会在这里露出来。"""
    day = [f"2026-01-{i:02d}" for i in range(1, 6)]
    series = {
        "A": _mk(["UT", "DT", "UT", "UT", "DT"], [10, 9, 11, 12, 10], name="A", dates=day),
        "B": _mk(["DT", "UT", "UT", "DT", "UT"], [20, 21, 22, 19, 20], name="B", dates=day),
    }
    assert fp.simulate(series, capital=100_000, max_positions=2) == \
           fp.simulate(series, capital=100_000, max_positions=2)
