import { describe, expect, it } from 'vitest'
import { dissolveNavGroup, moveNavPage, navPageIds, resolveNavLayout, visibleNavLayout, type NavLayout } from './navLayout'

const entries = ['/paper', '/watchlist', '/screener', '/analysis/auction'].map(id => ({ id, visible: true }))
const layout: NavLayout = { v: 1, items: [
  { type: 'page', id: '/paper' },
  { type: 'group', id: 'group:research', label: '研究分析', children: [
    { type: 'page', id: '/analysis/auction' }, { type: 'page', id: '/company/offline' },
  ] },
  { type: 'page', id: '/watchlist' }, { type: 'page', id: '/screener' },
] }

describe('nav layout', () => {
  it('normalizes legacy analysis IDs, deduplicates, and pins home', () => {
    const result = resolveNavLayout(null, entries, ['auction', '/watchlist', 'auction', '/paper', '/settings'])
    expect(result.items.map(x => x.id)).toEqual(['/paper', '/analysis/auction', '/watchlist', '/screener'])
  })
  it.each([false, true])('omits fixed settings from saved layouts (nested: %s) while retaining other pages', nested => {
    const settings = { type: 'page' as const, id: '/settings' }
    const saved: NavLayout = { v: 1, items: [
      { type: 'page', id: '/paper' },
      { type: 'group', id: 'group:tools', label: '工具', children: [
        { type: 'page', id: '/offline' }, ...(nested ? [settings] : []),
      ] },
      ...(nested ? [] : [settings]),
      { type: 'page', id: '/watchlist' },
    ] }
    const result = resolveNavLayout(saved, [...entries, { id: '/settings', visible: true }])
    expect(result.items.flatMap(navPageIds)).not.toContain('/settings')
    expect(result.items[1]).toEqual({ type: 'group', id: 'group:tools', label: '工具', children: [{ type: 'page', id: '/offline' }] })
    expect(result.items[2]).toEqual({ type: 'page', id: '/watchlist' })
  })
  it('keeps unavailable references in storage and appends new plugins at root', () => {
    const result = resolveNavLayout(layout, [...entries, { id: '/new', visible: true }])
    expect(result.items.at(-1)?.id).toBe('/new')
    expect(result.items[1]).toEqual(layout.items[1])
    expect(visibleNavLayout(result, entries, []).items[1]).toEqual({
      type: 'group', id: 'group:research', label: '研究分析', children: [{ type: 'page', id: '/analysis/auction' }],
    })
  })
  it('retains unavailable paths while upgrading a legacy flat order', () => {
    expect(resolveNavLayout(null, entries, ['/offline', '/watchlist']).items).toContainEqual({ type: 'page', id: '/offline' })
  })
  it('hides groups whose pages are hidden/unavailable, respects legacy hidden IDs, and keeps home visible', () => {
    expect(visibleNavLayout(layout, entries, ['auction', '/paper']).items.map(x => x.id))
      .toEqual(['/paper', '/watchlist', '/screener'])
  })
  it('keeps a newly created empty category visible in its saved position', () => {
    const empty: NavLayout = { v: 1, items: [{ type: 'page', id: '/paper' },
      { type: 'group', id: 'group:new', label: '新分类', children: [] }, { type: 'page', id: '/watchlist' }] }
    expect(visibleNavLayout(empty, entries, []).items).toEqual(empty.items)
  })
  it('moves pages between groups/root without duplicates, preserving other entries', () => {
    const moved = moveNavPage(layout, '/watchlist', 'group:research')
    expect(moved.items.some(x => x.id === '/watchlist')).toBe(false)
    expect(moved.items[1]).toMatchObject({ children: [
      { type: 'page', id: '/analysis/auction' }, { type: 'page', id: '/company/offline' }, { type: 'page', id: '/watchlist' },
    ] })
    expect(moveNavPage(moved, '/watchlist', null).items.at(-1)?.id).toBe('/watchlist')
    expect(moveNavPage(layout, '/paper', 'group:research')).toEqual(layout)
    expect(moveNavPage(layout, '/watchlist', 'missing')).toEqual(layout)
  })
  it('dissolves a group at its original position without deleting its children', () => {
    expect(dissolveNavGroup(layout, 'group:research').items.map(x => x.id))
      .toEqual(['/paper', '/analysis/auction', '/company/offline', '/watchlist', '/screener'])
  })
  it('ships a grouped default layout for users who never reordered the menu', () => {
    const all = ['/paper', '/watchlist', '/screener', '/dashboard', '/indices',
      '/stock-analysis', '/limit-ladder', '/concept-analysis', '/industry-analysis', '/financials',
      '/regime', '/abnormal', '/signals', '/backtest', '/factors', '/review',
      '/data', '/monitor', '/minds'].map(id => ({ id, visible: true }))
    const result = resolveNavLayout(null, all)
    expect(result.items[0]).toEqual({ type: 'page', id: '/paper' })
    expect(result.items.slice(1, 9).map(x => x.type === 'group' ? x.label : x.id))
      .toEqual(['/watchlist', '/screener', '/stock-analysis', '/regime', '/limit-ladder', '/abnormal', '/review', '/data'])
    expect(result.items.slice(9).map(x => x.type === 'group' ? x.label : x.id))
      .toEqual(['闲置功能'])
  })
})
