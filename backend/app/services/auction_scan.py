"""[fork 增强] R110 竞价一进二扫描 — 昨日首板 × 今日竞价表现。

做什么: 9:15-9:25 竞价阶段, 把"昨日首板"名单与当下竞价快照交叉, 按四个维度
打分, 给出今日最可能二连板的候选。

为什么放在异动监控的「竞价异动」标签: 那一栏本来就是盘前观察位, 原有的
「全市场竞价扫描」是个占位卡(采集任务从未落地), 这里把它填成真东西。

数据来源与口径(**每一项都标明出处, 不含猜测**):
  - 昨日首板: enriched 预计算列 signal_limit_up + consecutive_limit_ups == 1
    (与连板梯队同一口径, 不另算涨停); 仅主板(60/00 开头), 剔除 ST/退市。
  - 今日竞价: 实时数据源的全市场快照(fuyao/TickFlow 均可)。竞价撮合阶段
    last_price=竞价参考价、volume=竞价累计撮合量。
  - 昨日量能/换手: enriched 的昨日行。

评分(满分 100) —— 与"开盘啦"那套的差别必须说清楚:
  - 竞价涨幅 35: **温和高开给高分**(3~6% 最优), 高开 >9% 反而扣分 ——
    本面板 60 日回测结论就是"高开 ≥5% 子集当日 -1.97%, 追高是陷阱"
    (见 services/auction_benchmark 与异动监控页脚注), 不照抄外部"越高越好"。
  - 竞价量能 30: 竞价撮合量 / 昨日全天成交量。竞价就放出昨日 3%+ 的量
    说明资金抢筹意愿强。
  - 昨日封板质量 20: **替代口径** —— 真封单质量要五档盘口(depth5,
    TickFlow Expert 专有), 本 fork 免费档 + fuyao 都没有, 故改用昨日
    换手率与是否一字板近似, 并在返回里标 quality_proxy=True 明示。
  - 市场情绪 15: 昨日首板总家数 —— 首板成群才有接力土壤, 冰点时二板多是
    独苗。(外部那套用"板块地位", 需概念映射; 本 fork 不对用户的扩展数据源
    做硬依赖, 改用必然可得的首板宽度, 口径在返回里写明。)

竞价数据无历史接口(fuyao/TickFlow 都只有当下快照), 所以扫描结果按日落盘
积累: data/user_data/auction_scan/YYYY-MM-DD.json, 从启用之日起有历史。
"""
from __future__ import annotations

import json
import logging
from datetime import date as date_cls
from pathlib import Path
from typing import Any

import polars as pl

from app.services.json_store import atomic_write_json, lock_for

logger = logging.getLogger(__name__)

MAX_CANDIDATES = 30          # 榜单上限: 首板通常几十只, 取分高的
_MIN_AUCTION_PCT = -3.0      # 竞价跌超 3% 直接出局(低开破位, 二板无从谈起)


def _dir(data_dir: Path) -> Path:
    return data_dir / "user_data" / "auction_scan"


def _path(data_dir: Path, d: date_cls) -> Path:
    return _dir(data_dir) / f"{d.isoformat()}.json"


def _is_main_board(symbol: str) -> bool:
    """仅主板: 60/00 开头。剔除创业板(300/301)、科创(688)、北交所(4/8)。

    一进二战法针对主板 10% 涨停; 20% 涨跌幅的双创节奏完全不同, 混在一起
    评分没有可比性。
    """
    code = symbol.split(".")[0]
    return code.startswith(("60", "00")) and not code.startswith("003")


def first_boards(repo: Any) -> tuple[list[dict], date_cls | None]:
    """昨日首板名单(主板, 非 ST)。返回 (行, 该日期)。

    口径与连板梯队一致: enriched 的 signal_limit_up 且 consecutive_limit_ups==1。
    """
    try:
        df, d = repo.get_enriched_latest()
    except Exception as e:  # noqa: BLE001
        logger.warning("auction_scan: 读 enriched 失败: %s", e)
        return [], None
    if df is None or df.is_empty() or d is None:
        return [], d

    need = {"symbol", "signal_limit_up", "consecutive_limit_ups", "close"}
    if not need.issubset(set(df.columns)):
        logger.warning("auction_scan: enriched 缺列 %s", need - set(df.columns))
        return [], d

    keep = [c for c in [
        "symbol", "name", "close", "volume", "amount", "turnover_rate",
        "open", "high", "low", "prev_close",
    ] if c in df.columns]
    rows = (
        df.filter(
            pl.col("signal_limit_up").fill_null(False)
            & (pl.col("consecutive_limit_ups").fill_null(0) == 1),
        )
        .select(keep)
        .to_dicts()
    )
    out = []
    for r in rows:
        sym = str(r.get("symbol") or "")
        nm = str(r.get("name") or "")
        if not _is_main_board(sym):
            continue
        if "ST" in nm.upper() or "退" in nm:
            continue
        out.append(r)
    return out, d


def _quality_proxy(row: dict) -> tuple[float, str]:
    """昨日封板质量的**替代**评分(0~20) —— 无五档盘口时的近似。

    真口径要封单量/封成比(depth5), 这里用能拿到的量价特征:
      - 一字板(最低价=涨停价): 封板最强, 但次日买不到 → 给高分并在文案里点破
      - 换手率适中(3~15%): 有承接又没炸开, 最健康
      - 换手率过低(<1%, 多为一字)或过高(>25%, 巨量换手风险)酌减
    """
    close = row.get("close")
    low = row.get("low")
    turnover = row.get("turnover_rate")
    one_word = close is not None and low is not None and abs(float(low) - float(close)) < 1e-6
    if one_word:
        return 18.0, "昨日一字封板(最强, 但今日多半买不到)"
    if turnover is None:
        return 8.0, "昨日换手数据缺失"
    t = float(turnover) * (100 if float(turnover) < 1 else 1)   # 兼容小数制/百分数制
    if 3 <= t <= 15:
        return 16.0, f"昨日换手 {t:.1f}% — 有承接且没炸开"
    if 1 <= t < 3:
        return 12.0, f"昨日换手 {t:.1f}% — 偏低, 封板较硬"
    if 15 < t <= 25:
        return 10.0, f"昨日换手 {t:.1f}% — 换手偏大, 分歧明显"
    if t < 1:
        return 11.0, f"昨日换手 {t:.1f}% — 极低换手(接近一字)"
    return 5.0, f"昨日换手 {t:.1f}% — 巨量换手, 抛压重"


def _pct_score(auction_pct: float) -> tuple[float, str]:
    """竞价涨幅评分(0~35)。温和高开最优 —— 本面板回测: 高开≥5%当日 -1.97%。"""
    p = auction_pct
    if p < 0:
        return max(0.0, 12 + p * 3), f"竞价低开 {p:.2f}% — 昨日封板资金没接住"
    if p < 1:
        return 16.0, f"竞价平开 {p:.2f}% — 分歧, 看开盘后承接"
    if 1 <= p < 3:
        return 28.0, f"竞价小幅高开 {p:.2f}% — 温和, 空间足"
    if 3 <= p <= 6:
        return 35.0, f"竞价高开 {p:.2f}% — 最优区间(有资金但不透支空间)"
    if 6 < p <= 9:
        return 24.0, f"竞价高开 {p:.2f}% — 偏高, 空间被压缩"
    return 10.0, f"竞价高开 {p:.2f}% — 追高陷阱区(本面板回测: 高开≥5%当日均值为负)"


def _volume_score(auction_vol: float | None, prev_vol: float | None) -> tuple[float, str]:
    """竞价量能评分(0~30): 竞价撮合量 / 昨日全天成交量。"""
    if not auction_vol or not prev_vol or prev_vol <= 0:
        return 8.0, "竞价量能数据缺失"
    ratio = auction_vol / prev_vol
    pct = ratio * 100
    if ratio >= 0.06:
        return 30.0, f"竞价量达昨日 {pct:.1f}% — 抢筹明显"
    if ratio >= 0.03:
        return 24.0, f"竞价量达昨日 {pct:.1f}% — 量能充足"
    if ratio >= 0.015:
        return 16.0, f"竞价量达昨日 {pct:.1f}% — 量能一般"
    return 8.0, f"竞价量仅昨日 {pct:.1f}% — 无人抢筹"


def scan(repo: Any, provider_rows: list[dict]) -> dict:
    """执行一次竞价扫描。provider_rows 为全市场快照(调用方提供, 保持插件边界)。"""
    boards, board_date = first_boards(repo)
    if not boards:
        return {
            "as_of": board_date.isoformat() if board_date else None,
            "candidates": [], "total_first_boards": 0,
            "error": "昨日没有主板首板 —— 一进二无候选(或 enriched 数据未就绪)",
        }

    quote_by_symbol = {str(r.get("symbol") or ""): r for r in provider_rows}
    # 市场情绪(替代"板块地位"): 昨日首板家数 —— 首板成群说明赚钱效应在,
    # 一进二的土壤才成立; 首板寥寥时二板多半是独苗孤军。
    # (真正的"同板块家数"要概念映射, 依赖用户配的扩展数据源, 不做硬依赖)
    n_boards = len(boards)
    if n_boards >= 40:
        s_sector, why_sector = 15.0, f"昨日首板 {n_boards} 家 — 赚钱效应强, 接力土壤好"
    elif n_boards >= 20:
        s_sector, why_sector = 11.0, f"昨日首板 {n_boards} 家 — 情绪中性偏暖"
    elif n_boards >= 10:
        s_sector, why_sector = 7.0, f"昨日首板 {n_boards} 家 — 情绪一般, 接力谨慎"
    else:
        s_sector, why_sector = 3.0, f"昨日首板仅 {n_boards} 家 — 冰点, 二板多为独苗"

    out: list[dict] = []
    for b in boards:
        sym = str(b.get("symbol") or "")
        q = quote_by_symbol.get(sym)
        if not q:
            continue
        last = q.get("last_price") or q.get("close")
        prev_close = b.get("close")     # 昨日收盘(即昨日涨停价)
        if last is None or not prev_close:
            continue
        auction_pct = (float(last) - float(prev_close)) / float(prev_close) * 100
        if auction_pct < _MIN_AUCTION_PCT:
            continue

        s_pct, why_pct = _pct_score(auction_pct)
        s_vol, why_vol = _volume_score(q.get("volume"), b.get("volume"))
        s_q, why_q = _quality_proxy(b)
        out.append({
            "symbol": sym,
            "name": b.get("name") or sym,
            "score": round(s_pct + s_vol + s_q + s_sector),
            "auction_pct": round(auction_pct, 2),
            "auction_volume": q.get("volume"),
            "prev_volume": b.get("volume"),
            "prev_close": prev_close,
            "auction_price": last,

            "breakdown": [
                {"dim": "竞价涨幅", "score": round(s_pct), "max": 35, "note": why_pct},
                {"dim": "竞价量能", "score": round(s_vol), "max": 30, "note": why_vol},
                {"dim": "封板质量", "score": round(s_q), "max": 20, "note": why_q, "proxy": True},
                {"dim": "市场情绪", "score": round(s_sector), "max": 15, "note": why_sector},
            ],
        })

    out.sort(key=lambda r: r["score"], reverse=True)
    return {
        "as_of": board_date.isoformat() if board_date else None,
        "total_first_boards": len(boards),
        "matched": len(out),
        "candidates": out[:MAX_CANDIDATES],
        "quality_proxy": True,   # 封板质量为替代口径(无五档盘口), 前端据此标注
    }


def save_scan(data_dir: Path, payload: dict, d: date_cls) -> None:
    """按日落盘(竞价无历史接口, 从启用之日起积累)。"""
    p = _path(data_dir, d)
    p.parent.mkdir(parents=True, exist_ok=True)
    with lock_for(p):
        atomic_write_json(p, payload)


def load_scan(data_dir: Path, d: date_cls) -> dict | None:
    p = _path(data_dir, d)
    if not p.exists():
        return None
    try:
        with lock_for(p):
            return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def list_scan_dates(data_dir: Path, limit: int = 30) -> list[str]:
    d = _dir(data_dir)
    if not d.exists():
        return []
    return sorted((p.stem for p in d.glob("*.json")), reverse=True)[:limit]
