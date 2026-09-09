"""[fork 增强] 今日总览机会区: 买入机会的把握打分与筛选。

核心约定: 买入机会先打分再显示, 信号越"陈旧"(错过入场窗口)分数越低;
卖出/风险提醒走行动区, 不经过这里的筛选。
"""
from app.api.today import _OPP_MAX_SHOW, _OPP_MIN_HIST_PCT, rank_opportunities


def _trend(signal, duration, close=10.0):
    return {
        "state": "UT", "state_cn": "上涨趋势", "side": "多头",
        "duration": duration, "close": close, "as_of": "2026-08-14",
        "signal": signal, "signal_desc": f"突破上关键点 {close}",
    }


def test_fresh_signal_outranks_stale_one():
    """同为转多: 第 1 天把握分必须高于第 3 天, 第 3 天又高于第 5 天。"""
    names = {"000001.SZ": "平安银行", "000002.SZ": "万科A", "000003.SZ": "国农科技"}
    trends = {
        "000001.SZ": _trend("转多", 1),
        "000002.SZ": _trend("转多", 3),
        "000003.SZ": _trend("转多", 5),
    }
    shown, _ = rank_opportunities(trends, {}, names)
    scores = {o["symbol"]: o["score"] for o in shown}
    assert scores["000001.SZ"] > scores["000002.SZ"]
    assert shown[0]["symbol"] == "000001.SZ"
    assert "入场窗口最佳" in shown[0]["why"]
    # [R134] 新鲜度是趋势维度里权重最大的一项, 它必须能自己拉开差距
    assert shown[0]["factors"]["fresh"] > shown[1]["factors"]["fresh"]
    # 第 5 天已过入场窗口, 分数低于第 3 天(可能已被滤掉)
    assert scores.get("000003.SZ", 0) < scores["000002.SZ"]


def test_stale_weak_signal_is_below_the_bar_but_still_shown():
    """[R201] 第 5 天的回升信号把握不足 —— **仍然要报"被滤掉 1 只"**,
    但页面不再空着。

    用户: 「筛选标准不能过严导致今日总览页面无任何个股显示」。旧行为是
    直接 `shown == []`, 那正是空页。现在门槛的判定一个字没变(它依旧没过),
    只是保底把它摆出来并打上 `below_bar` —— 界面据此说明白"这只没到你的
    门槛"。**判定与展示分开**, 两件事都不失真。

    [R220] 门槛的单位换成历史分位之后, 这条测试改走 `filter_opportunities`:
    分位来自台账, 而测试环境的台账是空的, 走 `rank_opportunities` 造不出
    非 None 的分位(那时门槛按设计整个失效, 见下面那条测试)。
    """
    from app.api.today import filter_opportunities
    rows = [{"symbol": "000002.SZ", "name": "万科A", "score": 55, "why": [],
             "partial": False, "board": "深主板", "hist_pct": 12.0}]
    shown, filtered = filter_opportunities(rows, min_hist_pct=50, max_show=50)
    assert filtered == 1, "「被滤掉」说的是没过门槛的条数, 与保底展示无关"
    assert len(shown) == 1 and shown[0]["below_bar"] is True


def test_ai_signal_no_longer_moves_the_score():
    """[R134] AI 置信度退出评分, 只作注记。

    它是模型对自己输出的自评, 不可回测, 而且会过时(用户明确提过"别搞过时信息")。
    v1 里 AI 看空扣 40 分, 效果等于把票藏起来 —— 藏起来用户就不知道有过这个冲突,
    更谈不上自己定夺。现在改成: 分数不动, 但矛盾要**显眼地**摆出来。
    """
    names = {"000001.SZ": "平安银行", "000002.SZ": "万科A"}
    trends = {"000001.SZ": _trend("转多", 2), "000002.SZ": _trend("转多", 2)}
    signals = {
        "000001.SZ": {"signal": "buy", "confidence": 90},
        "000002.SZ": {"signal": "sell", "confidence": 80},
    }
    shown, _ = rank_opportunities(trends, signals, names)
    by = {o["symbol"]: o for o in shown}
    assert set(by) == {"000001.SZ", "000002.SZ"}, "看空的票不再被悄悄藏起来"
    assert by["000001.SZ"]["score"] == by["000002.SZ"]["score"]
    bear_note = {n["key"]: n for n in by["000002.SZ"]["notes"]}["ai"]
    assert bear_note["tone"] == "bad" and "矛盾" in bear_note["text"]
    assert "AI" not in "".join(by["000001.SZ"]["why"]), "注记不许混进评分理由"


def test_high_confidence_cannot_rescue_stale_signal():
    """关键约定: 信号拖了 5 天, 即使 AI 置信度 95 也不该压过刚转强的票。"""
    names = {"stale": "陈年信号", "fresh": "刚转强"}
    trends = {"stale": _trend("转多", 5), "fresh": _trend("转多", 1)}
    signals = {"stale": {"signal": "buy", "confidence": 95}}
    shown, _ = rank_opportunities(trends, signals, names)
    assert shown[0]["symbol"] == "fresh"


def test_near_breakout_distance_no_longer_scores_but_is_still_exposed():
    """[R134] 距触发价退出评分 —— 它与通道位置指向同一件事(离上方阻力多远),
    两个一起放是把同一份信息计价两次。改成结构化字段摆在列上给人看。
    """
    names = {"near": "贴价", "far": "还差些"}
    signals = {
        "near": {"signal": "buy", "confidence": 70, "close": 100.0,
                 "watch_points": [{"direction": "up", "price": 100.3, "action": "突破关注买入"}]},
        "far": {"signal": "buy", "confidence": 70, "close": 100.0,
                "watch_points": [{"direction": "up", "price": 101.9, "action": "突破关注买入"}]},
    }
    shown, _ = rank_opportunities({}, signals, names, min_hist_pct=0)
    by = {o["symbol"]: o for o in shown}
    assert by["near"]["score"] == by["far"]["score"]
    assert by["near"]["gap_pct"] == 0.3 and by["far"]["gap_pct"] == 1.9
    assert by["near"]["fresh_from"] == "near_breakout"


def test_show_cap_and_filtered_count():
    """机会再多也只显示前 N 条, 其余计入被滤掉的数量。

    这里刻意用 min_hist_pct=0 把门槛这一层摘掉 —— 要测的是**截断**, 不是门槛。
    (原来这两件事挤在一个断言里, [R201] 给数据稀薄的候选加了置信折扣之后,
    这批只有六态没有别的原料的合成候选不再自动过 60 分, 断言就同时测了两件
    事而失败。拆开之后各测各的, 都更稳。)
    """
    names = {f"S{i:03d}": f"票{i}" for i in range(20)}
    trends = {s: _trend("转多", 1) for s in names}
    shown, filtered = rank_opportunities(trends, {}, names, min_hist_pct=0)
    assert len(shown) == _OPP_MAX_SHOW
    assert filtered == 0, "min_hist_pct=0 时没有谁是被门槛滤掉的"


def _ranked(n=20, hist_pct=10.0):
    """[R220] 直接造排序后的行 —— 门槛现在按 `hist_pct` 判, 而那个值来自台账,
    测试环境里台账是空的, 走 rank_opportunities 造不出非 None 的分位。"""
    return [{"symbol": f"S{i:03d}", "name": f"票{i}", "score": 90 - i,
             "why": [], "partial": False, "board": "沪主板",
             "hist_pct": hist_pct} for i in range(n)]


def test_floor_guarantees_the_page_is_never_empty():
    """[R201] 保底: 一只都没过门槛时也要摆出前几只, 并标 below_bar。"""
    from app.api.today import FLOOR_ROWS, filter_opportunities
    shown, filtered = filter_opportunities(_ranked(20, hist_pct=10.0),
                                           min_hist_pct=90, max_show=50)
    assert filtered == 20, "门槛的判定不受保底影响"
    assert len(shown) == FLOOR_ROWS
    assert all(o["below_bar"] for o in shown)
    # 保底取的是**分最高的那几只**, 不是随便几只
    assert [o["symbol"] for o in shown] == ["S000", "S001", "S002"]


def test_台账没攒够时门槛整个失效而不是静默挡光():
    """[R220] **这一条是这个旋钮的安全绳。**

    分位来自台账。台账还没攒够(`score_distribution` 返回 None)时每行的
    `hist_pct` 都是 None —— 那时候门槛必须**谁也不挡**, 而不是把 None 当 0
    然后把整页挡光。静默失效正是这一轮反复栽跟头的那类问题, 界面另有一句话
    说明"这个门槛现在不起作用"。
    """
    from app.api.today import filter_opportunities
    rows = [{**r, "hist_pct": None} for r in _ranked(8)]
    shown, filtered = filter_opportunities(rows, min_hist_pct=90, max_show=50)
    assert filtered == 0, "没有分位可用时不该有人被判成「没过门槛」"
    assert len(shown) == 8
    assert not any(o["below_bar"] for o in shown)


def test_分位门槛每一格都真的在挡人():
    """换掉绝对分就是为了这个 —— 拖到 30 就该挡掉分位低于 30 的那些。"""
    from app.api.today import filter_opportunities
    rows = [{**r, "hist_pct": float(i * 10)} for i, r in enumerate(_ranked(10))]
    for bar, want_pass in ((0, 10), (30, 7), (60, 4), (90, 1)):
        shown, filtered = filter_opportunities(rows, min_hist_pct=bar, max_show=50)
        assert filtered == 10 - want_pass, (bar, filtered)


def test_floor_does_not_kick_in_when_enough_passed():
    names = {f"S{i:03d}": f"票{i}" for i in range(20)}
    trends = {s: _trend("转多", 1) for s in names}
    shown, _ = rank_opportunities(trends, {}, names, min_hist_pct=0)
    assert not any(o["below_bar"] for o in shown), "够格的够多时不该有 below_bar"


def test_scores_are_clamped_to_0_100():
    names = {"a": "甲", "b": "乙"}
    trends = {"a": _trend("转多", 1), "b": _trend("回升", 9)}
    signals = {"a": {"signal": "buy", "confidence": 100},
               "b": {"signal": "sell", "confidence": 100}}
    shown, _ = rank_opportunities(trends, signals, names)
    assert all(0 <= o["score"] <= 100 for o in shown)


# ================================================================
# [R210 加, R230 删] 候选路 C 的那一组测试(选票 / 只认多头 / 不跟 AB 抢额度 /
# 缺读数不崩 / 全是安静自选也不空页)在这里删掉了。
#
# 路 C 是 R201 跟着量化通道延申一起加的, 判据就是 `keltner_geometry.phase()`,
# 随评分系统回退到 R134 一起撤掉了。功能没了, 断言也一起走 —— 按 R198 的规矩,
# 留着测一个不存在的能力就是下一个「看起来像在用」的死代码。
#
# **那次修的 bug 本身没有作废**: R201 的路 C 一次都没跑过, 因为选票和建候选
# 各写各的、而其中一处永远走不到。那条教训搬进了 docs/scoring-and-rules.md,
# 下次再加候选路时要先问「它到底选不选得出票来」。

# ---------------------------------------------- [R210] 空页要说清空在哪一步


def test_空页原因分得清三种情形():
    from app.api.today import empty_reason
    gates_blocked = {"candidates": 12, "passed": 0, "blocked_total": 12,
                     "blocked": {"trend_side": 9, "lifeline": 5}}
    # ① 候选池本身是空的 —— 市场状态
    why = empty_reason([], [], {"candidates": 0, "blocked": {}}, None)
    assert "三条候选路" in why
    # ② 有候选但全被门槛挡下 —— 门槛在干活
    why = empty_reason([], [], gates_blocked, None)
    assert "门槛" in why and "12 只" in why and "逆势" in why
    # ③ 板块过滤滤没了 —— **这是用户自己的筛选, 一键就能撤**
    why = empty_reason([{"x": 1}] * 7, [], {"candidates": 7, "blocked": {}}, ["北交所"])
    assert "北交所" in why and "去掉板块过滤还有 7 只" in why


def test_不空的时候不给原因():
    from app.api.today import empty_reason
    assert empty_reason([1], [1], {"candidates": 1, "blocked": {}}, None) is None


def test_有候选过了门槛却空了要明说是bug():
    """保底本该兜住这种情形。真出现了就是 bug, 不能装作是市场没机会。"""
    from app.api.today import empty_reason
    why = empty_reason([{"x": 1}], [], {"candidates": 1, "blocked": {}}, None)
    assert "bug" in why


# [R226 加, R230 删] 「挤在一起那一档的三种全都要能进路 C」那条网格测试删掉了
# —— 路 C 已随评分系统回退到 R134 一起撤掉, 没有 `_COILING_PHASES` 可核对了。
#
# 那次量出来的结论仍然记在 docs/rule-layers.md: R215 把「挤在一起」拆成
# 横盘中 / 刚启动 / 看不出 三档时漏掉了第三档, 取材面一次缩掉 44%
# (系统性网格 3087 格: 2940 → 1660)。教训是「拆档位时要回头看谁在按档位取材」,
# 与路 C 存不存在无关, 所以留在文档里。
#
# 下面这条留着: 它测的是 `keltner_geometry.phase()` 本身 —— 那一层没有被删,
# 只是从"进分/取材"降成了界面上的注记。

def test_看不出这一档确实是酝酿而不是别的():
    """[R230] 原话是「把为什么它该进路 C 钉住」。路 C 没了, 但这一档的**含义**
    没变, 而且它现在照样显示在决策台「走势」列里: 三条线还挤着、重合已松开、
    但没在加速 —— 这是比「刚启动」更早一步的酝酿, 不是"没结论"。
    读的人会照着它做判断, 所以这条继续守着。"""
    from app.indicators import keltner_geometry as kg
    geo = {"spread": 0.7, "accel": {"a1": 0.0}, "compress": 0.6,
           "torn": False, "nested": True}
    ph = kg.phase(geo)
    assert ph["code"] == kg.PH_UNCLEAR
    assert "分是分开了" in ph["watch"] or "没有力气" in ph["watch"]
