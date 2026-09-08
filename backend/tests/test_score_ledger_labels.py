"""[fork 增强] R175 台账「回头看」: 按标签分组 + 全期/最近背离。

这一层要守住的东西只有两条, 剩下的都是 group-by:
  · **样本不足不给结论** —— 5 个样本的 60% 和 500 个样本的 60% 不是一回事,
    背离判定必须两边都够样本才开口;
  · **没标签的行不能丢** —— 丢了的话各档占比失真, 用户会以为"通道结论天天
    都有", 其实多数日子它是 None。
"""
from app.services import score_ledger as sl


def _row(*, ctx: dict, as_of: str, t5: float) -> dict:
    return {"symbol": "000001", "score": 70, "rank": 1, "shown": True,
            "ctx": ctx, "as_of": as_of, "r": {"t1": t5 / 2, "t3": t5, "t5": t5}}


def test_没有标签的行归进未标注档而不是被丢掉():
    rows = [_row(ctx={"verdict": "top_confirmed"}, as_of="2025-01-02", t5=1.0),
            _row(ctx={}, as_of="2025-01-02", t5=-1.0),
            _row(ctx={}, as_of="2025-01-02", t5=-2.0)]
    dims = {d["key"]: d for d in sl._by_label(rows, {"2025-01-02"})}
    items = {i["value"]: i for i in dims["verdict"]["items"]}
    assert items["—"]["count"] == 2, "没有 verdict 的行必须留在未标注档里"
    # 总数守恒 —— 分组不能凭空吃掉行
    assert sum(i["count"] for i in dims["verdict"]["items"]) == len(rows)


def test_verdict_code_显示成中文标题():
    """对着 keltner 的真值断言, 不写死字面 —— 作者改了文案不该让这个测试红。"""
    from app.indicators.keltner import _VERDICTS

    code = "bounce_in_downtrend"
    rows = [_row(ctx={"verdict": code}, as_of="2025-01-02", t5=1.0)]
    dims = {d["key"]: d for d in sl._by_label(rows, {"2025-01-02"})}
    names = [i["value"] for i in dims["verdict"]["items"]]
    assert code not in names, "不该把 code 直接显示给用户"
    assert _VERDICTS[code][0] in names, f"应是 keltner 里那个标题, 实际 {names}"


def test_样本不足时不给背离结论():
    # 每边只有 3 个样本, 远低于 MIN_LABEL_N
    rows = [_row(ctx={"verdict": "top_confirmed"}, as_of="2025-01-02", t5=1.0)
            for _ in range(3)]
    dims = {d["key"]: d for d in sl._by_label(rows, {"2025-01-02"})}
    item = dims["verdict"]["items"][0]
    assert item["shift"] is None, "样本不足必须闭嘴, 不能硬给一个背离结论"


def test_样本够且明显转差时报出背离():
    n = sl.MIN_LABEL_N + 5
    # 全期(含最近): 老日子全赢, 最近全输 —— 胜率必然大幅下滑
    old = [_row(ctx={"verdict": "top_confirmed"}, as_of="2025-01-02", t5=1.0)
           for _ in range(n * 3)]
    recent = [_row(ctx={"verdict": "top_confirmed"}, as_of="2025-06-02", t5=-1.0)
              for _ in range(n)]
    dims = {d["key"]: d for d in sl._by_label(old + recent, {"2025-06-02"})}
    item = dims["verdict"]["items"][0]
    assert item["shift"] is not None
    assert item["shift"]["dir"] == "down", item["shift"]
    assert item["shift"]["delta"] < 0


def test_最近这一列只统计最近那批日子():
    rows = [_row(ctx={"state": "UT"}, as_of="2025-01-02", t5=1.0),
            _row(ctx={"state": "UT"}, as_of="2025-06-02", t5=1.0)]
    dims = {d["key"]: d for d in sl._by_label(rows, {"2025-06-02"})}
    item = dims["state"]["items"][0]
    assert item["count"] == 2
    assert item["recent_count"] == 1, "最近列不能把老日子算进去"


def test_龙虎榜缺字段等于未上榜():
    rows = [_row(ctx={"dragon": True}, as_of="2025-01-02", t5=1.0),
            _row(ctx={}, as_of="2025-01-02", t5=1.0)]
    dims = {d["key"]: d for d in sl._by_label(rows, {"2025-01-02"})}
    names = {i["value"]: i["count"] for i in dims["dragon"]["items"]}
    assert names.get("上榜") == 1
    assert names.get("—") == 1, "没这个键就是没上榜, 归进未标注档"


def test_每个注册的维度都出现在结果里():
    rows = [_row(ctx={}, as_of="2025-01-02", t5=1.0)]
    keys = {d["key"] for d in sl._by_label(rows, set())}
    assert keys == {d["key"] for d in sl.LABEL_DIMS}, "注册表加了维度就该自动出现"
