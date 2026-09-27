import { describe, expect, it } from 'vitest'
import { TREND_QUANT_COLORS as C } from './theme'
import {
  alignTrendQuant, TREND_MARKS, TREND_QUANT_HELP, TREND_QUANT_LEGEND, trendQuantLegendGraphic, trendQuantSeries,
  type TrendQuantData,
} from './trendQuantSeries'

const marks = (on: (number | null)[]) => Object.fromEntries(
  TREND_MARKS.map(m => [m.key, m.key === 'sheng' ? on : on.map(() => null)]),
) as TrendQuantData['marks']

const Q: TrendQuantData = {
  dates: ['d1', 'd2', 'd3'],
  wave: [1, 2, 1.5], wave_prev: [null, 1, 2], avg: [1.1, 1.6, 1.7],
  stick_up: [1, 1, 0], xichou: [0.6, 1.2, null], xichou_bar: [1, 1, null],
  marks: marks([null, 1, null]),
}

describe('[R486] 趋势量化副图', () => {
  it('按日期对齐; 图上有、后端没有的日子不画', () => {
    const a = alignTrendQuant(['d0', 'd1', 'd2', 'd3'], Q)
    expect(a.avg).toEqual([null, 1.1, 1.6, 1.7])
    expect(a.marks.sheng).toEqual([false, false, true, false])
  })

  it('画的先后照原文: 超买、超卖、平均线、红绿短柱、八种字、吸筹白柱、吸筹线', () => {
    const s = trendQuantSeries(alignTrendQuant(Q.dates, Q), { xAxisIndex: 2, yAxisIndex: 2 })
    expect(s.map(x => x.name)).toEqual([
      '超买', '超卖', '平均线', '波动', ...TREND_MARKS.map(m => m.text), '吸筹柱', '吸筹',
    ])
    expect((s[0] as { data: number[] }).data).toEqual([3.2, 3.2, 3.2])
    expect((s[1] as { data: number[] }).data).toEqual([0.5, 0.5, 0.5])
  })

  it('红绿短柱: 从昨天的波动线画到今天的; 昨天没有值的那一根不画', () => {
    const s = trendQuantSeries(alignTrendQuant(Q.dates, Q), { xAxisIndex: 2, yAxisIndex: 2 })
    expect((s[3] as { data: number[][] }).data).toEqual([[1, 1, 2, 1], [2, 2, 1.5, 0]])
  })

  it('「升」写在当天平均线的高度; 吸筹白柱从 0.53 画起', () => {
    const s = trendQuantSeries(alignTrendQuant(Q.dates, Q), { xAxisIndex: 2, yAxisIndex: 2 })
    const sheng = s.find(x => x.name === '升') as { data: unknown[] }
    expect(sheng.data).toEqual(['-', [1, 1.6], '-'])
    const whites = s.find(x => x.name === '吸筹柱') as { data: number[][] }
    expect(whites.data).toEqual([[0, 0.53, 0.6, 0], [1, 0.53, 1.2, 0]])
  })

  it('颜色照原文: 极底红、逃黄、见底浅红(不是粉)', () => {
    const color = (k: string) => TREND_MARKS.find(m => m.key === k)!.color
    expect(color('jidi')).toBe(C.red)
    expect(color('tao')).toBe(C.yellow)
    expect(color('jiandi')).toBe(C.lightRed)
  })

  it('[R487] 对着通达信截图校准的三种默认色: 平均线紫(替洋红)、吸筹线绿、升顶下白', () => {
    expect(C.avg).toBe('#B84DFF')
    expect(C.xichou).toBe('#00FF00')
    expect(C.text).toBe('#FFFFFF')
  })

  it('[R555] 图例的色与图上那几条线同色 —— 看图例找得到线', () => {
    const s = trendQuantSeries(alignTrendQuant(Q.dates, Q), { xAxisIndex: 2, yAxisIndex: 2 })
    const lineColor = (name: string) =>
      (s.find(x => x.name === name) as { lineStyle: { color: string } }).lineStyle.color
    const legend = Object.fromEntries(TREND_QUANT_LEGEND.map(l => [l.name, l.color]))
    expect(legend['平均线']).toBe(lineColor('平均线'))
    expect(legend['吸筹']).toBe(lineColor('吸筹'))
    expect(legend['超买 / 超卖']).toBe(lineColor('超买'))
    expect(legend['超买 / 超卖']).toBe(lineColor('超卖'))
  })

  it('[R556 → R557] 超买 / 超卖两条黄线在右端注明名字, 不带数值', () => {
    const s = trendQuantSeries(alignTrendQuant(Q.dates, Q), { xAxisIndex: 2, yAxisIndex: 2 })
    const end = (name: string) => (s.find(x => x.name === name) as { endLabel: { show: boolean; formatter: string } }).endLabel
    expect(end('超买')).toMatchObject({ show: true, formatter: '超买' })
    expect(end('超卖')).toMatchObject({ show: true, formatter: '超卖' })
  })

  it('[R555] 图例名字用中性色, 色只落在那段线上; 悬停说明三段齐全', () => {
    const { graphic, width } = trendQuantLegendGraphic(108, 0, '#999')
    const texts = graphic.filter(g => g.type === 'text') as { style: { text: string; fill: string } }[]
    // [R556] 黄线的名字写在线右端, 图例行不再重复
    expect(texts.map(t => t.style.text)).toEqual(['平均线', '吸筹'])
    expect(texts.every(t => t.style.fill === '#999')).toBe(true)
    expect(width).toBeGreaterThan(0)
    expect(TREND_QUANT_HELP.split('\n\n')).toHaveLength(3)
  })
})
