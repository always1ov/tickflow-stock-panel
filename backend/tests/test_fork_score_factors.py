"""[R173] 把握分维度因子: 注册进作者的因子平台, 供 IC/IR 检验。

这一组盯的核心是**口径一致**: 因子算出来的数必须与 `opportunity_score` 里那条
路算出来的逐点相等。不相等的话, 检验结果指向的就是另一个因子, 比不检验更糟。
"""
from __future__ import annotations

import polars as pl
import pytest

from app.factors.registry import get_factor
from app.services import fork_score_factors as ff
from app.services import opportunity_score as osc


@pytest.fixture(autouse=True)
def _registered():
    ff.register_all()


# ── 与 opportunity_score 逐点同口径 ──────────────────────────
@pytest.mark.parametrize("curve_name", ["VOL_RATIO_CURVE", "TURNOVER_CURVE", "POS_CURVE",
                                        "FRESH_CURVE", "RS_CURVE"])
def test_piecewise_expr_matches_scalar_version(curve_name):
    """表达式版的分段插值必须与标量版逐点相等 —— 含两端之外、拐点上、拐点之间。"""
    curve = getattr(osc, curve_name)
    xs = []
    for (x0, _), (x1, _) in zip(curve, curve[1:]):
        xs += [x0, (x0 + x1) / 2]
    xs += [curve[-1][0], curve[0][0] - 99, curve[-1][0] + 99]

    df = pl.DataFrame({"x": [float(x) for x in xs]})
    got = df.select(ff.piecewise_expr(pl.col("x"), curve).alias("y"))["y"].to_list()
    want = [osc._piecewise(float(x), curve) for x in xs]
    for x, g, w in zip(xs, got, want):
        assert g == pytest.approx(w, abs=1e-9), f"x={x}: 表达式 {g} != 标量 {w}"


def test_dim_volume_matches_scoring_blend():
    """量能维度 = 量比得分×0.7 + 换手率得分×0.3, 与 score_candidate 内部一致。"""
    rows = {"vol_ratio_5d": [1.5, 0.5, 6.0], "turnover_rate": [4.0, 0.3, 30.0]}
    df = pl.DataFrame(rows)
    got = df.select(ff.scoring_expr(set(rows), "fk_dim_volume").alias("v"))["v"].to_list()
    for i, want_vr in enumerate(rows["vol_ratio_5d"]):
        want = (osc._piecewise(want_vr, osc.VOL_RATIO_CURVE) * osc.VOLUME_WEIGHTS["vol_ratio"]
                + osc._piecewise(rows["turnover_rate"][i], osc.TURNOVER_CURVE)
                * osc.VOLUME_WEIGHTS["turnover"])
        assert got[i] == pytest.approx(want)


def test_keltner_pos_formula():
    """位置 = (close − (ma20 − 2×ATR)) / (4×ATR); 贴下轨=0, 中轨=0.5, 贴上轨=1。"""
    df = pl.DataFrame({"close": [8.0, 10.0, 12.0], "ma20": [10.0] * 3, "atr_14": [1.0] * 3})
    got = df.select(ff.keltner_pos_expr().alias("p"))["p"].to_list()
    assert got == pytest.approx([0.0, 0.5, 1.0])


def test_keltner_pos_allows_out_of_band():
    """破轨时位置可以 <0 或 >1 —— 夹住的话 POS_CURVE 右端那截(破上轨扣分)就失效了。"""
    df = pl.DataFrame({"close": [6.0, 15.0], "ma20": [10.0, 10.0], "atr_14": [1.0, 1.0]})
    got = df.select(ff.keltner_pos_expr().alias("p"))["p"].to_list()
    assert got[0] < 0 and got[1] > 1


def test_keltner_pos_null_when_atr_missing():
    """ATR 缺失/为 0 时给 null 而不是除零 —— 那天这个因子就是算不出来。"""
    df = pl.DataFrame({"close": [10.0, 10.0], "ma20": [10.0, 10.0], "atr_14": [None, 0.0]})
    got = df.select(ff.keltner_pos_expr().alias("p"))["p"].to_list()
    assert got == [None, None]


# ── 注册进作者的注册表 ──────────────────────────────────────
def test_all_five_registered_and_grouped():
    ids = [ff.PREFIX + s for s, *_ in ff._DEFS]
    assert len(ids) == 5
    for fid in ids:
        spec = get_factor(fid)
        assert spec is not None, f"{fid} 没注册上"
        assert spec.group == ff.GROUP          # 单独成组, 与作者的内置因子分开
        assert spec.kind == "virtual"
        assert "fork" in spec.tags


def test_direction_is_not_prefilled():
    """方向留 none —— 按作者的规矩以最近一次检验的 IC 符号为准。
    预填方向等于先替检验下了结论, 那这次检验就白做了。"""
    for s, *_ in ff._DEFS:
        assert get_factor(ff.PREFIX + s).direction == "none"


def test_register_is_idempotent():
    """启动钩子与 scoring 转接口都会调它, 重复调用不能报错也不能重复注册。"""
    a = ff.register_all()
    b = ff.register_all()
    assert a == b and len(a) == 5


def test_stock_only():
    """把握分只用于个股 —— 挂到 ETF 上会让因子库里出现一个永远算不出的条目。"""
    for s, *_ in ff._DEFS:
        assert get_factor(ff.PREFIX + s).asset_types == frozenset({"stock"})


# ── 转接口的边界 ────────────────────────────────────────────
def test_scoring_expr_ignores_foreign_names():
    """不是 fk_ 前缀的一概不接 —— 否则会把上游因子的分派抢过来。"""
    assert ff.scoring_expr({"close"}, "ma20_bias") is None
    assert ff.scoring_expr({"close"}, "close") is None


def test_scoring_expr_none_when_deps_missing():
    """依赖列不齐 → None(与上游其它虚拟因子同样的约定), 不能拿 null 拼个假值。"""
    assert ff.scoring_expr({"close"}, "fk_dim_position") is None
    assert ff.scoring_expr({"vol_ratio_5d"}, "fk_dim_volume") is None
    assert ff.scoring_expr({"vol_ratio_5d", "turnover_rate"}, "fk_dim_volume") is not None


def test_scoring_expr_unknown_fk_name():
    assert ff.scoring_expr({"close"}, "fk_not_a_factor") is None


def test_warmup_covers_ma20():
    """位置类因子要 MA20 + ATR14, 预热不足会在样本头部产出一段假值。"""
    for s in ("keltner_pos", "dim_position"):
        assert get_factor(ff.PREFIX + s).warmup_bars >= 21
