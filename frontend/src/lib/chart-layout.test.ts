import { describe, expect, it } from 'vitest'
import {
  fitAnalysisPaneHeights, fitLevelsMainHeight, levelsChartTotalHeight, quantPaneHeight, trendPaneHeight, trendSubPaneHeight,
} from './chart-layout'

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

describe('[R649] 日K 并入的两张副图高度与关键价位同源', () => {
  it('趋势量化 = 副图 + 字道, 量化MACD = 副图 + 间隔 + 额外', () => {
    const main = 420
    const sub = trendSubPaneHeight(main)
    expect(trendPaneHeight(main)).toBe(sub + 50)
    expect(quantPaneHeight(main)).toBe(sub + 12 + 25)
    // 与整张关键价位图的总高反算一致: 主图 + 两张副图
    expect(main + trendPaneHeight(main) + quantPaneHeight(main)).toBe(levelsChartTotalHeight(main))
  })
})

describe('[R651] 空间不够时只压分析副图, 下限 100', () => {
  it('放得下就原样返回', () => {
    expect(fitAnalysisPaneHeights([168, 130], 400)).toEqual([168, 130])
  })

  it('放不下等比压缩, 且每张不低于 100', () => {
    const fitted = fitAnalysisPaneHeights([168, 130], 200)
    expect(fitted.every(height => height >= 100)).toBe(true)
    expect(fitted.reduce((a, b) => a + b, 0)).toBeLessThan(298)
  })

  it('空间为负(指标副图已占满)也不低于下限, 由整图溢出滚动兜底', () => {
    expect(fitAnalysisPaneHeights([168, 130], -56)).toEqual([100, 100])
  })
})
