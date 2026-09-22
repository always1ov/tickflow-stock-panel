"""[fork 增强] R205 「怎么办」—— 个股分析页的收敛层。

## 这一层为什么必须存在

决策台上现在有**五套彼此平行的判定**, 各说各的:

    ① 该动了   (watchlist_urgency)  紧迫度 —— 今天先看谁
    ② 六态趋势 (livermore)          方向   —— 往上还是往下
    ③ 通道档位 (keltner.verdict)    位置   —— 贵还是便宜
    ④ 通道阶段 (keltner_geometry)   成熟度 —— 走到哪一段了
    ⑤ AI 信号  (stock_signal)       买卖   —— 模型怎么看   [R435 停用, 已撤出]

每一套单独看都对, 摆在一起就是**用户每天要在脑子里做一次五路合成**。
这才是「数据堆砌」的真正来源 —— 不是数据太多, 是**没有收敛层**。

而且更要命的一件事: **系统从来不说这五套什么时候打架。**
「六态在多头侧 + AI 说卖出」「通道说该止盈了 + 阶段说刚开始分开」——
这些组合每天都在发生, 而界面把它们并排摆着, 谁都不提一句。
**打架恰恰是最该停手的时候**, 现在它反而是最容易被忽略的时候。

## 优先级: 第一条命中即止

纪律 > 时点 > 分歧 > 形态。顺序不是随手排的:

  1. **出场线已破 / 生命线破位** —— 这是纪律, 不参与讨论(R48 起的既定优先级:
     组合回撤 > 生命线 > 止盈线 > 六态转弱)。
  2. **今天已触发** —— 时点已经到了, 别的先放一边。
  3. **判定打架** —— 排在"逼近"之前是有意的: 几套判定分歧时, "还差 1.2% 到买点"
     这个信息会诱人下手, 而那正是不该下手的时刻。**先说分歧, 再说距离。**
  4. **逼近** —— 快到了, 盯着。
  5. **形态给的提示**(走过头了 / 后劲不足 / 主升浪 / 突破站稳)—— 不急, 但值得知道。
  6. 其余 = 没事。

## 边界

纯函数, 不读盘不调网, 输入全是别的层**已经算好**的结果 —— 一次新的取数都不加。
**不产生任何新判定**: 每一句话都能追到某一层的原话上, 这一层只负责挑出该说的
那一句、以及指出它们互相不一致。
"""
from __future__ import annotations

# 档位。order 越小越该先看 —— 与 watchlist_urgency.ORDER 同一个方向。
EXIT = "exit"            # 纪律已触发, 不讨论
ACT = "act"              # 今天就得动
CONFLICT = "conflict"    # 几套判定打架 —— 停手
WATCH = "watch"          # 盯着某个价
SHAPE = "shape"          # 形态提示, 不急
IDLE = "idle"            # 没事

ORDER = {EXIT: 0, ACT: 1, CONFLICT: 2, WATCH: 3, SHAPE: 4, IDLE: 5}
LABELS = {
    EXIT: "按纪律走", ACT: "今天就得动", CONFLICT: "先别动",
    WATCH: "盯着", SHAPE: "留意", IDLE: "没事",
}
TONE = {
    EXIT: "danger", ACT: "danger", CONFLICT: "warn",
    WATCH: "warn", SHAPE: "info", IDLE: "muted",
}

# 多头三态 / 空头三态。只引用不做副本。
from app.indicators.livermore import BULLISH  # noqa: E402

# [R435] 原来这里有 `_AI_BULL` / `_AI_BEAR` 两组(判打架时 AI 哪几个词算多、算空)。
# AI 信号整套停用, 与 AI 有关的三条打架规则(① 趋势 vs AI、③ 阶段 vs AI 两条)
# 一起撤了; 剩下的都是规则层自己的分歧。


def _mk(level: str, headline: str, why: str, *, price: float | None = None,
        note: str = "") -> dict:
    """[R299] `why` 与 `note` 分开: **`why` 讲这只票, `note` 讲这套系统的道理。**

    用户: 「内容要言简意赅精辟」「没帮助的东西就不要显示了」。

    原来两者串成一个字符串, 于是「出场纪律优先于形态与模型」「各说各的时候,
    等它们对齐比猜谁对划算」这类话跟着每一行印出去 —— **它们不随票变**,
    一屏扫下来是同一句道理重复几十遍, 挤掉的正是那行真正的读数。

    拆开之后 `note` 只进悬停(要核对时才看), 界面正文只留 `why`。
    """
    return {"level": level, "label": LABELS[level], "order": ORDER[level],
            "tone": TONE[level], "headline": headline, "why": why,
            "note": note, "price": price}


def _conflicts(*, held: bool, trend: dict | None, verdict: dict | None,
               phase: dict | None) -> list[str]:
    """找出互相矛盾的判定对。返回人话描述, 空列表 = 没打架。

    **只认真正相反的**: 一边明确说多、另一边明确说空。「观望」「无结论」
    这类不表态的一律不算 —— 把它们算进来会让一半的票都显示"打架", 那这一档
    就没有信息量了, 用户三天后就学会无视它。
    """
    out: list[str] = []
    state = (trend or {}).get("state")
    bull_trend = state in BULLISH if state else None

    # [R435] ① 趋势 vs AI —— 随 AI 信号撤了
    # ② 趋势 vs 通道位置
    #
    # [R214] **这条规则从写下那天起一次都没触发过。** 原来读的是
    # `verdict["side"]` —— 那个字段的取值域是 `("high", "low")`(贴的是上轨
    # 还是下轨), 代码却拿 `"sell"` / `"buy"` 去比。偏买偏卖在 verdict 里叫
    # `tone`, 不叫 `side`。**两套词汇对不上, 条件恒假。**
    #
    # 穷举 125 种通道组合 × 7 种趋势, 这条规则命中 0 次 —— 也就是说
    # 「趋势往上但位置已经该止盈」「趋势往下但位置看着便宜」这两类最典型的
    # 打架, 系统一次都没报过。用户说的「你没处理好组合表的所有情况」,
    # 根子就在这里。
    #
    # 病因与 R210 那个「候选路 C 是死代码」一模一样: 判定写对了、接线接错了,
    # 而测试恰好只测了判定。所以这次补的是**穷举式**的回归测试
    # (test_playbook_combo_matrix.py), 让"某条规则从来不触发"这件事本身失败。
    #
    # `avoid`(下跌途中·别碰)与 `sell` 同属偏卖侧 —— 原来的写法连这个都漏了。
    # `hold`(拿着别加)与 `watch`(还不到时候)是不表态, 照旧不算打架:
    # 「只有短期到上沿」的强势票天天都是这一档, 报打架等于把这一列变成噪音。
    #
    # `sell` 与 `avoid` 同属偏卖侧, 但**话不一样**: 「该止盈了」是贵,
    # 「下跌途中」不是贵而是通道整体在往下走。共用一句「贵了」会说出
    # 「位置上已经是『下跌途中』—— 贵了」这种不通的话。
    tone = (verdict or {}).get("tone")
    if bull_trend is True and tone == "sell":
        out.append(f"趋势往上,但位置上已经是「{verdict.get('title')}」—— 贵了")
    elif bull_trend is True and tone == "avoid":
        out.append(f"六态还挂着多头,但三档通道已经是「{verdict.get('title')}」"
                   "—— 通道结构比六态先转向了")
    elif bull_trend is False and tone == "buy":
        out.append(f"趋势往下,但位置上看是「{verdict.get('title')}」—— 便宜不等于该买")

    # [R435] ③ 阶段 vs AI —— 随 AI 信号撤了
    ph = (phase or {}).get("code")

    # ④ 持有 + 阶段说该想退出 + 趋势还没坏 —— 这一条只对持仓有意义
    if held and ph == "overextended" and bull_trend is True:
        out.append("趋势没坏但已经走得过头 —— 加仓与减仓的理由同时成立")
    return out


def playbook(*, position: dict | None, trend: dict | None, exit_line: dict | None,
             urgency: dict | None, verdict: dict | None, phase: dict | None,
             event: dict | None) -> dict:
    """五套判定 → 一句「怎么办」。纯函数。

    返回 {level, label, order, tone, headline, why, price, conflicts}。
    `conflicts` 始终返回(即使没命中 CONFLICT 档) —— 界面可以在别的档位上
    也把分歧作为一行小字带出来。
    """
    held = bool((position or {}).get("held"))
    ex = exit_line or {}
    urg = urgency or {}
    conflicts = _conflicts(held=held, trend=trend, verdict=verdict,
                           phase=phase)

    # ① 纪律: 出场线已破。**不参与讨论** —— 出场优先级是既定的
    if ex.get("triggered"):
        line = ex.get("line")
        fatal = ex.get("stage") == "fatal"
        return {**_mk(EXIT,
                      "生命线破位,清仓" if fatal else f"{ex.get('stage_cn') or '出场线'}已破",
                      ex.get("action") or "按纪律处理",
                      note="这一条不看别的判定 —— 出场纪律优先于形态与模型",
                      price=line),
                "conflicts": conflicts}

    # ② 今天已触发(买侧或卖侧)
    if urg.get("level") == "triggered":
        side = urg.get("side_cn") or ""
        return {**_mk(ACT, f"{side}点已触发" if side else "已触发",
                      # [R307] `what` 是**这只票的读数**(带具体价与百分比),
                      # `action` 是**这一档该怎么办的道理**(每只落到同一分支的
                      # 票都是同一句)。R299 已经为 EXIT/CONFLICT 拆过一次, 这里
                      # 是同一个毛病的第三处 —— 串在一起会让一句 20 字的读数
                      # 拖着 40 字的说教, 在一张 166 行的表里挤爆那一格。
                      urg.get("what") or "",
                      note=urg.get("action") or "",
                      price=ex.get("line")),
                "conflicts": conflicts}

    # ③ 判定打架 —— **刻意排在「逼近」之前**
    #
    # 「还差 1.2% 到买点」这种话会诱人下手, 而几套判定分歧的时候正是不该
    # 下手的时候。先说分歧, 再说距离。
    if conflicts:
        return {**_mk(CONFLICT, f"几个判定不一致({len(conflicts)} 处)",
                      conflicts[0] + (f";另有 {len(conflicts) - 1} 处" if len(conflicts) > 1 else ""),
                      note="各说各的时候, 等它们对齐比猜谁对划算"),
                "conflicts": conflicts}

    # ④ 逼近某个价
    if urg.get("level") in ("near", "flip", "band"):
        side = urg.get("side_cn") or ""
        return {**_mk(WATCH, f"{urg.get('label')}{side and '·' + side}",
                      urg.get("what") or "",
                      note=urg.get("action") or "",
                      price=ex.get("line")),
                "conflicts": conflicts}

    # ⑤ 形态给的提示
    ph_code = (phase or {}).get("code")
    ev_code = (event or {}).get("code")
    if held and ph_code in ("overextended", "stalling"):
        return {**_mk(SHAPE, "该想退出计划了",
                      (phase or {}).get("why") or "",
                      note=(phase or {}).get("watch") or ""),
                "conflicts": conflicts}
    if not held and ev_code in ("main_advance", "breakout_hold"):
        return {**_mk(SHAPE, "值得看一眼",
                      f"{(event or {}).get('cn')}:{(event or {}).get('why') or ''}"),
                "conflicts": conflicts}
    if not held and ph_code == "coiling":
        return {**_mk(SHAPE, "酝酿中",
                      (phase or {}).get("why") or "",
                      note=(phase or {}).get("watch") or ""),
                "conflicts": conflicts}

    # [R299] 这一档的 `why` **本来就没有内容可说** —— 它只是把「没事」换个说法
    # 再讲一遍。挪进 `note`(悬停)之后, 界面上这一档就只剩「没事」两个字,
    # 而这正是它该占的分量: 一张 166 行的表里, 没事的那些行不该和要动的一样响。
    return {**_mk(IDLE, "没事", "", note="五套判定都没有可说的 —— 今天不必看它"),
            "conflicts": conflicts}


def playbook_many(symbols: list[str], *, positions: dict, trends: dict,
                  exit_lines: dict, urgency: dict, keltner: dict,
                  phases: dict, events: dict) -> dict[str, dict]:
    """批量。原料全是调用方已经算好的, **零新增取数**。"""
    out: dict[str, dict] = {}
    for sym in symbols:
        kc = keltner.get(sym) or {}
        out[sym] = playbook(
            position=positions.get(sym), trend=trends.get(sym),
            exit_line=exit_lines.get(sym), urgency=urgency.get(sym),
            verdict=kc.get("verdict"), phase=phases.get(sym),
            event=events.get(sym))
    return out
