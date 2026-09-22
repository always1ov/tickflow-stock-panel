/** [R421] 「品红」「玫红」下架: 选色板里没有它们, 已存成这两色的分组显示成相邻的严肃色。 */
import { describe, it, expect } from 'vitest'
import { resolveWatchlistGroupColor, WATCHLIST_GROUP_COLORS } from './watchlist-group-colors'

describe('分组颜色', () => {
  it('选色板里不再有粉 / 洋红 / 玫红', () => {
    const ids = WATCHLIST_GROUP_COLORS.map(c => c.id as string)
    expect(ids).not.toContain('fuchsia')
    expect(ids).not.toContain('rose')
    for (const c of WATCHLIST_GROUP_COLORS) {
      expect(`${c.text} ${c.border} ${c.background} ${c.dot} ${c.ring}`).not.toMatch(/pink|fuchsia|rose/)
    }
  })

  it('已经存成品红 / 玫红的分组: 显示成紫 / 橙, 不是退回默认的天蓝(那会和别的组撞色)', () => {
    expect(resolveWatchlistGroupColor('fuchsia').id).toBe('violet')
    expect(resolveWatchlistGroupColor('rose').id).toBe('orange')
    expect(resolveWatchlistGroupColor('teal').id).toBe('teal')
    expect(resolveWatchlistGroupColor(null).id).toBe('sky')
  })
})
