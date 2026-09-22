"""[R435] AI 信号整套停用。

用户: 「清除了ai信号这部分, 后续我打算用斐波那契二型重做这部分, 但现在不做」。
三条答复: 整套停掉; 持仓档位的「加仓」不再出现; 那一列头一行的三个入口
(报告胶囊 / 行内 ✨AI 四维分析 / 🔔点位提醒)一起去掉。

这里钉「撤干净了」—— 生成、接口、定时、界面、下游用法一处不留, 免得哪天一半
被接回来(比如只恢复了前端那一列, 后端却没有数据, 表上一片「未分析」)。
各处行为变化另由改过的原守卫钉: 持仓档位见 test_today_r13 / test_keltner_stance,
「怎么办」见 test_stock_playbook / test_playbook_combo_matrix, 定时见
test_scheduled_ai_jobs, 列宽见 test_board_columns。
"""
from __future__ import annotations

import importlib.util
import inspect
from pathlib import Path

from tests.frontend_source import code_of

BACKEND = Path(__file__).resolve().parents[1] / "app"
FRONT = Path(__file__).resolve().parents[2] / "frontend" / "src"


def test_生成那一支没了():
    assert importlib.util.find_spec("app.services.stock_signal") is None
    sa = (BACKEND / "api" / "stock_analysis.py").read_text(encoding="utf-8")
    assert '@router.get("/signals")' not in sa and '@router.post("/signal/{symbol}")' not in sa
    st = (BACKEND / "api" / "settings.py").read_text(encoding="utf-8")
    assert "signal-ai-schedule" not in st.replace("# [R435] GET / PUT /preferences/signal-ai-schedule", "")


def test_今日总览从源头断成空():
    from app.api import today
    src = inspect.getsource(today._build_overview)
    assert "signals: dict[str, dict] = {}" in src, "今日总览又读回了 AI 信号"
    assert "stock_signal" not in src
    params = inspect.signature(today.holding_stance).parameters
    assert "ai_signal" not in params and "trend_signal" not in params
    notes = inspect.getsource(today._annotations)
    # 看代码的形状不看字: 说明里要写「AI 看多 / AI 看空 那一枚撤了」, 那几个字会出现
    assert '"key": "ai"' not in notes and "sig.get(" not in notes
    assert list(inspect.signature(today._annotations).parameters) == ["sym", "e"]


def test_界面上撤干净了():
    board = code_of("components/stock-analysis/WatchlistDecisionBoard.tsx")
    for gone in ("AI 信号", "stockSignals", "generateStockSignal", "AiActions", "SIGNAL_META",
                 "watch_points", "runBatch", "openHistoryReport"):
        assert gone not in board, f"决策台还留着 {gone}"
    api = code_of("lib/api.ts")
    for gone in ("stockSignals:", "generateStockSignal:", "signalAiScheduleGet", "SignalAiSchedule"):
        assert gone not in api, f"api.ts 还留着 {gone}"
    qk = code_of("lib/queryKeys.ts")
    assert "stockSignals" not in qk and "signalAiSchedule" not in qk
    alert = code_of("components/stock-analysis/PriceAlertDialog.tsx")
    assert "stockSignals" not in alert and "watch_points" not in alert, "价位提醒还在读 AI 预案"
    assert "定时个股信号" not in code_of("components/today/TodayControls.tsx")
    assert not (FRONT / "lib" / "signalFreshness.ts").exists()
    export = code_of("lib/decisionBoardExportColumns.ts")
    assert "key: 'signal'" not in export and "key: 'confidence'" not in export


def test_页面不再给决策台传那两个入口():
    page = code_of("pages/StockAnalysis.tsx")
    call = page[page.index("<WatchlistDecisionBoard"):]
    call = call[:call.index("/>")]
    assert "onAnalyze=" not in call and "onPriceAlert=" not in call
    # 弹窗里的 AI 四维分析入口还在(用户选「一起去掉」的理由正是它)
    assert "onAiAnalyze={(s, n) => handleAnalyze(s, n ?? s)}" in page
