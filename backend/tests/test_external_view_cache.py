"""[fork R146] 外部页面「最近一次结果」缓存 —— 点开不该每次都抓 + 调 AI。

起因(用户): 「这部分不应该每次点开都需要抓取分析一次」。

原来只有一层缓存, 键是 `sha256(url + hint + 原文)` —— 要算这个键就**必须先把
页面抓回来**; 而行情看板的 HTML 里带时间戳/随机 id, 原文哈希几乎从不命中,
于是每次点开都是一次抓取 + 一次 AI。既慢又花钱。

新加的这层只按「地址 + 提示词」索引, 命中且没过期就**连页面都不抓**。
"""
from __future__ import annotations

import time

import pytest

from app.config import settings
from app.services import external_view as ev


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    yield


def _payload(**kw):
    base = {"spec": {"stats": [], "sections": [], "notes": []}, "url": "https://x.test/",
            "hint": "", "model": "m", "generated_at": time.time(),
            "source_chars": 10, "fetched_at": time.time()}
    base.update(kw)
    return base


# ------------------------------------------------------- 存取


def test_latest_round_trip():
    ev.save_latest("https://x.test/", "看涨停", _payload(model="gpt"))
    got = ev.load_latest("https://x.test/", "看涨停")
    assert got and got["model"] == "gpt"


def test_latest_is_keyed_by_url_and_hint():
    """换了提示词就是另一份整理结果, 不能串。"""
    ev.save_latest("https://x.test/", "看涨停", _payload(model="a"))
    ev.save_latest("https://x.test/", "看跌停", _payload(model="b"))
    assert ev.load_latest("https://x.test/", "看涨停")["model"] == "a"
    assert ev.load_latest("https://x.test/", "看跌停")["model"] == "b"
    assert ev.load_latest("https://other.test/", "看涨停") is None


def test_hint_whitespace_does_not_split_the_cache():
    ev.save_latest("https://x.test/", "看涨停", _payload(model="a"))
    assert ev.load_latest("https://x.test/", "  看涨停  ")["model"] == "a"


def test_missing_or_broken_file_reads_as_none():
    assert ev.load_latest("https://x.test/", "") is None
    ev._latest_path().write_text("{ 不是 json", encoding="utf-8")
    assert ev.load_latest("https://x.test/", "") is None


def test_store_is_capped_and_keeps_the_newest():
    now = time.time()
    for i in range(25):
        ev.save_latest(f"https://x{i}.test/", "", _payload(generated_at=now + i))
    import json
    data = json.loads(ev._latest_path().read_text(encoding="utf-8"))
    assert len(data) == 20
    # 最早那几个被裁掉, 最新的还在
    assert ev.load_latest("https://x24.test/", "") is not None
    assert ev.load_latest("https://x0.test/", "") is None


# ------------------------------------------------------- build_view 的短路


@pytest.mark.asyncio
async def test_fresh_cache_skips_both_fetch_and_ai(monkeypatch):
    """命中期内: 一次网络都不发, 一次 AI 都不调。这才是这个改动的重点。"""
    ev.save_latest("https://x.test/", "", _payload(model="cached"))

    def _boom_fetch(*a, **k):
        raise AssertionError("命中最近结果时不该再抓页面")
    monkeypatch.setattr("app.services.external_fetch.fetch", _boom_fetch)

    out = await ev.build_view("https://x.test/", "")
    assert out["from_cache"] is True and out["cache_kind"] == "latest"
    assert out["model"] == "cached"
    assert out["age_seconds"] >= 0


@pytest.mark.asyncio
async def test_expired_cache_falls_through_to_fetch(monkeypatch):
    """过期了就该照常走抓取那条路 —— 缓存是省重复劳动, 不是把页面钉死。"""
    ev.save_latest("https://x.test/", "",
                   _payload(generated_at=time.time() - ev.LATEST_TTL_S - 1))
    calls = []

    def _fetch(url, force=False):
        calls.append(url)
        raise RuntimeError("到这里就够了")
    monkeypatch.setattr("app.services.external_fetch.fetch", _fetch)

    with pytest.raises(RuntimeError):
        await ev.build_view("https://x.test/", "")
    assert calls == ["https://x.test/"]


@pytest.mark.asyncio
async def test_force_always_refetches(monkeypatch):
    """「重新解析」必须绕过这层, 否则按钮就成了摆设。"""
    ev.save_latest("https://x.test/", "", _payload())
    calls = []

    def _fetch(url, force=False):
        calls.append(force)
        raise RuntimeError("stop")
    monkeypatch.setattr("app.services.external_fetch.fetch", _fetch)

    with pytest.raises(RuntimeError):
        await ev.build_view("https://x.test/", "", force=True)
    assert calls == [True]


@pytest.mark.asyncio
async def test_a_future_timestamp_is_not_treated_as_fresh(monkeypatch):
    """时钟回拨/手改过文件时, 未来的时间戳不能被当成"永远新鲜"。"""
    ev.save_latest("https://x.test/", "", _payload(generated_at=time.time() + 86400))
    called = []

    def _fetch(url, force=False):
        called.append(url)
        raise RuntimeError("stop")
    monkeypatch.setattr("app.services.external_fetch.fetch", _fetch)

    with pytest.raises(RuntimeError):
        await ev.build_view("https://x.test/", "")
    assert called, "未来时间戳应当视为不可信, 照常重抓"
