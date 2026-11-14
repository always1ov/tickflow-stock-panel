import { describe, expect, it } from 'vitest'
import { fitLevelsMainHeight, levelsChartTotalHeight, trendSubPaneHeight } from './chart-layout'

describe('[R623] 关键价位一屏装下的反算', () => {
  it('[R626] 副图是主图的 28%(限 108~136), 趋势量化的字道另算', () => {
    expect(trendSubPaneHeight(160)).toBe(108)
    // 1600×1000 实测: 主图 height=408 → 副图 108
    expect(trendSubPaneHeight(408)).toBe(108)
    // 高屏封顶 136, 不让副图跟着主图一起长
    expect(trendSubPaneHeight(720)).toBe(136)
    expect(trendSubPaneHeight(500)).toBe(132)
    expect(levelsChartTotalHeight(408)).toBe(408 + 108 * 2 + 50)
  })

  it('反算出来的主图高 + 两张副图不超过可用高度, 且再加 1px 就装不下', () => {
    for (const available of [520, 610, 680, 704, 757, 784, 1003, 1233, 1600]) {
      const main = fitLevelsMainHeight(available)
      expect(levelsChartTotalHeight(main)).toBeLessThanOrEqual(available)
      expect(levelsChartTotalHeight(main + 1)).toBeGreaterThan(available)
    }
  })

  it('[R626] 主图明显大于两张副图之和: 1000 / 1080 高的屏上主图 429 / 480', () => {
    expect(fitLevelsMainHeight(-131)).toBe(120)
    // 视口 1000: 弹窗 984, 右栏 835, 扣图外 131 → 可用 704 → 主图 429 / 趋势 162 / MACD 112
    expect(fitLevelsMainHeight(704)).toBe(429)
    // 视口 1080: 弹窗 1064, 右栏 915 → 可用 784 → 主图 480 / 趋势 177 / MACD 127
    expect(fitLevelsMainHeight(784)).toBe(480)
    // 主图占图栈(主图 + 两张副图)六成以上, 不再"主次不分"
    expect(fitLevelsMainHeight(704) / levelsChartTotalHeight(fitLevelsMainHeight(704))).toBeGreaterThan(0.6)
  })
})
