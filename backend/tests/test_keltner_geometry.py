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


def _driftless_walk(seed: int, n: int = 400, sigma: float = 0.02) -> list[float]:
    import random
    rnd = random.Random(seed)
    p, out = 100.0, []
    for _ in range(n):
        p *= (1 + rnd.gauss(0, sigma))
        out.append(p)
    return out


def test_频段能量的基线是随机游走不是匀速直线():
    """[R217] **换基线是这一版最实质的改动, 这条测试是它的验收标准。**

    老基线拿「匀速直线」当分母(9.5 : 20 : 30)。可真实价格离匀速直线远得很,
    它更接近随机游走 —— 拿匀速当分母, 中长频天然被高估, 短频占比被推高:
    实测 300 条**纯随机游走**(既没消息也没趋势), 66% 被判成「短波动主导」。
    那不是这些票的特征, 是分母选错了。

    新基线问的是有意义的那个问题:「和纯噪声比, 哪一段更突出」。所以校准
    标准也跟着变 —— **零漂移随机游走上三份各 1/3**, 而不是匀速直线上各 1/3。

    单条路径是噪声的(一条随机游走可以偏出很多), 所以这里对**分布**取中位数,
    与定标那次的做法一致。
    """
    import statistics as st

    acc = {"s": [], "m": [], "l": []}
    for seed in range(60):
        closes = _driftless_walk(seed)
        atrs = [max(1e-6, st.pstdev(closes[max(0, i - 13):i + 1]) if i else 1e-6) * 1.2
                for i in range(len(closes))]
        e = g.band_energy(closes, atrs)
        if e:
            for k_ in acc:
                acc[k_].append(e["share"][k_])
    assert len(acc["s"]) >= 50
    for k_ in ("s", "m", "l"):
        assert st.median(acc[k_]) == pytest.approx(1 / 3, abs=0.05), \
            {k2: round(st.median(v), 3) for k2, v in acc.items()}


def test_基线只留作对照的那一组仍然是天数跨度():
    """老基线没删, 降级成 `ENERGY_REF_STEADY` 留作对照 —— 它本身没算错,
    只是回答的问题(和匀速直线比)不是我们要问的那个。"""
    assert g.ENERGY_REF_STEADY == (g.SPAN1, g.SPAN2, g.SPAN3) == (9.5, 20.0, 30.0)
    assert g.ENERGY_REF != g.ENERGY_REF_STEADY
    # 短段归一到 9.5, 另外两段比匀速基线小得多 —— 随机游走里中长频本来就弱
    assert g.ENERGY_REF[0] == g.SPAN1
    assert g.ENERGY_REF[1] < g.SPAN2 and g.ENERGY_REF[2] < g.SPAN3


def test_噪声越大短段占比越高():
    """[R217] 原来这条钉的是「带噪声的趋势 → 短频占优」。**在新基线下那是错的
    期望** —— 那条序列本身就有一条实打实的趋势, 低频占优才对。

    真正该守的不变量是**单调性**: 同一条趋势上噪声加大, 短段占比必须上升。
    这一条不依赖基线怎么定, 换哪套分母都成立。
    """
    import random

    def share_s(noise: float) -> float:
        rnd = random.Random(3)
        closes = [100.0 + 0.5 * t + rnd.gauss(0, noise) for t in range(200)]
        return g.band_energy(closes, [1.5] * 200)["share"]["s"]

    quiet, loud = share_s(1.0), share_s(8.0)
    assert loud > quiet, (quiet, loud)


def test_趋势走平之后能量落到低频():
    """老趋势还在均线里, 但近期没有新动能 —— 低频占优 = 动能在衰减。"""
    flat = [100.0 + 0.5 * t for t in range(140)] + [170.0] * 60
    e = g.band_energy(flat, [1.5] * 200)
    assert e["dominant"] == "l"
    assert e["share"]["l"] > 0.4


def test_频段占比恒和为一():
    """三份 share 各自 round 到 3 位, 所以和最多差 1.5e-3 —— 容差必须容得下
    这个舍入, 否则它会在某些输入上偶发地红(改基线那次就撞上了)。"""
    trend = [100.0 + 0.3 * t for t in range(200)]
    e = g.band_energy(trend, [1.5] * 200)
    assert sum(e["share"].values()) == pytest.approx(1.0, abs=2e-3)


def test_频段能量样本不够就不给():
    assert g.band_energy([100.0] * 50, [1.0] * 50) is None
    assert g.band_energy(None, None) is None


# ---------- ⑨ [R199] 阶段判定 ----------

def _geo(spread, a1, o=0.3, torn=False, nested=None):
    """[R215] `nested` 默认**按 spread 推**, 不再让调用方随便填。

    原来它默认 False, 于是这份 helper 造得出 `spread=0.7 且 nested=False` 这种
    **真的 `geometry()` 永远不会返回**的形状(|间距| ≤ 1 必然 nested)。
    「刚启动」那一档就是靠这个假形状显得有人走 —— 实际线上一次都没到过。
    与 R214 里 `verdict={"side": "sell"}` 那条测试是同一个毛病:
    **假数据自己对得上, 于是死路看着像活路。**
    """
    return {"spread": spread, "accel": {"a1": a1}, "compress": o, "torn": torn,
            "nested": abs(spread) <= g.NESTED_ATR if nested is None else nested}


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


# ================================================================
# [R207] 「一路往下走」「间距 -1.7 匀速」这类残句
#
# 用户: 「这类描述改成更明确的意思, 这样太含糊不清了」。两个毛病:
#   ·「间距 -1.7」没说是**谁和谁**之间, 没有单位, 负号要人自己想是什么意思;
#   ·「匀速」单独摆着不知道在讲什么 —— 匀速地涨? 匀速地跌?
#
# 顺带翻出一个**真错误**: 「走得过头了」由 |间距| ≥ 5 触发, 所以一只**深跌**
# 的票也会落到这一档, 却配着「追进去的性价比很低」这种只对涨过头成立的话。


def _torn(sp):
    return {"spread": sp, "accel": {"a1": 0.0}, "compress": 0.0,
            "torn": True, "nested": False}


def test_走过头要分涨过头和跌过头():
    """同一个 |间距| ≥ 5, 涨上去和跌下来该说的话完全相反。"""
    up = g.phase(_torn(6.2))
    down = g.phase(_torn(-6.2))
    assert up["code"] == down["code"] == g.PH_OVEREXTENDED, "还是同一档, 只是说法不同"
    assert up["cn"] == "涨过头" and down["cn"] == "跌过头"


def test_跌过头不能配追高的话():
    """这是这次翻出来的真错误 —— 对一只已经崩下去的票说「追进去性价比很低」
    是答非所问, 它根本不存在「追」这个动作。"""
    down = g.phase(_torn(-6.2))
    assert "追" not in down["watch"], "跌过头那一档还在说追高的事"
    assert "抄" in down["watch"], "跌过头该说的是「别急着抄」"
    up = g.phase(_torn(6.2))
    assert "追" in up["watch"], "涨过头那一档反倒不提追了"


@pytest.mark.parametrize("sp,accel,o,torn,nested", [
    (6.2, 0.0, 0.0, True, False),
    (-6.2, 0.0, 0.0, True, False),
    (-1.7, 0.0, 0.2, False, False),
    (2.2, 0.15, 0.1, False, False),
    (0.3, 0.0, 0.95, False, True),
    (0.7, 0.15, 0.5, False, False),
    (3.6, -0.2, 0.0, False, False),
])
def test_阶段文案里不许出现残句(sp, accel, o, torn, nested):
    """每一句都得说清**谁比谁高(低)多少**, 而不是甩一个「间距 X」出来。"""
    p = g.phase({"spread": sp, "accel": {"a1": accel}, "compress": o,
                 "torn": torn, "nested": nested}, {"compress_days": 12})
    body = p["why"] + p["watch"]
    assert "间距" not in body, f"还有裸的「间距」: {p['why']}"
    # 只要提到了具体数字, 就必须带单位
    if any(ch.isdigit() for ch in p["why"]):
        assert "倍日常波动" in p["why"] or "天" in p["why"], f"数字没有单位: {p['why']}"


def test_阶段名都在四个字以内且不含方向歧义():
    """决策台那一列很窄, 而且名字要能一眼读出方向。"""
    for code, cn in g.PHASE_CN.items():
        assert len(cn) <= 4, f"{code} 的名字「{cn}」太长, 列里放不下"
    assert set(g.PHASE_OVEREXTENDED_CN) == {"up", "down"}
    assert g.PHASE_OVEREXTENDED_CN["up"] != g.PHASE_OVEREXTENDED_CN["down"]


def test_文案里没有漏掉的f前缀():
    """R207 拼字符串时把 `f` 拼进了正文, 界面上就会显示成「—— f短、中、长」。
    这类手误不会报错, 只能扫。"""
    import re
    for sp, o, nested in ((0.3, 0.95, True), (2.2, 0.1, False), (-1.7, 0.2, False)):
        p = g.phase({"spread": sp, "accel": {"a1": 0.0}, "compress": o,
                     "torn": False, "nested": nested}, {"compress_days": 12})
        for text in (p["why"], p["watch"]):
            assert not re.search(r"[—,、。\s]f[一-鿿]", text), f"混进了 f 前缀: {text}"


# ---------------------------------------------- [R209] 走到哪一步 / 还有没有劲


@pytest.mark.parametrize("sp,expect", [
    (0.4, "刚起步"), (-0.4, "刚起步"),
    (1.5, "走到中段"), (-1.5, "走到中段"),
    (3.6, "走了很长"), (-3.6, "走了很长"),
    (6.2, "走过头了"), (-6.2, "走过头了"),
])
def test_走到哪一步按打分那一层的同一组门槛分档(sp, expect):
    """**门槛必须与打分同源。** 界面上说「走了很长」的那一刻, 打分那边也该正好
    在扣分 —— 两边各编一套的话, 用户会看到"界面说走过头了但分数还很高"。"""
    p = g.phase({"spread": sp, "accel": {"a1": 0.0}, "compress": 0.0,
                 "torn": abs(sp) >= g.TORN_ATR, "nested": False})
    assert p["maturity_cn"] == expect


@pytest.mark.parametrize("a1,expect", [
    (0.3, "还在加速"), (0.0, "速度平稳"), (-0.3, "正在放慢"),
])
def test_还有没有劲三档(a1, expect):
    p = g.phase({"spread": 2.0, "accel": {"a1": a1}, "compress": 0.1,
                 "torn": False, "nested": False})
    assert p["pace_cn"] == expect


# ================================================================
# [R277] 快慢的措辞必须分方向 —— 上一版在空头一侧说的是反话
# ================================================================

@pytest.mark.parametrize("a1,expect", [
    (-0.3, "跌得更急"),      # 加速度为负 + 空头结构 = 跌得更凶, 不是"放慢"
    (0.3, "跌势在缓"),       # 加速度转正 = 往多头方向变 = 跌势在收
    (0.0, "速度平稳"),
])
def test_R277_空头结构里快慢要换一套说法(a1, expect):
    """**这是用户问出来的一个真错。**

    加速度是带方向的(`a1 = v1 − v2`, 符号表示"往多头还是往空头变"), 不是
    "变快还是变慢"。可「还在加速 / 正在放慢」读起来正是后者 —— 于是一只跌得
    越来越急的票, a1 明显为负, 界面上写着「正在放慢」。

    与 R207(「走得过头了」把只对涨过头成立的话配给深跌票)、R215①(「涨势转弱」
    配给已经跌完的票)同一族: **措辞只考虑了上涨那一侧。**
    """
    p = g.phase({"spread": -2.0, "accel": {"a1": a1}, "compress": 0.0,
                 "torn": False, "nested": False,
                 "d": {"s": -2.5, "m": -1.5, "l": -0.5}, "stack": "bear"})
    assert p["pace_cn"] == expect


def test_R277_挤在一起时不按间距分方向():
    """[R224 立过的规矩] 三条线挤在一起时 `spread` 的正负是**噪声不是方向**
    (差一点点就会翻号)。拿它挑措辞等于按噪声说话 —— 同一只横盘票会在
    「还在加速」和「跌势在缓」之间随机跳。

    横盘里「还在加速」本来就该读成"开始往外走了", 与 `PH_LAUNCHING` 一致。
    """
    for sp in (-0.2, 0.2):
        p = g.phase({"spread": sp, "accel": {"a1": 0.3}, "compress": 0.5,
                     "torn": False, "nested": True})
        assert p["pace_cn"] == "还在加速", f"间距 {sp} 时措辞被噪声带偏了"


def test_R277_上涨那一侧一个字没变():
    """**只补空头那一侧, 不许顺手改动已经对的那一半。**

    上涨结构的三档是 R209 定下的, 用户看惯了; 这次的毛病只在另一侧。
    """
    for a1, expect in ((0.3, "还在加速"), (0.0, "速度平稳"), (-0.3, "正在放慢")):
        p = g.phase({"spread": 2.4, "accel": {"a1": a1}, "compress": 0.0,
                     "torn": False, "nested": False,
                     "d": {"s": 2.5, "m": 1.5, "l": 0.5}, "stack": "bull"})
        assert p["pace_cn"] == expect


def test_R277_四个方向都说得出话且互不相同():
    """穷举四角: 涨/跌 × 加速/减速。**四句话必须两两不同** ——
    只要有两个方向共用一句, 就说明又有一侧在借另一侧的措辞。
    """
    said = {}
    for sp, tag in ((2.4, "涨"), (-2.4, "跌")):
        for a1, k in ((0.3, "正"), (-0.3, "负")):
            p = g.phase({"spread": sp, "accel": {"a1": a1}, "compress": 0.0,
                         "torn": False, "nested": False,
                         "d": {"s": sp, "m": sp / 2, "l": sp / 4},
                         "stack": "bull" if sp > 0 else "bear"})
            said[f"{tag}{k}"] = p["pace_cn"]
    assert len(set(said.values())) == 4, f"有方向在借别人的措辞: {said}"


def test_这两个读数里一个数字都没有():
    """这一列重做的**全部理由**: 上一版摆的是「短线低 1.7 倍波动 / 速度没变」,
    那还是测量值。扫表的人换算不出「1.7 倍日常波动」意味着什么。"""
    import itertools
    for sp, a1 in itertools.product((-6.2, -1.5, 0.3, 2.2, 6.2), (-0.3, 0.0, 0.3)):
        p = g.phase({"spread": sp, "accel": {"a1": a1}, "compress": 0.3,
                     "torn": abs(sp) >= g.TORN_ATR, "nested": False})
        for k in ("cn", "maturity_cn", "pace_cn"):
            assert not any(ch.isdigit() for ch in p[k]), f"{k} 里有数字: {p[k]}"


# ================================================================
# [R212] explain(): 数据 + 一句解释
#
# 这一块改过三版, 每一版错在同一地方的不同侧面:
#   v1 只给数字   → 「用数字看不懂」(得先知道"多少算大")
#   v2 只给状态词 → 「仍旧看不懂, 获取不到结论性信息」(「走到中段」然后呢?)
#   v3 三样一起   → 名称(在说什么) + 数值(能核对) + 解释(所以呢)


def _full_geo(spread=-1.3, a1=0.15, o=0.10, level="loose", combo="中下中"):
    return {"accel": {"level": g.ACCEL_UP if a1 > g.ACCEL_FLAT
                      else g.ACCEL_DOWN if a1 < -g.ACCEL_FLAT else g.ACCEL_STEADY,
                      "a1": a1, "gain_atr": round(a1 * g.SPAN1, 2)},
            "spread": spread, "compress": o, "compress_level": level,
            "torn": abs(spread) >= g.TORN_ATR, "nested": abs(spread) <= g.NESTED_ATR,
            "stack": g.STACK_BEAR if spread < 0 else g.STACK_BULL, "combo": combo,
            "d": {"s": -0.3, "m": -1.1, "l": 0.2}}


def test_每一条都同时给出名称数值和解释():
    rows = g.explain(_full_geo(), {"compress_days": 0, "compress_avg": 0.25},
                     {"dominant": "s", "dominant_cn": "几天的短波动"})
    assert rows, "一条都没有"
    for r in rows:
        assert set(r) == {"label", "value", "why"}, r
        assert r["label"] and r["value"] and r["why"], r
        # **解释必须真的解释**, 不能只是把数值换个说法
        assert len(r["why"]) >= 12, f"解释太短, 等于没说: {r}"


def test_覆盖那七样读数():
    rows = g.explain(_full_geo(), {"compress_days": 0, "compress_avg": 0.25},
                     {"dominant": "m", "dominant_cn": "一波行情的主体"})
    labels = {r["label"] for r in rows}
    for want in ("最近快慢", "三线间距", "三种看法", "连着挤了", "这季平均",
                 "波动来自", "三档位置"):
        assert want in labels, f"少了「{want}」"


def test_数值里必须带得出数字或原词():
    """数值那一列的存在意义就是**能核对** —— 换成一句话就白改了。"""
    rows = g.explain(_full_geo(), {"compress_days": 12, "compress_avg": 0.7},
                     {"dominant": "l", "dominant_cn": "长期老趋势"})
    numeric = [r for r in rows if any(c.isdigit() for c in r["value"])]
    assert len(numeric) >= 5, f"只有 {len(numeric)} 条带得出数: {rows}"


def test_挤了几天与这季平均要合起来解释():
    """两个数分开看都读不出东西, 合起来才分得清「刚走出来」和「反复挤回去」。"""
    just_out = g.explain(_full_geo(), {"compress_days": 0, "compress_avg": 0.75}, None)
    why = next(r["why"] for r in just_out if r["label"] == "这季平均")
    assert "刚刚才走出来" in why

    flaky = g.explain(_full_geo(), {"compress_days": 3, "compress_avg": 0.25}, None)
    why = next(r["why"] for r in flaky if r["label"] == "这季平均")
    assert "反复散开又挤回去" in why


def test_间距的解释按方向与远近分四档():
    for sp, kw in ((0.4, "方向还没真正出来"), (2.0, "行情的主体"),
                   (3.6, "已经走了很长"), (6.2, "没有一个共同认可的合理价")):
        rows = g.explain(_full_geo(spread=sp), None, None)
        why = next(r["why"] for r in rows if r["label"] == "三线间距")
        assert kw in why, f"间距 {sp} 的解释不对: {why}"
    # 跌得太深不能配追高的话
    deep = g.explain(_full_geo(spread=-6.2), None, None)
    why = next(r["why"] for r in deep if r["label"] == "三线间距")
    assert "别急着抄" in why and "追" not in why


def test_没有输入时安静返回空():
    assert g.explain(None) == []
    assert g.explain({}) == []


# ================================================================
# [R215] 阶段表全组合核对 —— 用户: 「下跌中贴下轨的怎么会是涨势转弱, 正常吗」
#
# 不正常。截图那一格是 下跌趋势 7 天 / 涨势转弱·走到中段 / 正在放慢。穷举之后
# 是三类毛病, 同一个根: **`phase()` 只读了短线中枢与长线中枢的间距和快慢,
# 措辞却在替它没看过的两件事打包票** —— 三条线是不是真排成一列, 以及价格在哪儿。
#
#   ① 「涨势转弱」说的是"有一段涨势, 正在转弱"。价格已经跌到三条线之下时,
#      转弱这件事**已经完成了**(中枢滞后: 均线还没交叉, 价格早走完了)。
#   ② 「三条线稳稳朝上/朝下散开」—— 间距只比了短和长两条, 中线在哪儿没看过。
#   ③ 「刚启动」「看不出」两个阶段**一次都出不来**: NESTED_ATR 恰好等于
#      SPREAD_LAUNCH(都是 1.0), "挤在一起"那一档把"刚走出来"的区间整个吞了。
#
# 下面守的是**性质**, 不是几个用例 —— 与 R214 的组合矩阵同一个路子。

_PHASE_GRID = (-4.0, -2.0, -1.0, 0.0, 1.0, 2.0, 4.0)


def _phase_cases():
    """用真的 `geometry()` 造 geo, 不手搓 —— 手搓造得出现实里不存在的形状。"""
    atr = 1.0
    for ma_s in _PHASE_GRID:
        for ma_m in _PHASE_GRID:
            for ma_l in _PHASE_GRID:
                bands = {key: {"mid": ma, "atr": atr,
                               "upper": ma + g.K[key] * atr, "lower": ma - g.K[key] * atr}
                         for key, ma in (("s", ma_s), ("m", ma_m), ("l", ma_l))}
                for close in (ma_s - 3, ma_s - 2, ma_s, ma_s + 2, ma_s + 3):
                    geo = g.geometry(bands, close)
                    if geo:
                        yield geo


def test_每个阶段都到得了():
    """一个永远出不来的阶段和没写是一回事 —— 而且看起来还像写了。

    `PH_LAUNCHING` 就这么躺了很多轮: `today.py` 的 `_COILING_PHASES` 里正列着它,
    等于候选路 C 又瘸了一半(R210 刚修过那条路的另一半)。
    """
    seen = {g.phase(geo)["code"] for geo in _phase_cases() if g.phase(geo)}
    missing = set(g.PHASE_CN) - seen
    assert not missing, f"这些阶段在全枚举里一次都没出现(等于没写): {sorted(missing)}"


def test_排列不干净就不许说三条线散开():
    """间距只比了短和长两条。中线没排到中间时, 「散开」这句话就是假的。"""
    bad = []
    for geo in _phase_cases():
        p = g.phase(geo)
        if not p:
            continue
        if p["code"] == g.PH_ADVANCING and geo["stack"] != g.STACK_BULL \
                and "稳稳朝上散开" in p["why"]:
            bad.append(("advancing", geo["stack"], geo["spread"]))
        if p["code"] == g.PH_DECLINING and geo["stack"] != g.STACK_BEAR \
                and "三条线朝下散开" in p["why"]:
            bad.append(("declining", geo["stack"], geo["spread"]))
    assert not bad, f"{len(bad)} 例排列不干净却说了「散开」, 前 3: {bad[:3]}"


def test_价格位置与阶段名不许打架():
    """价格已经跌穿三条线还叫「涨势转弱」, 或者已经翻上三条线还只说「下跌中」。"""
    bad = []
    for geo in _phase_cases():
        p = g.phase(geo)
        if not p:
            continue
        d = geo["d"]
        below = all(d[key] < 0 for key in ("s", "m", "l"))
        above = all(d[key] > 0 for key in ("s", "m", "l"))
        if p["code"] in (g.PH_STALLING, g.PH_ADVANCING) and below \
                and "价格已经跌到三条线之下" not in p["why"]:
            bad.append(("涨势档没说价格已跌穿", p["cn"], geo["spread"], d))
        if p["code"] == g.PH_DECLINING and above and "反弹" not in p["why"]:
            bad.append(("下跌档没说眼下在反弹", p["cn"], geo["spread"], d))
    assert not bad, f"{len(bad)} 例阶段名与价格位置打架, 前 3: {bad[:3]}"


def test_用户撞见的那一格():
    """中枢还是短线高出长线, 但价格已经跌穿三条线 —— 不该再叫「涨势转弱」。"""
    atr = 1.0
    mas = {"s": 0.0, "m": -0.6, "l": -2.0}
    bands = {key: {"mid": ma, "atr": atr,
                   "upper": ma + g.K[key] * atr, "lower": ma - g.K[key] * atr}
             for key, ma in mas.items()}
    geo = g.geometry(bands, -2.5)          # 收在三条线之下, 贴着短期下轨
    assert geo["spread"] > 0, "这一格的前提就是中枢还朝上"
    assert all(geo["d"][key] < 0 for key in ("s", "m", "l"))
    p = g.phase({**geo, "accel": {"a1": -0.3}})   # 正在放慢
    assert p["cn"] == g.PHASE_STALLING_DONE_CN
    assert p["cn"] != "涨势转弱"
    assert "价格已经跌到三条线之下" in p["why"]
    assert "均线还没掉头" in p["why"]


def test_刚启动要的是重合度松开加提速():
    """「挤在一起」这一档里面再分一层, 用的是现成的重合度门槛与快慢档。

    一个阈值都没新立 —— `SPREAD_LAUNCH` 与打分层共用, 动它就是改口径。
    """
    tight = _geo(0.7, 0.12, o=0.95)      # 还高度重合 → 还是横着
    assert g.phase(tight)["code"] == g.PH_COILING
    loose_up = _geo(0.7, 0.12, o=0.6)    # 重合松开 + 在加速 → 刚启动
    assert g.phase(loose_up)["code"] == g.PH_LAUNCHING
    loose_flat = _geo(0.7, 0.0, o=0.6)   # 松开了却没劲 → 看不出
    assert g.phase(loose_flat)["code"] == g.PH_UNCLEAR
    loose_down = _geo(0.7, -0.12, o=0.6)
    assert g.phase(loose_down)["code"] == g.PH_UNCLEAR


# ================================================================
# [R221] 联网交叉验证之后补的三条
#
# 拿 Keltner 通道的公开资料对了一遍(StockCharts / Raschke 版定义 / 多周期
# 分析的通行做法), 再用蒙特卡洛量了组合表的真实频率。结论有三:
#
#   ① 「收盘站上上轨」在上升趋势里是**强势延续**而不是超买卖点 —— 与本系统
#      `high_short_only`(拿着, 别在这加仓) 和 R212「上沿+多头不是卖」一致 ✓
#   ② 多周期冲突时**长周期为准** —— 与 `verdict()` 先判"短期与长期反向"
#      (超跌反弹 / 强势深调) 一致 ✓
#   ③ **但三档的门槛松紧不一样**, 而这一点原来没在任何地方说过。


def test_三档门槛按各自波动折算是越长越松():
    """[R221] 这是交叉验证挖出来的那件事, 闭式的, 不依赖任何模拟。

    价格绕 MA_n 的离散度按 √n 增长, 而 ATR 倍数只从 2 涨到 3 —— 倍数追不上
    离散度, 于是长期档反而是最容易到边的那一个。「三档同时到上沿」因此
    **不是三重确认**。
    """
    sigma_ratio = {key: (g.WINDOW[key] / g.WINDOW["s"]) ** 0.5 for key in ("s", "m", "l")}
    eff = {key: g.K[key] / sigma_ratio[key] for key in ("s", "m", "l")}
    assert eff["s"] > eff["m"] > eff["l"], eff
    assert eff["s"] == pytest.approx(2.00, abs=0.01)
    assert eff["m"] == pytest.approx(1.44, abs=0.02)
    assert eff["l"] == pytest.approx(1.22, abs=0.02)


def test_组合表每一格都标了有多常见():
    """27 行摆在一起看着像 27 种势均力敌的情形, 实际不是 —— 四格占一多半,
    七格几乎不出现。不标出来, 人会把常态当警报, 也会对着永远不亮的格子研究。"""
    rows = g.combo_table()
    assert len(rows) == 27
    assert all(r["rarity"] for r in rows), [r["combo"] for r in rows if not r["rarity"]]
    by = {r["combo"]: r["rarity"] for r in rows}
    assert by["上上上"] == "很常见" and by["下下下"] == "很常见"
    assert by["下上下"] == "几乎不出现"


def test_三档同向那两格必须带上不是三重确认这句():
    """[R221] 底层的方向没说错, 但语气会让人以为这是罕见的极端信号 ——
    而它们恰恰是最常见的两格。底层禁止改, 所以校正写在补充层。"""
    for code in ("上上上", "下下下"):
        assert code in g.COMBO_NOTES, code
        assert code not in g.COMBO_CLEAN, code
        title, detail = g.COMBO_NOTES[code]
        assert "三重确认" in title or "三重确认" in detail, code
    row = next(r for r in g.combo_table() if r["combo"] == "上上上")
    assert row["note"] and row["verdict"], "注记与底层结论要并排出现, 不是替换"
    assert row["verdict"]["title"] == "大顶区域", "底层结论一个字都不许改"


def test_均线是简单均线而不是指数均线():
    """[R221] 标准 Keltner(Raschke 版)用 EMA20 ± 2×ATR10, 本系统用 SMA。

    **这不是疏漏, 是几何层的前提**: 「MA_n ≈ (n−1)/2 天前的价格」这条恒等式
    与由它推出的「匀速时 a1 精确为 0」只在简单均线下成立。换成 EMA, 整个
    二阶推导(速度/加速度/匀速基准)就只剩近似。

    这条测试钉住的是**别人来"顺手改成 EMA"的时候会红**。
    """
    import inspect
    from app.indicators import pipeline
    src = inspect.getsource(pipeline)
    assert 'rolling_mean(20).over("symbol").alias("ma20")' in src, \
        "ma20 必须是简单均线 —— 换成 EMA 会毁掉几何层的恒等式"
    # 恒等式本身再验一遍(与前面那条匀速测试同源, 这里只钉 SMA 这个前提)
    v, atr = 0.4, 1.0
    path = [100.0 + v * t for t in range(200)]
    b = _bands(path[-1], _ma_of(path, 20), _ma_of(path, 60), _ma_of(path, 120), atr)
    assert g.geometry(b, path[-1])["accel"]["a1"] == pytest.approx(0.0, abs=2e-3)


# ================================================================
# [R222] 逐行核对 27 条结论 —— 用户: 「组合表的结论都正确的吗」
#
# R221 验的是**原则**(站上上轨=延续 / 长周期为准 / SMA 是前提)和**频率**,
# 没有逐行核对结论本身。这一节把那件事补上, 而且做成机器可查的两条性质,
# 不是一次性人工过一遍 —— 底层哪天改了措辞, 这里要能红。
#
# 两类漏洞, 判据不同:
#   甲 正文把这一格的事实**说反了**(如「大级别还早」而长期档就在上沿)
#   乙 正文每句都对, 但**漏掉了长期档**, 于是两格拿到逐字相同的话
#      (中下中 与 中下下 —— 前者长期在中部, 后者长期也在下沿)
#
# 底层禁止改, 所以两类都由补充层注记兜。这两条测试守的是"必须有人兜"。


def _combo_rows():
    return {r["combo"]: r for r in g.combo_table()}


# 底层正文里可以被组合直接证伪的断言
_FALSIFIABLE = (
    ("只有短期到上沿", lambda s, m, l: not (m == "上" or l == "上")),
    ("大级别还早", lambda s, m, l: l != "上"),
    ("只有短期到下沿", lambda s, m, l: not (m == "下" or l == "下")),
    ("长期还在下沿", lambda s, m, l: l == "下"),
    ("长期仍在上沿", lambda s, m, l: l == "上"),
    ("三档同时到上沿", lambda s, m, l: s == m == l == "上"),
    ("三档同时到下沿", lambda s, m, l: s == m == l == "下"),
    ("短期和中期同时到上沿", lambda s, m, l: s == "上" and m == "上"),
    ("短期和中期同时到下沿", lambda s, m, l: s == "下" and m == "下"),
    ("短期还在通道中部", lambda s, m, l: s == "中"),
)


def test_正文说错了事实的那几格必须有注记兜着():
    """甲类。底层是禁止改的, 所以"说错"只能靠旁边加注纠正 —— 但**必须真的有**。"""
    naked = []
    for code, r in _combo_rows().items():
        v = r["verdict"]
        if not v:
            continue
        s, m, l = code
        wrong = [p for p, ok in _FALSIFIABLE if p in v["detail"] and not ok(s, m, l)]
        if wrong and not r["note"]:
            naked.append((code, v["title"], wrong))
    assert not naked, f"这些格子的正文与事实对不上, 却没有补充注记: {naked}"


def test_长期档在轨上时正文或注记必须提到它():
    """乙类。**这一条是这次逐行核对新加的。**

    「中下中」与「中下下」在底层拿到逐字相同的正文, 而那段话只讲短期与中期。
    差别恰恰在长期: 前者长期在通道中部, 后者长期也在下沿 —— 一个是"大级别
    跌到位、等入场点", 另一个半年尺度本身还在低位。而「中下下」是第四常见的
    格子(约 12%), 不是边角情形。

    所以立一条: **长期档只要在轨上, 这一行就必须有人提到它** —— 底层正文提了
    也行, 补充注记提了也行, 但不能两边都不提。
    """
    silent = []
    for code, r in _combo_rows().items():
        v = r["verdict"]
        if not v or code[2] == "中":
            continue
        # 注记的标题在弹窗里也是显示的(`▸ 标题:正文`), 所以标题里提到了也算
        note_txt = (r["note"]["title"] + r["note"]["detail"]) if r["note"] else ""
        said = "长期" in v["detail"] or "长期" in note_txt
        if not said:
            silent.append((code, v["title"], r["rarity"]))
    assert not silent, f"长期档在轨上却没人提它的格子: {silent}"


def test_注记与干净两份名单恰好把27格分完():
    """没有注记必须是**明确的结论**(底层说准了), 不是"忘了写"。"""
    allc = {a + b + c for a in "上中下" for b in "上中下" for c in "上中下"}
    assert set(g.COMBO_NOTES) | g.COMBO_CLEAN == allc
    assert not (set(g.COMBO_NOTES) & g.COMBO_CLEAN), "一格不能既有注记又算干净"


def test_注记只补话不改底层结论():
    """整个补充层的边界: 加注可以, 改判定不行(用户: 「这是根本, 不能够改动的」)。"""
    rows = _combo_rows()
    for code in ("上上上", "中下下", "中上上", "上中上"):
        r = rows[code]
        assert r["note"], code
        assert r["verdict"], f"{code} 的底层结论必须照旧摆着, 不是被注记替换"
    # 底层判定必须是**现调**出来的, 不是表里誊抄的一份
    from app.indicators.keltner import POS_ABOVE, verdict
    live = verdict({k_: {"pos": POS_ABOVE} for k_ in ("s", "m", "l")})
    assert rows["上上上"]["verdict"]["title"] == live["title"]


# ================================================================
# [R224] R223 的那一节整块删了 —— `trend_phase_gap` 已经被 `alignment` 取代
#
# R223 我给「六态 vs 阶段」加了一处成对冲突检查。用户随后问「怎么那么多打架的」,
# 一量才发现是**我造成的**:
#
#     六态 vs 通道结论  29.8%
#     六态 vs 阶段      33.2%   ← R223 加的
#     至少报一个        51.5%   ← 超过一半的行挂着警告
#
# **N 个判定做成对检查就有 N(N−1)/2 个警报**, 而它们并不独立。R205 立的规矩
# (「一半的票都显示打架就没人看了」)被我自己破了。
#
# 换成 `alignment`: 三者不是三个意见, 是一个**滞后阶梯**(价格最快 → 六态 →
# 均线中枢最慢), 不一致本身就是"转折走到第几步"的读数。**报进度, 不报警。**
# 下面那一节测的就是它。

# ================================================================
# [R224] 具名场景 —— 不许随机抽样
#
# 用户: 「不允许随机抽取, 必须是精心挑选」。**这条批评是对的, 我已经栽过两次**:
# 用随机游走量红绿节拍, 400 条全判 `failing`(随机游走结构上产不出「蓄势」);
# 用随机抽的因子量相关性, 而其中六个是我独立抽的 —— 那测的是我的抽样。
#
# 换成手工构造的具名场景之后**第一轮就又抓到一个自己的错**: 摆动幅度给了
# 0.4%, ATR 塌到接近 0, 于是「缓慢爬升」被判成"大顶区域 + 涨过头"。
# 真实日线波动约 2%, 改过来才对。这条教训写在 fixtures 里。


def _scen(name):
    import sys, pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).parent))
    from fixtures.market_archetypes import SCENARIOS, atrs
    c = SCENARIOS[name][1]
    a = atrs(c)
    bands = {key: k.assess(close=c[-1], ma=sum(c[-w:]) / w, atr=a[-1], n=g.K[key])
             for key, w in (("s", 20), ("m", 60), ("l", 120))}
    geo = g.geometry(bands, c[-1])
    return c, a, bands, geo, g.runs(g.series(c, a))


def test_样本的波动幅度必须像真的():
    """ATR 塌了整套样本就废 —— 这一条钉住那个教训。

    真实 A 股日线 ATR 约占价格 2~3%。样本低于 0.8% 就说明摆动写小了,
    那时任何一根 K 线在 ATR 尺度上都成天文数字, 一切判定跟着失真。
    """
    for name in ("蓄势突破前", "缓慢爬升", "下跌途中"):
        c, a, *_ = _scen(name)
        pct = a[-1] / c[-1]
        assert 0.008 <= pct <= 0.06, f"{name}: ATR 占价格 {pct:.1%}, 不像真的"


def test_横盘场景必须判成挤在一起():
    """场景名就是断言 —— 「蓄势突破前」判不出压缩就是系统的问题。"""
    *_, geo, runs = _scen("蓄势突破前")
    assert geo["nested"], geo["spread"]
    assert g.phase(geo, runs)["code"] == g.PH_COILING


def test_挤在一起的时候三尺度不许报方向():
    """[R224] 具名场景抓到的: 纯横盘的「蓄势突破前」因为 spread 恰好差一点点负,
    被报成「正在转空」。横盘票三个符号本来就随时翻号, 拿它们数票是错的。"""
    *_, geo, _ = _scen("蓄势突破前")
    al = g.alignment("NR", geo)
    assert al["level"] is None and "挤在一起" in al["cn"], al


def test_趋势场景三尺度要一致():
    for name in ("主升浪", "涨过头"):
        *_, geo, _ = _scen(name)
        assert g.alignment("UT", geo)["level"] == 3, name
    for name in ("下跌途中", "破位下跌", "跌过头"):
        *_, geo, _ = _scen(name)
        assert g.alignment("DT", geo)["level"] == 0, name


def test_具名场景一个都不许算崩():
    """整套场景跑通 —— 几何/阶段/事件/三尺度都得给得出东西。"""
    import sys, pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).parent))
    from fixtures.market_archetypes import SCENARIOS
    for name in SCENARIOS:
        *_, geo, runs = _scen(name)
        assert geo, name
        assert g.phase(geo, runs), name
        assert g.event(state="NR", duration=3, geo=geo, run=runs), name
        assert g.alignment("NR", geo), name
