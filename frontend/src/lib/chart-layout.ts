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
 * 认可的「副图 = 主图 40%」, 下限 160→140。
 * [R626] 用户: 「主图和副图还是显得主次不够分明, 两个副图占用的空间还是觉得多」——
 * 40% / 140 在 1000 高的屏上仍是主图 345 vs 两张副图 329, 几乎对半。比例收到 28%、
 * 下限 108、上限 136, 扣除两张副图后主图约 429(占图栈 61%), 副图 162 / 112。
 * 判据只此一处: 画图的 `AnalysisKChart` 与「弹窗要给多高才装得下」的反算 `fitLevelsMainHeight` 都从这里取。
 */
export const TREND_LANES_EXTRA = 50
/**
 * [R633] 趋势量化与量化MACD 两张副图之间的空白间隔(px)。
 * 用户: 「两个副图之间还需要留点空间, 趋势量化不用动, 下面量化macd 往下挪挪」——
 * 间隔记在 MACD pane 顶部(标题与图一起下移), 趋势量化的高度与比例完全不变。
 * [R637] R636 曾把这段间隔换成两行自绘日期, 用户随即改口「所有副图后面都不需要日期行」——
 * 日期只留最底部那条真时间轴, 这里恢复成 12px 空白间隔。
 */
export const SUB_PANE_GAP = 12
/**
 * [R635] 关键价位图日期轴底部空白的裁切量(px)。
 *
 * 轴高是库按字号算出来的(`border 1 + tick 5 + padding 3 + 字号 11 + padding 3 + 底部偏移 4 ≈ 28`),
 * `timeScale.minimumHeight` 只能抬不能压, 把开着的一个小值传进去也不会变矮。
 * 而日期文字垂直居中画在轴顶向下 14px 处, 文字下面白留了 11px。
 * 用户: 「日期那一行往下移动到快接触到边界但不能和边界重叠, 和日期上面那根横线也跟着往下移调整」——
 * 既然是轴自己多留的白, 就把轴底部这 9px 裁掉(留 2px, 不切到文字): 日期行贴到卡片底边 4px,
 * 轴上方那根横线跟着一起下移。代价是悬停时的日期标签框(高 23px)底边少 4px —— 只切到它的下圆角,
 * 文字仍在。
 *
 * 只给关键价位图用; 日K / 分时的成交量轴不动。
 */
export const LEVELS_AXIS_CLIP = 9
/**
 * [R635] 从日期轴空白(9px)与卡片底部留白(16px)腾给量化MACD 的高度(px), 数据区更高、柱更饱满。
 * [R637] R636 曾从这里分走 14px 去画日期行, 现已撤回(见 `SUB_PANE_GAP`), 恢复 25px。
 */
export const MACD_PANE_EXTRA = 25
const TREND_SUB_PANE_RATIO = 0.28
const TREND_SUB_PANE_MIN = 108
const TREND_SUB_PANE_MAX = 136

export function trendSubPaneHeight(mainHeight: number): number {
  const mainPaneH = Math.max(120, mainHeight - CHART_LAYOUT.timeAxis)
  return Math.round(Math.min(TREND_SUB_PANE_MAX, Math.max(TREND_SUB_PANE_MIN, mainPaneH * TREND_SUB_PANE_RATIO)))
}

/**
 * [R649] 日K 并入的两张分析副图高度 —— 与关键价位那张图同一套判据:
 * 趋势量化要多给上下两条字道, 量化MACD 多给副图间隔与 R635 让出的那截。
 */
export function trendPaneHeight(mainHeight: number): number {
  return trendSubPaneHeight(mainHeight) + TREND_LANES_EXTRA
}

export function quantPaneHeight(mainHeight: number): number {
  return trendSubPaneHeight(mainHeight) + SUB_PANE_GAP + MACD_PANE_EXTRA
}

/** `height` = 主图高时, 关键价位那张图连两张副图、副图间隔与 [R635] 额外让给 MACD 的高度在内的总高(不含卡片里的按钮/图例)。 */
export function levelsChartTotalHeight(mainHeight: number): number {
  return mainHeight + 2 * trendSubPaneHeight(mainHeight) + TREND_LANES_EXTRA + SUB_PANE_GAP + MACD_PANE_EXTRA
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
