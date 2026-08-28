import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Sparkles, LineChart, History as HistoryIcon, Loader2, ExternalLink, Bell, X, Maximize2, Minimize2 } from 'lucide-react'
import { PageHeader } from '@/components/PageHeader'
import { StockFinancialSearch } from '@/components/financials/StockFinancialSearch'
import { StockPreviewDialog } from '@/components/StockPreviewDialog'
import { LastStockChip } from '@/components/LastStockChip'
import { PriceAlertDialog } from '@/components/stock-analysis/PriceAlertDialog'
import { StockLevelsPanel, StockLevelsPriceTag } from '@/components/stock-analysis/StockLevelsPanel'
import { WatchlistDecisionBoard } from '@/components/stock-analysis/WatchlistDecisionBoard'
import { cn } from '@/lib/cn'
import { useDialogBackdrop } from '@/lib/useDialogBackdrop'
import { useLastStock } from '@/lib/useLastStock'
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

      {/* [R60] 统一页面留白 */}
      <div className="w-full px-3 pb-4 pt-3 lg:px-4 space-y-3">
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
        <WatchlistDecisionBoard currentSymbol={symbol} onSelect={onSelect} />
      </div>

      {/* [R28] 关键价位分析弹窗:日 K + 压力支撑 + 六态趋势条。
          常驻挂载、由 symbol 是否为 null 驱动, 这样关闭时退场动画能播完 */}
      <LevelsDialog
        symbol={showLevels && symbol ? symbol : null}
        name={name}
        onClose={() => setShowLevels(false)}
      />

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
// 决策台占满整页后, 关键价位不再内联切换, 而是弹窗查看: 列表不会被推走,
// 看完一只关掉即可继续扫下一只。动效/尺寸/可放大都对齐个股日 K 详情弹窗
// (StockPreviewDialog), 两个弹窗手感一致, 不会一个丝滑一个生硬。
function LevelsDialog({ symbol, name, onClose }: { symbol: string | null; name: string; onClose: () => void }) {
  const [maximized, setMaximized] = useState(false)
  const backdrop = useDialogBackdrop(onClose)

  // Esc 关闭 —— 弹窗高频开关, 键盘退出比找关闭按钮快
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  // 关掉时重置放大态, 下次开回到常规尺寸
  useEffect(() => { if (!symbol) setMaximized(false) }, [symbol])

  return (
    <AnimatePresence>
      {symbol && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
            className="absolute inset-0 bg-black/60 backdrop-blur-sm"
            {...backdrop}
          />
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: 12 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.97, y: 8 }}
            transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
            className={cn(
              'relative rounded-card border border-border bg-base shadow-2xl overflow-hidden flex flex-col transition-all duration-200 ease-smooth',
              maximized ? 'w-screen h-screen max-w-none max-h-none' : 'w-[92vw] max-w-[1100px] max-h-[95vh]',
            )}
          >
            {/* 顶栏: 与个股日 K 弹窗同款 —— 代码 + 名称在左, 行情摘要与操作在右 */}
            <div className="flex shrink-0 items-center justify-between gap-3 px-4 py-3 sm:px-5">
              <div className="flex min-w-0 items-center gap-2">
                <LineChart className="h-4 w-4 shrink-0 text-sky-400" />
                <span className="shrink-0 font-mono text-sm font-medium text-foreground">{symbol}</span>
                {name && <span className="truncate text-xs text-muted">{name}</span>}
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <StockLevelsPriceTag symbol={symbol} />
                <button
                  onClick={() => setMaximized(v => !v)}
                  title={maximized ? '缩小' : '放大'}
                  className="rounded-md p-1 text-muted transition-colors hover:bg-elevated hover:text-foreground"
                >
                  {maximized ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}
                </button>
                <button
                  onClick={onClose}
                  title="关闭(Esc)"
                  className="rounded-md p-1 text-muted transition-colors hover:bg-elevated hover:text-foreground"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
            </div>
            <div className="flex-1 overflow-auto px-4 pb-4 sm:px-5">
              {/* bare: 去掉内层卡片外框与标题条 —— 弹窗里再套一层框正是"辣眼睛"的来源 */}
              <StockLevelsPanel symbol={symbol} bare height={maximized ? 720 : 520} />
            </div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
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
