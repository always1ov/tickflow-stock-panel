"""[fork R506] 情绪周期整组撤下宏观分析页; 「当前主线」从转折页页头搬进「现在」卡; 阶段切换推送关掉。

用户先问「情绪周期呢, 我完全不知道什么对我有用, 经过一段时间测试也没观察出什么对我有用」,
听完分析(它全部由涨停梯队算出, 衡量打板情绪; 与综合分的「投机」维同一批数; 节奏比趋势持仓短)
后说:「你找最优解, 转折页面的那个显示主线我想搬回这里」。
"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

import polars as pl

from tests.frontend_source import code_of

ROOT = Path(__file__).resolve().parents[2]
REGIME = "pages/Regime.tsx"


def test_R506_情绪周期整组不再显示():
    src = code_of(REGIME)
    for gone in ("macro-phase", "情绪周期时间轴", "阶段规律", "阶段 × 主线", "主线排行",
                 "api.regimePhases", "api.regimePhaseLive", "api.regimeMainline(", "MARKET_PHASE", "PHASE_LEGEND"):
        assert gone not in src, f"宏观分析页还留着情绪周期的 {gone}"


def test_R506_当前主线进了现在卡_色与停更规矩一起搬过来():
    src = code_of(REGIME)
    card = src[src.index('aria-labelledby="macro-regime"'):]
    card = card[:card.index("</section>")]
    assert "api.todayMainline()" in src, "当前主线要和今日总览同一个后端函数出, 不在前端另算"
    assert "{ml?.stale ? '当前主线(停更)' : '当前主线'}" in card, "停更没在标题上说出来"
    assert "ml.stale ? 'text-muted' : 'text-amber-300'" in card, "主线没上琥珀 / 停更没降级成灰"
    assert "{ml.rows[0].member}" in card
    # 口径面板(宽基屏蔽 / 剔除 ST)原来挂在主线排行上, 排行撤了它得有新入口, 否则就配不了了
    assert "setFilterOpen(v => !v)" in card and "<MainlineFilterPanel" in card
    assert "filter={mainlineNow.data?.filter ?? undefined}" in card


def test_R506_转折页页头不再有主线():
    flip = code_of("pages/FlipPaper.tsx")
    head = flip[flip.index("<PageHeader"):flip.index('<div className="min-h-0 flex-1')]
    assert "主线" not in head and "mlStale" not in flip


def test_R506_当前主线接口与今日总览同一个函数出(monkeypatch):
    from app.api import today as today_api
    from app.services import market_mainline

    d = date.today() - timedelta(days=1)
    hist = pl.DataFrame({
        "date": [d, d, d], "member": ["光通信", "算力", "机器人"], "rank": [1, 2, 3],
        "score": [80.0, 70.0, 60.0], "limit_up_count": [9, 6, 4], "max_boards": [5, 3, 2],
        "leader_symbol": ["600487.sh", None, None],
    })
    monkeypatch.setattr(market_mainline, "load_mainline_history", lambda *_a, **_k: hist)
    req = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(repo=SimpleNamespace(
        store=SimpleNamespace(data_dir=ROOT)))))
    out = today_api.get_mainline(req)
    ml = out["mainline"]
    assert [r["member"] for r in ml["rows"]] == ["光通信", "算力", "机器人"]
    assert ml["stale"] is False and ml["date"] == d.isoformat()
    assert "membership_note" in out and "filter" in out

    old = date.today() - timedelta(days=30)
    monkeypatch.setattr(market_mainline, "load_mainline_history",
                        lambda *_a, **_k: hist.with_columns(pl.lit(old).alias("date")))
    assert today_api.get_mainline(req)["mainline"]["stale"] is True, "停更判定没接上"

    def boom(*_a, **_k):
        raise RuntimeError("no data")
    monkeypatch.setattr(market_mainline, "load_mainline_history", boom)
    assert today_api.get_mainline(req)["mainline"] is None, "主线取不到时不该报 500"


def test_R506_阶段切换推送关了_阶段本身照算():
    pipe = (ROOT / "backend" / "app" / "jobs" / "daily_pipeline.py").read_text(encoding="utf-8")
    assert "_push_phase_change_alert" not in pipe and '"phase_change"' not in pipe
    regime_api = (ROOT / "backend" / "app" / "api" / "regime.py").read_text(encoding="utf-8")
    assert "regime_builder.refresh_phase_labels(data_dir)" in regime_api, "阶段不该跟着停算 —— 对话里 AI 助手的 get_regime 工具还读它"
