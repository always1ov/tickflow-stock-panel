"""[fork 增强] R59 AI 操盘手 —— 撮合规矩与两条隔离。

这个功能的目的不是"让 AI 帮我赚钱", 而是拿它当**这套系统的体检**: 一个模型
只拿本系统给出的信息, 长期能不能跑出正收益。所以下面守的每一条, 守的都是
"这个成绩到底能不能拿来判断系统好不好":

  · 撮合放宽任何一条(一手、T+1、手续费), 跑出来的收益都不能信;
  · 操作员之间只要漏一点信息, 比的就不再是"同一份信息谁用得更好";
  · 上下文里混进系统外的东西, 结论就跟这套系统没关系了。
"""
from __future__ import annotations

import polars as pl
import pytest

from app.services import paper_trader as pt
from app.services import paper_trader_run as run


@pytest.fixture(autouse=True)
def store(tmp_path, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    return tmp_path


def _bk(cash: float = 100_000.0, **kw) -> dict:
    """一本账(见 paper_trader.book())—— 撮合与净值全部按账本算。"""
    b = pt.new_book(cash)
    b.update(kw)
    return b


def _t(cash: float = 100_000.0, **kw) -> dict:
    """一个操作员: 两本独立的账。kw 里的 positions/orders 落到自选那本。"""
    t = {"id": "t1", "name": "m", "profile_id": "p", "initial_capital": cash,
         "books": {sc: pt.new_book(cash) for sc in pt.SCOPES},
         "schedule": {"enabled": False, "hour": 15, "minute": 30}}
    t["books"][pt.SCOPE_WATCHLIST].update(kw)
    return t


# ---------- 撮合规矩 ----------

def test_buy_rounds_down_to_whole_lots():
    """A 股一手 100 股。允许零股会让回测式的成绩虚高一点点, 而且是做不到的。"""
    t = _bk()
    e = pt.apply_order(t, action="buy", symbol="600000.SH", shares=250,
                       price=10.0, trade_date="2026-08-20")
    assert e["shares"] == 200
    assert t["positions"]["600000.SH"]["shares"] == 200


def test_an_order_below_one_lot_is_rejected_but_still_logged():
    """拒单也要留痕 —— "AI 想买但买不成"和"AI 没想买"是两件事,
    只记成交的话复盘时看到的是一段安静的空窗。"""
    t = _bk()
    e = pt.apply_order(t, action="buy", symbol="600000.SH", shares=50,
                       price=10.0, trade_date="2026-08-20")
    assert e["rejected"] and e["shares"] == 0
    assert len(t["orders"]) == 1, "被拒的这一笔必须进历史"


def test_buying_more_than_the_cash_allows_is_rejected():
    t = _bk(cash=1000.0)
    e = pt.apply_order(t, action="buy", symbol="600000.SH", shares=1000,
                       price=10.0, trade_date="2026-08-20")
    assert e["rejected"] == "现金不够"
    assert t["cash"] == 1000.0, "拒单不能动到现金"


def test_costs_and_slippage_come_out_of_the_cash():
    """手续费和滑点不算的话, 成绩里有一块是凭空来的。"""
    t = _bk(cash=100_000.0)
    pt.apply_order(t, action="buy", symbol="600000.SH", shares=100,
                   price=10.0, trade_date="2026-08-20")
    # 买价被滑点抬高, 再加佣金 —— 花掉的一定多于 1000
    assert t["cash"] < 99_000.0


def test_slippage_hurts_on_both_sides():
    """买贵一点、卖便宜一点。两边都按有利方向算等于凭空多赚。"""
    assert pt._fill_price(10.0, "buy") > 10.0
    assert pt._fill_price(10.0, "sell") < 10.0


def test_t_plus_one_blocks_selling_what_was_bought_today():
    """放宽这条模型会学会做 T, 而那在 A 股做不到。"""
    t = _bk()
    pt.apply_order(t, action="buy", symbol="600000.SH", shares=100,
                   price=10.0, trade_date="2026-08-20")
    e = pt.apply_order(t, action="sell", symbol="600000.SH", shares=100,
                       price=11.0, trade_date="2026-08-20")
    assert "T+1" in (e.get("rejected") or "")
    assert t["positions"]["600000.SH"]["shares"] == 100


def test_selling_the_next_day_works():
    t = _bk()
    pt.apply_order(t, action="buy", symbol="600000.SH", shares=100,
                   price=10.0, trade_date="2026-08-20")
    cash_after_buy = t["cash"]
    e = pt.apply_order(t, action="sell", symbol="600000.SH", shares=100,
                       price=12.0, trade_date="2026-08-21")
    assert not e.get("rejected") and e["shares"] == 100
    assert t["cash"] > cash_after_buy
    assert "600000.SH" not in t["positions"], "卖光了就不该留一条 0 股的持仓"


def test_adding_to_a_position_resets_the_t_plus_one_clock():
    """加仓那部分当天同样不能卖 —— 不刷新的话可以靠"昨天买过一手"绕开 T+1。"""
    t = _bk()
    pt.apply_order(t, action="buy", symbol="600000.SH", shares=100,
                   price=10.0, trade_date="2026-08-20")
    pt.apply_order(t, action="buy", symbol="600000.SH", shares=100,
                   price=11.0, trade_date="2026-08-21")
    e = pt.apply_order(t, action="sell", symbol="600000.SH", shares=200,
                       price=12.0, trade_date="2026-08-21")
    assert "T+1" in (e.get("rejected") or "")


def test_average_cost_is_recomputed_on_add():
    t = _bk()
    pt.apply_order(t, action="buy", symbol="600000.SH", shares=100,
                   price=10.0, trade_date="2026-08-20")
    pt.apply_order(t, action="buy", symbol="600000.SH", shares=100,
                   price=20.0, trade_date="2026-08-21")
    cost = t["positions"]["600000.SH"]["cost"]
    assert 14.9 < cost < 15.2, cost


def test_selling_what_you_do_not_hold_is_rejected():
    t = _bk()
    e = pt.apply_order(t, action="sell", symbol="600000.SH", shares=100,
                       price=10.0, trade_date="2026-08-20")
    assert e["rejected"] == "没有这只票的持仓"


def test_an_order_without_a_price_is_rejected_not_filled_at_zero():
    """取不到价就该拒 —— 按 0 成交会凭空造出一笔天量盈利。"""
    t = _bk()
    e = pt.apply_order(t, action="buy", symbol="XXXXX", shares=100,
                       price=0.0, trade_date="2026-08-20")
    assert e["rejected"] == "没有可用价格"


# ---------- 净值 ----------

def test_nav_is_cash_plus_market_value():
    t = _bk(cash=50_000.0, positions={"600000.SH": {"shares": 100, "cost": 10.0,
                                                   "opened_on": "2026-08-20"}})
    assert pt.nav(t, {"600000.SH": 12.0}) == 51_200.0


def test_marking_the_same_day_twice_updates_instead_of_appending():
    """一天两条会把净值曲线画花。"""
    t = _bk()
    pt.mark_nav(t, {}, "2026-08-20")
    pt.mark_nav(t, {}, "2026-08-20")
    assert len(t["nav_history"]) == 1


# ---------- 解析模型输出 ----------

def test_orders_are_parsed_out_of_a_fenced_json_block():
    """模型经常在 JSON 前后写一段话或用 ``` 包起来 —— 因为格式没对上丢掉
    一整天的决策, 会让长期观察出现莫名其妙的空窗。"""
    text = '今天我打算这样做:\n```json\n{"note":"轻仓试探","orders":[{"action":"buy","symbol":"600000.SH","shares":100,"reason":"到位了"}]}\n```\n以上。'
    orders, note = pt.parse_orders(text)
    assert note == "轻仓试探"
    assert orders == [{"action": "buy", "symbol": "600000.SH", "shares": 100, "reason": "到位了"}]


def test_chinese_action_words_are_understood():
    orders, _ = pt.parse_orders('{"orders":[{"action":"买入","symbol":"600000.sh","shares":200}]}')
    assert orders[0]["action"] == "buy" and orders[0]["symbol"] == "600000.SH"


def test_hold_entries_are_not_orders():
    orders, _ = pt.parse_orders('{"orders":[{"action":"hold","symbol":"600000.SH","shares":100}]}')
    assert orders == []


def test_unparseable_output_becomes_no_trades_not_a_guess():
    """猜错一笔单子比空一天糟得多。"""
    orders, note = pt.parse_orders("今天大盘不好, 我先观望。")
    assert orders == []
    assert "观望" in note, "原文要留住, 不然复盘时不知道它当时在想什么"


def test_empty_output_is_handled():
    assert pt.parse_orders("") == ([], "")


# ---------- 账本 ----------

def test_traders_are_persisted_and_listed_in_creation_order():
    a = pt.create(name="model-a", profile_id="p1")
    b = pt.create(name="model-b", profile_id="p2")
    assert [t["name"] for t in pt.list_traders()] == ["model-a", "model-b"]
    assert pt.book(pt.get(a["id"]), pt.SCOPE_MARKET)["cash"] == pt.DEFAULT_CAPITAL
    assert pt.get(b["id"]) is not None


def test_reset_puts_a_trader_back_to_the_starting_line():
    """改了系统就想再看一轮 —— 删了重建要把名字/模型/资金重填一遍。"""
    t = pt.create(name="m", profile_id="p", capital=50_000.0)
    pt.apply_order(pt.book(t, pt.SCOPE_WATCHLIST), action="buy", symbol="600000.SH",
                   shares=100, price=10.0, trade_date="2026-08-20")
    pt.save(t)
    back = pt.book(pt.reset(t["id"]), pt.SCOPE_WATCHLIST)
    assert back["cash"] == 50_000.0 and back["positions"] == {} and back["orders"] == []


def test_delete_removes_only_that_trader():
    a = pt.create(name="a", profile_id="p")
    b = pt.create(name="b", profile_id="p")
    assert pt.delete(a["id"]) is True
    assert [t["id"] for t in pt.list_traders()] == [b["id"]]


def test_there_is_a_cap_on_how_many_traders():
    for i in range(pt.MAX_TRADERS):
        pt.create(name=f"m{i}", profile_id="p")
    with pytest.raises(ValueError, match="最多"):
        pt.create(name="one-too-many", profile_id="p")


# ---------- 隔离: 这是整个功能的前提 ----------

class _Repo:
    """只给最基本的价格与一个空的 enriched 快照。"""

    @staticmethod
    def get_enriched_latest():
        return pl.DataFrame([{"symbol": "600000.SH", "close": 10.0}]), "2026-08-20"


@pytest.fixture
def quiet_overview(monkeypatch):
    """把今日总览换成一份固定的假数据 —— 这些测试要验的是隔离, 不是总览。"""
    monkeypatch.setattr(run, "_overview", lambda repo: {
        "as_of": "2026-08-20",
        "weather": {"posture": "谨慎", "posture_reason": "量能一般", "bull": 3, "bear": 5},
        "opportunities": [{"name": "浦发银行", "symbol": "600000.SH", "score": 80,
                           "text": "转多第 1 天", "why": "放量突破"}],
        "actions": [],
    })


def test_a_traders_context_never_mentions_anyone_else(quiet_overview):
    """整个功能的前提: 比的是"同一份信息谁用得更好"。漏一点别人的东西,
    比的就不再是这个了。"""
    mine = _t(positions={"600000.SH": {"shares": 100, "cost": 9.0, "opened_on": "2026-08-19"}})
    mine["id"], mine["name"] = "mine", "model-a"
    other = pt.create(name="model-b", profile_id="p2")
    pt.apply_order(pt.book(other, pt.SCOPE_WATCHLIST), action="buy", symbol="000858.SZ",
                   shares=100, price=50.0, trade_date="2026-08-19", reason="别人的独门理由")
    pt.save(other)

    ctx = run.build_context(_Repo(), mine, pt.SCOPE_WATCHLIST)
    for leak in ("000858", "model-b", "别人的独门理由", other["id"]):
        assert leak not in ctx, f"上下文里漏了别人的信息: {leak}"


def test_the_context_carries_this_traders_own_account(quiet_overview):
    mine = _t(positions={"600000.SH": {"shares": 100, "cost": 9.0, "opened_on": "2026-08-19"}})
    pt.book(mine, pt.SCOPE_WATCHLIST)["cash"] = 12_345.0
    ctx = run.build_context(_Repo(), mine, pt.SCOPE_WATCHLIST)
    assert "12,345" in ctx and "600000.SH" in ctx


def test_the_context_only_contains_material_from_this_system(quiet_overview):
    """来源要写在脸上 —— 复盘时能对上是哪个模块给的, 才谈得上"改进系统"。"""
    ctx = run.build_context(_Repo(), _t(), pt.SCOPE_WATCHLIST)
    assert "来自 今日总览" in ctx
    assert "全部来自本系统" in ctx


def test_the_boundary_is_about_outside_information_not_about_seeing_less():
    """[R65] 界限是**外部信息**, 不是"少给它看"。

    第一版把这两件事混成了一件, 结果模型只拿到一小段摘要 —— 那考的就不是
    "这套系统的信息够不够用"了, 而是"一段摘要够不够用"。禁的是新闻/研报/
    行情网站; 系统自己算出来的东西一样不该藏。
    """
    for p in (run.SYSTEM_PROMPT, run.LOOK_PROMPT):
        assert "没有联网能力" in p
        assert "只看得到自己这本账" in p
        # 明确写出"系统里的东西都可以用" —— 只写禁令的话模型会保守到不敢用
        assert "都可以用" in p
    assert "T+1" in run.SYSTEM_PROMPT


def test_the_look_round_offers_the_deep_dive():
    assert "细看" in run.LOOK_PROMPT and str(run.MAX_DEEP_DIVE) in run.LOOK_PROMPT


def test_an_empty_watchlist_still_produces_a_usable_context(monkeypatch):
    """没候选的那天也得能跑 —— 报错的话长期曲线会断一天。"""
    monkeypatch.setattr(run, "_overview", lambda repo: {"as_of": "2026-08-20"})
    ctx = run.build_context(_Repo(), _t(), pt.SCOPE_WATCHLIST)
    assert "今天没有达到门槛的候选" in ctx


# ---------- [R61] 两本账: 全市场 vs 我的自选 ----------
#
# 这不是"两个功能", 而是这套系统最想问的那个问题的对照组: **我这份自选到底
# 有没有价值**。同一个模型、同一天、同一套判定口径, 一边只能从我圈的票里选,
# 一边可以从全市场选 —— 两条净值曲线的差就是我选股这件事的价值。
# 所以两本账只要有一处串了, 这个对照就废了。

def test_a_new_trader_starts_with_two_independent_books():
    t = pt.create(name="m", profile_id="p", capital=50_000.0)
    for sc in pt.SCOPES:
        assert pt.book(t, sc)["cash"] == 50_000.0, "两本各自一份初始资金"


def test_trading_in_one_book_never_touches_the_other():
    """共用现金或共用持仓, 对照就没有意义了。"""
    t = pt.create(name="m", profile_id="p")
    pt.apply_order(pt.book(t, pt.SCOPE_MARKET), action="buy", symbol="600000.SH",
                   shares=100, price=10.0, trade_date="2026-08-20")
    pt.save(t)
    back = pt.get(t["id"])
    assert pt.book(back, pt.SCOPE_MARKET)["positions"], "全市场那本该有持仓"
    assert pt.book(back, pt.SCOPE_WATCHLIST)["positions"] == {}, "自选那本不该被动到"
    assert pt.book(back, pt.SCOPE_WATCHLIST)["cash"] == pt.DEFAULT_CAPITAL


def test_resetting_one_book_leaves_the_other_running():
    t = pt.create(name="m", profile_id="p")
    for sc in pt.SCOPES:
        pt.apply_order(pt.book(t, sc), action="buy", symbol="600000.SH", shares=100,
                       price=10.0, trade_date="2026-08-20")
    pt.save(t)
    back = pt.reset(t["id"], pt.SCOPE_MARKET)
    assert pt.book(back, pt.SCOPE_MARKET)["orders"] == []
    assert pt.book(back, pt.SCOPE_WATCHLIST)["orders"], "只重置一本, 另一本要留着"


def test_an_old_single_book_trader_migrates_into_the_watchlist_book():
    """老数据那版的上下文本来就是自选口径 —— 记到全市场那本会把成绩
    安到错误的对照组上。"""
    legacy = {"id": "old", "name": "m", "profile_id": "p", "initial_capital": 100_000.0,
              "cash": 90_000.0,
              "positions": {"600000.SH": {"shares": 100, "cost": 10.0, "opened_on": "2026-08-19"}},
              "orders": [{"date": "2026-08-19", "action": "buy", "symbol": "600000.SH"}],
              "nav_history": [{"date": "2026-08-19", "nav": 100_500.0}]}
    wl = pt.book(legacy, pt.SCOPE_WATCHLIST)
    assert wl["cash"] == 90_000.0 and wl["positions"] and wl["orders"]
    assert pt.book(legacy, pt.SCOPE_MARKET)["cash"] == 100_000.0, "全市场那本从头开始"
    assert "cash" not in legacy, "迁移完不该再留一份平铺的旧字段"


def test_an_unknown_scope_is_rejected():
    with pytest.raises(ValueError, match="未知分组"):
        pt.book(_t(), "somewhere_else")


def test_the_market_book_is_told_it_may_only_buy_from_the_market_list(quiet_overview):
    ctx = run.build_context(_Repo(), _t(), pt.SCOPE_MARKET)
    assert "全市场" in ctx and "全市场候选" in ctx
    assert "值得关注" not in ctx, "自选那份清单不该出现在全市场这本账里"


def test_the_watchlist_book_never_sees_the_market_screen(quiet_overview):
    ctx = run.build_context(_Repo(), _t(), pt.SCOPE_WATCHLIST)
    assert "值得关注" in ctx
    assert "全市场候选" not in ctx


def test_my_holdings_risk_alerts_stay_out_of_the_market_book(monkeypatch):
    """「需要行动」讲的是我自己自选持仓的风险 —— 漏给全市场那本, 等于让
    对照组看到了我的持仓。"""
    monkeypatch.setattr(run, "_overview", lambda repo: {
        "as_of": "2026-08-20",
        "actions": [{"severity": "high", "symbol": "000858.SZ", "name": "五粮液",
                     "text": "跌破生命线"}],
    })
    assert "000858" not in run.build_context(_Repo(), _t(), pt.SCOPE_MARKET)
    assert "000858" in run.build_context(_Repo(), _t(), pt.SCOPE_WATCHLIST)


# ---------- [R61] 生命线: 唯一允许用实时价的地方 ----------

class _LifeRepo(_Repo):
    """给 20 根收盘价, 均线正好 10.0。"""

    @staticmethod
    def get_daily_batch(symbols, start, end, columns=None):
        rows = []
        for s in symbols:
            for i in range(20):
                rows.append({"symbol": s, "date": f"2026-08-{i + 1:02d}", "close": 10.0})
        return pl.DataFrame(rows)


def _held(price_now: float) -> dict:
    t = _t()
    pt.book(t, pt.SCOPE_WATCHLIST)["positions"] = {
        "600000.SH": {"shares": 100, "cost": 9.0, "opened_on": "2026-08-01"}}
    del price_now
    return t


def test_breaking_the_lifeline_force_sells_without_asking_the_ai(quiet_overview):
    """生命线是硬纪律, 不是建议 —— 让模型有机会"再看看"就等于把纪律变成建议。"""
    t = _held(9.0)
    forced = run.check_lifelines(_LifeRepo(), t, pt.SCOPE_WATCHLIST,
                                 live={"600000.SH": {"close": 9.0}}, trade_date="2026-08-20")
    assert len(forced) == 1 and forced[0]["action"] == "sell"
    assert forced[0]["lifeline"] is True and forced[0]["intraday"] is True
    assert pt.book(t, pt.SCOPE_WATCHLIST)["positions"] == {}


def test_a_holding_above_the_lifeline_is_left_alone(quiet_overview):
    t = _held(11.0)
    forced = run.check_lifelines(_LifeRepo(), t, pt.SCOPE_WATCHLIST,
                                 live={"600000.SH": {"close": 11.0}}, trade_date="2026-08-20")
    assert forced == []
    assert pt.book(t, pt.SCOPE_WATCHLIST)["positions"]


def test_the_lifeline_itself_is_always_a_closing_price_average(quiet_overview):
    """触发可以看实时, 但生命线本身拿实时价算的话, 这条线自己就会跟着盘中抖。"""
    import inspect
    src = inspect.getsource(run._ma20_map)
    assert "get_daily_batch" in src and "live" not in src


def test_without_live_quotes_it_falls_back_to_the_close(quiet_overview):
    """收盘后跑定时任务走的就是这条路。"""
    t = _held(9.0)      # _Repo 的收盘价是 10.0, 不低于均线 10.0
    assert run.check_lifelines(_LifeRepo(), t, pt.SCOPE_WATCHLIST,
                               trade_date="2026-08-20") == []


def test_a_symbol_without_enough_history_has_no_lifeline(quiet_overview):
    """不足 20 根就没有生命线 —— 不拿 12 根算个假的出来去强平。"""
    class _Short(_Repo):
        @staticmethod
        def get_daily_batch(symbols, start, end, columns=None):
            return pl.DataFrame([{"symbol": s, "date": "2026-08-01", "close": 10.0}
                                 for s in symbols])

    t = _held(1.0)
    assert run.check_lifelines(_Short(), t, pt.SCOPE_WATCHLIST,
                               live={"600000.SH": {"close": 1.0}},
                               trade_date="2026-08-20") == []


# ---------- [R61] 定时 ----------

def test_a_new_trader_has_a_schedule_that_is_off_by_default():
    """默认不自己跑 —— 一个会自动调用付费 API 的东西不该开箱就开着。"""
    t = pt.create(name="m", profile_id="p")
    assert t["schedule"] == {"enabled": False, "hour": 15, "minute": 30}


def test_the_default_time_is_after_the_close():
    """收盘价出来了才有得算; 默认给个盘中时间等于默认跑一次没有意义的决策。"""
    t = pt.create(name="m", profile_id="p")
    assert (t["schedule"]["hour"], t["schedule"]["minute"]) >= (15, 0)


# ---------- [R61] 定时装卸 ----------

class _FakeScheduler:
    def __init__(self):
        self.jobs: dict[str, dict] = {}

    def add_job(self, fn, *, trigger, id, **kw):
        self.jobs[id] = {"fn": fn, "trigger": trigger, **kw}

    def get_jobs(self):
        return [type("J", (), {"id": k})() for k in list(self.jobs)]

    def remove_job(self, job_id):
        self.jobs.pop(job_id, None)


def test_only_enabled_schedules_get_installed():
    from app.services import paper_trader_schedule as ps

    a = pt.create(name="on", profile_id="p")
    pt.create(name="off", profile_id="p")
    a["schedule"] = {"enabled": True, "hour": 15, "minute": 30}
    pt.save(a)

    sched = _FakeScheduler()
    assert ps.install(sched, repo=None) == 1
    assert list(sched.jobs) == [f"{ps.JOB_PREFIX}{a['id']}"]


def test_turning_a_schedule_off_actually_removes_the_job():
    """只管添加的话, 关了定时它还在照跑 —— 而那意味着继续烧 AI 额度。"""
    from app.services import paper_trader_schedule as ps

    t = pt.create(name="m", profile_id="p")
    t["schedule"] = {"enabled": True, "hour": 15, "minute": 30}
    pt.save(t)
    sched = _FakeScheduler()
    ps.install(sched, repo=None)
    assert sched.jobs

    t = pt.get(t["id"])
    t["schedule"]["enabled"] = False
    pt.save(t)
    assert ps.install(sched, repo=None) == 0
    assert sched.jobs == {}, "关掉之后任务必须真的摘下来"


def test_a_deleted_trader_leaves_no_orphan_job():
    from app.services import paper_trader_schedule as ps

    t = pt.create(name="m", profile_id="p")
    t["schedule"] = {"enabled": True, "hour": 15, "minute": 30}
    pt.save(t)
    sched = _FakeScheduler()
    ps.install(sched, repo=None)
    pt.delete(t["id"])
    ps.install(sched, repo=None)
    assert sched.jobs == {}


def test_installing_does_not_touch_other_peoples_jobs():
    """调度器上还挂着盘后管道等任务, 重装操盘手定时不能把它们扫掉。"""
    from app.services import paper_trader_schedule as ps

    sched = _FakeScheduler()
    sched.jobs["post_market_pipeline"] = {"fn": None, "trigger": None}
    ps.install(sched, repo=None)
    assert "post_market_pipeline" in sched.jobs


def test_the_scheduled_run_does_lifelines_before_asking_the_ai():
    """清仓会腾出现金。反过来的话, 模型是拿着一笔本该已经卖掉的持仓在做判断,
    那天的决定就建立在一个错的账面上。"""
    import inspect

    from app.services import paper_trader_schedule as ps

    src = inspect.getsource(ps.run_trader_once)
    assert src.index("check_lifelines") < src.index("run_once")


# ---------- [R63] 持仓只数上限 ----------
#
# 上限存在的理由不是"防止乱买", 而是**让成绩可比**: 一个能同时拿 40 只的账户
# 跑出来的曲线, 本质上是在拿分散度换波动, 和一个只拿 5 只的账户不是同一回事。

def test_a_new_position_beyond_the_cap_is_rejected():
    bk = _bk(cash=1_000_000.0)
    for i in range(3):
        pt.apply_order(bk, action="buy", symbol=f"60000{i}.SH", shares=100,
                       price=10.0, trade_date="2026-08-20", max_positions=3)
    e = pt.apply_order(bk, action="buy", symbol="600009.SH", shares=100,
                       price=10.0, trade_date="2026-08-20", max_positions=3)
    assert "上限 3" in (e.get("rejected") or "")
    assert len(bk["positions"]) == 3


def test_adding_to_an_existing_position_is_not_capped():
    """挡加仓等于逼它去开一只新的 —— 那正好和"控制分散度"反着来。"""
    bk = _bk(cash=1_000_000.0)
    pt.apply_order(bk, action="buy", symbol="600000.SH", shares=100,
                   price=10.0, trade_date="2026-08-20", max_positions=1)
    e = pt.apply_order(bk, action="buy", symbol="600000.SH", shares=100,
                       price=10.0, trade_date="2026-08-21", max_positions=1)
    assert not e.get("rejected")
    assert bk["positions"]["600000.SH"]["shares"] == 200


def test_selling_frees_a_slot():
    bk = _bk(cash=1_000_000.0)
    pt.apply_order(bk, action="buy", symbol="600000.SH", shares=100,
                   price=10.0, trade_date="2026-08-20", max_positions=1)
    pt.apply_order(bk, action="sell", symbol="600000.SH", shares=100,
                   price=10.0, trade_date="2026-08-21", max_positions=1)
    e = pt.apply_order(bk, action="buy", symbol="600001.SH", shares=100,
                       price=10.0, trade_date="2026-08-21", max_positions=1)
    assert not e.get("rejected")


def test_no_cap_given_means_no_limit():
    """撮合本身不该自带一个隐形上限 —— 上限是操作员的设置, 由调用方传下来。"""
    bk = _bk(cash=1_000_000.0)
    for i in range(6):
        pt.apply_order(bk, action="buy", symbol=f"60000{i}.SH", shares=100,
                       price=10.0, trade_date="2026-08-20")
    assert len(bk["positions"]) == 6


@pytest.mark.parametrize("raw,want", [
    (0, 1), (-5, 1),                       # 0 只等于这本账不能买任何东西
    (999, pt.MAX_POSITIONS_CAP),
    ("abc", pt.DEFAULT_MAX_POSITIONS), (None, pt.DEFAULT_MAX_POSITIONS),
])
def test_the_cap_is_clamped_to_something_sane(raw, want):
    assert pt.clamp_max_positions(raw) == want


def test_the_cap_is_written_into_the_context(quiet_overview):
    """不写给模型看的话, 它会开一堆买单、大半被拒, 那一天的决策就废了一半。"""
    t = _t()
    t["max_positions"] = 4
    ctx = run.build_context(_Repo(), t, pt.SCOPE_WATCHLIST)
    assert "最多持有 4 只" in ctx


# ---------- [R63] 两本账各自的本金 ----------

def test_each_book_carries_its_own_capital():
    t = pt.create(name="m", profile_id="p", capital=200_000.0)
    for sc in pt.SCOPES:
        assert pt.book(t, sc)["initial_capital"] == 200_000.0


def test_changing_one_books_capital_leaves_the_other_alone():
    t = pt.create(name="m", profile_id="p", capital=100_000.0)
    t["books"][pt.SCOPE_MARKET] = pt.new_book(500_000.0)
    pt.save(t)
    back = pt.get(t["id"])
    assert pt.book(back, pt.SCOPE_MARKET)["initial_capital"] == 500_000.0
    assert pt.book(back, pt.SCOPE_WATCHLIST)["initial_capital"] == 100_000.0


def test_resetting_keeps_the_capital_i_configured():
    """重置只是回到起跑线 —— 我改过的本金不该被一次重置抹回默认值。"""
    t = pt.create(name="m", profile_id="p", capital=100_000.0)
    t["books"][pt.SCOPE_MARKET] = pt.new_book(500_000.0)
    pt.apply_order(pt.book(t, pt.SCOPE_MARKET), action="buy", symbol="600000.SH",
                   shares=100, price=10.0, trade_date="2026-08-20")
    pt.save(t)
    back = pt.reset(t["id"])
    assert pt.book(back, pt.SCOPE_MARKET)["initial_capital"] == 500_000.0
    assert pt.book(back, pt.SCOPE_MARKET)["cash"] == 500_000.0
    assert pt.book(back, pt.SCOPE_MARKET)["orders"] == []


def test_an_old_book_without_its_own_capital_inherits_the_traders():
    """老账本没有这个字段, 补上之后行为要和以前一模一样。"""
    legacy = {"id": "old", "name": "m", "profile_id": "p", "initial_capital": 80_000.0,
              "books": {pt.SCOPE_WATCHLIST: {"cash": 80_000.0, "positions": {},
                                             "orders": [], "nav_history": []}}}
    assert pt.book(legacy, pt.SCOPE_WATCHLIST)["initial_capital"] == 80_000.0
    assert pt.book(legacy, pt.SCOPE_MARKET)["initial_capital"] == 80_000.0


def test_the_context_shows_this_books_own_capital(quiet_overview):
    t = _t()
    t["books"][pt.SCOPE_WATCHLIST]["initial_capital"] = 333_000.0
    assert "333,000" in run.build_context(_Repo(), t, pt.SCOPE_WATCHLIST)


# ---------- [R65] 细看: 系统里的东西全都能用 ----------
#
# 第一版把"不能上网"错做成了"只能看一小段摘要"。界限本来是: 禁的是**外部信息**,
# 系统自己算出来的东西一样不该藏 —— 否则考的就不是"这套系统够不够用"了。

def test_focus_picks_are_limited_to_what_this_book_may_touch():
    """模型凭记忆报一只不在候选里的票, 给它明细就等于放它出了这本账的选股
    范围, 而两本账能对照的前提就是各自只在自己那个池子里选。"""
    allowed = {"600000.SH", "000001.SZ"}
    got = run.parse_focus(
        '{"focus": ["600000.SH", "999999.SZ", "000001.sz"], "why": "看看"}', allowed)
    assert got == ["600000.SH", "000001.SZ"], "范围外的要丢掉, 大小写要归一"


def test_focus_is_capped():
    allowed = {f"60000{i}.SH" for i in range(9)}
    picks = ",".join(f'"60000{i}.SH"' for i in range(9))
    text = f'{{"focus": [{picks}]}}'
    assert len(run.parse_focus(text, allowed)) == run.MAX_DEEP_DIVE


def test_an_unparseable_look_reply_just_means_no_deep_dive():
    """看盘轮没读懂不该让这一天报废 —— 退回只看摘要下单。"""
    assert run.parse_focus("我先看看吧", {"600000.SH"}) == []
    assert run.parse_focus("", {"600000.SH"}) == []


def test_the_allowed_set_is_candidates_plus_own_holdings(quiet_overview):
    """已持仓的也得能细看 —— 不然它没法判断该不该卖。"""
    t = _t(positions={"000858.SZ": {"shares": 100, "cost": 9.0, "opened_on": "2026-08-19"}})
    allowed = run._allowed_symbols(_Repo(), t, pt.SCOPE_WATCHLIST)
    assert "600000.SH" in allowed, "今日总览里的候选"
    assert "000858.SZ" in allowed, "自己的持仓"


def test_the_deep_dive_is_assembled_from_local_modules_only():
    """每一项都得是本地算出来或本地存着的 —— 这一段是"系统给的信息"的主体,
    混进任何外部来源, 整个体检的结论就跟这套系统没关系了。"""
    import inspect
    src = inspect.getsource(run.symbol_detail)
    for local in ("livermore_service", "keltner_service", "compute_levels",
                  "_kline_story", "_recent_report"):
        assert local in src
    for outside in ("http", "requests", "urlopen", "fetch"):
        assert outside not in src.lower()


def test_the_kline_story_marks_what_a_person_reads_off_a_chart(quiet_overview):
    """模型读不了图片, 但"哪天涨停、收在均线哪一侧、这段区间多宽"正是人看图
    时真正在读的东西 —— 这就是"看图"的文字版。"""
    import inspect
    src = inspect.getsource(run._kline_story)
    for marker in ("涨停", "跌停", "炸板", "20日线", "区间"):
        assert marker in src
