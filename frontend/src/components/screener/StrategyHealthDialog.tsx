import { Fragment, useState, useRef, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Activity, Loader2, Sparkles, X, AlertTriangle, ChevronDown, ChevronRight, Send } from 'lucide-react'
import { api } from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import { BOARDS, getBoardType, type BoardType } from '@/lib/board'
import { toast } from '@/components/Toast'

/** 策略体检 —— 零配置批量回测:策略池逐个跑(各自的交易参数+服务端默认),出胜率对比表。
 *  点策略名展开详情(完整指标/出场原因分布/收益口径);「AI 解读」支持多轮追问。 */

type ExitReasonAgg = { reason: string; count: number; avg_pnl: number }
type HealthRow = {
  id: string
  name: string
  status: 'pending' | 'running' | 'done' | 'error'
  error?: string
  win_rate?: number | null
  profit_factor?: number | null
  total_return?: number | null
  max_drawdown?: number | null
  n_trades?: number | null
  avg_pnl?: number | null
  // 详情/诊断素材(回测完成时聚合): 配置 + 全量 stats + 出场原因分布 + 同期基准收益
  diagConfig?: Record<string, unknown>
  diagStats?: Record<string, unknown>
  exitReasons?: ExitReasonAgg[]
  benchmarkReturn?: number | null
  diagText?: string
}
type ChatMsg = { role: 'user' | 'assistant'; content: string }

const WINDOW_PRESETS = [
  { days: 90, label: '近3个月' },
  { days: 180, label: '近6个月' },
]
const MIN_TRADES = 30  // 样本量低于此数, 胜率统计意义不足
const CUSTOM_MIN = 30, CUSTOM_MAX = 365

// 出场原因 → 中文标签(未知原因原样显示)
const EXIT_LABEL: Record<string, string> = {
  stop_loss: '止损', max_hold: '持有到期', exit_signal: '出场信号',
  take_profit: '止盈', trailing_stop: '移动止损', trailing_take_profit: '移动止盈',
  end_of_backtest: '回测结束平仓', unknown: '其他',
}

function pct(v: number | null | undefined, digits = 1): string {
  return v == null ? '—' : `${(v * 100).toFixed(digits)}%`
}
function num(v: unknown): string {
  return typeof v === 'number' && Number.isFinite(v) ? String(v) : '—'
}

export function StrategyHealthDialog({ open, onClose, strategyIds, nameOf }: {
  open: boolean
  onClose: () => void
  strategyIds: string[]
  nameOf: (id: string) => string
}) {
  const [windowDays, setWindowDays] = useState(90)
  const [customDays, setCustomDays] = useState('')   // 自定义天数(空 = 未启用)
  // 回测范围: 全市场(作者默认语义) / 仅自选 / 具体板块
  const [scope, setScope] = useState<'market' | 'watchlist' | BoardType>('market')
  const [rows, setRows] = useState<HealthRow[]>([])
  const [running, setRunning] = useState(false)
  const cancelRef = useRef(false)
  // 详情/诊断展开(单行) + AI 解读多轮对话 —— 都必须在 if(!open) 早退之前声明
  const [openId, setOpenId] = useState<string | null>(null)
  const [diagLoadingId, setDiagLoadingId] = useState<string | null>(null)
  const [chat, setChat] = useState<ChatMsg[]>([])
  const [question, setQuestion] = useState('')
  const [aiLoading, setAiLoading] = useState(false)

  const watchlistQ = useQuery({
    queryKey: QK.watchlist,
    queryFn: () => api.watchlistList(),
    staleTime: 60_000,
    enabled: open,
  })
  const watchlistSymbols = (watchlistQ.data?.symbols ?? []).map(s => s.symbol)

  // 板块范围: 全市场快照按代码前缀分板块(getBoardType), 仅选中板块时才拉取
  const isBoard = (BOARDS as readonly string[]).includes(scope)
  const snapshotQ = useQuery({
    queryKey: QK.marketSnapshot,
    queryFn: () => api.marketSnapshot(),
    staleTime: 10 * 60_000,
    enabled: open && isBoard,
  })
  const boardSymbols = useMemo(() => {
    if (!isBoard) return []
    return (snapshotQ.data?.rows ?? [])
      .map(r => r.symbol)
      .filter(s => getBoardType(s) === scope)
  }, [isBoard, scope, snapshotQ.data])
  const scopeSymbols = scope === 'watchlist' ? watchlistSymbols : isBoard ? boardSymbols : null
  const scopeNotReady = isBoard && snapshotQ.isLoading

  if (!open) return null

  // 生效窗口: 自定义天数(合法时)优先于预设
  const customParsed = Number(customDays)
  const customValid = customDays !== '' && Number.isFinite(customParsed)
    && customParsed >= CUSTOM_MIN && customParsed <= CUSTOM_MAX
  const effectiveDays = customValid ? Math.round(customParsed) : windowDays
  const windowLabel = customValid ? `近${effectiveDays}天` : (WINDOW_PRESETS.find(w => w.days === windowDays)?.label ?? '')

  const start = () => {
    if (running || strategyIds.length === 0) return
    if (customDays !== '' && !customValid) {
      toast(`自定义天数需在 ${CUSTOM_MIN}~${CUSTOM_MAX} 之间`, 'error')
      return
    }
    if (isBoard && boardSymbols.length === 0) {
      toast('板块清单为空(全市场快照未就绪), 请稍后再试', 'error')
      return
    }
    cancelRef.current = false
    setChat([]); setOpenId(null)
    setRunning(true)
    const init: HealthRow[] = strategyIds.map(id => ({ id, name: nameOf(id), status: 'pending' }))
    setRows(init)
    const end = new Date()
    const from = new Date(end.getTime() - effectiveDays * 86400_000)
    const iso = (d: Date) => d.toISOString().slice(0, 10)
    ;(async () => {
      for (let i = 0; i < strategyIds.length; i++) {
        if (cancelRef.current) break
        const id = strategyIds[i]
        setRows(prev => prev.map(r => r.id === id ? { ...r, status: 'running' } : r))
        try {
          // 只传 strategy_id + 区间(+可选股票池), 其余用服务端默认(次日开盘/等权/费率)+ 策略自带交易参数
          const res = await api.strategyBacktestRun({
            strategy_id: id, start: iso(from), end: iso(end),
            symbols: scopeSymbols && scopeSymbols.length > 0 ? scopeSymbols : undefined,
          })
          const s = res.stats ?? {}
          // 详情/诊断素材: 出场原因分布(死因证据) + 同期基准收益(区分策略问题/环境问题)
          const byReason = new Map<string, { count: number; sum: number }>()
          for (const t of res.trades ?? []) {
            const k = t.exit_reason || 'unknown'
            const d = byReason.get(k) ?? { count: 0, sum: 0 }
            d.count += 1; d.sum += t.pnl_pct; byReason.set(k, d)
          }
          const exitReasons: ExitReasonAgg[] = [...byReason.entries()]
            .map(([reason, d]) => ({ reason, count: d.count, avg_pnl: +(d.sum / d.count).toFixed(4) }))
            .sort((a, b) => b.count - a.count)
          const bc = res.benchmark_curve ?? []
          const benchmarkReturn = bc.length >= 2 && bc[0].value
            ? +((bc[bc.length - 1].value / bc[0].value) - 1).toFixed(4) : null
          setRows(prev => prev.map(r => r.id === id ? {
            ...r, status: 'done',
            win_rate: s.win_rate ?? null,
            profit_factor: s.profit_factor ?? null,
            total_return: s.total_return ?? null,
            max_drawdown: s.max_drawdown ?? null,
            n_trades: s.n_trades ?? null,
            avg_pnl: s.avg_pnl ?? null,
            diagConfig: (res.strategy_info ?? {}) as Record<string, unknown>,
            diagStats: s as Record<string, unknown>,
            exitReasons,
            benchmarkReturn,
          } : r))
        } catch (e) {
          setRows(prev => prev.map(r => r.id === id ? {
            ...r, status: 'error', error: String((e as Error)?.message || '回测失败'),
          } : r))
        }
      }
      setRunning(false)
    })()
  }

  const doneRows = rows.filter(r => r.status === 'done')
  // 展示排序: 胜率降序, 样本不足/失败垫底
  const sorted = [...rows].sort((a, b) => {
    const av = a.status === 'done' && (a.n_trades ?? 0) >= MIN_TRADES ? (a.win_rate ?? -1) : -2
    const bv = b.status === 'done' && (b.n_trades ?? 0) >= MIN_TRADES ? (b.win_rate ?? -1) : -2
    return bv - av
  })

  const scopeLabel = scope === 'market' ? '全市场' : scope === 'watchlist' ? `仅自选(${watchlistSymbols.length}只)` : scope

  // 单策略 AI 诊断: 配置+指标+出场原因分布+基准收益 → 死因归析与具体改法(结果进详情面板)
  const diagnose = async (row: HealthRow) => {
    if (diagLoadingId) return
    setOpenId(row.id)
    if (row.diagText) return
    setDiagLoadingId(row.id)
    try {
      const res = await api.backtestDiagnose({
        name: row.name,
        window_label: windowLabel,
        scope_label: scopeLabel,
        config: row.diagConfig ?? {},
        stats: row.diagStats ?? {},
        exit_reasons: row.exitReasons ?? [],
        benchmark_return: row.benchmarkReturn ?? null,
      })
      setRows(prev => prev.map(r => r.id === row.id ? { ...r, diagText: res.text } : r))
    } catch (e) {
      toast(String((e as Error)?.message || 'AI 诊断失败'), 'error')
    } finally {
      setDiagLoadingId(null)
    }
  }

  // AI 解读(多轮): 首轮 messages 空 = 完整解读; 之后带对话历史继续追问
  const tablePayload = () => doneRows.map(r => ({
    name: r.name, win_rate: r.win_rate, profit_factor: r.profit_factor,
    total_return: r.total_return, max_drawdown: r.max_drawdown,
    n_trades: r.n_trades, avg_pnl: r.avg_pnl,
  }))
  const interpret = async () => {
    if (aiLoading || doneRows.length === 0) return
    setAiLoading(true)
    try {
      const res = await api.backtestHealthInterpret(tablePayload(), windowLabel)
      setChat([{ role: 'assistant', content: res.text }])
    } catch (e) {
      toast(String((e as Error)?.message || 'AI 解读失败'), 'error')
    } finally {
      setAiLoading(false)
    }
  }
  const ask = async () => {
    const q = question.trim()
    if (!q || aiLoading || doneRows.length === 0) return
    setQuestion('')
    const next: ChatMsg[] = [...chat, { role: 'user', content: q }]
    setChat(next)
    setAiLoading(true)
    try {
      const res = await api.backtestHealthInterpret(tablePayload(), windowLabel, next)
      setChat([...next, { role: 'assistant', content: res.text }])
    } catch (e) {
      toast(String((e as Error)?.message || 'AI 追问失败'), 'error')
    } finally {
      setAiLoading(false)
    }
  }

  const tryClose = () => {
    if (running) { cancelRef.current = true; setRunning(false) }
    onClose()
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/55 p-4 backdrop-blur-sm" onClick={tryClose}>
      <div role="dialog" aria-modal="true" className="flex max-h-[88vh] w-full max-w-3xl flex-col overflow-hidden rounded-lg border border-border bg-surface shadow-2xl" onClick={e => e.stopPropagation()}>
        <header className="flex flex-wrap items-center gap-2.5 border-b border-border/60 px-5 py-3.5">
          <span className="grid h-8 w-8 shrink-0 place-items-center rounded-md border border-emerald-400/25 bg-emerald-400/10 text-emerald-400">
            <Activity className="h-4 w-4" />
          </span>
          <div className="flex-1 min-w-[180px]">
            <h2 className="text-sm font-medium text-foreground">策略体检</h2>
            <p className="text-[11px] text-muted">策略池零配置批量回测 · 点策略名看详情 · 各策略用自己的交易参数</p>
          </div>
          {/* 范围 + 窗口(预设/自定义) + 开始 */}
          <div className="flex flex-wrap items-center gap-1.5">
            <select
              value={scope}
              onChange={e => setScope(e.target.value as typeof scope)}
              disabled={running}
              title="回测股票池范围: 全市场(作者默认) / 仅自选(注意选择偏差) / 按板块"
              className="h-[26px] rounded border border-border bg-base px-1.5 text-[11px] text-foreground focus:outline-none focus:border-emerald-400/50 disabled:opacity-50 cursor-pointer"
            >
              <option value="market">全市场</option>
              <option value="watchlist" disabled={watchlistSymbols.length === 0}>仅自选{watchlistSymbols.length ? ` (${watchlistSymbols.length})` : ''}</option>
              {BOARDS.map(b => <option key={b} value={b}>{b}</option>)}
            </select>
            <span className="mx-0.5 h-4 w-px bg-border/60" />
            {WINDOW_PRESETS.map(w => (
              <button key={w.days} onClick={() => { setWindowDays(w.days); setCustomDays('') }} disabled={running}
                className={`text-[11px] px-2 py-1 rounded border transition-colors cursor-pointer disabled:opacity-50 ${
                  !customValid && windowDays === w.days ? 'border-accent/50 bg-accent/10 text-accent' : 'border-border bg-base text-muted hover:text-foreground'
                }`}>{w.label}</button>
            ))}
            <label className={`flex items-center gap-1 text-[11px] ${customValid ? 'text-accent' : 'text-muted'}`}>
              自定义
              <input
                type="number" min={CUSTOM_MIN} max={CUSTOM_MAX} placeholder="天"
                value={customDays}
                onChange={e => setCustomDays(e.target.value)}
                disabled={running}
                title={`自定义回测天数(${CUSTOM_MIN}~${CUSTOM_MAX});填了就优先于预设`}
                className={`h-[26px] w-14 rounded border bg-base px-1.5 text-[11px] text-right font-mono text-foreground focus:outline-none disabled:opacity-50 ${
                  customValid ? 'border-accent/50' : customDays !== '' ? 'border-danger/60' : 'border-border'
                }`}
              />
              天
            </label>
            <button onClick={start} disabled={running || strategyIds.length === 0 || scopeNotReady}
              className="inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-btn bg-accent/15 border border-accent/40 text-accent hover:bg-accent/25 disabled:opacity-50 transition-colors cursor-pointer">
              {(running || scopeNotReady) ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Activity className="h-3.5 w-3.5" />}
              {scopeNotReady ? '加载板块清单…' : running ? `体检中 ${rows.filter(r => r.status === 'done' || r.status === 'error').length}/${rows.length}` : '开始体检'}
            </button>
          </div>
          <button onClick={tryClose} className="text-muted hover:text-foreground transition-colors cursor-pointer"><X className="h-4 w-4" /></button>
        </header>

        <div className="flex-1 overflow-auto p-5 space-y-4">
          {rows.length === 0 ? (
            <div className="py-10 text-center text-sm text-muted">
              将对策略池 {strategyIds.length} 个策略逐个回测(约每个 10~30 秒),出胜率对比表。<br />
              <span className="text-[11px] text-muted/60">零配置:选好范围与时间窗口点「开始体检」;各策略使用你在策略设置里配的止损/持有/触发器。</span>
            </div>
          ) : (
            <table className="w-full text-xs">
              <thead className="text-[10px] text-muted">
                <tr className="text-left border-b border-border/40">
                  <th className="py-1.5 pr-2 font-normal">策略(点击看详情)</th>
                  <th className="py-1.5 px-2 font-normal text-right">胜率</th>
                  <th className="py-1.5 px-2 font-normal text-right">盈亏比</th>
                  <th className="py-1.5 px-2 font-normal text-right" title="模拟组合的期末净值相对期初的涨跌(见详情面板「这些数字怎么来的」)">区间收益</th>
                  <th className="py-1.5 px-2 font-normal text-right">最大回撤</th>
                  <th className="py-1.5 px-2 font-normal text-right">笔数</th>
                  <th className="py-1.5 pl-2 font-normal">状态</th>
                </tr>
              </thead>
              <tbody>
                {sorted.map(r => {
                  const lowSample = r.status === 'done' && (r.n_trades ?? 0) < MIN_TRADES
                  const expanded = openId === r.id
                  const cfg = r.diagConfig ?? {}
                  const st = r.diagStats ?? {}
                  return (
                    <Fragment key={r.id}>
                    <tr className={`border-b border-border/20 ${lowSample ? 'opacity-55' : ''}`}>
                      <td className="py-2 pr-2">
                        <button
                          onClick={() => r.status === 'done' && setOpenId(expanded ? null : r.id)}
                          disabled={r.status !== 'done'}
                          className="inline-flex items-center gap-1 text-foreground hover:text-emerald-300 disabled:hover:text-foreground transition-colors cursor-pointer disabled:cursor-default text-left"
                          title={r.status === 'done' ? '展开: 完整指标 / 出场原因分布 / 收益口径 / AI 诊断' : undefined}
                        >
                          {r.status === 'done' && (expanded
                            ? <ChevronDown className="h-3 w-3 text-muted shrink-0" />
                            : <ChevronRight className="h-3 w-3 text-muted shrink-0" />)}
                          {r.name}
                        </button>
                      </td>
                      <td className={`py-2 px-2 text-right font-mono tabular-nums ${(r.win_rate ?? 0) >= 0.5 ? 'text-red-400' : 'text-muted'}`}>{r.status === 'done' ? pct(r.win_rate) : '—'}</td>
                      <td className="py-2 px-2 text-right font-mono tabular-nums text-muted">{r.status === 'done' ? (r.profit_factor ?? '—') : '—'}</td>
                      <td className={`py-2 px-2 text-right font-mono tabular-nums ${(r.total_return ?? 0) > 0 ? 'text-red-400' : (r.total_return ?? 0) < 0 ? 'text-emerald-400' : 'text-muted'}`}>{r.status === 'done' ? pct(r.total_return) : '—'}</td>
                      <td className="py-2 px-2 text-right font-mono tabular-nums text-emerald-400/80">{r.status === 'done' ? pct(r.max_drawdown) : '—'}</td>
                      <td className="py-2 px-2 text-right font-mono tabular-nums text-muted">{r.n_trades ?? '—'}</td>
                      <td className="py-2 pl-2">
                        {r.status === 'pending' && <span className="text-[10px] text-muted/50">排队</span>}
                        {r.status === 'running' && <span className="inline-flex items-center gap-1 text-[10px] text-accent"><Loader2 className="h-2.5 w-2.5 animate-spin" />回测中</span>}
                        {r.status === 'done' && (
                          <span className="inline-flex items-center gap-1.5">
                            {lowSample
                              ? <span className="inline-flex items-center gap-1 text-[10px] text-warning/80" title={`交易仅 ${r.n_trades} 笔(<${MIN_TRADES}), 胜率统计意义不足`}><AlertTriangle className="h-2.5 w-2.5" />样本不足</span>
                              : <span className="text-[10px] text-emerald-400/80">✓</span>}
                            {(r.n_trades ?? 0) > 0 && (
                              <button onClick={() => diagnose(r)} disabled={diagLoadingId !== null && diagLoadingId !== r.id}
                                title="AI 诊断: 结合配置/出场原因分布/基准收益, 归析亏损死因并给具体参数改法"
                                className="inline-flex items-center gap-0.5 text-[10px] px-1.5 py-0.5 rounded border border-sky-400/30 bg-sky-400/10 text-sky-300 hover:bg-sky-400/20 disabled:opacity-40 transition-colors cursor-pointer">
                                {diagLoadingId === r.id ? <Loader2 className="h-2.5 w-2.5 animate-spin" /> : <Sparkles className="h-2.5 w-2.5" />}
                                诊断
                              </button>
                            )}
                          </span>
                        )}
                        {r.status === 'error' && <span className="text-[10px] text-danger" title={r.error}>失败</span>}
                      </td>
                    </tr>
                    {/* ===== 详情面板: 完整指标 / 出场原因分布 / 收益口径 / AI 诊断 ===== */}
                    {expanded && r.status === 'done' && (
                      <tr>
                        <td colSpan={7} className="px-3 pb-3 pt-1">
                          <div className="rounded-lg border border-border/50 bg-elevated/20 px-4 py-3 space-y-3">
                            {/* 完整指标 */}
                            <div className="grid grid-cols-4 gap-x-6 gap-y-1.5 text-[11px]">
                              {[
                                ['年化收益', pct(st.annual_return as number)],
                                ['同期基准', pct(r.benchmarkReturn)],
                                ['超额收益', r.total_return != null && r.benchmarkReturn != null ? pct(r.total_return - r.benchmarkReturn) : '—'],
                                ['夏普比率', num(st.sharpe)],
                                ['平均盈利', pct(st.avg_win as number)],
                                ['平均亏损', pct(st.avg_loss as number)],
                                ['平均单笔', pct(r.avg_pnl)],
                                ['卡玛比率', num(st.calmar)],
                              ].map(([k, v]) => (
                                <div key={k as string} className="flex justify-between gap-2">
                                  <span className="text-muted">{k}</span>
                                  <span className="font-mono tabular-nums text-foreground">{v}</span>
                                </div>
                              ))}
                            </div>
                            {/* 出场原因分布 */}
                            {(r.exitReasons?.length ?? 0) > 0 && (
                              <div>
                                <div className="text-[10px] text-muted mb-1">出场原因分布(亏损死因看这里)</div>
                                <div className="flex flex-wrap gap-1.5">
                                  {r.exitReasons!.map(er => (
                                    <span key={er.reason} className={`text-[10px] px-1.5 py-0.5 rounded border ${er.avg_pnl < 0 ? 'border-emerald-400/30 bg-emerald-400/5 text-emerald-300' : 'border-red-400/30 bg-red-400/5 text-red-300'}`}>
                                      {EXIT_LABEL[er.reason] ?? er.reason} · {er.count}笔 · 均{pct(er.avg_pnl)}
                                    </span>
                                  ))}
                                </div>
                              </div>
                            )}
                            {/* 收益口径说明 */}
                            <div className="text-[10px] text-muted/70 leading-relaxed border-t border-border/30 pt-2">
                              <span className="text-muted">这些数字怎么来的:</span>
                              模拟一个组合——初始资金 100 万、最多 10 仓等权;策略每日选股命中后<span className="text-secondary">次日开盘价买入</span>,
                              按该策略自己的交易参数卖出(止损 {cfg.stop_loss != null ? pct(cfg.stop_loss as number) : '未设'} /
                              持有上限 {cfg.max_hold_days != null ? `${cfg.max_hold_days}天` : '未设'} / 出场触发器 {Array.isArray(cfg.exit_signals) && cfg.exit_signals.length ? (cfg.exit_signals as string[]).join('、') : '无'}),
                              全程计佣金/印花税/滑点。<span className="text-secondary">区间收益 = 期末组合净值相对期初的涨跌</span>;
                              基准为同期指数。想看净值曲线和逐笔明细,去回测页选同一策略。
                            </div>
                            {/* AI 诊断 */}
                            {(r.diagText || diagLoadingId === r.id) && (
                              <div className="rounded-lg border border-sky-400/20 bg-sky-400/[0.04] px-3 py-2.5 text-xs leading-relaxed text-secondary whitespace-pre-wrap">
                                {r.diagText || 'AI 诊断中…'}
                              </div>
                            )}
                          </div>
                        </td>
                      </tr>
                    )}
                    </Fragment>
                  )
                })}
              </tbody>
            </table>
          )}

          {/* AI 解读(多轮对话, 可追问) */}
          {doneRows.length > 0 && !running && (
            <div className="space-y-2">
              {chat.length === 0 ? (
                <button onClick={interpret} disabled={aiLoading}
                  className="inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-btn border border-sky-400/30 bg-sky-400/10 text-sky-300 hover:bg-sky-400/20 disabled:opacity-50 transition-colors cursor-pointer">
                  {aiLoading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Sparkles className="h-3.5 w-3.5" />}
                  {aiLoading ? 'AI 解读中…' : 'AI 解读(留谁/调谁/怎么调)'}
                </button>
              ) : (
                <div className="space-y-2">
                  {chat.map((m, i) => (
                    <div key={i} className={m.role === 'assistant'
                      ? 'rounded-lg border border-border/60 bg-elevated/30 px-4 py-3 text-xs leading-relaxed text-secondary whitespace-pre-wrap'
                      : 'rounded-lg border border-sky-400/25 bg-sky-400/[0.06] px-4 py-2 text-xs text-sky-200 ml-10'}>
                      {m.content}
                    </div>
                  ))}
                  {aiLoading && (
                    <div className="flex items-center gap-1.5 text-[11px] text-muted"><Loader2 className="h-3 w-3 animate-spin" />AI 思考中…</div>
                  )}
                </div>
              )}
              {chat.length > 0 && (
                <div className="flex items-center gap-2">
                  <input
                    value={question}
                    onChange={e => setQuestion(e.target.value)}
                    onKeyDown={e => { if (e.key === 'Enter') ask() }}
                    disabled={aiLoading}
                    placeholder="继续追问, 如: 为什么布林突破盈亏比这么低? 止损改多少合适?"
                    className="flex-1 h-8 rounded-lg border border-border bg-base px-3 text-xs text-foreground placeholder:text-muted/50 focus:outline-none focus:border-sky-400/50 disabled:opacity-50"
                  />
                  <button onClick={ask} disabled={aiLoading || !question.trim()}
                    className="inline-flex items-center gap-1 h-8 px-3 rounded-lg border border-sky-400/30 bg-sky-400/10 text-sky-300 text-xs hover:bg-sky-400/20 disabled:opacity-40 transition-colors cursor-pointer">
                    <Send className="h-3 w-3" />
                    追问
                  </button>
                </div>
              )}
            </div>
          )}

          <p className="text-[10px] text-muted/50 leading-relaxed">
            说明:结果是「当前策略代码回放历史」的模拟胜率(次日开盘成交,含费率/滑点),调参后历史成绩会变;样本 &lt;{MIN_TRADES} 笔的行已灰显,勿作依据。
            「仅自选」模式是把今天的自选回放到历史上,存在选择偏差,成绩会系统性偏乐观,只宜横向比较策略、不宜当收益预期。
          </p>
        </div>
      </div>
    </div>
  )
}
