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
RATCHET = {
    "裸圆角": 2305,        # rounded / -sm / -md / -lg / -xl / -2xl(非语义 token)
    "任意字号": 2336,      # text-[Npx]
    "硬编码色": 1071,      # text-/bg-/border- + Tailwind 调色板
    "任意容器宽": 44,      # max-w-[Npx]
}


def _tsx_text() -> str:
    try:
        return "\n".join(p.read_text(encoding="utf-8") for p in SRC.rglob("*.tsx"))
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
# 二、棘轮: 越界用法只许降不许升
# ================================================================

_PALETTE = ("slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|"
            "emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose")


def _counts(text: str) -> dict[str, int]:
    raw_radius = [m for m in re.findall(r"\brounded(?:-(?:sm|md|lg|xl|2xl|3xl))?\b", text)]
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
