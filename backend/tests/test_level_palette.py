"""[fork R409] 关键价位的配色 —— 一个指标一个颜色, 两套主题各一份, 而且不许浅。

用户原话:「关键价位的所有指标的各个指标的颜色都要不一样, 因为重叠的时候容易混淆
是视觉, 而且不能搞浅色, 也要符合自身含义」。

**为什么非得有守卫**: 颜色改坏了屏幕上只是"有点怪", 什么都不会报错。改之前这一组
就已经坏了很久 ——

  · 压力支撑与布林带写成了**同一个 #F97316**(ΔE 0.0), 两组线叠在一起完全分不出;
  · 另有 32 对 ΔE < 20, 其中 5 对 < 8.5;
  · 亮色主题下四个组对白底的对比度是 1.35 / 1.69 / 1.79 / 2.01 —— 1px 虚线在这种
    对比度下等于没画;
  · ATR 波动通道 #EF4444 离 K 线的涨红 #C74040 只有 ΔE 5~6 —— 一条指标线长得像一
    根阳线, 这是最要命的一个。

这几条**没有一条会让任何测试变红**, 全靠人眼发现, 而人眼是在用了几个月之后才发现
的。所以这里把它们逐条变成可断言的事实。

钉的是**性质, 不是具体色值**: 两两分得开、离涨跌色够远、两套主题都不浅、三档通道
在同族里明度单调、键与开关一一对应。想换配色随时换, 只要仍然满足这些性质 ——
真正不许发生的是"换完之后又撞在一起而没人知道"。
"""
from __future__ import annotations

import math
import re

from app.indicators import dinapoli
from tests.frontend_source import code_lines, read_src

THEME_TS = "lib/theme.ts"
CHART_TSX = "components/stock-analysis/AnalysisKChart.tsx"

# 页底色(index.css 的 --base), 两套主题各一个。价位线画在它上面。
BG = {"light": "#F6F7FB", "dark": "#0A0A0B"}

# K 线的涨跌色。**价位线必须离这两个够远** —— 一条指标线长得像一根蜡烛是最坏的
# 一种混淆: 看的人不会怀疑, 只会读错。
#   · THEME.bull / THEME.bear: AnalysisKChart 里 K 线画布用的那两个;
#   · --bull / --bear: 界面文字用的那两个(R368 冻结, 亮暗各一份)。
CANDLE = {
    "light": ("#C74040", "#2D9B65", "#D92D20", "#15803D"),
    "dark": ("#C74040", "#2D9B65", "#FE595F", "#03935B"),
}

# 门槛。取值的由来:
#   · ΔE 8 —— 改之前最近的一对是 0.0(完全相同), 5 对在 8.5 以下。8 是"再往下就是
#     已经出过事的那一档"。
#   · 离涨跌色 ΔE 10 —— 改之前 ATR 通道是 5。
#   · 对比度 亮 3.0 / 暗 5.0 —— 改之前亮色最低 1.35。WCAG 对非文字图形的线是 3.0,
#     暗色底上本来就容易拉开, 所以门槛给高一档。
MIN_PAIR_DE = 8.0
MIN_CANDLE_DE = 10.0
MIN_CONTRAST = {"light": 3.0, "dark": 5.0}


# ── 色彩换算(无依赖, 直接写在这儿)──────────────────────────
def _rgb(hex_: str) -> tuple[float, float, float]:
    h = hex_.lstrip("#")
    assert len(h) == 6, f"不是 6 位 hex: {hex_}"
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))  # type: ignore[return-value]


def _lin(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def luminance(hex_: str) -> float:
    r, g, b = (_lin(c) for c in _rgb(hex_))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: str, b: str) -> float:
    la, lb = luminance(a), luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def oklab(hex_: str) -> tuple[float, float, float]:
    r, g, b = (_lin(c) for c in _rgb(hex_))
    l = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b
    m = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b
    s = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b
    l, m, s = l ** (1 / 3), m ** (1 / 3), s ** (1 / 3)
    return (0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s,
            1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
            0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s)


def delta_e(a: str, b: str) -> float:
    """OKLab 距离 ×100。约 2 是刚刚分得出, 8~10 是并排放能一眼看出不同。"""
    x, y = oklab(a), oklab(b)
    return 100 * math.sqrt(sum((p - q) ** 2 for p, q in zip(x, y)))


# ── 从源码里把配色读出来 ─────────────────────────────────────
def _palette() -> dict[str, dict[str, str]]:
    """`lib/theme.ts` 的 LEVEL_PALETTE。"""
    src = read_src(THEME_TS)
    i = src.index("export const LEVEL_PALETTE")
    blk = src[i:src.index("\n}", i)]
    out: dict[str, dict[str, str]] = {}
    for key, light, dark in re.findall(
            r"^\s*(\w+):\s*\{\s*light:\s*'(#[0-9A-Fa-f]{6})',\s*dark:\s*'(#[0-9A-Fa-f]{6})'",
            blk, re.M):
        out[key] = {"light": light, "dark": dark}
    assert out, "LEVEL_PALETTE 读不出来 —— 格式变了就得改这个解析"
    return out


def _role_consts() -> dict[str, str]:
    """`lib/theme.ts` 里那三个具名角色键 —— `FIB2_ROLE_RETRACE` 等。

    [R410] 它们原来是直接写成字符串字面量当 `FIB2_ROLE` 的键的; 前端要按角色
    过滤(推算位默认不画)时需要拿到名字, 所以提成了常量。这里跟着改解析。
    """
    src = read_src(THEME_TS)
    out = dict(re.findall(r"export const (FIB2_ROLE_\w+) = '(#[0-9A-Fa-f]{6})'", src))
    assert len(out) == 3, f"三个角色键常量读不全: {out}"
    return out


def _fib2_roles() -> dict[str, dict[str, str]]:
    """`lib/theme.ts` 的 FIB2_ROLE(键是后端那三个常量的字面值)。"""
    src = read_src(THEME_TS)
    i = src.index("export const FIB2_ROLE:")
    blk = src[i:src.index("\n}", i)]
    consts = _role_consts()
    out: dict[str, dict[str, str]] = {}
    for key, light, dark in re.findall(
            r"^\s*\[(FIB2_ROLE_\w+)\]:\s*\{\s*light:\s*'(#[0-9A-Fa-f]{6})',\s*dark:\s*'(#[0-9A-Fa-f]{6})'",
            blk, re.M):
        out[consts[key]] = {"light": light, "dark": dark}
    assert out, "FIB2_ROLE 读不出来"
    return out


def _group_keys() -> list[str]:
    """`LEVEL_GROUPS` 里的 key, 按出现顺序。"""
    src = read_src(CHART_TSX)
    i = src.index("export const LEVEL_GROUPS")
    blk = code_lines(src[i:src.index("\n]", i)])
    keys = re.findall(r"key:\s*'(\w+)'", blk)
    assert keys, "LEVEL_GROUPS 读不出来"
    return keys


def _all_colors(theme: str) -> dict[str, str]:
    """一套主题下**图上会同时出现**的全部颜色: 13 个组色 + 二型另外两种线。"""
    out = {k: v[theme] for k, v in _palette().items()}
    roles = _fib2_roles()
    out["fib2_目标"] = roles[dinapoli.C_TARGET][theme]
    out["fib2_失效位"] = roles[dinapoli.C_INVALID][theme]
    return out


# ── 守卫 ────────────────────────────────────────────────────
def test_R409_每个价位组都有配色_不多不少():
    """漏一个组 → 那个组的线会画成 `undefined`(ECharts 自己挑一个色, 每次还不一定
    一样); 多一个 → 配色表里躺着一条没人用的, 下次照着它挑色就会挑错。"""
    keys = set(_group_keys())
    pal = set(_palette())
    assert keys == pal, (
        f"开关组与配色表对不上: 只在开关里 {sorted(keys - pal)}, 只在配色表里 {sorted(pal - keys)}")


def test_R409_任意两个指标色都分得开_两套主题各算一遍():
    """用户: 「重叠的时候容易混淆是视觉」。

    **改之前压力支撑与布林带是同一个值** —— 这条断言最直接要挡的就是那个。
    """
    bad: list[str] = []
    for theme in ("light", "dark"):
        cols = _all_colors(theme)
        names = sorted(cols)
        for i, a in enumerate(names):
            for b in names[i + 1:]:
                d = delta_e(cols[a], cols[b])
                if d < MIN_PAIR_DE:
                    bad.append(f"[{theme}] {a} × {b} 只差 ΔE {d:.1f}({cols[a]} / {cols[b]})")
    assert not bad, "有指标色撞在一起:\n  " + "\n  ".join(bad)


def test_R409_没有一个指标色像K线的涨红或跌绿():
    """**最要命的一种混淆**: 一条指标线长得像一根蜡烛, 看的人不会怀疑, 只会读错。

    改之前 ATR 波动通道 #EF4444 离涨红只有 ΔE 5~6。红绿两段色相整个让开是本仓库的
    既定口径(R405 写过), 这里把它变成可断言的。
    """
    bad: list[str] = []
    for theme in ("light", "dark"):
        for name, hex_ in _all_colors(theme).items():
            for candle in CANDLE[theme]:
                d = delta_e(hex_, candle)
                if d < MIN_CANDLE_DE:
                    bad.append(f"[{theme}] {name} {hex_} 离 K 线色 {candle} 只有 ΔE {d:.1f}")
    assert not bad, "指标色离涨跌色太近:\n  " + "\n  ".join(bad)


def test_R409_没有一个色是浅到看不见的():
    """用户: 「不能搞浅色」。

    **这是那句话的机器形式。** 改之前亮色主题下通道长期 #67E8F9 对白底只有 1.35:1,
    通道中期 1.69、前高前低 1.79、一型 2.01 —— 四个组实际上是画了跟没画一样。
    一个 hex 同时要在近白底和近黑底上站住, 就只能挤在很窄的一段明度里, 那正是"浅"
    的来源; 所以现在按主题分了两套值, 这条断言两套都查。
    """
    bad: list[str] = []
    for theme in ("light", "dark"):
        for name, hex_ in _all_colors(theme).items():
            c = contrast(hex_, BG[theme])
            if c < MIN_CONTRAST[theme]:
                bad.append(f"[{theme}] {name} {hex_} 对页底 {BG[theme]} 只有 {c:.2f}:1"
                           f"(下限 {MIN_CONTRAST[theme]})")
    assert not bad, "有颜色浅到看不见:\n  " + "\n  ".join(bad)


def test_R409_量化通道三档留在同族但明度分得开():
    """三档是**同一个指标的三个周期**, 换成三个色相就读不出"同一家"了。

    但也不能像以前那样靠"一档比一档浅"来区分 —— 那正是长期档 1.35:1 的由来。
    所以: 色相相近(同族), 明度单调且每两档之间拉开够多。
    """
    for theme in ("light", "dark"):
        pal = _palette()
        s, m, l = (pal[f"keltner_{x}"][theme] for x in ("s", "m", "l"))
        hues = []
        for hex_ in (s, m, l):
            _L, a, b = oklab(hex_)
            hues.append(math.degrees(math.atan2(b, a)) % 360)
        spread = max(hues) - min(hues)
        assert spread < 25, f"[{theme}] 三档通道色相散开了 {spread:.1f}° —— 读不出是同一个指标"
        ls = [oklab(x)[0] for x in (s, m, l)]
        assert ls[0] > ls[1] > ls[2], f"[{theme}] 三档明度不单调: {ls}"
        assert min(ls[0] - ls[1], ls[1] - ls[2]) > 0.05, \
            f"[{theme}] 相邻两档明度差太小, 分不出来: {ls}"


def test_R409_曲线不再自带颜色_一律跟所属组():
    """改之前 CURVE_DEFS 里另写了三个 hex(布林中轨 / ATR上轨 / 二型均线), 于是
    **同一个开关底下冒出了组色之外的颜色** —— 开关上的小圆点一种色、图上的线另一种,
    而且那三个 hex 与别的组撞不撞谁也没管(ATR上轨 #F87171 离涨红只有 ΔE 6)。
    """
    src = read_src(CHART_TSX)
    i = src.index("const CURVE_DEFS")
    blk = code_lines(src[i:src.index("\n]", i)])
    found = re.findall(r"#[0-9A-Fa-f]{6}", blk)
    assert not found, f"CURVE_DEFS 里又出现了写死的颜色: {found}"
    assert "color:" not in blk, "CURVE_DEFS 又多了 color 这一列 —— 颜色只能有一个产地"


def test_R409_开关组也不自带颜色():
    """同上, 换成 LEVEL_GROUPS 那一侧。两处都堵住, 配色才真的只有一个产地。"""
    src = read_src(CHART_TSX)
    i = src.index("export const LEVEL_GROUPS")
    blk = code_lines(src[i:src.index("\n]", i)])
    found = re.findall(r"#[0-9A-Fa-f]{6}", blk)
    assert not found, f"LEVEL_GROUPS 里又出现了写死的颜色: {found}"
    assert "color:" not in blk, "LEVEL_GROUPS 又多了 color 这一列"


def test_R409_二型三种线的角色键前后端逐字对得上():
    """**这是一层隐式耦合, 所以必须有守卫。**

    后端按角色发 `color` 字段(R405 定的契约), 而颜色要按主题分两套、后端不知道当前
    是哪套 —— 于是后端那三个常量退回去只当"角色标识", 前端 FIB2_ROLE 以它们为键。
    后端改了常量而前端没跟, 屏幕上的表现是**二型那三种线退回亮色的值**, 在暗色主题
    下只是"看着有点闷", 不会报错。
    """
    want = {dinapoli.C_RETR, dinapoli.C_TARGET, dinapoli.C_INVALID}
    got = set(_fib2_roles())
    assert want == got, (
        f"前后端角色键对不上: 后端有而前端没有 {sorted(want - got)}, "
        f"前端有而后端没有 {sorted(got - want)}")


def test_R409_角色键的亮色那一份就是它自己():
    """键取的是**亮色那一份**, 所以即便前端认不出来(映射漏了), 退化行为也只是
    "暗色下用了亮色的值", 而不是没有颜色。这条钉住那个前提。"""
    for key, pair in _fib2_roles().items():
        assert pair["light"].upper() == key.upper(), \
            f"{key} 的亮色值写成了 {pair['light']} —— 那样认不出来时会退化成别的颜色"


def test_R409_回撤线用的就是二型的组色():
    """二型组的开关是一个, 图上最多的线是回撤线。开关上的圆点与那批线不同色的话,
    「这个开关管的是哪几条线」就没法一眼对上。"""
    pal = _palette()
    roles = _fib2_roles()
    for theme in ("light", "dark"):
        assert roles[dinapoli.C_RETR][theme].upper() == pal["fib2"][theme].upper(), \
            f"[{theme}] 回撤线 {roles[dinapoli.C_RETR][theme]} 与组色 {pal['fib2'][theme]} 不一致"


def test_R409_一型与二型不是同一个色族():
    """两个名字只差一个字(斐波那契一型 / 二型), 再同色就是全图最容易混的一对。

    改之前一型是 #F59E0B、二型是 #A77A1C —— ΔE 16.8, 同一个金。金留给作者的那一组
    (斐波那契配金是约定), 二型让路。

    **钉的是色相隔了多远, 不是 ΔE 多大。** 第一版写的是 `ΔE >= 25`, 而实际值是
    24.3 —— 差一点没过, 可那两个色一个是金一个是粉, 肉眼上八竿子打不着。ΔE 在
    这里不是好判据: 它把明度差也算进去, 于是"同一个金、一深一浅"和"金 vs 粉"
    可以得到相近的数。要说的话本来就是「不是同一个色族」, 那就直接量色相。
    """
    pal = _palette()
    for theme in ("light", "dark"):
        a, b = pal["fib"][theme], pal["fib2"][theme]
        ha, hb = (math.degrees(math.atan2(oklab(x)[2], oklab(x)[1])) % 360 for x in (a, b))
        gap = abs(ha - hb)
        gap = min(gap, 360 - gap)
        assert gap >= 60, f"[{theme}] 一型 {a} 与二型 {b} 色相只隔 {gap:.0f}° —— 名字已经够像了"
        d = delta_e(a, b)
        assert d >= 20, f"[{theme}] 一型 {a} 与二型 {b} 只差 ΔE {d:.1f}"


def test_R409_价位线的透明度有下限():
    """「不能搞浅色」不只是色值的事 —— **画线时还叠了两层透明度**。

    改之前: 常态 `opacity: 0.7`, 再乘 strengthColor 的 0.55(弱) → 实际 0.39。
    色值再深, 叠完也是浅的。这条把两层的下限都钉住。
    """
    src = read_src(CHART_TSX)
    code = code_lines(src)
    # strengthColor 的两档
    m = re.search(r"if \(strength === 'weak'\) return base \+ '([0-9A-Fa-f]{2})'", code)
    assert m, "strengthColor 的 weak 那一档读不出来"
    assert int(m[1], 16) >= 0xB0, f"最弱那一档透明度 0x{m[1]} 太低了"
    m = re.search(r"if \(strength === 'medium'\) return base \+ '([0-9A-Fa-f]{2})'", code)
    assert m, "strengthColor 的 medium 那一档读不出来"
    assert int(m[1], 16) >= 0xD9, f"中间那一档透明度 0x{m[1]} 比以前还低"
    # 画线时的常态 opacity(价位线与曲线各一处), 淡化态 0.12 是 hover 聚焦用的, 不算
    normals = [float(x) for x in re.findall(r"dimming \? \(hit \? 1 : 0\.12\) : ([\d.]+)", code)]
    assert len(normals) == 2, f"常态 opacity 应该正好两处(价位线 + 曲线), 读到 {normals}"
    assert min(normals) >= 0.85, f"常态不透明度掉回去了: {normals}"
