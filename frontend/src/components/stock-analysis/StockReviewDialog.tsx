/**
 * [R48] 逐日复盘弹窗 —— 决策台「趋势」「结论」两列点进去看的就是这个。
 *
 * [R51] 两列点开的**不是同一张表**。原来两边都弹出同一份逐日表格, 结论那一列
 * 点进去只是在趋势表最右边多一个 4 字徽标, 等于把列里已经有的东西又抄了一遍。
 * 现在分成两个视图, 各答各的问题:
 *
 *   · 趋势视图(从「趋势」列点进来): 这个状态是怎么走到今天的。一张精简的
 *     逐日表 —— 日期/收盘/涨跌(带涨停标)/状态, 转折那天单独标出来。
 *     状态是这一列的全部内容, 表里就不该混进通道那套。
 *   · 结论视图(从「结论」列点进来): 把每天的**悬停卡片**摊开。徽标背后那三段
 *     (怎么做/为什么/依据)才是这一列真正的内容, 复盘时要看的正是它们。
 *     连续同一档的天合并成一段 —— 「强势深调」连着 4 天时铺 4 张一模一样的
 *     卡片才是真的重复; 合成一段再标出天数, 反而看得出这一档持续了多久。
 *
 * 两个视图共用同一份数据(一次请求), 顶部可以互相切换 —— 从哪一列进来只决定
 * 默认落在哪个视图, 不把人锁死。
 */
import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { CalendarRange, Loader2, X } from 'lucide-react'
import { api, type KeltnerVerdict, type ReviewRow, type StockReview } from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import { trendBadgeCls } from '@/components/stock-analysis/TrendStateBar'

export type ReviewTab = 'trend' | 'verdict'

// 与决策台「结论」列同一套配色 —— 两处不一样的话, 翻历史时得先在脑子里做一次换算
const VERDICT_CLS: Record<KeltnerVerdict['tone'], string> = {
  sell: 'border-red-400/40 bg-red-400/10 text-red-400',
  buy: 'border-sky-400/40 bg-sky-400/10 text-sky-300',
  hold: 'border-amber-400/40 bg-amber-400/10 text-amber-400',
  avoid: 'border-border bg-base text-muted',
  watch: 'border-border bg-elevated/60 text-secondary',
}
const VERDICT_BAR: Record<KeltnerVerdict['tone'], string> = {
  sell: 'bg-red-400',
  buy: 'bg-sky-400',
  hold: 'bg-amber-400',
  avoid: 'bg-border',
  watch: 'bg-secondary/60',
}

const RANGES = [60, 120, 250] as const
const BAND_CN: Record<'s' | 'm' | 'l', string> = { s: '短期', m: '中期', l: '长期' }

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

/** 连续同一档结论合成一段。rows 是新→旧, 段内也保持这个顺序。 */
type Segment = { v: KeltnerVerdict; rows: ReviewRow[] }

function toSegments(rows: ReviewRow[]): Segment[] {
  const out: Segment[] = []
  let prevIdx = -2      // 上一条有结论的行在 rows 里的下标
  rows.forEach((r, i) => {
    if (!r.verdict) return
    const last = out[out.length - 1]
    // 只有**紧挨着**的同一档才并段。中间隔了没有结论的日子就是两次独立出现,
    // 并起来会把"这一档连着出现了几天"说多。
    if (last && last.v.code === r.verdict.code && prevIdx === i - 1) last.rows.push(r)
    else out.push({ v: r.verdict, rows: [r] })
    prevIdx = i
  })
  return out
}

export function StockReviewDialog({ symbol, name, tab: initialTab, onClose }: {
  symbol: string
  name: string
  /** 从哪一列点进来 —— 只决定默认视图 */
  tab: ReviewTab
  onClose: () => void
}) {
  const [tab, setTab] = useState<ReviewTab>(initialTab)
  const [days, setDays] = useState<number>(120)
  // 趋势视图专用: 只看有事的日子。120 行里找那几天转折是不现实的
  const [onlyMarked, setOnlyMarked] = useState(false)

  const q = useQuery({
    queryKey: QK.stockReview(symbol, days),
    queryFn: () => api.stockReview(symbol, days),
    staleTime: 5 * 60_000,
  })
  const d: StockReview | undefined = q.data

  const trendRows = useMemo(() => {
    const all = d?.rows ?? []
    if (!onlyMarked) return all
    return all.filter((r) => r.limit_up || r.limit_down || r.broken_limit_up || r.trend?.flipped)
  }, [d, onlyMarked])

  const segments = useMemo(() => toSegments(d?.rows ?? []), [d])

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4" onClick={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        className="flex max-h-[88vh] w-full max-w-5xl flex-col overflow-hidden rounded-lg border border-border bg-surface shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between gap-3 border-b border-border/60 px-4 py-3">
          <div className="flex min-w-0 items-baseline gap-2.5">
            <CalendarRange className="h-4 w-4 self-center shrink-0 text-sky-400" />
            <span className="shrink-0 text-sm font-medium text-foreground">{name} 复盘</span>
            <span className="shrink-0 font-mono text-[10px] text-muted">{symbol}</span>
            {d && !d.error && (
              <span className="truncate text-[10px] text-muted">
                {d.start} ~ {d.end} · {d.days} 个交易日
                {tab === 'trend' && ` · 六态阈值 ${(d.threshold * 100).toFixed(0)}%${d.threshold_source !== 'default' ? `(${d.threshold_source})` : ''}`}
              </span>
            )}
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <div className="flex overflow-hidden rounded-btn border border-border/60">
              {([['trend', '趋势状态'], ['verdict', '通道结论']] as const).map(([k, label]) => (
                <button
                  key={k}
                  onClick={() => setTab(k)}
                  className={`px-2.5 py-1 text-[10px] transition-colors cursor-pointer ${
                    tab === k ? 'bg-sky-400/15 text-sky-300' : 'text-muted hover:text-foreground'}`}
                >
                  {label}
                </button>
              ))}
            </div>
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

        {d && !d.error && tab === 'trend' && (
          <TrendView d={d} rows={trendRows} onlyMarked={onlyMarked} onToggleMarked={() => setOnlyMarked((v) => !v)} />
        )}
        {d && !d.error && tab === 'verdict' && <VerdictView d={d} segments={segments} />}
      </div>
    </div>
  )
}

// ===== 趋势视图: 这个状态是怎么走到今天的 =====

function TrendView({ d, rows, onlyMarked, onToggleMarked }: {
  d: StockReview
  rows: ReviewRow[]
  onlyMarked: boolean
  onToggleMarked: () => void
}) {
  return (
    <>
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

      <div className="flex items-center justify-end px-4 pt-3">
        <button
          onClick={onToggleMarked}
          title="只留下有涨跌停、或趋势翻转的那些天 —— 其余日子状态没变, 复盘时没有信息"
          className={`rounded-btn border px-2 py-1 text-[10px] transition-colors cursor-pointer ${
            onlyMarked ? 'border-sky-400/40 bg-sky-400/15 text-sky-300' : 'border-border/60 text-muted hover:text-foreground'}`}
        >
          只看有事的日子
        </button>
      </div>

      <div className="mt-2 overflow-auto border-t border-border/60">
        <table className="w-full text-xs">
          <thead className="sticky top-0 z-10 bg-surface">
            <tr className="border-b border-border/60 text-[10px] text-muted">
              <th className="whitespace-nowrap px-3 py-2 text-left font-normal">日期</th>
              <th className="whitespace-nowrap px-2 py-2 text-right font-normal">收盘</th>
              <th className="whitespace-nowrap px-2 py-2 text-right font-normal">涨跌</th>
              <th className="whitespace-nowrap px-3 py-2 text-left font-normal">六态状态</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr
                key={r.date}
                className={`border-b border-border/30 hover:bg-elevated/30 ${r.trend?.flipped ? 'bg-amber-400/[0.05]' : ''}`}
              >
                <td className="whitespace-nowrap px-3 py-1.5 font-mono text-[10px] text-secondary">{r.date}</td>
                <td className="whitespace-nowrap px-2 py-1.5 text-right font-mono tabular-nums text-foreground">{r.close.toFixed(2)}</td>
                <td className={`whitespace-nowrap px-2 py-1.5 text-right font-mono tabular-nums ${chgCls(r.change_pct)}`}>
                  {pct(r.change_pct, 2)}
                  <LimitTag r={r} />
                </td>
                <td className="whitespace-nowrap px-3 py-1.5">
                  {r.trend ? (
                    <>
                      <span
                        className={`inline-flex whitespace-nowrap rounded border px-1.5 py-0.5 text-[10px] ${trendBadgeCls(r.trend.state)}`}
                        title={`${r.trend.state_cn}(${r.trend.state_en})`}
                      >
                        {r.trend.state_cn} 第 {r.trend.day} 天
                      </span>
                      {r.trend.flipped && (
                        <span className="ml-1.5 text-[9px] text-amber-400" title="这天六态状态发生了翻转">
                          ← 转折
                        </span>
                      )}
                    </>
                  ) : <span className="text-[10px] text-muted/40">—</span>}
                </td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr><td colSpan={4} className="px-3 py-10 text-center text-[11px] text-muted">这段时间里没有涨跌停, 状态也没翻转过</td></tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="border-t border-border/60 px-4 py-2 text-[10px] leading-relaxed text-muted">
        收盘口径, 与决策台「趋势」列同一个状态机、同一个阈值(含你自己调过的那个)。
      </div>
    </>
  )
}

// ===== 结论视图: 把每天的悬停卡片摊开 =====

function VerdictView({ d, segments }: { d: StockReview; segments: Segment[] }) {
  return (
    <>
      {/* 各档结论在这只票上过去好不好使 */}
      {d.outcomes.length > 0 && (
        <div className="px-4 pt-4">
          <div className="mb-1.5 text-[10px] text-muted">
            各档结论出现后 {d.forward_days} 日表现(样本小, 只作参考, 不是胜率统计)
          </div>
          <div className="flex flex-wrap gap-1.5">
            {d.outcomes.map((o) => (
              <span
                key={o.code}
                className={`inline-flex items-center gap-1.5 rounded border px-1.5 py-0.5 text-[10px] ${VERDICT_CLS[o.tone]}`}
                title={`「${o.title}」在这只票上出现 ${o.n} 天, 之后 ${d.forward_days} 个交易日平均 ${pct(o.avg_fwd)}, 其中 ${o.win} 天收涨`}
              >
                {o.title}
                <span className="opacity-70">{o.n}天</span>
                <span className={`font-mono ${chgCls(o.avg_fwd)}`}>{pct(o.avg_fwd)}</span>
              </span>
            ))}
          </div>
        </div>
      )}

      <div className="mt-3 flex-1 overflow-auto border-t border-border/60 p-4">
        {segments.length === 0 && (
          <div className="py-14 text-center text-[11px] text-muted">
            这段时间里三档通道一直在中部 —— 位置上没有可说的, 听趋势和信号的
          </div>
        )}
        <div className="space-y-2.5">
          {segments.map((seg) => <SegmentCard key={seg.rows[0].date} seg={seg} forwardDays={d.forward_days} />)}
        </div>
      </div>

      <div className="border-t border-border/60 px-4 py-2 text-[10px] leading-relaxed text-muted">
        每一段就是决策台「结论」列当时悬停会看到的那张卡片。收盘口径, 同一组通道公式。
        均线与 ATR 按<b className="text-secondary">当前</b>复权因子回算 —— 之后除权的话,
        同一天今天算出的通道会和当时屏幕上略有出入, 复盘看的是形态与节奏。
      </div>
    </>
  )
}

/**
 * 一段结论 = 决策台上当时悬停会看到的那张卡片, 加上"这几天实际走了什么"。
 *
 * 「之后 N 日」取这一段**最后一天**的前瞻收益 —— 一档结论连着出现几天时,
 * 真正该问的是"它最后一次说完之后怎么样了", 拿段首那天算等于把段内的涨跌
 * 也算进兑现里。
 */
function SegmentCard({ seg, forwardDays }: { seg: Segment; forwardDays: number }) {
  const { v, rows } = seg
  const newest = rows[0]              // rows 是新→旧
  const oldest = rows[rows.length - 1]
  const span = rows.reduce((a, r) => a * (1 + (r.change_pct ?? 0)), 1) - 1
  const limitUps = rows.filter((r) => r.limit_up).length
  const bands = (['s', 'm', 'l'] as const).filter((k) => oldest.bands[k])

  return (
    <div className="flex overflow-hidden rounded-lg border border-border/60 bg-elevated/20">
      <div className={`w-1 shrink-0 ${VERDICT_BAR[v.tone]}`} />
      <div className="min-w-0 flex-1 px-3 py-2.5">
        <div className="flex flex-wrap items-baseline gap-2">
          <span className={`inline-flex shrink-0 whitespace-nowrap rounded border px-1.5 py-0.5 text-[11px] ${VERDICT_CLS[v.tone]}`}>
            {v.title}
          </span>
          <span className="shrink-0 font-mono text-[10px] text-secondary">
            {rows.length > 1 ? `${oldest.date} ~ ${newest.date}` : newest.date}
          </span>
          <span className="shrink-0 text-[10px] text-muted">{rows.length} 天</span>
          <span className={`shrink-0 font-mono text-[10px] ${chgCls(span)}`} title="这一段期间的累计涨跌">
            期间 {pct(span)}
          </span>
          {limitUps > 0 && (
            <span className="shrink-0 rounded border border-red-400/50 bg-red-400/15 px-1 text-[9px] text-red-300">
              含 {limitUps} 次涨停
            </span>
          )}
          <span
            className={`ml-auto shrink-0 font-mono text-[10px] ${chgCls(newest.fwd)}`}
            title={newest.fwd == null
              ? `这一段结束还不到 ${forwardDays} 个交易日, 结果未知`
              : `这一档最后一次出现(${newest.date})之后 ${forwardDays} 个交易日的涨跌`}
          >
            之后{forwardDays}日 {newest.fwd == null ? '待定' : pct(newest.fwd)}
          </span>
        </div>

        {/* 徽标背后的三段 —— 这才是「结论」列真正的内容 */}
        <div className="mt-2 rounded border border-border/60 bg-base/60 px-2 py-1.5">
          <div className="text-[9px] text-muted">怎么做</div>
          <div className="mt-0.5 text-[11px] leading-snug text-foreground">{v.action}</div>
        </div>
        <div className="mt-1.5 text-[10px] leading-relaxed text-secondary">{v.detail}</div>
        <div className="mt-1.5 flex flex-wrap items-baseline gap-1.5">
          <span className="text-[9px] text-muted">依据</span>
          <span className="text-[10px] text-secondary">{v.bands_text}</span>
          <span className="text-[9px] text-muted/70">·</span>
          {bands.map((k) => (
            <span key={k} className="rounded border border-border/60 px-1 text-[9px] text-muted">
              {BAND_CN[k]}{oldest.bands[k]!.pos_cn}
            </span>
          ))}
        </div>
      </div>
    </div>
  )
}
