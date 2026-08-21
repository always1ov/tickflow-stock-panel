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


def _t(cash: float = 100_000.0, **kw) -> dict:
    t = {"id": "t1", "name": "m", "profile_id": "p", "initial_capital": cash,
         "cash": cash, "positions": {}, "orders": [], "nav_history": []}
    t.update(kw)
    return t


# ---------- 撮合规矩 ----------

def test_buy_rounds_down_to_whole_lots():
    """A 股一手 100 股。允许零股会让回测式的成绩虚高一点点, 而且是做不到的。"""
    t = _t()
    e = pt.apply_order(t, action="buy", symbol="600000.SH", shares=250,
                       price=10.0, trade_date="2026-08-20")
    assert e["shares"] == 200
    assert t["positions"]["600000.SH"]["shares"] == 200


def test_an_order_below_one_lot_is_rejected_but_still_logged():
    """拒单也要留痕 —— "AI 想买但买不成"和"AI 没想买"是两件事,
    只记成交的话复盘时看到的是一段安静的空窗。"""
    t = _t()
    e = pt.apply_order(t, action="buy", symbol="600000.SH", shares=50,
                       price=10.0, trade_date="2026-08-20")
    assert e["rejected"] and e["shares"] == 0
    assert len(t["orders"]) == 1, "被拒的这一笔必须进历史"


def test_buying_more_than_the_cash_allows_is_rejected():
    t = _t(cash=1000.0)
    e = pt.apply_order(t, action="buy", symbol="600000.SH", shares=1000,
                       price=10.0, trade_date="2026-08-20")
    assert e["rejected"] == "现金不够"
    assert t["cash"] == 1000.0, "拒单不能动到现金"


def test_costs_and_slippage_come_out_of_the_cash():
    """手续费和滑点不算的话, 成绩里有一块是凭空来的。"""
    t = _t(cash=100_000.0)
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
    t = _t()
    pt.apply_order(t, action="buy", symbol="600000.SH", shares=100,
                   price=10.0, trade_date="2026-08-20")
    e = pt.apply_order(t, action="sell", symbol="600000.SH", shares=100,
                       price=11.0, trade_date="2026-08-20")
    assert "T+1" in (e.get("rejected") or "")
    assert t["positions"]["600000.SH"]["shares"] == 100


def test_selling_the_next_day_works():
    t = _t()
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
    t = _t()
    pt.apply_order(t, action="buy", symbol="600000.SH", shares=100,
                   price=10.0, trade_date="2026-08-20")
    pt.apply_order(t, action="buy", symbol="600000.SH", shares=100,
                   price=11.0, trade_date="2026-08-21")
    e = pt.apply_order(t, action="sell", symbol="600000.SH", shares=200,
                       price=12.0, trade_date="2026-08-21")
    assert "T+1" in (e.get("rejected") or "")


def test_average_cost_is_recomputed_on_add():
    t = _t()
    pt.apply_order(t, action="buy", symbol="600000.SH", shares=100,
                   price=10.0, trade_date="2026-08-20")
    pt.apply_order(t, action="buy", symbol="600000.SH", shares=100,
                   price=20.0, trade_date="2026-08-21")
    cost = t["positions"]["600000.SH"]["cost"]
    assert 14.9 < cost < 15.2, cost


def test_selling_what_you_do_not_hold_is_rejected():
    t = _t()
    e = pt.apply_order(t, action="sell", symbol="600000.SH", shares=100,
                       price=10.0, trade_date="2026-08-20")
    assert e["rejected"] == "没有这只票的持仓"


def test_an_order_without_a_price_is_rejected_not_filled_at_zero():
    """取不到价就该拒 —— 按 0 成交会凭空造出一笔天量盈利。"""
    t = _t()
    e = pt.apply_order(t, action="buy", symbol="XXXXX", shares=100,
                       price=0.0, trade_date="2026-08-20")
    assert e["rejected"] == "没有可用价格"


# ---------- 净值 ----------

def test_nav_is_cash_plus_market_value():
    t = _t(cash=50_000.0, positions={"600000.SH": {"shares": 100, "cost": 10.0,
                                                   "opened_on": "2026-08-20"}})
    assert pt.nav(t, {"600000.SH": 12.0}) == 51_200.0


def test_marking_the_same_day_twice_updates_instead_of_appending():
    """一天两条会把净值曲线画花。"""
    t = _t()
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
    assert pt.get(a["id"])["cash"] == pt.DEFAULT_CAPITAL
    assert pt.get(b["id"]) is not None


def test_reset_puts_a_trader_back_to_the_starting_line():
    """改了系统就想再看一轮 —— 删了重建要把名字/模型/资金重填一遍。"""
    t = pt.create(name="m", profile_id="p", capital=50_000.0)
    pt.apply_order(t, action="buy", symbol="600000.SH", shares=100,
                   price=10.0, trade_date="2026-08-20")
    pt.save(t)
    back = pt.reset(t["id"])
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
    pt.apply_order(other, action="buy", symbol="000858.SZ", shares=100,
                   price=50.0, trade_date="2026-08-19", reason="别人的独门理由")
    pt.save(other)

    ctx = run.build_context(_Repo(), mine)
    for leak in ("000858", "model-b", "别人的独门理由", other["id"]):
        assert leak not in ctx, f"上下文里漏了别人的信息: {leak}"


def test_the_context_carries_this_traders_own_account(quiet_overview):
    mine = _t(cash=12_345.0,
              positions={"600000.SH": {"shares": 100, "cost": 9.0, "opened_on": "2026-08-19"}})
    ctx = run.build_context(_Repo(), mine)
    assert "12,345" in ctx and "600000.SH" in ctx


def test_the_context_only_contains_material_from_this_system(quiet_overview):
    """来源要写在脸上 —— 复盘时能对上是哪个模块给的, 才谈得上"改进系统"。"""
    ctx = run.build_context(_Repo(), _t())
    assert "来自 今日总览" in ctx
    assert "全部来自本系统" in ctx


def test_the_prompt_forbids_going_outside_the_given_information():
    """结构上模型也没有联网的手(它只拿到一段文本, 没有工具),
    这条提示词是把同一件事说给它听, 两者一起才完整。"""
    assert "没有联网能力" in run.SYSTEM_PROMPT
    assert "只看得到自己的账户" in run.SYSTEM_PROMPT
    assert "T+1" in run.SYSTEM_PROMPT


def test_an_empty_watchlist_still_produces_a_usable_context(monkeypatch):
    """没候选的那天也得能跑 —— 报错的话长期曲线会断一天。"""
    monkeypatch.setattr(run, "_overview", lambda repo: {"as_of": "2026-08-20"})
    ctx = run.build_context(_Repo(), _t())
    assert "今天没有达到门槛的候选" in ctx
