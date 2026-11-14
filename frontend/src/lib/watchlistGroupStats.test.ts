// @vitest-environment node
import { describe, expect, it } from 'vitest'
import { defaultLeaderLabel, orderGroupRows, GROUP_LEADER_MAX } from './watchlistGroupStats'

describe('defaultLeaderLabel: 默认代表标签', () => {
  it('第一位是龙头, 后续为辅龙 N', () => {
    expect(defaultLeaderLabel(0)).toBe('龙头')
    expect(defaultLeaderLabel(1)).toBe('辅龙 1')
    expect(defaultLeaderLabel(2)).toBe('辅龙 2')
  })

  it('上限与后端一致 (每组 3 位)', () => {
    expect(GROUP_LEADER_MAX).toBe(3)
  })
})

describe('orderGroupRows: 代表置顶', () => {
  const rows = [
    { symbol: 'A', pct: -0.02 },
    { symbol: 'B', pct: 0.05 },
    { symbol: 'C', pct: 0.01 },
    { symbol: 'D', pct: 0.03 },
  ]

  it('代表按设定顺序排在前面, 其余保持原顺序', () => {
    const ordered = orderGroupRows(rows, [{ symbol: 'C' }, { symbol: 'A' }])
    expect(ordered.map(r => r.symbol)).toEqual(['C', 'A', 'B', 'D'])
  })

  it('未设置代表时原样返回', () => {
    expect(orderGroupRows(rows, [])).toBe(rows)
    expect(orderGroupRows(rows, undefined)).toBe(rows)
  })

  it('已不在组内的代表被忽略, 不产生空位', () => {
    const ordered = orderGroupRows(rows, [{ symbol: 'MISSING' }, { symbol: 'D' }])
    expect(ordered.map(r => r.symbol)).toEqual(['D', 'A', 'B', 'C'])
  })
})
