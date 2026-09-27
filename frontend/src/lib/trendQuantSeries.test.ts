import { describe, expect, it } from 'vitest'
import { TREND_QUANT_COLORS as C } from './theme'
import {
  alignTrendQuant, laneLayout, tqYRange, TQ_LANES_H, TREND_MARKS, TREND_QUANT_HELP, TREND_QUANT_LEGEND,
  trendQuantLegendGraphic, trendQuantSeries,
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
    // [R559] 八种字合成一个「标注」系列画在字道里
    expect(s.map(x => x.name)).toEqual([
      '超买', '超卖', '平均线', '波动', '标注', '吸筹柱', '吸筹',
    ])
    expect((s[0] as { data: number[] }).data).toEqual([3.2, 3.2, 3.2])
    expect((s[1] as { data: number[] }).data).toEqual([0.5, 0.5, 0.5])
  })

  it('红绿短柱: 从昨天的波动线画到今天的; 昨天没有值的那一根不画', () => {
    const s = trendQuantSeries(alignTrendQuant(Q.dates, Q), { xAxisIndex: 2, yAxisIndex: 2 })
    expect((s[3] as { data: number[][] }).data).toEqual([[1, 1, 2, 1], [2, 2, 1.5, 0]])
  })

  it('「升」对准它那一天、写在底下的字道; 吸筹白柱从 0.53 画起', () => {
    const s = trendQuantSeries(alignTrendQuant(Q.dates, Q), { xAxisIndex: 2, yAxisIndex: 2 })
    const a = alignTrendQuant(Q.dates, Q)
    expect(laneLayout(a.marks, [10, 20, 30])).toEqual([
      { m: TREND_MARKS.find(m => m.key === 'sheng'), x: 20, row: 0 },
    ])
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

  it('[R559] 字道: 挨得太近的换到第二行, 离得开的留在第一行; 卖出一侧在上, 买入一侧在下', () => {
    const none = () => [false, false, false, false]
    const marks = Object.fromEntries(TREND_MARKS.map(m => [m.key, none()])) as Record<string, boolean[]>
    marks.ding[0] = true; marks.tao[0] = true       // 同一天: 顶 + 逃
    marks.ding[3] = true                            // 离得远的一个
    marks.jiancang[0] = true                        // 买入一侧
    const out = laneLayout(marks as never, [100, 110, 120, 200])
    const at = (k: string, x: number) => out.find(o => o.m.key === k && o.x === x)!
    expect(at('ding', 100).m.lane).toBe('top')
    expect(at('ding', 100).row).toBe(0)
    expect(at('tao', 100).row).toBe(1)           // 与「顶」同一处, 换行
    expect(at('ding', 200).row).toBe(0)          // 离得开, 回第一行
    expect(at('jiancang', 100).m.lane).toBe('bottom')
    expect(at('jiancang', 100).row).toBe(0)      // 另一条字道, 不和「顶」抢
    // 看不见的那几根不排
    expect(laneLayout(marks as never, [null, null, null, 200]).map(o => o.x)).toEqual([200])
  })

  it('[R559] 纵轴两头留出字道: 0~4 全装下, 副图越矮留得越多(换算成数值)', () => {
    const r175 = tqYRange(175 + 50), r220 = tqYRange(220 + 50)
    expect(r175.min).toBeLessThan(0)
    expect(r175.max).toBeGreaterThan(4)
    expect(r175.max - 4).toBeGreaterThan(r220.max - 4)
    expect(TQ_LANES_H).toBeGreaterThan(0)
  })
})
