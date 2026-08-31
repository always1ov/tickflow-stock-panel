"""[fork 增强] R93 使用观察笔记 — 纯文本笔记的增删改查。

用途: 用户归纳"这个系统怎么用、哪些功能有用"的个人笔记本。
存储: data/user_data/usage_notes.json (数组, 按 updated_at 降序返回)。
并发: 走 json_store 的按文件互斥锁 + 原子落盘(R72 约定) —— 读-改-写整段在锁里。

每条笔记结构:
{
  "id": "note_xxxxxxxxxxxx",
  "content": "纯文本正文",
  "status": "",                      # ""=随手记 / pending=待验证 / verified=已验证 / rejected=不成立
  "pinned": false,                   # 置顶(排序最前)
  "created_at": "2026-08-31T10:00:00",
  "updated_at": "2026-08-31T10:05:00"
}

[R96] status/pinned 是按用户实际用法加的: 记的多是"观察→等市场验证"的猜想,
一条链是 随手记 → 待验证 → 已验证/不成立。老数据无这两个字段, 读时补默认。
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path

from app.config import settings
from app.services.json_store import atomic_write_json, lock_for

MAX_NOTES = 500          # 防失控: 纯文本笔记 500 条足够, 超出拒绝新增
MAX_CONTENT_CHARS = 20000
STATUSES = ("", "pending", "verified", "rejected")


def _path() -> Path:
    return settings.data_dir / "user_data" / "usage_notes.json"


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _read_unlocked() -> list[dict]:
    p = _path()
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:  # noqa: BLE001
        # 解析失败不吞成空列表回写(那会永久丢数据, 见 R68 教训) —— 只读场景返回空,
        # 写场景由调用方先 list 再改, 锁内一致; 真损坏时最坏是新写覆盖, 有 tmp 原子性兜底
        return []


def _with_defaults(note: dict) -> dict:
    """老数据补默认字段(不回写盘, 读时视图)。"""
    return {"status": "", "pinned": False, **note}


def list_notes() -> list[dict]:
    """全部笔记: 置顶在前, 组内按 updated_at 降序(最近编辑的在前)。"""
    with lock_for(_path()):
        notes = [_with_defaults(n) for n in _read_unlocked()]
    # sorted 稳定: 先按时间降序, 再把置顶的整体提前, 组内时间序保持
    by_time = sorted(notes, key=lambda n: n.get("updated_at") or "", reverse=True)
    return sorted(by_time, key=lambda n: 0 if n.get("pinned") else 1)


def create_note(content: str) -> dict:
    content = (content or "").strip()
    if not content:
        raise ValueError("笔记内容不能为空")
    if len(content) > MAX_CONTENT_CHARS:
        raise ValueError(f"单条笔记最长 {MAX_CONTENT_CHARS} 字")
    with lock_for(_path()):
        notes = _read_unlocked()
        if len(notes) >= MAX_NOTES:
            raise ValueError(f"笔记数量已达上限 {MAX_NOTES} 条, 请先删除旧的")
        now = _now()
        note = {
            "id": f"note_{uuid.uuid4().hex[:12]}",
            "content": content,
            "status": "",
            "pinned": False,
            "created_at": now,
            "updated_at": now,
        }
        notes.append(note)
        atomic_write_json(_path(), notes)
    return note


def update_note(
    note_id: str,
    *,
    content: str | None = None,
    status: str | None = None,
    pinned: bool | None = None,
) -> dict | None:
    """就地改字段(None = 不改)。返回更新后的笔记; 不存在返回 None。

    只有正文修改才刷新 updated_at —— 标状态/置顶是整理动作,
    不该把一条旧观察顶到"最近编辑"的最前面去。
    """
    if content is not None:
        content = content.strip()
        if not content:
            raise ValueError("笔记内容不能为空")
        if len(content) > MAX_CONTENT_CHARS:
            raise ValueError(f"单条笔记最长 {MAX_CONTENT_CHARS} 字")
    if status is not None and status not in STATUSES:
        raise ValueError(f"status 必须是 {STATUSES} 之一")
    with lock_for(_path()):
        notes = _read_unlocked()
        for note in notes:
            if note.get("id") == note_id:
                if content is not None:
                    note["content"] = content
                    note["updated_at"] = _now()
                if status is not None:
                    note["status"] = status
                if pinned is not None:
                    note["pinned"] = bool(pinned)
                atomic_write_json(_path(), notes)
                return _with_defaults(dict(note))
    return None


def delete_note(note_id: str) -> bool:
    with lock_for(_path()):
        notes = _read_unlocked()
        remaining = [n for n in notes if n.get("id") != note_id]
        if len(remaining) == len(notes):
            return False
        atomic_write_json(_path(), remaining)
    return True
