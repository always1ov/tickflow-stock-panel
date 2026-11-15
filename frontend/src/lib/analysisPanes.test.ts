import { describe, expect, it } from 'vitest'
import { quantPaneReadouts, quantPaneSeries, quantPaneTitle } from './analysisPanes'

/** [R724] 趋势量化整张删除后, 这里只剩量化MACD 这一张分析副图的画法守卫。 */
const DATES = ['2026-11-03', '2026-11-04', '2026-11-05']
const quantData = {
  symbol: '603083.SH',
  dates: DATES,
  diff: [-1.2, -0.8, 0.4],
  dea: [-1.0, -0.9, -0.6],
  yellow: [null, -0.2, 0.1],
  gold_icon: [null, null, 0.9],
  dead_icon: [null, null, null],
}

describe('[R648] 分析副图的画法只此一份, pane 下标由调用方给', () => {
  it('量化MACD: 零值线把 0 拉进纵轴, 系列同样落在给定 pane', () => {
    const { series, decor } = quantPaneSeries(DATES, quantData, false, 4)
    expect(series.every(item => item.pane === 4)).toBe(true)
    const zero = series.find(item => item.id === 'qm:scale_zero')!
    expect(zero.data.map(point => (point as any).value)).toEqual([0, 0, 0])
    expect(decor.items.some(item => item.kind === 'icon')).toBe(true)
  })

  it('取数失败 / 没数据时保留一块空副图, 标题写明状态', () => {
    expect(quantPaneSeries(DATES, undefined, false, 6).series)
      .toEqual([expect.objectContaining({ id: 'qm:empty', pane: 6 })])
    expect(quantPaneTitle(true)).toContain('取数失败')
    expect(quantPaneTitle(false)).toBe('量化MACD')
  })

  it('读数行: 有数据列名字, 没数据写等待, 失败写重试', () => {
    expect(quantPaneReadouts(quantData, false, '#fff')[0].text).toBe('DIFF')
    expect(quantPaneReadouts(undefined, false, '#fff')).toEqual([{ text: '等待数据', color: '#fff' }])
    expect(quantPaneReadouts(undefined, true, '#fff')).toEqual([{ text: '取数失败, 稍后刷新重试', color: '#fff' }])
  })
})
