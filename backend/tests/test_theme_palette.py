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

[R379] 用户又给了一份 WavMint 视觉设计包, 说「现在的前端太像一个后台系统」,
于是**铬色**换成了那一套暖白＋靛蓝。上面那张表因此拆成 `CHROME` 与 `MARKET`:
铬色可以随皮肤换, **指标色冻结**。用户当场补的那句话就是这条规矩的来源 ——
「我这个是炒股系统, 所以一些指标显示颜色要对要注意」。

[R382] R379 只换了亮色, 而用户用的是暗色 —— 他截图问「怎么前端还是老样子」。
版式那两轮(R380/R381)是主题无关的, 暗色下照常生效, 漏的只有颜色这一层。
所以暗色的强调色也对齐到同一个靛蓝, 并补了一组钉暗色的守卫。
**作者的黑(base/surface/elevated/border)一个字没动** —— R163 记着那是定过案的。
"""
from __future__ import annotations

import math
import pathlib
import re

from tests.frontend_source import SRC

CSS = SRC / "index.css"

# 用户逐值指定的那一套 —— **这张表就是需求本身**, 改它等于改需求
#
# [R379] 拆成两段, 因为它们来自**两次不同的要求, 改动权限也不同**:
#
#   · 铬色(界面本身的颜色)来自 R379 那份 WavMint 视觉设计包 —— 用户说
#     「现在的前端太像一个后台系统」, 换的是皮肤。以后还可能再换。
#   · 指标色(涨/跌/警示)来自 R368 用户逐值给的那三个 hex, **冻结**。
#     用户原话: 「我这个是炒股系统, 所以一些指标显示颜色要对要注意」——
#     红涨绿跌是看盘的人肌肉记忆里的东西, 换皮肤不能把它带着漂。
#     下面 test_R379_换皮肤没有碰到任何指标色 专门钉这一段。
#
# [R408] 亮色这四档**由用户改口而压深**: 「所有颜色显示都淡了好多, 看起来好辛苦」
#     「总之觉得颜色都浅了」。改的是 CHROME(皮肤, 上面那条注释写明「以后还可能
#     再换」), **MARKET 一个字没碰**。旧 → 新, 以及为什么是这四个:
#
#       --border        #E7EAF2 → #D1D4DD   白底对比 1.12 → 1.38
#       --border-input  #DCE0EF → #C2C7D6   1.23 → 1.58(仍比普通边框深一档)
#       --fg-secondary  #596376 → #4B5569   5.65 → 7.00
#       --fg-muted      #6B7488 → #5A6377   4.38 → 5.63(**原值低于正文线 4.5**)
#
#     根子在 R399 撤掉静态面阴影, 理由是「层级靠 base/surface/elevated 三档
#     明度差 + 1px 边框」—— 这话在暗色成立, 在亮色不成立(边框 1.12、抬升 1.10,
#     阴影一撤就什么都不剩)。**暗色那边一个字没动**: 那是 R163「还是用回以前
#     作者的黑」定过案的, 由 test_R382_作者的黑一个字没动 钉着。
# [R501] 背景这一层照用户给的参考截图换成中性白灰: 页底 #F6F7FB → #FFFFFF,
#     侧栏 #FFFFFF → #FAFAFA, 次级面去掉蓝调(明度不动, 见下面那条 R501 守卫)。
#     用户原话: 「参考这个图片的风格, 日间主题就用这种颜色背景色」。只换背景, 边框/文字/
#     主题色/指标色一个没动。
# [R509] 主题色去蓝: 用户指着侧栏选中项「别搞蓝色主题, 就只用黑白」。四个 accent 令牌换成
#     中性黑灰(#222222 / 悬停 #3D3D3D / 选中底 #EDEDED); 文字三级、边框、背景、指标色都没动。
CHROME = {
    "base": "#FFFFFF",
    "sidebar": "#FAFAFA",
    "elevated": "#E2E2E2",
    "border": "#D1D4DD",
    "border-input": "#C2C7D6",
    "fg-primary": "#222738",
    "fg-secondary": "#4B5569",
    "fg-muted": "#5A6377",
    "accent": "#222222",
    "accent-text": "#222222",
    "accent-hover": "#3D3D3D",
    "accent-soft": "#EDEDED",
}
# **这三个不许动。** 值来自 R368, 与 WavMint 那份包无关。
MARKET = {
    "bull": "#D92D20",
    "bear": "#15803D",
    "warning": "#B54708",
}
PALETTE = {**CHROME, **MARKET}


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
    """`:root { … }` 那一段 —— 只看亮色。
    [R382] 暗色那一段现在也有守卫了, 见 `_dark_block`。"""
    css = CSS.read_text(encoding="utf-8")
    i = css.index(":root {")
    j = css.index("html.dark {")
    blk = css[i:j]
    assert blk.strip() and "--base:" in blk
    return blk


def _dark_block() -> str:
    """`html.dark { … }` 那一段。[R382] 起暗色也有要钉的东西了。"""
    css = CSS.read_text(encoding="utf-8")
    i = css.index("html.dark {")
    blk = css[i:css.index("\n}", i)]
    assert blk.strip() and "--accent:" in blk
    return blk


def _token(blk: str, name: str) -> tuple[float, float, float]:
    m = re.search(rf"--{re.escape(name)}:\s*([\d.]+)\s+([\d.]+)\s+([\d.]+)\s*;", blk)
    assert m, f"这一段里找不到 --{name}"
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
    """侧栏必须有**自己的一档**, 不能直接写 `bg-surface`。

    [R368] 当时两档是 #F8FAFC / #FFFFFF(侧栏更灰);
    [R379] 换成 WavMint 工作台的分法后两档都是白, 分界改由**页底那条缝**给出 ——
    所以这条断言钉的从来不是"两个颜色不一样", 而是**侧栏走的是自己那个令牌**:
    只要它还是一档独立的变量, 下次想让侧栏再变灰就是改一个值的事, 不用回头
    满仓库找 `bg-surface`。"""
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
    """用户: 「不使用…发光效果」。原来有 15 处 `shadow-[0_0_…]` 的彩色外发光。

    **[R377] 第一版只扫 `shadow-[0_0_…]` —— 正中无偏移的那种光晕。** 于是带偏移的
    辉光(`shadow-[0_8px_24px_rgba(59,130,246,0.45)]`、`shadow-[0_6px_24px_-10px_…]`)
    整个漏网: 上游 v0.3.0 新带进来的 AI 助手悬浮球就是一个, 仓里还蹲着 5 处存量,
    守卫全绿。**和当初漏掉 `bg-[radial-gradient(…)]` 是同一类洞** —— 扫的是「我想到
    的那一种写法」, 不是立论。

    立论其实是**阴影里不许出现写死的颜色**: 辉光之所以是辉光, 在于它带色; 而写死
    的色值同时也绕开了 `--accent`/`--border` 那套令牌, 换主题不会跟着变。所以判据
    改成「任意值阴影里含颜色字面量(`rgba(` / `rgb(` / `#`)」—— 位移、模糊、扩散
    随便写, 中性黑(`rgba(0,0,0,…)`)的抬升阴影也照旧放行, 那是层次不是发光。
    走令牌的 `shadow-[0_2px_8px_oklch(var(--accent)/0.15)]` 同样放行。
    """
    # 中性黑的抬升阴影: 不带色相, 是「浮起来」不是「发光」
    neutral = re.compile(r"rgba?\(\s*0\s*,\s*0\s*,\s*0\s*[,)]")
    colored = re.compile(r"rgba?\(|#[0-9a-fA-F]{3,8}\b")
    hits = []
    for f in sorted(SRC.rglob("*.tsx")):
        txt = f.read_text(encoding="utf-8")
        for m in re.finditer(r"(?:drop-)?shadow-\[([^\]]*)\]", txt):
            body = m.group(1)
            if "0_0_" in body:                       # 正中光晕, 一律算发光
                hits.append(f"{f.relative_to(SRC)}: {m.group(0)}")
                continue
            if colored.search(neutral.sub("", body)):  # 剩下的色值才是辉光
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
            # [R377] 第一版要求 `bg-gradient` 与 `from-…/to-…` **写在同一行** —— 而那两个
            # AI 气泡把方向类放在 className 上、把 `from-purple-500/25 to-fuchsia-500/20`
            # 放在另一行的 `accent` 变量里, 于是一整条紫→品红渐变从守卫底下走过去了。
            # 色阶类本来就常被抽成变量, 所以判据改成**单看色阶类**: 只要 `from-`/`to-`
            # 落在禁色上, 不管方向类在不在同一行。
            if "bg-gradient" not in line and not re.search(r"\b(?:from|via|to)-[a-z]+-\d", line):
                continue
            i = line.index("bg-gradient") if "bg-gradient" in line else 0
            seg = line[i:]
            if any(f"-{b}-" in seg or f"-{b}/" in seg for b in banned):
                hits.append(f"{f.relative_to(SRC)}: {seg.strip()[:80]}")
            elif "from-sky-" in seg and "to-blue-" in seg:
                hits.append(f"{f.relative_to(SRC)}: {seg.strip()[:80]}")
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


# ── [R379] 换皮肤不许碰指标色 ────────────────────────────────────────────
#
# 用户在这一轮当场补的: 「我这个是炒股系统, 所以一些指标显示颜色要对要注意」。
#
# 换皮肤时最容易出的事不是"忘了改", 而是"顺手一起改了" —— 一遍全局替换把
# 涨跌色也扫进去, 屏幕上红还是红、绿还是绿, 只是**换了一个红**, 谁也看不出来,
# 而看盘的人靠的正是那个肌肉记忆。所以这一组钉的是「哪些东西这次不许动」。

K_BULL, K_BEAR = "#C74040", "#2D9B65"


def test_R379_换皮肤没有碰到任何指标色():
    """三个语义 token 逐字对上 R368 冻结的那几个 hex。"""
    blk = _light_block()
    bad = []
    for name, want in MARKET.items():
        got = _oklch_to_hex(*_token(blk, name))
        if got.upper() != want.upper():
            bad.append(f"--{name}: 现在是 {got}, 冻结值是 {want}")
    # `--danger` 与 `--bull` 同值 —— 破坏性按钮与价格格子的语境不重叠
    assert _token(blk, "danger") == _token(blk, "bull"), "--danger 不再等于 --bull"
    assert not bad, "指标色被换皮肤带着漂了:\n  " + "\n  ".join(bad)


def test_R379_K线那两个常量没动():
    """K 线的红绿是**写死在组件里的常量**(canvas 不吃 CSS 变量), 换皮肤时它们
    既不会跟着变、也没有任何守卫拦着有人顺手改 —— 所以在这儿点名钉住。
    它们是亮暗两套共用的, 改一处两套都变。"""
    from tests.frontend_source import code_of
    code = code_of("components/EChartsCandlestick.tsx")
    # 先断言再切片 —— 直接 index() 的话改了色只会抛 ValueError, 看不出改了什么
    assert f"bull: '{K_BULL}'" in code and f"bear: '{K_BEAR}'" in code, \
        "K 线的涨跌红绿被改了(它是亮暗两套共用的常量)"
    multi = code_of("components/EChartsMultiDayIntraday.tsx")
    assert f"up: '{K_BULL}'" in multi and f"down: '{K_BEAR}'" in multi, \
        "多日分时的涨跌色与 K 线对不上了"


def test_R379_主题色不许落进涨跌的色相带():
    """靛蓝离红绿很远, 现在当然没问题 —— **钉的是以后**。

    下一次换皮肤如果挑了个偏红或偏绿的主题色, 界面上就会出现「不表示涨跌、
    但看着像涨跌」的色块(选中态、主按钮、链接), 而那是**颜色在说假话**,
    没有任何东西会报错。留 40° 的隔离带。
    """
    blk = _light_block()
    _, c_accent, h_accent = _token(blk, "accent")
    # [R509] 主题色改成中性黑灰(彩度 0): 没有色相可言, 灰不可能被看成涨或跌 —— 这条守卫
    # 钉的是「以后换成偏红偏绿」, 中性色直接放行。哪天又换回有彩度的, 下面照旧生效。
    if c_accent < 0.01:
        return
    for name in ("bull", "bear"):
        h = _token(blk, name)[2]
        d = min(abs(h_accent - h), 360 - abs(h_accent - h))
        assert d >= 40, f"主题色色相 {h_accent:.1f} 离 --{name} 的 {h:.1f} 只有 {d:.1f}°"


# ── [R379 第二层] 版式:页头放开 + 开篇块只有一个产地 ────────────────────
#
# 用户: 「我觉得现在的前端太像一个后台系统」。换色只解决一半 —— 剩下那一半是
# **版式**: 52px 的页头配一条实边框, 那是工具栏不是页头。
#
# 这一层刻意只动**两个共用件**(PageHeader / SectionIntro)与**一个容器**
# (设置区), 不逐页改: 逐页改既碰不全, 又必然随时间漂成 24 种样子。
# 看盘页的密度(表格行高、字号、列宽、卡片内边距)一个像素没动 —— 那是
# 这套工具的命根子, 不在这一层的范围里。


def test_R379_页头有呼吸感而且只有一个产地():
    """页头改一处 24 页受益。**这条钉的是那三个数没被调回去** ——
    它们看着像"随手写的样式", 其实是这一层改动的全部内容。"""
    from tests.frontend_source import code_of
    code = code_of("components/PageHeader.tsx")
    assert "min-h-[60px] px-4 py-3 border-b border-border/60" in code, \
        "页头被调回紧凑工具栏那一档了"
    assert "text-xl font-semibold leading-tight tracking-tight" in code, \
        "页标题字号被调回去了"
    # 徽标是药丸, baseline 对齐会让它坐歪 —— 这条是踩过才知道的。
    #
    # [R394] 原来钉的是整串 `"flex min-w-0 items-center gap-2.5"`, 而这条在乎的
    # 只有 `items-center` 那一个词。窄屏排版修好之后那一行还得加 `flex-wrap` /
    # `basis-full` / `pl-11`(给悬浮汉堡让位), **对齐方式一个字没动**, 这条却红了
    # —— 又一次「钉名字不钉性质」: 锚是那串字面量, 而纪律是那一个属性。
    # 改成只问标题行是不是 `items-center`, 顺带明确禁掉它真正怕的 `items-baseline`。
    title_row = code.split("<h1", 1)[0].rsplit("<div", 1)[-1]
    assert "items-center" in title_row, "标题行的对齐方式被动了(徽标会坐歪)"
    assert "items-baseline" not in title_row, "标题行用了 baseline 对齐, 药丸徽标会坐歪"


def test_R379_开篇块只有一个产地():
    """小号大写标签 + 大标题 + 一段说明 —— 这个版式原来**手搓了两份**, 字号、
    间距、标签颜色各写各的(一处 `text-accent/80`、另一处 `text-cyan-400/80`,
    后者还是照深色底调的)。两份的下场是必然的: 谁也不会记得同时改两处,
    于是同一个位置在两页长得不一样, **而且不报错**。

    所以这条钉两头: 组件在, 且**没有人再手搓第二份**。
    """
    from tests.frontend_source import SRC, code_of
    intro = code_of("components/SectionIntro.tsx")
    for anchor in ("export function SectionIntro", "eyebrow", "text-2xl font-semibold"):
        assert anchor in intro, f"SectionIntro 少了 {anchor}"

    # 手搓的特征: 那串 eyebrow 的字号/字重/字距组合
    hand_rolled = "text-[10.5px] font-semibold uppercase tracking-wider"
    offenders = [
        f.relative_to(SRC).as_posix()
        for f in sorted(SRC.rglob("*.tsx"))
        if f.name != "SectionIntro.tsx" and hand_rolled in code_of(f.relative_to(SRC).as_posix())
    ]
    assert not offenders, "又有人手搓开篇块了, 收进 SectionIntro:\n  " + "\n  ".join(offenders)


def test_R379_看盘页的密度一个像素没动():
    """**这一层最要紧的一条不是"改了什么", 是"没改什么"。**

    WavMint 那套是给「一屏几张卡」的工具站做的: 48px 控件、96px 区块间距。
    照搬到这里会把看盘要的信息密度毁掉 —— 一屏几百个数字才是这个工具的用处。
    所以钉住两个最容易被顺手放大的地方: 表格行的紧凑字号与行距。
    """
    from tests.frontend_source import code_of
    # 自选表格的行: 紧凑档位还在
    table = code_of("components/stock-table/primitives.tsx")
    assert "text-xs" in table or "text-[11px]" in table, "自选表格的紧凑字号没了"
    # 模拟盘信号行: R356 定下的行高与栅格没被放开
    flip = code_of("pages/FlipPaper.tsx")
    # [R383] 行高改成由整屏统一决定撑不撑(整屏没名次就不撑 —— 那时每行只有两行字,
    # 垫高是白送滚动)。**这不是"放开密度"而是相反**: 该紧的时候更紧了。
    # 所以这里钉的从"写死 3.5rem"换成"那一档还在, 且由 shape 统一决定"。
    # [R513] 信号行那套定宽网格随今日信号重做删了(三段各一种长相)。密度这条立论照旧钉:
    # 盯着那一段上百只, 一只一行 28px、12px 字, 多列密排 —— 放大它就是把一屏几百个数字毁掉。
    assert "flex h-7 break-inside-avoid items-center gap-2 border-b border-border/30 text-xs" in flip, \
        "模拟盘盯着那一段的密排行被放大了"
    assert "min-[1800px]:columns-5" in flip, "宽屏上盯着那一段的栏数被减了"


# ── [R382] 换皮肤别漏掉暗色 ──────────────────────────────────────────────
#
# R379 只换了亮色, 而用户用的是暗色 —— 于是「换了皮肤」在他屏幕上基本没发生,
# 他截图问「怎么前端还是老样子」。**版式那两轮(R380/R381)是主题无关的, 暗色下
# 照常生效; 漏的只有颜色这一层。**
#
# 教训不是「暗色忘了改」, 是**「主题色」这个东西本来就不该分主题** —— 同一个
# 产品在两套主题下得是同一个颜色, 否则它就是两个颜色。下面第一条钉的就是这个。


def test_R382_两套主题是同一个品牌色():
    """亮色靛蓝、暗色蓝 = 两个品牌色。明度可以按底色各调各的(暗底上要更亮),
    但**色相必须一致** —— 色相才是「这是什么颜色」。"""
    _, c_light, h_light = _token(_light_block(), "accent")
    _, c_dark, h_dark = _token(_dark_block(), "accent")
    # [R509] 两边都是中性(彩度 0)也算同一个品牌色 —— 「黑白」就是这个品牌的颜色;
    # 一边中性一边有彩度才是两个品牌色。
    if c_light < 0.01 and c_dark < 0.01:
        return
    assert c_light >= 0.01 and c_dark >= 0.01, "一套主题中性、一套有彩度 —— 两套主题成了两个品牌色"
    assert abs(h_light - h_dark) < 1.0, \
        f"亮色主题色色相 {h_light:.2f}, 暗色 {h_dark:.2f} —— 两套主题成了两个品牌色"


def test_R382_暗色的强调色不再借别处的值():
    """原来 `--accent-hover: var(--t-blue-400)` / `--accent-soft: var(--elevated)`。

    借值本身不是错, 错在**借的是不会跟着强调色走的东西**: 前者是蓝族色阶(换了
    色相它不跟), 后者是中性灰(R379 把侧栏选中态改成「同色系药丸」之后, 暗色下
    那颗药丸是灰的 —— 「选中」只剩字色在说, 底色一句话没说)。
    """
    blk = _dark_block()
    assert "--accent-hover: var(" not in blk, "暗色的悬停档又去借别处的值了"
    assert "--accent-soft: var(" not in blk, "暗色的选中底又借成中性灰了"
    # 三档都得是同一个色相
    h = _token(blk, "accent")[2]
    for name in ("accent-text", "accent-hover", "accent-soft"):
        assert abs(_token(blk, name)[2] - h) < 1.0, f"--{name} 与 --accent 不是同一个色相"
    # 暗色里 hover 要**更亮**(与亮色相反 —— 亮色是压暗)
    assert _token(blk, "accent-hover")[0] > _token(blk, "accent")[0], \
        "暗色的 hover 比常态还暗 —— 暗底上那是往后退, 不是往前站"
    # 选中底要坐在卡面之上、又远低于文字
    assert _token(blk, "surface")[0] < _token(blk, "accent-soft")[0] < _token(blk, "accent")[0], \
        "选中底的明度没夹在卡面与强调色之间"


def test_R501_日间背景是中性白灰_侧栏比页底略灰_次级面明度没被调浅():
    """用户: 「参考这个图片的风格, 日间主题就用这种颜色背景色」。

    · 三档背景都是中性灰(彩度 0) —— 参考图的灰没有蓝调;
    · 侧栏比页底略灰: 页底纯白之后, 白侧栏会与页面糊成一片;
    · 次级面(hover/次级面板)的明度仍是 R408 为了看得见压到的 0.91 —— 这次只去色, 不调浅。
    """
    blk = _light_block()
    for name in ("base", "sidebar", "elevated"):
        assert _token(blk, name)[1] == 0, f"--{name} 还带着色调"
    assert _token(blk, "base")[0] == 1, "页底不是纯白"
    assert _token(blk, "sidebar")[0] < _token(blk, "base")[0], "侧栏没比页底灰 —— 两块白会糊在一起"
    assert abs(_token(blk, "elevated")[0] - 0.91) < 0.0005, "次级面的明度被调浅了(R408 用户嫌淡)"
    # 边框不跟着参考图换淡: 页底与卡片都白之后, 卡片只剩边框在分界
    assert CHROME["border"] == "#D1D4DD"


def test_R382_作者的黑一个字没动():
    """R163 记着用户原话「还是用回以前作者的黑吧」—— 那是定过案的。
    这一轮换的是强调色, **底子不许跟着动**。"""
    blk = _dark_block()
    for name, want in (("base", 0.1452), ("surface", 0.2103),
                       ("elevated", 0.262), ("border", 0.365)):
        got = _token(blk, name)[0]
        assert abs(got - want) < 0.0005, f"--{name} 的明度动了: {got} != {want}"


def test_R382_暗色的指标色也没被带着漂():
    """与亮色那条同一个立论(用户: 「我这个是炒股系统, 指标显示颜色要对要注意」),
    只是这次钉暗色那一份 —— 换皮肤扫到哪儿, 哪儿就得有这条。"""
    blk = _dark_block()
    for name, want_h in (("bull", 22.00), ("bear", 158.00), ("warning", 70.00)):
        assert abs(_token(blk, name)[2] - want_h) < 0.01, f"--{name} 的色相被改了"
    assert _token(blk, "danger") == _token(blk, "bull"), "--danger 不再等于 --bull"
    # 主题色离涨跌足够远 —— 与亮色那条同样的隔离带。[R509] 中性(彩度 0)没有色相, 直接放行
    _, c_accent, h_accent = _token(blk, "accent")
    if c_accent < 0.01:
        return
    for name in ("bull", "bear"):
        h = _token(blk, name)[2]
        d = min(abs(h_accent - h), 360 - abs(h_accent - h))
        assert d >= 40, f"暗色主题色色相离 --{name} 只有 {d:.1f}°"
