/**
 * [fork 增强] R67 「盘面参考」分组 —— 它在菜单里是**一行**, 不是四行。
 *
 * R57 引进这个分组时, 表头是"挂"在这一组第一个可见成员上的 —— 分组本身在
 * 「设置 → 菜单」里没有对应的一行。后果有三个:
 *
 *   1. 想挪它, 没得挪 —— 列表里只有成员, 没有分组;
 *   2. 就算去拖成员, 挪的也不一定是它 —— 表头挂在谁身上取决于谁排最前;
 *   3. 成员一旦散落在顺序的两端, 表头和成员会被中间的普通菜单切开。
 *
 * 现在分组有自己的 id, 跟普通菜单项一样参与排序: 拖它就是拖整块。四个成员
 * 不再出现在顶层, 只作为它的子项 —— 各自仍可单独隐藏, 组内也可单独排序。
 *
 * 分组行的默认位置放在「个股分析」之后 —— 也就是老逻辑下它实际待的地方,
 * 这样已经存过顺序的人升级上来看到的位置和以前一样, 只是从此拖得动了。
 */

export const BROWSE_GROUP_ID = 'group:browse'

export const BROWSE_GROUP = {
  id: BROWSE_GROUP_ID,
  label: '盘面参考',
  hint: '展示型: 看盘面用, 不产出候选也不影响仓位',
  /** 组内默认顺序 —— 用户在设置里可以自己调 */
  paths: ['/dashboard', '/limit-ladder', '/concept-analysis', '/industry-analysis'],
} as const

const BROWSE_PATHS: ReadonlySet<string> = new Set<string>(BROWSE_GROUP.paths)

/** 这一页是不是「盘面参考」的成员 —— 是的话它不在顶层出现。 */
export function isBrowsePath(path: string): boolean {
  return BROWSE_PATHS.has(path)
}

/** 把排好序的菜单拆成「顶层」和「组内成员」两串, 分组行留在顶层原位。 */
export function splitBrowseGroup<T>(items: T[], idOf: (item: T) => string): {
  top: T[]
  members: T[]
} {
  const top: T[] = []
  const members: T[] = []
  for (const item of items) {
    if (isBrowsePath(idOf(item))) members.push(item)
    else top.push(item)
  }
  return { top, members }
}

/**
 * 把顶层顺序和组内顺序拼回一条扁平的 nav_order。
 *
 * 成员紧跟在分组行后面 —— 存成这样, 即使别处仍按扁平顺序渲染, 出来的也是
 * 连在一起的一块, 不会再被切开。
 */
export function composeNavOrder(topIds: string[], memberIds: string[]): string[] {
  const out: string[] = []
  let placed = false
  for (const id of topIds) {
    if (isBrowsePath(id)) continue          // 成员不该出现在顶层串里
    out.push(id)
    if (id === BROWSE_GROUP_ID) {
      out.push(...memberIds)
      placed = true
    }
  }
  // 分组行不在顶层串里(理论上不该发生)时兜底, 别把成员弄丢
  if (!placed) out.push(BROWSE_GROUP_ID, ...memberIds)
  return out
}
