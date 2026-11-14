import { describe, expect, it } from 'vitest'
import {
  PANE_HEADER_H, quantPaneReadouts, quantPaneSeries, quantPaneTitle,
  trendPaneReadouts, trendPaneSeries, trendPaneTitle,
} from './analysisPanes'
import type { TrendQuantData } from './trendQuantSeries'

const DATES = ['2026-11-03', '2026-11-04', '2026-11-05']
const trendData: TrendQuantData = {
  dates: DATES,
  wave: [1.2, 1.5, 1.4],
  wave_prev: [1.0, 1.2, 1.5],
  avg: [1.1, 1.3, 1.45],
  stick_up: [1, 1, 0],
  xichou: [0.8, null, 0.9],
  xichou_bar: [1, null, 1],
  marks: {
    jidi: [1, 0, 0], sheng: [0, 1, 0], ding: [0, 0, 1], xia: [0, 0, 0],
    jiancang: [0, 1, 0], tao: [0, 0, 1], jiandi: [1, 0, 0], juedi: [0, 0, 0],
  },
}
const quantData = {
  symbol: '603083.SH',
  dates: DATES,
  diff: [-1.2, -0.8, 0.4],
  dea: [-1.0, -0.9, -0.6],
  yellow: [null, -0.2, 0.1],
  gold_icon: [null, null, 0.9],
  dead_icon: [null, null, null],
}

describe('[R648] 两张分析副图的画法只此一份, pane 下标由调用方给', () => {
  it('趋势量化: 系列全部落在给定 pane, 图元与字道同源', () => {
    const { series, decor } = trendPaneSeries(DATES, trendData, false, 150, 120, 3)
    expect(series.length).toBeGreaterThan(0)
    expect(series.every(item => item.pane === 3)).toBe(true)
    // 第一条必须是有数据的纵轴系列 —— 补画图元挂在它上面
    expect(series[0].id).toBe('tq:scale')
    expect(series[0].data).toHaveLength(DATES.length)
    expect(decor.headerH).toBe(PANE_HEADER_H)
    // 3 根红绿短柱 + 3 根吸筹白柱 + 信号字 + 2 个右端名字
    expect(decor.items.filter(item => item.kind === 'stick')).toHaveLength(3 + 2)
    expect(decor.items.filter(item => item.kind === 'text').length).toBeGreaterThan(0)
    expect(decor.items.filter(item => item.kind === 'label').map(item => (item as any).text))
      .toEqual(['超买', '超卖'])
  })

  it('量化MACD: 零值线把 0 拉进纵轴, 系列同样落在给定 pane', () => {
    const { series, decor } = quantPaneSeries(DATES, quantData, false, 4)
    expect(series.every(item => item.pane === 4)).toBe(true)
    const zero = series.find(item => item.id === 'qm:scale_zero')!
    expect(zero.data.map(point => (point as any).value)).toEqual([0, 0, 0])
    expect(decor.items.some(item => item.kind === 'icon')).toBe(true)
  })

  it('取数失败 / 没数据时保留一块空副图, 标题写明状态', () => {
    expect(trendPaneSeries(DATES, undefined, true, 150, 120, 5).series)
      .toEqual([expect.objectContaining({ id: 'tq:empty', pane: 5 })])
    expect(quantPaneSeries(DATES, undefined, false, 6).series)
      .toEqual([expect.objectContaining({ id: 'qm:empty', pane: 6 })])
    expect(trendPaneTitle(true)).toContain('取数失败')
    expect(quantPaneTitle(false)).toBe('量化MACD')
  })

  it('读数行: 有数据列名字, 没数据写等待, 失败写重试', () => {
    expect(trendPaneReadouts(250, trendData, false, '#fff')[0].text).toBe('平均线')
    expect(quantPaneReadouts(quantData, false, '#fff')[0].text).toBe('DIFF')
    expect(trendPaneReadouts(120, undefined, false, '#fff')).toEqual([{ text: '等待数据', color: '#fff' }])
    expect(quantPaneReadouts(undefined, true, '#fff')).toEqual([{ text: '取数失败, 稍后刷新重试', color: '#fff' }])
  })
})
