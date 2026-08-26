"""回归测试: Free 档自选实时 symbols 超过 capability batch 上限时分批请求 (PR #46 问题 4)。"""
from contextlib import ExitStack
from unittest.mock import MagicMock, patch

import polars as pl

from app.services.quote_service import QuoteService
from app.tickflow.capabilities import Cap, CapabilityLimits, CapabilitySet


def _make_svc(engine_rules: dict) -> QuoteService:
    """创建最小可用的 QuoteService 实例 (跳过 __init__)。"""
    svc = QuoteService.__new__(QuoteService)
    svc._app_state = MagicMock()
    svc._repo = MagicMock()
    svc._lock = MagicMock()

    engine = MagicMock()
    engine.rules = engine_rules
    svc._app_state.monitor_engine = engine
    svc._app_state.repo = svc._repo

    svc._repo.get_index_symbol_set.return_value = {"000001.SH"}
    svc._repo.get_etf_symbol_set.return_value = set()
    return svc


def _run_fetch(svc, tf, watchlist: list[str], capset: CapabilitySet):
    """在完整 patch 环境下执行 _fetch_watchlist_quotes。"""
    with ExitStack() as stack:
        stack.enter_context(patch(
            "app.services.preferences.get_realtime_watchlist_symbols",
            return_value=watchlist,
        ))
        # [fork] 自选实时已改多 key 池化(get_realtime_client_pool), 单 key 即单元素池
        stack.enter_context(patch(
            "app.tickflow.client.get_realtime_client_pool", return_value=[tf],
        ))
        stack.enter_context(patch(
            "app.tickflow.policy.detect_capabilities", return_value=capset,
        ))
        stack.enter_context(patch("app.tickflow.rate_limits.sleep_between_batches"))
        # patch 分批之后的下游处理
        stack.enter_context(patch.object(
            QuoteService, "_build_daily", return_value=pl.DataFrame(),
        ))
        stack.enter_context(patch.object(
            QuoteService, "_build_quote_extra", return_value=pl.DataFrame(),
        ))
        stack.enter_context(patch.object(
            QuoteService, "_build_index_quotes", return_value=pl.DataFrame(),
        ))
        stack.enter_context(patch.object(QuoteService, "_broadcast_quote_updated"))
        stack.enter_context(patch.object(QuoteService, "_evaluate_monitors"))
        stack.enter_context(patch("app.services.quote_service._persist_last_fetch"))
        svc._fetch_watchlist_quotes()


def test_watchlist_batch_respects_capability_limit():
    """6 symbols / batch 5 → 分 2 批请求, 不整轮失败。"""
    engine_rules = {
        "r_idx": {"enabled": True, "asset_type": "index", "scope": "symbols",
                  "symbols": ["000001.SH"]},
    }
    svc = _make_svc(engine_rules)

    tf = MagicMock()
    tf.quotes.get.return_value = [
        {"symbol": "600000.SH", "last_price": 10.0, "prev_close": 9.9, "ext": {}},
    ]
    capset = CapabilitySet({Cap.QUOTE_BY_SYMBOL: CapabilityLimits(batch=5, rpm=60)})

    _run_fetch(svc, tf,
               ["600000.SH", "600001.SH", "600002.SH", "600003.SH", "600004.SH"],
               capset)

    # [fork R30 轮转窗口] 6 symbols 超过单轮容量(batch 5 × 1 key) → 本轮只拉 5 只,
    # 剩下的下一轮接着轮转 —— 不再是"一次全拉完分 2 批"
    assert tf.quotes.get.call_count == 1
    first_window = tf.quotes.get.call_args_list[0][1]["symbols"]
    assert len(first_window) == 5

    # 第二轮: 窗口从上次结尾接着转, 覆盖剩下的指数标的
    _run_fetch(svc, tf,
               ["600000.SH", "600001.SH", "600002.SH", "600003.SH", "600004.SH"],
               capset)
    assert tf.quotes.get.call_count == 2
    second_window = tf.quotes.get.call_args_list[1][1]["symbols"]
    assert "000001.SH" in second_window
    # 两轮合起来 6 只全覆盖
    assert set(first_window) | set(second_window) >= {
        "600000.SH", "600001.SH", "600002.SH", "600003.SH", "600004.SH", "000001.SH"}


def test_watchlist_batch_partial_failure_keeps_other_batches():
    """某一批拉取失败不影响其他批次 (已有股票实时刷新不丢失)。"""
    engine_rules = {
        "r_idx": {"enabled": True, "asset_type": "index", "scope": "symbols",
                  "symbols": ["000001.SH"]},
    }
    svc = _make_svc(engine_rules)

    tf = MagicMock()
    # [fork R30 轮转窗口] 第一轮(5 只)失败, 第二轮(轮转到剩余标的)成功 ——
    # 一轮失败不该让轮转卡死, 下一轮照常接着转
    tf.quotes.get.side_effect = [
        ConnectionError("timeout"),
        [{"symbol": "000001.SH", "last_price": 10.0, "prev_close": 9.9, "ext": {}}],
    ]
    capset = CapabilitySet({Cap.QUOTE_BY_SYMBOL: CapabilityLimits(batch=5, rpm=60)})

    _run_fetch(svc, tf,
               ["600000.SH", "600001.SH", "600002.SH", "600003.SH", "600004.SH"],
               capset)
    _run_fetch(svc, tf,
               ["600000.SH", "600001.SH", "600002.SH", "600003.SH", "600004.SH"],
               capset)

    # 两轮都被尝试 (第一轮失败不阻断第二轮)
    assert tf.quotes.get.call_count == 2


def test_watchlist_no_index_rules_no_extra_symbols():
    """无指数监控规则时, symbols 不追加指数标的。"""
    svc = _make_svc({})  # 无规则

    tf = MagicMock()
    tf.quotes.get.return_value = [
        {"symbol": "600000.SH", "last_price": 10.0, "prev_close": 9.9, "ext": {}},
    ]
    capset = CapabilitySet({Cap.QUOTE_BY_SYMBOL: CapabilityLimits(batch=5, rpm=60)})

    _run_fetch(svc, tf, ["600000.SH", "600001.SH"], capset)

    # 2 symbols / batch 5 → 1 批
    assert tf.quotes.get.call_count == 1
    assert tf.quotes.get.call_args_list[0][1]["symbols"] == ["600000.SH", "600001.SH"]
