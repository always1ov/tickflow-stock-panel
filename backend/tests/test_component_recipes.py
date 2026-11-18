"""R814: 控件视觉统一的棘轮 —— 手写配方只许降, 基础件覆盖只许升。

用户: 「统一整个项目的前端组件按钮啥的显示视觉效果, 就当作是固定的样式」。

## 为什么是棘轮而不是"一处都不许"

R813 的教训: 全站 1270 个 `<button>` 里, 708 个手写了字面 class, 合起来 **499 种
写法 / 262 种结构骨架**。这不是"再定一套样式"能解决的 —— 定完也没人拦得住第
500 种。而一次性改完 1270 个按钮既没法验证也没法回退。

所以按页分批迁移, 这里钉住三件事:

1. **手写配方只许降。** 每批迁移把数字往下调; 数字降了没调, 这条会红, 提醒你
   把成果锁住。新写一处手写, 数字涨, 当场红。
2. **基础件覆盖只许升。** `buttonClass()` 的文件数一旦回退, 说明又有人开始自己
   拼 class 串了。
3. **基础件本身不许越界。** 那几条在 `test_design_spec.py` 里(硬线), 不在这儿重复。

Run from backend with:
    .venv/bin/python -m pytest tests/test_component_recipes.py -q
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import pytest

from tests.frontend_source import SRC, code_lines

UI = SRC / "components" / "ui"

#: [R814] 迁移基线 —— **按钮/输入/下拉/卡片/徽标 只许降; 基础件覆盖只许升**。
#: 每完成一批迁移就把对应数字调下来(降了不调也会红, 防止成果不被锁住)。
RATCHET = {
    # [R817] P1(自选链 + 个股弹窗 + 复盘链)迁完: 708 → 642, 禁用态 105 → 98。
    # [R818] P2(选股 + 市场环境 + 指数 + 异动 + 连板)迁完: 642 → 618, 禁用态 98 → 96。
    # 剩下的绝大多数是整行容器钮 / 行内文字链接 / py-px 窄药丸 / 表格内
    # 小于 24px 的密集图标钮 —— 它们没有对应的基础件档位, 留给 P5 长尾。
    # [R819] P3(数据 + 设置: Data/System/AI/ImportCenter/DataSources/Monitoring)
    # 迁完: 618 → 596, 禁用态 96 → 94。
    # 剩下的绝大多数是整行容器钮 / 行内文字链接 / py-px 窄药丸 / 表格内
    # 小于 24px 的密集图标钮 —— 它们没有对应的基础件档位, 留给 P5 长尾。
    #
    # [R823] P4(回测 + 因子 + 信号 + 监控)迁完: 596 → 532, 输入 248 → 207,
    # 下拉 74 → 59, 卡片 161 → 133, 徽标 45 → 38, 弹窗面板 29 → 24,
    # 禁用态 94 → 80。这一批是表单密集区(StrategyBacktest / RuleEditor /
    # 因子库), 也是手写 color 最集中的一片 —— 硬编码色同批清了 112 处。
    "手写按钮配方": 532,
    "手写输入配方": 206,
    "手写下拉配方": 59,
    "手写卡片配方": 133,
    "手写徽标配方": 38,
    "禁用态opacity-40(基础件之外)": 80,
    "aria-pressed手写底色": 1,
    "手写弹窗面板": 24,
}

#: 用上基础件(`buttonClass()` 或 `<Button>`)的文件数, **只许升**(迁移的进度条)。
#: [R819] 口径从"调用 buttonClass()"放宽到"用上基础件": 直接写 `<Button>` 的页面
#: 已经不调那个函数了, 老口径会把迁移成果记成回退。56 → 73。
#: [R823] P4(回测 + 因子 + 信号 + 监控)迁完: 73 → 79。
BASE_COVERAGE = 79


def _files() -> list[Path]:
    return [p for p in sorted(SRC.rglob("*.tsx")) if ".test." not in p.name]


def _jsx_tags(src: str, tag: str) -> list[str]:
    """取开标签的属性串。

    **不能用 `<tag[^>]*>`**: `onClick={() => …}` 里的 `>` 会让正则在箭头函数处
    提前收尾, 于是 className 落到"取不到"里 —— 第一版统计因此把 921 个按钮误判
    成"没有 className"。这里按花括号配平扫到真正的 `>`。
    """
    out: list[str] = []
    for m in re.finditer(rf"<{tag}\b", src):
        i, depth = m.end(), 0
        while i < len(src):
            ch = src[i]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
            elif ch == ">" and depth == 0:
                break
            i += 1
        out.append(src[m.end():i])
    return out


_LITERAL = re.compile(r'className="([^"]*)"')


def _literal(attrs: str) -> str | None:
    m = _LITERAL.search(attrs)
    return m.group(1) if m else None


@lru_cache(maxsize=1)
def _counts() -> dict[str, int]:
    counts = {k: 0 for k in RATCHET}
    counts["buttonClass文件数"] = 0
    for path in _files():
        src = code_lines(path.read_text(encoding="utf-8"))
        for attrs in _jsx_tags(src, "button"):
            literal = _literal(attrs)
            if literal:
                counts["手写按钮配方"] += 1
                if "aria-pressed" in attrs and re.search(r"\bbg-[\w-]+", literal):
                    counts["aria-pressed手写底色"] += 1
        counts["手写输入配方"] += sum(1 for a in _jsx_tags(src, "input") if _literal(a))
        counts["手写下拉配方"] += sum(1 for a in _jsx_tags(src, "select") if _literal(a))
        counts["手写卡片配方"] += len(re.findall(
            r"rounded-card\s+border\s+border-border\s+bg-surface", src))
        counts["手写徽标配方"] += len(re.findall(r"bg-elevated\s+px-", src))
        for m in re.finditer(r'panelClassName="([^"]*)"', src):
            if re.search(r"\bbg-|\brounded-(?!dialog)", m.group(1)):
                counts["手写弹窗面板"] += 1
        if UI not in path.parents:
            counts["禁用态opacity-40(基础件之外)"] += src.count("disabled:opacity-40")
        # [R819] 覆盖看的是"这个文件用上了基础件", 而不是"用没用某个函数":
        # P3 那几页原来是 `const BTN = buttonClass(...)` 再到处铺, 迁完直接写
        # `<Button>`, buttonClass( 反而从文件里消失了 —— 只数函数名会把"越迁越
        # 规范"判成"回退成手写"。两种用法都算覆盖。
        if "buttonClass(" in src or "<Button" in src:
            counts["buttonClass文件数"] += 1
    return counts


@pytest.mark.parametrize("kind", list(RATCHET))
def test_R814_手写配方只许降不许升(kind):
    got = _counts()[kind]
    cap = RATCHET[kind]
    assert got <= cap, (
        f"「{kind}」从 {cap} 涨到了 {got} —— 又新写了 {got - cap} 处绕开 `components/ui/` 的写法。\n"
        f"按钮/输入/下拉/徽标请用 Button.tsx / Field.tsx / Badge.tsx 里的取值, "
        f"不要就地手写 class 串。"
    )
    if got < cap:
        pytest.fail(
            f"「{kind}」已降到 {got}(棘轮还写着 {cap})—— "
            f"**把 RATCHET 里的数字调到 {got}**, 否则这一批迁移的成果不会被锁住。")


def test_R814_基础件覆盖只许升不许降():
    got = _counts()["buttonClass文件数"]
    assert got >= BASE_COVERAGE, (
        f"用 `buttonClass()` 的文件从 {BASE_COVERAGE} 掉到 {got} —— "
        f"有页面又回去手写按钮 class 串了。")
    if got > BASE_COVERAGE:
        pytest.fail(
            f"用 `buttonClass()` 的文件已增加到 {got}(基线写着 {BASE_COVERAGE})—— "
            f"**把 BASE_COVERAGE 调到 {got}**, 把这一批的成果锁住。")


def test_R814_基础件里禁用态只有一个值():
    """全站禁用态只有一个说法。

    现状里 `Switch` 与个股弹窗的按钮用 40、`Button` 用 50 —— 同屏相邻的两个
    不可点控件深浅不同, 读的人会以为其中一个是"半可用"。R814 统一到 50。
    """
    offenders = []
    for path in sorted(UI.glob("*.tsx")):
        src = code_lines(path.read_text(encoding="utf-8"))
        if "disabled:opacity-40" in src:
            offenders.append(path.name)
    assert not offenders, (
        f"基础件里还在用 disabled:opacity-40: {offenders} —— 全站只有 50 这一个值")


def test_R814_新基础件必须从index导出():
    """加了组件却没人能 import, 等于没加 —— 下一个写界面的人只会回去手写。"""
    index = (UI / "index.ts").read_text(encoding="utf-8")
    for name in ("Badge", "Toolbar", "DialogClose", "dialogPanel", "Checkbox", "Radio"):
        assert name in index, f"`{name}` 没有从 components/ui/index.ts 导出"
