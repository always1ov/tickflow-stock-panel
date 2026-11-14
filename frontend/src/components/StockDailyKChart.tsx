import { lazy, Suspense, useCallback, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { type KlineRow } from '@/lib/api'
import { klineDailyQueryOptions, klineDateRange } from '@/lib/kline'
import { storage } from '@/lib/storage'
import type { ChartMarker, ChartPriceLine, ChartRange, ChartRenderer, DailyAnalysisPane, DailyMarkerStyle, OHLC, VolumeCompareConfig } from '@/lib/chart-types'
import { OVERLAY_INDICATORS, SUB_CHART_META } from '@/lib/chart-indicators'
import {
  CHART_LAYOUT, SUB_PANE_GAP, dailyChartHeight, fitAnalysisPaneHeights, quantPaneHeight, trendPaneHeight,
} from '@/lib/chart-layout'
import { PANE_HEADER_H } from '@/lib/analysisPanes'
import { useStockQuantMacd, useStockTrendQuant } from '@/lib/useStockAnalysisPanes'
import { useShownLevels } from '@/components/stock-analysis/AnalysisKChart'
import { useStockLevels } from '@/components/stock-analysis/StockLevelsPanel'
import { DEFAULT_LEVEL_TYPES, useLevelControls } from '@/components/stock-analysis/levelControls'
import { LevelToolbar } from '@/components/stock-analysis/LevelToolbar'
import { LEVEL_GROUPS } from '@/components/stock-analysis/analysis-chart-model'
import { LEVEL_CURVE_COLOR, fib2RoleColor, levelColors, useTheme } from '@/lib/theme'
import { levelCurveSeries, levelPriceLines } from '@/lib/levelOverlays'

const EChartsCandlestick = lazy(() => import('./EChartsCandlestick').then(m => ({ default: m.EChartsCandlestick })))
const LightweightDaily = lazy(() => import('./charts/LightweightDaily').then(m => ({ default: m.LightweightDaily })))

const SUB_INFO_H = 16
const SUB_GAP = 4
/** [R652] 主图上那四条默认均线 —— 工具栏逐个开关, 顺序与画线顺序一致 */
const MA_KEYS = ['ma5', 'ma10', 'ma20', 'ma60'] as const
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

/** 工具栏小胶囊开关（指标与标注开关共用一套尺寸/关闭态样式，激活色由调用方给字面量）。 */
function ChartPill({
  active, label, activeClass, title, onClick,
}: {
  active: boolean
  label: string
  activeClass: string
  title?: string
  onClick: () => void
}) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      title={title}
      className={`px-2 py-0.5 rounded-btn text-micro font-mono cursor-pointer transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/60 ${
        active ? activeClass : 'bg-surface border border-border text-foreground hover:text-foreground'
      }`}
    >
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
}: Props) {
  const [activeIndicators, setActiveIndicators] = useState<string[]>(['vol'])
  // [R652] 四条主图均线逐条可控, 默认全开(与改版前一致)。ECharts 渲染器画不了单条, 仍按 showMA 整组。
  const [maKeys, setMaKeys] = useState<string[]>(() => showMA ? [...MA_KEYS] : [])
  // [R649] 关键价位那两张副图并入日K, 默认关闭 —— 与改版前日K一样只留成交量。
  const [showTrendQuant, setShowTrendQuant] = useState(false)
  const [showQuantMacd, setShowQuantMacd] = useState(false)
  const [showMarkers, setShowMarkers] = useState(true)
  const [markerStyle, setMarkerStyle] = useState<DailyMarkerStyle>(() => {
    const saved = storage.stockDailyMarkerStyle.get('label')
    return saved === 'candle' ? 'candle' : 'label'
  })
  // 加入自选日标注（与「异动」标记相互独立）
  const [showAddedMark, setShowAddedMark] = useState(true)
  const [volumeCompare, setVolumeCompare] = useState<VolumeCompareConfig>(() =>
    normalizeVolumeCompare(storage.stockVolumeCompare.get(DEFAULT_VOLUME_COMPARE)),
  )
  const dateRange = externalDateRange ?? getDefaultRange()

  // 查询配置统一来自 klineDailyQueryOptions, 与 StockPanel 信息条/邻近预取共享同一 cache key (只发一次请求)
  const kline = useQuery({ ...klineDailyQueryOptions(symbol, dateRange, extColumns), enabled: !!symbol })

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

  const updateMarkerStyle = (style: DailyMarkerStyle) => {
    setMarkerStyle(style)
    storage.stockDailyMarkerStyle.set(style)
  }

  const activeSubDefs = activeIndicators
    .map(key => SUB_CHART_META.find(s => s.key === key))
    .filter((d): d is typeof SUB_CHART_META[number] => !!d)

  // [R649] 两张分析副图只在 lightweight 渲染下存在; 数据与关键价位视图同源(同一查询键)。
  const tquantQ = useStockTrendQuant(symbol, showTrendQuant)
  const qmacdQ = useStockQuantMacd(symbol, showQuantMacd)

  // [R653] 关键价位主图那套价位指标并进日K: 取数、档位、开关状态与「关键价位」视图共用同一份
  // (`QK.stockLevels` + `useLevelControls`), 不新增接口、不另算口径。
  const theme = useTheme()
  const levelCtl = useLevelControls(DEFAULT_LEVEL_TYPES)
  const levelsQ = useStockLevels(symbol, renderer === 'lightweight')
  const shown = useShownLevels(levelsQ.data?.levels, levelsQ.data?.fib2, kline.data?.rows ?? [],
    levelCtl.fib2Grain, levelCtl.fib2ShowTargets)
  const levelColorsByTheme = levelColors(theme)
  const roleColor = useCallback((role: string) => fib2RoleColor(role, theme), [theme])
  const levelLines = useMemo(() => renderer !== 'lightweight'
    ? [] : levelPriceLines(shown.effLevels, levelCtl.activeTypes, levelCtl.pivotRank,
      { ...levelColorsByTheme, ...LEVEL_CURVE_COLOR }, roleColor),
  [renderer, shown.effLevels, levelCtl.activeTypes, levelCtl.pivotRank, levelColorsByTheme, roleColor])
  const levelSeries = useMemo(() => renderer !== 'lightweight'
    ? [] : levelCurveSeries({
      rows: kline.data?.rows ?? [],
      series: levelsQ.data?.series,
      seriesDates: levelsQ.data?.dates,
      active: levelCtl.activeTypes,
      colors: { ...levelColorsByTheme, ...LEVEL_CURVE_COLOR },
    }),
  [renderer, kline.data?.rows, levelsQ.data?.series, levelsQ.data?.dates, levelCtl.activeTypes, levelColorsByTheme])
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
  const Chart = renderer === 'lightweight' ? LightweightDaily : EChartsCandlestick

  if (!symbol) return null

  return (
    <div className={className} style={{ minHeight: chartHeight }}>
      {showIndicatorControls && rows.length > 0 && (
        <div className={renderer === 'lightweight' ? 'flex min-h-10 flex-wrap items-center gap-1 border-b border-border/50 bg-elevated/20 px-3 py-1.5 xl:h-10 xl:flex-nowrap xl:py-0' : 'flex items-center gap-1.5 px-1 pb-0.5'}>
          {renderer === 'lightweight' && <span className="mr-2 shrink-0 text-xs font-semibold text-foreground">日 K</span>}
          {SUB_CHART_META.map(ind => (
            <ChartPill
              key={ind.key}
              active={activeIndicators.includes(ind.key)}
              label={ind.label}
              activeClass="bg-accent/20 text-accent"
              onClick={() => toggleIndicator(ind.key)}
            />
          ))}
          {OVERLAY_INDICATORS.map(ind => (
            <ChartPill
              key={ind.key}
              active={activeIndicators.includes(ind.key)}
              label={ind.label}
              activeClass="bg-accent/20 text-accent"
              onClick={() => toggleIndicator(ind.key)}
            />
          ))}
          {/* [R652] 主图四条均线各自可开关 —— 与其它指标同一套胶囊, 默认全开 */}
          {renderer === 'lightweight' && MA_KEYS.map(key => (
            <ChartPill
              key={key}
              active={maKeys.includes(key)}
              label={key.toUpperCase()}
              activeClass="bg-accent/20 text-accent"
              onClick={() => toggleMA(key)}
            />
          ))}
          {/* [R649] 从「关键价位」并过来的两张副图 —— 固定排在各指标副图之后 */}
          {renderer === 'lightweight' && (
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
          )}
          {activeIndicators.includes('vol') && (
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
          )}
          {/* 两个标注开关统一右对齐 */}
          <div className="ml-auto flex items-center gap-1.5">
            {showMarkerToggle && showLimitMarkers && (
              <div className="flex items-center gap-1">
                <ChartPill
                  active={showMarkers}
                  label="异动"
                  activeClass="text-[#FACC15] bg-[#FACC15]/10"
                  onClick={() => setShowMarkers(v => !v)}
                />
                {renderer === 'lightweight' && <select
                  aria-label="异动显示方式"
                  title="文字：显示板/炸/跌/翘标记；颜色：涨停为黄，跌停为青蓝；炸板收阳为玫紫、收阴为蓝紫；翘板收阳为薄荷青、收阴为钢蓝。开收同价沿用对应收阴色，影线保留原涨跌色。"
                  value={markerStyle}
                  disabled={!showMarkers}
                  onChange={event => updateMarkerStyle(event.target.value as DailyMarkerStyle)}
                  className="h-5 w-[74px] rounded-btn border border-border bg-base px-1 text-micro text-secondary outline-none focus-visible:ring-2 focus-visible:ring-accent/60 disabled:opacity-40"
                >
                  <option value="label">文字</option>
                  <option value="candle">颜色</option>
                </select>}
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
          </div>
        </div>
      )}
      {/* [R653] 价位开关排: 与「关键价位」同一个 LevelToolbar、同一份状态, 切视图不丢 */}
      {showIndicatorControls && renderer === 'lightweight' && rows.length > 0 && (
        <div className="flex flex-wrap items-center border-b border-border/50 bg-elevated/10 px-3 pt-1.5" data-testid="level-toolbar">
          <LevelToolbar
            groups={LEVEL_GROUPS}
            controls={levelCtl}
            effLevels={shown.effLevels}
            fib2Raw={shown.fib2Raw}
            fib2={levelsQ.data?.fib2}
          />
        </div>
      )}
      {kline.isLoading && <div className="text-sm text-muted py-4">加载中…</div>}
      {kline.isError && <div className="text-sm text-danger py-2">日K加载失败</div>}
      {!kline.isLoading && !kline.isError && (kline.data?.rows?.length ?? 0) > 0 && rows.length === 0 && (
        <div className="text-sm text-danger py-2">数据格式异常，请刷新页面</div>
      )}
      {rows.length > 0 && (
        <Suspense fallback={<div className="flex items-center justify-center text-xs text-muted" style={{ height }}>正在加载图表…</div>}>
        <Chart
          data={rows}
          markers={allMarkers}
          ranges={ranges}
          priceLines={priceLines}
          height={chartHeight - (renderer === 'lightweight' ? CHART_LAYOUT.toolbar : 22)}
          showMA={showMA}
          maKeys={renderer === 'lightweight' ? maKeys : undefined}
          showInfoBar={showInfoBar}
          showMarkers={showMarkers}
          markerStyle={renderer === 'lightweight' ? markerStyle : undefined}
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
        />
        </Suspense>
      )}
    </div>
  )
}
