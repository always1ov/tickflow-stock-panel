"""[fork 增强] R179 今日总览行动区的分级与限流。

要守的两条:
  · **「无条件清仓」必须自成一档。** 跌破生命线和"持有票转下跌趋势"原来同为
    high, 谁排上面全靠 dict 迭代顺序 —— 等于没定。
  · **已经发生过的事不能挤掉此刻要处理的事。** 监控触发是近 24h 的历史记录,
    原来最多灌 10 条进行动区。
"""
from app.api.today import SEVERITY_RANK, _MAX_ALERT_ACTIONS


def _sorted(items: list[dict]) -> list[str]:
    out = sorted(items, key=lambda a: SEVERITY_RANK.get(a["severity"], 9))
    return [a["kind"] for a in out]


def test_四档从急到缓():
    assert (SEVERITY_RANK["fatal"] < SEVERITY_RANK["high"]
            < SEVERITY_RANK["mid"] < SEVERITY_RANK["low"])


def test_无条件清仓永远排在最前():
    """跌破生命线是"不用想, 照做"; 其余 high 都要看情况, 不是一个量级。"""
    items = [
        {"kind": "alert", "severity": "low"},
        {"kind": "exit_near", "severity": "mid"},
        {"kind": "trend_break", "severity": "high"},
        {"kind": "portfolio_drawdown", "severity": "high"},
        {"kind": "lifeline_broken", "severity": "fatal"},
    ]
    assert _sorted(items)[0] == "lifeline_broken"


def test_监控触发永远排在最后():
    """它说的是"昨天发生过什么", 行动区其余各项说的是"此刻是什么状态"。"""
    items = [
        {"kind": "alert", "severity": "low"},
        {"kind": "exit_near", "severity": "mid"},
    ]
    assert _sorted(items)[-1] == "alert"


def test_同档内保持插入顺序():
    """Python 的 sort 是稳定的 —— 同档内的先后由构建顺序决定, 不该被打乱。"""
    items = [{"kind": f"h{i}", "severity": "high"} for i in range(5)]
    assert _sorted(items) == [f"h{i}" for i in range(5)]


def test_未知档位排到最后而不是报错():
    """多一个没见过的 severity 不该让整个行动区崩掉。"""
    items = [{"kind": "weird", "severity": "???"}, {"kind": "x", "severity": "mid"}]
    assert _sorted(items) == ["x", "weird"]


def test_监控触发有上限():
    assert _MAX_ALERT_ACTIONS <= 3, "历史记录列太多就会把要处理的挤下去"


def test_限流常量与四档同在一个模块():
    """两者一起决定行动区读起来什么样, 分散到两处以后改一个忘一个。"""
    import app.api.today as t
    assert hasattr(t, "SEVERITY_RANK") and hasattr(t, "_MAX_ALERT_ACTIONS")
