"""[fork 增强] R54 回测 SSE 的 `done` 负载必须是合法 JSON。

实测踩到的: 跑完一次回测, 界面上只剩一句"结果解析失败", 跑了几分钟的结果全丢。

原因是 ``json.dumps`` 对 float 的 nan/inf 会写出裸 ``NaN`` / ``Infinity``——
那是 Python 的方言, 不是合法 JSON, 浏览器 ``JSON.parse`` 直接抛。而零波动的
区间(比如只成交了一两笔、或者取消得早)算出来的 sharpe/sortino 正好就是 nan。

优化器和 walk-forward 两路早就套了 ``_json_safe``, 单次回测那一路漏了。这里守的
就是"三路都得清洗"这件事本身 —— 漏掉任何一路, 表现都是同一句没有信息量的
"结果解析失败"。
"""
from __future__ import annotations

import json

import pytest

from app.api.backtest import _json_safe


def _reject(token: str):
    """模拟浏览器 JSON.parse 的严格口径: 见到 NaN/Infinity 就报错。"""
    raise ValueError(f"invalid JSON literal: {token}")


def _dumps(obj) -> str:
    """与 SSE 里那一行逐字同一套参数。"""
    return json.dumps(obj, ensure_ascii=False, default=str)


# ---------- 为什么需要清洗 ----------

def test_raw_dumps_of_nan_emits_a_bare_literal_no_browser_accepts():
    """这条不是测我们的代码, 是把"为什么要有 _json_safe"钉在测试里 ——
    否则下一个人看到这层包装会以为是多余的。

    注意 Python 自己的 json.loads **默认认** NaN/Infinity(它的非标准扩展),
    所以后端怎么自测都发现不了 —— 崩的是浏览器那边严格按 RFC 8259 的
    JSON.parse。这也正是这个 bug 一直活着的原因, 所以这里断言的是
    "输出里有裸字面量", 而不是"Python 解析不了"。
    """
    raw = _dumps({"sharpe": float("nan"), "sortino": float("inf")})
    assert "NaN" in raw and "Infinity" in raw
    # 严格模式(浏览器的口径)下才会拒
    with pytest.raises(ValueError):
        json.loads(raw, parse_constant=_reject)


# ---------- 清洗本身 ----------

@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_floats_become_null(bad):
    """置 None 而不是 0 —— "算不出来"和"正好是 0"在夏普上是两回事。"""
    assert _json_safe({"sharpe": bad}) == {"sharpe": None}


def test_finite_numbers_and_strings_pass_through_untouched():
    src = {"sharpe": 1.25, "n": 3, "name": "七上八下", "ok": True, "nothing": None}
    assert _json_safe(src) == src


def test_cleaning_reaches_into_nested_lists_and_dicts():
    """逐组/逐折的结果嵌套很深, 只洗顶层等于没洗。"""
    src = {"folds": [{"metrics": {"sortino": float("nan")}}, {"metrics": {"sortino": 2.0}}]}
    got = _json_safe(src)
    assert got["folds"][0]["metrics"]["sortino"] is None
    assert got["folds"][1]["metrics"]["sortino"] == 2.0
    json.loads(_dumps(got))    # 真的能被解析才算数


def test_a_realistic_result_with_nan_survives_the_round_trip():
    """零波动区间(只成交一两笔)算出的 nan 正是实测那次的情形。"""
    result = {
        "strategy_id": "pullback_ma20_bounce",
        "metrics": {"sharpe": float("nan"), "sortino": float("-inf"),
                    "total_return": 0.108, "max_drawdown": -0.306},
        "trades": [{"symbol": "000001.SZ", "pnl_pct": float("nan")}],
        "equity": [1.0, 1.0, 1.0],
    }
    back = json.loads(_dumps(_json_safe(result)))
    assert back["metrics"]["sharpe"] is None and back["metrics"]["sortino"] is None
    assert back["metrics"]["total_return"] == 0.108
    assert back["trades"][0]["pnl_pct"] is None


# ---------- 三路都要洗 ----------

def test_every_done_payload_goes_through_the_cleaner():
    """单次回测那一路就是这么漏掉的 —— 优化器和 WF 都洗了, 只有它没洗,
    而三路的失败表现一模一样, 没有测试的话下次还会漏。"""
    import inspect

    from app.api import backtest

    src = inspect.getsource(backtest)
    done_lines = [ln.strip() for ln in src.splitlines() if "event: done" in ln]
    assert len(done_lines) == 3, f"新增了 done 分支就要一起纳入本检查: {done_lines}"
    for ln in done_lines:
        assert "_json_safe" in ln or "payload" in ln, ln
    # payload 这个中间变量也必须是洗过的
    assert "payload = _json_safe(" in src


def test_cleaner_leaves_unknown_objects_to_default_str():
    """date / Decimal 之类交给 dumps 的 default=str, 清洗层不该自作主张改写它们。"""
    from datetime import date

    got = _json_safe({"as_of": date(2026, 8, 20)})
    assert got["as_of"] == date(2026, 8, 20)
    assert json.loads(_dumps(got))["as_of"] == "2026-08-20"
