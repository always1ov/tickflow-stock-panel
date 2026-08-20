/**
 * [fork 增强] 六态趋势条 + 回测调参弹窗(利弗莫尔 Market Key)。
 *
 * 文案沿用引入代码包的原版表达:六个状态名 / STATE_ACTION 操作建议 /
 * 转多·转空·回升·回撤信号 / 上·下关键点 / 多头·空头。
 * 配色按本系统 A 股惯例:多头红、空头绿;趋势确认态实心,中间态描边。
 */
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { FlaskConical, Loader2, Sparkles, TrendingUp, X } from 'lucide-react'
import { api, type LivermoreState, type TrendBacktestResult, type TrendDetail } from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import { toast } from '@/components/Toast'

// 状态 → 徽章样式。多头(上涨趋势/自然回升/次级回升)红系,空头绿系;
// 趋势确认态(UT/DT)实心,其余中间态描边。
const STATE_BADGE: Record<LivermoreState, string> = {
  UT: 'bg-bull/15 border-bull/50 text-bull font-semibold',
  NR: 'border-bull/40 text-bull/90',
  SR: 'border-bull/30 text-bull/70',
  SREA: 'border-bear/30 text-bear/70',
  NREA: 'border-bear/40 text-bear/90',
  DT: 'bg-bear/15 border-bear/50 text-bear font-semibold',
}

const SIGNAL_BADGE: Record<string, string> = {
  转多: 'bg-bull/15 border-bull/40 text-bull',
  转空: 'bg-bear/15 border-bear/40 text-bear',
  回升: 'border-bull/30 text-bull/80',
  回撤: 'border-bear/30 text-bear/80',
}

export function trendBadgeCls(state: LivermoreState): string {
  return STATE_BADGE[state] ?? 'border-border text-muted'
}

export function TrendStateBar({ symbol, trend }: { symbol: string; trend: TrendDetail | undefined }) {
  const [showBacktest, setShowBacktest] = useState(false)

  if (!trend) return null
  if (trend.error) {
    return (
      <div className="flex items-center gap-2 rounded-lg border border-border/50 bg-elevated/20 px-3 py-2 text-[11px] text-muted">
        <TrendingUp className="h-3.5 w-3.5" />
        六态趋势:{trend.error}
      </div>
    )
  }

  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 rounded-lg border border-border/50 bg-elevated/20 px-3 py-2">
      <span
        className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs ${trendBadgeCls(trend.state)}`}
        title={`${trend.state_en} · 窗口 ${trend.window_days} 个交易日${trend.intraday ? '\n⚠ 盘中临时口径:实时价参与判定,收盘确认为准' : ''}`}
      >
        {trend.state_cn}
      </span>
      {trend.intraday && (
        <span
          className="inline-flex rounded border border-amber-400/30 bg-amber-400/10 px-1.5 py-0.5 text-[10px] text-amber-300"
          title="实时价参与了六态判定,收盘价可能改变结论 —— 定稿以收盘为准"
        >
          盘中口径
        </span>
      )}
      <span className="text-xs text-foreground/90">
        第 <span className="font-mono font-semibold">{trend.duration}</span> 天
        <span className="text-muted"> · 自 {trend.since}</span>
        {trend.entered_from_cn && <span className="text-muted"> · 由「{trend.entered_from_cn}」转入</span>}
      </span>
      {trend.signal && (
        <span
          className={`inline-flex rounded-full border px-2 py-0.5 text-[10px] ${SIGNAL_BADGE[trend.signal] ?? ''}`}
          title={trend.signal_desc ?? undefined}
        >
          {trend.signal}
        </span>
      )}
      {/* [R29] 主打「跌破转弱 / 站上转强」两条翻转触发价 —— 趋势途中上关键点就是
          本轮最高收盘价(创新高当天等于当日收盘), 当触发价看没有参考价值。
          关键点降级为悬停可见的参考信息。 */}
      <span
        className="text-[11px] font-mono text-muted"
        title={`本轮最高收盘 ${trend.leg_high?.toFixed(2) ?? '—'} · 本轮最低收盘 ${trend.leg_low?.toFixed(2) ?? '—'}\n上关键点 ${trend.up_pivot?.toFixed(2) ?? '—'} · 下关键点 ${trend.dn_pivot?.toFixed(2) ?? '—'}\n阈值 ${(trend.threshold * 100).toFixed(0)}%`}
      >
        {trend.flip_down != null && (
          <>跌破 <span className="text-bear/90">{trend.flip_down.toFixed(2)}</span> 转弱</>
        )}
        {trend.flip_down != null && trend.flip_up != null && <span className="mx-1.5 text-muted/40">|</span>}
        {trend.flip_up != null && (
          <>站上 <span className="text-bull/90">{trend.flip_up.toFixed(2)}</span> 转强</>
        )}
        {trend.flip_down == null && trend.flip_up == null && (
          <>上关键点 <span className="text-bull/90">{trend.up_pivot?.toFixed(2) ?? '—'}</span>
            <span className="mx-1.5 text-muted/40">|</span>
            下关键点 <span className="text-bear/90">{trend.dn_pivot?.toFixed(2) ?? '—'}</span></>
        )}
      </span>
      <span className="text-[11px] text-amber-300/90">{trend.action}</span>
      <button
        onClick={() => setShowBacktest(true)}
        className="ml-auto inline-flex items-center gap-1 rounded-full border border-violet-400/30 bg-violet-400/10 px-2 py-0.5 text-[10px] text-violet-300 hover:bg-violet-400/20 transition-colors cursor-pointer"
        title="按阈值网格回测近 180 个交易日,选择该票的合适回撤/回升阈值"
      >
        <FlaskConical className="h-3 w-3" />
        回测调参 {(trend.threshold * 100).toFixed(0)}%
        {trend.threshold_source === 'override' && <span className="text-violet-300/60">(已定制)</span>}
      </button>
      {showBacktest && (
        <TrendBacktestDialog symbol={symbol} onClose={() => setShowBacktest(false)} />
      )}
    </div>
  )
}

// ===== 回测调参弹窗 =====

function pct(v: number | null | undefined, digits = 1): string {
  if (v === null || v === undefined) return '—'
  return `${(v * 100).toFixed(digits)}%`
}

function TrendBacktestDialog({ symbol, onClose }: { symbol: string; onClose: () => void }) {
  const qc = useQueryClient()
  const [result, setResult] = useState<TrendBacktestResult | null>(null)

  const run = useMutation({
    mutationFn: () => api.stockTrendBacktest(symbol, true),
    onSuccess: (r) => {
      if (r.error) toast(r.error, 'error')
      else setResult(r)
    },
    onError: (e: Error) => toast(`回测失败: ${e.message}`, 'error'),
  })

  const apply = useMutation({
    mutationFn: ({ threshold, source }: { threshold: number; source: 'manual' | 'ai' | 'rule' }) =>
      api.stockTrendSetThreshold(symbol, threshold, source),
    onSuccess: (r) => {
      toast(`已应用阈值 ${(r.threshold * 100).toFixed(0)}%`, 'success')
      qc.invalidateQueries({ queryKey: QK.stockTrend(symbol) })
      qc.invalidateQueries({ queryKey: QK.stockLevels(symbol) })
      qc.invalidateQueries({ queryKey: ['stock-trends'] })
    },
    onError: (e: Error) => toast(`应用失败: ${e.message}`, 'error'),
  })

  const reset = useMutation({
    mutationFn: () => api.stockTrendSetThreshold(symbol, null),
    onSuccess: () => {
      toast('已恢复默认阈值', 'success')
      qc.invalidateQueries({ queryKey: QK.stockTrend(symbol) })
      qc.invalidateQueries({ queryKey: QK.stockLevels(symbol) })
      qc.invalidateQueries({ queryKey: ['stock-trends'] })
    },
  })

  const grid = result?.grid ?? []
  const current = result?.current_threshold

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4" onClick={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        className="flex max-h-[86vh] w-full max-w-3xl flex-col overflow-hidden rounded-lg border border-border bg-surface shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-border/60 px-4 py-3">
          <div className="flex items-center gap-2">
            <FlaskConical className="h-4 w-4 text-violet-300" />
            <span className="text-sm font-medium text-foreground">六态阈值回测调参</span>
            <span className="text-[10px] font-mono text-muted">{symbol}</span>
            {result && <span className="text-[10px] text-muted">{result.from} ~ {result.to} · {result.window_days} 个交易日</span>}
          </div>
          <button onClick={onClose} className="text-muted hover:text-foreground"><X className="h-4 w-4" /></button>
        </div>

        <div className="flex-1 overflow-auto p-4 space-y-4">
          {!result && (
            <div className="flex flex-col items-center gap-3 py-10">
              <p className="text-xs text-muted max-w-md text-center leading-relaxed">
                对近 180 个交易日按 3%~15% 阈值网格逐一回测六态状态机(纯计算,即时完成),
                再由 AI 结合波动率当调参顾问(一次调用;未配 AI 时给规则建议)。
              </p>
              <button
                onClick={() => run.mutate()}
                disabled={run.isPending}
                className="inline-flex items-center gap-1.5 rounded-btn bg-accent px-4 py-2 text-xs font-medium text-white hover:bg-accent/90 disabled:opacity-50"
              >
                {run.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <FlaskConical className="h-3.5 w-3.5" />}
                {run.isPending ? '回测中…' : '一键回测'}
              </button>
            </div>
          )}

          {result && (
            <>
              {/* 指标表 */}
              <div className="overflow-x-auto rounded-lg border border-border/60">
                <table className="w-full min-w-[640px] text-[11px]">
                  <thead className="bg-elevated/40 text-[10px] text-muted">
                    <tr className="text-right">
                      <th className="px-2 py-1.5 text-left font-normal">阈值</th>
                      <th className="px-2 py-1.5 font-normal">翻转</th>
                      <th className="px-2 py-1.5 font-normal">多头段</th>
                      <th className="px-2 py-1.5 font-normal">假信号率</th>
                      <th className="px-2 py-1.5 font-normal">平均段长</th>
                      <th className="px-2 py-1.5 font-normal">跟随收益</th>
                      <th className="px-2 py-1.5 font-normal">超额</th>
                      <th className="px-2 py-1.5 font-normal">前半/后半</th>
                      <th className="px-2 py-1.5 font-normal">应用</th>
                    </tr>
                  </thead>
                  <tbody className="font-mono">
                    {grid.map((r) => {
                      const isCurrent = current !== undefined && Math.abs(r.threshold - current) < 0.001
                      const isRule = Math.abs(r.threshold - result.rule_suggestion.threshold) < 0.001 && !result.rule_suggestion.sample_insufficient
                      const isAi = result.ai && Math.abs(r.threshold - result.ai.threshold) < 0.001
                      return (
                        <tr key={r.threshold} className={`border-t border-border/40 text-right ${isCurrent ? 'bg-accent/10' : isAi ? 'bg-violet-400/10' : ''}`}>
                          <td className="px-2 py-1 text-left">
                            {pct(r.threshold, 0)}
                            {isCurrent && <span className="ml-1 text-[9px] text-accent">当前</span>}
                            {isRule && <span className="ml-1 text-[9px] text-sky-300">规则荐</span>}
                            {isAi && <span className="ml-1 text-[9px] text-violet-300">AI荐</span>}
                          </td>
                          <td className="px-2 py-1">{r.flips}</td>
                          <td className="px-2 py-1">{r.bull_segs}</td>
                          <td className={`px-2 py-1 ${r.false_rate !== null && r.false_rate >= 0.5 ? 'text-bear' : ''}`}>{pct(r.false_rate, 0)}</td>
                          <td className="px-2 py-1">{r.avg_seg_days}天</td>
                          <td className={`px-2 py-1 ${r.strategy_return >= 0 ? 'text-bull' : 'text-bear'}`}>{pct(r.strategy_return)}</td>
                          <td className={`px-2 py-1 ${r.excess >= 0 ? 'text-bull' : 'text-bear'}`}>{pct(r.excess)}</td>
                          <td className="px-2 py-1 text-muted">{pct(r.first_half, 0)}/{pct(r.second_half, 0)}</td>
                          <td className="px-2 py-1">
                            <button
                              onClick={() => apply.mutate({ threshold: r.threshold, source: 'manual' })}
                              disabled={apply.isPending || isCurrent}
                              className="rounded border border-border px-1.5 py-0.5 text-[9px] text-muted hover:text-foreground hover:border-accent/50 disabled:opacity-30"
                            >
                              用
                            </button>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
              <p className="text-[10px] text-muted leading-relaxed">
                买入持有基准 {pct(grid[0]?.buyhold_return)}。跟随收益 = 仅多头状态持有的复利收益;
                假信号率 = 收益≤0 的多头段占比;前半/后半 = 窗口两半各自的跟随收益(差异大说明该阈值不稳定,谨防过拟合)。
              </p>

              {/* 建议卡片 */}
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <div className="rounded-lg border border-sky-400/20 bg-sky-400/[0.06] px-3.5 py-3">
                  <div className="mb-1 flex items-center justify-between">
                    <span className="text-xs font-medium text-sky-300">规则建议 · {pct(result.rule_suggestion.threshold, 0)}</span>
                    <button
                      onClick={() => apply.mutate({ threshold: result.rule_suggestion.threshold, source: 'rule' })}
                      disabled={apply.isPending}
                      className="rounded-btn border border-sky-400/40 px-2 py-0.5 text-[10px] text-sky-300 hover:bg-sky-400/10 disabled:opacity-40"
                    >
                      应用
                    </button>
                  </div>
                  <p className="text-[10px] leading-relaxed text-muted">{result.rule_suggestion.reason}</p>
                </div>
                <div className="rounded-lg border border-violet-400/20 bg-violet-400/[0.06] px-3.5 py-3">
                  {result.ai ? (
                    <>
                      <div className="mb-1 flex items-center justify-between">
                        <span className="inline-flex items-center gap-1 text-xs font-medium text-violet-300">
                          <Sparkles className="h-3 w-3" />
                          AI 推荐 · {pct(result.ai.threshold, 0)}
                          <span className="text-[9px] text-violet-300/70">置信 {result.ai.confidence}%</span>
                        </span>
                        <button
                          onClick={() => apply.mutate({ threshold: result.ai!.threshold, source: 'ai' })}
                          disabled={apply.isPending}
                          className="rounded-btn border border-violet-400/40 px-2 py-0.5 text-[10px] text-violet-300 hover:bg-violet-400/10 disabled:opacity-40"
                        >
                          应用
                        </button>
                      </div>
                      <p className="text-[10px] leading-relaxed text-muted">{result.ai.reason}</p>
                    </>
                  ) : (
                    <p className="text-[10px] leading-relaxed text-muted">
                      <Sparkles className="mr-1 inline h-3 w-3 text-violet-300/60" />
                      {result.ai_error ?? 'AI 未参与本次回测'}
                    </p>
                  )}
                </div>
              </div>
            </>
          )}
        </div>

        <div className="flex items-center justify-between border-t border-border/60 px-4 py-2.5">
          <button
            onClick={() => reset.mutate()}
            disabled={reset.isPending}
            className="text-[10px] text-muted hover:text-foreground disabled:opacity-40"
            title="清除该票的阈值覆盖,恢复全局默认"
          >
            恢复默认阈值
          </button>
          {result && (
            <button
              onClick={() => run.mutate()}
              disabled={run.isPending}
              className="inline-flex items-center gap-1 rounded-btn border border-border px-3 py-1 text-[10px] text-muted hover:text-foreground disabled:opacity-40"
            >
              {run.isPending ? <Loader2 className="h-3 w-3 animate-spin" /> : <FlaskConical className="h-3 w-3" />}
              重新回测
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

/** 页面侧封装:自取趋势数据(含分段)的挂载入口。 */
export function useStockTrend(symbol: string) {
  return useQuery({
    queryKey: QK.stockTrend(symbol),
    queryFn: () => api.stockTrend(symbol),
    enabled: !!symbol,
    staleTime: 60_000,
  })
}
