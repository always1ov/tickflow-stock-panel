"""AI 买卖信号(自选决策台 P2)—— 为自选生成结构化操作倾向信号。

与 `stock_analyzer`(客观、明确不给买卖建议)**分开**:本模块专门产出一个明确的
{signal, confidence, reason},仅供用户**个人决策参考**。信号缓存在 signals.json,
供决策台纵览对比。非流式(输出很短),便于批量。
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

from app.config import settings
from app.indicators.levels import compute_levels, summarize_levels
from app.services.stock_analyzer import _clean_rows, _load_kline, _KLINE_KEEP_COLS

logger = logging.getLogger(__name__)

# 喂给信号模型的日 K 窗口(比四维分析短, 控制批量成本)
_SIGNAL_WINDOW = 30
_VALID_SIGNALS = {"buy", "sell", "hold", "watch"}

_SYSTEM_PROMPT = """你是 A 股交易信号助手。基于给定的行情、技术指标与关键价位,为用户**个人参考**给出一个明确的操作倾向信号,并推荐当前最该设「点位提醒」的价位。

**只输出一个 JSON 对象**,不要任何多余文字、解释或 markdown 代码块:
{"signal": "buy|sell|hold|watch", "confidence": 0-100, "reason": "一句话中文理由", "watch_points": [{"direction": "up|down", "price": 数字, "label": "引用的关键价位名", "action": "具体操作", "confidence": 0-100, "reason": "一句话为何盯这个点"}]}

- signal: buy=偏多可关注买入 / sell=偏空可关注卖出 / hold=已持有可继续持有 / watch=观望等待
- confidence: 你对该信号的把握(0-100 整数)
- reason: **一句话**(≤40 字),必须引用具体数值/价位/形态(如「站上 60 日线且放量,近压力位 12.5」)
- watch_points: 从上面「关键价位概览」里挑 **1-3 个**当前最该设提醒的价位:
    · direction=up 表示「涨至该价提醒」(通常上方压力/突破确认位);down 表示「跌至该价提醒」(通常下方支撑/风险位)。
    · price 必须用关键价位里的**实际数值**;label 写对应关键价位名。
    · **action**:到这个价位时**具体该怎么操作**,≤8 字、明确可执行,如「突破关注买入」「站稳可加仓」「跌破止损」「反弹减仓」「支撑企稳观察」;**突出动作,不要含糊**。
    · confidence:对这个点位建议的把握(0-100 整数)。
    · reason:一句话说明为何盯它(结合你的 signal 判断)。
- 客观基于数据,仅供个人参考,不是投资建议。"""


def _store_path() -> Path:
    p = settings.data_dir / "user_data" / "signals.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def load_all() -> dict[str, dict]:
    """返回 {SYMBOL: {signal, confidence, reason, close, created_at}}。"""
    p = _store_path()
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception as e:  # noqa: BLE001
        logger.warning("load signals failed: %s", e)
        return {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _parse_signal(text: str) -> dict | None:
    """从模型输出里抽取 {signal, confidence, reason};非法返回 None。"""
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(obj, dict):
        return None
    sig = str(obj.get("signal", "")).strip().lower()
    if sig not in _VALID_SIGNALS:
        return None
    try:
        conf = int(round(float(obj.get("confidence", 0))))
    except (TypeError, ValueError):
        conf = 0
    conf = max(0, min(100, conf))
    reason = str(obj.get("reason", "")).strip()[:60]

    # watch_points: 从关键价位里挑的推荐提醒点(最多 3 个, 防御性校验)
    points: list[dict] = []
    raw_points = obj.get("watch_points")
    if isinstance(raw_points, list):
        for p in raw_points[:3]:
            if not isinstance(p, dict):
                continue
            d = str(p.get("direction", "")).strip().lower()
            if d not in ("up", "down"):
                continue
            try:
                price = float(p.get("price"))
            except (TypeError, ValueError):
                continue
            if not (price > 0):
                continue
            try:
                p_conf = int(round(float(p.get("confidence", 0))))
            except (TypeError, ValueError):
                p_conf = 0
            points.append({
                "direction": d,
                "price": round(price, 3),
                "label": str(p.get("label", "")).strip()[:20],
                "action": str(p.get("action", "")).strip()[:16],
                "confidence": max(0, min(100, p_conf)),
                "reason": str(p.get("reason", "")).strip()[:60],
            })

    return {"signal": sig, "confidence": conf, "reason": reason, "watch_points": points}


async def generate_signal(repo, data_dir: Path, symbol: str) -> dict:
    """为单只标的生成买卖信号并缓存。返回 {symbol, signal, confidence, reason, close, created_at} 或 {symbol, error}。"""
    sym = (symbol or "").strip().upper()
    df = _load_kline(repo, sym)
    if df.is_empty():
        return {"symbol": sym, "error": "暂无日 K 数据"}

    from app.services.ai_provider import ai_configured, generate_ai_text
    if not ai_configured():
        return {"symbol": sym, "error": "未配置 AI"}

    levels = compute_levels(df)
    close = float(df.tail(1)["close"][0]) if "close" in df.columns else None
    kline_tail = _clean_rows(df.tail(_SIGNAL_WINDOW), _KLINE_KEEP_COLS)
    user_prompt = (
        f"标的: {sym}\n"
        f"关键价位概览: {summarize_levels(levels, close)}\n"
        f"最近 {_SIGNAL_WINDOW} 日 K(JSON,含指标):\n{json.dumps(kline_tail, ensure_ascii=False)}"
    )
    try:
        text = await generate_ai_text(
            [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
            max_tokens=300,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("signal gen failed for %s: %s", sym, e)
        return {"symbol": sym, "error": f"AI 调用失败: {e}"}

    parsed = _parse_signal(text)
    if not parsed:
        return {"symbol": sym, "error": "AI 返回无法解析为信号"}

    entry = {**parsed, "close": close, "created_at": _now_iso()}
    data = load_all()
    data[sym] = entry
    _store_path().write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"symbol": sym, **entry}
