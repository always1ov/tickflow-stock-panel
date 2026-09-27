"""[fork R554] 浏览器标签页: 图标改红、标题去掉英文。

用户截图标签页「[紫色图标] 牛来 · Quant Terminal」: 「改成红色, 和删掉英文」。
图标原来是紫(#5B21B6 / PNG 里 #8B5CF6), 也正是硬约束第 15 条禁的那种 —— 守卫只扫
src 下的 ts/tsx/css, public 里的图标和 index.html 漏在外面, 这里补上。
"""
from __future__ import annotations

from PIL import Image

from tests.frontend_source import FRONTEND
from tests.test_no_purple import purple_in_code

PUBLIC = FRONTEND / "public"
RED = (217, 45, 32)  # #D92D20 = --bull(亮色主题的红涨)


def test_R554_标题只有中文名():
    html = (FRONTEND / "index.html").read_text(encoding="utf-8")
    assert "<title>牛来</title>" in html
    assert "Quant Terminal" not in html


def test_R554_图标与入口页没有紫():
    for rel in ("public/favicon.svg", "public/manifest.webmanifest", "index.html"):
        text = (FRONTEND / rel).read_text(encoding="utf-8")
        assert not purple_in_code(text), f"{rel} 里又有紫: {purple_in_code(text)}"
    assert "#D92D20" in (PUBLIC / "favicon.svg").read_text(encoding="utf-8")


def test_R554_主屏图标是红的():
    for f in ("apple-touch-icon.png", "icon-192.png", "icon-512.png", "icon-maskable-512.png"):
        colors = {c[:3] for _, c in Image.open(PUBLIC / f).convert("RGBA").getcolors(1 << 20)}
        assert RED in colors, f"{f} 没有品牌红"
        assert (139, 92, 246) not in colors, f"{f} 还是紫的"
