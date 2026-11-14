import { describe, expect, it } from 'vitest'
import {
  fitLevelsMainHeight, levelsChartTotalHeight, TREND_LANES_RESERVE, trendPaneHeight, trendPlotHeight, trendSubPaneHeight,
} from './chart-layout'

describe('[R623] 关键价位一屏装下的反算', () => {
  it('[R626] 量化MACD 是主图的 28%(限 108~136)', () => {
    expect(trendSubPaneHeight(160)).toBe(108)
    // 1600×1000 实测: 主图 height≈419 → MACD 109
    expect(trendSubPaneHeight(408)).toBe(108)
    // 高屏封顶 136, 不让副图跟着主图一起长
    expect(trendSubPaneHeight(720)).toBe(136)
    expect(trendSubPaneHeight(500)).toBe(132)
  })

  it('[R627] 趋势量化 = 字道 135 + 走势 48~64, 走势区不再被压扁', () => {
    expect(TREND_LANES_RESERVE).toBe(135)
    expect(trendPlotHeight(160)).toBe(48)
    // 主图 408 → 走势 57, 比 R626 的 31px 厚了近一倍
    expect(trendPlotHeight(408)).toBe(57)
    expect(trendPlotHeight(500)).toBe(64)
    expect(trendPlotHeight(720)).toBe(64)
    expect(trendPaneHeight(408)).toBe(135 + 57)
    expect(levelsChartTotalHeight(408)).toBe(408 + 192 + 108)
  })

  it('反算出来的主图高 + 两张副图不超过可用高度, 且再加 1px 就装不下', () => {
    for (const available of [520, 610, 680, 704, 757, 784, 1003, 1233, 1600]) {
      const main = fitLevelsMainHeight(available)
      expect(levelsChartTotalHeight(main)).toBeLessThanOrEqual(available)
      expect(levelsChartTotalHeight(main + 1)).toBeGreaterThan(available)
    }
  })

  it('[R627] 1000 / 1080 高的屏: 主图 404 / 463, 仍然大于两张副图之和', () => {
    expect(fitLevelsMainHeight(-131)).toBe(120)
    // 视口 1000: 弹窗 984, 右栏 835, 扣图外 112 → 可用 723 → 主图 419 / 趋势 192 / MACD 109
    expect(fitLevelsMainHeight(704)).toBe(404)
    // 视口 1080: 弹窗 1064, 右栏 915 → 可用 784 → 主图 463 / 趋势 199 / MACD 122
    expect(fitLevelsMainHeight(784)).toBe(463)
    const main = fitLevelsMainHeight(704)
    expect(main).toBeGreaterThan(trendPaneHeight(main) + trendSubPaneHeight(main))
    expect(main / levelsChartTotalHeight(main)).toBeGreaterThan(0.55)
  })
})
