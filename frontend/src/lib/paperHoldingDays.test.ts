import { describe, expect, it } from 'vitest'
import { paperHoldingDays } from './paperHoldingDays'

const CAL = ['2026-09-22', '2026-09-23', '2026-09-24', '2026-09-25', '2026-09-28']

describe('[R562] 虚拟账户持有天数', () => {
  it('成交当天算第 1 个交易日, 按净值日历数, 不数周末', () => {
    const fills = [{ symbol: 'A', date: '2026-09-24', side: 'buy', qty: 100 }]
    expect(paperHoldingDays(fills, CAL).get('A')).toBe(3)   // 24 / 25 / 28
  })

  it('分批加仓不重置起点, 部分减仓也不重置', () => {
    const fills = [
      { symbol: 'A', date: '2026-09-22', side: 'buy', qty: 200 },
      { symbol: 'A', date: '2026-09-24', side: 'buy', qty: 100 },
      { symbol: 'A', date: '2026-09-25', side: 'sell', qty: 100 },
    ]
    expect(paperHoldingDays(fills, CAL).get('A')).toBe(5)
  })

  it('清仓之后重新买, 从新买那天起算', () => {
    const fills = [
      { symbol: 'A', date: '2026-09-22', side: 'buy', qty: 100 },
      { symbol: 'A', date: '2026-09-23', side: 'sell', qty: 100 },
      { symbol: 'A', date: '2026-09-25', side: 'buy', qty: 100 },
    ]
    expect(paperHoldingDays(fills, CAL).get('A')).toBe(2)
  })

  it('清仓了就不在结果里; 除权记录不算买卖', () => {
    const fills = [
      { symbol: 'A', date: '2026-09-22', side: 'buy', qty: 100 },
      { symbol: 'A', date: '2026-09-23', side: 'corp_action', kind: 'corp_action' },
      { symbol: 'A', date: '2026-09-24', side: 'sell', qty: 100 },
    ]
    expect(paperHoldingDays(fills, CAL).has('A')).toBe(false)
  })

  it('买进那天不在净值日历里(还没结算定版)就缺数, 不拿自然日冒充交易日', () => {
    const fills = [{ symbol: 'A', date: '2026-09-29', side: 'buy', qty: 100 }]
    expect(paperHoldingDays(fills, CAL).has('A')).toBe(false)
  })
})
