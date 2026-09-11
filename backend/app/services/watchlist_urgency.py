"""[fork 增强] R178 决策台「该动了」判定 —— 自选一多, 该先看谁。

用户: 「我个股很多, 必须抓住重点和买卖点机会」。

决策台原来默认按 **AI 置信度** 降序排。置信度是"AI 有多确定", 不是"这只有多急" ——
一只 AI 95% 确信「观望」的票, 会排在一只 70% 置信、今天刚跌破止损线的票上面。
15 个排序键每个都是单一维度, 没有一个回答"今天该动谁", 于是自选一多就只能靠人
在 15 列里横向扫 + 心算。

这个模块就出那一个数。**纯规则、零 AI** —— 和出场线/把握分同一条路子:
AI 可以在旁边解释, 但不许决定你先看谁(这条规矩在台账「只记不反馈」、
R175「AI 只念表」都立过, 唯独决策台的默认排序破了例, 这里补上)。

档位从急到缓, **首个命中即定档**:
  triggered 已触发   出场线破了 —— 纪律层面已经该动手, 没有比这更急的
  near      逼近     离出场线 ≤1.5%, 或离趋势翻转价 ≤2%
  flip      刚转折   今天六态刚翻转(duration==1) —— 昨天还不是这个状态
  band      到轨     短期通道贴/破上下轨 —— 常盯的高抛低吸位
  idle      无事     其余; 自选里绝大多数应该落在这一档, 那才正常

两个刻意的取舍:

  · **到轨口径直接复用 `focus_list._BAND_POS`**, 不另立阈值。CONTEXT.md 写死了
    这条: 「决策台『短通道』列写"贴上轨"的那天, 这里也必须是贴轨」。推送门和
    决策台排序如果各用一套"贴轨"的定义, 用户会看到"界面说贴轨了却没推送"。

  · **同档内按"离触发还有多远"升序**, 不按涨跌幅也不按分数。同样是 near 档,
    离线 0.3% 的显然比离线 1.4% 的更该先看。这与决策台「止盈线」列既有的排序
    语义一致(那一列早就是按距离排而不是按线价 —— 线价不同票差几十倍没有可比性)。

**没有把 AI 信号放进判定。** 它照旧显示在自己那一列, 只是不再决定顺序。
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

TRIGGERED = "triggered"
NEAR = "near"
FLIP = "flip"
BAND = "band"
IDLE = "idle"

LABELS = {
    TRIGGERED: "已触发",
    NEAR: "逼近",
    # [R286] 「刚变盘」→「刚转折」。同一件事复盘那边一直叫「转折」, 决策台
    # 的走势列现在也标它, 三处不能是两个词(AGENTS.md 规则 12)。
    # 另一半原因: 「变盘」是作者内置策略里**另一件事**的名字(均线粘合突破的
    # 变盘启动点), 那些文件只读, 所以该让路的是这边。
    FLIP: "刚转折",
    BAND: "到轨",          # [R209] 实际显示的是「到上沿」/「到下沿」, 见 _mk 的 label
    IDLE: "无事",
}
# 越小越急。前端默认排序直接用它, 免得两边各编一套顺序(与 keltner verdict 的
# rank 同一个做法)。
ORDER = {TRIGGERED: 0, NEAR: 1, FLIP: 2, BAND: 3, IDLE: 4}

# ---------------------------------------------------------------- 方向
#
# [R193] 用户: 「这一列要把话说清楚, 太简洁了, 这也不行, 会误人子弟」。**说得对,
# 而且这是这一列唯一一处真会害人的地方**:
#
#     「逼近 0.0%」可以是"再跌一点就破止损, 准备卖", 也可以是"再涨一点就转强,
#      是个买点线索" —— **两个相反的动作, 长得一模一样**(同一个词、同一个琥珀色)。
#     「已触发 0.0%」更糟: 触发了什么? 0.0% 还是个假数(触发档的 distance 被写死
#      成 0.0), 显示出来像"离触发还有 0%", 其实是"已经破了"。
#
# 光靠悬停不算说清楚 —— 一列 80 行是用来**扫**的, 扫的时候没人会悬停。所以档位
# 之外必须再出两样, 而且要出在单元格里:
#
#   side   这一条是**卖方向**还是**买方向** —— 最要命的那一项
#   what   到底是哪条线、什么价、差多远
#   action 该干什么
#
# 档位(急不急)和方向(买还是卖)是两个正交的维度, 原来只显示了前者。

SIDE_SELL = "sell"     # 卖出/减仓方向 —— 纪律或形态转弱
SIDE_BUY = "buy"       # 买入方向 —— 机会线索, 不是纪律
SIDE_INFO = "info"     # 只是提醒, 不指向任何一边

SIDE_CN = {SIDE_SELL: "卖", SIDE_BUY: "买", SIDE_INFO: ""}

# 「要动的」= 前四档。idle 不算 —— 决策台的「只看要动的」开关就按这个筛。
ACTIONABLE = frozenset({TRIGGERED, NEAR, FLIP, BAND})

# 离出场线多近算逼近。1.5% 不是拍的: 出场线本身按 ATR 定, 而 A 股日内 1.5% 是
# 一根很普通的波动 —— 到这个距离时"今天就可能破"已经是现实问题, 不是预警。
EXIT_NEAR_PCT = 0.015
# 离趋势翻转价多近算逼近。比出场线松一档: 翻转是形态确认不是纪律触发,
# 早一点进视野有意义, 但也不能太松, 否则整个自选都会挤进 near 档。
FLIP_NEAR_PCT = 0.02


def _band_positions() -> frozenset:
    """到轨的五档位置。从 focus_list 取, 不在这里复制一份常量。"""
    from app.services.focus_list import _BAND_POS
    return _BAND_POS


def _abs_or_none(v) -> float | None:
    try:
        return abs(float(v))
    except (TypeError, ValueError):
        return None


def assess(*, position: dict | None, trend: dict | None,
           exit_line: dict | None, bands: dict | None) -> dict:
    """一只票 → {level, label, order, distance, reason}。纯函数, 不读盘不调网。

    distance: 促成这个档位的那个距离(绝对值, 小数)。同档内按它升序排。
              idle 档为 None。
    reason:   一句话说明为什么是这个档 —— 界面上悬停显示, 用户得能追问"凭什么"。
    """
    held = bool((position or {}).get("held"))
    ex = exit_line or {}
    stage = ex.get("stage_cn") or "出场线"
    line = _num(ex.get("line"))
    line_txt = f"{stage} {line:.2f}" if line is not None else stage
    do = ex.get("action") or "按纪律处理"

    # ① 已触发 —— 纪律层面已经该动手
    if ex.get("triggered"):
        # [R193] 距离用**真的破了多少**, 不再写死 0.0。原来那个 0.0 显示成
        # 「已触发 0.0%」, 读起来像"离触发还有 0%"(还没破), 意思正好反了。
        depth = _abs_or_none(ex.get("distance_pct")) or 0.0
        return _mk(TRIGGERED, depth, kind="exit_broken", side=SIDE_SELL,
                   what=f"{line_txt} 已跌破" + (f" {depth * 100:.1f}%" if depth else ""),
                   action=do)

    # ② 逼近: 出场线优先于翻转价 —— 前者是纪律, 后者是形态
    ex_d = _abs_or_none(ex.get("distance_pct"))
    if ex_d is not None and ex_d <= EXIT_NEAR_PCT:
        return _mk(NEAR, ex_d, kind="exit_near", side=SIDE_SELL,
                   what=f"离{line_txt} 还有 {ex_d * 100:.1f}%",
                   action=f"跌破就{do}")

    flip_d, flip_info = _nearest_flip(trend, held)
    if flip_d is not None and flip_d <= FLIP_NEAR_PCT:
        return _mk(NEAR, flip_d, **flip_info)

    # ③ 今天刚翻转 —— duration==1 就是"昨天还不是这个状态"
    # [R286] 载荷里现在另有一个 `flipped` 说同一件事(两者恒等, 见
    # `test_R286_转折与已1天恒等`)。这里没跟着换, 是因为 `assess()` 是被直接
    # 传字典调用的判定函数, 换字段等于改它的入参约定; 恒等由那条测试钉住。
    if (trend or {}).get("duration") == 1:
        frm = (trend or {}).get("entered_from_cn")
        cur = (trend or {}).get("state_cn") or "新状态"
        bull = (trend or {}).get("side") == "多头"
        return _mk(FLIP, flip_d, kind="flipped",
                   side=SIDE_BUY if bull else SIDE_SELL,
                   what=f"今日刚转入{cur}" + (f"(自{frm})" if frm else ""),
                   action=("转多第一天 —— 买点窗口从今天起算, 但要量能配合"
                           if bull else "转空第一天 —— 持有的该考虑减了"))

    # ④ 到轨 —— 短期通道贴/破上下轨。**必须看趋势方向**, 见下。
    s_band = (bands or {}).get("s") or {}
    pos = s_band.get("pos")
    if pos in _band_positions():
        return _band_call(pos, s_band, trend, flip_d, bands or {})

    return _mk(IDLE, None, kind="none", side=SIDE_INFO,
               what="没有触到任何线", action="")


# 多头三态。只引用不做副本。
_BULLISH = ("UT", "NR", "SR")


def _verdict_tone(bands: dict) -> str | None:
    """三档组合的偏买/偏卖语气。取自作者的 `keltner.verdict`, 不另立一套。

    延后 import: `keltner` 是纯函数模块, 但这里保持与 `_band_positions` 同样的
    写法, 免得模块级互相牵连。
    """
    from app.indicators.keltner import verdict
    return (verdict(bands) or {}).get("tone")


def _band_call(pos: str, band: dict, trend: dict | None,
               flip_d: float | None, bands: dict) -> dict:
    """到轨 → 一档判定。**这一档必须看趋势方向, 也必须看另外两档。**

    ## [R212] 这里原来有个真 bug

    用户: 「有矛盾, 马上逼近上沿了又叫买, 到上沿了又叫卖, 很奇怪到底是买还是卖」。

    原来这一档是无脑的: `上沿 → 卖 / 下沿 → 买`, **一眼都不看趋势**。于是同一只
    正在上涨的票, 昨天离转强价 1.5% 报「逼近·买」, 今天站上去顺带碰到上沿,
    立刻翻成「到上沿·卖」—— 前后两天给出相反的动作, 而这两件事说的其实是
    **同一次突破**。

    错在哪: 转强价(六态关键点)与短期通道上沿常常挨得很近, 站上去这件事在六态
    那套里是"转强"、在通道那套里是"到顶"。**谁对取决于趋势在哪一侧**, 而不是
    取决于哪一档判定先命中。

    这一条 `keltner_geometry.event` 里早就写对了(破上轨在 UT 里是趋势内加速、
    在空头侧才是反弹遇阻), 只是「该动了」这一层当时没跟上。现在对齐:

        到上沿 + 多头侧 → **不是卖**。沿着上沿走是趋势票的常态, 要减看止盈线
        到上沿 + 空头侧 → 卖。反弹撞到阻力, 方向没变
        到下沿 + 多头侧 → 买侧, 但要提醒这更像甩人下车而不是破位
        到下沿 + 空头侧 → **不是买**。往下走的时候下沿会跟着往下移
        趋势读不到     → 退回中性, 不替用户猜方向

    ## [R214] 只看趋势还不够 —— 还得看另外两档

    穷举 125 种通道组合 × 7 种趋势之后, 上面那张表还剩一类会打架:

        三档全在下沿 + 六态还在多头侧 → 这里说「到下沿·买(相对便宜)」,
        而作者的 `verdict` 在同一组数据上说的是「下跌途中 —— 别抄,
        下轨会一路下移」。**同一格里上下两行, 一个叫买一个叫别买。**

    错因和 R212 是同一种, 只是漏看的东西不同: 那次漏看趋势, 这次漏看
    **另外两档通道**。「趋势没坏而掉到下沿 = 甩人下车」这句话成立的前提是
    大级别还在上面 —— 长期档也在下沿的时候, 那就不是洗盘, 是真的在往下走。

    作者的 `verdict` 早就把这件事分得很清楚了(`dip_in_uptrend` 短下沿+长上沿
    = 最好的低吸位置; `falling_all_bands` 三档全下沿 = 别抄), 所以这里**不另立
    一套判据**, 直接问它一句语气: 想给的方向与它相反就降级成中性, 把话让给
    「结论」上行。少动一次 —— 两套判据打架时不给动手的理由(AGENTS.md 第 10 条)。
    """
    pos_cn = band.get("pos_cn") or "到轨"
    up = pos in ("above", "near_upper")
    state = (trend or {}).get("state")
    cn = (trend or {}).get("state_cn") or ""
    bull = None if state is None else state in _BULLISH
    label = "到上沿" if up else "到下沿"
    what = f"短期通道{pos_cn}"
    # 三档组合明确偏卖(该止盈 / 别碰)时, 不许再说"买", 也不许再说"不必减"。
    # 中性语气(hold / watch / 无结论)不拦 —— 「只有短期到上沿」的强势票天天
    # 都是 hold, 拦了等于把最常见的一档也变成中性废话。
    # 反方向不用拦: 短期在上沿时三档组合的语气只可能是 sell/hold/watch,
    # 不存在"偏买", 所以没有对称的那半边(有也是死代码)。
    bearish_bands = _verdict_tone(bands) in ("sell", "avoid")

    if up:
        if bull is True and not bearish_bands:
            return _mk(BAND, flip_d, kind="band_up", side=SIDE_INFO, label=label,
                       what=f"{what}(趋势还在多头侧{f'·{cn}' if cn else ''})",
                       action="沿着上沿走是趋势票的常态 —— 不必因为「到高位了」就减。"
                              "真要减看止盈线, 别拿到轨当卖出理由")
        if bull is True:
            # 趋势还在多头侧, 但中期/长期也到了上沿 —— 大一级别也涨到位了。
            # 既不说"该减"(趋势没坏, 减仓理由归止盈线), 也不再说"不必减"。
            return _mk(BAND, flip_d, kind="band_up", side=SIDE_INFO, label=label,
                       what=f"{what}(趋势还在多头侧{f'·{cn}' if cn else ''}, 但大级别也到上沿了)",
                       action="不是只有短期高 —— 大一级的通道也到上沿了, "
                              "「沿上轨走是常态」这句话在这里不成立。看「通道档位」那一行")
        if bull is False:
            return _mk(BAND, flip_d, kind="band_up", side=SIDE_SELL, label=label,
                       what=f"{what}(趋势在空头侧{f'·{cn}' if cn else ''})",
                       action="逆势冲到上沿多半是反弹撞到阻力, 不是突破 —— 持有的可考虑高抛")
        return _mk(BAND, flip_d, kind="band_up", side=SIDE_INFO, label=label,
                   what=what, action="到上沿了。趋势读不到, 是突破还是撞顶得自己看日 K")

    if bull is True and not bearish_bands:
        return _mk(BAND, flip_d, kind="band_down", side=SIDE_BUY, label=label,
                   what=f"{what}(趋势还在多头侧{f'·{cn}' if cn else ''})",
                   action="趋势没坏而掉到下沿, 更像甩人下车 —— 相对便宜, 但别把甩人当破位")
    if bull is True:
        # 三档都在下沿。六态还挂多头, 但通道结构已经整体下移 —— 不给买方向。
        return _mk(BAND, flip_d, kind="band_down", side=SIDE_INFO, label=label,
                   what=f"{what}(趋势还挂多头{f'·{cn}' if cn else ''}, 但三档通道整体在下沿)",
                   action="不只是短期掉下来 —— 大级别通道也在下沿, 这不是洗盘。"
                          "六态还没转过来而已, 别拿它当低吸理由")
    if bull is False:
        # 通道结构说这个位置便宜(low_short_only / bottom_confirmed)时**也走这一句** ——
        # 那两条结论的原文本来就带着「趋势没坏的话」这个前提, 而这里前提正好不成立。
        # 所以「别抄」不是在跟它们唱反调, 是在替它们把前提兑现。真正的分歧
        # (如短下沿 + 长上沿的强势深调撞上空头六态)由「结论」那一行报打架。
        return _mk(BAND, flip_d, kind="band_down", side=SIDE_INFO, label=label,
                   what=f"{what}(趋势在空头侧{f'·{cn}' if cn else ''})",
                   action="往下走的时候下沿会跟着一路下移 —— 别拿「到下沿」当抄底理由")
    return _mk(BAND, flip_d, kind="band_down", side=SIDE_INFO, label=label,
               what=what, action="到下沿了。趋势读不到, 是超跌还是破位得自己看日 K")


def _nearest_flip(trend: dict | None, held: bool) -> tuple[float | None, dict]:
    """离翻转还有多远。持有的看转弱(要卖), 没持有的看转强(要买)。

    两边都有值时取更近的那个 —— 一只票同时逼近上下两个翻转价的情况很少,
    真出现了也是"离哪个近就先盯哪个"。

    [R193] 返回的不再是一句话, 而是**一整份说明**(kind/side/what/action) ——
    转弱和转强是相反的两件事, 只给一句「离转弱价仅 0.5%」而不标方向, 扫表时
    和「离转强价仅 0.5%」长得一模一样。
    """
    t = trend or {}
    cands: list[tuple[float, dict]] = []
    dn = _abs_or_none(t.get("flip_down_distance_pct"))
    up = _abs_or_none(t.get("flip_up_distance_pct"))
    dn_px, up_px = _num(t.get("flip_down")), _num(t.get("flip_up"))
    if dn is not None:
        cands.append((dn, {
            "kind": "flip_down_near",
            # 空仓的票转弱与你无关(你本来就没拿), 所以只对持有的算卖方向
            "side": SIDE_SELL if held else SIDE_INFO,
            "what": (f"离转弱价 {dn_px:.2f} 还有 {dn * 100:.1f}%" if dn_px is not None
                     else f"离转弱价还有 {dn * 100:.1f}%"),
            "action": ("跌破就转空 —— 持有的先想好减多少"
                       if held else "跌破就转空 —— 空仓的别在这时候接"),
        }))
    if up is not None:
        cands.append((up, {
            "kind": "flip_up_near",
            "side": SIDE_BUY,
            "what": (f"离转强价 {up_px:.2f} 还有 {up * 100:.1f}%" if up_px is not None
                     else f"离转强价还有 {up * 100:.1f}%"),
            "action": "站上才算转强 —— 别提前抢, 收盘确认再动",
        }))
    if not cands:
        return None, {}
    # 持有的票优先看转弱(卖点), 空仓的优先看转强(买点); 但只在两边都存在时才偏袒
    if len(cands) == 2:
        pick = cands[0] if held else cands[1]
        other = cands[1] if held else cands[0]
        # 另一边近得多(差一倍以上)就还是听距离的 —— 偏好不该压过事实
        return (other if other[0] * 2 < pick[0] else pick)
    return cands[0]


def _num(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _mk(level: str, distance: float | None, *, kind: str, side: str,
        what: str, action: str, label: str | None = None) -> dict:
    """一档判定。

    `reason` 是把 what + action 拼起来的整句, 留给悬停与导出; 界面上**这两半
    要分开显示** —— 「哪条线差多远」和「该干什么」是两行不同的信息。

    [R209] `label` 可以逐档覆盖。加它是为了「到轨」那一档 —— 用户:
    「到轨要说清楚到什么轨」。上沿和下沿是**两个相反的动作**(一个偏卖一个偏买),
    共用一个「到轨」等于把它们画成同一件事; 旁边虽然有买/卖色块, 但标题本身
    读起来仍然一模一样。改成「到上沿」「到下沿」, 标题自己就说清了。
    """
    reason = what + (f" —— {action}" if action else "")
    return {"level": level, "label": label or LABELS[level], "order": ORDER[level],
            "distance": None if distance is None else round(distance, 4),
            "kind": kind, "side": side, "side_cn": SIDE_CN[side],
            "what": what, "action": action, "reason": reason}


def assess_many(symbols: list[str], *, positions: dict, trends: dict,
                exit_lines: dict, keltner: dict) -> dict[str, dict]:
    """批量。任何一只出错只让那一只降级为 idle, 不连累整张表。"""
    out: dict[str, dict] = {}
    for sym in symbols:
        try:
            out[sym] = assess(position=positions.get(sym), trend=trends.get(sym),
                              exit_line=exit_lines.get(sym), bands=keltner.get(sym))
        except Exception as e:  # noqa: BLE001
            logger.warning("urgency assess failed for %s: %s", sym, e)
            out[sym] = _mk(IDLE, None, kind="none", side=SIDE_INFO,
                           what="判定失败", action="")
    return out
