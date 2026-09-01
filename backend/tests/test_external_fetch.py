"""[fork R117] 外部网页抓取: SSRF 守卫 / 大小上限 / 逐跳重定向校验 / TTL。"""
from __future__ import annotations

import pytest

from app.services import external_fetch as ef


@pytest.fixture(autouse=True)
def _clear_cache():
    ef._cache.clear()
    yield
    ef._cache.clear()


@pytest.fixture
def _public_dns(monkeypatch):
    """把所有域名解析成公网地址, 好让守卫之外的逻辑能跑起来。"""
    monkeypatch.setattr(ef.socket, "getaddrinfo", lambda host, port: [(2, 1, 6, "", ("93.184.216.34", 0))])


@pytest.mark.parametrize("url", [
    "ftp://example.com/x",
    "file:///etc/passwd",
    "javascript:alert(1)",
    "example.com/no-scheme",
])
def test_rejects_non_http_scheme(url):
    with pytest.raises(ef.FetchError):
        ef._normalize(url)


def test_rejects_credentials_in_url(_public_dns):
    with pytest.raises(ef.FetchError, match="账号密码"):
        ef._normalize("https://user:pw@example.com/")


@pytest.mark.parametrize("addr", [
    "127.0.0.1",      # 环回
    "192.168.0.168",  # 用户的 NAS 所在网段
    "10.0.0.5",
    "172.16.3.9",
    "169.254.169.254",  # 云元数据服务, 典型 SSRF 目标
    "0.0.0.0",
])
def test_rejects_internal_addresses(monkeypatch, addr):
    monkeypatch.setattr(ef.socket, "getaddrinfo", lambda h, p: [(2, 1, 6, "", (addr, 0))])
    with pytest.raises(ef.FetchError, match="内网"):
        ef._normalize("https://evil.example.com/")


def test_rejects_when_any_resolved_address_is_internal(monkeypatch):
    """一个域名解析出多个地址时, 只要有一个是内网就整体拒绝。"""
    monkeypatch.setattr(ef.socket, "getaddrinfo", lambda h, p: [
        (2, 1, 6, "", ("93.184.216.34", 0)),
        (2, 1, 6, "", ("127.0.0.1", 0)),
    ])
    with pytest.raises(ef.FetchError, match="内网"):
        ef._normalize("https://mixed.example.com/")


def test_public_address_passes(_public_dns):
    assert ef._normalize(" https://example.com/a?b=1 ") == "https://example.com/a?b=1"


def test_fetch_returns_text_and_caches(monkeypatch, _public_dns):
    calls = {"n": 0}

    def fake_get(url):
        calls["n"] += 1
        return 200, "text/html; charset=utf-8", "你好".encode(), ""

    monkeypatch.setattr(ef, "_http_get", fake_get)
    got = ef.fetch("https://example.com/")
    assert got["ok"] and got["text"] == "你好" and got["status"] == 200
    assert got["cached"] is False
    # TTL 内第二次不打上游
    again = ef.fetch("https://example.com/")
    assert calls["n"] == 1 and again["cached"] is True
    # force 强制穿透缓存
    ef.fetch("https://example.com/", force=True)
    assert calls["n"] == 2


def test_redirect_hops_are_revalidated(monkeypatch):
    """302 到内网必须被拦 —— 首跳合法不代表终点合法。"""
    def resolve(host, port):
        addr = "127.0.0.1" if host == "inner.example.com" else "93.184.216.34"
        return [(2, 1, 6, "", (addr, 0))]

    monkeypatch.setattr(ef.socket, "getaddrinfo", resolve)
    monkeypatch.setattr(ef, "_http_get", lambda url: (302, "", b"", "https://inner.example.com/x"))
    with pytest.raises(ef.FetchError, match="内网"):
        ef.fetch("https://ok.example.com/")


def test_redirect_limit(monkeypatch, _public_dns):
    monkeypatch.setattr(ef, "_http_get", lambda url: (302, "", b"", "https://example.com/next"))
    with pytest.raises(ef.FetchError, match="重定向"):
        ef.fetch("https://example.com/")


def test_failure_leaves_no_cache(monkeypatch, _public_dns):
    monkeypatch.setattr(ef, "_http_get", lambda url: (_ for _ in ()).throw(ef.httpx.ConnectError("boom")))
    with pytest.raises(ef.FetchError, match="抓取失败"):
        ef.fetch("https://example.com/")
    assert ef._cache == {}


def test_size_cap_aborts_download(monkeypatch, _public_dns):
    import httpx

    monkeypatch.setattr(ef, "MAX_BYTES", 1024)
    transport = httpx.MockTransport(lambda req: httpx.Response(200, content=b"x" * 4096))
    monkeypatch.setattr(ef, "_client", lambda: httpx.Client(transport=transport, follow_redirects=False))
    with pytest.raises(ef.FetchError, match="上限"):
        ef.fetch("https://example.com/big")


@pytest.mark.parametrize("raw,ctype,expect", [
    ("中文".encode("utf-8"), "text/html; charset=utf-8", "中文"),
    ("中文".encode("gb18030"), "text/html; charset=gbk", "中文"),
    ("中文".encode("gb18030"), "text/html", "中文"),          # 无 charset 时兜底 gb18030
    (b'{"a":1}', "application/json", '{"a":1}'),
])
def test_decode_variants(raw, ctype, expect):
    assert ef._decode(raw, ctype) == expect
