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

_SYSTEM_PROMPT = """你是一位拥有 15 年 A 股一线交易经验的信号分析师,擅长从量价、关键价位与趋势结构中提炼**可执行的条件计划**。你的任务是:基于给定数据,为用户**个人决策参考**输出一个明确的操作倾向信号 + 上下两个方向的到价预案。

## 输出规范

**只输出一个 JSON 对象**,不要任何多余文字、解释或 markdown 代码块:
{"signal": "buy|sell|hold|watch", "confidence": 0-100, "reason": "一句话中文理由", "watch_points": [{"direction": "up|down", "price": 数字, "label": "引用的关键价位名", "action": "具体操作", "confidence": 0-100, "reason": "一句话为何盯这个点"}]}

- signal: buy=偏多可关注买入 / sell=偏空可关注卖出 / hold=已持有可继续持有 / watch=观望等待
- reason: **一句话**(≤40 字),先给依据后给预案,**必须点明下一步触发条件**
  (如「RSI 超买贴上轨,回落 17.5 企稳再接;上破 17.96 转追」)
- watch_points: 从「关键价位概览」里挑 **1-3 个**最该设「点位提醒」的价位:
    · direction=up 涨至提醒(压力/突破确认位);down 跌至提醒(支撑/风险位)
    · price 必须用关键价位里的**实际数值**,label 写对应价位名
    · **action ≤8 字、动作明确可执行**:如「突破关注买入」「站稳可加仓」「跌破止损」「反弹减仓」;不许含糊

## 信号纪律(务必遵守)

1. **数据说话**:每个判断引用具体数值/价位/形态,严禁空泛套话(「走势偏强」必须改成「连续 3 日站稳 20 日线且放量」)
2. **敢于表态**:多空条件明确时必须给出对应倾向;**watch 只在多空证据真正矛盾或都不成熟时使用,禁止因保守而滥用**——但凡存在明确触发条件,就给倾向信号并把条件写进 watch_points
3. **趋势为纲**:提供了六态趋势(利弗莫尔)时,以其为方向前提——顺趋势信号常规证据即可,**逆趋势信号需要更强的量价证据**,并在 reason 里说明为何逆势
4. **风险入置信度**:超买/超卖、量价背离、临近关键压力等风险因素,体现在调低 confidence 和收紧 watch_points,而不是一律退回观望
5. **预案完备**:只要关键价位存在,watch_points **必须至少给 1 个 up + 1 个 down**——上方到哪做什么、下方到哪做什么,到价时用户不至于毫无准备
6. **价位精确**:预案价位必须落到给定关键价位的具体数值,不许自造价格
7. **持仓出场线优先**:若提供了「持仓出场线」(系统按 ATR 三阶段规则算好的止损线/保本线/移动止盈线),
   watch_points **必须包含该线作为 down 方向预案**,action 按其阶段用「跌破止损」「保本离场」或「止盈了结」;
   该线是确定性计算结果,你不得修改其数值,只能围绕它解释与补充其他预案
8. **生命线不可动摇**:若提供了「生命线」,这是用户亲划的绝对底线。已跌破生命线时 signal 必须为 sell,
   reason 必须明确"纪律性清仓离场",**禁止任何"再观察""等反弹"类表述**;未跌破时不得建议把仓位风险
   放到生命线之下

仅供用户个人决策参考,不构成投资建议。"""


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


# 部分厂家模型会用中文回信号词 —— 宽进严出, 映射回标准值
_SIGNAL_ALIASES = {
    "买入": "buy", "买": "buy", "卖出": "sell", "卖": "sell",
    "持有": "hold", "观望": "watch", "观察": "watch",
}


def _parse_signal(text: str) -> dict | None:
    """从模型输出里抽取 {signal, confidence, reason};非法返回 None。

    [R22] 解析走跨厂家容错器(围栏/解说文字/截断都能救), 信号词兼容中文。
    """
    from app.services.ai_json import extract_json_object
    obj = extract_json_object(text)
    if obj is None:
        return None
    sig = str(obj.get("signal", "")).strip().lower()
    sig = _SIGNAL_ALIASES.get(sig, sig)
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
    # [fork 增强] 六态趋势作为方向锚喂给信号 AI(零额外成本,失败静默跳过)
    trend_line = ""
    try:
        from app.services.livermore_service import trend_for_symbol
        t = trend_for_symbol(repo, sym)
        if "error" not in t:
            trend_line = (
                f"六态趋势(利弗莫尔): {t['state_cn']} 第{t['duration']}天"
                f", 上关键点 {t['up_pivot'] if t['up_pivot'] is not None else '—'}"
                f", 下关键点 {t['dn_pivot'] if t['dn_pivot'] is not None else '—'}"
                f", 参考动作: {t['action']}\n"
            )
    except Exception as e:  # noqa: BLE001
        logger.debug("trend context for signal skipped: %s", e)
    # [fork 增强] 持仓出场线上下文(仅持有+已填成本时有;规则算好, AI 不得改数值)
    exit_line = ""
    try:
        from app.services.position_exit import exit_for_symbol
        ex = exit_for_symbol(repo, sym)
        if ex:
            life_label = "生命线(20日线)" if ex.get("lifeline_src") == "ma20" else "生命线"
            life_part = (
                f"; {life_label} {ex['lifeline']}(用户绝对底线, 跌破必须无条件清仓离场)"
                if ex.get("lifeline") else ""
            )
            exit_line = (
                f"持仓出场线: 成本 {ex['cost']}, 浮盈 {ex['profit_atr']}×ATR, {ex['stage_cn']},"
                f" {ex['line_cn']} {ex['line']}(跌破则{ex['action']}; ATR14={ex['atr']},"
                f" 持仓最高收盘 {ex['highest_close']}, k={ex['k']}){life_part}\n"
            )
    except Exception as e:  # noqa: BLE001
        logger.debug("exit context for signal skipped: %s", e)
    user_prompt = (
        f"标的: {sym}\n"
        f"{trend_line}"
        f"{exit_line}"
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
            max_tokens=2000,  # [R22] 思考型模型(<think>)先烧一段推理 token, 上限太小时
                              # JSON 正文根本没机会输出 → "无法解析"; 普通模型不受影响
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("signal gen failed for %s: %s", sym, e)
        return {"symbol": sym, "error": f"AI 调用失败: {e}"}

    parsed = _parse_signal(text)
    if not parsed:
        snippet = (text or "").replace("\n", " ").strip()[:100]
        return {"symbol": sym,
                "error": f"AI 返回无法解析为信号(原文开头: {snippet or '空'}…)——可重试或换模型"}

    entry = {**parsed, "close": close, "created_at": _now_iso()}
    data = load_all()
    data[sym] = entry
    _store_path().write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"symbol": sym, **entry}
