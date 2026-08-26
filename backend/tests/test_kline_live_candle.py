"""[fork 增强] K线当日实时蜡烛注入: 免费自选档走实时叠加层。"""
import sys
import types
from datetime import date, timedelta
from types import SimpleNamespace

import polars as pl

# 本测试环境未装 TickFlow SDK; kline 模块的导入链会触及它, 打桩绕过(不影响被测逻辑)
if "tickflow" not in sys.modules:
    _stub = types.ModuleType("tickflow")
    _stub.AsyncTickFlow = object
    _stub.TickFlow = object
    sys.modules["tickflow"] = _stub

from app.api.kline import _maybe_inject_live_candle  # noqa: E402


def _request(overlay: pl.DataFrame | None, quote_service=None):
    repo = SimpleNamespace(
        get_watchlist_live=lambda asset_type="stock": overlay if overlay is not None else pl.DataFrame(),
        get_enriched_latest_asset=lambda asset: (pl.DataFrame(), None),
    )
    state = SimpleNamespace(repo=repo, quote_service=quote_service)
    return SimpleNamespace(app=SimpleNamespace(state=state))


def _overlay(d: date, close=11.9):
    return pl.DataFrame({
        "symbol": ["600722.SH"], "date": [str(d)],
        "open": [11.3], "high": [12.0], "low": [11.2], "close": [close],
        "volume": [990_000], "amount": [1.1e7], "change_pct": [0.055],
        "ma5": [11.5], "ma20": [10.9],
    })


def test_overlay_row_becomes_today_candle():
    """免费档: 叠加层有当日行 → 追加为今日实时蜡烛(is_live), 指标一并带上。"""
    rows = [{"date": "2026-08-14", "close": 11.28}]
    out = _maybe_inject_live_candle(_request(_overlay(date.today())), "600722.SH", rows)
    assert len(out) == 2
    live = out[-1]
    assert live["date"] == str(date.today())
    assert live["close"] == 11.9
    assert live["is_live"] is True
    assert live["ma5"] == 11.5, "叠加层的指标字段要带进蜡烛"


def test_stale_overlay_date_is_not_injected():
    """叠加层还是上一交易日的行(周末/未开实时)→ 不注入, 防重复蜡烛。"""
    rows = [{"date": "2026-08-14", "close": 11.28}]
    out = _maybe_inject_live_candle(
        _request(_overlay(date.today() - timedelta(days=3))), "600722.SH", rows)
    assert out == rows


def test_no_overlay_no_quote_service_keeps_rows():
    rows = [{"date": "2026-08-14", "close": 11.28}]
    out = _maybe_inject_live_candle(_request(None), "600722.SH", rows)
    assert out == rows


def test_existing_today_row_is_overwritten_not_duplicated():
    """收盘后日线已落盘, 叠加层仍在 → 覆盖今日行而不是再加一根。"""
    today = str(date.today())
    rows = [{"date": "2026-08-14", "close": 11.28}, {"date": today, "close": 11.5}]
    out = _maybe_inject_live_candle(_request(_overlay(date.today())), "600722.SH", rows)
    assert len(out) == 2
    assert out[-1]["close"] == 11.9


# ---------- [R74] 单票按需实时: 弹窗"点开就是最新" ----------
#
# 后台实时开关关着时叠加层没人喂, 弹窗 K 线只能停在最后一个同步日。
# refresh_single 给一个按需的单票通道 —— 这里守它的三条契约:
# 冷却(不烧配额)、无 key 静默失败(退回收盘口径, 不报错)、走同一条落盘链。

def _quote_service_for_single(monkeypatch, pool):
    """只桩掉网络边界; 共享层写入口全部装上警报器 —— 单票刷新碰到就算失败。"""
    from app.services.quote_service import QuoteService
    qs = QuoteService()
    shared_writes: list[str] = []
    qs._repo = SimpleNamespace(
        get_index_symbol_set=lambda: set(),
        get_etf_symbol_set=lambda: set(),
        merge_live_daily_asset=lambda asset, df: shared_writes.append(f"daily:{asset}"),
        update_watchlist_live=lambda asset, df: shared_writes.append(f"overlay:{asset}"),
    )
    monkeypatch.setattr(
        "app.tickflow.client.get_realtime_client_pool", lambda: pool)
    monkeypatch.setattr(
        qs, "_flush_live_enriched",
        lambda df, extra=None, asset_type="stock", merge=False, overlay=False:
            shared_writes.append(f"enriched:{asset_type}"))
    return qs, shared_writes


def _quote(sym="600722.SH", ts=None):
    import time as _time
    return {"symbol": sym, "open": 11.3, "high": 12.0, "low": 11.2,
            "last_price": 11.9, "volume": 990_000, "amount": 1.1e7,
            "prev_close": 11.28,
            "timestamp": ts if ts is not None else _time.time() * 1000}


def test_refresh_single_without_key_returns_false(monkeypatch):
    """无 key 静默 False —— 图表退回收盘口径, 绝不报错打断弹窗。"""
    qs, shared = _quote_service_for_single(monkeypatch, pool=[])
    assert qs.refresh_single("600722.SH") is False
    assert shared == []


def test_refresh_single_fills_the_isolated_cache_only(monkeypatch):
    """[R77 回归] 单票刷新只进独立缓存, **绝不碰任何共享层**。

    R74/R76 曾把它灌进自选叠加层 + merge 进 kline_daily —— 监控引擎在自选档
    拿叠加层当股票评估快照(日期还强制标今天), 于是随手点开过弹窗的票混着
    可能过期的价, 让异动监控和策略评估的是一份垃圾快照(用户实况)。
    """
    client = SimpleNamespace(quotes=SimpleNamespace(get=lambda symbols: [_quote()]))
    qs, shared = _quote_service_for_single(monkeypatch, pool=[client])

    assert qs.refresh_single("600722.sh") is True   # 顺带: 小写入参要被归一
    assert shared == [], f"单票刷新写了共享层: {shared}"

    row = qs.get_single_live("600722.SH")
    assert row is not None and row["close"] == 11.9
    # 日期来自行情自带的 quote_ts, 不是无条件的"今天"
    assert row["date"]
    # 口径: change_pct 小数制(与 enriched 一致)
    assert abs(row["change_pct"] - (11.9 / 11.28 - 1)) < 1e-9


def test_refresh_single_without_quote_ts_refuses_to_invent_a_date(monkeypatch):
    """行情没带时间戳就放弃 —— 宁可不显示, 不造日期。

    R74 的 _build_daily 会把日期无条件标 cn_today: 非交易时段点弹窗
    等于造出一根"幽灵交易日"蜡烛。
    """
    q = _quote(); q["timestamp"] = None
    client = SimpleNamespace(quotes=SimpleNamespace(get=lambda symbols: [q]))
    qs, shared = _quote_service_for_single(monkeypatch, pool=[client])
    assert qs._pull_single("600722.SH") is False
    assert qs.get_single_live("600722.SH") is None
    assert shared == []


def test_refresh_single_cooldown_skips_the_network(monkeypatch):
    """15s 冷却期内不再打网络 —— 反复开关弹窗不该烧配额。"""
    calls: list[int] = []

    def _get(symbols):
        calls.append(1)
        return [_quote(symbols[0])]

    client = SimpleNamespace(quotes=SimpleNamespace(get=_get))
    qs, _ = _quote_service_for_single(monkeypatch, pool=[client])
    assert qs.refresh_single("600722.SH") is True
    assert qs.refresh_single("600722.SH") is True     # 冷却期内: 视为已最新
    assert len(calls) == 1, "冷却期内第二次不该再发请求"


def test_refresh_single_failure_still_occupies_the_cooldown(monkeypatch):
    """失败也占冷却位 —— 坏 key 被连点时不该变成请求风暴。"""
    calls: list[int] = []

    def _boom(symbols):
        calls.append(1)
        raise RuntimeError("key 无效")

    client = SimpleNamespace(quotes=SimpleNamespace(get=_boom))
    qs, _ = _quote_service_for_single(monkeypatch, pool=[client])
    assert qs.refresh_single("600722.SH") is False
    assert qs.refresh_single("600722.SH") is True     # 冷却期内直接短路
    assert len(calls) == 1


# ---------- [R76] 弹窗不再白等网络: 后台拉取 + 空闲 key ----------

def test_background_refresh_returns_started_then_fresh(monkeypatch):
    """第一次认领返回 started(后台在拉), 冷却期内再问返回 fresh —— 前端
    靠这两个词定节奏: started 才补取, fresh 停手, 不会打转。"""
    import threading as _threading

    from app.services.quote_service import QuoteService
    qs = QuoteService()
    qs._repo = SimpleNamespace()
    client = SimpleNamespace(quotes=SimpleNamespace(get=lambda symbols: []))
    monkeypatch.setattr("app.tickflow.client.get_realtime_client_pool", lambda: [client])

    pulled = _threading.Event()
    monkeypatch.setattr(QuoteService, "_pull_single",
                        lambda self, sym: pulled.set() or True)

    assert qs.refresh_single_background("600722.SH") == "started"
    assert pulled.wait(timeout=5), "后台线程要真的去拉"
    assert qs.refresh_single_background("600722.SH") == "fresh"


def test_background_refresh_without_key_says_off(monkeypatch):
    from app.services.quote_service import QuoteService
    qs = QuoteService()
    qs._repo = SimpleNamespace()
    monkeypatch.setattr("app.tickflow.client.get_realtime_client_pool", lambda: [])
    assert qs.refresh_single_background("600722.SH") == "off"


def test_single_pull_prefers_an_idle_key():
    """后台轮询占着的 key 不去挤 —— 挤上的就是限流等待, 弹窗跟着慢。"""
    from app.services.quote_service import QuoteService
    qs = QuoteService()
    a, b, c = object(), object(), object()
    qs._busy_key_idx = {0, 2}
    for _ in range(10):
        assert qs._pick_single_client([a, b, c]) is b, "只有 1 号 key 空闲"
    # 全忙时退化为随便挑一个, 不是拒绝服务
    qs._busy_key_idx = {0, 1, 2}
    assert qs._pick_single_client([a, b, c]) in (a, b, c)
