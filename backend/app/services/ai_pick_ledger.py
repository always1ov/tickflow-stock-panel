"""[fork 增强] R121 AI 优选**命中率台账** —— 靠不靠谱, 最后只能用记录说话。

事实校验(today_ai_verify)管的是"这句话是不是编的"; 这里管的是另一半:
**它选的票后来涨了没有**。每天优选落一条, 之后用日线回看 T+1/T+3/T+5 的收益,
累计出胜率与平均收益, 直接贴在优选卡上。

刻意的取舍:
  - **只记, 不预测**。台账不参与选股, 不反馈给提示词 —— 一旦拿历史胜率去
    影响当期选择, 这个数就不再是干净的事后统计了。
  - 收益用**收盘价对收盘价**, 起点是优选生成当日的收盘价。真实交易还有滑点和
    开盘价差, 所以这个数天然偏乐观, 界面上要如实说明。
  - 被校验**驳回**的 pick 不进台账(它压根就没被当成推荐展示)。
  - 一天一条记录, 重复生成覆盖当天 —— 与 today_ai_store 的"今天只有一份"一致。

存 ``user_data/ai_pick_ledger.json``: {"entries": [...]}, 最多保留 240 天。
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime

logger = logging.getLogger(__name__)

MAX_ENTRIES = 240
HORIZONS = (1, 3, 5)      # 回看的交易日数


def _path():
    from app.config import settings
    p = settings.data_dir / "user_data" / "ai_pick_ledger.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _read() -> list[dict]:
    import json
    p = _path()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    entries = data.get("entries") if isinstance(data, dict) else None
    return [e for e in entries if isinstance(e, dict)] if isinstance(entries, list) else []


def _write(entries: list[dict]) -> None:
    from app.services.json_store import atomic_write_json
    try:
        atomic_write_json(_path(), {"entries": entries[-MAX_ENTRIES:]})
    except Exception as e:  # noqa: BLE001
        logger.warning("save ai pick ledger failed: %s", e)


def record(as_of: str | None, picks: list[dict], closes: dict[str, float]) -> dict:
    """记一条当日优选。picks 应是**已校验且未被驳回**的那些。

    closes: {symbol: 当日收盘价} —— 收益的起点, 记下来免得日后复权口径变了对不上。
    """
    from app.services.json_store import lock_for
    day = str(as_of or "").strip()
    if not day:
        return {"ok": False, "error": "缺少日期"}
    rows = [
        {
            "symbol": str(p.get("symbol", "")).upper(),
            "name": p.get("name") or "",
            "reason": str(p.get("reason") or "")[:80],
            "verdict": p.get("verdict") or "",
            "entry_close": closes.get(str(p.get("symbol", "")).upper()),
        }
        for p in picks or []
        if p.get("symbol") and p.get("verdict") != "驳回"
    ]
    entry = {
        "as_of": day,
        "picks": rows,
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    with lock_for(_path()):
        entries = [e for e in _read() if e.get("as_of") != day]   # 当天重复生成 → 覆盖
        entries.append(entry)
        entries.sort(key=lambda e: str(e.get("as_of")))
        _write(entries)
    return {"ok": True, "recorded": len(rows)}


def _forward_returns(repo, symbol: str, as_of: str, entry_close: float | None) -> dict:
    """从 as_of 之后的日线算 T+1/T+3/T+5 收益(收盘对收盘)。数据不够就留空。"""
    out: dict[str, float | None] = {f"t{h}": None for h in HORIZONS}
    if not entry_close:
        return out
    try:
        import polars as pl

        from app.services.stock_analyzer import _load_kline
        df = _load_kline(repo, symbol)     # 与优选送审同一条读取路径, 口径一致
        if df is None or df.is_empty() or "date" not in df.columns:
            return out
        after = df.filter(pl.col("date").cast(pl.Utf8) > as_of).sort("date")
        closes = [c for c in after["close"].to_list() if c is not None]
    except Exception as e:  # noqa: BLE001 —— 回看失败不该影响主流程
        logger.debug("forward return failed for %s: %s", symbol, e)
        return out
    for h in HORIZONS:
        if len(closes) >= h:
            out[f"t{h}"] = round((float(closes[h - 1]) / entry_close - 1) * 100, 2)
    return out


def evaluate(repo, limit: int = 60) -> dict:
    """回看最近 limit 条记录, 返回逐条明细 + 汇总胜率。

    纯读: 只查日线, 不写台账(收益随数据补齐会变, 存下来反而会过期)。
    """
    entries = _read()[-limit:]
    detail: list[dict] = []
    for e in entries:
        day = str(e.get("as_of"))
        for p in e.get("picks") or []:
            rets = _forward_returns(repo, p.get("symbol", ""), day, p.get("entry_close"))
            detail.append({**p, "as_of": day, **rets})

    def _agg(key: str) -> dict:
        vals = [d[key] for d in detail if d.get(key) is not None]
        if not vals:
            return {"n": 0, "win_rate": None, "avg": None}
        wins = len([v for v in vals if v > 0])
        return {
            "n": len(vals),
            "win_rate": round(wins / len(vals) * 100, 1),
            "avg": round(sum(vals) / len(vals), 2),
        }

    return {
        "detail": detail[-60:],
        "stats": {f"t{h}": _agg(f"t{h}") for h in HORIZONS},
        "recorded_days": len(entries),
        # 界面必须原样带上这句 —— 不说清口径的胜率就是误导
        "caveat": "收盘价对收盘价, 未计滑点与开盘价差; 只是事后记录, 不参与选股",
    }
