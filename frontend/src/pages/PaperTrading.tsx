/**
 * [R59] AI 操盘手 —— 让模型只用这套系统给的信息模拟炒股。
 *
 * 目的不是"让 AI 帮我赚钱", 而是拿它当**系统的体检**: 一个模型只拿本系统给出
 * 的信息, 长期能不能跑出正收益。跑不出来, 差在哪一块就是下一步该改的地方。
 * 所以每一笔都留着理由 —— 那份记录才是这个功能真正的产出。
 *
 * 界面上刻意不做「所有人持仓一览」: 那样我看完再去调提示词, 就把操作员之间的
 * 隔离破坏掉了。列表只给成绩, 明细要点进某一个人才看得到。
 */
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Bot, Clock, Eye, Loader2, Play, Plus, RotateCcw, ShieldAlert, Trash2, TrendingUp, X,
} from 'lucide-react'
import {
  api, type PaperBook, type PaperOrder, type PaperScope, type PaperTrader,
} from '@/lib/api'
import { PageHeader } from '@/components/PageHeader'
import { toast } from '@/components/Toast'

const INPUT = 'h-8 w-full rounded-input border border-border bg-surface px-2 text-xs text-foreground outline-none transition-colors focus:border-accent'

function pct(v: number | null | undefined, digits = 2): string {
  return v == null ? '—' : `${v > 0 ? '+' : ''}${(v * 100).toFixed(digits)}%`
}
function money(v: number | null | undefined): string {
  return v == null ? '—' : v.toLocaleString('zh-CN', { maximumFractionDigits: 0 })
}
// A股习惯: 涨红跌绿
function pnlCls(v: number | null | undefined): string {
  if (v == null || v === 0) return 'text-muted'
  return v > 0 ? 'text-red-400' : 'text-emerald-400'
}

export function PaperTrading() {
  const qc = useQueryClient()
  const [openId, setOpenId] = useState<{ id: string; scope: PaperScope } | null>(null)
  const [adding, setAdding] = useState(false)

  const q = useQuery({ queryKey: ['paper-traders'], queryFn: () => api.paperTraders(), refetchInterval: 30_000 })
  const traders = q.data?.traders ?? []
  const refresh = () => qc.invalidateQueries({ queryKey: ['paper-traders'] })

  const run = useMutation({
    mutationFn: (v: { id: string; scope: PaperScope }) => api.paperBookRun(v.id, v.scope),
    onSuccess: res => {
      refresh()
      qc.invalidateQueries({ queryKey: ['paper-book'] })
      const filled = res.orders.filter(o => !o.rejected).length
      const rejected = res.orders.length - filled
      toast(res.orders.length === 0
        ? `${res.date} 今天不动 —— ${res.note || '没给理由'}`
        : `${res.date} 成交 ${filled} 笔${rejected ? `, 被拒 ${rejected} 笔` : ''}`, 'success')
    },
    onError: e => { refresh(); toast(String((e as Error).message || e), 'error') },
  })

  // [R61] 生命线检查: 不问 AI, 也是全流程唯一用实时价的地方
  const lifeline = useMutation({
    mutationFn: (v: { id: string; scope: PaperScope }) => api.paperBookLifeline(v.id, v.scope),
    onSuccess: res => {
      refresh()
      qc.invalidateQueries({ queryKey: ['paper-book'] })
      toast(res.count === 0 ? '没有持仓跌破生命线' : `按纪律清掉 ${res.count} 只`, 'success')
    },
    onError: e => toast(String((e as Error).message || e), 'error'),
  })

  return (
    <div className="flex min-h-full flex-col bg-base">
      <PageHeader
        title="AI 操盘手"
        subtitle={<span className="hidden md:inline">让模型只用本系统的信息模拟交易 · 长期看这套信息够不够用</span>}
        className="shrink-0 bg-base/95 px-3 lg:px-5"
        right={(
          <button type="button" onClick={() => setAdding(true)}
            className="inline-flex h-8 items-center gap-1.5 rounded-btn border border-border bg-surface px-2.5 text-xs text-secondary transition-colors hover:border-accent/40 hover:text-accent">
            <Plus className="h-3.5 w-3.5" />加操作员
          </button>
        )}
      />

      <main className="min-h-0 flex-1 space-y-3 overflow-auto px-3 pb-4 pt-3 lg:px-4">
        <section className="rounded-card border border-border bg-surface px-3 py-2.5 text-[11px] leading-5 text-secondary">
          <div className="mb-1 flex items-center gap-1.5">
            <Bot className="h-3.5 w-3.5 text-accent" />
            <span className="text-xs font-semibold text-foreground">这个页面是拿来体检的, 不是拿来赚钱的</span>
          </div>
          每个操作员就是一个模型, 每天拿<span className="text-foreground">同一份</span>本系统的信息独立做决定。
          每人带<span className="text-foreground">两本独立的账</span>——
          「全市场」只能从全市场候选里选, 「我的自选」只能从我圈的票里选。
          <span className="text-muted"> 这两条曲线的差, 就是我这份自选到底有没有价值。</span>
          <br />
          <span className="text-muted">它们没有联网能力(只拿到一段服务端拼好的文本, 没有工具),
          也互相看不见对方的持仓和理由 —— 上下文是按人按账组装的, 不是靠提示词叮嘱。
          全程走<span className="text-secondary">收盘口径</span>;
          唯一的例外是<span className="text-secondary">跌破生命线</span>——
          那是硬纪律, 不问 AI, 允许用实时价立刻清掉。
          撮合按 A 股规矩: 100 股一手、T+1 当天买的不能卖、算佣金印花税滑点。</span>
          <br />
          <span className="text-muted">跑一段时间后, 谁做得好不重要 —— 重要的是看它们
          <span className="text-secondary">因为缺什么信息而做错</span>, 那就是系统下一步该补的。</span>
        </section>

        {q.isLoading && (
          <div className="flex items-center justify-center gap-2 py-16 text-xs text-muted">
            <Loader2 className="h-4 w-4 animate-spin" />加载中…
          </div>
        )}

        {!q.isLoading && traders.length === 0 && (
          <div className="rounded-card border border-border bg-surface px-4 py-14 text-center text-xs text-muted">
            还没有操作员 —— 点右上角「加操作员」。<br />
            <span className="text-muted/70">配两个以上不同的模型才有比较的意义。模型在 设置 → AI 里配。</span>
          </div>
        )}

        {traders.length > 0 && (
          <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
            {traders.map(t => (
              <TraderCard key={t.id} t={t}
                runningScope={run.isPending && run.variables?.id === t.id ? run.variables.scope : null}
                onRun={sc => run.mutate({ id: t.id, scope: sc })}
                onLifeline={sc => lifeline.mutate({ id: t.id, scope: sc })}
                onOpen={sc => setOpenId({ id: t.id, scope: sc })}
                onChanged={refresh} />
            ))}
          </div>
        )}
      </main>

      {adding && <AddTrader onClose={() => setAdding(false)} onDone={() => { setAdding(false); refresh() }} />}
      {openId && <BookDetail id={openId.id} scope={openId.scope} onClose={() => setOpenId(null)} />}
    </div>
  )
}

function TraderCard({ t, runningScope, onRun, onLifeline, onOpen, onChanged }: {
  t: PaperTrader
  runningScope: PaperScope | null
  onRun: (scope: PaperScope) => void
  onLifeline: (scope: PaperScope) => void
  onOpen: (scope: PaperScope) => void
  onChanged: () => void
}) {
  const remove = useMutation({
    mutationFn: () => api.paperTraderDelete(t.id),
    onSuccess: () => { onChanged(); toast('已删除', 'success') },
    onError: e => toast(String((e as Error).message || e), 'error'),
  })
  const setSched = useMutation({
    mutationFn: (v: { enabled: boolean; hour: number; minute: number }) =>
      api.paperTraderSchedule(t.id, v),
    onSuccess: r => {
      onChanged()
      toast(r.schedule.enabled
        ? `已开启定时 —— 每个交易日 ${String(r.schedule.hour).padStart(2, '0')}:${String(r.schedule.minute).padStart(2, '0')}`
        : '已关闭定时', 'success')
    },
    onError: e => toast(String((e as Error).message || e), 'error'),
  })
  const sched = t.schedule

  return (
    <section className="flex flex-col rounded-card border border-border bg-surface">
      <header className="flex flex-wrap items-center gap-2 border-b border-border px-3 py-2">
        <Bot className="h-3.5 w-3.5 shrink-0 text-accent" />
        <span className="min-w-0 flex-1 truncate text-xs font-semibold text-foreground">{t.name}</span>
        <span className="shrink-0 text-[10px] text-muted">本金 {money(t.initial_capital)}</span>
        <button type="button" disabled={remove.isPending}
          onClick={() => { if (window.confirm(`删掉操作员 ${t.name}？\n两本账的全部历史会一起删掉, 拿不回来。`)) remove.mutate() }}
          title="删掉这个操作员及其两本账的全部历史"
          className="shrink-0 p-1 text-muted transition-colors hover:text-danger">
          <Trash2 className="h-3.5 w-3.5" />
        </button>
      </header>

      {/* [R61] 定时: 收盘后自己跑。长期观察靠人记得点按钮是不成立的 ——
          漏几天就是净值曲线上几个说不清的缺口。 */}
      <div className="flex flex-wrap items-center gap-2 border-b border-border/60 bg-elevated/20 px-3 py-1.5">
        <Clock className="h-3 w-3 shrink-0 text-muted" />
        <label className="flex shrink-0 items-center gap-1 text-[10px] text-secondary">
          <input type="checkbox" className="h-3 w-3 accent-accent" checked={sched.enabled}
            disabled={setSched.isPending}
            onChange={e => setSched.mutate({ ...sched, enabled: e.target.checked })} />
          每个交易日自动跑
        </label>
        <input type="time" disabled={setSched.isPending}
          value={`${String(sched.hour).padStart(2, '0')}:${String(sched.minute).padStart(2, '0')}`}
          onChange={e => {
            const [h, m] = e.target.value.split(':').map(Number)
            if (Number.isFinite(h) && Number.isFinite(m)) setSched.mutate({ ...sched, hour: h, minute: m })
          }}
          className="h-6 rounded-input border border-border bg-surface px-1.5 text-[10px] text-foreground outline-none focus:border-accent" />
        <span className="text-[10px] text-muted">
          建议收盘后 —— 收盘价出来了才有得算。到点会先查生命线, 再让两本账各决策一次。
        </span>
      </div>

      {/* 两本账并排 —— 这两条曲线的差就是"我这份自选有没有价值" */}
      <div className="grid grid-cols-1 divide-y divide-border/60 sm:grid-cols-2 sm:divide-x sm:divide-y-0">
        {t.books.map(b => (
          <BookPane key={b.scope} b={b}
            busy={runningScope === b.scope}
            onRun={() => onRun(b.scope)}
            onLifeline={() => onLifeline(b.scope)}
            onOpen={() => onOpen(b.scope)}
            onReset={() => {
              if (window.confirm(`把「${b.scope_cn}」这本账重置到起跑线？\n只影响这一本, 另一本不动。`)) {
                api.paperTraderReset(t.id, b.scope).then(() => { onChanged(); toast('已重置', 'success') })
                  .catch(e => toast(String((e as Error).message || e), 'error'))
              }
            }} />
        ))}
      </div>
    </section>
  )
}

function BookPane({ b, busy, onRun, onLifeline, onOpen, onReset }: {
  b: PaperBook; busy: boolean
  onRun: () => void; onLifeline: () => void; onOpen: () => void; onReset: () => void
}) {
  return (
    <div className="flex min-w-0 flex-col px-3 py-2.5">
      <div className="mb-2 flex items-center gap-2">
        <button onClick={onOpen} className="shrink-0 text-[11px] font-medium text-foreground hover:text-accent">
          {b.scope_cn}
        </button>
        <span className={`ml-auto shrink-0 font-mono text-sm font-bold ${pnlCls(b.return_pct)}`}>
          {pct(b.return_pct)}
        </span>
      </div>

      <div className="grid grid-cols-3 gap-1.5 text-center">
        <div>
          <div className="text-[9px] text-muted">总资产</div>
          <div className="mt-0.5 font-mono text-[11px] text-foreground">{money(b.nav)}</div>
        </div>
        <div>
          <div className="text-[9px] text-muted">持仓/现金</div>
          <div className="mt-0.5 font-mono text-[11px] text-foreground">{b.positions_count} / {money(b.cash)}</div>
        </div>
        <div>
          <div className="text-[9px] text-muted">交易/天数</div>
          <div className="mt-0.5 font-mono text-[11px] text-foreground">{b.orders_count} / {b.days}</div>
        </div>
      </div>

      {b.last_note && (
        <div className="mt-2 rounded border border-border/60 bg-elevated/30 px-2 py-1 text-[10px] leading-4 text-secondary">
          上次想法: {b.last_note}
        </div>
      )}
      {b.last_error && (
        <div className="mt-2 rounded border border-danger/40 bg-danger/[0.06] px-2 py-1 text-[10px] leading-4 text-danger">
          上次没跑成: {b.last_error}
        </div>
      )}

      <div className="mt-auto flex items-center gap-1 pt-2">
        <button type="button" disabled={busy} onClick={onRun}
          title="按今天的信息做一次决策(调用这个操作员绑定的模型)"
          className="inline-flex h-7 items-center gap-1 rounded-btn bg-accent px-2 text-[10px] font-medium text-white transition-opacity disabled:opacity-50">
          {busy ? <Loader2 className="h-3 w-3 animate-spin" /> : <Play className="h-3 w-3" />}
          跑一次
        </button>
        <button type="button" onClick={onLifeline}
          title="查一遍持仓有没有跌破生命线(20日线)。这一路不问 AI —— 硬纪律, 也是全流程唯一用实时价的地方"
          className="inline-flex h-7 items-center gap-1 rounded-btn border border-amber-400/40 px-2 text-[10px] text-amber-400 transition-colors hover:bg-amber-400/10">
          <ShieldAlert className="h-3 w-3" />查生命线
        </button>
        <button type="button" onClick={onOpen}
          className="inline-flex h-7 items-center gap-1 rounded-btn border border-border px-2 text-[10px] text-secondary transition-colors hover:border-accent/40 hover:text-accent">
          <TrendingUp className="h-3 w-3" />明细
        </button>
        <button type="button" onClick={onReset} title="把这一本账重置到起跑线(另一本不动)"
          className="ml-auto p-1 text-muted transition-colors hover:text-amber-400">
          <RotateCcw className="h-3.5 w-3.5" />
        </button>
      </div>
    </div>
  )
}

function AddTrader({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const profiles = useQuery({ queryKey: ['ai-profiles'], queryFn: () => api.aiProfiles() })
  const rows = profiles.data?.profiles ?? []
  const [profileId, setProfileId] = useState('')
  const [name, setName] = useState('')
  const [capital, setCapital] = useState(1_000_000)

  const create = useMutation({
    mutationFn: () => api.paperTraderCreate({ name, profile_id: profileId, capital }),
    onSuccess: () => { onDone(); toast('操作员已就位, 点「跑一次」开始', 'success') },
    onError: e => toast(String((e as Error).message || e), 'error'),
  })

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm" onClick={onClose}>
      <div role="dialog" aria-modal="true" className="w-full max-w-md rounded-lg border border-border bg-surface shadow-2xl"
        onClick={e => e.stopPropagation()}>
        <header className="flex items-center justify-between border-b border-border px-4 py-3">
          <span className="text-sm font-medium text-foreground">加一个操作员</span>
          <button onClick={onClose} className="text-muted hover:text-foreground"><X className="h-4 w-4" /></button>
        </header>
        <div className="space-y-3 px-4 py-3">
          <label className="block">
            <span className="mb-1 block text-[10px] font-medium text-secondary">用哪个模型</span>
            <select className={INPUT} value={profileId}
              onChange={e => {
                setProfileId(e.target.value)
                const p = rows.find(x => x.id === e.target.value)
                // 名字默认就是模型名 —— 这张表比的是模型, 名字里带别的会看走眼
                if (p && !name) setName(p.model || p.label || '')
              }}>
              <option value="">选一个已配置的 AI 档位…</option>
              {rows.map(p => (
                <option key={p.id} value={p.id}>{p.label ? `${p.label} · ` : ''}{p.model}</option>
              ))}
            </select>
            {rows.length === 0 && (
              <span className="mt-1 block text-[10px] text-amber-400">还没配过 AI —— 先去 设置 → AI 配一个档位。</span>
            )}
          </label>
          <label className="block">
            <span className="mb-1 block text-[10px] font-medium text-secondary">
              操作员名字 <span className="text-muted">(默认就是模型名, 建议别改)</span>
            </span>
            <input className={INPUT} value={name} onChange={e => setName(e.target.value)} placeholder="如 deepseek-v4-pro" />
          </label>
          <label className="block">
            <span className="mb-1 block text-[10px] font-medium text-secondary">初始资金</span>
            <input className={INPUT} type="number" min={10000} step={10000}
              value={capital} onChange={e => setCapital(Number(e.target.value))} />
            <span className="mt-1 block text-[10px] text-muted">
              想互相比较的话, 几个操作员要用同一个数 —— 本金不同, 收益率也就不可比。
            </span>
          </label>
        </div>
        <div className="flex justify-end gap-2 border-t border-border px-4 py-3">
          <button onClick={onClose} className="h-8 rounded-btn border border-border px-3 text-xs text-secondary">取消</button>
          <button disabled={!profileId || create.isPending} onClick={() => create.mutate()}
            className="inline-flex h-8 items-center gap-1.5 rounded-btn bg-accent px-3 text-xs font-medium text-white disabled:opacity-50">
            {create.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}加上
          </button>
        </div>
      </div>
    </div>
  )
}

function BookDetail({ id, scope, onClose }: {
  id: string; scope: PaperScope; onClose: () => void
}) {
  const [tab, setTab] = useState<'orders' | 'positions' | 'context'>('orders')
  const q = useQuery({ queryKey: ['paper-book', id, scope], queryFn: () => api.paperBook(id, scope) })
  const ctx = useQuery({
    queryKey: ['paper-book-context', id, scope],
    queryFn: () => api.paperBookContext(id, scope),
    enabled: tab === 'context',
  })
  const d = q.data

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm" onClick={onClose}>
      <div role="dialog" aria-modal="true"
        className="flex max-h-[88vh] w-full max-w-4xl flex-col overflow-hidden rounded-lg border border-border bg-surface shadow-2xl"
        onClick={e => e.stopPropagation()}>
        <header className="flex items-center gap-2.5 border-b border-border px-4 py-3">
          <Bot className="h-4 w-4 shrink-0 text-accent" />
          <span className="shrink-0 text-sm font-medium text-foreground">{d?.name ?? '…'}</span>
          {d && (
            <>
              <span className="shrink-0 rounded border border-border/60 bg-elevated/40 px-1.5 py-0.5 text-[10px] text-secondary">
                {d.scope_cn}
              </span>
              <span className="truncate text-[10px] text-muted">
                总资产 {money(d.nav)} · 收益 <span className={pnlCls(d.return_pct)}>{pct(d.return_pct)}</span> ·
                {' '}{d.orders_count} 笔 · {d.days} 天
              </span>
            </>
          )}
          <div className="ml-auto flex shrink-0 items-center gap-2">
            <div className="flex overflow-hidden rounded-btn border border-border/60">
              {([['orders', '操作记录'], ['positions', '持仓'], ['context', '它看到了什么']] as const).map(([k, label]) => (
                <button key={k} onClick={() => setTab(k)}
                  className={`px-2.5 py-1 text-[10px] transition-colors ${tab === k ? 'bg-accent/15 text-accent' : 'text-muted hover:text-foreground'}`}>
                  {label}
                </button>
              ))}
            </div>
            <button onClick={onClose} className="text-muted hover:text-foreground"><X className="h-4 w-4" /></button>
          </div>
        </header>

        {q.isLoading && (
          <div className="flex items-center justify-center gap-2 py-16 text-xs text-muted">
            <Loader2 className="h-4 w-4 animate-spin" />加载中…
          </div>
        )}

        {d && tab === 'orders' && (
          <div className="overflow-auto">
            <table className="w-full text-xs">
              <thead className="sticky top-0 z-10 bg-surface">
                <tr className="border-b border-border/60 text-[10px] text-muted">
                  <th className="whitespace-nowrap px-3 py-2 text-left font-normal">日期</th>
                  <th className="whitespace-nowrap px-2 py-2 text-left font-normal">操作</th>
                  <th className="whitespace-nowrap px-2 py-2 text-right font-normal">股数 @ 价</th>
                  <th className="px-3 py-2 text-left font-normal">为什么</th>
                </tr>
              </thead>
              <tbody>
                {d.orders.map((o: PaperOrder, i: number) => <OrderRow key={`${o.ts}-${i}`} o={o} />)}
                {d.orders.length === 0 && (
                  <tr><td colSpan={4} className="px-3 py-12 text-center text-[11px] text-muted">还没有操作过 —— 点卡片上的「跑一次」</td></tr>
                )}
              </tbody>
            </table>
          </div>
        )}

        {d && tab === 'positions' && (
          <div className="overflow-auto">
            <table className="w-full text-xs">
              <thead className="sticky top-0 z-10 bg-surface">
                <tr className="border-b border-border/60 text-[10px] text-muted">
                  <th className="whitespace-nowrap px-3 py-2 text-left font-normal">标的</th>
                  <th className="whitespace-nowrap px-2 py-2 text-right font-normal">股数</th>
                  <th className="whitespace-nowrap px-2 py-2 text-right font-normal">成本 / 现价</th>
                  <th className="whitespace-nowrap px-2 py-2 text-right font-normal">市值</th>
                  <th className="whitespace-nowrap px-2 py-2 text-right font-normal">浮盈</th>
                  <th className="whitespace-nowrap px-3 py-2 text-left font-normal">建仓日</th>
                </tr>
              </thead>
              <tbody>
                {d.positions.map(p => (
                  <tr key={p.symbol} className="border-b border-border/30">
                    <td className="whitespace-nowrap px-3 py-1.5 font-mono text-[11px] text-foreground">{p.symbol}</td>
                    <td className="whitespace-nowrap px-2 py-1.5 text-right font-mono tabular-nums text-secondary">{p.shares}</td>
                    <td className="whitespace-nowrap px-2 py-1.5 text-right font-mono tabular-nums text-secondary">
                      {p.cost.toFixed(2)} / {p.price?.toFixed(2) ?? '—'}
                    </td>
                    <td className="whitespace-nowrap px-2 py-1.5 text-right font-mono tabular-nums text-secondary">{money(p.market_value)}</td>
                    <td className={`whitespace-nowrap px-2 py-1.5 text-right font-mono tabular-nums ${pnlCls(p.pnl_pct)}`}>{pct(p.pnl_pct, 1)}</td>
                    <td className="whitespace-nowrap px-3 py-1.5 font-mono text-[10px] text-muted">{p.opened_on}</td>
                  </tr>
                ))}
                {d.positions.length === 0 && (
                  <tr><td colSpan={6} className="px-3 py-12 text-center text-[11px] text-muted">当前空仓</td></tr>
                )}
              </tbody>
            </table>
          </div>
        )}

        {tab === 'context' && (
          <div className="min-h-0 flex-1 overflow-auto p-4">
            <p className="mb-2 text-[10px] leading-4 text-muted">
              这就是这本账下一次会拿到的<span className="text-secondary">全部</span>信息 —— 没有别的输入, 也没有联网。
              要判断"系统给的信息够不够", 先看清楚给了什么。
              <span className="text-muted/70"> 这里也是核对隔离的地方: 别人的持仓和理由一个字都不该出现。</span>
            </p>
            {ctx.isLoading && <div className="flex items-center gap-2 py-8 text-xs text-muted"><Loader2 className="h-4 w-4 animate-spin" />生成中…</div>}
            {ctx.data && (
              <>
                <div className="mb-2 rounded border border-border/60 bg-elevated/30 p-3">
                  <div className="mb-1 flex items-center gap-1 text-[10px] text-muted"><Eye className="h-3 w-3" />它被告知的规则</div>
                  <pre className="whitespace-pre-wrap break-words font-mono text-[10px] leading-4 text-secondary">{ctx.data.system_prompt}</pre>
                </div>
                <pre className="whitespace-pre-wrap break-words rounded border border-border/60 bg-base/40 p-3 font-mono text-[10px] leading-4 text-secondary">
                  {ctx.data.context}
                </pre>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

function OrderRow({ o }: { o: PaperOrder }) {
  const buy = o.action === 'buy'
  return (
    <tr className={`border-b border-border/30 ${o.rejected ? 'opacity-60' : ''}`}>
      <td className="whitespace-nowrap px-3 py-1.5 font-mono text-[10px] text-muted">{o.date}</td>
      <td className="whitespace-nowrap px-2 py-1.5">
        <span className={`inline-flex whitespace-nowrap rounded border px-1 py-0.5 text-[10px] ${
          o.rejected ? 'border-border bg-base text-muted'
            : buy ? 'border-red-400/40 bg-red-400/10 text-red-400'
              : 'border-emerald-400/40 bg-emerald-400/10 text-emerald-400'}`}>
          {buy ? '买入' : '卖出'}
        </span>
        <span className="ml-1.5 font-mono text-[10px] text-secondary">{o.symbol}</span>
      </td>
      <td className="whitespace-nowrap px-2 py-1.5 text-right font-mono tabular-nums text-secondary">
        {o.rejected ? '—' : `${o.shares} @ ${o.price}`}
      </td>
      <td className="px-3 py-1.5 text-[10px] leading-4 text-muted">
        {/* 被拒的也留着 —— "想买但买不成"和"没想买"是两件事 */}
        {/* [R61] 纪律强平单独标出来: 这一笔不是模型的决定, 混在一起会把
            "它自己止损了"和"系统按纪律替它砍了"记成同一回事 */}
        {o.lifeline && (
          <span className="mr-1 inline-flex whitespace-nowrap rounded border border-amber-400/50 bg-amber-400/10 px-1 text-[9px] text-amber-300">
            纪律强平{o.intraday ? ' · 实时' : ''}
          </span>
        )}
        {o.rejected
          ? <span className="text-amber-400">被拒: {o.rejected}{o.reason ? ` · 原意图: ${o.reason}` : ''}</span>
          : (o.reason || <span className="text-muted/50">(没给理由)</span>)}
      </td>
    </tr>
  )
}
