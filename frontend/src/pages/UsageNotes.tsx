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
 *
 * [R180] 改造成**消息面**。用户: 「当作是个消息面, 我上传的数据或者图片都会调度
 * AI 凝练后保存, 然后还要凝练一大段总的, 以后每次做出决策性的结论都得参考一次
 * 这一大段总的」。三件事是新的:
 *   · 可以传图/传文本文件(也支持直接 Ctrl+V 粘贴截图) —— 研报、公告截图最常见;
 *   · 每条可让 AI 凝练成一段要点;
 *   · **只保存凝练, 不保存图片; 文字保留原文**(用户定的口径) —— 图片凝练成功后
 *     原件即删, 只留要点与文件名; 文本文件的内容并进正文。盘上不长期堆附件。
 *     代价说明白: 图删了就没法重新凝练, AI 读错了也回不去。
 *   · 顶部一段**总的** —— 综合全部条目, 并且**之后每次 AI 决策都会带上它**
 *     (今日导读·优选 / 个股信号 / 模拟交易)。
 *
 * 状态链一个字没改 —— 消息面同样需要"这条后来成立没有"。而且标了「不成立」的
 * 会被明确喂给综合, 让它写清楚哪条已经被证伪: 留着一条已经错了的判断比没有更糟。
 *
 * **注入只到 AI 层。** 把握分/出场线/六态/通道位置这些规则层的东西一个字都不吃
 * 这段总结 —— 它们必须保持可复现。这条边界在后端有测试钉着。
 */
import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  NotebookPen, Plus, Pencil, Trash2, Loader2, X, Check, Search, Pin, PinOff,
  Sparkles, ImageIcon, Paperclip, ChevronDown, RefreshCw,
} from 'lucide-react'
import { api, type NewsDeskSummary, type UsageNote } from '@/lib/api'
import { toast } from '@/components/Toast'
import { QK } from '@/lib/queryKeys'
import { PageHeader } from '@/components/PageHeader'
import { EmptyState } from '@/components/EmptyState'
import { CollapsibleText } from '@/components/CollapsibleText'
import { storage } from '@/lib/storage'
import { cn } from '@/lib/cn'

/** [R266] 收起时留几行。
 *
 * 总览给 6 行 —— 够看清开头是「今天什么基调」还是「有几条埋伏待验证」, 决定要不要展开;
 * 卡片给 8 行 —— 一条记录的头两三句通常就说清了是什么事, 再多是细节。
 * 两者都只是**收起高度**, 真实内容一个字不少, 展开即见。
 */
const SUMMARY_LINES = 6
const NOTE_LINES = 8

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

/** [R181] 时效档: 与 status(成立了吗)正交的第二个轴 —— 这条多久有效。
 *
 * 三类在决策里的用法完全不同, 所以配色也拉开:
 *   时效  几天内有效, 影响今天买不买 —— 中性
 *   埋伏  还没兑现的逻辑, 影响持有耐心 —— 暖色(要一直看得见)
 *   规律  方法论, 不过期 —— 冷色(不针对某只票)
 */
type Horizon = 'news' | 'thesis' | 'rule'
const HORIZON_CYCLE: Horizon[] = ['news', 'thesis', 'rule']
const HORIZON_META: Record<Horizon, { label: string; cls: string; hint: string }> = {
  news: {
    label: '时效', cls: 'border-border text-muted',
    hint: '时效 —— 政策/突发/公告。几天内影响判断, 过后就不再进决策。点击切换',
  },
  thesis: {
    label: '埋伏', cls: 'border-amber-400/40 bg-amber-400/10 text-amber-400',
    hint: '埋伏 —— 业绩/基本面逻辑, 不会立刻兑现。不按天数淘汰, 一直留在总览里影响'
      + '「要不要有耐心继续持有」; 到兑现检查点会提醒你回来给结论。点击切换',
  },
  rule: {
    label: '规律', cls: 'border-sky-400/40 bg-sky-400/10 text-sky-300',
    hint: '规律 —— 关于市场本身的经验(某形态胜率高之类)。不针对某只票, 永不过期。点击切换',
  },
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

function NoteCard({ note, onDigest, digesting }: {
  note: UsageNote
  /** [R180] 凝练由页面统一持有 —— 卡片自己发起的话, 每张卡都要挂一份
   *  mutation, 而"哪一张正在凝练"的状态又得靠 id 比对, 不如提上去。 */
  onDigest: (id: string) => void
  digesting: boolean
}) {
  const qc = useQueryClient()
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(note.content)
  const [showRaw, setShowRaw] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const invalidate = () => {
    qc.invalidateQueries({ queryKey: QK.usageNotes })
    // 标了结论之后到期提醒要跟着消失, 否则那条横幅会一直挂着
    qc.invalidateQueries({ queryKey: ['usage-notes-due'] })
  }

  const update = useMutation({
    mutationFn: (patch: { content?: string; status?: string; pinned?: boolean; horizon?: Horizon }) =>
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
          {/* [R180] 有凝练时以**要点**为主体, 原文收进可展开的一行。
              凝练是多一层不是替换 —— 原文永远还在, 因为 AI 会漏、会读错,
              而这条记录之后要进综合、进决策, 得能翻回去核对。 */}
          {note.digest ? (
            <div className="flex-1">
              {/* [R266] 收起到固定行数 —— 卡片墙里一条长记录原来会撑出上千像素的卡片,
                  同一行旁边那条只有一句话, 高度差到整面墙没法看。 */}
              <CollapsibleText
                lines={NOTE_LINES}
                className="whitespace-pre-wrap text-[13px] leading-relaxed text-foreground"
              >
                {note.digest}
              </CollapsibleText>
              {(note.content || note.attachment) && (
                <button
                  onClick={() => setShowRaw(v => !v)}
                  className="mt-1.5 inline-flex items-center gap-1 text-[10px] text-muted/70 transition-colors hover:text-foreground cursor-pointer"
                >
                  <ChevronDown className={cn('h-3 w-3 transition-transform', showRaw && 'rotate-180')} />
                  {showRaw ? '收起原文' : '原文'}
                  {note.attachment && (
                    <span className="opacity-70" title={note.attachment.path
                      ? '原件还在(这条还没凝练成功)'
                      : '来自这个文件; 图片原件在凝练后已删除, 只保留要点'}>
                      · 来自 {note.attachment.name}
                    </span>
                  )}
                </button>
              )}
              {showRaw && (
                /* 原文可能很长(整份研报的文字) —— 给个上限自己滚, 不让它把卡片顶穿 */
                <p className="mt-1 max-h-48 overflow-y-auto whitespace-pre-wrap rounded border border-border/40 bg-base/50 px-2 py-1.5 text-[11px] leading-relaxed text-muted">
                  {note.content || <span className="italic opacity-70">(只有附件, 没有正文)</span>}
                </p>
              )}
            </div>
          ) : (
            <div className="flex-1">
              {note.content ? (
                <CollapsibleText
                  lines={NOTE_LINES}
                  className="whitespace-pre-wrap text-[13px] leading-relaxed text-foreground"
                >
                  {note.content}
                </CollapsibleText>
              ) : (
                <p className="text-[13px] leading-relaxed">
                  <span className="italic text-muted">(只有附件)</span>
                </p>
              )}
              {note.attachment && (
                <span
                  className="mt-1 inline-flex items-center gap-1 text-[10px] text-warning/80"
                  title="还没凝练成功 —— 原件暂时留着, 点 ✨ 重试。凝练成功后图片会被删掉, 只留要点。"
                >
                  {note.kind === 'image' ? <ImageIcon className="h-3 w-3" /> : <Paperclip className="h-3 w-3" />}
                  {note.attachment.name} · 待凝练
                </span>
              )}
            </div>
          )}
          <div className="mt-2.5 flex items-center gap-2 border-t border-border/50 pt-2">
            <StatusChip status={status} onCycle={cycleStatus} busy={update.isPending} />
            {/* [R181] 时效档。点击循环 时效→埋伏→规律 —— AI 判错了要能一键改, 
                而不是去某个下拉里找。 */}
            <button
              onClick={() => {
                const cur = (note.horizon ?? 'news') as Horizon
                const next = HORIZON_CYCLE[(HORIZON_CYCLE.indexOf(cur) + 1) % HORIZON_CYCLE.length]
                update.mutate({ horizon: next })
              }}
              disabled={update.isPending}
              title={HORIZON_META[(note.horizon ?? 'news') as Horizon].hint}
              className={cn(
                'rounded border px-1.5 py-0.5 text-[10px] transition-colors cursor-pointer',
                HORIZON_META[(note.horizon ?? 'news') as Horizon].cls,
              )}
            >
              {HORIZON_META[(note.horizon ?? 'news') as Horizon].label}
            </button>
            {note.horizon === 'thesis' && note.due_at && (
              <span
                className={cn('text-[10px] tabular-nums',
                  new Date(note.due_at) <= new Date() ? 'text-warning' : 'text-muted/60')}
                title={new Date(note.due_at) <= new Date()
                  ? '到兑现检查点了 —— 回来把它标成「已验证」还是「不成立」'
                  : '到这天回来核对它兑现了没有'}
              >
                {new Date(note.due_at) <= new Date() ? '⏰ 该核对' : `核对 ${fmtTime(note.due_at).slice(0, 5)}`}
              </span>
            )}
            <span className="text-[10px] tabular-nums text-muted/60" title={`创建 ${note.created_at.replace('T', ' ')}`}>
              {note.updated_at !== note.created_at ? `改 ${fmtTime(note.updated_at)}` : fmtTime(note.created_at)}
            </span>
            <div className="ml-auto flex items-center gap-0.5">
              <button
                onClick={() => onDigest(note.id)}
                disabled={digesting}
                title={note.digest
                  ? '重新凝练(改过正文之后可以重来)'
                  : '让 AI 把这条凝练成要点。图片会直接读图。'}
                className="rounded p-1 text-muted/60 transition-colors hover:bg-elevated hover:text-violet-300 disabled:opacity-40"
              >
                {digesting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Sparkles className="h-3.5 w-3.5" />}
              </button>
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
  // [R266] 总览默认收起 —— 但用户上次展开过就照他的来
  const [summaryOpen, setSummaryOpen] = useState(() => storage.newsDeskSummaryOpen.get(false))

  const create = useMutation({
    mutationFn: () => api.usageNoteCreate(draft),
    onSuccess: () => {
      setDraft('')
      qc.invalidateQueries({ queryKey: QK.usageNotes })
    },
  })

  // [R180] 上传: 落盘即返回, 然后**自动**触发一次凝练。
  // 两步分开是后端的设计(上传要立刻有反馈), 但对用户来说传完就该看到要点,
  // 所以这里替他把第二步也点了; 凝练失败只提示, 记录已经存下了不会丢。
  const upload = useMutation({
    mutationFn: async (file: File) => {
      const note = await api.usageNoteUpload(file, draft)
      try {
        return await api.usageNoteDigest(note.id)
      } catch (e) {
        toast(e instanceof Error ? e.message : '已保存, 但凝练失败', 'error')
        return note
      }
    },
    onSuccess: () => {
      setDraft('')
      qc.invalidateQueries({ queryKey: QK.usageNotes })
    },
    onError: (e) => toast(e instanceof Error ? e.message : '上传失败', 'error'),
  })

  const digest = useMutation({
    mutationFn: (id: string) => api.usageNoteDigest(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: QK.usageNotes }),
    onError: (e) => toast(e instanceof Error ? e.message : '凝练失败', 'error'),
  })

  // [R181] 到了兑现检查点、还没给结论的埋伏。
  // **埋伏最容易失败的方式不是记错, 是记了之后忘了** —— 三个月后财报出来, 人早忘了
  // 当初为什么买。所以到期要主动顶到页面最前, 不能等用户自己翻。
  const dueQ = useQuery({
    queryKey: ['usage-notes-due'],
    queryFn: api.usageNotesDue,
    staleTime: 5 * 60_000,
  })
  const due = dueQ.data?.items ?? []

  // 一大段总的 —— 只在点按钮时重新综合, 打开页面读已存的
  const summaryQ = useQuery({
    queryKey: ['usage-notes-summary'],
    queryFn: api.usageNotesSummaryGet,
    staleTime: 5 * 60_000,
  })
  const summary: NewsDeskSummary | null = summaryQ.data?.summary ?? null
  // 过期多少天 —— 一段过期的消息面总结比没有更危险, 标题行要直说
  const staleDays = useMemo(() => {
    if (!summary?.as_of) return null
    const d = (Date.now() - new Date(summary.as_of).getTime()) / 86400_000
    return d > 0 ? Math.floor(d) : 0
  }, [summary])
  const rebuild = useMutation({
    mutationFn: api.usageNotesSummaryBuild,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['usage-notes-summary'] })
      toast('已重新综合 —— 之后的 AI 决策会带上这一段', 'success')
    },
    onError: (e) => toast(e instanceof Error ? e.message : '综合失败', 'error'),
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
      && (!kw || n.content.toLowerCase().includes(kw)
        || (n.digest ?? '').toLowerCase().includes(kw)),
    )
  }, [notes, filter, search])

  return (
    <div className="flex h-full flex-col">
      <PageHeader title="消息面" subtitle="记录 → AI 凝练 → 综合成一段总的 → 每次 AI 决策都带上它" />
      <div className="min-h-0 flex-1 overflow-y-auto px-3 pb-4 pt-3 lg:px-4">
        {/* [R129] 原来 mx-auto max-w-5xl(1024px) 居中: 这是一面卡片墙, 宽屏下
            两侧空一大片而卡片仍挤成两列。改为贴左 + 放宽到 1600px, 配合下方
            网格在宽屏加到三列 —— 观察条目多的时候一屏能多看一行。 */}
        <div className="w-full max-w-[1600px] space-y-3">
          {/* [R181] 到期埋伏提醒 —— 排在总览之前, 因为它是这一页唯一需要你"现在动手"的东西 */}
          {due.length > 0 && (
            <div className="rounded-card border border-warning/30 bg-warning/[0.07] px-3 py-2">
              <div className="mb-1 text-[11px] font-medium text-warning">
                ⏰ {due.length} 条埋伏到兑现检查点了 —— 回来给个结论
              </div>
              <ul className="space-y-0.5">
                {due.map(n => (
                  <li key={n.id} className="text-[11px] leading-relaxed text-foreground/85">
                    · {(n.digest || n.content).slice(0, 60)}
                    {(n.digest || n.content).length > 60 && '…'}
                  </li>
                ))}
              </ul>
              <p className="mt-1 text-[10px] text-muted/70">
                在下面找到它, 把状态点成「已验证」或「不成立」——
                不给结论的话它会一直留在总览里影响之后的判断。
              </p>
            </div>
          )}

          {/* [R180] 一大段总的 —— 这一页最重要的产物: 之后每次 AI 决策都会带上它。
              所以放最上面, 并且把"多旧、基于几条"直接写在标题行上: 一段过期的
              消息面总结比没有更危险, 用户得一眼看见它的时效。 */}
          <section className="rounded-card border border-violet-400/25 bg-violet-400/[0.05] p-3">
            <div className="mb-1.5 flex flex-wrap items-center gap-2">
              <span className="inline-flex items-center gap-1.5 text-[11px] font-medium text-violet-300">
                <Sparkles className="h-3.5 w-3.5" />
                消息面总览
              </span>
              {summary && (
                <span className="text-[10px] text-muted">
                  综合自 {summary.item_count} 条 · {fmtTime(summary.as_of)}
                  {staleDays != null && staleDays > 7 && (
                    <span className="ml-1.5 text-warning">已过期 {staleDays} 天,不再参与决策</span>
                  )}
                </span>
              )}
              <button
                onClick={() => rebuild.mutate()}
                disabled={rebuild.isPending || notes.length === 0}
                title={'把下面全部条目重新综合成一段。\n'
                  + '这一段会被带进: 今日 AI 导读·优选 / AI 个股信号 / 模拟交易。\n'
                  + '不会进把握分、出场线、六态、通道位置 —— 那些是纯规则的, 必须保持可复现。'}
                className="ml-auto inline-flex items-center gap-1 rounded-btn border border-violet-400/40 bg-violet-400/15 px-2 py-0.5 text-[10px] text-violet-300 transition-colors cursor-pointer hover:bg-violet-400/25 disabled:opacity-40"
              >
                {rebuild.isPending ? <Loader2 className="h-3 w-3 animate-spin" /> : <RefreshCw className="h-3 w-3" />}
                {summary ? '重新综合' : '生成总览'}
              </button>
            </div>
            {summary?.text ? (
              /* [R266] 这一段是 AI 综合出来的, 动辄几十行 —— 原来全量铺开, 一进页面
                 就把整屏吃光, 下面的输入框和卡片墙全被顶到屏外。收起到几行, 想读再展开;
                 展开与否记在本地, 看惯了展开的人不用每次重点。 */
              <CollapsibleText
                lines={SUMMARY_LINES}
                defaultOpen={summaryOpen}
                onOpenChange={(v) => { setSummaryOpen(v); storage.newsDeskSummaryOpen.set(v) }}
                moreLabel="展开全文"
                className="whitespace-pre-wrap text-[12px] leading-relaxed text-foreground/90"
              >
                {summary.text}
              </CollapsibleText>
            ) : (
              <p className="text-[11px] text-muted">
                还没有总览。下面记几条之后点「生成总览」——
                之后每次 AI 做决策(今日导读·优选 / 个股信号 / 模拟交易)都会先看这一段。
              </p>
            )}
            {/* [R266] 这段边界说明只在展开时出现: 收起时是在扫一眼, 两行小字白占地方;
                真要细读这段总览的时候, 才需要看见"它不会覆盖规则层"这条界限。 */}
            {(summaryOpen || !summary?.text) && (
              <p className="mt-1.5 text-[10px] text-muted/60">
                总览只作背景参考,<b className="font-medium">不会覆盖价格与规则层的事实</b>
                (趋势状态、出场线、通道位置、把握分)。两者冲突时以价格与规则为准。
              </p>
            )}
          </section>

          {/* 新增区: 单行起步, 聚焦时长高 */}
          <div className="rounded-card border border-border bg-surface p-3">
            <div className="flex items-start gap-2">
              <textarea
                // [R266] rows 默认是 2, min-h 只管下限 —— 空着时按意图该是一行,
                // 实际却白占了一行高。写死 rows=1, 聚焦或有草稿时再靠 min-h 长高。
                rows={1}
                className={cn(TA_CLS, draft ? 'min-h-[72px]' : 'min-h-[38px] focus:min-h-[72px]')}
                placeholder="记一条观察… (Ctrl+Enter 保存)"
                value={draft}
                onChange={e => setDraft(e.target.value)}
                onKeyDown={e => {
                  if ((e.ctrlKey || e.metaKey) && e.key === 'Enter' && draft.trim()) create.mutate()
                }}
                onPaste={e => {
                  // 截图直接粘 —— 研报/公告截图是这一页最常见的输入, 让它少一步
                  const img = Array.from(e.clipboardData.files).find(f => f.type.startsWith('image/'))
                  if (img) { e.preventDefault(); upload.mutate(img) }
                }}
              />
              {/* [R180] 传图/传文件。上面那个 textarea 里的文字会作为这条的备注一起带上 ——
                  「这张图是什么」经常比图本身更重要。 */}
              <label
                title={'传图片(png/jpg/webp…)或文本文件(txt/md/csv/json)。也可以直接在左边输入框里 Ctrl+V 粘贴截图。\n'
                  + '传完自动让 AI 凝练一次。\n'
                  + '注意: 图片凝练成功后原件会被删除, 只保留要点(文字会保留原文)。'}
                className="inline-flex h-[38px] shrink-0 cursor-pointer items-center gap-1 rounded-btn border border-border bg-base px-2.5 text-xs text-muted transition-colors hover:text-foreground"
              >
                {upload.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Paperclip className="h-3.5 w-3.5" />}
                传图/文件
                <input
                  type="file"
                  className="hidden"
                  accept=".png,.jpg,.jpeg,.webp,.gif,.bmp,.txt,.md,.csv,.tsv,.json,.log"
                  onChange={e => {
                    const f = e.target.files?.[0]
                    if (f) upload.mutate(f)
                    e.target.value = ''      // 同一个文件连传两次也要能触发
                  }}
                />
              </label>
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
              {shown.map(note => (
                <NoteCard
                  key={note.id}
                  note={note}
                  onDigest={(id) => digest.mutate(id)}
                  digesting={digest.isPending && digest.variables === note.id}
                />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
