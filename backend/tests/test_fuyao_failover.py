"""[fork R97] fuyao 主备 key「失效才切换」语义。

- 鉴权失败(401/403) = key 真失效 → 立即切备并粘住;
- 限频(4001/429) = 瞬时 → 单次不切(本次抛错交给软失败), 同一把 key 连续
  限频满 3 次才判失效切备;
- 网络/业务错误 → 换 key 也没救, 不切。
"""
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


_RL = {"code": 4001, "message": "rate limited"}


def test_auth_failure_switches_immediately_and_sticks():
    c, fake = _client("key-a,key-b", [
        _FakeResp(status_code=403),   # 主 key 鉴权失败 = 失效
        _FakeResp(),                  # 备 key 成功
        _FakeResp(),                  # 下一次调用
    ])
    assert c._get("/x", {}) == {"ok": True}
    assert fake.used_keys == ["key-a", "key-b"]
    # 粘住备 key
    assert c._get("/x", {}) == {"ok": True}
    assert fake.used_keys[-1] == "key-b"


def test_single_rate_limit_does_not_switch():
    c, fake = _client("key-a,key-b", [
        _FakeResp(payload=dict(_RL)),
    ])
    with pytest.raises(FuyaoError):
        c._get("/x", {})
    assert fake.used_keys == ["key-a"]  # 瞬时限频: 本次抛错, 不动备 key


def test_three_consecutive_rate_limits_escalate_to_switch():
    c, fake = _client("key-a,key-b", [
        _FakeResp(payload=dict(_RL)),   # 第 1 次: 抛错不切
        _FakeResp(payload=dict(_RL)),   # 第 2 次: 抛错不切
        _FakeResp(payload=dict(_RL)),   # 第 3 次: 判失效, 切备重试
        _FakeResp(),                    # 备 key 成功
    ])
    with pytest.raises(FuyaoError):
        c._get("/x", {})
    with pytest.raises(FuyaoError):
        c._get("/x", {})
    assert c._get("/x", {}) == {"ok": True}
    assert fake.used_keys == ["key-a", "key-a", "key-a", "key-b"]


def test_success_resets_rate_limit_streak():
    c, fake = _client("key-a,key-b", [
        _FakeResp(payload=dict(_RL)),
        _FakeResp(payload=dict(_RL)),
        _FakeResp(),                    # 成功清零计数
        _FakeResp(payload=dict(_RL)),   # 重新从 1 数起, 不该切
    ])
    for _ in range(2):
        with pytest.raises(FuyaoError):
            c._get("/x", {})
    assert c._get("/x", {}) == {"ok": True}
    with pytest.raises(FuyaoError):
        c._get("/x", {})
    assert fake.used_keys == ["key-a"] * 4


def test_business_error_does_not_switch():
    c, fake = _client("key-a,key-b", [
        _FakeResp(payload={"code": 1234, "message": "bad param"}),
    ])
    with pytest.raises(FuyaoError):
        c._get("/x", {})
    assert fake.used_keys == ["key-a"]


def test_all_keys_auth_failed_raises_last_error():
    c, fake = _client("key-a,key-b", [
        _FakeResp(status_code=401),
        _FakeResp(status_code=401),
    ])
    with pytest.raises(FuyaoError):
        c._get("/x", {})
    assert fake.used_keys == ["key-a", "key-b"]


def test_single_key_auth_failure_raises_directly():
    c, fake = _client("only-key", [
        _FakeResp(status_code=403),
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
