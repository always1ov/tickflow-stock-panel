"""[fork R505] 宏观分析 · 市场环境这一组精简: 7 块 → 「现在」一张卡 + 环境综合分趋势。

用户:「分析市场环境这个部分有哪些是值得我关注的, 是否有重复, 单纯展示数据就没必要显示了,
而且占用了很多空间, 如果不影响环境综合分趋势的没用的部分还可以考虑删除了」, 看过改前改后
对比图后「动手」。

撤掉的四块: 状态时间轴、日历热力图(与趋势图背景色带是同一份「每天哪一档」)、状态分布饼图、
状态转换次数(纯统计, 不指向任何动作)。留下的是解读: 在哪一档 / 在变好还是变坏 / 哪一维在拉。
"""
from __future__ import annotations

from tests.frontend_source import code_of

REGIME = "pages/Regime.tsx"


def _regime_group() -> str:
    src = code_of(REGIME)
    a = src.index('aria-labelledby="macro-regime"')
    # [R506] 情绪周期撤了, 市场环境这一组一直到它的 </section>
    return src[a:src.index("</section>", a)]


def test_R505_撤掉的四块不再出现():
    g = _regime_group()
    for gone in ('title="状态时间轴"', 'title="日历热力图"', 'title="状态分布"', "次切换", "节奏"):
        assert gone not in g, f"市场环境这一组还留着 {gone}"
    src = code_of(REGIME)
    for dead in ("pieOption", "pieRef", "calendarMonths", "calendarExpanded", "api.regimeStates", "scoreToColor"):
        assert dead not in src, f"撤掉的块留下了没人用的 {dead}"


def test_R505_留下的三样解读合成一张卡():
    g = _regime_group()
    for kept in ("最新状态 · {latest.date}", "当前势头", "四维拆解", "5日", "上次弱势"):
        assert kept in g, f"「现在」卡丢了 {kept}"
    for dim in ("latest.profit_score", "latest.speculation_score", "latest.resilience_score", "latest.trend_score"):
        assert dim in g
    # 原来直接显示原始小数(88.9313), 挤出卡片右边
    assert "Math.round(d.val)" in g


def test_R505_趋势图还在_独占整行_本身没动():
    g = _regime_group()
    assert 'title="环境综合分趋势"' in g and "ref={trendRef}" in g
    assert "lg:col-span-2" not in g, "趋势图又和别的块挤在一行"
    src = code_of(REGIME)
    assert "const trendRef = useEChart(trendOption, [trendOption])" in src
    assert "api.regimeHistory(histRange.start, histRange.end, histRange.limit)" in src


def test_R510_四维拆解的条子定宽_轨道在白底上看得见():
    """用户截图(2000px 宽): 四条被拉到半屏长, 数字离标签半屏远; 0 分那一维什么都没画, 像坏了。
    根因两个: 条子 flex-1 跟着四等分的格子撑; 轨道底色是 --base, R501 之后页底纯白, 轨道隐形。"""
    g = _regime_group()
    i = g.index("四维拆解")
    seg = g[i:i + 1800]
    assert "w-24 shrink-0 overflow-hidden rounded-full bg-elevated" in seg, "条子又撑满 / 轨道又隐形了"
    assert "flex flex-wrap gap-x-5" in seg and "lg:grid-cols-4" not in seg, "四条又被四等分撑开了"
    # 用户: 「口径改成过滤」
    assert "<Filter className=\"h-2.5 w-2.5\" /> 过滤" in g and "/> 口径" not in g
