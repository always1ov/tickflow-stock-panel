import { useEffect, useMemo, useRef, useState } from 'react'
import { CandlestickChart, Clock, History } from 'lucide-react'
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
import { hasOverviewLevels, LevelOverview, useShownLevels } from '@/components/stock-analysis/AnalysisKChart'
import { TrendBacktestButton, useStockTrend } from '@/components/stock-analysis/TrendStateBar'
import { useAnalysisKline, useStockLevels } from '@/components/stock-analysis/StockLevelsPanel'
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
import { useMediaQuery } from '@/lib/useMediaQuery'
import { storage } from '@/lib/storage'
import { navItemKey, type NavItem } from '@/lib/listNav'
import { useListNav } from '@/lib/useListNav'
import { ExtensionSlot } from '@/extensions/ExtensionSlot'

interface Props {
  symbol: string | null
  name?: string
  onClose: () => void
  /** [R103] 全站统一弹窗后所有入口看到同一套视图(日K/分时/复盘)。 */
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

export type PreviewView = 'daily' | 'intraday' | 'review'

/** [R612] 右栏顶部的视图切换 —— 复盘从原「图表与价位」下面独立成一个视图 */
const VIEW_TABS: { key: PreviewView; label: string; Icon: typeof Clock }[] = [
  { key: 'daily', label: '日 K', Icon: CandlestickChart },
  { key: 'intraday', label: '分时', Icon: Clock },
  { key: 'review', label: '复盘', Icon: History },
]

/** [R612] 图高上限 */
const CHART_MAX_HEIGHT = 720
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

/**
 * [R680] 「回测调参」—— 用户先要求放到头部「自选于」前面, 又改成
 * 「还是放到中里面的『异动 颜色 自选』的自选的后面」。挂在图上方工具栏右端,
 * 借同一份 `useStockTrend` 缓存出阈值; 趋势没取到 (或报错) 时不渲染。
 */
function BacktestEntry({ symbol }: { symbol: string }) {
  const t = useStockTrend(symbol).data
  if (!t || t.error) return null
  // [R685] 与「异动 / 自选」同尺寸(65×19), 标签收成「回测 8%」, 阀值来源进悬停
  return <TrendBacktestButton symbol={symbol} trend={t} compact />
}

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

/** 分时默认档位: 没有保存过就选 20 日 (与浅源收窄后的 5 日兜底一致)。 */
const DEFAULT_PREVIEW_INTRADAY_DAYS = 20

function loadIntradayDays(): number {
  const saved = storage.stockPreviewIntradayDays.get(DEFAULT_PREVIEW_INTRADAY_DAYS)
  return INTRADAY_DAY_OPTIONS.includes(saved as typeof INTRADAY_DAY_OPTIONS[number])
    ? saved
    : DEFAULT_PREVIEW_INTRADAY_DAYS
}

export function StockPreviewDialog({ symbol, name, onClose, navList: navListSource, onNavigate, initialView, onAiAnalyze, aiBusy = false }: Props) {
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
  const [chartView, setChartView] = useState<PreviewView>('daily')
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
  // [R612-fix] 关键价位不再被裁: 那张图的画布 = 主图(`height`)+ 量化MACD 一张副图;
  // 改版第一版右栏 overflow-hidden, 画布比右栏高 → 副图被整块裁掉。
  //
  // [R614] 用户: 「按这个方案调整副图高度」—— 曾把主图压到「右栏 − 卡片其余部分 − 两张副图」,
  // 让三块一屏装下。
  //
  // [R616] 用户: 「副图的趋势量化和量化macd没有和我升级到R565之前显示的一样」—— 副图
  // 改回 R565 的比例(主图 48%、限 160~220), 一屏装下因此失效:
  // ([R724] 趋势量化已删, 只剩量化MACD 一张。)
  // 579 高的右栏里画布会比可用空间高约 180px, 由右栏滚动兜底(R613 的兜底保留)。
  // 这里仍按 `height` = 主图高来算, 公式与 R614 相同 —— 日K 的副图数量由图内工具栏决定、
  // 外面算不出来, 维持 420; 分时没有额外副图, 继续跟着右栏放宽。
  const wide = useMediaQuery('(min-width: 1280px)')
  // [R732] ≥1536: 弹窗满宽满高, 左栏左边再拆一列常驻复盘(「复盘」标签随之隐藏)。
  const showReviewWide = useMediaQuery('(min-width: 1536px)')
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
      // [R668] 用户: 「主图显示还是恢复原来日K里面的风格吧」「要到最近一次右侧留白带之前那个版本」——
      // R663 那套「按关键价位反算主图高度」撤掉, 日K 回到自己的默认高度与版式。
      : undefined
    : undefined
  // [R622] 切视图回到顶部: 右栏是滚动容器, 在关键价位滚到底再切去日K/分时,
  // 新视图会停在半截 (实测残留 213px), 看起来像图表顶部被裁。换视图即归零。
  useEffect(() => {
    const el = chartAreaRef.current
    if (el) el.scrollTop = 0
  }, [chartView])
  // [R732] 复盘改为左列常驻后, 中栏不再有这一页; 从决策台带 'review' 进来时落回日 K,
  // 复盘内容就在最左边那一列里。
  useEffect(() => {
    if (showReviewWide && chartView === 'review') setChartView('daily')
  }, [showReviewWide, chartView])
  const prevSymbolRef = useRef<string | null>(null)
  const initialViewRef = useRef(initialView)
  initialViewRef.current = initialView
  useEffect(() => {
    if (prevSymbolRef.current == null && symbol != null) {
      // [R430] 入口指定了哪一页就用哪一页; 不传落到日K
      // [R663] 「关键价位」视图已下线, 它的画线与开关都并进日K
      const iv = initialViewRef.current
      setChartView(iv === 'review' ? 'review' : iv === 'intraday' ? 'intraday' : 'daily')
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
      // [R663] 日K 现在自己画价位与分析副图, 刷新要连它们那份数据一起重取
      // ([R724] 趋势量化撤掉后, 日K 只剩量化MACD 这一张分析副图)
      qc.invalidateQueries({ queryKey: QK.analysisKline(symbol) })
      qc.invalidateQueries({ queryKey: QK.stockLevels(symbol) })
      qc.invalidateQueries({ queryKey: QK.stockTrend(symbol) })
      qc.invalidateQueries({ queryKey: QK.stockQuantMacd(symbol) })
    } else if (chartView === 'intraday') {
      qc.invalidateQueries({ queryKey: ['kline-minute-range', symbol] })
      qc.invalidateQueries({ queryKey: ['kline-minute', symbol] })
    } else {
      // [R612] 复盘成了独立视图, 刷新要重取的是它自己的那份回算
      qc.invalidateQueries({ queryKey: QK.stockReview(symbol, reviewDays) })
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
  // [R672] 右栏常驻: 用户「时刻显示右侧价位那部分」—— 不再按有无点位收栏,
  // 三栏结构不随数据变化。只在「所有价位类型都被关掉」时给一句提示, 不留白。
  const levelPanelEmpty = shownLevels.effLevels
    ? !hasOverviewLevels(shownLevels.effLevels, levelCtl.activeTypes, levelCtl.pivotRank)
    : true

  const openPriceAlert = (targetPrice: number, currentPrice: number) => {
    setPriceAlertDraft({ id: Date.now(), targetPrice, currentPrice })
  }

  // [R658] 用户: 「这一行『区间跟上面的天数走 日K 分时 关键价位 复盘』放到顶部的 60 日的左边」,
  // 随后又限定「仅针对…这点内容」—— 所以只搬**那行提示文字 + 视图标签**,
  // 分时那排 5/10/20 日天数留在原处(它也属于那条横条, 但不是这句话点名的东西)。
  // [R670] 那句提示撤了: 头部本来就印着「起 ~ 止 · N 个交易日」, 再说一遍「区间跟上面的天数走」
  // 是把同一件事写两次。复盘视图同理, 它的卡片头自己带日期与交易日数(还有六态阈值来源)。
  const viewControls = (
    // [R679] 用户: 「日K、分时、复盘 没有后面的 60日/120日/250日 的按钮大小一样」——
    // 那三颗原来装在一个带边距的分段容器里(容器 p-1 + 边框把它们整体撑大), 现在拆成
    // 和天数胶囊同一套独立按钮: 同样的边框/底色/选中样式、同样的 72×32。
    <div role="tablist" aria-label="图表视图" className="inline-flex shrink-0 items-center gap-2">
      {/* [R732] 复盘已常驻在最左一列, 宽屏不再需要这个标签 */}
      {VIEW_TABS.filter(tab => !(showReviewWide && tab.key === 'review')).map(({ key, label, Icon }) => (
        <button key={key} type="button" role="tab" aria-selected={chartView === key}
                onClick={() => setChartView(key)}
                className={`inline-flex h-8 w-[72px] shrink-0 items-center justify-center gap-1 whitespace-nowrap rounded-btn border text-xs transition-colors duration-hover ${
                  chartView === key ? PILL_ON : PILL_IDLE
                }`}>
          <Icon className="h-3.5 w-3.5" />
          {label}
        </button>
      ))}
    </div>
  )

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
              // [R732] ≥1536 满宽满高: 左栏再拆一列放复盘, 图与价位仍同屏
              '2xl:h-[calc(100dvh-16px)] 2xl:w-[calc(100vw-16px)] 2xl:max-w-none',
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
                onClose={onClose}
                viewControls={viewControls}
                // [R671] 指标行并进头部第二行 —— 与中栏那张图同一份取数(同查询键, 不多发请求)
                stats={(
                  <StockPanel
                    symbol={symbol}
                    dateRange={heroRange}
                    headerStats
                    prefetchSymbols={prefetchSymbols}
                    addedDate={addedDate}
                  />
                )}
              />
            )}

            {/* [R612] 多栏: 左「现状」/ 中图表与复盘 / 右「当前价·压力位·支撑位」; <1280 单列, 整块一起滚。
                [R479] 原来挪在新块后面等删的旧顶栏、切换条、信息条和旧内容已删。
                [R665] 用户: 「当前价这部分挪到右边, 最终弹窗里面是左中右布局」——
                价位块从左边挪到第三栏, 从此是左中右三栏。
                [R672] 用户: 「始终保持上下布局, 下布局里面始终保持左中右」——
                上面是头部、下面是三栏, 三栏不再随数据增删(右栏常驻)。
                [R682] 用户: 「跌破转弱站上转强都不要了, 剩下的趋势六态和通道阶段内容合并到
                右里面, 从此左中右布局变成左右布局」—— 左栏撤掉, 现状整块并进右栏顶部,
                图上方的宽度全给图。 */}
            <div className="min-h-0 flex-1 overflow-y-auto xl:grid xl:grid-cols-[minmax(240px,290px)_minmax(0,1fr)_minmax(250px,300px)] xl:overflow-hidden 2xl:grid-cols-[minmax(300px,26%)_minmax(0,1fr)_minmax(230px,18%)]">
              {/* [R837] 用户: 「个股弹窗左边的两列合并成一列显示」——
                 2xl 下原本是「复盘」与「现状」两列并排, 现在并成一列: 复盘在上、现状在下,
                 同列一起滚。窄屏这一列里没有复盘(复盘走顶部标签), 内容与合并前一致。
                 [R838] 用户: 「主图区域的宽度不能这么宽, 但比原来大」—— 合并后图吃掉了
                 让出来的 250px 变成 850。这里给它封顶 760(原来约 590), 多出来的空白
                 交给整行居中, 不再继续喂给图。
                 [R839] 用户: 「合理分配左中右比例, 主图区域才是主体」—— 封顶是死数, 换成分比例:
                 左 24% / 中 1fr(约 58%) / 右 18%, 下限 300 / 0 / 230。图在任何宽度下都是最宽的那栏,
                 两侧随窗口一起收放, 不会再出现「图 850、左边 520 显得差不多宽」。 */}
              <div className="border-border/60 px-4 py-4 sm:px-6 xl:min-h-0 xl:overflow-y-auto xl:border-r">
                {/* [R840] 左栏顺序: 现状(趋势/通道/三档) → 一条线 → 复盘(历史表现 → 逐日复盘)。
                    原来复盘挂在最上面, 读完 120 天明细才看到「现在在哪一天」。 */}
                <StatusSection symbol={symbol} days={reviewDays} />
                {showReviewWide && (
                  <div className="mt-5 border-t border-border/60 pt-4">
                    <ReviewSection key={symbol} symbol={symbol} days={reviewDays} compact />
                  </div>
                )}
              </div>

              {/* 中(原左): 一张图 / 复盘([R658] 只有提示文字与四个视图标签搬进头部) */}
              {/* [R700] 用户圈出「市值」那行与「主图指标」那排胶囊之间的空白「太多了」——
                  原来这里是 py-4(16) + mt-3(12) = 28px, 收到 pt-1(4) + mt-1(4) = 8px。 */}
              <div className="flex min-h-0 min-w-0 flex-col px-4 pt-1 pb-4 sm:px-6">
                {/* 分时天数不属于搬走的那句内容, 仍留在图上方 */}
                {chartView === 'intraday' && (
                  <div className="flex flex-wrap items-center gap-2 pb-1" aria-label="分时周期">
                    {dayOptions.map(d => (
                      <button key={d} type="button" aria-pressed={effectiveIntradayDays === d}
                              onClick={() => selectIntradayDays(d)}
                              className={`${PILL} ${effectiveIntradayDays === d ? PILL_ON : PILL_IDLE}`}>
                        {d} 日
                      </button>
                    ))}
                  </div>
                )}
                {/* [R612-fix] 一律可滚: 关键价位的画布比这里的可视区高(下面挂着两张副图),
                    裁掉就等于把副图删了 —— 改版前靠弹窗整页滚, 现在是右栏自己滚。 */}
                <div ref={chartAreaRef} className="mt-1 min-h-0 flex-1 overflow-y-auto">
                  {chartView === 'review' && !showReviewWide ? (
                    // [R442] key 跟着票走(换票时「只看有事的日子」复位) —— 与旧复盘页一样
                    <ReviewSection key={symbol} symbol={symbol} days={reviewDays} />
                  ) : (
                    <ChartLevelsSection>
                      {chartView === 'daily' ? (
                        <StockPanel
                          symbol={symbol}
                          // [R649] 日K 统一走 lightweight: 关键价位的两张副图已并入它的底部,
                          // 与右侧「关键价位」同一套画布(ECharts 版画不出这两张副图)
                          renderer="lightweight"
                          height={chartHeight ?? 420}
                          // [R650] 右栏可视高度: 日K 用它算两张分析副图还剩多少空间;
                          // [R651] 主图不动, 放不下就让整图溢出、右栏滚动
                          fillHeight={chartAreaH > 0 ? chartAreaH : undefined}
                          // [R783] 日K 就是日K: 不再右侧挂分时小图。分时是头部独立视图,
                          // 由「分时」按钮进入(用户: 「日K里面不需要显示分时, 除非我点了分时」)
                          showIntraday={false}
                          dateRange={heroRange}
                          // 区间取到了还不够: 默认只露最后 N 根
                          visibleBars={reviewDays}
                          priceLines={monitorPriceLines}
                          onPriceDoubleClick={openPriceAlert}
                          refetchIntervalMs={intradayRefetchMs}
                          prefetchSymbols={prefetchSymbols}
                          addedDate={addedDate}
                          // [R660] 与「关键价位」共用同一份开关/悬停, 盘中同样现拉最新一根
                          levelControls={levelCtl}
                          levelHoveredKey={levelHover}
                          onLevelHoverKey={setLevelHover}
                          refreshLive
                          // [R671] 指标行已并进头部, 这里只画图
                          hideInfoBar
                          // [R673] 中栏本身就是一栏, 不再罩卡框
                          flat
                          // [R680] 回测调参放进图上方工具栏, 排在「异动 / 自选」之后
                          toolbarExtra={<BacktestEntry symbol={symbol} />}
                        />
                      ) : (
                        // [R437] 与旧分时页同一套: 上面一条信息栏(只要信息栏, 不画日 K), 下面多日分时。
                        // [R671] 信息栏已并进头部第二行, 这里只剩多日分时。
                        <StockMultiDayIntradayChart
                          symbol={symbol}
                          days={effectiveIntradayDays}
                          height={chartHeight ?? 480}
                          refetchIntervalMs={intradayRefetchMs}
                          priceLines={monitorPriceLines}
                          onPriceDoubleClick={openPriceAlert}
                          flat
                        />
                      )}
                    </ChartLevelsSection>
                  )}
                </div>
              </div>

              {/* 右栏: 价位 —— [R665] 用户: 「当前价这部分挪到右边」。
                  [R670] 当前价回头部唯一提供。
                  [R672] 这一栏常驻: 用户要「时刻显示右侧价位那部分」, 通道三档也回列。
                  [R680] 价位列表改成阶梯 —— 压力在上、现价居中、支撑在下, 每条带距离。
                  [R681] 三档位置曾搬回左栏。
                  [R682] 权限反转: 左栏整块撤掉, 趋势六态 / 通道阶段 / 三档位置并到这一栏顶部。
                  [R707] 左栏恢复并装回三格, 这一栏回到只放价位阶梯 —— 三栏重新是
                  「现状 / 图 / 价位」。 */}
              <div className="border-t border-border/60 px-4 py-4 sm:px-6 xl:min-h-0 xl:overflow-y-auto xl:border-t-0 xl:border-l">
                {!shownLevels.effLevels ? (
                  <div className="text-xs text-muted">…</div>
                ) : levelPanelEmpty ? (
                  <div className="text-xs text-muted">未开启价位 —— 在图上方「价位」开关里打开</div>
                ) : (
                  <LevelOverview
                    levels={shownLevels.effLevels}
                    activeTypes={levelCtl.activeTypes}
                    pivotRank={levelCtl.pivotRank}
                    close={heroRows.at(-1)?.close}
                    hoveredKey={levelHover}
                    onHover={setLevelHover}
                    stacked
                    ladder
                    // [R674] 右栏本身就是一栏, 不再在栏里罩一层圆角框
                    flat
                  />
                )}
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
