"""R813: 按钮不许用「灰底」。

用户反复提过: 市场环境页的按钮是灰的, 夜间看不清。根因不是主题变量本身, 而是
页面 CSS / JSX 手写按钮时用了「页面底色(--base)或浮起底色(--elevated)当按钮底」,
再配灰字(--fg-secondary) —— 暗色下整块和页面融在一起, 读起来就是禁用态。
全站按钮的正解是 `buttonClass()`: `bg-surface + text-foreground`(R645)。

这条守卫只拦**按钮自己的底色**:

- CSS: 选择器里带 `button`、且不是 `:hover/:focus/:active/:disabled` 这类状态规则的
  声明块, 不许把 `--base / --elevated / --muted` 当选中的底色。
- TSX: `<button>` 的 className 里, 去掉 `hover:` 等变体后, 不许出现
  `bg-base / bg-elevated / bg-muted`(含 `/40` 这类透明度写法)。

放行的: 透明底(ghost)、`bg-surface`(描边按钮)、`bg-accent`(主按钮)、
状态色与图表色; 也放行 `text-secondary` —— 无边框图标钮用次级字色是全站既有
约定(R645 的 ghost), 那不是"灰底按钮"。

Run from backend with:
    uv run pytest tests/test_button_fill_tokens.py -q
"""
from __future__ import annotations

import re
from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "src"

GRAY_FILL = re.compile(r"background(?:-color)?\s*:[^;]*var\(--(?:base|elevated|muted)\b")
VARIANT = re.compile(r"^[\w-]+:")
GRAY_BG_TOKEN = re.compile(r"\bbg-(?:base|elevated|muted)(?:/\d+)?\b")
STATE = re.compile(r":(?:hover|focus|focus-visible|active|disabled)\b")
SELECTED = re.compile(r'\[aria-(?:pressed|selected)="true"\]')


def _css_rules(text: str):
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    for raw_selector, body in re.findall(r"([^{}]+)\{([^{}]*)\}", text):
        selector = " ".join(raw_selector.split())
        if selector.startswith("@"):
            continue
        yield selector, body


def test_css_button_rules_do_not_fill_gray():
    offenders = []
    for path in FRONTEND.rglob("*.css"):
        for selector, body in _css_rules(path.read_text(encoding="utf-8")):
            parts = [p.strip() for p in selector.split(",")]
            plain = [
                p for p in parts
                if "button" in p and not STATE.search(p) and not SELECTED.search(p)
            ]
            if plain and GRAY_FILL.search(body):
                offenders.append(f"{path.relative_to(FRONTEND)}: {selector}")
    assert not offenders, (
        "按钮底色用了 --base/--elevated/--muted(暗色下=灰块), 改用 --surface + --fg-primary:\n"
        + "\n".join(offenders)
    )


def test_tsx_buttons_do_not_fill_gray():
    offenders = []
    for path in FRONTEND.rglob("*.tsx"):
        source = path.read_text(encoding="utf-8")
        for match in re.finditer(r"<button\b[^>]*?>", source, re.S):
            tag = match.group(0)
            literal = re.search(r'className="([^"]*)"', tag)
            if not literal:
                continue
            classes = [
                token for token in literal.group(1).split()
                if not VARIANT.match(token)
            ]
            if GRAY_BG_TOKEN.search(" ".join(classes)):
                line = source[: match.start()].count("\n") + 1
                offenders.append(f"{path.relative_to(FRONTEND)}:{line}")
    assert not offenders, (
        "按钮 className 里用了 bg-base/bg-elevated/bg-muted(暗色下=灰块), "
        "改用 bg-surface + text-foreground(buttonClass 的描边档):\n"
        + "\n".join(offenders)
    )


# ================================================================
# R816: 文字不许和自己的底色同色
# ================================================================
#
# 用户截图: 市场环境页签选中那一格是一块浅色, 可「市场环境」四个字不见了。
# 根因不是缺规范, 是那张页面 CSS 把 `--accent-text` 当「accent 实底上的字」用了 ——
# 而 `--accent-text` 是「深底上的 accent 文字」, 在亮暗两套主题里都和 `--accent` 同值。
# 这跟 R813 的灰底按钮是同一类: 静态就能判, 不必等截图。

DECL_BG = re.compile(r"(?:^|;)\s*background(?:-color)?\s*:[^;]*var\((--[\w-]+)")
DECL_FG = re.compile(r"(?:^|;)\s*color\s*:[^;]*var\((--[\w-]+)")


def test_R816_同一个声明块里字色不许等于底色():
    """`background: var(--x); color: var(--x)` —— 不管亮色暗色, 字都隐形。"""
    offenders = []
    for path in FRONTEND.rglob("*.css"):
        for selector, body in _css_rules(path.read_text(encoding="utf-8")):
            bg, fg = DECL_BG.search(body), DECL_FG.search(body)
            if bg and fg and bg.group(1) == fg.group(1):
                offenders.append(f"{path.relative_to(FRONTEND)}: {selector} ({bg.group(1)})")
    assert not offenders, (
        "底色和字色用了同一个 token, 文字在这个主题下会隐形:\n" + "\n".join(offenders))


def test_R816_accent底上的字不许用accent_text():
    """`--accent-text` 不是「accent 底上的字」—— 它和 `--accent` 同值。
    实底上的字只有两档正解: `--base`(等价 `text-on-accent`) 或 `--surface`(等价 `SEG_ON`)。"""
    offenders = []
    for path in FRONTEND.rglob("*.css"):
        for selector, body in _css_rules(path.read_text(encoding="utf-8")):
            if (re.search(r"(?:^|;)\s*background(?:-color)?\s*:[^;]*var\(--accent\)", body)
                    and re.search(r"(?:^|;)\s*color\s*:[^;]*var\(--accent-text\)", body)):
                offenders.append(f"{path.relative_to(FRONTEND)}: {selector}")
    assert not offenders, (
        "accent 实底上用了 --accent-text 当字色 —— 两者同值, 字会隐形。"
        "改用 --base 或 --surface:\n" + "\n".join(offenders))
