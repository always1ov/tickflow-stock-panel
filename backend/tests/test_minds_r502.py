"""[fork R502] Minds ① —— 消息面原位改名 Minds, 悬浮 AI 助手搬进「对话」一栏。

用户: 「系统里面悬浮的那个 ai 助手改造复刻成这三张图 minds 的功能, 也做成一个菜单选项在左侧」,
几轮问答全部「按推荐」: 悬浮按钮去掉、对话成为第四栏且原样搬过去; 消息面并进来当「笔记」,
菜单原位改名, 旧地址重定向; 四栏叫 笔记 / 洞见 / 交易计划 / 对话。

这里钉的是接线与边界, 不钉版式细节:
  · 旧地址、旧菜单偏好都不能断(书签、排好的顺序、藏掉的项);
  · 核心页面不 import 扩展目录 —— 对话走 `minds.chat` 插槽, 删扩展仍是整体卸载;
  · 悬浮三件套真的撤干净了, 没有一个只是「不挂载」的孤儿文件留着骗人。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from app.services import preferences
from tests.frontend_source import code_of

ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = ROOT / "frontend" / "src"

MINDS = "pages/Minds.tsx"
ASSISTANT = "custom/assistant"


# ── 菜单偏好: 原位改名, 位置与显隐都跟过去 ─────────────────────────────

@pytest.fixture()
def prefs_file(tmp_path, monkeypatch):
    path = tmp_path / "preferences.json"
    monkeypatch.setattr(preferences, "_path", lambda: path)
    preferences._invalidate_cache()
    yield path
    preferences._invalidate_cache()


def test_R502_存过的菜单顺序里旧路径换成新路径_位置不变(prefs_file):
    prefs_file.write_text(json.dumps({
        "nav_order": ["/watchlist", "/review", "/usage-notes", "/indices"],
    }), encoding="utf-8")
    assert preferences.get_nav_order() == ["/watchlist", "/review", "/minds", "/indices"]


def test_R502_藏掉的消息面改名后仍是藏着的(prefs_file):
    prefs_file.write_text(json.dumps({"nav_hidden": ["/usage-notes", "/data"]}), encoding="utf-8")
    assert preferences.get_nav_hidden() == ["/minds", "/data"]


def test_R502_新旧两个路径都在时只留先出现的那一个(prefs_file):
    prefs_file.write_text(json.dumps({
        "nav_order": ["/minds", "/review", "/usage-notes"],
        "nav_hidden": ["/usage-notes", "/minds"],
    }), encoding="utf-8")
    assert preferences.get_nav_order() == ["/minds", "/review"]
    assert preferences.get_nav_hidden() == ["/minds"]


def test_R502_只在读时换_不回写文件(prefs_file):
    raw = {"nav_order": ["/usage-notes"], "nav_hidden": []}
    prefs_file.write_text(json.dumps(raw), encoding="utf-8")
    preferences.get_nav_order()
    assert json.loads(prefs_file.read_text(encoding="utf-8")) == raw


def test_R502_接口读的就是换过名的那一份():
    """菜单排序与显隐两处都只走这两个函数 —— 有人绕过去直接 load()["nav_order"] 就漏了。"""
    text = (ROOT / "backend" / "app" / "api" / "settings.py").read_text(encoding="utf-8")
    assert '"nav_order": preferences.get_nav_order()' in text
    assert '"nav_hidden": preferences.get_nav_hidden()' in text


# ── 路由与菜单 ─────────────────────────────────────────────────────

def test_R502_旧地址重定向到笔记一栏():
    r = code_of("router.tsx")
    assert "{ path: 'minds', element: <Minds /> }" in r
    assert "{ path: 'usage-notes', element: <Navigate to=\"/minds?tab=notes\" replace /> }" in r
    assert "'/minds'," in r and "'/usage-notes'," in r, "两条路径都得登记为核心路由, 扩展不能占用"
    assert "<UsageNotes" not in r


def _paths(src: str, key: str) -> list[str]:
    return re.findall(rf"\{{ {key}: '([^']+)'", src)


def test_R502_侧栏原位改名():
    nav = code_of("components/Layout.tsx")
    i0 = nav.index("const nav = [")
    nav = nav[i0:nav.index("] as const", i0)]
    paths = _paths(nav, "to")
    assert "/usage-notes" not in paths, "侧栏还挂着旧路径"
    i = paths.index("/minds")
    assert paths[i - 1] == "/review" and paths[i + 1] == "/indices", "Minds 没在消息面原来的位置"
    assert "{ to: '/minds', label: 'Minds', icon: Brain }" in nav


def test_R502_菜单设置的默认顺序与侧栏同一处改名():
    ms = code_of("pages/settings/MenuSettings.tsx")
    ids = _paths(ms, "id")
    assert "/usage-notes" not in ids
    i = ids.index("/minds")
    assert ids[i + 1] == "/financials", "默认顺序里 Minds 挪了位置"
    assert "{ id: '/minds', label: 'Minds', type: 'builtin', visible: true }" in ms


# ── Minds 页 ──────────────────────────────────────────────────────

def test_R502_四栏的名字与顺序():
    m = code_of(MINDS)
    tabs = re.findall(r"^\s+(\w+): \{ title: '([^']+)'", m, re.M)
    assert tabs == [("notes", "笔记"), ("insights", "洞见"), ("plans", "交易计划"), ("chat", "对话")]
    assert "searchParams.get('tab')" in m and "setSearchParams(next, { replace: true })" in m
    assert ": 'notes'" in m, "没带 ?tab= 时该落在笔记"


def test_R502_核心页面不import扩展目录_对话走插槽():
    m = code_of(MINDS)
    assert not re.search(r"""from ['"][^'"]*custom/""", m), "核心页面 import 了扩展目录"
    assert '<ExtensionSlot name="minds.chat" context={{}} />' in m
    assert "getFrontendSlotRegistrations('minds.chat').length === 0" in m, "扩展删掉时对话栏得有交代"
    types = code_of("extensions/types.ts")
    assert "'minds.chat': Record<string, never>" in types


def test_R502_笔记栏就是原来的消息面正文_不带自己的页头():
    notes = code_of("pages/UsageNotes.tsx")
    assert "export function NotesPanel()" in notes
    assert "PageHeader" not in notes and "export function UsageNotes" not in notes
    assert "import { NotesPanel } from './UsageNotes'" in code_of(MINDS)


def test_R502_切栏不加动画():
    m = code_of(MINDS)
    for x in ("motion", "AnimatePresence", "transition-all", "animate-"):
        assert x not in m, f"切栏是高频操作, 不该有 {x}"


def test_R502_插槽写进二开文档():
    doc = (ROOT / "docs" / "secondary-development.md").read_text(encoding="utf-8")
    assert "`minds.chat`" in doc and "minds.chat\n```" in doc


# ── 悬浮助手搬家 ──────────────────────────────────────────────────

def test_R502_悬浮三件套撤干净():
    ui = FRONTEND_SRC / ASSISTANT / "ui"
    for gone in ("AssistantFloatingButton.tsx", "AiConfigEntry.tsx", "AssistantDrawer.clampWidth.test.ts"):
        assert not (ui / gone).exists(), f"{gone} 还在 —— 不挂载的孤儿文件会骗下一个读代码的人"
    launcher = code_of(f"{ASSISTANT}/AssistantLauncher.tsx")
    assert "return null" in launcher, "宿主只剩快捷键与页面上下文, 不该再渲染东西"
    store = code_of(f"{ASSISTANT}/store.ts")
    for x in ("toggleAssistant", "openAssistant", "closeAssistant", "open: boolean"):
        assert x not in store, f"没有开关可言了, {x} 还留着"


def test_R502_对话面板嵌在栏里_不再是浮层():
    panel = code_of(f"{ASSISTANT}/ui/AssistantDrawer.tsx")
    assert "export function AssistantPanel()" in panel
    for x in ("createPortal", "motion.aside", "fixed inset-y-0", "clampWidth", "cursor-col-resize", "closeAssistant"):
        assert x not in panel, f"浮层的残留: {x}"
    assert "transition-all" not in panel
    ext = code_of(f"{ASSISTANT}/extension.tsx")
    assert "name: 'minds.chat'" in ext and "component: AssistantPanel" in ext


def test_R502_快捷键从开关抽屉改成跳到对话栏():
    launcher = code_of(f"{ASSISTANT}/AssistantLauncher.tsx")
    assert "export const CHAT_PATH = '/minds?tab=chat'" in launcher
    assert "navigate(CHAT_PATH, { replace: pathname === '/minds' })" in launcher
    assert "Escape" not in launcher, "没有要关的东西了"


def test_R502_只在有鼠标的设备上自动聚焦输入框():
    """手机上一聚焦就弹键盘, 半屏消息被顶没。"""
    panel = code_of(f"{ASSISTANT}/ui/AssistantDrawer.tsx")
    assert "matchMedia?.('(pointer: fine)').matches" in panel
    assert "}, [locationKey])" in panel, "已在对话栏时再按 Ctrl+K 不会重新聚焦"
