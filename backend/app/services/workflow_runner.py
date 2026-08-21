"""[fork 增强] R39 工作流后台节拍器 —— 让工作流不依赖页面开着。

一个后台线程, 每 TICK_SECONDS 醒一次, 把所有 running 的工作流各推进一格。
推进本身是 async(要等 AI), 所以线程里自己起一个事件循环跑。

为什么是线程 + 自带 loop, 而不是挂 APScheduler:
  推进一格可能要等 AI 几十秒、等回测几分钟, 挂在共享调度器上会顶住别的任务;
  独立线程互不影响, 进程退出时是 daemon 直接走人。

真正的重活(挖掘 run / 回测 worker)都在 heavy_job_limiter 的槽位里排队, 所以
即使同时开几个工作流, 也不会真的并发烧机器 —— 它们会自己排成一队。
"""
from __future__ import annotations

import asyncio
import logging
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)

TICK_SECONDS = 20.0
# 一拍最多推进几个工作流, 免得一次醒来把所有队列全填满
MAX_PER_TICK = 4


class WorkflowRunner:
    def __init__(self, *, tick_seconds: float = TICK_SECONDS) -> None:
        self._tick_seconds = tick_seconds
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._app_state: Any = None

    def start(self, app_state: Any) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._app_state = app_state
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="workflow-runner", daemon=True)
        self._thread.start()
        logger.info("workflow runner started (tick=%.0fs)", self._tick_seconds)

    def shutdown(self, wait: bool = False) -> None:
        self._stop.set()
        if wait and self._thread is not None:
            self._thread.join(timeout=5)

    def _loop(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            while not self._stop.is_set():
                try:
                    loop.run_until_complete(self.tick_once())
                except Exception as e:  # noqa: BLE001
                    # 单拍失败绝不能让节拍器停摆 —— 停了之后所有工作流都无声挂起
                    logger.warning("workflow tick failed: %s", e)
                self._stop.wait(self._tick_seconds)
        finally:
            loop.close()

    async def tick_once(self) -> int:
        """把当前所有 running 工作流各推进一格, 返回推进了几个。"""
        from app.services import workflow, workflow_drivers

        running = workflow.running_workflows()
        if not running:
            return 0
        drivers = workflow_drivers.build_drivers(self._app_state)
        done = 0
        for wf in running[:MAX_PER_TICK]:
            if self._stop.is_set():
                break
            try:
                await workflow.tick(wf, drivers=drivers)
                done += 1
            except Exception as e:  # noqa: BLE001
                logger.warning("workflow %s tick failed: %s", wf.get("workflow_id"), e)
        return done


workflow_runner = WorkflowRunner()


def recover_on_boot() -> int:
    """[R39] 重启后把"卡在半路"的工作流接回来。

    进程被杀时 current 里可能记着一个已经不在跑的挖掘会话。这里不猜它的死活 ——
    下一拍 driver 自己会去读会话状态, 读不到就报错、连击三次收掉。真正需要在
    这里做的只有一件事: 把已经过了截止时刻的工作流直接收掉, 免得重启后又白跑一轮。
    """
    from app.services import workflow

    now = time.time()
    closed = 0
    for wf in workflow.running_workflows():
        go, stop = workflow.should_continue(wf, now_ts=now)
        if not go:
            workflow.save(workflow.finish(wf, stop or workflow.STOP_DEADLINE))
            closed += 1
    return closed
