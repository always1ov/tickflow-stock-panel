"""[R421] 全站禁止粉色 / 洋红 / 玫红。

用户: 「整个系统禁止少女系风格, 比如粉色, 投资是一件很严肃的事情」。

这条要能一直是真的, 就不能靠"改的时候记得" —— 下一个人从 Tailwind 调色板里随手挑一个
`pink-400`、或者抄一段带 `#e879f9` 的示例代码, 屏幕上只是"多了一点颜色", 什么都不会报错。
所以扫两处:

- **前端** `frontend/src` 下全部 ts / tsx / css 的**代码**(注释剥掉 —— 注释里复述
  "原来是洋红"是允许的, 讲清楚为什么改恰恰要写出旧值): Tailwind 的 pink / fuchsia /
  rose 三族类名一律不许; 十六进制、rgb()、hsl() 以及 `index.css` 里以 `L C H` 三个数
  写的 OKLCH 令牌, 落进粉区的不许。
- **后端** `backend/app` 里以字符串发出去的颜色(`"#RRGGBB"`)—— 后端按角色发 `color`
  字段(比如斐波那契二型), 它发什么前端就画什么。

**粉区的判据**(OKLCH, 色度 ≥ 0.06 才算有颜色):

- 色相 ∈ [315°, 360°) ∪ [0°, 12°) —— 洋红、品红、粉、玫红; 浅粉(`#FFC0CB` 8°、
  `#FFB6C1` 5°)也在这一段里。

**红不在里面**: 界面上的涨红(暗色 `--bull` #FE595F 色相 22°、K 线 #C74040 24.5°、
亮色 #D92D20、Tailwind red 族令牌统一锚在 22°~29.5°)都在 12° 以上。第一版还加了
一条「12°~35° 且明度 ≥ 0.80 也算粉」, 当场把暗色的 `red-300`(涨的浅红文字)拦下了
—— 涨红是冻结的, 那条删掉。紫也不在里面(枢轴点 #9362F9 294°、
Tailwind violet / purple 在 290°~305°)—— 用户点名的是粉, 紫是另一个问题, 没问过就不扩大。
"""
from __future__ import annotations

import colorsys
import math
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FRONT = ROOT / "frontend" / "src"
BACK = ROOT / "backend" / "app"

TW_PINK = re.compile(r"\b[a-z:-]*-(?:pink|fuchsia|rose)-\d{2,3}\b")
# tailwind.config.ts 里把族名加回调色板: `rose: { 300: ... }`
TW_FAMILY = re.compile(r"\b(?:pink|fuchsia|rose)\s*:\s*\{")
HEX = re.compile(r"#([0-9A-Fa-f]{6}|[0-9A-Fa-f]{3})\b")
RGB = re.compile(r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)")
HSL = re.compile(r"hsla?\(\s*([\d.]+)(?:deg)?[\s,]+([\d.]+)%[\s,]+([\d.]+)%")
OKLCH_TOKEN = re.compile(r"--[\w-]+:\s*([\d.]+)\s+([\d.]+)\s+([\d.]+)\s*;")
PY_COLOR = re.compile(r"""["']#([0-9A-Fa-f]{6})["']""")


def _lin(c: float) -> float:
    c /= 255
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def oklch(r: int, g: int, b: int) -> tuple[float, float, float]:
    r_, g_, b_ = _lin(r), _lin(g), _lin(b)
    l = 0.4122214708 * r_ + 0.5363325363 * g_ + 0.0514459929 * b_
    m = 0.2119034982 * r_ + 0.6806995451 * g_ + 0.1073969566 * b_
    s = 0.0883024619 * r_ + 0.2817188376 * g_ + 0.6299787005 * b_
    l, m, s = (x ** (1 / 3) for x in (l, m, s))
    L = 0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s
    a = 1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s
    bb = 0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s
    return L, math.hypot(a, bb), math.degrees(math.atan2(bb, a)) % 360


def is_pink(L: float, C: float, H: float) -> bool:
    if C < 0.06:
        return False
    return H >= 315 or H < 12


def _hex_rgb(h: str) -> tuple[int, int, int]:
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def strip_ts_comments(src: str) -> str:
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)          # 块注释(含 JSX 的 {/* */})
    return re.sub(r"(^|\s)//.*$", r"\1", src, flags=re.M)    # 行注释; `path://` `https://` 前面不是空白, 不误伤


#: 核查过、确实不会画到屏幕上的粉色值 —— 每一条写清为什么。宁缺毋滥。
ALLOWED: dict[tuple[str, str], str] = {
    ("frontend/src/lib/theme.ts", "#E01DB5"):
        "退役的二型回撤角色键, 只当查表的键(FIB2_ROLE_RETIRED), 映射到靛青; "
        "换色前缓存里的响应还带着它, 删了那批响应就会原样画成洋红",
}


def front_files():
    for p in sorted(FRONT.rglob("*")):
        if p.suffix not in (".ts", ".tsx", ".css") or "node_modules" in p.parts:
            continue
        if p.name.endswith((".test.ts", ".test.tsx")):
            continue    # 测试里的粉色是**样本**(拿来证明被拦下 / 被改色), 不上屏
        yield p
    # Tailwind 的调色板映射在 src 外面; 族名一旦加回来, 类名就又能用了
    yield ROOT / "frontend" / "tailwind.config.ts"


def pink_in_code(code: str) -> list[str]:
    """一段(已去注释的)前端代码里落进粉区的颜色与类名。"""
    out: list[str] = []
    out += [f"类名 {m.group(0)}" for m in TW_PINK.finditer(code)]
    out += [f"调色板族 {m.group(0)}" for m in TW_FAMILY.finditer(code)]
    for m in HEX.finditer(code):
        L, C, H = oklch(*_hex_rgb(m.group(1)))
        if is_pink(L, C, H):
            out.append(f"#{m.group(1)} (H {H:.0f}°)")
    for m in RGB.finditer(code):
        L, C, H = oklch(*map(int, m.groups()))
        if is_pink(L, C, H):
            out.append(f"{m.group(0)}) (H {H:.0f}°)")
    for m in HSL.finditer(code):
        h, s, l = (float(x) for x in m.groups())
        r, g, b = (round(x * 255) for x in colorsys.hls_to_rgb(h / 360, l / 100, s / 100))
        L, C, H = oklch(r, g, b)
        if is_pink(L, C, H):
            out.append(f"{m.group(0)} (H {H:.0f}°)")
    for m in OKLCH_TOKEN.finditer(code):
        L, C, H = (float(x) for x in m.groups())
        if L <= 1 and C < 0.5 and is_pink(L, C, H):
            out.append(f"{m.group(0).strip()} (OKLCH 令牌)")
    return out


def test_R421_判据本身_粉的判粉_红的紫的不误伤():
    """守卫先证明自己分得清 —— 判据错了, 下面那两条要么漏、要么把涨红也拦掉。"""
    pinks = ["#E01DB5", "#FCA2DF", "#F845AF", "#B31364", "#D75AFA", "#E879F9",
             "#F472B6", "#EC4899", "#F06292", "#FFC0CB", "#FFB6C1", "#D946EF", "#B84A8A"]
    for h in pinks:
        assert is_pink(*oklch(*_hex_rgb(h[1:]))), f"{h} 是粉, 判据没认出来"
    keep = ["#C74040", "#FE595F", "#D92D20", "#D03050", "#EF4444", "#F87171",   # 涨红
            "#9362F9", "#A855F7", "#8B5CF6",                                   # 紫
            "#322097", "#7687BA", "#2859B1", "#2288E8", "#9A3412", "#E07A12",  # R421 新色
            "#991B1B", "#A1A1AA", "#FCA5A5"]                                  # 暗色涨的浅红文字
    for h in keep:
        assert not is_pink(*oklch(*_hex_rgb(h[1:]))), f"{h} 不是粉, 判据误伤了"
    assert pink_in_code("x text-rose-400 y bg-fuchsia-400/10 ring-pink-300")
    assert pink_in_code("colors: { rose: { 300: 'oklch(...)' } }")
    assert not pink_in_code("text-red-400 bg-violet-500/10 'path://M6.5,0'")
    assert not pink_in_code("const RETIRED = { rose: 'orange' }")   # 旧 id 的映射表不是调色板


def test_R421_前端代码里没有粉():
    bad: list[str] = []
    for p in front_files():
        rel = str(p.relative_to(ROOT))
        code = strip_ts_comments(p.read_text(encoding="utf-8"))
        for (f, hexv) in ALLOWED:
            if f == rel:
                code = re.sub(re.escape(hexv), "", code, flags=re.I)
        for hit in pink_in_code(code):
            bad.append(f"{rel}: {hit}")
    assert not bad, "前端又出现了粉色(用户: 「整个系统禁止少女系风格」):\n  " + "\n  ".join(bad)


def test_R421_后端发出去的颜色没有粉():
    bad: list[str] = []
    for p in sorted(BACK.rglob("*.py")):
        for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            code = line.split("  #", 1)[0]          # 行尾注释不算
            for m in PY_COLOR.finditer(code):
                L, C, H = oklch(*_hex_rgb(m.group(1)))
                if is_pink(L, C, H):
                    bad.append(f"{p.relative_to(ROOT)}:{n}: #{m.group(1)} (H {H:.0f}°)")
    assert not bad, "后端发出了粉色:\n  " + "\n  ".join(bad)


def test_R421_守卫扫到了东西_不是空转():
    """路径错了或正则哑了, 上面两条会永远绿。钉一个下限: 前端文件与颜色都得扫到一批。"""
    files = list(front_files())
    assert len(files) > 100, f"只扫到 {len(files)} 个前端文件, 路径多半错了"
    n_colors = sum(len(HEX.findall(strip_ts_comments(p.read_text(encoding="utf-8")))) for p in files)
    assert n_colors > 200, f"只扫到 {n_colors} 个颜色, 正则多半哑了"


def test_R421_放行表每一条都还用得着():
    """放行表里的值要是已经从文件里删掉了, 那一条就该一起删 —— 否则它会悄悄替
    以后某个真写回来的同值粉色放行。"""
    for (f, hexv), why in ALLOWED.items():
        src = strip_ts_comments((ROOT / f).read_text(encoding="utf-8"))
        assert hexv.lower() in src.lower(), f"{f} 里已经没有 {hexv} 了, 放行表那一条该删({why})"
