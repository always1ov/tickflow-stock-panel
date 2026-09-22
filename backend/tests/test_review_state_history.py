"""[R431] 复盘「六个状态在这只票上的历史表现」那张表的数。

用户排版图第三块; 答复「只摆数, 不下结论」—— 所以这里只有测量, 没有一个字的建议。
分段**复用** R177 的 `_episodes`(同一个分段口径, 不另写一份), 在它之上多算三样:
共多少天、这段里涨跌、走完后 N 天。还在走的那一段计次数与天数, 不计后两样。
"""
from app.services import review_service as rs


def _rows(states):
    return [{"date": f"2025-01-{i + 1:02d}",
             "trend": None if s is None else {"state": s}} for i, s in enumerate(states)]


def _by(out):
    return {o["key"]: o for o in out}


def test_六个状态都占一行_按梯子顺序_名字取后端那一份():
    out = rs._state_history(_rows(["UT"] * 3), [10.0] * 10, 0)
    assert [o["key"] for o in out] == ["UT", "NR", "SR", "SREA", "NREA", "DT"]
    assert [o["label"] for o in out] == [rs.STATE_LABELS[k][0] for k in rs.STATE_LABELS]
    none = _by(out)["DT"]
    assert none["n"] == 0 and none["days"] == 0 and none["avg_ret"] is None


def test_段里涨跌从进段前一天收盘算到段末():
    # 暖机 1 根(offset=1): 10 → UT 两天 11, 12 → NR 一天 9 → UT 一天(还在走)
    closes = [10.0, 11.0, 12.0, 9.0, 9.9]
    out = _by(rs._state_history(_rows(["UT", "UT", "NR", "UT"]), closes, 1))
    ut = out["UT"]
    assert ut["n"] == 2 and ut["days"] == 3, "还在走的那一段也要计次数与天数"
    assert ut["done"] == 1, "还在走的那段不算走完"
    assert abs(ut["avg_ret"] - 0.2) < 1e-9, "10 → 12, 从进段前一天收盘算"
    assert ut["ret_win"] == 1
    nr = out["NR"]
    assert abs(nr["avg_ret"] - (9.0 / 12.0 - 1)) < 1e-9
    assert nr["ret_win"] == 0
    assert out["UT"]["current"] is True and out["NR"]["current"] is False


def test_走完后N天从段末收盘起算_不足N天不计():
    # 段首收盘 10、段末收盘 20: 从段首起算与从段末起算必须算出不同的数
    closes = [10.0, 10.0, 20.0, 22.0, 22.0, 22.0, 30.0, 22.0, 22.0, 22.0]
    rows = _rows(["UT", "UT"] + ["DT"] * 7)
    ut = _by(rs._state_history(rows, closes, 1))["UT"]
    assert ut["after_scored"] == 1
    assert abs(ut["avg_after"] - 0.1) < 1e-9, "段末 20 → 5 天后 22; 从段首起算会是 10 → 30"
    # DT 是还在走的那段: 走完后无从谈起
    dt = _by(rs._state_history(rows, closes, 1))["DT"]
    assert dt["after_scored"] == 0 and dt["avg_after"] is None


def test_末尾没有读数时最后一段不算还在走():
    out = _by(rs._state_history(_rows(["UT", "UT", None]), [10.0, 11.0, 12.0, 12.0], 1))
    assert out["UT"]["current"] is False and out["UT"]["done"] == 1


def test_分段与R177同一个口径():
    rows = _rows(["UT", "UT", "DT", None, "DT", "UT"])
    closes = [10.0] * 12
    eps = rs._episodes(rows, lambda r: (r.get("trend") or {}).get("state"), closes, 1, 5)
    hist = _by(rs._state_history(rows, closes, 1))
    for k in ("UT", "DT"):
        assert hist[k]["n"] == sum(1 for e in eps if e["key"] == k)
        assert hist[k]["days"] == sum(e["days"] for e in eps if e["key"] == k)


def test_只有测量没有结论():
    """用户选了「只摆数, 不下结论」: 不许出现胜率、建议一类的字段。"""
    for o in rs._state_history(_rows(["UT", "DT"]), [10.0] * 10, 0):
        assert set(o) == {"key", "label", "n", "days", "done", "avg_ret", "ret_win",
                          "after_scored", "avg_after", "current"}


def test_复盘载荷带上六个状态_分段与R177一致():
    from tests.test_flip_trades import _Repo, _review_frame
    out = rs.review_for_symbol(_Repo(_review_frame()), "600000.SH", 120)
    hist = out["state_history"]
    assert [h["key"] for h in hist] == list(rs.STATE_LABELS)
    by_trend = {o["key"]: o["n"] for o in out["trend_outcomes"]}
    for h in hist:
        assert h["n"] == by_trend.get(h["key"], 0), f"{h['key']} 段数与 trend_outcomes 对不上"
    assert sum(h["days"] for h in hist) == sum(1 for r in out["rows"] if r.get("trend"))
    assert sum(1 for h in hist if h["current"]) <= 1
