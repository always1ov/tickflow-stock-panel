import type { AnnotationData } from '@/components/charts/ChartAnnotations'
import {
  buildAnalysisChartModel, collectPriceLines, type LevelType,
} from '@/components/stock-analysis/analysis-chart-model'
import { nextBusinessDates, normalizeDate } from '@/components/stock-analysis/AnalysisKChart'
import type { ChartRange } from '@/lib/chart-types'
import type { Fib2Overlay, KlineRow, LevelSeries, PriceLevel } from '@/lib/api'
import type { PlotSeries } from '@/lib/lightweight-model'

/**
 * [R653] 关键价位那张图的主图叠加物 —— 价位横线与通道曲线。
 *
 * 日K 与关键价位**同一套画法同一个产地**：价位横线走 `collectPriceLines`，通道曲线走
 * `buildAnalysisChartModel` 里的 `curve:*` 序列。这里只做「形状转换」：
 *   · 横线转成日K 标注层认识的 `priceLines`（右侧端点带名字，走价格轴不另开标签带）；
 *   · 曲线原样透传给日K 的画布 —— 主图一条一条线，副图与蜡烛都不受影响。
 */

export type LevelLine = NonNullable<AnnotationData['priceLines']>[number]

/** 价位横线：与关键价位同一份收集逻辑，只补上日K 标注层需要的透明度与避让优先级。 */
export function levelPriceLines(
  levels: Record<LevelType, PriceLevel[]> | undefined,
  active: Iterable<LevelType>,
  pivotRank: 1 | 2 | 3,
  colors?: Record<string, string>,
  roleColor?: (role: string) => string,
): LevelLine[] {
  return collectPriceLines(levels, new Set(active), pivotRank, colors, roleColor).map(line => ({
    value: line.value,
    label: line.label,
    color: line.color,
    opacity: 0.9,
    labelPriority: 1,
  }))
}

/** 通道/带状曲线（26日布林、Keltner 三档、ATR 上下轨、Ⅱ型均线）：只取主图那几条。 */
export function levelCurveSeries(input: {
  rows: KlineRow[]
  series?: LevelSeries
  seriesDates?: string[]
  active: Iterable<LevelType>
  colors?: Record<string, string>
  roleColor?: (role: string) => string
}): PlotSeries[] {
  if (!input.series) return []
  const model = buildAnalysisChartModel({
    rows: input.rows,
    series: input.series,
    seriesDates: input.seriesDates,
    activeTypes: input.active,
    colors: input.colors,
    roleColor: input.roleColor,
  })
  return model.series.filter(item => item.id.startsWith('curve:'))
}

/** 现价贴签：与关键价位那张图一样一条淡线 + 右端「现价 x.xx」，用来量还差多少到位。 */
export function levelLastPriceLine(close: number | null | undefined, color: string): LevelLine[] {
  if (close == null || !Number.isFinite(close)) return []
  return [{ value: close, label: `现价 ${close.toFixed(2)}`, color, opacity: 0.45, labelPriority: 4 }]
}

export interface LevelFib2Overlay {
  priceLines: LevelLine[]
  ranges: ChartRange[]
  labels: NonNullable<AnnotationData['labels']>
  verticals: NonNullable<AnnotationData['verticals']>
  /** 位移均线露到最后一根之外的三个值 + 它们的空槽日期 */
  future: { dates: string[]; labels: string[]; values: number[] } | null
}

/**
 * [R654] 斐波那契Ⅱ型在主图上的那块画法：单边上攻段底色、回踩密集带上下沿、
 * 首次回踩等标记、「未来」分隔线与末尾三个空槽。与关键价位同一套判据与文案。
 */
export function levelFib2Overlay(input: {
  active: Iterable<LevelType>
  fib2?: Fib2Overlay | null
  fib2Zone?: { low: number; high: number; strength: number } | null
  rows: KlineRow[]
  lastClose?: number | null
  theme: string
  fibColor: string
  textColor: string
}): LevelFib2Overlay {
  const result: LevelFib2Overlay = { priceLines: [], ranges: [], labels: [], verticals: [], future: null }
  if (!new Set(input.active).has('fib2') || !input.fib2) return result
  const { fib2, rows } = input
  const dates = rows.map(row => normalizeDate(row.date))
  const dateIndex = new Map(dates.map((date, index) => [date, index]))

  const futureVals = fib2.dma3_future ?? []
  if (futureVals.length && dates.length) {
    const nextDates = nextBusinessDates(dates.at(-1)!, futureVals.length)
    if (nextDates.length === futureVals.length) {
      result.future = {
        dates: nextDates,
        labels: futureVals.map((_, index) => `未来${index + 1}`),
        values: futureVals,
      }
    }
  }

  const thrust = fib2.thrust
  const thrustStart = thrust ? normalizeDate(thrust.start) : ''
  const thrustEnd = thrust ? normalizeDate(thrust.end) : ''
  if (thrust && dateIndex.has(thrustStart) && dateIndex.has(thrustEnd)) {
    result.ranges.push({
      start: thrustStart,
      end: thrustEnd,
      label: `单边上攻 ${thrust.days} 天`,
      color: input.theme === 'dark' ? 'rgba(210,70,59,0.20)' : 'rgba(210,70,59,0.13)',
    })
  }

  const zone = input.fib2Zone
  if (zone && zone.high > 0) {
    const thin = Math.max(0, (input.lastClose ?? zone.high) * 0.003 - (zone.high - zone.low)) / 2
    result.priceLines.push({
      value: Math.max(0, zone.low - thin),
      label: `回踩密集带下沿 ${zone.low.toFixed(2)}`,
      color: input.fibColor,
      opacity: 0.9,
      labelPriority: 2,
    })
    result.priceLines.push({
      value: zone.high + thin,
      label: `回踩密集带上沿 ${zone.high.toFixed(2)} · ${zone.strength} 条挤在一起`,
      color: input.fibColor,
      opacity: 0.9,
      labelPriority: 2,
    })
  }

  for (const marker of fib2.markers ?? []) {
    const date = normalizeDate(marker.date)
    const index = date ? dateIndex.get(date) : undefined
    if (index == null) continue
    result.labels.push({ time: rows[index].date, value: rows[index].high, text: marker.label, color: input.fibColor })
  }

  if (result.future) result.verticals.push({ time: result.future.dates[0], label: '未来', color: input.textColor })
  return result
}

/** 把「未来」那三个位移均线值接到曲线上（其余曲线原样返回）。 */
export function withFib2Future(curves: PlotSeries[], future: LevelFib2Overlay['future']): PlotSeries[] {
  if (!future) return curves
  return curves.map(item => item.id === 'curve:fib2_dma3'
    ? { ...item, data: [...item.data, ...future.values.map((value, index) => ({ time: future.dates[index], value }))] }
    : item)
}
