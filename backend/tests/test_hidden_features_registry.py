"""[fork R507] 隐藏与撤下的功能登记簿(docs/hidden-features.md)不许说假话。

用户:「要登记好哪些功能等于隐藏了以后说不定用得上」。登记簿本身是给人读的散文, 钉不住 ——
能钉的是它**声称的事实**: 「一、隐藏」里说还在的接口与字段真的还在; 说留在磁盘上的存档仍登记在
数据体检里(否则体检会把它当孤儿, 劝人删掉); 写出来的提交号真的存在(找回的路是通的)。

哪条红了, 通常不是测试错了, 是有人把「隐藏」那条的后端也删了 —— 把它挪进「二、撤下」并写上提交号。
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "docs" / "hidden-features.md"

# 「一、隐藏」逐条的锚点: (登记簿里的名字, 文件, 必须还在的那一句)
STILL_THERE = [
    ("情绪周期", "backend/app/api/regime.py", '@router.get("/phases")'),
    ("情绪周期", "backend/app/api/regime.py", '@router.get("/phase/live")'),
    ("情绪周期", "backend/app/api/regime.py", "regime_builder.refresh_phase_labels(data_dir)"),
    ("主线排行", "backend/app/api/regime.py", '@router.get("/mainline")'),
    ("主线排行", "backend/app/api/regime.py", '@router.post("/mainline/recompute")'),
    ("状态分布饼图", "backend/app/api/regime.py", '@router.get("/states")'),
    ("有信号但没做成", "backend/app/services/flip_portfolio.py", "skipped: list[dict] = []"),
    ("有信号但没做成", "frontend/src/lib/api.ts", "skipped: FlipSkipped[]"),
    ("今日总览没人显示的几块", "backend/app/api/today.py", '"actions": actions,'),
    ("今日总览没人显示的几块", "backend/app/api/today.py", '"holdings": holdings,'),
    ("今日总览没人显示的几块", "backend/app/api/today.py", '"meso": meso,'),
    ("今日总览没人显示的几块", "backend/app/api/today.py", '"position_hint": {'),
    ("今日总览没人显示的几块", "backend/app/api/today.py", '"portfolio": portfolio,'),
    ("AI 导读 · 优选", "backend/app/api/today.py", '@router.post("/ai")'),
    ("AI 导读 · 优选", "backend/app/api/today.py", '@router.get("/ai/track-record")'),
    ("批次登记页", "frontend/src/router.tsx", "{ path: 'lots-registry', element: <Lots /> }"),
    ("开发者工具", "frontend/src/router.tsx", "{ path: 'dev', element: <Dev /> }"),
]

# 登记簿说「留在磁盘上」的存档 —— 必须仍在数据体检的名单里
ARCHIVES = [
    "user_data/today_ai.json", "user_data/ai_pick_ledger.json", "user_data/ladder_ai_reports.json",
    "user_data/seesaw_history.json", "user_data/signals.json", "user_data/paper_traders.json",
    "user_data/lots",
]


def _doc() -> str:
    return DOC.read_text(encoding="utf-8")


def _section(title: str) -> str:
    doc = _doc()
    a = doc.index(f"## {title}")
    b = doc.find("\n## ", a + 1)
    return doc[a:b if b > 0 else None]


@pytest.mark.parametrize("name,rel,anchor", STILL_THERE, ids=[f"{n}:{a[:30]}" for n, _, a in STILL_THERE])
def test_R507_隐藏的功能后端真的还在(name, rel, anchor):
    assert name in _section("一、隐藏"), f"锚点对应的「{name}」不在登记簿「一、隐藏」里"
    text = (ROOT / rel).read_text(encoding="utf-8")
    assert anchor in text, (
        f"登记簿说「{name}」的后端还在, 但 {rel} 里已经没有 {anchor!r} —— "
        "把这一条挪进「二、撤下」并写上提交号")


def test_R507_留在磁盘上的存档仍在数据体检名单里():
    from app.services import data_doctor as dd

    known = {s.rel for s in dd.STORES}
    doc = _doc()
    for rel in ARCHIVES:
        assert rel in doc, f"{rel} 没写进登记簿"
        assert rel in known, f"{rel} 不在数据体检名单里 —— 体检会把它当孤儿劝人删掉"


def test_R507_写出来的提交号都找得到():
    try:
        subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--git-dir"], check=True,
                       capture_output=True)
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("不在 git 仓库里(比如镜像内), 查不了提交号")
    hashes = set(re.findall(r"git (?:show|revert) ([0-9a-f]{8})", _doc()))
    assert len(hashes) >= 10, f"只抓到 {len(hashes)} 个提交号, 正则或登记簿格式变了"
    shallow = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--is-shallow-repository"],
                             capture_output=True, text=True).stdout.strip() == "true"
    missing = [h for h in sorted(hashes)
               if subprocess.run(["git", "-C", str(ROOT), "cat-file", "-e", f"{h}^{{commit}}"],
                                 capture_output=True).returncode != 0]
    if missing and shallow:
        pytest.skip(f"浅克隆里没有 {missing}(完整历史里才查得到)")
    assert not missing, f"登记簿里这些提交号找不到, 找回的路是断的: {missing}"


def test_R507_AGENTS里有这条规矩():
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert "docs/hidden-features.md" in agents, "AGENTS.md 没指向登记簿 —— 下一个 AI 撤功能时不会知道要登记"
