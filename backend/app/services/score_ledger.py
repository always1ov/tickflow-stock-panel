"""[fork 增强] R133 **规则层把握分台账** —— 这套评分到底有没有用, 只能用记录回答。

R121 的 ai_pick_ledger 记的是「AI 从前 8 名里挑的那 1-3 只后来涨没涨」。
它回答不了更前面的那个问题: **把握分本身有没有区分度**。原因是选择偏差 ——
台账里只有规则层前 8 名中被 AI 看中的那几只, 60 分和 90 分的票从没被同台比过。

所以这里换一个记法: **每天把完整候选池整个记下来**, 不管显示与否、不管 AI 选没选,
连同每只票的**因子拆解**(这 10 分是新鲜度给的还是主线给的)。之后回看
T+1/T+3/T+5, 就能同时回答三个问题:

  1. **分层单调吗?** 90 分档的胜率是不是真的高于 70 分档、70 高于 60。
     这比"前十名胜率 58%"重要得多 —— 单调才说明分数承载了信息,
     不单调的话再高的头部胜率也可能只是运气。
  2. **门槛与条数设在哪合适?** 记录里带名次与"当时显不显示",
     可以直接算"如果只看前 5 / 前 15 会怎样", 不必真的改了参数再等三个月。
  3. **哪个因子在做功?** 每只票存了因子增量, 可以分组比较:
     吃到放量加分的那批, 胜率是不是真的高于吃到缩量扣分的那批。
     某个因子两边胜率一样 —— 它就是在白占权重。

刻意的取舍(与 ai_pick_ledger 同源):
  - **只记, 不反馈**。台账不参与打分, 不喂给提示词。一旦拿它影响当期选择,
    这个数就不再干净。
  - 收益用**收盘价对收盘价**, 起点是记录当日收盘。真实交易有滑点与开盘价差,
    所以这个数天然偏乐观, 界面上必须如实标注。
  - **收益算出来就落盘**。已经过了 5 个交易日的记录, 其 T+5 收益不会再变,
    没必要每次打开页面重算一遍(几百只标的的日线读取会拖死接口)。
    只有还没到期的才留空, 下次再补。
  - **盘中快照标记 finalized=False**。盘中的 close 是实时价而非收盘价,
    用它当收益起点会得到假的收益; 收盘后同一天会被覆盖成定稿版。
    统计时只用定稿的。

存 ``user_data/score_ledger.json``: {"days": [...]}, 最多 ``MAX_DAYS`` 天,
每天最多 ``MAX_ROWS`` 只(按把握分降序取前 N —— 尾部的低分票对调参没有信息量)。
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

logger = logging.getLogger(__name__)

MAX_DAYS = 240            # 约一年交易日
MAX_ROWS = 50             # 每天记多少只候选(打分候选本身上限约 40 + 逼近突破那一路)
HORIZONS = (1, 3, 5)      # 回看的交易日数
# 单次 evaluate 最多补算多少只标的的日线 —— 首次打开时别把接口拖到超时,
# 补不完的下次接着补(已算出的都落了盘, 不会重复劳动)
MAX_FILL_SYMBOLS = 300
# 分层区间(左闭右开, 最后一档闭合)。按现行 min_score 默认 60 划, 60 以下单独一档:
# 那是"被滤掉的那批", 它们的胜率正是门槛值不值的证据
SCORE_BINS = ((0, 60), (60, 70), (70, 80), (80, 90), (90, 101))
# 排名段: 回答"只看前几名合适"
RANK_CUTS = (1, 3, 5, 10, 15, 20)
# [R134] 打分口径版本。v1 = 底分+八项加减(夹到 100), v2 = 三门槛+三维度加权,
# v3 [R189] = 四门槛 + 质地×时机两轴(几何平均)。
# **不同版本的记录绝不能混进同一个胜率里** —— 那是拿两套不同的分数当同一把尺子,
# 算出来的分层单调性没有任何意义。统计默认只取当前版本, 老记录留着但单独归档。
#
# 升到 v3 意味着 v2 攒下的样本从统计里退场, 用户明确接受了这件事:
# 「不管是前面的红绿节拍还是现在的六态升级, 只要能有提升我不在乎台账重新开始验证」。
SCORING_VERSION = 3
# 归因轴中文名(v3)。v2 的三维度与 v1 的八项加减保留在下面, 老记录还要按它解读。
FACTOR_LABELS = {
    "quality": "质地(趋势模板/磨底节拍/相对强度/六态)",
    "timing": "时机(新鲜度/通道位置/量比/换手)",
}
# v2 的三维度 —— 只用于解读 SCORING_VERSION == 2 的历史记录
V2_FACTOR_LABELS = {
    "trend": "趋势强度(新鲜度/六态/相对强度)",
    "volume": "量能确认(量比/换手)",
    "position": "位置成本(通道位置)",
}
# v1 的加减项 —— 只用于解读 SCORING_VERSION < 2 的历史记录与导出列
LEGACY_FACTOR_LABELS = {
    "fresh": "信号新鲜度",
    "ai": "AI 信号同向/反向",
    "rs": "相对强度(对大盘)",
    "vol": "量比",
    "win": "该票历史胜率",
    "mainline": "主线归属",
    "verdict": "量化波动通道结论",
    "near": "紧贴触发价",
    "clamp": "顶格削减(理论分 >100)",
}
CAVEAT = ("收盘价对收盘价, 未计滑点与开盘价差, 数字天然偏乐观; "
          "纯事后记录, 不参与打分也不喂给 AI")


# 本进程已经落过盘的 (日期, 是否定稿) —— 总览接口每次打开都会调 record_day,
# 没有它就会把整本台账反复重写(满载时几 MB), 把一个纯记账动作变成页面卡顿的来源。
_written: set[tuple[str, bool]] = set()


def _path():
    from app.config import settings
    p = settings.data_dir / "user_data" / "score_ledger.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _read() -> list[dict]:
    import json
    try:
        data = json.loads(_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    days = data.get("days") if isinstance(data, dict) else None
    return [d for d in days if isinstance(d, dict)] if isinstance(days, list) else []


def _write(days: list[dict]) -> None:
    from app.services.json_store import atomic_write_json
    try:
        atomic_write_json(_path(), {"days": days[-MAX_DAYS:]})
    except Exception as e:  # noqa: BLE001
        logger.warning("save score ledger failed: %s", e)


# --------------------------------------------------------------- 记录


def _row(o: dict, rank: int, shown: bool) -> dict:
    """一条候选 → 台账行。只留调参用得上的字段, 别把整份总览抄进来。

    [R134] ``f`` 存的是**维度分**而不是一串加减项(v1)。归因表因此从
    "加分组 vs 扣分组"变成"这一维高分组 vs 低分组" —— 维度分是 0~100 的连续量,
    没有正负之分, 硬套 v1 的三分法会把整批记录都归进"加分组", 归因表就废了。

    [R189] v3 起是**两根轴**(质地/时机)。轴分与维度分同为 0~100, 归因表的
    算法一个字不用改 —— 换的是记哪几个键。
    """
    f = {k: v for k, v in (o.get("axes") or o.get("dims") or o.get("factors") or {}).items()
         if v is not None}
    ctx = dict(o.get("ctx") or {})
    # 每个因子的子分也留下 —— 轴分能说明"时机这一档不行", 子分才能说明
    # "是量比不行还是位置不行"
    for k, v in (o.get("factors") or {}).items():
        if v is not None and k not in f:
            ctx.setdefault(f"sub_{k}", v)
    close = o.get("close")
    return {
        "symbol": o.get("symbol"),
        "name": o.get("name") or "",
        "score": int(o.get("score") or 0),
        "rank": rank,
        "shown": bool(shown),
        "kind": o.get("kind") or "",
        "board": o.get("board") or "",
        "close": round(float(close), 3) if close else None,
        "f": f,
        "ctx": {k: v for k, v in ctx.items() if v is not None},
        # 收益回看后填, 到期前是 None
        "r": {},
    }


def record_day(as_of: str | None, ranked: list[dict], shown_symbols: set[str],
               finalized: bool) -> dict:
    """记下这一天的完整候选池。

    ranked: score_opportunities() 的完整排序结果(未按门槛/条数截断)。
    shown_symbols: 当时实际显示给用户的那些 —— 用来复盘"当时的门槛漏掉了什么"。
    finalized: 数据是不是收盘定稿(盘中快照的 close 是实时价, 统计时要排除)。

    同一天重复调用直接覆盖: 盘中会写好几次, 最后一次(收盘后)才是准的。
    已定稿的那天不会被盘中快照覆盖回去。
    """
    from app.services.json_store import lock_for
    day = str(as_of or "").strip()[:10]
    if not day or not ranked:
        return {"ok": False, "recorded": 0}
    key = (day, bool(finalized))
    if key in _written:
        return {"ok": True, "recorded": 0, "skipped": "本进程已记过"}
    rows = [_row(o, i + 1, o.get("symbol") in shown_symbols)
            for i, o in enumerate(ranked[:MAX_ROWS])]
    try:
        with lock_for(_path()):
            days = _read()
            old = next((d for d in days if str(d.get("as_of")) == day), None)
            if old and old.get("finalized") and not finalized:
                _written.add(key)
                return {"ok": True, "recorded": 0, "skipped": "已有收盘定稿"}
            days = [d for d in days if str(d.get("as_of")) != day]
            days.append({
                "as_of": day,
                "finalized": bool(finalized),
                # 打分口径版本 —— 换了口径的记录不能和老记录混进同一个胜率里
                "scoring_version": SCORING_VERSION,
                "rows": rows,
                "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            })
            days.sort(key=lambda d: str(d.get("as_of")))
            _write(days)
            _written.add(key)
    except Exception as e:  # noqa: BLE001 —— 记账失败绝不能影响总览本身
        logger.warning("record score ledger failed: %s", e)
        return {"ok": False, "recorded": 0}
    return {"ok": True, "recorded": len(rows)}


# --------------------------------------------------------------- 收益回看


def _needs_fill(days: list[dict]) -> dict[str, list[tuple[str, dict]]]:
    """哪些 (标的 → [(日期, 行)]) 还缺收益。只看定稿日。"""
    want: dict[str, list[tuple[str, dict]]] = {}
    for d in days:
        if not d.get("finalized"):
            continue
        day = str(d.get("as_of"))
        for row in d.get("rows") or []:
            sym = str(row.get("symbol") or "")
            r = row.get("r") or {}
            if not sym or not row.get("close"):
                continue
            if all(f"t{h}" in r for h in HORIZONS):
                continue
            want.setdefault(sym, []).append((day, row))
    return want


def _closes_after(repo, symbol: str, start: str) -> list[tuple[str, float]]:
    """start(不含)之后的 (日期, 收盘) 序列。一只票只读一次, 供它的所有记录共用。"""
    try:
        s = date.fromisoformat(start[:10])
        df = repo.get_daily_asset(
            repo.resolve_asset_type(symbol), symbol,
            s, date.today() + timedelta(days=1), columns=["date", "close"])
        if df is None or df.is_empty() or "date" not in df.columns:
            return []
        out: list[tuple[str, float]] = []
        for r in df.sort("date").select(["date", "close"]).to_dicts():
            d, c = str(r.get("date"))[:10], r.get("close")
            if d > start[:10] and c:
                out.append((d, float(c)))
        return out
    except Exception as e:  # noqa: BLE001
        logger.debug("score ledger closes failed for %s: %s", symbol, e)
        return []


def fill_returns(repo, days: list[dict]) -> tuple[int, int]:
    """把到期了的收益补上(就地改 days)。返回 (补了几只, 还差几只)。

    到期 = as_of 之后已经有第 h 根日 K。没到期的留空, 下次再补 ——
    **不能**用"目前最后一根"顶替, 那会把 T+2 的收益混进 T+5 的统计里。
    """
    want = _needs_fill(days)
    syms = sorted(want)
    todo, rest = syms[:MAX_FILL_SYMBOLS], syms[MAX_FILL_SYMBOLS:]
    filled = 0
    for sym in todo:
        entries = want[sym]
        earliest = min(day for day, _ in entries)
        seq = _closes_after(repo, sym, earliest)
        if not seq:
            continue
        for day, row in entries:
            after = [c for d, c in seq if d > day]
            base = row.get("close")
            if not base:
                continue
            r = row.setdefault("r", {})
            for h in HORIZONS:
                key = f"t{h}"
                if key in r or len(after) < h:
                    continue
                r[key] = round((after[h - 1] / float(base) - 1) * 100, 2)
                filled += 1
    return filled, len(rest)


def _bench_baseline(repo, day_dates: list[str]) -> dict:
    """同期基准指数的涨跌基线 —— 没有它, "胜率 55%" 说明不了任何问题。

    口径与候选完全一致: 同样的日期集合、同样的收盘对收盘、同样的 T+N。
    差别只在标的换成沪深300(取不到退到上证)。
    """
    from app.services.market_mode import BENCHMARKS, BENCHMARK_NAMES
    if not day_dates:
        return {}
    start = min(day_dates)
    for sym in BENCHMARKS:
        seq = _closes_after(repo, sym, (date.fromisoformat(start) - timedelta(days=1)).isoformat())
        if len(seq) < max(HORIZONS) + 1:
            continue
        by_date = {d: c for d, c in seq}
        dates_sorted = [d for d, _ in seq]
        out: dict[str, dict] = {}
        for h in HORIZONS:
            vals: list[float] = []
            for day in day_dates:
                if day not in by_date:
                    continue
                idx = dates_sorted.index(day)
                if idx + h >= len(dates_sorted):
                    continue
                base = by_date[day]
                vals.append((by_date[dates_sorted[idx + h]] / base - 1) * 100)
            out[f"t{h}"] = _agg(vals)
        return {"symbol": sym, "name": BENCHMARK_NAMES.get(sym, sym), "stats": out}
    return {}


# --------------------------------------------------------------- 统计


def _agg(vals: list[float]) -> dict:
    if not vals:
        return {"n": 0, "win_rate": None, "avg": None}
    wins = len([v for v in vals if v > 0])
    return {"n": len(vals), "win_rate": round(wins / len(vals) * 100, 1),
            "avg": round(sum(vals) / len(vals), 2)}


def _agg_rows(rows: list[dict]) -> dict:
    return {f"t{h}": _agg([r["r"][f"t{h}"] for r in rows
                           if r.get("r", {}).get(f"t{h}") is not None])
            for h in HORIZONS}


def _version_of(day: dict) -> int:
    """老记录没有这个字段, 它们都是 v1。"""
    try:
        return int(day.get("scoring_version") or 1)
    except (TypeError, ValueError):
        return 1


def _flat(days: list[dict], version: int | None = SCORING_VERSION) -> list[dict]:
    """定稿日的所有行摊平, 带上 as_of。

    [R134] 默认**只取当前打分口径**的记录。把 v1 和 v2 的分数混进同一个胜率里,
    等于拿两把不同刻度的尺子量同一段路 —— 算出来的分层单调性没有任何意义。
    version=None 时不过滤(导出用: 老记录也要能拿出去看)。
    """
    out = []
    for d in days:
        if not d.get("finalized"):
            continue
        if version is not None and _version_of(d) != version:
            continue
        for row in d.get("rows") or []:
            out.append({**row, "as_of": str(d.get("as_of")),
                        "scoring_version": _version_of(d)})
    return out


def _by_bucket(rows: list[dict]) -> list[dict]:
    out = []
    for lo, hi in SCORE_BINS:
        sub = [r for r in rows if lo <= r.get("score", -1) < hi]
        out.append({"label": f"{lo}-{hi - 1}", "lo": lo, "hi": hi - 1,
                    "count": len(sub), "stats": _agg_rows(sub)})
    return out


def _by_rank(rows: list[dict]) -> list[dict]:
    out = []
    for cut in RANK_CUTS:
        sub = [r for r in rows if 1 <= r.get("rank", 999) <= cut]
        out.append({"label": f"前 {cut}", "cut": cut,
                    "count": len(sub), "stats": _agg_rows(sub)})
    return out


# 维度分的高/低分界。取 70/40 是因为曲线峰值区都在 90 以上、谷底在 20 以下,
# 70 以上基本等于"这一维在甜区", 40 以下等于"这一维明确不合格"。
DIM_HIGH, DIM_LOW = 70.0, 40.0


def _by_factor(rows: list[dict]) -> list[dict]:
    """每个维度: 高分组 / 低分组 / 缺席, 三组分别的表现。

    [R134] v1 时这里分的是"吃到加分 / 吃到扣分"; v2 的维度分是 0~100 的连续量,
    没有正负, 所以改成按分数高低切。要回答的问题没变: **高分组不明显强于低分组,
    这一维就是在白占权重**。这是调参最直接的入口 —— 比如量能维度两组胜率一样,
    就该把 30% 的权重挪给趋势或位置。

    "缺席"那一列同样要看: 它是数据覆盖率的体检 —— 缺席比例高的维度,
    它的权重其实有一大半在被重归一化悄悄分给别人。
    """
    out = []
    for key, label in FACTOR_LABELS.items():
        vals = [(r, (r.get("f") or {}).get(key)) for r in rows]
        high = [r for r, v in vals if v is not None and v >= DIM_HIGH]
        low = [r for r, v in vals if v is not None and v < DIM_LOW]
        mid = [r for r, v in vals if v is not None and DIM_LOW <= v < DIM_HIGH]
        none = [r for r, v in vals if v is None]
        if not high and not low and not mid:
            continue
        out.append({
            "key": key, "label": label,
            "plus": {"count": len(high), "stats": _agg_rows(high)},
            "mid": {"count": len(mid), "stats": _agg_rows(mid)},
            "minus": {"count": len(low), "stats": _agg_rows(low)},
            "none": {"count": len(none), "stats": _agg_rows(none)},
        })
    return out


def _monotonic_note(buckets: list[dict], horizon: str = "t5") -> dict:
    """分层单调性 —— 这套评分有没有信息量, 主要看这一条。

    只在有样本的相邻档之间比。样本不足时如实说"还不能下结论", 不硬给结论。
    """
    seq = [(b["label"], b["stats"][horizon]["win_rate"], b["stats"][horizon]["n"])
           for b in buckets if b["stats"][horizon]["n"] >= 10]
    if len(seq) < 2:
        return {"ok": None, "text": f"有效分层不足 2 档(每档至少 10 个样本), {horizon.upper()} 还看不出单调性"}
    breaks = [f"{seq[i][0]}({seq[i][1]}%) → {seq[i + 1][0]}({seq[i + 1][1]}%)"
              for i in range(len(seq) - 1)
              if (seq[i + 1][1] or 0) < (seq[i][1] or 0)]
    lo, hi = seq[0][1] or 0, seq[-1][1] or 0
    if not breaks:
        return {"ok": True, "text": f"{horizon.upper()} 胜率随把握分单调上升({seq[0][0]} {lo}% → {seq[-1][0]} {hi}%), 分数是有信息量的"}
    if len(breaks) == 1 and hi > lo:
        return {"ok": True, "text": f"{horizon.upper()} 整体向上({lo}% → {hi}%), 有 1 处回落: {breaks[0]} —— 样本还少, 暂可接受"}
    return {"ok": False, "text": f"{horizon.upper()} 分层不单调, {len(breaks)} 处回落: {'; '.join(breaks)} —— 把握分没有把好票排到前面"}


# ======================= [R175] 回头看: 按标签分组 =======================
#
# 台账原来只按**把握分**切(90 分档 vs 70 分档谁的胜率高)。可界面上还有一批
# "说了句话但一分不参与打分"的标签 —— 通道结论、六态趋势、主线名次、龙虎榜。
# 恰恰因为它们不参与打分, 从来没人验证过它们说得对不对。
#
# 这里把它们换个轴切一遍。做法就是最朴素的 group-by, 没有模型也没有 AI ——
# 标签本身已经是离散的, 分组算前瞻收益就是全部答案。
#
# 关键是**两列并排**: 全期 vs 最近 N 日。
#   · 全期  = 这个标签长期什么成色
#   · 最近  = 它现在什么成色
# 用户问的"这个东西正在遵循什么规律", 落到实处就是这两列的**背离**:
# 长期能赚的那档最近开始亏, 才是真正要看见的信号。单看全期看不出来 ——
# 一年的均值会把最近一个月的转向稀释掉。

# 最近多少个**记录日**算"最近"。20 个交易日 ≈ 一个月, 短到能反映当前风格,
# 又不至于每档只剩两三个样本。
RECENT_DAYS = 20
# 一档至少要有多少样本才给读数。低于它照样列出来(要让用户看见"这档还没攒够"),
# 但不给胜率 —— 5 个样本的 60% 和 500 个样本的 60% 不是一回事。
MIN_LABEL_N = 15


def _verdict_titles() -> dict[str, str]:
    from app.indicators.keltner import _VERDICTS
    return {code: v[0] for code, v in _VERDICTS.items()}


def _state_titles() -> dict[str, str]:
    from app.indicators.livermore import STATE_LABELS
    return {code: cn for code, (cn, _en) in STATE_LABELS.items()}


def _rhythm_cn(v: str) -> str:
    from app.services.trend_rhythm import LEVEL_CN
    return LEVEL_CN.get(v, v)


def _basing_bucket(v) -> str:
    try:
        d = int(v)
    except (TypeError, ValueError):
        return "—"
    if d < 20:
        return "没在磨(<20天)"
    if d < 60:
        return "磨 20-60 天"
    if d < 120:
        return "磨 60-120 天"
    return "磨 120 天以上"


def _mainline_label(v) -> str:
    try:
        r = int(v)
    except (TypeError, ValueError):
        return "非主线"
    return f"主线第 {r} 位" if r <= 3 else "主线 4 位以后"


# 标签维度注册表。**加一个新标签就是加一行** —— 以后再往界面上添什么"结论",
# 只要它落进了 ctx, 在这里登记一行就能回答"我历史上好不好使"。
#   key    : ctx 里的字段名
#   label  : 界面上这一维叫什么
#   fmt    : 取值 → 人能读的名字
def _accel_cn(v) -> str:
    from app.indicators.keltner_geometry import ACCEL_CN
    return ACCEL_CN.get(str(v), str(v))


def _event_cn(v) -> str:
    from app.indicators.keltner_geometry import EVENT_CN
    return EVENT_CN.get(str(v), str(v))


def _tpl_bucket(v) -> str:
    """趋势模板通过条数 → 分档。八条里过几条是 0~8 的整数, 但 0~4 那几档
    样本会很少(过不了 5 条的票多半也过不了 G1/G3 门槛), 合成一档。"""
    try:
        n = int(v)
    except (TypeError, ValueError):
        return "—"
    if n >= 8:
        return "模板 8/8 全过"
    if n == 7:
        return "模板 7/8"
    if n == 6:
        return "模板 6/8"
    return "模板 ≤5/8"


LABEL_DIMS: list[dict] = [
    {"key": "verdict", "label": "通道结论",
     "fmt": lambda v: _verdict_titles().get(str(v), str(v))},
    {"key": "state", "label": "六态趋势",
     "fmt": lambda v: _state_titles().get(str(v), str(v))},
    {"key": "mainline_rank", "label": "主线归属", "fmt": _mainline_label},
    {"key": "dragon", "label": "龙虎榜", "fmt": lambda v: "上榜" if v else "未上榜"},
    # [R188] 红绿节拍。这一条正是加注册表的意义 —— R175 说「以后往界面加什么
    # 结论, 落进 ctx 再登记一行就能回答"我历史上好不好使"」, 这是第一次兑现。
    {"key": "rhythm", "label": "红绿节拍",
     "fmt": lambda v: _rhythm_cn(str(v))},
    # 磨底时长分档。天数本身是连续量, 直接当分组维度会碎成几百档 ——
    # 分成四段才看得出"磨得久的是不是真的更好"。
    {"key": "basing_days", "label": "磨底时长", "fmt": _basing_bucket},
    # [R189] 趋势模板通过条数。这一维是本次改动最该被验证的那个 ——
    # 「8 条全过的票是不是真的更好」直接决定 TEMPLATE_CURVE 那条上凸曲线
    # 该不该继续凸下去。
    {"key": "tpl_passed", "label": "趋势模板", "fmt": _tpl_bucket},
    # [R195] 量化波动通道的三个新维度。**事件那一条是本次最该被验证的** ——
    # 「主升浪特征之后是不是真的更好」直接决定 MAIN_ADVANCE 那五条阈值该不该
    # 继续这么定; 而那五条目前全是先验, 一条都没有台账支持。
    {"key": "chan_event", "label": "通道事件", "fmt": _event_cn},
    {"key": "accel", "label": "加速度", "fmt": _accel_cn},
    # 三档位置的三字码(如「上中下」)。27 种组合直接当分组维度会碎得没法看,
    # 但它是**唯一**能回答"哪几种组合真的好使"的东西, 所以原样落。
    {"key": "combo", "label": "通道组合", "fmt": lambda v: f"组合 {v}"},
]



def _by_label(rows: list[dict], recent_dates: set[str]) -> list[dict]:
    """每个标签维度 → 各取值的全期与最近表现。

    没有这个标签的行归进 "—"(未标注)那一档, 不丢掉 —— 丢掉的话每档的占比
    会失真, 用户会以为"通道结论天天都有", 其实多数日子它是 None。
    """
    out = []
    for dim in LABEL_DIMS:
        key, fmt = dim["key"], dim["fmt"]
        groups: dict[str, list[dict]] = {}
        for r in rows:
            v = (r.get("ctx") or {}).get(key)
            groups.setdefault("—" if v is None else fmt(v), []).append(r)
        items = []
        for name, sub in groups.items():
            recent = [r for r in sub if str(r.get("as_of")) in recent_dates]
            items.append({
                "value": name,
                "count": len(sub),
                "recent_count": len(recent),
                "stats": _agg_rows(sub),
                "recent_stats": _agg_rows(recent),
                "shift": _shift_note(_agg_rows(sub), _agg_rows(recent)),
            })
        # 样本多的排前面 —— 用户先看见的应该是站得住的那几档
        items.sort(key=lambda x: -x["count"])
        out.append({"key": key, "label": dim["label"], "items": items})
    return out


def _shift_note(all_st: dict, recent_st: dict, horizon: str = "t5") -> dict | None:
    """全期与最近的背离。**这是整个"回头看"里唯一有信息量的那个数。**

    两边样本都够才给结论。差值用胜率(不是均值) —— 均值容易被一两只翻倍股
    带偏, 而这里问的是"还灵不灵", 胜率更贴题。
    """
    a, b = all_st.get(horizon) or {}, recent_st.get(horizon) or {}
    if (a.get("n") or 0) < MIN_LABEL_N or (b.get("n") or 0) < MIN_LABEL_N:
        return None
    aw, bw = a.get("win_rate"), b.get("win_rate")
    if aw is None or bw is None:
        return None
    d = round(bw - aw, 1)
    # 10 个百分点以内当噪声。样本这个量级下, 更小的差值说不出什么。
    if abs(d) < 10:
        return {"dir": "flat", "delta": d,
                "text": f"最近与全期基本一致({aw}% → {bw}%)"}
    if d < 0:
        return {"dir": "down", "delta": d,
                "text": f"最近明显转差: 全期 {aw}% → 最近 {bw}%({d} 个百分点)"}
    return {"dir": "up", "delta": d,
            "text": f"最近明显转好: 全期 {aw}% → 最近 {bw}%(+{d} 个百分点)"}


def evaluate(repo, days_limit: int = MAX_DAYS) -> dict:
    """补齐收益并给出全套统计。补出来的收益会落盘, 下次不必重算。"""
    from app.services.json_store import lock_for
    pending, all_days = 0, []
    try:
        with lock_for(_path()):
            all_days = _read()
            days = all_days[-days_limit:]   # 同一批 dict 对象, 就地补完直接整本写回
            filled, pending = fill_returns(repo, days)
            if filled:
                _write(all_days)
    except Exception as e:  # noqa: BLE001
        logger.warning("score ledger evaluate/fill failed: %s", e)
    days = all_days[-days_limit:]

    rows = _flat(days)                          # 只含当前打分口径
    scored = [r for r in rows if r.get("r")]
    shown = [r for r in rows if r.get("shown")]
    buckets = _by_bucket(rows)
    day_dates = sorted({str(d.get("as_of")) for d in days
                        if d.get("finalized") and _version_of(d) == SCORING_VERSION})
    legacy_days = sorted({str(d.get("as_of")) for d in days
                          if d.get("finalized") and _version_of(d) != SCORING_VERSION})
    try:
        baseline = _bench_baseline(repo, day_dates)
    except Exception as e:  # noqa: BLE001
        logger.debug("score ledger baseline skipped: %s", e)
        baseline = {}

    return {
        "recorded_days": len(day_dates),
        "total_rows": len(rows),
        "evaluated_rows": len(scored),
        "pending_symbols": pending,
        "scoring_version": SCORING_VERSION,
        # 换口径之前的记录: 不进统计(两把尺子不能混), 但要如实报出来,
        # 否则用户会以为"攒了一个月怎么样本还是这么少"
        "legacy_days": len(legacy_days),
        "first_day": day_dates[0] if day_dates else None,
        "last_day": day_dates[-1] if day_dates else None,
        "all": _agg_rows(rows),
        "shown": _agg_rows(shown),
        "buckets": buckets,
        "ranks": _by_rank(rows),
        "factors": _by_factor(rows),
        # [R175] 回头看: 把不参与打分的那批标签也拉出来验一验
        "labels": _by_label(rows, set(day_dates[-RECENT_DAYS:])),
        "recent_days": min(RECENT_DAYS, len(day_dates)),
        "min_label_n": MIN_LABEL_N,
        "baseline": baseline,
        "monotonic": _monotonic_note(buckets),
        "caveat": CAVEAT,
    }


# --------------------------------------------------------------- 摘要(可粘贴)


def _cell(st: dict) -> str:
    if not st or not st.get("n"):
        return "—"
    return f"{st['win_rate']}% / {st['avg']:+.2f}% (n={st['n']})"


def build_summary_md(res: dict, ai_stats: dict | None = None) -> str:
    """把体检结果拼成一段可直接粘贴的 Markdown。

    存在的理由很实际: 调参的人(或 AI)需要的是**成套**的数字 —— 分层、排名段、
    因子归因、同期基准缺一不可, 单看"前十胜率 58%"什么都推不出来。让用户自己
    从四张表里抄, 抄漏一行结论就跟着歪。所以服务端一次拼好, 点一下全带走。

    刻意带上口径与样本量: 没有样本量的胜率是废话, 没有基准的胜率会骗人。
    """
    L: list[str] = []
    L.append("# 把握分评分系统体检(R133 规则层台账)")
    L.append("")
    L.append(f"- 记录区间: {res.get('first_day') or '—'} ~ {res.get('last_day') or '—'}"
             f"({res.get('recorded_days', 0)} 个交易日)")
    L.append(f"- 候选行数: {res.get('total_rows', 0)},已算出收益: {res.get('evaluated_rows', 0)}")
    if res.get("pending_symbols"):
        L.append(f"- 还有 {res['pending_symbols']} 只标的的收益没补完(下次打开继续补)")
    L.append(f"- 口径: {res.get('caveat', '')}")
    L.append("")

    L.append("## 总体(格式: 胜率 / 平均收益 (样本数))")
    L.append("")
    L.append("| 范围 | T+1 | T+3 | T+5 |")
    L.append("|---|---|---|---|")
    for label, key in (("全部候选(含被门槛滤掉的)", "all"), ("当时实际显示的", "shown")):
        st = res.get(key) or {}
        L.append(f"| {label} | {_cell(st.get('t1'))} | {_cell(st.get('t3'))} | {_cell(st.get('t5'))} |")
    bl = res.get("baseline") or {}
    if bl.get("stats"):
        s = bl["stats"]
        L.append(f"| 同期基准 {bl.get('name', '')}(每个记录日等权) "
                 f"| {_cell(s.get('t1'))} | {_cell(s.get('t3'))} | {_cell(s.get('t5'))} |")
    else:
        L.append("| 同期基准 | — | — | — |")
    if ai_stats:
        L.append(f"| 参考: AI 优选(R121 台账) | {_cell(ai_stats.get('t1'))} "
                 f"| {_cell(ai_stats.get('t3'))} | {_cell(ai_stats.get('t5'))} |")
    L.append("")

    L.append("## 分层单调性(最关键的一张表)")
    L.append("")
    L.append(f"> {(res.get('monotonic') or {}).get('text', '')}")
    L.append("")
    L.append("| 把握分档 | 条数 | T+1 | T+3 | T+5 |")
    L.append("|---|---|---|---|---|")
    for b in res.get("buckets") or []:
        st = b.get("stats") or {}
        L.append(f"| {b['label']} | {b['count']} | {_cell(st.get('t1'))} "
                 f"| {_cell(st.get('t3'))} | {_cell(st.get('t5'))} |")
    L.append("")

    L.append("## 按名次(用来定「最多显示几条」)")
    L.append("")
    L.append("| 名次段 | 条数 | T+1 | T+3 | T+5 |")
    L.append("|---|---|---|---|---|")
    for r in res.get("ranks") or []:
        st = r.get("stats") or {}
        L.append(f"| {r['label']} | {r['count']} | {_cell(st.get('t1'))} "
                 f"| {_cell(st.get('t3'))} | {_cell(st.get('t5'))} |")
    L.append("")

    L.append(f"## 维度归因(T+5;高分组 ≥{DIM_HIGH:.0f} 分,低分组 <{DIM_LOW:.0f} 分)")
    L.append("")
    L.append("> 高分组不明显强于低分组 = 这一维在白占权重,该把它的权重挪给别的维度。"
             "「缺席」比例高说明数据覆盖不足,那部分权重其实被重归一化悄悄分掉了。")
    L.append("")
    L.append("| 维度 | 高分组 | 中间 | 低分组 | 缺席 |")
    L.append("|---|---|---|---|---|")
    for f in res.get("factors") or []:
        def c(side: str) -> str:
            g = f.get(side) or {}
            return f"{_cell((g.get('stats') or {}).get('t5'))}"
        L.append(f"| {f['label']} | {c('plus')} | {c('mid')} | {c('minus')} | {c('none')} |")
    L.append("")
    L.append(f"当前打分口径 v{res.get('scoring_version')}(三道硬门槛 + 三维度加权)。")
    if res.get("legacy_days"):
        L.append(f"另有 {res['legacy_days']} 天是换口径之前记的,**未计入上面任何一张表** ——"
                 "两套分数刻度不同,混在一起算胜率没有意义。")
    L.append("")
    L.append("需要更细的可以要明细 CSV(同一面板里「导出明细 CSV」按钮),"
             "一行一候选,三个维度分与每个因子的子分各占一列,可离线重算任意权重组合。")
    return "\n".join(L)


# --------------------------------------------------------------- 导出


# 每个因子的子分(0~100), 与 opportunity_score.FACTOR_CN 的键一一对应。
# 维度分说明"量能这一档不行", 子分才说明"是量比不行还是换手不行"。
SUB_FACTOR_KEYS = ("fresh", "state", "rs", "vol_ratio", "turnover", "pos")

CSV_HEADER = [
    "as_of", "scoring_version", "symbol", "name", "score", "rank", "shown",
    "kind", "board", "close",
    # 三个维度分 —— 离线重算权重的起点
    *[f"dim_{k}" for k in FACTOR_LABELS],
    *[f"sub_{k}" for k in SUB_FACTOR_KEYS],
    "ctx_dur", "ctx_state", "ctx_vol_ratio", "ctx_turnover", "ctx_channel_pct",
    "ctx_rs", "ctx_gap_pct", "ctx_partial", "ctx_fresh_from", "ctx_kinds",
    "ctx_intraday",
    # v1 老记录才有的加减项, 一并带出去(v2 的行全是空) —— 换口径不该让历史消失
    *[f"legacy_{k}" for k in LEGACY_FACTOR_LABELS],
    "legacy_win_rate", "legacy_win_n", "legacy_mainline_rank", "legacy_verdict",
    *[f"ret_t{h}" for h in HORIZONS],
]


def export_csv(repo) -> str:
    """整本台账导出成一行一候选的 CSV —— 交给外部做调参/回归的入口。

    刻意做成扁平宽表而不是嵌套 JSON: 因子增量各占一列, 直接就能丢进
    Excel 透视表或 pandas 分组, 不需要先写解析代码。
    """
    import csv
    import io
    from app.services.json_store import lock_for
    try:
        with lock_for(_path()):
            days = _read()
            filled, _ = fill_returns(repo, days)
            if filled:
                _write(days)
    except Exception as e:  # noqa: BLE001
        logger.warning("score ledger export fill failed: %s", e)
        days = _read()

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(CSV_HEADER)
    for d in days:
        day, fin, ver = str(d.get("as_of")), d.get("finalized"), _version_of(d)
        for row in d.get("rows") or []:
            f, ctx, r = row.get("f") or {}, row.get("ctx") or {}, row.get("r") or {}
            w.writerow([
                day, ver, row.get("symbol"), row.get("name"), row.get("score"),
                row.get("rank"), int(bool(row.get("shown"))), row.get("kind"),
                row.get("board"), row.get("close"),
                *[f.get(k) for k in FACTOR_LABELS],
                *[ctx.get(f"sub_{k}") for k in SUB_FACTOR_KEYS],
                ctx.get("dur"), ctx.get("state"), ctx.get("vol_ratio"),
                ctx.get("turnover"), ctx.get("channel_pct"), ctx.get("rs"),
                ctx.get("gap_pct"), int(bool(ctx.get("partial"))),
                ctx.get("fresh_from"), ctx.get("kinds"),
                int(bool(ctx.get("intraday"))) if not fin else 0,
                *[f.get(k) for k in LEGACY_FACTOR_LABELS],
                ctx.get("win_rate"), ctx.get("win_n"), ctx.get("mainline_rank"),
                ctx.get("verdict"),
                *[r.get(f"t{h}") for h in HORIZONS],
            ])
    return buf.getvalue()
