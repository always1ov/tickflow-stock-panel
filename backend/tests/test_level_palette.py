"""[fork R409 → R443] 关键价位的配色。

[R443] 用户: 「关键指标的颜色还是用作者原来的颜色, 然后自定的你再帮我选深色的」——
作者的 11 组回到上游原色(缺口位除外: 原色是粉, 全站禁粉); R409 / R424 那套「全体两两
分得开、一律不浅」只对自定的那几种还管着(见 `test_R443_*`)。下面是 R409 当时的说明。

[fork R409] 关键价位的配色 —— 一个指标一个颜色, 两套主题各一份, 而且不许浅。

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

# [R443] 门槛。作者的 11 组回到作者原色之后, R409 / R424 那套「全体两两分得开、
# 一律不浅」对作者的颜色不再成立(作者原样就有撞色、偏浅、ATR 像阳线), 只管**自定的**:
#   · 彼此 ΔE ≥ 10; 离作者的颜色 ≥ 9.5; 离 K 线涨跌色 ≥ 10(被读成涨跌是最要命的一种);
#   · 深: 亮色明度 ≤ 0.50、暗色 ≤ 0.65; 对页底对比 亮 ≥ 4.5、暗 ≥ 3.0(再深就看不见)。
MIN_CUSTOM_PAIR_DE = 10.0
MIN_CUSTOM_AUTHOR_DE = 9.5
MIN_CANDLE_DE = 10.0
MAX_CUSTOM_L = {"light": 0.50, "dark": 0.65}
MIN_CUSTOM_CONTRAST = {"light": 4.5, "dark": 3.0}

#: 作者的原色, 逐字取自上游 `upstream/main` 的 `AnalysisKChart.tsx`(LEVEL_GROUPS 与
#: CURVE_DEFS 的 color 列)。**缺口位不在里面**: 作者原色 #EC4899 是粉, 全站禁粉。
AUTHOR = {
    "sr": "#F97316", "pivot": "#8B5CF6", "extreme": "#EAB308", "boll": "#F97316",
    "keltner_s": "#06B6D4", "keltner_m": "#22D3EE", "keltner_l": "#67E8F9",
    "atr_stop": "#EF4444", "fib": "#F59E0B", "round": "#71717A",
}
AUTHOR_CURVES = {"boll_mid": "#FB923C", "atr_tp": "#F87171"}
#: 自定的组(另两种二型线在 `_customs` 里补上)
CUSTOM = {"gap", "livermore", "fib2"}


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


def _customs(theme: str) -> dict[str, str]:
    """一套主题下自定的全部颜色: 三个组色 + 二型另外两种线。"""
    out = {k: v[theme] for k, v in _palette().items() if k in CUSTOM}
    roles = _fib2_roles()
    out["fib2_目标"] = roles[dinapoli.C_TARGET][theme]
    out["fib2_失效位"] = roles[dinapoli.C_INVALID][theme]
    return out


def test_R443_作者的指标就是作者原来的颜色():
    """[R443] 用户: 「关键指标的颜色还是用作者原来的颜色, 然后自定的你再帮我选深色的」。
    作者就是一个值, 两套主题都用它; 作者单独配过色的两条曲线也照回。"""
    pal = _palette()
    assert set(pal) == set(AUTHOR) | CUSTOM, "配色表的组 = 作者的 + 自定的, 不多不少"
    for k, hex_ in AUTHOR.items():
        assert pal[k] == {"light": hex_, "dark": hex_}, f"{k} 不是作者原来的 {hex_}: {pal[k]}"
    src = read_src(THEME_TS)
    blk = src[src.index("export const LEVEL_CURVE_COLOR"):]
    blk = blk[:blk.index("\n}")]
    assert dict(re.findall(r"(\w+): '(#[0-9A-Fa-f]{6})'", blk)) == AUTHOR_CURVES
    chart = code_lines(read_src(CHART_TSX))
    assert "const curveColor = LEVEL_CURVE_COLOR[def.alignedKey] ?? LC[def.group]" in chart


def test_R443_自定的是深色_不粉_分得开():
    bad: list[str] = []
    for theme in ("light", "dark"):
        cust = _customs(theme)
        others = list(AUTHOR.values()) + list(AUTHOR_CURVES.values())
        for name, hex_ in cust.items():
            L, a, b = oklab(hex_)
            hue = math.degrees(math.atan2(b, a)) % 360
            if (hue >= 315 or hue <= 12) and math.hypot(a, b) > 0.03:
                bad.append(f"[{theme}] {name} {hex_} 落在粉 / 洋红一带(色相 {hue:.0f}°)")
            if L > MAX_CUSTOM_L[theme]:
                bad.append(f"[{theme}] {name} {hex_} 明度 {L:.2f} > {MAX_CUSTOM_L[theme]}, 不够深")
            c = contrast(hex_, BG[theme])
            if c < MIN_CUSTOM_CONTRAST[theme]:
                bad.append(f"[{theme}] {name} {hex_} 对页底只有 {c:.2f}:1, 深到看不见了")
            d = min(delta_e(hex_, x) for x in others)
            if d < MIN_CUSTOM_AUTHOR_DE:
                bad.append(f"[{theme}] {name} {hex_} 离作者的颜色只有 ΔE {d:.1f}")
            d = min(delta_e(hex_, x) for x in CANDLE[theme])
            if d < MIN_CANDLE_DE:
                bad.append(f"[{theme}] {name} {hex_} 离 K 线涨跌色只有 ΔE {d:.1f}")
        names = sorted(cust)
        for i, x in enumerate(names):
            for y in names[i + 1:]:
                d = delta_e(cust[x], cust[y])
                if d < MIN_CUSTOM_PAIR_DE:
                    bad.append(f"[{theme}] {x} × {y} 只差 ΔE {d:.1f}")
    assert not bad, "自定的颜色不合格:\n  " + "\n  ".join(bad)


def test_R472_斐波那契二型是深紫():
    """[R472] 用户: 「斐波那契二型用深紫色」。钉色相落在紫(290°~310°, 离禁粉的 315° 留余量),
    且换下来的深青进了退役表 —— 缓存里还带着旧键的响应不能画成一条认不出的线。"""
    pal = _palette()
    for theme in ("light", "dark"):
        _, a, b = oklab(pal["fib2"][theme])
        hue = math.degrees(math.atan2(b, a)) % 360
        assert 290 <= hue <= 310, f"[{theme}] 二型 {pal['fib2'][theme]} 色相 {hue:.0f}° 不是紫"
    src = read_src(THEME_TS)
    retired = src[src.index("const FIB2_ROLE_RETIRED"):]
    retired = retired[:retired.index("\n}")]
    assert "'#115E59': FIB2_ROLE_RETRACE" in retired, "R443~R471 的深青回撤位没进退役表"
