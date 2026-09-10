"""[fork 增强] R48 单只个股的逐日复盘。

决策台的「趋势」和「结论」两列只显示**今天**的读数。要判断这两列到底靠不靠谱,
得能翻回去看: 上次它说"强势深调"是哪天、之后走了什么、这只票的涨停都出现在
什么状态下。这个模块就是把那段历史一次算出来。

三样东西按同一条时间轴对齐:
  · 六态趋势状态 —— 走 ``indicators.livermore.compute`` 的 steps, 与决策台
    「趋势」列同一个状态机、同一个阈值(含用户自己调过的那个)。
  · Keltner 三档位置与结论 —— 走 ``indicators.keltner``, 与决策台三列、
    「结论」列、个股分析图表同一组公式, 只是把输入换成当天的均线/ATR。
  · 涨停 / 跌停 / 炸板 / 连板数 —— 直接取 enriched 的预计算列, 不自己判
    (涨跌停幅度按板块和 ST 状态分档, 那套判定在 pipeline 里已经很细了)。

口径提醒(界面要显示出来): 均线与 ATR 都是按**当前**复权因子回算的。之后除权
的话, 同一天今天算出来的通道会和当天实际看到的略有出入 —— 复盘看的是形态与
节奏, 不是当时屏幕的像素级还原。
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

import polars as pl

from app.indicators import keltner as k
from app.indicators import keltner_geometry as k_geo
from app.indicators.livermore import BULLISH, STATE_LABELS, compute
from app.services import flip_trades

logger = logging.getLogger(__name__)

# 默认回看多少个交易日。半年够看完一轮完整的趋势切换, 再长的话表格本身就没法读了。
DEFAULT_DAYS = 120
MAX_DAYS = 250

# 长期档要 120 根做暖机, 六态状态机也需要一段历史才稳定 —— 多取的这部分只参与
# 计算, 不进结果。
_WARMUP_BARS = 130
# 交易日 → 日历日的换算余量(节假日 + 停牌)
_CALENDAR_RATIO = 1.7

# 结论出现之后看几天 —— 与历史胜率那套(livermore_service 的 horizon=5)对齐,
# 一周左右正好是这些位置结论该兑现的尺度。
FORWARD_DAYS = 5

# [R287] `open` 是给「按转折买卖」那一栏用的 —— 信号收盘才定, 最早只能次日开盘
# 执行。它与 `close` 同为前复权(原始价另存 raw_close/raw_high/raw_low), 所以
# 开盘→开盘 的收益率与这里其余读数同一个口径。
_WANT_COLS = ("date", "open", "close", "change_pct", "ma20", "ma60", "atr_14",
              "signal_limit_up", "signal_limit_down", "signal_broken_limit_up",
              "consecutive_limit_ups")


def _load(repo, symbol: str, days: int) -> pl.DataFrame:
    end = date.today()
    span = int((days + _WARMUP_BARS) * _CALENDAR_RATIO) + 30
    try:
        at = repo.resolve_asset_type(symbol)
    except Exception:  # noqa: BLE001
        at = "stock"
    try:
        df = repo.get_daily_asset(at, symbol, end - timedelta(days=span), end,
                                  columns=list(_WANT_COLS))
    except Exception as e:  # noqa: BLE001
        logger.warning("review daily load failed for %s: %s", symbol, e)
        return pl.DataFrame()
    if df is None or df.is_empty() or not {"date", "close"} <= set(df.columns):
        return pl.DataFrame()
    return df.drop_nulls("close").sort("date")


def _ma120(df: pl.DataFrame) -> list[float | None]:
    """长期档是唯一没有预计算列的一档。不足 120 根的那些天留 None ——
    拿 60 根算出来的"120 日均线"是个假数, 宁可这一档缺席。"""
    s = df["close"].rolling_mean(120)
    return [None if v is None else float(v) for v in s]


def _steps(df: pl.DataFrame, threshold: float) -> list[dict]:
    """跑一次六态状态机。**整页只跑这一次** —— 逐日行与「按转折买卖」那一栏
    用的必须是同一份 steps, 各跑各的就会有一处漏改的那天开始各说各话(R286)。"""
    closes = [float(c) for c in df["close"]]
    dates = [str(d) for d in df["date"]]
    if len(closes) < 2:
        return []
    try:
        return compute(closes, dates, threshold)["steps"]
    except Exception as e:  # noqa: BLE001
        logger.debug("review trend compute failed: %s", e)
        return []


def _trend_by_date(steps: list[dict]) -> dict[str, dict]:
    """逐日六态状态 + 该状态到当天已经走了第几天。"""
    out: dict[str, dict] = {}
    run = 0
    prev_state = None
    for st in steps:
        state = st.get("state")
        run = run + 1 if state == prev_state else 1
        prev_state = state
        cn, en = STATE_LABELS.get(state, (state or "—", ""))
        out[str(st["date"])] = {
            "state": state, "state_cn": cn, "state_en": en,
            "side": "多头" if state in BULLISH else "空头",
            "day": run,
            # 转折那天单独标出来 —— 复盘时最想找的就是这些天
            "flipped": bool(st.get("flipped")),
            # [R191] 翻转触发价。逐日行里用不着, 但**最后一行**要 —— 「现在」
            # 那一条得说清"再走到哪个价就换状态", 不然复盘完还是不知道盯什么。
            "flip_down": st.get("flip_down"),
            "flip_up": st.get("flip_up"),
        }
    return out


def _bands_for_row(close, ma20, ma60, ma120, atr) -> dict:
    """当天的三档通道读数。与决策台走同一个 ``assess``, 只是输入换成当天的值。"""
    bands: dict[str, dict] = {}
    mas = {"ma20": ma20, "ma60": ma60, None: ma120}
    for key, ma_col, _window, n, cn in k.BANDS:
        got = k.assess(close=close, ma=mas.get(ma_col), atr=atr, n=n)
        if got:
            bands[key] = dict(got, band_cn=cn)
    return bands


def _forward_returns(closes: list[float], i: int, horizon: int) -> float | None:
    j = i + horizon
    if j >= len(closes) or not closes[i]:
        return None
    return closes[j] / closes[i] - 1


# ==================== [R177] 按「段」而不是按「天」聚合 ====================
#
# 这只票在某个状态下之后普遍怎么走 —— 要回答这个, 单位必须是**段**, 不是天。
#
# 原因是前瞻收益会重叠。一段持续 8 天的「上涨趋势」, 按天算就是 8 个样本, 可
# 这 8 天各自的"之后 5 日"互相共享 4 天, 根本不独立。把它们平均起来, n 看着
# 有 8, 实际信息量只有 1 段多一点 —— 这会让一个很薄的结论显得挺扎实, 恰恰是
# 这套复盘最该避免的事。
#
# 所以: **一段 = 一次**, 收益从段的第一天起算。代价是样本数变得更小更难看,
# 但那个更小的数字才是真的。

def _episodes(rows: list[dict], key_of, closes: list[float],
              offset: int, horizon: int) -> list[dict]:
    """把连续同值的行压成段。返回 [{key, start, days, fwd}]。

    key_of(row) 返回 None 的行不进段, 并且**打断**当前段 —— 中间隔了一段没有
    读数的日子, 前后不该算同一次。
    """
    out: list[dict] = []
    cur_key, cur_start, cur_days = None, 0, 0

    def _flush():
        if cur_key is None:
            return
        out.append({"key": cur_key, "start": rows[cur_start]["date"],
                    "days": cur_days,
                    "fwd": _forward_returns(closes, offset + cur_start, horizon)})

    for i, r in enumerate(rows):
        key = key_of(r)
        if key == cur_key and key is not None:
            cur_days += 1
            continue
        _flush()
        cur_key, cur_start, cur_days = key, i, 1
    _flush()
    return out


def _agg_episodes(eps: list[dict], label_of) -> list[dict]:
    """段 → 每个取值的次数 / 平均持续 / 之后 horizon 日表现。

    末尾不足 horizon 的段不计收益(还不知道结果), 但**仍计次数** —— 那一段
    确实发生过, 只是结果还没出来; 把它从次数里也抹掉会让"这只票出现过几次"
    这个最基本的问题都答错。
    """
    agg: dict = {}
    for e in eps:
        a = agg.setdefault(e["key"], {"key": e["key"], "n": 0, "days": 0,
                                      "scored": 0, "sum": 0.0, "win": 0})
        a["n"] += 1
        a["days"] += e["days"]
        if e["fwd"] is not None:
            a["scored"] += 1
            a["sum"] += e["fwd"]
            a["win"] += 1 if e["fwd"] > 0 else 0
    out = []
    for a in agg.values():
        out.append({
            "key": a["key"],
            "label": label_of(a["key"]),
            "n": a["n"],                                    # 出现过几段
            "avg_days": round(a["days"] / a["n"], 1),       # 平均持续几天
            "scored": a["scored"],                          # 其中几段已知结果
            "avg_fwd": round(a["sum"] / a["scored"], 4) if a["scored"] else None,
            "win": a["win"],
        })
    out.sort(key=lambda x: -x["n"])
    return out


def _trend_outcomes(rows: list[dict], closes: list[float], offset: int) -> list[dict]:
    """[R177] 六态各状态在这只票上出现过几段、之后怎么走。

    「趋势状态」这一列原来只统计了"涨停出现在什么状态下"; 那回答的是另一个
    问题。这里补上真正该问的: **每种状态之后普遍怎么走。**
    """
    eps = _episodes(rows, lambda r: (r.get("trend") or {}).get("state"),
                    closes, offset, FORWARD_DAYS)
    return _agg_episodes(eps, lambda k: STATE_LABELS.get(k, (k, ""))[0])


def _outcomes(rows: list[dict], closes: list[float], offset: int) -> list[dict]:
    """每种结论在这只票上出现过几**段**、之后 FORWARD_DAYS 走成什么样。

    这是复盘真正想问的那个问题 —— 「结论」列说的话, 在**这只票**身上过去
    好不好使。样本小得很(半年内同一档往往只有个位数), 所以只报次数和均值,
    不折算成胜率百分比去装得像统计结论。

    [R177] 从按天改成**按段**。原来一段持续 5 天的"强势深调"会被算成 5 个
    样本, 而这 5 天的前瞻窗口互相重叠 4 天 —— n 被撑大了, 一个很薄的结论
    看着挺扎实。改完之后数字更小, 但那个更小的数字才是真的。
    """
    title_tone: dict[str, tuple[str, str]] = {}
    for r in rows:
        v = r.get("verdict")
        if v:
            title_tone.setdefault(v["code"], (v["title"], v["tone"]))

    eps = _episodes(rows, lambda r: (r.get("verdict") or {}).get("code"),
                    closes, offset, FORWARD_DAYS)
    out = _agg_episodes(eps, lambda k: title_tone.get(k, (k, ""))[0])
    for o in out:
        o["code"] = o["key"]
        o["title"] = o["label"]
        o["tone"] = title_tone.get(o["key"], ("", "info"))[1]
    return out


# ================================================================
# [R191] 判定层 —— 把测量变成结论
#
# 这一栏原来五块内容全是**测量**: 涨停几次、磨底几天、各状态之后平均涨跌多少。
# 一个都没有回答用户打开复盘时真正带着的那个问题 ——
#
#     「这套六态在**这只票**上到底灵不灵? 我该怎么用它?」
#
# 四个状态各自的 5 日均值摆在那里, 要自己在脑子里两两相减才读得出结论, 而
# 那个结论恰恰是可以算出来的。所以补两样:
#
#   · side_edge  多头侧 vs 空头侧的分离度 → 「这只票上六态哪一半有用」
#   · now        当前这一段与它自己的历史对照 → 「现在在什么位置, 盯哪个价」
#
# **判定只用已经算好的段统计**(_trend_outcomes 的 n/scored/avg_fwd/win),
# 不新增任何一次取数。

# 一侧至少要有这么多**已兑现的段**才下结论。3 段仍然很少, 但 1~2 段是纯噪声,
# 拿它说"这只票上六态很灵"是在骗自己。
MIN_SIDE_EPISODES = 3
# 一侧算不算"有方向": FORWARD_DAYS(5 个交易日)内平均走出这么多才算。
# 3% 是个刻意保守的数 —— A 股 5 日振幅本来就大, 门槛太低会把噪声读成信号。
SIDE_EDGE = 0.03


def _side_stats(outcomes: list[dict], states: set[str]) -> dict:
    """按**已兑现段数**加权合出一侧的平均表现。

    加权而不是简单平均: 「上涨趋势 4 段 +7.9%」与「自然回升 7 段 -4.5%」直接
    取平均会让只出现过 4 次的那一档和出现过 7 次的那一档一样重。
    """
    n = sum(o["scored"] for o in outcomes if o["key"] in states)
    if not n:
        return {"episodes": 0, "avg_fwd": None, "win": 0}
    total = sum((o["avg_fwd"] or 0.0) * o["scored"]
                for o in outcomes if o["key"] in states and o["avg_fwd"] is not None)
    win = sum(o["win"] for o in outcomes if o["key"] in states)
    return {"episodes": n, "avg_fwd": round(total / n, 4), "win": win}


def _side_edge(outcomes: list[dict]) -> dict:
    """多头侧 vs 空头侧: 这只票上六态哪一半有用。

    返回 {level, label, text, bull, bear, spread}。level 取值:

      both     买卖都能判断   —— 转多之后真涨, 转空之后真跌
      defense  只能用来判断卖 —— 转空确实跌, 但转多不涨
      offense  只能用来判断买 —— 转多确实涨, 但转空也没怎么跌
      flat     买卖都判断不了 —— 在这只票上六态说明不了什么
      inverted 判断买的反而更差 —— 多头侧之后反而不如空头侧
      thin     样本不够, 不下结论

    [R285] 五个档位名各加两个字, **点明它说的是「判断」而不是「动作」**。
    用户指着「只能用来买」说: 「这类词都加多两个字, 比如只能用来判断买,
    这样表述清楚」。原来那批名字有歧义 —— 「只能用来买」读起来像在叫人买入,
    而它的意思是"这套判定在这只票上只有买那一侧灵"。**它评的是判定本身好不好使,
    不是今天该干什么**; 少这两个字, 一个统计结论就被读成了操作指令。

    **defense / offense 是这一层最值钱的两个结论**: 它们说的是"这只票的六态
    只有一半能用", 而这件事在四个并排的均值里是看不出来的 —— 得把同侧的段
    合起来才显形。

    [R206] 档位名一律改成大白话。「只有进攻灵」「两头都灵」「反着的」这类
    说法要读的人先在心里翻译一道 —— 「进攻」是买还是加仓?「灵」是准还是有用?
    换成「只能用来买」「买卖都能用」, 一眼就知道能拿它干什么。

    [R207] **价位那一层(`_verdict_edge`)用同一套六个标签**, 不再是
    「只能用来找便宜 / 只能用来躲贵」。两层问的本来就是同一个问题 ——
    「这套判定我能拿来买, 还是拿来卖, 还是两头都行」—— 两套说法只会
    让人以为它们是两种不同的东西。区别留给下面那句正文去说。

    [R208] inverted 那一档由「方向反过来了」改成「**说买的反而更差**」。
    「方向反过来了」说的是抽象的方向, 读的人还得自己想「什么的方向、
    反过来之后我该干嘛」; 换成直接陈述发生了什么, 一句话读完就明白。

    **措辞刻意用「更差」不用「反而跌」**: 这一档的判据是
    `多头侧均值 < 空头侧均值`, 而 +1% 对 +3% 同样命中 —— 写成"跌"就是
    在没跌的时候说它跌了。这一档本来就常常是小样本下的巧合(正文里明说了),
    再把话说过头, 用户真反着做就是被这个标签坑的。
    """
    bear_states = {s for s in STATE_LABELS if s not in BULLISH}
    bull = _side_stats(outcomes, set(BULLISH))
    bear = _side_stats(outcomes, bear_states)
    out = {"bull": bull, "bear": bear, "spread": None,
           "level": "thin", "label": "样本不够", "text": ""}

    if bull["episodes"] < MIN_SIDE_EPISODES or bear["episodes"] < MIN_SIDE_EPISODES:
        out["text"] = (f"多头侧 {bull['episodes']} 段、空头侧 {bear['episodes']} 段, "
                       f"任一侧不足 {MIN_SIDE_EPISODES} 段就不下结论 —— "
                       f"把窗口拉长到 250 日再看。")
        return out

    b, r = bull["avg_fwd"] or 0.0, bear["avg_fwd"] or 0.0
    out["spread"] = round(b - r, 4)
    up_ok, down_ok = b >= SIDE_EDGE, r <= -SIDE_EDGE
    tail = (f"(多头侧 {bull['episodes']} 段平均 {b:+.1%}, "
            f"空头侧 {bear['episodes']} 段平均 {r:+.1%})")

    if b < r:
        out.update(level="inverted", label="判断买的反而更差",
                   text="多头侧之后反而比空头侧更差 —— 样本这么小时多半是巧合, "
                        "但至少说明六态在这只票上没有正向信息, 别拿它做主要依据。" + tail)
    elif up_ok and down_ok:
        out.update(level="both", label="买卖都能判断",
                   text="转多之后真涨、转空之后真跌 —— 这只票可以照六态找买点, "
                        "也可以照它离场。" + tail)
    elif down_ok:
        out.update(level="defense", label="只能用来判断卖",
                   text="转空之后确实跌, 但转多之后并不涨 —— 在这只票上, "
                        "六态是「离场信号」, 不是买入依据; 买点另找。" + tail)
    elif up_ok:
        out.update(level="offense", label="只能用来判断买",
                   text="转多之后确实涨, 但转空之后也没怎么跌 —— 在这只票上, "
                        "六态是「买点线索」, 离场靠出场线与生命线, 别等它转空。" + tail)
    else:
        out.update(level="flat", label="买卖都判断不了",
                   text="多头侧与空头侧之后的走势差不多 —— 在这只票上六态说明不了"
                        "什么, 排名和买卖点都别主要靠它。" + tail)
    return out


def _now(rows: list[dict], outcomes: list[dict]) -> dict | None:
    """当前这一段, 与它自己的历史对照。

    复盘打开时最想知道的其实是「我现在在哪」, 而这件事原来要自己去表格里
    从上往下数 —— 表格第一行是今天, 但"这个状态平均能持续多久、以前出现过
    几次、之后普遍怎么走"分散在下面另外两块里, 得来回对。这里合成一条。
    """
    if not rows:
        return None
    last = rows[-1]
    t = last.get("trend") or {}
    state = t.get("state")
    if not state:
        return None
    hist = next((o for o in outcomes if o["key"] == state), None)
    day = int(t.get("day") or 1)
    avg_days = hist["avg_days"] if hist else None
    # 走到平均时长的哪儿了。avg_days 是"这只票上这个状态平均持续几天",
    # 不是预测 —— 用它只为回答"我在这一段的前段还是后段"。
    phase = None
    if avg_days:
        phase = "前段" if day < avg_days * 0.6 else "后段" if day > avg_days * 1.2 else "中段"
    return {
        "date": last["date"],
        "state": state,
        "state_cn": t.get("state_cn"),
        "side": t.get("side"),
        "day": day,
        "avg_days": avg_days,
        "phase": phase,
        "n": hist["n"] if hist else 0,
        "scored": hist["scored"] if hist else 0,
        "avg_fwd": hist["avg_fwd"] if hist else None,
        "win": hist["win"] if hist else 0,
        # 再走到哪个价就换状态 —— 复盘完总得知道盯什么
        "flip_down": t.get("flip_down"),
        "flip_up": t.get("flip_up"),
        "close": last["close"],
    }


def _seal(limit_ups: int, broken: int) -> dict | None:
    """封板率 —— 把「涨停 6 / 炸板 5」两个计数变成一句性格判断。

    冲了 11 次板只封住 6 次, 说明这只票**封不住板**: 盘中冲板时追进去有近一半
    概率当天就收在板下。这件事在两个并排的计数里得自己去除, 而它恰恰是这四张
    卡片里唯一能直接改变操作的信息。
    """
    attempts = limit_ups + broken
    if attempts < 3:      # 冲板次数太少, 这个比率没有意义
        return None
    rate = limit_ups / attempts
    if rate >= 0.75:
        text = f"冲板 {attempts} 次封住 {limit_ups} 次 —— 板封得住, 冲板时的追入相对可靠"
    elif rate >= 0.5:
        text = f"冲板 {attempts} 次封住 {limit_ups} 次 —— 一半上下, 盘中冲板不能当成已经涨停"
    else:
        text = f"冲板 {attempts} 次只封住 {limit_ups} 次 —— 封不住板, 盘中冲板追进去多半收在板下"
    return {"attempts": attempts, "sealed": limit_ups, "rate": round(rate, 3), "text": text}


def _verdict_edge(outcomes: list[dict]) -> dict:
    """[R199] 通道结论在这只票上灵不灵 —— 与 R191 给六态做的那层完全平行。

    「各档结论出现后 5 日表现」原来是十来个并排的均值, 要自己在脑子里把偏买的
    几档和偏卖的几档分别合起来再相减, 才读得出"这套结论在这只票上有没有信息"。
    那个减法可以算, 所以就该算。

    偏买侧 = tone 为 buy 的那几档; 偏卖侧 = tone 为 sell 的。**watch/hold/avoid
    不进任何一侧** —— 它们本来就是"还不到动手"或"别碰", 不构成方向主张,
    塞进去会把两侧都稀释掉。
    """
    from app.indicators.keltner import TONE_BUY, TONE_SELL

    def side(tone: str) -> dict:
        picked = [o for o in outcomes if o.get("tone") == tone and o.get("scored")]
        n = sum(o["scored"] for o in picked)
        if not n:
            return {"episodes": 0, "avg_fwd": None, "win": 0}
        tot = sum((o["avg_fwd"] or 0.0) * o["scored"] for o in picked)
        return {"episodes": n, "avg_fwd": round(tot / n, 4),
                "win": sum(o["win"] for o in picked)}

    buy, sell = side(TONE_BUY), side(TONE_SELL)
    out = {"buy": buy, "sell": sell, "spread": None,
           "level": "thin", "label": "样本不够", "text": ""}
    if buy["episodes"] < MIN_SIDE_EPISODES or sell["episodes"] < MIN_SIDE_EPISODES:
        out["text"] = (f"说便宜的 {buy['episodes']} 段、说贵的 {sell['episodes']} 段, "
                       f"任一侧不足 {MIN_SIDE_EPISODES} 段就不下结论 —— 把窗口拉长再看。")
        return out
    b, r = buy["avg_fwd"] or 0.0, sell["avg_fwd"] or 0.0
    out["spread"] = round(b - r, 4)
    tail = f"(说便宜的 {buy['episodes']} 段平均 {b:+.1%}, 说贵的 {sell['episodes']} 段平均 {r:+.1%})"
    if b >= SIDE_EDGE and r <= -SIDE_EDGE:
        out.update(level="both", label="买卖都能判断",
                   text="说便宜的之后真涨、说贵的之后真跌 —— 这只票的通道结论可以照着做。" + tail)
    elif b >= SIDE_EDGE:
        out.update(level="offense", label="只能用来判断买",
                   text="说便宜的之后确实涨, 但说贵的之后也没怎么跌 —— 拿它找买点, "
                        "别拿它当卖出理由。" + tail)
    elif r <= -SIDE_EDGE:
        out.update(level="defense", label="只能用来判断卖",
                   text="说贵的之后确实跌, 但说便宜的之后并不涨 —— 拿它躲开高位、找卖点, "
                        "买点另找依据。" + tail)
    elif b < r:
        out.update(level="inverted", label="判断买的反而更差",
                   text="说便宜的那几档之后反而比说贵的更差 —— 样本这么小时多半是巧合, "
                        "但至少说明通道结论在这只票上没有正向信息。" + tail)
    else:
        out.update(level="flat", label="买卖都判断不了",
                   text="说便宜的和说贵的之后走势差不多 —— 在这只票上, 这个价位判断说明不了什么。" + tail)
    return out


def _channel(df: pl.DataFrame, rows: list[dict]) -> dict | None:
    """[R198] 量化波动通道的几何 + 历史序列 + 事件。失败降级为 None。

    复盘弹窗的「通道结论」栏原来只有逐段卡片, 而几何层(加速度/压缩/频段)在
    决策台上只挤得下一格悬停。这里是唯一有地方把它们摊开的位置。
    """
    try:
        from app.indicators import keltner_geometry as kg
        if "atr_14" not in df.columns or df.is_empty() or not rows:
            return None
        closes = [float(c) for c in df["close"]]
        atrs = [None if a is None else float(a) for a in df["atr_14"]]
        series = kg.series(closes, atrs)
        if not series:
            return None
        runs = kg.runs(series)
        runs["compress_avg"] = kg.compress_avg(series)
        last = rows[-1]
        # 末日的三档读数走与逐日行同一条路(_bands_for_row), 保证与卡片一致
        i = len(closes) - 1
        ma120 = _ma120(df)
        cols = set(df.columns)
        def col(name):
            return list(df[name]) if name in cols else [None] * len(closes)
        bands = _bands_for_row(closes[i], col("ma20")[i], col("ma60")[i], ma120[i], atrs[i])
        geo = kg.geometry(bands, closes[i]) if bands else None
        if not geo:
            return None
        t = (last.get("trend") or {})
        ev = kg.event(state=t.get("state"), duration=t.get("day"), geo=geo, run=runs)
        note = kg.combo_note(bands)
        energy = kg.band_energy(closes, atrs)
        return {"geo": geo, "runs": runs, "energy": energy,
                "event": dict(ev, combo_note=note) if note else ev,
                # [R199] 阶段判定 —— 三个几何量单看都答不了"我该怎么办",
                # 合起来才回答"现在处在哪一段"
                "phase": kg.phase(geo, runs),
                "explain": kg.explain(geo, runs, energy)}
    except Exception as e:  # noqa: BLE001
        logger.debug("review channel geometry skipped: %s", e)
        return None


def _b(v) -> bool:
    return bool(v) if v is not None else False


def review_for_symbol(repo, symbol: str, days: int = DEFAULT_DAYS) -> dict:
    """逐日复盘: 趋势状态 / 三档通道结论 / 涨停, 按同一条时间轴对齐。

    行按**新→旧**返回 —— 打开就该先看到最近几天, 那才是要复盘的部分。
    """
    sym = (symbol or "").strip().upper()
    if not sym:
        return {"symbol": sym, "error": "symbol 不能为空"}
    days = max(10, min(int(days or DEFAULT_DAYS), MAX_DAYS))

    df = _load(repo, sym, days)
    if df.is_empty():
        return {"symbol": sym, "error": "日 K 数据不足, 无法复盘"}

    from app.services.livermore_service import get_effective_threshold
    thr, thr_src = get_effective_threshold(sym)
    steps = _steps(df, thr)
    trend_map = _trend_by_date(steps)

    cols = set(df.columns)
    ma120 = _ma120(df)
    closes = [float(c) for c in df["close"]]
    n_total = len(closes)
    offset = max(0, n_total - days)

    def col(name: str) -> list:
        return list(df[name]) if name in cols else [None] * n_total

    dates = [str(d) for d in df["date"]]
    ma20s, ma60s, atrs = col("ma20"), col("ma60"), col("atr_14")
    chg = col("change_pct")
    lu, ld, bl = col("signal_limit_up"), col("signal_limit_down"), col("signal_broken_limit_up")
    streak = col("consecutive_limit_ups")

    rows: list[dict] = []
    for i in range(offset, n_total):
        bands = _bands_for_row(closes[i], ma20s[i], ma60s[i], ma120[i], atrs[i])
        v = k.verdict(bands) if bands else None
        # [R51] 每天单独带上"之后 FORWARD_DAYS 走成什么样"。结论视图按段展示时要
        # 说清这一段结论出现后到底兑现没有 —— 只有一个全票平均数看不出是哪一次。
        fwd = _forward_returns(closes, i, FORWARD_DAYS)
        rows.append({
            "date": dates[i],
            "close": round(closes[i], 2),
            "change_pct": None if chg[i] is None else round(float(chg[i]), 4),
            "limit_up": _b(lu[i]),
            "limit_down": _b(ld[i]),
            "broken_limit_up": _b(bl[i]),
            "limit_streak": int(streak[i] or 0),
            "trend": trend_map.get(dates[i]),
            # 三档只带位置文字 —— 逐日全套读数会让这个响应大到没必要
            "bands": {key: {"pos": b["pos"], "pos_cn": b["pos_cn"]}
                      for key, b in bands.items()},
            # [R294] 三字位置码(如「上中下」), 也就是 27 格速查表的行号。
            # **在这儿算而不是让前端从 bands 拼**: 拼法归 `combo_code` 管,
            # 前端再拼一份就是同一个规则两处定义(R286 立过的规矩)。
            "combo": k_geo.combo_code(bands) if bands else None,
            "verdict": v,
            # 末尾不足 FORWARD_DAYS 的那几天为 None —— 还不知道结果, 不拿半截数据凑
            "fwd": None if fwd is None else round(fwd, 4),
        })

    limit_ups = sum(1 for r in rows if r["limit_up"])
    broken = sum(1 for r in rows if r["broken_limit_up"])
    trend_outcomes = _trend_outcomes(rows, closes, offset)
    out_rows = list(reversed(rows))
    return {
        "symbol": sym,
        "days": len(rows),
        "start": rows[0]["date"] if rows else None,
        "end": rows[-1]["date"] if rows else None,
        "threshold": thr,
        "threshold_source": thr_src,
        "forward_days": FORWARD_DAYS,
        "stats": {
            "limit_ups": limit_ups,
            "limit_downs": sum(1 for r in rows if r["limit_down"]),
            "broken_limit_ups": broken,
            # [R191] 封板率 —— 「涨停 6 / 炸板 5」两个并排的计数要自己去除才读得出
            # "这票封不住板", 而那是这四张卡片里唯一能直接改变操作的信息
            "seal": _seal(limit_ups, broken),
            "max_streak": max((r["limit_streak"] for r in rows), default=0),
            # 涨停都出现在什么趋势状态下 —— 复盘时最直接的一条: 这只票的涨停
            # 是趋势里出的, 还是下跌途中的反抽
            "limit_up_states": _limit_up_states(rows),
        },
        "outcomes": (_oc := _outcomes(rows, closes, offset)),
        # [R199] 与 R191 给六态做的那层平行: 偏买档 vs 偏卖档的分离度 ——
        # 「这套位置结论在这只票上灵不灵」
        "verdict_edge": _verdict_edge(_oc),
        # [R177] 「趋势状态」那一栏的同类统计 —— 原来那栏只有"涨停出在什么状态下",
        # 回答的是另一个问题; 这条补上"每种状态之后普遍怎么走"
        "trend_outcomes": trend_outcomes,
        # [R191] 判定层。上面那些全是测量, 这两条才回答用户带着的问题:
        # 「六态在这只票上灵不灵」与「我现在在哪、盯什么价」。
        # 两条都只用已经算好的段统计, 不新增取数。
        "side_edge": _side_edge(trend_outcomes),
        "now": _now(rows, trend_outcomes),
        # [R188 加, R229 删] "rhythm"(磨底与红绿节拍)不再进复盘载荷 ——
        # 用户: 「红绿节拍移除掉」, 整个规则层退役。
        # [R198] 量化波动通道的几何层。复盘是"看清楚"的地方 —— 决策台只给一格,
        # 这里要把速度/加速度/压缩/频段摊开。原料就是同一份 df, 不新增取数。
        "channel": _channel(df, rows),
        # [R287] 「按转折买卖」—— 每两个转折之间到底赚了多少。口径与取舍全在
        # `flip_trades` 的 docstring 里。**只切窗口内的那一段**: 统计必须与
        # 屏幕上那 120 行的转折标记一一对得上, 拿暖机段一起算就对不上了。
        "flip_trades": _trades(flip_trades.trend_days(steps[offset:]),
                               col("open")[offset:], closes[offset:],
                               lu[offset:], ld[offset:]),
        # [R288] 同一台发动机, 换一套「什么时候该有仓位」。用户: 「通道结论这个
        # 部分也能这样搞类似的统计吗」。**输入直接就是逐日行** —— 那些行里的
        # verdict 就是「通道结论」页签上一张张卡片的来源, 所以统计与卡片天然对齐。
        "verdict_trades": _trades(flip_trades.verdict_days(rows),
                                  col("open")[offset:], closes[offset:],
                                  lu[offset:], ld[offset:]),
        "rows": out_rows,
    }


def _trades(days, opens, closes, lu, ld) -> dict:
    """[R287] 「按…买卖」+ 一个样本量标记。**两个页签共用这一处。**

    `thin` 在这里挂而不在 `flip_trades` 里挂, 是因为门槛 `MIN_SIDE_EPISODES`
    归这个模块管(R191 定的 3 段)。搬一份常量过去就是同一个数两处定义 ——
    R286 刚为这件事立过规矩。
    """
    got = flip_trades.simulate(days, opens, closes, limit_up=lu, limit_down=ld)
    got["thin"] = got["bull"]["scored"] < MIN_SIDE_EPISODES
    return got


def _limit_up_states(rows: list[dict]) -> list[dict]:
    agg: dict[str, int] = {}
    for r in rows:
        if not r["limit_up"]:
            continue
        t = (r.get("trend") or {}).get("state_cn") or "—"
        agg[t] = agg.get(t, 0) + 1
    return [{"state_cn": s, "n": n} for s, n in
            sorted(agg.items(), key=lambda kv: -kv[1])]
