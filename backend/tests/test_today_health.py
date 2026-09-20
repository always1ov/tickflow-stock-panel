"""[R274] 今日总览自检 —— **每一次静默跳过都要有人知道**。

用户: 「有没有办法验证今日总览的所有显示有没有问题、是否在正常工作」。

## 问题不在"会不会崩", 在"崩了没人知道"

这一页的构建过程里有十几处 `try/except`, 每一处都是**只写一行日志然后继续**。
那个设计本身是对的(中观算不出来不该拖垮整页), 但它缺了另一半: 失败之后页面照常
渲染, 那个区块只是空的, 而看的人**根本分不出「今天真没有」和「算挂了」**。
日志在服务器上, 没人会去翻。

这一组里分量最重的是 `test_R274_每一处跳过都要登记`: 只要有人加了新的 `except`
却忘了 `_h.skip(...)`, 那一处就悄悄退回了"静默跳过" —— 而那正是这轮要根治的东西。
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path

import pytest

from app.api.today import _Health

TODAY_PY = Path(__file__).resolve().parents[1] / "app" / "api" / "today.py"


def _builder_src() -> str:
    """`_build_overview` 的函数体 —— 自检要覆盖的就是这一段。"""
    s = TODAY_PY.read_text(encoding="utf-8")
    a = s.index("def _build_overview(")
    b = s.index("\n@router.get(\"\")", a)
    return s[a:b]


# ================================================================
# 登记表不许漏 —— 这一条是其余全部结论的前提
# ================================================================

def test_R274_每一处跳过都要登记():
    """扫 `_build_overview` 里每一个 `except`, 后面必须跟着 `_h.skip(...)`。

    漏一处 = 那个区块又变回"挂了也没人知道"。而这种漏是**最容易发生**的:
    加一段新逻辑、顺手包个 try/except 防它拖垮整页 —— 完全合理, 但自检就此有个洞。
    """
    src = _builder_src()
    lines = src.splitlines()
    misses: list[str] = []
    for i, ln in enumerate(lines):
        if not ln.strip().startswith("except "):
            continue
        # 往后看几行(日志 + skip 通常挨着)
        window = "\n".join(lines[i + 1:i + 5])
        if "_h.skip(" not in window:
            misses.append(f"第 {i + 1} 行附近: {ln.strip()}")
    assert not misses, (
        "这些 except 没有登记进自检 —— 那一处的失败在界面上看不见:\n  "
        + "\n  ".join(misses))


def test_R274_登记的key都在名录里():
    """`_h.skip("xxx")` 里的 key 必须在 `SITES` 中有中文名和档次 ——
    否则界面上会冒出一个英文 key, 而人不知道那是哪一块。"""
    used = set(re.findall(r'_h\.skip\("([a-z_]+)"', _builder_src()))
    assert used, "一处都没登记?"
    unknown = sorted(used - set(_Health.SITES))
    assert not unknown, f"这些 key 没在 _Health.SITES 里登记: {unknown}"


def test_R274_名录里不许有没人用的key():
    """反向也要守: 删掉一段逻辑却留着名录项, 名录就开始说假话。"""
    used = set(re.findall(r'_h\.skip\("([a-z_]+)"', _builder_src()))
    stale = sorted(set(_Health.SITES) - used)
    assert not stale, f"这些 key 名录里有、代码里没人用: {stale}"


def test_R274_每一项都说清楚是整块缺还是少个标():
    """后果不一样: 整块没了界面上是空的(得醒目), 少个标主体还在(提一句就够)。
    分错档的话, 要么把小事报成大事、要么把大事说得像小事。"""
    for key, (cn, level) in _Health.SITES.items():
        assert cn and not cn.isascii(), f"{key} 没有给人看的中文名"
        assert level in ("block", "detail"), f"{key} 的档次是 {level}"


# ================================================================
# 收集器本身
# ================================================================

def test_R274_没跳过就是健康():
    rep = _Health().report("2026-09-10")
    assert rep["ok"] is True and rep["blocks"] == [] and rep["details"] == []


def test_R274_整块与少个标分开报():
    h = _Health()
    h.skip("meso", "boom")           # block
    h.skip("annotations", "boom")    # detail
    rep = h.report("2026-09-10")
    assert rep["ok"] is False
    assert [r["key"] for r in rep["blocks"]] == ["meso"]
    assert [r["key"] for r in rep["details"]] == ["annotations"]


def test_R274_同一处反复失败只记一条错但要计数():
    """逐只算 ATR 那种循环里, 一次网络抖动能刷出几百条一模一样的。"""
    h = _Health()
    for i in range(300):
        h.skip("atr_load", f"第 {i} 次")
    rep = h.report("2026-09-10")
    row = rep["details"][0]
    assert row["n"] == 300
    assert row["error"] == "第 0 次", "留第一条, 后面的只计数"


def test_R274_错误文本有上限():
    """堆栈之类的长文本会把响应撑大, 而报告只需要够定位。"""
    h = _Health()
    h.skip("meso", "x" * 5000)
    assert len(h.report("2026-09-10")["blocks"][0]["error"]) <= 200


def test_R274_报出数据陈了几天():
    """**另一类问题**: 什么都没报错, 但整页数字是几天前的 —— 收盘后管道没跑就是这样。
    它和"算挂了"一样会让人看着假数据做决定。

    [R319] 口径从自然日改成**交易日**(见下面 R319 那一组)。这条守的意图没变:
    陈了要报、没陈不报 —— 只是把"几天"钉在一个固定的时点上算, 不再随今天是周几漂。
    """
    from datetime import datetime
    from app.services.trading_day import CN_TZ
    wed_night = datetime(2026, 9, 16, 21, 0, tzinfo=CN_TZ)      # 周三 21:00, 当天那根该落盘了
    assert _Health().report("2026-09-11", now=wed_night)["stale_days"] == 3   # 周五的数据: 一二三
    assert _Health().report("2026-09-16", now=wed_night)["stale_days"] == 0   # 当天的数据: 不陈


def test_R274_日期坏了不抛():
    for bad in (None, "", "不是日期", "2026-13-99"):
        rep = _Health().report(bad)
        assert rep["stale_days"] is None


def test_R274_未登记的key也不抛只是没中文名():
    """名录漏了不该让整页 500 —— 有守卫在测试里拦, 运行时降级就好。"""
    h = _Health()
    h.skip("从没见过的东西", "boom")
    assert h.report("2026-09-10")["details"][0]["cn"] == "从没见过的东西"


# ================================================================
# 接进响应
# ================================================================

def test_R274_health进了总览响应():
    src = TODAY_PY.read_text(encoding="utf-8")
    body = src[src.index("def _build_overview("):]
    body = body[:body.index("\n@router.get(\"\")")]
    assert '"health": _h.report(as_of)' in body


@pytest.mark.parametrize("key", sorted(_Health.SITES))
def test_R274_名录每一项都真的接在代码里(key):
    """逐项点名 —— 整表比对一次会把"少了哪一个"混成一条失败。"""
    assert f'_h.skip("{key}"' in _builder_src()


# ================================================================
# 界面上真的说出来了
# ================================================================

def _page() -> str:
    """[R351] 今日总览删了 —— 这个 helper 指向模拟盘。

    它现在是自检条、市场状态与那份 `/api/today` 数据唯一的落脚页, 下面那几条
    守卫要守的东西一样没变, 只是换了一个文件去找。
    """
    from tests.frontend_source import code_of
    return code_of("pages/FlipPaper.tsx")


def _bar() -> str:
    """[R341] 自检条从 `pages/Today.tsx` 拆成了独立组件 —— 模拟盘也要用它。

    **下面那几条守的东西一个字没变**(正常时不渲染、陈数据要报、整块与少个标分开说、
    措辞按交易日), 换的只是它们去哪个文件里找。
    """
    from tests.frontend_source import code_of
    return code_of("components/today/TodayHealthBar.tsx")


def test_R274_自检条被挂在页面上():
    """组件存在不等于被挂上去了 —— 两页都得真的渲染它。"""
    from tests.frontend_source import code_of

    assert "export function TodayHealthBar" in _bar()
    # [R351] 今日总览删了, 自检条现在只挂在模拟盘上 —— 但「组件存在 ≠ 被挂上去」
    # 这条立论不变, 只是要守的页面从两个变成一个。
    for page in ("pages/FlipPaper.tsx",):
        code = code_of(page)
        assert "<TodayHealthBar h=" in code, f"{page} 没把自检条挂上去"
        assert "from '@/components/today/TodayHealthBar'" in code


def test_R274_一切正常时不渲染任何东西():
    """常驻一条「运行正常」的绿条, 看两天就成了背景板 —— 真出问题那天照样被忽略。"""
    body = _bar()
    assert "if (h.ok && !stale) return null" in body


def test_R274_陈数据也要报():
    """**这一条最阴**: 什么都没报错, 页面看起来完全正常, 而你在用几天前的数字做决定。"""
    body = _bar()
    assert "stale" in body and "h.stale_days" in body


def test_R274_整块与少个标在界面上分开说():
    """分不开的话, 要么把小事报成大事、要么把大事说得像小事。"""
    body = _bar()
    assert "h.blocks.length" in body and "h.details.length" in body
    assert "不是「今天没有」" in body, "得说清空是因为算挂了, 不是今天真没有"


# ================================================================
# [R319] 「陈了几天」按交易日算, 不按自然日
# ================================================================
#
# 原来 `date.today() - as_of`: 每个周末健康条都亮 —— 周六「距今 1 天」、周日
# 「2 天」、周一早上「3 天」, 而周五的定稿就是最新数据。健康条自己的注释写着
# 「常驻的警告看两天就成了背景板」, 这正是在它自己身上发生的事。
#
# 新口径: as_of 落后「最新一根**本该已落盘**的日 K」几个交易日。落盘时点取
# 20:00(今日总览「盘后」提示写的 17:30~20:00 区间末端)。

from datetime import date, datetime

from app.services import trading_day as td

_TZ = td.CN_TZ


def _at(y, m, d, hh=12, mm=0):
    return datetime(y, m, d, hh, mm, tzinfo=_TZ)


# 2026-09-11 是周五; 12/13 周末; 14 周一。
_FRI = date(2026, 9, 11)


def test_R319_周末不算陈():
    """周六、周日: 最新该落盘的仍是周五那根, 周五的 as_of 落后 0。"""
    assert td.stale_trading_days(_FRI, now=_at(2026, 9, 12)) == 0
    assert td.stale_trading_days(_FRI, now=_at(2026, 9, 13, 23, 59)) == 0


def test_R319_周一落盘前不算陈_落盘后算一天():
    """周一 20:00 之前, 今天这根还没到该落盘的时候; 之后没落就是陈了 1 个交易日。"""
    assert td.stale_trading_days(_FRI, now=_at(2026, 9, 14, 9, 30)) == 0
    assert td.stale_trading_days(_FRI, now=_at(2026, 9, 14, 19, 59)) == 0
    assert td.stale_trading_days(_FRI, now=_at(2026, 9, 14, 20, 0)) == 1


def test_R319_落后多天只数工作日():
    """周五的 as_of, 到下周三晚上: 一、二、三 = 3 个交易日, 周末那两天不数。"""
    assert td.stale_trading_days(_FRI, now=_at(2026, 9, 16, 21)) == 3
    # 自然日是 5 天 —— 这正是旧算法会报的数
    assert (date(2026, 9, 16) - _FRI).days == 5


def test_R319_探针判了休市就退到上一个工作日():
    """工作日但探针说休市(节假日): 今天这根本就不该有, 不算陈。"""
    # 周一 21:00, 探针说今天休市 → 最新该落盘的仍是周五那根
    assert td.stale_trading_days(_FRI, now=_at(2026, 9, 14, 21), today_is_trading=False) == 0
    # 探针未知(None)按工作日处理 —— 保守方向: 宁可多报"可能陈了"
    assert td.stale_trading_days(_FRI, now=_at(2026, 9, 14, 21), today_is_trading=None) == 1


def test_R319_as_of_不早于该落盘那天就是零():
    """实时叠加层开着时 as_of 会是今天(盘中临时口径), 不许算成负数或报错。"""
    assert td.stale_trading_days(date(2026, 9, 14), now=_at(2026, 9, 14, 10)) == 0
    assert td.stale_trading_days(date(2026, 9, 14), now=_at(2026, 9, 14, 21)) == 0


def test_R319_健康条走的是交易日口径():
    """`_Health.report` 必须调这一套, 不许自己再减自然日。"""
    import inspect
    src = inspect.getsource(_Health.report)
    assert "stale_trading_days" in src, "健康条没走交易日口径"
    assert "date.today() - " not in src, "健康条又在减自然日了"
    # 端到端: 周六看周五的数据, 不该报陈
    rep = _Health().report("2026-09-11")
    # 只在真的周末时才能断言 0 —— 这条不依赖今天是周几, 只确认字段存在且非负
    assert rep["stale_days"] is None or rep["stale_days"] >= 0


def test_R319_只读探针缓存不主动探测():
    """`/api/today` 是页面主查询, 不该为一次交易日探测(可能打网络)多等几秒。

    `cached_verdict` 只看缓存: 没探过就 None, 而且**不能**把 `_probe_*` 叫起来。
    """
    import inspect
    src = inspect.getsource(td.cached_verdict)
    assert "_probe_" not in src, "cached_verdict 主动探测了"
    td.reset_cache()
    # 工作日、缓存为空 → None(未知), 不是 True/False
    assert td.cached_verdict(_at(2026, 9, 14, 12)) is None
    # 周末零成本直判, 与 is_trading_day 一致
    assert td.cached_verdict(_at(2026, 9, 12)) is False
    # 健康条那一行只许用缓存版
    body = _builder_src() if "_builder_src" in globals() else ""
    src2 = inspect.getsource(_Health.report)
    assert "cached_verdict" in src2 and "is_trading_day(" not in src2, (
        "健康条调了会主动探测的 is_trading_day —— 页面主查询会被拖慢"
    )


# ================================================================
# [R319] 实时质量: 标签承诺的和数据给的必须是一回事
# ================================================================
#
# 页头写着「● 实时中(N 只)」, 但页面原来不分时段一律每小时重取 —— 「盘中」列
# 里的价格可能是 59 分钟前的。后端行情层每 6 秒轮一次, 瓶颈全在前端节奏。
# 三处一起改: ① 盘中开着实时时 60 秒一刷; ② 切实时开关后立刻重取(原来全站
# 没有任何地方 invalidate 这个查询); ③ 「现在是不是盘中」收成一处产地。


def test_R319_盘中开着实时时六十秒一刷():
    """`refetchInterval` 必须是**函数**, 而且同时看两件事: 后端说实时叠加层在
    (`live`)、现在在实时窗口里。缺一个都不对 —— 只看时段, 关着实时也会每分钟
    白算一次全量; 只看 live, 盘后叠加层残留时也会一直刷。"""
    from tests.frontend_source import code_of

    # [R342] 这条查询的调用方涨到三个(今日总览页 / 模拟盘补充带 / 模拟盘按把握分
    # 排序), 节奏因此收到 `useTodayOverview` **一处定义**。守卫跟着挪到那一处 ——
    # 「三个调用方都不许自己抄一份」由 test_R342_今日总览那份数据只有一处定义 管。
    page = code_of("lib/useSharedQueries.ts")
    q = page[page.index("export function useTodayOverview"):]
    q = q[:q.index("refetchOnWindowFocus")]
    assert "refetchInterval: (query) =>" in q, "刷新间隔不是按状态算的函数"
    assert "?.live" in q, "没看后端的 live 标志"
    assert "inRealtimeWindow()" in q, "没看现在是不是实时窗口"
    assert "60_000" in q and "60 * 60 * 1000" in q, "两档节奏(60 秒 / 每小时)不全"
    assert "from './marketClock'" in page, "时段判断没走共用的市场时钟"


def test_R319_两个实时开关都让今日总览重取():
    """开关有两个入口(自动开关在 Layout, 直接开关在 useSharedMutations 的 hook),
    漏一个就是: 用那个入口切换的人看到的页头一直是旧状态。"""
    from tests.frontend_source import code_of
    layout = code_of("components/Layout.tsx")
    i = layout.index("const toggleRealtimeAuto = useMutation")
    # 切到 useMutation 调用的收尾 `\n  })`, 不能切到第一个 `})` —— 那会撞上
    # `invalidateQueries({ … })` 自己的括号, 把后面的行切掉(第一版就这么假红了)。
    blk = layout[i:layout.index("\n  })", i)]
    assert "QK.todayOverview" in blk, "自动开关切换后没让今日总览重取"

    hook = code_of("lib/useSharedMutations.ts")
    i = hook.index("export function useToggleRealtimeQuotes")
    blk = hook[i:hook.index("\n}\n", i)]
    assert "QK.todayOverview" in blk, "直接开关切换后没让今日总览重取"


def test_R319_市场时钟只有一处产地():
    """「现在是盘前/盘中/盘后」原来写在 MarketStatusCard 里; 今日总览要按它定
    刷新节奏, 第二个消费方一出现就得抽出来 —— 两处各自换时区算, 边界迟早对不上,
    卡片说「盘中」而页面按盘后节奏刷, 没有任何东西会报错。"""
    from tests.frontend_source import code_of
    clock = code_of("lib/marketClock.ts")
    for fn in ("export function cnClock", "export function cnMarketPhase", "export function inRealtimeWindow"):
        assert fn in clock, f"市场时钟缺了 {fn}"
    # 实时窗口的边界照抄后端 realtime_schedule(09:15 / 15:05)
    win = clock[clock.index("export function inRealtimeWindow"):]
    assert "9 * 60 + 15" in win and "15 * 60 + 5" in win, "实时窗口边界与后端 realtime_schedule 不一致"

    # [R351] `MarketStatusCard` 随今日总览一起删了 —— 它那段时段提示并进了模拟盘
    # 页头。**立论一个字没变**(时钟只许有一处产地), 要扫的消费方换成了现存的这些。
    #
    # **改成全仓扫**, 而不是点名某几个文件: 点名的写法会随着文件增删反复失效,
    # 而这条规矩本来就是"**谁都不许自己换时区**"。
    from tests.frontend_source import SRC

    # **两处已知欠账**, 早于 R319 就存在(那一轮只修了卡片与今日总览):
    #   · SectorRotationCard.beijingDateParts()  自己算 {date, minutes}
    #   · lib/kline.ts 的 cnToday() / cnNowHHMM() 配 MARKET_ALL_OVER='15:30'
    # 两个都**真的在判时段**, 不是格式化时间戳 —— 立论说的就是它们。没有当场修:
    # `marketClock` 现在只出 `{day, mins}`, 要接这两处得先给它加日期字符串的出口,
    # 那是另一件事。**记在这儿而不是让守卫绕开它们** —— 名单摆在明面上, 才不会
    # 被下一个人当成"本来就允许"。
    KNOWN_DEBT = {"components/SectorRotationCard.tsx", "lib/kline.ts"}

    # [R371] 上游新增了 `lib/format.ts` 的 cnDateFromUtc/cnDateTimeFromUtc: 把
    # **调用方传进来的**时间戳按北京时间渲染, 自己从不取"现在"。上面那句立论说的是
    # 「谁都不许自己换时区判时段」—— 纯格式化器不在其内(这条区分本来就写在 KNOWN_DEBT
    # 上面那段注释里)。所以扫法收紧一层: 把**当前时刻**喂进时区格式化器的才算产地。
    # 两张名单都双向自证, 谁也不能靠"曾经允许过"混进来。
    now_fed = re.compile(r"\.(?:format|formatToParts)\(\s*new Date\(\)\s*\)")
    shanghai = {
        f.relative_to(SRC).as_posix(): src
        for f in SRC.rglob("*.ts*")
        if f.name != "marketClock.ts"
        and "timeZone: 'Asia/Shanghai'" in (src := f.read_text(encoding="utf-8"))
    }
    assert shanghai, "一个换时区的文件都没扫到 —— 扫法本身坏了"
    clocks = {p for p, src in shanghai.items() if now_fed.search(src)}
    formatters = set(shanghai) - clocks

    assert not (clocks - KNOWN_DEBT), \
        f"又出现了新的第二处产地: {sorted(clocks - KNOWN_DEBT)}"
    # 欠账还清了就把名单也删掉 —— 不许留一份"曾经允许过"的清单
    stale = KNOWN_DEBT - clocks
    assert not stale, f"这些已经不再自己换时区了, 把它们从 KNOWN_DEBT 里删掉: {sorted(stale)}"

    # 纯格式化器也得一个个过目 —— 新冒出来的必须先确认它真的只格式化传进来的时间戳
    PURE_FORMATTERS = {"lib/format.ts"}
    assert formatters == PURE_FORMATTERS, \
        f"换时区的纯格式化器名单对不上: 多了 {sorted(formatters - PURE_FORMATTERS)}, 少了 {sorted(PURE_FORMATTERS - formatters)}"


def test_R319_健康条措辞跟着交易日口径走():
    """后端按交易日算了, 页面还写「距今 N 天」的话, 周一早上看到「1」会以为是
    自然日在数。措辞与口径必须一起换。"""
    body = _bar()
    assert "个交易日" in body, "健康条没说清是交易日"
    assert "距今 {h.stale_days} 天" not in body, "健康条还在说「距今 N 天」—— 那是自然日的说法"
