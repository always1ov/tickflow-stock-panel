"""[fork R550] 弹窗点开 / 关闭时一闪 —— 两处成因, 各钉一道。

用户: 「弹窗点开和关闭会有一闪而过的闪屏的感觉」。逐帧采样(每个 rAF 读 computed opacity)抓到:
  ① framer-motion 原生动画跑完 → 撤掉之间漏一帧起始值: 入场遮罩 0.77 → 0 → 1, 退场淡到 0 又亮回 1;
  ② 个股弹窗外面包一层 `x && <StockPreviewDialog/>`, 一关就连根卸掉, 退场动画根本不跑。
"""
from __future__ import annotations

import re

from tests.frontend_source import SRC, code_of


def test_R550_入口装上WAAPI交接补帧():
    main = code_of("main.tsx")
    assert "installWaapiHandoff()" in main, "main.tsx 没装 WAAPI 交接补帧, 弹窗开关又会闪一帧"
    shim = code_of("lib/waapiHandoff.ts")
    assert "commitStyles()" in shim and "'finished'" in shim


def test_R550_个股弹窗不再被调用方连根卸掉():
    bad = []
    for p in SRC.rglob("*.tsx"):
        rel = p.relative_to(SRC).as_posix()
        if rel.startswith("__") or rel.endswith(".test.tsx"):
            continue
        code = code_of(rel)
        # `{cond && (<StockPreviewDialog` / `{cond && <StockPreviewDialog`
        if re.search(r"&&\s*\(?\s*<StockPreviewDialog\b", code):
            bad.append(rel)
    assert not bad, f"这些地方用 `x && <StockPreviewDialog/>` 挂弹窗, 关闭时退场动画不跑: {bad}"
