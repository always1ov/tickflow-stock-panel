"""[fork 增强] R205 「怎么办」收敛层。

这一层要守的是它存在的理由:

  1. **五套判定打架时必须说出来**, 而且要**盖过"逼近某个价"** ——
     「还差 1.2% 到买点」会诱人下手, 那正是不该下手的时刻。
  2. **纪律永远排第一**, 不参与讨论。
  3. **不产生新判定** —— 每句话都能追到某一层的原话。
  4. **不滥报打架** —— 「观望」「无结论」不算矛盾。一半的票都显示打架的话,
     用户三天后就学会无视它, 这一档就废了。
"""
import pytest

from app.services import stock_playbook as pb


def _run(**kw):
    base = dict(position=None, trend=None, exit_line=None, urgency=None,
                verdict=None, phase=None, event=None, signal=None)
    base.update(kw)
    return pb.playbook(**base)


_UT = {"state": "UT", "state_cn": "上涨趋势"}
_DT = {"state": "DT", "state_cn": "下跌趋势"}
_NEAR_BUY = {"level": "near", "label": "逼近", "side_cn": "买",
             "what": "还差 1.2% 到买点", "action": "到价再看"}


# ---------- 纪律永远第一 ----------

def test_出场线已破压过一切():
    r = _run(exit_line={"triggered": True, "stage_cn": "止盈线", "line": 12.3,
                        "action": "清仓"},
             urgency={"level": "triggered", "side_cn": "买"},
             trend=_UT, signal={"signal": "buy"})
    assert r["level"] == pb.EXIT
    assert r["price"] == 12.3
    assert "出场纪律优先" in r["why"]


def test_生命线破位单独说():
    r = _run(exit_line={"triggered": True, "stage": "fatal", "stage_cn": "生命线",
                        "line": 9.9, "action": "无条件清仓"})
    assert "生命线破位" in r["headline"]


# ---------- 这一层的核心: 打架要盖过「逼近」 ----------

def test_打架时不显示还差多少到买点():
    """**这是本层最值钱的一条。** 判定分歧时报「还差 1.2%」等于在催人下手。"""
    r = _run(trend=_UT, signal={"signal": "sell"}, urgency=_NEAR_BUY)
    assert r["level"] == pb.CONFLICT, "分歧被「逼近」盖住了"
    assert "1.2%" not in r["why"], "分歧档里不该再报距离 —— 那是在催人下手"
    assert "等它们对齐" in r["why"]


@pytest.mark.parametrize("trend,sig,keyword", [
    (_UT, "sell", "AI 说卖出"),
    (_DT, "buy", "AI 说买入"),
])
def test_趋势与AI相反算打架(trend, sig, keyword):
    r = _run(trend=trend, signal={"signal": sig})
    assert r["level"] == pb.CONFLICT and keyword in r["conflicts"][0]


def test_趋势往上而位置已经偏卖算打架():
    """[R214] 这条测试**自己就是 bug 的藏身处**, 值得留个记号。

    它原来传的是 `verdict={"side": "sell", ...}` —— 一个 `keltner.verdict()`
    **永远不会返回**的形状。真实的 verdict 里 `side` 只有 "high"/"low"(贴的是
    上轨还是下轨), 偏买偏卖叫 `tone`。测试自己捏了个对得上的假数据, 于是
    规则② 在测试里天天绿, 在线上一次都没跑过。

    现在按真函数的输出取, 并且用 `keltner.verdict` 真算一遍(见
    test_playbook_combo_matrix.py 的全组合穷举)。
    """
    r = _run(trend=_UT, verdict={"side": "high", "tone": "sell", "title": "该止盈了"})
    assert r["level"] == pb.CONFLICT
    assert "该止盈了" in r["conflicts"][0]


def test_假verdict形状不该再骗过测试():
    """把上一条的教训钉住: `side` 里不会出现 buy/sell, 拿它比就是恒假。"""
    from app.indicators import keltner as k
    r = _run(trend=_UT, verdict={"side": "sell", "title": "该止盈了"})
    assert r["level"] != pb.CONFLICT, "side 不该再被当成偏买偏卖来读"
    assert k.SIDE_HIGH == "high" and k.SIDE_LOW == "low"


def test_走过头了而AI还在喊买算打架():
    r = _run(phase={"code": "overextended", "cn": "走得过头了"},
             signal={"signal": "buy"})
    assert r["level"] == pb.CONFLICT


def test_持有且趋势没坏但已走过头_加减仓理由同时成立():
    r = _run(position={"held": True}, trend=_UT,
             phase={"code": "overextended", "cn": "走得过头了"})
    assert r["level"] == pb.CONFLICT
    assert any("同时成立" in c for c in r["conflicts"])


# ---------- 不滥报 ----------

@pytest.mark.parametrize("sig", ["watch", "hold", None])
def test_观望与持有不算矛盾(sig):
    """把不表态的也算成打架, 一半的票都会亮 —— 这一档就废了。"""
    r = _run(trend=_UT, signal=None if sig is None else {"signal": sig})
    assert r["conflicts"] == []
    assert r["level"] != pb.CONFLICT


def test_通道无结论不算矛盾():
    r = _run(trend=_UT, verdict=None)
    assert r["conflicts"] == []


def test_趋势读不到时一条都不报():
    """半边数据推不出"相反", 硬报就是编。"""
    r = _run(trend=None, signal={"signal": "sell"})
    assert r["conflicts"] == []


# ---------- 档位顺序 ----------

def test_已触发排在打架之前():
    r = _run(urgency={"level": "triggered", "side_cn": "卖", "what": "破位",
                      "action": "减"},
             trend=_UT, signal={"signal": "sell"})
    assert r["level"] == pb.ACT
    # 但分歧照旧带出来 —— 只是不当标题
    assert r["conflicts"], "已触发时也要把分歧作为附注带出去"


def test_不打架时逼近正常显示距离():
    r = _run(urgency=_NEAR_BUY, trend=_UT)
    assert r["level"] == pb.WATCH and "1.2%" in r["why"]


def test_持有且后劲不足给退出提示():
    r = _run(position={"held": True},
             phase={"code": "stalling", "cn": "后劲不足", "why": "劲在往回收",
                    "watch": "该想什么情况下走"})
    assert r["level"] == pb.SHAPE and "退出" in r["headline"]


def test_空仓遇到主升浪才提示看一眼():
    held = _run(position={"held": True},
                event={"code": "main_advance", "cn": "主升浪特征", "why": "五条全中"})
    flat = _run(position={"held": False},
                event={"code": "main_advance", "cn": "主升浪特征", "why": "五条全中"})
    assert flat["level"] == pb.SHAPE and "看一眼" in flat["headline"]
    assert held["level"] == pb.IDLE, "已经持有了就不必再喊「值得看」"


def test_什么都没有就是没事():
    r = _run()
    assert r["level"] == pb.IDLE and r["order"] == max(pb.ORDER.values())


# ---------- 边界 ----------

def test_全空不崩且字段齐全():
    r = _run()
    for k in ("level", "label", "order", "tone", "headline", "why", "price", "conflicts"):
        assert k in r, k


def test_不碰数据源():
    """原料全是别的层算好的 —— 加一次取数就会让决策台变慢。"""
    import inspect
    for fn in (pb.playbook, pb._conflicts, pb.playbook_many):
        src = inspect.getsource(fn)
        for bad in ("repo", "get_daily", "pl.", "requests", "await "):
            assert bad not in src, f"{fn.__name__} 不该碰 {bad}"


def test_文案里不许有markdown粗体():
    """后端文案在前端按纯文本渲染, `**` 会原样显示成星号(R175/R188 的老坑)。"""
    rows = [_run(), _run(trend=_UT, signal={"signal": "sell"}),
            _run(urgency=_NEAR_BUY), _run(exit_line={"triggered": True, "line": 1.0})]
    for r in rows:
        assert "**" not in r["headline"] and "**" not in r["why"]
