import { useState, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Sparkles, LineChart, History as HistoryIcon, Loader2, ExternalLink, Bell, AlertTriangle, X } from 'lucide-react'
import { PageHeader } from '@/components/PageHeader'
import { EmptyState } from '@/components/EmptyState'
import { StockFinancialSearch } from '@/components/financials/StockFinancialSearch'
import { StockPreviewDialog } from '@/components/StockPreviewDialog'
import { LastStockChip } from '@/components/LastStockChip'
import { AnalysisKChart, type PriceLevel, type LevelType } from '@/components/stock-analysis/AnalysisKChart'
import { PriceAlertDialog } from '@/components/stock-analysis/PriceAlertDialog'
import { WatchlistDecisionBoard } from '@/components/stock-analysis/WatchlistDecisionBoard'
import { TrendStateBar, useStockTrend } from '@/components/stock-analysis/TrendStateBar'
import { api } from '@/lib/api'
import { useDialogBackdrop } from '@/lib/useDialogBackdrop'
import { useLastStock } from '@/lib/useLastStock'
import { QK } from '@/lib/queryKeys'
import { toast } from '@/components/Toast'
import {
  startAnalysis, findTodayReport, openHistoryReport, loadHistory,
} from '@/lib/stockAnalysisStore'

/**
 * 个股分析页 —— 自选决策台(主体)+ 关键价位弹窗 + AI 四维分析。
 *
 * 与财务分析页的区别:
 *  - 以【自选决策台】为视觉主体:一屏纵览全部自选的现价/仓位/浮盈/出场线/六态/AI 信号
 *  - 关键价位(日 K + 压力支撑)改为点击标的后弹窗查看,不再挤占列表高度([R28])
 *  - AI 分析输出客观技术状态与风险提示(非买卖建议、非财务质量评级)
 *  - 报告胶囊用蓝色系,与财务分析(紫色)并存
 */
export function StockAnalysis() {
  const [symbol, setSymbol] = useState<string>('')
  const [name, setName] = useState<string>('')
  const [checking, setChecking] = useState(false)
  const [confirmReport, setConfirmReport] = useState<{ id: string; created_at: string; focus: string } | null>(null)
  const [previewSymbol, setPreviewSymbol] = useState<string | null>(null)
  const [showPriceAlerts, setShowPriceAlerts] = useState(false)
  // [R28] 关键价位分析弹窗:点决策台里的标的即弹出,关掉后列表原样还在
  const [showLevels, setShowLevels] = useState(false)
  const { last: lastStock, remember: rememberStock } = useLastStock('stock-analysis')

  // 进入页面立即加载历史报告(供决策台「报告」列)。store 内部有 historyLoaded 去重, 重复调用安全。
  useEffect(() => { loadHistory() }, [])

  // 自动恢复上次选中的股票(切走再回来不丢)。useLastStock 的 last 来自 localStorage, 同步可用。
  // [fork 增强] URL 带 ?symbol= 时优先(今日总览等页面点击跳转直达该票)。
  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const urlSym = (params.get('symbol') || '').trim().toUpperCase()
    if (urlSym) {
      setSymbol(urlSym)
      setName(params.get('name') || urlSym)
      return
    }
    if (!symbol && lastStock) {
      setSymbol(lastStock.symbol)
      setName(lastStock.name)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const onSelect = (sym: string, nm: string) => {
    setSymbol(sym)
    setName(nm)
    setConfirmReport(null)
    setShowPriceAlerts(false)
    rememberStock(sym, nm)
    // [R28] 选中即弹出关键价位分析 —— 页面主体已让给决策台, 不弹就等于点了没反应
    setShowLevels(true)
  }

  const handleAnalyze = async () => {
    if (!symbol || checking) return
    setChecking(true)
    try {
      // 当日已分析过 → 二次确认(查看今日报告 / 重新分析)
      const today = await findTodayReport(symbol)
      if (today) {
        setConfirmReport({ id: today.id, created_at: today.created_at, focus: today.focus })
      } else {
        await doAnalysis()
      }
    } catch {
      await doAnalysis()
    } finally {
      setChecking(false)
    }
  }

  const doAnalysis = async () => {
    const r = await startAnalysis(symbol, name)
    if (r.error) toast(r.error, 'error')
  }

  return (
    <>
      <PageHeader
        title="个股分析"
        subtitle="日 K · 关键价位 · AI 四维分析(技术 / 基本面 / 财务 / 消息面)"
        right={
          <div className="flex items-center gap-2">
            <LastStockChip stock={lastStock} onSelect={onSelect} />
          </div>
        }
      />

      <div className="w-full px-6 py-4 space-y-4">
        {/* 搜索栏 —— 窄屏时按钮整块换行, 不把「点位提醒」挤出可视区 */}
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
          <div className="w-72 shrink-0">
            <StockFinancialSearch onSelect={onSelect} assetTypes="stock,index" />
          </div>
          {symbol && (
            <>
              <button
                onClick={() => setPreviewSymbol(symbol)}
                title="查看个股日 K 详情"
                className="group flex shrink-0 items-center gap-2 text-sm rounded-md px-1.5 py-0.5 -mx-1.5 hover:bg-elevated transition-colors"
              >
                <span className="text-foreground font-medium group-hover:text-sky-300 transition-colors">{name || symbol}</span>
                <span className="text-[10px] font-mono text-muted">{symbol}</span>
                <ExternalLink className="h-3 w-3 text-muted opacity-0 group-hover:opacity-100 transition-opacity" />
              </button>
              <button
                onClick={() => setShowLevels(true)}
                className="inline-flex shrink-0 whitespace-nowrap items-center gap-1.5 px-3 py-1.5 rounded-btn border border-border bg-elevated text-secondary text-xs font-medium hover:text-foreground hover:border-sky-400/30 transition-all"
                title="打开关键价位分析(日 K + 压力支撑 + 六态趋势)"
              >
                <LineChart className="h-3.5 w-3.5" />
                关键价位
              </button>
              <button
                onClick={handleAnalyze}
                disabled={checking}
                className="inline-flex shrink-0 whitespace-nowrap items-center gap-1.5 px-3 py-1.5 rounded-btn bg-gradient-to-r from-sky-500/25 to-blue-500/15 border border-sky-400/30 text-sky-300 text-xs font-medium hover:from-sky-500/35 hover:to-blue-500/25 transition-all disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {checking ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Sparkles className="h-3.5 w-3.5" />}
                AI 个股分析
              </button>
              <button
                onClick={() => setShowPriceAlerts(true)}
                className="inline-flex shrink-0 whitespace-nowrap items-center gap-1.5 px-3 py-1.5 rounded-btn border border-sky-400/25 bg-sky-400/[0.08] text-sky-300 text-xs font-medium hover:border-sky-400/40 hover:bg-sky-400/[0.12] transition-all"
                title="设置价格点位提醒"
              >
                <Bell className="h-3.5 w-3.5" />
                点位提醒
              </button>
            </>
          )}
        </div>

        {/* 主体:自选决策台铺满整页 —— 点标的弹出关键价位分析([R28]) */}
        <WatchlistDecisionBoard currentSymbol={symbol} onSelect={onSelect} fullPage />
      </div>

      {/* [R28] 关键价位分析弹窗:日 K + 压力支撑 + 六态趋势条 */}
      {showLevels && symbol && (
        <LevelsDialog symbol={symbol} name={name} onClose={() => setShowLevels(false)} />
      )}

      {/* 二次确认:已有历史报告 */}
      {confirmReport && (
        <ConfirmModal
          report={confirmReport}
          onView={() => { openHistoryReport(confirmReport.id); setConfirmReport(null) }}
          onRedo={async () => { setConfirmReport(null); await doAnalysis() }}
          onClose={() => setConfirmReport(null)}
        />
      )}

      {/* 个股日 K 详情对话框(点击名称/代码打开) */}
      <StockPreviewDialog
        symbol={previewSymbol}
        name={previewSymbol === symbol ? name : undefined}
        triggerInfo={null}
        onClose={() => setPreviewSymbol(null)}
      />

      {showPriceAlerts && symbol && (
        <PriceAlertDialog
          key={symbol}
          symbol={symbol}
          name={name}
          onClose={() => setShowPriceAlerts(false)}
        />
      )}
    </>
  )
}

// ===== [R28] 关键价位分析弹窗 =====
// 决策台占满整页后, 关键价位不再内联切换, 而是像点股票名那样弹窗查看:
// 列表不会被推走, 看完一只关掉即可继续扫下一只。
function LevelsDialog({ symbol, name, onClose }: { symbol: string; name: string; onClose: () => void }) {
  const backdrop = useDialogBackdrop(onClose)

  // Esc 关闭 —— 弹窗高频开关, 键盘退出比找关闭按钮快
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4" {...backdrop}>
      <div className="w-full max-w-[1180px] max-h-[92vh] flex flex-col bg-surface border border-border rounded-2xl shadow-2xl overflow-hidden">
        <div className="flex items-center gap-2 px-4 py-2.5 border-b border-border/60 shrink-0">
          <LineChart className="h-4 w-4 text-sky-400 shrink-0" />
          <span className="text-sm font-medium text-foreground truncate">{name || symbol}</span>
          <span className="text-[10px] font-mono text-muted">{symbol}</span>
          <button
            onClick={onClose}
            title="关闭(Esc)"
            className="ml-auto p-1 rounded-md text-muted hover:text-foreground hover:bg-elevated transition-colors cursor-pointer"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="p-3 overflow-auto">
          <StockAnalysisBoard symbol={symbol} height={520} />
        </div>
      </div>
    </div>
  )
}

// ===== 分析看板:日 K + 关键价位 =====
function StockAnalysisBoard({ symbol, height = 480 }: { symbol: string; height?: number }) {
  const kline = useQuery({
    queryKey: ['kline', symbol, ''],
    queryFn: () => api.klineDaily(symbol, 250),
    enabled: !!symbol,
    staleTime: 60_000,
  })

  const levelsQ = useQuery({
    queryKey: QK.stockLevels(symbol),
    queryFn: () => api.stockAnalysisLevels(symbol, 250),
    enabled: !!symbol,
    staleTime: 60_000,
  })

  // [fork 增强] 六态趋势(利弗莫尔)—— 趋势条 + K 线多空分段着色
  const trendQ = useStockTrend(symbol)

  if (kline.isLoading) {
    return <div className="flex items-center justify-center py-20"><Loader2 className="h-5 w-5 animate-spin text-muted" /></div>
  }

  if (kline.isError) {
    return (
      <EmptyState
        icon={AlertTriangle}
        title="日 K 数据加载失败"
        hint="请检查网络或数据源配置后重试。"
      />
    )
  }

  const rows = kline.data?.rows ?? []
  if (rows.length === 0) {
    return <EmptyState icon={LineChart} title="暂无日 K 数据" hint="该标的尚未同步日 K,请先在数据页或自选页同步。" />
  }

  const levels = (levelsQ.data?.levels ?? {}) as Record<LevelType, PriceLevel[]>

  // [fork 增强] 六态多空分段 → K 线背景着色(多头段淡红、空头段淡绿,A 股惯例)
  const trendRanges = (trendQ.data?.segments ?? []).map(s => ({
    start: s.start_date,
    end: s.end_date,
    color: s.side === 'bull' ? 'rgba(239,68,68,0.05)' : 'rgba(34,197,94,0.05)',
  }))

  // 涨跌色:最后一根 K 线收 vs 前一根收(无前日则按开收判断)
  const last = rows[rows.length - 1]
  const prev = rows[rows.length - 2]
  const curClose = levelsQ.data?.close
  const isUp = prev ? (last.close >= prev.close) : (last.close >= last.open)

  return (
    <div className="rounded-card border border-border/60 bg-surface/40 overflow-hidden">
      <div className="px-4 py-3 border-b border-border/40">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2 min-w-0">
            <LineChart className="h-4 w-4 text-sky-400 shrink-0" />
            <span className="text-sm font-medium text-foreground">关键价位分析</span>
          </div>
          <div className="flex items-baseline gap-2 shrink-0">
            <span className="text-[10px] text-muted">{rows.length} 个交易日</span>
            <span className="text-[10px] text-muted/60">·</span>
            <span className="text-[10px] text-muted">当前价</span>
            <span className={`text-base font-mono font-bold ${isUp ? 'text-bull' : 'text-bear'}`}>
              {curClose?.toFixed(2) ?? '—'}
            </span>
          </div>
        </div>
      </div>
      <div className="p-3 space-y-2">
        {/* [fork 增强] 六态趋势条(利弗莫尔 Market Key) */}
        <TrendStateBar symbol={symbol} trend={trendQ.data} />
        <AnalysisKChart
          rows={rows}
          levels={levels}
          series={levelsQ.data?.series}
          seriesDates={levelsQ.data?.dates}
          defaultLevelTypes={['sr', 'pivot', 'keltner_s']}
          ranges={trendRanges}
          height={height}
        />
      </div>
    </div>
  )
}

// ===== 二次确认弹窗 =====
function ConfirmModal({ report, onView, onRedo, onClose }: {
  report: { id: string; created_at: string; focus: string }
  onView: () => void
  onRedo: () => void
  onClose: () => void
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4" onClick={onClose}>
      <div
        className="w-full max-w-sm bg-surface border border-border rounded-2xl p-5 shadow-2xl"
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-center gap-2 mb-2">
          <HistoryIcon className="h-4 w-4 text-sky-400" />
          <span className="text-sm font-medium text-foreground">该个股已有分析报告</span>
        </div>
        <p className="text-xs text-secondary leading-relaxed mb-1">
          最近一次报告生成于 <span className="text-foreground">{fmtRelative(report.created_at)}</span>。
        </p>
        {report.focus && <p className="text-xs text-muted mb-1">关注点: {report.focus}</p>}
        <p className="text-xs text-muted mb-4">可直接查看历史,或重新生成一份新报告。</p>
        <div className="flex gap-2">
          <button onClick={onView}
            className="flex-1 h-8 rounded-lg bg-elevated border border-border text-xs text-secondary hover:text-foreground transition-colors">
            查看历史
          </button>
          <button onClick={onRedo}
            className="flex-1 h-8 rounded-lg bg-gradient-to-r from-sky-500/20 to-blue-500/15 border border-sky-400/30 text-xs text-sky-300 hover:from-sky-500/30 transition-all">
            重新分析
          </button>
        </div>
      </div>
    </div>
  )
}

function fmtRelative(iso: string): string {
  try {
    const t = new Date(iso).getTime()
    const diff = Date.now() - t
    if (diff < 60_000) return '刚刚'
    if (diff < 3600_000) return `${Math.floor(diff / 60_000)} 分钟前`
    if (diff < 86400_000) return `${Math.floor(diff / 3600_000)} 小时前`
    if (diff < 7 * 86400_000) return `${Math.floor(diff / 86400_000)} 天前`
    return new Date(iso).toLocaleDateString('zh-CN')
  } catch { return iso }
}
