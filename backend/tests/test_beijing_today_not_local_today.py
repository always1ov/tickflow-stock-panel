"""[fork R414] 把「等北京午夜才会红」变成「任何时候都会红」。

## 病是什么

`app/api/kline.py` 与 `app/services/abnormal_moves.py` 判"是不是今天"用的是
**北京日期** `cn_today()`。而测试如果拿 `date.today()`(进程本地时区, 容器是
UTC)去造数据, 两边**只在一天里的某一段对得上**:

    UTC 00:00~16:00  →  本地日期 == 北京日期  →  测试绿
    UTC 16:00~24:00  →  北京已跨日, 本地没有  →  测试红

于是这几条测试**每天到点自己变红, 白天又自己变绿**。这比测错更坏:
红色变成了噪音, 人会习惯性忽略它 —— 而下一次真的测出问题时也就被一起忽略了。

## 为什么值得单独立一条守卫

**这个坑在这个仓库里犯过两次。** `test_abnormal_moves.py` 里那条
`test_benchmark_momentum_today_excludes_today_rows` 早就修过一次, 注释还在,
写着「CI 跑在 UTC 上正好每天踩中这一段」—— 但**当时没有扫一遍别处**,
于是同一个文件里另外两处、外加 `test_kline_live_candle.py` 两处, 一共四处
带着同样的写法活了下来, 直到 R411 那一轮跑全量时才撞见。

光把那四处改对是不够的: 下一个人写新测试时照样会写 `date.today()`,
而他在白天跑, 全绿。

## 这条守卫怎么做

**不去扫"有没有写 `date.today()`"**(那是钉措辞, 而且 `date.today()` 在别处
有大量正当用法), 而是**把时差直接造出来**: 把 `cn_today` 换成"本地日期 + 1 天",
再把那几条测试原样跑一遍。

  · 测试用的是 `cn_today()` → 造数据和被测代码用的是同一个(被挪过的)日期 → 绿
  · 测试用的是 `date.today()` → 两边差一天 → **当场红, 不用等到半夜**

也就是说: 这条守卫把那个只在特定时段出现的 bug, 变成了**任何时候都会出现**。
"""
from __future__ import annotations

from datetime import date, timedelta

import app.api.kline as kline_mod
import app.services.abnormal_moves as am_mod
import tests.test_abnormal_moves as t_am
import tests.test_kline_live_candle as t_kline


def _shift(monkeypatch) -> date:
    """把"北京今天"挪到本地日期的后一天 —— 模拟北京已跨日、本地还没跨。

    **四处都要挪**: 被测模块各自 `from app.market_time import cn_today` 拿的是
    自己模块里的引用, 只改 `app.market_time` 那一份是没用的(它们已经绑好了)。
    测试模块那两份也要挪, 否则测试造的数据仍然是旧日期 —— 那就变成测试自己
    在造时差, 不是在验被测代码。
    """
    fake = date.today() + timedelta(days=1)
    for mod in (kline_mod, am_mod, t_kline, t_am):
        if hasattr(mod, "cn_today"):
            monkeypatch.setattr(mod, "cn_today", lambda: fake)
    return fake


def test_R414_北京已跨日时_当日蜡烛注入照样对(monkeypatch):
    """`test_kline_live_candle` 那两条, 在时差窗口里重跑一遍。"""
    _shift(monkeypatch)
    t_kline.test_overlay_row_becomes_today_candle()
    t_kline.test_existing_today_row_is_overwritten_not_duplicated()


def test_R414_北京已跨日时_异动总览照样不重复计(monkeypatch):
    """`test_abnormal_moves` 那两条, 同上。"""
    _shift(monkeypatch)
    t_am.test_build_overview_cache_date_today_no_double_count()
    t_am.test_build_overview_negative_side_stricter_threshold()


def test_R414_这条守卫自己没哑掉(monkeypatch):
    """**守卫也要被验。**

    这个仓库栽过好几次「守卫不报错, 只是不吭声了」(R404 那条正则别名是最近的
    一次)。这里的哑法很具体: `_shift` 如果漏掉某个模块的引用, 时差根本没造出来,
    上面两条就退化成"普通重跑一遍", 永远绿。

    所以这里反过来证一次: **时差确实造出来了** —— 被测模块看到的"今天"
    必须与本地日期不同, 而且正好差一天。
    """
    fake = _shift(monkeypatch)
    assert fake != date.today(), "时差没造出来"
    assert kline_mod.cn_today() == fake, "kline 模块里的 cn_today 没被挪"
    assert am_mod.cn_today() == fake, "abnormal_moves 模块里的 cn_today 没被挪"
    assert t_kline.cn_today() == fake, "测试模块 test_kline_live_candle 里的没被挪"
    assert t_am.cn_today() == fake, "测试模块 test_abnormal_moves 里的没被挪"
