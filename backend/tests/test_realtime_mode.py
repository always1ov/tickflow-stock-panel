"""回归测试: 实时行情模式判定。

[fork R92] 上游 v0.2.2 移除了免费档自选实时(watchlist), 本 fork 明确保留 ——
免费档多 key 轮换自选实时是 fork 主干功能(R30/R35), 用户即以此形态运行。
此测试锁定 fork 语义, 防止未来同步上游时该通路被无意砍掉。
"""
from app.services.quote_service import QuoteService


def test_custom_realtime_source_is_full_market(monkeypatch):
    """自定义实时源(如 fuyao)无视 TickFlow 档位, 恒为全市场。"""
    from app.services import preferences
    monkeypatch.setattr(preferences, "get_realtime_data_provider", lambda: "fuyao")
    monkeypatch.setattr(QuoteService, "_current_tier", lambda: "free")
    assert QuoteService.realtime_mode() == "full_market"


def test_tickflow_free_keeps_watchlist_realtime(monkeypatch):
    """[fork] TickFlow 免费档 = 自选实时(watchlist), 不随上游 v0.2.2 下线。"""
    from app.services import preferences
    monkeypatch.setattr(preferences, "get_realtime_data_provider", lambda: "tickflow")
    monkeypatch.setattr(QuoteService, "_current_tier", lambda: "free")
    assert QuoteService.realtime_mode() == "watchlist"
    assert QuoteService.is_realtime_allowed() is True


def test_tickflow_no_key_has_no_realtime(monkeypatch):
    """无 key = 无实时。"""
    from app.services import preferences
    monkeypatch.setattr(preferences, "get_realtime_data_provider", lambda: "tickflow")
    monkeypatch.setattr(QuoteService, "_current_tier", lambda: "none")
    assert QuoteService.realtime_mode() == "none"
    assert QuoteService.is_realtime_allowed() is False


def test_tickflow_paid_is_full_market(monkeypatch):
    from app.services import preferences
    monkeypatch.setattr(preferences, "get_realtime_data_provider", lambda: "tickflow")
    monkeypatch.setattr(QuoteService, "_current_tier", lambda: "pro")
    assert QuoteService.realtime_mode() == "full_market"
