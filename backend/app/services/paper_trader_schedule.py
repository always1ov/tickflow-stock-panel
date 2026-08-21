"""[fork 增强] R61 操盘手定时 —— 每天到点自己跑一次。

长期观察这件事只有在"不用我记得点按钮"的前提下才成立: 靠人手点, 漏几天就是
净值曲线上几个说不清的缺口, 之后拿这条曲线判断系统好不好也就没了底气。

跑的时机刻意默认在**收盘之后**: 这套操盘手全程走收盘口径, 盘中跑等于让模型
拿一个还会变的价格做决定, 收盘一对账就对不上。

一次定时会做两件事, 顺序不能反:
  1. 先跑**生命线检查** —— 跌破 20 日线的按纪律清掉, 不问 AI。
  2. 再让 AI 对**两本账**各做一次决策。
先清后决策, 是因为清仓会腾出现金; 反过来的话模型是拿着一笔本该已经卖掉的
持仓在做判断, 那天的决定就建立在一个错的账面上。

每个操作员各自的时间独立配置。多个操作员撞在同一分钟也没关系 —— 这里串行跑,
并发调同一家 AI 只会互相限流。
"""
from __future__ import annotations

import asyncio
import logging

from app.services import paper_trader as pt

logger = logging.getLogger(__name__)

JOB_PREFIX = "paper_trader_"
# 错过了多久之内还补跑。收盘后这一跑不是非得准点, 但隔夜就没意义了 ——
# 第二天的信息已经变了, 补跑出来的决策是拿新信息填旧日子。
MISFIRE_GRACE_S = 3 * 3600


async def run_trader_once(repo, trader_id: str) -> dict:
    """一个操作员的一次完整定时: 先生命线, 再两本账各决策一次。"""
    from app.services import paper_trader_run

    out: dict = {"trader_id": trader_id, "forced": [], "books": {}}
    t = pt.get(trader_id)
    if t is None:
        return out

    for scope in pt.SCOPES:
        # 1) 纪律先行 —— 清仓腾出的现金, 下一步 AI 才用得上
        try:
            forced = paper_trader_run.check_lifelines(repo, t, scope)
            out["forced"].extend(forced)
        except Exception as e:  # noqa: BLE001
            logger.warning("paper trader %s lifeline check failed: %s", trader_id, e)

        # 2) AI 决策。一本账失败不该拖累另一本 —— 它们本来就是互相独立的对照组
        t = pt.get(trader_id) or t
        try:
            out["books"][scope] = await paper_trader_run.run_once(repo, t, scope)
        except Exception as e:  # noqa: BLE001
            logger.warning("paper trader %s (%s) run failed: %s", trader_id, scope, e)
            bk = pt.book(t, scope)
            bk["last_error"] = str(e)[:300]
            bk["last_run_at"] = pt.now_iso()
            pt.save(t)
            out["books"][scope] = {"error": str(e)[:300]}
    return out


def install(scheduler, repo) -> int:
    """把当前配置的定时装进调度器。改配置后重调一次即可(replace_existing)。

    返回装了几个。返回 0 是正常状态 —— 默认所有操作员的定时都是关的。
    """
    from apscheduler.triggers.cron import CronTrigger

    n = 0
    wanted: set[str] = set()
    for t in pt.list_traders():
        sched = t.get("schedule") or {}
        if not sched.get("enabled") or not t.get("enabled", True):
            continue
        tid = str(t["id"])
        job_id = f"{JOB_PREFIX}{tid}"
        wanted.add(job_id)
        scheduler.add_job(
            _make_job(repo, tid),
            trigger=CronTrigger(day_of_week="mon-fri",
                                hour=int(sched.get("hour", 15)),
                                minute=int(sched.get("minute", 30)),
                                timezone="Asia/Shanghai"),
            id=job_id,
            misfire_grace_time=MISFIRE_GRACE_S,
            replace_existing=True,
        )
        n += 1

    # 关掉/删掉的那些要真的摘下来 —— 只管添加的话, 关了定时它还在照跑,
    # 而那意味着继续烧 AI 额度。
    for job in list(scheduler.get_jobs()):
        if job.id.startswith(JOB_PREFIX) and job.id not in wanted:
            scheduler.remove_job(job.id)
    return n


def _make_job(repo, trader_id: str):
    """APScheduler 拿到的必须是协程函数本身, 不能是 lambda 包一层 ——
    包了它会当同步函数丢进线程池, 里面的 await 就永远不会被跑。"""
    async def _job():
        try:
            await run_trader_once(repo, trader_id)
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            logger.warning("paper trader scheduled run failed (%s): %s", trader_id, e)
    return _job
