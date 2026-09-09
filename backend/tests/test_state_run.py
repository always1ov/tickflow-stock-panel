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


# ---------------------------------------------------------------- 口径

def test_刚出现的那一档是第一天():
    """今天这一档成立就是第 1 天。**没有"第 0 天"** —— 那不是人话。"""
    assert ks._state_run("a", {"states": ["a", "b"], "state_dates": ["d1", "d0"]})["days"] == 1


def test_连着几天就数几天():
    lm = {"states": ["a", "a", "a", "b"], "state_dates": ["d3", "d2", "d1", "d0"]}
    got = ks._state_run("a", lm)
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
    lm = {"states": ["a", "a", "x", "a", "a", "a"],
          "state_dates": ["d6", "d5", "d4", "d3", "d2", "d1"]}
    got = ks._state_run("a", lm)
    assert got["days"] == 2, f"断档之后该从 2 起算, 却数成了 {got['days']} 天(累计是 5)"
    assert got["since"] == "d5"


def test_徽标那一档与序列今天不一致时保底一天():
    """两条路(enriched 快照 vs 日线批量)的"今天"本来就可能不一样。

    **[R248] 这条原来断言的是"不给天数"—— 那正是错的行为**, 也是用户
    「怎么不显示天数了?」撞到的东西。徽标印的是今天的真相, 至少 1 天。
    详见 `_state_run` 里那段。
    """
    assert ks._state_run("a", {"states": ["b", "b"]}) == {"days": 1, "capped": True}
    assert ks._state_run("a", {}) == {"days": 1, "capped": True}
    # 连徽标那一档都没有时才真的不给 —— 那是"这一格没有状态", 另一回事
    assert ks._state_run(None, {"states": ["a"]}) is None


def test_数到序列尽头时标成下界():
    assert ks._state_run("a", {"states": ["a", "a"]}).get("capped") is True


def test_再往前那天算不出来时也标成下界():
    """长期档要 120 根暖机, 更早的日子判不了 —— 那是**没得数了**, 不是段结束。
    不标下界的话, 一个被截断的天数会被当成准数印出去。"""
    assert ks._state_run("a", {"states": ["a", "a", None]}).get("capped") is True


def test_段自己结束时不许乱标下界():
    assert not ks._state_run("a", {"states": ["a", "x", "x"]}).get("capped")


# ---------------------------------------------------------------- 序列

def test_序列到第一个变化就收手():
    """调用方只要"今天这一档连着几天", 再往前算都是白算 ——
    一段 25 天的「候选池」不该跑满 250 天。多留的那一天是哨兵。

    喂**预计算的** ma20/ma60(与线上、与复盘同源), 自己滚均线得到的是另一套。
    """
    closes = _decline(40)
    n = len(closes)

    def ma(w, i):
        return None if i + 1 < w else sum(closes[i + 1 - w:i + 1]) / w

    seq = kg.state_series(closes, [_ATR] * n,
                          ma20=[ma(20, i) for i in range(n)],
                          ma60=[ma(60, i) for i in range(n)])
    assert seq[0] == "watch_low", f"夹具今天是 {seq[0]}, 这条测不到"
    assert len(seq) < 30, f"没有提前收手, 算了 {len(seq)} 天(上限是 {kg.MAX_LOOKBACK})"
    assert seq[-1] != seq[0], "最后一项该是哨兵(与今天不同的那一档)"
    assert all(x == seq[0] for x in seq[:-1]), "中间混进了别的档"


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
    got = ks._state_run("a", {"states": ["b", "b", "b"]})
    assert got is not None, "对不上就整个不给了 —— 徽标上的天数会静默消失"
    assert got["days"] == 1
    assert got["capped"] is True, "这是下界(真实天数可能更多), 该带 `+`"


def test_R248_没有历史时也保底一天():
    assert ks._state_run("a", {})["days"] == 1
    assert ks._state_run("a", {"states": []})["days"] == 1


def test_R248_连徽标那一档都没有时才不给():
    """这一格本来就没有状态 —— 那是真的没得说, 与"算不出来"不是一回事。"""
    assert ks._state_run(None, {"states": ["a"]}) is None


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
