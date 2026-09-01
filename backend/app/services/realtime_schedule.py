"""[fork 增强] R118 实时行情「自动开关」的时段判定(纯函数)。

用途: 用户不想每天早上手动打开、晚上手动关掉实时行情开关 —— 打开「自动」后
由后台按**交易日 + 交易时段**自己开关。

这里只回答一个问题: 此刻实时行情**应该**是开还是关。真正的开关动作、边沿判定、
线程生命周期都在 `quote_service` 里, 本模块不碰状态, 好单测。

时段(北京时间):
    09:15 开 —— 集合竞价就开始拉(轮询循环的 preopen 阶段本就会取数)
    15:05 关 —— 收盘后留 5 分钟给「收盘定版」那一版快照落定
    午休(11:30-13:00)**不关** —— 轮询循环自己会跳过取数, 而 11:30 的午休
    定版需要线程还活着; 中途关掉反而丢一版。

交易日: 走 `trading_day.is_trading_day()` 探针。
    True  → 按时段开关
    False → 一律关(周末与节假日)
    None  → 未知, 沿用探针本身的口径「维持周几近似」, 即工作日按开处理 ——
            宁可多开一段(轮询里还有休市门控兜底, 不会真去打请求),
            也不要在真交易日把用户的行情关掉。
"""
from __future__ import annotations

from datetime import datetime, time as dt_time

AUTO_ON = dt_time(9, 15)
AUTO_OFF = dt_time(15, 5)
# 收盘定版没成功时可以拖到这个点, 再晚就无条件关(防止一直失败挂着不停)
AUTO_OFF_HARD = dt_time(15, 40)


def desired_state(now: datetime, is_trading: bool | None) -> bool:
    """此刻实时行情应该开着吗。"""
    if is_trading is False:
        return False
    if now.weekday() >= 5:      # 探针返回 None 时的兜底: 周末一律关
        return False
    return AUTO_ON <= now.time() < AUTO_OFF


def in_grace_window(now: datetime) -> bool:
    """处于「该关了, 但收盘定版还没成功」的宽限期内(15:05~15:40)。"""
    return now.weekday() < 5 and AUTO_OFF <= now.time() < AUTO_OFF_HARD


def window_label() -> str:
    """给界面显示的一句话。"""
    return f"交易日 {AUTO_ON.strftime('%H:%M')} 自动开, {AUTO_OFF.strftime('%H:%M')} 自动关"
