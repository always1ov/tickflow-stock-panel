"""[fork R98] 收盘正式覆写确认: 常态窗口写入过低 → 标记待确认并有限重试。"""
from __future__ import annotations

from datetime import date

import pytest

from app.jobs import daily_pipeline as dp


@pytest.fixture(autouse=True)
def _reset():
    dp._today_official_pending = None
    dp._official_retry_count = 0
    yield
    dp._today_official_pending = None
    dp._official_retry_count = 0


def test_low_rows_on_trading_day_marks_pending(monkeypatch):
    from app.services import trading_day
    monkeypatch.setattr(trading_day, "is_trading_day", lambda now=None: True)
    dp._note_today_official(3, date.today())
    assert dp._today_official_pending == date.today()


def test_enough_rows_clears_pending(monkeypatch):
    dp._today_official_pending = date.today()
    dp._note_today_official(5600, date.today())
    assert dp._today_official_pending is None


def test_holiday_zero_rows_is_normal(monkeypatch):
    from app.services import trading_day
    monkeypatch.setattr(trading_day, "is_trading_day", lambda now=None: False)
    dp._note_today_official(0, date.today())
    assert dp._today_official_pending is None


class _FakeScheduler:
    def __init__(self) -> None:
        self.jobs: list[dict] = []

    def add_job(self, fn, trigger=None, run_date=None, **kw):
        self.jobs.append({"fn": fn, "run_date": run_date, **kw})


def test_retry_scheduled_up_to_max(monkeypatch):
    fake = _FakeScheduler()
    monkeypatch.setattr(dp, "_SCHEDULER", fake)
    monkeypatch.setattr(dp, "_PIPELINE_FN", lambda **_: None)
    dp._today_official_pending = date.today()
    for _ in range(5):
        dp._maybe_schedule_official_retry()
    assert len(fake.jobs) == dp._OFFICIAL_RETRY_MAX  # 超过上限不再安排


def test_no_retry_when_confirmed(monkeypatch):
    fake = _FakeScheduler()
    monkeypatch.setattr(dp, "_SCHEDULER", fake)
    monkeypatch.setattr(dp, "_PIPELINE_FN", lambda **_: None)
    dp._today_official_pending = None
    dp._official_retry_count = 2
    dp._maybe_schedule_official_retry()
    assert fake.jobs == []
    assert dp._official_retry_count == 0  # 确认过关后计数清零
