"""[fork 增强] R93 使用观察笔记 → [R180] 消息面 HTTP API。

增删改查照旧, 新增三条:
  POST /{id}/digest      让 AI 凝练这一条(图片走多模态)
  POST /upload           传图片 / 文本文件, 建一条带附件的记录
  POST /summary          把全部条目综合成一大段总的(GET 读已存的)

服务层见 services/usage_notes.py(逐条) 与 services/news_desk.py(凝练与综合)。
"""
from __future__ import annotations

import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from pydantic import BaseModel, ConfigDict, Field

from app.services import news_desk, usage_notes

logger = logging.getLogger(__name__)

# 图片按 10MB 封顶 —— 研报/公告截图远用不到这么大, 而它要整张进 base64 喂给
# 模型, 再大就先撞上下文窗口了。
_MAX_ATTACH_BYTES = 10 * 1024 * 1024
_CHUNK = 1024 * 1024
# 只收这些。二进制(pdf/docx/xlsx)一律不收 —— 收了也读不出内容, 只会变成一个
# 打不开的附件挂在那儿。用户要传 PDF 里的内容, 截图反而是能work的路。
_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
_TEXT_EXT = {".txt", ".md", ".csv", ".tsv", ".json", ".log"}

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
    horizon: str | None = None


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
            horizon=payload.horizon,
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


async def _save_upload(file: UploadFile, dest: Path) -> None:
    """分块落盘, 超限立刻拒 —— 抄 ext_data 的写法, 不一次性读进内存。"""
    total = 0
    with dest.open("wb") as f:
        while True:
            chunk = await file.read(_CHUNK)
            if not chunk:
                break
            total += len(chunk)
            if total > _MAX_ATTACH_BYTES:
                f.close()
                dest.unlink(missing_ok=True)
                raise HTTPException(413, f"文件过大(上限 {_MAX_ATTACH_BYTES // (1024*1024)}MB)")
            f.write(chunk)


@router.post("/upload")
async def upload_note(request: Request, file: UploadFile = File(...),
                      content: str = "") -> dict:
    """传一张图或一个文本文件, 建一条带附件的消息。

    **落盘就返回, 不在这里等 AI。** 凝练是单独一步 —— 上传要立刻有反馈,
    卡在一次几十秒的 AI 调用上会让人以为传失败了。
    """
    from app.config import settings

    name = (file.filename or "upload").strip()
    ext = Path(name).suffix.lower()
    if ext in _IMAGE_EXT:
        kind = "image"
    elif ext in _TEXT_EXT:
        kind = "file"
    else:
        raise HTTPException(415, f"不支持的类型 {ext or '(无扩展名)'} —— "
                                 f"图片 {sorted(_IMAGE_EXT)} 或文本 {sorted(_TEXT_EXT)}")

    rel = Path("user_data") / "news_desk" / f"{uuid.uuid4().hex[:12]}{ext}"
    dest = settings.data_dir / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    await _save_upload(file, dest)

    try:
        return usage_notes.create_note(
            content, kind=kind,
            attachment={"path": str(rel), "name": name, "size": dest.stat().st_size})
    except ValueError as e:
        dest.unlink(missing_ok=True)      # 建记录失败就别留孤儿文件
        raise HTTPException(status_code=422, detail=str(e)) from e


@router.post("/{note_id}/digest")
async def digest_note(note_id: str, request: Request) -> dict:
    """让 AI 凝练这一条。重复调用会重新凝练(用户改了正文之后要能重来)。"""
    from app.config import settings

    note = next((n for n in usage_notes.list_notes() if n.get("id") == note_id), None)
    if not note:
        raise HTTPException(404, "笔记不存在")
    try:
        text = await news_desk.digest_item(note, data_dir=settings.data_dir)
    except Exception as e:  # noqa: BLE001
        # 失败时**什么都不动** —— 文件还在, 用户可以重试。
        # 一张图删了就再也凝练不了, 所以删除只发生在成功之后(见 set_digest)。
        raise HTTPException(400, f"凝练失败: {e}") from e

    # 文本文件: 内容并进正文, 那就是用户要保留的"原文"。图片不留原件。
    raw = None
    att = note.get("attachment") or {}
    if (note.get("kind") == "file") and att.get("path"):
        raw = news_desk.read_attachment_text(settings.data_dir / att["path"])
    updated = usage_notes.set_digest(
        note_id, text["digest"], raw_text=raw,
        horizon=text["horizon"], due_days=text["due_days"])
    if not updated:
        raise HTTPException(404, "笔记不存在")
    return updated


@router.get("/due")
def list_due() -> dict:
    """[R181] 到了兑现检查点、还没给结论的埋伏 —— 界面上要顶到最前面提醒。"""
    return {"items": news_desk.due_theses(usage_notes.list_notes())}


@router.get("/summary")
def get_summary() -> dict:
    """读已存的那一大段总的。没有就返回 null, 不当错误。"""
    return {"summary": news_desk.latest()}


@router.post("/summary")
async def build_summary() -> dict:
    """重新综合成一大段总的。"""
    try:
        return {"summary": await news_desk.synthesize(usage_notes.list_notes())}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, f"综合失败: {e}") from e
