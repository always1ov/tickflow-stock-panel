import type { AnnotationData } from '@/components/charts/ChartAnnotations'
import type { KlineRow, LevelSeries } from '@/lib/api'
import type { OHLC } from '@/lib/chart-types'
import type { PlotSeries } from '@/lib/lightweight-model'
import { validDailyRows } from '@/lib/lightweight-model'

/**
 * 个股分析「关键价位」图表的纯数据模型。
 *
 * 渲染交给 lightweight-charts（FinancialPlot），这里只负责把后端 rows / levels /
 * 带状指标序列转换成绘图序列与标注，并提供十字线命中判断，便于单测覆盖。
 */

// ===== 价位类型(与后端 levels.py 的 LEVEL_TYPES 对齐) =====
export type LevelType = 'sr' | 'pivot' | 'extreme' | 'boll' | 'keltner_s' | 'keltner_m' | 'keltner_l' | 'atr_stop' | 'gap' | 'fib' | 'round' | 'livermore' | 'fib2'

export interface PriceLevel {
  value: number
  label: string
  type: LevelType
  side: 'resistance' | 'support' | 'neutral'
  strength?: 'strong' | 'medium' | 'weak'
  /** 档位(仅 pivot 有):0=P, 1=R1/S1, 2=R2/S2, 3=R3/S3 */
  rank?: number
  /**
   * 这一条线自己的角色, 盖过所在组的颜色(目前只有斐波那契二型会发)。
   * 它是角色标识, 不是最终颜色 —— 画之前由调用方过 `fib2RoleColor()` 换成当前主题值。
   */
  color?: string
}

/** 价位组开关配置:label = 按钮文案。颜色不在开关上, 单一产地在下面的默认表 + 主题表。 */
export const LEVEL_GROUPS: { key: LevelType; label: string }[] = [
  { key: 'sr',       label: '压力支撑' },       // 橙(成交密集区,价量驱动)
  { key: 'pivot',    label: '枢轴点' },         // 紫
  { key: 'extreme',  label: '前高前低' },       // 黄
  { key: 'boll',     label: '26日布林' },       // 橙(26 日 ±2σ 曲线)
  { key: 'keltner_s',label: '量化通道短期' },   // 青(MA20±2ATR 曲线)
  { key: 'keltner_m',label: '量化通道中期' },   // 浅青(MA60±2.5ATR 曲线)
  { key: 'keltner_l',label: '量化通道长期' },   // 更浅青(MA120±3ATR 曲线)
  { key: 'atr_stop', label: 'ATR波动通道' },    // 红(警示)
  { key: 'gap',      label: '缺口位' },         // 靛(全站禁粉)
  { key: 'fib',      label: '斐波那契Ⅰ型' },   // 金
  { key: 'round',    label: '整数关口' },       // 灰(心理位,弱视觉)
  { key: 'livermore',label: '六态关键点' },     // 蓝(fork 自定)
  { key: 'fib2',     label: '斐波那契Ⅱ型' },   // 深紫(fork 自定)
]

/**
 * 组色兜底表。**只在调用方没传 `colors`(无主题上下文/单测)时使用**;
 * 真正的界面配色单一产地在 `lib/theme.ts` 的 LEVEL_PALETTE, 由组件注入。
 */
const DEFAULT_GROUP_COLORS: Record<LevelType, string> = {
  sr: '#F97316', pivot: '#8B5CF6', extreme: '#EAB308', boll: '#F97316',
  keltner_s: '#06B6D4', keltner_m: '#22D3EE', keltner_l: '#67E8F9',
  atr_stop: '#EF4444', gap: '#3730A3', fib: '#F59E0B', round: '#71717A',
  livermore: '#1D4ED8', fib2: '#6A0DAD',
}

/** 作者单独配过色、不跟组色的曲线(其余曲线一律跟 `group`)。 */
const DEFAULT_CURVE_COLORS: Record<string, string> = {
  boll_mid: '#FB923C', atr_tp: '#F87171', fib2_dma3: '#6A0DAD',
}

/** 带状曲线指标(按组渲染成曲线，而不是水平价位线) */
const CURVE_GROUP_TYPES = new Set<LevelType>(['boll', 'keltner_s', 'keltner_m', 'keltner_l', 'atr_stop'])

// 通道曲线元数据(单一数据源):供绘图序列和右侧预留带标签共用。
//   alignedKey: 与 rows 日期对齐后的 series key
//   group:      所属价位开关组(开关该组即开关这条曲线)
//   endLabel:   右侧端点的文字前缀
export const CURVE_DEFS: { alignedKey: string; group: LevelType; endLabel: string; dashed?: boolean }[] = [
  { alignedKey: 'boll_upper',     group: 'boll',      endLabel: '26日布林上轨', dashed: true },
  { alignedKey: 'boll_lower',     group: 'boll',      endLabel: '26日布林下轨', dashed: true },
  { alignedKey: 'boll_mid',       group: 'boll',      endLabel: '26日布林中轨', dashed: false },
  { alignedKey: 'keltner_s_upper',group: 'keltner_s', endLabel: 'Keltner短上', dashed: true },
  { alignedKey: 'keltner_s_lower',group: 'keltner_s', endLabel: 'Keltner短下', dashed: true },
  { alignedKey: 'keltner_m_upper',group: 'keltner_m', endLabel: 'Keltner中上', dashed: true },
  { alignedKey: 'keltner_m_lower',group: 'keltner_m', endLabel: 'Keltner中下', dashed: true },
  { alignedKey: 'keltner_l_upper',group: 'keltner_l', endLabel: 'Keltner长上', dashed: true },
  { alignedKey: 'keltner_l_lower',group: 'keltner_l', endLabel: 'Keltner长下', dashed: true },
  { alignedKey: 'atr_stop',       group: 'atr_stop',  endLabel: 'ATR下轨', dashed: true },
  { alignedKey: 'atr_tp',         group: 'atr_stop',  endLabel: 'ATR上轨', dashed: true },
  // 斐波那契Ⅱ型的 3 日均线(往后移 3 根)。叫「Ⅱ型均线」, 避免与 MA5 同名。
  { alignedKey: 'fib2_dma3',      group: 'fib2',      endLabel: 'Ⅱ型均线', dashed: false },
]

/** 曲线色:作者的专属色优先, 否则跟所属组色 —— 单一产地, 不许在 CURVE_DEFS 里写死。 */
function curveColorOf(alignedKey: string, group: LevelType, colors?: Record<string, string>): string {
  return colors?.[alignedKey] ?? colors?.[group] ?? DEFAULT_CURVE_COLORS[alignedKey] ?? DEFAULT_GROUP_COLORS[group]
}

/** 画布右侧预留给价位/曲线标签的空白带宽度 (px) */
export const ANALYSIS_LABEL_BAND_PX = 148
export const LEVEL_LINE_OPACITY = 0.9
export const LEVEL_LINE_DIM_OPACITY = 0.12
export const LEVEL_LINE_WIDTH = 1
export const LEVEL_LINE_HIT_WIDTH = 2
const CURVE_COLOR_NORMAL_SUFFIX = 'CC'
const CURVE_COLOR_DIM_SUFFIX = '1F'
const VOL_UP = 'rgba(199,64,64,0.55)'
const VOL_DOWN = 'rgba(45,155,101,0.55)'

// ===== 预留:标记 / 区间(后续新闻面、事件区间用) =====
export interface ChartMarker {
  date: string
  label?: string
  color?: string
  above?: boolean
}
export interface ChartRange {
  start: string
  end: string
  label?: string
  color?: string
}

export interface AnalysisChartInput {
  rows: KlineRow[]
  levels?: Record<LevelType, PriceLevel[]>
  /** 带状曲线指标(布林带/Keltner/ATR)的每日序列 —— 画成跟随时间漂移的曲线 */
  series?: LevelSeries
  /** series 数据对应的日期数组(与 series 各数组对齐) */
  seriesDates?: string[]
  activeTypes: Iterable<LevelType>
  pivotRank?: 1 | 2 | 3
  /** 双向联动高亮:当前悬浮的价位键(levelKey)或曲线组(group) */
  hoveredKey?: string | null
  precision?: number
  markers?: ChartMarker[]
  ranges?: ChartRange[]
  /**
   * 按主题覆盖的价位/曲线颜色。键可以是价位组(group)或曲线 alignedKey;
   * 不传时保持上面的默认色 —— 组件里传 `levelColors(theme)` + `LEVEL_CURVE_COLOR`。
   */
  colors?: Record<string, string>
  /** 单条价位的角色色映射(斐波那契二型用), 不传时把 `PriceLevel.color` 当最终色。 */
  roleColor?: (role: string) => string
}

export interface AnalysisChartModel {
  rows: OHLC[]
  dates: string[]
  dateIndex: Map<string, number>
  series: PlotSeries[]
  annotations: AnnotationData
  /** 当前可悬浮的键:水平价位(levelKey) + 已开启曲线组(group) */
  hoverKeys: Set<string>
  hitLines: { key: string; value: number }[]
  hitCurves: { key: string; values: (number | null)[] }[]
}

/** 价位唯一标识: 同类型同价格视为同一点位(用于联动高亮)。 */
export function levelKey(type: string, value: number): string {
  return `${type}-${value.toFixed(2)}`
}

export function strengthColor(strength: string | undefined, base: string): string {
  // [R409] 强度靠透明度表达, 但最弱一档也不能淡到要凑近看: BF / E6, 叠完常态 0.9。
  if (strength === 'weak') return base + 'BF'
  if (strength === 'medium') return base + 'E6'
  return base
}

function normalizeRows(rows: KlineRow[]): OHLC[] {
  const mapped = rows.map(row => ({
    date: typeof row.date === 'string' ? row.date.slice(0, 10) : String(row.date),
    open: Number(row.open),
    high: Number(row.high),
    low: Number(row.low),
    close: Number(row.close),
    volume: row.volume != null && Number.isFinite(Number(row.volume)) ? Number(row.volume) : undefined,
  }))
  return validDailyRows(mapped)
}

/** 把后端 series(按 seriesDates 对齐)映射到图表 rows 的 dates 顺序,缺失填 null。 */
function alignChannels(series: LevelSeries | undefined, seriesDates: string[] | undefined, dates: string[]): Record<string, (number | null)[]> {
  const aligned: Record<string, (number | null)[]> = {}
  if (!series || !seriesDates?.length) return aligned
  const sourceIndex = new Map(seriesDates.map((date, index) => [date, index]))
  const align = (values: (number | null)[] | undefined): (number | null)[] => dates.map(date => {
    if (!values) return null
    const index = sourceIndex.get(date)
    return index == null ? null : values[index] ?? null
  })
  if (series.boll) {
    aligned.boll_upper = align(series.boll.upper)
    aligned.boll_lower = align(series.boll.lower)
    if (series.boll.mid) aligned.boll_mid = align(series.boll.mid)
  }
  for (const [key, value] of [['keltner_s', series.keltner_s], ['keltner_m', series.keltner_m], ['keltner_l', series.keltner_l]] as const) {
    if (!value) continue
    aligned[`${key}_upper`] = align(value.upper)
    aligned[`${key}_lower`] = align(value.lower)
  }
  if (series.atr) {
    aligned.atr_stop = align(series.atr.stop_loss)
    aligned.atr_tp = align(series.atr.take_profit)
  }
  if (series.fib2) aligned.fib2_dma3 = align(series.fib2.dma3)
  return aligned
}

export interface CollectedPriceLine { value: number; label: string; color: string; type: string }

/** 收集要画的水平价位线(按开启的组 + 枢轴档位 + 强度配色)。通道组走曲线,不在此画线。 */
export function collectPriceLines(
  levels: Record<LevelType, PriceLevel[]> | undefined,
  active: Set<LevelType>,
  pivotRank: 1 | 2 | 3,
  colors?: Record<string, string>,
  roleColor?: (role: string) => string,
): CollectedPriceLine[] {
  if (!levels) return []
  const out: CollectedPriceLine[] = []
  for (const group of LEVEL_GROUPS) {
    if (!active.has(group.key)) continue
    for (const point of levels[group.key] ?? []) {
      if (point.type === 'pivot' && point.rank !== undefined && point.rank > pivotRank) continue
      if (CURVE_GROUP_TYPES.has(point.type)) continue
      const base = point.color
        ? (roleColor ? roleColor(point.color) : point.color)
        : (colors?.[group.key] ?? DEFAULT_GROUP_COLORS[group.key])
      // 斐波那契二型不按强弱淡化: 哪些线挤在一起已由密集带表达, 线本身保持实色。
      out.push({
        value: point.value, label: point.label,
        color: point.type === 'fib2' ? base : strengthColor(point.strength, base),
        type: point.type,
      })
    }
  }
  return out
}

function curveState(hoveredKey: string | null, group: LevelType): 'normal' | 'hit' | 'dim' {
  if (hoveredKey == null) return 'normal'
  return hoveredKey === group ? 'hit' : 'dim'
}

function curveLineColor(color: string, state: 'normal' | 'hit' | 'dim'): string {
  if (state === 'hit') return color
  return color + (state === 'dim' ? CURVE_COLOR_DIM_SUFFIX : CURVE_COLOR_NORMAL_SUFFIX)
}

function curveLabelColor(color: string, state: 'normal' | 'hit' | 'dim'): string {
  return state === 'dim' ? color + CURVE_COLOR_DIM_SUFFIX : color
}

export function buildAnalysisChartModel(input: AnalysisChartInput): AnalysisChartModel {
  const precision = input.precision ?? 2
  const rows = normalizeRows(input.rows)
  const dates = rows.map(row => row.date)
  const dateIndex = new Map(dates.map((date, index) => [date, index]))
  const active = new Set(input.activeTypes)
  const pivotRank = input.pivotRank ?? 1
  const hoveredKey = input.hoveredKey ?? null
  const dimming = hoveredKey != null
  const aligned = alignChannels(input.series, input.seriesDates, dates)

  const series: PlotSeries[] = [{
    id: 'price', type: 'Candlestick', pane: 0,
    data: rows.map(row => ({ time: row.date, open: row.open, high: row.high, low: row.low, close: row.close })),
  }]
  series.push({
    id: 'volume', type: 'Volume', pane: 1, priceFormat: 'volume',
    data: rows.map(row => ({
      time: row.date,
      value: row.volume ?? 0,
      color: row.close >= row.open ? VOL_UP : VOL_DOWN,
    })),
  })

  const hitCurves: AnalysisChartModel['hitCurves'] = []
  for (const def of CURVE_DEFS) {
    if (!active.has(def.group)) continue
    const values = aligned[def.alignedKey]
    if (!values || !values.some(value => value != null)) continue
    const state = curveState(hoveredKey, def.group)
    const baseColor = curveColorOf(def.alignedKey, def.group, input.colors)
    series.push({
      id: `curve:${def.alignedKey}`, type: 'Line', pane: 0,
      color: curveLineColor(baseColor, state),
      lineWidth: state === 'hit' ? 2 : 1,
      precision,
      data: values.map((value, index) => value == null ? { time: dates[index] } : { time: dates[index], value }),
    })
    hitCurves.push({ key: def.group, values })
  }

  const horizontal = collectPriceLines(input.levels, active, pivotRank, input.colors, input.roleColor)
  const lines: NonNullable<AnnotationData['priceLines']> = []
  const hoveredLines: NonNullable<AnnotationData['priceLines']> = []
  for (const line of horizontal) {
    const key = levelKey(line.type, line.value)
    const hit = hoveredKey === key
    const entry = {
      value: line.value,
      label: `${line.label} ${line.value.toFixed(precision)}`,
      color: line.color,
      opacity: dimming ? (hit ? 1 : LEVEL_LINE_DIM_OPACITY) : (line.type === 'fib2' ? 1 : LEVEL_LINE_OPACITY),
      width: hit ? LEVEL_LINE_HIT_WIDTH : LEVEL_LINE_WIDTH,
      labelPriority: hit ? 3 : 2,
    }
    ;(hit ? hoveredLines : lines).push(entry)
  }
  // 通道曲线最新值:右侧预留带内只画文字标签(不画水平线),与旧图 endLabel 位置一致。
  for (const def of CURVE_DEFS) {
    if (!active.has(def.group)) continue
    const values = aligned[def.alignedKey]
    if (!values) continue
    let lastValue: number | null = null
    for (let index = values.length - 1; index >= 0; index--) {
      if (values[index] != null) { lastValue = values[index]; break }
    }
    if (lastValue == null) continue
    const state = curveState(hoveredKey, def.group)
    lines.push({
      value: lastValue,
      label: `${def.endLabel} ${lastValue.toFixed(precision)}`,
      color: curveLabelColor(curveColorOf(def.alignedKey, def.group, input.colors), state),
      noLine: true,
      opacity: 1,
      labelPriority: state === 'hit' ? 3 : 1,
    })
  }
  lines.push(...hoveredLines)

  const labels = (input.markers ?? []).flatMap(marker => {
    const index = dateIndex.get(marker.date)
    if (index == null) return []
    const row = rows[index]
    return [{
      time: row.date,
      value: marker.above ? row.high : row.low,
      text: marker.label ?? '',
      ...(marker.color ? { color: marker.color } : {}),
    }]
  })

  const annotations: AnnotationData = {
    dates,
    priceLines: lines,
    ...(labels.length > 0 ? { labels } : {}),
    ...(input.ranges?.length ? { ranges: input.ranges.map(range => ({ ...range })) } : {}),
  }

  const hoverKeys = new Set<string>()
  for (const line of horizontal) hoverKeys.add(levelKey(line.type, line.value))
  for (const curve of hitCurves) hoverKeys.add(curve.key)

  return {
    rows, dates, dateIndex, series, annotations, hoverKeys,
    hitLines: horizontal.map(line => ({ key: levelKey(line.type, line.value), value: line.value })),
    hitCurves,
  }
}

/**
 * 十字线命中:按像素容差返回最近的价位键(水平价位优先于曲线)。
 * pricePerPixel = 竖轴 1px 对应的价格,用于把价格差换算成像素。
 */
export function hitTestAnalysis(
  model: AnalysisChartModel,
  price: number,
  pricePerPixel: number,
  index: number,
  tolerancePx = 6,
): string | null {
  if (!Number.isFinite(price) || !Number.isFinite(pricePerPixel) || pricePerPixel <= 0) return null
  if (!Number.isInteger(index) || index < 0 || index >= model.dates.length) return null
  let best: { key: string; distance: number } | null = null
  for (const line of model.hitLines) {
    const distance = Math.abs(price - line.value) / pricePerPixel
    if (distance <= tolerancePx && (!best || distance < best.distance)) best = { key: line.key, distance }
  }
  for (const curve of model.hitCurves) {
    const value = curve.values[index]
    if (value == null || !Number.isFinite(value)) continue
    const distance = Math.abs(price - value) / pricePerPixel
    if (distance <= tolerancePx && (!best || distance < best.distance)) best = { key: curve.key, distance }
  }
  return best?.key ?? null
}
