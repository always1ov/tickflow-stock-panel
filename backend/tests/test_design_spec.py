"""[R399] 设计规范 · 方向 A「仪器盘」—— 规范本身 + 一把只许收紧的棘轮。

用户: 「风格不统一、排版乱、层次不清、三端适配也不好、整体不伦不类」,
要求按「诊断 → 定方向 → 统一重做」三阶段整理。第二阶段选定方向 A(TradingView)。

## 这一组钉两件事

**一、规范层本身存在且自洽。** 五档字号、两套间距刻度、三档圆角、三档容器宽,
都在 `index.css` 里有变量, 且 Tailwind 真的指向它们 —— 而不是"文档里写了、
代码里没接"。

**二、越界用法只许降不许升(棘轮)。** 现状是 2305 处裸圆角、2336 处任意字号、
1071 处硬编码色 —— **一次性改完既没法验证也没法回退**, 所以按页迁移。
棘轮的作用是: 迁移让数字往下走, 而任何一次新写的越界会让它往上走, 当场红。

**为什么不是"一处越界都不许有"**: 那样这条从第一天起就是红的, 只能被注释掉,
于是等于没有。棘轮能从第一天起就真的拦住"又新写了一个硬编码色"。
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.frontend_source import SRC

CSS = SRC / "index.css"
TW = SRC.parent / "tailwind.config.ts"

#: 迁移基线 —— **只许降不许升**。每完成一批迁移就把对应的数字调下来。
#: 调高需要一个明确理由(比如合并上游带进来一批), 并且要在提交信息里说明。
#: [R400] 这一轮的数字由**两件事**一起造成, 分开记清楚:
#:   ① 3.2 真的迁移掉的(基础件收口 + 模拟盘一条链):
#:        2305→2295 / 2336→2291 / 1071→1053 / 44→44
#:   ② `_tsx_text()` 改成**剥注释再数**(理由见那个函数):
#:        2295→2285 / 2291→2282 / 1053→1047 / 44→42
#: ② 那一截是一直躺在注释里的旧写法, **不是迁移成果** —— 只此一次, 以后不会再降。
#:
#: [R406] 「裸圆角」2285 → **945**: 不是迁移了 1340 处, 是**这条正则原来数错了** ——
#: 它把 `rounded-btn`(780)/`rounded-card`(243)/`rounded-input`(52)这些**规范
#: 想要的**语义 token 也算成了越界。真正要命的不是数字虚高, 而是: 把 `rounded-md`
#: 迁成 `rounded-btn` 时这个数**一动不动**, 棘轮看不见它存在的意义所在的那种迁移。
#: 详见 `_counts()`。另外「任意字号」2282 → 2280 是这一轮真迁的(两个档位选择器)。
RATCHET = {
    "裸圆角": 750,         # 真·裸圆角: rounded / -sm/-md/-lg/-xl/-2xl, 不含语义 token
    "任意字号": 42,      # text-[Npx]
    "硬编码色": 756,      # text-/bg-/border- + Tailwind 调色板
    "任意容器宽": 42,      # max-w-[Npx]
}

#: [R400] 基础件所在目录。新写界面从这里取, 不再手写 class 串。
UI = SRC / "components" / "ui"


def _tsx_text() -> str:
    """[R400] **剥注释再数。**

    R399 这把棘轮原来连注释一起数, 于是有两个反向的毛病:
      一、写清楚"这儿原来是 `focus:border-sky-400/50`, 为什么不再这么写"会让
          数字**涨**, 也就是**解释清楚了反而算违规**(当场撞上过);
      二、反过来, 删掉一段解释能让数字**降** —— 那不是迁移, 那是把理由删了。
    AGENTS.md 第 12 条本来就写着"注释和 docstring 里复述旧说法是允许的"。
    剥掉之后四个基线都往下走了一截, 那一截是**一直在里面的注释**, 不是这次迁移
    的成果 —— 分得清这一点, 下次看这几个数才不会得出错的结论。
    """
    try:
        return "\n".join(_strip_comments(p.read_text(encoding="utf-8"))
                         for p in SRC.rglob("*.tsx"))
    except OSError:  # pragma: no cover
        pytest.skip("拿不到前端源码(只跑后端时正常)")


def _css() -> str:
    try:
        return CSS.read_text(encoding="utf-8")
    except OSError:
        pytest.skip("拿不到前端源码(只跑后端时正常)")


# ================================================================
# 一、规范层存在且自洽
# ================================================================

def test_R399_字号五档且每档差至少2px():
    """旧状况是 16 种、一半是任意值, 9/10/11px 三档肉眼分不开 ——
    **层次不是靠字号建立的, 是靠位置猜的**。五档的意义在于每一档都能一眼分辨。"""
    css = _css()
    tiers = ["micro", "body", "title"]          # 这三档是定值, 可以直接比
    px = []
    for t in tiers:
        m = re.search(rf"--fs-{t}:\s*(\d+)px", css)
        assert m, f"字号档 --fs-{t} 不在规范里了"
        px.append(int(m.group(1)))
    assert px == sorted(px), f"字号档不是递增的: {px}"
    for a, b in zip(px, px[1:]):
        assert b - a >= 2, f"相邻两档只差 {b - a}px —— 分不开就等于没有分档"
    # 另外两档是 clamp(), 只要求它们存在
    for t in ("page", "hero"):
        assert f"--fs-{t}:" in css and "clamp(" in css, f"--fs-{t} 应当用 clamp() 随视口缩放"


def test_R399_两套间距刻度都在且不重叠():
    """骨架用 8 基(8/16/24/32/48/64), 行内密度另有一套(2/4/6/8)。

    **为什么不合并**: 8 基套进数据表行内会把 100+ 行的自选拉长约 40%,
    一屏少看十几行 —— 而「看盘的人要的是稳定可扫读」是这个项目的既定纪律。
    """
    css = _css()
    skeleton = [int(re.search(rf"--space-{i}:\s*(\d+)px", css).group(1)) for i in range(1, 7)]
    assert skeleton == [8, 16, 24, 32, 48, 64], f"骨架刻度被改了: {skeleton}"
    inline = [int(re.search(rf"--gap-{i}:\s*(\d+)px", css).group(1)) for i in range(1, 5)]
    assert inline == [2, 4, 6, 8], f"行内密度刻度被改了: {inline}"


def test_R399_圆角三档且是仪器盘的量级():
    """方向 A 的第二条纪律: 圆角小而统一。圆角一大, 整屏就从仪器变成卡片墙。"""
    css = _css()
    vals = {}
    for k in ("control", "card", "dialog"):
        m = re.search(rf"--r-{k}:\s*(\d+)px", css)
        assert m, f"--r-{k} 不在规范里了"
        vals[k] = int(m.group(1))
    assert vals["control"] <= vals["card"] <= vals["dialog"], f"圆角不是递增的: {vals}"
    assert vals["dialog"] <= 12, (
        f"弹窗圆角 {vals['dialog']}px 超出仪器盘的量级 —— 再大就是卡片墙了")


def test_R399_Tailwind真的指向规范变量():
    """**这条是整组里最要紧的一条。** 规范写在 CSS 里、Tailwind 却还指着写死的
    px, 等于"文档里写了、代码里没接" —— 那比没有规范更糟, 因为它看起来有。"""
    tw = TW.read_text(encoding="utf-8")
    for token, var in [("card", "--r-card"), ("btn", "--r-control"),
                       ("input", "--r-control"), ("dialog", "--r-dialog")]:
        assert re.search(rf"{token}:\s*'var\({var}\)'", tw), (
            f"borderRadius.{token} 没有指向 {var}")
    for tier in ("micro", "body", "title", "page", "hero"):
        assert f"--fs-{tier}" in tw, f"fontSize.{tier} 没有接上规范变量"
    for i in range(1, 7):
        assert f"--space-{i}" in tw, f"间距 s{i} 没有接上规范变量"


def test_R399_静态面无影_只有浮层留影():
    """仪器盘的层级靠 base/surface/elevated 三档明度差 + 1px 边框, 不靠阴影。"""
    css, tw = _css(), TW.read_text(encoding="utf-8")
    assert re.search(r"--shadow-flat:\s*none", css), "--shadow-flat 应当是 none"
    for k in ("sm", "DEFAULT", "card"):
        assert re.search(rf"{k}:\s*'var\(--shadow-flat\)'", tw), (
            f"boxShadow.{k} 还挂着投影 —— 静态面在仪器盘里不该有影")


# ================================================================
# 一·下 [R400] 基础件: 它自己必须是规范的样板
# ================================================================

def _strip_comments(src: str) -> str:
    """**扫代码, 不扫注释。**

    与 AGENTS.md 第 12 条同一个道理: 讲清楚"以前写的是 `sky-400/15`、为什么
    不再这么写"恰恰**必须**把旧写法原样写出来。不剥注释的话, 这几条守卫会把
    "解释清楚了"判成"违规", 于是逼人把理由删掉 —— 那正好是反的。
    """
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"(?<![:'\"])//[^\n]*", "", src)


def _ui_sources() -> dict[str, str]:
    try:
        srcs = {p.name: _strip_comments(p.read_text(encoding="utf-8"))
                for p in UI.glob("*.tsx")}
    except OSError:  # pragma: no cover
        pytest.skip("拿不到前端源码(只跑后端时正常)")
    assert srcs, "components/ui/ 空了 —— 基础件整个没了"
    return srcs


def test_R400_基础件自己不许越界():
    """**取值表这一处越界, 是会被抄到每个调用点的那种越界。**

    别处还有两千多处待迁移(见下面的棘轮), 但这三个文件是样板, 从第一天起
    就得是干净的 —— 所以这里不是棘轮而是硬线。
    """
    for name, src in _ui_sources().items():
        assert not re.search(r"text-\[\d+px\]", src), f"{name} 里写了任意字号"
        assert not re.search(r"\b(?:p|m|gap|px|py|mx|my)-\[\d+px\]", src), f"{name} 里写了任意间距"
        assert not re.search(rf"(?:text|bg|border)-(?:{_PALETTE})-\d{{2,3}}", src), (
            f"{name} 里写了调色板硬编码色 —— 基础件只许用语义色")
        assert "transition-all" not in src, (
            f"{name} 用了 transition-all(AGENTS.md 前端动效硬规则第 1 条)")


def test_R400_基础件的样式一律过cn():
    """**不过 `cn()` 的基础件, 它的 `className` 参数是假的。**

    裸模板串拼出来的 class, 调用方传的 `px-s3` 与内置的 `px-s2` 会两个都留着,
    最终哪个生效由 CSS 先后决定 —— 也就是"能传但不一定覆盖得掉", 而且不报错。
    (`cn()` 认得本项目刻度这件事另有 `src/lib/cn.test.ts` 钉着。)
    """
    for name, src in _ui_sources().items():
        assert "from '@/lib/cn'" in src, f"{name} 没有走 cn()"
        assert not re.search(r"className=\{`", src), (
            f"{name} 里有裸模板串拼 class —— 覆盖会失效, 请走 cn()")


def test_R400_按钮不重复实现全局已有的交互反馈():
    """按下缩放(R128)、焦点环(R124)、减少动效(R317)都是 `index.css` 里的全局规则。

    在按钮里再写一遍不是"更保险", 是**多一处会和全局写岔的地方** —— 全局那条
    按下反馈是 0.97 且排除了拖拽手柄, 组件里随手写个 0.95 就出现两种手感。
    """
    btn = _ui_sources()["Button.tsx"]
    for banned in ("active:scale", "focus:ring", "focus-visible:", "motion-reduce:"):
        assert banned not in btn, (
            f"Button.tsx 自己实现了 `{banned}` —— 这件事 index.css 已经全局做了")


def test_R400_主按钮字色不用那个有歧义的名字():
    """`text-base` **同时是颜色和字号**(Tailwind 出厂 16px 一档)。

    裸 class 串里靠 CSS 先后侥幸各管各的; 一旦进 `cn()` 就与字号撞组, **颜色被
    静默丢掉**。基础件全部走 `cn()`, 所以主按钮必须用没有歧义的那个名字。
    """
    btn = _ui_sources()["Button.tsx"]
    assert "text-on-accent" in btn, "主按钮的字色应当是 text-on-accent"
    assert not re.search(r"\btext-base\b", btn), (
        "Button.tsx 里出现了 text-base —— 它既是颜色又是字号, 进 cn() 会丢颜色")
    tw = TW.read_text(encoding="utf-8")
    assert "'on-accent'" in tw, "tailwind.config.ts 里没有 on-accent 这个语义色"


def test_R400_输入框不写那句永远不生效的聚焦边框():
    """`index.css` 里 `input:not([type='checkbox']):not([type='radio'])` 是 (0,2,1),
    而 Tailwind 的 `.focus\\:border-*:focus` 只有 (0,2,0) —— **低一档, 抢不过**。

    现状里那几个 `focus:border-sky-400/50` / `focus:border-violet-400/50` 从写下
    那天起就没生效过。基础件不许把这句话抄进去: 抄进来就是一行"看起来在做事、
    其实什么也没做"的代码, 而且会被后面几十个调用点跟着抄。
    真要让边框跟着变, 得改 `index.css` 那条规则的适用范围。
    """
    fld = _ui_sources()["Field.tsx"]
    assert not re.search(r"focus:border-", fld), (
        "Field.tsx 写了 focus:border-… —— 那条被 index.css 的输入框规则压着, 不会生效")


def test_R400_选中态全站只有一种说法():
    """现状里"选中"有 `sky-400/15`、`accent/10`、`violet-500/20` 三四种颜色 ——
    同一件事换页面换颜色, 读的人得先确认它们是不是一回事(AGENTS.md 第 12 条)。

    [R449] 那一种说法从强调色换成个股弹窗的**黑白反相**。用户: 「全局都想要像弹窗
    这样大的字体和样式」。弹窗那边(`stock-preview/pill.ts`)直接转用这一份。"""
    btn = _ui_sources()["Button.tsx"]
    m = re.search(r"const SELECTED = '([^']*)'", btn)
    assert m, "Button.tsx 里找不到选中态的取值"
    assert m.group(1) == "border border-foreground bg-foreground font-medium text-surface", (
        f"选中态不是弹窗那套反相: {m.group(1)}")
    pill = (SRC / "components" / "stock-preview" / "pill.ts").read_text(encoding="utf-8")
    assert "SELECTED as PILL_ON" in pill, "弹窗的选中态没有用全站那一份"


# ================================================================
# 二、棘轮: 越界用法只许降不许升
# ================================================================

_PALETTE = ("slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|"
            "emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose")


def _counts(text: str) -> dict[str, int]:
    # [R406] **把语义 token 排除在外** —— 这一条原来数的是"所有圆角"而不是
    # 名字说的"裸圆角": `\brounded\b` 会把 `rounded-btn`(780 处)、`rounded-card`
    # (243)、`rounded-input`(52)一起算进去, 而那三个正是规范**想要**的写法。
    #
    # 后果不只是数字虚高 1075。真正的毛病是: **把 `rounded-md` 迁成 `rounded-btn`
    # 时这个数一动不动** —— 棘轮看不见它存在的意义所在的那种迁移, 于是"迁移让
    # 数字往下走"这个前提根本不成立。(这一轮改档位选择器时当场撞上。)
    #
    # `rounded-full` 也不算越界: 药丸和圆点本来就该用它, 规范里没有、也不需要
    # 一个语义名字。`(?![-\w])` 把这些全挡在外面, 只留真正光秃秃的那些。
    raw_radius = [m for m in re.findall(
        r"\brounded(?:-(?:sm|md|lg|xl|2xl|3xl))?(?![-\w])", text)]
    return {
        "裸圆角": len(raw_radius),
        "任意字号": len(re.findall(r"text-\[\d+px\]", text)),
        "硬编码色": len(re.findall(rf"(?:text|bg|border)-(?:{_PALETTE})-\d{{2,3}}", text)),
        "任意容器宽": len(re.findall(r"max-w-\[\d+px\]", text)),
    }


@pytest.mark.parametrize("kind", list(RATCHET))
def test_R399_越界用法只许降不许升(kind):
    got = _counts(_tsx_text())[kind]
    cap = RATCHET[kind]
    assert got <= cap, (
        f"「{kind}」从 {cap} 涨到了 {got} —— 又新写了 {got - cap} 处绕开规范的用法。\n"
        f"规范在 src/index.css 的 [R399] 那一段; 要新增档位请改规范, 不要就地写死。")
    if got < cap:
        pytest.fail(
            f"「{kind}」已降到 {got}(棘轮还写着 {cap})—— "
            f"**把 RATCHET 里的数字调到 {got}**, 否则这一批迁移的成果不会被锁住, "
            f"下次有人写回去也不会红。")
