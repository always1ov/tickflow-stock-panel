/** [R421] 「品红」「玫红」下架; [R514] 「靛蓝」「紫色」也下架(「不要紫色」)。
 *  选色板里没有它们, 已存成这几色的分组显示成相邻的严肃色。 */
import { describe, it, expect } from 'vitest'
import { resolveWatchlistGroupColor, WATCHLIST_GROUP_COLORS } from './watchlist-group-colors'

describe('分组颜色', () => {
  it('选色板里不再有粉 / 洋红 / 玫红, 也没有紫 / 靛蓝', () => {
    const ids = WATCHLIST_GROUP_COLORS.map(c => c.id as string)
    for (const gone of ['fuchsia', 'rose', 'violet', 'indigo']) expect(ids).not.toContain(gone)
    for (const c of WATCHLIST_GROUP_COLORS) {
      expect(`${c.text} ${c.border} ${c.background} ${c.dot} ${c.ring}`).not.toMatch(/pink|fuchsia|rose|purple|violet|indigo/)
    }
  })

  it('已经存成退役色的分组: 显示成相邻的非紫色, 不是退回默认的天蓝(那会和别的组撞色)', () => {
    expect(resolveWatchlistGroupColor('fuchsia').id).toBe('blue')
    expect(resolveWatchlistGroupColor('rose').id).toBe('orange')
    expect(resolveWatchlistGroupColor('indigo').id).toBe('blue')
    expect(resolveWatchlistGroupColor('violet').id).toBe('cyan')
    expect(resolveWatchlistGroupColor('teal').id).toBe('teal')
    expect(resolveWatchlistGroupColor(null).id).toBe('sky')
  })
})
