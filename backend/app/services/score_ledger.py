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
# 因子中文名 —— 归因表直接用, 别让用户对着 key 猜
FACTOR_LABELS = {
    "fresh": "信号新鲜度",
    "ai": "AI 信号同向/反向",
    "rs": "相对强度(对大盘)",
    "vol": "量比",
    "win": "该票历史胜率",
    "mainline": "主线归属",
    "verdict": "Keltner 通道结论",
    "near": "紧贴触发价",
    # 不是"因子", 是把握分被夹到 100 削掉的那部分。单列出来是因为它本身就是个
    # 结论: 顶格的那批票在榜上彼此没有区分度, 它们的表现值不值这个第一名要看数据
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
    """一条候选 → 台账行。只留调参用得上的字段, 别把整份总览抄进来。"""
    f = {k: v for k, v in (o.get("factors") or {}).items() if v}
    ctx = o.get("ctx") or {}
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


def _flat(days: list[dict]) -> list[dict]:
    """定稿日的所有行摊平, 带上 as_of。"""
    out = []
    for d in days:
        if not d.get("finalized"):
            continue
        for row in d.get("rows") or []:
            out.append({**row, "as_of": str(d.get("as_of"))})
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


def _by_factor(rows: list[dict]) -> list[dict]:
    """每个因子: 吃到加分的 / 吃到扣分的 / 没触发的, 三组分别的表现。

    加分组不明显强于扣分组 —— 那个因子就是在白占权重。这是调参最直接的入口。
    """
    out = []
    for key, label in FACTOR_LABELS.items():
        plus = [r for r in rows if (r.get("f") or {}).get(key, 0) > 0]
        minus = [r for r in rows if (r.get("f") or {}).get(key, 0) < 0]
        none = [r for r in rows if not (r.get("f") or {}).get(key)]
        if not plus and not minus:
            continue
        out.append({
            "key": key, "label": label,
            "plus": {"count": len(plus), "stats": _agg_rows(plus)},
            "minus": {"count": len(minus), "stats": _agg_rows(minus)},
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

    rows = _flat(days)
    scored = [r for r in rows if r.get("r")]
    shown = [r for r in rows if r.get("shown")]
    buckets = _by_bucket(rows)
    day_dates = sorted({str(d.get("as_of")) for d in days if d.get("finalized")})
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
        "first_day": day_dates[0] if day_dates else None,
        "last_day": day_dates[-1] if day_dates else None,
        "all": _agg_rows(rows),
        "shown": _agg_rows(shown),
        "buckets": buckets,
        "ranks": _by_rank(rows),
        "factors": _by_factor(rows),
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

    L.append("## 因子归因(T+5;加分组不明显强于扣分组 = 这个因子在白占权重)")
    L.append("")
    L.append("| 因子 | 加分组 | 扣分组 | 未触发 |")
    L.append("|---|---|---|---|")
    for f in res.get("factors") or []:
        def c(side: str) -> str:
            g = f.get(side) or {}
            return f"{_cell((g.get('stats') or {}).get('t5'))}"
        L.append(f"| {f['label']} | {c('plus')} | {c('minus')} | {c('none')} |")
    L.append("")
    L.append("需要更细的可以要明细 CSV(同一面板里「导出明细 CSV」按钮),"
             "一行一候选, 因子增量各占一列, 可离线重算任意权重组合。")
    return "\n".join(L)


# --------------------------------------------------------------- 导出


CSV_HEADER = [
    "as_of", "symbol", "name", "score", "rank", "shown", "kind", "board", "close",
    # f_base 单列: 底分(转多70/回升55/逼近62)不是"因子"(不进归因表), 但离线重算
    # 权重时它是起点, 少了这一列就复原不出总分
    "f_base",
    *[f"f_{k}" for k in FACTOR_LABELS],
    "ctx_dur", "ctx_signal", "ctx_vol_ratio", "ctx_rs", "ctx_win_rate", "ctx_win_n",
    "ctx_mainline_rank", "ctx_verdict", "ctx_gap_pct", "ctx_intraday",
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
        day, fin = str(d.get("as_of")), d.get("finalized")
        for row in d.get("rows") or []:
            f, ctx, r = row.get("f") or {}, row.get("ctx") or {}, row.get("r") or {}
            w.writerow([
                day, row.get("symbol"), row.get("name"), row.get("score"),
                row.get("rank"), int(bool(row.get("shown"))), row.get("kind"),
                row.get("board"), row.get("close"),
                f.get("base", 0), *[f.get(k, 0) for k in FACTOR_LABELS],
                ctx.get("dur"), ctx.get("signal"), ctx.get("vol_ratio"), ctx.get("rs"),
                ctx.get("win_rate"), ctx.get("win_n"), ctx.get("mainline_rank"),
                ctx.get("verdict"), ctx.get("gap_pct"),
                int(bool(ctx.get("intraday"))) if not fin else 0,
                *[r.get(f"t{h}") for h in HORIZONS],
            ])
    return buf.getvalue()
