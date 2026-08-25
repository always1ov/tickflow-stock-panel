"""[fork 增强] R72 小 JSON 存储的两件安全件: 按文件互斥锁 + 原子落盘。

R68 在操盘手账本上修过一次"操作员凭空消失": 裸 ``Path.write_text`` 是
**先清空再写**, 两个线程同时写(或写到一半进程被停)会留下半截 JSON; 读的
那侧把解析失败当成"空的", 下一次保存就把别人全覆盖没了 —— 短暂损坏被
放大成永久丢失。当时只修了账本自己; 事后按 CONTRIBUTING §6.2 复查, fork
的另外六个自建 JSON 存储(AI 信号 / 工作流 / 挖掘自动驾驶 / 跷跷板 /
今日 AI / 今日偏好)是同一个形状 —— 于是把两件安全件提出来共用:

- ``lock_for(path)``: 同一个文件全进程共用一把锁, "读 → 改 → 写"整段包住,
  两个并发改动排队而不是互相覆盖。
- ``atomic_write_json(path, payload)``: 同目录临时文件 → flush+fsync →
  ``os.replace``。盘上要么是旧的整份、要么是新的整份, 没有中间态。

operate_trader 的账本(paper_trader.py)没有迁过来: 它另有 .bak 回退与
StoreError fail-closed 语义, 且已有一组测试守着 —— 重构它没有新收益。
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

# 每个文件一把锁。注册表本身也要锁 —— 两个线程同时首次访问同一个文件时,
# 各拿到一把不同的锁等于没锁。
_REGISTRY: dict[str, threading.RLock] = {}
_REGISTRY_LOCK = threading.Lock()


def lock_for(path: Path | str) -> threading.RLock:
    """这个文件的互斥锁。调用方用 ``with lock_for(p):`` 包住读-改-写整段。"""
    key = str(Path(path).resolve())
    with _REGISTRY_LOCK:
        lk = _REGISTRY.get(key)
        if lk is None:
            lk = _REGISTRY[key] = threading.RLock()
        return lk


def atomic_write_json(path: Path | str, payload: Any) -> None:
    """原子写 JSON: 临时文件 + fsync + os.replace, 不存在半截文件。

    只管"写这个动作不撕裂"; 并发的"读-改-写"覆盖要靠 lock_for 排队,
    两件事各管一半, 都要用。
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    tmp = p.with_name(f"{p.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    try:
        with tmp.open("w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, p)
    finally:
        tmp.unlink(missing_ok=True)
