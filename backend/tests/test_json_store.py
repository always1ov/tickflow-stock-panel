"""[fork 增强] R72 小 JSON 存储的并发安全 —— 按 CONTRIBUTING §6.2 补的一课。

R68 修过一次真事故: 操盘手账本被并发写撕裂, 读侧把半截 JSON 当空账本,
下一次保存把其他操作员全覆盖没了。这里守的是同一形状在其余 fork 存储上的
复现 —— 尤其 ai_signals.json, 它是全系统并发最重的一份(今日总览定时、
个股分析页、多个操盘手 refresh 都写它)。
"""
from __future__ import annotations

import json
import threading

import pytest


@pytest.fixture(autouse=True)
def store(tmp_path, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    return tmp_path


# ---------- 基础件 ----------

def test_atomic_write_never_leaves_a_torn_file(tmp_path):
    from app.services.json_store import atomic_write_json
    p = tmp_path / "a" / "b.json"
    atomic_write_json(p, {"x": 1})
    assert json.loads(p.read_text(encoding="utf-8")) == {"x": 1}
    # 目录里不残留临时文件
    assert [f.name for f in p.parent.iterdir()] == ["b.json"]


def test_lock_for_returns_the_same_lock_for_the_same_file(tmp_path):
    from app.services.json_store import lock_for
    a = lock_for(tmp_path / "x.json")
    b = lock_for(str(tmp_path / "x.json"))
    assert a is b, "同一个文件必须拿到同一把锁, 否则等于没锁"
    assert lock_for(tmp_path / "y.json") is not a


# ---------- AI 信号: 并发重出不能互丢 ----------

# [R72 → R435 退役] `test_concurrent_signal_saves_keep_every_symbol` 钉的是 AI 信号那份
# signals.json 的并发落盘(读-改-写上锁)。AI 信号整套停用, 那个模块删了; `lock_for` /
# `atomic_write_json` 这对原语本身由本文件其余几条照测。

