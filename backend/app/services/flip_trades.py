"""[fork 增强] R287 「按转折买卖」—— 每两个转折之间到底赚了多少。

用户: 「我想统计每两个转折之间的收益, 也就是说出现转折我第二天开盘就买或者卖,
这个根据转折后的状态判断」。

复盘页原来有的是**前瞻均值**(「各状态出现后 5 日表现」): 固定看 5 天、按段平均。
它回答的是"这个状态之后一般怎么走", 回答不了用户真正带着的那个问题 ——

    「我要是真按它买卖, 这半年下来是赚是亏?」

这两件事差得很远: 前瞻均值把每一段都截成 5 天, 而真按信号做是**拿到下次转折
为止**, 一段可能 3 天也可能 40 天。用户的交易哲学是「尽可能减少买卖次数,
趋势为王」—— 5 日窗口恰恰量不到"拿住"这件事的价值。


## 口径(界面上必须原样写出来)

  信号   六态转折日 D —— 收盘之后才算得出来
  执行   **D 的下一个交易日开盘价**
  方向   转折后的状态在多头侧(上涨趋势/自然回升/次级回升) → 买入并持有
         转折后的状态在空头侧(下跌趋势/自然回撤/次级回撤) → 卖出清仓
  一段   从这次执行价, 到下次转折的执行价 —— 一进一出用的是同一个价, 段与段
         之间没有缝, 所以「跟着做」与「一直拿着」可以直接比

**执行价用次日开盘而不是转折日收盘, 是这个模块存在的全部理由。** 作者的
`livermore.backtest_thresholds` 里已经有一份"跟随收益", 那份是**转折日收盘进出**
的 —— 而转折这件事要等收盘价定下来才算得出来, 拿同一根收盘价成交, 等于假设你
在收盘那一刻就知道了收盘之后才知道的事。两份数字会有出入, 差的就是隔夜跳空,
而跳空恰恰在转折日最大(截图那只票好几个转折日是跌停)。作者那份不动, 这份另算。

**空头段不做空。** A 股散户也做不了。那一段的涨跌是"你没参与的" —— 但必须显示,
因为这套打法值不值, 一半的答案在"躲开了多少"里。所以空头段照样出一个收益率,
只是它不进「跟着做」的复利, 界面上也不能写成"赚"。

**未完成的段不进胜负统计**, 与 R177「按段计、只数已兑现」同一条纪律。最后一次
转折如果次日还没到(窗口末尾), 那就是"信号有了、手还没动", 不许拿收盘价冒充成交
价补一笔进去。

纯函数: 不读盘、不调网、不碰 repo。输入是已经对齐好的几条等长序列。
"""
from __future__ import annotations

from app.indicators.livermore import BULLISH, STATE_LABELS


def _f(v) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f > 0 else None


def _blocked(bull: bool, i: int, limit_up, limit_down) -> bool:
    """这一笔的执行日会不会**根本成交不了**。

    **方向必须对上**: 买入日撞涨停才买不进, 卖出日撞跌停才卖不掉。反过来是好事
    (买入日跌停买得更便宜, 卖出日涨停卖得更贵), 标成风险会把利好读成利空。

    这里只用「当天涨停/跌停」这个已有的标志, 不去判一字板 —— 判一字要 high/low,
    而复盘那份 df 里没有。所以措辞只能到"未必成交得到这个价"为止, 不能更硬。
    """
    flags = limit_up if bull else limit_down
    if not flags or i >= len(flags):
        return False
    return bool(flags[i])


def _leg(flip_i: int, enter_i: int, steps, opens, dates, limit_up, limit_down) -> dict:
    state = steps[enter_i]["state"]
    cn, _en = STATE_LABELS.get(state, (state or "—", ""))
    bull = state in BULLISH
    return {
        "flip_date": dates[flip_i],
        "enter_date": dates[enter_i],
        "enter_price": opens[enter_i],
        "state": state,
        "state_cn": cn,
        "side": "多头" if bull else "空头",
        "blocked": _blocked(bull, enter_i, limit_up, limit_down),
    }


def simulate(steps: list[dict], opens: list, closes: list, *,
             limit_up: list | None = None, limit_down: list | None = None) -> dict:
    """按转折买卖跑一遍。口径见模块 docstring。

    steps  ``livermore.compute()`` 的 steps 切片(要带 state / flipped / date)
    opens  与 steps 等长的开盘价(前复权, 与 closes 同一口径)
    closes 与 steps 等长的收盘价 —— 只在最后一段还没走完时用得着
    limit_up / limit_down
           与 steps 等长的当日涨停/跌停标志。给了就标出"这一笔的执行日撞上了
           涨跌停, 未必成交得到这个价"; 不给就一律当作不知道(False), 不瞎猜

    返回::

        legs     每一段 {flip_date, enter_date, enter_price, exit_date,
                          exit_price, state, state_cn, side, bars, ret,
                          open_ended, blocked, act}
                 act 是这一段**起头时手上该干什么**: 买入 / 持有 / 卖出 / 空仓。
                 「持有」与「空仓」就是那些转折了但不用动手的段。
        trades   真正下过单的次数 = 建仓次数。**不等于多头段数** ——
                 连着的多头段是一次持仓
        bull/bear{n, scored, win, avg, best, worst}
        follow   跟着做的累计收益(只叠已完成的多头段)
        hold     同一段区间一直拿着的收益 —— 同起点同终点, 可以直接比
        excess   follow − hold
        pending  最后一个还没轮到执行的转折日; 没有就是 None
        skipped  因为缺开盘价而没法执行的转折日
        blocked  有几笔的执行日撞上了涨跌停 —— 这几笔的价不能当真
        reason   一笔都做不成时的原因: "no_flip"(这段里六态没转过) /
                 "no_open"(缺开盘价, 算不了)。做成了就是 None。
                 **空栏必须自己解释** —— 读的人分不清"确实没有"和"算不出来"。
    """
    n = len(steps)
    dates = [str(s.get("date")) for s in steps]
    opens = [_f(v) for v in opens]
    closes = [_f(v) for v in closes]

    # ① 找出所有**能执行**的转折: 转折在 i, 手在 i+1 动。
    entries: list[tuple[int, int]] = []   # (转折日下标, 执行日下标)
    pending: str | None = None
    skipped: list[str] = []
    for i, s in enumerate(steps):
        if not s.get("flipped") or s.get("state") is None:
            continue
        # **开机那天不是转折。** `compute()` 给第一天的 `flipped` 是 True(它的
        # `prev` 是 None), 但昨天根本没有状态, 谈不上"从什么转成什么"。照着它
        # 买一笔, 等于把"我们开始观察了"当成买入信号 —— 而它落在窗口最左边,
        # 于是这个假信号会一路吃掉整段区间, 把「跟着做」直接顶高。
        if s.get("prev") is None:
            continue
        j = i + 1
        if j >= n:
            pending = dates[i]          # 信号有了, 次日还没到
            continue
        if opens[j] is None:
            skipped.append(dates[i])    # 停牌之类 —— 说出来, 不静默跳过
            continue
        entries.append((i, j))

    # 一笔都没做成时的原因。`entries` 非空却仍然落到这里, 说明是价格那侧缺了
    # (末日收盘价也没有), 归 no_open —— 不能说成"六态没转过", 那是另一回事。
    empty = {"legs": [], "trades": 0,
             "reason": "no_open" if (skipped or pending or entries) else "no_flip", "follow": None, "hold": None, "excess": None,
             "from_date": None, "to_date": None, "pending": pending,
             "skipped": skipped, "blocked": 0,
             "bull": _side_stats([]), "bear": _side_stats([])}
    if not entries:
        # pending 那一支也归到 no_open: 信号有了但一笔都没做成, 原因是"还没到
        # 能执行的那天", 与缺价同属"数据侧还差点", 而不是"六态没转过"。
        return empty

    # ② 一段接一段。**下一段的买入价就是这一段的卖出价** —— 一进一出同一个价,
    #    段与段之间没有缝, 所以「跟着做」与「一直拿着」量的是同一段区间。
    legs: list[dict] = []
    for k, (flip_i, enter_i) in enumerate(entries):
        leg = _leg(flip_i, enter_i, steps, opens, dates, limit_up, limit_down)
        if k + 1 < len(entries):
            exit_i = entries[k + 1][1]
            leg["exit_date"] = dates[exit_i]
            leg["exit_price"] = opens[exit_i]
            leg["open_ended"] = False
        else:
            # 还没走完的那一段: 用最后一天的收盘价看看现在浮在哪儿, 并标出来。
            exit_i = n - 1
            last = closes[exit_i]
            if last is None:
                continue
            leg["exit_date"] = dates[exit_i]
            leg["exit_price"] = last
            leg["open_ended"] = True
        leg["bars"] = exit_i - enter_i
        leg["ret"] = round(leg["exit_price"] / leg["enter_price"] - 1, 4)
        legs.append(leg)

    if not legs:
        return empty

    # ③ 段 ≠ 动作。**连着两个多头段是一次持仓, 不是两次买卖** —— 自然回升转
    #    上涨趋势也是一次转折, 但两边都在多头侧, 手上根本不用动。用户的哲学是
    #    「尽可能减少买卖次数」, 把段数当买卖次数摆给他就是虚报手续费。
    for k, l in enumerate(legs):
        prev_side = legs[k - 1]["side"] if k else None
        if l["side"] == "多头":
            l["act"] = "持有" if prev_side == "多头" else "买入"
        else:
            l["act"] = "空仓" if prev_side == "空头" else "卖出"

    done_bull = [l for l in legs if l["side"] == "多头" and not l["open_ended"]]
    eq = 1.0
    for l in done_bull:
        eq *= 1 + l["ret"]

    first, last = legs[0], legs[-1]
    hold = last["exit_price"] / first["enter_price"] - 1
    follow = eq - 1
    return {
        "legs": legs,
        # 真正下过单的次数 = 建仓次数(含最后那次还没卖的)。已完成的多头**段**数
        # 是另一个数, 在 bull.scored 里。
        "trades": sum(1 for l in legs if l["act"] == "买入"),
        "follow": round(follow, 4),
        "hold": round(hold, 4),
        "excess": round(follow - hold, 4),
        "from_date": first["enter_date"],
        "to_date": last["exit_date"],
        "pending": pending,
        "skipped": skipped,
        "blocked": sum(1 for l in legs if l["blocked"]),
        "reason": None,
        "bull": _side_stats([l for l in legs if l["side"] == "多头"]),
        "bear": _side_stats([l for l in legs if l["side"] == "空头"]),
    }


def _side_stats(legs: list[dict]) -> dict:
    """一侧的汇总。**只数已完成的段** —— 见模块 docstring 那条纪律。"""
    done = [l for l in legs if not l["open_ended"]]
    rets = [l["ret"] for l in done]
    return {
        "n": len(legs),
        "scored": len(done),
        "win": sum(1 for r in rets if r > 0),
        "avg": round(sum(rets) / len(rets), 4) if rets else None,
        "best": round(max(rets), 4) if rets else None,
        "worst": round(min(rets), 4) if rets else None,
    }
