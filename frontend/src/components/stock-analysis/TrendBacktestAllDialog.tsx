/**
 * [R312] 「全量回测」—— 一次把整个自选的六态阈值都跑一遍。
 *
 * 用户: 「在刷新后面加个一键回测所有个股」。
 *
 * ## 为什么不调 AI
 *
 * 单只那个弹窗(`TrendBacktestDialog`)跑完网格之后会再问一次 AI 当调参顾问。
 * 批量**不问**, 三条理由:
 *
 *   ① 166 只票就是 166 次调用 —— 慢、要钱, 而这个按钮就挨在「刷新」旁边,
 *      那一带的东西全是不计费的;
 *   ② 规则建议是**纯函数、可复算**, 样本不足时它会明说「不足以支撑调参」
 *      而不是硬荐一个数 —— 批量场景要的正是这种克制;
 *   ③ 想听 AI 的意见, 逐只打开那个弹窗就是, 入口一直在。
 *
 * ## 为什么不直接套用
 *
 * 阈值一改, 这只票的六态整条历史跟着变 —— 决策台的方向、打分的趋势硬门槛、
 * 「按转折买卖」的全部统计都是从它出来的。**166 只票一键改掉是不可逆的**
 * (没有"撤销上一次批量"这回事)。
 *
 * 所以这里是**先看后用**: 跑完摆一张表, 每一行写清楚「现在多赚多少 → 改了之后
 * 多赚多少」, 勾选想改的再落盘。默认只勾**真的更好**的那些(建议≠当前 且
 * 样本够 且 多赚有提升), 其余留空。
 *
 * ## 这张表按"值不值"排序
 *
 * 不是按代码、不是按名字, 是按**改完能多赚几个点**从大到小 —— 一屏就能看完
 * 值得动的那几只, 剩下的往下翻。只说「建议 8%」是不可证伪的一句话, 把
 * `excess` 两边都摆出来才知道这次调参到底买到了什么。
 */
import { useMemo, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { FlaskConical, Loader2, X, Check } from 'lucide-react'

import { api, type TrendBacktestBatchRow, type TrendBacktestBatchResult } from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import { toast } from '@/components/Toast'
import { TYPE, buttonClass } from '@/components/ui'

/** 小数 → 带符号百分数。`—` 表示这一格算不出来, 与 0% 不是一回事。 */
function pct(v: number | null | undefined, digits = 1): string {
  if (v === null || v === undefined) return '—'
  return `${v > 0 ? '+' : ''}${(v * 100).toFixed(digits)}%`
}

/** 这一行改完能多赚几个点。任一边缺就返回 null —— 不拿 0 顶替。 */
function gain(r: TrendBacktestBatchRow): number | null {
  if (r.excess_now === null || r.excess_suggested === null) return null
  return r.excess_suggested - r.excess_now
}

/** 默认勾上的判据: 建议与当前不同、样本够、而且确实更好。 */
function worthIt(r: TrendBacktestBatchRow): boolean {
  const g = gain(r)
  return !r.sample_insufficient
    && Math.abs(r.suggested - r.current_threshold) > 1e-9
    && g !== null && g > 0
}

export function TrendBacktestAllDialog({ symbols, onClose }: {
  symbols: string[]
  onClose: () => void
}) {
  const qc = useQueryClient()
  const [result, setResult] = useState<TrendBacktestBatchResult | null>(null)
  const [picked, setPicked] = useState<Set<string>>(new Set())

  const run = useMutation({
    mutationFn: () => api.stockTrendBacktestBatch(symbols),
    onSuccess: (r) => {
      setResult(r)
      setPicked(new Set(r.rows.filter(worthIt).map((x) => x.symbol)))
    },
    onError: (e: Error) => toast(`回测失败: ${e.message}`, 'error'),
  })

  const apply = useMutation({
    mutationFn: (items: { symbol: string; threshold: number; source: 'rule' }[]) =>
      api.stockTrendSetThresholdBatch(items),
    onSuccess: (r) => {
      toast(`已应用 ${r.applied.length} 只的阈值`, 'success')
      // 阈值一改, 六态整条历史跟着变 —— 决策台那几份都得重拉
      qc.invalidateQueries({ queryKey: QK.stockTrendsAll })
      qc.invalidateQueries({ queryKey: QK.watchlistEnriched() })
      onClose()
    },
    onError: (e: Error) => toast(`应用失败: ${e.message}`, 'error'),
  })

  /** 按「改完能多赚几个点」从大到小。算不出来的沉底 —— 它们不构成决策。 */
  const rows = useMemo(() => {
    const rs = [...(result?.rows ?? [])]
    rs.sort((a, b) => {
      const ga = gain(a), gb = gain(b)
      if (ga === null && gb === null) return a.symbol.localeCompare(b.symbol)
      if (ga === null) return 1
      if (gb === null) return -1
      return gb - ga
    })
    return rs
  }, [result])

  const changed = rows.filter(worthIt).length
  const toggle = (sym: string) => setPicked((prev) => {
    const next = new Set(prev)
    if (next.has(sym)) next.delete(sym); else next.add(sym)
    return next
  })

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm"
         onClick={onClose}>
      <div role="dialog" aria-modal="true"
           className="flex max-h-[86vh] w-full max-w-4xl flex-col overflow-hidden rounded-btn border border-border bg-surface shadow-2xl"
           onClick={(e) => e.stopPropagation()}>

        <div className="flex items-center justify-between border-b border-border/60 px-4 py-3">
          <div className="flex items-center gap-2">
            <FlaskConical className="h-4 w-4 text-secondary" />
            <span className={TYPE.section}>全量六态阈值回测</span>
            <span className="font-mono text-micro text-muted">{symbols.length} 只</span>
            {result && (
              <span className="text-micro text-muted">
                {rows.length} 只跑出结果 · {changed} 只建议调整
                {result.skipped.length > 0 && ` · ${result.skipped.length} 只数据不足`}
              </span>
            )}
          </div>
          <button onClick={onClose} className={buttonClass({ variant: 'ghost', icon: true })}>
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="flex-1 space-y-4 overflow-auto p-4">
          {!result && (
            <div className="flex flex-col items-center gap-3 py-10">
              <p className="max-w-lg text-center text-xs leading-relaxed text-muted">
                对自选里这 {symbols.length} 只票各按 3%~15% 阈值网格跑一遍六态状态机
                (纯计算,不调用 AI、不计费)。
                <br />
                跑完先摆结果,<b className="text-foreground/80">勾选之后才写入</b> ——
                阈值一改,这只票的六态整条历史都会跟着变。
              </p>
              <button
                onClick={() => run.mutate()}
                disabled={run.isPending}
                className={buttonClass({ variant: 'primary' }, 'gap-1.5')}
              >
                {run.isPending
                  ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  : <FlaskConical className="h-3.5 w-3.5" />}
                {run.isPending ? '回测中…' : '开始回测'}
              </button>
            </div>
          )}

          {result && (
            <div className="overflow-x-auto rounded-btn border border-border/60">
              <table className="w-full min-w-[680px] text-xs">
                <thead className="bg-elevated/40 text-micro text-muted">
                  <tr>
                    <th className="w-8 px-2 py-1.5" />
                    <th className="px-2 py-1.5 text-left font-normal">标的</th>
                    <th className="px-2 py-1.5 text-right font-normal">当前</th>
                    <th className="px-2 py-1.5 text-right font-normal">建议</th>
                    <th className="px-2 py-1.5 text-right font-normal"
                        title="「多赚」= 跟随收益 − 买入持有,与复盘页那一栏是同一个概念">
                      现在多赚
                    </th>
                    <th className="px-2 py-1.5 text-right font-normal">改后多赚</th>
                    <th className="px-2 py-1.5 text-right font-normal">差</th>
                    <th className="px-2 py-1.5 text-left font-normal">理由</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => {
                    const g = gain(r)
                    const on = picked.has(r.symbol)
                    const same = Math.abs(r.suggested - r.current_threshold) <= 1e-9
                    return (
                      <tr key={r.symbol}
                          className={`border-t border-border/30 transition-colors duration-hover hover:bg-elevated/30 ${
                            r.sample_insufficient || same ? 'opacity-45' : ''}`}>
                        <td className="px-2 py-1">
                          {/* 样本不足的票**不给勾** —— 规则明说了不足以支撑调参,
                              摆一个能勾的框等于请人去点一个没有依据的改动。 */}
                          <button
                            type="button"
                            disabled={r.sample_insufficient}
                            onClick={() => toggle(r.symbol)}
                            aria-label={`选择 ${r.symbol}`}
                            className={`flex h-3.5 w-3.5 items-center justify-center rounded-[3px] border transition-colors duration-hover disabled:cursor-not-allowed disabled:opacity-30 ${
                              on ? 'border-accent bg-accent text-white' : 'border-border bg-base'}`}>
                            {on && <Check className="h-2.5 w-2.5" strokeWidth={3} />}
                          </button>
                        </td>
                        <td className="whitespace-nowrap px-2 py-1 font-mono text-foreground">
                          {r.symbol}
                          <span className="ml-1 text-micro text-muted/60">{r.window_days}日</span>
                        </td>
                        <td className="px-2 py-1 text-right font-mono tabular-nums">
                          {(r.current_threshold * 100).toFixed(0)}%
                          {r.current_source === 'override' && (
                            <span className="ml-0.5 text-micro text-accent/70" title="这只票有自己的覆盖值">*</span>
                          )}
                        </td>
                        <td className={`px-2 py-1 text-right font-mono tabular-nums ${
                          same ? 'text-muted' : 'text-foreground'}`}>
                          {(r.suggested * 100).toFixed(0)}%
                        </td>
                        <td className="px-2 py-1 text-right font-mono tabular-nums text-muted">
                          {pct(r.excess_now)}
                        </td>
                        <td className="px-2 py-1 text-right font-mono tabular-nums text-muted">
                          {pct(r.excess_suggested)}
                        </td>
                        {/* A 股红涨绿跌 —— 与整个界面同一套配色 */}
                        <td className={`px-2 py-1 text-right font-mono tabular-nums ${
                          g === null ? 'text-muted/40' : g > 0 ? 'text-bull' : g < 0 ? 'text-bear' : 'text-muted'}`}>
                          {pct(g)}
                        </td>
                        <td className="max-w-[18rem] truncate px-2 py-1 text-muted/80" title={r.reason}>
                          {r.reason}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}

          {result && result.skipped.length > 0 && (
            <p className="text-micro text-muted/60">
              没跑的 {result.skipped.length} 只:{result.skipped.slice(0, 12).map((x) => x.symbol).join('、')}
              {result.skipped.length > 12 && ` 等`} —— {result.skipped[0]?.why}
            </p>
          )}
        </div>

        {result && (
          <div className="flex items-center justify-between border-t border-border/60 px-4 py-3">
            <span className="text-xs text-muted">
              选中 <b className="font-mono text-foreground">{picked.size}</b> 只
              {picked.size > 0 && ' —— 写入后这些票的六态历史会按新阈值重算'}
            </span>
            <button
              onClick={() => apply.mutate(rows.filter((r) => picked.has(r.symbol))
                .map((r) => ({ symbol: r.symbol, threshold: r.suggested, source: 'rule' as const })))}
              disabled={picked.size === 0 || apply.isPending}
              className={buttonClass({ variant: 'primary' }, 'gap-1.5')}
            >
              {apply.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
              应用选中的 {picked.size} 只
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
