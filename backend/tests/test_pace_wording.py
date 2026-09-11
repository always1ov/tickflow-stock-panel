"""[R278] 快慢措辞的**唯一产地**, 以及那几个给阈值背书的数字**必须可复算**。

用户: 「校准整个系统的表达」「特别是涉及评分阈值的要认真检查」
      「v2 版本的打分系统是稳定版, 不能动」「禁止造假, 要有科学依据」。

## 查出来的是同一个毛病的四份拷贝

加速度 `a1 = v1 − v2` 是**带方向**的(符号表示往多头还是往空头变), 可全系统有
三套措辞在按"变快还是变慢"描述它, 于是在跌势里一律说反:

    ACCEL_CN      加速 / 匀速 / 减速          → 决策台悬停、组合速查、今日总览、HTML 导出
    _pace()       还在加速 / … / 正在放慢     → 「间距」列 (R277 只修了这一套)
    explain()     还在加力 / 推力在退         → 通道档位页签
    PACE_CLS      按**词**取色                → 其中两个词的颜色与符号相反

第四份是颜色。有意思的是 `ComboView` 的配色**从来没错过** —— 它按 `level`
(a1 的符号)取色, 而颜色编的正是符号。**错的一直是词, 不是色。**

## 阈值一个都没动

`ACCEL_FLAT = 0.05` 与 `MAIN_ADVANCE["min_a1"] = 0.0` 不一致(实测 16.1% 的
交易日落在这条缝里: 界面说「速度平稳」而主升浪第⑤条判「不通过」)。**没有改**:
`MAIN_ADVANCE` 那五条阈值代码自述「全是先验, 一条都没有台账支持」, 在没有后验
证据的情况下动它, 只是拿一个猜测替换另一个猜测 —— 那正是"造假"。

能做的是**把给阈值背书的数字变成可复算的**, 见 `test_R278_门槛的立论必须复算得出来`。
"""
from __future__ import annotations

import re
import statistics as st
from pathlib import Path

import pytest

from app.indicators import keltner_geometry as g
from tests.fixtures.market_archetypes import SCENARIOS, atrs, closes

KG = Path(g.__file__)


# ================================================================
# 一个产地
# ================================================================

def test_R278_只有一处在决定这句话怎么说():
    """`accel_cn()` 是唯一产地。别处再写一遍 = 又一次漂移。"""
    src = KG.read_text(encoding="utf-8")
    body = "\n".join(ln for ln in src.splitlines() if not ln.lstrip().startswith("#"))
    # 五个词只许出现在 _PACE_BULL / _PACE_BEAR 两张表里
    for word in ("还在加速", "正在放慢", "跌得更急", "跌势在缓"):
        hits = [ln for ln in body.splitlines()
                if f'"{word}"' in ln and "_PACE_B" not in ln]
        assert not hits, f"「{word}」在产地之外还写了一遍:\n  " + "\n  ".join(hits)


def test_R278_pace走的就是那一处():
    src = KG.read_text(encoding="utf-8")
    fn = src[src.index("    def _pace()"):]
    fn = fn[:fn.index("\n    def mk(")]
    code = "\n".join(ln for ln in fn.splitlines() if not ln.lstrip().startswith(("#", '"')))
    assert "accel_cn(" in code, "_pace 又自己造词了"


def test_R278_geometry也带方向():
    """`accel.level_cn` 以前是三档中性词, 四个下游(决策台悬停/组合速查/今日总览/
    HTML 导出)因此全在跌势里说反话。`geometry()` 手上就有 spread。"""
    src = KG.read_text(encoding="utf-8")
    fn = src[src.index("def geometry(bands"):]
    fn = fn[:fn.index("\ndef ")]
    assert "accel_cn(level, spread)" in fn, "geometry 又把方向丢了"


@pytest.mark.parametrize("name", SCENARIOS)
def test_R278_两处产地在每个具名场景上都一致(name):
    """逐个场景点名 —— 整表比一次会把"哪一个对不上"混成一条失败。"""
    geo = _geo(name)
    assert geo["accel"]["level_cn"] == g.phase(geo)["pace_cn"]


def _geo(name: str):
    cs, at = closes(name), atrs(closes(name))
    t = len(cs) - 1
    a = at[t]
    ma = lambda n: sum(cs[t - n + 1:t + 1]) / n          # noqa: E731
    return g.geometry({k: {"upper": m + ka * a, "lower": m - ka * a}
                       for k, m, ka in (("s", ma(20), 2.0), ("m", ma(60), 2.5),
                                        ("l", ma(120), 3.0))}, cs[t])


# ================================================================
# 方向判据与阶段同源 —— R277 那两个平行式子差一个边界点
# ================================================================

def test_R278_方向判据与阶段判定是同一个式子():
    """R277 用 `not nested and sp < 0`, 而 `phase()` 用 `sp <= -SPREAD_LAUNCH`。
    **差一个边界点**: `spread = -1.00` 时阶段说「下跌中」而快慢说「正在放慢」。"""
    for sp in (-1.10, -1.05, -1.01, -1.00, -0.99, -0.95):
        geo = {"spread": sp, "accel": {"a1": -0.30}, "compress": 0.3,
               "torn": False, "nested": abs(sp) <= g.NESTED_ATR,
               "d": {"s": sp, "m": sp / 2, "l": sp / 4}, "stack": "bear"}
        p = g.phase(geo)
        bear_phase = p["cn"] in ("下跌中", "跌过头")
        bear_word = p["pace_cn"] in ("跌得更急", "跌势在缓")
        assert bear_phase == bear_word, (
            f"spread={sp}: 阶段说「{p['cn']}」而快慢说「{p['pace_cn']}」")


def test_R278_那个边界点本身():
    """钉死上面那条查出来的具体值 —— 免得下次谁改了阈值又悄悄错开。"""
    assert g.bear_structure(-g.SPREAD_LAUNCH) is True
    assert g.bear_structure(-g.SPREAD_LAUNCH + 0.001) is False
    assert g.bear_structure(None) is False


def test_R278_常量只定义一次():
    """`SPREAD_LAUNCH` 原来在同一个文件里定义了两次(文件头一份、phase 区一份)。
    改了上面那份而下面那份把它盖回去, 是最难查的一类错。"""
    src = KG.read_text(encoding="utf-8")
    for name in ("SPREAD_LAUNCH", "SPREAD_MATURE", "ACCEL_FLAT"):
        n = len(re.findall(rf"^{name} = ", src, re.M))
        assert n == 1, f"{name} 在文件里定义了 {n} 次"


# ================================================================
# 没有方向可用时的中性说法
# ================================================================

def test_R278_中性说法不许用加速减速():
    """台账按 `level` 跨多只票分组, 那里**根本没有"这一只的方向"**, 纠正不了。
    所以中性场合必须选一组四个象限都不会读反的词 —— 「往上/往下」说的是符号。"""
    # 光秃秃的「加速 / 减速」正是会读反的那一对 —— 它们描述大小, 而这个量的
    # 意义在符号。带方位前缀的「往上/往下加速」说的就是符号, 四个象限都成立。
    assert g.ACCEL_CN[g.ACCEL_DOWN] not in ("减速", "变慢", "放慢"), (
        f"中性说法用了会读反的词: {g.ACCEL_CN[g.ACCEL_DOWN]}")
    assert g.ACCEL_CN[g.ACCEL_UP] not in ("加速", "提速", "加快")
    assert g.ACCEL_CN[g.ACCEL_DOWN] == "往下加速"
    assert g.ACCEL_CN[g.ACCEL_UP] == "往上加速"


def test_R278_不给方向就走中性():
    assert g.accel_cn(g.ACCEL_DOWN) == "往下加速"
    assert g.accel_cn(g.ACCEL_DOWN, -2.0) == "跌得更急"
    assert g.accel_cn(g.ACCEL_DOWN, 2.0) == "正在放慢"
    assert g.accel_cn(None) == "" and g.accel_cn(None, 1.0) == ""


def test_R278_台账仍按码存不按词存():
    """改措辞不许动历史台账。台账落的是 `level`(码), 词只在渲染时套 ——
    否则每改一次说法, 过去几个月的分组就断成两截。"""
    from app.api import today
    src = Path(today.__file__).read_text(encoding="utf-8")
    assert '"accel": ((geo or {}).get("accel") or {}).get("level")' in src, \
        "台账落的不是 level 码了 —— 改词会把历史分组打断"


# ================================================================
# 「禁止造假」: 给阈值背书的数字必须当场复算得出来
# ================================================================

def _a1_samples() -> list[float]:
    """16 个具名场景 × 逐日。**无随机抽取** —— 见 AGENTS.md 那条纪律。

    从第 130 天起算: MA120 要 120 天料, 之前算出来的是半成品。
    """
    out: list[float] = []
    for name in SCENARIOS:
        cs, at = closes(name), atrs(closes(name))
        for t in range(130, len(cs)):
            a = at[t]
            if not a or a <= 0:
                continue
            ma = lambda n: sum(cs[t - n + 1:t + 1]) / n     # noqa: E731,B023
            geo = g.geometry({k: {"upper": m + ka * a, "lower": m - ka * a}
                              for k, m, ka in (("s", ma(20), 2.0), ("m", ma(60), 2.5),
                                               ("l", ma(120), 3.0))}, cs[t])
            if geo:
                out.append(geo["accel"]["a1"])
    return out


def test_R278_门槛的立论必须复算得出来():
    """**这一条是「禁止造假」的直接守卫。**

    原注释拿三个数给 `ACCEL_FLAT = 0.05` 背书:「|a1| 中位数约 0.12, 取 0.05 时
    匀速约占两成, 两侧各四成」。复算之后一个都对不上 —— 那段说明在用一组编出来的
    数字给一个阈值撑腰, 而**看的人无从验证**。

    现在注释里写的是实测值, 这条测试**当场重算一遍去对**。谁再往里塞一个没算过的
    数字, 这里就会红。
    """
    src = KG.read_text(encoding="utf-8")
    blk = src[src.index("# [R278] **这个门槛的立论重新量过了"):src.index("ACCEL_FLAT = 0.05")]
    claim = {k: float(v) for k, v in re.findall(
        r"(中位数|加速|平稳|减速)\s*=?\s*([\d.]+)%?", blk)}
    assert len(claim) == 4, f"注释里没写全那四个数, 只解析到: {claim}"

    vals = _a1_samples()
    n = len(vals)
    assert n > 500, f"样本太少({n}), 结论说明不了问题"
    got = {
        "中位数": round(st.median(abs(v) for v in vals), 3),
        "加速": round(100 * sum(1 for v in vals if v > g.ACCEL_FLAT) / n, 1),
        "平稳": round(100 * sum(1 for v in vals if abs(v) <= g.ACCEL_FLAT) / n, 1),
        "减速": round(100 * sum(1 for v in vals if v < -g.ACCEL_FLAT) / n, 1),
    }
    assert got == claim, f"注释里的数字复算不出来:\n  注释 {claim}\n  实测 {got}"


def test_R278_原注释那三个数确实是错的():
    """把"为什么要改"钉住 —— 不是为了改而改。

    哪天底层变了让原注释重新成立, 这条会红, 那时该回头看看是不是我算错了。
    """
    vals = _a1_samples()
    n = len(vals)
    assert abs(st.median(abs(v) for v in vals) - 0.12) > 0.02, "原注释的 0.12 又对了?"
    flat = sum(1 for v in vals if abs(v) <= g.ACCEL_FLAT) / n
    assert abs(flat - 0.20) > 0.05, "原注释的「匀速约占两成」又对了?"


def test_R278_阈值一个都没动():
    """这一轮只改措辞。数值一动, 判定与台账口径就跟着变, 而那需要证据。"""
    assert g.ACCEL_FLAT == 0.05
    assert g.SPREAD_LAUNCH == 1.0 and g.SPREAD_MATURE == 3.0
    assert g.MAIN_ADVANCE["min_a1"] == 0.0
    assert g.TORN_ATR == 5.0 and g.NESTED_ATR == 1.0


def test_R278_界面与主升浪那条缝有多宽():
    """把那 16% 量出来并钉住 —— **它是一个已知的、被记录在案的不一致**,
    不是没人发现。哪天决定动阈值, 这条就是当时的基线。

    界面用 ±0.05 分档(免得天天在两个词之间跳), 主升浪第⑤条用 `a1 >= 0`
    (问的是"有没有掉头")。两个门槛服务两个不同的问题, 数值不同本身不是错;
    错的是没人知道这条缝有多宽。
    """
    vals = _a1_samples()
    n = len(vals)
    seam = sum(1 for v in vals if -g.ACCEL_FLAT <= v < 0) / n
    assert 0.10 < seam < 0.25, f"那条缝的宽度变了: {seam:.1%} —— 该重新看一眼"


# ================================================================
# 那句假话不许回来
# ================================================================

def test_R278_不许再说与打分同源():
    """原注释写着「与 opportunity_score 的 SPREAD_CURVE 甜区(1.5~3)对齐」——
    **`SPREAD_CURVE` 全仓不存在**, `git log -S` 确认历史上也从未存在过。"""
    src = KG.read_text(encoding="utf-8")
    i = src.index("SPREAD_LAUNCH = 1.0")
    blk = src[max(0, i - 1500):i]
    assert "SPREAD_CURVE 甜区" not in blk, "那句假话又回来了"


def test_R278_几何确实不进把握分():
    """把**当前的真实约束**测出来, 取代那条测不到东西的旧断言。

    R229 起几何整层从打分里剥离。`opportunity_score` 的位置轴走 `channel_pct`
    (短期通道位置 0~1)配 `POS_CURVE`, 与 spread / 加速度全无关系。
    """
    from app.services import opportunity_score as osc
    src = Path(osc.__file__).read_text(encoding="utf-8")
    code = "\n".join(ln for ln in src.splitlines() if not ln.lstrip().startswith("#"))
    for name in ("spread", "accel", "keltner_geometry", "SPREAD_CURVE"):
        assert name not in code, (
            f"打分层出现了 `{name}` —— 几何又进分了? 那 R229 的剥离就白做了, "
            f"而且界面上「不进把握分」那句话会变成假话")


def test_R278_界面上那句不进把握分还在():
    """反面: 剥离这件事得让看的人知道, 否则它会被重新当成分数的依据。"""
    from tests.frontend_source import code_of
    page = code_of("components/today/OpportunityTable.tsx")
    assert "不进把握分" in page


# ================================================================
# 配色: 编的是符号, 不是那句话
# ================================================================

# [R278 → **R310 退役**] `test_R278_快慢配色按符号取` 钉的是前端 `PACE_CLS`
# ——「颜色编的是符号(a1 的正负), 不是那句话的字面」。
#
# **那张配色表随「怎么办」列一起删了**(R310: 用户删掉了那一列, 两个刻度跟着
# 离场), 而决策台之外唯一还印加速度的地方是今日总览的机会表, 它有意用的是
# 无彩的 `text-muted` —— 那里不按符号上色是对的, 不是漏了。
#
# **所以这条没有可守的对象了, 而不是被绕过去了。** 它那条立论(符号 vs 字面)
# 由这个文件里另外 17 条守着后端那份判定 —— 说法、阈值、方向判据、中性兜底、
# 台账存码不存词, 一条都没退。颜色是那份判定的下游, 下游没了, 上游还在。
