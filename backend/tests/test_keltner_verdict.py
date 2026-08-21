"""[fork 增强] R44 三档通道组合 → 一句话结论。

八种组合都要给得出结论, 但真正要守的是**判定顺序**: 短期与长期反向的那两种
("超跌反弹"和"强势深调")必须先判。它们正是最容易读反的 —— 同样一个"短期到轨",
长期档一翻结论完全相反; 放在后面判就会被"三档同向"之类的粗规则先吃掉。
"""
from __future__ import annotations

import pytest

from app.indicators import keltner as k


def _b(s, m=None, long=None):
    out = {"s": {"pos": s, "pos_cn": k.POS_CN[s]}}
    if m:
        out["m"] = {"pos": m, "pos_cn": k.POS_CN[m]}
    if long:
        out["l"] = {"pos": long, "pos_cn": k.POS_CN[long]}
    return out


# ---------- 八种组合 ----------

@pytest.mark.parametrize("bands,code,title", [
    # 偏贵一侧
    ((k.POS_ABOVE, k.POS_INSIDE, k.POS_INSIDE), "high_short_only", "短线冲高"),
    ((k.POS_ABOVE, k.POS_NEAR_UPPER, k.POS_INSIDE), "top_confirmed", "到位了"),
    ((k.POS_ABOVE, k.POS_ABOVE, k.POS_ABOVE), "top_all_bands", "大顶区域"),
    ((k.POS_ABOVE, k.POS_INSIDE, k.POS_BELOW), "bounce_in_downtrend", "超跌反弹"),
    # 偏便宜一侧
    ((k.POS_NEAR_LOWER, k.POS_INSIDE, k.POS_INSIDE), "low_short_only", "短线回调"),
    ((k.POS_BELOW, k.POS_BELOW, k.POS_INSIDE), "bottom_confirmed", "调到位了"),
    ((k.POS_BELOW, k.POS_BELOW, k.POS_BELOW), "falling_all_bands", "下跌途中"),
    ((k.POS_BELOW, k.POS_INSIDE, k.POS_ABOVE), "dip_in_uptrend", "强势深调"),
])
def test_every_combination_has_a_verdict(bands, code, title):
    v = k.verdict(_b(*bands))
    assert v["code"] == code and v["title"] == title
    assert v["action"], "每一条都要给得出一句可执行的结论"
    assert v["detail"], "每一条都要说清为什么"


def test_inside_the_short_channel_gives_no_verdict():
    """短期在通道中部 = 这一列此刻没有信息, 不硬凑一句话。"""
    assert k.verdict(_b(k.POS_INSIDE)) is None
    assert k.verdict(_b(k.POS_INSIDE, k.POS_ABOVE, k.POS_ABOVE)) is None


# ---------- 判定顺序: 矛盾组合优先 ----------

def test_bounce_wins_over_aligned_when_long_band_disagrees():
    """短期+中期都到上沿, 但长期还在下沿 —— 这是跌深了反弹, 不是"到位了"。
    顺序反了会说成止盈时机, 那是把反弹当成上涨。"""
    v = k.verdict(_b(k.POS_ABOVE, k.POS_ABOVE, k.POS_BELOW))
    assert v["code"] == "bounce_in_downtrend"
    assert v["tone"] == k.TONE_SELL


def test_deep_dip_wins_over_aligned_when_long_band_disagrees():
    """短期+中期都到下沿, 但长期仍在上沿 —— 强势股洗盘, 不是"下跌途中"。
    顺序反了会说成别抄, 那正好错过最好的低吸位置。"""
    v = k.verdict(_b(k.POS_BELOW, k.POS_BELOW, k.POS_ABOVE))
    assert v["code"] == "dip_in_uptrend"
    assert v["tone"] == k.TONE_BUY


def test_the_two_contradictory_cases_point_opposite_ways():
    """同样是"短期到轨", 长期档一翻, 结论必须完全相反 —— 这是三档一起看的全部意义。"""
    high = k.verdict(_b(k.POS_ABOVE, k.POS_INSIDE, k.POS_BELOW))
    low = k.verdict(_b(k.POS_BELOW, k.POS_INSIDE, k.POS_ABOVE))
    assert high["tone"] == k.TONE_SELL and low["tone"] == k.TONE_BUY
    assert "反弹" in high["detail"] and "洗盘" in low["detail"]


# ---------- 语气分档 ----------

def test_only_the_short_band_never_says_sell():
    """只有短期到上沿是强势票的常态, 说"该减"会让人反复卖飞。"""
    v = k.verdict(_b(k.POS_ABOVE, k.POS_INSIDE, k.POS_INSIDE))
    assert v["tone"] == k.TONE_HOLD
    assert "别在这加仓" in v["action"]


def test_falling_across_all_bands_says_stay_away_not_buy():
    """三档同时到下沿是下跌途中, 这时候说"低吸"就是让人越抄越套。"""
    v = k.verdict(_b(k.POS_BELOW, k.POS_BELOW, k.POS_BELOW))
    assert v["tone"] == k.TONE_AVOID
    assert "别抄" in v["action"]


def test_verdicts_never_issue_a_clear_out_instruction():
    """清不清仓是出场线/生命线的事, 优先级在通道之上。通道只谈加减, 不谈清仓。"""
    for code in ("high_short_only", "top_confirmed", "top_all_bands", "bounce_in_downtrend"):
        title, action, detail, _side, _tone = k._VERDICTS[code]  # noqa: SLF001
        assert "清仓" not in action + detail


# ---------- 与 pressure 一致 ----------

def test_verdict_side_always_matches_pressure():
    for pos in (k.POS_ABOVE, k.POS_NEAR_UPPER, k.POS_BELOW, k.POS_NEAR_LOWER):
        bands = _b(pos)
        assert k.verdict(bands)["side"] == k.pressure(bands)["side"]


def test_verdict_carries_which_bands_agreed():
    v = k.verdict(_b(k.POS_ABOVE, k.POS_ABOVE, k.POS_ABOVE))
    assert v["bands_aligned"] == 3
    assert "中期" in v["bands_text"] and "长期" in v["bands_text"]


def test_verdict_survives_missing_bands():
    """新股不够 120 根时长期档缺席, 不该因此算不出结论。"""
    v = k.verdict(_b(k.POS_ABOVE))
    assert v["code"] == "high_short_only"
    assert k.verdict(None) is None
    assert k.verdict({}) is None


# ---------- 批量服务把结论带出来 ----------

def test_batch_attaches_the_verdict():
    import polars as pl

    from app.services import keltner_service

    class _Repo:
        @staticmethod
        def get_enriched_latest():
            return pl.DataFrame([{"symbol": "600000.SH", "close": 108.5,
                                  "atr_14": 5.0, "ma20": 100.0, "ma60": 95.0}]), "2026-08-21"

        @staticmethod
        def get_daily_batch(symbols, start, end, columns=None):
            return pl.DataFrame({"symbol": ["600000.SH"] * 140,
                                 "date": [start] * 140, "close": [100.0] * 140})

    out = keltner_service.channels_for_symbols(_Repo(), ["600000.SH"])["600000.SH"]
    assert out["verdict"]["title"], "决策台要直接拿这句话显示, 不该自己再拼一遍规则"
    assert out["verdict"]["side"] == k.SIDE_HIGH
