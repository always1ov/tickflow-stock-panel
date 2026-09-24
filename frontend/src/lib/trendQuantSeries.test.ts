import { describe, expect, it } from 'vitest'
import { TREND_QUANT_COLORS as C } from './theme'
import { alignTrendQuant, TREND_MARKS, trendQuantSeries, type TrendQuantData } from './trendQuantSeries'

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
})
