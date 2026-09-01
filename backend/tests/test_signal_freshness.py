"""[fork R131] AI 信号增量判据 + [R27 恢复] 两个定时 job 的存在性。"""
from __future__ import annotations

from datetime import date, datetime

import pytest

from app.jobs import daily_pipeline as dp


NOW = datetime(2026, 9, 2, 20, 0)      # 周三晚上
AS_OF = date(2026, 9, 2)               # 当日 K 线已落盘


def _refresh(created, as_of=AS_OF, now=NOW, **kw):
    return dp.signal_needs_refresh(created, as_of, now=now, **kw)


# ------------------------------------------------------- 主判据: 见没见过最新 K


def test_signal_after_close_is_fresh():
    """当天收盘后生成 → 见过最新那根 K, 不必重算。"""
    assert _refresh("2026-09-02T18:30:00") is False


def test_signal_before_close_must_refresh():
    """当天盘中生成的信号没见过当日收盘 K —— 必须重算。"""
    assert _refresh("2026-09-02T10:00:00") is True


def test_yesterday_signal_must_refresh():
    assert _refresh("2026-09-01T18:00:00") is True


def test_never_analyzed():
    assert _refresh(None) is True
    assert _refresh("") is True


def test_broken_timestamp_is_treated_as_missing():
    """时间戳坏了宁可多算一次, 也不能把不知道新旧的信号当成最新。"""
    assert _refresh("不是时间") is True


# ------------------------------------------------------- 安全阀: TTL


def test_ttl_forces_refresh_when_data_stops_updating():
    """长假期间数据不更新: 光看 as_of 会永远不重算, TTL 兜住。"""
    # as_of 停在 8-28, 信号是 8-28 收盘后生成的 → 主判据认为新鲜
    assert dp.signal_needs_refresh("2026-08-28T18:00:00", date(2026, 8, 28),
                                   now=datetime(2026, 8, 28, 20, 0)) is False
    # 但过了 24 小时就允许重算
    assert dp.signal_needs_refresh("2026-08-28T18:00:00", date(2026, 8, 28),
                                   now=datetime(2026, 8, 30, 10, 0)) is True


def test_ttl_is_configurable():
    assert _refresh("2026-09-02T18:30:00", ttl_hours=1) is True


def test_missing_as_of_falls_back_to_ttl_only():
    """取不到数据基准日时不该硬判过期 —— 只按 TTL。"""
    assert dp.signal_needs_refresh("2026-09-02T19:00:00", None, now=NOW) is False
    assert dp.signal_needs_refresh("2026-08-01T19:00:00", None, now=NOW) is True


def test_unparsable_as_of_does_not_crash():
    assert dp.signal_needs_refresh("2026-09-02T19:00:00", "不是日期", now=NOW) is False


def test_timezone_aware_timestamp_is_converted():
    """带 Z 的 UTC 时间戳要按北京时间比 —— 09-02T10:30Z = 北京 18:30, 算新鲜。"""
    assert _refresh("2026-09-02T10:30:00Z") is False
    # 北京 09:00(UTC 01:00) 是盘中, 要重算
    assert _refresh("2026-09-02T01:00:00Z") is True


def test_as_of_accepts_string_form():
    assert dp.signal_needs_refresh("2026-09-02T18:30:00", "2026-09-02", now=NOW) is False


# ------------------------------------------------------- [R27 恢复] 定时 job


def test_scheduled_ai_jobs_are_importable():
    """这两个 job 曾在一次上游合并里整段丢失, 而 settings.py 一直 import 它们 ——
    用户一开定时就 ImportError 500。这条测试就是为了别再悄悄丢一次。"""
    from app.api import settings as settings_api  # noqa: F401
    for name in ("TODAY_AI_JOB_ID", "SIGNAL_AI_JOB_ID",
                 "_register_today_ai_job", "_register_signal_ai_job",
                 "_run_scheduled_today_ai", "_run_scheduled_signal_ai"):
        assert hasattr(dp, name), f"daily_pipeline 缺少 {name}"


def test_settings_endpoint_can_import_what_it_needs():
    """按 settings.py 里那两行 import 原样再走一遍。"""
    from app.jobs.daily_pipeline import (  # noqa: F401
        SIGNAL_AI_JOB_ID, TODAY_AI_JOB_ID,
        _register_signal_ai_job, _register_today_ai_job,
    )


def test_register_jobs_uses_stable_ids():
    """job id 必须稳定 —— settings.py 关闭定时时靠 id 去 remove_job。"""
    class _Sched:
        def __init__(self): self.jobs = {}
        def add_job(self, fn, **kw): self.jobs[kw["id"]] = kw

    sched = _Sched()
    dp._register_today_ai_job(sched, None, 18, 30)
    dp._register_signal_ai_job(sched, None, 19, 0)
    assert set(sched.jobs) == {dp.TODAY_AI_JOB_ID, dp.SIGNAL_AI_JOB_ID}
    assert all(j["replace_existing"] for j in sched.jobs.values())


@pytest.mark.parametrize("job_id", ["scheduled_today_ai", "scheduled_signal_ai"])
def test_job_ids_match_what_settings_removes(job_id):
    assert job_id in {dp.TODAY_AI_JOB_ID, dp.SIGNAL_AI_JOB_ID}
