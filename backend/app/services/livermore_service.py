"""[fork 增强] 六态趋势服务 —— 阈值存储 + 趋势查询 + 回测调参(可选 AI 顾问)。

阈值存储:`data/user_data/livermore.json`
  {"default": 0.06, "overrides": {SYMBOL: {"threshold": 0.08, "source": "ai|manual|rule", "updated_at": iso}}}
纯本地、非敏感,与 positions.json 同款 merge-write 模式。

窗口:近 180 个交易日(用户指定口径)。趋势与回测共用同一窗口保持一致。
数据:仓库日线 close(复权口径,与关键价位/图表同源)。
AI 只当"调参顾问":网格回测是纯函数零成本,AI 拿指标表选参数,一次调用;
未配 AI 时规则建议兜底,功能不残缺。
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import polars as pl

from app.config import settings
from app.indicators.livermore import (
    BULLISH,
    DEFAULT_THRESHOLD,
    GRID_THRESHOLDS,
    STATE_ACTION,
    STATE_LABELS,
    backtest_thresholds,
    compute,
    rule_suggest,
    side_segments,
    signal_kind,
)

logger = logging.getLogger(__name__)

WINDOW_TRADING_DAYS = 180
# 180 交易日 ≈ 260+ 日历日,留足节假日余量
_CALENDAR_SPAN_DAYS = 320
# 状态转换在 N 天内视为"新信号"(转多/转空/回升/回撤徽章)
SIGNAL_FRESH_DAYS = 5
_MIN_DAYS = 40


# ================================================================
# 阈值存储
# ================================================================

def _store_path() -> Path:
    p = settings.data_dir / "user_data" / "livermore.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _load_store() -> dict:
    p = _store_path()
    if not p.exists():
        return {"default": DEFAULT_THRESHOLD, "overrides": {}}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("bad store")
        data.setdefault("default", DEFAULT_THRESHOLD)
        data.setdefault("overrides", {})
        return data
    except Exception as e:  # noqa: BLE001
        logger.warning("load livermore store failed: %s", e)
        return {"default": DEFAULT_THRESHOLD, "overrides": {}}


def _save_store(data: dict) -> None:
    _store_path().write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _clamp(t: float) -> float:
    return max(0.01, min(0.30, round(float(t), 4)))


def get_effective_threshold(symbol: str) -> tuple[float, str]:
    """返回 (生效阈值, 来源) —— 来源: override / default。"""
    store = _load_store()
    ov = store["overrides"].get((symbol or "").strip().upper())
    if ov and isinstance(ov, dict) and ov.get("threshold"):
        return _clamp(ov["threshold"]), "override"
    return _clamp(store.get("default", DEFAULT_THRESHOLD)), "default"


def set_threshold(symbol: str, threshold: float | None, source: str = "manual") -> dict:
    """设置/清除某只票的阈值覆盖;symbol 为空则改全局默认。threshold=None 清除覆盖。"""
    store = _load_store()
    sym = (symbol or "").strip().upper()
    if not sym:
        if threshold is None:
            raise ValueError("默认阈值不可清除")
        store["default"] = _clamp(threshold)
    elif threshold is None:
        store["overrides"].pop(sym, None)
    else:
        store["overrides"][sym] = {
            "threshold": _clamp(threshold),
            "source": source,
            "updated_at": _now_iso(),
        }
    _save_store(store)
    eff, src = get_effective_threshold(sym) if sym else (store["default"], "default")
    return {"symbol": sym or None, "threshold": eff, "source": src}


# ================================================================
# 数据装载
# ================================================================

def _closes_window(df: pl.DataFrame) -> tuple[list[float], list[str]]:
    """从日线 df 提取近 WINDOW_TRADING_DAYS 的 (closes, dates),升序、去 null。"""
    if df.is_empty() or "close" not in df.columns or "date" not in df.columns:
        return [], []
    df = df.select("date", "close").drop_nulls().sort("date").tail(WINDOW_TRADING_DAYS)
    return [float(c) for c in df["close"]], [str(d) for d in df["date"]]


def _load_symbol_window(repo, symbol: str) -> tuple[list[float], list[str]]:
    end = date.today()
    start = end - timedelta(days=_CALENDAR_SPAN_DAYS)
    df = repo.get_daily_asset(repo.resolve_asset_type(symbol), symbol, start, end,
                              columns=["date", "close"])
    return _closes_window(df)


# ================================================================
# 趋势查询
# ================================================================

def _trend_payload(closes: list[float], dates: list[str], threshold: float, source: str) -> dict:
    res = compute(closes, dates, threshold)
    last = res["last"]
    st = last["state"]
    cn, en = STATE_LABELS.get(st, (st or "—", ""))
    kind = signal_kind(res) if res["duration"] <= SIGNAL_FRESH_DAYS else None
    frm_cn = STATE_LABELS.get(res["entered_from"], (None,))[0] if res["entered_from"] else None
    return {
        "state": st,
        "state_cn": cn,
        "state_en": en,
        "action": STATE_ACTION.get(st, ""),
        "side": "多头" if st in BULLISH else "空头",
        "duration": res["duration"],
        "since": res["since"],
        "entered_from": res["entered_from"],
        "entered_from_cn": frm_cn,
        "up_pivot": last["up_pivot"],
        "dn_pivot": last["dn_pivot"],
        "close": last["close"],
        "as_of": last["date"],
        "signal": kind[0] if kind else None,
        "signal_desc": kind[1] if kind else None,
        "threshold": threshold,
        "threshold_source": source,
        "window_days": len(closes),
    }


def trend_for_symbol(repo, symbol: str, with_segments: bool = False) -> dict:
    """单只趋势详情。with_segments=True 附带多空分段(K 线背景着色用)。"""
    sym = (symbol or "").strip().upper()
    closes, dates = _load_symbol_window(repo, sym)
    if len(closes) < _MIN_DAYS:
        return {"symbol": sym, "error": f"日 K 不足 {_MIN_DAYS} 天,无法判定趋势"}
    thr, src = get_effective_threshold(sym)
    out = {"symbol": sym, **_trend_payload(closes, dates, thr, src)}
    if with_segments:
        res = compute(closes, dates, thr)
        out["segments"] = [
            {"side": s["side"], "start_date": s["start_date"], "end_date": s["end_date"]}
            for s in side_segments(res["steps"])
        ]
    return out


def trends_for_symbols(repo, symbols: list[str]) -> dict[str, dict]:
    """批量趋势(决策台「趋势」列)。股票走一次批量 scan;ETF/指数逐只回退。"""
    out: dict[str, dict] = {}
    syms = [s.strip().upper() for s in symbols if s and s.strip()]
    if not syms:
        return out
    stock_syms = [s for s in syms if repo.resolve_asset_type(s) == "stock"]
    other_syms = [s for s in syms if s not in stock_syms]

    if stock_syms:
        end = date.today()
        start = end - timedelta(days=_CALENDAR_SPAN_DAYS)
        try:
            df = repo.get_daily_batch(stock_syms, start, end, ["symbol", "date", "close"])
        except Exception as e:  # noqa: BLE001
            logger.warning("livermore batch daily failed: %s", e)
            df = pl.DataFrame()
        if not df.is_empty():
            for sym, part in df.group_by("symbol"):
                key = str(sym[0] if isinstance(sym, tuple) else sym)
                closes, dts = _closes_window(part)
                if len(closes) < _MIN_DAYS:
                    continue
                thr, src = get_effective_threshold(key)
                out[key] = _trend_payload(closes, dts, thr, src)

    for sym in other_syms:
        try:
            r = trend_for_symbol(repo, sym)
            if "error" not in r:
                r.pop("symbol", None)
                out[sym] = r
        except Exception as e:  # noqa: BLE001
            logger.debug("livermore trend for %s failed: %s", sym, e)
    return out


# ================================================================
# 回测调参(网格 + 规则建议 + 可选 AI 顾问)
# ================================================================

def _price_limit_hint(symbol: str) -> str:
    code = symbol.split(".")[0]
    if code.startswith(("30", "68")):
        return "20%(创业板/科创板)"
    if symbol.endswith(".BJ"):
        return "30%(北交所)"
    return "10%(主板)"


def _annualized_vol(closes: list[float]) -> float | None:
    if len(closes) < 20:
        return None
    rets = [closes[i] / closes[i - 1] - 1.0 for i in range(1, len(closes))]
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
    return round((var ** 0.5) * (252 ** 0.5), 4)


_AI_SYSTEM_PROMPT = (
    "你是量化调参顾问。用户对一只 A 股用利弗莫尔六态状态机做趋势判定,"
    "需要为回撤/回升阈值选一个稳健值。你会收到阈值网格回测指标表(近180交易日)。\n"
    "选择原则:\n"
    "1. 警惕过拟合:不许选指标表上孤立的尖峰最优值,优先选表现平台期(与相邻阈值表现接近)的稳健值;\n"
    "2. 前/后半段收益不一致的阈值降权;\n"
    "3. 假信号率与翻转次数过高说明阈值对该票太敏感;平均段持续过长、翻转过少说明太迟钝;\n"
    "4. 结合该票波动率与涨跌幅限制:高波动票通常需要更大阈值;\n"
    "5. 多头段样本不足(普遍<2段)时明说样本不足,建议默认值 0.06 附近,置信度给低。\n"
    "只输出一个 JSON 对象,不要任何其他文字:"
    '{"threshold": 0.08, "confidence": 75, "reason": "80字内的中文理由"}\n'
    "threshold 必须取自指标表中出现过的阈值。"
)


async def run_backtest(repo, symbol: str, use_ai: bool = True) -> dict:
    """阈值网格回测:返回指标表 + 规则建议 + (可选)AI 推荐。"""
    sym = (symbol or "").strip().upper()
    closes, dates = _load_symbol_window(repo, sym)
    if len(closes) < _MIN_DAYS:
        return {"symbol": sym, "error": f"日 K 不足 {_MIN_DAYS} 天,无法回测"}

    rows = backtest_thresholds(closes, dates)
    rule = rule_suggest(rows)
    cur, cur_src = get_effective_threshold(sym)
    out: dict = {
        "symbol": sym,
        "window_days": len(closes),
        "from": dates[0],
        "to": dates[-1],
        "grid": rows,
        "rule_suggestion": rule,
        "current_threshold": cur,
        "current_source": cur_src,
        "ai": None,
    }

    if not use_ai:
        return out
    from app.services.ai_provider import ai_configured, generate_ai_text
    if not ai_configured():
        out["ai_error"] = "未配置 AI(规则建议仍可用)"
        return out

    meta = {
        "symbol": sym,
        "annualized_vol": _annualized_vol(closes),
        "price_limit": _price_limit_hint(sym),
        "current_threshold": cur,
    }
    user_prompt = (
        f"标的信息: {json.dumps(meta, ensure_ascii=False)}\n"
        f"阈值网格回测指标表(JSON 数组,收益均为小数):\n"
        f"{json.dumps(rows, ensure_ascii=False)}"
    )
    try:
        text = await generate_ai_text(
            [
                {"role": "system", "content": _AI_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
            max_tokens=300,
        )
        out["ai"] = _parse_ai_reco(text)
        if out["ai"] is None:
            out["ai_error"] = "AI 返回无法解析"
    except Exception as e:  # noqa: BLE001
        logger.warning("livermore ai reco failed for %s: %s", sym, e)
        out["ai_error"] = f"AI 调用失败: {e}"
    return out


def _parse_ai_reco(text: str) -> dict | None:
    import re
    m = re.search(r"\{.*\}", text or "", re.DOTALL)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
        thr = float(obj.get("threshold"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    # 只认网格里出现过的阈值,防 AI 幻觉出格值
    valid = min(GRID_THRESHOLDS, key=lambda t: abs(t - thr))
    if abs(valid - thr) > 0.005:
        return None
    try:
        conf = max(0, min(100, int(round(float(obj.get("confidence", 0))))))
    except (TypeError, ValueError):
        conf = 0
    return {
        "threshold": valid,
        "confidence": conf,
        "reason": str(obj.get("reason", "")).strip()[:120],
    }
