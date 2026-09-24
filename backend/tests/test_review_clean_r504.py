"""[fork R504] 复盘页回到作者的样子 —— 撤 AI 打板复盘(含跷跷板)、复盘三模式, RPS 入口放回原处。

用户:「切断 ai 打板复盘, 后续我做复盘部分再提醒我, 保持干净和上游一致准备整改这个页面」,
范围问过两次都选了推荐: 「复盘页功能回到上游」「删代码, 留存档」。

钉三件事: 撤干净(前后端都没有残留入口)、存档没被当成孤儿、提醒真的留下了。
"""
from __future__ import annotations

from pathlib import Path

from tests.frontend_source import code_of

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "backend" / "app"
SRC = ROOT / "frontend" / "src"
REMINDER = ROOT / ".scratch" / "review-page-rework" / "issues" / "01-ladder-ai-and-friends.md"


def test_R504_复盘页页头只剩作者那一排():
    r = code_of("pages/Review.tsx")
    for gone in ("LadderAiReview", "RpsRotationDialog", "recapMode", "MODE_LABEL", "连读昨日", "板块RPS轮动"):
        assert gone not in r, f"复盘页还留着 {gone}"
    for kept in ("刷新", "定时", "生成复盘"):
        assert kept in r


def test_R504_前端组件与接口撤干净():
    assert not (SRC / "components" / "LadderAiReview.tsx").exists()
    assert not (SRC / "components" / "regime" / "SeesawPanel.tsx").exists()
    api = code_of("lib/api.ts")
    for gone in ("ladderAiReview", "ladderAiReports", "ladderAiDeleteReport", "regimeSeesaw", "SeesawResult",
                 "'continuity'"):
        assert gone not in api, f"api.ts 还留着 {gone}"
    assert "ladderAiReports" not in code_of("lib/queryKeys.ts")
    assert "regimeSeesaw" not in code_of("lib/queryKeys.ts")
    assert "mode" not in code_of("lib/reviewStore.ts").split("startReviewGeneration(")[1].split("{")[0]


def test_R504_后端接口与服务撤干净():
    assert not (APP / "services" / "seesaw.py").exists()
    assert not (APP / "services" / "seesaw_store.py").exists()
    screener = (APP / "api" / "screener.py").read_text(encoding="utf-8")
    assert "/ladder-ai" not in screener and "_ladder_reports" not in screener
    assert "/seesaw" not in (APP / "api" / "regime.py").read_text(encoding="utf-8")
    recap_api = (APP / "api" / "market_recap.py").read_text(encoding="utf-8")
    recap_svc = (APP / "services" / "market_recap.py").read_text(encoding="utf-8")
    assert "continuity" not in recap_api and "continuity" not in recap_svc
    assert "_week_digest_section" not in recap_svc and "_prev_recap_section" not in recap_svc


def test_R504_存档没删_体检仍认得它们():
    """删的是代码不是数据 —— 登记要留着, 否则体检会把两份存档当成来路不明的孤儿。"""
    from app.services import data_doctor as dd

    known = {s.rel: s for s in dd.STORES}
    for rel in ("user_data/ladder_ai_reports.json", "user_data/seesaw_history.json"):
        assert rel in known, f"{rel} 的登记被一起删了"
        assert "R504" in known[rel].note, "没说明这份存档现在没人读写"


def test_R504_RPS入口回到行业概念两页_弹窗不再自带维度切换():
    for page, kind in (("pages/IndustryAnalysis.tsx", ' kind="industry"'), ("pages/ConceptAnalysis.tsx", "")):
        src = code_of(page)
        assert "onClick={() => setShowRps(true)}" in src and "涨幅RPS轮动分析" in src, f"{page} 没有 RPS 入口"
        assert f"<RpsRotationDialog onClose={{() => setShowRps(false)}}{kind} />" in src
    dlg = code_of("components/RpsRotationDialog.tsx")
    assert "allowKindSwitch" not in dlg and "setKind" not in dlg


def test_R504_整改时的提醒留下了():
    assert REMINDER.exists(), "用户要求「后续我做复盘部分再提醒我」, 提醒文件没了"
    text = REMINDER.read_text(encoding="utf-8")
    for item in ("AI 打板复盘", "板块跷跷板", "复盘三模式", "RPS 轮动", "ladder_ai_reports.json", "seesaw_history.json"):
        assert item in text
    # 动复盘页的人一打开文件就能看见这条提醒(它写在注释里, 所以读原文, 不走剥注释的 code_of)
    raw = (SRC / "pages" / "Review.tsx").read_text(encoding="utf-8")
    assert ".scratch/review-page-rework/issues/01-ladder-ai-and-friends.md" in raw
