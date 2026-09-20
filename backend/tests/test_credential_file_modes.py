"""凭据类文件的落盘权限 (安全审查 run-1)。

两件事:

1. **权限必须在文件存在的那一刻就位。** `atomic_write_text` 的上一版注释声称
   「mode 在替换之前打到临时文件上……先改临时文件就没有这个窗口」——
   那句话不成立: 临时文件是先写满内容、下一条语句才 chmod, 窗口没消失, 只是
   从正式路径挪到了 `.tmp` 路径, 而 `.tmp` 里躺的是同一份明文。
2. **哪些文件算凭据类, 要按内容算, 不按当初写注释时的印象算。**
   `preferences.json` 的模块注释说自己「非敏感数据」, 而它存着飞书 HMAC 签名
   密钥、企微机器人密钥, 以及 `key=` / `access_token=` 本身就是凭据的
   企微/钉钉 webhook URL。
"""
from __future__ import annotations

import json
import os
import stat

import pytest

from app.services import fs_utils


def _mode(path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def test_mode_is_set_at_creation_not_after_the_content_is_written(tmp_path, monkeypatch):
    """钉住修复的**机制**, 不只是结果。

    结果(最终 0600)在旧写法下也成立, 所以只断言结果是抓不到这个 bug 的。
    这里断言的是: 创建临时文件用的是带 mode 的 os.open, 且带 O_CREAT|O_EXCL。
    """
    seen: list[tuple[str, int, int]] = []
    real_open = os.open

    def spy(path, flags, mode=0o777, **kw):
        seen.append((str(path), flags, mode))
        return real_open(path, flags, mode, **kw)

    monkeypatch.setattr(fs_utils.os, "open", spy)
    target = tmp_path / "secrets.json"
    fs_utils.atomic_write_text(target, '{"k": "v"}', mode=0o600)

    tmp_opens = [s for s in seen if s[0].endswith(".json.tmp")]
    assert tmp_opens, "临时文件应当先以目标权限创建, 而不是写完内容再 chmod"
    _, flags, mode = tmp_opens[0]
    assert mode == 0o600, "创建时就要带上目标权限"
    assert flags & os.O_CREAT
    assert flags & os.O_EXCL, "必须独占创建, 否则会复用残留 .tmp 的旧权限"
    assert _mode(target) == 0o600


def test_a_stale_tmp_with_wide_permissions_is_not_reused(tmp_path):
    """残留 .tmp 会保留它自己的旧权限 —— 复用它等于把窗口又开回来。"""
    target = tmp_path / "auth.json"
    stale = tmp_path / "auth.json.tmp"
    stale.write_text("{}", encoding="utf-8")
    os.chmod(stale, 0o644)

    fs_utils.atomic_write_text(target, '{"sessions": {}}', mode=0o600)
    assert _mode(target) == 0o600
    assert not stale.exists()


def test_no_mode_argument_keeps_the_old_plain_write(tmp_path):
    """不传 mode 的调用方(策略覆盖、持仓、分析菜单等)行为不变。"""
    target = tmp_path / "plain.json"
    fs_utils.atomic_write_text(target, "{}")
    assert target.read_text(encoding="utf-8") == "{}"


def test_chmod_failure_is_logged_instead_of_silently_swallowed(tmp_path, monkeypatch, caplog):
    """一个**要求了 0600 却没拿到**的凭据文件必须在日志里留痕。"""
    def boom(*a, **kw):
        raise OSError("no chmod here")

    monkeypatch.setattr(fs_utils.os, "chmod", boom)
    with caplog.at_level("WARNING"):
        fs_utils.atomic_write_text(tmp_path / "x.json", "{}", mode=0o600)
    assert any("mode" in r.message or "mode" in r.getMessage() for r in caplog.records)


@pytest.mark.parametrize("first_write", [True, False])
def test_save_ai_profiles_writes_0600_even_when_creating_the_file(tmp_path, monkeypatch, first_write):
    """save_ai_profiles 原本是 write_text 之后再 chmod, **直接打在正式路径上**。"""
    from app import secrets_store

    monkeypatch.setattr(secrets_store, "_path", lambda: tmp_path / "secrets.json")
    if not first_write:
        secrets_store.save({"tickflow_api_key": "DUMMY"})
    secrets_store.save_ai_profiles([
        {"id": "p1", "label": "x", "api_key": "DUMMY-NOT-REAL", "model": "m"},
    ])
    path = tmp_path / "secrets.json"
    assert path.exists()
    assert _mode(path) == 0o600
    if not first_write:
        # 整表覆写不许把同文件里的其他凭据顺手抹掉
        assert json.loads(path.read_text(encoding="utf-8"))["tickflow_api_key"] == "DUMMY"


def test_preferences_file_is_0600_because_it_holds_webhook_credentials(tmp_path, monkeypatch):
    from app.services import preferences

    monkeypatch.setattr(preferences, "_path", lambda: tmp_path / "preferences.json")
    preferences._invalidate_cache()
    preferences.save({"feishu_webhook_secret": "DUMMY-NOT-REAL"})
    assert _mode(tmp_path / "preferences.json") == 0o600


def test_realtime_keys_setter_goes_through_the_locked_atomic_path(tmp_path, monkeypatch):
    """原本是 _SAVE_LOCK 之外的一次裸 write_text, 绕开了锁、原子性和权限。"""
    from app.services import preferences

    monkeypatch.setattr(preferences, "_path", lambda: tmp_path / "preferences.json")
    preferences._invalidate_cache()
    preferences.save({"feishu_webhook_secret": "DUMMY-NOT-REAL"})
    preferences.set_realtime_keys_per_round(7)

    path = tmp_path / "preferences.json"
    assert _mode(path) == 0o600
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["realtime_keys_per_round"] == 7
    # 合并写入, 不是整表覆写 —— 旁边的键必须还在
    assert data["feishu_webhook_secret"] == "DUMMY-NOT-REAL"
