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
