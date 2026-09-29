"""[R562] 虚拟账户「跟六态转折」—— 接上作者账本的那一半。

判定在 flip_follow.decide(已单独钉住); 这里钉的是: 单子真的挂进了作者的账本、
第二天盘后结算按**开盘价**成交、重跑同一天不重复下单、封板没成交次日重挂、
方向反了撤单, 以及「跟六态转折」作为作者自动跟单里的一种规则能建、能认出来。
"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import polars as pl
import pytest

from app.services import flip_follow as ff
from app.services import flip_follow_run as run
from app.services.flip_trades import BEAR, BULL
from app.strategy import paper, paper_auto
from app.tickflow.repository import DataStore, KlineRepository

SYM = "600519.SH"
D0 = date(2026, 9, 25)      # 周五
D1 = date(2026, 9, 28)      # 周一: 转折日
D2 = date(2026, 9, 29)      # 周二: 次日开盘成交
D3 = date(2026, 9, 30)


def _write_daily(tmp_path: Path, rows: list[tuple[date, float, float]]) -> None:
    repo = KlineRepository(DataStore(tmp_path))
    repo.append_daily(pl.DataFrame({
        "symbol": [SYM] * len(rows),
        "date": [r[0] for r in rows],
        "open": [r[1] for r in rows],
        "high": [max(r[1], r[2]) for r in rows],
        "low": [min(r[1], r[2]) for r in rows],
        "close": [r[2] for r in rows],
        "volume": [10000.0] * len(rows),
        "amount": [r[2] * 10000.0 for r in rows],
    }))


def _evening(monkeypatch, d: date) -> None:
    """把「现在」钉在 d 这天收盘后 —— 盘后管道跑的时刻。不钉的话下单时间取真实时钟,
    撞上测试里的某一天就会被作者「开盘后才下的单留到下一交易日」那条规矩拦住。"""
    monkeypatch.setattr(paper, "cn_today", lambda: d)
    monkeypatch.setattr(paper, "_now_iso", lambda: f"{d.isoformat()}T18:00:00+08:00")


@pytest.fixture
def acc(tmp_path, monkeypatch):
    """一个转折账户: 10 万本金、转折账户费率、最多 2 只。"""
    _evening(monkeypatch, D1)
    paper.create_account(tmp_path, 100_000, **ff.FEES)
    paper_auto.create_auto_rule(tmp_path, {"name": "跟六态转折", "match_kind": ff.KIND,
                                           "max_positions": 2})
    return tmp_path


def _flip(side: str, close: float, flipped: bool = True) -> dict:
    return {SYM: {"side": side, "flipped": flipped, "close": close}}


def _orders(data_dir: Path) -> list[dict]:
    return paper.load_orders(data_dir)


def test_转多当晚挂次日开盘买单_第二天按开盘价成交(acc):
    _write_daily(acc, [(D0, 10.0, 10.0), (D1, 10.0, 10.0), (D2, 10.5, 11.0)])
    out = run.follow_day(acc, D1.isoformat(), rows=_flip(BULL, 10.0))
    assert [b["symbol"] for b in out["buys"]] == [SYM]
    [o] = _orders(acc)
    assert (o["side"], o["order_type"], o["status"]) == ("buy", "next_open", "pending")
    assert o["source"].startswith("auto:arule_")

    # 当晚结算不成交(开盘价早就打印过了), 第二天盘后按 D2 开盘价成交
    assert paper.settle_day(acc, D1.isoformat())["filled"] == 0
    assert paper.settle_day(acc, D2.isoformat())["filled"] == 1
    [o] = _orders(acc)
    assert o["status"] == "filled"
    assert o["fill_price"] == pytest.approx(10.5 * 1.0005, abs=1e-4)


def test_重跑同一天不重复下单(acc):
    _write_daily(acc, [(D0, 10.0, 10.0), (D1, 10.0, 10.0)])
    run.follow_day(acc, D1.isoformat(), rows=_flip(BULL, 10.0))
    again = run.follow_day(acc, D1.isoformat(), rows=_flip(BULL, 10.0))
    assert again["buys"] == [] and len(_orders(acc)) == 1


def test_今天买进_今晚转空_也能挂次日开盘卖单(acc, monkeypatch):
    """T+1: 今天开盘买的, 明天开盘就能卖 —— 今晚挂单不该被当天的可卖数拦住。"""
    _write_daily(acc, [(D0, 10.0, 10.0), (D1, 10.0, 10.0), (D2, 10.5, 9.0), (D3, 8.8, 9.0)])
    run.follow_day(acc, D1.isoformat(), rows=_flip(BULL, 10.0))
    _evening(monkeypatch, D2)
    paper.settle_day(acc, D2.isoformat())
    out = run.follow_day(acc, D2.isoformat(), rows=_flip(BEAR, 9.0))
    assert out["failed"] == []
    assert [s["symbol"] for s in out["sells"]] == [SYM]
    _evening(monkeypatch, D3)
    paper.settle_day(acc, D3.isoformat())
    assert paper.load_positions(acc) == {} or paper.load_positions(acc)[SYM]["qty"] == 0


def test_开盘涨停没买进_方向没变就次日重挂(acc, monkeypatch):
    # D2 开盘直接涨停(10 × 1.1 = 11.0), 买不进
    _write_daily(acc, [(D0, 10.0, 10.0), (D1, 10.0, 10.0), (D2, 11.0, 11.0)])
    run.follow_day(acc, D1.isoformat(), rows=_flip(BULL, 10.0))
    _evening(monkeypatch, D2)
    paper.settle_day(acc, D2.isoformat())
    assert _orders(acc)[0]["status"] == "expired"
    out = run.follow_day(acc, D2.isoformat(), rows=_flip(BULL, 11.0, flipped=False))
    [buy] = out["buys"]
    assert buy["since"] == D1.isoformat()
    assert [o["status"] for o in _orders(acc)].count("pending") == 1


def test_在途买单遇上反向转折_撤单(acc):
    _write_daily(acc, [(D0, 10.0, 10.0), (D1, 10.0, 10.0)])
    run.follow_day(acc, D1.isoformat(), rows=_flip(BULL, 10.0))
    out = run.follow_day(acc, D1.isoformat(), rows=_flip(BEAR, 10.0))
    assert out["cancels"] == [SYM]
    assert _orders(acc)[0]["status"] == "cancelled"
    assert run.load_state(acc)["log"][-1]["reason"] == ff.WHY_VOIDED


def test_没有转折规则的账户_什么也不做(tmp_path, monkeypatch):
    _evening(monkeypatch, D1)
    paper.create_account(tmp_path, 100_000)
    assert run.follow_day(tmp_path, D1.isoformat(), rows=_flip(BULL, 10.0)) is None
    assert _orders(tmp_path) == []


def test_转折规则_每个账户只能有一条(acc):
    with pytest.raises(ValueError, match="只能有一条"):
        paper_auto.create_auto_rule(acc, {"name": "再来一条", "match_kind": ff.KIND,
                                          "max_positions": 3})


def test_转折规则_不接监控事件(acc):
    ev = [{"symbol": SYM, "price": 10.0, "rule_id": ff.MATCH_ID, "source": "strategy",
           "strategy_id": ff.MATCH_ID}]
    assert paper_auto.on_rule_events(acc, ev) == []


@pytest.mark.parametrize("n", [0, 51, "3", None])
def test_转折规则_同时持有上限必须是1到50(tmp_path, n):
    with pytest.raises(ValueError):
        paper_auto.create_auto_rule(tmp_path, {"name": "x", "match_kind": ff.KIND,
                                               "max_positions": n})



def test_T加1放宽只对次日开盘单_今天买的今天收盘仍然卖不了(acc, monkeypatch):
    _write_daily(acc, [(D0, 10.0, 10.0), (D1, 10.0, 10.0), (D2, 10.5, 10.6)])
    run.follow_day(acc, D1.isoformat(), rows=_flip(BULL, 10.0))
    _evening(monkeypatch, D2)
    paper.settle_day(acc, D2.isoformat())
    qty = paper.load_positions(acc)[SYM]["qty"]
    for order_type in ("close", "market"):
        _, err = paper.create_order(acc, SYM, "sell", qty=qty, order_type=order_type)
        assert err is not None and "可卖数量不足" in err


def test_API_能建跟六态转折规则(acc):
    from types import SimpleNamespace

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api.paper import router

    app = FastAPI()
    app.include_router(router)
    app.state.repo = SimpleNamespace(store=SimpleNamespace(data_dir=acc))
    client = TestClient(app)
    paper.create_account(acc, 50_000, account_id="flip2", **ff.FEES)
    r = client.post("/api/paper/auto_rules?account=flip2",
                    json={"name": "跟六态转折", "match_kind": ff.KIND, "max_positions": 5})
    assert r.status_code == 200, r.text
    rule = r.json()["rule"]
    assert (rule["match_kind"], rule["max_positions"], rule["order_type"]) == (ff.KIND, 5, "next_open")
    assert "size_value" not in rule and "side" not in rule
    # 作者原来那种规则照旧要 size_value
    r = client.post("/api/paper/auto_rules?account=flip2",
                    json={"name": "x", "match_kind": "rule", "match_id": "r1"})
    assert r.status_code == 400


def test_取数_最后一天暴跌_认出转空_收盘价取不复权(tmp_path, monkeypatch):
    """load_rows 走的是个股页同一条路(livermore_service 窗口 + trend_days)。
    造 80 天稳步上涨、最后一天跌 15%: 前一天必在多头, 最后一天必在空头且是转折日。"""
    from app.services import livermore_service

    monkeypatch.setattr(livermore_service, "get_effective_threshold", lambda s: (0.06, "test"))
    start = date(2026, 5, 1)
    days = [start + timedelta(days=i) for i in range(120)]
    days = [d for d in days if d.weekday() < 5][:81]
    closes = [10.0 * (1.01 ** i) for i in range(80)]
    closes.append(closes[-1] * 0.85)
    _write_daily(tmp_path, list(zip(days, closes, closes, strict=True)))
    repo = KlineRepository(DataStore(tmp_path))
    monkeypatch.setattr(repo, "resolve_asset_type", lambda s: "stock")
    # 批量接口生产上读「增强日线」, 测试库里没有; 换成直接给原始日线, 窗口裁剪与判定仍走真路
    raw = pl.DataFrame({"symbol": [SYM] * len(days), "date": days, "close": closes})
    monkeypatch.setattr(repo, "get_daily_batch", lambda syms, start, end, cols: raw.select(cols))

    # 原始日 K 已经到了、判定用的窗口还差最后一天(增强日线没跟上) → 不出行,
    # 不拿前一天的状态冒充今天
    monkeypatch.setattr(repo, "get_daily_batch", lambda syms, start, end, cols: raw.head(-1).select(cols))
    assert run.load_rows(repo, tmp_path, [SYM], days[-1].isoformat()) == {}
    monkeypatch.setattr(repo, "get_daily_batch", lambda syms, start, end, cols: raw.select(cols))
    rows = run.load_rows(repo, tmp_path, [SYM], days[-1].isoformat())
    assert rows[SYM]["side"] == BEAR and rows[SYM]["flipped"] is True
    assert rows[SYM]["close"] == pytest.approx(closes[-1])
