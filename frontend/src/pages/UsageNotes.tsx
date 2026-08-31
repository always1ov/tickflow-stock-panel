/**
 * [fork 增强] R93 我的使用观察 — 纯文本笔记本。
 *
 * 用途: 归纳"这个系统怎么用、哪些功能有用"的个人观察。刻意保持极简:
 * 一个输入框新增, 每条可就地编辑/删除, 没有分类没有标签没有富文本 ——
 * 它就是一本草稿纸, 不该比正文更花时间。
 *
 * 交互约定:
 *   - 新增/编辑用同一种 textarea, Ctrl/⌘+Enter 保存, Esc 取消编辑;
 *   - 删除二次确认(点一次变红问一次, 再点才删), 不弹全局对话框;
 *   - 保存中禁用按钮, 失败由 api.ts 统一 toast, 本页不重复报错。
 */
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { NotebookPen, Plus, Pencil, Trash2, Loader2, X, Check } from 'lucide-react'
import { api, type UsageNote } from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import { PageHeader } from '@/components/PageHeader'
import { EmptyState } from '@/components/EmptyState'
import { cn } from '@/lib/cn'

const TA_CLS =
  'w-full min-h-[96px] rounded-lg bg-base border border-border px-3 py-2 text-sm leading-relaxed text-foreground placeholder:text-muted/40 focus:outline-none focus:border-accent/60 transition-colors resize-y'

function fmtTime(iso: string): string {
  return iso.replace('T', ' ').slice(0, 16)
}

function NoteCard({ note }: { note: UsageNote }) {
  const qc = useQueryClient()
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(note.content)
  const [confirmDelete, setConfirmDelete] = useState(false)

  const update = useMutation({
    mutationFn: () => api.usageNoteUpdate(note.id, draft),
    onSuccess: () => {
      setEditing(false)
      qc.invalidateQueries({ queryKey: QK.usageNotes })
    },
  })
  const remove = useMutation({
    mutationFn: () => api.usageNoteDelete(note.id),
    onSuccess: () => qc.invalidateQueries({ queryKey: QK.usageNotes }),
  })

  const startEdit = () => { setDraft(note.content); setEditing(true); setConfirmDelete(false) }

  return (
    <div className="rounded-card border border-border bg-surface p-4">
      {editing ? (
        <div className="space-y-2">
          <textarea
            className={TA_CLS}
            value={draft}
            onChange={e => setDraft(e.target.value)}
            onKeyDown={e => {
              if ((e.ctrlKey || e.metaKey) && e.key === 'Enter' && draft.trim()) update.mutate()
              if (e.key === 'Escape') setEditing(false)
            }}
            autoFocus
          />
          <div className="flex items-center justify-end gap-2">
            <button
              onClick={() => setEditing(false)}
              className="inline-flex h-8 items-center gap-1 rounded-btn border border-border bg-base px-2.5 text-xs text-secondary hover:text-foreground transition-colors"
            >
              <X className="h-3.5 w-3.5" /> 取消
            </button>
            <button
              onClick={() => update.mutate()}
              disabled={update.isPending || !draft.trim()}
              className="inline-flex h-8 items-center gap-1 rounded-btn bg-accent/15 px-2.5 text-xs font-medium text-accent hover:bg-accent/25 transition-colors disabled:opacity-50"
            >
              {update.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />}
              保存
            </button>
          </div>
        </div>
      ) : (
        <>
          <p className="whitespace-pre-wrap text-sm leading-relaxed text-foreground">{note.content}</p>
          <div className="mt-2.5 flex items-center gap-2 border-t border-border/50 pt-2">
            <span className="text-[10px] text-muted/70">
              {note.updated_at !== note.created_at ? `编辑于 ${fmtTime(note.updated_at)}` : fmtTime(note.created_at)}
            </span>
            <div className="ml-auto flex items-center gap-1">
              <button
                onClick={startEdit}
                className="rounded p-1.5 text-muted hover:bg-elevated hover:text-foreground transition-colors"
                title="编辑"
              >
                <Pencil className="h-3.5 w-3.5" />
              </button>
              <button
                onClick={() => (confirmDelete ? remove.mutate() : setConfirmDelete(true))}
                onBlur={() => setConfirmDelete(false)}
                disabled={remove.isPending}
                className={cn(
                  'rounded p-1.5 transition-colors',
                  confirmDelete
                    ? 'bg-danger/15 text-danger hover:bg-danger/25'
                    : 'text-muted hover:bg-elevated hover:text-danger',
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

  const create = useMutation({
    mutationFn: () => api.usageNoteCreate(draft),
    onSuccess: () => {
      setDraft('')
      qc.invalidateQueries({ queryKey: QK.usageNotes })
    },
  })

  const notes = notesQuery.data?.items ?? []

  return (
    <div className="flex h-full flex-col">
      <PageHeader title="我的使用观察" subtitle="归纳这套系统怎么用、哪些功能有用" />
      <div className="min-h-0 flex-1 overflow-y-auto px-3 pb-4 pt-3 lg:px-4">
        <div className="mx-auto w-full max-w-3xl space-y-3">
          {/* 新增区 */}
          <div className="rounded-card border border-border bg-surface p-4">
            <textarea
              className={TA_CLS}
              placeholder="记一条观察… (Ctrl+Enter 保存)"
              value={draft}
              onChange={e => setDraft(e.target.value)}
              onKeyDown={e => {
                if ((e.ctrlKey || e.metaKey) && e.key === 'Enter' && draft.trim()) create.mutate()
              }}
            />
            <div className="mt-2 flex items-center justify-between">
              <span className="text-[10px] text-muted/60">纯文本, 单条最长 2 万字</span>
              <button
                onClick={() => create.mutate()}
                disabled={create.isPending || !draft.trim()}
                className="inline-flex h-8 items-center gap-1 rounded-btn bg-accent/15 px-3 text-xs font-medium text-accent hover:bg-accent/25 transition-colors disabled:opacity-50"
              >
                {create.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Plus className="h-3.5 w-3.5" />}
                添加
              </button>
            </div>
          </div>

          {/* 列表 */}
          {notesQuery.isLoading ? null : notes.length === 0 ? (
            <EmptyState
              icon={NotebookPen}
              title="还没有笔记"
              hint="用它记下你摸索出来的用法: 哪个页面配哪个功能最顺手、哪些结果值得信、踩过什么坑。"
            />
          ) : (
            notes.map(note => <NoteCard key={note.id} note={note} />)
          )}
        </div>
      </div>
    </div>
  )
}
