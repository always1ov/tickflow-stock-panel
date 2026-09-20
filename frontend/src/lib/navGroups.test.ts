// @vitest-environment node
import { describe, expect, it } from 'vitest'
import {
  BROWSE_GROUP,
  BROWSE_GROUP_END_ID,
  BROWSE_GROUP_ID,
  browseMembersOf,
  composeNavOrder,
  splitBrowseGroup,
} from './navGroups'

const G = BROWSE_GROUP_ID
const END = BROWSE_GROUP_END_ID

describe('[R378] 闲置功能的成员由顺序说了算', () => {
  it('老配置(没有收尾哨兵)回落到默认名单 —— 升级上来位置不变', () => {
    expect([...browseMembersOf(['/watchlist', G, '/dashboard', '/data'])])
      .toEqual([...BROWSE_GROUP.paths])
    expect([...browseMembersOf([])]).toEqual([...BROWSE_GROUP.paths])
  })

  it('带哨兵时只认首尾之间那一段, 与默认名单无关', () => {
    // 默认名单里的 /dashboard 被拖了出去, 默认名单外的 /signals 被拖了进来
    const order = ['/watchlist', G, '/signals', END, '/dashboard', '/data']
    expect([...browseMembersOf(order)]).toEqual(['/signals'])
  })

  it('空组不回落到默认名单 —— 否则用户永远搬不空这个组', () => {
    expect([...browseMembersOf(['/watchlist', G, END, '/data'])]).toEqual([])
  })

  it('哨兵排在分组行之前(数据坏了)时当没有名单处理, 不返回负区间', () => {
    expect([...browseMembersOf([END, '/signals', G])]).toEqual([...BROWSE_GROUP.paths])
  })
})

describe('[R378] composeNavOrder 存成「首尾夹一段」', () => {
  it('成员紧跟分组行, 哨兵压在成员末尾', () => {
    expect(composeNavOrder(['/watchlist', G, '/data'], ['/signals', '/review']))
      .toEqual(['/watchlist', G, '/signals', '/review', END, '/data'])
  })

  it('存了再读回来, 成员一字不差 —— 两个函数是一对', () => {
    const order = composeNavOrder(['/watchlist', G, '/data'], ['/signals', '/review'])
    expect([...browseMembersOf(order)]).toEqual(['/signals', '/review'])
  })

  it('顶层串里混进了成员或旧哨兵, 一律剔掉, 不会出现两份', () => {
    const order = composeNavOrder(['/watchlist', G, '/signals', END, '/data'], ['/signals'])
    expect(order).toEqual(['/watchlist', G, '/signals', END, '/data'])
    expect(order.filter(id => id === END)).toHaveLength(1)
    expect(order.filter(id => id === '/signals')).toHaveLength(1)
  })

  it('空组也要写哨兵 —— 不写的话下次读回来就被当成老配置, 默认名单原地复活', () => {
    const order = composeNavOrder(['/watchlist', G], [])
    expect(order).toContain(END)
    expect([...browseMembersOf(order)]).toEqual([])
  })

  it('顶层串里没有分组行时兜底, 成员不会丢', () => {
    expect(composeNavOrder(['/watchlist'], ['/signals']))
      .toEqual(['/watchlist', G, '/signals', END])
  })
})

describe('[R378] splitBrowseGroup 按给定名单拆', () => {
  const items = ['/watchlist', G, '/signals', '/data'].map(id => ({ id }))
  const idOf = (x: { id: string }) => x.id

  it('名单里的进组, 其余留顶层', () => {
    const { top, members } = splitBrowseGroup(items, idOf, new Set(['/signals']))
    expect(top.map(idOf)).toEqual(['/watchlist', G, '/data'])
    expect(members.map(idOf)).toEqual(['/signals'])
  })

  it('分组行即使被写进名单也留在顶层 —— 它不能钻进自己肚子里', () => {
    const { top, members } = splitBrowseGroup(items, idOf, new Set([G, '/signals']))
    expect(top.map(idOf)).toContain(G)
    expect(members.map(idOf)).not.toContain(G)
  })

  it('空名单 = 组里空着, 顶层原样', () => {
    const { top, members } = splitBrowseGroup(items, idOf, new Set<string>())
    expect(top.map(idOf)).toEqual(['/watchlist', G, '/signals', '/data'])
    expect(members).toEqual([])
  })
})
