"""[R322] toast 分级 —— 失败要人动手, 成功只是回执; 同一句不叠; 最多四张; 退场淡出。

调用方式一个字没变(`toast(msg)` / `toast(msg, 'success')`), 改的全在容器 `Toast.tsx`。
这组守卫钉的是那几条规矩本身, 全部走 `code_of`(剥掉注释再断言)。
"""
from __future__ import annotations

import re

from tests.frontend_source import code_of

TOAST = "components/Toast.tsx"


def _ms() -> dict[str, int]:
    code = code_of(TOAST)
    m = re.search(r"TOAST_MS[^=]*=\s*\{([^}]*)\}", code)
    assert m, "找不到 TOAST_MS"
    return {k: int(v) for k, v in re.findall(r"(\w+):\s*(\d+)", m.group(1))}


def test_R322_调用方式没变_老调用点一个不用改():
    code = code_of(TOAST)
    assert "function toast(msg: string, kind: ToastKind = 'error')" in code, \
        "第二个参数默认仍是 'error' —— 158 处 `toast(msg)` 报的都是错"
    assert "export { toast }" in code
    assert "export function ToastContainer" in code
    assert "<ToastContainer />" in code_of("components/Layout.tsx")


def test_R322_三档时长_失败最久_成功最短():
    ms = _ms()
    assert set(ms) == {"error", "success", "info"}
    assert ms["error"] > ms["info"] > ms["success"]
    assert ms["error"] >= 5000, "失败要读、要决定做什么, 不能一闪就走"
    assert ms["success"] <= 2500, "成功只是回执, 停久了就是噪音"


def test_R322_同一句话不叠_只重置计时():
    code = code_of(TOAST)
    fn = code[code.index("function toast("):code.index("export { toast }")]
    assert "x.msg === msg && x.kind === kind && !x.leaving" in fn
    assert "if (dup) { _arm(dup); return }" in fn


def test_R322_最多四张_超出挤掉最旧的():
    code = code_of(TOAST)
    assert re.search(r"TOAST_MAX\s*=\s*4\b", code)
    fn = code[code.index("function toast("):code.index("export { toast }")]
    assert "live.length > TOAST_MAX" in fn
    assert "dismiss(live[0].id)" in fn, "挤掉的必须是最旧那张, 不是刚来的"


def test_R322_退场先淡出再摘_不硬切():
    code = code_of(TOAST)
    fn = code[code.index("export function dismiss("):code.index("function toast(")]
    assert "item.leaving = true" in fn
    assert "_queue = _queue.filter(x => x.id !== id)" in fn
    assert "EXIT_MS" in fn, "过渡走完再摘 —— 直接摘就是硬切"
    card = code[code.index("function ToastCard"):code.index("export function ToastContainer")]
    assert "const shown = mounted && !t.leaving" in card


def test_R322_走_transition_不走_keyframes_且退场快于入场():
    code = code_of(TOAST)
    card = code[code.index("function ToastCard"):code.index("export function ToastContainer")]
    assert "transition-[opacity,transform]" in card
    assert "animate-in" not in card, "toast 会被连着触发, keyframes 每次从零开始"
    line = next(l for l in card.splitlines() if "shown ?" in l)
    assert "duration-expand" in line.split(":")[0], "入场 200ms"
    assert "duration-hover" in line.split(":")[1], "退场 150ms —— 比入场快"


def test_R322_失败才有关闭钮与_alert_语义_成功没有():
    code = code_of(TOAST)
    card = code[code.index("function ToastCard"):code.index("export function ToastContainer")]
    assert "role={t.kind === 'error' ? 'alert' : undefined}" in card
    btn = card[card.index("<button"):]
    guard = card[:card.index("<button")]
    assert guard.rstrip().endswith("{t.kind === 'error' && ("), "关闭钮只给失败那档"
    assert 'aria-label="关闭提示"' in btn
    assert "onClick={() => dismiss(t.id)}" in card, "整张卡都能点掉"
