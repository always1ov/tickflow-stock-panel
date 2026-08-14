/**
 * [fork 增强] 今日总览 —— 决策汇聚层。
 *
 * 把六态趋势/AI 信号预案/持仓出场线/监控触发按"需要行动的紧迫度"聚合成一屏:
 * ① 行动区(必须处理) ② 机会区(值得看) ③ 市场天气(定基调) ④ 持仓体检。
 * 数据全部来自既有模块,零新计算;AI 导读可选(手动点击,一次调用)。
 */
import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import {
  AlertTriangle, CheckCircle2, Compass, Loader2, RefreshCw, Sparkles, Sunrise, Target,
} from 'lucide-react'
import { api } from '@/lib/api'
import { toast } from '@/components/Toast'

const POSTURE_STYLE: Record<string, string> = {
  进攻: 'border-red-400/40 bg-red-400/10 text-red-400',
  谨慎: 'border-amber-400/40 bg-amber-400/10 text-amber-300',
  防守: 'border-emerald-400/40 bg-emerald-400/10 text-emerald-400',
  观察: 'border-border bg-base text-muted',
}

export function Today() {
  const navigate = useNavigate()
  const q = useQuery({
    queryKey: ['today-overview'],
    queryFn: () => api.todayOverview(),
    staleTime: 60_000,
  })
  const [brief, setBrief] = useState<string | null>(null)
  const briefMut = useMutation({
    mutationFn: () => api.todayBrief(),
    onSuccess: (r) => {
      if (r.error) toast(r.error, 'error')
      else setBrief(r.brief ?? null)
    },
    onError: (e: Error) => toast(`导读生成失败: ${e.message}`, 'error'),
  })

  const goStock = (symbol: string, name: string) =>
    navigate(`/stock-analysis?symbol=${encodeURIComponent(symbol)}&name=${encodeURIComponent(name)}`)

  const d = q.data

  return (
    <div className="p-4 md:p-6 max-w-5xl mx-auto space-y-4">
      {/* 头部 */}
      <div className="flex flex-wrap items-center gap-3">
        <Sunrise className="h-5 w-5 text-amber-300" />
        <h1 className="text-base font-semibold text-foreground">今日总览</h1>
        {d?.as_of && <span className="text-[10px] text-muted">数据截至 {d.as_of} · 自选 {d.watchlist_total} 只(六态判定 {d.trend_total})</span>}
        <div className="ml-auto flex items-center gap-2">
          <button
            onClick={() => briefMut.mutate()}
            disabled={briefMut.isPending || !d}
            className="inline-flex items-center gap-1 rounded-full border border-violet-400/30 bg-violet-400/10 px-2.5 py-1 text-[10px] text-violet-300 hover:bg-violet-400/20 disabled:opacity-50 transition-colors cursor-pointer"
          >
            {briefMut.isPending ? <Loader2 className="h-3 w-3 animate-spin" /> : <Sparkles className="h-3 w-3" />}
            AI 导读
          </button>
          <button
            onClick={() => q.refetch()}
            disabled={q.isFetching}
            className="inline-flex items-center gap-1 rounded-full border border-border bg-base px-2.5 py-1 text-[10px] text-muted hover:text-foreground disabled:opacity-50 transition-colors cursor-pointer"
          >
            <RefreshCw className={`h-3 w-3 ${q.isFetching ? 'animate-spin' : ''}`} />
            刷新
          </button>
        </div>
      </div>

      {brief && (
        <div className="rounded-lg border border-violet-400/20 bg-violet-400/[0.06] px-4 py-3 text-xs leading-relaxed text-foreground/90">
          <Sparkles className="mr-1.5 inline h-3.5 w-3.5 text-violet-300" />
          {brief}
        </div>
      )}

      {q.isLoading && (
        <div className="flex items-center justify-center py-16"><Loader2 className="h-5 w-5 animate-spin text-muted" /></div>
      )}
      {q.isError && (
        <div className="rounded-lg border border-red-400/30 bg-red-400/10 px-4 py-3 text-xs text-red-400">
          总览加载失败:{(q.error as Error)?.message}
        </div>
      )}

      {d && (
        <>
          {/* ③ 市场天气(放最上面一条横幅, 定基调) */}
          <div className="flex flex-wrap items-center gap-3 rounded-lg border border-border/60 bg-surface/40 px-4 py-3">
            <Compass className="h-4 w-4 text-sky-400" />
            <span className={`inline-flex rounded-full border px-3 py-0.5 text-sm font-medium ${POSTURE_STYLE[d.weather.posture] ?? POSTURE_STYLE['观察']}`}>
              {d.weather.posture}
            </span>
            <span className="text-xs text-muted">{d.weather.posture_reason}</span>
            <span className="ml-auto text-[11px] font-mono text-muted">
              多头 <span className="text-red-400 font-semibold">{d.weather.bull}</span>
              <span className="mx-1 text-muted/40">/</span>
              空头 <span className="text-emerald-400 font-semibold">{d.weather.bear}</span>
              <span className="mx-2 text-muted/40">·</span>
              新转多 {d.weather.new_bull} · 新转空 {d.weather.new_bear}
            </span>
          </div>

          {/* ① 行动区 */}
          <section className="rounded-lg border border-border/60 bg-surface/40 overflow-hidden">
            <div className="flex items-center gap-2 border-b border-border/40 px-4 py-2.5">
              <AlertTriangle className="h-4 w-4 text-red-400" />
              <span className="text-sm font-medium text-foreground">需要行动</span>
              <span className="text-[10px] text-muted">{d.actions.length} 项</span>
            </div>
            {d.actions.length === 0 ? (
              <div className="flex items-center gap-2 px-4 py-5 text-xs text-muted">
                <CheckCircle2 className="h-4 w-4 text-emerald-400" />
                今日无需操作 —— 这本身就是有价值的信息,管住手
              </div>
            ) : (
              <ul className="divide-y divide-border/30">
                {d.actions.map((a, i) => (
                  <li key={i}>
                    <button
                      onClick={() => a.symbol && goStock(a.symbol, a.name)}
                      className="flex w-full items-start gap-2.5 px-4 py-2.5 text-left hover:bg-elevated/40 transition-colors cursor-pointer"
                    >
                      <span className={`mt-0.5 h-1.5 w-1.5 shrink-0 rounded-full ${a.severity === 'high' ? 'bg-red-400' : 'bg-amber-300'}`} />
                      <span className="text-xs leading-relaxed">
                        <span className="font-medium text-foreground">{a.name}</span>
                        <span className="ml-1.5 text-[9px] font-mono text-muted">{a.symbol}</span>
                        <span className="ml-2 text-foreground/80">{a.text}</span>
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </section>

          {/* ② 机会区 */}
          <section className="rounded-lg border border-border/60 bg-surface/40 overflow-hidden">
            <div className="flex items-center gap-2 border-b border-border/40 px-4 py-2.5">
              <Target className="h-4 w-4 text-red-400" />
              <span className="text-sm font-medium text-foreground">值得关注</span>
              <span className="text-[10px] text-muted">{d.opportunities.length} 项 · 刚转多/回升 + 逼近突破预案</span>
            </div>
            {d.opportunities.length === 0 ? (
              <div className="px-4 py-5 text-xs text-muted">暂无新信号 —— 等待比出手更常见</div>
            ) : (
              <ul className="divide-y divide-border/30">
                {d.opportunities.map((o, i) => (
                  <li key={i}>
                    <button
                      onClick={() => goStock(o.symbol, o.name)}
                      className="flex w-full items-start gap-2.5 px-4 py-2.5 text-left hover:bg-elevated/40 transition-colors cursor-pointer"
                    >
                      <span className="mt-0.5 h-1.5 w-1.5 shrink-0 rounded-full bg-red-400/70" />
                      <span className="text-xs leading-relaxed">
                        <span className="font-medium text-foreground">{o.name}</span>
                        <span className="ml-1.5 text-[9px] font-mono text-muted">{o.symbol}</span>
                        <span className="ml-2 text-foreground/80">{o.text}</span>
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </section>

          {/* ④ 持仓体检 */}
          <section className="rounded-lg border border-border/60 bg-surface/40 overflow-hidden">
            <div className="flex items-center gap-2 border-b border-border/40 px-4 py-2.5">
              <span className="text-sm font-medium text-foreground">持仓体检</span>
              <span className="text-[10px] text-muted">{d.holdings.length} 只(已触发/最接近出场线的排前面)</span>
            </div>
            {d.holdings.length === 0 ? (
              <div className="px-4 py-5 text-xs text-muted">
                暂无持仓标记 —— 在个股分析页决策台把持有的票标「持有」并填成本,这里就会出现仓位全景
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[640px] text-xs">
                  <thead className="text-[10px] text-muted">
                    <tr className="text-left">
                      <th className="px-4 py-1.5 font-normal">标的</th>
                      <th className="px-2 py-1.5 font-normal text-right">现价</th>
                      <th className="px-2 py-1.5 font-normal text-right">浮盈</th>
                      <th className="px-2 py-1.5 font-normal text-right">出场线</th>
                      <th className="px-2 py-1.5 font-normal text-center">阶段</th>
                      <th className="px-2 py-1.5 font-normal text-center">趋势</th>
                      <th className="px-4 py-1.5 font-normal text-center">AI 信号</th>
                    </tr>
                  </thead>
                  <tbody>
                    {d.holdings.map((h) => (
                      <tr
                        key={h.symbol}
                        onClick={() => goStock(h.symbol, h.name)}
                        className="border-t border-border/30 hover:bg-elevated/40 cursor-pointer"
                      >
                        <td className="px-4 py-1.5">
                          <span className="font-medium text-foreground">{h.name}</span>
                          <span className="ml-1.5 text-[9px] font-mono text-muted">{h.symbol}</span>
                        </td>
                        <td className="px-2 py-1.5 text-right font-mono">{h.close?.toFixed(2) ?? '—'}</td>
                        <td className={`px-2 py-1.5 text-right font-mono ${h.pnl_pct == null ? 'text-muted' : h.pnl_pct > 0 ? 'text-red-400' : h.pnl_pct < 0 ? 'text-emerald-400' : 'text-muted'}`}>
                          {h.pnl_pct != null ? `${(h.pnl_pct * 100).toFixed(1)}%` : '—'}
                        </td>
                        <td className={`px-2 py-1.5 text-right font-mono ${h.exit_triggered ? 'text-red-400' : (h.distance_pct ?? -1) > -0.03 ? 'text-amber-300' : 'text-muted'}`}>
                          {h.line != null ? `${h.line.toFixed(2)}${h.exit_triggered ? ' 已触发' : h.distance_pct != null ? ` · 距${(Math.abs(h.distance_pct) * 100).toFixed(1)}%` : ''}` : '—'}
                        </td>
                        <td className="px-2 py-1.5 text-center text-[10px] text-muted">{h.stage_cn ?? '—'}</td>
                        <td className="px-2 py-1.5 text-center text-[10px]">
                          {h.trend_cn ? (
                            <span className={h.trend_side === '多头' ? 'text-red-400' : 'text-emerald-400'}>
                              {h.trend_cn} {h.trend_duration}天
                            </span>
                          ) : '—'}
                        </td>
                        <td className="px-4 py-1.5 text-center text-[10px] text-muted">{h.signal ?? '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </>
      )}
    </div>
  )
}
