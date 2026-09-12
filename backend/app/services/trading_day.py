"""交易日探针 (oracle) — 回答「今天是否 A 股交易日」。

消费方 (实时行情轮询 / 盘中分钟增量) 在周几+时段门控之后调用, 用于把
「工作日但休市」的节假日从轮询窗口里剔除; 返回 None (未知) 时调用方
维持现状行为 (周几近似 + 快照新鲜度判据兜底), 不引入新依赖。

探测链 (按确定性排序, 先到先得):
  1. fuyao 交易日历 (已配置 fuyao 时): GET /api/a-share/calendar/trading-days,
     今天在近一年交易日列表内 ⇔ 交易日。权威日历, 无时段依赖, 无开盘缓冲问题。
  2. tickflow 实时行情时间戳: 拉一篮流动性票快照 (单请求), max(timestamp)
     日期 == 今天 ⇔ 交易日。非交易日全市场戳停在上一交易日 (2026-08-29 周六
     实测 5551/5551, 含停牌股 — 戳是快照定版时刻, 非最后成交时刻);
     交易日集合竞价阶段 (9:15-9:30) 戳是否已翻新未实测 → 开盘缓冲窗内
     戳过期不作数, 保守视为未知。
  3. 均不可用 → None: 调用方按周几近似继续。

安全约束:
  - 周末直接返回 False (周几判断零成本, 不打任何请求)。
  - 探针是纯读: 只产出一个布尔判定, 不落盘、不进行情管道、不碰归属链路。
  - 只用于「降档」(休市不轮询); 休市结论 TTL 较短 (30 分钟) 定期复探,
    探针误判最坏损失一段快照且可自愈; 未知结论短 TTL (5 分钟) 防止
    轮询循环每拍重打失败的探测。
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from datetime import time as dt_time

from app.market_time import CN_TZ, cn_now

# tickflow 戳探针的开盘缓冲窗: 此时刻之前戳仍是上一交易日属正常 (集合竞价),
# 不据此判休市。周一实测竞价戳翻新时机后可收紧。仅上午首个窗口需要。
_STALE_BUFFER_UNTIL = dt_time(9, 40)

# 一篮流动性票: 探 max(timestamp), 任一戳为今日即交易日 (OR 语义)。
# 大盘蓝筹同日全部停牌 = 市场性事件, 与休市同处理无碍。
_BASKET = ("000001.SZ", "600519.SH", "600036.SH", "601318.SH", "000651.SZ")

_TTL_TRADING_S = 3600.0   # 交易日结论每小时复探 (跨日天然失效)
_TTL_HOLIDAY_S = 1800.0   # 休市结论 30 分钟复探, 误判自愈上限
_TTL_UNKNOWN_S = 300.0    # 未知结论 5 分钟后重试探测

_CACHE_LOCK = threading.Lock()


@dataclass
class _Cache:
    day: object | None = None
    verdict: bool | None = None
    probed_at: float = 0.0


_CACHE = _Cache()


def reset_cache() -> None:
    """清空探针缓存 (测试用)。"""
    with _CACHE_LOCK:
        _CACHE.day = None
        _CACHE.verdict = None
        _CACHE.probed_at = 0.0


def _probe_fuyao(now: datetime) -> bool | None:
    """fuyao 交易日历: 今天在列表内 ⇔ 交易日。未配置 fuyao / 失败 → None。"""
    try:
        from app.data_providers import custom as custom_sources

        if not custom_sources.is_custom_provider("fuyao"):
            return None
        provider = custom_sources.get_provider("fuyao")
        days = provider.trading_days()
        return now.date() in days if days else None
    except Exception:  # noqa: BLE001 — 探针失败按未知处理, 不上抛
        return None


def _probe_tickflow(now: datetime) -> bool | None:
    """tickflow 行情时间戳: max(timestamp) 日期 == 今天 ⇔ 交易日。

    戳停在上一交易日: 开盘缓冲窗内 → None (可能是竞价未翻新), 窗后 → False。
    无实时权限 / 网络失败 / 无有效戳 → None。
    """
    try:
        from app.tickflow.client import get_client

        rows = get_client().quotes.get(symbols=list(_BASKET)) or []
        stamps = [r.get("timestamp") for r in rows if isinstance(r, dict)]
        valid = [int(t) for t in stamps if isinstance(t, (int, float)) and t]
        if not valid:
            return None
        latest_day = datetime.fromtimestamp(max(valid) / 1000, tz=CN_TZ).date()
        if latest_day == now.date():
            return True
        if now.time() < _STALE_BUFFER_UNTIL:
            return None
        return False
    except Exception:  # noqa: BLE001 — 无权限/网络失败按未知处理
        return None


def is_trading_day(now: datetime | None = None) -> bool | None:
    """今天是否 A 股交易日。True=交易日, False=确定休市, None=未知 (维持周几近似)。

    周末零成本直判; 工作日走探测链 (fuyao 日历 → tickflow 时间戳),
    结论按 TTL 缓存。线程安全: 实时行情与分钟增量两个线程共用。
    """
    now = now or cn_now()
    if now.weekday() >= 5:
        return False

    with _CACHE_LOCK:
        # 「未知」(None) 也是一个结论, 同样按 TTL 缓存 —— 它正是 _TTL_UNKNOWN_S 要
        # 挡住的场景 (未配 fuyao 且 tickflow 不可用时, 轮询每拍都会重打一次探测)。
        # _CACHE.day 只在探测写回时设置, 因此「当天已探过」用它判定即可。
        if (
            _CACHE.day == now.date()
            and (time.monotonic() - _CACHE.probed_at) < _ttl_of(_CACHE.verdict)
        ):
            return _CACHE.verdict

    verdict = _probe_fuyao(now)
    if verdict is None:
        verdict = _probe_tickflow(now)

    with _CACHE_LOCK:
        _CACHE.day = now.date()
        _CACHE.verdict = verdict
        _CACHE.probed_at = time.monotonic()
    return verdict


def _ttl_of(verdict: bool | None) -> float:
    if verdict is True:
        return _TTL_TRADING_S
    if verdict is False:
        return _TTL_HOLIDAY_S
    return _TTL_UNKNOWN_S


# ================================================================
# [R319] 「数据陈了几天」要按交易日算, 不按自然日
# ================================================================
#
# 今日总览的健康条原来用 `date.today() - as_of` 报「距今 N 天」—— 于是每个
# 周末它都亮: 周六「距今 1 天」、周日「2 天」、周一早上「3 天」, 而那时数据
# 完全正确(周五定稿就是最新)。健康条自己的注释写着「常驻的警告看两天就成了
# 背景板」, 这正是在自己身上发生的事。
#
# 正确的问法不是"今天离 as_of 几天", 而是**"最新一根本该落盘的日 K 是哪天,
# as_of 落后它几个交易日"**。两件事要分开定义:
#
#   · 最新一根本该落盘的日 K: 工作日且到了落盘时点(见 DAILY_BAR_LANDED_BY)
#     → 今天; 否则 → 上一个工作日。周末 / 探针已判休市的工作日, 都退到上一个
#     工作日。
#   · 落后几个交易日: (as_of, 那一天] 之间的工作日数; as_of 不早于它 → 0。
#
# **节假日只扣今天这一天**(靠探针的缓存结论), 更早的节假日不扣 —— 本地没有
# 交易日历, 与其猜不如少报: 国庆长假期间会多报几天"陈了", 那是**保守方向**的
# 误差(把正确的数据说成可能陈了), 比反过来(把陈了的数据说成正确)安全得多。
#
# 这里只读探针的**缓存**, 不主动探测: /api/today 是页面主查询, 不该因为
# 一次交易日探测(可能打网络)而多等几秒。实时行情自动开关那条线程本来就在
# 定期探, 开着的话缓存自然是热的。

# 日 K 一般 17:30~20:00 落盘(今日总览的「盘后」提示写的就是这个区间),
# 取区间末端: 20:00 之后还没落盘, 才算真的陈了。
DAILY_BAR_LANDED_BY = dt_time(20, 0)


def cached_verdict(now: datetime | None = None) -> bool | None:
    """探针**已有**的今日结论; 没探过 / 过期 / 不是今天 → None。**不触发探测。**"""
    now = now or cn_now()
    if now.weekday() >= 5:
        return False
    with _CACHE_LOCK:
        # 与上面 is_trading_day 同一个判据: 上游 e956e3a 起「未知」(None) 也是按 TTL
        # 缓存的结论, 所以这里不再要求 verdict 非空 —— 两段循环必须一致, 否则同一
        # 份缓存两种读法。
        if (
            _CACHE.day == now.date()
            and (time.monotonic() - _CACHE.probed_at) < _ttl_of(_CACHE.verdict)
        ):
            return _CACHE.verdict
    return None


def _prev_weekday(d: date) -> date:
    d -= timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def expected_latest_bar_date(now: datetime | None = None,
                             today_is_trading: bool | None = None) -> date:
    """最新一根**本该已经落盘**的日 K 是哪天。纯函数(探针结论由调用方传入)。

    today_is_trading: True/None 按工作日处理; False = 探针判了休市, 退到上一个工作日。
    """
    now = now or cn_now()
    today = now.date()
    if (now.weekday() < 5 and today_is_trading is not False
            and now.time() >= DAILY_BAR_LANDED_BY):
        return today
    return _prev_weekday(today)


def weekdays_between(a: date, b: date) -> int:
    """(a, b] 之间的工作日数; b <= a → 0。节假日不扣(见上面的说明)。"""
    if b <= a:
        return 0
    n, d = 0, a
    while d < b:
        d += timedelta(days=1)
        if d.weekday() < 5:
            n += 1
    return n


def stale_trading_days(as_of: date, now: datetime | None = None,
                       today_is_trading: bool | None = None) -> int:
    """as_of 落后「最新一根本该落盘的日 K」几个交易日。0 = 不陈。"""
    return weekdays_between(as_of, expected_latest_bar_date(now, today_is_trading))
