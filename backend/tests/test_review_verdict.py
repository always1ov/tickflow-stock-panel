"""[fork 增强] R191 复盘「趋势状态」的判定层。

这一栏原来五块内容全是**测量**。判定层要守的是它存在的理由:

  1. 「多头侧灵、空头侧不灵」这种一半有用的情况, 在四个并排的均值里看不出来
     —— 必须把同侧的段合起来才显形。这是本层最值钱的两个结论(defense/offense)。
  2. 样本不够就不下结论 —— 1~2 段说"这只票上六态很灵"是在骗自己。
  3. 合侧要**按段数加权**: 4 段的一档和 7 段的一档不能一样重。
  4. 判定只用已经算好的段统计, 不新增取数。
"""
import pytest

from app.services import review_service as rv


def _oc(key, n, avg_fwd, win=0, avg_days=5.0):
    """造一条 _trend_outcomes 的行。scored 一律等于 n(都已兑现)。"""
    return {"key": key, "n": n, "scored": n, "avg_fwd": avg_fwd,
            "win": win, "avg_days": avg_days, "label": key}


# 多头 UT/NR/SR, 空头 DT/NREA/SREA
def _both_sides(bull_fwd, bear_fwd, bull_n=6, bear_n=6):
    return [_oc("UT", bull_n, bull_fwd), _oc("DT", bear_n, bear_fwd)]


# ---------- 本层存在的理由: 一半有用 ----------

def test_只有避险灵是能被认出来的():
    """截图里那只票就是这样: 空头侧 -7%, 多头侧 0% —— 四个并排的均值看不出
    这件事, 合侧之后一眼就有。这是整个判定层最值钱的一条。"""
    got = rv._side_edge([
        _oc("NREA", 8, -0.052), _oc("NR", 7, -0.045),
        _oc("DT", 5, -0.105), _oc("UT", 4, 0.079),
    ])
    assert got["level"] == "defense", got
    assert "离场信号" in got["text"] and "买点另找" in got["text"]
    # 多头侧被 7 段 -4.5% 压回了零附近 —— 只看「上涨趋势 +7.9%」会得出相反结论
    assert abs(got["bull"]["avg_fwd"]) < 0.01
    assert got["bear"]["avg_fwd"] < -0.05


def test_只有进攻灵():
    got = rv._side_edge(_both_sides(0.09, 0.005))
    assert got["level"] == "offense"
    assert "买点线索" in got["text"] and "别等它转空" in got["text"]


def test_两头都灵():
    got = rv._side_edge(_both_sides(0.09, -0.08))
    assert got["level"] == "both"


def test_分不开就直说别拿它当依据():
    got = rv._side_edge(_both_sides(0.005, -0.004))
    assert got["level"] == "flat"
    assert "说明不了" in got["text"]


def test_反着的也如实说():
    """多头侧比空头侧还差。样本这么小时多半是巧合, 但不能悄悄按 flat 处理。"""
    got = rv._side_edge(_both_sides(-0.08, 0.05))
    assert got["level"] == "inverted"
    assert got["spread"] < 0


# ---------- 样本纪律 ----------

@pytest.mark.parametrize("bull_n,bear_n", [(2, 6), (6, 2), (1, 1), (0, 5)])
def test_任一侧样本不够就不下结论(bull_n, bear_n):
    got = rv._side_edge(_both_sides(0.09, -0.08, bull_n=bull_n, bear_n=bear_n))
    assert got["level"] == "thin", got
    assert got["spread"] is None, "样本不够时不该给出分离度 —— 那个数会被当成结论"
    assert "不下结论" in got["text"]


def test_没有任何段也不崩():
    got = rv._side_edge([])
    assert got["level"] == "thin" and got["bull"]["episodes"] == 0


def test_未兑现的段不进平均():
    """scored=0 的段确实发生过(计次数), 但结果未知, 不能进均值。"""
    rows = [dict(_oc("UT", 5, None), scored=0), _oc("DT", 5, -0.08)]
    got = rv._side_edge(rows)
    assert got["bull"]["episodes"] == 0
    assert got["level"] == "thin"


def test_合侧按段数加权而不是简单平均():
    """4 段的一档和 7 段的一档一样重的话, 罕见状态会喧宾夺主。"""
    got = rv._side_edge([_oc("UT", 1, 0.30), _oc("NR", 9, -0.02),
                         _oc("DT", 5, -0.06)])
    # 简单平均是 (30-2)/2 = +14%; 加权是 (1×30 + 9×(-2))/10 = +1.2%
    assert got["bull"]["avg_fwd"] == pytest.approx(0.012, abs=1e-3)


# ---------- 门槛值本身 ----------

def test_门槛是常量不是散在代码里的魔数():
    assert rv.MIN_SIDE_EPISODES >= 3
    assert 0.01 <= rv.SIDE_EDGE <= 0.10


def test_刚好卡在门槛上算通过():
    got = rv._side_edge(_both_sides(rv.SIDE_EDGE, -rv.SIDE_EDGE))
    assert got["level"] == "both"


# ---------- 「现在」那一条 ----------

def _rows(state, day, close=100.0):
    return [{"date": "2026-09-09", "close": close,
             "trend": {"state": state, "state_cn": "上涨趋势", "side": "多头",
                       "day": day, "flip_down": 92.0, "flip_up": None}}]


def test_现在这一条把当前段与它自己的历史对上():
    got = rv._now(_rows("UT", 4), [_oc("UT", 6, 0.05, win=4, avg_days=9.0)])
    assert got["state"] == "UT" and got["day"] == 4
    assert got["avg_days"] == 9.0
    assert got["n"] == 6 and got["win"] == 4
    assert got["flip_down"] == 92.0, "复盘完总得知道盯哪个价"


@pytest.mark.parametrize("day,avg_days,phase", [
    (2, 10.0, "前段"), (7, 10.0, "中段"), (30, 10.0, "后段"),
])
def test_按平均时长给出前中后段(day, avg_days, phase):
    got = rv._now(_rows("UT", day), [_oc("UT", 6, 0.05, avg_days=avg_days)])
    assert got["phase"] == phase


def test_没有历史同类段时不假装有():
    got = rv._now(_rows("SR", 3), [_oc("UT", 6, 0.05)])
    assert got["n"] == 0 and got["avg_fwd"] is None and got["phase"] is None


def test_现在空输入不崩():
    assert rv._now([], []) is None
    assert rv._now([{"date": "d", "close": 1.0, "trend": None}], []) is None


# ---------- 封板率 ----------

@pytest.mark.parametrize("up,broken,keyword", [
    (9, 1, "封得住"), (6, 5, "一半上下"), (2, 9, "封不住板"),
])
def test_封板率给的是性格判断不是一个比率(up, broken, keyword):
    got = rv._seal(up, broken)
    assert keyword in got["text"]
    assert got["attempts"] == up + broken


def test_冲板次数太少就不给比率():
    """2 次里封住 1 次不能说明任何事 —— 给个 50% 反而像个结论。"""
    assert rv._seal(1, 1) is None
    assert rv._seal(0, 0) is None


# ---------- 边界 ----------

def test_判定层不碰数据源():
    """只用已经算好的段统计 —— 加一次取数就会让复盘弹窗变慢。"""
    import inspect
    for fn in (rv._side_edge, rv._side_stats, rv._now, rv._seal):
        src = inspect.getsource(fn)
        for bad in ("repo", "get_daily", "compute(", "pl."):
            assert bad not in src, f"{fn.__name__} 不该碰 {bad}"


def test_文案里不许有markdown粗体():
    """后端文案在前端按纯文本渲染, `**` 会原样显示成星号(R175/R188 的老坑)。"""
    texts = [rv._side_edge(_both_sides(b, r))["text"]
             for b, r in [(0.09, -0.08), (0.09, 0.0), (0.0, -0.08), (0.0, 0.0), (-0.08, 0.05)]]
    texts += [rv._seal(u, b)["text"] for u, b in [(9, 1), (6, 5), (2, 9)]]
    texts.append(rv._side_edge([])["text"])
    for t in texts:
        assert "**" not in t, t


# ---------- [R208] inverted 那一档的措辞 ----------

def test_说买的反而更差这一档不许把话说成跌():
    """判据是「多头侧均值 < 空头侧均值」—— **+1% 对 +3% 同样命中**。
    写成"反而跌"就是在没跌的时候说它跌了。

    这一档本来就常常是小样本下的巧合(正文里明说了), 措辞再说过头,
    用户真反着做就是被这个标签坑的。
    """
    got = rv._side_edge(_both_sides(0.01, 0.03))   # 两边都涨, 只是多头侧涨得少
    assert got["level"] == "inverted"
    assert got["label"] == "说买的反而更差"
    assert "跌" not in got["label"], "标签把话说过头了"
    assert "多半是巧合" in got["text"], "小样本的告诫不能丢"


def test_两层用的是同一个标签():
    """六态层与价位层问的是同一个问题, 标签不该有两套说法。"""
    a = rv._side_edge(_both_sides(-0.08, 0.05))["label"]
    from app.indicators.keltner import TONE_BUY, TONE_SELL
    # 价位层是按 tone 分侧的(不是按 key) —— 说便宜的那几档反而更差
    b = rv._verdict_edge([
        {"key": "low_short_only", "tone": TONE_BUY, "n": 6, "scored": 6,
         "avg_fwd": -0.08, "win": 1, "avg_days": 5.0, "label": "低吸候选"},
        {"key": "high_short_only", "tone": TONE_SELL, "n": 6, "scored": 6,
         "avg_fwd": 0.05, "win": 4, "avg_days": 5.0, "label": "短线冲高"},
    ])["label"]
    assert a == b == "说买的反而更差"
