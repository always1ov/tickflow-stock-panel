"""[fork R513] 模拟盘「今日信号」重做 —— 不折叠, 三段一次摊开, 每段一种长相。

用户: 「今日页面这个页面重做, 改的好看点, 不要折叠了, 你自己设计」, 看过效果图后「确认」。

    要动手   卡片(ActionCard), 字最大、色最重; 名次与走势两格原样留着
    持仓     方块(HoldingTile), 每块一根离清仓线的距离条
    盯着     一只一行密排(WatchGroup), 多列, 色最淡; 按转了会不会变成动作分两组

原来那套定宽网格与两处折叠的守卫(R331 / R350 / R355 / R356 / R360 / R366 / R381 / R384~R386)
在 test_flip_fusion / test_flip_today 里退役或改了钉法; 出手铁律、打分只排序、两个弹窗各开各的
那几条仍在原处。这里钉新版面自己的性质。
"""
from __future__ import annotations

from tests.frontend_source import code_of

FLIP = "pages/FlipPaper.tsx"


def _fn(name: str) -> str:
    code = code_of(FLIP)
    blk = code[code.index(f"function {name}("):]
    nxt = blk.find("\nfunction ", 1)
    return blk if nxt < 0 else blk[:nxt]


def _today() -> str:
    code = code_of(FLIP)
    return code[code.index("function TodaySignals"):code.index("function ZoneHead")]


def test_R513_三段各用各的组件_次序是要动手_持仓_盯着():
    blk = _today()
    order = ['<ZoneHead title="要动手"', "<ActionCard", '<ZoneHead title="持仓"', "<HoldingTile",
             '<ZoneHead title="盯着"', "<WatchGroup"]
    idx = [blk.index(t) for t in order]
    assert idx == sorted(idx), f"三段次序乱了: {order}"
    assert "SignalRow" not in code_of(FLIP) and "ROW_GRID" not in code_of(FLIP), "旧的定宽网格还留着"


def test_R513_盯着按转了会不会变成动作分两组_判据只看side():
    """没拿着的票: 空头侧站上触发价转多 → 转了就是买入; 多头侧跌破转空 → 没拿着, 转了也没有动作。
    分组只看后端给的 `side`, 打分一分不参与; 两组都全列出来, 不折叠。"""
    blk = _today()
    assert "const toBull = byRank(idle.filter((r) => r.side === '空头'))" in blk
    assert "const toBear = byRank(idle.filter((r) => r.side !== '空头'))" in blk, "两组必须互为补集"
    assert blk.index('title="离转多" note="转了就是买点"') < blk.index('title="离转空" note="没拿着, 转了也不用动"'), \
        "能变成买点的那组该排在前面"


def test_R513_两组的说法与后端的出手判据对得上():
    """「转了就是买点」「转了也不用动」这两句是对后端 `evaluate` 的转述 —— 后端改了, 这两句就成了假话。
    所以直接跑判据: 没拿着的票, 空头侧(DT)转成多头 → 买入; 多头侧(UT)转成空头 → 没有动作。"""
    from app.services import flip_today as ft
    from tests.test_flip_today import _steps
    # 盯着时 side 是转折**之前**那一侧 —— 离转多的那组 side=bear, 转了之后:
    up = ft.evaluate(_steps(["DT", "UT"]), held=False, last_close=10.0)
    assert up is not None and up["act"] == ft.ACT_BUY, "没拿着的票转多不再是买入 —— 「转了就是买点」成了假话"
    # 离转空的那组 side=bull, 没拿着, 转了之后:
    down = ft.evaluate(_steps(["UT", "DT"]), held=False, last_close=10.0)
    assert down is not None and down["act"] is None, "没拿着的票转空有了动作 —— 「转了也不用动」成了假话"
    # 盯着那一侧的 side 确实是转折之前的那一侧(前端靠它分组)
    watch_bear = ft.evaluate(_steps(["DT", "DT"], flip_up=10.2), held=False, last_close=10.0)
    # 前端拿 `r.side === '空头'` 分组 —— 这个字面量必须就是后端发出来的那个值
    from app.services.flip_trades import BEAR
    assert watch_bear is not None and watch_bear["side"] == BEAR == "空头" and watch_bear["stage"] == ft.STAGE_WATCH
    assert f"r.side === '{BEAR}'" in _today(), "前端分组用的字面量与后端发出的 side 对不上"


def test_R513_持仓方块的距离条_只画不判():
    """条越短越贴近清仓线, 满格是 EXIT_GAUGE_FULL 以上。它只影响条的长短, 不产生任何动作;
    也不给宽度加过渡 —— 宽度动画每帧重排, 且数据不加装饰性动效。"""
    code = code_of(FLIP)
    assert "const EXIT_GAUGE_FULL = 0.10" in code
    tile = _fn("HoldingTile")
    assert "Math.min(1, dist / EXIT_GAUGE_FULL)" in tile
    assert "style={{ width: `${Math.max(fill * 100, 3)}%` }}" in tile
    for banned in ("transition-all", "transition-[width]", "animate-", "motion"):
        assert banned not in tile, f"距离条上出现了动效: {banned}"


def test_R513_盯着那一段是列优先的密排():
    """上百只一次摊开又不淹掉上面两段: 行矮(h-7)、多列; 多列用 CSS columns(列优先), 次序与打分排的一致。"""
    wg = _fn("WatchGroup")
    assert "sm:columns-2" in wg and "lg:columns-3" in wg and "2xl:columns-4" in wg and "min-[1800px]:columns-5" in wg
    assert "break-inside-avoid" in wg and "grid-cols" not in wg, "用了 grid —— 行优先会把次序打乱"
    assert "flex h-7" in wg


def test_R513_手机上持仓一排两块_方块里的说明让位给价格():
    blk = _today()
    assert "grid grid-cols-2 gap-2 lg:grid-cols-3 2xl:grid-cols-5" in blk
    tile = _fn("HoldingTile")
    assert '<span className="hidden shrink-0 sm:inline">离清仓线</span>' in tile, "手机上「离清仓线」会被挤成竖排"


def test_R513_三段都不加装饰性动效():
    """AGENTS.md 硬规则第 7 条: 功能性数据不做「跳动」「流动」。只许颜色过渡(hover)。"""
    for comp in ("ActionCard", "HoldingTile", "WatchGroup", "ZoneHead", "SymbolButton", "StateLine"):
        src = _fn(comp)
        for banned in ("animate-", "motion", "transition-all", "translate", "hover:scale", "transition-transform"):
            assert banned not in src, f"{comp} 里出现了 {banned}"
