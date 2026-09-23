import { useState, useEffect } from 'react'
import { History as HistoryIcon, Bell, LocateFixed } from 'lucide-react'
import { PageHeader } from '@/components/PageHeader'
import { StockFinancialSearch } from '@/components/financials/StockFinancialSearch'
import { StockPreviewDialog, type PreviewView } from '@/components/StockPreviewDialog'
import { PriceAlertDialog } from '@/components/stock-analysis/PriceAlertDialog'
// [fork R363] 关键价位弹窗摘成了共用组件 —— 模拟盘也点标的弹它, 不抄第二份
import { LevelsDialog } from '@/components/stock-analysis/LevelsDialog'
import { WatchlistDecisionBoard } from '@/components/stock-analysis/WatchlistDecisionBoard'
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
  const [confirmReport, setConfirmReport] = useState<{ id: string; created_at: string; focus: string; symbol: string; name: string } | null>(null)
  const [previewSymbol, setPreviewSymbol] = useState<string | null>(null)
  // [R427] 个股弹窗打开时落在哪一页: 点名字 → 关键价位(默认), 点「走势/位置」→ 复盘
  const [previewView, setPreviewView] = useState<PreviewView | undefined>(undefined)
  const [showPriceAlerts, setShowPriceAlerts] = useState(false)
  // [R28] 关键价位分析弹窗:点决策台里的标的即弹出,关掉后列表原样还在
  const [showLevels, setShowLevels] = useState(false)
  // [R157] 「定位」按钮计数: 每按一次 +1, 决策台据此把当前个股那一行滚到正中
  const [locateNonce, setLocateNonce] = useState(0)
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
      setLocateNonce((k) => k + 1)   // [R157b] 从别的页跳过来: 到了就定位到它那一行
      return
    }
    if (!symbol && lastStock) {
      setSymbol(lastStock.symbol)
      setName(lastStock.name)
      setLocateNonce((k) => k + 1)   // [R157b] 恢复上次那只: 同样定位到正中
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

  // [R106] 选中但不弹任何窗(行内 ✨/🔔 用: 只要上下文跟随, 不要弹窗打断)
  const selectQuiet = (sym: string, nm: string) => {
    setSymbol(sym)
    setName(nm)
    setShowLevels(false)
    rememberStock(sym, nm)
  }

  const handleAnalyze = async (sym?: string, nm?: string) => {
    const target = sym || symbol
    const targetName = nm ?? (sym ? sym : name)
    if (!target || checking) return
    if (sym) selectQuiet(sym, targetName)
    setChecking(true)
    try {
      // 当日已分析过 → 二次确认(查看今日报告 / 重新分析)
      const today = await findTodayReport(target)
      if (today) {
        setConfirmReport({ id: today.id, created_at: today.created_at, focus: today.focus, symbol: target, name: targetName })
      } else {
        await doAnalysis(target, targetName)
      }
    } catch {
      await doAnalysis(target, targetName)
    } finally {
      setChecking(false)
    }
  }

  const doAnalysis = async (sym?: string, nm?: string) => {
    const r = await startAnalysis(sym || symbol, nm ?? name)
    if (r.error) toast(r.error, 'error')
  }

  const openPriceAlert = (sym?: string, nm?: string) => {
    if (sym) selectQuiet(sym, nm ?? sym)
    setShowPriceAlerts(true)
  }

  return (
    <>
      {/* [R104] 页头重排: 名称按钮与"上次查看"胶囊已被整合弹窗取代(列表点标的即弹),
          撤销这两个入口; AI 个股分析/点位提醒 上移到页头右侧, 搜索行只留搜索框
          和一个非交互的"当前个股"小标签(标明 AI 分析/点位提醒作用在谁身上)。 */}
      <PageHeader
        title="个股分析"
        subtitle="日 K · 关键价位 · AI 四维分析(技术 / 基本面 / 财务 / 消息面)"
      />

      {/* [R60] 统一页面留白 */}
      <div className="w-full px-3 pb-4 pt-3 lg:px-4 space-y-3">
        {/* 搜索 + 当前个股标签(纯展示, 点开弹窗走下方列表的标的名称) */}
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
          <div className="w-72 shrink-0">
            {/* [R157b] 搜索选中 = 明确的"带我去它那一行": 滚到正中并高亮, 不只是"进视野" */}
            <StockFinancialSearch
              onSelect={(s, n) => { onSelect(s, n); setLocateNonce((k) => k + 1) }}
              assetTypes="stock,index"
            />
          </div>
          {symbol && (
            <span className="inline-flex shrink-0 items-center gap-1.5 text-xs text-muted">
              当前
              <span className="font-medium text-secondary">{name || symbol}</span>
              <span className="font-mono text-micro">{symbol}</span>
              {/* [R157] 定位: 把这只票在决策台里的那一行滚到正中并闪一下。
                  不在自选 / 被「只看持有」挡住时会提示, 不会静默没反应 */}
              <button
                onClick={() => setLocateNonce((n) => n + 1)}
                title={`在决策台里定位 ${name || symbol} 那一行`}
                className="rounded p-1 text-accent/80 hover:bg-accent/10 hover:text-accent transition-colors"
              >
                <LocateFixed className="h-3.5 w-3.5" />
              </button>
              {/* [R106] 搜索出的股(可能不在自选列表)也能设提醒 —— 与列表行内同一个动作。
                  [R428] 「AI 四维分析」那个按钮从这里挪进了个股弹窗顶栏 —— 用户: 「ai 四维
                  分析想要放到弹窗里面去, 找个合适的位置, 外面就不要了」。 */}
              <button
                onClick={() => openPriceAlert()}
                title={`为 ${name || symbol} 设置价格点位提醒`}
                className="rounded p-1 text-sky-300/70 hover:bg-sky-400/10 hover:text-sky-300 transition-colors"
              >
                <Bell className="h-3.5 w-3.5" />
              </button>
            </span>
          )}
        </div>

        {/* 主体:自选决策台铺满整页 —— 点标的弹出关键价位分析([R28]) */}
        {/* [R103] 点标的名称 = 选中该股 + 弹整合版个股弹窗(与全站其他列表一致) */}
        <WatchlistDecisionBoard
          currentSymbol={symbol}
          locateNonce={locateNonce}
          onSelect={onSelect}
          onPreview={(s, n, v) => {
            onSelect(s, n)
            // 整合弹窗自带关键价位视图, 不再叠一层 R28 的关键价位弹窗
            setShowLevels(false)
            setPreviewView(v)
            setPreviewSymbol(s)
          }}
          // [R435] 行内 ✨ / 🔔 随「AI 信号」列一起撤了: AI 四维分析走个股弹窗里的入口,
          // 点位提醒走页头那个 🔔 或弹窗里双击图
        />
      </div>

      {/* [R28] 关键价位分析弹窗:日 K + 压力支撑 + 六态趋势条。
          常驻挂载、由 symbol 是否为 null 驱动, 这样关闭时退场动画能播完 */}
      <LevelsDialog
        symbol={showLevels && symbol ? symbol : null}
        name={name}
        onClose={() => setShowLevels(false)}
      />

      {/* 个股日 K 详情对话框(点击名称/代码打开) */}
      <StockPreviewDialog
        symbol={previewSymbol}
        name={previewSymbol === symbol ? name : undefined}
        triggerInfo={null}
        enableLevelsView
        initialView={previewView}
        // [R428] AI 四维分析的入口挪进了弹窗顶栏; 流程(查今日报告 → 确认)仍是这一页那一套
        onAiAnalyze={(s, n) => handleAnalyze(s, n ?? s)}
        aiBusy={checking}
        onClose={() => setPreviewSymbol(null)}
      />

      {/* 二次确认:已有历史报告
          [R428] 挪到个股弹窗**之后**渲染: 两者都是 fixed z-50, 同层级时后渲染的在上。
          AI 入口进了弹窗之后, 这个确认框是从弹窗里触发的 —— 排在前面就会被弹窗盖住,
          点了按钮看起来没反应。 */}
      {confirmReport && (
        <ConfirmModal
          report={confirmReport}
          onView={() => { openHistoryReport(confirmReport.id); setConfirmReport(null) }}
          onRedo={async () => { const t = confirmReport; setConfirmReport(null); await doAnalysis(t.symbol, t.name) }}
          onClose={() => setConfirmReport(null)}
        />
      )}


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
            className="flex-1 h-8 rounded-lg bg-accent-soft border border-sky-400/30 text-xs text-sky-300 hover:from-sky-500/30 transition-ui">
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
