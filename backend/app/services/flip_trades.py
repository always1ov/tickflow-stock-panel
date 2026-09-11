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

[R304] **成交不了的不许记成交, 成交得到的不许过滤。** 这是两件事, 分界很干净:
一字板(收盘在板上且开盘不低于收盘)是**真的挂不进去**, 所以顺延到下一个能成交
的日子, 一直封到下一个信号就作废这张单; 而次日跳空低开、高开都是**成交得到**
的, 一律如实成交如实记账 —— 在执行层加一个"跌太多就不买"的过滤, 测出来的就
不是这套判定了, 是"这套判定 + 一个我编的过滤器", 而那个过滤器的参数没有依据。

[R303] **但那条纪律管的是胜负统计, 不是那两个对照数。** `follow` 与 `hold`
必须量同一段区间 —— 同一个起点(第一次可执行的转折)、同一个终点(最后一天)。
最后那个还拿着的多头段照旧按收盘 mark-to-market 算进 `follow`, 否则一只
"从头到尾只买过一次、拿到今天"的票会算出「跟着做 0% / 一直拿着 +67%」,
而那两件事根本是同一件事。胜负统计(`bull.scored / win / avg`)照旧只数已兑现。

纯函数: 不读盘、不调网、不碰 repo。输入是已经对齐好的几条等长序列。
"""
from __future__ import annotations

from app.indicators.livermore import BULLISH, STATE_LABELS

# 仓位只有两种。名字沿用六态那边的说法, 免得同一件事两个词(AGENTS.md 规则 12)。
BULL = "多头"      # 满仓持有
BEAR = "空头"      # 空仓 —— **不是做空**, A 股散户也做不了


# ================================================================
# 适配器 —— 把一套判定翻成「逐日仓位」
# ================================================================
#
# 两个页签用的是同一台发动机(`simulate`), 差别全在这里: 什么算一次变化、
# 变化之后手上该是满仓还是空仓。分开写而不是塞成一个 if, 是因为两套规则的
# **形状不同** —— 六态每天非多即空, 通道档位有三种"不是动作"的状态。


def trend_days(steps: list[dict]) -> list[dict]:
    """[R287] 六态 → 逐日仓位。多头三态(上涨趋势/自然回升/次级回升)满仓, 其余空仓。

    `steps` 直接吃 ``livermore.compute()`` 的输出, 原样带走 date/prev/flipped。
    """
    out = []
    for st in steps:
        state = st.get("state")
        cn, _en = STATE_LABELS.get(state, (state or "—", ""))
        out.append({**st, "state_cn": cn,
                    "side": BULL if state in BULLISH else BEAR})
    return out


# 作者给每一档写的 `action` 就是这张表的依据 —— **不另立一套判断**:
#
#   强势深调「最好的低吸位置」/ 调整到位「低吸分量更足」/ 短线回调「趋势没坏
#   就是低吸候选」                                          → buy   建仓
#   该止盈了「可落袋一部分」/ 超跌反弹「反弹卖点, 不是买点」/
#   大顶区域「动仓位基调, 不只减这一只」                     → sell  清仓
#   下跌途中「别抄, 下轨会一路下移」                          → avoid 清仓
#
# 剩下三种**都不是动作**, 所以一律**维持上一天的仓位**:
#   短线冲高「拿着, 别在这加仓」        hold
#   候选池「大级别到位, 等短期入场点」/ 高位回落「别追, 等回到下沿再看」 watch
#   三档都在通道中部 → `verdict()` 返回 None, 压根没有结论
#
# 把 hold/watch/无结论 当成卖出是这一层最容易犯的错: 那会让仓位天天翻,
# 而作者的原话是「拿着」「等」。
_TONE_SIDE = {"buy": BULL, "sell": BEAR, "avoid": BEAR}


def verdict_days(rows: list[dict]) -> list[dict]:
    """[R288] 通道档位 → 逐日仓位。

    `rows` 是复盘逐日行(要带 `date` 与 `verdict`)。一次「变化」= **结论换了一档**
    (含从有结论变成没结论), 与「通道档位」页签上那一张张卡片一一对应。

    起手是**空仓** —— 窗口开头还没等到任何买入信号, 不许假设手上已经有票。
    """
    out: list[dict] = []
    side = BEAR
    prev_code: str | None = None
    for r in rows:
        v = r.get("verdict") or {}
        code = v.get("code")
        side = _TONE_SIDE.get(v.get("tone"), side)   # 认不出的一律维持, 不瞎动
        out.append({
            "date": r.get("date"),
            "state": code,
            "state_cn": v.get("title") or "没档位",
            "side": side,
            "prev": prev_code,
            # 第一天的 prev 是 None, 与 `compute()` 开机那天同一个形状 ——
            # `simulate` 会跳过它(那不是一次变化, 是"我们开始看了")
            "flipped": bool(out) and code != prev_code,
        })
        prev_code = code
    return out


def _f(v) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f > 0 else None


def _sealed(bull: bool, i: int, opens, closes, limit_up, limit_down) -> bool:
    """这一天的**开盘价**根本成交不了 —— 也就是**一字板**。

    用户: 「第一天转折的时候涨停收盘的时候也买不进去」「连续跌停买不进去」。

    ## 判据: 收盘在板上 **且** 开盘不低于收盘

    涨停价是当天的上限, **开盘不可能高于它**。所以「收盘涨停」+「开盘 ≥ 收盘」
    ⇒ 开盘就在涨停价上 ⇒ 开盘那一刻封着板, 你挂不进去。跌停同理反过来。

    这比 R287 那版(只看「当天涨跌停」标志)**既更严也更准**:
      · 更准 —— 盘中打开过、尾盘才封回去的那种, 开盘价是能成交的, 旧判据
        把它也标成风险, 属于**误报**(把买得到的说成买不到);
      · 更严 —— 认出来的这些是真的成交不了, 所以不再只贴一句"未必成交得到
        这个价", 而是**真的顺延**(见 `simulate` 的第①步)。

    **不需要 high/low**: R287 当时说判一字要 high/low 所以做不了 —— 那是错的,
    `open` 与 `close` 加上板的标志已经够了。复盘那份 df 两样都取了。

    **方向必须对上**: 买入日撞涨停才买不进, 卖出日撞跌停才卖不掉。反过来是好事
    (买入日跌停买得更便宜, 卖出日涨停卖得更贵), 标成风险会把利好读成利空。
    """
    flags = limit_up if bull else limit_down
    if not flags or i >= len(flags) or not flags[i]:
        return False
    o, c = opens[i], closes[i]
    if o is None or c is None:
        return False
    return o >= c if bull else o <= c


def _leg(flip_i: int, enter_i: int, steps, opens, dates) -> dict:
    # **信号取自转折日, 不是执行日。** 执行日的状态要等它自己收盘才知道 ——
    # 下单那一刻(次日开盘)你手上只有转折日那个信号。转折连着两天出现时, 取错
    # 会把方向标反, 并且把中间那个真实的来回整段吞掉。见
    # `test_R288_连着两天转折时用的是下单那一刻知道的信号`。
    #
    # 价格那一侧仍然取执行日(开盘价、涨跌停标志都是那天的) —— 分得清清楚楚:
    # **信号是昨天的, 成交是今天的**。
    st = steps[flip_i]
    bull = st["side"] == BULL
    return {
        "flip_date": dates[flip_i],
        "enter_date": dates[enter_i],
        "enter_price": opens[enter_i],
        "state": st.get("state"),
        "state_cn": st.get("state_cn") or st.get("state") or "—",
        "side": st["side"],
        # [R304] 一字板顺延之后, 成交日与信号日之间可能隔了几天 —— 隔了几天
        # 就是"这几天你想动手却动不了"。0 表示次日就成交了(正常情形)。
        "delayed": enter_i - flip_i - 1,
    }


def simulate(steps: list[dict], opens: list, closes: list, *,
             limit_up: list | None = None, limit_down: list | None = None) -> dict:
    """按转折买卖跑一遍。口径见模块 docstring。

    steps  逐日 {date, side, flipped, prev, state, state_cn} —— 由下面两个适配器
           之一产出。**`side` 是适配器算好的仓位, 不在这里判** ——
           六态每天非多即空, 而通道档位有「拿着」「等着」「没结论」三种
           **不是动作**的状态, 两套规则没法写成一个 if。
    opens  与 steps 等长的开盘价(前复权, 与 closes 同一口径)
    closes 与 steps 等长的收盘价 —— 只在最后一段还没走完时用得着
    limit_up / limit_down
           与 steps 等长的当日涨停/跌停标志。配合 opens/closes 判**一字板**
           (见 `_sealed`): 撞上了就把成交顺延到下一个能成交的日子, 一直封到
           下一个信号就把这张单子作废。不给就一律当作能成交, 不瞎猜

    返回::

        legs     每一段 {flip_date, enter_date, enter_price, exit_date,
                          exit_price, state, state_cn, side, bars, ret,
                          open_ended, delayed, act}
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
        delayed  有几笔因为一字板顺延过 —— 成交日比信号日的次日晚
        voided   一直封到下一个信号、单子作废的那几个信号日
        reason   一笔都做不成时的原因: "no_flip"(这段里六态没转过) /
                 "no_open"(缺开盘价, 算不了)。做成了就是 None。
                 **空栏必须自己解释** —— 读的人分不清"确实没有"和"算不出来"。
    """
    n = len(steps)
    dates = [str(s.get("date")) for s in steps]
    opens = [_f(v) for v in opens]
    closes = [_f(v) for v in closes]

    # ① 找出所有**能执行**的转折: 转折在 i, 手在 i+1 动 —— 除非那天是一字板。
    #
    # [R304] **撞上一字板就顺延到下一个能成交的日子。** 用户: 「第一天转折的
    # 时候涨停收盘的时候也买不进去」「连续跌停买不进去」。R287 那版只贴一句
    # "未必成交得到这个价", 成交照记 —— 于是一只一字涨停三天的票, 模拟按
    # 第一天的开盘价买进, 吃到了一段**现实里根本拿不到**的涨幅。
    #
    # 顺延有个硬边界: **不许越过下一个转折信号**。等到那时候状态已经变了,
    # 这张单子在现实里也该撤了 —— 越过去就等于"拿着一个过期的理由下单"。
    # 撤掉的那些单独计数(`voided`), 不许静默吞掉。
    flips = [i for i, s in enumerate(steps)
             if s.get("flipped") and s.get("state") is not None and s.get("prev") is not None]
    nxt = {i: flips[k + 1] for k, i in enumerate(flips[:-1])}

    entries: list[tuple[int, int]] = []   # (转折日下标, 执行日下标)
    pending: str | None = None
    skipped: list[str] = []
    voided: list[str] = []
    delayed = 0
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
        bull = s.get("side") == BULL
        limit = nxt.get(i, n)           # 下一个转折日; 没有就到窗口末
        while j < n and j <= limit and _sealed(bull, j, opens, closes, limit_up, limit_down):
            j += 1
        if j >= n or j > limit:
            voided.append(dates[i])     # 一直封到下一个信号 —— 这张单子作废
            continue
        if opens[j] is None:
            skipped.append(dates[i])    # 停牌之类 —— 说出来, 不静默跳过
            continue
        delayed += j - i - 1
        entries.append((i, j))

    # 一笔都没做成时的原因。`entries` 非空却仍然落到这里, 说明是价格那侧缺了
    # (末日收盘价也没有), 归 no_open —— 不能说成"六态没转过", 那是另一回事。
    empty = {"legs": [], "trades": 0,
             "reason": "no_open" if (skipped or pending or entries or voided) else "no_flip", "follow": None, "hold": None, "excess": None,
             "from_date": None, "to_date": None, "pending": pending,
             "skipped": skipped, "delayed": 0, "voided": voided, "open_bull": False,
             "bull": _side_stats([]), "bear": _side_stats([])}
    if not entries:
        # pending 那一支也归到 no_open: 信号有了但一笔都没做成, 原因是"还没到
        # 能执行的那天", 与缺价同属"数据侧还差点", 而不是"六态没转过"。
        return empty

    # ② 一段接一段。**下一段的买入价就是这一段的卖出价** —— 一进一出同一个价,
    #    段与段之间没有缝, 所以「跟着做」与「一直拿着」量的是同一段区间。
    legs: list[dict] = []
    for k, (flip_i, enter_i) in enumerate(entries):
        leg = _leg(flip_i, enter_i, steps, opens, dates)
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
        if l["side"] == BULL:
            l["act"] = "持有" if prev_side == BULL else "买入"
        else:
            l["act"] = "空仓" if prev_side == BEAR else "卖出"

    # [R303] **两个数必须量同一段。** 用户: 「跟着买和一直拿的统计起点必须要一样」。
    #
    # 起点本来就一样(都是 `legs[0].enter_price`; 空仓段对「跟着做」乘 1)。
    # **不一样的是终点**: `hold` 一路算到最后一天收盘, 而 `follow` 原来只叠
    # **已走完**的多头段 —— 把最后那个还拿着的段整个丢掉了。
    #
    # 后果是系统性的, 而且专挑最常见的情形下手: 只要这只票**现在还持仓**,
    # 这一段的浮盈就被从「跟着做」里扣掉、却留在「一直拿着」里。极端情形
    # (从头到尾只买过一次、拿到今天)会算出「跟着做 0% / 一直拿着 +67%」——
    # 而那两件事**根本是同一件事**。
    #
    # 所以最后那个未了结的多头段照旧按最后一天收盘 mark-to-market 乘进去,
    # 与 `hold` 的终点严丝合缝。**「只数已兑现」那条纪律没有松**: 它守的是
    # 分段胜负统计(`bull.scored / win / avg`), 那里照旧排除未完成的段 ——
    # 一段没走完就谈不上"这次赢了还是输了", 但它的浮盈浮亏是实实在在的。
    bull_legs = [l for l in legs if l["side"] == BULL]
    eq = 1.0
    for l in bull_legs:
        # **用原始比值复利, 不用 `l["ret"]`** —— 那个数是 `round(…, 4)` 过的,
        # 一段一段乘起来会把四舍五入的误差累起来。R294 那条「多切几刀不改变
        # 成绩」在 R303 把最后一段并进来之后当场红了(0.1582 → 0.1581),
        # 红的正是这个: 切得越碎, 被乘进去的舍入误差越多。
        eq *= l["exit_price"] / l["enter_price"]

    first, last = legs[0], legs[-1]
    hold = last["exit_price"] / first["enter_price"] - 1
    follow = eq - 1
    # 未了结的那一段是**这只票的**情况, 得说出来: 两个数都含它的浮盈浮亏。
    open_bull = bool(bull_legs and bull_legs[-1]["open_ended"])
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
        # [R304] 被一字板顺延过的笔数, 与"一直封到下一个信号、单子作废"的那几次
        "delayed": sum(1 for l in legs if l["delayed"] > 0),
        "voided": voided,
        # [R303] 最后一段还拿着 —— 「跟着做」与「一直拿着」都含它的浮盈浮亏
        "open_bull": open_bull,
        "reason": None,
        "bull": _side_stats([l for l in legs if l["side"] == BULL]),
        "bear": _side_stats([l for l in legs if l["side"] == BEAR]),
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
