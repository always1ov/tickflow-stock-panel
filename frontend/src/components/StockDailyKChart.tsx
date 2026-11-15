import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState, type ComponentType, type ReactNode } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { type KlineRow } from '@/lib/api'
import { klineDailyQueryOptions, klineDateRange } from '@/lib/kline'
import { storage } from '@/lib/storage'
import type { ChartMarker, ChartPriceLine, ChartRange, ChartRenderer, DailyAnalysisPane, DailyChartProps, OHLC, VolumeCompareConfig } from '@/lib/chart-types'
import { DAILY_LINE_COLORS, SUB_CHART_META } from '@/lib/chart-indicators'

/**
 * [R659] 用户: 「日K 里面的副图 MACD 可以删除了」。MACD 的取数与画法仍是共享的
 * (`LightweightDaily` / `EChartsCandlestick` 都还画, 指数页也在用), 这里只撤掉日K 的入口。
 * [R684] 用户: 「RSI 和 KDJ 都可以删除了」—— 副图指标只剩成交量, 趋势量化 / 量化MACD 紧跟其后。
 */
const DAILY_SUB_CHARTS = SUB_CHART_META.filter(def => def.key === 'vol')

/** [R694] 用户: 「不搞圆点和颜色切换了，异动这个按钮就直接控制，效果以后只有颜色这一种显示方式」——
 *  「圆点 / 颜色」两个显示方式撤掉, 「异动」只剩开关一个职责, 图上固定按颜色画。 */
import {
  CHART_LAYOUT, SUB_PANE_GAP, dailyChartHeight, fitAnalysisPaneHeights, quantPaneHeight, trendPaneHeight,
} from '@/lib/chart-layout'
import { PANE_HEADER_H } from '@/lib/analysisPanes'
import { useStockQuantMacd, useStockTrendQuant } from '@/lib/useStockAnalysisPanes'
import { useShownLevels } from '@/components/stock-analysis/AnalysisKChart'
import { Fib2GrainDialog } from '@/components/stock-analysis/Fib2GrainDialog'
import { useStockLevels } from '@/components/stock-analysis/StockLevelsPanel'
import {
  DEFAULT_LEVEL_TYPES, useLevelControls, type LevelControls,
} from '@/components/stock-analysis/levelControls'
import { LevelToolbar } from '@/components/stock-analysis/LevelToolbar'
import {
  LEVEL_GROUPS, buildAnalysisChartModel, hitTestAnalysis,
} from '@/components/stock-analysis/analysis-chart-model'
import { fib2Status } from '@/lib/fib2Status'
import { LEVEL_CURVE_COLOR, fib2RoleColor, levelColors, useChartTheme, useTheme } from '@/lib/theme'
import {
  levelFib2Overlay, levelLastPriceLine, withFib2Future,
} from '@/lib/levelOverlays'

const EChartsCandlestick = lazy(() => import('./EChartsCandlestick').then(m => ({ default: m.EChartsCandlestick })))
const LightweightDaily = lazy(() => import('./charts/LightweightDaily').then(m => ({ default: m.LightweightDaily })))

const SUB_INFO_H = 16
const SUB_GAP = 4
/** [R652] 主图上那四条默认均线 —— 工具栏逐个开关, 顺序与画线顺序一致 */
const MA_KEYS = ['ma5', 'ma10', 'ma20', 'ma60'] as const
/**
 * [R689] 胶囊色点，只给主图那四条均线用（[R690] 用户：「只有主图指标才会有『颜色+文字』」）。
 * 四色与 `LightweightDaily` 画线取同一份(`DAILY_LINE_COLORS`), 点即图上那条线。
 */
const MA_DOTS: Record<typeof MA_KEYS[number], { dark: string; light: string }> = {
  ma5: DAILY_LINE_COLORS.gray,
  ma10: DAILY_LINE_COLORS.blue,
  ma20: DAILY_LINE_COLORS.orange,
  ma60: DAILY_LINE_COLORS.plum,
}
const DEFAULT_VOLUME_COMPARE: VolumeCompareConfig = { enabled: true, days: 1 }

function normalizeVolumeCompare(config: VolumeCompareConfig): VolumeCompareConfig {
  return {
    enabled: config.enabled !== false,
    days: Math.max(1, Math.min(20, Math.round(Number(config.days) || 1))),
  }
}

interface Props {
  symbol: string
  renderer?: ChartRenderer
  height?: number
  /**
   * [R651] 卡里给整张图留的高度上限。**主图与指标副图的高度、位置不参与压缩** ——
   * 只有两张分析副图(趋势量化 / 量化MACD)按剩余空间收, 收到下限 100 就不再压,
   * 再放不下就让整张图向下溢出、由外层滚动兜底。
   * ([R650] 曾用它等比压缩整图, 主图被压小, 已按用户「主图位置不能动」改掉。)
   */
  maxHeight?: number
  className?: string
  dateRange?: { start: string; end: string }
  markers?: ChartMarker[]
  ranges?: ChartRange[]
  priceLines?: ChartPriceLine[]
  showLimitMarkers?: boolean
  showIndicatorControls?: boolean
  showMarkerToggle?: boolean
  showMA?: boolean
  showInfoBar?: boolean
  /** 初始可见蜡烛根数; 'all' = 适配显示全部数据 */
  visibleBars?: number | 'all'
  linkedPrice?: number | null
  onDateClick?: (date: string) => void
  onPriceDoubleClick?: (price: number, currentPrice: number) => void
  /** 扩展数据列参数（逗号分隔 config_id.field_name），透传给 klineDaily 接口 */
  extColumns?: string
  /** 加入自选日 (北京时间 YYYY-MM-DD); 有值时日K主图绘制「自选」竖虚线 */
  addedDate?: string | null
  /**
   * [R660] 价位开关状态由外面持有(个股弹窗): 与「关键价位」用同一份 `useLevelControls`,
   * 切视图再切回来, 开着的那几类还在。不传则自己持有(详情页等其它入口不受影响)。
   */
  levelControls?: LevelControls
  /** [R660] 悬停高亮状态由外面持有(个股弹窗左栏价位面板联动); 不传则自己持有 */
  hoveredKey?: string | null
  onHoverKey?: (key: string | null) => void
  /** [R660] 回测「成交K线」弹窗不需要这排价位开关 */
  showLevelToolbar?: boolean
  /** [R680] 工具栏右端、「异动 / 自选」之后的一颗东西(弹窗放「回测调参」) */
  toolbarExtra?: ReactNode
  /** [R660] 盘中现拉最新一根, 与关键价位视图同口径 */
  refreshLive?: boolean
}

function isValidRow(r: any): boolean {
  return r && r.date != null && r.open != null && r.close != null
}

export function toOHLC(rows: KlineRow[]): OHLC[] {
  return rows
    .filter(isValidRow)
    .map(r => ({
      date: typeof r.date === 'string' ? r.date.slice(0, 10) : String(r.date),
      open: Number(r.open),
      high: Number(r.high),
      low: Number(r.low),
      close: Number(r.close),
      volume: Number(r.volume ?? 0),
      ma5: r.ma5 != null ? Number(r.ma5) : null,
      ma10: r.ma10 != null ? Number(r.ma10) : null,
      ma20: r.ma20 != null ? Number(r.ma20) : null,
      ma60: r.ma60 != null ? Number(r.ma60) : null,
      macd_dif: r.macd_dif != null ? Number(r.macd_dif) : null,
      macd_dea: r.macd_dea != null ? Number(r.macd_dea) : null,
      macd_hist: r.macd_hist != null ? Number(r.macd_hist) : null,
      rsi_6: r.rsi_6 != null ? Number(r.rsi_6) : null,
      rsi_14: r.rsi_14 != null ? Number(r.rsi_14) : null,
      rsi_24: r.rsi_24 != null ? Number(r.rsi_24) : null,
      kdj_k: r.kdj_k != null ? Number(r.kdj_k) : null,
      kdj_d: r.kdj_d != null ? Number(r.kdj_d) : null,
      kdj_j: r.kdj_j != null ? Number(r.kdj_j) : null,
      // [R528] 图表画的是 26 日布林(接口现场算的 boll26_*), 不是 enriched 那组 20 日列
      boll_upper: r.boll26_upper != null ? Number(r.boll26_upper) : null,
      boll_mid: r.boll26_mid != null ? Number(r.boll26_mid) : null,
      boll_lower: r.boll26_lower != null ? Number(r.boll26_lower) : null,
    }))
}

function isRecoveredLimitDown(row: KlineRow): boolean {
  // 旧信号定义只涵盖收阳；图表用引擎判定价识别两种阴阳，不改用户的策略信号。
  if (row.limit_down_price === undefined) return row.signal_limit_down_recovery === true
  const { raw_low: low, raw_close: close, limit_down_price: limit } = row
  return [low, close, limit].every(value => typeof value === 'number' && Number.isFinite(value) && value > 0)
    && low! <= limit! && close! > limit!
}

function buildLimitMarkers(rows: KlineRow[], includeLimitDown: boolean): ChartMarker[] {
  const markers: ChartMarker[] = []
  for (const r of rows) {
    const date = typeof r.date === 'string' ? r.date.slice(0, 10) : String(r.date)
    if (includeLimitDown && r.signal_limit_down) {
      markers.push({ date, kind: 'sell', above: false, color: '#22D3EE', label: '跌', event: 'limit_down' })
    } else if (r.signal_broken_limit_up) {
      markers.push({ date, kind: 'neutral', above: true, color: '#8B5CF6', label: '炸', event: 'broken_limit_up' })
    } else if (r.signal_limit_up) {
      const boards: number = r.consecutive_limit_ups ?? 1
      markers.push({ date, kind: 'buy', above: true, color: '#FACC15', label: boards <= 1 ? '板' : String(boards), event: 'limit_up' })
    } else if (includeLimitDown && isRecoveredLimitDown(r)) {
      markers.push({ date, kind: 'neutral', above: false, color: '#60A5FA', label: '翘', event: 'limit_down_recovery' })
    }
  }
  return markers
}

export function getDefaultRange(): { start: string; end: string } {
  return klineDateRange()
}

/**
 * 工具栏小胶囊开关。
 * [R689] 用户: 「参考压力支撑、枢轴点这种指标的显示方式, 颜色+文字」—— 传了 `color` 的
 * (主图 / 副图指标) 走价位开关那套: 前面一颗与图上线条同色的点, 开着时整颗反相
 * (暗色主题白底黑字、亮色主题黑底白字), 色点换成另一套主题的深/亮版, 免得点落在同色底上消失。
 * 不传 `color` 的 (异动 / 自选) 保持原来的强调色高亮。
 */
function ChartPill({
  active, label, color, activeClass, title, onClick,
}: {
  active: boolean
  label: string
  color?: string
  activeClass?: string
  title?: string
  onClick: () => void
}) {
  const dotted = !!color
  // 同价位开关: 反相时底色与常态相反, 色点得换另一套主题那一档
  const base = dotted
    ? `inline-flex w-20 shrink-0 items-center justify-center gap-1.5 whitespace-nowrap px-2 py-0.5 rounded-btn text-micro font-mono cursor-pointer transition-colors duration-hover ring-1 ring-inset focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/60 ${
      active ? 'bg-foreground text-surface font-medium ring-foreground' : 'bg-surface text-foreground ring-border hover:bg-elevated'
    }`
    // [R669] 用户: 「按这个方案统一按钮大小」—— 一排胶囊统一成 65px 宽(最长的「量化MACD」实测 64.8),
    // 高度 19px 不变; 短标签居中, 不再一颗宽一颗窄。
    : `inline-flex w-[65px] shrink-0 items-center justify-center whitespace-nowrap px-2 py-0.5 rounded-btn text-micro font-mono cursor-pointer transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/60 ${
      active ? activeClass : 'bg-surface ring-1 ring-inset ring-border text-foreground hover:text-foreground'
    }`
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      title={title}
      className={base}
    >
      {color && <span className="h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: color }} />}
      {label}
    </button>
  )
}

export function StockDailyKChart({
  symbol,
  renderer = 'echarts',
  height = 520,
  className,
  dateRange: externalDateRange,
  markers,
  ranges,
  priceLines,
  showLimitMarkers = true,
  showIndicatorControls = true,
  showMarkerToggle = true,
  showMA = true,
  showInfoBar = true,
  visibleBars,
  linkedPrice,
  onDateClick,
  onPriceDoubleClick,
  extColumns,
  addedDate,
  maxHeight,
  levelControls,
  hoveredKey: hoveredKeyProp,
  onHoverKey,
  showLevelToolbar = true,
  toolbarExtra,
  refreshLive = false,
}: Props) {
  const [activeIndicators, setActiveIndicators] = useState<string[]>(['vol'])
  // [R652] 四条主图均线逐条可控。[R655] 用户要求默认只留 MA20, 其余三条默认关。
  // ECharts 渲染器画不了单条, 仍按 showMA 整组。
  const [maKeys, setMaKeys] = useState<string[]>(() => showMA ? ['ma20'] : [])
  // [R649] 关键价位那两张副图并入日K, 默认关闭 —— 与改版前日K一样只留成交量。
  const [showTrendQuant, setShowTrendQuant] = useState(false)
  const [showQuantMacd, setShowQuantMacd] = useState(false)
  const [showMarkers, setShowMarkers] = useState(true)
  // 加入自选日标注（与「异动」标记相互独立）
  const [showAddedMark, setShowAddedMark] = useState(true)
  const [volumeCompare, setVolumeCompare] = useState<VolumeCompareConfig>(() =>
    normalizeVolumeCompare(storage.stockVolumeCompare.get(DEFAULT_VOLUME_COMPARE)),
  )
  const dateRange = externalDateRange ?? getDefaultRange()

  // 查询配置统一来自 klineDailyQueryOptions, 与 StockPanel 信息条/邻近预取共享同一 cache key (只发一次请求)
  // [R660] refreshLive 时缓存键多一格 'live', 且调用方(StockPanel)透传同一个值, 仍不会重复请求。
  const klineOptions = klineDailyQueryOptions(symbol, dateRange, extColumns, { refreshLive })
  const kline = useQuery({ ...klineOptions, enabled: !!symbol })
  const qc = useQueryClient()
  // [R660] 与关键价位同一套跟进: 后台现拉最新一根时, 稍后再取一次, 盘中最后一根不落后。
  const liveRefresh = kline.data?.live_refresh
  const klineKey = klineOptions.queryKey
  const klineKeyId = JSON.stringify(klineKey)
  useEffect(() => {
    if (liveRefresh !== 'started' || !symbol) return
    const timers = [1500, 4000].map(ms => setTimeout(
      () => qc.invalidateQueries({ queryKey: klineKey }), ms))
    return () => timers.forEach(clearTimeout)
  }, [liveRefresh, kline.dataUpdatedAt, symbol, qc, klineKeyId])

  const rows = useMemo(() => toOHLC(kline.data?.rows ?? []), [kline.data?.rows])
  const stockInfo = kline.data?.stock_info
  const limitMarkers = useMemo(() => buildLimitMarkers(kline.data?.rows ?? [], renderer === 'lightweight'), [kline.data?.rows, renderer])
  const allMarkers = useMemo(() => [
    ...(markers ?? []),
    ...(showLimitMarkers ? limitMarkers : []),
  ], [limitMarkers, markers, showLimitMarkers])

  const toggleIndicator = useCallback((key: string) => {
    setActiveIndicators(prev => prev.includes(key) ? prev.filter(k => k !== key) : [...prev, key])
  }, [])

  const toggleMA = useCallback((key: string) => {
    setMaKeys(prev => prev.includes(key) ? prev.filter(k => k !== key) : [...prev, key])
  }, [])

  const updateVolumeCompare = useCallback((patch: Partial<VolumeCompareConfig>) => {
    setVolumeCompare(prev => {
      const next = normalizeVolumeCompare({ ...prev, ...patch })
      storage.stockVolumeCompare.set(next)
      return next
    })
  }, [])

  const activeSubDefs = activeIndicators
    .map(key => SUB_CHART_META.find(s => s.key === key))
    .filter((d): d is typeof SUB_CHART_META[number] => !!d)

  // [R649] 两张分析副图只在 lightweight 渲染下存在; 数据与关键价位视图同源(同一查询键)。
  const tquantQ = useStockTrendQuant(symbol, showTrendQuant)
  const qmacdQ = useStockQuantMacd(symbol, showQuantMacd)

  // [R653] 关键价位主图那套价位指标并进日K: 取数(`QK.stockLevels` 同一个键)、价位的收集与画法
  // 与「关键价位」视图共用同一份, 不新增接口、不另算口径。
  // [R660] 开关与悬停状态由个股弹窗持有(与「关键价位」同一份), 切视图保持; 其它入口不传就自己持有。
  const theme = useTheme()
  const ownLevelCtl = useLevelControls(DEFAULT_LEVEL_TYPES)
  const levelCtl = levelControls ?? ownLevelCtl
  const [ownHoveredKey, setOwnHoveredKey] = useState<string | null>(null)
  const hoveredKey = hoveredKeyProp ?? ownHoveredKey
  const setHoveredKey = onHoverKey ?? setOwnHoveredKey
  const [fib2FitOpen, setFib2FitOpen] = useState(false)
  const levelsQ = useStockLevels(symbol, renderer === 'lightweight')
  const shown = useShownLevels(levelsQ.data?.levels, levelsQ.data?.fib2, kline.data?.rows ?? [],
    levelCtl.fib2Grain, levelCtl.fib2ShowTargets)
  const levelColorsByTheme = levelColors(theme)
  const ct = useChartTheme()
  const roleColor = useCallback((role: string) => fib2RoleColor(role, theme), [theme])
  const levelPalette = useMemo(() => ({ ...levelColorsByTheme, ...LEVEL_CURVE_COLOR }),
    [levelColorsByTheme])
  const lastClose = rows.at(-1)?.close
  // [R660] 价位横线/曲线直接吃「关键价位」同一个模型: 标签带数值、曲线右端带端值、
  // 悬停时该线加粗其余淡化 —— 不再在 levelOverlays 里另拼一套。
  const levelModel = useMemo(() => {
    if (renderer !== 'lightweight') return null
    return buildAnalysisChartModel({
      rows: kline.data?.rows ?? [],
      levels: shown.effLevels,
      series: levelsQ.data?.series,
      seriesDates: levelsQ.data?.dates,
      activeTypes: levelCtl.activeTypes,
      pivotRank: levelCtl.pivotRank,
      hoveredKey,
      colors: levelPalette,
      roleColor,
    })
  }, [renderer, kline.data?.rows, shown.effLevels, levelsQ.data?.series, levelsQ.data?.dates,
    levelCtl.activeTypes, levelCtl.pivotRank, hoveredKey, levelPalette, roleColor])
  // [R411] 形态状态行读整档 `fib2Raw`(不是减线后的), 与关键价位同一份判据。
  const fib2Line = useMemo(() => fib2Status({
    dates: rows.map(row => row.date),
    close: lastClose,
    thrust: levelsQ.data?.fib2?.thrust,
    markers: levelsQ.data?.fib2?.markers,
    zone: shown.fib2Zone,
    levels: shown.fib2Raw ?? [],
  }), [rows, lastClose, levelsQ.data?.fib2, shown.fib2Zone, shown.fib2Raw])
  // [R660] 与关键价位同一套清理: 换标的 / 关掉价位组后, 旧的高亮不残留。
  useEffect(() => { setHoveredKey(null) }, [symbol])
  useEffect(() => {
    if (hoveredKey != null && levelModel && !levelModel.hoverKeys.has(hoveredKey)) setHoveredKey(null)
  }, [levelModel, hoveredKey, setHoveredKey])
  const handleLevelCrosshair = useCallback((point: { time: string; price: number; pixelsPerPrice: number } | null) => {
    if (!levelModel || !point) {
      if (hoveredKey != null) setHoveredKey(null)
      return
    }
    const index = levelModel.dateIndex.get(point.time) ?? -1
    const next = index < 0 ? null : hitTestAnalysis(levelModel, point.price, point.pixelsPerPrice, index)
    if (next !== hoveredKey) setHoveredKey(next)
  }, [levelModel, hoveredKey, setHoveredKey])
  // [R654] 斐波那契Ⅱ型: 上攻段底色、回踩密集带、首次回踩标记、「未来」分隔线与末尾三个空槽。
  const fib2Overlay = useMemo(() => renderer !== 'lightweight'
    ? { priceLines: [], ranges: [], labels: [], verticals: [], future: null }
    : levelFib2Overlay({
      active: levelCtl.activeTypes,
      fib2: levelsQ.data?.fib2,
      fib2Zone: shown.fib2Zone,
      rows: kline.data?.rows ?? [],
      lastClose,
      theme,
      fibColor: levelColorsByTheme.fib2,
      textColor: ct.text,
    }), [renderer, levelCtl.activeTypes, levelsQ.data?.fib2, shown.fib2Zone, kline.data?.rows,
    lastClose, theme, levelColorsByTheme, ct.text])
  const levelLines = useMemo(() => renderer !== 'lightweight' ? [] : [
    ...(levelModel?.annotations.priceLines ?? []),
    ...fib2Overlay.priceLines,
    ...levelLastPriceLine(lastClose, ct.text),
  ], [renderer, levelModel, fib2Overlay, lastClose, ct.text])
  const levelSeries = useMemo(() => renderer !== 'lightweight' || !levelModel
    ? []
    : withFib2Future(levelModel.series.filter(item => item.id.startsWith('curve:')), fib2Overlay.future),
  [renderer, levelModel, fib2Overlay.future])
  // [R663] 右侧标签带按当前最长标签自适应: 标签短就收窄, 不白占地方。
  // [R668] 用户要回到「右侧留白带之前那个版本」—— 带子与自适带宽都撤了, 标签画回图内。
  const analysisPanes = useMemo<DailyAnalysisPane[]>(() => {
    if (renderer !== 'lightweight') return []
    const panes: DailyAnalysisPane[] = []
    if (showTrendQuant) {
      panes.push({ kind: 'trend', height: trendPaneHeight(height), data: tquantQ.data, error: tquantQ.isError })
    }
    if (showQuantMacd) {
      panes.push({
        kind: 'quant', height: quantPaneHeight(height), topInset: SUB_PANE_GAP, headerH: PANE_HEADER_H,
        data: qmacdQ.data, error: qmacdQ.isError,
      })
    }
    return panes
  }, [renderer, showTrendQuant, showQuantMacd, height, tquantQ.data, tquantQ.isError, qmacdQ.data, qmacdQ.isError])
  // ECharts 渲染器(EChartsCandlestick 自己排版)的副图占位, 与 R650 前一致, 本轮不动。
  let subExtraH = 0
  activeSubDefs.forEach(def => { subExtraH += SUB_INFO_H + def.height })
  if (activeSubDefs.length > 0) subExtraH += activeSubDefs.length * SUB_GAP + 14
  const baseChartHeight = renderer === 'lightweight'
    ? dailyChartHeight(height, activeSubDefs.length)
    : height + subExtraH

  // [R651] 主图与指标副图的高度、位置一律不动; 两张分析副图只吃卡里剩下的空间,
  // 不够就压它们自己(下限 100), 再不够就让整张图向下溢出滚动 —— 不拿主图去换。
  const fittedPanes = useMemo(() => {
    if (!analysisPanes.length || !maxHeight) return analysisPanes
    const heights = fitAnalysisPaneHeights(
      analysisPanes.map(pane => pane.height), Math.max(360, maxHeight) - baseChartHeight)
    return analysisPanes.map((pane, index) => ({ ...pane, height: heights[index] }))
  }, [analysisPanes, maxHeight, baseChartHeight])
  const chartHeight = baseChartHeight + fittedPanes.reduce((sum, pane) => sum + pane.height, 0)
  // [R667] 副图开关那一排现在允许换行(胶囊不再被挤成竖排), 高度不再恒为 40 ——
  // 量一下实际高度再从画布高度里扣, 否则折成两排时卡片会多出 16px。
  const toolbarRef = useRef<HTMLDivElement>(null)
  const [toolbarH, setToolbarH] = useState<number>(CHART_LAYOUT.toolbar)
  useEffect(() => {
    const el = toolbarRef.current
    if (!el) { setToolbarH(0); return }
    const ro = new ResizeObserver(entries => setToolbarH(entries[0].contentRect.height))
    ro.observe(el)
    return () => ro.disconnect()
  }, [showIndicatorControls, rows.length, renderer])
  const Chart = (renderer === 'lightweight' ? LightweightDaily : EChartsCandlestick) as ComponentType<DailyChartProps>

  // [R686] 用户: 「『成交量 量比 前1日均量 趋势量化 量化MACD』应该这样排列『成交量 趋势量化 量化MACD 量比 前1日均量』,
  // 前面都是指标」—— 量比那组是成交量的参数、不是指标, 排到所有指标胶囊之后, 单独跟一条竖线。
  // [R684] 两种渲染器都要用同一份胶囊, 提到 return 之前只写一遍。
  // [R656] 原来的 BOLL 开关撤下 —— 26 日布林改由「主图指标」里那排价位开关的「26日布林」控制。
  // [R689] 色点 = 图上那条线的主色。开着的胶囊反相(白底 / 黑底), 点得换成另一套主题那一档,
  // 否则暗色主题里那颗近黄的点点在白底上就没了 —— 与价位开关 `LC_ON` 同一个做法。
  // [R690] 用户: 「只有主图指标才会有『颜色+文字』」—— 这套只留给均线四颗, 副图指标退回纯文字胶囊。
  const dotColor = (pal: { dark: string; light: string }, on: boolean) =>
    on ? pal[theme === 'dark' ? 'light' : 'dark'] : pal[theme]

  const subIndicatorPills = DAILY_SUB_CHARTS.map(ind => (
    <ChartPill
      key={ind.key}
      active={activeIndicators.includes(ind.key)}
      label={ind.label}
      activeClass="bg-accent/20 text-accent"
      onClick={() => toggleIndicator(ind.key)}
    />
  ))

  // [R683] 「量比」只对成交量生效; [R686] 排位从成交量后面挪到副图指标全部之后。
  const volumeCompareControl = activeIndicators.includes('vol') && (
    <div className="ml-0.5 flex h-5 items-center gap-1.5 border-l border-border/70 pl-2">
      <span className="text-micro text-muted">量比</span>
      <button
        type="button"
        role="switch"
        aria-checked={volumeCompare.enabled}
        aria-label="开启量能对比"
        title={volumeCompare.enabled ? '关闭量能对比' : '开启量能对比'}
        onClick={() => updateVolumeCompare({ enabled: !volumeCompare.enabled })}
        className={`relative h-3.5 w-6 shrink-0 rounded-full transition-colors ${
          volumeCompare.enabled ? 'bg-accent' : 'bg-surface border border-border'
        }`}
      >
        <span className={`absolute left-0 top-0.5 h-2.5 w-2.5 rounded-full bg-white transition-transform ${
          volumeCompare.enabled ? 'translate-x-3' : 'translate-x-0.5'
        }`} />
      </button>
      <select
        aria-label="量能对比周期"
        value={volumeCompare.days}
        disabled={!volumeCompare.enabled}
        onChange={event => updateVolumeCompare({ days: Number(event.target.value) })}
        className="h-5 rounded-btn border border-border bg-base px-1 text-micro text-secondary outline-none disabled:opacity-40"
      >
        {Array.from({ length: 20 }, (_, index) => index + 1).map(days => (
          <option key={days} value={days}>前{days}日均量</option>
        ))}
      </select>
    </div>
  )

  // [R649] 从「关键价位」并过来的两张副图 —— 固定排在各指标副图之后; ECharts 渲染没有这两张副图, 不给开关。
  const analysisPanePills = (
    <>
      <ChartPill
        active={showTrendQuant}
        label="趋势量化"
        activeClass="bg-accent/20 text-accent"
        onClick={() => setShowTrendQuant(value => !value)}
      />
      <ChartPill
        active={showQuantMacd}
        label="量化MACD"
        activeClass="bg-accent/20 text-accent"
        onClick={() => setShowQuantMacd(value => !value)}
      />
    </>
  )

  // 两个标注开关统一右对齐
  const markerControls = (
    <div className="ml-auto flex items-center gap-1.5">
      {showMarkerToggle && showLimitMarkers && (
        <div className="flex items-center gap-1">
          <ChartPill
            active={showMarkers}
            label="异动"
            activeClass="text-[#FACC15] bg-[#FACC15]/10"
            title={showMarkers ? '隐藏涨停 / 炸板 / 跌停 / 翘板着色' : '显示涨停 / 炸板 / 跌停 / 翘板着色'}
            onClick={() => setShowMarkers(v => !v)}
          />
        </div>
      )}
      {/* 激活色与图表里的 ADDED_DATE_COLOR 一致; Tailwind 只认字面量类名, 故写死色值 */}
      {showMarkerToggle && addedDate && (
        <ChartPill
          active={showAddedMark}
          label="自选"
          activeClass="text-[#3B82F6] bg-[#3B82F6]/10"
          title={showAddedMark ? '隐藏K线上的加入自选日标注' : '显示K线上的加入自选日标注'}
          onClick={() => setShowAddedMark(v => !v)}
        />
      )}
      {/* [R680] 回测调参 —— 用户: 「还是放到中里面的『异动 颜色 自选』的自选的后面」 */}
      {toolbarExtra}
      {/* [R688] 用户: 「全部清除放到回测按钮的后面」—— 从价位那排挪到工具栏右端。
          价位开关只在这个渲染器里有, ECharts 那边不画。 */}
      {renderer === 'lightweight' && (
        <button
          type="button"
          onClick={levelCtl.clearAll}
          disabled={levelCtl.activeTypes.size === 0}
          title="清空所有已开启的价位"
          className="inline-flex shrink-0 items-center justify-center whitespace-nowrap rounded-btn bg-surface px-2 py-0.5 text-micro text-secondary ring-1 ring-inset ring-border transition-colors duration-hover cursor-pointer hover:text-foreground disabled:cursor-not-allowed disabled:opacity-40"
        >
          全部清除
        </button>
      )}
    </div>
  )

  if (!symbol) return null

  return (
    <div className={className} style={{ minHeight: chartHeight }}>
      {showIndicatorControls && rows.length > 0 && (
        <div ref={toolbarRef} className={renderer === 'lightweight' ? 'border-b border-border/50 bg-elevated/20' : 'flex items-center gap-1.5 px-1 pb-0.5'}>
          {/* [R684] 用户: 「(压力支撑 / 枢轴点 / 前高前低 / 26日布林 / 量化通道短期·中期·长期 /
              ATR波动通道 / 缺口位 / 斐波那契Ⅰ型 / 整数关口 / 六态关键点)这些都是主图指标」——
              这些价位开关本来就画在主图上, 和四条均线同属主图指标, 不该自成第三类、还挂不上名字。
              工具栏因此按专业术语分三段: 主图指标(均线) → 主图指标续(价位开关, 缩进对齐) → 副图指标。 */}
          {renderer === 'lightweight' && (
            <>
              {/* [R691] 用户: 「主图指标，也就是第一行…距离上下结构分隔线太远了，留白了好多空间」——
                  外边距收到 4px(上) / 6px(下), 三段之间统一 6px 行距, 整块从 119 高降到 107。
                  [R695] 用户: 「指标这部分往上靠近上下分隔线」—— 再收到 2px(上) / 2px(下), 行间 4px。 */}
              <div className="flex flex-wrap items-center gap-x-1 gap-y-2 px-3 pt-0.5 pb-0">
                <span className="w-16 shrink-0 text-micro text-muted" title="画在主图上的指标">主图指标</span>
                {/* [R652] 主图四条均线各自可开关, 默认只开 MA20; [R689] 色点即那条均线在图上颜色 */}
                {MA_KEYS.map(key => {
                  const on = maKeys.includes(key)
                  return (
                    <ChartPill
                      key={key}
                      active={on}
                      label={key.toUpperCase()}
                      color={dotColor(MA_DOTS[key], on)}
                      onClick={() => toggleMA(key)}
                    />
                  )
                })}
              </div>
              {/* [R653] 价位开关排: 与「关键价位」同一个 LevelToolbar、同一套计数与文案;
                  [R660] 开关/悬停状态由弹窗持有, 切视图保持; 回测「成交K线」弹窗不显示这排;
                  [R683] 用户: 「我不需要『价位 · 1 类』这样折叠，我喜欢指标都放出来」——
                  折叠按钮撤掉, 价位开关常开。
                  [R684] 归到「主图指标」组内: 左侧缩进到与均线那排胶囊的左边缘对齐。 */}
              {showLevelToolbar && (
                <div className="flex flex-wrap items-center gap-y-2 pr-3 pl-3 pt-1 pb-0 sm:pl-20 [&>div]:mb-0 [&>div]:gap-y-2" data-testid="level-toolbar">
                  {/* [R687] 用户: 「全部清除后面的问号按钮删掉」—— 不传 help, 「?」不在弹窗工具栏出现 */}
                  <LevelToolbar
                    groups={LEVEL_GROUPS}
                    controls={levelCtl}
                    effLevels={shown.effLevels}
                    fib2Raw={shown.fib2Raw}
                    fib2={levelsQ.data?.fib2}
                    onOpenFit={symbol ? () => setFib2FitOpen(true) : undefined}
                    showClearAll={false}
                    compact
                  />
                </div>
              )}
              {/* [R411] 形态走到哪一步 —— 只报事实, 一个动词都没有; 显示沿用日K 自己的极简行 */}
              {levelCtl.activeTypes.has('fib2') && fib2Line && (
                <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 px-3 pb-1.5 text-micro leading-5">
                  <span className="h-1.5 w-1.5 shrink-0 rounded-full" style={{ backgroundColor: levelColorsByTheme.fib2 }} />
                  {fib2Line.map((segment, index) => (
                    <span key={segment} className={index === 0 ? 'text-secondary' : 'text-muted'}>
                      {index > 0 && <span className="mr-2 opacity-40">·</span>}
                      {segment}
                    </span>
                  ))}
                </div>
              )}
              <div className="flex flex-wrap items-center gap-x-1 gap-y-2 px-3 pt-1 pb-0.5">
                <span className="w-16 shrink-0 text-micro text-muted" title="画在下方副图里的指标">副图指标</span>
                {subIndicatorPills}
                {analysisPanePills}
                {volumeCompareControl}
              </div>
            </>
          )}
          {renderer !== 'lightweight' && (
            <>
              {subIndicatorPills}
              {volumeCompareControl}
              {markerControls}
            </>
          )}
        </div>
      )}
      {fib2FitOpen && symbol && (
        <Fib2GrainDialog
          symbol={symbol}
          current={levelCtl.fib2Grain}
          onPick={levelCtl.setFib2Grain}
          onClose={() => setFib2FitOpen(false)}
        />
      )}
      {kline.isLoading && <div className="text-sm text-muted py-4">加载中…</div>}
      {kline.isError && <div className="text-sm text-danger py-2">日K加载失败</div>}
      {!kline.isLoading && !kline.isError && (kline.data?.rows?.length ?? 0) > 0 && rows.length === 0 && (
        <div className="text-sm text-danger py-2">数据格式异常，请刷新页面</div>
      )}
      {rows.length > 0 && (
        <Suspense fallback={<div className="flex items-center justify-center text-xs text-muted" style={{ height }}>正在加载图表…</div>}>
        {/* [R696] 用户: 「异动 自选 回测 8% 全部清除这几个按钮挪到换手后面, 保持右对齐」——
            这四颗交回读数条右端, 工具栏第一行只剩「主图指标」那四颗均线。 */}
        <Chart
          data={rows}
          markers={allMarkers}
          ranges={ranges}
          priceLines={priceLines}
          height={chartHeight - (renderer === 'lightweight' ? toolbarH : 22)}
          showMA={showMA}
          maKeys={renderer === 'lightweight' ? maKeys : undefined}
          showInfoBar={showInfoBar}
          showMarkers={showMarkers}
          readoutExtra={renderer === 'lightweight' && showIndicatorControls && rows.length > 0 ? markerControls : undefined}
          stockInfo={stockInfo}
          assetType={kline.data?.asset_type}
          symbol={symbol}
          linkedPrice={linkedPrice}
          onDateClick={onDateClick}
          onPriceDoubleClick={onPriceDoubleClick}
          visibleBars={visibleBars ?? (renderer === 'lightweight' ? undefined : 60)}
          activeIndicators={activeIndicators}
          volumeCompare={volumeCompare}
          addedDate={showAddedMark ? addedDate : null}
          analysisPanes={fittedPanes}
          levelLines={levelLines}
          levelSeries={levelSeries}
          levelRanges={fib2Overlay.ranges}
          levelLabels={fib2Overlay.labels}
          levelVerticals={fib2Overlay.verticals}
          levelFuture={fib2Overlay.future}
          onCrosshairMove={renderer === 'lightweight' ? handleLevelCrosshair : undefined}
        />
        </Suspense>
      )}
    </div>
  )
}
