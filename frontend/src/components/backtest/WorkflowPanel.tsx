import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertTriangle, ChevronDown, Info, LoaderCircle, Play, Rocket, Square, Trash2, Workflow as WorkflowIcon,
} from 'lucide-react'
import { toast } from '@/components/Toast'
import { api, type Workflow, type WorkflowKind } from '@/lib/api'
import { QK } from '@/lib/queryKeys'

/**
 * [fork 增强] R39 研究工作流面板 —— 挖掘与回测共用。
 *
 * 和下面那块「AI 自动挖掘」的区别只有一句话: 自动挖掘跑在页面里, 关页面就断、
 * 用满轮数就停; 工作流跑在服务端, 关页面照跑, 一次跑完不达标就换配置再来一次,
 * 直到达标或预算用尽。
 *
 * [R53] 两者是**包含关系**: 工作流的一次"重开"就是开一个自动挖掘会话。所以
 * 挖掘这一路两边不能同时开 —— 后端两侧都装了闸(建工作流时看有没有手动会话开着,
 * 开手动会话时看有没有工作流在跑), 这里只负责把 409 的中文原文 toast 出来。
 *
 * 手动路径一行没动 —— 这个面板只是又一个入口, 底下走的是同一批 step / run。
 */

const INPUT = 'h-8 w-full rounded-input border border-border bg-surface px-2 text-xs text-foreground outline-none transition-colors focus:border-accent'
const LABEL = 'mb-1 block text-[10px] font-medium text-secondary'
/** 有工作流在跑时才勤刷 —— 后台节拍器 20 秒一拍, 这里跟着它走 */
const LIVE_POLL_MS = 10_000

const STATUS_LABEL: Record<Workflow['status'], string> = {
  running: '跑着呢',
  satisfied: '跑出结果了',
  exhausted: '预算用完',
  stopped: '你中止了',
  failed: '出错停了',
}
const STATUS_CLS: Record<Workflow['status'], string> = {
  running: 'bg-accent/10 text-accent',
  satisfied: 'bg-success/10 text-success',
  exhausted: 'bg-warning/10 text-warning',
  stopped: 'bg-muted/10 text-muted',
  failed: 'bg-danger/10 text-danger',
}

function num(v: unknown, digits = 2) {
  return typeof v === 'number' && Number.isFinite(v) ? v.toFixed(digits) : '—'
}

function pct(v: unknown, digits = 1) {
  return typeof v === 'number' && Number.isFinite(v) ? `${(v * 100).toFixed(digits)}%` : '—'
}

function yearsAgo(years: number) {
  const d = new Date()
  d.setFullYear(d.getFullYear() - years)
  return d.toISOString().slice(0, 10)
}

export function WorkflowPanel({ kind, extraConfig, hint }: {
  kind: WorkflowKind
  /** 页面自己的账户事实(费率/初始资金/撮合口径等), 原样透传给后端, AI 碰不到 */
  extraConfig?: Record<string, unknown>
  hint?: string
}) {
  const queryClient = useQueryClient()
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState({
    start: yearsAgo(5),
    end: new Date().toISOString().slice(0, 10),
    maxAttempts: 12,
    roundsPerAttempt: 6,
    maxHours: 6,
    profile: 'balanced' as 'balanced' | 'strict',
  })

  const list = useQuery({
    queryKey: QK.workflows(kind),
    queryFn: () => api.workflowList(kind),
    refetchInterval: q => {
      const items = (q.state.data as { items: Workflow[] } | undefined)?.items ?? []
      return items.some(w => w.status === 'running') ? LIVE_POLL_MS : false
    },
  })
  const items = list.data?.items ?? []
  const active = items[0]
  const running = active?.status === 'running'

  const refresh = () => queryClient.invalidateQueries({ queryKey: QK.workflows(kind) })

  const create = useMutation({
    mutationFn: () => api.workflowCreate({
      kind,
      config: {
        ...(extraConfig ?? {}),
        start: form.start,
        end: form.end,
        ...(kind === 'mining' ? { budget_profile: form.profile, holdout_days: 365 } : {}),
      },
      max_attempts: form.maxAttempts,
      rounds_per_attempt: form.roundsPerAttempt,
      max_hours: form.maxHours,
    }),
    onSuccess: () => { refresh(); setOpen(false); toast('工作流开跑了 —— 可以关页面, 它在服务端自己跑', 'success') },
    onError: e => toast(String((e as Error).message || e), 'error'),
  })

  const stop = useMutation({
    mutationFn: (id: string) => api.workflowStop(id),
    onSuccess: () => { refresh(); toast('已中止', 'success') },
    onError: e => toast(String((e as Error).message || e), 'error'),
  })

  const tick = useMutation({
    mutationFn: (id: string) => api.workflowTick(id),
    onSuccess: () => refresh(),
    onError: e => toast(String((e as Error).message || e), 'error'),
  })

  // [R55] 删历史。跑着的后端会 409 —— 界面也不给按, 免得点了才知道不行
  const remove = useMutation({
    mutationFn: (id: string) => api.workflowDelete(id),
    onSuccess: () => { refresh(); toast('已删除', 'success') },
    onError: e => toast(String((e as Error).message || e), 'error'),
  })
  const onDelete = (wf: Workflow) => {
    if (window.confirm(`删掉这条工作流记录？\n${wf.progress_text}\n跑出来的候选方案不受影响, 删的只是这条运行记录。`)) {
      remove.mutate(wf.workflow_id)
    }
  }

  return (
    <section className="rounded-card border border-border bg-surface">
      <header className="flex flex-wrap items-center gap-x-2 gap-y-1.5 border-b border-border px-3 py-2">
        <WorkflowIcon className="h-3.5 w-3.5 shrink-0 text-accent" />
        <h2 className="shrink-0 text-xs font-semibold text-foreground">工作流</h2>
        <span className="text-[9px] text-muted">
          {hint ?? '开了就不用管 —— 服务端自己跑, 关页面照跑, 一次不成换配置再来一次'}
        </span>
        {active && (
          <span className={`ml-auto shrink-0 rounded-btn px-2 py-px text-[10px] font-medium ${STATUS_CLS[active.status]}`}>
            {STATUS_LABEL[active.status]} · {active.progress_text}
          </span>
        )}
      </header>

      <div className="flex flex-wrap items-center gap-2 border-b border-border px-3 py-2">
        {!running && (
          <button type="button" onClick={() => setOpen(v => !v)}
            className="inline-flex h-8 items-center gap-1.5 rounded-btn bg-accent px-3 text-xs font-semibold text-white transition-opacity hover:opacity-90">
            <Play className="h-3.5 w-3.5" />
            {open ? '收起' : '开一个工作流'}
          </button>
        )}
        {running && (
          <>
            <button type="button" disabled={tick.isPending}
              onClick={() => tick.mutate(active.workflow_id)}
              title="后台每 20 秒自己推一格; 这里是想立刻看它动一下"
              className="inline-flex h-8 items-center gap-1.5 rounded-btn border border-border px-3 text-xs text-secondary transition-colors hover:border-accent/40 hover:text-accent disabled:opacity-50">
              {tick.isPending ? <LoaderCircle className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />}
              催一格
            </button>
            <button type="button" disabled={stop.isPending}
              onClick={() => {
                if (window.confirm('确定中止这个工作流？已经跑完的轮次会保留。')) stop.mutate(active.workflow_id)
              }}
              className="inline-flex h-8 items-center gap-1.5 rounded-btn border border-danger/40 px-3 text-xs text-danger transition-colors hover:bg-danger/10 disabled:opacity-50">
              <Square className="h-3.5 w-3.5" />
              中止
            </button>
          </>
        )}
      </div>

      {open && !running && (
        <div className="border-b border-border px-3 py-2.5">
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
            <label><span className={LABEL}>开始</span>
              <input type="date" className={INPUT} value={form.start}
                onChange={e => setForm({ ...form, start: e.target.value })} /></label>
            <label><span className={LABEL}>结束</span>
              <input type="date" className={INPUT} value={form.end}
                onChange={e => setForm({ ...form, end: e.target.value })} /></label>
            {kind === 'mining' && (
              <label><span className={LABEL}>档位</span>
                <select className={INPUT} value={form.profile}
                  onChange={e => setForm({ ...form, profile: e.target.value as 'balanced' | 'strict' })}>
                  <option value="balanced">均衡</option>
                  <option value="strict">严格</option>
                </select></label>
            )}
            <label>
              <span className={LABEL} title="一次跑不出达标结果就换一批配置重来, 这是最多重来几次">
                最多重开几次
              </span>
              <input type="number" min={1} max={100} className={INPUT} value={form.maxAttempts}
                onChange={e => setForm({ ...form, maxAttempts: Number(e.target.value) })} /></label>
            <label>
              <span className={LABEL} title="每次重开内部最多让 AI 调几轮">每次最多几轮</span>
              <input type="number" min={1} max={20} className={INPUT} value={form.roundsPerAttempt}
                onChange={e => setForm({ ...form, roundsPerAttempt: Number(e.target.value) })} /></label>
            <label>
              <span className={LABEL} title="到点无论跑到哪一步都收工">最多跑多久(小时)</span>
              <input type="number" min={0.5} max={72} step={0.5} className={INPUT} value={form.maxHours}
                onChange={e => setForm({ ...form, maxHours: Number(e.target.value) })} /></label>
          </div>
          <button type="button" disabled={create.isPending} onClick={() => create.mutate()}
            className="mt-2.5 inline-flex h-8 items-center gap-1.5 rounded-btn bg-accent px-3 text-xs font-semibold text-white transition-opacity hover:opacity-90 disabled:opacity-50">
            {create.isPending ? <LoaderCircle className="h-3.5 w-3.5 animate-spin" /> : <Rocket className="h-3.5 w-3.5" />}
            开跑
          </button>
        </div>
      )}

      {!active ? (
        <div className="px-3 py-6 text-center text-[11px] text-muted">
          还没开过工作流 —— 点上面「开一个工作流」，设好预算就不用再管了。
        </div>
      ) : (
        <WorkflowCard wf={active} onDelete={onDelete} deleting={remove.isPending} />
      )}

      {items.length > 1 && (
        <details className="border-t border-border">
          <summary className="cursor-pointer px-3 py-2 text-[10px] text-muted hover:text-secondary">
            以前的 {items.length - 1} 个工作流
          </summary>
          {items.slice(1).map(w => (
            <WorkflowCard key={w.workflow_id} wf={w} compact onDelete={onDelete} deleting={remove.isPending} />
          ))}
        </details>
      )}
    </section>
  )
}

function WorkflowCard({ wf, compact = false, onDelete, deleting }: {
  wf: Workflow; compact?: boolean
  onDelete?: (wf: Workflow) => void
  deleting?: boolean
}) {
  const [open, setOpen] = useState(false)
  const best = wf.best
  const running = wf.status === 'running'
  return (
    <div className="border-t border-border/60 first:border-t-0">
      <div className="px-3 py-2.5">
        <div className="flex flex-wrap items-center gap-2">
          {wf.status === 'running' && <LoaderCircle className="h-3 w-3 shrink-0 animate-spin text-accent" />}
          <span className={`shrink-0 rounded-btn px-2 py-px text-[10px] font-medium ${STATUS_CLS[wf.status]}`}>
            {STATUS_LABEL[wf.status]}
          </span>
          <span className="font-mono text-[10px] text-muted">{wf.progress_text}</span>
          {compact && <span className="font-mono text-[9px] text-muted">{wf.created_at.slice(0, 16).replace('T', ' ')}</span>}
          {onDelete && (
            <button type="button" disabled={running || deleting}
              onClick={() => onDelete(wf)}
              title={running ? '还在跑 —— 先中止再删' : '删掉这条运行记录(候选方案不受影响)'}
              className="ml-auto inline-flex h-6 shrink-0 items-center gap-1 rounded-btn border border-border px-1.5 text-[10px] text-muted transition-colors hover:border-danger/40 hover:text-danger disabled:cursor-not-allowed disabled:opacity-40">
              <Trash2 className="h-3 w-3" />删除
            </button>
          )}
        </div>

        {/* 最好的一次成绩。达标与否用颜色分开 —— 这是唯一需要一眼看到的东西 */}
        {best ? (
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <Rocket className={`h-3.5 w-3.5 shrink-0 ${best.passed ? 'text-success' : 'text-muted'}`} />
            <span className="text-xs font-semibold text-foreground">{best.label}</span>
            <span className={`rounded-btn px-1.5 py-px text-[9px] font-medium ${
              best.passed ? 'bg-success/10 text-success' : 'bg-warning/10 text-warning'}`}>
              {best.passed ? '达标' : '未达标'}
            </span>
            <span className="font-mono text-[10px] text-muted">
              Sharpe {num(best.sharpe)}
              {best.detail?.['最大回撤'] != null && ` · 回撤 ${pct(best.detail['最大回撤'])}`}
              {best.detail?.['总收益'] != null && ` · 总收益 ${pct(best.detail['总收益'])}`}
              {best.detail?.['交易数'] != null && ` · 成交 ${String(best.detail['交易数'])} 笔`}
              {best.detail?.['成交笔数'] != null && ` · 成交 ${String(best.detail['成交笔数'])} 笔`}
            </span>
          </div>
        ) : (
          <p className="mt-2 text-[10px] text-muted">还没有成绩 —— 第一轮跑完才有。</p>
        )}

        {/* 抽卡账本: 试了多少次, 这个数字该怎么看 */}
        {wf.overfit_note && (
          <p className="mt-2 flex gap-1.5 text-[10px] leading-4 text-warning">
            <Info className="mt-px h-3 w-3 shrink-0" />
            {wf.overfit_note}
          </p>
        )}
        {wf.ledger.last_error && wf.status === 'running' && (
          <p className="mt-1.5 flex gap-1.5 text-[10px] leading-4 text-danger">
            <AlertTriangle className="mt-px h-3 w-3 shrink-0" />
            上一格出错({wf.ledger.errors_in_a_row}/3)：{wf.ledger.last_error}
          </p>
        )}

        {wf.attempts.length > 0 && (
          <button type="button" onClick={() => setOpen(v => !v)}
            className="mt-2 inline-flex items-center gap-1 text-[10px] text-muted hover:text-secondary">
            <ChevronDown className={`h-3 w-3 transition-transform ${open ? '' : '-rotate-90'}`} />
            每次重开的结果({wf.attempts.length})
          </button>
        )}
      </div>

      {open && (
        <div className="space-y-1 border-t border-border/60 bg-base/40 px-3 py-2">
          {wf.attempts.map((a, i) => (
            <div key={i} className="flex flex-wrap items-baseline gap-2 text-[10px]">
              <span className="font-semibold text-foreground">第 {a.attempt ?? i + 1} 次</span>
              <span className="text-secondary">{a.outcome}</span>
              {a.rounds != null && <span className="font-mono text-muted">{a.rounds} 轮</span>}
              {a.conclusion && <span className="min-w-0 flex-1 text-accent/90">{a.conclusion}</span>}
              {a.message && <span className="min-w-0 flex-1 text-muted">{a.message}</span>}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
