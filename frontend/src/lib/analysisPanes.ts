/**
 * [R648] 「量化MACD」分析副图的**唯一产地** —— 日K 与关键价位两个入口
 * 都从这里取系列、读数行与标题, 避免各画一份、口径走散。
 *
 * 数值与颜色怎么算、怎么摆, 全部沿用 R565(还是 ECharts 时)的画法:
 *   量化MACD 的 DIFF 实心柱、DEA 空心点线框、金叉 / 死叉箭头、共振黄柱。
 * 数据仍只有一份(后端 `/quant-macd`), 这里算的只是"怎么画"。
 *
 * [R724] 用户: 「彻底删掉趋势量化这个指标」—— 上面那张「趋势量化」副图连同它的
 * 系列、读数、字道一起删除, 这里只剩量化MACD。
 */
import type { PaneDecorData, DecorItem } from '@/components/charts/SubPaneDecor'
import type { QuantMacdResult } from '@/lib/api'
import type { PlotData, PlotSeries } from '@/lib/lightweight-model'
import { QUANT_MACD_COLORS } from '@/lib/theme'
import {
  alignQuantMacd, diffExposed, QUANT_MACD_HELP, STICK_RATIO,
} from '@/lib/quantMacdSeries'

/** 副图顶上给 pane 标题留的带(px): R565 的标题画在图外, 现在画在图里 */
export const PANE_HEADER_H = 18

/** [R626] 副图的长说明: 图外那条图例删了, 悬停说明挂在开关键排最右的「?」上 */
export const ANALYSIS_PANE_HELP = QUANT_MACD_HELP

export type PaneReadout = { text: string; color?: string }

export function quantPaneTitle(error: boolean) {
  return error ? '量化MACD · 取数失败' : '量化MACD'
}

/** 量化MACD 副图的读数行。 */
export function quantPaneReadouts(
  quantMacd: QuantMacdResult | undefined, error: boolean, textColor: string,
): PaneReadout[] {
  if (error) return [{ text: '取数失败, 稍后刷新重试', color: textColor }]
  if (!quantMacd) return [{ text: '等待数据', color: textColor }]
  return [
    { text: 'DIFF', color: QUANT_MACD_COLORS.red },
    { text: 'DEA', color: QUANT_MACD_COLORS.darkRed },
    { text: '共振', color: QUANT_MACD_COLORS.yellow },
    // [R626] 图外那行图例撤了, 金叉 / 死叉的名称搬进副图 —— 与图上的上下箭头同义
    { text: '↑金叉', color: QUANT_MACD_COLORS.yellow },
    { text: '↓死叉', color: QUANT_MACD_COLORS.green },
  ]
}

/** 量化MACD 副图的系列 + 补画图元。`pane` = 这张副图在图表里的 pane 下标。 */
export function quantPaneSeries(
  dates: string[], quantMacd: QuantMacdResult | undefined, error: boolean, pane = 1,
): { series: PlotSeries[]; decor: PaneDecorData } {
  const empty = () => ({ series: [emptyPaneSeries('qm:empty', pane, dates)], decor: { items: [] } })
  if (error || !quantMacd || dates.length === 0) return empty()
  const data = alignQuantMacd(dates, quantMacd)
  const C = QUANT_MACD_COLORS
  if (!data.diff.some(value => value != null)) return empty()

  // [R616] 顺序 = 原文语句的先后: DIFF → DEA → 金叉 → 死叉 → 共振黄柱(后画的盖在上面)。
  const items: DecorItem[] = []
  // DIFF 实心柱: 被 DEA 空心框盖住, 只画露出来的那一截(`diffExposed`)。
  data.diff.forEach((diff, index) => {
    const segment = diffExposed(diff, data.dea[index])
    if (!segment) return
    items.push({
      kind: 'stick', time: dates[index], from: segment[0], to: segment[1],
      color: diff != null && diff >= 0 ? C.red : C.green, ratio: STICK_RATIO,
    })
  })
  // DEA 空心点线框。
  data.dea.forEach((dea, index) => {
    if (dea == null) return
    items.push({
      kind: 'hollow', time: dates[index], from: 0, to: dea,
      color: dea >= 0 ? C.darkRed : C.green, ratio: STICK_RATIO,
    })
  })
  data.gold_icon.forEach((value, index) => {
    if (value != null) items.push({ kind: 'icon', time: dates[index], value, up: true, color: C.red })
  })
  data.dead_icon.forEach((value, index) => {
    if (value != null) items.push({ kind: 'icon', time: dates[index], value, up: false, color: C.icon2 })
  })
  data.yellow.forEach((value, index) => {
    if (value != null) {
      items.push({ kind: 'stick', time: dates[index], from: 0, to: value, color: C.yellow, ratio: STICK_RATIO })
    }
  })

  // 图里一条线都不画; 这些透明线只负责纵轴(死叉画在 DEA×1.1, 必须进范围)。
  // [R616] 第一条必须是有数据的 series: 补画图元挂在第一条上, 空数据 series 的
  // `priceToCoordinate` 返回 null, 柱子 / 箭头会整片消失。
  return {
    series: [
      { id: 'qm:scale_diff', type: 'Line', pane, color: 'transparent', lineWidth: 1, data: valuePoints(dates, data.diff) },
      { id: 'qm:scale_dea', type: 'Line', pane, color: 'transparent', lineWidth: 1, data: valuePoints(dates, data.dea) },
      { id: 'qm:scale_yellow', type: 'Line', pane, color: 'transparent', lineWidth: 1, data: valuePoints(dates, data.yellow) },
      { id: 'qm:scale_gold', type: 'Line', pane, color: 'transparent', lineWidth: 1, data: valuePoints(dates, data.gold_icon) },
      { id: 'qm:scale_dead', type: 'Line', pane, color: 'transparent', lineWidth: 1, data: valuePoints(dates, data.dead_icon) },
      // [R630] 原文纵轴是 `scale: false` —— 0 永远在轴里, 因为每根柱子都从 0 长出来。
      // lightweight 的 autoscale 只听数据: 一段全是负值(或全是正值)的窗口里 0 会掉出轴外,
      // DEA 空心框 / 共振黄柱的柱根就被上边缘裁掉(和 R415 注释记录的老问题同一个)。
      // 补一条透明的 0 值线, 把 0 拉回范围, 等价于原图的 scale: false。
      { id: 'qm:scale_zero', type: 'Line', pane, color: 'transparent', lineWidth: 1,
        data: dates.map(time => ({ time, value: 0 })) },
    ],
    decor: { items },
  }
}

/** 一块空的副图仍保留 pane 与标题(取数失败 / 加载中时不让副图消失)。 */
export function emptyPaneSeries(id: string, pane: number, dates: string[]): PlotSeries {
  return { id, type: 'Line', pane, color: 'transparent', lineWidth: 1, data: dates.map(time => ({ time })) }
}

export function valuePoints(dates: string[], values: (number | null)[]): PlotData[] {
  return values.map((value, index) =>
    value == null || !Number.isFinite(value) ? { time: dates[index] } : { time: dates[index], value })
}
