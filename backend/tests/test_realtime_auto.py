"""[fork R118] 实时行情自动开关: 时段判定 + 边沿触发 + 收盘定版宽限。"""
from __future__ import annotations

from datetime import datetime

import pytest

from app.services import realtime_schedule as rs


# ------------------------------------------------------------ 时段判定

# 2026-09-02 是周三, 2026-09-05 是周六
@pytest.mark.parametrize("hhmm,expect", [
    ((9, 0), False),      # 开盘前
    ((9, 14), False),
    ((9, 15), True),      # 集合竞价即开
    ((10, 30), True),
    ((11, 45), True),     # 午休不关 —— 11:30 午休定版需要线程活着
    ((14, 59), True),
    ((15, 4), True),      # 收盘后留 5 分钟给收盘定版
    ((15, 5), False),
    ((20, 0), False),
])
def test_desired_state_within_trading_day(hhmm, expect):
    now = datetime(2026, 9, 2, *hhmm)
    assert rs.desired_state(now, True) is expect


def test_holiday_is_always_off():
    assert rs.desired_state(datetime(2026, 9, 2, 10, 30), False) is False


def test_weekend_is_off_even_when_probe_unknown():
    assert rs.desired_state(datetime(2026, 9, 5, 10, 30), None) is False


def test_unknown_probe_on_weekday_keeps_it_on():
    """探针未知时沿用「维持周几近似」—— 宁可多开一段, 也不在真交易日关掉。"""
    assert rs.desired_state(datetime(2026, 9, 2, 10, 30), None) is True


def test_grace_window():
    assert rs.in_grace_window(datetime(2026, 9, 2, 15, 6)) is True
    assert rs.in_grace_window(datetime(2026, 9, 2, 15, 40)) is False
    assert rs.in_grace_window(datetime(2026, 9, 2, 14, 0)) is False
    assert rs.in_grace_window(datetime(2026, 9, 5, 15, 6)) is False   # 周六


# ------------------------------------------------------------ 边沿触发


class _FakeRepo:
    """[同步上游 ed2f81c] 首用门禁判据: 日K/enriched 最近日期。"""

    def __init__(self, empty=False):
        self._empty = empty

    def latest_daily_date(self):
        return None if self._empty else "2026-09-01"

    def latest_enriched_date(self):
        return None


class _FakeService:
    """只保留自动开关需要的那几个成员, 不碰真正的轮询线程。"""

    _AUTO_TICK_S = 30.0
    _final_sync_key = staticmethod(lambda phase: ("2026-09-02", "close") if phase == "close_final" else None)

    def __init__(self, *, has_data=True):
        self._repo = _FakeRepo() if has_data else _FakeRepo(empty=True)
        self._enabled = False
        self._auto_last_desired = None
        self._auto_pref_last = None
        self._final_sync_done = set()
        self.calls: list[str] = []

    def is_realtime_allowed(self):
        return True

    def enable(self):
        self._enabled = True
        self.calls.append("enable")
        return True

    def stop(self):
        self._enabled = False
        self.calls.append("stop")

    def disable(self):        # 不该被自动开关调用: 它会清掉自选实时叠加层
        self.calls.append("disable")

    # 被测方法直接借真实现
    from app.services.quote_service import QuoteService as _QS
    _auto_tick = _QS._auto_tick
    _final_sync_pending = _QS._final_sync_pending
    _has_local_data = _QS._has_local_data
    notify_auto_pref_changed = _QS.notify_auto_pref_changed


@pytest.fixture
def svc(monkeypatch, tmp_path):
    from app.config import settings
    from app.services import preferences
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    preferences._invalidate_cache()
    from app.services import trading_day
    monkeypatch.setattr(trading_day, "is_trading_day", lambda now=None: True)
    return _FakeService()


def _at(svc, monkeypatch, dt):
    import app.market_time as mt
    monkeypatch.setattr(mt, "cn_now", lambda: dt)
    svc._auto_tick()


def test_auto_off_does_nothing(svc, monkeypatch):
    _at(svc, monkeypatch, datetime(2026, 9, 2, 10, 0))
    assert svc.calls == [] and svc._enabled is False


def test_auto_turns_on_and_off_on_edges(svc, monkeypatch):
    from app.services import preferences
    preferences.set_realtime_auto(True)

    _at(svc, monkeypatch, datetime(2026, 9, 2, 9, 0))     # 开盘前
    assert svc.calls == [] and svc._enabled is False

    _at(svc, monkeypatch, datetime(2026, 9, 2, 9, 15))    # 开盘边沿
    assert svc.calls == ["enable"] and svc._enabled is True

    _at(svc, monkeypatch, datetime(2026, 9, 2, 10, 0))    # 盘中不重复动作
    assert svc.calls == ["enable"]

    svc._final_sync_done.add(("2026-09-02", "close"))     # 收盘定版已完成
    _at(svc, monkeypatch, datetime(2026, 9, 2, 15, 6))    # 收盘边沿
    assert svc.calls == ["enable", "stop"] and svc._enabled is False
    assert "disable" not in svc.calls   # 自动关不清叠加层([R16] 语义不同)


def test_manual_override_between_edges_is_respected(svc, monkeypatch):
    """自动开了之后用户手动关掉 —— 到下一个边界之前不许自动给他打开回去。"""
    from app.services import preferences
    preferences.set_realtime_auto(True)
    _at(svc, monkeypatch, datetime(2026, 9, 2, 9, 15))
    assert svc._enabled is True

    svc._enabled = False                                   # 用户手动关
    _at(svc, monkeypatch, datetime(2026, 9, 2, 10, 0))
    _at(svc, monkeypatch, datetime(2026, 9, 2, 13, 30))
    assert svc.calls == ["enable"] and svc._enabled is False


def test_close_is_postponed_until_final_sync_done(svc, monkeypatch):
    from app.services import preferences
    preferences.set_realtime_auto(True)
    _at(svc, monkeypatch, datetime(2026, 9, 2, 9, 15))

    # 15:06 收盘定版还没成功 → 不关, 继续给它机会拉最后一版
    _at(svc, monkeypatch, datetime(2026, 9, 2, 15, 6))
    assert svc._enabled is True and svc.calls == ["enable"]

    # 定版成功后的下一拍才关
    svc._final_sync_done.add(("2026-09-02", "close"))
    _at(svc, monkeypatch, datetime(2026, 9, 2, 15, 10))
    assert svc.calls == ["enable", "stop"]


def test_close_is_forced_after_hard_cutoff(svc, monkeypatch):
    """定版一直失败也不能挂着不停 —— 15:40 之后无条件关。"""
    from app.services import preferences
    preferences.set_realtime_auto(True)
    _at(svc, monkeypatch, datetime(2026, 9, 2, 9, 15))
    _at(svc, monkeypatch, datetime(2026, 9, 2, 15, 41))
    assert svc.calls == ["enable", "stop"]


def test_turning_auto_on_midsession_applies_immediately(svc, monkeypatch):
    """盘中才打开「自动」→ 当拍就该把行情开起来, 不用等到明天开盘。"""
    from app.services import preferences
    _at(svc, monkeypatch, datetime(2026, 9, 2, 10, 0))     # 自动还没开
    preferences.set_realtime_auto(True)
    svc.notify_auto_pref_changed()
    _at(svc, monkeypatch, datetime(2026, 9, 2, 10, 0))
    assert svc.calls == ["enable"] and svc._enabled is True


def test_holiday_keeps_it_off(svc, monkeypatch):
    from app.services import preferences, trading_day
    preferences.set_realtime_auto(True)
    monkeypatch.setattr(trading_day, "is_trading_day", lambda now=None: False)
    _at(svc, monkeypatch, datetime(2026, 9, 2, 10, 0))
    assert svc.calls == [] and svc._enabled is False


def test_no_realtime_permission_is_a_noop(svc, monkeypatch):
    from app.services import preferences
    preferences.set_realtime_auto(True)
    svc.is_realtime_allowed = lambda: False
    _at(svc, monkeypatch, datetime(2026, 9, 2, 10, 0))
    assert svc.calls == []


def test_preference_round_trip(svc):
    from app.services import preferences
    assert preferences.get_realtime_auto() is False
    preferences.set_realtime_auto(True)
    assert preferences.get_realtime_auto() is True


def test_auto_is_blocked_when_local_store_is_empty(svc, monkeypatch):
    """[同步上游 ed2f81c] 空库下自动开关不该硬开 —— 与作者的首用门禁同口径。

    那道门禁在 API 层, 自动开关走服务层 enable() 绕得过去, 所以服务层自己再判一次。
    """
    from app.services import preferences
    preferences.set_realtime_auto(True)
    svc._repo = _FakeRepo(empty=True)
    _at(svc, monkeypatch, datetime(2026, 9, 2, 10, 0))
    assert svc.calls == [] and svc._enabled is False
