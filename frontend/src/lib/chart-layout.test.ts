import { describe, expect, it } from 'vitest'
import { fitLevelsMainHeight, levelsChartTotalHeight, trendSubPaneHeight } from './chart-layout'

describe('[R623] 关键价位一屏装下的反算', () => {
  it('副图守 R565 的 160~220, 趋势量化的字道另算', () => {
    expect(trendSubPaneHeight(160)).toBe(160)
    // 1600×1000 实测: 主图 height=408(主图区 380) → 副图 182
    expect(trendSubPaneHeight(408)).toBe(182)
    expect(trendSubPaneHeight(720)).toBe(220)
    expect(levelsChartTotalHeight(408)).toBe(408 + 182 * 2 + 50)
  })

  it('反算出来的主图高 + 两张副图不超过可用高度, 且再加 1px 就装不下', () => {
    for (const available of [520, 610, 680, 715, 757, 872, 1003, 1233, 1600]) {
      const main = fitLevelsMainHeight(available)
      expect(levelsChartTotalHeight(main)).toBeLessThanOrEqual(available)
      expect(levelsChartTotalHeight(main + 1)).toBeGreaterThan(available)
    }
  })

  it('空间不足时先压主图, 但不低于 120', () => {
    expect(fitLevelsMainHeight(400)).toBe(120)
    expect(fitLevelsMainHeight(-131)).toBe(120)
    // 视口 1000: 右栏 811, 扣图外 131 → 主图 310
    expect(fitLevelsMainHeight(811 - 131)).toBe(310)
    // 视口 1080: 右栏 888 → 主图 374, 与现在的 380 基本持平
    expect(fitLevelsMainHeight(888 - 131)).toBe(374)
  })
})
