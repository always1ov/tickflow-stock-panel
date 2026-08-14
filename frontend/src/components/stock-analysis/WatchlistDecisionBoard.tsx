import { useState, useMemo, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { ChevronDown, Star, Wallet, Sparkles, Loader2, ArrowUp, ArrowDown, RefreshCw, FileText } from 'lucide-react'
import { api } from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import { toast } from '@/components/Toast'
import { useHistoryReports, openHistoryReport, loadHistory } from '@/lib/stockAnalysisStore'

type Position = { held: boolean; cost: number | null; updated_at: string }
type Signal = { signal: string; confidence: number; reason: string; close: number | null; created_at: string }
type SortKey = 'name' | 'close' | 'changePct' | 'held' | 'pnl' | 'confidence' | 'signal' | 'report'
const SIGNAL_RANK: Record<string, number> = { buy: 0, sell: 1, hold: 2, watch: 3 }

// AI 信号 → 展示标签/配色。买入=红(A股涨红), 卖出=绿, 持有=琥珀, 观望=灰。
const SIGNAL_META: Record<string, { label: string; cls: string }> = {
  buy: { label: '买入', cls: 'border-red-400/40 bg-red-400/10 text-red-400' },
  sell: { label: '卖出', cls: 'border-emerald-400/40 bg-emerald-400/10 text-emerald-400' },
  hold: { label: '持有', cls: 'border-amber-400/40 bg-amber-400/10 text-amber-400' },
  watch: { label: '观望', cls: 'border-border bg-base text-muted' },
}

function fmtAgo(iso?: string): string {
  if (!iso) return ''
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000)
  if (s < 60) return '刚刚'
  if (s < 3600) return `${Math.floor(s / 60)}分前`
  if (s < 86400) return `${Math.floor(s / 3600)}小时前`
  return `${Math.floor(s / 86400)}天前`
}

/** 自选决策台 —— 一行一只自选:点行即切换分析(免搜索)、标记仓位/成本、纵观对比浮盈。
 *  AI 买卖信号列为 P2,后续接入(留位)。 */
export function WatchlistDecisionBoard({ currentSymbol, onSelect }: {
  currentSymbol: string
  onSelect: (symbol: string, name: string) => void
}) {
  const qc = useQueryClient()
  const [open, setOpen] = useState(true)
  const [heldOnly, setHeldOnly] = useState(false)
  // 排序:默认按置信度降序(信号最强的排前面;未分析的始终垫底)
  const [sort, setSort] = useState<{ key: SortKey; dir: 'asc' | 'desc' }>({ key: 'confidence', dir: 'desc' })
  const toggleSort = (key: SortKey) =>
    setSort((s) => (s.key === key ? { key, dir: s.dir === 'asc' ? 'desc' : 'asc' } : { key, dir: key === 'name' ? 'asc' : 'desc' }))
  const caret = (key: SortKey) =>
    sort.key === key ? (sort.dir === 'asc' ? <ArrowUp className="h-2.5 w-2.5" /> : <ArrowDown className="h-2.5 w-2.5" />) : null
  const thBtn = 'inline-flex items-center gap-0.5 hover:text-foreground cursor-pointer'

  const enriched = useQuery({
    queryKey: QK.watchlistEnriched(),
    queryFn: () => api.watchlistEnriched(),
    staleTime: 30_000,
  })
  const positionsQ = useQuery({
    queryKey: ['watchlist-positions'],
    queryFn: () => api.watchlistPositions(),
    staleTime: 30_000,
  })
  const positions = positionsQ.data?.positions ?? {}

  const signalsQ = useQuery({
    queryKey: ['stock-signals'],
    queryFn: () => api.stockSignals(),
    staleTime: 30_000,
  })
  const signals = signalsQ.data?.signals ?? {}

  // 历史报告整合: 每只自选显示最近一份 AI 分析报告(时间+份数), 点击直接打开报告弹窗。
  // 数据来自 stockAnalysisStore(个股分析页挂载时已 loadHistory, 此处再调一次是安全去重)。
  const { reports } = useHistoryReports()
  useEffect(() => { loadHistory() }, [])
  const reportsBySymbol = useMemo(() => {
    const m = new Map<string, { latest: (typeof reports)[number]; count: number }>()
    for (const r of reports) {  // reports 已按 created_at 降序 → 首见即最新
      const cur = m.get(r.symbol)
      if (cur) cur.count += 1
      else m.set(r.symbol, { latest: r, count: 1 })
    }
    return m
  }, [reports])

  // 手动刷新:重新拉取行情/仓位/信号(不调用 AI、不计费)。盘中本就 SSE 自动刷新,
  // 这个按钮主要给收盘后/关闭实时时,想一键看最新盘后快照用。
  const refreshing = enriched.isFetching || positionsQ.isFetching || signalsQ.isFetching
  const refreshAll = () => {
    qc.invalidateQueries({ queryKey: QK.watchlistEnriched() })
    qc.invalidateQueries({ queryKey: ['watchlist-positions'] })
    qc.invalidateQueries({ queryKey: ['stock-signals'] })
  }

  const setPos = useMutation({
    mutationFn: ({ symbol, held, cost }: { symbol: string; held: boolean; cost: number | null }) =>
      api.setWatchlistPosition(symbol, held, cost),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['watchlist-positions'] }),
  })

  // 「分析全部/持有」—— 逐只并发(限 3)调用信号接口, 每完成一只即刷新, 显示进度。
  const [progress, setProgress] = useState<{ done: number; total: number } | null>(null)
  const runBatch = async (syms: string[]) => {
    if (progress) return
    if (!syms.length) {
      // 静默 return 会让按钮看起来"点了没反应" —— 空列表必须说明原因
      toast('没有可分析的标的:行情数据未就绪或自选为空(只看持有时需先标记持有)', 'error')
      return
    }
    setProgress({ done: 0, total: syms.length })
    let done = 0
    let failed = 0
    let firstErr = ''
    let idx = 0
    const worker = async () => {
      while (idx < syms.length) {
        const s = syms[idx++]
        try {
          // 注意: 后端信号接口失败时返回 200 + {error} 而非抛 HTTP 错误,
          // 必须检查响应体 —— 否则 AI 挂掉时(如 503)整批"成功"但信号纹丝不动
          const res = await api.generateStockSignal(s)
          if (res?.error) {
            failed++
            if (!firstErr) firstErr = res.error
          }
        } catch (e: any) {
          // 单只失败不阻断, 但必须计数并保留首个错误 —— 全军覆没时(如 AI Key
          // 失效/未配置)若静默吞掉, 用户看到的就是"点了没反应"
          failed++
          if (!firstErr) firstErr = e?.message ?? String(e)
        }
        done++
        setProgress({ done, total: syms.length })
        qc.invalidateQueries({ queryKey: ['stock-signals'] })
      }
    }
    await Promise.all(Array.from({ length: Math.min(3, syms.length) }, () => worker()))
    setProgress(null)
    qc.invalidateQueries({ queryKey: ['stock-signals'] })
    if (failed) {
      toast(
        `AI 分析完成:成功 ${syms.length - failed} 只,失败 ${failed} 只${firstErr ? ` — ${firstErr}` : ''}`,
        failed === syms.length ? 'error' : 'success',
      )
    }
  }
  const allSyms = () => (enriched.data?.rows ?? []).map((r: any) => String(r.symbol))
  const runAll = () => runBatch(allSyms())
  // 只分析标记为「持有」的自选 —— 省 AI 调用, 持仓优先
  const runHeld = () => runBatch(allSyms().filter((sym: string) => positions[sym]?.held))

  const rows = useMemo(() => {
    const src = enriched.data?.rows ?? []
    return src
      .map((r: any) => {
        const symbol = String(r.symbol)
        const pos: Position | undefined = positions[symbol]
        const sig: Signal | undefined = signals[symbol]
        const close = typeof r.close === 'number' ? r.close : null
        const cost = pos?.cost ?? null
        const pnl = pos?.held && cost && cost > 0 && close != null ? (close - cost) / cost : null
        return { symbol, name: r.name ?? symbol, close, changePct: r.change_pct ?? null, held: !!pos?.held, cost, pnl, sig }
      })
      .filter((r) => (heldOnly ? r.held : true))
  }, [enriched.data, positions, signals, heldOnly])

  const sortedRows = useMemo(() => {
    const val = (r: (typeof rows)[number]): string | number | null => {
      switch (sort.key) {
        case 'name': return r.name
        case 'close': return r.close
        case 'changePct': return r.changePct
        case 'held': return r.held ? 1 : 0
        case 'pnl': return r.pnl
        case 'confidence': return r.sig?.confidence ?? null
        case 'signal': return r.sig ? (SIGNAL_RANK[r.sig.signal] ?? 9) : null
        case 'report': {
          const rep = reportsBySymbol.get(r.symbol)
          return rep ? new Date(rep.latest.created_at).getTime() : null
        }
      }
    }
    const arr = [...rows]
    arr.sort((a, b) => {
      const av = val(a), bv = val(b)
      if (av == null && bv == null) return 0
      if (av == null) return 1  // 空值(未分析/无数据)始终垫底
      if (bv == null) return -1
      const c = typeof av === 'string' ? av.localeCompare(String(bv)) : (av as number) - (bv as number)
      return sort.dir === 'asc' ? c : -c
    })
    return arr
  }, [rows, sort, reportsBySymbol])

  const heldCount = Object.values(positions).filter((p) => p.held).length

  return (
    <div className="rounded-xl border border-border/60 bg-surface/40 overflow-hidden">
      <div className="flex items-center gap-2 px-4 py-2.5">
        <button onClick={() => setOpen((v) => !v)} className="flex items-center gap-2 cursor-pointer">
          <ChevronDown className={`h-3.5 w-3.5 text-muted transition-transform ${open ? '' : '-rotate-90'}`} />
          <Wallet className="h-3.5 w-3.5 text-sky-400" />
          <span className="text-xs font-medium text-foreground">自选决策台</span>
          <span className="text-[10px] text-muted">{rows.length} 只 · 持有 {heldCount}</span>
        </button>
        <button
          onClick={refreshAll}
          disabled={refreshing}
          title="刷新行情/仓位/信号快照(不调用 AI、不计费)"
          className="ml-auto inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full border border-border bg-base text-muted hover:text-foreground disabled:opacity-60 transition-colors cursor-pointer"
        >
          <RefreshCw className={`h-3 w-3 ${refreshing ? 'animate-spin' : ''}`} />
          刷新
        </button>
        <button
          onClick={() => setHeldOnly((v) => !v)}
          className={`text-[10px] px-2 py-0.5 rounded-full border transition-colors cursor-pointer ${
            heldOnly ? 'border-accent/40 bg-accent/10 text-accent' : 'border-border bg-base text-muted hover:text-foreground'
          }`}
        >
          只看持有
        </button>
        {heldCount > 0 && (
          <button
            onClick={runHeld}
            disabled={!!progress}
            title="只对标记为「持有」的自选生成 AI 买卖信号(省调用, 持仓优先)"
            className="inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full border border-amber-400/30 bg-amber-400/10 text-amber-300 hover:bg-amber-400/20 disabled:opacity-60 transition-colors cursor-pointer"
          >
            {progress ? <Loader2 className="h-3 w-3 animate-spin" /> : <Sparkles className="h-3 w-3" />}
            AI 分析持有
          </button>
        )}
        <button
          onClick={runAll}
          disabled={!!progress}
          title="对全部自选逐只生成 AI 买卖信号(会调用 AI,按只计费)"
          className="inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full border border-sky-400/30 bg-sky-400/10 text-sky-300 hover:bg-sky-400/20 disabled:opacity-60 transition-colors cursor-pointer"
        >
          {progress ? <Loader2 className="h-3 w-3 animate-spin" /> : <Sparkles className="h-3 w-3" />}
          {progress ? `分析中 ${progress.done}/${progress.total}` : 'AI 分析全部'}
        </button>
      </div>

      {open && (
        <div className="max-h-[280px] overflow-auto border-t border-border/60">
          <table className="w-full min-w-[720px] text-xs">
            <thead className="sticky top-0 bg-surface/95 backdrop-blur text-[10px] text-muted">
              <tr className="text-left">
                <th className="px-4 py-1.5 font-normal"><button onClick={() => toggleSort('name')} className={thBtn}>标的{caret('name')}</button></th>
                <th className="px-2 py-1.5 font-normal text-right"><button onClick={() => toggleSort('close')} className={thBtn}>现价{caret('close')}</button></th>
                <th className="px-2 py-1.5 font-normal text-right"><button onClick={() => toggleSort('changePct')} className={thBtn}>涨跌{caret('changePct')}</button></th>
                <th className="px-2 py-1.5 font-normal text-center"><button onClick={() => toggleSort('held')} className={thBtn}>仓位{caret('held')}</button></th>
                <th className="px-2 py-1.5 font-normal text-right">成本</th>
                <th className="px-2 py-1.5 font-normal text-right"><button onClick={() => toggleSort('pnl')} className={thBtn}>浮盈{caret('pnl')}</button></th>
                <th className="px-2 py-1.5 font-normal text-right"><button onClick={() => toggleSort('confidence')} className={thBtn}>置信{caret('confidence')}</button></th>
                <th className="px-2 py-1.5 font-normal text-center"><button onClick={() => toggleSort('report')} className={thBtn} title="最近一份 AI 分析报告(点击单元格直接打开)">报告{caret('report')}</button></th>
                <th className="px-4 py-1.5 font-normal text-left"><button onClick={() => toggleSort('signal')} className={thBtn}>AI 信号{caret('signal')}</button></th>
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 ? (
                <tr><td colSpan={9} className="px-4 py-6 text-center text-muted">自选为空 —— 去自选页添加标的</td></tr>
              ) : sortedRows.map((r) => {
                const active = r.symbol === currentSymbol
                const up = (r.changePct ?? 0) > 0
                const down = (r.changePct ?? 0) < 0
                return (
                  <tr key={r.symbol} className={`border-t border-border/30 hover:bg-elevated/40 ${active ? 'bg-accent/[0.06]' : ''}`}>
                    {/* 点标的即切换分析(免搜索) */}
                    <td className="px-4 py-1.5">
                      <button onClick={() => onSelect(r.symbol, r.name)} className="flex items-center gap-1.5 text-left cursor-pointer group">
                        {active && <Star className="h-2.5 w-2.5 text-accent shrink-0" />}
                        <span className="font-medium text-foreground group-hover:text-sky-300 transition-colors truncate max-w-[110px]">{r.name}</span>
                        <span className="text-[9px] font-mono text-muted">{r.symbol}</span>
                      </button>
                    </td>
                    <td className="px-2 py-1.5 text-right font-mono tabular-nums text-foreground">{r.close != null ? r.close.toFixed(2) : '—'}</td>
                    <td className={`px-2 py-1.5 text-right font-mono tabular-nums ${up ? 'text-red-400' : down ? 'text-emerald-400' : 'text-muted'}`}>
                      {r.changePct != null ? `${(r.changePct * 100).toFixed(2)}%` : '—'}
                    </td>
                    {/* 仓位:持有/空仓 切换 */}
                    <td className="px-2 py-1.5 text-center">
                      <button
                        onClick={() => setPos.mutate({ symbol: r.symbol, held: !r.held, cost: r.cost })}
                        className={`text-[10px] px-1.5 py-0.5 rounded border transition-colors cursor-pointer ${
                          r.held ? 'border-amber-400/40 bg-amber-400/10 text-amber-400' : 'border-border bg-base text-muted hover:border-amber-400/30'
                        }`}
                      >
                        {r.held ? '持有' : '空仓'}
                      </button>
                    </td>
                    {/* 成本:仅持有时可填 */}
                    <td className="px-2 py-1.5 text-right">
                      {r.held ? (
                        <input
                          type="number"
                          defaultValue={r.cost ?? ''}
                          placeholder="成本"
                          onBlur={(e) => {
                            const v = e.target.value === '' ? null : Number(e.target.value)
                            if (v !== r.cost) setPos.mutate({ symbol: r.symbol, held: true, cost: v })
                          }}
                          className="w-16 h-6 px-1 rounded bg-base border border-border text-[11px] font-mono text-right text-foreground focus:outline-none focus:border-accent/50"
                        />
                      ) : <span className="text-muted">—</span>}
                    </td>
                    {/* 浮盈 */}
                    <td className={`px-2 py-1.5 text-right font-mono tabular-nums ${r.pnl == null ? 'text-muted' : r.pnl > 0 ? 'text-red-400' : r.pnl < 0 ? 'text-emerald-400' : 'text-muted'}`}>
                      {r.pnl != null ? `${(r.pnl * 100).toFixed(1)}%` : '—'}
                    </td>
                    {/* 置信度(独立列, 可排序) */}
                    <td className="px-2 py-1.5 text-right font-mono tabular-nums text-muted">
                      {r.sig ? `${r.sig.confidence}%` : '—'}
                    </td>
                    {/* 历史报告: 最近一份的时间(+份数), 点击直接打开报告弹窗 */}
                    <td className="px-2 py-1.5 text-center">
                      {(() => {
                        const rep = reportsBySymbol.get(r.symbol)
                        if (!rep) return <span className="text-[10px] text-muted/40">—</span>
                        return (
                          <button
                            onClick={() => openHistoryReport(rep.latest.id)}
                            title={`打开最近报告(${new Date(rep.latest.created_at).toLocaleString()})${rep.count > 1 ? ` · 共 ${rep.count} 份` : ''}`}
                            className="inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded border border-violet-400/30 bg-violet-400/10 text-violet-300 hover:bg-violet-400/20 transition-colors cursor-pointer"
                          >
                            <FileText className="h-2.5 w-2.5" />
                            {fmtAgo(rep.latest.created_at)}
                            {rep.count > 1 && <span className="text-violet-300/60">·{rep.count}</span>}
                          </button>
                        )
                      })()}
                    </td>
                    {/* AI 信号:徽标 + 时间 + 理由整段换行(不截断) */}
                    <td className="px-4 py-1.5 min-w-[240px] align-top">
                      {r.sig ? (
                        <div className="flex flex-col gap-0.5">
                          <div className="flex items-center gap-1.5">
                            <span className={`text-[10px] px-1.5 py-0.5 rounded border ${SIGNAL_META[r.sig.signal]?.cls ?? 'border-border text-muted'}`}>
                              {SIGNAL_META[r.sig.signal]?.label ?? r.sig.signal}
                            </span>
                            <span className="text-[9px] text-muted/50">{fmtAgo(r.sig.created_at)}</span>
                          </div>
                          {r.sig.reason && (
                            <span className="text-[10px] text-muted/80 leading-snug whitespace-normal break-words">{r.sig.reason}</span>
                          )}
                        </div>
                      ) : (
                        <span className="text-[10px] text-muted/50">未分析</span>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
