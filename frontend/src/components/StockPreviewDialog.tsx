import { useEffect, useMemo, useRef, useState } from 'react'
import { CandlestickChart, Clock, Crosshair, History } from 'lucide-react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { motion, AnimatePresence, useReducedMotion } from 'framer-motion'
import { api } from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import { cn } from '@/lib/cn'
import { cnDateFromUtc } from '@/lib/format'
import { StockPanel, getDefaultRange } from '@/components/StockPanel'
import { NavWrapToast } from '@/components/NavPager'
import { StockMultiDayIntradayChart } from '@/components/StockMultiDayIntradayChart'
import { RuleEditor } from '@/components/monitor/RuleEditor'
import { PriceAlertDialog } from '@/components/stock-analysis/PriceAlertDialog'
import { LevelOverview, useShownLevels } from '@/components/stock-analysis/AnalysisKChart'
import { StockLevelsPanel, useAnalysisKline, useStockLevels } from '@/components/stock-analysis/StockLevelsPanel'
import { useLevelControls } from '@/components/stock-analysis/levelControls'
import { HERO_DAYS_DEFAULT, PreviewHero } from '@/components/stock-preview/PreviewHero'
import { ChartLevelsSection } from '@/components/stock-preview/ChartLevelsSection'
import { ReviewSection } from '@/components/stock-preview/ReviewSection'
import { StatusSection } from '@/components/stock-preview/StatusSection'
import { PILL, PILL_IDLE, PILL_ON } from '@/components/stock-preview/pill'
import { buildMonitorPriceLines } from '@/lib/price-alerts'
import { usePreferences } from '@/lib/useSharedQueries'
import { setFocusSymbol, clearFocusSymbol } from '@/lib/useQuoteStream'
import { useDialogBackdrop } from '@/lib/useDialogBackdrop'
import { fitLevelsMainHeight } from '@/lib/chart-layout'
import { useMediaQuery } from '@/lib/useMediaQuery'
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
  /** 有序候选列表: 提供后支持左右键切股(首尾循环) */
  navList?: NavItem[]
  /** 切股回调: 收到目标 symbol/name, 由调用方更新预览状态 */
  onNavigate?: (symbol: string, name?: string) => void
  /**
   * [R427] 打开时落在哪一页。不传 = 「关键价位」(R185 的默认)。
   * 决策台点「走势/位置」时传 'review' —— [R479] 旧复盘页删了, 打开时直接定位到新「复盘」块。
   */
  initialView?: PreviewView
  /**
   * [R428] AI 四维分析(技术 / 基本面 / 财务 / 消息面)。传了才在顶栏操作区出这个按钮。
   * 流程(今日已分析过 → 确认查看 / 重新分析)仍归调用方, 这里只是入口 ——
   * 用户: 「ai 四维分析想要放到弹窗里面去, 找个合适的位置, 外面就不要了」。
   */
  onAiAnalyze?: (symbol: string, name?: string) => void
  /** [R428] 调用方正在查今日报告 / 发起分析 —— 按钮转圈并禁用, 防连点 */
  aiBusy?: boolean
}

export type PreviewView = 'daily' | 'intraday' | 'levels' | 'review'

/** [R612] 右栏顶部的视图切换 —— 复盘从原「图表与价位」下面独立成第 4 个视图 */
const VIEW_TABS: { key: PreviewView; label: string; Icon: typeof Clock }[] = [
  { key: 'daily', label: '日 K', Icon: CandlestickChart },
  { key: 'intraday', label: '分时', Icon: Clock },
  { key: 'levels', label: '关键价位', Icon: Crosshair },
  { key: 'review', label: '复盘', Icon: History },
]

/** [R612] 图高上限 */
const CHART_MAX_HEIGHT = 720
/**
 * [R615] 关键价位这张卡里, 图表画布以外还要占的高度 —— 1600×913 实测 131:
 *   · 卡片内边距 32 + 上下边框 2;
 *   · 画布上方: 开关键排 78(右栏 940px 上下宽时折成两排) + 两张副图的图例 19。
 * 画布下方原来那条价位统计面板(114 + 上间距 12)已按用户要求挪到左栏, 不再占这里的账。
 * 这些都写死在图表组件里, 外面拿不到, 所以按实测写常量。图表内部版式一变就要回来重算。
 */
const LEVELS_CHROME_H = 131
/**
 * [R614] 分时那张卡里, 图以外还要占的高度 —— 1600×913 实测 109:
 * 卡片内边距 32 + 上下边框 2 + 上方天数行 63 + 间距 12。分时没有副图, 减掉它就是一屏。
 */
const INTRADAY_CHROME_H = 109

interface PriceAlertDraft {
  id: number
  targetPrice: number
  currentPrice: number
}
const INTRADAY_DAY_OPTIONS = [1, 5, 10, 20] as const

// [R552] 弹窗开合的动效参数(动效评审 R550/R551 四条):
//   · 遮罩与面板同一条有力的 ease-out(--ease-out-strong), 原来遮罩吃 framer 默认的软曲线, 两者不同步;
//   · 面板位移写完整 transform 字符串, 不用 `scale` / `y` 简写 —— 简写在主线程逐帧算,
//     打开那 200ms 正是 K 线图、复盘表挂载最忙的时候, 会掉帧; 字符串交给浏览器原生动画跑;
//   · 退场比入场快(150 vs 200ms): 点开是用户主动的, 关掉是系统应答, 该利落;
//   · 减少动态效果: framer 的 reducedMotion 只认 x / y / scale 这类键, 不认 `transform` 字符串,
//     所以这里自己判断, 开了就只剩透明度。
const EASE_OUT_STRONG = [0.23, 1, 0.32, 1] as const
const PANEL_MOTION = {
  from: 'translateY(12px) scale(0.95)',
  to: 'translateY(0px) scale(1)',
  exit: 'translateY(8px) scale(0.97)',
} as const

function loadIntradayDays(): number {
  const saved = storage.stockPreviewIntradayDays.get(DEFAULT_INTRADAY_DAYS)
  return INTRADAY_DAY_OPTIONS.includes(saved as typeof INTRADAY_DAY_OPTIONS[number])
    ? saved
    : DEFAULT_INTRADAY_DAYS
}

export function StockPreviewDialog({ symbol, name, onClose, enableLevelsView = true, navList: navListSource, onNavigate, initialView, onAiAnalyze, aiBusy = false }: Props) {
  // [R479] 旧顶栏 + 切换条(最近查看 / 搜索)删了: 弹窗里不再有内部换股, symbol / name 就是调用方给的;
  // 方向键切股(useListNav)照旧, 由调用方 onNavigate 换票。
  // [R185] 默认落在「关键价位」而不是日K —— 这个弹窗是拿来做决策的, 图表模块
  // 自己的注释也写着「本图表面向分析决策, 核心是关键价位」。点进来先看到的
  // 该是压力/支撑/枢轴那几条线, 而不是一根还要自己看的 K 线。
  // [R429] 60 / 120 / 250 日 —— 新头部与复盘页**同一个值**(用户: 「直接按照图片」放在头部)
  const [reviewDays, setReviewDays] = useState<number>(HERO_DAYS_DEFAULT)
  // [R430] 右栏的视图, 以及价位列表与图共用的开关状态。都不随切股重置 —— 与原来的关键价位页一样,
  // 方向键翻票时开着的那几类、看的那个视图都留着。
  // [R612] 复盘从压在图表下面的第 4 块, 变成右栏的第 4 个视图, 也由这一个状态管。
  const [chartView, setChartView] = useState<PreviewView>('levels')
  const levelCtl = useLevelControls()
  /** [R615] 悬停高亮: 图的价位标签 ↔ 左栏那条价位统计, 两边同一份状态 */
  const [levelHover, setLevelHover] = useState<string | null>(null)
  const [intradayDays, setIntradayDays] = useState<number | null>(loadIntradayDays)
  const [dateRange] = useState(getDefaultRange)
  const [showMonitorEditor, setShowMonitorEditor] = useState(false)
  const [priceAlertDraft, setPriceAlertDraft] = useState<PriceAlertDraft | null>(null)
  const qc = useQueryClient()
  const backdrop = useDialogBackdrop(onClose)
  const reduceMotion = useReducedMotion()

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
  // [R479] 入口指定 'review'(决策台点「走势/位置」)时直接落在复盘 —— 现在它是右栏第 4 个视图,
  // 原来那条「滚到底再钉住」的补丁随竖向串联布局一起删了。
  //
  // [R612] 双栏只在 ≥1280 生效; 窄屏单列、整页滚, 图高回落到改版前写死的值。
  //
  // [R612-fix] 关键价位不再被裁: 那张图的画布 = 主图(`height`)+ 趋势量化 + 量化MACD
  // 两张副图; 改版第一版右栏 overflow-hidden, 画布比右栏高 → 两张副图被整块裁掉。
  //
  // [R614] 用户: 「按这个方案调整副图高度」—— 曾把主图压到「右栏 − 卡片其余部分 − 两张副图」,
  // 让三块一屏装下。
  //
  // [R616] 用户: 「副图的趋势量化和量化macd没有和我升级到R565之前显示的一样」—— 两张副图
  // 改回 R565 的比例(主图 48%、限 160~220, 趋势量化再 +50 字道), 一屏装下因此失效:
  // 579 高的右栏里画布会比可用空间高约 180px, 由右栏滚动兜底(R613 的兜底保留)。
  // 这里仍按 `height` = 主图高来算, 公式与 R614 相同 —— 日K 的副图数量由图内工具栏决定、
  // 外面算不出来, 维持 420; 分时没有额外副图, 继续跟着右栏放宽。
  const wide = useMediaQuery('(min-width: 1280px)')
  const chartAreaRef = useRef<HTMLDivElement>(null)
  const [chartAreaH, setChartAreaH] = useState(0)
  useEffect(() => {
    const el = chartAreaRef.current
    if (!el || !wide) { setChartAreaH(0); return }
    const ro = new ResizeObserver(entries => setChartAreaH(entries[0].contentRect.height))
    ro.observe(el)
    return () => ro.disconnect()
  }, [wide, symbol, chartView])
  const chartHeight = wide && chartAreaH > 0
    ? chartView === 'intraday'
      ? Math.max(480, Math.min(chartAreaH - INTRADAY_CHROME_H, CHART_MAX_HEIGHT))
      : chartView === 'levels'
        // [R623] 主图反算: 让主图 + 趋势量化 + 量化MACD 正好填满右栏, 不再靠滚轮。
        // 判据与 AnalysisKChart 的副图高同源(lib/chart-layout 的 fitLevelsMainHeight)。
        ? Math.min(fitLevelsMainHeight(chartAreaH - LEVELS_CHROME_H), CHART_MAX_HEIGHT)
        : undefined
    : undefined
  // [R622] 切视图回到顶部: 右栏是滚动容器, 在关键价位滚到底再切去日K/分时,
  // 新视图会停在半截 (实测残留 213px), 看起来像图表顶部被裁。换视图即归零。
  useEffect(() => {
    const el = chartAreaRef.current
    if (el) el.scrollTop = 0
  }, [chartView])
  const prevSymbolRef = useRef<string | null>(null)
  const initialViewRef = useRef(initialView)
  initialViewRef.current = initialView
  const enableLevelsViewRef = useRef(enableLevelsView)
  enableLevelsViewRef.current = enableLevelsView
  useEffect(() => {
    if (prevSymbolRef.current == null && symbol != null) {
      // [R430] 入口指定了哪一页就用哪一页; 不传落到关键价位(关掉了就落到日K)
      const iv = initialViewRef.current
      setChartView(
        iv === 'review' ? 'review'
          : iv === 'daily' || iv === 'intraday' ? iv
            : enableLevelsViewRef.current ? 'levels' : 'daily',
      )
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

  // [R437] 刷新当前视图那份数据。[R479] 旧顶栏(和它的 `view`)删了, 只剩新「图表与价位」的 chartView。
  const handleRefresh = () => {
    if (!symbol) return
    if (chartView === 'daily') {
      qc.invalidateQueries({ queryKey: ['kline', symbol] })
    } else if (chartView === 'intraday') {
      qc.invalidateQueries({ queryKey: ['kline-minute-range', symbol] })
      qc.invalidateQueries({ queryKey: ['kline-minute', symbol] })
    } else if (chartView === 'review') {
      // [R612] 复盘成了独立视图, 刷新要重取的是它自己的那份回算
      qc.invalidateQueries({ queryKey: QK.stockReview(symbol, reviewDays) })
    } else {
      qc.invalidateQueries({ queryKey: QK.analysisKline(symbol) })
      qc.invalidateQueries({ queryKey: QK.stockLevels(symbol) })
      qc.invalidateQueries({ queryKey: QK.stockTrend(symbol) })
      // [R472] 关键价位图的量化MACD 副图是单独一个查询, 原来漏了 —— 它取数失败时
      // 图上叫人「点右上角刷新重试」, 点了却不会重取。
      qc.invalidateQueries({ queryKey: QK.stockQuantMacd(symbol) })
      // [R486] 趋势量化同理, 一起重取
      qc.invalidateQueries({ queryKey: QK.stockTrendQuant(symbol) })
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

  // [R615] 用户: 「量化macd下面那部分，也就是当前价那些，可以放到左侧部分里面显示」。
  // 面板搬到左栏后，「画了哪几条价位」得在这里算 —— 与图内同一个 `useShownLevels`
  // (二型的粗细档换线等都在里面), 不另算一套; 查询键与图那份相同, 不多发请求。
  const levelsQ = useStockLevels(symbol ?? '')
  const shownLevels = useShownLevels(levelsQ.data?.levels, levelsQ.data?.fib2, heroRows,
    levelCtl.fib2Grain, levelCtl.fib2ShowTargets)

  const openPriceAlert = (targetPrice: number, currentPrice: number) => {
    setPriceAlertDraft({ id: Date.now(), targetPrice, currentPrice })
  }

  // 「关键价位」视图可以被调用方关掉 —— 关掉时右栏只有 3 个视图
  const viewTabs = enableLevelsView ? VIEW_TABS : VIEW_TABS.filter(t => t.key !== 'levels')

  return (
    <AnimatePresence>
      {symbol && (
        // [R552] 退场期间不接点击: 弹窗常挂之后退场真的会跑, 已经淡出的遮罩还会拦住 150ms 的点击,
        // 关掉一只马上点下一只, 第一下被吞掉
        <motion.div className="fixed inset-0 z-50 flex items-center justify-center"
                    exit={{ pointerEvents: 'none' }}>
          {/* 遮罩 */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15, ease: EASE_OUT_STRONG }}
            className="absolute inset-0 bg-black/60 backdrop-blur-sm"
            {...backdrop}
          />

          {/* 弹窗主体 —— 终态 transform 收回 none: 非 none 的 transform 会成为 fixed 子元素的包含块(见 Modal.tsx) */}
          <motion.div
            initial={{ opacity: 0, transform: reduceMotion ? 'none' : PANEL_MOTION.from }}
            animate={{ opacity: 1, transform: reduceMotion ? 'none' : PANEL_MOTION.to, transitionEnd: { transform: 'none' } }}
            exit={{ opacity: 0, transform: reduceMotion ? 'none' : PANEL_MOTION.exit,
                    transition: { duration: 0.15, ease: EASE_OUT_STRONG } }}
            transition={{ duration: 0.2, ease: EASE_OUT_STRONG }}
            className={cn(
              'relative flex flex-col overflow-hidden rounded-card border border-border bg-base shadow-2xl',
              // [R612] 双栏要更宽: 1440 上限; 手机上整屏, 不再留一圈背景
              // [R623] 88vh → 96dvh: 关键价位要一屏装下主图 + 两张副图
              // [R624] 再吃到 calc(100dvh - 16px): 多出的 24px 全部给主图, 让主图明显大于副图
              'h-[min(1120px,calc(100dvh-16px))] min-h-[640px] w-[94vw] max-w-wide',
              'max-md:h-[100dvh] max-md:max-h-none max-md:min-h-0 max-md:w-screen max-md:rounded-none max-md:border-0',
            )}
          >
            {/* [R429] 新头部(用户给的排版图)。[R479] 旧顶栏已删(用户框出整块:「我是想删除掉框出来的这部分」),
                加监控 R478 已先搬到这里。 */}
            {symbol && (
              <PreviewHero
                symbol={symbol} name={name}
                days={reviewDays} onDaysChange={setReviewDays}
                inWatchlist={inWatchlist} watchBusy={toggleWatchlist.isPending}
                onWatchAdd={groupId => toggleWatchlist.mutate({ action: 'add', groupId })}
                onWatchRemove={() => toggleWatchlist.mutate({ action: 'remove' })}
                onAiAnalyze={onAiAnalyze} aiBusy={aiBusy}
                onRefresh={handleRefresh}
                onAddMonitor={() => setShowMonitorEditor(true)}
              />
            )}

            {/* [R612] 双栏: 左「现状」/ 右图表与复盘; <1280 单列, 整块一起滚。
                [R479] 原来挪在新块后面等删的旧顶栏、切换条、信息条和旧内容已删。 */}
            <div className="min-h-0 flex-1 overflow-y-auto xl:grid xl:grid-cols-[minmax(300px,340px)_minmax(0,1fr)] xl:overflow-hidden">
              {/* 左栏: 现状(只有现成读数) */}
              <div className="border-b border-border/60 px-4 py-4 sm:px-6 xl:min-h-0 xl:overflow-y-auto xl:border-b-0 xl:border-r">
                <StatusSection symbol={symbol} days={reviewDays} stacked={wide} />
                {/* [R615] 原来挂在量化MACD 下面的「当前价 / 压力位 / 支撑位」—— 挪到这里,
                    哪一页都看得见; 悬停与图上的价位标签联动 */}
                {shownLevels.effLevels && (
                  <LevelOverview
                    levels={shownLevels.effLevels}
                    activeTypes={levelCtl.activeTypes}
                    pivotRank={levelCtl.pivotRank}
                    close={heroRows.at(-1)?.close}
                    hoveredKey={levelHover}
                    onHover={setLevelHover}
                    stacked
                  />
                )}
              </div>

              {/* 右栏: 视图切换条 + 一张图 / 复盘 */}
              <div className="flex min-h-0 min-w-0 flex-col px-4 py-4 sm:px-6">
                <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
                  {chartView === 'intraday' ? (
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
                  ) : chartView === 'review' ? (
                    <span className="text-xs text-muted">最近 {reviewDays} 个交易日</span>
                  ) : (
                    <span className="text-xs text-muted">区间跟上面的天数走</span>
                  )}
                  <div role="tablist" aria-label="图表视图"
                       className="ml-auto inline-flex shrink-0 items-center gap-1 rounded-btn border border-border bg-elevated/60 p-1">
                    {viewTabs.map(({ key, label, Icon }) => (
                      <button key={key} type="button" role="tab" aria-selected={chartView === key}
                              onClick={() => setChartView(key)}
                              className={`inline-flex h-8 items-center gap-1.5 rounded-btn px-3 text-sm transition-colors duration-hover ${
                                chartView === key ? 'bg-foreground font-medium text-surface' : 'text-secondary hover:text-foreground'
                              }`}>
                        <Icon className="h-3.5 w-3.5" />
                        {label}
                      </button>
                    ))}
                  </div>
                </div>

                {/* [R612-fix] 一律可滚: 关键价位的画布比这里的可视区高(下面挂着两张副图),
                    裁掉就等于把副图删了 —— 改版前靠弹窗整页滚, 现在是右栏自己滚。 */}
                <div ref={chartAreaRef} className="mt-3 min-h-0 flex-1 overflow-y-auto">
                  {chartView === 'review' ? (
                    // [R442] key 跟着票走(换票时「只看有事的日子」复位) —— 与旧复盘页一样
                    <ReviewSection key={symbol} symbol={symbol} days={reviewDays} />
                  ) : (
                    <ChartLevelsSection>
                      {chartView === 'daily' ? (
                        <StockPanel
                          symbol={symbol}
                          height={chartHeight ?? 420}
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
                          // [R625] 数据源确认没有该日分钟数据时收起右边空列(原来常驻一块
                          // 空分时 + 一个拉了也没用的按钮, 日K被挤在 57% 宽里)
                          hideEmptyIntraday
                        />
                      ) : chartView === 'intraday' ? (
                        // [R437] 与旧分时页同一套: 上面一条信息栏(只要信息栏, 不画日 K), 下面多日分时。
                        // 区间与新日 K 同一个(同一份缓存, 不多发请求)
                        <div className="flex flex-col gap-3">
                        <StockPanel
                          symbol={symbol}
                          dateRange={heroRange}
                          infoBarOnly
                          prefetchSymbols={prefetchSymbols}
                          intradayDays={effectiveIntradayDays}
                          addedDate={addedDate}
                        />
                        <StockMultiDayIntradayChart
                          symbol={symbol}
                          days={effectiveIntradayDays}
                          height={chartHeight ?? 480}
                          refetchIntervalMs={intradayRefetchMs}
                          priceLines={monitorPriceLines}
                          onPriceDoubleClick={openPriceAlert}
                        />
                        </div>
                      ) : (
                        // [R551] 不要图上方的六态条: 与左栏「现状」是同一份六态(用户圈出「重复了」),
                        // 它独有的回测调参入口、转折信号已挪进现状卡
                        <StockLevelsPanel symbol={symbol} bare height={chartHeight ?? 520} trendBar={false}
                                          controls={levelCtl} visibleBars={reviewDays}
                                          overview={false} hoveredKey={levelHover} onHoverKey={setLevelHover} />
                      )}
                    </ChartLevelsSection>
                  )}
                </div>
              </div>
            </div>


            {/* 扩展插槽: 对话框底部二开区 (无注册时不渲染)。[R479] 旧顶栏删了, 显隐改跟新「图表与价位」
                的视图(chartView)走 —— 插槽名与 context 形状不变, 这是 docs/secondary-development.md
                里写明的公开插槽。 */}
            {(chartView === 'daily' || chartView === 'intraday') && (
              <div className="shrink-0">
                <ExtensionSlot
                  name="stock-preview.footer"
                  context={{ symbol, name: name ?? null, view: chartView }}
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
        </motion.div>
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
