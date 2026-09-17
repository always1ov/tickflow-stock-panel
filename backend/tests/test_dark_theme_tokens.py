"""R371: light-only tokens must not leak into the dark palette.

Run from backend with:
    uv run pytest tests/test_dark_theme_tokens.py -q

This guard checks the real CSS source; browser/visual checks remain separate.
"""
from __future__ import annotations

import math
import re
from pathlib import Path

CSS = Path(__file__).resolve().parents[2] / "frontend" / "src" / "index.css"

# Timing curves are deliberately shared; every other theme token needs both modes.
SHARED = {"--ease-out-strong", "--ease-in-out-strong", "--ease-drawer"}


def _blocks(css: str) -> tuple[dict[str, str], dict[str, str]]:
    source = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    result = []
    for selector in (":root", "html.dark"):
        matches = re.findall(
            rf"(?m)^\s*{re.escape(selector)}\s*\{{([^{{}}]*)\}}", source
        )
        assert len(matches) == 1, f"Expected one {selector} palette block"
        pairs = re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", matches[0])
        tokens = {name: value.strip() for name, value in pairs}
        assert len(tokens) >= 50, f"Incomplete {selector} palette extraction"
        assert len(tokens) == len(pairs), f"Duplicate {selector} token"
        result.append(tokens)
    return result[0], result[1]


def _resolve(tokens: dict[str, str], name: str) -> tuple[float, float, float]:
    seen: set[str] = set()
    while True:
        assert name not in seen, f"Cyclic theme alias: {name}"
        seen.add(name)
        assert name in tokens, f"Missing theme token: {name}"
        value = tokens[name]
        alias = re.fullmatch(r"var\((--[\w-]+)\)", value)
        if not alias:
            parts = tuple(float(part) for part in value.split())
            assert len(parts) == 3 and all(math.isfinite(x) for x in parts)
            return parts[0], parts[1], parts[2]
        name = alias[1]


def _luminance(color: tuple[float, float, float]) -> float:
    lightness, chroma, hue = color
    a = chroma * math.cos(math.radians(hue))
    b = chroma * math.sin(math.radians(hue))
    ll = (lightness + 0.3963377774 * a + 0.2158037573 * b) ** 3
    mm = (lightness - 0.1055613458 * a - 0.0638541728 * b) ** 3
    ss = (lightness - 0.0894841775 * a - 1.2914855480 * b) ** 3
    rgb = (
        4.0767416621 * ll - 3.3077115913 * mm + 0.2309699292 * ss,
        -1.2684380046 * ll + 2.6097574011 * mm - 0.3413193965 * ss,
        -0.0041960863 * ll - 0.7034186147 * mm + 1.7076147010 * ss,
    )
    return sum(w * max(0.0, min(1.0, x)) for w, x in zip((0.2126, 0.7152, 0.0722), rgb))


def test_every_theme_token_has_an_explicit_dark_definition():
    light, dark = _blocks(CSS.read_text(encoding="utf-8"))
    assert set(light) - SHARED == set(dark), (
        f"Missing dark tokens: {sorted(set(light) - SHARED - set(dark))}; "
        f"dark-only tokens: {sorted(set(dark) - set(light))}"
    )


def test_dark_surfaces_do_not_inherit_light_backgrounds():
    light, dark = _blocks(CSS.read_text(encoding="utf-8"))
    effective = light | dark
    for name in ("--sidebar", "--accent-soft"):
        assert _resolve(effective, name)[0] < 0.5, f"Light surface leaked: {name}"
    assert _resolve(effective, "--border-input")[0] < 0.7
    assert _resolve(effective, "--accent-hover") != _resolve(light, "--accent-hover")


def test_dark_sidebar_text_is_readable():
    light, dark = _blocks(CSS.read_text(encoding="utf-8"))
    effective = light | dark
    background = _luminance(_resolve(effective, "--sidebar"))
    for name in ("--fg-primary", "--fg-secondary", "--fg-muted"):
        foreground = _luminance(_resolve(effective, name))
        contrast = (max(background, foreground) + 0.05) / (min(background, foreground) + 0.05)
        assert contrast >= 4.5, f"{name} / sidebar contrast = {contrast:.2f}:1"
