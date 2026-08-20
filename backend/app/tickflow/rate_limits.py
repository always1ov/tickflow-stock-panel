"""TickFlow capability rate-limit helpers.

This module centralizes the small pieces of batch/rpm resolution used by
TickFlow-backed services. It intentionally does not manage custom data sources.
"""
from __future__ import annotations

import random
import threading
import time
from dataclasses import dataclass
from typing import Any, TypeVar

from app.tickflow.capabilities import Cap, CapabilitySet

T = TypeVar("T")

# TickFlow Pro 单进程安全预算: 套餐标称 rpm 的 80%。
# 注意: _next_slot 仅在本 Python 进程内共享, 不能跨 Gold 容器与 A 股面板进程。
# Stage A 期间跨产品靠错峰(盘中 Gold 优先, A 股 Pro 批处理建议 16:00 后),
# 不要把「各进程各扣 80%」误当成账户级共享限频。
SAFETY_RPM_FACTOR = 0.8

# 进程级共享限速器: 按 rpm 分桶的「下一个可用时刻」表 (Lock 守护)。
# 限制: sleep_between_batches(index=0) 只登记槽位、不 sleep, 因此多个调用方若同时以
# index=0 启动, 仍可能瞬时突发超过单能力 rpm。后续 index>0 批次会按同一时间轴排队。
# Phase 1 / Stage A: 不要并发启动多个 probe 或大批量 sync; 跨进程仍靠错峰, 非账户级限频。
_slot_lock = threading.Lock()
_next_slot: dict[int, float] = {}


def apply_safety_rpm(rpm: int | None, *, factor: float = SAFETY_RPM_FACTOR) -> int | None:
    """Scale a package rpm by the shared safety factor (default 80%)."""
    if rpm is None or rpm <= 0:
        return rpm
    return max(1, int(rpm * factor))


def _reserve_slot(rpm: int, interval: float) -> float:
    """在共享时间轴上为一次请求预约一个发包槽, 返回需等待的秒数 (>=0)。

    interval = 60/rpm。now 早于该 rpm 桶的 next_slot 时排到 next_slot, 否则排到 now;
    随后把该桶 next_slot 后移 interval。持锁仅做时间账目, 不在锁内 sleep。
    """
    key = rpm if rpm and rpm > 0 else -1
    with _slot_lock:
        now = time.monotonic()
        scheduled = max(now, _next_slot.get(key, now))
        _next_slot[key] = scheduled + interval
        return scheduled - now


@dataclass(frozen=True)
class ResolvedLimit:
    batch: int | None
    rpm: int | None


def resolve_limit(
    capset: CapabilitySet,
    cap: Cap,
    *,
    default_batch: int | None = None,
    default_rpm: int | None = None,
    default_rpm_when_unset: bool = True,
    apply_safety: bool = True,
) -> ResolvedLimit:
    """Return a capability's batch/rpm with caller-provided fallbacks.

    By default rpm is scaled by SAFETY_RPM_FACTOR (0.8) inside this process only.
    This is not a cross-container account budget. Pass apply_safety=False for diagnostics.
    """
    lim = capset.limits(cap)
    if lim is None:
        rpm = default_rpm
    else:
        rpm = lim.rpm if lim.rpm else (default_rpm if default_rpm_when_unset else None)
        default_batch = lim.batch if lim.batch else default_batch
    if apply_safety:
        rpm = apply_safety_rpm(rpm)
    if lim is None:
        return ResolvedLimit(batch=default_batch, rpm=rpm)
    return ResolvedLimit(
        batch=default_batch,
        rpm=rpm,
    )


def batch_interval(rpm: int | None, *, default: float = 0.0) -> float:
    """Return the existing uniform batch interval formula: 60 / rpm."""
    return 60.0 / rpm if rpm and rpm > 0 else default


def chunked(items: list[T], batch_size: int | None) -> list[list[T]]:
    """Split items by batch size, preserving the existing None-as-one-batch behavior."""
    if batch_size is None:
        return [items]
    return [items[i:i + batch_size] for i in range(0, len(items), batch_size)]


def sleep_between_batches(index: int, rpm: int | None, *, default_interval: float = 0.0) -> None:
    """Pace batches via the process-local shared slot table.

    - index == 0: reserve a slot but do **not** sleep (documented first-batch burst).
    - index > 0: wait until the reserved slot time.

    Concurrent callers that all pass index=0 can still burst above rpm; only later
    batches and single-pipeline callers get full spacing. Do not launch multiple
    Phase 1 probes/syncs at once during Stage A.
    """
    interval = batch_interval(rpm, default=default_interval)
    if interval <= 0:
        return
    if index <= 0:
        # First batch: reserve only (no sleep). Concurrent index=0 calls may burst.
        _reserve_slot(rpm or -1, interval)
        return
    wait = _reserve_slot(rpm or -1, interval)
    if wait > 0:
        time.sleep(wait)


def min_batch(preferred: int, limit: ResolvedLimit) -> int:
    """Clamp a user-preferred batch size by a resolved capability batch limit."""
    return min(preferred, limit.batch) if limit.batch else preferred


# ── [fork 增强] R35 多 key 轮询的错峰与抖动 ──

def spread_delays(
    n_batches: int,
    n_keys: int,
    rpm: int | None,
    *,
    jitter: float = 0.35,
    rng: Any = None,
) -> list[float]:
    """多 key 池化时, 每批调用前该等多久(秒)。

    原来同一轮里 n_keys 批是背靠背打出去的(一个突发), 打完再干等一个窗口。
    改成把这些调用摊开在窗口内, 并给每次间隔加随机抖动, 好处是:
      - 刷新变成连续滚动, 而不是"一跳一跳"地整块更新
      - 一次网络抖动只毁掉一批(5 只), 不再整轮 70 只一起失败
      - 不与其他客户端形成同步节拍, 避免共振式的重试风暴

    额度约束不变: 抖动系数恒为 [1, 1+jitter], 只会让间隔变大不会变小, 所以同一个
    key 两次调用的实际间隔始终 >= 60/rpm。
    """
    if n_batches <= 0:
        return []
    n_keys = max(1, int(n_keys))
    window = batch_interval(rpm, default=0.0)
    if window <= 0:
        return [0.0] * n_batches
    base = window / n_keys
    r = rng or random.Random()
    # 第 0 批不等 —— 一轮总要有人先开口, 否则每轮白白多等一个间隔
    return [0.0] + [round(base * (1.0 + r.random() * jitter), 4)
                    for _ in range(n_batches - 1)]


def shuffled_key_order(n_keys: int, n_batches: int, rng: Any = None) -> list[int]:
    """每批用第几个 key。每轮重新洗牌, 而不是固定 i % n_keys。

    固定映射会让同一组标的永远由同一个 key 拉取; 一旦某个 key 出问题(限流/失效),
    受影响的永远是那几只。打散之后失败面在轮次之间随机分布, 更容易被察觉,
    也不会让某几只长期拿不到数据。
    """
    n_keys = max(1, int(n_keys))
    if n_batches <= 0:
        return []
    r = rng or random.Random()
    order: list[int] = []
    while len(order) < n_batches:
        chunk = list(range(n_keys))
        r.shuffle(chunk)
        order.extend(chunk)
    return order[:n_batches]
