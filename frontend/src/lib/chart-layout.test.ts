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
    // [R633] 两张副图之间再留 SUB_PANE_GAP(12px); [R635] 量化MACD 另加 MACD_PANE_EXTRA(25px)
    expect(levelsChartTotalHeight(408)).toBe(408 + 108 * 2 + 50 + 12 + 25)
  })

  it('反算出来的主图高 + 两张副图不超过可用高度, 且再加 1px 就装不下', () => {
    for (const available of [520, 610, 680, 704, 757, 784, 1003, 1233, 1600]) {
      const main = fitLevelsMainHeight(available)
      expect(levelsChartTotalHeight(main)).toBeLessThanOrEqual(available)
      expect(levelsChartTotalHeight(main + 1)).toBeGreaterThan(available)
    }
  })

  it('[R635] 主图仍明显大于两张副图: 可用 704 / 784 时主图 401 / 457', () => {
    expect(fitLevelsMainHeight(-131)).toBe(120)
    // 可用 704 → 主图 401 / 趋势 108+50 / MACD 108 + 间隔 12 + 额外 25
    expect(fitLevelsMainHeight(704)).toBe(401)
    // 可用 784 → 主图 457 / 趋势 120+50 / MACD 120 + 间隔 12 + 额外 25
    expect(fitLevelsMainHeight(784)).toBe(457)
    // 主图仍占图栈(主图 + 两张副图 + 间隔 + MACD 额外)过半, 不再"主次不分"
    expect(fitLevelsMainHeight(704) / levelsChartTotalHeight(fitLevelsMainHeight(704))).toBeGreaterThan(0.56)
  })
})
