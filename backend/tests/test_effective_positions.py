"""[R169] 标的级持仓合并视图: 手填标记(positions.json) ⊕ 批次登记(lots/)。

这一层要证明的核心是**手填永远压过派生** —— 用户在决策台敲进去的数字, 不能被
批次算出来的加权平均悄悄改掉; 批次只负责填空(用户没填的地方)与提示漂移。
"""
from __future__ import annotations

import json

import pytest

from app.config import settings
from app.services import effective_positions as eff
from app.services import positions as pos_svc
from app.strategy import lots as lots_domain


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    return tmp_path


def _write_positions(data_dir, mapping):
    p = data_dir / "user_data" / "positions.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(mapping, ensure_ascii=False), encoding="utf-8")


def _add_lot(data_dir, lot_id, symbol, qty, cost_price, **extra):
    lot = lots_domain.normalize_lot(
        {"id": lot_id, "symbol": symbol, "qty": qty, "cost_price": cost_price,
         "target_pct": 10, **extra}
    )
    lots_domain.save_one(data_dir, lot)
    return lot


# ── 无批次时: 与原 positions 行为完全一致 ──────────────────────
def test_no_lots_is_passthrough(data_dir):
    """没有任何批次时, 合并视图必须与 positions.load_all() 逐字段一致 ——
    否则接进 today.py / 出场线就会改变既有行为。"""
    _write_positions(data_dir, {
        "600519.SH": {"held": True, "cost": 1500.0, "weight": 12.5, "updated_at": "x"},
        "000001.SZ": {"held": False, "cost": None, "weight": None, "updated_at": "y"},
    })
    out = eff.load_all()
    assert set(out) == {"600519.SH", "000001.SZ"}
    assert out["600519.SH"]["held"] is True
    assert out["600519.SH"]["cost"] == 1500.0
    assert out["600519.SH"]["weight"] == 12.5
    assert out["600519.SH"]["cost_source"] == "manual"
    assert out["600519.SH"]["lot_count"] == 0
    assert out["000001.SZ"]["cost"] is None
    assert out["000001.SZ"]["cost_source"] is None


def test_empty_everything(data_dir):
    assert eff.load_all() == {}


# ── 手填优先 ────────────────────────────────────────────────
def test_manual_cost_wins_over_lots(data_dir):
    """决策台填过成本 → 批次算出来的均价不得覆盖它, 只能作为 lot_cost 并排显示。"""
    _write_positions(data_dir, {"600519.SH": {"held": True, "cost": 1500.0, "weight": 10.0}})
    _add_lot(data_dir, "lot_a", "600519.SH", qty=100, cost_price=1400.0)
    out = eff.load_all()["600519.SH"]
    assert out["cost"] == 1500.0
    assert out["cost_source"] == "manual"
    assert out["lot_cost"] == 1400.0          # 派生值仍带出来, 供 UI 提示不一致
    assert out["cost_drift_pct"] == pytest.approx((1500.0 - 1400.0) / 1400.0 * 100)


def test_manual_held_false_wins(data_dir):
    """用户明确标了空仓, 即使批次还没删, 也按空仓算 —— 卖出后忘删批次是常态。"""
    _write_positions(data_dir, {"600519.SH": {"held": False, "cost": None}})
    _add_lot(data_dir, "lot_a", "600519.SH", qty=100, cost_price=1400.0)
    out = eff.load_all()["600519.SH"]
    assert out["held"] is False
    assert out["lot_count"] == 1              # 批次仍如实报出, 好让 UI 提示"有批次未清"


# ── 批次填空 ────────────────────────────────────────────────
def test_lots_fill_missing_cost(data_dir):
    """标了持有但没填成本 → 用批次的加权平均补上, 并注明来源。"""
    _write_positions(data_dir, {"600519.SH": {"held": True, "cost": None, "weight": 8.0}})
    _add_lot(data_dir, "lot_a", "600519.SH", qty=100, cost_price=1000.0)
    _add_lot(data_dir, "lot_b", "600519.SH", qty=300, cost_price=1200.0)
    out = eff.load_all()["600519.SH"]
    assert out["cost"] == pytest.approx((100 * 1000 + 300 * 1200) / 400)   # 1150
    assert out["cost_source"] == "lots"
    assert out["lot_count"] == 2
    assert out["lot_qty"] == 400
    assert out["weight"] == 8.0               # 仓位% 只能手填, 批次给不出


def test_symbol_only_in_lots_appears_as_held(data_dir):
    """只在批次里登记过、决策台没标过的票, 也应出现在持仓视图里。"""
    _add_lot(data_dir, "lot_a", "300750.SZ", qty=200, cost_price=180.0)
    out = eff.load_all()
    assert "300750.SZ" in out
    assert out["300750.SZ"]["held"] is True
    assert out["300750.SZ"]["cost"] == 180.0
    assert out["300750.SZ"]["cost_source"] == "lots"
    assert out["300750.SZ"]["weight"] is None


def test_zero_qty_lots_fall_back_to_simple_average(data_dir):
    """批次可以只填成本不填数量(作者的校验允许 qty=0) —— 此时按简单平均。"""
    _add_lot(data_dir, "lot_a", "600000.SH", qty=0, cost_price=10.0)
    _add_lot(data_dir, "lot_b", "600000.SH", qty=0, cost_price=20.0)
    out = eff.load_all()["600000.SH"]
    assert out["cost"] == pytest.approx(15.0)
    assert out["lot_qty"] == 0


def test_mixed_qty_uses_only_qty_bearing_lots(data_dir):
    """一部分批次填了数量一部分没填 → 加权平均只用填了数量的, 避免 0 权重吞掉。"""
    _add_lot(data_dir, "lot_a", "600000.SH", qty=100, cost_price=10.0)
    _add_lot(data_dir, "lot_b", "600000.SH", qty=0, cost_price=99.0)
    out = eff.load_all()["600000.SH"]
    assert out["cost"] == pytest.approx(10.0)


def test_symbol_case_is_normalized(data_dir):
    """批次里的 symbol 大小写不一致时也要能与 positions 的键对上。"""
    _write_positions(data_dir, {"600519.SH": {"held": True, "cost": None}})
    _add_lot(data_dir, "lot_a", "600519.sh", qty=100, cost_price=1400.0)
    out = eff.load_all()
    assert len(out) == 1
    assert out["600519.SH"]["cost"] == 1400.0


def test_lot_without_cost_is_ignored_for_average(data_dir):
    """cost_price<=0 的批次不参与均价(作者的校验挡了, 但历史文件可能有脏数据)。"""
    _add_lot(data_dir, "lot_a", "600000.SH", qty=100, cost_price=10.0)
    lots_domain.save_one(data_dir, lots_domain.normalize_lot(
        {"id": "lot_b", "symbol": "600000.SH", "qty": 100, "cost_price": 0}))
    out = eff.load_all()["600000.SH"]
    assert out["cost"] == pytest.approx(10.0)
    assert out["lot_count"] == 2               # 条数如实报, 只是不参与算均价


def test_never_raises_on_broken_lots_dir(data_dir, monkeypatch):
    """批次读盘炸了不能拖垮持仓视图 —— 决策台/出场线/今日总览都靠它。"""
    _write_positions(data_dir, {"600519.SH": {"held": True, "cost": 1500.0}})

    def _boom(*a, **k):
        raise OSError("disk on fire")

    monkeypatch.setattr(lots_domain, "load_all", _boom)
    out = eff.load_all()
    assert out["600519.SH"]["cost"] == 1500.0
    assert out["600519.SH"]["lot_count"] == 0


# ── 写口径不变 ──────────────────────────────────────────────
def test_writes_still_go_to_positions_only(data_dir):
    """合并只在读侧。写仍然只落 positions.json, 不碰批次文件。"""
    _add_lot(data_dir, "lot_a", "600519.SH", qty=100, cost_price=1400.0)
    pos_svc.set_position("600519.SH", held=True, cost=1600.0, weight=5.0)
    raw = json.loads((data_dir / "user_data" / "positions.json").read_text(encoding="utf-8"))
    assert raw["600519.SH"]["cost"] == 1600.0
    assert lots_domain.load_all(data_dir)[0]["cost_price"] == 1400.0   # 批次原样不动
    assert eff.load_all()["600519.SH"]["cost"] == 1600.0


# ── 到期提醒 ────────────────────────────────────────────────
def test_next_remind_date_picks_nearest_future(data_dir):
    """多笔批次各有到期日时, 取最近的一个未过期的。"""
    _add_lot(data_dir, "lot_a", "600000.SH", qty=100, cost_price=10.0, remind_date="2099-12-31")
    _add_lot(data_dir, "lot_b", "600000.SH", qty=100, cost_price=10.0, remind_date="2099-01-01")
    assert eff.load_all()["600000.SH"]["next_remind_date"] == "2099-01-01"


def test_expired_remind_date_not_reported(data_dir):
    """已过期的到期日不报 —— 上游监控引擎自己会处理, 体检里再显示一次只是噪音。"""
    _add_lot(data_dir, "lot_a", "600000.SH", qty=100, cost_price=10.0, remind_date="2000-01-01")
    assert eff.load_all()["600000.SH"]["next_remind_date"] is None


def test_no_remind_date_is_none(data_dir):
    _add_lot(data_dir, "lot_a", "600000.SH", qty=100, cost_price=10.0)
    assert eff.load_all()["600000.SH"]["next_remind_date"] is None
