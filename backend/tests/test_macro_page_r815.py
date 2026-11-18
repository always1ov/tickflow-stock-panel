"""[R815] 市场环境页回到作者版 —— 页签与情绪周期整组都在。

R503 / R505 / R506 曾按「一页平铺、撤页签、撤情绪周期、删四块」写过 14 条守卫。
R809 用户选了方案 A(全量同步作者), R815 再次确认「保留作者版: 恢复页签 + 情绪周期」。
那 14 条据此作废, 但它们守的通用性质一条没丢, 只是锚点换到作者版:
两个页签可键盘切换 / 两组面板互斥 / 两页共用一组时间范围 / 趋势图有自己的容器与句柄 /
四维四条上下叠且轨道在白底上看得见 / 页名与菜单同名 / 当前主线仍与今日总览同一个后端函数 /
阶段切换照算但不推手机。

**不要再按 R503 那套把它改成平铺** —— 同一页里两套设计轮流上, 每次都要重写这组守卫。
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

import polars as pl

from tests.frontend_source import code_of

ROOT = Path(__file__).resolve().parents[2]
REGIME = "pages/Regime.tsx"
REGIME_CSS = "pages/Regime.css"


def _src() -> str:
    return code_of(REGIME)


# ================================================================
# 页签: 两个都在, 键盘能换
# ================================================================

def test_R815_两个页签都在_键盘能换():
    """页签不是装饰: 它把两组内容真的隔开(单页高度减半), 键盘也得能用。

    撤掉页签的代价不是少两个按钮 —— 是情绪周期整组没有落脚处。
    """
    s = _src()
    assert 'role="tablist" aria-label="市场环境视图"' in s
    assert "id={`regime-tab-${k}`}" in s and 'role="tab"' in s
    assert "aria-selected={view === k}" in s, "页签没有选中态, 读屏不知道在哪一页"
    assert "aria-controls={`regime-panel-${k}`}" in s, "页签没关联到面板"
    assert "tabIndex={view === k ? 0 : -1}" in s, "两个页签都在 Tab 序列里, 要多按一次"
    for key in ("event.key === 'Home'", "event.key === 'End'", "'ArrowLeft', 'ArrowRight'"):
        assert key in s, f"页签少了键盘处理: {key}"
    assert "setView(next)" in s and "?.focus()" in s, "键盘换了页签却没把焦点带过去"


def test_R815_两个面板互斥且都登记了属于谁():
    """面板用 `hidden` 互斥(不是条件渲染) —— 切回来时不丢滚动位置与图实例。"""
    s = _src()
    for k in ("phase", "regime"):
        assert (
            f'id="regime-panel-{k}" role="tabpanel" '
            f'aria-labelledby="regime-tab-{k}" hidden={{view !== \'{k}\'}}'
        ) in s, f"{k} 面板的 tabpanel 三件套不齐"


# ================================================================
# 情绪周期整组都在
# ================================================================

def test_R815_情绪周期整组都在():
    """R506 撤过它, R815 又请回来了 —— 那就把「整组」逐块点名,
    免得哪天同步上游时悄悄少一块(只少一块最难看: 页面不报错, 只是永远看不到阶段规律)。"""
    s = _src()
    for kept in ("当前阶段", "阶段规律", "情绪周期时间轴", "阶段 × 主线", "主线排行"):
        assert kept in s, f"情绪周期少了「{kept}」"
    assert "api.regimePhases(" in s and "api.regimeMainline(" in s
    assert "MARKET_PHASE_GUIDE" in s and "MARKET_PHASE_LABELS" in s, "阶段的名词/图例没接上"


# ================================================================
# 市场环境这一组: 四块 + 四维
# ================================================================

def test_R815_环境四块都在():
    """状态时间轴 / 状态分布 / 日历热力图 / 环境综合分趋势 —— 四块各自是作者版的内容,
    数据同源但回答的问题不同(何时 / 占比 / 哪天 / 走向)。"""
    s = _src()
    for kept in ('title="状态时间轴"', 'title="状态分布"', 'title="日历热力图"', 'title="环境综合分趋势"'):
        assert kept in s, f"市场环境少了 {kept}"
    for aria in ('aria-label="最新环境状态"', 'aria-label="环境四维拆解"', 'aria-label="环境运行节奏"'):
        assert aria in s, f"市场环境少了 {aria}"


def test_R815_四维四条上下叠_轨道在白底上看得见():
    """[R510/R511 的教训搬过来] 四条被拉到半屏长、0 分那维什么都没画 —— 根因是轨道
    用了页底色 `--base`: R501 之后页底纯白, 轨道在白底上就是隐形。作者版的 CSS 里
    也踩了同一个坑, 这里按性质钉住: 四条是 grid 上下叠, 轨道必须是 `--elevated`。
    """
    s, css = _src(), code_of(REGIME_CSS)
    seg = s[s.index('aria-label="环境四维拆解"'):]
    seg = seg[:seg.index("</section>")]
    for dim in ("profit_score", "speculation_score", "resilience_score", "trend_score"):
        assert dim in seg, f"四维拆解少了 {dim}"
    assert "regime-dimensions" in seg and "regime-track" in seg
    assert "grid-template-columns" not in seg, "四条又被排成一横排了"
    assert "Math.max(0, Math.min(100," in seg, "比例没夹在 0~100, 0 分那一维会画反"

    assert ".regime-dimensions { display: grid;" in css
    for cls in (".regime-track", ".regime-score-meter"):
        line = next(ln for ln in css.splitlines() if ln.startswith(cls))
        assert "var(--elevated)" in line, f"{cls} 的轨道又用了页底色, 白底上看不见"


# ================================================================
# 共用一组时间范围 / 趋势图容器
# ================================================================

def test_R815_两页共用一组时间范围():
    """两个页签只有一组时间范围 —— 各页各带一个的话, 切过去数字对不上, 人会以为页面算错了。"""
    s = _src()
    assert len(re.findall(r"useState<RangePreset>", s)) == 1, "时间范围不止一组了"
    assert "resolveHistoryRange(range, coverage.data)" in s
    assert "api.regimeHistory(histRange.start, histRange.end, histRange.limit)" in s


def test_R815_趋势图有自己的容器与句柄():
    """图实例挂在 `trendRef` 上、随 `view` 重画 —— 页签切换后 canvas 尺寸会变,
    不重建就只剩半张图(这正是作者版用 `[trendOption, view]` 的原因)。"""
    s = _src()
    assert 'title="环境综合分趋势"' in s and "ref={trendRef}" in s
    assert "const trendRef = useEChart(trendOption, [trendOption, view])" in s
    assert "export const TREND_LEGEND" in s, "图例项没单独导出, 手机上加一条就会折行"


# ================================================================
# 页名 / 主线 / 推送 —— 这三条跨页, 和页签无关
# ================================================================

def test_R815_页名与菜单同名_市场环境():
    s = _src()
    assert "<h1>市场环境</h1>" in s, "页名又不叫市场环境了"
    assert "{ id: '/regime', label: '市场环境', icon: IconRegime }" in code_of("lib/navigation.ts")
    assert "getNavigationEntries(" in code_of("pages/settings/MenuSettings.tsx")


def test_R815_转折页页头不再有主线():
    # [R564] 转折页并进虚拟账户, 页头那几样(天气 / 刷新)挂到了「跟六态转折」信号块的标题行上
    flip = code_of("components/paper/FlipFollowCard.tsx")
    head = flip[flip.index("<span className=\"text-sm font-medium\">信号</span>"):flip.index("{q.isLoading ? (")]
    assert "主线" not in head and "mlStale" not in flip


def test_R815_当前主线接口与今日总览同一个函数出(monkeypatch):
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


def test_R815_阶段切换推送关了_阶段本身照算():
    pipe = (ROOT / "backend" / "app" / "jobs" / "daily_pipeline.py").read_text(encoding="utf-8")
    assert "_push_phase_change_alert" not in pipe and '"phase_change"' not in pipe
    regime_api = (ROOT / "backend" / "app" / "api" / "regime.py").read_text(encoding="utf-8")
    assert "regime_builder.refresh_phase_labels(data_dir)" in regime_api, (
        "阶段不该跟着停算 —— 对话里 AI 助手的 get_regime 工具还读它")
