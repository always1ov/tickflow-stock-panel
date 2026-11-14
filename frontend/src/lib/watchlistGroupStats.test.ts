// @vitest-environment node
import { describe, expect, it } from 'vitest'
import { orderGroupRows, GROUP_LEADER_MAX } from './watchlistGroupStats'

describe('分组龙头', () => {
  it('上限与后端一致 (每组 3 位)', () => {
    expect(GROUP_LEADER_MAX).toBe(3)
  })
})

describe('orderGroupRows: 龙头置顶', () => {
  const rows = [
    { symbol: 'A', pct: -0.02 },
    { symbol: 'B', pct: 0.05 },
    { symbol: 'C', pct: 0.01 },
    { symbol: 'D', pct: 0.03 },
  ]

  it('龙头按设定顺序排在前面, 其余保持原顺序', () => {
    const ordered = orderGroupRows(rows, ['C', 'A'])
    expect(ordered.map(r => r.symbol)).toEqual(['C', 'A', 'B', 'D'])
  })

  it('未设置龙头时原样返回', () => {
    expect(orderGroupRows(rows, [])).toBe(rows)
    expect(orderGroupRows(rows, undefined)).toBe(rows)
  })

  it('已不在组内的龙头被忽略, 不产生空位', () => {
    const ordered = orderGroupRows(rows, ['MISSING', 'D'])
    expect(ordered.map(r => r.symbol)).toEqual(['D', 'A', 'B', 'C'])
  })
})
