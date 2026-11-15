import type { AnnotationData } from '@/components/charts/ChartAnnotations'
import type { LevelType } from '@/components/stock-analysis/analysis-chart-model'
import { nextBusinessDates, normalizeDate } from '@/components/stock-analysis/AnalysisKChart'
import type { ChartRange } from '@/lib/chart-types'
import type { Fib2Overlay, KlineRow } from '@/lib/api'
import type { PlotSeries } from '@/lib/lightweight-model'

/**
 * [R653] 关键价位那张图的主图叠加物 —— 价位横线与通道曲线。
 *
 * [R660] 横线与曲线**不再在这里另拼一套**：日K 直接消费 `buildAnalysisChartModel()` 产出的
 * `annotations.priceLines` 与 `curve:*` 序列 —— 标签带数值、曲线端值、悬停时的高亮/淡化
 * 与「关键价位」逐项同源。这里只剩二型那几块形状转换。
 */

export type LevelLine = NonNullable<AnnotationData['priceLines']>[number]

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
    // [R701] 主图不再显示指标文字, 这两条线只画线、不留标签(横线本身仍是虚线, 与旧图一致)。
    result.priceLines.push({
      value: Math.max(0, zone.low - thin),
      label: '',
      color: input.fibColor,
      opacity: 0.9,
      labelPriority: 2,
    })
    result.priceLines.push({
      value: zone.high + thin,
      label: '',
      color: input.fibColor,
      opacity: 0.9,
      labelPriority: 2,
    })
  }

  for (const marker of fib2.markers ?? []) {
    const date = normalizeDate(marker.date)
    const index = date ? dateIndex.get(date) : undefined
    if (index == null) continue
    // [R725] R565 前这里是一颗向下三角(图表 symbol), 换 lightweight 后退化成一行字;
    // 用户 R701 又要求主图不写指标文字, 所以还原成三角本身, 名字只在悬停读数里给。
    result.labels.push({ time: rows[index].date, value: rows[index].high, text: '▼', color: input.fibColor })
  }

  if (result.future) result.verticals.push({ time: result.future.dates[0], label: '未来', color: input.textColor })
  return result
}

/** 把「未来」那三个位移均线值接到曲线上（历史曲线原样保留，未来段单画一条加粗线）。 */
export function withFib2Future(curves: PlotSeries[], future: LevelFib2Overlay['future']): PlotSeries[] {
  if (!future) return curves
  const source = curves.find(item => item.id === 'curve:fib2_dma3')
  if (!source) return curves
  const points = source.data as { time: string; value?: number }[]
  const last = [...points].reverse().find(point => point.value != null)
  // [R726] 未来段和 R565 前一致: 2.2px 加粗、实色 —— 不再和历史段共用 1px + CC 透明度。
  const color = source.color && source.color.length === 9 ? source.color.slice(0, 7) : source.color
  return [...curves, {
    id: 'curve:fib2_dma3_future', type: 'Line', pane: source.pane, color, lineWidth: 2,
    precision: source.precision,
    data: [
      ...(last?.value != null ? [{ time: last.time, value: last.value }] : []),
      ...future.values.map((value, index) => ({ time: future.dates[index], value })),
    ],
  }]
}
