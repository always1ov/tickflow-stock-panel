import type { AnnotationData } from '@/components/charts/ChartAnnotations'
import {
  buildAnalysisChartModel, collectPriceLines, type LevelType,
} from '@/components/stock-analysis/analysis-chart-model'
import type { KlineRow, LevelSeries, PriceLevel } from '@/lib/api'
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
