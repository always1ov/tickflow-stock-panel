"""[fork 增强] R189 趋势模板(Minervini 八条)。

守的是三件事:

  1. **判不出来 ≠ 没通过。** 历史不足时 `pass=None`, 不是 False。整个门槛层
     与打分层对"缺数据"的处理都是放行/缺席, 这里破一次例, 次新股就会被
     无声地判成"结构不行"。
  2. **周期是 50/150/200, 不是 20/60/120。** 引入外部标准的全部价值就在于
     它被公开检验过; 换成本地口径, 得到的只是个长得像的东西。
  3. **不返回分数。** 八条过几条是事实, 值多少分是 opportunity_score 的事。
"""
import pytest

from app.services import trend_template as tt


def _rising(n: int = 300, rate: float = 0.004, start: float = 10.0) -> list[float]:
    return [start * (1 + rate) ** i for i in range(n)]


def _falling(n: int = 300, rate: float = 0.004, start: float = 100.0) -> list[float]:
    return [start * (1 - rate) ** i for i in range(n)]


# ---------- 两个极端 ----------

def test_一路上涨的票八条全过():
    got = tt.assess(_rising(), rs_6m=0.25)
    assert got["known"] == 8 and got["complete"] is True
    assert got["passed"] == 8, [c for c in got["criteria"] if not c["pass"]]


def test_一路下跌的票一条都不过():
    got = tt.assess(_falling(), rs_6m=-0.25)
    assert got["known"] == 8
    assert got["passed"] == 0, [c["label"] for c in got["criteria"] if c["pass"]]


# ---------- 缺数据 ----------

def test_历史不足的条目是未知而不是未通过():
    """次新股只有 100 根 —— 判不了年线, 不等于它长期趋势向下。"""
    got = tt.assess(_rising(100), rs_6m=0.2)
    assert got["complete"] is False
    long_terms = [c for c in got["criteria"]
                  if c["code"] in ("above_mid_long", "mid_above_long", "long_rising",
                                   "ma_stacked", "off_low", "near_high")]
    assert all(c["pass"] is None for c in long_terms), long_terms
    assert all(c["pass"] is not False for c in got["criteria"]), "缺数据不许判成没通过"
    # 但短周期那两条是判得出来的 —— 能判的就要判
    assert got["known"] >= 2


def test_没有基准时RS那一条是未知():
    got = tt.assess(_rising(), rs_6m=None)
    rs = next(c for c in got["criteria"] if c["code"] == "rs_positive")
    assert rs["pass"] is None
    assert got["known"] == 7 and got["complete"] is False


def test_空输入不崩():
    got = tt.assess(None)
    assert got["passed"] == 0 and got["known"] == 0
    assert got["total"] == 8 and got["complete"] is False


def test_全是None的序列不崩():
    assert tt.assess([None, None, None])["known"] == 0


# ---------- 单条的口径 ----------

def test_均线周期是50_150_200不是本地的20_60_120():
    """换成本地口径就只是"一个长得像趋势模板的东西", 外部的检验记录一并作废。"""
    assert (tt.MA_SHORT, tt.MA_MID, tt.MA_LONG) == (50, 150, 200)
    labels = " ".join(c["label"] for c in tt.assess(_rising())["criteria"])
    assert "MA200" in labels and "MA150" in labels and "MA50" in labels


def test_52周高低点按收盘算不按盘中极值():
    """六态全线是收盘口径 —— 混入影线会让「距高点 25% 以内」在插针行情里跳。"""
    import inspect
    src = inspect.getsource(tt)
    for bad in ("high", "low_price", "amplitude"):
        assert f'"{bad}"' not in src, f"不该读盘中 {bad}"
    # 只吃一串收盘价, 连 df 都不认
    assert "close" not in inspect.signature(tt.assess).parameters


def test_刚从底部涨起来但离52周高点太远的过不了近高点那条():
    """从 100 跌到 30 再涨回 45 —— 高出低点 50% 过了, 但离高点还差一半。"""
    closes = _falling(200, 0.006, 100.0) + [30.0 * (1 + 0.01) ** i for i in range(60)]
    got = tt.assess(closes, rs_6m=0.4)
    off_low = next(c for c in got["criteria"] if c["code"] == "off_low")
    near_high = next(c for c in got["criteria"] if c["code"] == "near_high")
    assert off_low["pass"] is True
    assert near_high["pass"] is False, "离 52 周高点还远, 这一条就不该过"


def test_年线斜率看的是一个月前不是昨天():
    assert tt.SLOPE_LOOKBACK == 22
    got = tt.assess(_rising(), rs_6m=0.2)
    c = next(x for x in got["criteria"] if x["code"] == "long_rising")
    assert "22" in c["detail"]


# ---------- 输出契约 ----------

def test_不给分数():
    """给个分数就会有人直接把它加进把握分, 而"过 6 条值多少分"是打分层的事。"""
    got = tt.assess(_rising(), rs_6m=0.2)
    assert "score" not in got and "points" not in got


def test_每条都带一句能核对的detail():
    for c in tt.assess(_rising(), rs_6m=0.2)["criteria"]:
        assert c["detail"], c["label"]
        assert c["code"] and c["label"]


def test_八条就是八条():
    assert len(tt.assess(_rising())["criteria"]) == tt.TOTAL == 8


@pytest.mark.parametrize("closes,rs", [(_rising(), 0.2), (_rising(100), None),
                                       ([], None), (_falling(), -0.1)])
def test_summary总能说出一句人话(closes, rs):
    text = tt.summary(tt.assess(closes, rs))
    assert text and "趋势模板" in text


def test_不依赖任何AI():
    import inspect
    src = inspect.getsource(tt)
    for bad in ("ai_provider", "generate_ai_text", "news_desk"):
        assert bad not in src, f"这是规则层, 不许碰 {bad}"
