"""[fork 增强] PRD 缺口补全: 仓位比例存储 + 组合净值回撤。"""
import json

import pytest


@pytest.fixture()
def user_data(tmp_path, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    return tmp_path


# ---------- 缺口③: 仓位比例 ----------

def test_position_weight_roundtrip(user_data):
    from app.services import positions
    entry = positions.set_position("000001.SZ", True, 10.5, weight=15)
    assert entry["weight"] == 15.0
    assert positions.load_all()["000001.SZ"]["weight"] == 15.0


def test_position_weight_optional_and_clamped(user_data):
    from app.services import positions
    assert positions.set_position("A", True, 10.0)["weight"] is None
    assert positions.set_position("B", True, 10.0, weight=150)["weight"] == 100.0
    assert positions.set_position("C", True, 10.0, weight=-5)["weight"] == 0.0
    assert positions.set_position("D", True, 10.0, weight="乱填")["weight"] is None


# ---------- 缺口④: 组合净值回撤 ----------

def test_drawdown_from_peak(user_data):
    from app.services import portfolio_history as ph
    assert ph.update("2026-08-10", 1.00)["drawdown"] == 0.0
    assert ph.update("2026-08-11", 1.10)["drawdown"] == 0.0  # 新高
    snap = ph.update("2026-08-12", 0.99)
    assert snap["peak"] == 1.10
    assert snap["drawdown"] == pytest.approx(0.10, abs=0.001)


def test_same_day_refresh_overwrites_not_appends(user_data):
    from app.services import portfolio_history as ph
    ph.update("2026-08-10", 1.00)
    ph.update("2026-08-10", 1.05)
    entries = json.loads((user_data / "user_data" / "portfolio_history.json").read_text())
    assert len(entries) == 1
    assert entries[0]["nav"] == 1.05


def test_drawdown_never_negative(user_data):
    from app.services import portfolio_history as ph
    ph.update("2026-08-10", 1.00)
    assert ph.update("2026-08-11", 1.20)["drawdown"] == 0.0
