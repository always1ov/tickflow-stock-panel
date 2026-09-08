"""[fork 增强] R195 三档 Keltner 的几何补充层。

**这一层只读不写。** 用户: 「原本系统的 Keltner 短期/中期/长期 禁止动, 这是根本,
不能改动。这一套组合是它的补充。」所以第一组测试就是钉这条边界。

其余守的是那几条推导本身 —— 它们是可以被算错的:
  1. MA/ATR 从上下轨反推是**恒等式**, 不是估计;
  2. 匀速时 a1 = 0 必须**精确**成立, 不是近似;
  3. 压缩指数的两个临界(包含 1 ATR / 脱开 5 ATR)是闭式解, 不是拟合;
  4. 事件分类必须同时用上位置、方向、时间三样 —— 少一样就答不了"站稳还是突破"。
"""
import math

import pytest

from app.indicators import keltner as k
from app.indicators import keltner_geometry as g


def _bands(close: float, ma_s: float, ma_m: float, ma_l: float, atr: float) -> dict:
    """走真正的 keltner.assess 造读数 —— 不自己拼 dict, 免得测的是假输入。"""
    out = {}
    for key, ma in (("s", ma_s), ("m", ma_m), ("l", ma_l)):
        got = k.assess(close=close, ma=ma, atr=atr, n=g.K[key])
        assert got, key
        out[key] = got
    return out


# ---------- ① 边界: 不许改动底层 ----------

def test_只读底层不改动它():
    """补充层不许自己定义一套通道参数, 必须从 keltner.BANDS 取。

    [R199] 原来这里还用字符串扫 `= 2.0 / 2.5 / 3.0`。那是个**太粗的代理**:
    它撞上了阶段层的 `SPREAD_MATURE = 3.0`(那是"分离度超过 3 个 ATR 算走了
    一大段"的门槛, 与通道倍数毫无关系)。换成精确断言 —— 直接比对常量本身,
    并要求两个派生量真的由 K 推出来而不是写死。
    """
    import inspect
    assert "from app.indicators.keltner import" in inspect.getsource(g)
    # 倍数与窗口逐项等于底层的定义
    assert g.K == {key: n for key, _ma, _w, n, _cn in k.BANDS}
    assert g.WINDOW == {key: w for key, _ma, w, _n, _cn in k.BANDS}
    # 两个临界必须是从 K 推出来的, 不是另写的数
    assert g.TORN_ATR == g.K["s"] + g.K["l"]
    assert g.NESTED_ATR == g.K["l"] - g.K["s"]
    # 滞后天数必须与窗口一致((n−1)/2)
    for key, w in g.WINDOW.items():
        assert g.LAG[key] == (w - 1) / 2, key


def test_几何层不产出买卖指令():
    """位置与几何是事实, 买卖是把握分与出场线的事(与 POS_HINT 同一条纪律)。"""
    import inspect
    src = inspect.getsource(g.explain)
    for bad in ("买入", "卖出", "该买", "该卖", "加仓", "减仓"):
        assert bad not in src, f"explain 不该说 {bad}"


# ---------- ② MA/ATR 反推是恒等式 ----------

@pytest.mark.parametrize("atr", [0.5, 1.0, 3.7])
def test_从上下轨反推均线与ATR是精确的(atr):
    b = _bands(close=100.0, ma_s=100.0, ma_m=98.0, ma_l=95.0, atr=atr)
    geo = g.geometry(b, 100.0)
    assert geo["ma"]["s"] == pytest.approx(100.0, abs=0.02)
    assert geo["ma"]["m"] == pytest.approx(98.0, abs=0.02)
    assert geo["ma"]["l"] == pytest.approx(95.0, abs=0.02)
    assert geo["atr"] == pytest.approx(atr, abs=0.02)


def test_缺一档就整块不给():
    """半档数据推不出速度, 更推不出加速度 —— 给个半成品会显示一个像真的假数。"""
    b = _bands(100.0, 100.0, 98.0, 95.0, 2.0)
    del b["l"]
    assert g.geometry(b, 100.0) is None
    assert g.compress(b) is None


# ---------- ③ 二阶: 匀速时加速度精确为零 ----------

def _ma_of(path, n):
    return sum(path[-n:]) / n


def test_匀速时加速度精确为零():
    """这一条是整个二阶推导的地基: 匀速 v 下 C−MA20 = 9.5v 而 MA20−MA60 = 20v,
    各除以自己的天数都得回 v, 所以 a1 = 0 是恒等而非近似。"""
    v, atr = 0.3, 1.5
    path = [100.0 + v * t for t in range(200)]
    c = path[-1]
    b = _bands(c, _ma_of(path, 20), _ma_of(path, 60), _ma_of(path, 120), atr)
    geo = g.geometry(b, c)
    assert geo["accel"]["a1"] == pytest.approx(0.0, abs=2e-3)
    assert geo["accel"]["level"] == g.ACCEL_STEADY
    # 三段速度也该相等, 且等于 v/ATR
    for key in ("v1", "v2", "v3"):
        assert geo["v"][key] == pytest.approx(v / atr, rel=0.02)


def _ramp(slow_first: bool) -> list[float]:
    """前 185 天一个速度、最近 15 天另一个速度 —— 让加速/减速**正在发生**。"""
    a, b_ = (0.05, 0.9) if slow_first else (0.8, 0.05)
    path = [100.0 + a * t for t in range(185)]
    return path + [path[-1] + b_ * (i + 1) for i in range(15)]


def test_加速与减速分得开():
    atr = 1.5
    for name, path, want in (("加速中", _ramp(slow_first=True), g.ACCEL_UP),
                             ("减速中", _ramp(slow_first=False), g.ACCEL_DOWN)):
        c = path[-1]
        b = _bands(c, _ma_of(path, 20), _ma_of(path, 60), _ma_of(path, 120), atr)
        assert g.geometry(b, c)["accel"]["level"] == want, name


def test_轻微的曲率不算加速也不算减速():
    """√t 到第 200 天早就走平了, 近 10 天与之前那一段的速度差不到半个 ATR ——
    判成「匀速」是门槛在正常工作, 不是漏判。门槛太低会把噪声读成信号。"""
    path = [100.0 + 12 * math.sqrt(t) for t in range(200)]
    c = path[-1]
    b = _bands(c, _ma_of(path, 20), _ma_of(path, 60), _ma_of(path, 120), 1.5)
    geo = g.geometry(b, c)
    assert geo["accel"]["level"] == g.ACCEL_STEADY
    assert abs(geo["accel"]["gain_atr"]) < 0.5


def test_匀速参照比是59比19():
    """等价的比值形式。写成测试是为了钉住"3.105 不是随手取的"。"""
    assert g.STEADY_RATIO_MID == pytest.approx(59 / 19)
    assert g.STEADY_RATIO_LONG == pytest.approx(119 / 19)


def test_加速度门槛是量出来的不是拍的():
    # 0.05 ATR/天 = 10 天累积半个 ATR
    assert g.ACCEL_FLAT * g.SPAN1 == pytest.approx(0.475, abs=0.03)


# ---------- ④ 重叠: 两个临界是闭式解 ----------

def test_短带被长带完全包住的临界是1个ATR():
    atr = 2.0
    for delta_atr, nested in ((0.0, True), (0.99, True), (1.5, False), (4.0, False)):
        b = _bands(100.0, 100.0 + delta_atr * atr, 100.0, 100.0, atr)
        assert g.geometry(b, 100.0)["nested"] is nested, delta_atr
    assert g.NESTED_ATR == g.K["l"] - g.K["s"] == 1.0


def test_短带与长带完全脱开的临界是5个ATR():
    atr = 2.0
    for delta_atr, torn in ((4.9, False), (5.0, True), (7.0, True)):
        b = _bands(100.0, 100.0 + delta_atr * atr, 100.0, 100.0, atr)
        assert g.geometry(b, 100.0)["torn"] is torn, delta_atr
    assert g.TORN_ATR == g.K["s"] + g.K["l"] == 5.0


def test_压缩指数在粘合时为1在强趋势时为0():
    atr = 2.0
    tight = _bands(100.0, 100.0, 100.0, 100.0, atr)
    assert g.compress(tight) == pytest.approx(1.0)
    loose = _bands(100.0, 100.0 + 4 * atr, 100.0, 100.0 - 4 * atr, atr)
    assert g.compress(loose) == pytest.approx(0.0)


def test_压缩指数没有方向所以打分不能用它():
    """涨的和跌的可以给出同一个 O —— 这正是打分走带符号 spread 的理由。"""
    atr = 2.0
    up = _bands(100.0, 100.0 + 2 * atr, 100.0, 100.0 - 2 * atr, atr)
    down = _bands(100.0, 100.0 - 2 * atr, 100.0, 100.0 + 2 * atr, atr)
    assert g.compress(up) == pytest.approx(g.compress(down))
    assert g.geometry(up, 100.0)["spread"] > 0 > g.geometry(down, 100.0)["spread"]


# ---------- ⑤ 历史序列 ----------

def test_压缩持续天数数的是连续的():
    closes = [100.0] * 200 + [100.0 + 3 * i for i in range(1, 11)]
    rows = g.series(closes, [1.0] * len(closes))
    r = g.runs(rows)
    assert r["compress_days"] == 0, "最后 10 天已经拉开了, 不该还算粘合"
    r2 = g.runs(rows[:200])
    assert r2["compress_days"] > 50


def test_在轨外连续天数区分突破与站稳():
    closes = [100.0] * 200 + [100.0 + 4 * i for i in range(1, 6)]
    rows = g.series(closes, [1.0] * len(closes))
    assert g.runs(rows)["above_run"] >= g.CONFIRM_DAYS
    # 只冲一天就回落
    closes2 = [100.0] * 200 + [140.0, 100.5]
    assert g.runs(g.series(closes2, [1.0] * 202))["above_run"] == 0


def test_序列空输入不崩():
    assert g.series(None, None) == []
    assert g.series([1.0, 2.0], [1.0]) == []
    assert g.runs([])["compress_days"] == 0


# ---------- ⑥ 事件: 位置 × 方向 × 时间 ----------

def _ev(state, dur=5, spread=2.5, stack=g.STACK_BULL, a1=0.1, up=0, dn=0, cd=0, o=0.0):
    return g.event(state=state, duration=dur,
                   geo={"stack": stack, "spread": spread, "accel": {"a1": a1}, "compress": o},
                   run={"above_run": up, "below_run": dn, "compress_days": cd})


def test_同一个破上轨在不同六态下是不同的事():
    """这是整个事件层存在的理由 —— 用户的原话:「K 线穿过短期上轨算站稳了还是
    突破了? 还是说这就算进入了主升浪?」光看通道答不了, 必须叉上六态与天数。"""
    assert _ev("NR", up=1)["code"] == g.EV_BREAKOUT_TRY      # 回升途中第一天 = 突破尝试
    assert _ev("NR", up=3)["code"] == g.EV_BREAKOUT_HOLD     # 守住了 = 站稳
    assert _ev("UT", up=1, spread=1.0)["code"] == g.EV_TREND_ACCEL   # 趋势内加速
    assert _ev("DT", up=3, stack=g.STACK_BEAR, spread=-2.0)["code"] == g.EV_BOUNCE_CAP


def test_突破与站稳的区别只在天数上():
    a, b = _ev("SR", up=1), _ev("SR", up=g.CONFIRM_DAYS)
    assert a["confirmed"] is False and b["confirmed"] is True
    assert a["code"] != b["code"]


def test_主升浪五条缺一不可():
    full = dict(state="UT", up=4, spread=2.6, stack=g.STACK_BULL, a1=0.08)
    assert _ev(**full)["code"] == g.EV_MAIN_ADVANCE
    assert _ev(**{**full, "state": "NR"})["code"] != g.EV_MAIN_ADVANCE      # ① 非 UT
    assert _ev(**{**full, "stack": g.STACK_MIXED})["code"] != g.EV_MAIN_ADVANCE  # ② 排列
    assert _ev(**{**full, "spread": 1.0})["code"] != g.EV_MAIN_ADVANCE      # ③ 未分离
    assert _ev(**{**full, "up": 2})["code"] != g.EV_MAIN_ADVANCE            # ④ 天数不够
    assert _ev(**{**full, "a1": -0.2, "up": 6})["code"] == g.EV_EXHAUSTING  # ⑤ 在减速


def test_多头侧跌破下轨是洗盘不是破位():
    assert _ev("UT", dn=1)["code"] == g.EV_SHAKEOUT
    assert _ev("DT", dn=3, stack=g.STACK_BEAR)["code"] == g.EV_BREAKDOWN_HOLD


def test_没到轨时粘合久了叫压缩待变():
    assert _ev("NREA", cd=20, o=0.95)["code"] == g.EV_COILING
    assert _ev("NREA", cd=0)["code"] == g.EV_NONE


def test_事件缺输入不崩():
    assert g.event(state=None, duration=None, geo=None, run=None)["code"] == g.EV_NONE


# ---------- ⑦ 27 种组合的补充注记 ----------

def test_27种组合被完全分类():
    """要么需要补一句, 要么明确"底层已说准" —— 不许有第三种(那是忘了写)。"""
    allc = [a + b + c for a in "上中下" for b in "上中下" for c in "上中下"]
    noted, clean = set(g.COMBO_NOTES), set(g.COMBO_CLEAN)
    assert len(allc) == 27
    assert not (noted & clean), "同一种组合不能既要补又说已准"
    assert set(allc) == noted | clean


def test_补充注记只在底层说不准时才出现():
    atr = 2.0
    # 上中中: 只有短期到上沿 —— 底层的「短线冲高」说得准, 不该多话
    b = _bands(100.0 + 2.2 * atr, 100.0, 100.0 + 2.2 * atr, 100.0 + 2.2 * atr, atr)
    assert g.combo_code(b) == "上中中"
    assert g.combo_note(b) is None


def test_底层没有结论的两种组合这里补上了():
    """中中上 / 中中下 —— keltner.verdict 在这两格返回 None。"""
    for combo in ("中中上", "中中下"):
        assert combo in g.COMBO_NOTES
        assert g.COMBO_NOTES[combo][1], combo


# ---------- ⑧ [R197] O 的时间积分 与 频段能量 ----------

def test_平均压缩度与连续压缩天数量的不是同一件事():
    """一只票可以「昨天刚脱开」(compress_days=0)而「整个季度几乎都粘着」
    (compress_avg 很高) —— 那是刚刚启动。两个数分开看才知道是哪一种。"""
    # 拉开要够大才算数: O ≥ 0.8 等价于 |spread| ≤ 1.8 个 ATR, 三天小涨根本
    # 拉不开(spread 才 1.25) —— 这个前提本身就是压缩指数的定义在起作用。
    closes = [100.0] * 200 + [100.0 + 8 * i for i in range(1, 11)]
    rows = g.series(closes, [1.0] * len(closes))
    r = g.runs(rows)
    avg = g.compress_avg(rows)
    assert r["compress_days"] == 0, f"最后十天已经拉开, 实际连续 {r['compress_days']} 天"
    assert avg is not None and avg > 0.7, f"但这个季度大部分时间是粘的, 实际 {avg}"


def test_平均压缩度是窗口内的均值():
    closes = [100.0] * 300
    rows = g.series(closes, [1.0] * 300)
    assert g.compress_avg(rows) == pytest.approx(1.0)
    assert g.compress_avg([]) is None


def test_频段能量必须扣掉趋势基线():
    """**这是整个指标成立的前提。** 匀速趋势下三个带通的幅度天然正比于各自
    覆盖的天数(9.5 : 20 : 30), 不扣基线的话它会永远说"低频占优" ——
    那是均线的定义, 不是这只票的特征。扣掉之后纯趋势恰好三份各 1/3。"""
    trend = [100.0 + 0.5 * t for t in range(200)]
    e = g.band_energy(trend, [1.5] * 200)
    for k_ in ("s", "m", "l"):
        assert e["share"][k_] == pytest.approx(1 / 3, abs=0.02), e["share"]


def test_高频噪声让短频占优():
    import random
    random.seed(3)
    noisy = [100.0 + 0.5 * t + random.gauss(0, 4) for t in range(200)]
    e = g.band_energy(noisy, [1.5] * 200)
    assert e["dominant"] == "s"
    assert e["share"]["s"] > 1 / 3


def test_趋势走平之后能量落到低频():
    """老趋势还在均线里, 但近期没有新动能 —— 低频占优 = 动能在衰减。"""
    flat = [100.0 + 0.5 * t for t in range(140)] + [170.0] * 60
    e = g.band_energy(flat, [1.5] * 200)
    assert e["dominant"] == "l"
    assert e["share"]["l"] > 0.4


def test_频段占比恒和为一():
    trend = [100.0 + 0.3 * t for t in range(200)]
    e = g.band_energy(trend, [1.5] * 200)
    assert sum(e["share"].values()) == pytest.approx(1.0, abs=1e-3)


def test_频段能量样本不够就不给():
    assert g.band_energy([100.0] * 50, [1.0] * 50) is None
    assert g.band_energy(None, None) is None


def test_基线常量就是三段的天数跨度():
    assert g.ENERGY_REF == (g.SPAN1, g.SPAN2, g.SPAN3) == (9.5, 20.0, 30.0)


# ---------- ⑨ [R199] 阶段判定 ----------

def _geo(spread, a1, o=0.3, torn=False, nested=False):
    return {"spread": spread, "accel": {"a1": a1}, "compress": o,
            "torn": torn, "nested": nested}


def test_阶段是三个量一起读出来的():
    """**这是阶段层存在的理由**: 压缩 0.9 是好是坏? 分离度 2.4 呢? 单看每一个
    都答不了「我该怎么办」, 三个一起才落到某一段上。"""
    assert g.phase(_geo(0.3, 0.0, o=0.95, nested=True))["code"] == g.PH_COILING
    assert g.phase(_geo(0.7, 0.12, o=0.6))["code"] == g.PH_LAUNCHING
    assert g.phase(_geo(2.2, 0.08))["code"] == g.PH_ADVANCING
    assert g.phase(_geo(3.6, -0.15))["code"] == g.PH_STALLING
    assert g.phase(_geo(6.2, 0.1, torn=True))["code"] == g.PH_OVEREXTENDED
    assert g.phase(_geo(-2.4, -0.1))["code"] == g.PH_DECLINING


def test_同一个分离度加速度不同就是不同的阶段():
    """分离度一样、加速度反号 —— 推进 vs 钝化。只看分离度会把它们混为一谈。"""
    assert g.phase(_geo(3.5, 0.10))["code"] == g.PH_ADVANCING
    assert g.phase(_geo(3.5, -0.10))["code"] == g.PH_STALLING


def test_脱开了但没有动能不叫启动():
    """刚脱开却没加速, 很容易缩回去 —— 不该给它「启动初期」这个乐观的名字。"""
    assert g.phase(_geo(0.7, 0.0, o=0.6))["code"] == g.PH_UNCLEAR


def test_每个阶段都说清了该盯什么():
    for geo in (_geo(0.3, 0.0, o=0.95, nested=True), _geo(0.7, 0.12), _geo(2.2, 0.08),
                _geo(3.6, -0.15), _geo(6.2, 0.1, torn=True), _geo(-2.4, -0.1)):
        p = g.phase(geo)
        assert p["why"] and p["watch"], p


def test_阶段层不下买卖指令():
    """与 explain 同一条纪律 —— 同一个阶段对持仓和对空仓要做的事不同。"""
    import inspect
    src = inspect.getsource(g.phase)
    for bad in ("该买", "该卖", "买入", "卖出", "清仓"):
        assert bad not in src, f"phase 不该说 {bad}"


def test_阶段的两个刻度与打分曲线的甜区对齐():
    """不另立一套数 —— SPREAD_CURVE 的甜区就是 1.5~3。"""
    assert g.SPREAD_LAUNCH == 1.0 and g.SPREAD_MATURE == 3.0


def test_阶段空输入不崩():
    assert g.phase(None) is None
    assert g.phase({"accel": {}}) is None


# ================================================================
# [R203] 匀速基准 —— 加速度的比值形式
#
# 这一层的推导 R195 就写在模块头里了, 但一直没算出来。补上它的理由不是
# "多一个数", 是**这句话用户能自己核对**:
#
#     「短期偏离 1.2, 按匀速中期该到 3.7, 实际只有 2.1 —— 跟不上」
#
# 而 a1 = −0.08 不能。两者是同一件事的两种写法, 各有各的用处:
# 打分走差值(比值在 d短 跨零时会翻转解释), 界面走比值。


def test_匀速时比值精确等于一():
    """这是**精确**成立的, 不是近似 —— 匀速下 d_n ∝ (n−1)/2。"""
    b = g.baseline({"s": 1.0, "m": g.STEADY_RATIO_MID, "l": g.STEADY_RATIO_LONG})
    assert b["ratio"] == 1.0
    assert b["level"] == "onpace"


def test_加速时中期跟不上短期的甩开():
    b = g.baseline({"s": 2.0, "m": 3.5, "l": 5.0})
    assert b["level"] == "lead" and b["ratio"] < 1
    assert "比之前快" in b["why"]


def test_减速时中期比该有的位置还远():
    b = g.baseline({"s": 0.5, "m": 3.0, "l": 7.0})
    assert b["level"] == "lag" and b["ratio"] > 1
    assert "收劲" in b["why"]


def test_短期偏离太小时不给结论而不是给个假数():
    """分母趋近 0 时任何比值都没有意义。给个"看着像真的"的数比不给更坏。"""
    assert g.baseline({"s": 0.1, "m": 0.3, "l": 0.6}) is None
    assert g.baseline({"s": 0.0, "m": 0.0, "l": 0.0}) is None
    assert g.baseline(None) is None
    assert g.baseline({"s": 1.0}) is None


def test_比值形式与差值形式方向一致():
    """两种写法是同一件事 —— 结论打架就说明有一边写错了。

    只在**短期偏离够大**(比值有意义)且**判定不在容差带里**时比较:
    两者的门槛本来就不同(一个是 ±15% 的比值容差, 一个是 0.05 ATR/天),
    边界附近各自落在不同档是正常的, 不是矛盾。
    """
    import itertools
    checked = 0
    for ds, dm in itertools.product((0.5, 1.0, 2.0, 3.0), (0.5, 2.0, 4.0, 8.0, 12.0)):
        d = {"s": ds, "m": dm, "l": dm * 2}
        b = g.baseline(d)
        if not b or b["level"] == "onpace":
            continue
        # 差值形式: v1 = d_s / SPAN1, v2 = (d_s − d_m) / SPAN2 …
        # 这里直接用 geometry 那套的定义重算一遍
        v1 = ds / g.SPAN1
        v2 = (ds - dm) / g.SPAN2 * -1      # d_m − d_s = (MA_s − MA_m)/ATR
        a1 = v1 - v2
        if abs(a1) <= g.ACCEL_FLAT:
            continue
        checked += 1
        assert (b["level"] == "lead") == (a1 > 0), (
            f"d={d} 比值说 {b['level']}, 差值说 a1={a1:.3f} —— 两种写法打架")
    assert checked >= 5, "样本太少, 这条测不到什么"


def test_基准挂在几何量的返回值里():
    """算了不给出去等于没算 —— R200 那次 explain() 就是这么躺了五轮。"""
    bands = _bands(104.0, 102.0, 100.0, 96.0, atr=2.0)
    got = g.geometry(bands, close=104.0)
    assert got is not None and "baseline" in got
