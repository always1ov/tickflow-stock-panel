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
from typing import Any

import polars as pl
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.indicators.levels import compute_levels, summarize_levels
from app.services import stock_reports
from app.services.ndjson_heartbeat import with_heartbeat
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
                           "livermore": [], "fib2": []},
                "close": None, "summary": "无数据", "symbol": symbol,
                "dates": [], "series": {}, "fib2": {}}

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
    # [R403] 这里原来还注入一组「持仓止盈」的线(生效出场线 + 生命线), 已撤。
    # 撤的只是这张图上的线 —— `services/position_exit.py` 整个模块原样在跑,
    # 决策台的止盈线列、盘中 `exit_*`/`exitlife_*` 推送、AI 信号里的持仓上下文
    # 全部不受影响。理由与恢复办法见 `indicators/levels.py` 的 LEVEL_TYPES。
    close = float(df.tail(1)["close"][0]) if "close" in df.columns else None
    # 日期 + 带状曲线序列(供前端画 Keltner/ATR/布林带曲线)
    dates = df["date"].to_list()
    date_strs = [str(d) for d in dates]
    series = _build_series(df)

    # [R405 · fork 增强] 斐波那契二型(帝纳波利点位)——**与六态同一个套路**:
    # 在 API 层注入, 不进 `compute_levels`。两个理由:
    #   · `compute_levels` 是作者的, 这一组是 fork 加的, 分开放边界才清楚;
    #   · 它还有横线之外的东西(回踩密集带色带、上攻段底色、首次回踩标记、
    #     短期均线), 那些塞不进"一组横线"的结构。
    # **只出位置, 不出动作**: 不进把握分、不产生提醒、不碰六态、不碰模拟盘。
    fib2_overlay: dict[str, Any] = {}
    try:
        from app.indicators import dinapoli

        # 三档一次算完。纯几何, 250 根 K 线跑三遍是毫秒级 —— 与其让用户改个数
        # 等一轮重算, 不如全给它, 图上切换零延迟。
        grains: dict[str, Any] = {}
        base: dinapoli.Fib2 | None = None
        for name, k in dinapoli.GRAINS.items():
            res = dinapoli.compute(df, pivot_k=k)
            grains[name] = {
                "k": k,
                "levels": dinapoli.to_levels(res, close),
                "zone": res.zone,
            }
            if name == "mid":
                base = res
        # levels.fib2 给中档 —— 它是默认档, 也让"只读 levels 的调用方"拿到能用的一组
        levels["fib2"] = grains["mid"]["levels"]
        if base is not None and not base.is_empty():
            series["fib2"] = {"dma3": base.dma3}
            thrust = None
            if base.thrust and base.thrust[1] < len(date_strs):
                s, e = base.thrust
                thrust = {"start": date_strs[s], "end": date_strs[e],
                          "days": e - s + 1}
            marks = []
            if (base.first_pullback_bar is not None
                    and base.first_pullback_bar < len(date_strs)):
                marks.append({"date": date_strs[base.first_pullback_bar],
                              "label": "首次回踩"})
            fib2_overlay = {
                # 这两样与粗细档无关(推进段和均线都不看摆点), 所以不按档重复
                "thrust": thrust, "markers": marks,
                # 平移之后露到最后一根之外的那几个值 = 图上「未来」区那一段
                "dma3_future": dinapoli.future_dma(
                    [float(x) for x in df["close"].to_list()],
                    dinapoli.DMA_LEN, dinapoli.DMA_SHIFT),
                "grain": grains,
            }
    except Exception as e:  # noqa: BLE001
        logger.debug("fib2 levels skipped: %s", e)
        levels["fib2"] = []

    return {
        "levels": levels,
        "close": close,
        "summary": summarize_levels(levels, close),
        "symbol": symbol,
        "dates": date_strs,
        "series": series,
        "fib2": fib2_overlay,
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
        async for chunk in with_heartbeat(analyze_stock_stream(repo, data_dir, req.symbol, req.focus)):
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
                # [R224] 三个尺度对齐到哪一步了。**报进度不报警** ——
                # R223 那版是成对冲突检查, 实测让超过一半的行挂上警告
                # (六态vs通道档位 29.8% + 六态vs阶段 33.2%), 那是我自己
                # 破了 R205「一半的票都打架就没人看了」那条规矩。
                # 三者是滞后阶梯(价格最快→六态→均线最慢), 不一致本身
                # 就是"转折走到第几步"的读数。
                al = kg.alignment(t.get("state"), kc.get("geo"))
                phases[sym] = dict(ph, align=al) if al else ph
        except Exception as e:  # noqa: BLE001
            logger.debug("channel event skipped for %s: %s", sym, e)
    urgency = watchlist_urgency.assess_many(
        syms, positions=positions, trends=trends, exit_lines=exits, keltner=keltner)
    # [R205] 「怎么办」收敛层 —— 五套判定合成一句话, 并指出它们什么时候打架。
    # 原料全是上面已经算好的, **零新增取数**; AI 信号从本地缓存读, 不调模型。
    from app.services import stock_playbook
    try:
        from app.services import stock_signal
        all_sigs = stock_signal.load_all()
        sigs = {s_: (all_sigs.get(s_) or {}) for s_ in syms}
    except Exception as e:  # noqa: BLE001
        logger.debug("playbook: 读 AI 信号失败, 按没有信号处理: %s", e)
        sigs = {}
    play = stock_playbook.playbook_many(
        syms, positions=positions, trends=trends, exit_lines=exits,
        urgency=urgency, keltner=keltner, phases=phases, events=events, signals=sigs)
    return {"urgency": urgency, "event": events, "phase": phases, "playbook": play}


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


@router.get("/glossary")
def get_glossary() -> dict:
    """[R292] 「说明」—— 六态状态与通道档位各是什么意思。

    用户: 「把全景按钮改成说明或者帮助按钮, 里面是解释每个六态状态、结论状态
    是什么意思」。

    与 `/combo-table` 同一条路: **无参数、无取数、结果恒定**, 而且**名字与结论
    文案的正主在后端** —— 前端誊抄一份的话, 底层改了措辞那份就开始说假话, 且
    没有任何东西会报错。口径与不泄露算法的取舍见 `services/glossary.py`。
    """
    from app.services import glossary
    return glossary.terms()


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


class Fib2GrainBacktestRequest(BaseModel):
    """[R412] 斐波那契二型粗细档回测请求。"""
    symbol: str
    use_ai: bool = True


@router.post("/fib2/grain-backtest")
async def fib2_grain_backtest(request: Request, req: Fib2GrainBacktestRequest):
    """[R412] 粗细档回测 —— 评的是**「线画得准不准」**, 不是「跟着做赚不赚」。

    用户: 「粗中细我看不懂, 这个调优能不能交给 ai 就像我六态设置了一个回测
    按钮, 参考这种模式」。形状照搬六态那个(指标表 + 规则建议 + 可选 AI),
    但**评的量完全不同**: 这一组不出买卖信号, 没有收益可算; 要算收益就得先编
    一条买卖规则, 那等于把 R405 砍掉的判定层从后门接回来。

    评的是: 历史上每一次上攻之后, 实际回踩的最低点有没有落在当时画出来的线上。
    **必须除以线数** —— 细档线多, 蒙中的概率天然更高。
    """
    if not req.symbol.strip():
        raise HTTPException(400, "symbol 不能为空")
    from app.services import fib2_grain_service
    return await fib2_grain_service.run_grain_backtest(
        request.app.state.repo, req.symbol, req.use_ai)


class TrendBacktestBatchRequest(BaseModel):
    """[R312] 全量阈值回测请求。symbols 为空 = 整个自选。"""
    symbols: list[str] = []


# 一次批量的上限。自选 166 只是常态, 给到 400 留足余量;
# 再多就该分批发 —— 一次请求算几千只票会把连接卡在那里超时。
_BATCH_MAX = 400


@router.post("/trend/backtest-batch")
def trend_backtest_batch(request: Request, req: TrendBacktestBatchRequest):
    """[R312] 全量阈值回测 —— **纯计算, 不调 AI、不计费**(与「刷新」同一带)。

    单只那个弹窗会额外问一次 AI 当调参顾问; 批量不问 —— 166 只票就是 166 次
    调用, 而规则建议本身是纯函数、可复算, 样本不足时还会明说不足以调参。
    要听 AI 的意见, 逐只打开那个弹窗, 入口一直在。
    """
    from app.services import livermore_service, watchlist
    syms = [x for x in (req.symbols or []) if str(x).strip()]
    if not syms:
        syms = sorted(watchlist.symbol_set())
    if not syms:
        raise HTTPException(400, "自选是空的,没有可回测的标的")
    if len(syms) > _BATCH_MAX:
        raise HTTPException(400, f"一次最多回测 {_BATCH_MAX} 只,收到 {len(syms)} 只")
    return livermore_service.batch_backtest(request.app.state.repo, syms)


class TrendThresholdBatchItem(BaseModel):
    symbol: str
    threshold: float | None = None
    source: str = "rule"


class TrendThresholdBatchRequest(BaseModel):
    """[R312] 批量应用阈值。threshold=null = 清除该票覆盖。"""
    items: list[TrendThresholdBatchItem] = []


@router.put("/trend/threshold-batch")
def set_trend_threshold_batch(req: TrendThresholdBatchRequest):
    """[R312] 批量写入阈值覆盖 —— 一次读一次写, 要么全进要么全不进。

    **不是循环调单只那个接口。** 那样 166 只就是 166 次整文件读写, 而且中途
    出错会留下半套(前 80 只改了、后 86 只没改), 用户看到的只有一个失败提示。
    """
    from app.services import livermore_service
    if not req.items:
        raise HTTPException(400, "没有要应用的项")
    if len(req.items) > _BATCH_MAX:
        raise HTTPException(400, f"一次最多应用 {_BATCH_MAX} 只")
    for it in req.items:
        if it.source not in ("manual", "ai", "rule"):
            raise HTTPException(400, f"source 无效: {it.source}")
    return livermore_service.set_thresholds([it.model_dump() for it in req.items])


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
