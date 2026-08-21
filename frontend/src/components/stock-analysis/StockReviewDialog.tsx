/**
 * [R48] 逐日复盘弹窗 —— 决策台「趋势」「结论」两列点进去看的就是这个。
 *
 * 那两列只显示今天。要判断它们靠不靠谱, 得能翻回去看: 上次说"强势深调"是哪天、
 * 之后走了什么、这只票的涨停都出现在什么状态下。
 *
 * 三样东西按同一条时间轴排成一张表 —— 趋势状态、三档通道结论、涨停。数据全部
 * 由后端算, 与决策台那两列同一个状态机、同一组公式、同一个阈值; 这里只负责显示,
 * 不在前端补任何判定, 否则复盘表和列里说的又会是两回事。
 */
import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { CalendarRange, Loader2, X } from 'lucide-react'
import { api, type KeltnerVerdict, type ReviewRow, type StockReview } from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import { trendBadgeCls } from '@/components/stock-analysis/TrendStateBar'

// 与决策台「结论」列同一套配色 —— 两处不一样的话, 翻历史时得先在脑子里做一次换算
const VERDICT_CLS: Record<KeltnerVerdict['tone'], string> = {
  sell: 'border-red-400/40 bg-red-400/10 text-red-400',
  buy: 'border-sky-400/40 bg-sky-400/10 text-sky-300',
  hold: 'border-amber-400/40 bg-amber-400/10 text-amber-400',
  avoid: 'border-border bg-base text-muted',
  watch: 'border-border bg-elevated/60 text-secondary',
}

const RANGES = [60, 120, 250] as const

function pct(v: number | null | undefined, digits = 1): string {
  return v == null ? '—' : `${v > 0 ? '+' : ''}${(v * 100).toFixed(digits)}%`
}

// A股习惯: 涨红跌绿
function chgCls(v: number | null | undefined): string {
  if (v == null || v === 0) return 'text-muted'
  return v > 0 ? 'text-red-400' : 'text-emerald-400'
}

/** 涨停/跌停/炸板标。连板时把第几个板写出来 —— 复盘时"3 板"和"1 板"完全是两回事 */
function LimitTag({ r }: { r: ReviewRow }) {
  if (r.limit_up) {
    return (
      <span
        className="ml-1 inline-flex whitespace-nowrap rounded border border-red-400/50 bg-red-400/15 px-1 text-[9px] text-red-300"
        title={`涨停${r.limit_streak > 1 ? ` · 第 ${r.limit_streak} 个板` : ''}`}
      >
        {r.limit_streak > 1 ? `${r.limit_streak}板` : '涨停'}
      </span>
    )
  }
  if (r.limit_down) {
    return <span className="ml-1 inline-flex rounded border border-emerald-400/50 bg-emerald-400/15 px-1 text-[9px] text-emerald-300">跌停</span>
  }
  if (r.broken_limit_up) {
    return (
      <span
        className="ml-1 inline-flex whitespace-nowrap rounded border border-amber-400/40 bg-amber-400/10 px-1 text-[9px] text-amber-300"
        title="炸板 —— 盘中最高触及涨停但收盘没封住"
      >
        炸板
      </span>
    )
  }
  return null
}

export function StockReviewDialog({ symbol, name, onClose }: {
  symbol: string
  name: string
  onClose: () => void
}) {
  const [days, setDays] = useState<number>(120)
  // 只看有信息的那些天。148 只自选翻 120 行找那 4 天"强势深调"是不现实的
  const [onlyMarked, setOnlyMarked] = useState(false)

  const q = useQuery({
    queryKey: QK.stockReview(symbol, days),
    queryFn: () => api.stockReview(symbol, days),
    staleTime: 5 * 60_000,
  })
  const d: StockReview | undefined = q.data

  const rows = useMemo(() => {
    const all = d?.rows ?? []
    if (!onlyMarked) return all
    return all.filter((r) => r.verdict || r.limit_up || r.limit_down || r.broken_limit_up || r.trend?.flipped)
  }, [d, onlyMarked])

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4" onClick={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        className="flex max-h-[88vh] w-full max-w-5xl flex-col overflow-hidden rounded-lg border border-border bg-surface shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-border/60 px-4 py-3">
          <div className="flex items-baseline gap-2.5">
            <CalendarRange className="h-4 w-4 self-center text-sky-400" />
            <span className="text-sm font-medium text-foreground">{name} 逐日复盘</span>
            <span className="font-mono text-[10px] text-muted">{symbol}</span>
            {d && !d.error && (
              <span className="text-[10px] text-muted">
                {d.start} ~ {d.end} · {d.days} 个交易日 · 六态阈值 {(d.threshold * 100).toFixed(0)}%
                {d.threshold_source !== 'default' ? `(${d.threshold_source})` : ''}
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <div className="flex overflow-hidden rounded-btn border border-border/60">
              {RANGES.map((n) => (
                <button
                  key={n}
                  onClick={() => setDays(n)}
                  className={`px-2 py-1 text-[10px] transition-colors cursor-pointer ${
                    days === n ? 'bg-sky-400/15 text-sky-300' : 'text-muted hover:text-foreground'}`}
                >
                  {n}日
                </button>
              ))}
            </div>
            <button
              onClick={() => setOnlyMarked((v) => !v)}
              title="只留下有结论、有涨跌停、或趋势翻转的那些天 —— 其余的日子复盘时没有信息"
              className={`rounded-btn border px-2 py-1 text-[10px] transition-colors cursor-pointer ${
                onlyMarked ? 'border-sky-400/40 bg-sky-400/15 text-sky-300' : 'border-border/60 text-muted hover:text-foreground'}`}
            >
              只看有事的日子
            </button>
            <button onClick={onClose} className="text-muted hover:text-foreground"><X className="h-4 w-4" /></button>
          </div>
        </div>

        {q.isLoading && (
          <div className="flex items-center justify-center gap-2 py-16 text-xs text-muted">
            <Loader2 className="h-4 w-4 animate-spin" /> 正在回算 {days} 个交易日…
          </div>
        )}
        {q.isError && <div className="px-4 py-16 text-center text-xs text-red-400">复盘数据加载失败</div>}
        {d?.error && <div className="px-4 py-16 text-center text-xs text-muted">{d.error}</div>}

        {d && !d.error && (
          <>
            {/* 涨停统计 —— 用户点进来最先想知道的那几个数 */}
            <div className="grid grid-cols-4 gap-3 px-4 pt-4">
              <div className="rounded-lg border border-red-400/20 bg-red-400/[0.05] px-4 py-3">
                <div className="text-[10px] text-muted">涨停</div>
                <div className="mt-1 font-mono text-2xl font-bold text-red-400">{d.stats.limit_ups}</div>
              </div>
              <div className="rounded-lg border border-border/60 bg-elevated/20 px-4 py-3">
                <div className="text-[10px] text-muted">最高连板</div>
                <div className="mt-1 font-mono text-2xl font-bold text-foreground">{d.stats.max_streak}</div>
              </div>
              <div className="rounded-lg border border-border/60 bg-elevated/20 px-4 py-3">
                <div className="text-[10px] text-muted" title="盘中最高触及涨停但收盘没封住">炸板</div>
                <div className="mt-1 font-mono text-2xl font-bold text-amber-400">{d.stats.broken_limit_ups}</div>
              </div>
              <div className="rounded-lg border border-emerald-400/20 bg-emerald-400/[0.05] px-4 py-3">
                <div className="text-[10px] text-muted">跌停</div>
                <div className="mt-1 font-mono text-2xl font-bold text-emerald-400">{d.stats.limit_downs}</div>
              </div>
            </div>

            {/* 涨停出在什么状态下 —— 趋势里出的板和下跌途中的反抽完全是两回事 */}
            {d.stats.limit_up_states.length > 0 && (
              <div className="flex flex-wrap items-center gap-1.5 px-4 pt-3 text-[10px] text-muted">
                <span>涨停出现在:</span>
                {d.stats.limit_up_states.map((s) => (
                  <span key={s.state_cn} className="rounded border border-border/60 bg-elevated/30 px-1.5 py-0.5 text-secondary">
                    {s.state_cn} {s.n} 次
                  </span>
                ))}
              </div>
            )}

            {/* 结论的后验 —— 「结论」列说的话在这只票身上过去好不好使 */}
            {d.outcomes.length > 0 && (
              <div className="px-4 pt-3">
                <div className="mb-1.5 text-[10px] text-muted">
                  各档结论出现后 {d.forward_days} 日表现(样本小, 只作参考, 不是胜率统计)
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {d.outcomes.map((o) => (
                    <span
                      key={o.code}
                      className={`inline-flex items-center gap-1.5 rounded border px-1.5 py-0.5 text-[10px] ${VERDICT_CLS[o.tone]}`}
                      title={`「${o.title}」在这只票上出现 ${o.n} 次, 之后 ${d.forward_days} 个交易日平均 ${pct(o.avg_fwd)}, 其中 ${o.win} 次收涨`}
                    >
                      {o.title}
                      <span className="opacity-70">{o.n}次</span>
                      <span className={`font-mono ${chgCls(o.avg_fwd)}`}>{pct(o.avg_fwd)}</span>
                    </span>
                  ))}
                </div>
              </div>
            )}

            <div className="mt-3 overflow-auto border-t border-border/60">
              <table className="w-full text-xs">
                <thead className="sticky top-0 z-10 bg-surface">
                  <tr className="border-b border-border/60 text-[10px] text-muted">
                    <th className="whitespace-nowrap px-3 py-2 text-left font-normal">日期</th>
                    <th className="whitespace-nowrap px-2 py-2 text-right font-normal">收盘</th>
                    <th className="whitespace-nowrap px-2 py-2 text-right font-normal">涨跌</th>
                    <th className="whitespace-nowrap px-2 py-2 text-center font-normal">趋势</th>
                    <th className="whitespace-nowrap px-1.5 py-2 text-center font-normal" title="短期 MA20 ± 2.0×ATR14">短</th>
                    <th className="whitespace-nowrap px-1.5 py-2 text-center font-normal" title="中期 MA60 ± 2.5×ATR14">中</th>
                    <th className="whitespace-nowrap px-1.5 py-2 text-center font-normal" title="长期 MA120 ± 3.0×ATR14">长</th>
                    <th className="whitespace-nowrap px-2 py-2 text-center font-normal">结论</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => (
                    <tr
                      key={r.date}
                      className={`border-b border-border/30 hover:bg-elevated/30 ${
                        r.trend?.flipped ? 'bg-amber-400/[0.04]' : ''}`}
                    >
                      <td className="whitespace-nowrap px-3 py-1.5 font-mono text-[10px] text-secondary">
                        {r.date}
                        {r.trend?.flipped && (
                          <span className="ml-1 text-[9px] text-amber-400" title="这天六态状态发生了翻转">转</span>
                        )}
                      </td>
                      <td className="whitespace-nowrap px-2 py-1.5 text-right font-mono tabular-nums text-foreground">
                        {r.close.toFixed(2)}
                      </td>
                      <td className={`whitespace-nowrap px-2 py-1.5 text-right font-mono tabular-nums ${chgCls(r.change_pct)}`}>
                        {pct(r.change_pct, 2)}
                        <LimitTag r={r} />
                      </td>
                      <td className="whitespace-nowrap px-2 py-1.5 text-center">
                        {r.trend ? (
                          <span
                            className={`inline-flex whitespace-nowrap rounded border px-1.5 py-0.5 text-[10px] ${trendBadgeCls(r.trend.state)}`}
                            title={`${r.trend.state_cn}(${r.trend.state_en})· 第 ${r.trend.day} 天`}
                          >
                            {r.trend.state_cn} {r.trend.day}天
                          </span>
                        ) : <span className="text-[10px] text-muted/40">—</span>}
                      </td>
                      {(['s', 'm', 'l'] as const).map((key) => (
                        <td key={key} className="whitespace-nowrap px-1.5 py-1.5 text-center text-[10px] text-secondary">
                          {r.bands[key]?.pos_cn ?? <span className="text-muted/40">—</span>}
                        </td>
                      ))}
                      <td className="whitespace-nowrap px-2 py-1.5 text-center">
                        {r.verdict ? (
                          <span
                            className={`inline-flex whitespace-nowrap rounded border px-1 py-0.5 text-[10px] ${VERDICT_CLS[r.verdict.tone]}`}
                            title={`${r.verdict.action}\n\n${r.verdict.detail}\n\n依据:${r.verdict.bands_text}`}
                          >
                            {r.verdict.title}
                          </span>
                        ) : <span className="text-[10px] text-muted/40">—</span>}
                      </td>
                    </tr>
                  ))}
                  {rows.length === 0 && (
                    <tr>
                      <td colSpan={8} className="px-3 py-10 text-center text-[11px] text-muted">
                        这段时间里没有结论、没有涨跌停、也没有趋势翻转
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>

            <div className="border-t border-border/60 px-4 py-2 text-[10px] leading-relaxed text-muted">
              收盘口径, 与决策台「趋势」「结论」两列同一个状态机、同一组通道公式、同一个阈值。
              均线与 ATR 按<b className="text-secondary">当前</b>复权因子回算 —— 之后除权的话,
              同一天今天算出的通道会和当时屏幕上略有出入, 复盘看的是形态与节奏。
            </div>
          </>
        )}
      </div>
    </div>
  )
}
