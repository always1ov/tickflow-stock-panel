import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useDroppable,
  useSensor,
  useSensors,
  type DragEndEvent,
  type DragOverEvent,
  type DragStartEvent,
} from '@dnd-kit/core'
import {
  arrayMove,
  SortableContext,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import {
  Eye, EyeOff, ExternalLink, GripVertical, Settings, Bell, Layers3,
  CornerDownRight, CornerLeftUp,
} from 'lucide-react'
import { Link } from 'react-router-dom'
import { api } from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import { usePreferences } from '@/lib/useSharedQueries'
import { SectionIntro } from '@/components/SectionIntro'
import {
  BROWSE_GROUP,
  BROWSE_GROUP_ID,
  browseMembersOf,
  composeNavOrder,
  splitBrowseGroup,
} from '@/lib/navGroups'

interface NavEntry {
  id: string
  label: string
  type: 'builtin' | 'analysis' | 'group'
  visible: boolean
}

// 与 Layout 侧边栏默认顺序保持一致 (nav_order 未保存时的默认展示顺序)
const BUILTIN_PAGES: NavEntry[] = [
  // [R64] 看板已从根路径挪到 /dashboard —— 这里跟着改, 否则隐藏/排序对它失效
  // (那种失效不报错, 只表现为"我明明勾了不显示, 它还在")
  { id: '/dashboard', label: '看板', type: 'builtin', visible: true },
  { id: '/watchlist', label: '自选', type: 'builtin', visible: true },
  { id: '/screener', label: '策略', type: 'builtin', visible: true },
  { id: '/factors', label: '因子', type: 'builtin', visible: true },
  { id: '/backtest', label: '回测', type: 'builtin', visible: true },
  // [R170 → R370] 「AI 操盘手 (仓位中心)」这一条**删掉了**(用户: 「菜单设置
  // 里面的菜单, 要是没有的, 就应该删除」)。
  //
  // 它早就是个空壳: R327 把整套 AI 操盘手换成了转折模拟盘, `/paper-trading`
  // 只剩一条 `<Navigate to="/lots">` 重定向, 而**侧栏 `nav` 里根本没有它** ——
  // 也就是说, 这一行给的是一个"排序与显隐都作用不到任何东西"的开关: 拖它、
  // 勾掉它, 屏幕上不会有任何变化, 而且不报错。同一张表里 `/lots`「模拟盘」
  // 才是真正在用的那一条。
  //
  // **路由那条不动**: router 里写着「书签、菜单设置里存的旧路径不能断」, 老书签
  // 点进去仍然会落到 /lots。删的只是这张配置表里的一行。
  //
  // 已存过的 `nav_order` 里若带着 `/paper-trading` 也没关系 —— 下面合并时走的是
  // `entryMap.get(id)`, 取不到就跳过, 不会把那份配置弄坏。
  { id: '/limit-ladder', label: '连板梯队', type: 'builtin', visible: true },
  { id: '/concept-analysis', label: '概念分析', type: 'builtin', visible: true },
  { id: '/industry-analysis', label: '行业分析', type: 'builtin', visible: true },
  { id: '/stock-analysis', label: '个股分析', type: 'builtin', visible: true },
  // [R67] 分组自己占一行 —— 拖它就是整块挪。默认位置排在「个股分析」之后,
  // 也就是老逻辑(表头挂在第一个成员上)算出来的那个位置, 升级上来位置不变。
  { id: BROWSE_GROUP_ID, label: BROWSE_GROUP.label, type: 'group', visible: true },
  { id: '/minds', label: 'Minds', type: 'builtin', visible: true },   // [R502] 原「消息面」, 原位改名
  { id: '/financials', label: '财务分析', type: 'builtin', visible: true },
  { id: '/monitor', label: '监控中心', type: 'builtin', visible: true },
  { id: '/regime', label: '宏观分析', type: 'builtin', visible: true },   // [R503] 原「市场环境」
  { id: '/abnormal', label: '异动监控', type: 'builtin', visible: true },
  { id: '/lots', label: '模拟盘', type: 'builtin', visible: true },   // [R183] 整页 AI 模拟盘
  { id: '/signals', label: '信号库', type: 'builtin', visible: true },
  { id: '/review', label: '复盘', type: 'builtin', visible: true },
  { id: '/indices', label: '指数', type: 'builtin', visible: true },
  { id: '/data', label: '数据', type: 'builtin', visible: true },
]

// ── Sortable row ──

/** 表格列宽 —— 表头与每一行共用同一串, 分两处写迟早对不齐。 */
const GRID_COLS = 'grid-cols-[2.5rem_1fr_4.5rem_3rem_3rem_3rem_3rem]'

/**
 * [R378] 空组的投放区 id。
 *
 * `SortableContext` 只在**成员行**上建可投放点, 组里一个成员都没有时整段就是
 * 空的 —— 没有任何东西接得住拖过来的行, 于是「全拖出来之后再也拖不回去」。
 * 所以空组时单独摆一个 `useDroppable`。
 */
const MEMBER_DROP_ID = 'dropzone:browse'

/** 空组时的投放区 —— 它存在的唯一理由就是让空组还能接住东西。 */
function EmptyMemberDropZone({ active }: { active: boolean }) {
  const { setNodeRef, isOver } = useDroppable({ id: MEMBER_DROP_ID })
  return (
    <div
      ref={setNodeRef}
      className={`border-b border-border/70 py-4 pl-10 pr-4 text-xs transition-colors ${
        isOver
          ? 'bg-accent/10 text-accent'
          : active
            ? 'bg-elevated/25 text-secondary'
            : 'bg-elevated/25 text-muted'
      }`}
    >
      {active
        ? `松手放到这里, 就收进「${BROWSE_GROUP.label}」`
        : `组里现在是空的 —— 把任意一行拖到这里, 或点那一行的「闲置」按钮, 就能收进来。`}
    </div>
  )
}

function SortableItem({ entry, hidden, onToggleHidden, badgeEnabled, onToggleBadge, indent, note, onToggleGroup }: {
  entry: NavEntry
  hidden: boolean
  onToggleHidden: (id: string) => void
  badgeEnabled?: boolean
  onToggleBadge?: (id: string) => void
  /** 组内成员 —— 缩进一格, 表示它跟着分组走 */
  indent?: boolean
  /** 代替路径显示的说明文字(分组行没有自己的页面, 显示 group:browse 没意义) */
  note?: string
  /**
   * [R378] 一键移入/移出「闲置功能」—— 拖拽之外的第二条路。
   *
   * 不是给拖不动的人留的备份, 是**键盘那条路**: dnd-kit 的键盘拖拽在单个列表
   * 里好用, 跨到另一个容器要靠空格+方向键摸索落点, 谁也摸不准。分组行本身不给
   * (它不能钻进自己肚子里), 所以这个 prop 是可选的。
   */
  onToggleGroup?: (id: string) => void
}) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: entry.id })

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.6 : 1,
    zIndex: isDragging ? 10 : undefined,
  }

  return (
    <div
      ref={setNodeRef}
      style={style}
      className={`grid ${GRID_COLS} items-center border-b border-border/70 py-3 pr-4 last:border-b-0 ${
        indent ? 'pl-10 bg-elevated/25' : 'pl-4'
      } ${isDragging ? 'bg-elevated rounded-btn shadow-lg' : ''} ${hidden ? 'opacity-50' : ''}`}
    >
      <div
        {...attributes}
        {...listeners}
        className="no-press cursor-grab active:cursor-grabbing text-muted hover:text-foreground transition-colors"
      >
        <GripVertical className="h-4 w-4" />
      </div>
      <div className="min-w-0 flex items-center gap-2">
        {entry.type === 'group' && <Layers3 className="h-3.5 w-3.5 shrink-0 text-muted" />}
        <span className={`truncate text-sm font-medium ${!hidden ? 'text-foreground' : 'text-muted line-through'}`}>
          {entry.label}
        </span>
        {hidden && (
          <span className="rounded bg-elevated px-1.5 py-0.5 text-micro text-muted shrink-0">已隐藏</span>
        )}
        <span className={`truncate text-xs text-muted ${note ? '' : 'font-mono'}`}>{note ?? entry.id}</span>
      </div>
      <div>
        <span className={`inline-flex items-center rounded-btn px-2 py-0.5 text-xs ${
          entry.type === 'analysis' ? 'bg-accent/10 text-accent' : 'bg-elevated text-muted'
        }`}>
          {entry.type === 'builtin' ? '内置' : entry.type === 'group' ? '分组' : '扩展'}
        </span>
      </div>
      <div className="flex justify-center">
        <button
          onClick={() => onToggleHidden(entry.id)}
          className={`rounded p-1 transition-colors ${
            hidden
              ? 'text-muted hover:text-accent hover:bg-accent/10'
              : 'text-accent hover:bg-accent/10'
          }`}
          title={hidden ? '显示' : '隐藏'}
        >
          {hidden ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
        </button>
      </div>
      {/* [R378] 第 5 列: 移入 / 移出「闲置功能」 */}
      <div className="flex justify-center">
        {onToggleGroup && (
          <button
            onClick={() => onToggleGroup(entry.id)}
            className="rounded p-1 text-muted transition-colors hover:bg-accent/10 hover:text-accent"
            title={indent ? `移出「${BROWSE_GROUP.label}」` : `收进「${BROWSE_GROUP.label}」`}
          >
            {indent
              ? <CornerLeftUp className="h-3.5 w-3.5" />
              : <CornerDownRight className="h-3.5 w-3.5" />}
          </button>
        )}
      </div>
      <div className="flex justify-center">
        {entry.type === 'group' ? null : entry.type === 'builtin' ? (
          <Link
            to={entry.id}
            className="rounded p-1 text-muted hover:text-accent hover:bg-accent/10 transition-colors"
            title="打开页面"
          >
            <ExternalLink className="h-3.5 w-3.5" />
          </Link>
        ) : (
          <Link
            to={`/settings?tab=ext-pages`}
            className="rounded p-1 text-muted hover:text-accent hover:bg-accent/10 transition-colors"
            title="编辑扩展页面"
          >
            <Settings className="h-3.5 w-3.5" />
          </Link>
        )}
      </div>
      {/* 第 6 列: 徽标开关 (仅监控中心) */}
      <div className="flex justify-center">
        {onToggleBadge && (
          <button
            onClick={() => onToggleBadge(entry.id)}
            className={`rounded p-1 transition-colors ${
              badgeEnabled
                ? 'text-accent hover:bg-accent/10'
                : 'text-muted hover:text-accent hover:bg-accent/10'
            }`}
            title={badgeEnabled ? '关闭数字提示' : '开启数字提示'}
          >
            <Bell className="h-3.5 w-3.5" />
          </button>
        )}
      </div>
    </div>
  )
}

// ── Main panel ──

export function SettingsMenuSettingsPanel() {
  const qc = useQueryClient()
  const { data: prefs } = usePreferences()
  const menus = useQuery({ queryKey: QK.analysisMenus, queryFn: api.analysisMenus })

  const builtinPages = useMemo(() => {
    const pages = [...BUILTIN_PAGES]
    if (prefs?.external_page_enabled && prefs.external_page_url) {
      const anchor = pages.findIndex(page => page.id === '/industry-analysis')
      pages.splice(anchor + 1, 0, {
        id: '/external-page',
        label: prefs.external_page_name || '利弗莫尔趋势',
        type: 'builtin',
        visible: true,
      })
    }
    return pages
  }, [prefs?.external_page_enabled, prefs?.external_page_name, prefs?.external_page_url])

  const analysisEntries: NavEntry[] = (menus.data?.items ?? []).map(m => ({
    id: m.id,
    label: m.label,
    type: 'analysis' as const,
    visible: m.visible,
  }))

  const allEntries = useMemo(() => {
    const saved = prefs?.nav_order ?? []
    const entryMap = new Map<string, NavEntry>()
    for (const e of builtinPages) entryMap.set(e.id, e)
    for (const e of analysisEntries) entryMap.set(e.id, e)

    if (saved.length === 0) return [...builtinPages, ...analysisEntries]

    const ordered: NavEntry[] = []
    const seen = new Set<string>()
    for (const id of saved) {
      const entry = entryMap.get(id)
      if (entry) {
        ordered.push(entry)
        seen.add(id)
      }
    }
    for (const e of [...builtinPages, ...analysisEntries]) {
      if (seen.has(e.id)) continue
      // 未保存过排序的新条目: 内置页插回默认位置, 分析菜单追加到末尾
      const defaultIndex = builtinPages.findIndex(p => p.id === e.id)
      let anchor = -1
      if (defaultIndex > 0) {
        for (let i = defaultIndex - 1; i >= 0 && anchor < 0; i -= 1) {
          anchor = ordered.findIndex(o => o.id === builtinPages[i].id)
        }
      }
      if (anchor >= 0) ordered.splice(anchor + 1, 0, e)
      else if (defaultIndex >= 0) ordered.unshift(e)
      else ordered.push(e)
    }
    return ordered
  }, [prefs?.nav_order, analysisEntries, builtinPages])

  const hiddenSet = useMemo(() => new Set(prefs?.nav_hidden ?? []), [prefs?.nav_hidden])

  // Local order state for optimistic drag updates
  const [localOrder, setLocalOrder] = useState<string[] | null>(null)
  const orderedEntries = useMemo(() => {
    const order = localOrder ?? prefs?.nav_order ?? []
    if (!order.length) return allEntries
    const byId = new Map(allEntries.map(e => [e.id, e]))
    const result: NavEntry[] = []
    const seen = new Set<string>()
    for (const id of order) {
      const e = byId.get(id)
      if (e) { result.push(e); seen.add(id) }
    }
    for (const e of allEntries) {
      if (seen.has(e.id)) continue
      // 与 allEntries 同一语义: 未保存的新内置页插回默认位置而非追加到末尾
      const defaultIndex = builtinPages.findIndex(p => p.id === e.id)
      let anchor = -1
      if (defaultIndex > 0) {
        for (let i = defaultIndex - 1; i >= 0 && anchor < 0; i -= 1) {
          anchor = result.findIndex(o => o.id === builtinPages[i].id)
        }
      }
      if (anchor >= 0) result.splice(anchor + 1, 0, e)
      else if (defaultIndex >= 0) result.unshift(e)
      else result.push(e)
    }
    return result
  }, [localOrder, prefs?.nav_order, allEntries, builtinPages])

  // [R67] 「闲置功能」的成员不在顶层排 —— 它们跟着分组行走, 组内单独排序。
  // [R378] 谁是成员改由顺序里那对首尾标记说了算, 不再是写死的名单。
  const effectiveOrder = useMemo(
    () => localOrder ?? prefs?.nav_order ?? [],
    [localOrder, prefs?.nav_order],
  )
  const memberSet = useMemo(() => browseMembersOf(effectiveOrder), [effectiveOrder])
  const { top: topEntries, members: memberEntries } = useMemo(
    () => splitBrowseGroup(orderedEntries, e => e.id, memberSet),
    [orderedEntries, memberSet],
  )

  const saveNavOrder = useMutation({
    mutationFn: (order: string[]) => api.saveNavOrder(order),
    onSuccess: () => {
      setLocalOrder(null)
      qc.invalidateQueries({ queryKey: QK.preferences })
    },
  })

  const saveNavHidden = useMutation({
    mutationFn: (hidden: string[]) => api.saveNavHidden(hidden),
    onSuccess: () => qc.invalidateQueries({ queryKey: QK.preferences }),
  })

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  )

  // ── [R378] 一个拖拽上下文管两串 ────────────────────────────────────────
  //
  // R67 那版是**两个 DndContext**(顶层一个、组内一个), 于是"组内只能换先后、
  // 拖不出去也拖不进来" —— 两个上下文之间没有任何联系, 从一个里拖出来的东西
  // 另一个根本看不见。用户要的「都能拉进拉出」, 前提就是把它们并成一个。
  //
  // 并了之后仍是**两串**(两个 SortableContext), 不是一串扁的 —— 分组行要能
  // 「整块挪」, 就必须让顶层那串里它只占一格, 成员不参与顶层排序。
  const [dragging, setDragging] = useState<string | null>(null)
  const containerOf = (id: string) => (memberSet.has(id) && id !== BROWSE_GROUP_ID ? 'members' : 'top')

  /** 把一次跨容器的搬运落成新的扁平顺序; `overId` 是落点(空组时是投放区的 id)。 */
  const moveAcross = (activeId: string, overId: string, to: 'top' | 'members') => {
    const topIds = topEntries.map(e => e.id).filter(id => id !== activeId)
    const memberIds = memberEntries.map(e => e.id).filter(id => id !== activeId)
    if (to === 'members') {
      const at = memberIds.indexOf(overId)
      memberIds.splice(at < 0 ? memberIds.length : at, 0, activeId)
    } else {
      const at = topIds.indexOf(overId)
      // 落不到具体某行(理论上不该发生)时放回分组行后面, 别塞到列表最前面
      topIds.splice(at < 0 ? Math.max(topIds.indexOf(BROWSE_GROUP_ID) + 1, 0) : at, 0, activeId)
    }
    return composeNavOrder(topIds, memberIds)
  }

  const handleDragStart = (event: DragStartEvent) => setDragging(String(event.active.id))

  /**
   * 跨容器搬运在 `onDragOver` 就落, 不等松手 —— 拖到一半就能看见它已经缩进去了,
   * 松手只是确认。等到 `onDragEnd` 再落, 整个拖拽过程里那一行都还待在原处, 看
   * 不出自己到底会掉进哪一边。
   */
  const handleDragOver = (event: DragOverEvent) => {
    const { active, over } = event
    if (!over) return
    const activeId = String(active.id)
    const overId = String(over.id)
    // 分组行不能钻进自己肚子里
    if (activeId === BROWSE_GROUP_ID) return
    const from = containerOf(activeId)
    const to = overId === MEMBER_DROP_ID ? 'members' : containerOf(overId)
    if (from === to) return
    setLocalOrder(moveAcross(activeId, overId, to))
  }

  /** 松手: 同容器内换先后, 然后无论如何都存一次 —— 跨容器那一步已经在上面落过了。 */
  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event
    setDragging(null)
    if (!over) { setLocalOrder(null); return }

    const activeId = String(active.id)
    const overId = String(over.id)
    let topIds = topEntries.map(e => e.id)
    let memberIds = memberEntries.map(e => e.id)

    if (activeId !== overId && overId !== MEMBER_DROP_ID) {
      const list = containerOf(activeId) === 'members' ? memberIds : topIds
      const oldIdx = list.indexOf(activeId)
      const newIdx = list.indexOf(overId)
      if (oldIdx >= 0 && newIdx >= 0) {
        const moved = arrayMove(list, oldIdx, newIdx)
        if (containerOf(activeId) === 'members') memberIds = moved
        else topIds = moved
      }
    }
    const next = composeNavOrder(topIds, memberIds)
    setLocalOrder(next)
    saveNavOrder.mutate(next)
  }

  const handleDragCancel = () => { setDragging(null); setLocalOrder(null) }

  /** [R378] 一键移入/移出 —— 键盘那条路(跨容器的键盘拖拽摸不准落点)。 */
  const toggleGroup = (id: string) => {
    const inGroup = containerOf(id) === 'members'
    const topIds = topEntries.map(e => e.id).filter(x => x !== id)
    const memberIds = memberEntries.map(e => e.id).filter(x => x !== id)
    if (inGroup) {
      // 移出: 放在分组行整块的紧后面, 原位置附近, 不要甩到列表末尾
      topIds.splice(Math.max(topIds.indexOf(BROWSE_GROUP_ID) + 1, 0), 0, id)
    } else {
      memberIds.push(id)
    }
    const next = composeNavOrder(topIds, memberIds)
    setLocalOrder(next)
    saveNavOrder.mutate(next)
  }

  const toggleHidden = (id: string) => {
    const next = new Set(hiddenSet)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    saveNavHidden.mutate([...next])
  }

  // 监控中心徽标开关 (localStorage)
  const [badgeEnabled, setBadgeEnabled] = useState(() => {
    try { return localStorage.getItem('monitor_badge_enabled') !== '0' } catch { return true }
  })
  const toggleBadge = (id: string) => {
    if (id !== '/monitor') return
    const next = !badgeEnabled
    setBadgeEnabled(next)
    try { localStorage.setItem('monitor_badge_enabled', next ? '1' : '0') } catch { /* ignore */ }
  }

  return (
    <div className="max-w-5xl space-y-6">
      {/* [R379] 这一块的手搓版收进 `SectionIntro` —— 与扩展页面那一处合成一个产地 */}
      <SectionIntro eyebrow="菜单" title="调整左侧菜单顺序">
        拖动左侧手柄调整菜单排列顺序，点击眼睛图标控制菜单在侧边栏中的显示或隐藏。
        「{BROWSE_GROUP.label}」是一个分组，拖它整块一起挪；缩进的那几行是它的成员。
        <strong className="font-medium text-foreground">任何一行都能拖进或拖出这个分组</strong>
        ，也可以点那一行的「闲置」按钮一键收进去 / 放出来。
      </SectionIntro>

      <section className="rounded-card border border-border bg-surface overflow-hidden">
        <div className={`grid ${GRID_COLS} items-center border-b border-border px-4 py-2 text-xs text-muted`}>
          <div />
          <div>菜单</div>
          <div>类型</div>
          <div className="text-center">显示</div>
          <div className="text-center">闲置</div>
          <div className="text-center">设置</div>
          <div className="text-center">数字</div>
        </div>

        {/* [R378] 一个上下文管两串 —— 两个上下文之间拖不过去, 那正是旧版的毛病 */}
        <DndContext
          sensors={sensors}
          collisionDetection={closestCenter}
          onDragStart={handleDragStart}
          onDragOver={handleDragOver}
          onDragEnd={handleDragEnd}
          onDragCancel={handleDragCancel}
        >
          <SortableContext
            items={topEntries.map(e => e.id)}
            strategy={verticalListSortingStrategy}
          >
            {topEntries.map((entry) => (
              <div key={entry.id}>
                <SortableItem
                  entry={entry}
                  hidden={hiddenSet.has(entry.id)}
                  onToggleHidden={toggleHidden}
                  note={entry.id === BROWSE_GROUP_ID ? `${memberEntries.length} 项 · ${BROWSE_GROUP.hint}` : undefined}
                  badgeEnabled={entry.id === '/monitor' ? badgeEnabled : undefined}
                  onToggleBadge={entry.id === '/monitor' ? toggleBadge : undefined}
                  onToggleGroup={entry.id === BROWSE_GROUP_ID ? undefined : toggleGroup}
                />
                {entry.id === BROWSE_GROUP_ID && (
                  <SortableContext
                    items={memberEntries.map(e => e.id)}
                    strategy={verticalListSortingStrategy}
                  >
                    {memberEntries.map(m => (
                      <SortableItem
                        key={m.id}
                        entry={m}
                        indent
                        hidden={hiddenSet.has(m.id)}
                        onToggleHidden={toggleHidden}
                        onToggleGroup={toggleGroup}
                      />
                    ))}
                    {memberEntries.length === 0 && (
                      <EmptyMemberDropZone active={dragging !== null && dragging !== BROWSE_GROUP_ID} />
                    )}
                  </SortableContext>
                )}
              </div>
            ))}
          </SortableContext>
        </DndContext>

        {menus.isLoading && (
          <div className="px-5 py-10 text-center text-sm text-muted">正在加载菜单...</div>
        )}
      </section>
    </div>
  )
}
