"""[R313] SR / SREA 细分档 —— **只标不改**, 一条逻辑都不许被它碰到。

用户: 「补上那两态, 但只是显示, 不触发转折不参与评分, 反正就只显示,
不能影响当前系统任何逻辑。」

「不能影响任何逻辑」这句话必须**逐条落成守卫**, 否则它只是一句愿望:

  ① `state` 一个字节不变(叠加层跑不跑, 状态机给的东西一模一样)
  ② `flipped` 不变 —— 细分档在一段里中途变回去是常事, 那**不是转折**
  ③ 多空归属不变 —— SR 那天仍算多头, SREA 那天仍算空头
  ④ `flip_trades` 的账一分不差
  ⑤ 打分不认识这个字段
  ⑥ 作者内置的 `indicators/livermore.py` 一个字没动
  ⑦ 没有前视 —— 第 i 天只用第 i 天之前走完的段

判据本身取自仓库自己的名词表(`services/glossary.py`), 不从外部搬定义:
  SR   「力度比「自然回升」还弱」  → 本段反弹高点 ≤ 上一段回升高点
  SREA 「还没跌破前一个低点」      → 本段回落低点 ≥ 上一段回撤低点
"""
from __future__ import annotations

import copy

import pytest

from app.indicators import livermore as lv
from app.services import livermore_substate as sub
from tests.fixtures.market_archetypes import SCENARIOS, closes


def _run(cs: list[float], threshold: float = lv.DEFAULT_THRESHOLD) -> dict:
    return lv.compute(cs, [f"d{i:04d}" for i in range(len(cs))], threshold)


def _all_cases():
    """16 个具名场景 × 13 个阈值。**无随机抽取** —— 见 AGENTS.md 那条纪律。"""
    for name in SCENARIOS:
        cs = closes(name)
        for th in lv.GRID_THRESHOLDS:
            yield name, th, _run(cs, th)


# ================================================================
# ① 只标不改
# ================================================================

def test_R313_叠加层不碰入参():
    """`steps` 是作者那份的产物, 这一层只读。改了它, 下游读到的就是被污染的。"""
    for _name, _th, res in _all_cases():
        before = copy.deepcopy(res["steps"])
        sub.substates(res["steps"])
        assert res["steps"] == before, "叠加层改了作者给的 steps"


def test_R313_状态码一个字节不变():
    """**这条是「不能影响任何逻辑」的总闸。**

    跑不跑这个叠加层, `compute()` 给出的每一天的 state 必须一模一样 ——
    这一层根本不在状态机里, 但把它钉死: 哪天有人图省事把判据塞回状态机,
    这条会红。
    """
    for name, th, res in _all_cases():
        states = [s["state"] for s in res["steps"]]
        sub.substates(res["steps"])
        again = [s["state"] for s in res["steps"]]
        assert states == again, f"{name}@{th}: 状态码被叠加层改了"
        # 状态机照旧只产出这四个码 —— 细分档没有混进去
        assert set(states) <= {"UT", "NR", "NREA", "DT", None}, (
            f"{name}@{th}: 状态机里出现了细分码 —— 它该只活在叠加层里"
        )


def test_R313_细分档只落在那两个中间档上():
    """UT / DT 是两端, 没有「次级上涨趋势」这回事。落错档就是在造新状态。"""
    for name, th, res in _all_cases():
        for st, s in zip(res["steps"], sub.substates(res["steps"])):
            if s == sub.SR:
                assert st["state"] == "NR", f"{name}@{th}: SR 落在了 {st['state']} 上"
            elif s == sub.SREA:
                assert st["state"] == "NREA", f"{name}@{th}: SREA 落在了 {st['state']} 上"
            else:
                assert s is None, f"{name}@{th}: 冒出了第三个细分码 {s!r}"


def test_R313_长度与_steps_严格对齐():
    """错一位就是把昨天的档贴到今天头上, 而且不会有任何东西报错。"""
    for _name, _th, res in _all_cases():
        assert len(sub.substates(res["steps"])) == len(res["steps"])
    assert sub.substates([]) == []


# ================================================================
# ② 不触发转折
# ================================================================

def test_R313_细分档在一段中途变化不算转折():
    """**这是这次最容易踩的坑。**

    一段 NR 里, 反弹一开始没超过上一段的高点(SR), 后来超过了(回到 NR)——
    细分档中途变了, 但**那不是转折**: `flipped` 是作者按 state 给的, 与细分
    档无关。把它算成转折, 凭空多出来的买卖信号会直接串进「按转折买卖」的账。
    """
    changed_mid_run = 0
    for _name, _th, res in _all_cases():
        subs = sub.substates(res["steps"])
        for i in range(1, len(subs)):
            same_state = res["steps"][i]["state"] == res["steps"][i - 1]["state"]
            if same_state and subs[i] != subs[i - 1]:
                changed_mid_run += 1
                assert not res["steps"][i]["flipped"], (
                    "细分档中途变化那天被标成转折了"
                )
    assert changed_mid_run > 0, (
        "一次都没出现「同一段里细分档变了」—— 这条守卫就没有守到东西, "
        "要么判据退化了, 要么场景选得不对"
    )


def test_R313_flipped_与叠加层无关():
    for _name, _th, res in _all_cases():
        flips = [s["flipped"] for s in res["steps"]]
        sub.substates(res["steps"])
        assert [s["flipped"] for s in res["steps"]] == flips


# ================================================================
# ③ 多空归属不变
# ================================================================

def test_R313_SR_仍算多头_SREA_仍算空头():
    """`BULLISH` 是全系统唯一的多空口径(打分、决策台、按转折买卖都引用它)。
    细分档**不参与**这个判断 —— SR 那天底层还是 NR, 仍在多头侧。"""
    assert "SR" in lv.BULLISH and "SREA" not in lv.BULLISH, "作者那份多空表变了"
    for name, th, res in _all_cases():
        for st, s in zip(res["steps"], sub.substates(res["steps"])):
            if s == sub.SR:
                assert st["state"] in lv.BULLISH, f"{name}@{th}: SR 那天掉出多头侧了"
            elif s == sub.SREA:
                assert st["state"] not in lv.BULLISH, f"{name}@{th}: SREA 那天跑进多头侧了"


def test_R313_按转折买卖的账一分不差():
    """叠加层存在与否, `flip_trades` 的每一笔、每一个收益必须逐值相同。"""
    from app.services import flip_trades as ft
    for name, th, res in _all_cases():
        steps = res["steps"]
        cs = [s["close"] for s in steps]
        a = ft.simulate(ft.trend_days(steps), cs, cs)
        sub.substates(steps)
        b = ft.simulate(ft.trend_days(steps), cs, cs)
        assert a == b, f"{name}@{th}: 叠加层跑过之后账变了"


# ================================================================
# ④ 评分不认识它
# ================================================================

def test_R313_打分模块完全不认识细分档():
    """`score_candidate` 只认 `state`。这条正反各钉一次。"""
    import inspect
    from app.services import opportunity_score as osc

    src = inspect.getsource(osc)
    assert "substate" not in src and "livermore_substate" not in src, (
        "打分模块认识细分档了 —— 它是 R134 冻结的, 一个字都不该动"
    )
    # SR 早就在 STATE_SCORE 里(作者留的死分档), 但**打分拿到的永远是 state**,
    # 而状态机不产出 SR —— 所以那一档照旧取不到。这一版没有把它激活。
    assert osc.STATE_SCORE == {"UT": 100.0, "NR": 78.0, "SR": 58.0}, "打分的状态表被改了"


def test_R313_硬门槛认的仍然是那四个码():
    """打分的趋势硬门槛 `check_gates` 只看 `state`。这条正反各钉一次:

      · 状态机真会产出的那四个码, 多空两侧各判各的 —— 与从前一模一样;
      · 细分码喂进去**不该被当成多头** —— 万一哪天有人把叠加层的输出
        直接塞进来, 这条会红。SR 在作者的 `BULLISH` 里是多头, 所以它
        「通过」本身不算错; 真正要防的是 **SREA 被放行**。
    """
    from app.services import opportunity_score as osc

    def gate(state):
        return osc.check_gates(state=state, above_ma20=True, above_ma20_prev=True,
                               close=12.0, ma120=10.0, ma120_rising=True)

    for state in ("UT", "NR"):
        assert osc.GATE_TREND not in gate(state)["failed"], f"{state} 被挡住了"
    for state in ("NREA", "DT"):
        assert osc.GATE_TREND in gate(state)["failed"], f"{state} 被放行了"
    # 细分码不该出现在这里, 但万一出现: 空头那一档必须照样被挡住
    assert osc.GATE_TREND in gate("SREA")["failed"], "SREA 被放行了 —— 它是空头侧"


# ================================================================
# ⑤ 作者那份没动
# ================================================================

def test_R313_作者内置的状态机与上一版逐字节相同():
    """这一整次改动的总闸: **`indicators/livermore.py` 一个字节都不许变。**

    「作者内置的指标都是不能动的」—— 补细分档的正确做法是外挂一层标注,
    而不是改他的状态机。
    """
    import pathlib
    import subprocess
    src = pathlib.Path(lv.__file__)
    repo = src.parents[3]
    got = subprocess.run(
        ["git", "-C", str(repo), "show", "HEAD:backend/app/indicators/livermore.py"],
        capture_output=True, text=True)
    if got.returncode != 0:
        pytest.skip("拿不到 HEAD 的那一份(浅克隆), 这条只在完整仓库里有意义")
    assert src.read_text(encoding="utf-8") == got.stdout, (
        "indicators/livermore.py 被改了 —— 细分档该外挂, 不该进状态机"
    )


def test_R313_叠加层不导入状态机内部():
    """它只吃 `steps` 这个出参。碰了 `compute` 的内部就迟早会跟着漂。"""
    import inspect
    code = inspect.getsource(sub)
    body = "\n".join(ln for ln in code.splitlines() if not ln.lstrip().startswith("#"))
    assert "import" not in body.split('"""')[-1], "叠加层引了别的模块 —— 它该是纯函数"


# ================================================================
# ⑥ 没有前视
# ================================================================

@pytest.mark.parametrize("name", SCENARIOS)
def test_R313_没有前视(name):
    """第 i 天的细分档只许用第 i 天之前走完的段。

    做法与状态机那条前视测试一样: 拿前缀重算一遍, 逐值对比。
    **这条是"显示层也不许偷看未来"的底线** —— 复盘时看到的细分档必须是
    当天真的能知道的那一个, 否则整条历史都是事后诸葛。
    """
    res = _run(closes(name))
    full = sub.substates(res["steps"])
    for k in (30, 80, 150, len(res["steps"])):
        if k > len(res["steps"]):
            continue
        assert sub.substates(res["steps"][:k]) == full[:k], f"前 {k} 天的细分档用到了未来"


# ================================================================
# ⑦ 判据本身 —— 具名场景, 不靠真实数据碰运气
# ================================================================

def test_R313_第一段没有参照物时不标():
    """「算不出来」与「判定为普通档」是两件事(R246/R248 那个坑)。"""
    got = sub.substates([
        {"state": "NR", "leg_high": 11.0, "leg_low": 10.0},
        {"state": "NR", "leg_high": 12.0, "leg_low": 10.0},
    ])
    assert got == [None, None], f"第一段就标了细分档, 而它没有可比的上一段: {got}"


def test_R313_反弹没超过上一段就是次级回升():
    """名词表原话:「力度比「自然回升」还弱」。"""
    steps = [
        {"state": "NR", "leg_high": 12.0, "leg_low": 10.0},    # 第一段回升, 高点 12
        {"state": "NREA", "leg_high": 12.0, "leg_low": 11.0},  # 回撤
        {"state": "NR", "leg_high": 11.5, "leg_low": 11.0},    # 第二段只到 11.5 → 弱
        {"state": "NR", "leg_high": 12.5, "leg_low": 11.0},    # 终于超过 12 → 回到普通档
    ]
    assert sub.substates(steps) == [None, None, sub.SR, None]


def test_R313_回落没跌破上一段就是次级回撤():
    """名词表原话:「还没跌破前一个低点」。"""
    steps = [
        {"state": "NREA", "leg_high": 12.0, "leg_low": 10.0},   # 第一段回撤, 低点 10
        {"state": "NR", "leg_high": 13.0, "leg_low": 10.0},     # 回升
        {"state": "NREA", "leg_high": 13.0, "leg_low": 10.5},   # 第二段只到 10.5 → 浅
        {"state": "NREA", "leg_high": 13.0, "leg_low": 9.5},    # 跌破 10 → 回到普通档
    ]
    assert sub.substates(steps) == [None, None, sub.SREA, None]


def test_R313_刚好打平算次级():
    """边界点单独钉 —— 「没能**超过**上一段」, 打平就是没超过。
    不写下来的话, 下次谁把 `<=` 改成 `<` 也没人发现。"""
    steps = [
        {"state": "NR", "leg_high": 12.0, "leg_low": 10.0},
        {"state": "NREA", "leg_high": 12.0, "leg_low": 11.0},
        {"state": "NR", "leg_high": 12.0, "leg_low": 11.0},     # 与上一段一样高
    ]
    assert sub.substates(steps)[-1] == sub.SR


def test_R313_回撤刚好打平也算次级():
    """与上面回升那一条配对。**变异电池逼出来的**: 只钉了回升那一侧的边界,
    把回撤这边的 `>=` 改成 `>` 一样绿 —— 一半的边界没人守。"""
    steps = [
        {"state": "NREA", "leg_high": 12.0, "leg_low": 10.0},
        {"state": "NR", "leg_high": 13.0, "leg_low": 10.0},
        {"state": "NREA", "leg_high": 13.0, "leg_low": 10.0},   # 与上一段一样低
    ]
    assert sub.substates(steps)[-1] == sub.SREA


def test_R313_两端那两档永远不标():
    steps = [
        {"state": "NR", "leg_high": 12.0, "leg_low": 10.0},
        {"state": "NREA", "leg_high": 12.0, "leg_low": 11.0},
        {"state": "UT", "leg_high": 20.0, "leg_low": 11.0},
        {"state": "DT", "leg_high": 20.0, "leg_low": 5.0},
    ]
    assert sub.substates(steps)[2:] == [None, None]


def test_R313_真实场景里两档都跑得出来():
    """判据写对了但一次都触发不到, 与没写是一回事(R214 那个恒假条件的教训)。

    16 个具名场景 × 13 个阈值里, 两档都必须真的出现过。
    """
    seen = {sub.SR: 0, sub.SREA: 0}
    for _name, _th, res in _all_cases():
        for s in sub.substates(res["steps"]):
            if s in seen:
                seen[s] += 1
    assert seen[sub.SR] > 0, "SR 一次都没触发 —— 与没实现是一回事"
    assert seen[sub.SREA] > 0, "SREA 一次都没触发"


# ================================================================
# ⑧ 一路接到界面 —— 「只是显示」也得真的显示出来
# ================================================================

def test_R313_复盘逐日行带上了细分档():
    """产出了却没人接, 与没做是一回事(`state_run` 就这么死过一轮, R308 才捡回来)。

    而且必须**从同一处带过去**: 「现在」那一行不许自己再算一套 ——
    同一个判定两处实现必然漂(R277/R294 反复治过)。
    """
    import inspect
    from app.services import review_service as rs

    # **必须测行为, 不能只读源码。** 第一版写的是「源码里有 `"sub_state"` 这个键」,
    # 而把值改成 `None` 照样绿 —— 键还在, 值没了。变异电池当场逼出来的。
    steps = [
        {"date": "d0", "state": "NR", "leg_high": 12.0, "leg_low": 10.0, "flipped": False},
        {"date": "d1", "state": "NREA", "leg_high": 12.0, "leg_low": 11.0, "flipped": True},
        {"date": "d2", "state": "NR", "leg_high": 11.5, "leg_low": 11.0, "flipped": True},
    ]
    got = rs._trend_by_date(steps)
    assert got["d2"]["sub_state"] == "SR", f"逐日行没有接上细分档: {got['d2']}"
    assert got["d2"]["sub_state_cn"] == "次级回升", "细分档没翻成中文"
    assert got["d0"]["sub_state"] is None and got["d0"]["sub_state_cn"] == ""
    # 反面: 接上细分档不许把原来的东西碰坏
    assert got["d2"]["state"] == "NR" and got["d2"]["side"] == "多头"
    assert got["d1"]["flipped"] is True

    now_src = inspect.getsource(rs._now)
    now_code = "\n".join(ln for ln in now_src.splitlines() if not ln.lstrip().startswith("#"))
    assert 't.get("sub_state")' in now_code, "「现在」那一行没带上细分档"
    assert "substates" not in now_code, (
        "「现在」那一行自己又算了一遍 —— 同一个判定两处实现必然漂"
    )


def test_R313_界面上是注记不是替换():
    """用户: 「只是显示」。所以它**挂在状态旁边**, 不换徽标的词、不换徽标的色。

    换色是最隐蔽的一种"影响逻辑": 徽标的色编的是多空, 而细分档不改多空 ——
    拿它去取色, 界面就会说一件底层没说过的事。
    """
    from tests.frontend_source import code_of
    src = code_of("components/stock-analysis/StockReviewDialog.tsx")
    # **锚在渲染条件上, 不是锚在字段名上。** 把 `{r.trend.sub_state_cn && (`
    # 换成 `{false && (` 之后, 字段名照样在源码里 —— 本仓库这个坑的第 N 次,
    # 这次又是变异电池抓的。
    assert "{r.trend.sub_state_cn && (" in src, "逐日行不再渲染细分档了"
    assert "{d.now.sub_state_cn && (" in src, "「现在」那一行不再渲染细分档了"
    # 正面: 原来的状态词还在, 没被替换
    assert "{r.trend.state_cn} 第 {r.trend.day} 天" in src, "细分档把状态词顶掉了"
    # 反面: 不许拿它取色、不许拿它判多空、不许拿它标转折
    for bad in ("trendBadgeCls(r.trend.sub_state", "sub_state)", "sub_state ==="):
        assert bad not in src, f"细分档被拿去做判断了: {bad}"
    # 说明只有一处产地 —— 两处注记说两句话就是下一个漂移点
    assert src.count("SUB_STATE_TIP") >= 3, (
        "细分档的说明没有收成一处(一个定义 + 两处引用)"
    )
