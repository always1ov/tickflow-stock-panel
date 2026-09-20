/**
 * [fork 增强] R67 「闲置功能」分组 —— 它在菜单里是**一行**, 不是四行。
 *   [R373] 标签从「盘面参考」改成「闲置功能」(用户口径); 内部 id、localStorage
 *   key、变量名都不动, 已存过的菜单顺序不会跟着这条改动漂。
 *
 * R57 引进这个分组时, 表头是"挂"在这一组第一个可见成员上的 —— 分组本身在
 * 「设置 → 菜单」里没有对应的一行。后果有三个:
 *
 *   1. 想挪它, 没得挪 —— 列表里只有成员, 没有分组;
 *   2. 就算去拖成员, 挪的也不一定是它 —— 表头挂在谁身上取决于谁排最前;
 *   3. 成员一旦散落在顺序的两端, 表头和成员会被中间的普通菜单切开。
 *
 * 现在分组有自己的 id, 跟普通菜单项一样参与排序: 拖它就是拖整块。组内成员
 * 不再出现在顶层, 只作为它的子项 —— 各自仍可单独隐藏, 组内也可单独排序。
 *
 * 分组行的默认位置放在「个股分析」之后 —— 也就是老逻辑下它实际待的地方,
 * 这样已经存过顺序的人升级上来看到的位置和以前一样, 只是从此拖得动了。
 *
 * ── [R378] 成员名单从写死改成用户可调 ───────────────────────────────────
 *
 * 用户: 「想要所有菜单都可以随时调整, 比如都能拉进拉出闲置里面」。
 *
 * 在这之前成员是**编译期常量**(一个四条路径的数组), 谁也搬不动: 界面上那几行
 * 看着能拖, 但只能在组内换先后, 拖不出去也拖不进来。
 *
 * 改法是**让顺序本身说明归属**, 而不是另开一个存储键:
 *
 *   nav_order = [ …, 'group:browse', <成员…>, 'group:browse:end', … ]
 *
 * 「谁是成员」= 夹在分组行与收尾哨兵之间的那一段。这么做有三个好处:
 *
 *   · **不动后端。** `nav_order` 后端只当一串字符串存, 不认识里头是什么;
 *     多一个非路径 id 不需要新接口、新字段、新迁移 —— 而分组行 `group:browse`
 *     本来就已经是一个非路径 id, 哨兵跟它同一个体例。
 *   · **顺序与归属不可能打架。** 两者要是分两处存, 迟早出现「名单说它在组里,
 *     顺序把它排在组外」这种谁也不报错的矛盾。挤在一条串里, 这种状态根本表示
 *     不出来。
 *   · **老配置照旧。** 已存过的顺序里没有哨兵 —— 这时回落到下面的默认名单,
 *     升级上来看到的和以前一模一样; 用户头一次拖动时才写进哨兵。
 *
 * 渲染侧不需要认识哨兵: 两处合并菜单时走的都是「按 id 查条目, 查不到就跳过」,
 * 哨兵查不到任何页面, 自然不会渲染成一行。
 */

export const BROWSE_GROUP_ID = 'group:browse'

/**
 * 成员段的收尾哨兵 —— 只出现在 `nav_order` 里, 不对应任何页面, 不渲染。
 *
 * 必须以分组 id 开头之外再带后缀, 别写成两个互不相干的字符串: 日后有人搜
 * `group:browse` 想找出所有相关位置时, 哨兵得一起被搜到。
 */
export const BROWSE_GROUP_END_ID = 'group:browse:end'

export const BROWSE_GROUP = {
  id: BROWSE_GROUP_ID,
  label: '闲置功能',
  hint: '闲置中, 不产出候选也不影响仓位',
  /**
   * **默认**成员 —— 仅在用户还没调整过时生效(存过的顺序里没有收尾哨兵)。
   * 调整之后归属完全由 `nav_order` 说了算, 这张表不再参与。
   *
   * 注: 外部网页(/external-page)不在默认名单里 —— 但 R378 之后它和别的菜单
   * 一样拖得进来, 那条「不入组」不再是限制, 只是默认值。
   */
  paths: ['/dashboard', '/limit-ladder', '/concept-analysis', '/industry-analysis'],
} as const

const DEFAULT_BROWSE_PATHS: ReadonlySet<string> = new Set<string>(BROWSE_GROUP.paths)

/**
 * 从保存的扁平顺序里读出「谁在闲置功能组里」。
 *
 * 顺序里带收尾哨兵 → 归属由顺序说了算(哪怕一个成员都不剩, 那也是用户把它们
 * 全拖出来了, **不能**回落到默认名单 —— 那样用户永远搬不空这个组)。
 * 不带哨兵(老配置 / 从没存过)→ 回落到默认名单。
 */
export function browseMembersOf(savedOrder: readonly string[] = []): ReadonlySet<string> {
  const start = savedOrder.indexOf(BROWSE_GROUP_ID)
  const end = savedOrder.indexOf(BROWSE_GROUP_END_ID)
  if (start < 0 || end < 0 || end < start) return DEFAULT_BROWSE_PATHS
  return new Set(savedOrder.slice(start + 1, end))
}

/** 把排好序的菜单拆成「顶层」和「组内成员」两串, 分组行留在顶层原位。 */
export function splitBrowseGroup<T>(
  items: T[],
  idOf: (item: T) => string,
  members: ReadonlySet<string>,
): { top: T[]; members: T[] } {
  const top: T[] = []
  const inGroup: T[] = []
  for (const item of items) {
    const id = idOf(item)
    // 分组行自己永远在顶层 —— 否则它会被收进自己的肚子里
    if (id !== BROWSE_GROUP_ID && members.has(id)) inGroup.push(item)
    else top.push(item)
  }
  return { top, members: inGroup }
}

/**
 * 把顶层顺序和组内顺序拼回一条扁平的 nav_order。
 *
 * 成员紧跟在分组行后面、收尾哨兵压在成员末尾 —— 存成这样, 即使别处仍按扁平
 * 顺序渲染, 出来的也是连在一起的一块, 不会再被切开; 而那对首尾标记同时就是
 * 「谁是成员」的唯一凭据。
 */
export function composeNavOrder(topIds: string[], memberIds: string[]): string[] {
  const out: string[] = []
  let placed = false
  for (const id of topIds) {
    // 成员与哨兵不该出现在顶层串里
    if (id === BROWSE_GROUP_END_ID || memberIds.includes(id)) continue
    out.push(id)
    if (id === BROWSE_GROUP_ID) {
      out.push(...memberIds, BROWSE_GROUP_END_ID)
      placed = true
    }
  }
  // 分组行不在顶层串里(理论上不该发生)时兜底, 别把成员弄丢
  if (!placed) out.push(BROWSE_GROUP_ID, ...memberIds, BROWSE_GROUP_END_ID)
  return out
}
