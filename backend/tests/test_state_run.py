"""[R246] 结论列的「最近这一档连着几天」。

用户: 「显示每个个股的通道结论里面的最近的状态和持续时间」。

盯四件事:

  ① 天数是**真的数出来的**, 不是拍的;
  ② **中断即重算** —— 说成累计出现次数会把这一档持续了多久说多;
  ③ 数不到头时标成下界(`capped`), 不假装是准数;
  ④ 判定一个字都没自己写 —— 仍然走作者的 `assess` / `verdict`。
"""
from __future__ import annotations

import datetime as dt

import polars as pl

from app.indicators import keltner as k
from app.indicators import keltner_geometry as kg
from app.services import keltner_service as ks

_ATR = 0.25
_END = dt.date(2026, 9, 9)


def _trading_days(n: int, end: dt.date = _END) -> list[dt.date]:
    out, d = [], end
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d -= dt.timedelta(days=1)
    return out[::-1]


def _repo(closes: list[float], symbol: str = "X"):
    """线上那条链的最小复制: enriched 快照 + 带预计算均线列的日线批量。"""
    n = len(closes)
    dates = _trading_days(n)

    def ma(w: int, i: int):
        return None if i + 1 < w else sum(closes[i + 1 - w:i + 1]) / w

    class _Repo:
        def get_enriched_latest(self):
            return pl.DataFrame({
                "symbol": [symbol], "close": [closes[-1]], "atr_14": [_ATR],
                "ma20": [ma(20, n - 1)], "ma60": [ma(60, n - 1)],
            }), str(_END)

        def get_daily_batch(self, symbols, start, end, cols):
            keep = [i for i, d in enumerate(dates) if start <= d <= end]
            return pl.DataFrame({
                "symbol": [symbol] * len(keep), "date": [dates[i] for i in keep],
                "close": [closes[i] for i in keep], "atr_14": [_ATR] * len(keep),
                "ma20": [ma(20, i) for i in keep], "ma60": [ma(60, i) for i in keep],
            })

    return _Repo()


def _row(closes: list[float]) -> dict:
    return ks.channels_for_symbols(_repo(closes), ["X"]).get("X") or {}


def _decline(n: int, base: float = 10.0, total: int = 400) -> list[float]:
    """长期横盘 + 最后 n 根缓跌 —— 短期回到通道中部而中期到下沿 = 候选池。"""
    return [base] * (total - n) + [round(base - 0.025 * i, 4) for i in range(1, n + 1)]


def _run(key, states, dates=None, as_of=None):
    """`_state_run` 的调用适配器。

    [R256] 多收了一个 `as_of`(enriched 快照的日期)—— 用它跟序列最新一根的日期
    对一下, 才分得清「序列里有今天」和「日线滞后一天」。默认让两者同一天。
    """
    dates = dates or [f"d{len(states) - i}" for i in range(len(states))]
    return ks._state_run(key, {"states": states, "state_dates": dates},
                         as_of if as_of is not None else (dates[0] if dates else None))


# ---------------------------------------------------------------- 口径

def test_刚出现的那一档是第一天():
    """今天这一档成立就是第 1 天。**没有"第 0 天"** —— 那不是人话。"""
    assert _run("a", ["a", "b"], ["d1", "d0"])["days"] == 1


def test_连着几天就数几天():
    got = _run("a", ["a", "a", "a", "b"], ["d3", "d2", "d1", "d0"])
    assert got["days"] == 3
    assert got["since"] == "d1", "起始日该指向这一段的第一个交易日"
    assert not got.get("capped"), "段自己结束了, 是准数不该标下界"


def test_中断即重算不累计():
    """**这条是整个口径的关键。**

    「候选池」出现 3 天、隔一天回到通道中部、再出现 2 天 —— 那是**两次独立的
    出现**, 报的是 2 天。报 5 天会让人以为它已经在这个位置磨了一周,
    而实际上刚回来两天。与"在轨外连续几天"、六态 duration 同一条纪律。
    """
    # 断档**后面还得再出现同一档**, 否则"中断即重算"和"累计出现次数"给的是
    # 同一个数, 这条就测不到东西(变异测试当场证明过)。
    got = _run("a", ["a", "a", "x", "a", "a", "a"],
               ["d6", "d5", "d4", "d3", "d2", "d1"])
    assert got["days"] == 2, f"断档之后该从 2 起算, 却数成了 {got['days']} 天(累计是 5)"
    assert got["since"] == "d5"


def test_徽标那一档与序列今天不一致时保底一天():
    """两条路(enriched 快照 vs 日线批量)的"今天"本来就可能不一样。

    **[R248] 这条原来断言的是"不给天数"—— 那正是错的行为**, 也是用户
    「怎么不显示天数了?」撞到的东西。徽标印的是今天的真相, 至少 1 天。
    详见 `_state_run` 里那段。
    """
    # [R256] 序列的今天判成了别的档 —— 那一根跳过, 今天以徽标为准算 1 天。
    # **不再标下界**: 历史还长着, 只是这一档确实是今天才有的。
    assert _run("a", ["b", "b"]) == {"days": 1, "since": "d2"}
    # 连历史都没有时才是下界(下一根是什么, 无从知道)
    assert _run("a", []) == {"days": 1, "capped": True}
    # 连徽标那一档都没有时才真的不给 —— 那是"这一格没有状态", 另一回事
    assert _run(None, ["a"]) is None


def test_数到序列尽头时标成下界():
    assert _run("a", ["a", "a"]).get("capped") is True


def test_再往前那天算不出来时也标成下界():
    """长期档要 120 根暖机, 更早的日子判不了 —— 那是**没得数了**, 不是段结束。
    不标下界的话, 一个被截断的天数会被当成准数印出去。"""
    assert _run("a", ["a", "a", None]).get("capped") is True


def test_段自己结束时不许乱标下界():
    assert not _run("a", ["a", "x", "x"]).get("capped")


# ---------------------------------------------------------------- 序列

def test_R256_序列只在算不出来时停():
    """[R256] **提前退出不能绑在序列自己的今天上。**

    原来是「跟 out[0] 不一样就停」, 于是序列里只剩它自己那一档的连续段。可数
    天数的是调用方, 它手上的是**快照那一档** —— 两边一对不上, 序列里根本找不到
    要数的那一档, 全表退化成「已1天+」(用户截图)。

    现在只在**算不出来**时停(长期档 120 根暖机, 更早的日子判不了)。那既是真的
    没得数了, 也把循环钉在几十次以内, 不会空转到 limit。
    """
    closes = _decline(40)
    n = len(closes)

    def ma(w, i):
        return None if i + 1 < w else sum(closes[i + 1 - w:i + 1]) / w

    seq = kg.state_series(closes, [_ATR] * n,
                          ma20=[ma(20, i) for i in range(n)],
                          ma60=[ma(60, i) for i in range(n)])
    assert seq[0] == "watch_low", f"夹具今天是 {seq[0]}, 这条测不到"
    # 今天这一档只连着十几天, 而序列该一直数到"算不出来"为止。
    # 老写法(绑自己的今天)交出来的是 15+1 项 —— **只看长度就能分辨**;
    # 只数"有几种不同的档"不行, 老写法也有两种(连续段 + 那个哨兵),
    # 变异测试当场证明过那条断言是空的。
    run0 = next(i for i, x in enumerate(seq) if x != seq[0])
    assert len(seq) > run0 * 3 and len(seq) > 100, (
        f"序列只有 {len(seq)} 项而今天这一档才连着 {run0} 天 —— "
        f"提前退出又绑回自己的今天了, 两条路一对不上就会全表「已1天+」"
    )
    assert all(x is not None for x in seq), "算不出来的那些天不该留在序列里"


def test_判定仍然走作者那两个函数():
    """[守则] `indicators/keltner.py` 是作者的, 一个字节都不许改。
    这一层只负责**数天数**, 判定必须原样借用。"""
    closes = _decline(30)
    n = len(closes)
    bands = {}
    for key in ("s", "m", "l"):
        w = kg.WINDOW[key]
        bands[key] = k.assess(close=closes[-1], ma=sum(closes[n - w:]) / w,
                              atr=_ATR, n=kg.K[key])
    assert kg.state_series(closes, [_ATR] * n)[0] == k.verdict(bands)["code"]


def test_数据不齐时安静返回空而不是崩():
    assert kg.state_series(None, None) == []
    assert kg.state_series([], []) == []
    assert kg.state_series([10.0] * 5, [_ATR] * 5) == [None]      # 太短, 长期档出不来
    assert kg.state_series([10.0] * 5, [_ATR] * 4) == []          # 长度对不上


# ---------------------------------------------------------------- 整条链

def test_端到端_天数真的出现在接口返回的_verdict_里():
    """单元测试盯不到"两个模块之间" —— 这条走完整条 `channels_for_symbols`。"""
    v = (_row(_decline(30)) or {}).get("verdict")
    assert v and v["code"] == "watch_low", f"夹具造出来的是 {v and v.get('code')}"
    assert v["days"] > 1, f"连着挂了很多天却只报了 {v['days']} 天"
    assert v.get("since"), "没给起始日, 悬停里就核对不了"


def test_端到端_对上复盘弹窗那张卡片():
    """用户截图: 兆易创新复盘里写着「候选池 2026-08-06 ~ 2026-09-09 持续25天」。
    决策台结论列必须是同一个数、同一个起始日 —— 两处对不上就等于没做。"""
    for nd in range(20, 60):
        v = (_row(_decline(nd)) or {}).get("verdict") or {}
        if v.get("code") == "watch_low" and v.get("days") == 25:
            assert v["since"] == "2026-08-06", f"起始日是 {v['since']}, 与复盘对不上"
            return
    raise AssertionError("没造出「候选池 25 天」的夹具, 这条测不到")


def test_端到端_没有结论那一格也有天数():
    """三档都在通道中部时底层判不出结论, 那一格印的是组合注记的标题
    (「半年低位」这类**带时间词却没有天数**的话)。用户要的正是天数。"""
    row = _row([10.0] * 400)
    assert not row.get("verdict"), "这份夹具本该判不出结论, 前提就错了"
    run = row.get("state_run")
    assert run and run["days"] > 1, f"没结论那一格没拿到天数: {run}"


def test_端到端_有结论时不另给一个平级的天数():
    """同一行摆两个数, 读的人得先判断哪个是哪个。有结论时天数只有一份。"""
    row = _row(_decline(30))
    assert row.get("verdict", {}).get("days")
    assert "state_run" not in row


def test_十条结论没有一条被排除在天数之外():
    """防的是"只给某几档算天数"这种半吊子实现 —— 那样用户会发现有的徽标带
    天数有的不带, 而且看不出规律。盯实现: 不许出现按 code 分支的逻辑。"""
    import inspect

    from app.indicators.keltner import _VERDICTS
    src = inspect.getsource(kg.state_series) + inspect.getsource(ks._state_run)
    for code in _VERDICTS:
        assert code not in src, f"出现了 `{code}` —— 这一层不该认识任何具体结论码"


def test_徽标上写的是_已N天_不是历史累计():
    """「已」字不是修饰, 是这句话的全部意思 —— 「候选池 25天」可以读成"历史上
    累计 25 天", 而这里说的是"已经**连着** 25 天"。一字之差是两个数。"""
    import pathlib

    p = (pathlib.Path(__file__).resolve().parents[2] / "frontend" / "src"
         / "components" / "stock-analysis" / "decision-board" / "cells.tsx")
    if not p.exists():
        import pytest
        pytest.skip("拿不到前端源码(只跑后端时正常)")
    src = "\n".join(ln for ln in p.read_text(encoding="utf-8").splitlines()
                    if not ln.lstrip().startswith(("//", "*", "/*")))
    assert "已{d.days}天{d.capped ? '+' : ''}" in src, "徽标没按统一写法渲染天数"
    assert "<Days d={v} />" in src, "有结论那一格没渲染天数"
    assert "<Days d={stateRun} />" in src, "没结论那一格没渲染天数"


# ===== [R248] 徽标上有一档, 就一定有天数 =====
#
# 用户: 「怎么不显示天数了?」
#
# R246 在两条路对不上时返回 `None`, 注释里写着「让上层退回今天刚变」——
# **那个兜底根本没写**, 于是对不上的行天数整个不显示。
#
# 这是同一件事第二次栽(R234 也是), 所以规矩钉死: 徽标印的是今天的真相,
# 说它「已1天」是真话; **一个偏保守的数字远好过一个消失的字段** ——
# "算不出来"和"功能没部署"在界面上长得一模一样, 而这两种要做的事完全不同。


def test_R248_两条路对不上时保底一天而不是整个不给():
    got = _run("a", ["b", "b", "b"])
    assert got is not None, "对不上就整个不给了 —— 徽标上的天数会静默消失"
    assert got["days"] == 1
    # [R256] 历史还长着, 只是这一档今天才有 —— 那是准数, 不该带 `+`
    assert not got.get("capped")


def test_R248_没有历史时也保底一天():
    assert _run("a", [])["days"] == 1
    assert _run("a", [])["days"] == 1


def test_R248_连徽标那一档都没有时才不给():
    """这一格本来就没有状态 —— 那是真的没得说, 与"算不出来"不是一回事。"""
    assert _run(None, ["a"]) is None


def test_R248_端到端_快照与日线对不上时徽标仍有天数():
    """**这条是用户实际撞到的那个现象。**

    徽标那一档来自 enriched 快照, 逐日序列来自日线批量 —— 两者在最后一根上
    本来就可能不一样(复权口径、不是同一天收的)。造一份"快照价与日线末根差
    一点"的数据, 断言天数没有消失。
    """
    import datetime as dt

    closes = [10.0] * 370 + [round(10.0 - 0.025 * i, 4) for i in range(1, 31)]
    n = len(closes)
    dates = _trading_days(n)

    def ma(w, i):
        return None if i + 1 < w else sum(closes[i + 1 - w:i + 1]) / w

    class _Skewed:
        def get_enriched_latest(self):
            # 快照价比日线末根低一点 —— 足以把这一格判成另一档
            return pl.DataFrame({
                "symbol": ["X"], "close": [closes[-1] - 0.15], "atr_14": [_ATR],
                "ma20": [ma(20, n - 1)], "ma60": [ma(60, n - 1)],
            }), str(_END)

        def get_daily_batch(self, symbols, start, end, cols):
            keep = [i for i, d in enumerate(dates) if start <= d <= end]
            return pl.DataFrame({
                "symbol": ["X"] * len(keep), "date": [dates[i] for i in keep],
                "close": [closes[i] for i in keep], "atr_14": [_ATR] * len(keep),
                "ma20": [ma(20, i) for i in keep], "ma60": [ma(60, i) for i in keep],
            })

    row = ks.channels_for_symbols(_Skewed(), ["X"]).get("X") or {}
    v = row.get("verdict")
    assert v, "这份夹具本该有结论, 前提就错了"
    assert v.get("days"), (
        f"两条路对不上, 天数就整个消失了 —— 这正是用户看到的现象。拿到的是 {sorted(v)}"
    )


def test_R248_只要有结论就一定有天数():
    """总闸: 遍历一组走势各异的夹具, 每一只只要出了结论就必须带天数。"""
    from tests.fixtures import market_archetypes as fx

    checked = 0
    for name in fx.SCENARIOS:
        cl = list(fx.closes(name))
        if len(cl) < 400:
            cl = [cl[0]] * (400 - len(cl)) + cl
        row = _row(cl)
        v = row.get("verdict")
        if not v:
            assert (row.get("state_run") or {}).get("days"), \
                f"{name}: 没结论那一格也没天数"
        else:
            assert v.get("days"), f"{name}: 出了结论「{v['title']}」却没有天数"
        checked += 1
    assert checked >= 10, f"只核了 {checked} 个场景"


# ===== [R256] 序列里到底有没有「今天」 =====
#
# 用户: 「有的个股怎么没显示完整」—— 截图里几乎每一行都是「已1天+」。
#
# 根因是提前退出绑在**序列自己的今天**上(见 test_R256_序列只在算不出来时停)。
# 修好之后还得把这三种情形分开数, 混成一种就会差一天:
#
#   ① 同一天, 序列这一档就是徽标那一档  → 序列的头就是今天, 直接数
#   ② 同一天, 序列判成了别的档          → 跳过那一根, 今天以徽标为准算 1 天
#   ③ 日线比快照滞后                    → 序列里没有今天, 今天单算, 再接着数


def test_R256_同一天且对得上时直接数序列():
    got = _run("a", ["a", "a", "a", "x"], ["d4", "d3", "d2", "d1"], as_of="d4")
    assert got["days"] == 3 and got["since"] == "d2"


def test_R256_同一天但序列判成别的档时跳过那一根():
    """那一根是**今天的另一个读数**(复权口径/取数时点不同), 不是昨天 ——
    拿它当昨天数会把天数多算一天。"""
    got = _run("a", ["b", "a", "a"], ["d3", "d2", "d1"], as_of="d3")
    assert got["days"] == 3, f"应当是 今天1 + 序列里的2 = 3, 得到 {got['days']}"
    assert got["since"] == "d1"


def test_R256_日线滞后时今天单算再接着数():
    """序列最新一根是**昨天** —— 今天不在里面, 得由徽标补上, 否则少一天。
    这正是修之前「日线滞后一天就少数一天」的那个差错。"""
    got = _run("a", ["a", "a", "a"], ["d3", "d2", "d1"], as_of="d4")
    assert got["days"] == 4, f"应当是 今天1 + 序列里的3 = 4, 得到 {got['days']}"
    assert got["since"] == "d1"


def test_R256_今天刚变成这一档时起始日就是今天():
    got = _run("a", ["b", "b"], ["d2", "d1"], as_of="d2")
    assert got["days"] == 1 and got["since"] == "d2"


def test_R256_端到端_日线滞后不再少数一天():
    """整条链: 日线批量比 enriched 快照少最后一根(数据滞后是常态)。"""
    from app.services import keltner_service as ks

    closes = _decline(40)
    full = _row(closes)
    v_full = (full.get("verdict") or {})

    n = len(closes)
    dates = _trading_days(n)

    def ma(w, i):
        return None if i + 1 < w else sum(closes[i + 1 - w:i + 1]) / w

    class _Lagging:
        def get_enriched_latest(self):
            return pl.DataFrame({
                "symbol": ["X"], "close": [closes[-1]], "atr_14": [_ATR],
                "ma20": [ma(20, n - 1)], "ma60": [ma(60, n - 1)],
            }), str(dates[-1])

        def get_daily_batch(self, symbols, start, end, cols):
            keep = [i for i, d in enumerate(dates) if start <= d <= end][:-1]   # 少最后一根
            return pl.DataFrame({
                "symbol": ["X"] * len(keep), "date": [dates[i] for i in keep],
                "close": [closes[i] for i in keep], "atr_14": [_ATR] * len(keep),
                "ma20": [ma(20, i) for i in keep], "ma60": [ma(60, i) for i in keep],
            })

    v_lag = (ks.channels_for_symbols(_Lagging(), ["X"]).get("X") or {}).get("verdict") or {}
    assert v_full.get("days") and v_lag.get("days"), "两边都该有天数"
    assert v_lag["days"] == v_full["days"], (
        f"日线滞后一天就少数了一天: 完整 {v_full['days']} vs 滞后 {v_lag['days']}"
    )


def test_R256_三档都在中部那一格也有名字():
    """用户: 「有的个股怎么没显示完整」, 箭头指的是印着 `—` 的那两行。

    27 种组合里**只有这一格**是光秃秃的(120 格有结论、4 格有补充层注记)。
    它其实有含义: 价格落在三条通道都认可的公共区间里 —— 那不是「没数据」,
    是「位置上没有可说的」。**底层判定一个字没动**, 改的只是这一格印什么。
    """
    import pathlib

    p = (pathlib.Path(__file__).resolve().parents[2] / "frontend" / "src"
         / "components" / "stock-analysis" / "decision-board" / "cells.tsx")
    if not p.exists():
        import pytest
        pytest.skip("拿不到前端源码(只跑后端时正常)")
    body = "\n".join(ln for ln in p.read_text(encoding="utf-8").splitlines()
                     if not ln.lstrip().startswith(("//", "*", "/*", "{/*")))
    assert "note.title : '通道中部'" in body, (
        "「中中中」那一格又变回光秃秃的 `—` 了 —— 旁边还跟着「已N天」, "
        "读起来是「什么都没有, 已经 1 天」"
    )
