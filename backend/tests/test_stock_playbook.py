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
    # [R299] 那句道理从 `why` 挪到了 `note` —— **`why` 讲这只票, `note` 讲这套
    # 系统的道理**。它不随票变, 印在正文就是一屏重复几十遍(用户: 「没帮助的
    # 东西就不要显示了」)。守的规矩一个字没变: 那句话不许丢, 只是换了个字段。
    assert "出场纪律优先" in r["note"], "那条纪律的道理没了 —— 那是删信息, 不是精简"
    assert "出场纪律优先" not in r["why"], "又串回正文那一行了"


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
    # [R299] 同上: 道理进 `note`, 正文只留"哪两个判定在打架"
    assert "等它们对齐" in r["note"], "打架该怎么办的那句话没了"
    assert "等它们对齐" not in r["why"], "又串回正文那一行了"


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


def test_R299_没事那一档在正文里只剩两个字():
    """用户看着一只什么也没发生的票: 「排版不好看, 内容要言简意赅精辟」
    「没帮助的东西就不要显示了」。

    截图里那一格是三行, 第三行写着「五套判定都没有可说的 —— 今天不必看它」——
    **它把「没事」换个说法又讲了一遍**, 一个字的新信息都没有, 却是整格里最宽的
    一行, 于是一张 166 行的表里"没事"的那些行和"要动"的一样响。

    修法在**后端**而不是前端加一个 `level === 'idle'` 判断: 判据留一处
    (R286 立过), 前端只问"有没有内容", 没有就不渲染那一行。
    """
    r = _run()
    assert r["level"] == pb.IDLE
    assert r["headline"] == "没事"
    assert r["why"] == "", (
        f"「没事」那一档还在正文里说话: {r['why']!r} —— 它没有内容可说"
    )
    # 反面: 不是删掉, 是降级。要核对时还得看得见
    assert "今天不必看它" in r["note"], "那句话整个没了 —— 那是删信息, 不是精简"


def test_R299_有事的那些档正文照旧有话说():
    """反面配对: 别为了精简把**真正的读数**也一起吞了。

    `why` 空掉只该发生在「没事」那一档; 别的档位那一行是唯一能告诉你
    "凭什么落到这一档"的地方。
    """
    r = _run(position={"held": True},
             exit_line={"triggered": True, "line": 12.3, "stage": "fatal",
                        "stage_cn": "生命线", "action": "清仓"})
    assert r["level"] == pb.EXIT and r["why"], "出场档的正文那一行空了"


def test_R307_逼近与已触发那两档也把说教挪进悬停():
    """[R299 → R307] **同一个毛病的第三处。** 用户指着截图: 「排版还是非常有问题」——
    那一格的第三行是

        到上沿 19.23(趋势还在多头侧·上涨趋势) —— 沿着上沿走是趋势票的常态 ——
        不必因为「到高位了」就减。真要减看止盈线, 别拿到轨当卖出理由

    **74 个字**, 而后面 51 个字**不随票变**: 每一只落到「到上沿 + 多头侧」这一
    分支的票印的都是同一段。前 23 个字才是这只票的读数(带具体价与方向)。

    `watchlist_urgency` 本来就把两者分成 `what` / `action` 两个字段, 是
    `stock_playbook` 用 `f"{what} —— {action}"` 把它们又粘回去了。拆开即可。
    """
    r = _run(urgency={"level": "band", "label": "到上沿", "side_cn": "",
                      "what": "到上沿 19.23(趋势还在多头侧·上涨趋势)",
                      "action": "沿着上沿走是趋势票的常态 —— 不必因为「到高位了」就减。"
                                "真要减看止盈线, 别拿到轨当卖出理由"})
    assert r["level"] == pb.WATCH
    assert r["why"] == "到上沿 19.23(趋势还在多头侧·上涨趋势)", (
        f"正文那一行还拖着说教: {r['why']!r}"
    )
    assert "沿着上沿走是趋势票的常态" in r["note"], "那句道理没了 —— 那是删信息, 不是精简"
    assert len(r["why"]) < len(r["note"]), "场景没搭对: 说教该比读数长得多"


def test_R307_已触发那一档同样只留读数():
    """反面配对: 别只修「逼近」那一支 —— 「今天已触发」走的是同一个粘法。"""
    r = _run(exit_line={"triggered": False},
             urgency={"level": "triggered", "side_cn": "卖",
                      "what": "生命线 399.85 已跌破 3.6%",
                      "action": "按纪律清仓, 别等反弹"})
    assert r["level"] == pb.ACT
    assert r["why"] == "生命线 399.85 已跌破 3.6%", f"正文还拖着说教: {r['why']!r}"
    assert r["note"] == "按纪律清仓, 别等反弹"


def test_R307_形态那两档也一样():
    """「该想退出计划了」「酝酿中」原来是 `phase.why —— phase.watch` 粘起来的。
    `why` 是这一段的读数, `watch` 是该盯什么 —— 后者不随票变, 进悬停。"""
    ph = {"code": "coiling", "cn": "横盘中", "why": "三条线挤在一起, 方向还没选",
          "watch": "等方向选出来再动, 别猜"}
    r = _run(position={"held": False}, phase=ph)
    assert r["level"] == pb.SHAPE and r["headline"] == "酝酿中"
    assert r["why"] == "三条线挤在一起, 方向还没选", f"正文还拖着说教: {r['why']!r}"
    assert r["note"] == "等方向选出来再动, 别猜"

