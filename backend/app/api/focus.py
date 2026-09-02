"""[fork R159] 推送焦点名单 HTTP API。服务层见 services/focus_list.py。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict

from app.services import focus_list, preferences

router = APIRouter(prefix="/api/focus", tags=["focus"])


class OverrideIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    symbol: str
    mode: str | None = None   # pin | mute | null


class PrefsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    focus_only: bool


def _view(request: Request) -> dict:
    from app.services import watchlist
    syms = [str(e.get("symbol", "")).upper() for e in watchlist.list_symbols() if e.get("symbol")]
    names: dict[str, str] = {}
    try:
        repo = request.app.state.repo
        names = {k: str(v) for k, v in (repo.get_name_map(syms) or {}).items()}
    except Exception:  # noqa: BLE001 —— 名字取不到只是显示代码
        pass
    return focus_list.build_view(syms, names)


@router.get("")
def get_focus(request: Request) -> dict:
    return _view(request)


@router.put("/override")
def put_override(payload: OverrideIn, request: Request) -> dict:
    try:
        focus_list.set_override(payload.symbol, payload.mode)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return _view(request)


@router.put("/prefs")
def put_prefs(payload: PrefsIn, request: Request) -> dict:
    preferences.set_push_focus_only(payload.focus_only)
    return _view(request)
