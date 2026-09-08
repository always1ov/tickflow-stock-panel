"""个股分析 API — 关键价位 + AI 四维分析 + 报告持久化。

路由前缀: /api/stock-analysis

端点:
  GET  /levels?symbol=         11 类关键价位(图表 markLine 数据源)
  POST /analyze                AI 流式四维分析(NDJSON)
  GET  /reports                历史报告列表
  POST /reports                保存一条报告
  DELETE /reports/{report_id}  删除一条报告
"""
from __future__ import annotations

import logging
import math
from datetime import date, timedelta

import polars as pl
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.indicators.levels import compute_levels, summarize_levels
from app.services import stock_reports
from app.services.stock_analyzer import analyze_stock_stream

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/stock-analysis", tags=["stock-analysis"])


def _to_float_list(series: pl.Series) -> list:
    """polars Series → JSON 安全的 float 列表(null/NaN → None)。"""
    out: list = []
    for v in series.to_list():
        if v is None:
            out.append(None)
            continue
        try:
            f = float(v)
            out.append(round(f, 2) if math.isfinite(f) else None)
        except (TypeError, ValueError):
            out.append(None)
    return out


def _build_series(df: pl.DataFrame) -> dict:
    """提取带状指标(布林带 / Keltner通道 / ATR止损)的每日时间序列。

    这些指标的本质是"每日一条线",随 MA/ATR/σ 漂移,画成曲线才能体现通道形态。
    其余固定价位(枢轴/前高前低等)不在此,仍用水平 markLine。

    返回结构(每个 value 都是按日期对齐的数组):
      {
        "boll":      {"upper": [...], "lower": [...]},
        "keltner_s": {"upper": [...], "lower": [...]},   # 短期 MA20±2ATR
        "keltner_m": {"upper": [...], "lower": [...]},   # 中期 MA60±2.5ATR
        "keltner_l": {"upper": [...], "lower": [...]},   # 长期 MA120±3ATR
        "atr":       {"stop_loss": [...], "take_profit": [...]},  # close∓2ATR
      }
    """
    if df.is_empty() or "close" not in df.columns:
        return {}

    out: dict[str, dict] = {}
    close = df["close"]
    has_atr = "atr_14" in df.columns

    # 布林带(上/下/中轨;中轨 = MA20,数据层已预计算)
    if "boll_upper" in df.columns and "boll_lower" in df.columns:
        out["boll"] = {
            "upper": _to_float_list(df["boll_upper"]),
            "lower": _to_float_list(df["boll_lower"]),
            "mid": _to_float_list(df["ma20"]) if "ma20" in df.columns else None,
        }

    # Keltner 通道三档(需要 ATR)
    if has_atr:
        atr = df["atr_14"]
        # MA120 现场算(不在预计算列中)
        ma120 = df.select(pl.col("close").rolling_mean(120))["close"] if df.height >= 120 else None

        def _channel(ma: pl.Series, n: float) -> dict:
            return {
                "upper": _to_float_list(ma + n * atr),
                "lower": _to_float_list(ma - n * atr),
            }

        if "ma20" in df.columns:
            out["keltner_s"] = _channel(df["ma20"], 2.0)
        if "ma60" in df.columns:
            out["keltner_m"] = _channel(df["ma60"], 2.5)
        if ma120 is not None:
            out["keltner_l"] = _channel(ma120, 3.0)

        # ATR 止损/止盈: close ± 2×ATR(跟随行情漂移的动态止损线)
        out["atr"] = {
            "stop_loss": _to_float_list(close - 2 * atr),
            "take_profit": _to_float_list(close + 2 * atr),
        }

    return out


@router.get("/levels")
def get_levels(
    request: Request,
    symbol: str = Query(..., description="标的代码,如 000001.SZ"),
    days: int = Query(120, ge=30, le=500, description="计算样本天数"),
):
    """计算 11 类关键价位(成交密集区压力支撑 / 枢轴点 / 前高前低 /
    布林带 / Keltner短中长 / ATR止损 / 缺口 / 斐波那契 / 整数关口)。

    返回 {levels: {sr, pivot, extreme, boll, keltner_s, keltner_m, keltner_l,
    atr_stop, gap, fib, round}, close, summary, dates, series}。
    前端按 levels 的 key 渲染开关按钮,逐组显隐 markLine / 曲线。
    """
    if not symbol:
        raise HTTPException(400, "symbol 不能为空")

    repo = request.app.state.repo
    end = date.today()
    start = end - timedelta(days=days * 2)
    # 按资产类型分流: ETF/指数走独立 enriched 存储, 股票保持原路径
    df = repo.get_daily_asset(repo.resolve_asset_type(symbol), symbol, start, end)
    if df.is_empty():
        return {"levels": {"sr": [], "pivot": [], "extreme": [],
                           "boll": [], "keltner_s": [], "keltner_m": [], "keltner_l": [],
                           "atr_stop": [], "gap": [], "fib": [], "round": [],
                           "livermore": []},
                "close": None, "summary": "无数据", "symbol": symbol,
                "dates": [], "series": {}}

    levels = compute_levels(df)
    # [fork 增强] 六态关键点 —— 上/下关键点作为一组关键价位(markLine + 点位提醒可用)
    try:
        from app.services.livermore_service import trend_for_symbol
        trend = trend_for_symbol(request.app.state.repo, symbol)
        lv_points = []
        # [R29] 翻转触发价优先画 —— 趋势途中上关键点就是本轮最高收盘价, 贴着现价
        # 画一条线没有参考价值; "跌到多少掉出上涨趋势"才是要盯的位置。
        if trend.get("flip_down"):
            lv_points.append({"value": float(trend["flip_down"]), "label": "六态跌破转弱",
                              "type": "livermore", "side": "support", "strength": "strong"})
        if trend.get("flip_up"):
            lv_points.append({"value": float(trend["flip_up"]), "label": "六态站上转强",
                              "type": "livermore", "side": "resistance", "strength": "strong"})
        # 关键点仍画, 但趋势态里它与翻转价重合/贴现价时会被上面两条盖过, 不重复添加
        seen = {round(p["value"], 4) for p in lv_points}
        if trend.get("up_pivot") and round(float(trend["up_pivot"]), 4) not in seen:
            lv_points.append({"value": float(trend["up_pivot"]), "label": "六态上关键点",
                              "type": "livermore", "side": "resistance", "strength": "strong"})
        if trend.get("dn_pivot") and round(float(trend["dn_pivot"]), 4) not in seen:
            lv_points.append({"value": float(trend["dn_pivot"]), "label": "六态下关键点",
                              "type": "livermore", "side": "support", "strength": "strong"})
        levels["livermore"] = lv_points
    except Exception as e:  # noqa: BLE001
        logger.debug("livermore levels skipped: %s", e)
        levels["livermore"] = []
    # [fork 增强] 持仓出场线(仅持有+已填成本的票才有;ATR 三阶段)
    levels["exit"] = []
    try:
        from app.services.position_exit import exit_for_symbol
        ex = exit_for_symbol(request.app.state.repo, symbol)
        if ex:
            levels["exit"] = [{
                "value": float(ex["line"]),
                "label": f"{ex['line_cn']}({ex['stage_cn']})",
                "type": "exit", "side": "support", "strength": "strong",
            }]
            # 生命线独立于生效线时单独画(绝对底线: 20日线或手填价)
            if ex.get("lifeline") and abs(float(ex["lifeline"]) - float(ex["line"])) > 0.001:
                levels["exit"].append({
                    "value": float(ex["lifeline"]),
                    "label": "生命线(20日线)" if ex.get("lifeline_src") == "ma20" else "生命线(手动)",
                    "type": "exit", "side": "support", "strength": "strong",
                })
    except Exception as e:  # noqa: BLE001
        logger.debug("exit level skipped: %s", e)
    close = float(df.tail(1)["close"][0]) if "close" in df.columns else None
    # 日期 + 带状曲线序列(供前端画 Keltner/ATR/布林带曲线)
    dates = df["date"].to_list()
    series = _build_series(df)
    return {
        "levels": levels,
        "close": close,
        "summary": summarize_levels(levels, close),
        "symbol": symbol,
        "dates": [str(d) for d in dates],
        "series": series,
    }


class AnalyzeRequest(BaseModel):
    """AI 个股分析请求。"""
    symbol: str
    focus: str = ""  # 可选:用户追加的分析关注点


@router.post("/analyze")
async def analyze_stock(request: Request, req: AnalyzeRequest):
    """AI 个股四维分析 — NDJSON 流式返回。

    组合 K 线(技术指标)+ 财务表 + 关键价位 → 客观技术分析提示词 →
    流式调用 LLM → 逐 chunk 以 NDJSON 推给前端(每行一个 JSON)。
    """
    if not req.symbol:
        raise HTTPException(400, "symbol 不能为空")

    repo = request.app.state.repo
    data_dir = repo.store.data_dir

    async def stream_gen():
        async for chunk in analyze_stock_stream(repo, data_dir, req.symbol, req.focus):
            yield chunk + "\n"

    return StreamingResponse(
        stream_gen(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ================================================================
# AI 买卖信号(自选决策台 P2)—— 结构化操作倾向, 与四维客观分析分开
# ================================================================


@router.get("/signals")
def list_signals():
    """全部已缓存的 AI 买卖信号 {SYMBOL: {signal, confidence, reason, close, created_at}}。"""
    from app.services import stock_signal
    return {"signals": stock_signal.load_all()}


@router.post("/signal/{symbol}")
async def generate_signal(symbol: str, request: Request):
    """为单只标的生成(并缓存)一个 AI 买卖信号。前端「分析全部自选」逐只并发调用本接口。"""
    if not symbol.strip():
        raise HTTPException(400, "symbol 不能为空")
    from app.services import stock_signal
    repo = request.app.state.repo
    data_dir = repo.store.data_dir
    return await stock_signal.generate_signal(repo, data_dir, symbol)


# ================================================================
# 报告 CRUD(历史报告持久化)
# ================================================================

class SaveReportRequest(BaseModel):
    """保存一条 AI 个股分析报告。"""
    symbol: str
    name: str = ""
    focus: str = ""
    content: str
    summary: str = ""
    close: float | None = None
    levels: dict | None = None


@router.get("/reports")
def list_reports(request: Request):
    """获取全部历史报告(按时间降序,后端已裁剪到上限)。"""
    return {"reports": stock_reports.list_reports()}


@router.post("/reports")
def save_report(request: Request, req: SaveReportRequest):
    """保存一条报告。"""
    report = stock_reports.save_report({
        "symbol": req.symbol,
        "name": req.name,
        "focus": req.focus,
        "content": req.content,
        "summary": req.summary,
        "close": req.close,
        "levels": req.levels,
    })
    return {"ok": True, "report": report}


@router.delete("/reports/{report_id}")
def delete_report(request: Request, report_id: str):
    """删除一条报告。"""
    ok = stock_reports.delete_report(report_id)
    return {"ok": ok}


# ================================================================
# [fork 增强] 六态趋势(利弗莫尔 Market Key)—— 趋势判定 + 回测调参
# ================================================================


@router.get("/trend")
def get_trend(request: Request, symbol: str = Query(...)):
    """单只六态趋势详情(含多空分段,K 线背景着色用)。

    [R16] 实时行情开着时, 当天实时价作为临时收盘参与判定(盘中口径)。
    """
    if not symbol.strip():
        raise HTTPException(400, "symbol 不能为空")
    from app.services import livermore_service
    from app.services.live_quotes import as_live_entries, watchlist_live_map
    # [R77] 并入弹窗单票缓存(带真实行情日) —— 弹窗的六态才能拿到刚按需拉的价
    live = as_live_entries(watchlist_live_map(
        request.app.state.repo,
        quote_service=getattr(request.app.state, 'quote_service', None)))
    return livermore_service.trend_for_symbol(
        request.app.state.repo, symbol, with_segments=True,
        live_entry=live.get(symbol.strip().upper()))


@router.get("/trends")
def get_trends(request: Request, symbols: str = Query(..., description="逗号分隔,最多 200 只")):
    """批量六态趋势(决策台「趋势」列)。返回 {trends: {SYMBOL: {...}}}。

    [R16] 实时行情开着时, 当天实时价作为临时收盘参与判定(盘中口径)。
    """
    syms = [s for s in symbols.split(",") if s.strip()][:200]
    if not syms:
        raise HTTPException(400, "symbols 不能为空")
    from app.services import livermore_service
    from app.services.live_quotes import as_live_entries, watchlist_live_map
    # [R77] 并入弹窗单票缓存(带真实行情日) —— 弹窗的六态才能拿到刚按需拉的价
    live = as_live_entries(watchlist_live_map(
        request.app.state.repo,
        quote_service=getattr(request.app.state, 'quote_service', None)))
    return {"trends": livermore_service.trends_for_symbols(
        request.app.state.repo, syms, live=live)}


@router.get("/keltner")
def get_keltner(request: Request, symbols: str = Query(..., description="逗号分隔,最多 300 只")):
    """[R42] 批量 Keltner 三档位置(决策台「短/中/长通道」三列)。

    返回 {keltner: {SYMBOL: {s|m|l: {pos, pos_cn, upper, lower, pct, ...}}}}。
    公式与个股分析图表共用 indicators.keltner, 收盘口径。
    """
    syms = [s for s in symbols.split(",") if s.strip()][:300]
    if not syms:
        raise HTTPException(400, "symbols 不能为空")
    from app.services import keltner_service
    return {"keltner": keltner_service.channels_for_symbols(request.app.state.repo, syms)}


@router.get("/urgency")
def get_urgency(request: Request, symbols: str = Query(..., description="逗号分隔,最多 300 只")):
    """[R178] 批量「该动了」判定(决策台默认排序)。

    返回 {urgency: {SYMBOL: {level, label, order, distance, reason}}}。

    单独一个端点而不是塞进 /trends 或 /keltner: 判定要同时看仓位、趋势、出场线、
    通道四样, 塞进任何一个都会让那个端点承担它不该有的依赖。这里用的全是既有的
    批量函数, 数据都走各自的缓存。
    """
    syms = [s.strip() for s in symbols.split(",") if s.strip()][:300]
    if not syms:
        raise HTTPException(400, "symbols 不能为空")

    from app.services import (
        effective_positions, keltner_service, livermore_service,
        position_exit, watchlist_urgency,
    )
    from app.services.live_quotes import as_live_entries, watchlist_live_map

    repo = request.app.state.repo
    # 任何一路取不到都不该让整张表失去排序 —— 缺的那一路当空处理, 判定会
    # 自动降级到还能判的那些档
    def _safe(fn, what: str, default):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001
            logger.warning("urgency: %s unavailable (%s)", what, e)
            return default

    live = _safe(lambda: as_live_entries(watchlist_live_map(
        repo, quote_service=getattr(request.app.state, "quote_service", None))),
        "live quotes", {})
    trends = _safe(lambda: livermore_service.trends_for_symbols(repo, syms, live=live),
                   "trends", {})
    keltner = _safe(lambda: keltner_service.channels_for_symbols(repo, syms),
                    "keltner", {})
    exits = _safe(lambda: position_exit.exit_lines_for_positions(repo), "exit lines", {})
    positions = _safe(effective_positions.load_all, "positions", {})

    # [R195] 通道事件在这里合成 —— **这个端点已经同时拿着六态与三档通道了**,
    # 零额外取数。放这儿而不是 /keltner, 是因为事件必须三样齐全才判得出:
    #
    #     位置(通道三档) × 方向(六态) × 确认(在轨外连续几天)
    #
    # 缺任何一个都答不了「破上轨算站稳了, 还是算突破, 还是主升浪」——
    # 这三个问题问的是三个不同的维度, 而通道只回答其中一个。
    #
    # **底层的三档判定一个字没动**, 这里只是读它。
    from app.indicators import keltner_geometry as kg
    events: dict[str, dict] = {}
    phases: dict[str, dict] = {}
    for sym in syms:
        kc = keltner.get(sym) or {}
        if not kc.get("geo"):
            continue
        t = trends.get(sym) or {}
        try:
            ev = kg.event(state=t.get("state"), duration=t.get("duration"),
                          geo=kc.get("geo"), run=kc.get("runs"))
            note = kg.combo_note(kc)
            if note:
                ev = dict(ev, combo_note=note)
            events[sym] = ev
            # [R200] 阶段。事件回答"今天发生了什么", 阶段回答"整体走到哪一段、
            # 该盯什么" —— 决策台悬停要的是后者。纯函数, 不新增取数。
            ph = kg.phase(kc.get("geo"), kc.get("runs"))
            if ph:
                phases[sym] = ph
        except Exception as e:  # noqa: BLE001
            logger.debug("channel event skipped for %s: %s", sym, e)
    return {"urgency": watchlist_urgency.assess_many(
        syms, positions=positions, trends=trends, exit_lines=exits, keltner=keltner),
        "event": events, "phase": phases}


@router.get("/combo-table")
def get_combo_table() -> dict:
    """[R203] 27 种组合速查表 —— 「系统结论」与「几何含义」并排。

    用户: 「我要看到系统结论和几何含义、偏离基准加速度等等」。

    **无参数、无取数、结果恒定** —— 它只是把作者那一层的 10 条结论按三档位置
    展开成 27 格, 再并上补充层的解读。所以整份可以让浏览器长期缓存。

    为什么做成端点而不是前端写死一份: 誊抄的表会漂 —— 底层哪天改了措辞,
    前端那份就开始说假话, 而且没有任何东西会报错。生成的表跟着底层走。
    """
    from app.indicators import keltner_geometry as kg
    return {"rows": kg.combo_table()}


@router.get("/review")
def get_review(request: Request, symbol: str = Query(...),
               days: int = Query(120, ge=10, le=250)):
    """[R48] 单只逐日复盘: 六态趋势 / Keltner 三档结论 / 涨停, 同一条时间轴。

    决策台的「趋势」「结论」两列点进来看的就是这个 —— 那两列只显示今天,
    要判断它们靠不靠谱得能翻回去看历史。

    收盘口径, 不叠加实时价: 复盘看的是已成立的事实, 掺进一个还会变的当日
    临时价会让最后一行跟着盘中跳。
    """
    if not symbol.strip():
        raise HTTPException(400, "symbol 不能为空")
    from app.services import review_service
    return review_service.review_for_symbol(request.app.state.repo, symbol, days)


class TrendBacktestRequest(BaseModel):
    """六态阈值网格回测请求。"""
    symbol: str
    use_ai: bool = True


@router.post("/trend/backtest")
async def trend_backtest(request: Request, req: TrendBacktestRequest):
    """阈值网格回测(纯计算,毫秒级)+ 规则建议 + 可选 AI 调参顾问(一次调用)。"""
    if not req.symbol.strip():
        raise HTTPException(400, "symbol 不能为空")
    from app.services import livermore_service
    return await livermore_service.run_backtest(request.app.state.repo, req.symbol, req.use_ai)


class TrendThresholdRequest(BaseModel):
    """设置六态阈值。symbol 为空 = 改全局默认;threshold=null = 清除该票覆盖。"""
    symbol: str = ""
    threshold: float | None = None
    source: str = "manual"  # manual / ai / rule


@router.put("/trend/threshold")
def set_trend_threshold(req: TrendThresholdRequest):
    """应用回测调参结果:写入该票的阈值覆盖(或全局默认)。"""
    from app.services import livermore_service
    if req.source not in ("manual", "ai", "rule"):
        raise HTTPException(400, "source 无效")
    try:
        return livermore_service.set_threshold(req.symbol, req.threshold, req.source)
    except ValueError as e:
        raise HTTPException(400, str(e))
