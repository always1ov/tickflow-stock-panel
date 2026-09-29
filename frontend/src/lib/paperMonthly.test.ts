import { describe, expect, it } from 'vitest'
import { monthlyReturns } from './paperMonthly'

describe('[R562] 虚拟账户逐月收益', () => {
  it('每个月单独算: 基准是上月最后一天, 第一个月的基准是本金', () => {
    const nav = [
      { date: '2026-08-28', nav: 101_000 },
      { date: '2026-08-31', nav: 102_000 },
      { date: '2026-09-01', nav: 99_960 },
      { date: '2026-09-30', nav: 107_100 },
    ]
    const m = monthlyReturns(nav, 100_000)
    expect(m.map((x) => x.month)).toEqual(['2026-08', '2026-09'])
    expect(m[0].ret).toBeCloseTo(0.02, 6)          // 102000 / 100000 - 1
    expect(m[1].ret).toBeCloseTo(0.05, 6)          // 107100 / 102000 - 1, 不是 / 99960
    expect(m.map((x) => x.days)).toEqual([2, 2])
    expect(m[1].nav).toBe(107_100)
  })

  it('首尾两个月标残月, 中间整月不标', () => {
    const nav = ['2026-07-31', '2026-08-31', '2026-09-30'].map((date) => ({ date, nav: 100_000 }))
    expect(monthlyReturns(nav, 100_000).map((x) => x.partial)).toEqual([true, false, true])
  })

  it('没有净值就没有格子', () => {
    expect(monthlyReturns([], 100_000)).toEqual([])
  })
})
