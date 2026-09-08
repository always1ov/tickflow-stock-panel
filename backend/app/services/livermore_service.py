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
    STATE_LABELS,
    action_text,
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

def _distance_pct(line: float | None, close: float | None) -> float | None:
    """(线 − 现价) / 现价。与 position_exit 同一口径, 两处必须一致 ——
    决策台把出场线距离和翻转价距离摆在一起比, 口径不同就没法比。"""
    try:
        if line is None or not close:
            return None
        return round((float(line) - float(close)) / float(close), 4)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


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
        "action": action_text(st, last["up_pivot"], last["dn_pivot"],
                              last.get("flip_down"), last.get("flip_up")),
        "side": "多头" if st in BULLISH else "空头",
        "duration": res["duration"],
        "since": res["since"],
        "entered_from": res["entered_from"],
        "entered_from_cn": frm_cn,
        "up_pivot": last["up_pivot"],
        "dn_pivot": last["dn_pivot"],
        # [R29] 翻转触发价 + 本轮高低水位: 趋势途中真正前瞻的价位(见 _flip_prices)
        "flip_down": last.get("flip_down"),
        "flip_up": last.get("flip_up"),
        # [R178] 离翻转还有多远。**口径与 position_exit 的 distance_pct 完全一致**:
        # (线 − 现价) / 现价, 所以 flip_down 通常为负(线在下方)、flip_up 为正。
        #
        # 补这两个数是因为一个不对称: 出场线一直有 distance_pct, 于是"该不该卖"
        # 能按紧迫度排序、能盘中推送; 而翻转价只有价位没有距离, "该不该买"就只
        # 剩一个静态数字, 自选一多就淹掉了。价位回答"到哪儿", 距离才回答"还有多急"。
        "flip_down_distance_pct": _distance_pct(last.get("flip_down"), last["close"]),
        "flip_up_distance_pct": _distance_pct(last.get("flip_up"), last["close"]),
        "leg_high": last.get("leg_high"),
        "leg_low": last.get("leg_low"),
        # [R30] 建仓/作废计划的锚: 进入当前状态那天的关键点, 不随新高漂移
        "entry_pivot": res.get("entry_up_pivot"),
        "entry_dn_pivot": res.get("entry_dn_pivot"),
        "close": last["close"],
        "as_of": last["date"],
        "signal": kind[0] if kind else None,
        "signal_desc": kind[1] if kind else None,
        "threshold": threshold,
        "threshold_source": source,
        "window_days": len(closes),
        # [R13] 近 20 交易日收益, 供今日总览算相对强度(个股 vs 大盘); 窗口不足给 None
        "ret_20d": (closes[-1] / closes[-21] - 1) if len(closes) >= 21 and closes[-21] else None,
        # [R188] 红绿节拍与磨底时长。**接在这里是零成本的** —— compute 已经跑完,
        # steps 就在手上, 原来用完即弃; 节拍判定只是对它做一次 O(n) 遍历。
        # 另起一条取数路的话, 决策台每只票就要多扫一遍盘。
        "rhythm": _rhythm(res),
    }


def _rhythm(res: dict) -> dict | None:
    """[R188] 红绿节拍 —— 失败只降级为 None, 不能让一个注记把趋势整条链拖垮。"""
    try:
        from app.services.trend_rhythm import assess
        return assess(res.get("steps"))
    except Exception as e:  # noqa: BLE001
        logger.debug("trend rhythm skipped: %s", e)
        return None


_CLOSING_PRICE_KEYS = ("flip_down", "flip_up", "leg_high", "leg_low",
                       "up_pivot", "dn_pivot", "entry_pivot", "entry_dn_pivot")


def _overlay_closing_prices(out: dict, closes: list[float], dates: list[str],
                            thr: float, src: str) -> None:
    """[R30] 盘中时把所有决策价位换成"只用已收盘日线"算的版本。

    状态/持续天数/信号仍是盘中临时口径(用户要的就是"当前阶段状态"),
    但价位是纪律线, 必须收盘口径 —— 否则盘中一根长上影就能把转弱线抬高,
    等于用没成立的高点放松出场标准。

    另附 action_closing: 按收盘口径价位重写的操作建议, 前端盘中展示这一条。
    价位算不出来时保持原值不动, 不制造空洞(PRD §9.4 数据不确定宁可不动)。
    """
    if len(closes) < _MIN_DAYS:
        return
    try:
        base = _trend_payload(closes, dates, thr, src)
    except Exception as e:  # noqa: BLE001
        logger.debug("closing-price overlay skipped: %s", e)
        return
    for k in _CLOSING_PRICE_KEYS:
        out[k] = base.get(k)
    out["action"] = base.get("action")
    out["price_basis"] = "closing"
    out["closing_state"] = base.get("state")
    out["closing_as_of"] = base.get("as_of")


def trend_for_symbol(repo, symbol: str, with_segments: bool = False,
                     live_entry: tuple[str, float] | None = None) -> dict:
    """单只趋势详情。with_segments=True 附带多空分段(K 线背景着色用)。"""
    sym = (symbol or "").strip().upper()
    closes, dates = _load_symbol_window(repo, sym)
    n_stored = len(closes)
    closes, dates = append_live_bar(closes, dates, live_entry)
    if len(closes) < _MIN_DAYS:
        return {"symbol": sym, "error": f"日 K 不足 {_MIN_DAYS} 天,无法判定趋势"}
    thr, src = get_effective_threshold(sym)
    out = {"symbol": sym, **_trend_payload(closes, dates, thr, src)}
    # [R18] 实时价确实参与了判定 → 标记盘中临时口径, 前端据此提示"待收盘确认"
    if len(closes) > n_stored:
        out["intraday"] = True
        # [R30] 但价位一律走收盘口径(PRD §7.5: 风险参考价统一用正式收盘价)。
        # 盘中冲高会把 leg_high 顶上去, 跟着算出的转弱线随之虚高 —— 那是拿一个
        # 未成立的高点去放松出场纪律, 方向正好反了。状态可以是盘中临时的,
        # 价位不行。
        _overlay_closing_prices(out, closes[:n_stored], dates[:n_stored], thr, src)
    if with_segments:
        res = compute(closes, dates, thr)
        out["segments"] = [
            {"side": s["side"], "start_date": s["start_date"], "end_date": s["end_date"]}
            for s in side_segments(res["steps"])
        ]
    return out


def _bullish_event_win_rate(states: list[str], closes: list[float],
                            horizon: int = 5, min_events: int = 3) -> dict | None:
    """[R20] 历史"转入多头侧"事件的胜率: 事件日后 horizon 个交易日收益为正的比例。

    事件 = 状态从空头侧转入多头侧的那一天; 距末尾不足 horizon 的事件(含刚发生的
    当前信号)不计入, 只统计已有完整结果的历史事件。样本 < min_events 返回 None
    (小样本胜率没有统计意义, 宁缺毋滥)。纯函数。
    """
    events = [i for i in range(1, len(states))
              if states[i] in BULLISH and states[i - 1] not in BULLISH]
    wins = 0
    n = 0
    for i in events:
        j = i + horizon
        if j >= len(closes):
            continue
        n += 1
        if closes[j] > closes[i]:
            wins += 1
    if n < min_events:
        return None
    return {"rate": round(wins / n, 3), "n": n}


def bullish_win_rate_for_symbol(repo, symbol: str, horizon: int = 5) -> dict | None:
    """该票在自身窗口与生效阈值下, 历史转强信号的胜率。数据不足返回 None。"""
    sym = (symbol or "").strip().upper()
    closes, dates = _load_symbol_window(repo, sym)
    if len(closes) < _MIN_DAYS:
        return None
    thr, _src = get_effective_threshold(sym)
    res = compute(closes, dates, thr)
    states = [s["state"] for s in res["steps"]]
    return _bullish_event_win_rate(states, closes, horizon=horizon)


# [R156] 历史胜率的批量版 + 按(票, 末日, 阈值)记忆。
#
# 起因: 今日总览对每只候选逐只调 bullish_win_rate_for_symbol, 每次都是一趟
# 320 日历日的 parquet 扫描 —— 候选上限 80 只就是 80 趟扫盘, 这是总览接口
# 最大的一块耗时。而 trends_for_symbols 早就示范了正确做法: 同一窗口、同一列,
# 一次 get_daily_batch 读完再按 symbol 分组。
#
# 记忆: 一只票的历史胜率只在新日线落地或阈值改动时才会变, 所以键取
# (symbol, 窗口末日, 阈值, horizon) —— 同一天再打开总览, 连 compute 都省了。
_WIN_CACHE: dict[tuple[str, str, float, int], dict | None] = {}
_WIN_CACHE_MAX = 4000


def bullish_win_rates_for_symbols(repo, symbols: list[str], horizon: int = 5) -> dict[str, dict]:
    """{SYMBOL: {"rate", "n"}}, 样本不足的票不出现。股票一次批量读; ETF/指数逐只回退。

    结果与逐只调 bullish_win_rate_for_symbol 完全一致(同窗口、同阈值、同纯函数),
    只是 IO 从 N 趟变成 1 趟。
    """
    out: dict[str, dict] = {}
    syms = sorted({str(s).strip().upper() for s in symbols if s and str(s).strip()})
    if not syms:
        return out
    series: dict[str, tuple[list[float], list[str]]] = {}
    stock_syms = [s for s in syms if repo.resolve_asset_type(s) == "stock"]
    if stock_syms:
        end = date.today()
        start = end - timedelta(days=_CALENDAR_SPAN_DAYS)
        try:
            df = repo.get_daily_batch(stock_syms, start, end, ["symbol", "date", "close"])
        except Exception as e:  # noqa: BLE001
            logger.warning("livermore win-rate batch daily failed: %s", e)
            df = pl.DataFrame()
        if df is not None and not df.is_empty() and "symbol" in df.columns:
            for sym, part in df.group_by("symbol"):
                key = str(sym[0] if isinstance(sym, tuple) else sym).upper()
                series[key] = _closes_window(part)
    for s in syms:
        if s in series:
            continue
        try:  # ETF / 指数, 或批量里没读到的
            series[s] = _load_symbol_window(repo, s)
        except Exception as e:  # noqa: BLE001
            logger.debug("livermore win-rate window for %s failed: %s", s, e)
    for s, (closes, dates) in series.items():
        if len(closes) < _MIN_DAYS:
            continue
        thr, _src = get_effective_threshold(s)
        key = (s, dates[-1], float(thr), int(horizon))
        if key in _WIN_CACHE:
            win = _WIN_CACHE[key]
        else:
            res = compute(closes, dates, thr)
            states = [st["state"] for st in res["steps"]]
            win = _bullish_event_win_rate(states, closes, horizon=horizon)
            if len(_WIN_CACHE) >= _WIN_CACHE_MAX:
                _WIN_CACHE.clear()
            _WIN_CACHE[key] = win
        if win:
            out[s] = win
    return out


def append_live_bar(closes: list[float], dates: list[str],
                    live_entry: tuple[str, float] | None) -> tuple[list[float], list[str]]:
    """[R16] 盘中实时: 把当天实时价作为"临时收盘"追加到窗口末尾。

    仅当实时行日期新于最后一根已存日 K 时追加(收盘后日线落盘则天然跳过,
    不会重复); 由此得到的六态是盘中临时判定, 收盘口径以真实收盘为准。纯函数。
    """
    if not live_entry or not dates:
        return closes, dates
    d, c = live_entry
    try:
        c = float(c)
    except (TypeError, ValueError):
        return closes, dates
    if d and c > 0 and str(d) > str(dates[-1]):
        return closes + [c], dates + [str(d)]
    return closes, dates


def trends_for_symbols(repo, symbols: list[str],
                       live: dict[str, tuple[str, float]] | None = None) -> dict[str, dict]:
    """批量趋势(决策台「趋势」列)。股票走一次批量 scan;ETF/指数逐只回退。

    live: {symbol: (date, close)} 自选实时行(可选) —— 传入时当天实时价参与
    六态判定(盘中临时口径), 见 append_live_bar。
    """
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
                n_stored = len(closes)
                closes, dts = append_live_bar(closes, dts, (live or {}).get(key))
                if len(closes) < _MIN_DAYS:
                    continue
                thr, src = get_effective_threshold(key)
                out[key] = _trend_payload(closes, dts, thr, src)
                if len(closes) > n_stored:  # [R18] 实时价参与判定 → 盘中临时口径
                    out[key]["intraday"] = True
                    # [R30] 价位回落到收盘口径, 与单只路径一致
                    _overlay_closing_prices(out[key], closes[:n_stored], dts[:n_stored], thr, src)

    for sym in other_syms:
        try:
            r = trend_for_symbol(repo, sym, live_entry=(live or {}).get(sym))
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
            max_tokens=None,  # [上游标准] 分析类调用不限制输出(推理模型思考计入预算)
        )
        out["ai"] = _parse_ai_reco(text)
        if out["ai"] is None:
            snippet = (text or "").replace("\n", " ").strip()[:80]
            out["ai_error"] = f"AI 返回无法解析(原文开头: {snippet or '空'}…)"
    except Exception as e:  # noqa: BLE001
        logger.warning("livermore ai reco failed for %s: %s", sym, e)
        out["ai_error"] = f"AI 调用失败: {e}"
    return out


def _parse_ai_reco(text: str) -> dict | None:
    # [R22] 跨厂家容错解析(围栏/解说文字/截断都能救)
    from app.services.ai_json import extract_json_object
    obj = extract_json_object(text)
    if obj is None:
        return None
    try:
        thr = float(obj.get("threshold"))
    except (TypeError, ValueError):
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
