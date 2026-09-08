"""[fork 增强] R177 个股复盘按「段」聚合。

要守的核心只有一条: **前瞻收益会重叠, 所以单位必须是段不是天。**
一段持续 8 天的上涨趋势, 按天算是 8 个样本, 可这 8 天各自的"之后 5 日"
互相共享 4 天。按天算出来的 n 是假的 —— 它会让一个很薄的结论显得扎实。
"""
from app.services import review_service as rs


def _rows(states: list[str | None]) -> list[dict]:
    """按给定的状态序列造行(日期从 2025-01-01 起递增, 只用来区分段起点)。"""
    return [{"date": f"2025-01-{i + 1:02d}",
             "trend": None if s is None else {"state": s, "state_cn": s}}
            for i, s in enumerate(states)]


def test_连续同状态压成一段而不是多个样本():
    rows = _rows(["UT"] * 8)
    closes = [10.0] * 20
    eps = rs._episodes(rows, lambda r: (r.get("trend") or {}).get("state"),
                       closes, 0, 5)
    assert len(eps) == 1, "8 天连续上涨趋势是 1 段, 不是 8 个样本"
    assert eps[0]["days"] == 8
    assert eps[0]["start"] == "2025-01-01", "收益要从段的第一天起算"


def test_状态切换后再切回来算两段():
    rows = _rows(["UT", "UT", "DT", "UT"])
    eps = rs._episodes(rows, lambda r: (r.get("trend") or {}).get("state"),
                       [10.0] * 20, 0, 5)
    keys = [e["key"] for e in eps]
    assert keys == ["UT", "DT", "UT"], f"中间断开就是两段 UT, 实际 {keys}"


def test_中间缺读数会打断段():
    rows = _rows(["UT", None, "UT"])
    eps = rs._episodes(rows, lambda r: (r.get("trend") or {}).get("state"),
                       [10.0] * 20, 0, 5)
    assert [e["key"] for e in eps] == ["UT", "UT"], "隔了一天没读数, 前后不是同一次"


def test_没有读数的行不产生段():
    eps = rs._episodes(_rows([None, None]),
                       lambda r: (r.get("trend") or {}).get("state"),
                       [10.0] * 20, 0, 5)
    assert eps == []


def test_末尾不足前瞻期的段仍计次数但不计收益():
    """那一段确实发生过, 只是结果还没出来 —— 把它从次数里抹掉会答错
    "这只票出现过几次"这个最基本的问题。"""
    eps = [{"key": "UT", "start": "d1", "days": 3, "fwd": 0.05},
           {"key": "UT", "start": "d2", "days": 2, "fwd": None}]
    got = rs._agg_episodes(eps, lambda k: k)[0]
    assert got["n"] == 2, "两段都要计数"
    assert got["scored"] == 1, "只有一段知道结果"
    assert got["avg_fwd"] == 0.05, "均值只能用已知结果的那段算"


def test_全部段都还不知道结果时均值为None():
    eps = [{"key": "UT", "start": "d1", "days": 3, "fwd": None}]
    got = rs._agg_episodes(eps, lambda k: k)[0]
    assert got["n"] == 1
    assert got["avg_fwd"] is None, "一段都没兑现就不能给均值"


def test_平均持续天数():
    eps = [{"key": "UT", "start": "d1", "days": 8, "fwd": 0.01},
           {"key": "UT", "start": "d2", "days": 2, "fwd": 0.01}]
    got = rs._agg_episodes(eps, lambda k: k)[0]
    assert got["avg_days"] == 5.0


def test_胜次按段数不按天数():
    eps = [{"key": "UT", "start": "d1", "days": 8, "fwd": 0.05},
           {"key": "UT", "start": "d2", "days": 1, "fwd": -0.02}]
    got = rs._agg_episodes(eps, lambda k: k)[0]
    assert got["win"] == 1, "赢的是 1 段, 不是 8 天"
    assert got["scored"] == 2


def test_趋势状态输出中文标签():
    from app.indicators.livermore import STATE_LABELS
    rows = _rows(["UT"] * 6)
    got = rs._trend_outcomes(rows, [10.0] * 20, 0)
    assert got[0]["label"] == STATE_LABELS["UT"][0]
    assert got[0]["n"] == 1
