// 日 K 与单日分时使用同一套垂直尺寸；额外日 K 指标向下扩展。
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
 * [R624] 趋势量化 / 量化MACD 两张副图的高度 —— 48% 的比例会让「主次不分」, 回到 R422 用户
 * 认可的「副图 = 主图 40%」, 下限 160→140: 1000 高的屏上, 160+50 字道让趋势图只比主图矮
 * 一点(281 vs 209), 主图不像主图; 140 时主图 374、趋势 190、MACD 140。
 * 判据只此一处: 画图的 `AnalysisKChart` 与「弹窗要给多高才装得下」的反算 `fitLevelsMainHeight` 都从这里取。
 */
export const TREND_LANES_EXTRA = 50
const TREND_SUB_PANE_RATIO = 0.4
const TREND_SUB_PANE_MIN = 140
const TREND_SUB_PANE_MAX = 200

export function trendSubPaneHeight(mainHeight: number): number {
  const mainPaneH = Math.max(120, mainHeight - CHART_LAYOUT.timeAxis)
  return Math.round(Math.min(TREND_SUB_PANE_MAX, Math.max(TREND_SUB_PANE_MIN, mainPaneH * TREND_SUB_PANE_RATIO)))
}

/** `height` = 主图高时, 关键价位那张图连两张副图在内的总高(不含卡片里的按钮/图例)。 */
export function levelsChartTotalHeight(mainHeight: number): number {
  return mainHeight + 2 * trendSubPaneHeight(mainHeight) + TREND_LANES_EXTRA
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
