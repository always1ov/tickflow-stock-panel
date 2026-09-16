"""[R327] 转折模拟盘取数层 —— 一趟 IO、用每只票自己的阈值、非股票不丢。"""
from __future__ import annotations

from datetime import date

import polars as pl
import pytest

from app.services import flip_portfolio_run as run_mod


class _Repo:
    """批量接口只认股票; ETF 走逐只, 与真 repo 的行为一致。"""

    def __init__(self, frames: dict[str, pl.DataFrame], etf: set[str] | None = None):
        self.frames = frames
        self.etf = etf or set()
        self.batch_calls = 0
        self.single_calls: list[str] = []

    def resolve_asset_type(self, sym: str) -> str:
        return "etf" if sym in self.etf else "stock"

    def get_name_map(self, symbols=None):
        """[R328] 名称的唯一来源 —— 与真 repo 同名同义。

        第一版这个假 repo **没有这个方法**, 而被测代码当时是从自选条目里取
        名称的; 测试的 fixture 又给自选塞了 `name` 字段 —— **造的数据比真实
        数据更完整**, 于是那条路永远绿, 真实环境整张表印的却是代码。
        """
        m = {"A": "甲公司", "B": "乙公司", "E": "丙 ETF"}
        return m if symbols is None else {k: v for k, v in m.items() if k in symbols}

    def get_daily_batch(self, syms, start, end, columns):
        self.batch_calls += 1
        parts = [self.frames[s].with_columns(pl.lit(s).alias("symbol"))
                 for s in syms if s in self.frames]
        return pl.concat(parts) if parts else pl.DataFrame()

    def get_daily_asset(self, at, sym, start, end, columns=None):
        self.single_calls.append(sym)
        return self.frames.get(sym, pl.DataFrame())


def _bars(closes: list[float], *, lu: list[bool] | None = None) -> pl.DataFrame:
    n = len(closes)
    return pl.DataFrame({
        "date": [date(2026, 1, 1).replace(day=min(i + 1, 28)) for i in range(n)],
        "close": closes,
        "signal_limit_up": lu or [False] * n,
        "signal_limit_down": [False] * n,
    })


@pytest.fixture(autouse=True)
def _no_watchlist_io(monkeypatch):
    monkeypatch.setattr(run_mod.watchlist, "symbol_set", lambda: frozenset({"A", "B"}))
    # [R328] **不给 name** —— 真实的 watchlist.parquet schema 只有
    # symbol / added_at / note / group_ids, 没有 name 这一列。
    monkeypatch.setattr(run_mod.watchlist, "list_symbols",
                        lambda: [{"symbol": "A"}, {"symbol": "B"}])
    monkeypatch.setattr(run_mod.livermore_service, "get_effective_threshold",
                        lambda s: (0.06, "default"))


def test_R327_股票走一趟批量_不是逐只():
    repo = _Repo({"A": _bars([10.0] * 30), "B": _bars([20.0] * 30)})
    run_mod.run(repo, symbols=["A", "B"])
    assert repo.batch_calls == 1, "两只票该只打一趟批量"
    assert repo.single_calls == [], "股票不该走逐只回退"


def test_R327_非股票逐只回退_不静默丢掉():
    repo = _Repo({"A": _bars([10.0] * 30), "E": _bars([5.0] * 30)}, etf={"E"})
    out = run_mod.run(repo, symbols=["A", "E"])
    assert repo.single_calls == ["E"], "ETF 批量给不了, 必须逐只补"
    assert set(out["symbols"]) == {"A", "E"}
    assert out["missing"] == []


def test_R327_取不到数据的票进_missing_不装作没这只():
    repo = _Repo({"A": _bars([10.0] * 30)})
    out = run_mod.run(repo, symbols=["A", "GONE"])
    assert out["symbols"] == ["A"]
    assert out["missing"] == ["GONE"], "取不到就得说出来, 不能悄悄少一只"


def test_R327_阈值用每只票自己的_不是全局默认(monkeypatch):
    seen: list[str] = []

    def _th(sym: str):
        seen.append(sym)
        return (0.08 if sym == "A" else 0.04), "override"

    monkeypatch.setattr(run_mod.livermore_service, "get_effective_threshold", _th)
    repo = _Repo({"A": _bars([10.0] * 30), "B": _bars([20.0] * 30)})
    run_mod.run(repo, symbols=["A", "B"])
    assert sorted(seen) == ["A", "B"], "每只票都要各问一次自己的阈值"


def test_R327_不给_symbols_就取当前自选():
    repo = _Repo({"A": _bars([10.0] * 30), "B": _bars([20.0] * 30)})
    out = run_mod.run(repo)
    assert set(out["symbols"]) == {"A", "B"}


def test_R327_自选为空时说明原因():
    repo = _Repo({})
    out = run_mod.run(repo, symbols=[])
    assert out["reason"] == "no_watchlist"
    assert out["nav"] == []


def test_R327_涨跌停列缺失时当作能成交_不瞎猜():
    df = _bars([10.0] * 30).drop("signal_limit_up", "signal_limit_down")
    repo = _Repo({"A": df})
    out = run_mod.run(repo, symbols=["A"])
    assert out["reason"] != "no_data"


def test_R327_名称带进流水_不是只有代码():
    repo = _Repo({"A": _bars([10.0, 11.0, 12.0] * 10)})
    out = run_mod.run(repo, symbols=["A"])
    if out["orders"]:
        assert out["orders"][0]["name"] == "甲公司"


def test_R327_本金与上限原样回显_界面要照口径写出来():
    repo = _Repo({"A": _bars([10.0] * 30)})
    out = run_mod.run(repo, symbols=["A"], capital=250_000, max_positions=7)
    assert out["capital"] == 250_000
    assert out["max_positions"] == 7


# ── [R328] 名称解析 ────────────────────────────────────────────────────
def test_R328_名称从_repo_取_不从自选条目取():
    """自选表没有 name 列 —— 从那里取必然每行都回退成代码。"""
    repo = _Repo({"A": _bars([10.0] * 30)})
    out = run_mod.run(repo, symbols=["A"])
    assert out["positions"] or out["orders"], "先确认真的跑出了东西"
    for row in out["positions"] + out["orders"]:
        assert row["name"] == "甲公司"
        assert row["name"] != row["symbol"], "印出代码就是没解析到名称"


def test_R328_维表查不到时退回代码_不留空白():
    """退市或还没进维表的票 —— 宁可印代码, 不印空白。

    **直接测 `_names` 而不是走一遍 run。** 第一版走 run 然后 `for row in
    positions + orders: assert ...` —— 而那组恒定价格根本不产生转折, 两个列表
    都是空的, **循环一次都没执行**, 于是断言恒真。变异电池当场抓到: 把回退
    改成空串照样绿。空集合上的断言等于没有断言。
    """
    repo = _Repo({})
    assert run_mod._names(repo, ["Z"]) == {"Z": "Z"}, "查不到就退回代码"
    assert run_mod._names(repo, ["A", "Z"]) == {"A": "甲公司", "Z": "Z"}, \
        "查得到的用名称, 查不到的退回代码 —— 两者可以同时出现"


def test_R328_退回的代码要真的印到行上():
    """上一条钉的是 `_names` 的契约; 这一条钉它真的流到了每一行。

    **必须先确认列表非空** —— 否则又是空集合上的断言。
    """
    repo = _Repo({"Z": _bars([10.0, 12.0, 9.0, 11.0] * 8)})   # 价格起伏才有转折
    out = run_mod.run(repo, symbols=["Z"])
    rows = out["positions"] + out["orders"]
    assert rows, "这组价格该跑出转折, 跑不出来的话下面的断言是空的"
    for row in rows:
        assert row["name"] == "Z"


def test_R328_名称解析失败不影响跑完(monkeypatch):
    """名称只是显示 —— 它挂了不该把整个模拟盘带下水。"""
    repo = _Repo({"A": _bars([10.0] * 30)})
    monkeypatch.setattr(type(repo), "get_name_map",
                        lambda self, symbols=None: (_ for _ in ()).throw(RuntimeError("维表炸了")))
    out = run_mod.run(repo, symbols=["A"])
    assert out["reason"] != "no_data", "名称解析失败不该让模拟盘跑不出来"
    for row in out["positions"] + out["orders"]:
        assert row["name"] == "A"


def test_R328_走的是仓库统一的名称入口_不另开一条():
    """**剥掉 docstring 再断言** —— 第一版直接查 `inspect.getsource`, 被
    `_names` 自己那句「第一版写的是 `watchlist.list_symbols()`」喂饱当场红。
    同一个坑这会话栽了两次, 于是收进 `tests/py_source.py`。"""
    from tests.py_source import body_of
    code = body_of(run_mod._names)
    assert "repo.get_name_map" in code, "名称解析必须走 repo.get_name_map"
    assert "list_symbols" not in code, "自选条目里没有 name, 从那里取是错的"


# ── [R367] 回溯窗口: 热身段只喂状态机, 不进账本 ─────────────────────────
#
# 界面上参数框写着「回溯 1 年」, 卡片上却印「19 个月 / 375 个交易日」——
# **两个数都在屏幕上, 互相打脸。**


def test_R367_账本窗口就是用户要的那么长_不含热身段():
    """`_load_batch` 为了热身多取了 60 根、再按 1.7 折算成日历日, `years=1` 实际
    取到 ≈557 天。那些**只该喂给状态机**, 不该进账本。"""
    from app.services import flip_portfolio_run as run_mod

    # **日期得真的有 n 个。** 第一版拿 `12 个月 × 28 天` 凑, 只有 336 个, 再
    # `[:400]` 也还是 336 —— 与 400 根收盘价对不上, polars 直接拒绝建表, 于是
    # 整只票被跳过, 账本跑了 0 天。切片凑数组是这么翻车的。
    import datetime as _dt
    n = 400                       # 比 1 年该留的 250 多出一截

    # **只取工作日。** 第一版用连续日历日, 于是 250 根只跨了 8 个多月 —— 而
    # 真实的 250 个交易日跨满一年。那时逐月格数断言红了, 红的是**假数据不像
    # 真数据**, 不是代码。日线本来就只有工作日, 造数据就该照着造。
    dates, d = [], _dt.date(2025, 1, 1)
    while len(dates) < n:
        if d.weekday() < 5:
            dates.append(d.isoformat())
        d += _dt.timedelta(days=1)
    closes = [10.0 + (i % 7) * 0.3 for i in range(n)]
    assert len(dates) == len(closes) == n

    class _Repo:
        def resolve_asset_type(self, s): return "stock"
        def get_name_map(self, syms): return {s: s for s in syms}
        def get_daily_batch(self, syms, start, end, cols):
            import polars as pl
            return pl.DataFrame({
                "symbol": ["A"] * n, "date": dates, "close": closes,
                "signal_limit_up": [False] * n, "signal_limit_down": [False] * n,
            })
        def get_watchlist_live(self, asset):
            import polars as pl
            return pl.DataFrame({"symbol": [], "date": [], "close": []})

    out = run_mod.run(_Repo(), symbols=["A"], capital=100_000,
                      max_positions=1, years=1)
    want = run_mod._window_bars(1)
    assert want == 250
    assert out["stats"]["days"] == want, (
        f"账本跑了 {out['stats']['days']} 个交易日, 而用户要的是 {want} —— "
        "热身段漏进账本了")
    # 逐月那一排也跟着回到一年的量级(残月首尾各一, 所以 12~14 之间)
    assert 12 <= len(out["monthly"]) <= 14, f"逐月格数对不上一年: {len(out['monthly'])}"


def test_R367_数据本来就短时不补不裁():
    """新股只有 80 根日线时, 不许硬凑 250 根, 也不许把它裁没。"""
    from app.services import flip_portfolio_run as run_mod
    assert run_mod._window_bars(0.5) == 125
    assert run_mod._window_bars(3) == 750
    # 再短也得留得下一次转折
    assert run_mod._window_bars(0.001) == 2


def test_R367_窗口的第一天就是该在的那一天():
    """**这一条挡的是静默数据错位。**

    `_flatten` 是按下标把 steps / dates / closes 配对的。只切其中一条的话, 第
    150 天的状态会贴到第 0 天的日期上 —— 整条曲线是错的, **而且不报错**。
    变异电池打出来的洞。

    判据很硬: 账本第一天的日期, 必须正好是原始序列倒数第 `keep` 根那一天。
    """
    from app.services import flip_portfolio_run as run_mod

    import datetime as _dt
    n = 400
    dates, d = [], _dt.date(2025, 1, 1)
    while len(dates) < n:
        if d.weekday() < 5:
            dates.append(d.isoformat())
        d += _dt.timedelta(days=1)
    closes = [10.0 + (i % 7) * 0.3 for i in range(n)]

    class _Repo:
        def resolve_asset_type(self, s): return "stock"
        def get_name_map(self, syms): return {s: s for s in syms}
        def get_daily_batch(self, syms, start, end, cols):
            import polars as pl
            return pl.DataFrame({
                "symbol": ["A"] * n, "date": dates, "close": closes,
                "signal_limit_up": [False] * n, "signal_limit_down": [False] * n,
            })
        def get_watchlist_live(self, asset):
            import polars as pl
            return pl.DataFrame({"symbol": [], "date": [], "close": []})

    out = run_mod.run(_Repo(), symbols=["A"], capital=100_000, max_positions=1, years=1)
    keep = run_mod._window_bars(1)
    assert out["nav"], "一天都没跑"
    assert out["nav"][0]["date"] == dates[-keep], (
        f"账本第一天是 {out['nav'][0]['date']}, 该是 {dates[-keep]} —— "
        "几条序列没对齐, 状态被贴到了别的日子上")
    assert out["as_of"] == dates[-1], "最后一天不是最新那根"


def test_R367_五条序列一次切完_漏不掉():
    """分成几行各切各的, 就永远有「漏一条」这种可能 —— 而漏掉的后果是静默错位。

    并成一个 zip 之后**漏不掉**: 这是把一类 bug 变得写不出来, 不是靠守卫去追。
    """
    from tests.py_source import code_of
    from app.services import flip_portfolio_run as run_mod
    code = code_of(run_mod)
    assert "steps, dates, closes, lu, ld = (" in code, "五条序列不是一次切完的"
    assert "x[-keep:] for x in (steps, dates, closes," in code
    # 死分支不许回来: `x[-250:]` 对 80 个元素就是全部, 负切片自己兜住了
    assert "if len(dates) > keep" not in code, "那个死掉的特判又回来了"


def test_R367_切在算完之后_不是算之前():
    """**热身是真的需要**: `compute()` 头几十根算出来的状态还没稳。

    所以仍然拿整条序列去算, 只把账本的窗口收回来 —— 切的位置必须在 `compute`
    之后。切在取数那一层(少取)等于把热身也砍了, 状态机开头那一段就不准了。
    """
    from tests.py_source import code_of
    from app.services import flip_portfolio_run as run_mod
    code = code_of(run_mod)
    i_compute = code.index('compute(closes, dates, threshold)')
    i_cut = code.index("keep = _window_bars(years)")
    assert i_compute < i_cut, "窗口切在了 compute 之前 —— 热身段被砍掉了"
    # **还要挡住"又多加一刀"。** 只断言"那一刀在 compute 之后"是不够的: 在
    # compute 之前**另加**一刀 `df.tail(...)`, 上面那条照样成立(原来那刀还在),
    # 而热身段已经被砍了。变异电池当场打绿。所以钉的是 compute 之前那一段里
    # 一次裁剪都没有。
    head = code[:i_compute]
    for cut in (".tail(", "_window_bars(", "[-keep:]"):
        assert cut not in head, f"compute 之前就动了序列长度: {cut} —— 热身段被砍"
    # 取数那一层仍然多取热身
    assert "_WARMUP_BARS" in code and "years * 250 + _WARMUP_BARS" in code, \
        "取数不再多取热身了"


def test_R367_没有不存在的_api_health():
    """白名单里多一条不存在的路径不会报任何错, **它只会骗人**: 排查线上问题时
    照着它去开 `/api/health`, 拿到的是 SPA 兜底的 index.html, 于是把"端点不存在"
    误读成"路由没配上", 往完全错的方向查。这次就是这么栽的。
    """
    from fastapi.testclient import TestClient

    from app import main as main_mod
    assert "/api/health" not in main_mod._AUTH_WHITELIST_EXACT
    assert "/health" in main_mod._AUTH_WHITELIST_EXACT

    # 白名单里的每一条 exact 路径都得**真的能拿到东西**。
    #
    # 不去扫 `app.routes`: 新版 FastAPI 把 include 进来的路由收成一个
    # `_IncludedRouter` 节点(40 条里 34 条是它), **根本没有 `.path`** ——
    # 拿它当路由表扫, 会把一堆真实存在的路径判成"不存在"。所以改成真的发请求。
    #
    # 判据是**有没有落进 SPA 兜底**: 兜底给的是 index.html, 里面必然有
    # `id="root"`。落进兜底 = 这条路径没有后端路由。
    with TestClient(main_mod.app) as c:
        for path in main_mod._AUTH_WHITELIST_EXACT:
            r = c.get(path)
            assert r.status_code == 200, f"白名单路径拿不到: {path} → {r.status_code}"
            assert b'id="root"' not in r.content, \
                f"{path} 落进了 SPA 兜底 —— 它根本不是一条后端路由"
        # 探活那条真的能探活
        assert b'"status":"ok"' in c.get("/health").content, "/health 不是探活端点了"
        # 反过来钉住: `/api/health` **不是**探活端点(这正是这次把我带偏的那个)。
        # 它在测试环境会被鉴权以 403 NOT_INITIALIZED 挡掉(没进白名单), 线上登录
        # 后则落进 SPA 兜底 —— 两种情形不同, 但**都不会给出探活那份 JSON**,
        # 所以钉的是这一条, 不是某个状态码。
        assert b'"status":"ok"' not in c.get("/api/health").content, \
            "/api/health 竟然真成了探活端点? 那上面那条注释与白名单都要重写"
