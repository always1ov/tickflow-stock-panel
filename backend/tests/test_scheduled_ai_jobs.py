"""定时 AI 任务的接线。

原来这个文件叫 `test_signal_freshness.py`, 前半测的是「个股 AI 信号要不要重算」
(`signal_needs_refresh`, R131), 后半测的是两个定时 job 的接线。

[R435] AI 信号整套停用(用户: 「清除了ai信号这部分, 后续我打算用斐波那契二型重做
这部分」), 前半随那个判据一起删了。后半留下来守剩下那一个 —— 「今日总览 AI 定时」
曾在一次上游合并里整段丢失, settings.py 一直 import 它, 用户一开定时就 ImportError 500。
另加一条反面: 信号那一支撤干净了, 没有留下能被 import 到的半截。
"""
from __future__ import annotations

from app.jobs import daily_pipeline as dp


def test_today_ai_job_is_importable():
    from app.api import settings as settings_api  # noqa: F401
    for name in ("TODAY_AI_JOB_ID", "_register_today_ai_job", "_run_scheduled_today_ai"):
        assert hasattr(dp, name), f"daily_pipeline 缺少 {name}"


def test_settings_endpoint_can_import_what_it_needs():
    """按 settings.py 里那一行 import 原样再走一遍。"""
    from app.jobs.daily_pipeline import TODAY_AI_JOB_ID, _register_today_ai_job  # noqa: F401


def test_register_job_uses_stable_id():
    """job id 必须稳定 —— settings.py 关闭定时时靠 id 去 remove_job。"""
    class _Sched:
        def __init__(self): self.jobs = {}
        def add_job(self, fn, **kw): self.jobs[kw["id"]] = kw

    sched = _Sched()
    dp._register_today_ai_job(sched, None, 18, 30)
    assert set(sched.jobs) == {"scheduled_today_ai"} == {dp.TODAY_AI_JOB_ID}
    assert all(j["replace_existing"] for j in sched.jobs.values())


def test_R435_个股AI信号定时撤干净了():
    for name in ("SIGNAL_AI_JOB_ID", "_register_signal_ai_job", "_run_scheduled_signal_ai",
                 "signal_needs_refresh", "SIGNAL_TTL_HOURS"):
        assert not hasattr(dp, name), f"daily_pipeline 还留着 {name}"
    from app.services import preferences
    assert not hasattr(preferences, "get_signal_ai_schedule")
    import importlib.util
    assert importlib.util.find_spec("app.services.stock_signal") is None, "stock_signal 模块还在"
