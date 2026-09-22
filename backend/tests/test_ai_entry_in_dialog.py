"""[R428] AI 四维分析的入口从个股分析页头挪进个股弹窗。

用户: 「ai 四维分析想要放到弹窗里面去, 找个合适的位置, 外面就不要了」。
"""
from tests.frontend_source import code_of

PAGE = "pages/StockAnalysis.tsx"
DLG = "components/StockPreviewDialog.tsx"


def test_R428_页头不再有AI四维分析按钮():
    page = code_of(PAGE)
    assert "handleAnalyze()" not in page, "页头那个「对当前个股 AI 分析」的按钮又回来了"
    assert "<Sparkles" not in page, "页面上还画着 AI 那颗星"


def test_R428_弹窗顶栏有入口_作用在弹窗当前这只():
    dlg = code_of(DLG)
    assert "onAiAnalyze?: (symbol: string, name?: string) => void" in dlg
    btn = dlg[dlg.index("{onAiAnalyze && symbol && ("):]
    btn = btn[:btn.index("</button>")]
    assert "onAiAnalyze(symbol, name)" in btn, "按钮没把弹窗当前这只(含弹窗里切过的)传出去"
    assert "disabled={aiBusy}" in btn, "查今日报告期间没防连点"
    # 位置: 与「自选」「加监控」同一组(对这只票做的事), 排在刷新之前
    assert dlg.index("{onAiAnalyze && symbol && (") < dlg.index("onClick={handleRefresh}")
    assert dlg.index('title="加监控"') < dlg.index("{onAiAnalyze && symbol && (")


def test_R428_确认框排在弹窗之后_不会被弹窗盖住():
    """两者都是 fixed z-50, 同层级时后渲染的在上。入口进了弹窗之后, 「今日已分析过」
    那个确认框是从弹窗里触发的 —— 排在前面就被盖住, 点了看起来没反应。"""
    page = code_of(PAGE)
    assert page.index("<StockPreviewDialog") < page.index("<ConfirmModal"), (
        "确认框渲染在个股弹窗前面了 —— 会被弹窗盖住")
    call = page[page.index("<StockPreviewDialog"):]
    call = call[:call.index("/>")]
    assert "onAiAnalyze=" in call and "aiBusy={checking}" in call, "页面没把 AI 入口接进弹窗"
