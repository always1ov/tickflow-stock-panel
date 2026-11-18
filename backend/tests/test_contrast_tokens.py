"""[R816] 字不许隐形 —— 所有页面、两套主题, 不用等截图。

用户截图: 市场环境页签选中那一格是一块浅色, 可「市场环境」四个字不见了。
两处根因:
1. 页面 CSS 把 `--accent-text` 当「accent 实底上的字」用, 而它在亮暗两套里都和
   `--accent` **同值** —— 白底白字 / 浅灰底浅灰字, 两套主题一样隐形;
2. 同页三处 `bg-accent text-white`: 暗色的 accent 是 #E4E4E4(浅灰), 白字贴上去几乎看不见。

这类问题**只靠肉眼看截图才发现**是不够的: 十二个页面各自手写 CSS/className,
换个状态色就会再犯一次。所以这里静态判, 判据三类:

1. 同一个声明块里底色与字色解析到同一个 token 值 → 隐形;
2. CSS 里 `--accent` 实底配 `--accent-text` 字 → 两者同值;
3. TSX 里 `text-white` 压在一个「亮底」token 上(oklch 亮度 > 0.8) → 暗色下隐形。

token 的值从 `index.css` **现读**(`:root` 与 `html.dark` 两块), 不抄常数 ——
主题一改(比如再调 accent), 这条守卫自动跟着变。
"""
from __future__ import annotations

import re
from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "src"
INDEX_CSS = (FRONTEND / "index.css").read_text(encoding="utf-8")

BG_DECL = re.compile(r"(?:^|;)\s*background(?:-color)?\s*:[^;]*var\(--([\w-]+)\)")
FG_DECL = re.compile(r"(?:^|;)\s*color\s*:[^;]*var\(--([\w-]+)\)")

# tailwind 类名 → token 名(与 tailwind.config.ts 的映射一致)
BG_TW = {
    "base": "base", "surface": "surface", "elevated": "elevated",
    "foreground": "fg-primary", "accent": "accent", "border": "border",
}
FG_TW = {
    "foreground": "fg-primary", "secondary": "fg-secondary", "muted": "fg-muted",
    "accent": "accent-text", "surface": "surface", "base": "base", "border": "border",
}


def _theme_values(selector: str) -> dict[str, str]:
    vals: dict[str, str] = {}
    for block in re.finditer(rf"(?m)^\s*{re.escape(selector)}\s*\{{([^}}]*)\}}", INDEX_CSS):
        for name, value in re.findall(r"--([\w-]+)\s*:\s*([^;]+);", block.group(1)):
            vals[name] = " ".join(value.split())
    return vals


_LIGHT = _theme_values(":root")
_DARK = {**_LIGHT, **_theme_values("html.dark")}
THEMES = (("亮", _LIGHT), ("暗", _DARK))


def _css_rules(text: str):
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    for raw_selector, body in re.findall(r"([^{}]+)\{([^{}]*)\}", text):
        selector = " ".join(raw_selector.split())
        if selector.startswith("@"):
            continue
        yield selector, body


def test_R816_token两套主题都读到了():
    """守卫自己的前提: 读不到值就会"全绿"——那比红更危险。"""
    for name in ("base", "surface", "elevated", "border", "fg-primary", "accent"):
        assert name in _LIGHT and name in _DARK, f"{name} 没从 index.css 读出来"
    assert _LIGHT["base"] != _DARK["base"], "亮暗两套读成了同一份, 解析错了"


def test_R816_css里底色和字色不许同值():
    offenders = []
    for path in FRONTEND.rglob("*.css"):
        for selector, body in _css_rules(path.read_text(encoding="utf-8")):
            bg, fg = BG_DECL.search(body), FG_DECL.search(body)
            if not bg or not fg:
                continue
            b, f = bg.group(1), fg.group(1)
            if b not in _LIGHT or f not in _LIGHT:
                continue
            # 半透明底(浅染)不算实底, 和字同族是正常的
            if re.search(rf"var\(--{re.escape(b)}\)\s*/", body):
                continue
            for theme, values in THEMES:
                if values[b] == values[f]:
                    offenders.append(
                        f"{path.relative_to(FRONTEND)}: {selector} —— {theme}色下 "
                        f"background 与 color 都是 --{b}")
    assert not offenders, "底色和字色同值, 文字会隐形:\n" + "\n".join(offenders)


def test_R816_accent实底上的字不许用accent_text():
    offenders = []
    for path in FRONTEND.rglob("*.css"):
        for selector, body in _css_rules(path.read_text(encoding="utf-8")):
            if (re.search(r"(?:^|;)\s*background(?:-color)?\s*:[^;]*var\(--accent\)", body)
                    and re.search(r"(?:^|;)\s*color\s*:[^;]*var\(--accent-text\)", body)):
                offenders.append(f"{path.relative_to(FRONTEND)}: {selector}")
    assert not offenders, (
        "--accent-text 是「深底上的 accent 文字」, 和 --accent 同值, "
        "拿它当实底上的字色就是隐形。改用 --base(text-on-accent)或 --surface(SEG_ON):\n"
        + "\n".join(offenders))


def test_R816_tsx静态className里底色字色不许同值():
    """只查**字面量** className —— 带 ternary 的模板串会把两支拼在一起, 是误报;
    写死在静态类名里的那一份照样要查。"""
    offenders = []
    for path in FRONTEND.rglob("*.tsx"):
        src = path.read_text(encoding="utf-8")
        for match in re.finditer(r'className="([^"]*)"', src):
            tokens = [t for t in match.group(1).split() if ":" not in t and "/" not in t]
            bgs = [t[3:] for t in tokens if t.startswith("bg-") and t[3:] in BG_TW]
            fgs = [t[5:] for t in tokens if t.startswith("text-") and t[5:] in FG_TW]
            for b in bgs:
                for f in fgs:
                    for theme, values in THEMES:
                        if values[BG_TW[b]] == values[FG_TW[f]]:
                            line = src[:match.start()].count("\n") + 1
                            offenders.append(
                                f"{path.relative_to(FRONTEND)}:{line} bg-{b} + text-{f} ({theme}色)")
    assert not offenders, "底色与字色同值:\n" + "\n".join(sorted(set(offenders)))


def test_R816_白字不许压在亮底上():
    """`text-white` 只有底色够深时才能用: 暗色的 accent 是 #E4E4E4, 白字压上去 ≈ 隐形。

    市场环境页那三处 `bg-accent text-white`(概念/行业切换、保存并重算、应用)就是这么来的。
    """
    def is_light(value: str) -> bool:
        return float(value.split()[0]) > 0.8

    offenders = []
    for path in FRONTEND.rglob("*.tsx"):
        src = path.read_text(encoding="utf-8")
        for match in re.finditer(r'className="([^"]*)"', src):
            tokens = [t for t in match.group(1).split() if ":" not in t and "/" not in t]
            if "text-white" not in tokens:
                continue
            for token in tokens:
                name = token[3:] if token.startswith("bg-") else None
                if name not in BG_TW:
                    continue
                css_token = BG_TW[name]
                if css_token not in _LIGHT:
                    continue
                for theme, values in THEMES:
                    if is_light(values[css_token]):
                        line = src[:match.start()].count("\n") + 1
                        offenders.append(
                            f"{path.relative_to(FRONTEND)}:{line} bg-{name} + text-white ({theme}色底)")
    assert not offenders, (
        "白字压在亮底上, 那一套主题下几乎看不见 —— accent/foreground 实底改用 "
        "text-on-accent(或 text-surface):\n" + "\n".join(sorted(set(offenders))))
