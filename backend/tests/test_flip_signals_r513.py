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
    ends = [e for e in (blk.find("\nfunction ", 1), blk.find("\nconst ", 1), blk.find("\n/**", 1)) if e > 0]
    return blk[:min(ends)] if ends else blk   # 截到下一个顶层声明(函数 / 常量 / 文档注释)


def _today() -> str:
    code = code_of(FLIP)
    return code[code.index("function TodaySignals"):code.index("function ZoneHead")]


def test_R513_各段各用各的组件_次序是要动手_持仓():
    blk = _today()
    order = ['<ZoneHead title="要动手"', "<ActionCard", '<ZoneHead title="持仓"', "<HoldingTile"]
    idx = [blk.index(t) for t in order]
    assert idx == sorted(idx), f"次序乱了: {order}"
    assert "SignalRow" not in code_of(FLIP) and "ROW_GRID" not in code_of(FLIP), "旧的定宽网格还留着"


def test_R516_盯着整段撤掉_没拿着又没转的票一行都不画():
    """用户: 「不要盯着」(R513 全列九十几行 → R515 只列快转多几只 → 整段撤掉)。
    交易只在收盘转折那一刻发生, 还没转的票转了那天会出现在「要动手」里。
    钉的是**性质**, 不是某个变量名: 渲染出去的只有要动手(isLive)与持仓(held)两段 ——
    没拿着、也没到转折的那一侧, 在 JSX 里没有任何一处 map 它。"""
    blk = _today()
    code = code_of(FLIP)
    assert "function WatchGroup(" not in code and "<WatchGroup" not in code, "盯着那一组的组件又回来了"
    assert '<ZoneHead title="盯着"' not in blk, "「盯着」那一段又回来了"
    assert "!r.held" not in blk, "又挑出了没拿着的那一侧 —— 挑出来就是要画的"
    jsx = blk[blk.index("return ("):]
    maps = [m for m in ("ordered.map(", "mineSorted.map(") if m in jsx]
    assert maps == ["ordered.map(", "mineSorted.map("] and jsx.count(".map(") == 2, \
        "信号栏里多了一处 map —— 除了要动手与持仓, 别的票不该画出来"
    assert "还没转的票不列" in code, "提示里没说还没转的票去哪儿了"


# [R516] `test_R513_R515_盯着只列快转多的那几只_判据只看side与距离` 退役 —— 用户: 「不要盯着」—— 今日信号里「盯着」那一段整个撤掉(还没转的票转了那天会出现在「要动手」里); 「还没转、没拿着的票一行都不画」的钉法在 test_flip_signals_r513.py 的 test_R516_盯着整段撤掉


# [R516] `test_R513_两组的说法与后端的出手判据对得上` 退役 —— 用户: 「不要盯着」—— 今日信号里「盯着」那一段整个撤掉(还没转的票转了那天会出现在「要动手」里); 「还没转、没拿着的票一行都不画」的钉法在 test_flip_signals_r513.py 的 test_R516_盯着整段撤掉


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


# [R516] `test_R513_盯着那一段是列优先的密排` 退役 —— 用户: 「不要盯着」—— 今日信号里「盯着」那一段整个撤掉(还没转的票转了那天会出现在「要动手」里); 「还没转、没拿着的票一行都不画」的钉法在 test_flip_signals_r513.py 的 test_R516_盯着整段撤掉


def test_R513_手机上持仓一排两块_方块里的说明让位给价格():
    blk = _today()
    assert "grid grid-cols-2 gap-2 lg:grid-cols-3 2xl:grid-cols-5" in blk
    tile = _fn("HoldingTile")
    assert '<span className="hidden shrink-0 sm:inline">离清仓线</span>' in tile, "手机上「离清仓线」会被挤成竖排"


def test_R513_三段都不加装饰性动效():
    """AGENTS.md 硬规则第 7 条: 功能性数据不做「跳动」「流动」。只许颜色过渡(hover)。"""
    for comp in ("ActionCard", "HoldingTile", "ZoneHead", "SymbolButton", "StateLine"):   # [R516] WatchGroup 撤了
        src = _fn(comp)
        for banned in ("animate-", "motion", "transition-all", "translate", "hover:scale", "transition-transform"):
            assert banned not in src, f"{comp} 里出现了 {banned}"
