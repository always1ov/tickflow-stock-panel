"""[fork 增强] R99 全球指数实时 HTTP API(独立模块, 不进能力路由)。"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from app.services import global_indices

router = APIRouter(prefix="/api/global-indices", tags=["global-indices"])


def _selected_keys() -> list[str]:
    from app.services import preferences
    raw = preferences.load().get("global_index_keys")
    if not isinstance(raw, list):
        return list(global_indices.DEFAULT_KEYS)
    valid = {p["key"] for p in global_indices.list_presets()}
    return [k for k in raw if k in valid]


@router.get("")
def quotes() -> dict:
    """当前所选全球指数的最新行情(服务端 TTL 合并, 失败回旧值/空)。"""
    return {"items": global_indices.get_quotes(_selected_keys())}


@router.get("/options")
def options() -> dict:
    return {"presets": global_indices.list_presets(), "selected": _selected_keys()}


class SelectionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    keys: list[str] = Field(max_length=12)


@router.put("/selection")
def save_selection(payload: SelectionIn) -> dict:
    from app.services import preferences
    valid = {p["key"] for p in global_indices.list_presets()}
    keys = [k for k in payload.keys if k in valid]
    preferences.save({"global_index_keys": keys})
    return {"selected": keys}
