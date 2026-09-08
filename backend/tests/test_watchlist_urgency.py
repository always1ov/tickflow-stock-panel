"""[fork 增强] R178 决策台「该动了」判定。

这个数决定用户打开决策台先看到谁, 所以要守的是**优先级不能错位**:
纪律(出场线)永远压过形态(翻转价), 形态永远压过位置(到轨)。
以及一条老规矩: **AI 不参与判定** —— 它可以在旁边解释, 不许决定顺序。
"""
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
