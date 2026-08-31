"""[fork R97] fuyao 主备 key 自动切换 + 自定义源默认轮询间隔。"""
from __future__ import annotations

import pytest

from app.plugins.fuyao.client import FuyaoClient, FuyaoError


class _FakeResp:
    def __init__(self, status_code: int = 200, payload: dict | None = None) -> None:
        self.status_code = status_code
        self._payload = payload or {"code": 0, "data": {"ok": True}}

    def json(self) -> dict:
        return self._payload


class _FakeHttp:
    """按脚本逐次返回响应; 记录每次请求用的 key。"""

    def __init__(self, script: list[_FakeResp]) -> None:
        self.script = list(script)
        self.headers: dict[str, str] = {}
        self.used_keys: list[str] = []

    def get(self, path: str, params: dict) -> _FakeResp:
        self.used_keys.append(self.headers.get("X-api-key", ""))
        return self.script.pop(0)


def _client(keys: str, script: list[_FakeResp]) -> tuple[FuyaoClient, _FakeHttp]:
    c = FuyaoClient(api_key=keys)
    fake = _FakeHttp(script)
    fake.headers["X-api-key"] = c._keys[0]
    c._http.close()
    c._http = fake  # type: ignore[assignment]
    return c, fake


def test_rate_limited_primary_switches_to_backup_and_sticks():
    c, fake = _client("key-a,key-b", [
        _FakeResp(payload={"code": 4001, "message": "rate limited"}),  # 主 key 限频
        _FakeResp(),                                                    # 备 key 成功
        _FakeResp(),                                                    # 下一次调用
    ])
    assert c._get("/x", {}) == {"ok": True}
    assert fake.used_keys == ["key-a", "key-b"]
    # 粘住备 key: 后续请求直接用 key-b, 不再先撞主 key
    assert c._get("/x", {}) == {"ok": True}
    assert fake.used_keys[-1] == "key-b"


def test_http_auth_failure_switches():
    c, fake = _client("key-a,key-b", [
        _FakeResp(status_code=403),
        _FakeResp(),
    ])
    assert c._get("/x", {}) == {"ok": True}
    assert fake.used_keys == ["key-a", "key-b"]


def test_business_error_does_not_switch():
    c, fake = _client("key-a,key-b", [
        _FakeResp(payload={"code": 1234, "message": "bad param"}),
    ])
    with pytest.raises(FuyaoError):
        c._get("/x", {})
    assert fake.used_keys == ["key-a"]  # 业务错误换 key 也没救, 不切


def test_all_keys_exhausted_raises_last_error():
    c, fake = _client("key-a,key-b", [
        _FakeResp(payload={"code": 4001, "message": "limited"}),
        _FakeResp(payload={"code": 4001, "message": "limited too"}),
    ])
    with pytest.raises(FuyaoError):
        c._get("/x", {})
    assert fake.used_keys == ["key-a", "key-b"]


def test_single_key_rate_limit_raises_directly():
    c, fake = _client("only-key", [
        _FakeResp(payload={"code": 4001, "message": "limited"}),
    ])
    with pytest.raises(FuyaoError):
        c._get("/x", {})
    assert fake.used_keys == ["only-key"]


def test_comma_keys_parsed_and_blank_rejected():
    c = FuyaoClient(api_key=" a , b ,, c ")
    assert c._keys == ["a", "b", "c"]
    c._http.close()
    with pytest.raises(FuyaoError):
        FuyaoClient(api_key=" , ")


# ── 自定义源默认轮询间隔 ─────────────────────────────────


def test_default_interval_3s_for_custom_provider(monkeypatch, tmp_path):
    from app import config as app_config
    from app.services import preferences

    monkeypatch.setattr(app_config.settings, "data_dir", tmp_path)
    preferences._invalidate_cache()
    monkeypatch.setattr(preferences, "get_realtime_data_provider", lambda: "fuyao")
    assert preferences.get_realtime_quote_interval() == 3.0
    monkeypatch.setattr(preferences, "get_realtime_data_provider", lambda: "tickflow")
    assert preferences.get_realtime_quote_interval() == 6.0
    # 用户手动存过的值永远优先
    preferences.set_realtime_quote_interval(5.0)
    monkeypatch.setattr(preferences, "get_realtime_data_provider", lambda: "fuyao")
    assert preferences.get_realtime_quote_interval() == 5.0
