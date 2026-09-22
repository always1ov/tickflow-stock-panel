/**
 * [R412] 斐波那契二型「粗细档」回测弹窗。
 *
 * 用户: 「粗中细我看不懂, 这个调优能不能交给 ai 就像我六态设置了一个回测按钮,
 * 参考这种模式」。形状照搬六态那个 —— 指标表 + 规则建议 + 可选 AI 顾问。
 *
 * **但评的东西完全不同, 界面上必须说清楚**:
 *
 *     六态那个评的是「跟着做赚不赚」—— 它出买卖信号, 有收益可算。
 *     这个评的是「线画得准不准」—— 它不出买卖信号, 也就没有收益这回事。
 *
 * 界面上一个收益数字都不该出现; 出现了就是在暗示这组线能拿来做买卖,
 * 而它从 R405 起的口径就是「只有位置, 没有动作」。
 *
 * **「每条线的贡献」那一列是全表最重要的一个数**, 所以它排在最右且加粗:
 * 细档画更多线, 蒙中的概率天然更高 —— 只看命中率排序会必然推荐最细那一档,
 * 那不是调参, 是过拟合的标准形态。
 */
import { useMutation } from '@tanstack/react-query'
import { FlaskConical, Loader2, Sparkles, X } from 'lucide-react'
import { api } from '@/lib/api'
import type { Fib2Grain, Fib2GrainBacktestResult } from '@/lib/api'
import { useLevelColors } from '@/lib/theme'

const CN: Record<Fib2Grain, string> = { coarse: '粗', mid: '中', fine: '细' }

const pct = (v: number | null | undefined) =>
  v == null ? '—' : `${(v * 100).toFixed(0)}%`
const num = (v: number | null | undefined, d = 1) =>
  v == null ? '—' : v.toFixed(d)

export function Fib2GrainDialog({
  symbol, current, onPick, onClose,
}: {
  symbol: string
  current: Fib2Grain
  onPick: (g: Fib2Grain) => void
  onClose: () => void
}) {
  const LC = useLevelColors()
  const run = useMutation<Fib2GrainBacktestResult>({
    mutationFn: () => api.fib2GrainBacktest(symbol, true),
  })
  const r = run.data
  const grid = r?.grid ?? []

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        className="flex max-h-[86vh] w-full max-w-2xl flex-col overflow-hidden rounded-dialog border border-border bg-surface shadow-dialog"
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-border/60 px-4 py-3">
          <div className="flex items-center gap-2">
            <FlaskConical className="h-4 w-4" style={{ color: LC.fib2 }} />
            <span className="text-sm font-medium text-foreground">粗细档回测</span>
            <span className="font-mono text-micro text-muted">{symbol}</span>
            {r?.window_days != null && (
              <span className="text-micro text-muted">{r.window_days} 根日线</span>
            )}
          </div>
          <button onClick={onClose} className="text-muted hover:text-foreground">
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="flex-1 space-y-4 overflow-auto p-4">
          {!r && (
            <div className="flex flex-col items-center gap-3 py-10">
              <p className="max-w-md text-center text-body leading-relaxed text-muted">
                回看这只票近三年**每一次上攻**, 看当时画出来的那几条线,
                有没有说中之后实际回踩的最低点。
                <br />
                <span className="text-secondary">
                  评的是「线画得准不准」, 不是「跟着做赚不赚」
                </span>
                —— 这一组不出买卖信号, 没有收益可算。
              </p>
              <button
                onClick={() => run.mutate()}
                disabled={run.isPending}
                className="inline-flex items-center gap-1.5 rounded-btn bg-accent px-4 py-2 text-body font-medium text-on-accent hover:bg-accent/90 disabled:opacity-50"
              >
                {run.isPending
                  ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  : <FlaskConical className="h-3.5 w-3.5" />}
                {run.isPending ? '回测中…' : '一键回测'}
              </button>
              {run.isError && (
                <p className="text-micro text-danger">{(run.error as Error).message}</p>
              )}
            </div>
          )}

          {r?.error && <p className="text-body text-danger">{r.error}</p>}

          {!!grid.length && (
            <>
              <div className="overflow-x-auto rounded-card border border-border/60">
                <table className="w-full min-w-[520px] text-body">
                  <thead className="bg-elevated/40 text-micro text-muted">
                    <tr className="text-right">
                      <th className="px-2 py-1.5 text-left font-normal">档</th>
                      <th className="px-2 py-1.5 font-normal" title="有完整回踩、能评估的上攻段数">
                        样本
                      </th>
                      <th className="px-2 py-1.5 font-normal" title="实际回踩的最低点落在某条回踩位上的比例">
                        说中
                      </th>
                      <th className="px-2 py-1.5 font-normal" title="落在回踩密集带里的比例; 分母是算得出密集带的段数">
                        带里
                      </th>
                      <th className="px-2 py-1.5 font-normal" title="每次平均画几条回踩位 —— 线越多代价越大">
                        画几条
                      </th>
                      <th className="px-2 py-1.5 font-normal" title="说中率 ÷ 画几条。线多本来就更容易蒙中, 不除这一下必然推荐最细那一档">
                        每条的贡献
                      </th>
                      <th className="px-2 py-1.5" />
                    </tr>
                  </thead>
                  <tbody>
                    {grid.map(row => {
                      const picked = r?.rule_suggestion?.grain === row.grain
                      return (
                        <tr
                          key={row.grain}
                          className="border-t border-border/40 text-right font-mono"
                          style={picked ? { backgroundColor: LC.fib2 + '14' } : undefined}
                        >
                          <td className="px-2 py-1.5 text-left font-sans text-foreground">
                            {CN[row.grain]}
                            {row.grain === current && (
                              <span className="ml-1 text-micro text-muted">当前</span>
                            )}
                          </td>
                          <td className="px-2 py-1.5 text-secondary">{row.samples}</td>
                          <td className="px-2 py-1.5 text-foreground">{pct(row.hit_rate)}</td>
                          <td className="px-2 py-1.5 text-secondary">{pct(row.zone_rate)}</td>
                          <td className="px-2 py-1.5 text-secondary">{num(row.avg_lines)}</td>
                          <td className="px-2 py-1.5 font-semibold text-foreground">
                            {num(row.per_line == null ? null : row.per_line * 100, 1)}
                          </td>
                          <td className="px-2 py-1.5">
                            <button
                              onClick={() => { onPick(row.grain); onClose() }}
                              disabled={row.grain === current}
                              className="rounded-btn border border-border px-2 py-0.5 font-sans text-micro text-muted hover:border-accent/40 hover:text-accent disabled:opacity-30"
                            >
                              用这档
                            </button>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>

              {r?.rule_suggestion && (
                <div className="rounded-btn border border-border/60 bg-base/40 px-3 py-2">
                  <div className="mb-0.5 text-micro text-muted">规则建议(纯计算, 可复算)</div>
                  <p className="text-body leading-relaxed text-secondary">
                    {r.rule_suggestion.reason}
                  </p>
                </div>
              )}

              {r?.ai && (
                <div className="rounded-btn border border-accent/30 bg-accent-soft px-3 py-2">
                  <div className="mb-0.5 flex items-center gap-1 text-micro text-accent">
                    <Sparkles className="h-3 w-3" />AI 顾问
                  </div>
                  <p className="text-body leading-relaxed text-secondary">
                    {r.ai.grain ? `建议「${CN[r.ai.grain]}」档 —— ` : ''}{r.ai.reason}
                  </p>
                </div>
              )}
              {r?.ai_error && <p className="text-micro text-muted">{r.ai_error}</p>}

              <p className="text-micro leading-relaxed text-muted">
                「每条的贡献」= 说中率 ÷ 画几条（×100）。
                <span className="text-secondary">线多本来就更容易蒙中</span>
                —— 只按说中率排, 必然推荐最细那一档, 那不是调参是过拟合。
                样本不足 3 次时不给建议; 这里**没有任何收益数字**, 因为这一组不出买卖信号。
              </p>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
