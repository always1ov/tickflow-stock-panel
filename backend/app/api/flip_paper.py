"""[fork 增强] R327 转折模拟盘 HTTP 接口。

替掉 R59 那套「AI 操盘手」的接口。差别不只是换了个算法 —— **这一套没有状态**:

  旧的  每天定时跑一次, 把 AI 给的单子撮合进账本, 账本落盘, 曲线由历史累积
  新的  **每次请求当场从日线重算一遍**, 不落盘、不定时

不落盘是有意的, 不是省事: 这套策略是**纯函数**, 同样的自选 + 同样的阈值 + 同样
的日线, 算出来必然是同一条曲线。落盘反而会带来两个真问题 ——

  · 改了某只票的阈值, 落盘那份就与当前判定对不上了, 而且不会有任何东西报错;
  · 自选加减一只, 历史那一段到底算不算它, 说不清。

当场重算则永远自洽: 你看到的曲线, 就是"按我**现在**这套设置, 过去两年会怎样"。

代价是每次要算几百只票的六态。实测自选规模下是秒级, 且 `get_daily_batch` 一趟
IO —— 真慢到不能忍时再加缓存, 那时缓存键必须包含自选清单与全部阈值。
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query, Request

from app.services import flip_portfolio, flip_portfolio_run

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/flip-paper", tags=["flip-paper"])

MAX_YEARS = 10


@router.get("")
def get_flip_paper(
    request: Request,
    capital: float = Query(flip_portfolio.DEFAULT_CAPITAL, gt=0, description="初始本金"),
    max_positions: int = Query(flip_portfolio.DEFAULT_MAX_POSITIONS, ge=1,
                               le=flip_portfolio.MAX_POSITIONS_CAP,
                               description="同时最多持有几只"),
    years: int = Query(flip_portfolio_run.DEFAULT_YEARS, ge=1, le=MAX_YEARS,
                       description="回溯几年"),
):
    """跑一遍转折模拟盘。标的取当前自选, 阈值取每只票自己的。

    口径见 `flip_portfolio` 模块 docstring —— 界面上那段说明必须与它一致。
    """
    repo = getattr(request.app.state, "repo", None)
    if repo is None:
        raise HTTPException(503, "数据仓库还没就绪")
    try:
        return flip_portfolio_run.run(
            repo, capital=capital, max_positions=max_positions, years=years,
        )
    except Exception as e:  # noqa: BLE001
        logger.exception("转折模拟盘跑失败")
        raise HTTPException(500, f"跑不动: {e}") from e


@router.get("/rules")
def get_rules():
    """界面上那段规则说明 —— **从后端出, 不在前端誊抄一份**。

    前端誊一份的话, 哪天口径改了那份誊抄就开始说假话, 而且不会有任何东西报错
    (R203 那 27 格速查表当初就是为这个理由做成端点的)。
    """
    return {
        "signal": "六态转折日 —— 当天收盘把状态从多头翻到空头, 或反过来",
        "execute": "转折日**当天的收盘价**成交",
        "direction": [
            "转折后在多头侧(上涨趋势 / 自然回升 / 次级回升)→ 买入",
            "转折后在空头侧(下跌趋势 / 自然回撤 / 次级回撤)→ 清仓",
        ],
        "sizing": "等权 —— 每笔目标金额 = 当日净值 ÷ 同时持有上限",
        "universe": "自选股。自选变了, 这条曲线跟着变",
        "short": "不做空。空头段就是空仓 —— A 股散户也做不了",
        "costs": {
            "commission": flip_portfolio.COMMISSION,
            "stamp_tax": flip_portfolio.STAMP_TAX,
            "slippage_bps": flip_portfolio.SLIPPAGE_BPS,
            "lot": flip_portfolio.LOT,
        },
        "caveat": (
            "「当天收盘价成交」的前提是**你能在尾盘按收盘价附近成交** —— "
            "系统每天给出 flip_up / flip_down 两个触发价, 开盘前就定死了, "
            "盘中盯着价格接近哪一条, 14:55 挂单就能做到。"
            "这不是「预知收盘」。滑点照扣。"
        ),
        "vs_flip_trades": (
            "复盘页那份「按转折买卖」用的是**次日开盘价**, 两份差的是隔夜跳空。"
            "这里问「尾盘做能拿到什么」, 那里问「第二天做能拿到什么」。"
        ),
        "why_no_state": (
            "这套不落盘、不定时 —— 每次打开当场从日线重算。"
            "同样的自选 + 阈值 + 日线, 必然是同一条曲线; "
            "落盘反而会在你改阈值或加减自选之后, 与当前判定对不上。"
        ),
    }
