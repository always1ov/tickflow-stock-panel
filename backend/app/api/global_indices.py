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
    keys = [k for k in raw if k in valid]
    # [R116/R149] 老选择里可能只剩已删除的指数(日经/恒生/道指/标普/韩国综合) —— 全被过滤掉
    # 就回落默认, 免得用户卡在"一张卡片都没有"。主动清空(存了空列表)时 raw
    # 本身为空, 不触发回落, 关得掉。
    if raw and not keys:
        return list(global_indices.DEFAULT_KEYS)
    return keys


@router.get("")
def quotes() -> dict:
    """当前所选全球指数的最新行情(服务端 TTL 合并, 失败回旧值/空)。"""
    return {"items": global_indices.get_quotes(_selected_keys())}


@router.get("/options")
def options() -> dict:
    return {"presets": global_indices.list_presets(), "selected": _selected_keys()}


@router.get("/debug")
def debug() -> dict:
    """诊断: 直连上游一次, 回原始行与解析结果。卡片不显示时打开这个看哪一步断了。"""
    return global_indices.debug_fetch(_selected_keys())


@router.get("/tickflow-probe")
def tickflow_probe() -> dict:
    """[R119/R149] 问 TickFlow: 纳指报价你给不给 —— 给了它就是侧栏那个数的源。

    看 `nasdaq_resolved`(代码根在合约清单里对上了哪个 symbol)与 `nasdaq_quote`
    (那个 symbol 真拿到报价没有)。不给也无妨, 自动回落 sina/腾讯。
    """
    return global_indices.tickflow_probe()


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
