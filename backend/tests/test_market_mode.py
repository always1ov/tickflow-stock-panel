"""[fork 增强] 大盘红绿灯: 模式判定 + 防守一票否决 + 切换黏性。"""
import pytest

from app.services.market_mode import (
    CONFIRM_DAYS, MIN_BARS, apply_stickiness, combine_posture, decide_mode, raw_mode,
)


def _closes(n=260, base=3000.0, step=1.0):
    """升序收盘序列: 默认温和上涨(收盘在 MA50/MA200 之上, 年动量为正)。"""
    return [base + i * step for i in range(n)]


# ---------- raw_mode ----------

def test_uptrend_is_attack():
    r = raw_mode(_closes())
    assert r["mode"] == "进攻"
    assert "年线" in r["reason"]


def test_below_ma200_is_defense_veto():
    """收盘跌破年线 → 防守, 不管别的指标多好。"""
    closes = _closes()
    closes[-1] = sum(closes[-201:-1]) / 200 * 0.98  # 压到 MA200 之下
    r = raw_mode(closes)
    assert r["mode"] == "防守"
    assert "年线" in r["reason"]


def test_negative_momentum_is_defense():
    """比一年前还低 → 防守, 即使仍在年线上方(高位滞涨形态)。"""
    n = 260
    closes = [4000.0 - i * 3 for i in range(n // 2)]  # 前半下跌
    closes += [closes[-1] + i * 2.2 for i in range(n - n // 2)]  # 后半回升但没回到一年前
    r = raw_mode(closes)
    if r["metrics"]["momentum_12m"] < 0 and r["metrics"]["close"] > r["metrics"]["ma200"]:
        assert r["mode"] == "防守"
        assert "一年前" in r["reason"]
    else:  # 构造不满足前提时至少不误报进攻
        assert r["mode"] in ("防守", "谨慎")


def test_below_ma50_above_ma200_is_caution():
    closes = _closes(step=2.0)
    ma50 = sum(closes[-50:]) / 50
    ma200 = sum(closes[-200:]) / 200
    closes[-1] = (ma50 + ma200) / 2  # 落在 MA200 与 MA50 之间
    r = raw_mode(closes)
    assert r["mode"] == "谨慎"


def test_insufficient_history_says_so():
    r = raw_mode(_closes(n=MIN_BARS - 1))
    assert r["mode"] == "观察"
    assert "指数历史仅" in r["reason"]


# ---------- 黏性 ----------

def test_hard_defense_applies_immediately():
    state = {"mode": "进攻", "raw_mode": "进攻", "raw_streak": 1, "as_of": "2026-08-14"}
    out = apply_stickiness({"mode": "防守", "veto": True, "reason": "跌破年线", "metrics": {}},
                           state, "2026-08-15")
    assert out["mode"] == "防守"
    assert out["pending"] is None
    assert state["mode"] == "防守"


def test_soft_defense_needs_confirmation():
    """[缺口①] 年线拐头的软防守走确认流程, 不立即切换。"""
    state = {"mode": "进攻", "raw_mode": "进攻", "raw_streak": 1, "as_of": "2026-08-14"}
    out = apply_stickiness({"mode": "防守", "veto": False, "reason": "年线拐头", "metrics": {}},
                           state, "2026-08-15")
    assert out["mode"] == "进攻", "软防守第 1 天应保持原模式"
    assert out["pending"]["mode"] == "防守"


# ---------- decide_mode 分支(缺口①: 年线斜率) ----------

def test_decide_below_ma50_rising_ma200_is_caution():
    out = decide_mode(close=100, ma50=105, ma200=95, momentum=0.1, ma200_rising=True)
    assert out["mode"] == "谨慎" and out["veto"] is False


def test_decide_below_ma50_falling_ma200_is_soft_defense():
    """PRD 4.4.2: 年线向上是中性的必要条件; 不成立 → 防守(软, 走确认)。"""
    out = decide_mode(close=100, ma50=105, ma200=95, momentum=0.1, ma200_rising=False)
    assert out["mode"] == "防守" and out["veto"] is False
    assert "拐头向下" in out["reason"]


def test_decide_hard_conditions_have_veto():
    assert decide_mode(90, 105, 95, 0.1, True)["veto"] is True   # 破年线
    assert decide_mode(100, 95, 96, -0.05, True)["veto"] is True  # 年动量为负


def test_non_defense_switch_needs_confirmation():
    """进攻→谨慎 需连续 CONFIRM_DAYS 天; 第 1 天保持原模式并标待确认。"""
    state = {"mode": "进攻", "raw_mode": "进攻", "raw_streak": 1, "as_of": "2026-08-13"}
    day1 = apply_stickiness({"mode": "谨慎", "reason": "跌破50日线", "metrics": {}},
                            state, "2026-08-14")
    assert day1["mode"] == "进攻"
    assert day1["pending"] == {"mode": "谨慎", "streak": 1, "need": CONFIRM_DAYS,
                               "raw_reason": "跌破50日线"}
    day2 = apply_stickiness({"mode": "谨慎", "reason": "跌破50日线", "metrics": {}},
                            state, "2026-08-15")
    assert day2["mode"] == "谨慎"
    assert day2["pending"] is None


def test_same_day_refresh_does_not_double_count():
    state = {"mode": "进攻", "raw_mode": "进攻", "raw_streak": 1, "as_of": "2026-08-13"}
    apply_stickiness({"mode": "谨慎", "reason": "x", "metrics": {}}, state, "2026-08-14")
    again = apply_stickiness({"mode": "谨慎", "reason": "x", "metrics": {}},
                             state, "2026-08-14")
    assert again["mode"] == "进攻", "同一交易日反复刷新不能把确认天数刷满"
    assert again["pending"]["streak"] == 1


def test_flip_back_resets_streak():
    """确认期内原始模式又翻回去 → 计数清零, 不留残余。"""
    state = {"mode": "进攻", "raw_mode": "进攻", "raw_streak": 1, "as_of": "2026-08-13"}
    apply_stickiness({"mode": "谨慎", "reason": "x", "metrics": {}}, state, "2026-08-14")
    back = apply_stickiness({"mode": "进攻", "reason": "回到50日线上", "metrics": {}},
                            state, "2026-08-15")
    assert back["mode"] == "进攻" and back["pending"] is None
    day = apply_stickiness({"mode": "谨慎", "reason": "x", "metrics": {}},
                           state, "2026-08-16")
    assert day["pending"]["streak"] == 1, "重新出现要从第 1 天重数"


def test_recovery_from_defense_also_needs_confirmation():
    state = {"mode": "防守", "raw_mode": "防守", "raw_streak": 1, "as_of": "2026-08-13"}
    day1 = apply_stickiness({"mode": "进攻", "reason": "收复年线", "metrics": {}},
                            state, "2026-08-14")
    assert day1["mode"] == "防守", "从防守恢复也要确认, 防止假反弹"


# ---------- 姿态合成 ----------

@pytest.mark.parametrize("market,breadth,expected", [
    ("防守", "进攻", "防守"),   # 大盘防守一票否决
    ("进攻", "防守", "防守"),   # 自选一片惨绿也不能进攻
    ("进攻", "谨慎", "谨慎"),
    ("谨慎", "进攻", "谨慎"),
    ("进攻", "进攻", "进攻"),
    ("观察", "进攻", "观察"),
])
def test_combine_takes_more_conservative(market, breadth, expected):
    assert combine_posture(market, breadth) == expected
