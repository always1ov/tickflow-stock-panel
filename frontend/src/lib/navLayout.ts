import { compareByDefaultNav, defaultNavIndex } from './navOrder'
import { BROWSE_GROUP, BROWSE_GROUP_END_ID, BROWSE_GROUP_ID, browseMembersOf } from './navGroups'

export type NavPage = { type: 'page'; id: string }
export type NavGroup = { type: 'group'; id: string; label: string; children: NavPage[] }
export type NavNode = NavPage | NavGroup
export type NavLayout = { v: 1; items: NavNode[] }

// [R598] 本 fork 的根路径重定向到虚拟账户 (R564)，固定置顶项跟着换成 /paper。
// 上游此处固定为 `/`「看板」，照搬会让侧栏多出一个指向同一页的重复入口。
export const HOME_NAV_ID = '/paper'

export const canonicalNavId = (id: string) => id.startsWith('/') ? id : `/analysis/${id}`
export const navPageIds = (node: NavNode) => node.type === 'group' ? node.children.map(x => x.id) : [node.id]

/** 保留离线插件引用，运行时显隐另行过滤；新页面补在顶层。 */
export function resolveNavLayout(
  layout: NavLayout | null | undefined, entries: readonly { id: string }[], legacyOrder: readonly string[] = [],
): NavLayout {
  // 设置由侧栏底部固定入口承载，兼容忽略旧布局里的可移动引用；
  // 本 fork 的固定置顶页是虚拟账户（R598），不是上游的 `/`。
  const seen = new Set<string>([HOME_NAV_ID, '/settings'])
  const items: NavNode[] = []
  if (layout?.v === 1 && Array.isArray(layout.items)) {
    for (const node of layout.items) {
      if (node.type === 'group') {
        const children = node.children.filter(x => {
          if (seen.has(x.id)) return false
          seen.add(x.id)
          return true
        }).map(x => ({ ...x }))
        items.push({ ...node, children })
      } else if (!seen.has(node.id)) {
        seen.add(node.id)
        items.push({ ...node })
      }
    }
  } else {
    // [R598] 旧配置是扁平 nav_order，其中「闲置功能」用一对首尾哨兵编码成员。
    // 这里把它翻成上游的 group 节点，老用户升级后分组仍在原位、成员不变。
    const members = browseMembersOf(legacyOrder)
    const group: NavGroup = { type: 'group', id: BROWSE_GROUP_ID, label: BROWSE_GROUP.label, children: [] }
    let groupPlaced = false
    const placeGroup = () => {
      if (groupPlaced) return
      groupPlaced = true
      items.push(group)
    }
    for (const raw of legacyOrder) {
      if (raw === BROWSE_GROUP_END_ID) continue
      if (raw === BROWSE_GROUP_ID) { placeGroup(); continue }
      const id = canonicalNavId(raw)
      if (members.has(id)) {
        if (seen.has(id)) continue
        seen.add(id)
        group.children.push({ type: 'page', id })
        placeGroup()
        continue
      }
      if (seen.has(id)) continue
      seen.add(id)
      items.push({ type: 'page', id })
    }
    // 默认成员即使不在旧顺序里也要进组，保持与 fork 侧栏一致
    for (const entry of entries) {
      if (seen.has(entry.id) || !members.has(entry.id)) continue
      seen.add(entry.id)
      group.children.push({ type: 'page', id: entry.id })
    }
    if (group.children.length) placeGroup()
  }
  const missing = entries.filter(x => !seen.has(x.id)).sort((a, b) => compareByDefaultNav(a.id, b.id))
  for (const entry of missing) {
    if (seen.has(entry.id)) continue
    const node: NavPage = { type: 'page', id: entry.id }
    // 已分组时只在顶层追加；旧平铺配置沿用默认位置补齐规则。
    const di = defaultNavIndex(entry.id)
    let anchor = -1
    if (!layout && Number.isFinite(di)) {
      for (let i = di - 1; i >= 0 && anchor < 0; i--) {
        anchor = items.findIndex(x => x.type === 'page' && defaultNavIndex(x.id) === i)
      }
    }
    if (anchor >= 0) items.splice(anchor + 1, 0, node)
    else items.push(node)
    seen.add(entry.id)
  }
  return { v: 1, items: [{ type: 'page', id: HOME_NAV_ID }, ...items] }
}

export function visibleNavLayout(
  layout: NavLayout, entries: readonly { id: string; visible?: boolean }[], hidden: readonly string[],
): NavLayout {
  const hiddenIds = new Set(hidden.map(canonicalNavId))
  hiddenIds.delete(HOME_NAV_ID)
  const visibleIds = new Set(entries.filter(x => x.visible !== false && !hiddenIds.has(x.id)).map(x => x.id))
  const items: NavNode[] = []
  for (const node of layout.items) {
    if (node.type === 'page') {
      if (visibleIds.has(node.id)) items.push(node)
    } else {
      const children = node.children.filter(x => visibleIds.has(x.id))
      if (children.length || node.children.length === 0) items.push({ ...node, children })
    }
  }
  return { v: 1, items }
}

export function moveNavPage(layout: NavLayout, id: string, groupId: string | null, beforeId?: string): NavLayout {
  if (id === HOME_NAV_ID || !layout.items.some(x => navPageIds(x).includes(id))) return layout
  if (groupId !== null && !layout.items.some(x => x.type === 'group' && x.id === groupId)) return layout
  const items = layout.items.flatMap<NavNode>(node => node.type === 'group'
    ? [{ ...node, children: node.children.filter(x => x.id !== id) }]
    : node.id === id ? [] : [node])
  const page: NavPage = { type: 'page', id }
  if (groupId === null) {
    const index = beforeId ? items.findIndex(x => x.id === beforeId) : -1
    items.splice(index > 0 ? index : items.length, 0, page)
  } else {
    const group = items.find(x => x.type === 'group' && x.id === groupId) as NavGroup
    const index = beforeId ? group.children.findIndex(x => x.id === beforeId) : -1
    group.children.splice(index >= 0 ? index : group.children.length, 0, page)
  }
  return { v: 1, items }
}

export function dissolveNavGroup(layout: NavLayout, id: string): NavLayout {
  return { v: 1, items: layout.items.flatMap<NavNode>(node =>
    node.type === 'group' && node.id === id ? node.children : [node]) }
}
