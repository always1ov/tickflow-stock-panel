"""[R791] 复盘档案瘦身: 列表 meta=1 只返档案摘要, 全文按 id 按需取。

用户: 「复盘部分需要出个方案大刀阔斧的改」→ 确认先做 P1+P2。
档案带只需要日期/情绪/摘要, 不该让首屏体积跟着正文一起膨胀(20 篇 ≈ 180KB+)。
默认列表行为保持不变 —— 契约只加不改, 其它调用方无感。
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.api import market_recap
from app.services import market_recap_reports

SAMPLE = [
    {
        "id": "mkr_2", "as_of": "2026-11-17", "focus": "",
        "content": "# 第二篇" + "x" * 500,
        "summary": "上+1.0% | 情绪 62", "emotion_score": 62, "emotion_label": "偏暖",
        "created_at": "2026-11-17T15:12:00",
    },
    {
        "id": "mkr_1", "as_of": "2026-11-14", "focus": "量能",
        "content": "# 第一篇",
        "summary": "上-0.4% | 情绪 47", "emotion_score": 47, "emotion_label": "震荡",
        "created_at": "2026-11-14T15:10:00",
    },
]


@pytest.fixture()
def reports(monkeypatch):
    monkeypatch.setattr(
        market_recap_reports._store, "list_reports", lambda: [dict(r) for r in SAMPLE],
    )
    return SAMPLE


def test_meta列表不带正文且字段齐全(reports):
    rows = market_recap.list_reports(None, meta=True)["reports"]
    assert [r["id"] for r in rows] == ["mkr_2", "mkr_1"], "档案带顺序应与默认列表一致(新→旧)"
    assert all("content" not in r for r in rows), "meta 列表又带上了正文"
    assert set(rows[0]) == set(market_recap_reports.META_FIELDS)


def test_默认列表保持旧行为(reports):
    rows = market_recap.list_reports(None)["reports"]
    assert rows[0]["content"].startswith("# 第二篇")


def test_单篇全文按id取(reports):
    assert market_recap.get_report(None, "mkr_1")["report"]["content"] == "# 第一篇"


def test_不存在的id返回404(reports):
    with pytest.raises(HTTPException) as ei:
        market_recap.get_report(None, "mkr_nope")
    assert ei.value.status_code == 404
