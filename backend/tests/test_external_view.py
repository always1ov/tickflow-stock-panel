"""[fork R117] 外部网页 AI 格式化: 原文清洗 / 契约归一 / 缓存命中。"""
from __future__ import annotations

import asyncio
import json

import pytest

from app.config import settings
from app.services import external_view as ev


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    yield


# ------------------------------------------------------------- 原文清洗


def test_clean_source_strips_scripts_styles_and_attributes():
    html = (
        '<html><head><style>.a{color:red}</style>'
        '<script>var x = 1; document.write("噪音")</script></head>'
        '<body><!-- 注释 --><table class="t" style="x"><tr><td>600519</td><td>2.31</td></tr></table></body></html>'
    )
    out = ev.clean_source(html, "text/html")
    assert "噪音" not in out and "color:red" not in out and "注释" not in out
    assert 'class="t"' not in out and "<table>" in out   # 标签骨架留着, 属性扔掉
    assert "600519" in out and "2.31" in out


def test_clean_source_keeps_json_structure():
    out = ev.clean_source('{"a":[1,2],"b":"x"}', "application/json")
    assert json.loads(out) == {"a": [1, 2], "b": "x"}


def test_clean_source_truncates_with_marker():
    out = ev.clean_source("x" * 500, "text/plain", limit=100)
    assert out.startswith("x" * 100) and "已截断" in out


def test_clean_source_empty():
    assert ev.clean_source("   ", "text/html") == ""


def test_build_messages_puts_hint_first():
    msgs = ev.build_messages("原文", "https://e.com/", "只要涨幅榜前 20")
    assert msgs[0]["role"] == "system" and "只输出 JSON" in msgs[0]["content"]
    assert msgs[1]["content"].index("只要涨幅榜前 20") < msgs[1]["content"].index("原文")


# ------------------------------------------------------------- 契约归一


def test_normalize_full_spec():
    spec = ev.normalize_spec({
        "title": "榜单", "updated_at": "2026-09-01",
        "stats": [{"label": "多头", "value": 128, "tone": "up"}],
        "sections": [{
            "title": "明细",
            "columns": [{"key": "symbol", "label": "代码"},
                        {"key": "pct", "label": "涨幅", "tone": "delta", "unit": "%"}],
            "rows": [{"symbol": "600519", "pct": 2.31}],
        }],
        "notes": ["来源: x"],
    })
    assert spec["title"] == "榜单" and spec["updated_at"] == "2026-09-01"
    assert spec["stats"][0] == {"label": "多头", "value": "128", "hint": None, "tone": "up"}
    sec = spec["sections"][0]
    assert sec["columns"][1] == {"key": "pct", "label": "涨幅", "align": "right", "tone": "delta", "unit": "%"}
    assert sec["rows"] == [{"symbol": "600519", "pct": 2.31}]
    assert spec["notes"] == ["来源: x"]


def test_normalize_accepts_top_level_rows():
    spec = ev.normalize_spec({"rows": [{"a": 1}]})
    assert spec["sections"][0]["rows"] == [{"a": 1}]


def test_normalize_accepts_bare_list():
    spec = ev.normalize_spec([{"a": 1}, {"a": 2}])
    assert len(spec["sections"][0]["rows"]) == 2


def test_normalize_infers_columns_when_missing():
    spec = ev.normalize_spec({"rows": [{"symbol": "600519", "pct": 2.31}]})
    cols = spec["sections"][0]["columns"]
    assert [c["key"] for c in cols] == ["symbol", "pct"]
    assert cols[0]["align"] == "left" and cols[1]["align"] == "right"  # 数值列右对齐


def test_normalize_drops_bad_tone_and_align():
    spec = ev.normalize_spec({
        "rows": [{"a": 1}],
        "columns": [{"key": "a", "tone": "彩虹色", "align": "斜的"}],
    })
    col = spec["sections"][0]["columns"][0]
    assert col["tone"] == "plain" and col["align"] in {"left", "right"}


def test_normalize_caps_rows_and_sections():
    spec = ev.normalize_spec({
        "sections": [{"rows": [{"i": i} for i in range(ev.MAX_ROWS + 50)]}] * (ev.MAX_SECTIONS + 3),
    })
    assert len(spec["sections"]) == ev.MAX_SECTIONS
    assert len(spec["sections"][0]["rows"]) == ev.MAX_ROWS


def test_normalize_rejects_empty_payload():
    with pytest.raises(ValueError, match="没有可显示"):
        ev.normalize_spec({"title": "只有标题"})
    with pytest.raises(ValueError, match="没有返回 JSON"):
        ev.normalize_spec("一句话")


def test_normalize_notes_only_is_valid():
    """AI 判定"这页没有可结构化数据"时只回 notes —— 这是合法结果, 不该报错。"""
    spec = ev.normalize_spec({"title": "登录页", "notes": ["抓到的是登录页, 没有数据"]})
    assert spec["sections"] == [] and spec["notes"]


# ------------------------------------------------------------- 缓存与编排


def _fake_fetch(text, ctype="application/json"):
    def _f(url, force=False):
        return {"ok": True, "status": 200, "url": url, "content_type": ctype,
                "bytes": len(text), "text": text, "fetched_at": 1.0, "cached": False}
    return _f


def test_build_view_calls_ai_once_then_hits_cache(monkeypatch):
    calls = {"n": 0}

    async def fake_ai(messages, **kw):
        calls["n"] += 1
        return '{"rows": [{"a": 1}]}'

    monkeypatch.setattr(ev, "MAX_SOURCE_CHARS", 500)
    import app.services.external_fetch as ef
    import app.services.ai_provider as ap
    monkeypatch.setattr(ef, "fetch", _fake_fetch('{"a":1}'))
    monkeypatch.setattr(ap, "generate_ai_text", fake_ai)
    monkeypatch.setattr(ap, "ai_configured", lambda *a, **k: True)
    monkeypatch.setattr(ap, "last_served_profile_name", lambda: "档位A")

    first = asyncio.run(ev.build_view("https://e.com/", "看涨幅"))
    assert first["from_cache"] is False and first["model"] == "档位A"
    assert first["spec"]["sections"][0]["rows"] == [{"a": 1}]

    second = asyncio.run(ev.build_view("https://e.com/", "看涨幅"))
    assert second["from_cache"] is True and calls["n"] == 1

    # 换了提示词 = 换了缓存键, 要重新问 AI
    asyncio.run(ev.build_view("https://e.com/", "换个问法"))
    assert calls["n"] == 2

    # force 强制重来
    asyncio.run(ev.build_view("https://e.com/", "看涨幅", force=True))
    assert calls["n"] == 3


def test_build_view_retries_once_on_unparsable_output(monkeypatch):
    outs = ["这不是 JSON, 我思考一下…", '{"rows": [{"a": 1}]}']

    async def fake_ai(messages, **kw):
        return outs.pop(0)

    import app.services.external_fetch as ef
    import app.services.ai_provider as ap
    monkeypatch.setattr(ef, "fetch", _fake_fetch('{"a":1}'))
    monkeypatch.setattr(ap, "generate_ai_text", fake_ai)
    monkeypatch.setattr(ap, "ai_configured", lambda *a, **k: True)
    monkeypatch.setattr(ap, "last_served_profile_name", lambda: "")

    got = asyncio.run(ev.build_view("https://e.com/"))
    assert got["spec"]["sections"][0]["rows"] == [{"a": 1}] and not outs


def test_build_view_requires_ai_configured(monkeypatch):
    import app.services.external_fetch as ef
    import app.services.ai_provider as ap
    monkeypatch.setattr(ef, "fetch", _fake_fetch('{"a":1}'))
    monkeypatch.setattr(ap, "ai_configured", lambda *a, **k: False)
    with pytest.raises(ValueError, match="还没有配置 AI"):
        asyncio.run(ev.build_view("https://e.com/"))


def test_build_view_rejects_empty_page(monkeypatch):
    import app.services.external_fetch as ef
    monkeypatch.setattr(ef, "fetch", _fake_fetch("   ", "text/html"))
    with pytest.raises(ValueError, match="空页面"):
        asyncio.run(ev.build_view("https://e.com/"))
