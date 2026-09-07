import { useEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowDown, ArrowUp, BookmarkPlus, ChevronRight, ChevronsUpDown, Clock, Info, Layers3, ListFilter, ListPlus, Loader2, Play, Search, Sparkles, Square, Zap } from 'lucide-react'
import { DatePicker } from '@/components/DatePicker'
import { EmptyState } from '@/components/EmptyState'
import { toast } from '@/components/Toast'
import { WatchlistGroupMenu } from '@/components/WatchlistAddMenu'
import { api, type FactorAiReading, type FactorAiRound, type FactorBatchItem, type FactorColumn } from '@/lib/api'
import { fmtPct, priceColorClass } from '@/lib/format'
import { QK } from '@/lib/queryKeys'
import { FactorBacktest } from './FactorBacktest'
import { AutoMiningDialog } from './AutoMiningDialog'
import { AddFactorSignalDialog } from './AddFactorSignalDialog'
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
type SortKey = 'ic' | 'ir' | 'return' | 't_nw' | 'win_rate' | 'drawdown'
type Verdict = 'valid' | 'edge' | 'invalid' | 'error'

// P0 判读为客户端经验规则, metrics_v2 (服务端显著性) 落地后切换为服务端 verdict
const VERDICT_META: Record<Verdict, { label: string; cls: string }> = {
  valid: { label: '有效', cls: 'bg-bull/10 text-bull' },
  edge: { label: '边缘', cls: 'bg-amber-400/10 text-amber-500' },
  invalid: { label: '无效', cls: 'bg-base text-muted' },
  error: { label: '失败', cls: 'bg-danger/10 text-danger' },
}

// 服务端判读优先 (metrics_v2: NW t ≥ 2 显著 且 BH q ≤ 0.1), 缺失时降级 P0 经验规则
const verdictOf = (item: FactorBatchItem): Verdict => {
  if (item.error) return 'error'
  const ic = Math.abs(item.ic_mean ?? 0)
  const ir = Math.abs(item.ir ?? 0)
  if (item.t_newey_west != null) {
    const significant = Math.abs(item.t_newey_west) >= 2
      && (item.q_value == null || item.q_value <= 0.1)
    const predictive = ic >= 0.02
    if (significant && predictive) return 'valid'
    if (significant || predictive) return 'edge'
    return 'invalid'
  }
  if (ic >= 0.02 && ir >= 0.3) return 'valid'
  if (ic >= 0.02 || ir >= 0.3) return 'edge'
  return 'invalid'
}

const hasServerVerdict = (results: FactorBatchItem[]): boolean =>
  results.some(item => !item.error && item.t_newey_west != null)

// 预设场景: 纯前端选择集, 数量按 columns 数据实时计算 (分组名缺失时该项自动为空并禁用)
type PresetDef = { id: string; label: string; hint: string; groups?: string[]; quick?: boolean }
const PRESETS: PresetDef[] = [
  { id: 'all', label: '全面体检', hint: '全部因子，耗时最长' },
  { id: 'quick', label: '快速体检', hint: '除财务组外每组各取 1 个代表因子' , quick: true },
  { id: 'trend', label: '趋势动量', hint: '动量组 + 趋势组', groups: ['动量', '趋势'] },
  { id: 'reversal', label: '超跌反转', hint: '超买超卖组 + 价格位置组', groups: ['超买超卖', '价格位置'] },
  { id: 'volume', label: '量价资金', hint: '量价组 + 流动性组', groups: ['量价', '流动性'] },
  { id: 'fundamental', label: '财务价值', hint: '财务组（需财务数据）', groups: ['财务'] },
]

const INTRO_STORAGE_KEY = 'factors-intro-collapsed'

// 表头排序: IC/IR/t 值/多空收益按 |值| 排 (正负都是信号), 胜率/回撤按原值排
const SORT_GETTERS: Record<SortKey, (item: FactorBatchItem) => number | null | undefined> = {
  ic: item => item.ic_mean,
  ir: item => item.ir,
  return: item => item.long_short_return,
  t_nw: item => item.t_newey_west,
  win_rate: item => item.ic_win_rate,
  drawdown: item => item.long_short_max_drawdown,
}
const ABS_SORT_KEYS: ReadonlySet<SortKey> = new Set(['ic', 'ir', 'return', 't_nw'])

function SortableTh({ label, sortKeyName, sortKey, sortAsc, onSort, className, title }: {
  label: string
  sortKeyName: SortKey
  sortKey: SortKey
  sortAsc: boolean
  onSort: (key: SortKey) => void
  className?: string
  title?: string
}) {
  const active = sortKey === sortKeyName
  const Icon = !active ? ChevronsUpDown : sortAsc ? ArrowUp : ArrowDown
  return (
    <th
      className={`${className ?? ''} font-medium`}
      title={title}
      aria-sort={active ? (sortAsc ? 'ascending' : 'descending') : 'none'}
    >
      <button
        type="button"
        onClick={() => onSort(sortKeyName)}
        className={`inline-flex items-center gap-0.5 rounded-btn transition-colors hover:text-foreground ${active ? 'text-foreground' : ''}`}
        title={title ? `${title}${active ? '' : '（点击排序）'}` : '点击排序'}
      >
        {label}
        <Icon className={`h-3 w-3 ${active ? 'text-accent' : 'text-muted/50'}`} />
      </button>
    </th>
  )
}

function BatchDiscovery({ onInspect, focusFactor }: { onInspect: (factorName: string) => void; focusFactor?: string }) {
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
  const [sortAsc, setSortAsc] = useState(false)
  const [factorQuery, setFactorQuery] = useState('')
  const [activePreset, setActivePreset] = useState<string | null>(null)
  const [signalFrom, setSignalFrom] = useState<FactorBatchItem | null>(null)

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
    // 多组并存: 一股计入每个所属分组
    const counts: Record<string, number> = { ungrouped: 0 }
    for (const entry of watchlistEntries) {
      const gids = entry.group_ids ?? []
      if (gids.length === 0) counts.ungrouped += 1
      else for (const gid of gids) counts[gid] = (counts[gid] ?? 0) + 1
    }
    return counts
  }, [watchlistEntries])
  useEffect(() => {
    if (initialized.current || !columns.data?.columns.length) return
    initialized.current = true
    // 因子库「去检验」联动: focus 参数命中则只选该因子
    if (focusFactor && columns.data.columns.some(column => column.id === focusFactor)) {
      setSelected([focusFactor])
      setActivePreset(null)
      return
    }
    setSelected(columns.data.columns.map(column => column.id))
    setActivePreset('all')
  }, [columns.data, focusFactor])

  const allColumns = useMemo(() => columns.data?.columns ?? [], [columns.data])
  const columnsByGroup = useMemo(() => {
    const groups: Record<string, FactorColumn[]> = {}
    for (const column of allColumns) (groups[column.group] ??= []).push(column)
    return groups
  }, [allColumns])
  const presetIds = (preset: PresetDef): string[] => {
    if (preset.id === 'all') return allColumns.map(item => item.id)
    if (preset.quick) {
      // 每组取列表中位代表 (上游按窗口升序排列时即窗口中位数, 如动量组取 20日)
      return Object.entries(columnsByGroup)
        .filter(([group]) => group !== '财务')
        .map(([, items]) => items[Math.floor((items.length - 1) / 2)])
        .filter(item => item != null)
        .map(item => item.id)
    }
    return (preset.groups ?? []).flatMap(group => columnsByGroup[group] ?? []).map(item => item.id)
  }

  const factorGroups = useMemo(() => {
    // 搜索只影响展示, 不改变已选集合; 匹配 id/中文label/公式描述
    const query = factorQuery.trim().toLowerCase()
    const groups: Record<string, FactorColumn[]> = {}
    for (const column of columns.data?.columns ?? []) {
      if (query && !`${column.id} ${column.label} ${column.desc}`.toLowerCase().includes(query)) continue
      ;(groups[column.group] ??= []).push(column)
    }
    return groups
  }, [columns.data, factorQuery])

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
      toast('已保存到候选方案（右上角「候选方案」查看）', 'success')
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
  // [R38] 中止: 循环跑在前端, 用 ref 而不是 state —— 闭包里读 state 拿到的是
  // 点开跑那一刻的旧值, 永远读不到"后来点了停"
  const abortRef = useRef(false)

  const runAutopilot = async () => {
    if (pilotBusy) return
    abortRef.current = false
    setPilotBusy(true)
    setRounds([]); setConclusion(null); setReading(null)
    const history: FactorAiRound[] = []
    try {
      for (let i = 1; i <= MAX_ROUNDS; i++) {
        if (abortRef.current) { setConclusion(`已中止 —— 跑完了 ${history.length} 轮`); break }
        setPilotStep(`第 ${i} 轮 · AI 正在决定用哪些因子…`)
        const plan = await api.factorAiPlan({ rounds: history, max_rounds: MAX_ROUNDS })
        if (abortRef.current) { setConclusion(`已中止 —— 跑完了 ${history.length} 轮`); break }
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
        if (abortRef.current) {
          setConclusion(`已中止 —— 第 ${i} 轮的结果已经在下面的表里, 但没让 AI 再往下判`)
          break
        }

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
    const getter = SORT_GETTERS[sortKey]
    const useAbs = ABS_SORT_KEYS.has(sortKey)
    const value = (item: FactorBatchItem) => {
      const raw = getter(item)
      if (raw == null || !Number.isFinite(raw)) return sortAsc ? Number.POSITIVE_INFINITY : Number.NEGATIVE_INFINITY
      return useAbs ? Math.abs(raw) : raw
    }
    return [...(run.data?.results ?? [])].sort((left, right) => (sortAsc ? value(left) - value(right) : value(right) - value(left)))
  }, [run.data, sortKey, sortAsc])

  const applySort = (key: SortKey) => {
    if (key === sortKey) {
      setSortAsc(current => !current)
    } else {
      setSortKey(key)
      setSortAsc(false)
    }
  }

  // 结论句: 有效数按经验规则统计; 最强按 |IC| 取 (与默认排序口径一致)
  const computableResults = useMemo(() => (run.data?.results ?? []).filter(item => !item.error), [run.data])
  const validCount = useMemo(() => computableResults.filter(item => verdictOf(item) === 'valid').length, [computableResults])
  const bestFactor = useMemo(() => {
    let best: FactorBatchItem | null = null
    for (const item of computableResults) {
      if (item.ic_mean == null) continue
      if (best == null || Math.abs(item.ic_mean) > Math.abs(best.ic_mean ?? 0)) best = item
    }
    return best
  }, [computableResults])

  const toggleFactor = (factorName: string) => {
    setActivePreset(null)
    setSelected(current => current.includes(factorName)
      ? current.filter(name => name !== factorName)
      : [...current, factorName])
  }
  const toggleGroup = (items: FactorColumn[]) => {
    setActivePreset(null)
    const ids = items.map(item => item.id)
    const allSelected = ids.every(id => selected.includes(id))
    setSelected(current => allSelected
      ? current.filter(id => !ids.includes(id))
      : [...current, ...ids.filter(id => !current.includes(id))]
    )
  }
  const importFromWatchlist = (groupId: string | null) => {
    // 'all'=全部自选; null=未分组; 其他=指定分组 (多组归属时该股计入每个所属分组)
    const entries = groupId === 'all'
      ? watchlistEntries
      : groupId == null
        ? watchlistEntries.filter(entry => !(entry.group_ids?.length))
        : watchlistEntries.filter(entry => !!entry.group_ids?.includes(groupId))
    const current = symbols.split(',').map(value => value.trim()).filter(Boolean)
    setSymbols(Array.from(new Set([...current, ...entries.map(entry => entry.symbol)])).join(','))
  }
  const allSelected = allColumns.length > 0 && allColumns.every(item => selected.includes(item.id))
  const applyPreset = (preset: PresetDef) => {
    setSelected(presetIds(preset))
    setActivePreset(preset.id)
  }

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
            onClick={() => { setActivePreset(null); setSelected(allSelected ? [] : allColumns.map(item => item.id)) }}
            className="rounded-btn px-2 py-1 text-[10px] text-accent transition-colors hover:bg-accent/10"
          >
            {allSelected ? '清空' : '全选'}
          </button>
        </div>

        <div>
          <div className="mb-1.5 text-[10px] text-muted">不知道测什么？从预设开始（一键选好因子）：</div>
          <div className="flex flex-wrap gap-1">
            {PRESETS.map(preset => {
              const ids = presetIds(preset)
              const active = activePreset === preset.id
              return (
                <button
                  key={preset.id}
                  type="button"
                  onClick={() => applyPreset(preset)}
                  disabled={ids.length === 0}
                  title={preset.hint}
                  className={`inline-flex items-center gap-1 rounded-btn border px-2 py-1 text-[10px] font-medium transition-colors disabled:pointer-events-none disabled:opacity-40 ${active
                    ? 'border-accent/60 bg-accent/10 text-accent'
                    : 'border-border bg-surface text-secondary hover:border-accent/40 hover:text-accent'
                  }`}
                >
                  {preset.label}
                  <span className="font-mono opacity-70">{ids.length}</span>
                  {active && <span aria-hidden>✓</span>}
                </button>
              )
            })}
            {activePreset == null && (
              <span className="inline-flex items-center rounded-btn border border-dashed border-border px-2 py-1 text-[10px] text-muted">
                自定义
              </span>
            )}
          </div>
        </div>

        <div className="relative">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3 w-3 -translate-y-1/2 text-muted" />
          <input
            type="text"
            value={factorQuery}
            onChange={event => setFactorQuery(event.target.value)}
            placeholder="搜索因子 (名称/公式)"
            className={`${INPUT_CLS} pl-7`}
          />
        </div>

        <div className="max-h-[45vh] space-y-2 overflow-y-auto pr-0.5">
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
          {Object.keys(factorGroups).length === 0 && (
            <div className="py-4 text-center text-[10px] text-muted">
              {columns.isLoading ? '因子加载中…' : '无匹配因子'}
            </div>
          )}
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
        {pilotBusy ? (
          /* [R38] 中止: 在轮与轮之间停。当前这一轮的请求已经发出去了, 停不掉,
             所以按钮上直接写清楚"跑完这轮就停", 不假装能立刻断 */
          <button
            type="button"
            onClick={() => { abortRef.current = true; toast('会在当前这一轮跑完后停下', 'success') }}
            title="因子筛选是一次性请求, 发出去就断不掉了 —— 这里是在下一轮开始前停住"
            className="inline-flex w-full items-center justify-center gap-1.5 rounded-btn border border-danger/40 px-3 py-2 text-sm font-medium text-danger transition-colors hover:bg-danger/10"
          >
            <Square className="h-3.5 w-3.5" />
            中止代跑(跑完这轮就停)
          </button>
        ) : (
          <button
            type="button"
            onClick={() => void runAutopilot()}
            disabled={run.isPending}
            title="AI 全程代劳: 挑因子 → 填表 → 跑 → 看结果 → 不行就换一批再跑, 最多 5 轮"
            className="inline-flex w-full items-center justify-center gap-1.5 rounded-btn bg-gradient-to-r from-accent to-accent/70 px-3 py-2 text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Sparkles className="h-3.5 w-3.5" />
            不会选? 让 AI 帮我跑
          </button>
        )}
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
                {computableResults.length > 0 && (
                  <div className="mt-1 text-[11px] text-secondary">
                    {computableResults.length} 个因子中 <span className="font-medium text-bull">{validCount} 个有效</span>
                    <span className="text-muted">
                      {hasServerVerdict(computableResults)
                        ? '（NW 显著性检验：|t|≥2 且 BH q≤0.1，|IC|≥0.02）'
                        : '（经验规则：|IC|≥0.02 且 |IR|≥0.3）'}
                    </span>
                    {bestFactor && bestFactor.ic_mean != null && (
                      <>。最强：<span className="font-medium text-foreground">{bestFactor.label}</span>（IC {fmtPct(bestFactor.ic_mean)}）</>
                    )}
                  </div>
                )}
              </div>
              <div className="ml-auto self-center text-[10px] text-muted" title="点击数值列表头可切换排序键与升/降序；IC/IR/t 值/多空收益按绝对值排序（正负都是信号）。">
                点击表头排序
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
                    <th className="w-12 px-3 py-2.5 text-center font-medium" title="按当前排序键排序的名次，默认按 |IC|。">排名</th>
                    <th className="px-3 py-2.5 font-medium">因子</th>
                    <SortableTh label="预测力 IC" sortKeyName="ic" sortKey={sortKey} sortAsc={sortAsc} onSort={applySort} className="px-3 py-2.5 text-right" title="每天用因子给股票打分、与次日真实涨跌算相关性（Rank IC）的均值。|IC|≥0.02 且稳定即有预测力；负值同样有效（反向使用）。" />
                    <SortableTh label="稳定度 IR" sortKeyName="ir" sortKey={sortKey} sortAsc={sortAsc} onSort={applySort} className="px-3 py-2.5 text-right" title="IC 均值 ÷ IC 波动。≥0.3 值得关注，≥0.5 相当稳定。" />
                    <SortableTh label="t 值(NW)" sortKeyName="t_nw" sortKey={sortKey} sortAsc={sortAsc} onSort={applySort} className="px-3 py-2.5 text-right" title="Newey-West HAC 稳健 t 值（滞后 1）：|t|≥2 视为统计显著；悬停查看多重检验校正后的 q 值（≤0.1 通过）。样本不足显示 —。" />
                    <SortableTh label="预测日占比" sortKeyName="win_rate" sortKey={sortKey} sortAsc={sortAsc} onSort={applySort} className="px-3 py-2.5 text-right" title="IC 与预测方向一致的天数占比。50% 是抛硬币，55%+ 不错。" />
                    <SortableTh label="多空收益" sortKeyName="return" sortKey={sortKey} sortAsc={sortAsc} onSort={applySort} className="px-3 py-2.5 text-right" title="每期买因子最高组、（模拟）卖最低组的累计收益差。A 股做空受限，此列为理论口径。" />
                    <SortableTh label="最大回撤" sortKeyName="drawdown" sortKey={sortKey} sortAsc={sortAsc} onSort={applySort} className="px-3 py-2.5 text-right" title="上述多空组合最痛的一段亏损幅度，衡量拿得住不住。" />
                    <th className="w-16 px-3 py-2.5 text-center font-medium" title="经验规则：|IC|≥0.02 且 |IR|≥0.3 为有效；其一达标为边缘。">结论</th>
                    <th className="w-24 px-3 py-2.5 text-right font-medium">操作</th>
                  </tr>
                </thead>
                <tbody>
                  {sortedResults.map((item, index) => (
                    <tr key={item.factor_name} className="border-t border-border/70 transition-colors hover:bg-elevated/40">
                      <td className="px-3 py-3 text-center font-mono text-muted">{index + 1}</td>
                      <td className="px-3 py-3">
                        <div className="font-medium text-foreground">
                          {item.label}
                          {!item.error && item.ic_mean != null && (
                            item.ic_mean >= 0
                              ? <span className="ml-1 text-bull" title="样本内方向：值大看多（IC 为正）。历史方向不代表未来。">↑</span>
                              : <span className="ml-1 text-bear" title="样本内方向：值小看多（IC 为负，反向使用）。历史方向不代表未来。">↓</span>
                          )}
                        </div>
                        <div className="mt-0.5 text-[10px] text-muted">{item.group} · {item.factor_name}</div>
                        {item.error && <div className="mt-1 text-[10px] text-danger">{item.error}</div>}
                      </td>
                      <td className={`px-3 py-3 text-right font-mono ${priceColorClass(item.ic_mean)}`}>{item.ic_mean == null ? '—' : fmtPct(item.ic_mean)}</td>
                      <td className="px-3 py-3 text-right font-mono text-foreground">{item.ir == null ? '—' : item.ir.toFixed(2)}</td>
                      <td
                        className={`px-3 py-3 text-right font-mono ${item.t_newey_west != null && Math.abs(item.t_newey_west) >= 2 ? 'text-foreground' : 'text-muted'}`}
                        title={item.t_newey_west != null
                          ? `NW t=${item.t_newey_west.toFixed(2)}${item.q_value != null ? `，BH q=${item.q_value.toFixed(3)}` : ''}（${item.q_value != null && item.q_value <= 0.1 ? '通过' : '未通过'}多重检验校正）`
                          : '样本不足，无法计算'}
                      >
                        {item.t_newey_west == null ? '—' : item.t_newey_west.toFixed(2)}
                      </td>
                      <td className="px-3 py-3 text-right font-mono text-secondary">{item.ic_win_rate == null ? '—' : fmtPct(item.ic_win_rate)}</td>
                      <td className={`px-3 py-3 text-right font-mono ${priceColorClass(item.long_short_return)}`}>{item.long_short_return == null ? '—' : fmtPct(item.long_short_return)}</td>
                      <td className="px-3 py-3 text-right font-mono text-bear">{item.long_short_max_drawdown == null ? '—' : fmtPct(item.long_short_max_drawdown)}</td>
                      <td className="px-3 py-3 text-center">
                        <span className={`inline-flex rounded-btn px-1.5 py-0.5 text-[10px] font-medium ${VERDICT_META[verdictOf(item)].cls}`}>
                          {VERDICT_META[verdictOf(item)].label}
                        </span>
                      </td>
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
                            onClick={() => setSignalFrom(item)}
                            disabled={!!item.error}
                            className="flex h-7 w-7 items-center justify-center rounded-btn text-muted transition-colors hover:bg-amber-400/10 hover:text-amber-400 disabled:opacity-40"
                            title="加入信号条件（方向按 IC 预填，阈值给建议值）"
                            aria-label={`把 ${item.label} 加入信号条件`}
                          >
                            <Zap className="h-3.5 w-3.5" />
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

      {signalFrom && <AddFactorSignalDialog item={signalFrom} onClose={() => setSignalFrom(null)} />}
    </div>
  )
}

export function FactorDiscovery({ focusFactor }: { focusFactor?: string } = {}) {
  const [view, setView] = useState<View>('batch')
  const [detailFactor, setDetailFactor] = useState('momentum_20d')
  const [autoOpen, setAutoOpen] = useState(false)
  const [introCollapsed, setIntroCollapsed] = useState(() => {
    try {
      return localStorage.getItem(INTRO_STORAGE_KEY) === '1'
    } catch {
      return false
    }
  })
  const collapseIntro = () => {
    setIntroCollapsed(true)
    try {
      localStorage.setItem(INTRO_STORAGE_KEY, '1')
    } catch { /* 隐私模式等场景忽略 */ }
  }
  const inspect = (factorName: string) => {
    setDetailFactor(factorName)
    setView('single')
  }
  return (
    <div className="flex h-full min-h-0 flex-col gap-3">
      {!introCollapsed && (
        <div className="flex shrink-0 items-start gap-2 rounded-card border border-border bg-surface/60 px-3 py-2 text-[11px] leading-relaxed text-secondary">
          <Info className="mt-0.5 h-3.5 w-3.5 shrink-0 text-accent" />
          <div className="min-w-0 flex-1">
            <span className="font-medium text-foreground">三步看懂本页：</span>
            ① 因子 = 给股票打分排序的特征（如 20日涨幅、换手率变化）；② 本页检验过去哪些特征真的能预测次日涨跌；③ IC = 预测准确度（绝对值越大越准，负值反向用），IR = 稳定度（越大越稳）。
          </div>
          <button
            type="button"
            onClick={collapseIntro}
            className="shrink-0 rounded-btn px-2 py-0.5 text-[10px] text-muted transition-colors hover:bg-elevated hover:text-foreground"
          >
            知道了
          </button>
        </div>
      )}
      <div className="flex shrink-0 items-center border-b border-border/70 px-1 pb-2">
        {view === 'single' && (
          <button
            type="button"
            onClick={() => setView('batch')}
            className="mr-2 inline-flex items-center gap-1 rounded-btn px-2 py-1 text-[11px] text-muted transition-colors hover:bg-elevated hover:text-foreground"
            title="返回批量结果（筛选配置与结果保留）"
          >
            ← 返回批量
          </button>
        )}
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
        <button
          type="button"
          onClick={() => setAutoOpen(true)}
          className="ml-auto mr-1 inline-flex items-center gap-1.5 rounded-btn border border-accent/40 bg-accent/5 px-2.5 py-1.5 text-xs font-medium text-accent transition-colors hover:bg-accent/10"
          title="不知道选什么因子？让系统全量筛选达标因子并自动搜索组合（嵌套样本外验证）"
        >
          <Sparkles className="h-3.5 w-3.5" />
          自动挖掘
        </button>
      </div>
      <div className="min-h-0 flex-1">
        {/* 批量视图保持挂载: 切到单因子检验再返回时, 选择集与结果不丢 */}
        <div className={view === 'batch' ? 'h-full' : 'hidden'}>
          <BatchDiscovery onInspect={inspect} focusFactor={focusFactor} />
        </div>
        {view === 'single' && (
          <div className="h-full">
            <FactorBacktest key={detailFactor} initialFactorName={detailFactor} />
          </div>
        )}
      </div>

      {autoOpen && <AutoMiningDialog onClose={() => setAutoOpen(false)} />}
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
