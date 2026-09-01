"""[R153] /assets 直出: 长缓存头 + 预压缩协商; 没有压缩文件时行为与原来一致。"""
from __future__ import annotations

import gzip

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.static_assets import IMMUTABLE, HashedAssets, accepted_encodings

JS = b"console.log('hello, world');\n" * 60


@pytest.fixture
def assets(tmp_path):
    (tmp_path / "app-abc123.js").write_bytes(JS)
    (tmp_path / "app-abc123.js.gz").write_bytes(gzip.compress(JS, 9))
    (tmp_path / "plain-def456.js").write_bytes(JS)          # 没有任何压缩版本
    (tmp_path / "font-xyz.woff2").write_bytes(b"\x00" * 200)  # 本就是压缩格式
    return tmp_path


@pytest.fixture
def client(assets):
    app = FastAPI()
    app.mount("/assets", HashedAssets(directory=assets), name="assets")
    return TestClient(app)


# ---------------------------------------------------------------- 协商


def test_serves_precompressed_gzip_when_accepted(client, assets):
    r = client.get("/assets/app-abc123.js", headers={"Accept-Encoding": "gzip"})
    assert r.status_code == 200
    assert r.headers["content-encoding"] == "gzip"
    # Content-Type 按原文件名判, 不能因为发的是 .gz 就变成 octet-stream
    assert r.headers["content-type"].startswith("text/javascript")
    # 线上传的是压缩后的字节数
    assert int(r.headers["content-length"]) == (assets / "app-abc123.js.gz").stat().st_size
    # 客户端解出来仍是原文
    assert r.content == JS


def test_prefers_brotli_over_gzip_when_both_present(client, assets):
    brotli = pytest.importorskip("brotli")
    (assets / "app-abc123.js.br").write_bytes(brotli.compress(JS))
    r = client.get("/assets/app-abc123.js", headers={"Accept-Encoding": "gzip, br"})
    assert r.headers["content-encoding"] == "br"
    assert r.content == JS


def test_identity_gets_raw_file(client):
    """客户端不接受压缩 → 原样发, 没有 Content-Encoding —— 与原来的 StaticFiles 一致。"""
    r = client.get("/assets/app-abc123.js", headers={"Accept-Encoding": "identity"})
    assert r.status_code == 200
    assert "content-encoding" not in r.headers
    assert r.content == JS


def test_no_compressed_sibling_falls_back_to_raw(client):
    r = client.get("/assets/plain-def456.js", headers={"Accept-Encoding": "gzip, br"})
    assert r.status_code == 200
    assert "content-encoding" not in r.headers
    assert r.content == JS


def test_q_zero_disables_that_encoding(client):
    r = client.get("/assets/app-abc123.js", headers={"Accept-Encoding": "gzip;q=0, identity"})
    assert "content-encoding" not in r.headers
    assert r.content == JS


def test_font_served_raw_with_right_type(client):
    r = client.get("/assets/font-xyz.woff2", headers={"Accept-Encoding": "gzip, br"})
    assert r.status_code == 200
    assert "content-encoding" not in r.headers
    assert r.headers["content-type"] == "font/woff2"


# ---------------------------------------------------------------- 缓存


@pytest.mark.parametrize("name", ["app-abc123.js", "plain-def456.js", "font-xyz.woff2"])
def test_every_asset_is_immutable_and_varies_on_encoding(client, name):
    r = client.get(f"/assets/{name}", headers={"Accept-Encoding": "gzip"})
    assert r.headers["cache-control"] == IMMUTABLE
    assert r.headers["vary"] == "Accept-Encoding"


def test_conditional_get_returns_304_with_cache_headers(client):
    first = client.get("/assets/app-abc123.js", headers={"Accept-Encoding": "gzip"})
    etag = first.headers["etag"]
    again = client.get(
        "/assets/app-abc123.js",
        headers={"Accept-Encoding": "gzip", "If-None-Match": etag},
    )
    assert again.status_code == 304
    assert again.headers["cache-control"] == IMMUTABLE


def test_head_request(client, assets):
    r = client.head("/assets/app-abc123.js", headers={"Accept-Encoding": "gzip"})
    assert r.status_code == 200
    assert r.headers["content-encoding"] == "gzip"
    assert r.content == b""


def test_missing_is_404(client):
    assert client.get("/assets/nope.js").status_code == 404


# ---------------------------------------------------------------- 解析


def test_accepted_encodings_parsing():
    assert accepted_encodings("gzip, deflate, br") == {"gzip", "deflate", "br"}
    assert accepted_encodings("br;q=1.0, gzip;q=0.8") == {"br", "gzip"}
    assert accepted_encodings("gzip;q=0, identity") == {"identity"}
    assert accepted_encodings("") == set()
