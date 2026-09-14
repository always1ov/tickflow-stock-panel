"""[fork 增强] R327 转折模拟盘的**取数层** —— 把自选股喂给 `flip_portfolio`。

纯函数那一层(`flip_portfolio.simulate`)不碰 repo、不读盘。这一层负责把它要的
几条序列备齐, 然后原样转交。分开的理由和 R287 一样: 判定逻辑要能被喂假数据逐条
钉住, 而取数那一半靠的是真盘。

## 一趟 IO, 不是 N 趟

自选上百只时逐只 `get_daily_asset` 就是上百趟。R156 走通过 `get_daily_batch`
那条路(历史胜率), R312 又走了一遍(批量回测), 这里是第三处 —— **口径必须与
逐只那条路逐值相同**, 省 IO 不许顺带改口径, 有守卫钉着。

## 阈值用每只票自己的

`livermore_service.get_effective_threshold(symbol)` —— 用户在单只弹窗里精心调过
的那个值。**不在这里用全局默认糊弄**: 模拟盘要回答的是"我这套判定真按它做行不
行", 拿一个用户没在用的阈值跑出来的曲线, 回答的是别人的问题。
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

import polars as pl

from app.indicators.livermore import compute
from app.services import flip_portfolio, flip_today, livermore_service, watchlist
from app.services.live_quotes import watchlist_live_map

logger = logging.getLogger(__name__)

# 要几年的历史。转折是低频信号 —— 窗口太短会只剩两三个转折, 曲线说明不了任何事。
DEFAULT_YEARS = 2
_CALENDAR_RATIO = 1.7          # 交易日 → 日历日(节假日 + 停牌), 与 review_service 同
_WARMUP_BARS = 60              # 状态机热身; 头几十根算出来的状态还没稳

_COLS = ("symbol", "date", "close", "signal_limit_up", "signal_limit_down")


def run(repo, *, symbols: list[str] | None = None,
        capital: float = flip_portfolio.DEFAULT_CAPITAL,
        max_positions: int = flip_portfolio.DEFAULT_MAX_POSITIONS,
        years: int = DEFAULT_YEARS) -> dict:
    """跑一遍转折模拟盘。`symbols` 不给就取当前自选。"""
    # `symbols is None` = 没指定, 用自选; `symbols == []` = **明确要空**, 就是空。
    # 用 `symbols or 自选` 会把这两件事混成一件 —— 「没给」与「给了个空的」不是
    # 同一回事(R246/R248 那个坑的同族)。
    pool = _watchlist_symbols() if symbols is None else symbols
    syms = [str(s).strip().upper() for s in pool if s]
    syms = sorted(set(syms))
    if not syms:
        return {**flip_portfolio.simulate({}), "symbols": [], "reason": "no_watchlist"}

    names = _names(repo, syms)
    frames = _load_batch(repo, syms, years)
    series: dict[str, dict] = {}
    for sym in syms:
        df = frames.get(sym)
        if df is None or df.is_empty() or len(df) < 2:
            continue
        threshold, _src = livermore_service.get_effective_threshold(sym)
        closes = [float(c) for c in df["close"]]
        dates = [str(d) for d in df["date"]]
        try:
            steps = compute(closes, dates, threshold)["steps"]
        except Exception as e:  # noqa: BLE001
            logger.debug("flip portfolio compute failed for %s: %s", sym, e)
            continue
        series[sym] = {
            "name": names.get(sym, sym),
            "steps": steps,
            "dates": dates,
            "closes": closes,
            "limit_up": _flags(df, "signal_limit_up"),
            "limit_down": _flags(df, "signal_limit_down"),
        }

    out = flip_portfolio.simulate(series, capital=capital, max_positions=max_positions)
    out["today"] = _today_signals(repo, series, out.get("positions") or [], names)
    out["symbols"] = sorted(series)
    out["missing"] = sorted(set(syms) - set(series))
    out["capital"] = capital
    out["max_positions"] = max_positions
    return out


def _watchlist_symbols() -> list[str]:
    try:
        return sorted(watchlist.symbol_set())
    except Exception as e:  # noqa: BLE001
        logger.warning("flip portfolio: 读自选失败: %s", e)
        return []


def _names(repo, syms: list[str]) -> dict[str, str]:
    """{symbol: 名称}。

    [R328] **名称从 repo 取, 不从自选条目取。** 第一版写的是
    `watchlist.list_symbols()` 里的 `r.get("name")` —— 而自选表**根本没有 name
    这一列**(schema 只有 symbol / added_at / note / group_ids), 于是每一行都走
    `or r.get("symbol")` 那个回退, 整张持仓表印出来是「000636.SZ 000636.SZ」。
    **没有任何东西会报错**, 因为回退本身是"成功"的。

    `repo.get_name_map()` 是这个仓库解析名称的统一入口(自选页 `api/watchlist.py`
    两处用的都是它), 合并了股票 + ETF + 指数三份维表。**不另走一条** —— 同一件事
    两处实现, 哪天维表口径改了必然漂。
    """
    try:
        m = repo.get_name_map(syms)
    except Exception as e:  # noqa: BLE001
        logger.warning("flip portfolio: 名称解析失败, 退回代码: %s", e)
        return {s: s for s in syms}
    # 维表里查不到的(退市、新股还没进维表)仍退回代码 —— 宁可印代码, 不印空白
    return {s: str(m.get(s) or s) for s in syms}


def _load_batch(repo, syms: list[str], years: int) -> dict[str, pl.DataFrame]:
    """一趟批量读。非股票(ETF/指数)批量接口给不了, 逐只回退 —— **不静默丢掉**。"""
    end = date.today()
    span = int((years * 250 + _WARMUP_BARS) * _CALENDAR_RATIO) + 30
    start = end - timedelta(days=span)
    out: dict[str, pl.DataFrame] = {}

    stock: list[str] = []
    for s in syms:
        try:
            is_stock = repo.resolve_asset_type(s) == "stock"
        except Exception:  # noqa: BLE001
            # 认不出资产类型就当股票试一把 —— 批量拿不到还有下面的逐只回退兜着,
            # 直接跳过才是真丢数据
            is_stock = True
        if is_stock:
            stock.append(s)
    if stock:
        try:
            df = repo.get_daily_batch(stock, start, end, list(_COLS))
        except Exception as e:  # noqa: BLE001
            logger.warning("flip portfolio batch daily failed: %s", e)
            df = pl.DataFrame()
        if df is not None and not df.is_empty() and "symbol" in df.columns:
            for sym, part in df.group_by("symbol"):
                key = str(sym[0] if isinstance(sym, tuple) else sym).upper()
                out[key] = part.drop_nulls("close").sort("date")

    for s in syms:
        if s in out:
            continue
        try:
            at = repo.resolve_asset_type(s)
            df = repo.get_daily_asset(at, s, start, end, columns=[c for c in _COLS if c != "symbol"])
            if df is not None and not df.is_empty():
                out[s] = df.drop_nulls("close").sort("date")
        except Exception as e:  # noqa: BLE001
            logger.debug("flip portfolio window for %s failed: %s", s, e)
    return out


def _flags(df: pl.DataFrame, col: str) -> list[bool]:
    """涨跌停标志。**列不存在就一律 False** —— 与 `simulate` 的约定一致:
    不给标志就当能成交, 不瞎猜。"""
    if col not in df.columns:
        return [False] * len(df)
    return [bool(v) if v is not None else False for v in df[col]]


def _today_signals(repo, series: dict[str, dict], positions: list[dict],
                   names: dict[str, str]) -> list[dict]:
    """[R329] 今日信号 —— 「收盘前五分钟该挂什么单」。

    **持仓取自模拟盘刚算完的那一份**, 不是真实持仓: 这一栏说的是"这套规则现在
    会让我做什么", 而规则手上拿着什么由它自己的账决定。混进真钱持仓就成了另一
    个问题的答案。

    实时价拿不到就不传 —— `evaluate` 会退回收盘口径并标 `live=false`,
    **不替用户去开那个要花额度的开关**。
    """
    held = {p["symbol"] for p in positions}
    try:
        live = watchlist_live_map(repo)
    except Exception as e:  # noqa: BLE001
        logger.debug("flip today: 实时叠加层读不到, 按收盘口径: %s", e)
        live = {}

    out: list[dict] = []
    for sym, d in series.items():
        closes = d.get("closes") or []
        sig = flip_today.evaluate(
            d.get("steps") or [],
            held=sym in held,
            last_close=closes[-1] if closes else None,
            live_close=(live.get(sym) or {}).get("close"),
        )
        if sig is None:
            continue
        out.append({"symbol": sym, "name": names.get(sym, sym), **sig})

    # 能出手的排最前, 其次盘中越线, 最后只是盯着 —— **版面顺序即急迫程度**
    rank = {flip_today.STAGE_FLIPPED: 0, flip_today.STAGE_CROSSING: 1,
            flip_today.STAGE_WATCH: 2}
    out.sort(key=lambda r: (rank.get(r["stage"], 9), r["act"] is None,
                            abs(r.get("gap_pct") or 0), r["symbol"]))
    return out
