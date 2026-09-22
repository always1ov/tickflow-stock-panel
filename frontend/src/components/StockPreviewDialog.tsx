import { useEffect, useMemo, useRef, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { motion, AnimatePresence } from 'framer-motion'
import { X, RefreshCw, Clock, LineChart, Star, RadioTower, Maximize2, Minimize2, Activity, Crosshair, CalendarRange, Sparkles, Loader2 } from 'lucide-react'
import { api } from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import { cn } from '@/lib/cn'
import { cnSignal } from '@/lib/signals'
import { useCustomSignalNames } from '@/lib/useCustomSignalNames'
import { fmtPct, cnDateFromUtc } from '@/lib/format'
import { StockPanel, getDefaultRange } from '@/components/StockPanel'
import { NavPager, NavWrapToast } from '@/components/NavPager'
import { WatchlistAddMenu } from '@/components/WatchlistAddMenu'
import { StockMultiDayIntradayChart } from '@/components/StockMultiDayIntradayChart'
import { DatePicker } from '@/components/DatePicker'
import { RuleEditor } from '@/components/monitor/RuleEditor'
import { PriceAlertDialog } from '@/components/stock-analysis/PriceAlertDialog'
import { StockLevelsPanel, StockLevelsPriceTag, useAnalysisKline } from '@/components/stock-analysis/StockLevelsPanel'
import { useLevelControls } from '@/components/stock-analysis/levelControls'
import { StockReviewPanel, type ReviewTab } from '@/components/stock-analysis/StockReviewDialog'
import { HERO_DAYS_DEFAULT, PreviewHero } from '@/components/stock-preview/PreviewHero'
import { ChartLevelsSection, type ChartView } from '@/components/stock-preview/ChartLevelsSection'
import { ReviewSection } from '@/components/stock-preview/ReviewSection'
import { StatusSection } from '@/components/stock-preview/StatusSection'
import { PILL, PILL_IDLE, PILL_ON } from '@/components/stock-preview/pill'
import { StockFinancialSearch } from '@/components/financials/StockFinancialSearch'
import { buildMonitorPriceLines } from '@/lib/price-alerts'
import { usePreferences } from '@/lib/useSharedQueries'
import { setFocusSymbol, clearFocusSymbol } from '@/lib/useQuoteStream'
import { useDialogBackdrop } from '@/lib/useDialogBackdrop'
import { storage } from '@/lib/storage'
import { navItemKey, type NavItem } from '@/lib/listNav'
import { useListNav } from '@/lib/useListNav'
import { DEFAULT_INTRADAY_DAYS } from '@/lib/kline'
import { ExtensionSlot } from '@/extensions/ExtensionSlot'

interface Props {
  symbol: string | null
  name?: string
  onClose: () => void
  /** 是否开放“关键价位”视图。[R103] 全站统一弹窗后默认开启 —— 自选/监控/异动
      等所有入口与策略页、个股分析页看到同一套三视图(日K/分时/关键价位)。 */
  enableLevelsView?: boolean
  /** 触发信息 (来自监控触发记录, 有值时在顶栏下方显示) */
  triggerInfo?: {
    price?: number | null
    changePct?: number | null
    ts?: number
    signals?: string[]
    message?: string
  } | null
  /** 有序候选列表: 提供后支持左右键/顶栏按钮切股, 标题栏显示 n/N */
  navList?: NavItem[]
  /** 切股回调: 收到目标 symbol/name, 由调用方更新预览状态 */
  onNavigate?: (symbol: string, name?: string) => void
  /**
   * [R427] 打开时落在哪一页。不传 = 「关键价位」(R185 的默认)。
   * 决策台点「走势/位置」时传 'review' —— 复盘原来是另一个弹窗, 现在是这里的一页。
   */
  initialView?: PreviewView
  /** [R427] 落在复盘页时先看哪一张: 趋势状态 / 通道档位 */
  reviewTab?: ReviewTab
  /**
   * [R428] AI 四维分析(技术 / 基本面 / 财务 / 消息面)。传了才在顶栏操作区出这个按钮。
   * 流程(今日已分析过 → 确认查看 / 重新分析)仍归调用方, 这里只是入口 ——
   * 用户: 「ai 四维分析想要放到弹窗里面去, 找个合适的位置, 外面就不要了」。
   */
  onAiAnalyze?: (symbol: string, name?: string) => void
  /** [R428] 调用方正在查今日报告 / 发起分析 —— 按钮转圈并禁用, 防连点 */
  aiBusy?: boolean
}

// ===== 板块标识（与 Screener 列表一致）=====

// 预设快捷范围（只保留半年和1年）
const PRESETS: { label: string; months: number }[] = [
  { label: '半年', months: 6 },
  { label: '1年', months: 12 },
]

export type PreviewView = 'daily' | 'intraday' | 'levels' | 'review'
interface PriceAlertDraft {
  id: number
  targetPrice: number
  currentPrice: number
}
const INTRADAY_DAY_OPTIONS = [1, 5, 10, 20] as const

function loadIntradayDays(): number {
  const saved = storage.stockPreviewIntradayDays.get(DEFAULT_INTRADAY_DAYS)
  return INTRADAY_DAY_OPTIONS.includes(saved as typeof INTRADAY_DAY_OPTIONS[number])
    ? saved
    : DEFAULT_INTRADAY_DAYS
}

function boardTag(symbol: string): { label: string; color: string } | null {
  if (/^(300|301)/.test(symbol)) return { label: '创', color: 'text-[#f97316] bg-[#f97316]/12 border-[#f97316]/25' }
  if (/^688/.test(symbol))       return { label: '科', color: 'text-purple-400 bg-purple-400/12 border-purple-400/25' }
  if (/^[48]/.test(symbol))      return { label: '北', color: 'text-cyan-400 bg-cyan-400/12 border-cyan-400/25' }
  return null
}

// ===== 异动边缘 (与异动页同口径) =====

const AB_STATUS_META: Record<string, { label: string; cls: string; bar: string; icon: string }> = {
  triggered: { label: '已触发', cls: 'bg-danger/20 text-danger font-semibold', bar: 'border-b border-danger/30 bg-danger/[0.08]', icon: 'text-danger' },
  edge: { label: '异动边缘', cls: 'bg-warning/20 text-warning font-semibold', bar: 'border-b border-warning/30 bg-warning/[0.07]', icon: 'text-warning' },
  watch: { label: '观察', cls: 'bg-elevated text-secondary font-semibold', bar: 'border-b border-border bg-surface', icon: 'text-secondary' },
}

/** 异动引擎计算时间 (服务端 asof 秒级时间戳 → 月-日 时:分:秒) */
function fmtAbnormalCalcTime(asofSec: number): string {
  const d = new Date(asofSec * 1000)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

// [R100] 全局最近查看 —— 所有入口共用一份(弹窗内随意切换的数据源)
const RECENT_MAX = 8

function pushRecentStock(symbol: string, name?: string) {
  const rows = storage.recentStocks.get([])
  const known = rows.find(r => r.symbol === symbol)
  const merged = [
    { symbol, name: name || known?.name || symbol },
    ...rows.filter(r => r.symbol !== symbol),
  ].slice(0, RECENT_MAX)
  storage.recentStocks.set(merged)
  return merged
}

export function StockPreviewDialog({ symbol: symbolProp, name: nameProp, onClose, triggerInfo, enableLevelsView = true, navList: navListSource, onNavigate, initialView, reviewTab = 'trend', onAiAnalyze, aiBusy = false }: Props) {
  // [R164] 作者的 navList/onNavigate 方向键切股与 fork R100 的最近查看并存: 父级 onNavigate 更新
  // symbolProp 后, 下面的 useEffect 会清掉内部 override, 两套不打架。
  // [R100] 弹窗内随意切换: 内部覆盖当前查看的股票; 外部换股/重开时回到外部指定。
  // 好处是全站 11 个调用方零改动 —— 它们只负责"打开哪只", 切换是弹窗自己的事。
  const [override, setOverride] = useState<{ symbol: string; name?: string } | null>(null)
  useEffect(() => { setOverride(null) }, [symbolProp])
  // 父级关闭(symbolProp=null)时 override 立即失效 —— 不能让内部切换把弹窗"扣住"
  const symbol = symbolProp ? (override?.symbol ?? symbolProp) : null
  const name = symbolProp && override ? override.name : nameProp
  // 最近查看: 打开/切换都记一笔(带上已知名称)
  const [recent, setRecent] = useState(() => storage.recentStocks.get([]))
  useEffect(() => {
    if (symbol) setRecent(pushRecentStock(symbol, name))
  }, [symbol, name])
  // [R185] 默认落在「关键价位」而不是日K —— 这个弹窗是拿来做决策的, 图表模块
  // 自己的注释也写着「本图表面向分析决策, 核心是关键价位」。点进来先看到的
  // 该是压力/支撑/枢轴那几条线, 而不是一根还要自己看的 K 线。
  const [view, setView] = useState<PreviewView>(initialView ?? 'levels')
  // [R429] 60 / 120 / 250 日 —— 新头部与复盘页**同一个值**(用户: 「直接按照图片」放在头部)
  const [reviewDays, setReviewDays] = useState<number>(HERO_DAYS_DEFAULT)
  // [R430] 新「图表与价位」那一块自己的视图(旧顶栏那一组还管着下面的旧内容, 两不相干),
  // 以及右侧价位列表与图共用的开关状态。都不随切股重置 —— 与旧的关键价位页一样,
  // 方向键翻票时开着的那几类、看的那个视图都留着。
  const [chartView, setChartView] = useState<ChartView>('levels')
  const levelCtl = useLevelControls()
  const [intradayDays, setIntradayDays] = useState<number | null>(loadIntradayDays)
  const [dateRange, setDateRange] = useState(getDefaultRange)
  const [showMonitorEditor, setShowMonitorEditor] = useState(false)
  const customNames = useCustomSignalNames()
  const [priceAlertDraft, setPriceAlertDraft] = useState<PriceAlertDraft | null>(null)
  const [maximized, setMaximized] = useState(false)
  const qc = useQueryClient()
  const backdrop = useDialogBackdrop(onClose)

  const watchlist = useQuery({
    queryKey: QK.watchlist,
    queryFn: api.watchlistList,
    enabled: !!symbol,
  })
  const monitorRules = useQuery({
    queryKey: QK.monitorRules,
    queryFn: api.monitorRulesList,
    enabled: !!symbol,
  })
  // 异动边缘: 与异动页同 queryKey 共享缓存; 该股处于观察/边缘/触发状态时在图表上方显示信息条
  const abnormal = useQuery({
    queryKey: QK.abnormalOverview(0.5, 300),
    queryFn: () => api.abnormalOverview(0.5, 300),
    enabled: !!symbol,
  })
  const abRow = symbol
    ? abnormal.data?.rows.find(r => r.symbol === symbol)
    : undefined
  // 接近度最高的窗口 (信息条中高亮)
  const abDominantWindow = abRow
    ? Object.entries(abRow.windows).reduce(
        (best, [k, w]) => (!best || w.closeness > best[1].closeness ? [k, w] as const : best),
        undefined as undefined | readonly [string, { value: number; threshold: number; closeness: number }],
      )
    : undefined
  const monitorPriceLines = useMemo(
    () => symbol ? buildMonitorPriceLines(monitorRules.data?.rules ?? [], symbol) : [],
    [monitorRules.data?.rules, symbol],
  )
  const watchlistEntry = useMemo(
    () => (watchlist.data?.symbols ?? []).find(s => s.symbol === symbol),
    [watchlist.data, symbol],
  )
  const inWatchlist = !!watchlistEntry
  // 加入自选日 (北京时间)。该日不在当前K线区间内或恰是非交易日时竖线不画, 由工具栏文字兜底。
  const addedDate = useMemo(
    () => cnDateFromUtc(watchlistEntry?.added_at) || null,
    [watchlistEntry],
  )

  const toggleWatchlist = useMutation({
    mutationFn: ({
      action,
      groupId,
    }: {
      action: 'add' | 'remove'
      groupId?: string | null
    }) => action === 'remove'
      ? api.watchlistRemove(symbol!)
      : api.watchlistAdd(symbol!, '', groupId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: QK.watchlist })
      qc.invalidateQueries({ queryKey: ['watchlist-enriched'] })
    },
  })

  // ===== 切股导航 =====
  // onClose 只有 ESC 用; onNavigate 由 useListNav 内部承接 (支持内联 lambda)
  const onCloseRef = useRef(onClose)
  onCloseRef.current = onClose

  const nav = useListNav<NavItem>({
    items: navListSource ?? [],
    keyOf: navItemKey,
    currentKey: symbol,
    onNavigate: n => onNavigate?.(n.symbol, n.name),
    // 点位监控弹窗/规则编辑器打开时方向键不切股 (与 ESC 的 !priceAlertDraft 守卫同层级)
    blocked: () => !!priceAlertDraft || showMonitorEditor,
    wrapHints: { head: '已到榜首', tail: '已到末尾' },
  })

  // 邻近预取目标: 当前股左右相邻两只 (首↔尾循环), 交由 StockPanel 提前拉取日K/财务/分时缓存
  const prefetchSymbols = useMemo(() => nav.neighbors.map(n => n.symbol), [nav.neighbors])

  // ESC 关闭 (左右键切股由 useListNav 接管)
  useEffect(() => {
    if (!symbol) return
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !priceAlertDraft) onCloseRef.current()
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [symbol, priceAlertDraft])

  // 弹窗内切股时保留当前视图 (分时 tab 下切股不应跳回去);
  // 仅当弹窗首次打开 (symbol 从 null 变非空) 时重置。
  // [R185] 重置目标跟着默认值一起从 daily 改成 levels —— 只改上面那个
  // useState 初值是不够的: 弹窗关掉再打开会走这一条, 又会跳回日K。
  // [R427] 重置目标改成**入口指定的那一页**(不传仍是 levels)。第一版在上面另加了
  // 一个「symbolProp 一变就重置」的 effect, 出图发现两处打架(这一条把复盘页又
  // 盖回了关键价位), 而且它会在父级方向键切股时把当前页也重置掉 —— 正是本条
  // 注释第一句要防的事。重置只该发生在这一处: 首次打开。
  const prevSymbolRef = useRef<string | null>(null)
  const initialViewRef = useRef(initialView)
  initialViewRef.current = initialView
  const enableLevelsViewRef = useRef(enableLevelsView)
  enableLevelsViewRef.current = enableLevelsView
  useEffect(() => {
    if (prevSymbolRef.current == null && symbol != null) {
      setView(initialViewRef.current ?? 'levels')
      // [R430] 新那一块: 入口指定了图的视图就用它, 否则(含「复盘」)落到关键价位
      const iv = initialViewRef.current
      setChartView(iv === 'daily' || iv === 'intraday' ? iv : enableLevelsViewRef.current ? 'levels' : 'daily')
    }
    prevSymbolRef.current = symbol
    setPriceAlertDraft(null)
    // [R429] 天数提到弹窗里持有后, 复盘页 `key={symbol}` 重建已经带不走它了 ——
    // 在这里补上原来的约定: 「60 日」是上一只票的上下文, 不带到下一只。
    setReviewDays(HERO_DAYS_DEFAULT)
  }, [symbol])

  // 焦点股票注册: SSE quotes_updated 推送时精准 invalidate 当前股票日K,
  // 让对话框日K最后一根蜡烛随实时价变化 (后端只读内存, 不调 TickFlow)。
  // 关闭/切股时清除, 避免无谓刷新。
  useEffect(() => {
    if (!symbol) return
    setFocusSymbol(symbol)
    return () => clearFocusSymbol()
  }, [symbol])

  // 分时图实时轮询: 详情打开即独立轮询, 不再依赖自选列表的「分时刷新」开关
  // 与实时行情运行状态 (打开详情就是要看实时分时); 间隔沿用偏好, 默认 6s。
  // 最新一根K由后端 live 参数直接实时拉取, 与行情列表节奏一致。
  const { data: prefs } = usePreferences()
  const intradayRefetchMs = (prefs?.minute_intraday_refresh_interval ?? 6) * 1000

  // 分时档位按分钟源历史深度收窄: 浅源(如 stock-sdk=5日)只显示可行档位、默认 5日;
  // 深源(tickflow/未声明)全档位、默认 20日。用户已保存的可行选择优先保留。
  const minuteHistoryDays = prefs?.minute_history_days ?? null
  const dayOptions = useMemo<number[]>(
    () => INTRADAY_DAY_OPTIONS.filter(d => minuteHistoryDays == null || d <= minuteHistoryDays),
    [minuteHistoryDays],
  )
  const defaultIntradayDays = minuteHistoryDays != null && minuteHistoryDays < 20 ? 5 : 20
  const effectiveIntradayDays = intradayDays ?? defaultIntradayDays
  useEffect(() => {
    if (!dayOptions.includes(effectiveIntradayDays)) {
      setIntradayDays(defaultIntradayDays)
    }
  }, [dayOptions, effectiveIntradayDays, defaultIntradayDays])

  const handleRefresh = () => {
    if (!symbol) return
    if (view === 'daily') {
      qc.invalidateQueries({ queryKey: ['kline', symbol] })
    } else if (view === 'intraday') {
      qc.invalidateQueries({ queryKey: ['kline-minute-range', symbol] })
      qc.invalidateQueries({ queryKey: ['kline-minute', symbol!] })
    } else {
      qc.invalidateQueries({ queryKey: QK.analysisKline(symbol) })
      qc.invalidateQueries({ queryKey: QK.stockLevels(symbol) })
      qc.invalidateQueries({ queryKey: QK.stockTrend(symbol) })
    }
  }

  const selectIntradayDays = (days: number) => {
    setIntradayDays(days)
    storage.stockPreviewIntradayDays.set(days)
  }

  // [R430] 新那一块的日 K 区间跟头部的 60 / 120 / 250 日走(用户选的「图跟着头部走」):
  // 起点取关键价位那份日 K 倒数第 N 根的日子 —— 与头部那行「起 ~ 止 · N 个交易日」
  // 是同一个数。日 K 还没到时先用旧的默认区间顶着。
  const heroRows = useAnalysisKline(symbol ?? '').data?.rows ?? []
  const heroStart = heroRows.length ? String((heroRows.at(-reviewDays) ?? heroRows[0]).date).slice(0, 10) : null
  const heroRange = heroStart ? { start: heroStart, end: new Date().toISOString().slice(0, 10) } : dateRange

  const openPriceAlert = (targetPrice: number, currentPrice: number) => {
    setPriceAlertDraft({ id: Date.now(), targetPrice, currentPrice })
  }

  return (
    <AnimatePresence>
      {symbol && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          {/* 遮罩 */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
            className="absolute inset-0 bg-black/60 backdrop-blur-sm"
            {...backdrop}
          />

          {/* 弹窗主体 */}
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: 12 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.97, y: 8 }}
            transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
            className={cn(
              'relative rounded-card border border-border bg-base shadow-2xl overflow-hidden flex flex-col transition-ui duration-expand ease-smooth',
              maximized ? 'w-screen h-screen max-w-none max-h-none' : 'w-[92vw] max-w-[1200px] max-h-[95vh]',
            )}
          >
            {/* [R429] 新头部(用户给的排版图)。**加在最前面, 旧顶栏原样留着** ——
                用户: 「你可以直接加在最前面, 后面等我叫你删除旧的」。 */}
            {symbol && (
              <PreviewHero
                symbol={symbol} name={name}
                days={reviewDays} onDaysChange={setReviewDays}
                inWatchlist={inWatchlist} watchBusy={toggleWatchlist.isPending}
                onWatchAdd={groupId => toggleWatchlist.mutate({ action: 'add', groupId })}
                onWatchRemove={() => toggleWatchlist.mutate({ action: 'remove' })}
                onAiAnalyze={onAiAnalyze} aiBusy={aiBusy}
              />
            )}

            {/* [R432] 头部以下整块一起滚。用户: 「图表与价位这部分提取到结论后面」——
                新的几块紧跟在头部(「结论」那一行)之后, 旧顶栏、切换条、信息条和旧内容
                整体挪到新块后面, 等「后面再梳理一遍统一删除」。旧顶栏因此不再钉在顶上,
                它的关闭按钮要滚下去才看得到; Esc / 点弹窗外照常能关。 */}
            <div className="min-h-0 flex-1 overflow-auto">
              <div className="space-y-6 px-4 pb-2 pt-4 sm:px-6">
              {/* [R433] 新「现状」(用户排版图: 「结论后面加」)。只有现成读数 ——
                  图里下半块那套买卖判定先写成草案给用户审, 审完再做。 */}
              <StatusSection symbol={symbol} days={reviewDays} />

              {/* [R430] 新「图表与价位」(用户排版图第二块)。旧的日K/分时/关键价位/复盘
                  原样留在下面 —— 用户: 「新块加上, 旧的先留着」。 */}
              <div>
                <ChartLevelsSection
                  view={chartView}
                  onViewChange={setChartView}
                  levelsEnabled={enableLevelsView}
                  toolbar={chartView === 'intraday' ? (
                    <div className="flex flex-wrap items-center gap-2" aria-label="分时周期">
                      {dayOptions.map(d => (
                        <button key={d} type="button" aria-pressed={effectiveIntradayDays === d}
                                onClick={() => selectIntradayDays(d)}
                                className={`${PILL} ${effectiveIntradayDays === d ? PILL_ON : PILL_IDLE}`}>
                          {d} 日
                        </button>
                      ))}
                    </div>
                  ) : chartView === 'levels' ? (
                    <span className="text-xs text-muted">关键价位模式: 点开哪一类, 就画到图上</span>
                  ) : (
                    <span className="text-xs text-muted">区间跟上面的天数走</span>
                  )}
                >
                  {chartView === 'daily' ? (
                    <StockPanel
                      symbol={symbol}
                      height={420}
                      showIntraday
                      dateRange={heroRange}
                      // 区间取到了还不够: 带分时小图时它默认只露最后 40 根
                      visibleBars={reviewDays}
                      priceLines={monitorPriceLines}
                      onPriceDoubleClick={openPriceAlert}
                      refetchIntervalMs={intradayRefetchMs}
                      prefetchSymbols={prefetchSymbols}
                      intradayDays={effectiveIntradayDays}
                      dailyKlineFlex="flex-[1.4]"
                      addedDate={addedDate}
                    />
                  ) : chartView === 'intraday' ? (
                    <StockMultiDayIntradayChart
                      symbol={symbol}
                      days={effectiveIntradayDays}
                      height={480}
                      refetchIntervalMs={intradayRefetchMs}
                      priceLines={monitorPriceLines}
                      onPriceDoubleClick={openPriceAlert}
                    />
                  ) : (
                    <StockLevelsPanel symbol={symbol} bare height={maximized ? 720 : 520}
                                      controls={levelCtl} visibleBars={reviewDays} />
                  )}
                </ChartLevelsSection>
              </div>

              {/* [R431] 新「复盘」(用户排版图第三块)。天数跟头部走; 旧的复盘页仍在旧顶栏里 */}
              <div>
                <ReviewSection symbol={symbol} days={reviewDays} />
              </div>
              </div>

              <div className="mt-6 border-t border-border/60">
            {/* 顶栏: 单行 = 个股身份 + 视图/区间控件 + 操作按钮。纯样式重排, 交互逻辑不变 */}
            <div className="shrink-0 border-b border-border/60 bg-elevated/30">
              <div className="flex flex-wrap items-center gap-x-3 gap-y-2 px-4 pb-2 pt-2.5 sm:px-5">
              <div className="flex min-w-0 items-center gap-2">
                {(() => {
                  const board = symbol ? boardTag(symbol) : null
                  return board ? (
                    <span className={`inline-flex items-center justify-center w-[18px] h-[18px] rounded text-[9px] font-bold leading-none border ${board.color}`}>
                      {board.label}
                    </span>
                  ) : null
                })()}
                <span className="shrink-0 font-mono text-[15px] font-semibold tracking-tight text-foreground">{symbol}</span>
                {name && <span className="truncate text-xs text-secondary">{name}</span>}

                {/* 切股导航: 上一只 / n·N / 下一只 */}
                <NavPager nav={nav} prevLabel="上一只" nextLabel="下一只" />
              </div>

              {/* 视图/区间控件: 原第二行并入顶行, 紧邻操作按钮 (原「自选于」标注位置) */}
              <div className="ml-auto flex min-w-0 flex-wrap items-center justify-end gap-2.5">
                {/* 日K / 分时 切换 */}
                <div role="tablist" aria-label="图表视图" className="inline-flex shrink-0 items-center rounded border border-border/60 bg-base/60 p-0.5">
                  <button
                    type="button"
                    role="tab"
                    aria-selected={view === 'daily'}
                    onClick={() => setView('daily')}
                    className={`inline-flex h-6 items-center gap-1 rounded px-2.5 text-[11px] transition-colors ${
                      view === 'daily' ? 'bg-accent/20 text-accent font-medium' : 'text-muted hover:text-secondary hover:bg-elevated/60'
                    }`}
                  >
                    <LineChart className="h-3 w-3" />
                    日 K
                  </button>
                  <button
                    type="button"
                    role="tab"
                    aria-selected={view === 'intraday'}
                    onClick={() => setView('intraday')}
                    className={`inline-flex h-6 items-center gap-1 rounded px-2.5 text-[11px] transition-colors ${
                      view === 'intraday' ? 'bg-accent/20 text-accent font-medium' : 'text-muted hover:text-secondary hover:bg-elevated/60'
                    }`}
                  >
                    <Clock className="h-3 w-3" />
                    分时
                  </button>
                  {/* [R103] fork 增强: 第三个视图「关键价位」。作者这一轮把工具栏重排了,
                      这一档按他的新样式补回来 —— 不再另起一个 tablist(合并时文件里一度
                      出现过两个, 那是重复不是增强)。 */}
                  {enableLevelsView && (
                    <button
                      type="button"
                      role="tab"
                      aria-selected={view === 'levels'}
                      onClick={() => setView('levels')}
                      className={`inline-flex h-6 items-center gap-1 rounded px-2.5 text-[11px] transition-colors ${
                        view === 'levels' ? 'bg-accent/20 text-accent font-medium' : 'text-muted hover:text-secondary hover:bg-elevated/60'
                      }`}
                    >
                      <Crosshair className="h-3 w-3" />
                      关键价位
                    </button>
                  )}
                  {/* [R427] 第四个视图「复盘」—— 原来的复盘弹窗(趋势状态 / 通道档位)
                      并进来了。用户: 「两个弹窗融合成一个」。 */}
                  <button
                    type="button"
                    role="tab"
                    aria-selected={view === 'review'}
                    onClick={() => setView('review')}
                    className={`inline-flex h-6 items-center gap-1 rounded px-2.5 text-[11px] transition-colors ${
                      view === 'review' ? 'bg-accent/20 text-accent font-medium' : 'text-muted hover:text-secondary hover:bg-elevated/60'
                    }`}
                  >
                    <CalendarRange className="h-3 w-3" />
                    复盘
                  </button>
                </div>
                <span className="h-4 w-px shrink-0 bg-border/70" />
                {/* 区间选择 — 随视图切换 */}
                {view === 'daily' ? (
                  <div className="inline-flex items-center gap-2">
                    <div className="inline-flex items-center rounded border border-border/60 bg-base/60 p-0.5">
                    {PRESETS.map(p => {
                      const now = new Date()
                      const s = new Date(now)
                      s.setMonth(s.getMonth() - p.months)
                      const expected = s.toISOString().slice(0, 10)
                      const isActive = dateRange.start === expected
                      return (
                        <button
                          key={p.label}
                          onClick={() => {
                            const end = new Date().toISOString().slice(0, 10)
                            const ns = new Date()
                            ns.setMonth(ns.getMonth() - p.months)
                            setDateRange({ start: ns.toISOString().slice(0, 10), end })
                          }}
                          className={`h-6 rounded px-2.5 text-[11px] transition-colors cursor-pointer
                            ${isActive
                              ? 'bg-accent/20 text-accent font-medium'
                              : 'text-muted hover:text-secondary hover:bg-elevated/60'
                            }`}
                        >
                          {p.label}
                        </button>
                      )
                    })}
                    </div>
                    <DatePicker
                      value={dateRange.start}
                      onChange={(v) => setDateRange(prev => ({ ...prev, start: v }))}
                      max={dateRange.end}
                    />
                    <span className="text-muted/70 text-[10px]">~</span>
                    <DatePicker
                      value={dateRange.end}
                      onChange={(v) => setDateRange(prev => ({ ...prev, end: v }))}
                      min={dateRange.start}
                    />
                  </div>
                ) : view === 'intraday' ? (
                  <div className="inline-flex items-center gap-2">
                    <div className="inline-flex shrink-0 items-center rounded border border-border bg-elevated p-0.5" aria-label="分时周期">
                      {dayOptions.map(days => (
                        <button
                          key={days}
                          type="button"
                          aria-pressed={effectiveIntradayDays === days}
                          onClick={() => selectIntradayDays(days)}
                          className={`h-6 rounded px-2.5 text-[11px] transition-colors ${
                            effectiveIntradayDays === days
                              ? 'bg-accent/20 text-accent font-medium'
                              : 'text-muted hover:text-secondary hover:bg-elevated/60'
                          }`}
                        >
                          {days}日
                        </button>
                      ))}
                    </div>
                  </div>
                ) : <StockLevelsPriceTag symbol={symbol} />}
              </div>

              <div className="flex shrink-0 items-center gap-1">
                {/* 自选 */}
                {inWatchlist ? (
                  <button
                    type="button"
                    onClick={() => toggleWatchlist.mutate({ action: 'remove' })}
                    disabled={toggleWatchlist.isPending}
                    className="rounded-btn p-1.5 text-[#FACC15] transition-colors cursor-pointer hover:bg-elevated disabled:opacity-50"
                    title="移出自选"
                    aria-label={`将 ${symbol} 移出自选`}
                  >
                    <Star className="h-4 w-4" />
                  </button>
                ) : (
                  <WatchlistAddMenu
                    onSelect={groupId => toggleWatchlist.mutate({ action: 'add', groupId })}
                    disabled={toggleWatchlist.isPending}
                    triggerClassName="rounded-btn p-1.5 text-muted transition-colors cursor-pointer hover:bg-elevated hover:text-foreground disabled:opacity-50"
                    ariaLabel={`将 ${symbol} 加入自选`}
                  >
                    <Star className="h-4 w-4" />
                  </WatchlistAddMenu>
                )}
                {/* 加监控 */}
                <button
                  onClick={() => setShowMonitorEditor(true)}
                  className="p-1.5 rounded-btn text-amber-400 hover:bg-amber-400/10 transition-colors cursor-pointer"
                  title="加监控"
                >
                  <RadioTower className="h-4 w-4" />
                </button>
                {/* [R428] AI 四维分析 —— 从个股分析页头挪进来。和「自选」「加监控」排在一起:
                    三个都是**对这只票做的事**; 后面的刷新 / 放大 / 关闭是**对这个弹窗做的事**。
                    作用对象就是弹窗当前这只(含弹窗里切过的), 不用再看页头「当前」是谁。 */}
                {onAiAnalyze && symbol && (
                  <button
                    type="button"
                    onClick={() => onAiAnalyze(symbol, name)}
                    disabled={aiBusy}
                    className="p-1.5 rounded-btn text-sky-300 hover:bg-sky-400/10 transition-colors cursor-pointer disabled:opacity-40"
                    title={`对 ${name || symbol} 生成 AI 四维分析(技术 / 基本面 / 财务 / 消息面)`}
                    aria-label={`对 ${name || symbol} 生成 AI 四维分析`}
                  >
                    {aiBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
                  </button>
                )}

                {/* 刷新 */}
                <button
                  onClick={handleRefresh}
                  className="p-1.5 rounded-btn text-secondary hover:text-foreground hover:bg-elevated transition-colors"
                  title="刷新"
                >
                  <RefreshCw className="h-4 w-4" />
                </button>

                {/* 放大 / 缩小 */}
                <button
                  onClick={() => setMaximized(v => !v)}
                  className="p-1.5 rounded-btn text-secondary hover:text-foreground hover:bg-elevated transition-colors"
                  title={maximized ? '缩小' : '放大'}
                >
                  {maximized ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}
                </button>

                <button
                  onClick={onClose}
                  className="shrink-0 rounded-btn p-1.5 text-secondary transition-colors hover:bg-danger/15 hover:text-danger"
                  aria-label="关闭个股详情"
                  title="关闭"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
              </div>
            </div>

            {/* [R100] 切换条: 最近查看 + 搜索 —— 不关弹窗随意换股 */}
            <div className="flex flex-wrap items-center gap-x-2 gap-y-1 border-b border-border/60 bg-elevated/30 px-5 py-1.5 shrink-0">
              <Clock className="h-3 w-3 shrink-0 text-muted/60" />
              {recent.filter(r => r.symbol !== symbol).slice(0, 6).map(r => (
                <button
                  key={r.symbol}
                  onClick={() => setOverride({ symbol: r.symbol, name: r.name })}
                  title={`切换到 ${r.name} ${r.symbol}`}
                  className="inline-flex items-center gap-1 rounded-btn border border-border/50 bg-base/60 px-2 py-0.5 text-[10px] text-secondary hover:border-accent/40 hover:text-foreground transition-colors cursor-pointer"
                >
                  <span className="max-w-[6em] truncate">{r.name}</span>
                  <span className="font-mono text-[9px] text-muted">{r.symbol}</span>
                </button>
              ))}
              {recent.filter(r => r.symbol !== symbol).length === 0 && (
                <span className="text-[10px] text-muted/50">最近查看的个股会出现在这里, 点击即切换</span>
              )}
              <div className="ml-auto w-52 shrink-0">
                <StockFinancialSearch
                  onSelect={(s, n) => setOverride({ symbol: s, name: n })}
                  assetTypes="stock,index"
                />
              </div>
            </div>

            {/* 触发信息条 (来自监控触发记录) */}
            {triggerInfo && (
              <div className="flex items-center gap-4 border-b border-amber-400/20 bg-amber-400/[0.06] px-5 py-2 shrink-0">
                {/* 左: 触发标记 + 时间 */}
                <div className="flex items-center gap-2 shrink-0">
                  <span className="text-[10px] font-semibold text-amber-400">⚡ 触发</span>
                  {triggerInfo.ts && (
                    <span className="text-[11px] text-secondary font-mono">
                      {new Date(triggerInfo.ts).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })}
                    </span>
                  )}
                </div>

                {/* 中: 价格 + 涨跌幅 */}
                <div className="flex items-center gap-2 shrink-0">
                  {triggerInfo.price != null && (
                    <span className="text-[11px] font-mono text-foreground/80">{triggerInfo.price.toFixed(2)}</span>
                  )}
                  {triggerInfo.changePct != null && (
                    <span className={`text-[11px] font-mono font-medium ${triggerInfo.changePct >= 0 ? 'text-danger' : 'text-bear'}`}>
                      {triggerInfo.changePct >= 0 ? '+' : ''}{(triggerInfo.changePct * 100).toFixed(2)}%
                    </span>
                  )}
                </div>

                {/* 右: 消息 + 信号标签 */}
                <div className="flex items-center gap-2 flex-wrap min-w-0">
                  {triggerInfo.message && (
                    <span className="text-[11px] text-foreground/70 truncate">{triggerInfo.message}</span>
                  )}
                  {triggerInfo.signals && triggerInfo.signals.length > 0 && (
                    <div className="flex items-center gap-1 flex-wrap">
                      {triggerInfo.signals.map((s, j) => (
                        <span key={j} className="rounded bg-accent/10 px-1.5 py-0.5 text-[9px] text-accent/80">{cnSignal(s, customNames)}</span>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* 异动边缘信息条 (与异动页同源; 该股无异动数据时不显示)。整条按状态着色提升辨识度 */}
            {abRow && (() => {
              const meta = AB_STATUS_META[abRow.status] ?? AB_STATUS_META.watch
              return (
                <div className={`flex flex-wrap items-center gap-x-3 gap-y-1 px-5 py-2 shrink-0 ${meta.bar}`}>
                  <span className="flex shrink-0 items-center gap-1.5">
                    <Activity className={`h-3.5 w-3.5 ${meta.icon}`} />
                    <span className={`text-[11px] font-bold ${meta.icon}`}>异动</span>
                    <span className={`rounded px-1.5 py-0.5 text-[10px] ${meta.cls}`}>
                      {meta.label}
                    </span>
                  </span>
                  {Object.entries(abRow.windows)
                    .sort((a, b) => parseInt(a[0], 10) - parseInt(b[0], 10))
                    .map(([w, info]) => {
                      const dominant = abDominantWindow?.[0] === w
                      return (
                        <span
                          key={w}
                          title={`近${parseInt(w, 10)}日累计偏离(含实时) / 交易所规则阈值 · 接近度=|偏离|/阈值`}
                          className={`shrink-0 rounded border px-1.5 py-0.5 font-mono text-[11px] ${
                            dominant
                              ? 'border-border bg-elevated font-semibold text-foreground'
                              : 'border-border/60 bg-base/40 text-secondary'
                          }`}
                        >
                          {parseInt(w, 10)}日{' '}
                          <span className={info.value >= 0 ? 'text-bull' : 'text-bear'}>{fmtPct(info.value)}</span>
                          <span className="text-muted"> / ±{(info.threshold * 100).toFixed(0)}%</span>
                          <span className="text-muted"> · 接近{(info.closeness * 100).toFixed(0)}%</span>
                        </span>
                      )
                    })}
                  <span
                    className="ml-auto shrink-0 font-mono text-[10px] text-muted"
                    title="异动引擎上次计算时间"
                  >
                    计算于 {fmtAbnormalCalcTime(abnormal.data?.asof ?? 0)}
                  </span>
                </div>
              )
            })()}
              </div>

              {/* 图表内容 — 内衬卡片容器, 图表区与弹窗背景分层 (纯样式) */}
              <div className="p-3 sm:p-4">
              <div className="rounded border border-border/50 bg-base/30 p-3">
              {view === 'daily' ? (
                <StockPanel
                  symbol={symbol}
                  height={420}
                  showIntraday
                  dateRange={dateRange}
                  priceLines={monitorPriceLines}
                  onPriceDoubleClick={openPriceAlert}
                  refetchIntervalMs={intradayRefetchMs}
                  prefetchSymbols={prefetchSymbols}
                  intradayDays={effectiveIntradayDays}
                  dailyKlineFlex="flex-[1.4]"
                  addedDate={addedDate}
                />
              ) : view === 'intraday' ? (
                <div className="flex flex-col gap-3">
                <StockPanel
                  symbol={symbol}
                  dateRange={dateRange}
                  infoBarOnly
                  prefetchSymbols={prefetchSymbols}
                  intradayDays={effectiveIntradayDays}
                  addedDate={addedDate}
                />
                <StockMultiDayIntradayChart
                  symbol={symbol}
                  days={effectiveIntradayDays}
                  height={480}
                  refetchIntervalMs={intradayRefetchMs}
                  priceLines={monitorPriceLines}
                  onPriceDoubleClick={openPriceAlert}
                />
                </div>
              ) : view === 'review' ? (
                // key 跟着票走: 切股时复盘页里的「只看有事的日子」「120 日」这类选择
                // 是上一只票的上下文, 不该带到下一只
                <StockReviewPanel key={symbol} symbol={symbol} tab={reviewTab}
                                  days={reviewDays} onDaysChange={setReviewDays} />
              ) : (
                <StockLevelsPanel symbol={symbol} bare height={maximized ? 720 : 520} />
              )}
              </div>
              </div>
            </div>


            {/* 扩展插槽: 对话框底部二开区 (无注册时不渲染) */}
            {(view === 'daily' || view === 'intraday') && (
              <div className="shrink-0">
                <ExtensionSlot
                  name="stock-preview.footer"
                  context={{ symbol, name: name ?? null, view }}
                />
              </div>
            )}

            {/* 加监控编辑器弹层 */}
            <AnimatePresence>
              {showMonitorEditor && symbol && (
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  className="absolute inset-0 z-20 flex items-start justify-center overflow-auto bg-black/40 p-4"
                  onClick={() => setShowMonitorEditor(false)}
                >
                  <div className="mt-8 w-full max-w-2xl" onClick={e => e.stopPropagation()}>
                    <RuleEditor
                      rule={null}
                      simple
                      preset={{
                        scope: 'symbols',
                        symbols: [symbol],
                        type: 'signal',
                        logic: 'or',
                      }}
                      onClose={() => setShowMonitorEditor(false)}
                      onSaved={() => setShowMonitorEditor(false)}
                    />
                  </div>
                </motion.div>
              )}
            </AnimatePresence>

            {/* 首↔尾循环弱提示 */}
            <NavWrapToast message={nav.wrapMsg} />
          </motion.div>
        </div>
      )}
      {symbol && priceAlertDraft && (
        <PriceAlertDialog
          key={`${symbol}-${priceAlertDraft.id}`}
          symbol={symbol}
          name={name ?? ''}
          initialTarget={priceAlertDraft.targetPrice}
          initialCurrentPrice={priceAlertDraft.currentPrice}
          onClose={() => setPriceAlertDraft(null)}
        />
      )}
    </AnimatePresence>
  )
}
