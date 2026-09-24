import { describe, expect, it } from 'vitest'
import { DOGE_IMAGE, DOGE_SIZE, zhuangXianIndexes, zhuangXianSeries } from './zhuangXianSeries'

describe('[R485] 庄现狗头', () => {
  it('按日期对到图上的 x 轴: 只标出庄现那几天, 后端没有的日子不画', () => {
    const dates = ['2026-01-01', '2026-01-02', '2026-01-03', '2026-01-04']
    const q = { dates: ['2026-01-02', '2026-01-03', '2026-01-04'], zhuang: [1, null, 1] }
    expect(zhuangXianIndexes(dates, q)).toEqual([1, 3])
  })

  it('旧缓存里没有这个字段时一个都不画, 不报错', () => {
    expect(zhuangXianIndexes(['2026-01-01'], { dates: ['2026-01-01'] })).toEqual([])
    expect(zhuangXianIndexes(['2026-01-01'], undefined)).toEqual([])
  })

  it('狗头贴着副图底边、水平居中于那一天 —— 位置不看量化MACD 的任何数值', () => {
    const s = zhuangXianSeries([5], { xAxisIndex: 1, yAxisIndex: 1 }) as {
      renderItem: (p: unknown, a: unknown) => { style: Record<string, unknown> }
      data: number[][]
    }
    expect(s.data).toEqual([[5]])
    const el = s.renderItem(
      { coordSys: { y: 100, height: 80 } },
      { value: () => 5, coord: () => [50, 999] },
    )
    expect(el.style.image).toBe(DOGE_IMAGE)
    expect(el.style.x).toBe(50 - DOGE_SIZE / 2)
    expect(el.style.y).toBe(100 + 80 - DOGE_SIZE - 2)
  })
})
