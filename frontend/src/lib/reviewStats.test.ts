/**
 * [R747] 钉住统计口径 —— 这些数字要拿去判断「这套策略有没有优势」,
 * 算错一个分位或区间不会报错, 只会安静地给出一个看着专业的错结论。
 *
 * [R749] 复盘只剩「结论 / 权益曲线 / 逐日」, 这里只留还用得着的三样:
 * 分位与 t 区间、Wilson 区间、段 → 笔。
 */
import { describe, it, expect } from 'vitest'
import type { StockReview } from '@/lib/api'
import { ci95, forwardByState, quantile, trades, wilson } from './reviewStats'

type Leg = NonNullable<StockReview['flip_trades']>['legs'][number]

function leg(act: Leg['act'], side: Leg['side'], ret: number, enter: string, exit: string, open = false): Leg {
  return {
    flip_date: enter, enter_date: enter, enter_price: 1, exit_date: exit, exit_price: 1,
    state: 'UT', state_cn: '上涨趋势', side, act, bars: 1, ret, open_ended: open, delayed: 0,
  }
}

describe('分位数与区间', () => {
  it('线性插值分位', () => {
    expect(quantile([1, 2, 3, 4], 0.5)).toBeCloseTo(2.5)
    expect(quantile([1, 2, 3, 4], 0.25)).toBeCloseTo(1.75)
    expect(quantile([], 0.5)).toBeNull()
  })

  it('Wilson 区间在 0/6 与 6/6 时仍落在 [0,1] 内', () => {
    expect(wilson(0, 6)!.lo).toBe(0)
    expect(wilson(6, 6)!.hi).toBeCloseTo(1, 6)
    const half = wilson(3, 6)!
    expect(half.lo).toBeCloseTo(0.188, 3)
    expect(half.hi).toBeCloseTo(0.812, 3)
  })

  it('小样本用 t 临界值, 区间比正态近似更宽', () => {
    const c = ci95([0.1, 0.2, 0.3])!
    expect(c.mean).toBeCloseTo(0.2)
    expect(c.lo).toBeCloseTo(-0.0485, 3)
    expect(c.hi).toBeCloseTo(0.4485, 3)
  })

  it('样本少于 2 个不给区间', () => {
    expect(ci95([0.1])).toBeNull()
  })
})

describe('六态之后的 5 天', () => {
  const row = (date: string, close: number, state: 'UT' | 'DT' | null) => ({
    date, close, change_pct: 0, limit_up: false, limit_down: false,
    broken_limit_up: false, limit_streak: 0, bands: {}, fwd: null,
    trend: state ? { state, state_cn: state === 'UT' ? '上涨趋势' : '下跌趋势', state_en: state, side: '多头' as const, day: 1, flipped: false } : null,
  })

  it('按状态分组, 取之后第 5 个交易日的涨跌', () => {
    // 6 天: 只有第 1 天有完整的未来 5 天
    const rows = [
      row('d6', 100, null), row('d5', 100, null), row('d4', 100, null), row('d3', 100, null),
      row('d2', 110, 'UT'), row('d1', 100, 'UT'),
    ]
    const got = forwardByState(rows, 5)
    expect(got).toHaveLength(1)
    expect(got[0].state).toBe('UT')
    expect(got[0].n).toBe(1)
    expect(got[0].median).toBeCloseTo(0)   // 100 → 100
    expect(got[0].wins).toBe(0)
  })

  it('中位不被一根大阳线拽走', () => {
    const rows = [
      row('d6', 100, null), row('d5', 100, null), row('d4', 100, null), row('d3', 100, null),
      row('d2', 200, 'DT'), row('d1', 100, 'DT'),
    ]
    const got = forwardByState(rows, 5)
    expect(got[0].median).toBeCloseTo(0)
  })

  it('没有六态的日子不算样本', () => {
    const rows = ['d6', 'd5', 'd4', 'd3', 'd2', 'd1'].map(d => row(d, 100, null))
    expect(forwardByState(rows, 5)).toHaveLength(0)
  })
})

describe('段 → 笔: 连续多头段算一次持仓', () => {
  it('买入 + 持有 合成一笔, 空头段不进出笔的收益', () => {
    const got = trades([
      leg('买入', '多头', 0.1, 'd1', 'd2'),
      leg('持有', '多头', 0.1, 'd2', 'd3'),
      leg('卖出', '空头', -0.05, 'd3', 'd4'),
      leg('买入', '多头', 0.2, 'd4', 'd5'),
    ])
    expect(got).toHaveLength(2)
    expect(got[0].ret).toBeCloseTo(0.21)
    expect(got[0].bars).toBe(2)
    expect(got[1].ret).toBeCloseTo(0.2)
    expect(got[1].open).toBe(false)
  })

  it('最后一笔没卖完要标出来', () => {
    const got = trades([leg('买入', '多头', 0.05, 'd1', 'd2', true)])
    expect(got[0].open).toBe(true)
  })
})
