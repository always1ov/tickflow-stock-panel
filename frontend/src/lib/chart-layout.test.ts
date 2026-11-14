import { describe, expect, it } from 'vitest'
import { fitLevelsMainHeight, levelsChartTotalHeight, trendSubPaneHeight } from './chart-layout'

describe('[R623] 关键价位一屏装下的反算', () => {
  it('[R624] 副图是主图的 40%(限 140~200), 趋势量化的字道另算', () => {
    expect(trendSubPaneHeight(160)).toBe(140)
    // 1600×1000 实测: 主图 height=408 → 副图 152
    expect(trendSubPaneHeight(408)).toBe(152)
    expect(trendSubPaneHeight(720)).toBe(200)
    expect(levelsChartTotalHeight(408)).toBe(408 + 152 * 2 + 50)
  })

  it('反算出来的主图高 + 两张副图不超过可用高度, 且再加 1px 就装不下', () => {
    for (const available of [520, 610, 680, 704, 757, 784, 1003, 1233, 1600]) {
      const main = fitLevelsMainHeight(available)
      expect(levelsChartTotalHeight(main)).toBeLessThanOrEqual(available)
      expect(levelsChartTotalHeight(main + 1)).toBeGreaterThan(available)
    }
  })

  it('[R624] 主图面积过半: 1000 / 1080 高的屏上主图 374 / 420', () => {
    expect(fitLevelsMainHeight(-131)).toBe(120)
    // 视口 1000: 弹窗 984, 右栏 835, 扣图外 131 → 374(54% 面积, 趋势 190)
    expect(fitLevelsMainHeight(704)).toBe(374)
    // 视口 1080: 弹窗 1064, 右栏 915 → 主图 420, 趋势 207
    expect(fitLevelsMainHeight(784)).toBe(420)
    // 1000 高的屏主图占比过半, 不再"主次不分"
    expect(fitLevelsMainHeight(704) / 704).toBeGreaterThan(0.5)
  })
})
