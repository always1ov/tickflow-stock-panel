"""[R514] 全站禁止紫色 —— 图表里的线与画图除外。

用户: 「不要紫色, 除了图表里面的划线画图」(2026-09-25)。

R421 禁粉时特意没带上紫(「用户点名的是粉, 紫是另一个问题, 没问过就不扩大」);
这一次用户点名了, 于是紫与粉并排各守一条。判据与扫描方式都借 `test_no_pink.py` 那一套
(OKLCH 色相, 色度 ≥ 0.06 才算有颜色; 注释剥掉 —— 注释里写「原来是紫」是允许的)。

**紫区**: 色相 ∈ [270°, 315°)。

- 下界 270°: 界面上的蓝都在 265° 以下(Tailwind blue-500 #3B82F6 约 260°、blue-600 #2563EB 263°、
  blue-700 #1D4ED8 264°、`rgb(29,78,216)` 264°), 靛蓝(indigo #4F46E5 / #6366F1 / #818CF8 约 277°)
  算紫 —— 屏幕上它就是蓝紫。
- 上界 315°: 再往上是粉区, 归 `test_no_pink.py` 管。
- 色度 < 0.06 的不算: 全站的文字灰带一点冷调(`--fg-primary` 色相 271°、色度 0.03), 那是灰不是紫。

**例外只有一类: 图表里的线与画图。** 按「文件 → 允许的值」逐条登记在 `CHART_ALLOWED`,
写清是哪条线; 放行表之外的紫一律不许。Tailwind 的 indigo / purple / violet 三族类名**没有例外**
—— 图表的线用 hex 画, 不走类名; 类名只会出现在界面上。
"""
from __future__ import annotations

import colorsys
import re

from tests.test_no_pink import (
    BACK, HEX, HSL, OKLCH_TOKEN, PY_COLOR, RGB, ROOT, _hex_rgb, front_files, oklch, strip_ts_comments,
)

TW_PURPLE = re.compile(r"\b[a-z:-]*-(?:purple|violet|indigo)-\d{2,3}\b")
TW_FAMILY = re.compile(r"\b(?:purple|violet|indigo)\s*:\s*\{")


def is_purple(L: float, C: float, H: float) -> bool:
    return C >= 0.06 and 270 <= H < 315


#: 图表里的线与画图 —— 用户点名的例外。键是文件, 值是(这个文件里允许的紫, 是哪几条线)。
CHART_ALLOWED: dict[str, tuple[set[str], str]] = {
    "frontend/src/components/EChartsCandlestick.tsx": (
        {"#8B5CF6"}, "K 线副图的 VOL10 / DEA / RSI24 / KDJ-J / MA60 线, 与它们图例上的同色小字"),
    "frontend/src/components/StockDailyKChart.tsx": (
        {"#8B5CF6"}, "日 K 上「炸」板的标记"),
    "frontend/src/components/SectorRotationCard.tsx": (
        {"#a78bfa", "#818cf8", "#9575cd"}, "板块走势线的 20 色调色板(列表里的小圆点跟线同色)"),
    "frontend/src/pages/backtest/charts/FactorGroupNavChart.tsx": (
        {"#6366f1", "#8b5cf6", "#a855f7"}, "因子分组净值曲线 Q1 / Q2 / Q10"),
    "frontend/src/lib/theme.ts": (
        {"#8B5CF6", "#3730A3", "#4F46E5", "#6A0DAD", "#724EA0", "#322097", "#7B07CE", "#B84DFF"},
        "关键价位图上的画线: 枢轴点、缺口、斐波那契二型回踩位(R472 用户点名「深紫」)及其退役角色键、"
        "分时均价线"),
}

#: 后端按角色发给图表的颜色(它发什么前端就画什么)
BACK_ALLOWED: dict[tuple[str, str], str] = {
    ("backend/app/indicators/dinapoli.py", "#6A0DAD"): "斐波那契二型回踩位的线色(= 前端 FIB2_ROLE_RETRACE)",
}


def purple_in_code(code: str) -> list[tuple[str, str]]:
    """一段(已去注释的)前端代码里的紫: [(原文, 说明)]。"""
    out: list[tuple[str, str]] = []
    out += [(m.group(0), "Tailwind 紫族类名") for m in TW_PURPLE.finditer(code)]
    out += [(m.group(0), "调色板里加回了紫族") for m in TW_FAMILY.finditer(code)]
    for m in HEX.finditer(code):
        L, C, H = oklch(*_hex_rgb(m.group(1)))
        if is_purple(L, C, H):
            out.append((f"#{m.group(1)}", f"H {H:.0f}°"))
    for m in RGB.finditer(code):
        L, C, H = oklch(*map(int, m.groups()))
        if is_purple(L, C, H):
            out.append((m.group(0) + ")", f"H {H:.0f}°"))
    for m in HSL.finditer(code):
        h, s, l = (float(x) for x in m.groups())
        r, g, b = (round(x * 255) for x in colorsys.hls_to_rgb(h / 360, l / 100, s / 100))
        L, C, H = oklch(r, g, b)
        if is_purple(L, C, H):
            out.append((m.group(0), f"H {H:.0f}°"))
    for m in OKLCH_TOKEN.finditer(code):
        L, C, H = (float(x) for x in m.groups())
        if L <= 1 and C < 0.5 and is_purple(L, C, H):
            out.append((m.group(0).strip(), "OKLCH 令牌"))
    return out


def test_R514_判据本身_紫的判紫_蓝的灰的粉的不误伤():
    purples = ["#8B5CF6", "#A855F7", "#6D28D9", "#7B4FC0", "#4F46E5", "#6366F1", "#818CF8", "#4F5DE8",
               "#9575CD", "#6A0DAD", "#B84DFF"]
    for h in purples:
        assert is_purple(*oklch(*_hex_rgb(h[1:]))), f"{h} 是紫, 判据没认出来"
    keep = ["#3B82F6", "#2563EB", "#1D4ED8", "#0369A1", "#06B6D4", "#71717A", "#222738",   # 蓝 / 青 / 灰
            "#E01DB5", "#EC4899",                                                          # 粉归禁粉那条管
            "#C74040", "#F59E0B", "#0F766E"]
    for h in keep:
        assert not is_purple(*oklch(*_hex_rgb(h[1:]))), f"{h} 不是紫, 判据误伤了"
    assert not is_purple(0.2759, 0.0324, 271.51), "带冷调的文字灰(--fg-primary)被当成了紫"
    assert purple_in_code("x text-purple-400 bg-violet-500/10 ring-indigo-400/60")
    assert purple_in_code("colors: { violet: { 300: 'oklch(...)' } }")
    assert not purple_in_code("text-sky-400 bg-accent/10 rgb(29,78,216)")


def test_R514_前端没有紫_图表的线除外():
    bad: list[str] = []
    for p in front_files():
        rel = str(p.relative_to(ROOT))
        allowed = {v.lower() for v in CHART_ALLOWED.get(rel, (set(), ""))[0]}
        for raw, why in purple_in_code(strip_ts_comments(p.read_text(encoding="utf-8"))):
            if raw.lower() in allowed:
                continue
            bad.append(f"{rel}: {raw} ({why})")
    assert not bad, (
        "界面上又出现了紫色(用户: 「不要紫色, 除了图表里面的划线画图」)。"
        "真是图表里的线就登记进 CHART_ALLOWED 并写清是哪条线:\n  " + "\n  ".join(bad))


def test_R514_后端发出去的颜色没有紫_图表的线除外():
    bad: list[str] = []
    for p in sorted(BACK.rglob("*.py")):
        rel = str(p.relative_to(ROOT))
        for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            code = line.split("  #", 1)[0]
            for m in PY_COLOR.finditer(code):
                hexv = "#" + m.group(1)
                L, C, H = oklch(*_hex_rgb(m.group(1)))
                if is_purple(L, C, H) and (rel, hexv) not in BACK_ALLOWED:
                    bad.append(f"{rel}:{n}: {hexv} (H {H:.0f}°)")
    assert not bad, "后端发出了紫色:\n  " + "\n  ".join(bad)


def test_R514_调色板里没有紫族():
    """族名在 tailwind.config 里一加回来, `text-purple-400` 这类类名就又能用了。"""
    cfg = strip_ts_comments((ROOT / "frontend" / "tailwind.config.ts").read_text(encoding="utf-8"))
    assert not TW_FAMILY.search(cfg), "tailwind.config 里加回了 indigo / purple / violet"
    css = (ROOT / "frontend" / "src" / "index.css").read_text(encoding="utf-8")
    assert not re.search(r"--t-(?:indigo|purple|violet)-\d", css), "index.css 里还留着紫族令牌"


def test_R514_放行表每一条都还用得着():
    """放行的值要是已经从文件里删了, 那一条就该一起删 —— 否则它会悄悄替以后写回来的同值紫放行。"""
    for rel, (values, why) in CHART_ALLOWED.items():
        src = strip_ts_comments((ROOT / rel).read_text(encoding="utf-8")).lower()
        for v in values:
            assert v.lower() in src, f"{rel} 里已经没有 {v} 了, 放行表那一条该删({why})"
    for (rel, v), why in BACK_ALLOWED.items():
        assert v.lower() in (ROOT / rel).read_text(encoding="utf-8").lower(), f"{rel} 里已经没有 {v} 了({why})"


def test_R514_放行的只有图表文件():
    """例外只给「图表里的线与画图」。放行表里混进一个页面或通用组件, 就等于给那一页开了口子。"""
    for rel, (_, why) in CHART_ALLOWED.items():
        assert any(w in why for w in ("线", "标记", "曲线", "画线")), f"{rel} 的放行理由不是图表里的线: {why}"
