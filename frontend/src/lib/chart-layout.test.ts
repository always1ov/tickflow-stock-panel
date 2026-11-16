import { describe, expect, it } from 'vitest'
import {
  analysisSubPaneHeight, fitAnalysisPaneHeights, fitLevelsMainHeight, levelsChartTotalHeight, quantPaneHeight,
} from './chart-layout'

describe('[R623] 关键价位一屏装下的反算', () => {
  it('[R626] 分析副图是主图的 28%(限 108~136)', () => {
    expect(analysisSubPaneHeight(160)).toBe(108)
    // 1600×1000 实测: 主图 height=408 → 副图 108
    expect(analysisSubPaneHeight(408)).toBe(108)
    // 高屏封顶 136, 不让副图跟着主图一起长
    expect(analysisSubPaneHeight(720)).toBe(136)
    expect(analysisSubPaneHeight(500)).toBe(132)
    // [R724] 只剩量化MACD 一张: 主图 + 副图 + SUB_PANE_GAP(12) + MACD_PANE_EXTRA(25)
    expect(levelsChartTotalHeight(408)).toBe(408 + 108 + 12 + 25)
  })

  it('反算出来的主图高 + 副图不超过可用高度, 且再加 1px 就装不下', () => {
    for (const available of [520, 610, 680, 704, 757, 784, 1003, 1233, 1600]) {
      const main = fitLevelsMainHeight(available)
      expect(levelsChartTotalHeight(main)).toBeLessThanOrEqual(available)
      expect(levelsChartTotalHeight(main + 1)).toBeGreaterThan(available)
    }
  })

  it('[R724] 主图仍明显大于副图: 可用 704 / 784 时主图 531 / 611', () => {
    expect(fitLevelsMainHeight(-131)).toBe(120)
    // 可用 704 → 主图 531 / 副图 136 + 间隔 12 + 额外 25
    expect(fitLevelsMainHeight(704)).toBe(531)
    // 可用 784 → 主图 611 / 副图 136 + 间隔 12 + 额外 25
    expect(fitLevelsMainHeight(784)).toBe(611)
    // 主图占图栈(主图 + 副图 + 间隔 + MACD 额外)过半
    expect(fitLevelsMainHeight(704) / levelsChartTotalHeight(fitLevelsMainHeight(704))).toBeGreaterThan(0.56)
  })
})

describe('[R649] 日K 并入的分析副图高度与关键价位同源', () => {
  it('量化MACD = 副图 + 间隔 + 额外', () => {
    const main = 420
    const sub = analysisSubPaneHeight(main)
    expect(quantPaneHeight(main)).toBe(sub + 12 + 25)
    // 与整张关键价位图的总高反算一致: 主图 + 一张副图
    expect(main + quantPaneHeight(main)).toBe(levelsChartTotalHeight(main))
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

  // [R757] 日K 里的量化MACD 已改成 95px(与指标副图同槽), 压缩不能把它反撑回 100
  it('本来就比下限矮的副图不会被撑高', () => {
    expect(fitAnalysisPaneHeights([95], 40)).toEqual([95])
    expect(fitAnalysisPaneHeights([164], 40)).toEqual([100])
  })
})
