"""[fork 增强] R29 六态翻转触发价。

背景: 趋势途中 up_pivot 退化成"本轮最高收盘价"—— 创新高当天就等于当日收盘,
拿它当"突破 X 加仓"的触发价等于没给价位。补出真正前瞻的两条线:
跌破 flip_down 转弱 / 站上 flip_up 转强。
"""
import pytest

from app.indicators.livermore import action_text, compute

THR = 0.06

# 先连续创新高 → 回撤破阈值 → 反弹未破前高 → 站上前高转 UT → UT 内震荡再新高
SERIES = [10, 10.5, 11, 11.6, 12.2, 12.8,   # 0-5   多头侧, 不断新高
          12.0, 11.6, 11.4,                  # 6-8   回撤(-10.9%) → NREA
          11.8,                              # 9     反弹但幅度不够
          12.3, 12.6,                        # 10-11 站上 lo×1.06 → NR
          13.0, 13.4,                        # 12-13 破前高 12.80 → UT
          13.1, 12.9, 13.2,                  # 14-16 UT 内震荡, 未创新高
          13.6]                              # 17    再创新高


@pytest.fixture()
def steps():
    dates = [f"d{i:02d}" for i in range(len(SERIES))]
    return compute(SERIES, dates, THR)["steps"]


def test_uptrend_pivot_degenerates_to_todays_close(steps):
    """确认用户观察到的现象真实存在 —— 这正是本次改动的动机。"""
    s = steps[17]
    assert s["state"] == "UT"
    assert s["up_pivot"] == pytest.approx(s["close"]), "创新高当天, 上关键点就是当日收盘"


def test_uptrend_pivot_holds_on_non_new_high_days(steps):
    """但不创新高的日子它会停住 —— 它是"本轮最高收盘价", 不是"最新收盘价"。"""
    assert [s["up_pivot"] for s in steps[13:17]] == [13.4, 13.4, 13.4, 13.4]


def test_uptrend_flip_down_is_forward_looking(steps):
    """上涨趋势: 跌破价 = 本轮最高 ×(1-阈值), 固定在现价下方。"""
    s = steps[17]
    assert s["flip_down"] == pytest.approx(13.6 * (1 - THR))
    assert s["flip_down"] < s["close"], "是前瞻位, 不贴现价"
    assert s["flip_up"] is None, "已是最强状态, 没有更强的一档"


def test_flip_down_only_moves_on_new_highs(steps):
    """UT 内不创新高的日子跌破价也不动 —— 盯盘时是一条稳定的线。"""
    assert [s["flip_down"] for s in steps[13:17]] == pytest.approx([13.4 * 0.94] * 4)


def test_rally_state_keeps_pivot_as_upside_trigger(steps):
    """回升态: 上关键点仍是真正的触发价(在现价上方), 这部分逻辑不动。"""
    s = steps[11]
    assert s["state"] == "NR"
    assert s["flip_up"] == s["up_pivot"] == 12.8
    assert s["close"] < s["flip_up"], "要站上去才确认转多"
    assert s["flip_down"] == pytest.approx(s["leg_high"] * (1 - THR))


def test_reaction_state_flip_up_from_leg_low(steps):
    """回撤态: 站上 本轮最低×(1+阈值) 转回升。"""
    s = steps[8]
    assert s["state"] == "NREA"
    assert s["flip_up"] == pytest.approx(11.4 * (1 + THR))
    assert s["flip_down"] is None, "本例尚未形成下关键点"


def test_downtrend_flip_up_and_no_flip_down():
    """下跌趋势镜像: 只有"站上多少转强", 没有更弱的一档。

    进 DT 必须先有下关键点再跌穿它 —— 单边下跌只会停在自然回撤态,
    所以中间插一段反弹把 dn_pivot 立起来。
    """
    closes = [20, 18, 16, 14, 12, 10, 11, 11.5, 9.8, 9.0, 8.0]
    steps = compute(closes, [f"d{i}" for i in range(len(closes))], THR)["steps"]
    s = steps[-1]
    assert s["state"] == "DT"
    assert s["flip_up"] == pytest.approx(s["leg_low"] * (1 + THR))
    assert s["flip_down"] is None


def test_leg_high_low_recorded(steps):
    s = steps[17]
    assert s["leg_high"] == 13.6
    assert steps[8]["leg_low"] == 11.4


# ---------- 操作建议文案 ----------

def test_action_text_uptrend_uses_flip_not_pivot():
    txt = action_text("UT", up_pivot=13.6, dn_pivot=11.4, flip_down=12.78, flip_up=None)
    assert "12.78" in txt and "跌破" in txt
    assert "突破 13.60" not in txt, "不再让用户'突破今天的收盘价再加仓'"
    assert "加仓" in txt, "PRD §6.6 的 ADD 语义不能因为换价位而丢掉"


def test_action_text_downtrend_uses_flip():
    txt = action_text("DT", up_pivot=None, dn_pivot=8.0, flip_down=None, flip_up=8.48)
    assert "8.48" in txt and "站上" in txt


def test_action_text_rally_keeps_pivot_and_adds_downside():
    txt = action_text("NR", up_pivot=12.8, dn_pivot=11.4, flip_down=11.56, flip_up=12.8)
    assert "上破 12.80" in txt and "11.56" in txt


def test_action_text_falls_back_without_flip_prices():
    """老调用方(不传翻转价)行为不变。"""
    assert action_text("UT", 13.6, 11.4) == "顺势持有多头 / 突破 13.60 可金字塔加仓"
    assert action_text(None, None, None) == ""
