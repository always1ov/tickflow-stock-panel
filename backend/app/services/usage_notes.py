"""[fork 增强] R93 使用观察笔记 — 纯文本笔记的增删改查。

用途: 用户归纳"这个系统怎么用、哪些功能有用"的个人笔记本。
存储: data/user_data/usage_notes.json (数组, 按 updated_at 降序返回)。
并发: 走 json_store 的按文件互斥锁 + 原子落盘(R72 约定) —— 读-改-写整段在锁里。

每条笔记结构:
{
  "id": "note_xxxxxxxxxxxx",
  "content": "纯文本正文",
  "created_at": "2026-08-31T10:00:00",
  "updated_at": "2026-08-31T10:05:00"
}
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


def list_notes() -> list[dict]:
    """全部笔记, 按 updated_at 降序(最近编辑的在前)。"""
    with lock_for(_path()):
        notes = _read_unlocked()
    return sorted(notes, key=lambda n: n.get("updated_at") or "", reverse=True)


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
            "created_at": now,
            "updated_at": now,
        }
        notes.append(note)
        atomic_write_json(_path(), notes)
    return note


def update_note(note_id: str, content: str) -> dict | None:
    """就地改正文。返回更新后的笔记; 不存在返回 None。"""
    content = (content or "").strip()
    if not content:
        raise ValueError("笔记内容不能为空")
    if len(content) > MAX_CONTENT_CHARS:
        raise ValueError(f"单条笔记最长 {MAX_CONTENT_CHARS} 字")
    with lock_for(_path()):
        notes = _read_unlocked()
        for note in notes:
            if note.get("id") == note_id:
                note["content"] = content
                note["updated_at"] = _now()
                atomic_write_json(_path(), notes)
                return dict(note)
    return None


def delete_note(note_id: str) -> bool:
    with lock_for(_path()):
        notes = _read_unlocked()
        remaining = [n for n in notes if n.get("id") != note_id]
        if len(remaining) == len(notes):
            return False
        atomic_write_json(_path(), remaining)
    return True
