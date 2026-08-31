"""[fork 增强] R93 使用观察笔记 HTTP API。

纯文本笔记的增删改查, 服务层见 services/usage_notes.py。
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.services import usage_notes

router = APIRouter(prefix="/api/usage-notes", tags=["usage-notes"])


class NoteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1, max_length=usage_notes.MAX_CONTENT_CHARS)


class NotePatch(BaseModel):
    """局部更新: 只带要改的字段。status 语义见 services/usage_notes。"""
    model_config = ConfigDict(extra="forbid")

    content: str | None = Field(default=None, min_length=1, max_length=usage_notes.MAX_CONTENT_CHARS)
    status: str | None = None
    pinned: bool | None = None


@router.get("")
def list_notes() -> dict:
    return {"items": usage_notes.list_notes()}


@router.post("")
def create_note(payload: NoteIn) -> dict:
    try:
        return usage_notes.create_note(payload.content)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@router.put("/{note_id}")
def update_note(note_id: str, payload: NotePatch) -> dict:
    try:
        note = usage_notes.update_note(
            note_id,
            content=payload.content,
            status=payload.status,
            pinned=payload.pinned,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    if note is None:
        raise HTTPException(status_code=404, detail="笔记不存在")
    return note


@router.delete("/{note_id}")
def delete_note(note_id: str) -> dict:
    if not usage_notes.delete_note(note_id):
        raise HTTPException(status_code=404, detail="笔记不存在")
    return {"ok": True}
