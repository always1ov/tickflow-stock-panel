"""[fork R368] 浅色蓝白配色 —— 用户逐值指定的那一套。

用户: 「前端采用浅色蓝白配色: 页面背景 #F6F8FC, 侧栏背景 #F8FAFC, 内容面板和
表单背景 #FFFFFF, 普通边框 #E4E7EC, 输入框边框 #D0D5DD。主要文字 #101828,
次要文字 #475467, 辅助文字 #667085。主题蓝 #2563EB, 悬停蓝 #1D4ED8, 选中背景
#EFF6FF。上涨红 #D92D20, 下跌绿 #15803D, 警示琥珀色 #B54708。…不使用蓝紫渐变、
大面积绿色、发光效果或彩色大面板。」

这组守卫钉两样:

  ① **色值真的是那几个 hex。** `index.css` 里存的是 oklch 分量, 肉眼对不出来 ——
     打错一位数字没有任何东西会报错, 屏幕上也只是"略微不对"。所以这里把 oklch
     **反解回 sRGB** 与用户给的 hex 逐个比。
  ② **那几条禁令没有回潮**: 发光、蓝紫渐变。
"""
from __future__ import annotations

import math
import pathlib
import re

from tests.frontend_source import SRC

CSS = SRC / "index.css"

# 用户逐值指定的那一套 —— **这张表就是需求本身**, 改它等于改需求
PALETTE = {
    "base": "#F6F8FC",
    "sidebar": "#F8FAFC",
    "border": "#E4E7EC",
    "border-input": "#D0D5DD",
    "fg-primary": "#101828",
    "fg-secondary": "#475467",
    "fg-muted": "#667085",
    "accent": "#2563EB",
    "accent-text": "#2563EB",
    "accent-hover": "#1D4ED8",
    "accent-soft": "#EFF6FF",
    "bull": "#D92D20",
    "bear": "#15803D",
    "warning": "#B54708",
}


# ── oklch → sRGB(反解, 用来把 CSS 里的数字翻回 hex)────────────────────
def _oklch_to_hex(L: float, C: float, H: float) -> str:
    h = math.radians(H)
    a, b = C * math.cos(h), C * math.sin(h)
    l_ = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3
    m_ = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3
    s_ = (L - 0.0894841775 * a - 1.2914855480 * b) ** 3
    r = +4.0767416621 * l_ - 3.3077115913 * m_ + 0.2309699292 * s_
    g = -1.2684380046 * l_ + 2.6097574011 * m_ - 0.3413193965 * s_
    bl = -0.0041960863 * l_ - 0.7034186147 * m_ + 1.7076147010 * s_

    def enc(x: float) -> int:
        x = max(0.0, min(1.0, x))
        x = 12.92 * x if x <= 0.0031308 else 1.055 * x ** (1 / 2.4) - 0.055
        return round(x * 255)

    return "#{:02X}{:02X}{:02X}".format(enc(r), enc(g), enc(bl))


def _light_block() -> str:
    """`:root { … }` 那一段 —— **只看亮色**。暗色一套这次一个字没动。"""
    css = CSS.read_text(encoding="utf-8")
    i = css.index(":root {")
    j = css.index("html.dark {")
    blk = css[i:j]
    assert blk.strip() and "--base:" in blk
    return blk


def _token(blk: str, name: str) -> tuple[float, float, float]:
    m = re.search(rf"--{re.escape(name)}:\s*([\d.]+)\s+([\d.]+)\s+([\d.]+)\s*;", blk)
    assert m, f"亮色里找不到 --{name}"
    return float(m[1]), float(m[2]), float(m[3])


def test_R368_每个色值都真的是用户给的那个hex():
    """**CSS 里存的是 oklch 分量, 肉眼对不出来。**

    打错一位数字不会有任何东西报错, 屏幕上也只是"略微不对" —— 这类错只有把
    数字反解回 sRGB 才抓得到。允许 ±1/255 的取整误差, 不允许更多。
    """
    blk = _light_block()
    bad = []
    for name, want in PALETTE.items():
        got = _oklch_to_hex(*_token(blk, name))
        if got.upper() != want.upper():
            # 逐通道比, 差 1 个量化档以内算对
            d = max(abs(int(got[i:i + 2], 16) - int(want.lstrip('#')[i - 1:i + 1], 16))
                    for i in (1, 3, 5))
            if d > 1:
                bad.append(f"--{name}: 写的是 {got}, 用户要的是 {want}(差 {d}/255)")
    assert not bad, "色值对不上:\n  " + "\n  ".join(bad)


def test_R368_白面板仍然是纯白():
    """用户: 「内容面板和表单背景 #FFFFFF」。"""
    blk = _light_block()
    L, C, _H = _token(blk, "surface")
    assert L == 1 and C == 0, f"面板底不是纯白: L={L} C={C}"


def test_R368_涨跌的色相锚到语义色_全站是同一个红():
    """[R317 立的规矩] 组件里 `text-red-400`(32 处)/`text-emerald-400` 才是涨跌的
    实际产地。它们的色相要与 `--bull`/`--bear` 对齐, 否则「涨」在这一页是一种红、
    在另一页是另一种红, **而两边都不报错**。"""
    blk = _light_block()
    h_bull, h_bear = _token(blk, "bull")[2], _token(blk, "bear")[2]
    for fam, want in (("red", h_bull), ("emerald", h_bear)):
        for step in (300, 400, 500):
            h = _token(blk, f"t-{fam}-{step}")[2]
            assert abs(h - want) < 0.5, \
                f"--t-{fam}-{step} 色相 {h} 没锚到 {want} —— 全站不是同一个颜色"


def test_R368_默认亮色_而且两处判据逐字一致():
    """**两处**: `index.html` 的预渲染脚本与 `src/lib/theme.ts` 的 `getTheme()`。

    不一致的表现是**首屏先画一种再跳成另一种**(FOUC), 而两边看上去都"没坏"。
    """
    html = (SRC.parent / "index.html").read_text(encoding="utf-8")
    assert "localStorage.getItem('tf-theme') === 'dark'" in html, \
        "预渲染脚本的判据不是「显式 dark 才暗」"
    from tests.frontend_source import code_of
    ts = code_of("lib/theme.ts")
    assert "localStorage.getItem(KEY) === 'dark' ? 'dark' : 'light'" in ts, \
        "getTheme() 的判据与预渲染脚本对不上 —— 首屏会闪一下"
    assert "return 'light'" in ts, "读不到 localStorage 时没退回亮色"


def test_R368_侧栏与内容面板不是同一档():
    """用户把这两个背景分开指定了(#F8FAFC / #FFFFFF)——
    同色的话两块贴在一起没有分界。"""
    from tests.frontend_source import code_of
    layout = code_of("components/Layout.tsx")
    assert "'bg-sidebar flex flex-col min-h-0 overflow-hidden'" in layout, \
        "侧栏没用它自己那一档"
    tw = (SRC.parent / "tailwind.config.ts").read_text(encoding="utf-8")
    assert "sidebar:   'oklch(var(--sidebar)" in tw, "sidebar 这一档没暴露给 Tailwind"


def test_R368_输入框边框走更深那一档_且不靠改组件():
    """全站输入框散在几十个文件里、写法还不统一 —— 逐个去改既碰不全又必然漂。
    「输入类控件的边框更深」本来就是**设计语言**的一条, 位置就在 index.css。"""
    css = CSS.read_text(encoding="utf-8")
    assert "border-color: oklch(var(--border-input));" in css, "输入框边框规则没了"
    i_star = css.index("* { border-color: oklch(var(--border)); }")
    i_input = css.index("border-color: oklch(var(--border-input));")
    assert i_star < i_input, "输入框那条排在通配符之前, 会被它盖掉"


def test_R368_全站没有发光():
    """用户: 「不使用…发光效果」。原来有 15 处 `shadow-[0_0_…]` 的彩色外发光。"""
    hits = []
    for f in sorted(SRC.rglob("*.tsx")):
        for m in re.finditer(r"(?:drop-)?shadow-\[0_0_[^\]]*\]", f.read_text(encoding="utf-8")):
            hits.append(f"{f.relative_to(SRC)}: {m.group(0)}")
    assert not hits, "发光回潮了:\n  " + "\n  ".join(hits)


def test_R368_没有彩色大面板():
    """用户: 「不使用…彩色大面板」。

    **这一条是截图抓出来的, 不是断言抓出来的。** 第一版只扫 `bg-gradient-to-*`
    这类方向类, 于是 `bg-[radial-gradient(…)]` 这种任意值写法整个漏网 —— 而登录
    页那两片铺满整屏的紫+蓝光晕(`rgba(139,92,246,0.15)` / `rgba(59,130,246,0.12)`)
    正是它。守卫全绿, 屏幕上一大片紫。

    教训写在这儿: **扫类名的守卫只能挡住用类名写的东西。** 同一件事有第二种写法
    时, 断言必须把那一种也覆盖掉, 否则它挡的是"我想到的那一半"。
    """
    hits = []
    for f in sorted(SRC.rglob("*.tsx")):
        for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if "radial-gradient" not in line:
                continue
            # 品牌引导页那两处是**引导动画**, 走的是 token(oklch(var(--accent))),
            # 跟着主题走, 不是写死的彩色面板 —— 放行。
            if "Onboarding.tsx" in str(f) and "var(--accent)" in line:
                continue
            hits.append(f"{f.relative_to(SRC)}:{i}: {line.strip()[:90]}")
    assert not hits, "彩色大面板回潮了:\n  " + "\n  ".join(hits)


def test_R368_档位标签不用渐变_也不在白底上糊成一片():
    """五档能力标签原本是紫→品红 / 蓝→紫→琥珀的**渐变标签 + 渐变文字**, 而且
    色值全是照着深色底调的(`#a1a1aa` / `#60a5fa` / `#c084fc` 落在白卡片上对比
    只有 2 点几)。"""
    from tests.frontend_source import code_of
    code = code_of("lib/capability-labels.tsx")
    i = code.index("const TIER_STYLE")
    blk = code[i:code.index("\n}", i)]
    assert blk.strip()
    assert "linear-gradient" not in blk, "档位标签还在用渐变"
    assert "BackgroundClip: 'text'" not in blk, "还在用渐变文字"
    for dark_only in ("#a1a1aa", "#60a5fa", "#c084fc", "#fbbf24"):
        assert dark_only not in blk, f"这个色是给深色底调的, 白底上看不清: {dark_only}"


def test_R368_没有蓝紫渐变():
    """用户: 「不使用蓝紫渐变」。

    钉的是**跨色相**那种(蓝→紫 / 紫→品红 / 天蓝→蓝)。同色相的透明度渐变
    (`from-accent to-accent/30`、`from-bull/45 to-bull/90`)不在此列 —— 那是
    一根柱子的明暗, 不是"蓝紫渐变"。
    """
    banned = ("purple", "fuchsia", "violet", "indigo")
    hits = []
    for f in sorted(SRC.rglob("*.tsx")):
        for line in f.read_text(encoding="utf-8").splitlines():
            if "bg-gradient" not in line:
                continue
            seg = line[line.index("bg-gradient"):]
            if any(b in seg for b in banned):
                hits.append(f"{f.relative_to(SRC)}: {seg[:80]}")
            elif "from-sky-" in seg and "to-blue-" in seg:
                hits.append(f"{f.relative_to(SRC)}: {seg[:80]}")
    assert not hits, "蓝紫渐变回潮了:\n  " + "\n  ".join(hits)


# ── [R369] 全球指数特性整个下线 ─────────────────────────────────────────
#
# 用户: 「删除这部分, 不需要了」(截图是设置页那张「全球指数」卡)。


def test_R369_全球指数整个特性没了_不是只删了那张卡():
    """**只删设置卡不算删。** 那样特性还在跑、还在打上游, 只是没了开关 ——
    比留着更糟: 没有任何地方能让它停下来。

    这一条同时钉住**该留的留住了**: 上游的 A 股指数页 `pages/Indices.tsx` 一个
    字没动, 侧栏的 A 股指数卡照常在。
    """
    import pathlib

    from tests.frontend_source import SRC, code_of

    # ① fork 那两个后端模块真的删了(它们是 fork 独有的, 删掉不会与上游冲突)
    back = pathlib.Path(__file__).resolve().parents[1] / "app"
    for gone in ("services/global_indices.py", "api/global_indices.py"):
        assert not (back / gone).exists(), f"后端模块还在: {gone}"

    # ② 全仓不许再出现任何引用 —— 少摘一处就是"半死不活"
    pats = ("global_indices", "global-indices", "globalIndices", "GlobalIndex")
    hits = []
    for root, exts in ((back, (".py",)), (SRC, (".ts", ".tsx"))):
        for f in sorted(root.rglob("*")):
            if f.suffix not in exts or "__pycache__" in str(f):
                continue
            txt = f.read_text(encoding="utf-8")
            for p in pats:
                if p in txt:
                    # R369 自己那条说明历史的注释不算
                    if all("R369" in ln for ln in txt.splitlines() if p in ln):
                        continue
                    hits.append(f"{f}: {p}")
    assert not hits, "还有残留引用:\n  " + "\n  ".join(sorted(set(hits)))

    # ③ **该留的留住**: 上游 A 股指数页还在, 侧栏 A 股指数卡还在
    assert (SRC / "pages/Indices.tsx").exists(), "上游的 A 股指数页被误删了"
    layout = code_of("components/Layout.tsx")
    assert "function SidebarIndexQuotes({ rows, items, cnLive }" in layout, \
        "侧栏 A 股指数卡被一起删掉了"
    assert "{items.map(item => {" in layout, "A 股那几张卡的渲染没了"
