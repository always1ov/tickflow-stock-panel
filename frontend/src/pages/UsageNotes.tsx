/**
 * [fork 增强] R93/R96 我的使用观察 — 观察验证账。
 *
 * R93 是一本纯文本草稿纸; 上线后看到的真实用法是记"盘面观察→等市场验证"
 * 的猜想(凯特纳贴下轨胜率高、昨日AI优选次日会涨…), R96 按这个用法重排:
 *
 *   - 每条可标状态: 随手记(默认) / 待验证 / 已验证 / 不成立 —— 点状态芯片
 *     直接循环切换, 一条观察的生命周期就是这条链;
 *   - 可置顶(常用结论钉在最上), 可搜索, 按状态过滤;
 *   - 紧凑两列卡片(宽屏), 时间与操作收进一行 footer, 不再一条笔记占一大块;
 *   - 标状态/置顶不刷新"编辑时间", 整理动作不打乱时间线。
 *
 * 仍然刻意没有: 分类、标签、富文本 —— 记下来就走。
 */
import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  NotebookPen, Plus, Pencil, Trash2, Loader2, X, Check, Search, Pin, PinOff,
} from 'lucide-react'
import { api, type UsageNote } from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import { PageHeader } from '@/components/PageHeader'
import { EmptyState } from '@/components/EmptyState'
import { cn } from '@/lib/cn'

const TA_CLS =
  'w-full rounded-lg bg-base border border-border px-3 py-2 text-[13px] leading-relaxed text-foreground placeholder:text-muted/40 focus:outline-none focus:border-accent/60 transition-colors resize-y'

type NoteStatus = '' | 'pending' | 'verified' | 'rejected'

/** 状态链: 点芯片循环切换 —— 随手记 → 待验证 → 已验证 → 不成立 → 随手记 */
const STATUS_CYCLE: NoteStatus[] = ['', 'pending', 'verified', 'rejected']

const STATUS_META: Record<NoteStatus, { label: string; cls: string; dot: string }> = {
  '':         { label: '随手记', cls: 'border-border text-muted',                          dot: 'bg-muted/50' },
  pending:    { label: '待验证', cls: 'border-warning/30 bg-warning/10 text-warning',      dot: 'bg-warning' },
  verified:   { label: '已验证', cls: 'border-emerald-400/30 bg-emerald-400/10 text-emerald-400', dot: 'bg-emerald-400' },
  rejected:   { label: '不成立', cls: 'border-danger/30 bg-danger/10 text-danger',         dot: 'bg-danger' },
}

const FILTERS: { key: 'all' | NoteStatus; label: string }[] = [
  { key: 'all', label: '全部' },
  { key: 'pending', label: '待验证' },
  { key: 'verified', label: '已验证' },
  { key: 'rejected', label: '不成立' },
  { key: '', label: '随手记' },
]

function fmtTime(iso: string): string {
  return iso.replace('T', ' ').slice(5, 16)   // "08-31 10:48" — 年份省掉, footer 更紧凑
}

function StatusChip({ status, onCycle, busy }: { status: NoteStatus; onCycle: () => void; busy: boolean }) {
  const meta = STATUS_META[status] ?? STATUS_META['']
  return (
    <button
      onClick={onCycle}
      disabled={busy}
      title="点击切换: 随手记 → 待验证 → 已验证 → 不成立"
      className={cn(
        'inline-flex h-6 items-center gap-1.5 rounded-btn border px-2 text-[10px] font-medium transition-colors cursor-pointer disabled:opacity-60',
        meta.cls,
      )}
    >
      <span className={cn('h-1.5 w-1.5 rounded-full', meta.dot)} />
      {meta.label}
    </button>
  )
}

function NoteCard({ note }: { note: UsageNote }) {
  const qc = useQueryClient()
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(note.content)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const invalidate = () => qc.invalidateQueries({ queryKey: QK.usageNotes })

  const update = useMutation({
    mutationFn: (patch: { content?: string; status?: string; pinned?: boolean }) =>
      api.usageNoteUpdate(note.id, patch),
    onSuccess: () => { setEditing(false); invalidate() },
  })
  const remove = useMutation({
    mutationFn: () => api.usageNoteDelete(note.id),
    onSuccess: invalidate,
  })

  const status = (note.status ?? '') as NoteStatus
  const cycleStatus = () => {
    const next = STATUS_CYCLE[(STATUS_CYCLE.indexOf(status) + 1) % STATUS_CYCLE.length]
    update.mutate({ status: next })
  }

  return (
    <div className={cn(
      'flex flex-col rounded-card border bg-surface p-3.5',
      note.pinned ? 'border-accent/40' : 'border-border',
    )}>
      {editing ? (
        <div className="space-y-2">
          <textarea
            className={cn(TA_CLS, 'min-h-[88px]')}
            value={draft}
            onChange={e => setDraft(e.target.value)}
            onKeyDown={e => {
              if ((e.ctrlKey || e.metaKey) && e.key === 'Enter' && draft.trim()) update.mutate({ content: draft })
              if (e.key === 'Escape') setEditing(false)
            }}
            autoFocus
          />
          <div className="flex items-center justify-end gap-2">
            <button
              onClick={() => setEditing(false)}
              className="inline-flex h-7 items-center gap-1 rounded-btn border border-border bg-base px-2 text-[11px] text-secondary hover:text-foreground transition-colors"
            >
              <X className="h-3 w-3" /> 取消
            </button>
            <button
              onClick={() => update.mutate({ content: draft })}
              disabled={update.isPending || !draft.trim()}
              className="inline-flex h-7 items-center gap-1 rounded-btn bg-accent/15 px-2 text-[11px] font-medium text-accent hover:bg-accent/25 transition-colors disabled:opacity-50"
            >
              {update.isPending ? <Loader2 className="h-3 w-3 animate-spin" /> : <Check className="h-3 w-3" />}
              保存
            </button>
          </div>
        </div>
      ) : (
        <>
          <p className="flex-1 whitespace-pre-wrap text-[13px] leading-relaxed text-foreground">{note.content}</p>
          <div className="mt-2.5 flex items-center gap-2 border-t border-border/50 pt-2">
            <StatusChip status={status} onCycle={cycleStatus} busy={update.isPending} />
            <span className="text-[10px] tabular-nums text-muted/60" title={`创建 ${note.created_at.replace('T', ' ')}`}>
              {note.updated_at !== note.created_at ? `改 ${fmtTime(note.updated_at)}` : fmtTime(note.created_at)}
            </span>
            <div className="ml-auto flex items-center gap-0.5">
              <button
                onClick={() => update.mutate({ pinned: !note.pinned })}
                disabled={update.isPending}
                className={cn(
                  'rounded p-1 transition-colors',
                  note.pinned ? 'text-accent hover:bg-accent/10' : 'text-muted/60 hover:bg-elevated hover:text-foreground',
                )}
                title={note.pinned ? '取消置顶' : '置顶'}
              >
                {note.pinned ? <Pin className="h-3.5 w-3.5" /> : <PinOff className="h-3.5 w-3.5" />}
              </button>
              <button
                onClick={() => { setDraft(note.content); setEditing(true); setConfirmDelete(false) }}
                className="rounded p-1 text-muted/60 hover:bg-elevated hover:text-foreground transition-colors"
                title="编辑"
              >
                <Pencil className="h-3.5 w-3.5" />
              </button>
              <button
                onClick={() => (confirmDelete ? remove.mutate() : setConfirmDelete(true))}
                onBlur={() => setConfirmDelete(false)}
                disabled={remove.isPending}
                className={cn(
                  'rounded p-1 transition-colors',
                  confirmDelete
                    ? 'bg-danger/15 text-danger hover:bg-danger/25'
                    : 'text-muted/60 hover:bg-elevated hover:text-danger',
                )}
                title={confirmDelete ? '再点一次确认删除' : '删除'}
              >
                {remove.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Trash2 className="h-3.5 w-3.5" />}
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  )
}

export function UsageNotes() {
  const qc = useQueryClient()
  const notesQuery = useQuery({ queryKey: QK.usageNotes, queryFn: api.usageNotesList })
  const [draft, setDraft] = useState('')
  const [filter, setFilter] = useState<'all' | NoteStatus>('all')
  const [search, setSearch] = useState('')

  const create = useMutation({
    mutationFn: () => api.usageNoteCreate(draft),
    onSuccess: () => {
      setDraft('')
      qc.invalidateQueries({ queryKey: QK.usageNotes })
    },
  })

  const notes = useMemo(() => notesQuery.data?.items ?? [], [notesQuery.data])
  const counts = useMemo(() => {
    const c: Record<string, number> = { all: notes.length }
    for (const f of FILTERS) if (f.key !== 'all') c[f.key] = 0
    for (const n of notes) c[(n.status ?? '') as string] = (c[(n.status ?? '') as string] ?? 0) + 1
    return c
  }, [notes])
  const shown = useMemo(() => {
    const kw = search.trim().toLowerCase()
    return notes.filter(n =>
      (filter === 'all' || (n.status ?? '') === filter)
      && (!kw || n.content.toLowerCase().includes(kw)),
    )
  }, [notes, filter, search])

  return (
    <div className="flex h-full flex-col">
      <PageHeader title="我的使用观察" subtitle="观察 → 待验证 → 已验证 / 不成立" />
      <div className="min-h-0 flex-1 overflow-y-auto px-3 pb-4 pt-3 lg:px-4">
        {/* [R129] 原来 mx-auto max-w-5xl(1024px) 居中: 这是一面卡片墙, 宽屏下
            两侧空一大片而卡片仍挤成两列。改为贴左 + 放宽到 1600px, 配合下方
            网格在宽屏加到三列 —— 观察条目多的时候一屏能多看一行。 */}
        <div className="w-full max-w-[1600px] space-y-3">
          {/* 新增区: 单行起步, 聚焦时长高 */}
          <div className="rounded-card border border-border bg-surface p-3">
            <div className="flex items-start gap-2">
              <textarea
                className={cn(TA_CLS, draft ? 'min-h-[72px]' : 'min-h-[38px] focus:min-h-[72px]')}
                placeholder="记一条观察… (Ctrl+Enter 保存)"
                value={draft}
                onChange={e => setDraft(e.target.value)}
                onKeyDown={e => {
                  if ((e.ctrlKey || e.metaKey) && e.key === 'Enter' && draft.trim()) create.mutate()
                }}
              />
              <button
                onClick={() => create.mutate()}
                disabled={create.isPending || !draft.trim()}
                className="inline-flex h-[38px] shrink-0 items-center gap-1 rounded-btn bg-accent px-3 text-xs font-medium text-white hover:bg-accent/90 transition-colors disabled:opacity-40"
              >
                {create.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Plus className="h-3.5 w-3.5" />}
                添加
              </button>
            </div>
          </div>

          {/* 过滤 + 搜索 */}
          {notes.length > 0 && (
            <div className="flex flex-wrap items-center gap-1.5">
              {FILTERS.map(f => (
                <button
                  key={f.key || 'plain'}
                  onClick={() => setFilter(f.key)}
                  className={cn(
                    'inline-flex h-7 items-center gap-1 rounded-btn px-2.5 text-[11px] font-medium transition-colors cursor-pointer',
                    filter === f.key ? 'bg-accent/15 text-accent' : 'text-muted hover:bg-elevated hover:text-secondary',
                  )}
                >
                  {f.label}
                  <span className="text-[10px] tabular-nums opacity-70">{counts[f.key] ?? 0}</span>
                </button>
              ))}
              <div className="relative ml-auto">
                <Search className="pointer-events-none absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted/50" />
                <input
                  type="text"
                  value={search}
                  onChange={e => setSearch(e.target.value)}
                  placeholder="搜索…"
                  className="h-7 w-40 rounded-btn border border-border bg-base pl-7 pr-2 text-[11px] text-foreground placeholder:text-muted/40 focus:outline-none focus:border-accent/50 transition-colors"
                />
              </div>
            </div>
          )}

          {/* 列表: 宽屏两列, 置顶在前(后端排序) */}
          {notesQuery.isLoading ? null : notes.length === 0 ? (
            <EmptyState
              icon={NotebookPen}
              title="还没有观察"
              hint="记下盘面里看到的规律和猜想: 先「随手记」, 等市场给出答案后标成「已验证」或「不成立」。"
            />
          ) : shown.length === 0 ? (
            <div className="rounded-btn border border-dashed border-border py-6 text-center text-xs text-muted">
              没有匹配的笔记 —— 换个过滤条件或清空搜索
            </div>
          ) : (
            <div className="grid grid-cols-1 items-start gap-3 lg:grid-cols-2 2xl:grid-cols-3">
              {shown.map(note => <NoteCard key={note.id} note={note} />)}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
