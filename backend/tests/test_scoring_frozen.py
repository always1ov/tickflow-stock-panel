"""[R280] v2 把握分**冻结基线** —— 参数动了必须是有意的、看得见的。

用户: 「v2 版本的打分系统是稳定版, 不能动」「不动我稳定版本的打分系统就行」。
写进 AGENTS.md 第 13 条。

## 为什么规矩之外还要一道闸

这条规矩是用户口头定的, 而**口头规矩只在有人记得的时候有效**。本仓库已经反复
栽在同一件事上: R258 的纪律比它的守卫扫得宽, 于是后端两处旧名活了下来;
R254 的死键名单靠人记得维护, 于是 spread 复活时得手动去挑。

打分参数比那两处都危险: 改一个权重, **界面不会报错、测试不会红、用户看到的只是
排名悄悄变了**。等发现的时候已经不知道是哪一次改的。

所以这里把那几组数原样抄一份当基线。它**不阻止修改** —— 真要调参就同步改这份
基线, 那一步会出现在 diff 里、出现在 FORK_NOTES 里、需要在提交信息里解释。
**闸的作用不是不许过, 是不许悄悄过。**

## 冻结的是数, 不是文件

注释、docstring、类型标注、重构随便改 —— 只要这几组数不变。所以这份基线不用
文件哈希(那样加一行注释都会红, 很快就没人当回事了), 只钉参数本身。
"""
from __future__ import annotations

import pytest

from app.services import opportunity_score as osc

# ----------------------------------------------------------------------------
# 基线 —— 抄自 R280 当天的 opportunity_score.py, 一个数都没改
# ----------------------------------------------------------------------------
FROZEN: dict[str, object] = {
    # 三个维度之间的权重
    "WEIGHTS": {"trend": 0.45, "volume": 0.30, "position": 0.25},
    # 维度内部的因子权重
    "TREND_WEIGHTS": {"fresh": 0.55, "state": 0.25, "rs": 0.20},
    "VOLUME_WEIGHTS": {"vol_ratio": 0.70, "turnover": 0.30},
    "POSITION_WEIGHTS": {"pos": 1.0},
    # 六态状态分
    "STATE_SCORE": {"UT": 100.0, "NR": 78.0, "SR": 58.0},
    # 「逼近触发价」那一路进来时的新鲜度替代值
    "FRESH_NEAR_BREAKOUT": 82.0,
    # 五条分段曲线
    "FRESH_CURVE": ((1, 100), (2, 98), (3, 72), (4, 46), (5, 30), (8, 12), (20, 5)),
    "POS_CURVE": ((0.4, 40), (0.5, 90), (0.58, 100), (0.66, 94), (0.75, 72),
                  (0.85, 50), (1.0, 26), (1.25, 10)),
    "RS_CURVE": ((-25, 0), (-10, 18), (-3, 42), (0, 55), (6, 88), (14, 100),
                 (25, 82), (40, 48), (70, 20)),
    "VOL_RATIO_CURVE": ((0.4, 12), (0.8, 35), (1.0, 55), (1.3, 92), (1.8, 100),
                        (2.5, 92), (3.5, 58), (5.0, 30), (8.0, 12)),
    "TURNOVER_CURVE": ((0.2, 12), (1.0, 45), (2.5, 80), (5.0, 100), (10.0, 85),
                       (16.0, 58), (25.0, 30), (40.0, 12)),
}

_WHY = (
    "\n\n这是 v2 稳定版打分参数(AGENTS.md 第 13 条)。**不是不许改, 是不许悄悄改**:\n"
    "  · 真要调参 → 同步改本文件的 FROZEN 基线, 并在 FORK_NOTES 与提交信息里说清依据\n"
    "  · 只是改注释/重构 → 那不该动到这几组数, 回头看看是不是改错了地方\n"
    "  · 想让某个量重新进分 → 先走台账(score_ledger「只记不反馈」)拿到证据"
)


@pytest.mark.parametrize("name", sorted(FROZEN), ids=sorted(FROZEN))
def test_R280_打分参数没有被改动(name):
    """逐项点名。整表比一次会把「是哪一个变了」混成一条失败。"""
    assert hasattr(osc, name), f"打分参数 {name} 不见了{_WHY}"
    assert getattr(osc, name) == FROZEN[name], f"打分参数 {name} 变了{_WHY}"


def test_R280_基线覆盖了全部数值参数():
    """**这一条比上面那些重要。**

    上面是逐项比对已知的参数; 而真正的风险是**新增一个参数却没进基线** ——
    那样它可以随便改而没人知道, 基线看着还是全绿的。

    与 R272 存储注册表、R277 排序键同一条教训: 手写名单靠人记得维护, 而人不会
    记得。所以反过来枚举模块里所有大写的数值常量, 逐个要求它在基线里。
    """
    live = {
        n for n in dir(osc)
        if n.isupper() and isinstance(getattr(osc, n), (int, float, tuple, list, dict))
        and not isinstance(getattr(osc, n), bool)
    }
    # 纯文案表不算参数 —— 改中文名不影响任何一个分数, 而它归 AGENTS.md 第 12 条管
    text_only = {n for n in live
                 if isinstance(getattr(osc, n), dict)
                 and all(isinstance(v, str) for v in getattr(osc, n).values())}
    # 维度/因子的 key 常量(DIM_TREND = "trend" 之类)是标识符不是参数
    ident = {n for n in live if isinstance(getattr(osc, n), str)}
    should = live - text_only - ident
    missing = sorted(should - set(FROZEN))
    assert not missing, (
        f"这些打分参数没进冻结基线, 改了不会有人知道: {missing}{_WHY}")


def test_R280_基线里没有已经不存在的项():
    """反向: 删掉一个参数却留着基线项, 基线就开始说假话(它在守一个不存在的东西)。"""
    stale = sorted(n for n in FROZEN if not hasattr(osc, n))
    assert not stale, f"基线里这些项在打分模块里已经没有了: {stale}"


def test_R280_权重加起来仍是一():
    """不是冻结, 是**这几组数自身的不变量** —— 抄基线时抄错一位数, 上面那些
    逐项比对照样全绿(因为它们比的是同一份抄错的数)。这条独立于基线成立。"""
    for name in ("WEIGHTS", "TREND_WEIGHTS", "VOLUME_WEIGHTS", "POSITION_WEIGHTS"):
        w = getattr(osc, name)
        assert abs(sum(w.values()) - 1.0) < 1e-9, f"{name} 权重和不是 1: {sum(w.values())}"


@pytest.mark.parametrize("name", ["FRESH_CURVE", "POS_CURVE", "RS_CURVE",
                                  "VOL_RATIO_CURVE", "TURNOVER_CURVE"])
def test_R280_分段曲线的横轴必须递增(name):
    """同上, 独立于基线的不变量。`_piecewise` 按顺序找区间, 横轴乱序会静默算错 ——
    不报错, 只是分数不对。"""
    xs = [x for x, _y in getattr(osc, name)]
    assert xs == sorted(xs), f"{name} 的横轴不是递增的: {xs}"


def test_R280_几何量仍然不进打分():
    """[R229 的剥离] 界面上「不进把握分」那句话得一直是真的。

    与 `test_pace_wording.py` 里那条同源 —— 这里再钉一次是因为这份文件才是
    「打分层不许长出新东西」的看门人, 而那边是「措辞不许说假话」的看门人。
    """
    from pathlib import Path
    src = Path(osc.__file__).read_text(encoding="utf-8")
    code = "\n".join(ln for ln in src.splitlines() if not ln.lstrip().startswith("#"))
    for banned in ("spread", "accel", "keltner_geometry"):
        assert banned not in code, (
            f"打分层出现了 `{banned}` —— 几何量自 R229 起整层不进把握分{_WHY}")


def test_R280_AGENTS里那条规矩指向的是这个文件():
    """同上 —— 规矩与它的执行处得对得上, 否则第 13 条就只是一句没人执行的话。"""
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    doc = (root / "AGENTS.md").read_text(encoding="utf-8")
    assert "稳定版打分系统，冻结" in doc, "AGENTS.md 第 13 条没了"
    rel = "backend/tests/test_scoring_frozen.py"
    assert rel in doc, f"规矩没指向执行处({rel})"
    assert (root / rel).exists()
