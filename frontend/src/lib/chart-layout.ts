// 日 K 与单日分时使用同一套垂直尺寸；额外日 K 指标向下扩展。
import { LANE_BOTTOM_PAD, LANE_ROW_H, LANE_ROWS, LANE_TOP_PAD } from './trendQuantSeries'

export const CHART_LAYOUT = {
  toolbar: 40,
  readout: 64,
  timeAxis: 28,
  subPaneSlot: 96,
  separator: 1,
} as const

export function dailyChartHeight(baseHeight: number, subPaneCount: number) {
  return baseHeight + subPaneCount * CHART_LAYOUT.subPaneSlot
}

export function plotPaneHeights(plotHeight: number, subPaneCount: number) {
  return [
    Math.max(120, plotHeight - CHART_LAYOUT.timeAxis - subPaneCount * CHART_LAYOUT.subPaneSlot),
    ...Array.from({ length: subPaneCount }, () => CHART_LAYOUT.subPaneSlot - CHART_LAYOUT.separator),
  ]
}

/**
 * 量化MACD 副图的高度。
 * [R626] 用户: 「主图和副图还是显得主次不够分明, 两个副图占用的空间还是觉得多」——
 * 比例收到主图的 28%(限 108~136)。1000 高的屏上 MACD 约 109, 主图约 419。
 * 判据只此一处: 画图的 `AnalysisKChart` 与「弹窗要给多高才装得下」的反算 `fitLevelsMainHeight` 都从这里取。
 */
const TREND_SUB_PANE_RATIO = 0.28
const TREND_SUB_PANE_MIN = 108
const TREND_SUB_PANE_MAX = 136

export function trendSubPaneHeight(mainHeight: number): number {
  const mainPaneH = Math.max(120, mainHeight - CHART_LAYOUT.timeAxis)
  return Math.round(Math.min(TREND_SUB_PANE_MAX, Math.max(TREND_SUB_PANE_MIN, mainPaneH * TREND_SUB_PANE_RATIO)))
}

/** 趋势量化副图顶上给 pane 标题留的带(px) */
export const TREND_PANE_HEADER = 18
/**
 * [R627] 趋势量化里字道占掉的固定高度 —— 标题带 + 上 3 行 + 下 3 行 + 留白。
 * 直接从字道自己的常量推出来, 不另写一个数字: R626 把副图压到 166 时, 这 135 之外
 * 只剩 31px 给 0~4 的走势, 被压成一条缝 —— 用户: 「趋势量化显示的内容被压扁得很厉害」。
 */
export const TREND_LANES_RESERVE = TREND_PANE_HEADER + LANE_TOP_PAD + LANE_ROWS * LANE_ROW_H + 4
  + LANE_BOTTOM_PAD + LANE_ROWS * LANE_ROW_H + 4

/** [R627] 字道之外, 0~4 走势本身的最小 / 最大高度 */
const TREND_PLOT_RATIO = 0.15
const TREND_PLOT_MIN = 48
const TREND_PLOT_MAX = 64

export function trendPlotHeight(mainHeight: number): number {
  const mainPaneH = Math.max(120, mainHeight - CHART_LAYOUT.timeAxis)
  return Math.round(Math.min(TREND_PLOT_MAX, Math.max(TREND_PLOT_MIN, mainPaneH * TREND_PLOT_RATIO)))
}

/**
 * [R627] 趋势量化副图高 = 字道固定 135 + 走势自己的 48~64。
 * 不再用「MACD 高 + 50」推 —— 那个 +50 是 R623 在副图 152 上加的, R626 把底色压到 116 后
 * 它跟着缩到 166, 走势区只剩 31px。现在走势区有下限, 副图该多高由它自己决定。
 */
export function trendPaneHeight(mainHeight: number): number {
  return TREND_LANES_RESERVE + trendPlotHeight(mainHeight)
}

/** `height` = 主图高时, 关键价位那张图连两张副图在内的总高(不含卡片里的按钮/图例)。 */
export function levelsChartTotalHeight(mainHeight: number): number {
  return mainHeight + trendPaneHeight(mainHeight) + trendSubPaneHeight(mainHeight)
}

/**
 * [R623] 在 `available` 高度里求最大的主图高, 让主图 + 两张副图一屏装下。
 * 总高随主图单调不减, 直接二分; 副图有 160 下限, 所以空间不足时先让主图变矮。
 */
export function fitLevelsMainHeight(available: number): number {
  let lo = 120
  let hi = Math.max(120, Math.floor(available))
  if (levelsChartTotalHeight(hi) <= available) return hi
  while (lo < hi) {
    const mid = Math.ceil((lo + hi) / 2)
    if (levelsChartTotalHeight(mid) <= available) lo = mid
    else hi = mid - 1
  }
  return lo
}
