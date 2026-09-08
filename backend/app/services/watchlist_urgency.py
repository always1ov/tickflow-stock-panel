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
  flip      刚变盘   今天六态刚翻转(duration==1) —— 昨天还不是这个状态
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
    FLIP: "刚变盘",
    BAND: "到轨",
    IDLE: "无事",
}
# 越小越急。前端默认排序直接用它, 免得两边各编一套顺序(与 keltner verdict 的
# rank 同一个做法)。
ORDER = {TRIGGERED: 0, NEAR: 1, FLIP: 2, BAND: 3, IDLE: 4}

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

    # ① 已触发 —— 纪律层面已经该动手
    if exit_line and exit_line.get("triggered"):
        return _mk(TRIGGERED, 0.0,
                   f"{exit_line.get('stage_cn') or '出场线'}已跌破"
                   f"({exit_line.get('action') or '按纪律处理'})")

    # ② 逼近: 出场线优先于翻转价 —— 前者是纪律, 后者是形态
    ex_d = _abs_or_none((exit_line or {}).get("distance_pct"))
    if ex_d is not None and ex_d <= EXIT_NEAR_PCT:
        return _mk(NEAR, ex_d,
                   f"离{exit_line.get('stage_cn') or '出场线'}仅 {ex_d * 100:.1f}%")

    flip_d, flip_txt = _nearest_flip(trend, held)
    if flip_d is not None and flip_d <= FLIP_NEAR_PCT:
        return _mk(NEAR, flip_d, flip_txt)

    # ③ 今天刚翻转 —— duration==1 就是"昨天还不是这个状态"
    if (trend or {}).get("duration") == 1:
        frm = (trend or {}).get("entered_from_cn")
        cur = (trend or {}).get("state_cn") or "新状态"
        return _mk(FLIP, flip_d,
                   f"今日刚转入{cur}" + (f"(自{frm})" if frm else ""))

    # ④ 到轨 —— 短期通道贴/破上下轨
    pos = ((bands or {}).get("s") or {}).get("pos")
    if pos in _band_positions():
        pos_cn = ((bands or {}).get("s") or {}).get("pos_cn") or "到轨"
        return _mk(BAND, flip_d, f"短期通道{pos_cn}")

    return _mk(IDLE, None, "无触发")


def _nearest_flip(trend: dict | None, held: bool) -> tuple[float | None, str]:
    """离翻转还有多远。持有的看转弱(要卖), 没持有的看转强(要买)。

    两边都有值时取更近的那个 —— 一只票同时逼近上下两个翻转价的情况很少,
    真出现了也是"离哪个近就先盯哪个"。
    """
    t = trend or {}
    cands: list[tuple[float, str]] = []
    dn = _abs_or_none(t.get("flip_down_distance_pct"))
    up = _abs_or_none(t.get("flip_up_distance_pct"))
    if dn is not None:
        cands.append((dn, f"离转弱价仅 {dn * 100:.1f}%"))
    if up is not None:
        cands.append((up, f"离转强价仅 {up * 100:.1f}%"))
    if not cands:
        return None, ""
    # 持有的票优先看转弱(卖点), 空仓的优先看转强(买点); 但只在两边都存在时才偏袒
    if len(cands) == 2:
        pick = cands[0] if held else cands[1]
        other = cands[1] if held else cands[0]
        # 另一边近得多(差一倍以上)就还是听距离的 —— 偏好不该压过事实
        return (other if other[0] * 2 < pick[0] else pick)
    return cands[0]


def _mk(level: str, distance: float | None, reason: str) -> dict:
    return {"level": level, "label": LABELS[level], "order": ORDER[level],
            "distance": None if distance is None else round(distance, 4),
            "reason": reason}


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
            out[sym] = _mk(IDLE, None, "判定失败")
    return out
