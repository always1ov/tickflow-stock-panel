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
import { useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Bot, Clock, Eye, Loader2, Play, Plus, RotateCcw, ShieldAlert, Target, Trash2, TrendingUp, X,
} from 'lucide-react'
import {
  api, type PaperBook, type PaperOrder, type PaperScope, type PaperTrader,
} from '@/lib/api'
import { PageHeader } from '@/components/PageHeader'
import { toast } from '@/components/Toast'
import { QK } from '@/lib/queryKeys'
// [R171] 交易计划: 三条线 / 出场归因标 / 出场分布
import { ExitStatsBar, ExitTag, PlanCell } from '@/components/paper/PlanCells'

const INPUT = 'h-8 w-full rounded-input border border-border bg-surface px-2 text-xs text-foreground outline-none transition-colors focus:border-accent'

/**
 * [R68] 输入框改动先在本地生效, 停手一会儿再发请求。
 *
 * 起因是个真的会丢数据的 bug: `<input type="time">` 打一个时间会分好几次
 * onChange(时段一次、分段一次), 每次都发一个 PUT —— 服务端同时几个请求在写
 * 同一个账本文件, 写坏了就有操作员凭空消失。服务端那边已经上锁 + 原子落盘,
 * 这里再把"一次修改就发一个请求"收掉: 改成 14:30 本来就该是一次保存, 不是四次
 * (中间那几次还会把定时短暂地设到 01:30 这种莫名其妙的时间上)。
 */
function useDebouncedField<T>(remote: T, commit: (v: T) => void, delay = 600) {
  const [local, setLocal] = useState(remote)
  const dirty = useRef(false)
  // commit 每次渲染都是新函数, 放进依赖会让计时器一直被重置, 所以走 ref
  const commitRef = useRef(commit)
  commitRef.current = commit
  // 服务端的值变了(别处改的 / 保存成功后回填)且本地没在编辑, 就跟过去
  useEffect(() => { if (!dirty.current) setLocal(remote) }, [remote])
  useEffect(() => {
    if (!dirty.current) return
    const id = setTimeout(() => { dirty.current = false; commitRef.current(local) }, delay)
    return () => clearTimeout(id)
  }, [local, delay])
  return [local, (v: T) => { dirty.current = true; setLocal(v) }] as const
}

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

// [R170] embedded: 被「仓位中心」当 tab 挂载时为 true, 不画自己的页头。
export function PaperTrading({ embedded = false }: { embedded?: boolean } = {}) {
  const qc = useQueryClient()
  const [openId, setOpenId] = useState<{ id: string; scope: PaperScope } | null>(null)
  const [adding, setAdding] = useState(false)

  const q = useQuery({ queryKey: QK.paperTraders, queryFn: () => api.paperTraders(), refetchInterval: 30_000 })
  const traders = q.data?.traders ?? []
  const refresh = () => qc.invalidateQueries({ queryKey: QK.paperTraders })

  const run = useMutation({
    mutationFn: (v: { id: string; scope: PaperScope }) => api.paperBookRun(v.id, v.scope),
    onSuccess: res => {
      refresh()
      qc.invalidateQueries({ queryKey: QK.paperBooksAll })
      const filled = res.orders.filter(o => !o.rejected).length
      const rejected = res.orders.length - filled
      const looked = res.focus?.length ? ` · 细看了 ${res.focus.length} 只` : ''
      const redone = res.refreshed?.filter(r => r.ok).length
      const fresh = redone ? ` · 重出了 ${redone} 个信号` : ''
      toast(res.orders.length === 0
        ? `${res.date} 今天不动${looked}${fresh} —— ${res.note || '没给理由'}`
        : `${res.date} 成交 ${filled} 笔${rejected ? `, 被拒 ${rejected} 笔` : ''}${looked}${fresh}`, 'success')
    },
    onError: e => { refresh(); toast(String((e as Error).message || e), 'error') },
  })

  // [R61] 生命线检查: 不问 AI, 也是全流程唯一用实时价的地方
  const lifeline = useMutation({
    mutationFn: (v: { id: string; scope: PaperScope }) => api.paperBookLifeline(v.id, v.scope),
    onSuccess: res => {
      refresh()
      qc.invalidateQueries({ queryKey: QK.paperBooksAll })
      toast(res.count === 0 ? '没有持仓跌破生命线' : `按纪律清掉 ${res.count} 只`, 'success')
    },
    onError: e => toast(String((e as Error).message || e), 'error'),
  })

  // [R171] 交易计划检查: 与生命线成对, 同样不问 AI。
  // 那条是系统定的纪律(跌破 20 日线), 这条是模型买入那一刻自己立的 ——
  // 止损/到期硬执行, 止盈只记提醒。
  const planCheck = useMutation({
    mutationFn: (v: { id: string; scope: PaperScope }) => api.paperPlanCheck(v.id, v.scope),
    onSuccess: res => {
      refresh()
      qc.invalidateQueries({ queryKey: QK.paperBooksAll })
      const bits: string[] = []
      if (res.count) bits.push(`按计划卖出 ${res.count} 只`)
      if (res.reminders.length) bits.push(`${res.reminders.length} 只到止盈线(系统不代劳)`)
      toast(bits.length ? bits.join(' · ') : '没有持仓触到计划的线', 'success')
    },
    onError: e => toast(String((e as Error).message || e), 'error'),
  })

  return (
    <div className="flex min-h-full flex-col bg-base">
      {embedded ? (
        // [R170] 嵌进「仓位中心」时页头归外壳画, 这里只保留「加操作员」按钮,
        // 外加一条常驻横幅 —— 隔壁 tab 是真钱, 这一侧必须一眼看出是模拟盘。
        <div className="flex shrink-0 items-center justify-between gap-3 px-3 pt-2 lg:px-5">
          <span className="inline-flex items-center gap-1.5 rounded border border-amber-400/40 bg-amber-400/10 px-2 py-1 text-[11px] text-amber-400">
            <ShieldAlert className="h-3.5 w-3.5" />
            模拟盘 · 非真实资金, 与「我的批次」互不相干
          </span>
          <button type="button" onClick={() => setAdding(true)}
            className="inline-flex h-8 items-center gap-1.5 rounded-btn border border-border bg-surface px-2.5 text-xs text-secondary transition-colors hover:border-accent/40 hover:text-accent">
            <Plus className="h-3.5 w-3.5" />加操作员
          </button>
        </div>
      ) : (
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
      )}

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
          <span className="text-muted">禁的是<span className="text-secondary">外部信息</span>——
          新闻、公告、研报、行情网站一律不许用, 它们也确实没有联网的手(只拿到服务端拼好的文本, 没有工具)。
          但<span className="text-secondary">系统里的东西全都能用</span>: 先看一轮候选,
          自己挑最多 6 只细看, 服务端把那几只的六态趋势、通道三档与结论、十一类关键价位、
          近月日 K 走势(带涨停/炸板标注)、以及已有的 AI 个股分析一次给全。
          <span className="text-secondary">信号旧了还能让它现场重出</span>——
          AI 信号是缓存的, 会标出多久前生成、过期就提示它 refresh(每次最多 3 只)。
          重出走的是系统默认那条 AI 链, 不是操作员自己的模型 —— 那份信号是系统产物,
          用它自己的模型生成就变成了它的意见, 还会被别的操作员当系统数据读到。
          它们互相看不见对方的持仓和理由 —— 上下文是按人按账组装的, 不是靠提示词叮嘱。
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
                onPlanCheck={sc => planCheck.mutate({ id: t.id, scope: sc })}
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

function TraderCard({ t, runningScope, onRun, onLifeline, onPlanCheck, onOpen, onChanged }: {
  t: PaperTrader
  runningScope: PaperScope | null
  onRun: (scope: PaperScope) => void
  onLifeline: (scope: PaperScope) => void
  onPlanCheck: (scope: PaperScope) => void
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
  const setSettings = useMutation({
    mutationFn: (n: number) => api.paperTraderSettings(t.id, n),
    onSuccess: r => { onChanged(); toast(`同时最多持有 ${r.max_positions} 只`, 'success') },
    onError: e => toast(String((e as Error).message || e), 'error'),
  })
  const sched = t.schedule
  // 停手 0.6 秒才发 —— 打一个时间会触发好几次 onChange, 一次改动只该保存一次
  const [maxPos, setMaxPos] = useDebouncedField(t.max_positions, v => {
    if (Number.isFinite(v) && v >= 1 && v !== t.max_positions) setSettings.mutate(v)
  })
  const [timeText, setTimeText] = useDebouncedField(
    `${String(sched.hour).padStart(2, '0')}:${String(sched.minute).padStart(2, '0')}`,
    v => {
      const [h, m] = v.split(':').map(Number)
      if (!Number.isFinite(h) || !Number.isFinite(m)) return
      if (h === sched.hour && m === sched.minute) return
      setSched.mutate({ ...sched, hour: h, minute: m })
    },
  )

  return (
    <section className="flex flex-col rounded-card border border-border bg-surface">
      <header className="flex flex-wrap items-center gap-2 border-b border-border px-3 py-2">
        <Bot className="h-3.5 w-3.5 shrink-0 text-accent" />
        <span className="min-w-0 flex-1 truncate text-xs font-semibold text-foreground">{t.name}</span>
        {/* [R63] 持仓只数上限对两本账一视同仁 —— 要对照, 这个数就得对齐,
            分开设会让"谁做得好"变成"谁被允许更分散" */}
        <label className="flex shrink-0 items-center gap-1 text-[10px] text-muted"
          title="同时最多持有几只。只挡新开的仓, 已有持仓加仓不受限">
          最多持有
          <input type="number" min={1} max={50}
            value={maxPos}
            onChange={e => setMaxPos(Number(e.target.value))}
            className="h-6 w-12 rounded-input border border-border bg-surface px-1 text-center text-[10px] text-foreground outline-none focus:border-accent" />
          只
        </label>
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
        <input type="time"
          value={timeText}
          onChange={e => setTimeText(e.target.value)}
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
            onPlanCheck={() => onPlanCheck(b.scope)}
            onOpen={() => onOpen(b.scope)}
            onReset={() => {
              if (window.confirm(`把「${b.scope_cn}」这本账重置到起跑线？\n只影响这一本, 另一本不动。本金保持不变。`)) {
                api.paperTraderReset(t.id, b.scope).then(() => { onChanged(); toast('已重置', 'success') })
                  .catch(e => toast(String((e as Error).message || e), 'error'))
              }
            }}
            onCapital={v => {
              if (window.confirm(`把「${b.scope_cn}」的本金改成 ${v.toLocaleString('zh-CN')}？\n这本账会一并重置到起跑线 —— 分母变了, 旧的收益率曲线就读不懂了。`)) {
                api.paperBookCapital(t.id, b.scope, v)
                  .then(() => { onChanged(); toast('本金已改, 这本账已重新起跑', 'success') })
                  .catch(e => toast(String((e as Error).message || e), 'error'))
              } else {
                onChanged()   // 撤销输入框里的改动
              }
            }} />
        ))}
      </div>
    </section>
  )
}

function BookPane({ b, busy, onRun, onLifeline, onPlanCheck, onOpen, onReset, onCapital }: {
  b: PaperBook; busy: boolean
  onRun: () => void; onLifeline: () => void; onPlanCheck: () => void
  onOpen: () => void; onReset: () => void
  onCapital: (v: number) => void
}) {
  return (
    <div className="flex min-w-0 flex-col px-3 py-2.5">
      <div className="mb-2 flex items-center gap-2">
        <button onClick={onOpen} className="shrink-0 text-[11px] font-medium text-foreground hover:text-accent">
          {b.scope_cn}
        </button>
        {/* [R63] 两本账各自的本金。改本金会连带重置这本账 —— 中途换本金而不
            重来的话, 收益率的分母变了但历史成交还在, 那条曲线就再也读不懂了。 */}
        <label className="flex shrink-0 items-center gap-1 text-[10px] text-muted"
          title="这本账的初始资金。改了会把这本账重置到起跑线 —— 分母变了, 旧曲线就读不懂了">
          本金
          <input type="number" min={10000} step={10000} defaultValue={b.initial_capital}
            onBlur={e => {
              const v = Number(e.target.value)
              if (Number.isFinite(v) && v > 0 && v !== b.initial_capital) onCapital(v)
              else e.target.value = String(b.initial_capital)
            }}
            className="h-6 w-24 rounded-input border border-border bg-surface px-1 text-right text-[10px] font-mono text-foreground outline-none focus:border-accent" />
        </label>
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

      {/* [R183] 绩效 —— 参考 MarketPulse 的 Metrics 补的。
          原来只有总资产和交易天数: **没有回撤就不知道过程多难受**, 一条从 +30%
          回撤到 0 的曲线和一条稳稳 +5% 的曲线, 只看总资产是看不出区别的。
          算不出的显示 —— 而不是 0, 0 会被读成"从没回撤过"。 */}
      {b.metrics && (
        <div className="mt-1.5 grid grid-cols-3 gap-1.5 text-center">
          <div title="从净值最高点起最深的一次回撤。样本不足时显示 — 而不是 0">
            <div className="text-[9px] text-muted">最大回撤</div>
            <div className="mt-0.5 font-mono text-[11px] text-bear">
              {b.metrics.max_drawdown != null ? `-${(b.metrics.max_drawdown * 100).toFixed(1)}%` : '—'}
            </div>
          </div>
          <div title="有持仓的交易日占比 —— 空仓躺着不动跑平也不叫本事">
            <div className="text-[9px] text-muted">下场率</div>
            <div className="mt-0.5 font-mono text-[11px] text-foreground">
              {b.metrics.exposure != null ? `${(b.metrics.exposure * 100).toFixed(0)}%` : '—'}
            </div>
          </div>
          <div title="按日夏普, 年化。少于 20 个净值点不给 —— 那个数是噪声">
            <div className="text-[9px] text-muted">夏普</div>
            <div className="mt-0.5 font-mono text-[11px] text-foreground">
              {b.metrics.sharpe != null ? b.metrics.sharpe.toFixed(2) : '—'}
            </div>
          </div>
        </div>
      )}

      {/* [R183] 持仓的批次视图 —— 「我的批次」并进模拟盘之后, 持仓按批次的样子摊开。
          这是**派生**的, 没有写进真的 lots.json(那会派生真实监控规则, 并污染决策台
          管真钱的那几列)。 */}
      {!!b.lots?.length && (
        <div className="mt-2 overflow-x-auto rounded border border-border/50">
          <table className="w-full min-w-[22rem] border-collapse text-[10px]">
            <thead>
              <tr className="border-b border-border/50 text-[9px] text-muted">
                <th className="px-1.5 py-1 text-left font-normal">批次</th>
                <th className="px-1.5 py-1 text-right font-normal">成本</th>
                <th className="px-1.5 py-1 text-right font-normal">数量</th>
                <th className="px-1.5 py-1 text-right font-normal">现价</th>
                <th className="px-1.5 py-1 text-right font-normal">盈亏</th>
              </tr>
            </thead>
            <tbody>
              {b.lots.map(l => (
                <tr key={l.id} className="border-b border-border/25 last:border-0">
                  <td className="whitespace-nowrap px-1.5 py-1 font-mono text-foreground/90"
                      title={l.buy_date ? `建仓 ${l.buy_date}` : undefined}>
                    {l.symbol}
                  </td>
                  <td className="px-1.5 py-1 text-right font-mono text-muted">{l.cost_price.toFixed(2)}</td>
                  <td className="px-1.5 py-1 text-right font-mono text-muted">{l.qty}</td>
                  <td className="px-1.5 py-1 text-right font-mono text-foreground/80">
                    {l.price != null ? l.price.toFixed(2) : '—'}
                  </td>
                  <td className={`px-1.5 py-1 text-right font-mono ${
                    l.pnl_pct == null ? 'text-muted' : l.pnl_pct > 0 ? 'text-bull' : 'text-bear'}`}>
                    {l.pnl_pct != null ? `${(l.pnl_pct * 100).toFixed(1)}%` : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* [R171] 出场归因分布 —— 逼模型先立计划真正的产出。摆在「上次想法」上面
          是有意的: 先看它做成了什么, 再看它当时怎么说的。 */}
      <div className="mt-2">
        <ExitStatsBar stats={b.exit_stats} />
      </div>

      {/* 已到止盈线但系统没替它卖的。止盈只提醒 —— 这里显示出来, 下一轮也会写进
          它的上下文, 由它自己决定落袋还是继续拿。 */}
      {(b.plan_reminders?.length ?? 0) > 0 && (
        <div className="mt-1.5 rounded border border-red-400/35 bg-red-400/[0.06] px-2 py-1 text-[10px] leading-4 text-red-400/90">
          已到止盈线({b.plan_reminders!.length} 只): {b.plan_reminders!.map(r => r.symbol).join('、')}
          <span className="ml-1 text-muted">—— 系统不代劳, 等它自己决定</span>
        </div>
      )}

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
        {/* [R171] 与「查生命线」成对: 那条是系统定的纪律, 这条是模型买入时
            自己立的计划。都不问 AI, 但归因分开记。 */}
        <button type="button" onClick={onPlanCheck}
          title="过一遍模型买入时立的计划。止损线与到期日到了直接卖(不问 AI); 到止盈线的只记提醒, 下一轮写进它的上下文"
          className="inline-flex h-7 items-center gap-1 rounded-btn border border-sky-400/40 px-2 text-[10px] text-sky-400 transition-colors hover:bg-sky-400/10">
          <Target className="h-3 w-3" />过计划
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
  const profiles = useQuery({ queryKey: QK.aiProfiles, queryFn: () => api.aiProfiles() })
  const rows = profiles.data?.profiles ?? []
  const [profileId, setProfileId] = useState('')
  const [name, setName] = useState('')
  const [capital, setCapital] = useState(1_000_000)
  const [maxPositions, setMaxPositions] = useState(10)

  const create = useMutation({
    mutationFn: () => api.paperTraderCreate({ name, profile_id: profileId, capital, max_positions: maxPositions }),
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
          <div className="grid grid-cols-2 gap-3">
            <label className="block">
              <span className="mb-1 block text-[10px] font-medium text-secondary">初始资金</span>
              <input className={INPUT} type="number" min={10000} step={10000}
                value={capital} onChange={e => setCapital(Number(e.target.value))} />
            </label>
            <label className="block">
              <span className="mb-1 block text-[10px] font-medium text-secondary">同时最多持有</span>
              <input className={INPUT} type="number" min={1} max={50}
                value={maxPositions} onChange={e => setMaxPositions(Number(e.target.value))} />
            </label>
          </div>
          <span className="block text-[10px] leading-4 text-muted">
            两本账各拿这么多本金起步(之后可以分别改)。想互相比较的话, 几个操作员要用同一个数 ——
            本金和持仓上限不同, 收益率就不是一回事: 能同时拿 40 只的账户是在拿分散度换波动。
          </span>
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
  const q = useQuery({ queryKey: QK.paperBook(id, scope), queryFn: () => api.paperBook(id, scope) })
  const ctx = useQuery({
    queryKey: QK.paperBookContext(id, scope),
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
                  {/* [R171] 买入时立的三条线。摆在浮盈旁边是有意的: 看到浮盈的
                      下一个问题必然是"那当初打算怎么办" */}
                  <th className="whitespace-nowrap px-2 py-2 text-left font-normal"
                      title="买入时模型自己立的计划。止损线与到期日到了系统直接卖(不问 AI); 止盈线到了只提醒。">
                    计划(损/盈/期)
                  </th>
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
                    <td className="whitespace-nowrap px-2 py-1.5"><PlanCell plan={p.plan} price={p.price} /></td>
                    <td className="whitespace-nowrap px-3 py-1.5 font-mono text-[10px] text-muted">{p.opened_on}</td>
                  </tr>
                ))}
                {d.positions.length === 0 && (
                  <tr><td colSpan={7} className="px-3 py-12 text-center text-[11px] text-muted">当前空仓</td></tr>
                )}
              </tbody>
            </table>
          </div>
        )}

        {tab === 'context' && (
          <div className="min-h-0 flex-1 overflow-auto p-4">
            <p className="mb-2 text-[10px] leading-4 text-muted">
              这是这本账下一次<span className="text-secondary">开局</span>会拿到的信息 —— 没有别的输入, 也没有联网。
              它还可以从里面挑最多 6 只要求细看, 那时会再给它趋势/通道/关键价位/近月走势/已有的 AI 分析。
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
        {/* [R171] 卖出归因: 止损/到期是系统按它自己的计划执行的, 止盈/主动卖是它
            自己的决定, 生命线是系统的纪律 —— 混成一类就看不出这个模型的章法 */}
        <ExitTag o={o} />
        {o.rejected
          ? <span className="text-amber-400">被拒: {o.rejected}{o.reason ? ` · 原意图: ${o.reason}` : ''}</span>
          : (o.reason || <span className="text-muted/50">(没给理由)</span>)}
      </td>
    </tr>
  )
}
