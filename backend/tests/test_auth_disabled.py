"""[fork 增强] R82 — AUTH_DISABLED 免登录开关。

开关语义:
  - 默认(未设置): 行为与从前逐字节一致 — 未设密码公网 403 / 已设密码无会话 401。
  - AUTH_DISABLED=1: 认证中间件对 /api/ 全放行(公网也放), /api/auth/status
    一律报告已登录(手动打开 /login 会直接弹回首页)。

测试通过真实的 app.main.auth_middleware 跑 HTTP 层, 不是复刻逻辑;
TestClient 默认的 client host 是 "testclient" — 不是内网地址, 恰好模拟公网来源。
"""
from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import config as app_config
from app import main as app_main
from app.api import auth as auth_api


@pytest.fixture(autouse=True)
def isolated_auth_store(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Iterator[ModuleType]:
    monkeypatch.setattr(app_config.settings, "data_dir", tmp_path)
    monkeypatch.setattr(app_config.settings, "auth_password", "")
    monkeypatch.setattr(app_config.settings, "auth_disabled", False)
    from app.services import auth

    auth._sessions.clear()
    auth._configured_cache = None
    yield auth
    auth._sessions.clear()
    auth._configured_cache = None


def _client() -> TestClient:
    """挂真实认证中间件 + 真实 /api/auth 路由的最小 app。"""
    test_app = FastAPI()
    test_app.middleware("http")(app_main.auth_middleware)
    test_app.include_router(auth_api.router)

    @test_app.get("/api/protected")
    def protected() -> dict:
        return {"ok": True}

    return TestClient(test_app)


# ── 默认行为不变(开关不存在时逐字节一致) ──────────────────────


def test_default_public_unconfigured_still_403(isolated_auth_store: ModuleType) -> None:
    resp = _client().get("/api/protected")
    assert resp.status_code == 403
    assert resp.json()["code"] == "NOT_INITIALIZED"


def test_default_configured_without_session_still_401(
    isolated_auth_store: ModuleType,
) -> None:
    isolated_auth_store.set_password("secret-pw")
    resp = _client().get("/api/protected")
    assert resp.status_code == 401


# ── AUTH_DISABLED=1: 全放行 ──────────────────────────────────


def test_disabled_bypasses_not_initialized_gate(
    isolated_auth_store: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(app_config.settings, "auth_disabled", True)
    resp = _client().get("/api/protected")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


def test_disabled_bypasses_session_check_even_with_password_set(
    isolated_auth_store: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    isolated_auth_store.set_password("secret-pw")
    monkeypatch.setattr(app_config.settings, "auth_disabled", True)
    resp = _client().get("/api/protected")  # 无 cookie, 公网来源
    assert resp.status_code == 200


def test_disabled_status_reports_authenticated(
    isolated_auth_store: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(app_config.settings, "auth_disabled", True)
    resp = _client().get("/api/auth/status")
    assert resp.status_code == 200
    body = resp.json()
    # authenticated=true → 前端 /login 页 useEffect 直接 navigate('/')
    assert body["authenticated"] is True
    assert body["configured"] is True
    assert body["disabled"] is True


def test_default_status_unchanged(isolated_auth_store: ModuleType) -> None:
    body = _client().get("/api/auth/status").json()
    assert body == {"configured": False, "authenticated": False}
