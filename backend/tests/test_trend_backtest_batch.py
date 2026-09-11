"""[R312] 全量六态阈值回测 —— 批量口径必须与逐只逐值相同, 批量写必须全进全不进。

用户: 「在刷新后面加个一键回测所有个股」。

## 这一组守的三件事

① **批量与逐只算出来的是同一个东西。** 批量为了省 IO 走的是一趟
   `get_daily_batch` 而不是 N 趟 `_load_symbol_window`(R156 给历史胜率走通过
   的那条路)。省 IO 不许顺带改口径 —— 一旦两条路给出不同的建议阈值, 用户在
   单只弹窗里看到 8%、在全量表里看到 9%, 而**没有任何东西会报错**。

② **批量写要么全进要么全不进。** 循环调单只那个函数的话, 每次都是
   load → 改一条 → save; 中途抛异常就留下半套(前 80 只改了、后 86 只没改),
   而用户看到的只有一个失败提示。

③ **样本不足的票不许被硬荐。** `rule_suggest` 在趋势段太少时会明说
   「不足以支撑调参」并回落默认值 —— 那个标记必须一路传到界面, 否则
   「建议 6%」会被读成"算过了, 就该 6%", 而真相是"算不出来"。
"""
from __future__ import annotations

import json

import pytest

from app.indicators import livermore as lv
from app.services import livermore_service as svc


# ================================================================
# ① 批量与逐只同口径
# ================================================================

class _FakeRepo:
    """只提供这一组用得到的两个方法。收盘序列由构造时给定, 完全可控 ——
    **不随机**: 造的是几条具名走势(单边上行 / 震荡 / 深 V), 见 AGENTS.md 那条纪律。
    """

    def __init__(self, series: dict[str, list[float]]):
        self.series = series
        self.batch_calls = 0
        self.single_calls = 0

    def resolve_asset_type(self, symbol: str) -> str:
        return "stock"

    def _frame(self, syms):
        import polars as pl
        rows = []
        for s in syms:
            cs = self.series.get(s, [])
            for i, c in enumerate(cs):
                rows.append({"symbol": s, "date": f"2025-{1 + i // 28:02d}-{1 + i % 28:02d}",
                             "close": float(c)})
        if not rows:
            return pl.DataFrame()
        return pl.DataFrame(rows)

    def get_daily_batch(self, symbols, start, end, columns):
        self.batch_calls += 1
        return self._frame(list(symbols))

    def get_daily_asset(self, asset_type, symbol, start, end, columns=None):
        self.single_calls += 1
        return self._frame([symbol]).select("date", "close")


def _ramp(n: int, step: float) -> list[float]:
    return [round(10.0 * (1 + step) ** i, 4) for i in range(n)]


def _wave(n: int, amp: float, period: int) -> list[float]:
    import math
    return [round(10.0 * (1 + amp * math.sin(2 * math.pi * i / period)), 4) for i in range(n)]


def _deep_v(n: int) -> list[float]:
    half = n // 2
    down = [round(10.0 * (1 - 0.012) ** i, 4) for i in range(half)]
    return down + [round(down[-1] * (1 + 0.015) ** i, 4) for i in range(n - half)]


SERIES = {
    "600000.SH": _ramp(200, 0.006),
    "600001.SH": _wave(200, 0.18, 45),
    "600002.SH": _deep_v(200),
}


def test_R312_批量与逐只给出的窗口逐值相同():
    """省 IO 不许顺带改口径 —— 窗口不同的话, 后面每一个数都不同。"""
    repo = _FakeRepo(SERIES)
    got = svc._windows_for_symbols(repo, list(SERIES))
    for sym in SERIES:
        one = svc._load_symbol_window(repo, sym)
        assert got[sym] == one, f"{sym} 的窗口两条路不一致"


def test_R312_批量真的只读一趟():
    """这条是整个批量存在的理由 —— 退化成 N 趟的话不如直接循环调单只。"""
    repo = _FakeRepo(SERIES)
    svc._windows_for_symbols(repo, list(SERIES))
    assert repo.batch_calls == 1, f"批量读了 {repo.batch_calls} 趟"
    assert repo.single_calls == 0, "还在逐只回退 —— 股票该全部走批量那条路"


def test_R312_批量给出的建议与逐只完全一致(tmp_path, monkeypatch):
    """**最要紧的一条。** 两条路给出不同的建议阈值时, 用户在单只弹窗看到 8%、
    在全量表里看到 9%, 而没有任何东西会报错。"""
    monkeypatch.setattr(svc, "_store_path", lambda: tmp_path / "livermore.json")
    repo = _FakeRepo(SERIES)
    out = svc.batch_backtest(repo, list(SERIES))
    by_sym = {r["symbol"]: r for r in out["rows"]}
    assert set(by_sym) == set(SERIES), f"有票没跑出来: {out['skipped']}"
    for sym in SERIES:
        closes, dates = svc._load_symbol_window(repo, sym)
        rule = lv.rule_suggest(lv.backtest_thresholds(closes, dates))
        assert by_sym[sym]["suggested"] == rule["threshold"], f"{sym} 的建议阈值两条路不一致"
        assert by_sym[sym]["reason"] == rule["reason"]
        assert by_sym[sym]["sample_insufficient"] == rule["sample_insufficient"]


def test_R312_两边的多赚都取自同一张网格(tmp_path, monkeypatch):
    """「现在多赚 / 改后多赚」是这张表唯一的决策依据 —— 只说「建议 8%」是不可
    证伪的一句话。两个数必须真的来自那一行, 不许另算一套。"""
    monkeypatch.setattr(svc, "_store_path", lambda: tmp_path / "livermore.json")
    repo = _FakeRepo(SERIES)
    out = svc.batch_backtest(repo, list(SERIES))
    for r in out["rows"]:
        closes, dates = svc._load_symbol_window(repo, r["symbol"])
        grid = {round(g["threshold"], 4): g for g in lv.backtest_thresholds(closes, dates)}
        assert r["excess_suggested"] == grid[round(r["suggested"], 4)]["excess"]
        assert r["excess_now"] == grid[round(r["current_threshold"], 4)]["excess"]


def test_R312_数据不足的票点名报出去而不是静默丢掉(tmp_path, monkeypatch):
    """"跑了但没结果"与"根本没跑"在界面上长得一模一样 —— R246/R248 栽过两次的
    正是这个形状。"""
    monkeypatch.setattr(svc, "_store_path", lambda: tmp_path / "livermore.json")
    repo = _FakeRepo({**SERIES, "600003.SH": _ramp(10, 0.01)})   # 10 天, 远不够
    out = svc.batch_backtest(repo, list(SERIES) + ["600003.SH"])
    assert [x["symbol"] for x in out["skipped"]] == ["600003.SH"]
    assert str(svc._MIN_DAYS) in out["skipped"][0]["why"], "没说清为什么没跑"
    assert "600003.SH" not in {r["symbol"] for r in out["rows"]}


# ================================================================
# ② 批量写全进全不进
# ================================================================

def _store(tmp_path) -> dict:
    p = tmp_path / "livermore.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def test_R312_批量写一次落盘(tmp_path, monkeypatch):
    monkeypatch.setattr(svc, "_store_path", lambda: tmp_path / "livermore.json")
    saves = {"n": 0}
    real = svc._save_store
    monkeypatch.setattr(svc, "_save_store", lambda d: (saves.__setitem__("n", saves["n"] + 1), real(d))[1])
    out = svc.set_thresholds([
        {"symbol": "600000.SH", "threshold": 0.08, "source": "rule"},
        {"symbol": "600001.SH", "threshold": 0.11, "source": "rule"},
        {"symbol": "600002.SH", "threshold": 0.05, "source": "rule"},
    ])
    assert saves["n"] == 1, f"落了 {saves['n']} 次盘 —— 批量的意义就在于只落一次"
    assert out["applied"] == ["600000.SH", "600001.SH", "600002.SH"]
    ov = _store(tmp_path)["overrides"]
    assert {k: v["threshold"] for k, v in ov.items()} == {
        "600000.SH": 0.08, "600001.SH": 0.11, "600002.SH": 0.05}


def test_R312_非法项被点名而不是整批失败(tmp_path, monkeypatch):
    """一只票的代码是空的, 不该把另外 165 只一起拖下水; 但也不许静默吞掉。"""
    monkeypatch.setattr(svc, "_store_path", lambda: tmp_path / "livermore.json")
    out = svc.set_thresholds([
        {"symbol": "600000.SH", "threshold": 0.08},
        {"symbol": "", "threshold": 0.08},
        {"symbol": "600001.SH", "threshold": "八个点"},
    ])
    assert out["applied"] == ["600000.SH"]
    assert len(out["skipped"]) == 2, f"被吞掉了: {out}"
    assert {x["symbol"] for x in out["skipped"]} == {"", "600001.SH"}


def test_R312_threshold_为空是清除不是写零(tmp_path, monkeypatch):
    """`None` 与 `0` 差得很远: 前者是"恢复默认", 后者会被 clamp 成 1% ——
    那只票从此每天都在翻转。"""
    monkeypatch.setattr(svc, "_store_path", lambda: tmp_path / "livermore.json")
    svc.set_thresholds([{"symbol": "600000.SH", "threshold": 0.09}])
    assert "600000.SH" in _store(tmp_path)["overrides"]
    out = svc.set_thresholds([{"symbol": "600000.SH", "threshold": None}])
    assert out["cleared"] == ["600000.SH"]
    assert "600000.SH" not in _store(tmp_path)["overrides"]
    assert svc.get_effective_threshold("600000.SH")[1] == "default"


def test_R312_批量写与逐只写落出来的结构一样(tmp_path, monkeypatch):
    """两条路写同一个文件。字段对不上的话, 先用批量再用单只就会读出半套。"""
    monkeypatch.setattr(svc, "_store_path", lambda: tmp_path / "livermore.json")
    svc.set_threshold("600000.SH", 0.08, "rule")
    one = dict(_store(tmp_path)["overrides"]["600000.SH"])
    svc.set_thresholds([{"symbol": "600001.SH", "threshold": 0.08, "source": "rule"}])
    many = dict(_store(tmp_path)["overrides"]["600001.SH"])
    assert set(one) == set(many), f"两条路写出的字段不同: {sorted(one)} vs {sorted(many)}"
    assert one["threshold"] == many["threshold"] and one["source"] == many["source"]


def test_R312_一条都没有时不去碰那个文件(tmp_path, monkeypatch):
    """空列表不该把 store 重写一遍 —— 那会无谓地动 mtime, 也给不出任何东西。"""
    monkeypatch.setattr(svc, "_store_path", lambda: tmp_path / "livermore.json")
    out = svc.set_thresholds([])
    assert out == {"applied": [], "cleared": [], "skipped": []}
    assert not (tmp_path / "livermore.json").exists(), "空批量把文件建出来了"


# ================================================================
# ③ 接口这一层
# ================================================================

@pytest.fixture()
def client():
    """只挂这一个 router 的裸 app —— 与 `test_mining_api` 同一套。

    走 `app.main` 那个完整 app 的话会先撞上鉴权中间件(403), 测到的就不是
    这两个接口自己的校验了。
    """
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.stock_analysis import router

    app = FastAPI()
    app.include_router(router)   # router 自带 /api/stock-analysis 前缀
    app.state.repo = _FakeRepo(SERIES)
    return TestClient(app)


def test_R312_批量回测接口不调_AI():
    """**这条是这个按钮能挨着「刷新」放的全部理由。**

    单只那个接口有 `use_ai`, 默认 True; 批量根本不该有这个开关 ——
    166 只票就是 166 次调用。哪天有人给它加回来, 这条会红。
    """
    import inspect
    from app.api import stock_analysis as m
    src = inspect.getsource(m.trend_backtest_batch)
    code = "\n".join(ln for ln in src.splitlines() if not ln.lstrip().startswith("#"))
    assert "use_ai" not in code, "批量回测接口把 AI 开关加回来了"
    assert "ai_provider" not in code and "generate_ai_text" not in code
    # 服务层同样不许碰 AI
    svc_src = inspect.getsource(svc.batch_backtest)
    svc_code = "\n".join(ln for ln in svc_src.splitlines() if not ln.lstrip().startswith("#"))
    assert "generate_ai_text" not in svc_code, "批量回测在服务层调了 AI"
    # 批量回测是只读的 —— 它绝不能顺手把阈值写下去
    assert "set_threshold" not in svc_code, (
        "批量回测把阈值写下去了 —— 它只回测, 落盘是另一个动作(而且没有撤销)"
    )


def test_R312_一次请求有上限(client):
    from app.api import stock_analysis as m
    too_many = [f"60{i:04d}.SH" for i in range(m._BATCH_MAX + 1)]
    r = client.post("/api/stock-analysis/trend/backtest-batch", json={"symbols": too_many})
    assert r.status_code == 400 and str(m._BATCH_MAX) in r.json()["detail"]


def test_R312_批量应用的_source_受限(client):
    r = client.put("/api/stock-analysis/trend/threshold-batch",
                   json={"items": [{"symbol": "600000.SH", "threshold": 0.08, "source": "乱写"}]})
    assert r.status_code == 400, "source 没校验 —— 台账里会混进来路不明的来源"


def test_R312_空批量被挡住(client):
    r = client.put("/api/stock-analysis/trend/threshold-batch", json={"items": []})
    assert r.status_code == 400
