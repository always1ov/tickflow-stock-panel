"""[R268] 前端脱敏 —— 界面上不许出现上游作者, 也不许留下找到他的入口。

用户: 「前端页面脱敏掉作者的信息, 包括能找的作者的任何入口」「我打算给别人用, 所以
要隐藏不暴露信息」。这台机器是要交到别人手上的, 界面就是别人能看到的全部。

**这条最容易在同步上游时破功。** 上游作者会继续往他自己的页面里加指向自己仓库的
链接与文档入口, 每次 merge 都可能带回来一批; 靠人肉复查一定会漏。所以扫的是**整个
前端源码目录**而不是几个已知文件 —— 新加的文件、新 merge 进来的文件, 一样跑不掉。

扫的是源码而不是构建产物, 因为 `dist/` 不进仓库、每次构建重新生成; 源码干净, 打出来
的页面就干净。
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
SRC = FRONTEND / "src"

#: 上游作者的身份标识。出现在前端任何位置都算破功。
AUTHOR_MARKS = {
    "shy3130": "上游作者的 GitHub 用户名",
    "415333856": "上游作者的邮箱前缀",
    "tickflow-stock-panel": "上游仓库名 —— 拿它一搜就能找到人",
}

#: 上游作者的 TickFlow 推荐返佣码。
#:
#: 这一条和其他几条不同: 它不只是"能找到作者", 而是**别人在这台机器上注册就把佣金
#: 记到他名下**。注册入口本身要留(TickFlow 是这套系统唯一的数据源), 去掉的是 ref。
REFERRAL_CODE = "V3KDKGXPEA"

#: 会被渲染出来的文件类型。`.md` 不在其中 —— 仓库里的文档不是界面。
UI_SUFFIXES = {".ts", ".tsx", ".html", ".css", ".svg", ".json"}


def _ui_files() -> list[Path]:
    out = [p for p in SRC.rglob("*") if p.is_file() and p.suffix in UI_SUFFIXES]
    for extra in ("index.html", "public"):
        target = FRONTEND / extra
        if target.is_file():
            out.append(target)
        elif target.is_dir():
            out.extend(p for p in target.rglob("*") if p.is_file() and p.suffix in UI_SUFFIXES)
    return out


@pytest.fixture(scope="module")
def ui_files() -> list[Path]:
    files = _ui_files()
    if not files:
        pytest.skip("拿不到前端源码(只跑后端时正常)")
    return files


@pytest.mark.parametrize("mark", sorted(AUTHOR_MARKS))
def test_R268_前端不含上游作者的身份标识(ui_files, mark):
    """**注释里也不许留** —— 源码会被打进 sourcemap, 也会被人直接翻。"""
    hits = [f"{p.relative_to(FRONTEND)}" for p in ui_files
            if mark in p.read_text(encoding="utf-8", errors="ignore")]
    assert not hits, f"{AUTHOR_MARKS[mark]}「{mark}」还留在: {', '.join(hits)}"


def test_R268_不留上游作者的推荐返佣码(ui_files):
    """别人用这台机器注册, 佣金不该记到别人名下 —— 注册入口留着, ref 去掉。"""
    hits = [f"{p.relative_to(FRONTEND)}" for p in ui_files
            if REFERRAL_CODE in p.read_text(encoding="utf-8", errors="ignore")]
    assert not hits, f"推荐码还留在: {', '.join(hits)}"


def test_R268_注册入口本身还在(ui_files):
    """反向也要守: 一刀切把 tickflow.org 全删掉, 别人就不知道去哪拿 Key 了。"""
    joined = "\n".join(p.read_text(encoding="utf-8", errors="ignore") for p in ui_files)
    assert "tickflow.org/auth/register" in joined, "注册入口被误删了"


_GH_RE = re.compile(r"https?://(?:www\.)?(?:github|gitee|gitcode|gitlab)\.com/[\w.-]+/[\w.-]+")


def test_R268_界面里没有指向任何代码仓库的链接(ui_files):
    """这类链接是最直接的入口: 点进去就是作者的仓库、issues、releases。

    连"某个第三方仓库"也一并禁掉 —— 这一页上本来就没有该出现的代码托管链接, 留一个
    白名单只会给下次 merge 开口子。
    """
    hits: list[str] = []
    for p in ui_files:
        for m in _GH_RE.finditer(p.read_text(encoding="utf-8", errors="ignore")):
            hits.append(f"{p.relative_to(FRONTEND)} → {m.group(0)}")
    assert not hits, "界面里还有代码仓库链接:\n  " + "\n  ".join(hits)


def test_R268_不再自称开源项目(ui_files):
    """「个人开源项目」「基于 MIT 协议开源」是一句明确的"去搜一下"的提示 ——
    对方顺着项目名一搜就到作者那里, 等于前面几条全白做。"""
    banned = ("开源项目", "MIT 协议", "MIT License", "开源许可")
    hits = []
    for p in ui_files:
        text = p.read_text(encoding="utf-8", errors="ignore")
        hits.extend(f"{p.relative_to(FRONTEND)} → {w}" for w in banned if w in text)
    assert not hits, "界面里还写着开源来历:\n  " + "\n  ".join(hits)


def test_R268_删链接没留下断头文案(ui_files):
    """只删 <a> 不改文案, 就会留下「点上方链接」「见下方文档」这种指向空气的句子 ——
    比留着链接更糟: 用户照做却什么也找不到。"""
    dangling = ("点上方链接", "点击上方链接", "见上方链接", "详细配置说明见",
                "前往 Issues", "前往 GitHub")
    hits = []
    for p in ui_files:
        text = p.read_text(encoding="utf-8", errors="ignore")
        hits.extend(f"{p.relative_to(FRONTEND)} → {w}" for w in dangling if w in text)
    assert not hits, "删了链接却留下指向空气的文案:\n  " + "\n  ".join(hits)
