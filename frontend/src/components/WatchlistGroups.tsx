import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { useQueryClient } from '@tanstack/react-query'
import { Check, ChevronDown, ChevronUp, FolderCog, FolderInput, Pencil, Plus, Trash2, X, Eraser } from 'lucide-react'
import { Modal } from '@/components/Modal'
import { SELECTED, TYPE, buttonClass } from '@/components/ui'
import { cn } from '@/lib/cn'
import { api } from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import { usePreferences } from '@/lib/useSharedQueries'
import { fmtPct } from '@/lib/format'
import type { WatchlistGroup, WatchlistGroupColor } from '@/lib/api'
import {
  groupPctColor,
  groupPctTitle,
  type GroupPctMap,
} from '@/lib/watchlistGroupStats'
import {
  DEFAULT_WATCHLIST_GROUP_COLOR,
  WATCHLIST_GROUP_COLORS,
  resolveWatchlistGroupColor,
} from '@/lib/watchlist-group-colors'

export type WatchlistGroupFilter = 'all' | 'ungrouped' | string

interface GroupBarProps {
  groups: WatchlistGroup[]
  counts: Record<string, number>
  selected: WatchlistGroupFilter
  total: number
  /** 分组等权平均涨跌幅 (key: 'all' | 'ungrouped' | 分组id); 缺省不显示 */
  pcts?: GroupPctMap
  onSelect: (group: WatchlistGroupFilter) => void
  onCreate: (name: string, color: WatchlistGroupColor) => Promise<void>
  onRename: (groupId: string, name: string, color: WatchlistGroupColor) => Promise<void>
  onDelete: (groupId: string) => Promise<void>
  onClearGroup?: (groupId: string) => Promise<void>
  /** 手动调整分组前后顺序 (持久化到后端) */
  onReorder?: (orderedIds: string[]) => Promise<void>
}

export function WatchlistGroupBar({
  groups,
  counts,
  selected,
  total,
  pcts,
  onSelect,
  onCreate,
  onRename,
  onDelete,
  onClearGroup,
  onReorder,
}: GroupBarProps) {
  const [managerOpen, setManagerOpen] = useState(false)
  const [confirmClear, setConfirmClear] = useState(false)
  const tabs = [
    { id: 'all', name: '全部', count: total, color: null },
    { id: 'ungrouped', name: '未分组', count: counts.ungrouped ?? 0, color: null },
    ...groups.map(group => ({ id: group.id, name: group.name, count: counts[group.id] ?? 0, color: group.color })),
  ]
  // 拖拽排序状态: dragIndex = 拖动中的分组下标, dropIndex = 插入位置 (均相对 groups 数组)
  const [dragIndex, setDragIndex] = useState<number | null>(null)
  const [dropIndex, setDropIndex] = useState<number | null>(null)
  const reorderable = !!onReorder && groups.length > 1
  const tablistRef = useRef<HTMLDivElement>(null)
  // [R508] 分组多时默认只露几行, 其余折起来 —— 32 个小分队原来在手机上占掉半屏
  // (34vh 上限内自己滚), 表格只剩「代码 + 现价」。现在电脑露三行、手机露两行,
  // 折起来的那部分用一个「还有 N 组」按钮展开; 展开与否不记住, 每次进来都是折的。
  const [expanded, setExpanded] = useState(false)
  const [overflowing, setOverflowing] = useState(false)
  useEffect(() => {
    const el = tablistRef.current
    if (!el) return
    const check = () => setOverflowing(el.scrollHeight > el.clientHeight + 1)
    check()
    // 观察的是每一个药丸而不只是容器: 容器高度被 max-h 钉死、宽度不变, 网页字体加载完
    // 药丸变宽从三行溢成四行时, 容器自己不会触发 ResizeObserver —— 实测就漏过这一次
    const ro = new ResizeObserver(check)
    ro.observe(el)
    for (const child of Array.from(el.children)) ro.observe(child)
    return () => ro.disconnect()
  }, [groups.length, expanded])

  const clearDrag = () => { setDragIndex(null); setDropIndex(null) }

  /**
   * 拖到标签栏边缘附近自动滚动, 保证能把分组拖到当前看不见的位置。
   *
   * [R402] **原来这一支是死的**: 它滚的是 `scrollLeft`, 且开头那句
   * `scrollWidth <= clientWidth` 就返回 —— 而这一栏自从改成 `flex-wrap`
   * (见上面那条 fork 增强)之后**永远不横向溢出**, 于是条件恒真, 整个函数
   * 每次都在第一行返回。注释写着"横向滚动", 而这一栏早就不横向滚了。
   * 现在它滚的是纵向 —— 那才是这一栏真正会溢出的方向。
   */
  const autoScroll = (clientY: number) => {
    const el = tablistRef.current
    if (!el || el.scrollHeight <= el.clientHeight) return
    const rect = el.getBoundingClientRect()
    const edge = 32
    if (clientY < rect.top + edge) el.scrollTop -= 16
    else if (clientY > rect.bottom - edge) el.scrollTop += 16
  }

  const handleDrop = () => {
    if (dragIndex == null || dropIndex == null) { clearDrag(); return }
    const ids = groups.map(group => group.id)
    const [moved] = ids.splice(dragIndex, 1)
    if (moved) {
      ids.splice(dropIndex > dragIndex ? dropIndex - 1 : dropIndex, 0, moved)
      if (ids.join(',') !== groups.map(group => group.id).join(',')) {
        void onReorder?.(ids)
      }
    }
    clearDrag()
  }

  return (
    <>
      {/* [fork 增强] 分组多了自动换行, 不再横向滚动: 分组一多时横滚要左右拖才能
          看全, 且被遮住的分组容易被忘掉。右侧操作按钮固定在首行不随行数漂移。 */}
      {/* [R508] 手机上药丸区独占整行(展开按钮 / 管理按钮先排在上一行右侧), 否则右边两个按钮
          把药丸区挤到 230px, 一行只放得下一个药丸; sm 起回到一行两栏 */}
      <div className="flex min-h-10 flex-wrap items-start border-b border-border bg-surface/40 px-5">
        <div
          ref={tablistRef}
          role="tablist"
          aria-label="自选分组"
          onDragOver={dragIndex != null ? e => autoScroll(e.clientY) : undefined}
          /*
            [R402] **加一个高度上限 + 自己滚。**

            用户: 「自选股看不到下面, 滚动下去也不行」。这一栏是 `flex-wrap`,
            分组一多就往下堆, 而它**既没有高度上限, 也不滚** —— 它是
            `flex flex-col h-full` 里的一个 flex 项, `min-height: auto` 让它
            不肯缩到内容高度以下, 于是它有多高就占多高。

            后果分两档, 用户遇到的是第二档:
              分组中等多 → 表格被挤成一条缝(实测 375×780 下只剩 **184px**,
                          而它里面有 6527px 的内容);
              分组再多   → 整栏超出视口, 而外层是 `h-full` 没有页面级滚动,
                          **下面的东西根本够不到, 也没有任何东西能滚**。

            上限取 `34vh`: 手机上约 6 行药丸, 导航占掉三分之一, 表格仍留三分之二
            —— 这一页的主角是表格, 分组是找路的。桌面上一行能排十几个, 34vh
            本来就到不了, 所以不必分档。
            **右侧那个操作按钮不在这一层**(它是兄弟节点), 所以滚的只是药丸,
            按钮仍然钉在首行, 与上面那条 fork 增强的约定一致。
          */
          className={`order-2 flex min-w-0 basis-full flex-wrap items-stretch gap-1 py-0.5 sm:order-1 sm:basis-0 sm:flex-1 ${
            // [R508] 折起时限高三行(每行 = 药丸 28 + 上下 my-0.5 4 + 行间 gap 4 → 3 行 108px), 展开后仍守 34vh 上限自己滚
            expanded ? 'max-h-[34vh] overflow-y-auto' : 'max-h-[6.75rem] overflow-hidden'
          }`}
        >
          {tabs.map((tab, tabIndex) => {
            const active = selected === tab.id
            const color = tab.color ? resolveWatchlistGroupColor(tab.color) : null
            // 前两个为固定标签 (全部/未分组), 其后对应 groups 数组 — 可拖拽排序
            const groupIndex = tabIndex - 2
            const draggable = reorderable && tabIndex >= 2
            const dragging = draggable && dragIndex === groupIndex
            return (
              <button
                key={tab.id}
                type="button"
                role="tab"
                aria-selected={active}
                draggable={draggable}
                onDragStart={draggable ? e => {
                  setDragIndex(groupIndex)
                  e.dataTransfer.effectAllowed = 'move'
                  e.dataTransfer.setData('text/plain', tab.id)
                } : undefined}
                onDragOver={draggable ? e => {
                  e.preventDefault()
                  e.dataTransfer.dropEffect = 'move'
                  autoScroll(e.clientX)
                  const rect = e.currentTarget.getBoundingClientRect()
                  setDropIndex(groupIndex + (e.clientX > rect.left + rect.width / 2 ? 1 : 0))
                } : undefined}
                onDrop={draggable ? e => { e.preventDefault(); handleDrop() } : undefined}
                onDragEnd={draggable ? clearDrag : undefined}
                onClick={() => onSelect(tab.id)}
                title={draggable ? `${tab.name} — 可拖拽调整分组顺序` : undefined}
                // [R452] 与全站按钮同高(32px); 「全部 / 未分组」选中是全站那套反相,
                // 彩色分组选中仍亮它自己的颜色(颜色是分组的身份)
                // [R508] 药丸压矮一档(28px)并一律带边框 —— 原来未选中的没边框、靠留白分隔,
                // 32 个排下来一片散点; 有边框之后一行能多放两个, 而且看得出每个是一个按钮
                className={`relative my-0.5 inline-flex h-7 shrink-0 items-center gap-1.5 rounded-btn border px-2.5 text-xs transition-colors ${
                  draggable ? 'no-press cursor-grab active:cursor-grabbing' : ''
                } ${
                  dragging ? 'opacity-40' : ''
                } ${
                  active
                    ? color
                      ? `${color.text} ${color.border} ${color.background}`
                      : SELECTED
                    : color
                      ? `border-border ${color.text} hover:bg-elevated`
                      : 'border-border text-secondary hover:bg-elevated hover:text-foreground'
                }`}
              >
                {draggable && dragIndex != null && dropIndex === groupIndex && (
                  <span className="absolute -left-0.5 top-1 bottom-1 w-0.5 rounded-full bg-accent" />
                )}
                {draggable && dragIndex != null && dropIndex === groupIndex + 1 && groupIndex === groups.length - 1 && (
                  <span className="absolute -right-0.5 top-1 bottom-1 w-0.5 rounded-full bg-accent" />
                )}
                {color && <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${color.dot}`} />}
                <span>{tab.name}</span>
                <span className={`font-mono text-micro tabular-nums ${active && !color ? 'opacity-70' : 'text-muted'}`}>
                  {tab.count}
                </span>
                {pcts && (() => {
                  const info = pcts[tab.id]
                  if (!info || info.pct == null || info.sampled === 0) return null
                  return (
                    <span
                      className={`font-mono text-micro tabular-nums ${groupPctColor(info.pct)}`}
                      title={groupPctTitle(info)}
                    >
                      {fmtPct(info.pct)}
                    </span>
                  )
                })()}
              </button>
            )
          })}
        </div>
        {(overflowing || expanded) && (
          <button
            type="button"
            onClick={() => setExpanded(v => !v)}
            aria-expanded={expanded}
            className="order-1 ml-auto inline-flex h-10 shrink-0 items-center gap-0.5 whitespace-nowrap text-micro text-muted hover:text-accent sm:order-2 sm:ml-1"
            title={expanded ? '收起分组' : '展开全部分组'}
          >
            {expanded ? '收起' : `全部 ${groups.length} 组`}
            <ChevronDown className={`h-3 w-3 transition-transform duration-expand ease-smooth ${expanded ? 'rotate-180' : ''}`} />
          </button>
        )}
        <button
          type="button"
          onClick={() => setManagerOpen(true)}
          className="order-1 ml-2 inline-flex h-10 w-8 shrink-0 items-center justify-center text-muted hover:text-accent sm:order-2"
          title="管理自选分组"
          aria-label="管理自选分组"
        >
          <FolderCog className="h-4 w-4" />
        </button>
        {/* 清空当前分组 — 仅选中具体分组时显示 */}
        {onClearGroup && selected !== 'all' && selected !== 'ungrouped' && (
          <button
            type="button"
            onClick={() => setConfirmClear(true)}
            className="order-1 inline-flex h-10 w-8 shrink-0 items-center justify-center text-muted hover:text-warning sm:order-2"
            title="清空当前分组"
            aria-label="清空当前分组"
          >
            <Eraser className="h-4 w-4" />
          </button>
        )}
      </div>

      {/* 清空分组确认弹窗 */}
      {confirmClear && selected !== 'all' && selected !== 'ungrouped' && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div
            className="absolute inset-0 bg-black/60 backdrop-blur-sm"
            onClick={() => setConfirmClear(false)}
          />
          <div className="relative w-[90vw] max-w-[380px] rounded-card border border-border bg-base shadow-2xl p-6">
            <h3 className={cn('mb-2', TYPE.section)}>清空分组</h3>
            <p className="text-xs text-secondary mb-5">
              确认清空「{tabs.find(t => t.id === selected)?.name}」分组? 分组内所有股票将转为未分组(不从自选中删除)。
            </p>
            <div className="flex items-center justify-end gap-2">
              <button
                onClick={() => setConfirmClear(false)}
                className={buttonClass()}
              >
                取消
              </button>
              <button
                onClick={() => { setConfirmClear(false); void onClearGroup?.(selected) }}
                className={buttonClass({}, 'border-warning/40 bg-warning/10 font-medium text-warning hover:bg-warning/20')}
              >
                确认清空
              </button>
            </div>
          </div>
        </div>
      )}

      {managerOpen && (
        <GroupManagerDialog
          groups={groups}
          counts={counts}
          onClose={() => setManagerOpen(false)}
          onCreate={onCreate}
          onRename={onRename}
          onDelete={onDelete}
          onReorder={onReorder}
        />
      )}
    </>
  )
}

function GroupColorPicker({
  value,
  onChange,
}: {
  value: WatchlistGroupColor
  onChange: (color: WatchlistGroupColor) => void
}) {
  return (
    <div role="radiogroup" aria-label="分组颜色" className="flex flex-wrap items-center gap-1.5">
      {WATCHLIST_GROUP_COLORS.map(option => {
        const selected = value === option.id
        return (
          <button
            key={option.id}
            type="button"
            role="radio"
            aria-checked={selected}
            aria-label={option.label}
            title={option.label}
            onClick={() => onChange(option.id)}
            className={`inline-flex h-6 w-6 items-center justify-center rounded-full border transition-transform hover:scale-110 ${
              selected
                ? `${option.border} ${option.background} ring-2 ${option.ring}`
                : 'border-transparent hover:bg-elevated'
            }`}
          >
            <span className={`h-3 w-3 rounded-full ${option.dot}`} />
          </button>
        )
      })}
    </div>
  )
}

function GroupManagerDialog({
  groups,
  counts,
  onClose,
  onCreate,
  onRename,
  onDelete,
  onReorder,
}: Omit<GroupBarProps, 'selected' | 'total' | 'onSelect' | 'onClearGroup'> & { onClose: () => void }) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [newName, setNewName] = useState('')
  const [newColor, setNewColor] = useState<WatchlistGroupColor>(DEFAULT_WATCHLIST_GROUP_COLOR)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editingName, setEditingName] = useState('')
  const [editingColor, setEditingColor] = useState<WatchlistGroupColor>(DEFAULT_WATCHLIST_GROUP_COLOR)
  const [deletingId, setDeletingId] = useState<string | null>(null)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState('')

  // 「显示在侧边栏」偏好开关
  const qc = useQueryClient()
  const prefs = usePreferences()
  const groupsInNav = prefs.data?.watchlist_groups_in_nav ?? false
  const [navTogglePending, setNavTogglePending] = useState(false)
  const toggleGroupsInNav = async (enabled: boolean) => {
    setNavTogglePending(true)
    try {
      await api.updateWatchlistGroupsInNav(enabled)
      await qc.invalidateQueries({ queryKey: QK.preferences })
    } finally {
      setNavTogglePending(false)
    }
  }

  const validate = (name: string) => {
    const value = name.trim()
    if (!value) return '请输入分组名称'
    if (value.length > 24) return '分组名称不能超过 24 个字符'
    return ''
  }

  const run = async (action: () => Promise<void>) => {
    setPending(true)
    setError('')
    try {
      await action()
    } catch (err) {
      setError(err instanceof Error ? err.message : '操作失败')
    } finally {
      setPending(false)
    }
  }

  const create = async () => {
    const message = validate(newName)
    if (message) {
      setError(message)
      return
    }
    await run(async () => {
      await onCreate(newName.trim(), newColor)
      setNewName('')
      setNewColor(DEFAULT_WATCHLIST_GROUP_COLOR)
      inputRef.current?.focus()
    })
  }

  const rename = async (groupId: string) => {
    const message = validate(editingName)
    if (message) {
      setError(message)
      return
    }
    await run(async () => {
      await onRename(groupId, editingName.trim(), editingColor)
      setEditingId(null)
    })
  }

  // 上移/下移: 与相邻分组交换位置, 新顺序由后端持久化 (json 数组顺序即定义顺序)
  const move = async (groupId: string, dir: -1 | 1) => {
    if (!onReorder) return
    const ids = groups.map(group => group.id)
    const index = ids.indexOf(groupId)
    const target = index + dir
    if (index < 0 || target < 0 || target >= ids.length) return
    ;[ids[index], ids[target]] = [ids[target], ids[index]]
    await run(async () => { await onReorder(ids) })
  }

  return (
    <Modal
      onClose={onClose}
      labelledBy="watchlist-groups-title"
      initialFocusRef={inputRef}
      panelClassName="w-[92vw] max-w-md bg-surface border border-border rounded-card shadow-xl"
    >
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <div>
          <h2 id="watchlist-groups-title" className={TYPE.section}>管理自选分组</h2>
          <p className="mt-0.5 text-xs text-muted">删除分组不会删除其中的股票</p>
        </div>
        <button type="button" onClick={onClose} className="h-8 w-8 inline-flex items-center justify-center text-muted hover:text-foreground" aria-label="关闭">
          <X className="h-4 w-4" />
        </button>
      </div>

      {/* 显示在侧边栏 开关 */}
      <div className="flex items-center justify-between border-b border-border px-4 py-2.5">
        <div className="min-w-0">
          <div className="text-xs font-medium text-foreground">显示在侧边栏</div>
          <div className="mt-0.5 text-micro text-muted">开启后可在左侧菜单展开分组子菜单</div>
        </div>
        <button
          type="button"
          onClick={() => void toggleGroupsInNav(!groupsInNav)}
          disabled={navTogglePending}
          className={`relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-colors duration-expand disabled:opacity-50 ${
            groupsInNav ? 'bg-accent' : 'bg-elevated'
          }`}
          title={groupsInNav ? '已开启 — 点击关闭' : '已关闭 — 点击开启'}
        >
          <span className={`inline-block h-4 w-4 rounded-full bg-white shadow-sm transition-transform duration-expand ${
            groupsInNav ? 'translate-x-[18px]' : 'translate-x-0.5'
          }`} />
        </button>
      </div>

      <div className="px-4 py-3">
        <div className="flex gap-2">
          <input
            ref={inputRef}
            value={newName}
            maxLength={24}
            onChange={event => setNewName(event.target.value)}
            onKeyDown={event => { if (event.key === 'Enter') void create() }}
            placeholder="新分组名称"
            className="h-8 min-w-0 flex-1 rounded-btn border border-border bg-elevated px-3 text-xs text-foreground outline-none focus:border-accent/50"
          />
          <button
            type="button"
            onClick={() => void create()}
            disabled={pending}
            className="inline-flex h-8 items-center gap-1.5 rounded-btn bg-accent px-3 text-xs text-white disabled:opacity-50"
          >
            <Plus className="h-3.5 w-3.5" />
            新建
          </button>
        </div>
        <div className="mt-2 flex items-start gap-2">
          <span className="mt-1 shrink-0 text-xs text-muted">分组颜色</span>
          <GroupColorPicker value={newColor} onChange={setNewColor} />
        </div>
        {error && <p className="mt-2 text-xs text-danger">{error}</p>}
      </div>

      <div className="max-h-[360px] overflow-y-auto border-t border-border px-4">
        {groups.length === 0 ? (
          <div className="py-10 text-center text-xs text-muted">暂无自定义分组</div>
        ) : groups.map((group, index) => {
          const color = resolveWatchlistGroupColor(group.color)
          return (
          <div key={group.id} className="flex min-h-12 items-center gap-2 border-b border-border/60 last:border-0">
            <span className={`h-6 w-1 shrink-0 rounded-full ${color.dot}`} />
            {editingId === group.id ? (
              <div className="min-w-0 flex-1 py-2">
                <div className="flex items-center gap-1.5">
                  <input
                    value={editingName}
                    maxLength={24}
                    onChange={event => setEditingName(event.target.value)}
                    onKeyDown={event => { if (event.key === 'Enter') void rename(group.id) }}
                    className={`h-7 min-w-0 flex-1 rounded-btn border bg-elevated px-2 text-xs text-foreground outline-none ${resolveWatchlistGroupColor(editingColor).border}`}
                    autoFocus
                  />
                  <button type="button" disabled={pending} onClick={() => void rename(group.id)} className={`p-1 ${resolveWatchlistGroupColor(editingColor).text}`} title="保存分组">
                    <Check className="h-3.5 w-3.5" />
                  </button>
                  <button type="button" onClick={() => setEditingId(null)} className="p-1 text-muted hover:text-foreground" title="取消">
                    <X className="h-3.5 w-3.5" />
                  </button>
                </div>
                <div className="mt-1.5">
                  <GroupColorPicker value={editingColor} onChange={setEditingColor} />
                </div>
              </div>
            ) : deletingId === group.id ? (
              <>
                <span className="min-w-0 flex-1 text-xs text-secondary">
                  删除“{group.name}”？{(counts[group.id] ?? 0) > 0 ? ` ${counts[group.id]} 只股票将回到未分组。` : ''}
                </span>
                <button
                  type="button"
                  disabled={pending}
                  onClick={() => void run(async () => { await onDelete(group.id); setDeletingId(null) })}
                  className="rounded px-2 py-1 text-xs text-danger bg-danger/10 hover:bg-danger/20 disabled:opacity-50"
                >
                  确认
                </button>
                <button type="button" onClick={() => setDeletingId(null)} className="p-1 text-muted hover:text-foreground" aria-label="取消删除">
                  <X className="h-3.5 w-3.5" />
                </button>
              </>
            ) : (
              <>
                <span className={`min-w-0 flex-1 truncate text-xs ${color.text}`}>{group.name}</span>
                <span className="font-mono text-micro text-muted tabular-nums">{counts[group.id] ?? 0} 只</span>
                {onReorder && groups.length > 1 && (
                  <>
                    <button
                      type="button"
                      disabled={pending || index === 0}
                      onClick={() => void move(group.id, -1)}
                      className="p-1 text-muted hover:text-accent disabled:opacity-30 disabled:hover:text-muted"
                      title="上移"
                      aria-label={`上移分组 ${group.name}`}
                    >
                      <ChevronUp className="h-3.5 w-3.5" />
                    </button>
                    <button
                      type="button"
                      disabled={pending || index === groups.length - 1}
                      onClick={() => void move(group.id, 1)}
                      className="p-1 text-muted hover:text-accent disabled:opacity-30 disabled:hover:text-muted"
                      title="下移"
                      aria-label={`下移分组 ${group.name}`}
                    >
                      <ChevronDown className="h-3.5 w-3.5" />
                    </button>
                  </>
                )}
                <button
                  type="button"
                  onClick={() => {
                    setEditingId(group.id)
                    setEditingName(group.name)
                    setEditingColor(group.color)
                    setDeletingId(null)
                    setError('')
                  }}
                  className="p-1 text-muted hover:text-accent"
                  title="编辑分组"
                >
                  <Pencil className="h-3.5 w-3.5" />
                </button>
                <button
                  type="button"
                  onClick={() => { setDeletingId(group.id); setEditingId(null); setError('') }}
                  className="p-1 text-muted hover:text-danger"
                  title="删除分组"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </>
            )}
          </div>
          )
        })}
      </div>
    </Modal>
  )
}

interface GroupPickerProps {
  groups: WatchlistGroup[]
  /** 该标的当前所属分组 id 列表 */
  groupIds: string[]
  symbol: string
  disabled?: boolean
  /** 勾选=加入该分组, 取消勾选=仅移出该分组 (标的保留在自选中) */
  onToggleMember: (symbol: string, groupId: string, member: boolean) => void
}

export function WatchlistGroupPicker({ groups, groupIds, symbol, disabled, onToggleMember }: GroupPickerProps) {
  const [open, setOpen] = useState(false)
  const [pos, setPos] = useState({ top: 0, left: 0, flipUp: false })
  const btnRef = useRef<HTMLButtonElement>(null)
  const popRef = useRef<HTMLDivElement>(null)

  const POP_WIDTH = 176
  const openMenu = () => {
    const rect = btnRef.current?.getBoundingClientRect()
    if (rect) {
      // 面板右对齐按钮 (视口边界保护); 底部放不下时翻转到按钮上方
      const estHeight = groups.length * 28 + 44
      const flipUp = rect.bottom + estHeight > window.innerHeight && rect.top > estHeight
      setPos({
        top: flipUp ? rect.top - 4 : rect.bottom + 4,
        left: Math.max(8, Math.min(rect.right - POP_WIDTH, window.innerWidth - POP_WIDTH - 8)),
        flipUp,
      })
    }
    setOpen(true)
  }

  // 外部点击 / Esc 关闭 (按钮与面板自身除外)
  useEffect(() => {
    if (!open) return
    const onDocMouseDown = (e: MouseEvent) => {
      const target = e.target as Node
      if (btnRef.current?.contains(target) || popRef.current?.contains(target)) return
      setOpen(false)
    }
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('mousedown', onDocMouseDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDocMouseDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  const memberSet = new Set(groupIds)
  const memberGroups = groupIds
    .map(gid => groups.find(g => g.id === gid))
    .filter((g): g is WatchlistGroup => !!g)
  const dots = memberGroups.slice(0, 3)
  const titleNames = memberGroups.map(g => g.name).join('、')

  return (
    <>
      <button
        ref={btnRef}
        type="button"
        disabled={disabled}
        onClick={event => { event.stopPropagation(); if (open) setOpen(false); else openMenu() }}
        // [R519] **定宽 32px, 内容居中。** 用户: 「一张表, 显示全部个股或者未分组的个股, 我滚动个股, 会发现不对齐」。
        // 原来宽度跟着内容走: 未分组是 14px 的文件夹图标, 一个组是 8px 的圆点, 叠点再宽一截, 超过三个还挂「+N」——
        // 这组按钮靠右对齐, 于是它的左边缘(连带名字能占的宽度)每行不一样, 实测落在三个位置, 最多差 24px。
        // 32px 装得下最宽的那种(三个叠点 + 「+N」)。
        className={`relative inline-flex h-5 w-8 shrink-0 items-center justify-center gap-0.5 rounded border border-transparent transition-colors ${
          memberGroups.length > 0
            ? 'hover:border-accent/30'
            : 'text-muted hover:border-accent/30 hover:text-accent'
        } ${disabled ? 'opacity-40' : ''}`}
        title={memberGroups.length === 0 ? '未分组 — 点击设置分组' : `分组：${titleNames}`}
        aria-label={`${symbol} 的分组`}
        aria-haspopup="menu"
        aria-expanded={open}
      >
        {dots.length === 0 ? (
          <FolderInput className="h-3.5 w-3.5" />
        ) : (
          // 叠瓦式圆点: 先加的分组在最上层完整显示, 后加的从其右侧露出半圆, 紧凑不撑宽
          <span className="flex items-center">
            {dots.map((g, i) => (
              <span
                key={g.id}
                style={{ zIndex: dots.length - i }}
                className={`relative h-2 w-2 rounded-full ring-1 ring-border/50 ${resolveWatchlistGroupColor(g.color).dot} ${i > 0 ? '-ml-1' : ''}`}
              />
            ))}
            {memberGroups.length > 3 && (
              <span className="ml-0.5 font-mono text-micro leading-none text-muted">+{memberGroups.length - 3}</span>
            )}
          </span>
        )}
      </button>
      {open && createPortal(
        <div
          ref={popRef}
          role="menu"
          aria-label={`${symbol} 的分组`}
          data-watchlist-group-menu
          style={{
            position: 'fixed',
            top: pos.flipUp ? undefined : pos.top,
            bottom: pos.flipUp ? window.innerHeight - pos.top : undefined,
            left: pos.left,
            width: POP_WIDTH,
          }}
          className="z-50 rounded-card border border-border bg-base p-1 shadow-xl"
          onClick={event => event.stopPropagation()}
        >
          <div className="px-2 pb-1 pt-1.5 text-micro text-muted">加入分组（可多选）</div>
          {groups.length === 0 ? (
            <div className="px-2 py-2 text-xs text-muted">暂无分组，请先新建</div>
          ) : groups.map(group => {
            const color = resolveWatchlistGroupColor(group.color)
            const member = memberSet.has(group.id)
            return (
              <button
                key={group.id}
                type="button"
                role="menuitemcheckbox"
                aria-checked={member}
                onClick={() => onToggleMember(symbol, group.id, !member)}
                className={`flex w-full items-center gap-2 rounded px-2 py-1 text-left text-xs transition-colors hover:bg-elevated ${
                  member ? color.text : 'text-secondary'
                }`}
              >
                <span className={`inline-flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded-sm border ${
                  member ? `${color.border} ${color.background}` : 'border-border'
                }`}>
                  {member && <Check className="h-2.5 w-2.5" />}
                </span>
                <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${color.dot}`} />
                <span className="min-w-0 flex-1 truncate">{group.name}</span>
              </button>
            )
          })}
          {groups.length > 0 && groupIds.length === 0 && (
            <div className="border-t border-border/60 px-2 pb-1 pt-1.5 text-micro text-muted">
              未加入任何分组 — 标的仍在自选中
            </div>
          )}
        </div>,
        document.body,
      )}
    </>
  )
}
