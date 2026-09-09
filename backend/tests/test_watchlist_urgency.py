"""[fork 增强] R178 决策台「该动了」判定。

这个数决定用户打开决策台先看到谁, 所以要守的是**优先级不能错位**:
纪律(出场线)永远压过形态(翻转价), 形态永远压过位置(到轨)。
以及一条老规矩: **AI 不参与判定** —— 它可以在旁边解释, 不许决定顺序。
"""
import pytest

from app.services import watchlist_urgency as u


def _exit(*, triggered=False, distance_pct=None, stage_cn="止损线"):
    return {"triggered": triggered, "distance_pct": distance_pct,
            "stage_cn": stage_cn, "action": "清仓"}


def _trend(*, dn=None, up=None, duration=5, state_cn="上涨趋势", frm=None):
    return {"flip_down_distance_pct": dn, "flip_up_distance_pct": up,
            "duration": duration, "state_cn": state_cn, "entered_from_cn": frm}


def _bands(pos=None):
    return {"s": {"pos": pos, "pos_cn": "贴下轨"}} if pos else {}


# ---------- 优先级 ----------

def test_已触发压过一切():
    got = u.assess(position={"held": True},
                   trend=_trend(dn=-0.001, duration=1),   # 又逼近又刚翻转
                   exit_line=_exit(triggered=True), bands=_bands("below"))
    assert got["level"] == u.TRIGGERED, "破了出场线就是最急的, 别的都得让位"


def test_出场线逼近压过翻转价逼近():
    """纪律先于形态 —— 止损是必须执行的, 翻转只是可能发生的。"""
    got = u.assess(position={"held": True},
                   trend=_trend(dn=-0.001),               # 翻转价更近
                   exit_line=_exit(distance_pct=-0.014),  # 出场线稍远但仍在阈内
                   bands=None)
    assert got["level"] == u.NEAR
    assert "止损线" in got["reason"], f"该报出场线而不是翻转价: {got['reason']}"


def test_逼近压过刚翻转():
    got = u.assess(position=None, trend=_trend(up=0.005, duration=1),
                   exit_line=None, bands=None)
    assert got["level"] == u.NEAR


def test_刚翻转压过到轨():
    got = u.assess(position=None, trend=_trend(duration=1, frm="自然回撤"),
                   exit_line=None, bands=_bands("near_lower"))
    assert got["level"] == u.FLIP
    assert "自然回撤" in got["reason"]


def test_什么都没有就是无事():
    got = u.assess(position=None, trend=_trend(), exit_line=None, bands=_bands())
    assert got["level"] == u.IDLE
    assert got["distance"] is None


# ---------- 买点侧: 没持仓的票也要能进视野 ----------

def test_空仓票逼近转强价也算逼近():
    """这是补翻转价距离的全部意义 —— 没持仓的票原来一个紧迫度数字都没有。"""
    got = u.assess(position=None, trend=_trend(up=0.008), exit_line=None, bands=None)
    assert got["level"] == u.NEAR
    assert "转强" in got["reason"]


def test_持有的票优先看转弱价():
    got = u.assess(position={"held": True}, trend=_trend(dn=-0.015, up=0.018),
                   exit_line=None, bands=None)
    assert "转弱" in got["reason"], f"持有的票该先盯卖点: {got['reason']}"


def test_空仓的票优先看转强价():
    got = u.assess(position=None, trend=_trend(dn=-0.015, up=0.018),
                   exit_line=None, bands=None)
    assert "转强" in got["reason"], f"空仓的票该先盯买点: {got['reason']}"


def test_另一边近得多时事实压过偏好():
    """偏好只在两边差不多时才起作用 —— 不能因为"你持有"就无视一个近一倍的价位。"""
    got = u.assess(position={"held": True}, trend=_trend(dn=-0.019, up=0.002),
                   exit_line=None, bands=None)
    assert "转强" in got["reason"], f"转强价近了近十倍, 该报它: {got['reason']}"


# ---------- 口径一致性 ----------

def test_到轨口径与推送焦点名单同源():
    """CONTEXT.md 立的规矩: 决策台写"贴上轨"的那天, 推送门也必须认它是贴轨。
    两处各写一套阈值的话, 用户会看到"界面说贴轨了却没推送"。"""
    from app.services.focus_list import _BAND_POS
    for pos in _BAND_POS:
        got = u.assess(position=None, trend=_trend(), exit_line=None,
                       bands={"s": {"pos": pos, "pos_cn": "到轨"}})
        assert got["level"] == u.BAND, f"{pos} 在焦点名单里算贴轨, 这里也必须算"


def test_通道中部不算到轨():
    got = u.assess(position=None, trend=_trend(), exit_line=None,
                   bands={"s": {"pos": "middle", "pos_cn": "中部"}})
    assert got["level"] == u.IDLE


# ---------- 排序契约 ----------

def test_档位顺序从急到缓():
    assert (u.ORDER[u.TRIGGERED] < u.ORDER[u.NEAR] < u.ORDER[u.FLIP]
            < u.ORDER[u.BAND] < u.ORDER[u.IDLE])


def test_要动的不含无事档():
    assert u.IDLE not in u.ACTIONABLE
    assert u.ACTIONABLE == {u.TRIGGERED, u.NEAR, u.FLIP, u.BAND}


def test_同档内距离可比():
    """同样是 near, 离线 0.3% 的必须排在 1.4% 前面 —— 所以 distance 要有值。"""
    a = u.assess(position={"held": True}, trend=_trend(),
                 exit_line=_exit(distance_pct=-0.003), bands=None)
    b = u.assess(position={"held": True}, trend=_trend(),
                 exit_line=_exit(distance_pct=-0.014), bands=None)
    assert a["level"] == b["level"] == u.NEAR
    assert a["distance"] < b["distance"]


def test_距离取绝对值():
    """出场线在下方(负)、转强价在上方(正), 比"多远"时符号没有意义。"""
    got = u.assess(position={"held": True}, trend=_trend(),
                   exit_line=_exit(distance_pct=-0.008), bands=None)
    assert got["distance"] == 0.008


# ---------- 不许 AI 参与 ----------

def test_判定不接收AI信号():
    import inspect
    params = set(inspect.signature(u.assess).parameters)
    assert params == {"position", "trend", "exit_line", "bands"}, \
        "判定只吃规则层产出 —— AI 信号可以显示, 不许决定用户先看谁"


# ---------- 批量 ----------

def test_单只出错不连累整张表():
    got = u.assess_many(["A", "B"], positions={"A": {"held": True}},
                        trends={"A": "这不是字典"},      # A 会炸
                        exit_lines={}, keltner={"B": _bands("above")})
    assert got["A"]["level"] == u.IDLE, "坏的那只降级"
    assert got["B"]["level"] == u.BAND, "好的那只照常"


def test_批量覆盖所有传入的票():
    got = u.assess_many(["A", "B", "C"], positions={}, trends={},
                        exit_lines={}, keltner={})
    assert set(got) == {"A", "B", "C"}, "缺数据的票也要有档位, 不能从表里消失"


# ==================== [R193] 把话说清楚 ====================
#
# 用户: 「这一列要把话说清楚, 太简洁了, 这也不行, 会误人子弟」。
#
# 这一组守的是**这一列唯一一处真会害人的地方**: 同一个「逼近」既可能是
# "再跌一点就破止损, 准备卖", 也可能是"再涨一点就转强, 是个买点线索" ——
# 两个相反的动作, 原来长得一模一样。


def _u(**kw):
    base = dict(position=None, trend=None, exit_line=None, bands=None)
    base.update(kw)
    return u.assess(**base)


_HELD = {"held": True}
_FLAT = {"held": False}


def test_逼近止损和逼近转强必须分得出方向():
    """整组测试的理由。两条都是 near 档、距离也差不多, 但一个该卖一个该买。"""
    sell = _u(position=_HELD,
              exit_line={"triggered": False, "stage_cn": "止损线", "line": 386.5,
                         "action": "清仓", "distance_pct": -0.005})
    buy = _u(position=_FLAT,
             trend={"flip_up": 412.3, "flip_up_distance_pct": 0.005, "duration": 6})
    assert sell["level"] == buy["level"] == u.NEAR, "两条同档 —— 光看档位分不出来"
    assert sell["side"] == u.SIDE_SELL and buy["side"] == u.SIDE_BUY
    assert sell["side_cn"] != buy["side_cn"]


def test_已触发不再报一个假的零距离():
    """原来触发档的 distance 写死成 0.0, 显示出来是「已触发 0.0%」——
    读起来像"离触发还有 0%"(还没破), 意思正好反了。"""
    got = _u(position=_HELD,
             exit_line={"triggered": True, "stage_cn": "止损线", "line": 386.5,
                        "action": "清仓", "distance_pct": 0.012})
    assert got["distance"] == 0.012
    assert "已跌破" in got["what"]


def test_每一档都说清哪条线以及该干什么():
    cases = [
        _u(position=_HELD, exit_line={"triggered": True, "stage_cn": "止损线",
                                      "line": 386.5, "action": "清仓", "distance_pct": 0.01}),
        _u(position=_HELD, exit_line={"triggered": False, "stage_cn": "移动止盈线",
                                      "line": 402.0, "action": "减半仓", "distance_pct": -0.008}),
        _u(position=_FLAT, trend={"flip_up": 412.3, "flip_up_distance_pct": 0.005, "duration": 6}),
        _u(position=_HELD, trend={"flip_down": 370.0, "flip_down_distance_pct": -0.004, "duration": 9}),
        _u(trend={"duration": 1, "state_cn": "上涨趋势", "side": "多头"}),
        # [R212] 到轨这一档要给方向, 就得先知道趋势在哪一侧 —— 见下面那一组
        _u(bands={"s": {"pos": "near_upper", "pos_cn": "贴上轨"}},
           trend={"duration": 5, "state": "DT", "state_cn": "下跌趋势"}),
    ]
    for got in cases:
        assert got["what"], got
        assert got["action"], f"{got['level']} 没说该干什么: {got}"
        assert got["side"] in (u.SIDE_SELL, u.SIDE_BUY), got
        assert got["kind"] != "none"


def test_具体价位要出现在话里():
    """「离转强价还有 0.5%」不如「离转强价 412.30 还有 0.5%」—— 后者能直接挂单。"""
    got = _u(position=_FLAT, trend={"flip_up": 412.3, "flip_up_distance_pct": 0.005, "duration": 6})
    assert "412.30" in got["what"]
    got = _u(position=_HELD, exit_line={"triggered": False, "stage_cn": "止损线",
                                        "line": 386.5, "action": "清仓", "distance_pct": -0.01})
    assert "386.50" in got["what"]


def test_没有价位时也不崩只是少说一句():
    got = _u(position=_FLAT, trend={"flip_up_distance_pct": 0.005, "duration": 6})
    assert got["level"] == u.NEAR and "转强价" in got["what"]


def test_上轨和下轨的方向要看趋势在哪一侧():
    """[R212] 原来这条写的是「上轨恒为卖、下轨恒为买」—— **那正是用户报的那个
    矛盾的来源**: 一只正在上涨的票碰到上沿就被判成卖, 而它昨天刚因为"逼近转强价"
    被判成买。上下沿确实相反, 但相反的前提是**同一个趋势侧**。"""
    bull_up = _u(bands={"s": {"pos": "near_upper", "pos_cn": "贴上轨"}},
                 trend={"duration": 5, "state": "UT", "state_cn": "上涨趋势"})
    bull_dn = _u(bands={"s": {"pos": "near_lower", "pos_cn": "贴下轨"}},
                 trend={"duration": 5, "state": "UT", "state_cn": "上涨趋势"})
    assert bull_up["side"] != u.SIDE_SELL, "上涨趋势里到上沿不该叫卖"
    assert bull_dn["side"] == u.SIDE_BUY

    bear_up = _u(bands={"s": {"pos": "near_upper", "pos_cn": "贴上轨"}},
                 trend={"duration": 5, "state": "DT", "state_cn": "下跌趋势"})
    bear_dn = _u(bands={"s": {"pos": "near_lower", "pos_cn": "贴下轨"}},
                 trend={"duration": 5, "state": "DT", "state_cn": "下跌趋势"})
    assert bear_up["side"] == u.SIDE_SELL
    assert bear_dn["side"] != u.SIDE_BUY, "下跌趋势里到下沿不该叫买"


def test_转多第一天是买方向转空第一天是卖方向():
    bull = _u(trend={"duration": 1, "state_cn": "上涨趋势", "side": "多头"})
    bear = _u(trend={"duration": 1, "state_cn": "下跌趋势", "side": "空头"})
    assert bull["side"] == u.SIDE_BUY and bear["side"] == u.SIDE_SELL


def test_空仓票逼近转弱不算卖方向():
    """本来就没拿, 它转弱与你无关 —— 标成"该卖"是无中生有。"""
    got = _u(position=_FLAT, trend={"flip_down": 370.0, "flip_down_distance_pct": -0.004,
                                    "duration": 9})
    assert got["side"] == u.SIDE_INFO
    assert "空仓" in got["action"]


def test_无事那一档不指向任何一边():
    got = _u(trend={"duration": 5}, bands={"s": {"pos": "inside"}})
    assert got["level"] == u.IDLE
    assert got["side"] == u.SIDE_INFO and got["side_cn"] == ""
    assert got["action"] == "", "无事就是无事, 不该编一个动作出来"


def test_reason_仍然是完整一句供悬停与导出():
    got = _u(position=_HELD, exit_line={"triggered": False, "stage_cn": "止损线",
                                        "line": 386.5, "action": "清仓", "distance_pct": -0.01})
    assert got["what"] in got["reason"] and got["action"] in got["reason"]


def test_判定失败也带齐字段():
    """降级路径少给一个键, 前端就会在渲染时炸掉整张表。"""
    got = u.assess_many(["X"], positions={"X": object()}, trends={}, exit_lines={}, keltner={})["X"]
    for key in ("level", "label", "order", "distance", "kind", "side", "side_cn", "what", "action", "reason"):
        assert key in got, key


def test_文案里不许有markdown粗体():
    """后端文案在前端按纯文本渲染, `**` 会原样显示成星号。"""
    for got in (_u(position=_HELD, exit_line={"triggered": True, "stage_cn": "止损线",
                                              "line": 1.0, "action": "清仓", "distance_pct": 0.01}),
                _u(position=_FLAT, trend={"flip_up": 1.0, "flip_up_distance_pct": 0.005, "duration": 6}),
                _u(bands={"s": {"pos": "above", "pos_cn": "破上轨"}}, trend={"duration": 5})):
        assert "**" not in got["reason"], got


# ================================================================
# [R212] 到轨这一档必须看趋势方向
#
# 用户: 「有矛盾, 马上逼近上沿了又叫买, 到上沿了又叫卖, 很奇怪到底是买还是卖」。
#
# 原来这一档是无脑的 `上沿→卖 / 下沿→买`, **一眼都不看趋势**。于是同一只正在
# 上涨的票: 昨天离转强价 1.5% 报「逼近·买」, 今天站上去顺带碰到上沿, 立刻翻成
# 「到上沿·卖」—— 前后两天相反的动作, 而这两件事说的其实是**同一次突破**。
#
# 转强价(六态关键点)与短期通道上沿常常挨得很近: 站上去在六态那套里是"转强",
# 在通道那套里是"到顶"。**谁对取决于趋势在哪一侧**, 不取决于哪一档先命中。

def _band(pos, pos_cn):
    return {"s": {"pos": pos, "pos_cn": pos_cn}}


def _at(pos, pos_cn, state=None, cn=None):
    t = {"state": state, "state_cn": cn} if state else None
    return u.assess(position=None, trend=t, exit_line=None, bands=_band(pos, pos_cn))


def test_上涨趋势里到上沿不是卖出信号():
    """**这就是用户报的那个矛盾。** 沿着上沿走是趋势票的常态。"""
    got = _at("near_upper", "贴上轨", "UT", "上涨趋势")
    assert got["level"] == u.BAND
    assert got["side"] != u.SIDE_SELL, "上涨趋势里到上沿还在叫卖"
    assert "常态" in got["action"] and "止盈线" in got["action"]


def test_下跌趋势里到上沿才是卖():
    got = _at("near_upper", "贴上轨", "DT", "下跌趋势")
    assert got["side"] == u.SIDE_SELL
    assert "反弹" in got["action"]


def test_下跌趋势里到下沿不是买入信号():
    """往下走的时候下沿会跟着一路下移 —— 拿它抄底正是最容易亏的做法。"""
    got = _at("near_lower", "贴下轨", "DT", "下跌趋势")
    assert got["side"] != u.SIDE_BUY, "下跌趋势里到下沿还在叫买"
    assert "下移" in got["action"]


def test_上涨趋势里到下沿是买但要提醒别当破位():
    got = _at("near_lower", "贴下轨", "UT", "上涨趋势")
    assert got["side"] == u.SIDE_BUY
    assert "甩人" in got["action"]


@pytest.mark.parametrize("pos,pos_cn", [("near_upper", "贴上轨"), ("near_lower", "贴下轨")])
def test_趋势读不到时退回中性不替用户猜方向(pos, pos_cn):
    got = _at(pos, pos_cn)
    assert got["side"] == u.SIDE_INFO
    assert "自己看日 K" in got["action"]


def test_与几何层的事件判定同向():
    """同一件事两层不能给相反的说法 —— `keltner_geometry.event` 早就写对了
    (破上轨在 UT 里是趋势内加速、在空头侧才是反弹遇阻), 这一层现在跟上。"""
    from app.indicators import keltner_geometry as kg
    geo = {"spread": 2.0, "accel": {"a1": 0.1}, "compress": 0.1,
           "torn": False, "nested": False, "stack": kg.STACK_BULL,
           "d": {"s": 1.5, "m": 2.0, "l": 3.0}}
    ev = kg.event(state="UT", duration=5, geo=geo, run={"above_run": 3, "below_run": 0,
                                                        "compress_days": 0})
    assert ev["code"] in (kg.EV_TREND_ACCEL, kg.EV_MAIN_ADVANCE), ev
    # 几何层说"趋势内提速/主升浪", 该动了那一层就不能说"卖"
    assert _at("above", "破上轨", "UT", "上涨趋势")["side"] != u.SIDE_SELL
