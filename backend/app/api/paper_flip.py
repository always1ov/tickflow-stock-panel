"""[fork 增强] R562 虚拟账户「跟六态转折」—— 页面那一块的数据。

规则本身走作者的自动跟单接口(`/api/paper/auto_rules`, match_kind = flip);
这里只给页面上那一块要读的东西。口径见 services/flip_follow 模块 docstring。
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query, Request

from app.services import flip_follow_run
from app.strategy import paper

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/paper/flip", tags=["paper"])


@router.get("")
def get_panel(request: Request, account: str = Query(paper.DEFAULT_ACCOUNT_ID)):
    repo = getattr(request.app.state, "repo", None)
    if repo is None:
        raise HTTPException(503, "数据仓库还没就绪")
    try:
        acc = paper.validate_account_id(account)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return flip_follow_run.panel(repo, acc)


@router.get("/defaults")
def get_defaults():
    """新建转折账户 / 规则时的默认值 —— 费率只在 flip_follow.FEES 一处, 前端不另写一份。"""
    from app.services import flip_follow as ff
    return {"fees": ff.FEES, "max_positions": ff.DEFAULT_MAX_POSITIONS, "cap": ff.MAX_POSITIONS_CAP}
