/**
 * [R431] 个股弹窗「复盘」。
 *
 * [R750] 用户: 「分析我的复盘模块符合什么数学理论和模型，我想用统计找出规律」「找出规律后
 *   推翻复盘再次重做」。拿 289 只票 × 250 日跑完统计之后, 这个模块的形状要跟着规律改:
 *
 *   量出来的东西(全市场 67413 个交易日 + 3684 笔):
 *     · 六态里实际只有四个主态; 状态之间的转移近于确定(UT→自然回升 95%,
 *       下跌趋势→自然回调 95%), 但**状态本身指不了方向** —— 之后 5 日的上涨占比
 *       四种状态都在 43%~48%, 全都不到五成;
 *     · 全样本所有状态之后 5 日的中位都是负的(下跌市), 所以「跟着做 vs 一直拿着」
 *       那点差额的来源是**空仓躲跌**, 不是买得准;
 *     · 每笔收益严重右偏厚尾(胜率 40%, 偏度 2.6, 去掉最好 5% 之后均值为负),
 *       所以这里**用中位不用均值**, 也**不能用正态分布去描述**。
 *
 *   于是复盘的顺序改成: 结论(含空仓归因 + 厚尾提醒) → 六态之后的规律 → 权益曲线
 *   (灰色 = 空仓, 把「不在场的价值」画出来) → 逐日。页签与三视图仍然是撤掉的。
 *
 * 数据仍是同一个查询(`useStockReview`)，天数跟头部的 60 / 120 / 250 日走。
 * 判定与文案仍以 R440「不多也不少」为准：这里只改排版与读数, 不改判定。
 */
import { useMemo } from 'react'
import { Loader2 } from 'lucide-react'
import type { ReviewRow, StockReview } from '@/lib/api'
import { cn } from '@/lib/cn'
import { TREND_FILL } from '@/lib/reviewTimeline'
import { ci95, forwardByState, mean, quantile, trades, type Trade } from '@/lib/reviewStats'
import {
  EvidencePanel, FLIP_BASIS, SUB_STATE_TIP, chgCls, pct, useStockReview,
} from '@/components/stock-analysis/StockReviewDialog'
import {
  LegAct, REASON_CN, TRADE_STAT_TIPS, legsByFlipDate, tradeNotes, type Leg,
} from '@/components/stock-analysis/FlipTradesPanel'
import { SectionTitle, TYPE } from '@/components/ui'

export function ReviewSection({ symbol, days, compact = false }: { symbol: string; days: number; compact?: boolean }) {
  const q = useStockReview(symbol, days)
  const d: StockReview | undefined = q.data
  const ok = !!d && !d.error
  const gaps = compact ? 'space-y-5' : 'space-y-6'

  return (
    <section>
      <SectionTitle title="复盘" />
      <div className={cn('mt-3', gaps)}>
        {q.isLoading && (
          <div className="flex items-center justify-center gap-2 rounded-card border border-border bg-surface py-16 text-xs text-muted">
            <Loader2 className="h-4 w-4 animate-spin" /> 正在回算 {days} 个交易日…
          </div>
        )}
        {q.isError && (
          <div className="rounded-card border border-border bg-surface px-4 py-16 text-center text-xs text-danger">复盘数据加载失败</div>
        )}
        {d?.error && (
          <div className="rounded-card border border-border bg-surface px-4 py-16 text-center text-xs text-muted">{d.error}</div>
        )}
        {ok && !!d.channel && <EvidencePanel ch={d.channel} edge={d.verdict_edge} compact={compact} />}
        {ok && <RangeLine d={d} compact={compact} />}
        {ok && <Conclusion d={d} compact={compact} />}
        {ok && <StateForward d={d} compact={compact} />}
        {ok && <EquityChart d={d} compact={compact} />}
        {ok && <DailyTable d={d} compact={compact} />}
      </div>
    </section>
  )
}

/** 旧「趋势状态」页页头那一句 —— 日期区间、交易日数、转折数、六态阈值。 */
function RangeLine({ d, compact }: { d: StockReview; compact: boolean }) {
  const flips = (d.rows ?? []).filter(r => r.trend?.flipped).length
  return (
    <p className={cn('font-mono text-micro leading-4 text-muted', compact && 'px-1')}>
      {d.start} ~ {d.end} · {d.days} 个交易日
      {flips > 0 ? ` · ${flips} 次转折` : ''}
      {` · 六态阈值 ${(d.threshold * 100).toFixed(0)}%${d.threshold_source !== 'default' ? `(${d.threshold_source})` : ''}`}
    </p>
  )
}

// ===== 1. 结论: 一句话 + 一排关键数字 =====

function Conclusion({ d, compact }: { d: StockReview; compact: boolean }) {
  const ft = d.flip_trades
  if (!ft) return null
  if (ft.reason) {
    return <p className="text-xs text-muted">{REASON_CN[ft.reason]}</p>
  }

  // 每笔 = 一次买入到一次卖出（连着两个多头段仍算同一笔），只算已经卖掉的。
  const done = useMemo(() => trades(ft.legs).filter(t => !t.open).map(t => t.ret), [ft])
  const ci = done.length >= 2 ? ci95(done) : null
  // 中位是这里的主读数: 每笔收益严重右偏(少数大赢家把均值抬起来), 中位才是「普通一笔」。
  const med = quantile(done, 0.5)
  const wins = done.filter(r => r > 0).length
  const notes = tradeNotes(ft)

  /** 空仓那几段: A 股散户真正能做的只有「不在场」, 这段的价格变化就是他躲掉/躲错的。 */
  const idle = useMemo(() => {
    let bars = 0
    let chg = 1
    for (const l of ft.legs) {
      if (l.side !== '空头') continue
      bars += l.bars
      chg *= 1 + l.ret
    }
    return bars > 0 ? { bars, chg: chg - 1 } : null
  }, [ft])

  /** 厚尾的证据: 去掉最好的 5% 之后均值还剩多少。样本不足 20 笔就不摆这一行。 */
  const trimmed = useMemo(() => {
    if (done.length < 20) return null
    const k = Math.max(1, Math.round(done.length * 0.05))
    const rest = [...done].sort((a, b) => b - a).slice(k)
    return { k, avg: mean(rest) }
  }, [done])

  // 跑赢/跑输后面跟的是**差距的大小**, 不带正负号 —— 「跑输 +3%」会读成正收益。
  const gap = ft.excess == null ? 0 : Math.abs(ft.excess) * 100
  const head = ft.excess == null
    ? '这组数字的起点终点没对齐, 给不出对比'
    : ft.excess > 0
      ? `这套方法比一直拿着多赚了 ${gap.toFixed(1)} 个点。`
      : ft.excess < 0
        ? `这套方法比一直拿着少赚了 ${gap.toFixed(1)} 个点。`
        : '这套方法和一直拿着差不多。'

  return (
    <div className={cn('rounded-card border border-border bg-surface/60', compact ? 'px-3 py-2' : 'px-4 py-2.5')}>
      <p className="text-xs leading-5 text-foreground">{head}</p>

      <div className="mt-1 flex flex-wrap items-baseline gap-x-2 gap-y-1" title={FLIP_BASIS}>
        <Inline label="跟着做" tip={TRADE_STAT_TIPS.follow} value={pct(ft.follow)} tone={ft.follow} />
        <Inline label="一直拿着" tip={TRADE_STAT_TIPS.hold} value={pct(ft.hold)} tone={ft.hold} />
        <Inline label="差额" tip={TRADE_STAT_TIPS.excess} value={pct(ft.excess)} tone={ft.excess} />
        <span className="ml-auto whitespace-nowrap font-mono text-micro tabular-nums text-muted" title={TRADE_STAT_TIPS.trades}>
          买卖 {ft.trades} 次
        </span>
      </div>

      {/* 差额是从哪来的 —— 全市场统计里, 所有状态之后 5 日的中位都是负的, 所以价值在空仓不在买卖点。 */}
      {idle && (
        <p className="mt-1 text-micro leading-4 text-muted">
          其中 <span className="font-mono tabular-nums text-secondary">{idle.bars}</span> 天空仓，这期间这只票
          {idle.chg <= 0 ? '跌了 ' : '涨了 '}
          <span className={cn('font-mono tabular-nums', chgCls(idle.chg))}>{pct(Math.abs(idle.chg))}</span>
          {idle.chg <= 0 ? '，差额主要是躲开这一段来的。' : '，这一段是躲错了，差额被它拖累。'}
        </p>
      )}

      {ci && (
        <p
          className="mt-1 text-micro leading-4 text-muted"
          title={`一笔 = 一次买入到一次卖出; 连着两个多头段仍算同一笔。\n中位数不受少数大赢家影响; 平均数的 95% 置信区间是 ${pct(ci.lo)} ~ ${pct(ci.hi)}。`}
        >
          走完的 {done.length} 笔里赚了 {wins} 笔，中位{' '}
          <span className={cn('font-mono font-semibold tabular-nums', chgCls(med))}>{pct(med, 2)}</span>
          ，平均 <span className={cn('font-mono tabular-nums', chgCls(ci.mean))}>{pct(ci.mean, 2)}</span>
          <span className="text-muted/60">（{pct(ci.lo)} ~ {pct(ci.hi)}）</span>
          {ci.lo <= 0 && ci.hi >= 0 && <span className="text-warning/80"> · 笔数太少，这个平均还不算数</span>}
        </p>
      )}

      {trimmed && (
        <p className="mt-0.5 text-micro leading-4 text-warning/90">
          赚的钱集中在少数几笔：去掉最好的 {trimmed.k} 笔，平均每笔就变成{' '}
          <span className="font-mono tabular-nums">{pct(trimmed.avg, 2)}</span>。
        </p>
      )}

      {notes.map(t => <p key={t} className="mt-0.5 text-micro leading-4 text-warning">{t}</p>)}
    </div>
  )
}

function Inline({ label, tip, value, tone }: { label: string; tip: string; value: string; tone: number | null }) {
  return (
    <span className="whitespace-nowrap font-mono text-xs tabular-nums" title={tip}>
      <span className="text-micro text-muted">{label} </span>
      <span className={cn('font-semibold', chgCls(tone))}>{value}</span>
    </span>
  )
}

// ===== 2. 六态之后的规律 =====

function StateForward({ d, compact }: { d: StockReview; compact: boolean }) {
  const stats = useMemo(() => forwardByState(d.rows ?? [], 5), [d.rows])
  if (!stats.length) return null
  const thin = stats.every(s => s.n < 30)
  const cols = compact
    ? 'grid grid-cols-[minmax(0,1fr)_38px_44px_58px] items-center gap-x-1.5'
    : 'grid grid-cols-[minmax(0,1fr)_56px_64px_88px] items-center gap-x-2'

  return (
    <div>
      <div className={cn('flex flex-wrap items-baseline gap-x-3 gap-y-1', compact && 'px-1')}>
        <span className={TYPE.card}>六态之后的 5 天</span>
        <span className="text-micro text-muted/60">这只票自己的记录 · 中位比均值耐看</span>
      </div>

      <div className="mt-1.5 rounded-card border border-border bg-surface/40">
        <div className={cn('border-b border-border/60 py-1.5 pl-2 pr-2 text-micro text-muted whitespace-nowrap', cols)}>
          <span>状态</span>
          <span className="text-right">出现</span>
          <span className="text-right">之后5天</span>
          <span className="text-right">上涨占比</span>
        </div>
        {stats.map(s => (
          <div key={s.state} className={cn('border-b border-border/30 py-1.5 pl-2 pr-2', cols)}>
            <span className="flex min-w-0 items-center gap-1.5">
              <span className={cn('h-1.5 w-1.5 shrink-0 rounded-full', TREND_FILL[s.state])} />
              <span className="truncate text-micro text-foreground">{s.stateCn}</span>
            </span>
            <span className="text-right font-mono text-micro tabular-nums text-muted">{s.n}</span>
            <span className={cn('text-right font-mono text-micro tabular-nums', chgCls(s.median))}>
              {pct(s.median)}
            </span>
            <span
              className="text-right font-mono text-micro tabular-nums text-secondary"
              title={s.n ? `之后 5 天收涨 ${s.wins} 天 / 共 ${s.n} 天` : undefined}
            >
              {s.n ? `${((s.wins / s.n) * 100).toFixed(0)}%` : '—'}
            </span>
          </div>
        ))}
      </div>

      <p className={cn('mt-1 text-micro leading-4 text-muted/70', compact && 'px-1')}>
        289 只票 250 日一起量过：四种状态之后 5 天的上涨占比都在 43%~48%，全都没到五成 ——
        状态本身指不了方向，上面哪一行高过五成，多半是运气。
        {thin && ' 这只票每档都不到 30 天，只能当个印象。'}
      </p>
    </div>
  )
}

// ===== 3. 权益曲线: 跟着做 vs 一直拿着 =====

type CurvePoint = {
  date: string
  /** 一直拿着: 收盘 / 第一天收盘 */
  hold: number
  /** 跟着做: 只在场内时跟随涨跌, 空仓期走平 */
  strat: number
  /** 这天在空仓 —— 策略线走平, 曲线上铺一块灰底 */
  flat: boolean
  /** 这天开盘有没有动作 —— 曲线上的圆点 */
  act?: '买入' | '卖出'
}

/**
 * 逐日净值。两条线都从**第一次成交那天开盘**起算（与后端 follow / hold 同一个
 * 起点与终点），所以曲线末端的读数能跟结论条上那两个数对上，不会出现「图上 -24%，
 * 结论 -26%」这种自己打自己的情况。买入日按开盘价成交、当天收盘就计入；卖出日
 * 开盘离场，从开盘价到前一日收盘的那一段仍是持仓收益。空仓期策略这条线走平 ——
 * 统计上这份差额就是空仓躲出来的, 所以图上的灰底才是重点。
 */
function curveOf(rows: ReviewRow[], legs: Leg[]): CurvePoint[] {
  const a = [...rows].reverse()
  const buy = new Map<string, number>()
  const sell = new Map<string, number>()
  for (const l of legs) {
    if (l.side === '多头') buy.set(l.enter_date, l.enter_price)
    else sell.set(l.enter_date, l.enter_price)
  }

  const origin = legs.length ? { date: legs[0].enter_date, price: legs[0].enter_price } : null
  let hold = 1
  let strat = 1
  let inMarket = false
  let started = false
  let prev: number | null = null

  return a.map((r) => {
    const on = origin != null && r.date >= origin.date
    const b = buy.get(r.date)
    const s = sell.get(r.date)
    let act: CurvePoint['act']

    if (on && !started) {
      // 起点那天: 拿第一笔的开盘价当基准
      started = true
      hold *= r.close / origin!.price
      if (b != null) {
        strat *= r.close / b
        inMarket = true
        act = '买入'
      }
    } else if (on && prev != null) {
      const base = prev
      hold *= r.close / base
      if (!inMarket && b != null) {
        strat *= r.close / b
        inMarket = true
        act = '买入'
      } else if (inMarket && s != null) {
        strat *= s / base
        inMarket = false
        act = '卖出'
      } else if (inMarket) {
        strat *= r.close / base
      }
    }

    prev = r.close
    return { date: r.date, hold, strat, flat: started && !inMarket, act }
  })
}

function EquityChart({ d, compact }: { d: StockReview; compact: boolean }) {
  const pts = useMemo(() => curveOf(d.rows ?? [], d.flip_trades?.legs ?? []), [d.rows, d.flip_trades])
  if (pts.length < 2) return null

  const W = 400
  const H = 120
  // 左边留出半个圆点的位置 —— 首尾那两天的买卖点不该被画布裁掉
  const L = 5
  const R = 5
  const T = 6
  const B = 6
  const plotW = W - L - R
  const plotH = H - T - B
  const n = pts.length

  const vals = [...pts.map(p => p.hold), ...pts.map(p => p.strat), 1]
  let lo = Math.min(...vals)
  let hi = Math.max(...vals)
  if (hi - lo < 0.02) {
    const mid = (hi + lo) / 2
    lo = mid - 0.01
    hi = mid + 0.01
  }
  const pad = (hi - lo) * 0.1
  lo -= pad
  hi += pad

  const x = (i: number) => L + (i / (n - 1)) * plotW
  const y = (v: number) => T + (1 - (v - lo) / (hi - lo)) * plotH
  const line = (k: 'hold' | 'strat') =>
    pts.map((p, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(p[k]).toFixed(1)}`).join(' ')
  const step = plotW / (n - 1)
  const last = pts[n - 1]

  return (
    <div>
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 px-1">
        <span className={TYPE.card}>权益曲线</span>
        <span className="whitespace-nowrap font-mono text-micro tabular-nums text-secondary">
          跟着做 <span className={chgCls(last.strat - 1)}>{pct(last.strat - 1)}</span>
        </span>
        <span className="whitespace-nowrap font-mono text-micro tabular-nums text-muted">
          一直拿着 <span className={chgCls(last.hold - 1)}>{pct(last.hold - 1)}</span>
        </span>
        <span className="ml-auto flex shrink-0 items-center gap-2 whitespace-nowrap text-micro text-muted/60">
          <span className="flex items-center gap-1">
            <span className="h-1.5 w-1.5 rounded-full bg-bull" />买入
          </span>
          <span className="flex items-center gap-1">
            <span className="h-1.5 w-1.5 rounded-full bg-bear" />卖出
          </span>
          <span className="flex items-center gap-1">
            <span className="h-2 w-2 rounded-[1px] bg-muted/20" />空仓
          </span>
        </span>
      </div>

      <div className={cn('mt-2', compact ? 'px-1' : 'px-1')}>
        <div className="flex gap-1">
          <div className="flex shrink-0 flex-col justify-between py-0.5 text-right font-mono text-micro tabular-nums text-muted/60">
            <span>{pct(hi - 1, 0)}</span>
            <span>{pct(lo - 1, 0)}</span>
          </div>
          <svg
            viewBox={`0 0 ${W} ${H}`}
            preserveAspectRatio="none"
            className="h-32 w-full"
            role="img"
            aria-label={`权益曲线: 跟着做 ${pct(last.strat - 1)}, 一直拿着 ${pct(last.hold - 1)}; 灰底是空仓期, 圆点是买卖日`}
          >
            {/* 空仓期 —— 把「不在场」画出来: 全市场统计里差额就来自这些日子 */}
            {pts.map((p, i) => !p.flat ? null : (
              <rect
                key={`f${p.date}`}
                x={x(i) - step / 2}
                y={T}
                width={step}
                height={plotH}
                className="text-muted"
                fill="currentColor"
                fillOpacity={0.1}
              />
            ))}

            <line
              x1={L} y1={y(1)} x2={L + plotW} y2={y(1)}
              strokeDasharray="3 3" strokeWidth={1} vectorEffect="non-scaling-stroke"
              className="text-border" style={{ stroke: 'currentColor' }}
            />
            <path
              d={line('hold')} fill="none" strokeWidth={1.2}
              strokeDasharray="4 3" vectorEffect="non-scaling-stroke"
              className="text-muted" style={{ stroke: 'currentColor', opacity: 0.8 }}
            />
            <path
              d={line('strat')} fill="none" strokeWidth={1.6}
              vectorEffect="non-scaling-stroke"
              className="text-foreground" style={{ stroke: 'currentColor' }}
            />

            {pts.map((p, i) => p.act && (
              <circle
                key={`a${p.date}`}
                cx={x(i)} cy={y(p.strat)} r={2.2}
                className={p.act === '买入' ? 'text-bull' : 'text-bear'}
                fill="currentColor"
              >
                <title>{`${p.date} 开盘${p.act} · 净值 ${(p.strat).toFixed(3)}`}</title>
              </circle>
            ))}
          </svg>
        </div>
        <div className="mt-0.5 flex justify-between font-mono text-micro tabular-nums text-muted/60">
          <span>{pts[0].date.slice(5)}</span>
          <span>{last.date.slice(5)}</span>
        </div>
      </div>
    </div>
  )
}

// ===== 4. 逐日 =====

const ROW_COLS = 'grid grid-cols-[64px_minmax(0,1fr)_64px_56px_76px] items-center gap-x-2'
/** [R732] 常驻左列(420~460)的窄版: 日期收两格, 五列挤进 400px */
const ROW_COLS_COMPACT = 'grid grid-cols-[44px_minmax(0,1fr)_52px_48px_68px] items-center gap-x-2'

/** 悬停时把这一天的原始记录补齐 —— 五列放不下的收盘价、涨跌停、通道档位都在这里。 */
function rowTitle(r: ReviewRow, leg?: Leg): string {
  const parts = [r.date, `收盘 ${r.close.toFixed(2)}`, `涨跌 ${pct(r.change_pct, 2)}`]
  if (r.limit_up) parts.push(`涨停${r.limit_streak > 1 ? ` · 第 ${r.limit_streak} 个板` : ''}`)
  if (r.limit_down) parts.push('跌停')
  if (r.broken_limit_up) parts.push('炸板(盘中触板, 收盘没封住)')
  parts.push(r.trend
    ? `六态 ${r.trend.state_cn} 第 ${r.trend.day} 天${r.trend.sub_state_cn ? `(${r.trend.sub_state_cn})` : ''}${r.trend.flipped ? ' · 转折' : ''}`
    : '六态 — 停牌或数据不足')
  if (r.verdict) parts.push(`通道档位 ${r.verdict.title}`)
  if (leg) {
    parts.push(`${leg.act} ${leg.enter_date.slice(5)} ${leg.enter_price.toFixed(2)} → ${leg.exit_date.slice(5)} ${leg.exit_price.toFixed(2)}`)
    if (leg.delayed > 0) parts.push(`顺延 ${leg.delayed} 个交易日才成交`)
  }
  return parts.join(' · ')
}

/** 每天手里有没有货 —— 买入日开盘进场, 卖出日开盘离场, 中间一直算在场内。 */
function positionByDate(rows: ReviewRow[], legs: Leg[]): Map<string, boolean> {
  const buy = new Set<string>()
  const sell = new Set<string>()
  for (const l of legs) (l.side === '多头' ? buy : sell).add(l.enter_date)
  const out = new Map<string, boolean>()
  let inMarket = false
  for (const r of [...rows].reverse()) {
    if (buy.has(r.date)) inMarket = true
    if (sell.has(r.date)) inMarket = false
    out.set(r.date, inMarket)
  }
  return out
}

function DailyTable({ d, compact }: { d: StockReview; compact: boolean }) {
  const rows = d.rows ?? []
  const legs = useMemo(() => legsByFlipDate(d.flip_trades), [d.flip_trades])
  const held = useMemo(() => positionByDate(rows, d.flip_trades?.legs ?? []), [rows, d.flip_trades])
  // 「结果」只在卖出那行落账, 给的是**这一笔交易**从头到尾的盈亏(按卖出成交日记),
  // 不是这一天的涨跌(涨跌在左边那列), 也不是空头段的涨跌(空头段跌了反而是好事)。
  const closed = useMemo(() => {
    const m = new Map<string, Trade>()
    for (const t of trades(d.flip_trades?.legs ?? [])) if (!t.open) m.set(t.exit, t)
    return m
  }, [d.flip_trades])
  /** 还没了结的那一笔 —— 买入那行写「还没卖」, 免得空着让人以为漏了。 */
  const openBuy = useMemo(
    () => new Set(trades(d.flip_trades?.legs ?? []).filter(t => t.open).map(t => t.enter)),
    [d.flip_trades],
  )
  const cols = compact ? ROW_COLS_COMPACT : ROW_COLS
  const empty = <span className="text-micro text-muted/30">—</span>

  return (
    <div>
      <div className={cn('flex flex-wrap items-baseline gap-x-3 gap-y-1', compact && 'px-1')}>
        <span className={TYPE.card}>逐日复盘</span>
        <span className="text-micro text-muted/60">最近的在最上面 · 结果只在卖出那行落账 · 悬停看收盘价与通道档位</span>
      </div>
      <p className={cn('mt-0.5 text-micro leading-4 text-muted/60', compact && 'px-1')}>
        自然回升 / 回撤是走反方向的正常波动，带「次级」的是这段波动里的回抽。
      </p>

      <div className={cn('mt-2 border-t border-border/60', compact ? '' : 'max-h-[560px] overflow-y-auto')}>
        <div className={cn(
          'sticky top-0 z-10 border-b border-border/60 bg-elevated py-2 pl-1 pr-2 text-micro text-muted',
          cols,
        )}>
          <span>日期</span>
          <span>状态</span>
          <span className="text-right">涨跌</span>
          <span>动作</span>
          <span className="text-right">结果</span>
        </div>

        {rows.map((r) => {
          const leg = legs.get(r.date)
          // 卖出这一格对应的正是那天开盘了结的那一笔
          const tr = leg?.act === '卖出' ? closed.get(leg.enter_date) : undefined
          return (
            <div
              key={r.date}
              title={rowTitle(r, leg)}
              className={cn(
                'border-b border-border/30 py-1.5 pl-1 pr-2',
                cols,
                r.trend?.flipped && 'bg-warning/[0.06]',
              )}
            >
              <span className="whitespace-nowrap font-mono text-micro text-secondary">{r.date.slice(5)}</span>

              <span className="flex min-w-0 items-center gap-1.5">
                {r.trend ? (
                  <>
                    <span className={cn('h-1.5 w-1.5 shrink-0 rounded-full', TREND_FILL[r.trend.state])} />
                    <span className="truncate text-micro text-foreground">{r.trend.state_cn}</span>
                    <span className="shrink-0 font-mono text-micro tabular-nums text-muted">第{r.trend.day}天</span>
                    {r.trend.sub_state_cn && (
                      <span className="shrink-0 text-micro text-muted/50" title={SUB_STATE_TIP}>
                        ({r.trend.sub_state_cn})
                      </span>
                    )}
                    {r.trend.flipped && <span className="shrink-0 text-micro text-warning">转</span>}
                  </>
                ) : empty}
              </span>

              <span className={cn('whitespace-nowrap text-right font-mono text-xs tabular-nums', chgCls(r.change_pct))}>
                {pct(r.change_pct, 2)}
              </span>

              <span className="min-w-0">
                {leg ? <LegAct leg={leg} /> : (
                  <span className={cn('text-micro', held.get(r.date) ? 'text-muted' : 'text-muted/40')}>
                    {held.get(r.date) ? '持有中' : '空仓'}
                  </span>
                )}
              </span>

              {/* 结果只在卖出那天落账: 买入那天还没卖, 中间的日子也都还没了结,
                  写了数只会让人以为「当天就赚了这么多」。 */}
              <span className={cn(
                'whitespace-nowrap text-right font-mono text-micro tabular-nums',
                tr ? chgCls(tr.ret) : 'text-muted/30',
              )}>
                {tr ? (
                  <>
                    {pct(tr.ret, 2)}
                    <span className="ml-1 text-muted/50">{tr.bars}天</span>
                  </>
                ) : leg?.act === '买入' && openBuy.has(leg.enter_date) ? (
                  <span className="text-muted/50">还没卖</span>
                ) : '—'}
              </span>
            </div>
          )
        })}

        {rows.length === 0 && (
          <div className="px-4 py-10 text-center text-xs text-muted">这段时间没有可以复盘的交易日</div>
        )}
      </div>
    </div>
  )
}
