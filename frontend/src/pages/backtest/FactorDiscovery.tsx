import { useEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { BookmarkPlus, ChevronRight, Clock, Layers3, ListFilter, ListPlus, Loader2, Play, Search, Sparkles } from 'lucide-react'
import { DatePicker } from '@/components/DatePicker'
import { EmptyState } from '@/components/EmptyState'
import { toast } from '@/components/Toast'
import { WatchlistGroupMenu } from '@/components/WatchlistAddMenu'
import { api, type FactorAiReading, type FactorAiRound, type FactorBatchItem, type FactorColumn } from '@/lib/api'
import { fmtPct, priceColorClass } from '@/lib/format'
import { QK } from '@/lib/queryKeys'
import { FactorBacktest } from './FactorBacktest'
import { factorBatchCandidate } from './researchCandidates'

const formatDate = (value: Date) => value.toISOString().slice(0, 10)
const monthsAgo = (months: number) => {
  const value = new Date()
  value.setMonth(value.getMonth() - months)
  return formatDate(value)
}
const TODAY = formatDate(new Date())
const INPUT_CLS = 'w-full rounded-input border border-border bg-surface px-2.5 py-1.5 text-xs focus:border-accent focus:outline-none'

type View = 'batch' | 'single'
type SortKey = 'ic' | 'ir' | 'return'

function valueOrBottom(value: number | null) {
  return value == null || !Number.isFinite(value) ? Number.NEGATIVE_INFINITY : Math.abs(value)
}

function BatchDiscovery({ onInspect }: { onInspect: (factorName: string) => void }) {
  const queryClient = useQueryClient()
  const initialized = useRef(false)
  const [selected, setSelected] = useState<string[]>([])
  const [symbols, setSymbols] = useState('')
  const [assetType, setAssetType] = useState<'stock' | 'etf'>('stock')
  const [start, setStart] = useState(monthsAgo(3))
  const [end, setEnd] = useState(TODAY)
  const [nGroups, setNGroups] = useState(5)
  const [rebalance, setRebalance] = useState<'daily' | 'weekly' | 'monthly'>('daily')
  const [fees, setFees] = useState('2')
  const [sortKey, setSortKey] = useState<SortKey>('ic')

  const columns = useQuery({
    queryKey: QK.factorColumns,
    queryFn: api.factorColumns,
  })
  const watchlist = useQuery({
    queryKey: QK.watchlist,
    queryFn: api.watchlistList,
    staleTime: 30_000,
  })
  const watchlistEntries = useMemo(() => watchlist.data?.symbols ?? [], [watchlist.data])
  const watchlistCounts = useMemo(() => {
    const counts: Record<string, number> = { ungrouped: 0 }
    for (const entry of watchlistEntries) {
      const groupId = entry.group_id ?? 'ungrouped'
      counts[groupId] = (counts[groupId] ?? 0) + 1
    }
    return counts
  }, [watchlistEntries])
  useEffect(() => {
    if (initialized.current || !columns.data?.columns.length) return
    initialized.current = true
    setSelected(columns.data.columns.map(column => column.id))
  }, [columns.data])

  const factorGroups = useMemo(() => {
    const groups: Record<string, FactorColumn[]> = {}
    for (const column of columns.data?.columns ?? []) {
      ;(groups[column.group] ??= []).push(column)
    }
    return groups
  }, [columns.data])

  // override 供 R33 代跑用: setState 是异步的, 代跑必须拿 AI 刚给的配置立刻跑,
  // 不能等表单 state 生效。手动点「筛选」时不传, 行为与原来完全一致。
  type BatchOverride = { factor_names: string[]; rebalance: 'daily' | 'weekly' | 'monthly'; n_groups: number }
  const run = useMutation({
    mutationFn: (override?: BatchOverride) => api.factorBatch({
      factor_names: override?.factor_names ?? selected,
      symbols: symbols ? symbols.split(',').map(value => value.trim()).filter(Boolean) : null,
      asset_type: assetType,
      start: start || null,
      end: end || null,
      n_groups: override?.n_groups ?? nGroups,
      rebalance: override?.rebalance ?? rebalance,
      fees_pct: Number(fees) / 10000,
    }),
  })
  const save = useMutation({
    mutationFn: (item: FactorBatchItem) => {
      if (!run.data) throw new Error('暂无批量结果')
      return api.researchCandidateCreate(factorBatchCandidate(run.data, item))
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QK.researchCandidates })
      toast('已保存到候选方案', 'success')
    },
    onError: error => toast(`保存失败 · ${String((error as Error).message || error)}`, 'error'),
  })

  // [fork 增强] R33 AI 代跑 —— 用户不会填表, AI 来填、来跑、来判断。
  // 每一轮都真的把配置灌进左侧表单再跑, 用户能亲眼看到它在操作, 不是黑箱。
  const [rounds, setRounds] = useState<FactorAiRound[]>([])
  const [pilotBusy, setPilotBusy] = useState(false)
  const [pilotStep, setPilotStep] = useState('')
  const [conclusion, setConclusion] = useState<string | null>(null)
  const MAX_ROUNDS = 5

  const runAutopilot = async () => {
    if (pilotBusy) return
    setPilotBusy(true)
    setRounds([]); setConclusion(null); setReading(null)
    const history: FactorAiRound[] = []
    try {
      for (let i = 1; i <= MAX_ROUNDS; i++) {
        setPilotStep(`第 ${i} 轮 · AI 正在决定用哪些因子…`)
        const plan = await api.factorAiPlan({ rounds: history, max_rounds: MAX_ROUNDS })
        if (plan.error) { toast(plan.error, 'error'); break }
        if (plan.satisfied) {
          setConclusion(plan.conclusion || plan.note || '已完成')
          break
        }
        if (!plan.next) { toast('AI 没给出下一轮配置, 可重试或换模型', 'error'); break }

        // 真的填表: 勾选框/调仓/分组数都按 AI 给的改, 用户看得见
        setSelected(plan.next.factor_names)
        setRebalance(plan.next.rebalance)
        setNGroups(plan.next.n_groups)
        setPilotStep(`第 ${i} 轮 · 正在跑 ${plan.next.factor_names.length} 个因子…`)

        // 走同一个 mutation —— 结果自动进原来那张结果表, 不另开一套展示
        const res = await run.mutateAsync(plan.next)
        if (res.error) { toast(res.error, 'error'); break }

        setPilotStep(`第 ${i} 轮 · AI 正在看结果…`)
        const digest = await api.factorAiReading({
          results: res.results, config: res.config,
          n_symbols: res.n_symbols, n_dates: res.n_dates,
        })
        const entry: FactorAiRound = {
          round: i, config: { ...plan.next },
          shortlist: digest.shortlist, stats: digest.stats,
          note: plan.note, satisfied: false,
        }
        history.push(entry)
        setRounds([...history])
        if (i === MAX_ROUNDS) setConclusion('已用满 5 轮 —— 上面是最后一轮的结果, 可以自己再调调看')
      }
    } catch (e) {
      toast(`代跑中断 · ${String((e as Error).message || e)}`, 'error')
    } finally {
      setPilotBusy(false); setPilotStep('')
    }
  }

  // [fork 增强] R32 AI 解读: 规则层先出短名单(零 AI 成本), AI 再做二次解读。
  // 结果原样回传给后端, 不必让服务端重算一遍。
  const [reading, setReading] = useState<FactorAiReading | null>(null)
  const aiRead = useMutation({
    mutationFn: () => {
      if (!run.data) throw new Error('先跑一次批量筛选')
      return api.factorAiReading({
        results: run.data.results,
        config: run.data.config,
        n_symbols: run.data.n_symbols,
        n_dates: run.data.n_dates,
      })
    },
    onSuccess: value => {
      setReading(value)
      if (value.error) toast(value.error, 'error')
    },
    onError: error => toast(`解读失败 · ${String((error as Error).message || error)}`, 'error'),
  })
  // 换一批结果就清掉旧解读 —— 免得读到的是上一次的结论
  useEffect(() => { setReading(null) }, [run.data])

  const sortedResults = useMemo(() => {
    const values = [...(run.data?.results ?? [])]
    const getter = sortKey === 'ic'
      ? (item: FactorBatchItem) => valueOrBottom(item.ic_mean)
      : sortKey === 'ir'
        ? (item: FactorBatchItem) => valueOrBottom(item.ir)
        : (item: FactorBatchItem) => valueOrBottom(item.long_short_return)
    return values.sort((left, right) => getter(right) - getter(left))
  }, [run.data, sortKey])

  const toggleFactor = (factorName: string) => {
    setSelected(current => current.includes(factorName)
      ? current.filter(name => name !== factorName)
      : [...current, factorName])
  }
  const toggleGroup = (items: FactorColumn[]) => {
    const ids = items.map(item => item.id)
    const allSelected = ids.every(id => selected.includes(id))
    setSelected(current => allSelected
      ? current.filter(id => !ids.includes(id))
      : [...current, ...ids.filter(id => !current.includes(id))]
    )
  }
  const importFromWatchlist = (groupId: string | null) => {
    const entries = groupId === 'all'
      ? watchlistEntries
      : watchlistEntries.filter(entry => (entry.group_id ?? null) === groupId)
    const current = symbols.split(',').map(value => value.trim()).filter(Boolean)
    setSymbols(Array.from(new Set([...current, ...entries.map(entry => entry.symbol)])).join(','))
  }
  const allColumns = columns.data?.columns ?? []
  const allSelected = allColumns.length > 0 && allColumns.every(item => selected.includes(item.id))

  return (
    <div className="grid h-full min-h-0 grid-cols-1 overflow-hidden rounded-card border border-border bg-surface/80 xl:grid-cols-[18rem_minmax(0,1fr)]">
      <section className="space-y-3 border-b border-border bg-base/25 px-3 py-3 xl:overflow-y-auto xl:border-b-0 xl:border-r">
        <div className="flex items-center justify-between border-b border-border/70 pb-2">
          <div>
            <div className="text-xs font-semibold text-foreground">筛选配置</div>
            <div className="mt-0.5 text-[10px] text-muted">已选 {selected.length} / {allColumns.length}</div>
          </div>
          <button
            type="button"
            onClick={() => setSelected(allSelected ? [] : allColumns.map(item => item.id))}
            className="rounded-btn px-2 py-1 text-[10px] text-accent transition-colors hover:bg-accent/10"
          >
            {allSelected ? '清空' : '全选'}
          </button>
        </div>

        <div className="space-y-2">
          {Object.entries(factorGroups).map(([group, items]) => {
            const groupSelected = items.filter(item => selected.includes(item.id)).length
            return (
              <div key={group} className="border-b border-border/50 pb-2 last:border-b-0">
                <div className="mb-1.5 flex items-center justify-between">
                  <span className="text-[11px] font-medium text-secondary">{group}</span>
                  <button
                    type="button"
                    onClick={() => toggleGroup(items)}
                    className="text-[9px] text-muted transition-colors hover:text-accent"
                  >
                    {groupSelected === items.length ? '取消本组' : `选择本组 ${groupSelected}/${items.length}`}
                  </button>
                </div>
                <div className="grid grid-cols-2 gap-x-2 gap-y-1.5">
                  {items.map(item => (
                    <label key={item.id} className="flex min-w-0 cursor-pointer items-center gap-1.5 text-[10px] text-secondary">
                      <input
                        type="checkbox"
                        checked={selected.includes(item.id)}
                        onChange={() => toggleFactor(item.id)}
                        className="h-3 w-3 shrink-0 accent-accent"
                      />
                      <span className="truncate" title={item.desc}>{item.label}</span>
                    </label>
                  ))}
                </div>
              </div>
            )
          })}
        </div>

        <div>
          <label className="mb-1.5 block text-xs font-medium text-secondary">资产与范围</label>
          <div className="mb-2 inline-flex h-8 overflow-hidden rounded-btn border border-border">
            {(['stock', 'etf'] as const).map(value => (
              <button
                key={value}
                type="button"
                onClick={() => { setAssetType(value); setSymbols('') }}
                className={`h-full px-3 text-xs font-medium transition-colors ${assetType === value
                  ? 'bg-accent/10 text-accent'
                  : 'text-muted hover:text-foreground'
                }`}
              >
                {value === 'stock' ? '股票' : 'ETF'}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-1.5">
            <input
              type="text"
              value={symbols}
              onChange={event => setSymbols(event.target.value)}
              placeholder="留空使用全市场"
              className={`${INPUT_CLS} min-w-0 flex-1 font-mono`}
            />
            <WatchlistGroupMenu
              onSelect={importFromWatchlist}
              disabled={watchlist.isLoading || watchlistEntries.length === 0}
              includeAll
              counts={watchlistCounts}
              total={watchlistEntries.length}
              disableEmpty
              menuLabel="选择自选分组"
              align="right"
              triggerClassName="inline-flex h-8 shrink-0 items-center gap-1 whitespace-nowrap rounded-input border border-border bg-surface px-2 text-[11px] text-secondary transition-colors hover:border-accent/50 hover:text-foreground disabled:cursor-not-allowed disabled:opacity-50"
              title="从自选分组加入筛选范围"
              ariaLabel="从自选加入筛选范围"
            >
              <ListPlus className="h-3 w-3" />
              {watchlist.isLoading ? '加载中' : watchlistEntries.length === 0 ? '自选为空' : '从自选加入'}
            </WatchlistGroupMenu>
          </div>
        </div>

        <div className="rounded-btn border border-border bg-surface p-2.5">
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="mb-1 block text-[11px] text-secondary">开始</label>
              <DatePicker value={start} onChange={setStart} max={end || undefined} className="w-full" buttonClassName="w-full justify-start" align="left" />
            </div>
            <div>
              <label className="mb-1 block text-[11px] text-secondary">结束</label>
              <DatePicker value={end} onChange={setEnd} min={start || undefined} className="w-full" buttonClassName="w-full justify-start" />
            </div>
          </div>
          <div className="mt-2 flex rounded-input bg-base/60 p-0.5">
            {[3, 6, 12].map(months => (
              <button
                key={months}
                type="button"
                onClick={() => { setStart(monthsAgo(months)); setEnd(TODAY) }}
                className="flex-1 rounded-btn px-2 py-1 text-[10px] text-muted transition-colors hover:bg-elevated hover:text-secondary"
              >
                {months === 12 ? '1年' : `${months}个月`}
              </button>
            ))}
          </div>
        </div>

        <div className="grid grid-cols-3 gap-2">
          <label className="block">
            <span className="mb-1 block text-[10px] text-muted">调仓</span>
            <select value={rebalance} onChange={event => setRebalance(event.target.value as typeof rebalance)} className={INPUT_CLS}>
              <option value="daily">日度</option>
              <option value="weekly">周度</option>
              <option value="monthly">月度</option>
            </select>
          </label>
          <label className="block">
            <span className="mb-1 block text-[10px] text-muted">分组</span>
            <select value={nGroups} onChange={event => setNGroups(Number(event.target.value))} className={INPUT_CLS}>
              <option value={3}>3组</option>
              <option value={5}>5组</option>
              <option value={10}>10组</option>
            </select>
          </label>
          <label className="block">
            <span className="mb-1 block text-[10px] text-muted">佣金/万</span>
            <input type="number" value={fees} onChange={event => setFees(event.target.value)} className={INPUT_CLS} />
          </label>
        </div>

        {/* [R33] 不会填表就点这个 —— AI 自己挑因子、自己定参数、自己跑, 跑不好自己换一批再跑 */}
        <button
          type="button"
          onClick={() => void runAutopilot()}
          disabled={pilotBusy || run.isPending}
          title="AI 全程代劳: 挑因子 → 填表 → 跑 → 看结果 → 不行就换一批再跑, 最多 5 轮"
          className="inline-flex w-full items-center justify-center gap-1.5 rounded-btn bg-gradient-to-r from-accent to-accent/70 px-3 py-2 text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {pilotBusy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Sparkles className="h-3.5 w-3.5" />}
          {pilotBusy ? 'AI 代跑中…' : '不会选? 让 AI 帮我跑'}
        </button>
        <button
          type="button"
          onClick={() => run.mutate(undefined)}
          disabled={run.isPending || pilotBusy || selected.length === 0}
          className="inline-flex w-full items-center justify-center gap-1.5 rounded-btn border border-border bg-surface px-3 py-2 text-sm font-medium text-secondary transition-colors hover:border-accent/40 hover:text-accent disabled:cursor-not-allowed disabled:opacity-50"
        >
          <Play className="h-3.5 w-3.5" />
          {run.isPending ? '筛选中…' : `自己跑 · ${selected.length} 个因子`}
        </button>
      </section>

      <section className="min-w-0 bg-base/15 xl:overflow-y-auto">
        {(pilotBusy || rounds.length > 0 || conclusion) && (
          <AutopilotTrace busy={pilotBusy} step={pilotStep} rounds={rounds} conclusion={conclusion} />
        )}
        {run.isPending && !pilotBusy && (
          <div className="m-3 flex items-center gap-3 rounded-btn border border-accent/30 bg-accent/5 px-3 py-2.5 text-xs text-secondary">
            <span className="h-4 w-4 animate-spin rounded-full border-2 border-accent/25 border-t-accent" />
            正在加载共享数据面板并评估 {selected.length} 个因子
          </div>
        )}
        {run.isError && (
          <div className="m-3 rounded-btn border border-danger/30 bg-danger/10 px-3 py-2 text-sm text-danger">
            {String((run.error as Error).message)}
          </div>
        )}
        {run.data?.error && (
          <div className="m-3 rounded-btn border border-danger/30 bg-danger/10 px-3 py-2 text-sm text-danger">{run.data.error}</div>
        )}
        {!run.data && !run.isPending && (
          <EmptyState icon={Search} title="运行因子筛选" hint="批量结果将按预测能力排序。" />
        )}
        {run.data && !run.data.error && (
          <div>
            <div className="flex flex-wrap items-center gap-3 border-b border-border px-4 py-3">
              <div>
                <div className="text-sm font-medium text-foreground">筛选结果</div>
                <div className="mt-0.5 flex items-center gap-3 text-[10px] text-muted">
                  <span>{run.data.results.length} 个因子</span>
                  <span>{run.data.n_symbols} 只标的</span>
                  <span>{run.data.n_dates} 个交易日</span>
                  <span className="inline-flex items-center gap-1"><Clock className="h-3 w-3" />{run.data.elapsed_ms.toFixed(0)} ms</span>
                </div>
              </div>
              <button
                type="button"
                onClick={() => aiRead.mutate()}
                disabled={aiRead.isPending}
                title="规则层先按 IC/IR/胜率筛出短名单并按因子组去重, AI 再解读哪几个真能用、哪些是同类冗余"
                className="ml-auto inline-flex h-8 items-center gap-1.5 rounded-btn border border-accent/40 bg-accent/10 px-3 text-xs font-medium text-accent transition-colors hover:bg-accent/20 disabled:opacity-50"
              >
                {aiRead.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Sparkles className="h-3.5 w-3.5" />}
                AI 解读
              </button>
              <label className="flex items-center gap-2 text-[11px] text-muted">
                排序
                <select value={sortKey} onChange={event => setSortKey(event.target.value as SortKey)} className="h-8 rounded-input border border-border bg-surface px-2 text-xs text-secondary focus:border-accent focus:outline-none">
                  <option value="ic">|IC|</option>
                  <option value="ir">|IR|</option>
                  <option value="return">|多空收益|</option>
                </select>
              </label>
            </div>
            {reading && <ReadingPanel reading={reading} onUseFactors={setSelected} />}
            <div className="overflow-x-auto">
              <table className="w-full min-w-[820px] text-xs">
                <thead className="sticky top-0 bg-elevated text-left text-[11px] text-secondary">
                  <tr>
                    <th className="w-12 px-3 py-2.5 text-center font-medium">排名</th>
                    <th className="px-3 py-2.5 font-medium">因子</th>
                    <th className="px-3 py-2.5 text-right font-medium">IC 均值</th>
                    <th className="px-3 py-2.5 text-right font-medium">IR</th>
                    <th className="px-3 py-2.5 text-right font-medium">IC 胜率</th>
                    <th className="px-3 py-2.5 text-right font-medium">多空收益</th>
                    <th className="px-3 py-2.5 text-right font-medium">最大回撤</th>
                    <th className="w-24 px-3 py-2.5 text-right font-medium">操作</th>
                  </tr>
                </thead>
                <tbody>
                  {sortedResults.map((item, index) => (
                    <tr key={item.factor_name} className="border-t border-border/70 transition-colors hover:bg-elevated/40">
                      <td className="px-3 py-3 text-center font-mono text-muted">{index + 1}</td>
                      <td className="px-3 py-3">
                        <div className="font-medium text-foreground">{item.label}</div>
                        <div className="mt-0.5 text-[10px] text-muted">{item.group} · {item.factor_name}</div>
                        {item.error && <div className="mt-1 text-[10px] text-danger">{item.error}</div>}
                      </td>
                      <td className={`px-3 py-3 text-right font-mono ${priceColorClass(item.ic_mean)}`}>{item.ic_mean == null ? '—' : fmtPct(item.ic_mean)}</td>
                      <td className="px-3 py-3 text-right font-mono text-foreground">{item.ir == null ? '—' : item.ir.toFixed(2)}</td>
                      <td className="px-3 py-3 text-right font-mono text-secondary">{item.ic_win_rate == null ? '—' : fmtPct(item.ic_win_rate)}</td>
                      <td className={`px-3 py-3 text-right font-mono ${priceColorClass(item.long_short_return)}`}>{item.long_short_return == null ? '—' : fmtPct(item.long_short_return)}</td>
                      <td className="px-3 py-3 text-right font-mono text-bear">{item.long_short_max_drawdown == null ? '—' : fmtPct(item.long_short_max_drawdown)}</td>
                      <td className="px-3 py-3">
                        <div className="flex justify-end gap-1">
                          <button
                            type="button"
                            onClick={() => save.mutate(item)}
                            disabled={!!item.error || save.isPending}
                            className="flex h-7 w-7 items-center justify-center rounded-btn text-muted transition-colors hover:bg-accent/10 hover:text-accent disabled:opacity-40"
                            title="保存候选"
                            aria-label={`保存 ${item.label} 为候选`}
                          >
                            <BookmarkPlus className="h-3.5 w-3.5" />
                          </button>
                          <button
                            type="button"
                            onClick={() => onInspect(item.factor_name)}
                            disabled={!!item.error}
                            className="flex h-7 w-7 items-center justify-center rounded-btn text-muted transition-colors hover:bg-elevated hover:text-foreground disabled:opacity-40"
                            title="单因子检验"
                            aria-label={`查看 ${item.label} 的单因子检验`}
                          >
                            <ChevronRight className="h-3.5 w-3.5" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </section>
    </div>
  )
}

export function FactorDiscovery() {
  const [view, setView] = useState<View>('batch')
  const [detailFactor, setDetailFactor] = useState('momentum_20d')
  const inspect = (factorName: string) => {
    setDetailFactor(factorName)
    setView('single')
  }
  return (
    <div className="flex h-full min-h-0 flex-col gap-3">
      <div className="flex shrink-0 items-center border-b border-border/70 px-1 pb-2">
        <div className="inline-flex rounded-btn border border-border bg-surface/80 p-0.5">
          {([
            ['batch', '批量筛选', ListFilter],
            ['single', '单因子检验', Layers3],
          ] as const).map(([value, label, Icon]) => (
            <button
              key={value}
              type="button"
              onClick={() => setView(value)}
              className={`inline-flex items-center gap-1.5 rounded-[5px] px-3 py-1.5 text-xs font-medium transition-colors ${view === value
                ? 'bg-accent text-white shadow-sm'
                : 'text-secondary hover:bg-elevated hover:text-foreground'
              }`}
            >
              <Icon className="h-3.5 w-3.5" />
              {label}
            </button>
          ))}
        </div>
      </div>
      <div className="min-h-0 flex-1">
        {view === 'batch'
          ? <BatchDiscovery onInspect={inspect} />
          : <FactorBacktest key={detailFactor} initialFactorName={detailFactor} />
        }
      </div>
    </div>
  )
}


/**
 * [fork 增强] R32 AI 解读面板。
 *
 * 呈现顺序按可信度从高到低: 规则层漏斗(确定的事) → AI 结论(判断) → 冗余提示。
 * 「用这几个重跑」直接把 AI 选中的因子灌回左侧勾选框, 省得手动找。
 */
function ReadingPanel({ reading, onUseFactors }: {
  reading: FactorAiReading
  onUseFactors: (factors: string[]) => void
}) {
  const st = reading.stats ?? {}
  const picks = reading.ai?.picks ?? []
  return (
    <div className="border-b border-border bg-elevated/30 px-4 py-3">
      {/* 漏斗: 回答"61 个里为什么只剩这几个" */}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[10px] text-muted">
        <span className="font-medium text-secondary">规则层筛选</span>
        <span>{st['总数'] ?? 0} 个因子</span>
        {!!st['算失败'] && <span className="text-danger">算失败 {st['算失败']}</span>}
        <span>有区分度 {st['有区分度'] ?? 0}</span>
        <span>同组去重剔除 {st['同组去重剔除'] ?? 0}</span>
        <span className="text-accent">进短名单 {st['进短名单'] ?? 0}</span>
      </div>

      {reading.error && (
        <p className="mt-2 text-[11px] text-warning">{reading.error}</p>
      )}

      {reading.ai?.summary && (
        <p className="mt-2 text-[11px] leading-relaxed text-secondary">
          <span className="mr-1 text-accent">AI</span>{reading.ai.summary}
        </p>
      )}

      {picks.length > 0 && (
        <div className="mt-2 space-y-1">
          {picks.map(p => (
            <div key={p.factor} className="flex flex-wrap items-baseline gap-x-2 text-[10px]">
              <span className="font-mono font-medium text-foreground">{p.factor}</span>
              <span className="text-secondary">{p.reason}</span>
            </div>
          ))}
        </div>
      )}

      {(reading.ai?.redundant ?? []).length > 0 && (
        <div className="mt-2 space-y-0.5">
          {reading.ai!.redundant.map(r => (
            <p key={r.keep} className="text-[10px] text-muted">
              同类冗余：留 <span className="font-mono text-secondary">{r.keep}</span>
              ，可丢 <span className="font-mono">{r.drop.join(', ')}</span>
              {r.reason && <span className="ml-1">· {r.reason}</span>}
            </p>
          ))}
        </div>
      )}

      {reading.ai?.next_step && (
        <p className="mt-2 text-[10px] leading-4 text-accent/90">下一步：{reading.ai.next_step}</p>
      )}

      <div className="mt-2 flex flex-wrap gap-2">
        {picks.length > 0 && (
          <button type="button" onClick={() => onUseFactors(picks.map(p => p.factor))}
            className="inline-flex h-7 items-center gap-1 rounded-btn border border-accent/40 bg-accent/10 px-2 text-[10px] font-medium text-accent hover:bg-accent/20">
            <Sparkles className="h-3 w-3" />
            只用 AI 选的这 {picks.length} 个重跑
          </button>
        )}
        {reading.shortlist.length > 0 && (
          <button type="button" onClick={() => onUseFactors(reading.shortlist.map(r => r.factor))}
            className="inline-flex h-7 items-center gap-1 rounded-btn border border-border px-2 text-[10px] text-secondary hover:border-accent/40 hover:text-accent"
            title="规则层短名单: 按可用度排序, 同组最多留 2 个">
            <ListFilter className="h-3 w-3" />
            用规则层短名单({reading.shortlist.length} 个)
          </button>
        )}
      </div>
    </div>
  )
}


/**
 * [fork 增强] R33 代跑过程条 —— 让"AI 在替我操作"看得见。
 *
 * 只呈现三件事: 现在在干嘛、每轮试了什么结果如何、最后的结论。
 * 结论里必须带上"这是描述性统计不是验证过的策略"的口径, 由后端提示词保证。
 */
function AutopilotTrace({ busy, step, rounds, conclusion }: {
  busy: boolean
  step: string
  rounds: FactorAiRound[]
  conclusion: string | null
}) {
  return (
    <div className="m-3 rounded-btn border border-accent/30 bg-accent/5 px-3 py-2.5">
      <div className="flex items-center gap-2">
        {busy
          ? <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin text-accent" />
          : <Sparkles className="h-3.5 w-3.5 shrink-0 text-accent" />}
        <span className="text-xs font-medium text-foreground">AI 代跑</span>
        <span className="min-w-0 flex-1 truncate text-[11px] text-secondary">
          {busy ? step : `共 ${rounds.length} 轮`}
        </span>
      </div>

      {rounds.length > 0 && (
        <div className="mt-2 space-y-1">
          {rounds.map(r => {
            const top = r.shortlist[0]
            return (
              <div key={r.round} className="flex flex-wrap items-baseline gap-x-2 text-[10px]">
                <span className="shrink-0 font-medium text-secondary">第 {r.round} 轮</span>
                <span className="font-mono text-muted">
                  {(r.config.factor_names as string[] | undefined)?.length ?? 0} 因子 ·
                  {String(r.config.rebalance ?? '')} · {String(r.config.n_groups ?? '')} 组
                </span>
                <span className="text-muted">
                  {top
                    ? `最好的是 ${top.factor}(IC ${top.IC均值?.toFixed(3) ?? '—'})`
                    : '没有因子有区分度'}
                </span>
                {r.note && <span className="min-w-0 flex-1 truncate text-secondary">{r.note}</span>}
              </div>
            )
          })}
        </div>
      )}

      {conclusion && (
        <p className="mt-2 border-t border-accent/20 pt-2 text-[11px] leading-relaxed text-secondary">
          <span className="mr-1 text-accent">结论</span>{conclusion}
        </p>
      )}
    </div>
  )
}
