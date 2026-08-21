"""[fork 增强] R39 研究工作流 —— 让挖掘/回测自己一直跑, 跑到达标为止。

用户要的是"一整套自己工作起来"的东西: 不用盯着页面, AI 反复试, 试到出成绩。
原来的 AI 代跑只能在页面开着时跑固定几轮, 关掉页面就断, 用满轮数就停 —— 那不是
工作流, 是一次性脚本。

这层做三件原来没有的事:

1. **服务端自己跑**。会话落盘, 后台线程按节拍推进, 关页面照跑, 重启接着跑。
2. **会重开**。一个会话用满轮数还没达标, 不是结束, 而是换一批配置重开一轮
   (用户说的"抽卡")。预算按"总共重开几次 / 总共多久"给, 不是按轮数。
3. **记账**。这是最要紧的一条。"一直抽总会中"在统计上就是多重检验:
   独立试 N 次, 光靠运气撞出"夏普 >= 0.5"的概率随 N 迅速逼近 1。
   所以每个工作流都记着一共试了多少轮, 结论里必须带上这个数
   —— 见 ``overfit_note``。搜索窗口上的漂亮数字只是线索, 只有终检窗口
   那一次(且全程对循环锁定)才算数。

设计上刻意分层: 本模块只有状态机与账本(纯函数, 好测), 真正跑挖掘/跑回测的
动作由外部注入的 driver 完成 —— 这样单测不需要真的跑一次回测。
手动路径一行没动: 工作流只是又一个调用方, 用的是同一批 step/run 入口。
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)

MAX_WORKFLOWS = 20

KIND_MINING = "mining"
KIND_BACKTEST = "backtest"
KINDS = (KIND_MINING, KIND_BACKTEST)

STATUS_RUNNING = "running"
STATUS_SATISFIED = "satisfied"
STATUS_EXHAUSTED = "exhausted"
STATUS_STOPPED = "stopped"
STATUS_FAILED = "failed"
OPEN_STATUSES = frozenset({STATUS_RUNNING})

# 停止原因 → 中文说法。状态只有五个, 原因要更细, 否则复盘时看不出为什么停的。
STOP_SATISFIED = "satisfied"
STOP_ATTEMPTS = "attempts_exhausted"
STOP_DEADLINE = "deadline_reached"
STOP_MANUAL = "stopped_by_user"
STOP_ERROR = "error"

STOP_CN = {
    STOP_SATISFIED: "跑出达标结果了",
    STOP_ATTEMPTS: "重开次数用完了",
    STOP_DEADLINE: "跑够时间了",
    STOP_MANUAL: "你中止了",
    STOP_ERROR: "出错停了",
}
_STOP_STATUS = {
    STOP_SATISFIED: STATUS_SATISFIED,
    STOP_ATTEMPTS: STATUS_EXHAUSTED,
    STOP_DEADLINE: STATUS_EXHAUSTED,
    STOP_MANUAL: STATUS_STOPPED,
    STOP_ERROR: STATUS_FAILED,
}

# 预算默认值。给得住够跑一晚上, 又不至于无限烧机器。
DEFAULT_MAX_ATTEMPTS = 12          # 最多重开几次
DEFAULT_ROUNDS_PER_ATTEMPT = 6     # 每次重开内部最多几轮
DEFAULT_MAX_HOURS = 6.0
MAX_ATTEMPTS_CAP = 100
MAX_ROUNDS_CAP = 20
MAX_HOURS_CAP = 72.0

# 连续出错多少次就认输 —— AI 没配好/额度用完时, 不能让它空转一整夜
MAX_CONSECUTIVE_ERRORS = 3


# ---------- 纯函数: 预算与账本 ----------

def _clamp(value: Any, lo: float, hi: float, default: float) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    if v != v:  # NaN
        return default
    return max(lo, min(hi, v))


def normalize_budget(raw: dict | None, *, now_ts: float | None = None) -> dict:
    """把用户填的预算收进合法范围, 并把"跑多久"换算成绝对截止时刻。

    存绝对时刻而不是时长: 后台线程可能因为重启而中断, 存时长的话每次重启
    都等于重新计时, 一个"最多跑 6 小时"的工作流能跑上好几天。
    """
    raw = raw or {}
    now = time.time() if now_ts is None else float(now_ts)
    hours = _clamp(raw.get("max_hours"), 0.1, MAX_HOURS_CAP, DEFAULT_MAX_HOURS)
    return {
        "max_attempts": int(_clamp(raw.get("max_attempts"), 1, MAX_ATTEMPTS_CAP,
                                   DEFAULT_MAX_ATTEMPTS)),
        "rounds_per_attempt": int(_clamp(raw.get("rounds_per_attempt"), 1, MAX_ROUNDS_CAP,
                                         DEFAULT_ROUNDS_PER_ATTEMPT)),
        "max_hours": round(hours, 2),
        "deadline_ts": round(now + hours * 3600, 3),
    }


def should_continue(wf: dict, *, now_ts: float) -> tuple[bool, str | None]:
    """还该不该继续跑。返回 (继续吗, 停止原因)。

    达标优先于一切预算判断 —— 已经跑出结果了就别再抽, 多抽只会让下面那条
    多重检验的账更难看。
    """
    if wf.get("status") not in OPEN_STATUSES:
        return False, wf.get("stop_reason")
    if (wf.get("best") or {}).get("passed"):
        return False, STOP_SATISFIED
    if int((wf.get("ledger") or {}).get("errors_in_a_row") or 0) >= MAX_CONSECUTIVE_ERRORS:
        return False, STOP_ERROR
    budget = wf.get("budget") or {}
    if int((wf.get("ledger") or {}).get("attempts") or 0) >= int(budget.get("max_attempts", 0)):
        return False, STOP_ATTEMPTS
    deadline = budget.get("deadline_ts")
    if deadline is not None and now_ts >= float(deadline):
        return False, STOP_DEADLINE
    return True, None


def merge_best(best: dict | None, candidate: dict | None) -> dict | None:
    """跨多次重开挑最好的一个。达标的永远压过不达标的, 同档比夏普。

    比较键要能吃下 None —— 回测跑出来没有成交时夏普是 None, 拿它跟数字比会炸。
    """
    if not candidate:
        return best
    if not best:
        return candidate

    def key(x: dict) -> tuple[int, float]:
        s = x.get("sharpe")
        return (1 if x.get("passed") else 0,
                float(s) if isinstance(s, (int, float)) else -1e9)

    return candidate if key(candidate) > key(best) else best


def overfit_note(attempts: int, rounds: int) -> str:
    """抽卡账本 → 一句话说清这个结果该怎么看。跟着赢家一路带到界面上。

    这是整个工作流最该说实话的地方。多重检验的老问题: 独立试 N 次,
    光靠运气撞出"过门槛"的概率随 N 迅速逼近 1。不写这句, 工作流就是
    一台专门生产虚假信心的机器。
    """
    n = max(0, int(rounds))
    a = max(0, int(attempts))
    tail = ("搜索窗口上的数字只能当线索, 真正算数的是终检窗口那一次"
            "(它对整个循环全程锁定, 没被挑拣过)。")
    if n <= 5:
        return f"一共试了 {n} 轮, 次数不多, 挑拣带来的水分有限。{tail}"
    if n <= 20:
        return (f"一共试了 {n} 轮({a} 次重开)。试得越多, 挑出来的赢家里"
                f"运气成分越大。{tail}")
    return (f"一共试了 {n} 轮({a} 次重开)。这个次数下, 纯靠运气也几乎必然"
            f"能撞出一个「过门槛」的组合 —— 搜索窗口上的指标基本没有信息量了。{tail}")


def progress_text(wf: dict) -> str:
    """一行状态, 给界面和通知用。"""
    ledger = wf.get("ledger") or {}
    budget = wf.get("budget") or {}
    a, m = int(ledger.get("attempts") or 0), int(budget.get("max_attempts") or 0)
    r = int(ledger.get("rounds") or 0)
    if wf.get("status") != STATUS_RUNNING:
        return f"{STOP_CN.get(wf.get('stop_reason'), '已结束')} · 共 {a} 次重开 / {r} 轮"
    return f"第 {a}/{m} 次重开 · 累计 {r} 轮"


def finish(wf: dict, stop: str) -> dict:
    """收工: 落状态、落原因、把抽卡账本的结论写进去。就地改, 返回同一个 dict。"""
    ledger = wf.get("ledger") or {}
    wf["status"] = _STOP_STATUS.get(stop, STATUS_FAILED)
    wf["stop_reason"] = stop
    wf["stop_reason_cn"] = STOP_CN.get(stop, stop)
    wf["overfit_note"] = overfit_note(
        int(ledger.get("attempts") or 0), int(ledger.get("rounds") or 0))
    wf["finished_at"] = _now()
    return wf


# ---------- 持久化 ----------

def _path() -> Path:
    p = settings.data_dir / "user_data" / "workflows.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _read_all() -> list[dict]:
    p = _path()
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        logger.warning("load workflows failed: %s", e)
        return []
    rows = data.get("workflows") if isinstance(data, dict) else None
    return [w for w in rows or [] if isinstance(w, dict)]


def _write_all(rows: list[dict]) -> None:
    try:
        _path().write_text(
            json.dumps({"workflows": rows[-MAX_WORKFLOWS:]}, ensure_ascii=False, indent=2),
            encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        logger.warning("save workflows failed: %s", e)


def list_workflows(limit: int = MAX_WORKFLOWS) -> list[dict]:
    """最新在前。"""
    return list(reversed(_read_all()))[:limit]


def get(workflow_id: str) -> dict | None:
    for w in _read_all():
        if w.get("workflow_id") == workflow_id:
            return w
    return None


def save(wf: dict) -> dict:
    wf["updated_at"] = _now()
    rows = [w for w in _read_all() if w.get("workflow_id") != wf.get("workflow_id")]
    rows.append(wf)
    _write_all(rows)
    return wf


def running_workflows() -> list[dict]:
    return [w for w in _read_all() if w.get("status") in OPEN_STATUSES]


def create(*, kind: str, config: dict, budget: dict | None = None,
           now_ts: float | None = None) -> dict:
    if kind not in KINDS:
        raise ValueError(f"unknown workflow kind: {kind!r}")
    wf = {
        "workflow_id": uuid.uuid4().hex[:12],
        "kind": kind,
        "config": dict(config or {}),
        "budget": normalize_budget(budget, now_ts=now_ts),
        "status": STATUS_RUNNING,
        "stop_reason": None,
        "stop_reason_cn": None,
        "overfit_note": None,
        "best": None,
        "attempts": [],
        "ledger": {"attempts": 0, "rounds": 0, "errors_in_a_row": 0, "last_error": None},
        "current": None,      # 本次重开的进行中状态, 由 driver 自己定义结构
        "created_at": _now(),
        "updated_at": _now(),
        "finished_at": None,
    }
    rows = _read_all()
    rows.append(wf)
    _write_all(rows)
    return wf


def stop(workflow_id: str) -> dict | None:
    """用户中止。已收工的原样返回 —— 重复点不该把结果抹掉。"""
    wf = get(workflow_id)
    if wf is None:
        return None
    if wf.get("status") in OPEN_STATUSES:
        finish(wf, STOP_MANUAL)
        save(wf)
    return wf


# ---------- 账本记录 ----------

def note_round(wf: dict, *, best_of_round: dict | None = None) -> dict:
    """跑完一轮: 累计轮数, 清错误连击, 顺带更新全局最好成绩。"""
    ledger = wf.setdefault("ledger", {})
    ledger["rounds"] = int(ledger.get("rounds") or 0) + 1
    ledger["errors_in_a_row"] = 0
    ledger["last_error"] = None
    wf["best"] = merge_best(wf.get("best"), best_of_round)
    return wf


def note_attempt_start(wf: dict, current: dict) -> dict:
    ledger = wf.setdefault("ledger", {})
    ledger["attempts"] = int(ledger.get("attempts") or 0) + 1
    wf["current"] = dict(current, attempt=ledger["attempts"], started_at=_now())
    return wf


def note_attempt_end(wf: dict, *, outcome: str, detail: dict | None = None) -> dict:
    """本次重开收尾, 归档进 attempts, 清空 current 好开下一次。"""
    cur = wf.get("current") or {}
    wf.setdefault("attempts", []).append({
        "attempt": cur.get("attempt"),
        "outcome": outcome,
        "started_at": cur.get("started_at"),
        "ended_at": _now(),
        **(detail or {}),
    })
    wf["current"] = None
    return wf


def note_error(wf: dict, message: str) -> dict:
    """AI 没配好/额度用完这类错不该让工作流空转一整夜, 连着几次就认输。"""
    ledger = wf.setdefault("ledger", {})
    ledger["errors_in_a_row"] = int(ledger.get("errors_in_a_row") or 0) + 1
    ledger["last_error"] = str(message)[:500]
    return wf


# ---------- 推进 ----------

async def tick(wf: dict, *, drivers: dict, now_ts: float | None = None) -> dict:
    """把一个工作流推进一格。

    drivers: {kind: driver}, driver 需实现 ``async advance(wf) -> dict``,
    返回 {"action": "running"|"round_done"|"attempt_done"|"error", ...}。
    真正跑挖掘/跑回测的动作全在 driver 里 —— 本函数只管账本与预算,
    单测因此不需要真跑一次回测。

    now_ts 可注入: 预算判定依赖墙钟, 不给个口子的话截止时刻相关的分支
    只能靠 sleep 去撞, 测不动。
    """
    now = time.time() if now_ts is None else float(now_ts)
    go, stop_reason = should_continue(wf, now_ts=now)
    if not go:
        return save(finish(wf, stop_reason or STOP_ATTEMPTS))

    driver = drivers.get(wf.get("kind"))
    if driver is None:
        return save(finish(note_error(wf, f"没有 {wf.get('kind')} 的执行器"), STOP_ERROR))

    try:
        out = await driver.advance(wf)
    except Exception as e:  # noqa: BLE001
        logger.warning("workflow %s advance failed: %s", wf.get("workflow_id"), e)
        note_error(wf, str(e))
        go, stop_reason = should_continue(wf, now_ts=now)
        return save(wf if go else finish(wf, stop_reason or STOP_ERROR))

    action = out.get("action")
    if action == "error":
        note_error(wf, out.get("message") or "未知错误")
    elif action == "round_done":
        note_round(wf, best_of_round=out.get("best"))
    elif action == "attempt_done":
        note_round(wf, best_of_round=out.get("best"))
        note_attempt_end(wf, outcome=out.get("outcome") or "done", detail=out.get("detail"))

    # 这一格跑完后预算可能刚好用尽 / 刚好达标 —— 立刻收工, 别多抽一次
    go, stop_reason = should_continue(wf, now_ts=now)
    return save(wf if go else finish(wf, stop_reason or STOP_ATTEMPTS))
