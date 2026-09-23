"""[R449] 全站文字层级与样式 —— 取值钉在 `components/ui/`, 迁完的文件不许再写死字号。

用户: 「全局都想要像弹窗这样大的字体和样式, 看着舒服」;「你要按照标题级别, 别无脑全部
一样, 样式是肯定要改的」;「全部都要」。规范与页面清单见 `docs/ui-hierarchy.md`。
"""
from __future__ import annotations

import re

import pytest

from tests.frontend_source import SRC, code_of

TYPE_TS = "components/ui/type.ts"

#: 迁完的文件(相对 `frontend/src`)。**加进来就是承诺: 里面一处写死字号都没有了。**
MIGRATED: list[str] = [
    "components/stock-preview/PreviewHero.tsx",
    "components/stock-preview/StatusSection.tsx",
    "components/stock-preview/ChartLevelsSection.tsx",
    "components/stock-preview/ReviewSection.tsx",
    "components/ui/SectionTitle.tsx",
    "components/Layout.tsx",
    "components/PageHeader.tsx",
    "components/PageShell.tsx",
    "pages/StockAnalysis.tsx",
    "components/stock-analysis/WatchlistDecisionBoard.tsx",
    "components/stock-analysis/decision-board/cells.tsx",
    "components/stock-analysis/decision-board/ComboView.tsx",
    "components/stock-analysis/decision-board/ExportColumnsDialog.tsx",
    "components/stock-analysis/decision-board/LotsLink.tsx",
    "components/stock-analysis/decision-board/BoardSkeletonRows.tsx",
    "pages/Watchlist.tsx",
    "components/WatchlistGroups.tsx",
    "components/WatchlistGroupCards.tsx",
    "components/WatchlistGroupStatsBar.tsx",
    "components/WatchlistAddMenu.tsx",
    "components/WatchlistImportDialog.tsx",
    "components/ListColumnCustomizer.tsx",
    "components/stock-table/StockDataTable.tsx",
    "pages/Dashboard.tsx",
    "components/SealedBadge.tsx",
    "components/DimensionMembersDialog.tsx",
    "components/data/ActiveJobCard.tsx",
    "components/AdjFactorSyncGate.tsx",
    "components/DatePicker.tsx",
    "pages/Monitor.tsx",
    "components/monitor/FocusBar.tsx",
    "components/monitor/RuleEditor.tsx",
    "components/screener/SignalPicker.tsx",
    "pages/FlipPaper.tsx",
    "pages/Lots.tsx",
    "components/today/ScoreCell.tsx",
    "components/today/TodayHealthBar.tsx",
    "components/today/TrendCell.tsx",
    "components/Hint.tsx",
    "components/DateShortcuts.tsx",
    "pages/Screener.tsx",
    "components/data/SettingsModal.tsx",
    "components/ui/segmented.ts",
    "components/screener/CompositeStrategyDialog.tsx",
    "components/screener/DefaultStrategyParamsDialog.tsx",
    "components/screener/ScreenerFilter.tsx",
    "components/screener/ScreenerTable.tsx",
    "components/screener/StrategyBuilderDialog.tsx",
    "components/screener/StrategyCard.tsx",
    "components/screener/StrategyPoolDialog.tsx",
    "components/screener/StrategySettingsDialog.tsx",
    "components/screener/StrategyStoreDialog.tsx",
    "pages/Regime.tsx",
    "components/regime/SeesawPanel.tsx",
    "pages/Indices.tsx",
    "components/EChartsIntraday.tsx",
    "pages/AbnormalMoves.tsx",
    "pages/LimitUpLadder.tsx",
    "pages/Review.tsx",
    "components/LadderAiReview.tsx",
    "components/RpsRotationDialog.tsx",
    "components/financials/MarkdownRenderer.tsx",
    "pages/Signals.tsx",
    "components/signals/CustomSignalDialog.tsx",
    "components/signals/SignalTriggerActions.tsx",
    "pages/ConceptAnalysis.tsx",
    "pages/IndustryAnalysis.tsx",
    "components/ExtDimensionAnalysis.tsx",
    "components/SectorRotationCard.tsx",
    "components/SectionIntro.tsx",
    "pages/Financials.tsx",
    "components/financials/AiAnalysisDialog.tsx",
    "components/financials/AiReportBubble.tsx",
    "components/financials/ReportHistoryPanel.tsx",
    "components/financials/StockFinancialDetail.tsx",
    "components/financials/StockFinancialSearch.tsx",
    "components/financials/AiAnalysisHost.tsx",
    "components/data/DepthConfigCard.tsx",
    "components/data/EnrichedRebuildPanel.tsx",
    "components/data/ExtendHistoryPanel.tsx",
    "components/data/MinuteSyncConfig.tsx",
    "components/data/PageSettingsModal.tsx",
    "components/data/PipelineScopeConfig.tsx",
    "components/data/QuoteConfigCard.tsx",
    "components/data/RegimeConfigCard.tsx",
    "components/data/RepairDailyPanel.tsx",
    "components/data/ScheduleEditor.tsx",
    "components/data/SchemaModal.tsx",
    "components/data/SectionTitle.tsx",
    "components/data/Skeleton.tsx",
    "components/data/StatCard.tsx",
    "components/ext-data/CreateExtDialog.tsx",
    "components/ext-data/EditExtDialog.tsx",
    "components/ext-data/ExtDataApiPanel.tsx",
    "components/ext-data/ExtDataPullPanel.tsx",
    "components/ext-data/ExtDataStatCard.tsx",
    "pages/Data.tsx",
    "pages/Factors.tsx",
    "pages/factors/FactorComposite.tsx",
    "pages/factors/FactorEditor.tsx",
    "pages/factors/FactorLibrary.tsx",
    "pages/factors/GenerateFactorStrategyDialog.tsx",
    "pages/backtest/FactorDiscovery.tsx",
    "pages/backtest/MiningWorkbench.tsx",
    "pages/backtest/ResearchCandidatesDialog.tsx",
    "pages/Backtest.tsx",
    "pages/backtest/AddFactorSignalDialog.tsx",
    "pages/backtest/AutoMiningDialog.tsx",
    "pages/backtest/FactorBacktest.tsx",
    "pages/backtest/RobustnessValidation.tsx",
    "pages/backtest/StrategyBacktest.tsx",
    "pages/backtest/StrategyOptimizer.tsx",
    "pages/backtest/StrategyWalkForward.tsx",
    "pages/backtest/charts/FactorGroupNavChart.tsx",
    "pages/backtest/charts/StrategyNavChart.tsx",
    "pages/backtest/components/PicksSymbolKlineModal.tsx",
    "pages/backtest/components/TradeKlineModal.tsx",
    "pages/backtest/components/paramSweep.tsx",
    "pages/Settings.tsx",
    "pages/settings/AI.tsx",
    "pages/settings/AiProfiles.tsx",
    "pages/settings/DataSourceEditor.tsx",
    "pages/settings/DataSources.tsx",
    "pages/settings/ExtPages.tsx",
    "pages/settings/JobTimeoutCard.tsx",
    "pages/settings/Keys.tsx",
    "pages/settings/MenuSettings.tsx",
    "pages/settings/Monitoring.tsx",
    "pages/settings/System.tsx",
    "pages/settings/TickflowKeys.tsx",
    "pages/settings/Timeout.tsx",
    "components/stock-analysis/TrendStateBar.tsx",
    "components/stock-analysis/VerdictHover.tsx",
    "components/stock-analysis/FlipTradesPanel.tsx",
    "components/stock-analysis/ReviewHelpView.tsx",
    "components/stock-analysis/AnalysisKChart.tsx",
    "components/stock-analysis/TrendBacktestAllDialog.tsx",
    "components/stock-analysis/StockLevelsPanel.tsx",
    "components/stock-analysis/StockAnalysisDialog.tsx",
    "components/stock-analysis/StockAnalysisBubble.tsx",
    "components/stock-analysis/ReviewDisclosure.tsx",
    "components/stock-analysis/PriceAlertDialog.tsx",
    "components/StockInfoBar.tsx",
    "components/analysis-shared.tsx",
    "components/StockDailyKChart.tsx",
    "components/StockMultiDayIntradayChart.tsx",
    "components/EChartsMultiDayIntraday.tsx",
    "components/LastStockChip.tsx",
    "components/WarmupBadge.tsx",
    "components/ScoreLedgerDialog.tsx",
    "components/EndpointTestDialog.tsx",
    "components/AlertToast.tsx",
    "components/GroupStatsSettings.tsx",
    "components/ScoringEditor.tsx",
    "components/ExternalViewRender.tsx",
    "components/NavPager.tsx",
    "components/GlossaryDialog.tsx",
    "components/CollapsibleText.tsx",
    "components/PageErrorBoundary.tsx",
    "lib/capability-labels.tsx",
    "custom/assistant/ui/messages.tsx",
    "custom/assistant/ui/AssistantDrawer.tsx",
    "custom/assistant/ui/DailyChartCard.tsx",
    "pages/UsageNotes.tsx",
    "pages/Onboarding.tsx",
    "pages/Auth.tsx",
    "pages/ExternalPage.tsx",
    "pages/Branding.tsx",
]


def _type() -> dict[str, str]:
    src = code_of(TYPE_TS)
    return dict(re.findall(r"^\s*(\w+): '([^']*)',", src, re.M))


def test_R449_层级按级别给字号_相邻两级分得开():
    t = _type()
    assert t == {
        "page": "text-xl font-semibold tracking-tight text-foreground",       # L1 21
        "section": "text-lg font-semibold text-foreground",                  # L2 18
        "card": "text-sm font-semibold text-foreground",                     # L3 15
        "body": "text-xs text-foreground",                                   # 13
        "label": "text-micro text-muted",                                    # 11
        "reading": "text-xl font-semibold tabular-nums",                     # 21
    }, t
    # 标题三级不许撞在一档上 —— 撞了就是「无脑全部一样」
    sizes = [re.search(r"text-(\w+)", t[k]).group(1) for k in ("page", "section", "card", "body", "label")]
    assert len(set(sizes)) == 5, f"有两级用了同一个字号: {sizes}"


def test_R449_分区标题用L2_页头用L1():
    st = code_of("components/ui/SectionTitle.tsx")
    assert "TYPE.section" in st
    ph = code_of("components/PageHeader.tsx")
    assert '<h1 className="shrink-0 text-xl font-semibold' in ph, "页头标题不是 L1 那一档"


def test_R449_按钮与卡片是弹窗那一套():
    btn = code_of("components/ui/Button.tsx")
    assert "sm: 'h-8 gap-g3 px-3 text-xs'," in btn, "默认按钮不是弹窗那一档(32px 高、13px 字)"
    assert "export const OUTLINE = 'border border-border bg-surface text-foreground hover:bg-elevated'" in btn
    card = code_of("components/ui/Card.tsx")
    assert "'rounded-card border border-border bg-surface'" in card
    # 弹窗自己不再另存一份
    assert not (SRC / "components" / "stock-preview" / "SectionTitle.tsx").exists()


def test_R449_弹窗里分区标题比卡片标题大():
    """R449 之前是反的: 分区标题 15px、卡片标题 16px。"""
    rs = code_of("components/stock-preview/ReviewSection.tsx")
    assert '<span className={TYPE.card}>逐日复盘</span>' in rs
    assert "text-base font-semibold" not in rs


@pytest.mark.parametrize("rel", MIGRATED)
def test_R449_迁完的文件不许再写死字号(rel):
    src = code_of(rel)
    hits = re.findall(r"text-\[[\d.]+px\]", src)
    assert not hits, f"{rel} 迁完了却还有写死的字号: {hits}"
