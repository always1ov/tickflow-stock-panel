"""[fork 增强] R117 外部网页抓取模式 HTTP API(独立模块, 不进能力路由)。"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.services import external_fetch, external_view

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/external-page", tags=["external-page"])


class ViewIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # 都可省略: 省略就用设置里存的那份(设置页的「试运行」会传还没保存的值)
    url: str | None = Field(default=None, max_length=2048)
    hint: str | None = Field(default=None, max_length=2000)
    force: bool = False   # True = 跳过原文缓存与 AI 结果缓存, 重新解析一次


def _resolve(payload: ViewIn) -> tuple[str, str]:
    from app.services import preferences
    cfg = preferences.get_external_page_config()
    url = (payload.url or "").strip() or cfg["external_page_url"]
    hint = payload.hint if payload.hint is not None else cfg["external_page_ai_hint"]
    if not url:
        raise HTTPException(status_code=400, detail="还没有配置网站地址")
    return url, hint or ""


@router.post("/view")
async def view(payload: ViewIn) -> dict:
    """抓页面 + 让面板自己的 AI 整理成固定结构。原文没变时直接回缓存。"""
    url, hint = _resolve(payload)
    try:
        return await external_view.build_view(url, hint, force=payload.force)
    except external_fetch.FetchError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:  # noqa: BLE001 —— AI 调用失败要明说, 不能静默 200
        logger.warning("external page view failed: %s", e)
        raise HTTPException(status_code=502, detail=f"AI 解析失败: {e}") from e


@router.post("/raw")
def raw(payload: ViewIn) -> dict:
    """只抓原文不调 AI —— 设置页用它确认"地址能不能抓通、抓回来长什么样"。"""
    url, _ = _resolve(payload)
    try:
        got = external_fetch.fetch(url, force=payload.force)
    except external_fetch.FetchError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    preview = external_view.clean_source(got["text"], got.get("content_type", ""))
    return {
        "ok": True,
        "url": got["url"],
        "status": got["status"],
        "content_type": got["content_type"],
        "bytes": got["bytes"],
        "fetched_at": got["fetched_at"],
        # 只回清洗后的前 4000 字: 设置页是给人看一眼, 不需要整页
        "preview": preview[:4000],
        "source_chars": len(preview),
    }
