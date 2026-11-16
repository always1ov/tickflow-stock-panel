/**
 * [R431] 个股弹窗「复盘」。
 *
 * [R759] 用户: 「复盘那部分, 保持现在四列排版不变了, 里面内容布局先恢复最开始的样子,
 *   复盘内部的排版要排好显示出所有信息, 我还没想好怎么重做」——
 *   弹窗在 2xl 的四栏(复盘 | 现状 | 主图 | 价位)不动; 复盘栏内部回到 R431 最初那一版
 *   的三块: 逐日复盘(六态与通道两套动作都摆) / 两套买卖的对比 / 六个状态的历史表现。
 *   R749/R750 那版把收盘价、通道档位、成交→了结都收进了悬停, 只剩五列, 信息读不全。
 *
 *   窄列(常驻左列 420~460)摊不开八列, 每天拆成两行:
 *     第一行: 日期 · 收盘 · 涨跌 · 六态状态(第几天 / 细分档 / 转折)
 *     第二行: 通道档位 · 六态与通道的动作 · 成交→了结 · 结果
 *   六态历史同样一行拆两行: 出现次数与天数在上, 段内涨跌与走完后 N 天在下。
 *
 * 数据仍是同一个查询(`useStockReview`)，天数跟头部的 60 / 120 / 250 日走。
 * 判定与文案仍以 R440「不多也不少」为准：这里只改排版与读数, 不改判定。
 */
import { useMemo, useState } from 'react'
import { Loader2 } from 'lucide-react'
import type { ReviewRow, ReviewStateHistory, StockReview } from '@/lib/api'
import { cn } from '@/lib/cn'
import { TREND_FILL } from '@/lib/reviewTimeline'
import { trendBadgeCls } from '@/components/stock-analysis/TrendStateBar'
import { VerdictHover } from '@/components/stock-analysis/VerdictHover'
import {
  EvidencePanel, FLIP_BASIS, LimitTag, SUB_STATE_TIP, VERDICT_BASIS, VERDICT_CLS,
  chgCls, pct, useStockReview,
} from '@/components/stock-analysis/StockReviewDialog'
import {
  LegAct, LegFill, LegResult, REASON_CN, TRADE_STAT_TIPS, legResultCls, legsByFlipDate, tradeNotes,
  type Leg,
} from '@/components/stock-analysis/FlipTradesPanel'
import { PILL, PILL_IDLE, PILL_ON } from './pill'
import { SectionTitle, TYPE } from '@/components/ui'

/** 走完不到这么多段, 「这只票的表现」就提醒样本太少(与脚注同一个数) */
const THIN = 3

export function ReviewSection({ symbol, days, compact = false }: { symbol: string; days: number; compact?: boolean }) {
  const q = useStockReview(symbol, days)
  const d: StockReview | undefined = q.data
  const ok = !!d && !d.error
  const gaps = compact ? 'space-y-5' : 'space-y-6'

  return (
    <section>
      <SectionTitle title="复盘" sub={ok ? `这 ${d.days} 天两套口径各自的结果` : undefined} />
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
        {ok && <DailyCard d={d} compact={compact} />}
        {ok && <SummaryCard d={d} compact={compact} />}
      </div>
    </section>
  )
}

// ===== 1. 逐日复盘 =====

function DailyCard({ d, compact }: { d: StockReview; compact: boolean }) {
  // [R431] 两个筛选各管各的, 都开 = 两类日子都留(并集)。都关 = 全部
  const [marked, setMarked] = useState(false)
  const [shifted, setShifted] = useState(false)
  const six = useMemo(() => legsByFlipDate(d.flip_trades), [d.flip_trades])
  const ch = useMemo(() => legsByFlipDate(d.verdict_trades), [d.verdict_trades])
  const rows = useMemo(() => {
    const all = d.rows ?? []
    if (!marked && !shifted) return all
    return all.filter(r =>
      (marked && (r.limit_up || r.limit_down || r.broken_limit_up || !!r.trend?.flipped))
      || (shifted && !!r.verdict_flipped))
  }, [d, marked, shifted])

  return (
    <div>
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className={TYPE.card}>逐日复盘</span>
        {/* 旧「趋势状态」页页头那一句 */}
        <span className="font-mono text-micro leading-4 text-muted">
          {d.start} ~ {d.end} · {d.days} 个交易日
          {` · 六态阈值 ${(d.threshold * 100).toFixed(0)}%${d.threshold_source !== 'default' ? `(${d.threshold_source})` : ''}`}
        </span>
      </div>

      <div className="mt-1.5 flex flex-wrap justify-end gap-2">
        <button type="button" onClick={() => setMarked(v => !v)} aria-pressed={marked}
                title="只留下有涨跌停、或六态转折的那些天 —— 其余日子状态没变, 复盘时没有信息"
                className={`${PILL} ${marked ? PILL_ON : PILL_IDLE}`}>
          只看有事的日子
        </button>
        <button type="button" onClick={() => setShifted(v => !v)} aria-pressed={shifted}
                title="只留下通道档位换过的那些天 —— 其余日子档位没变, 复盘时没有信息"
                className={`${PILL} ${shifted ? PILL_ON : PILL_IDLE}`}>
          只看换档的日子
        </button>
      </div>

      <div className={cn('mt-1.5 overflow-y-auto border-t border-border/60', compact ? 'max-h-[520px]' : 'max-h-[560px]')}>
        {rows.map(r => (
          <DayRow key={r.date} r={r} six={six.get(r.date)} ch={ch.get(r.date)} />
        ))}
        {rows.length === 0 && (
          <div className="px-2 py-10 text-center text-xs text-muted">这段时间里没有这类日子</div>
        )}
      </div>

      <p className="mt-1.5 text-micro leading-4 text-muted/70">
        两列同源: 一律按收盘算, 六态与决策台「趋势」列同一个状态机、同一个阈值(含你自己调过的那个);
        「通道档位」悬停看完整卡片。
      </p>
    </div>
  )
}

/** 一天两行 —— 窄列摊不开八列, 但八样信息一样不少。 */
function DayRow({ r, six, ch }: { r: ReviewRow; six?: Leg; ch?: Leg }) {
  const legs = ([['六态', six], ['通道', ch]] as const)
    .filter((x): x is readonly ['六态' | '通道', Leg] => !!x[1])
  return (
    <div className={cn(
      'border-b border-border/30 py-1.5',
      (r.trend?.flipped || r.verdict_flipped) && 'bg-warning/[0.06]',
    )}>
      <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
        <span className="font-mono text-micro text-secondary">{r.date.slice(5)}</span>
        <span className="font-mono text-micro font-medium tabular-nums text-foreground">{r.close.toFixed(2)}</span>
        <span className={cn('font-mono text-micro tabular-nums', chgCls(r.change_pct))}>
          {pct(r.change_pct, 2)}
          <LimitTag r={r} />
        </span>
        <span className="flex min-w-0 items-center gap-1">
          {r.trend ? (
            <>
              <span className={cn('inline-flex whitespace-nowrap rounded-btn border px-1 py-px text-micro', trendBadgeCls(r.trend.state))}
                    title={`${r.trend.state_cn}(${r.trend.state_en})`}>
                {r.trend.state_cn} 第 {r.trend.day} 天
              </span>
              {r.trend.sub_state_cn && (
                <span className="text-micro text-muted/60" title={SUB_STATE_TIP}>({r.trend.sub_state_cn})</span>
              )}
              {r.trend.flipped && <span className="text-micro text-warning" title="这天六态状态发生了翻转">← 转折</span>}
            </>
          ) : <span className="text-micro text-muted/40">—</span>}
        </span>
      </div>

      <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
        {/* 通道档位: 当天三档合起来的那一句结论 */}
        <span className="flex items-center gap-1">
          {r.verdict ? (
            <VerdictHover v={r.verdict} note="收盘口径">
              <span className={`inline-flex cursor-help whitespace-nowrap rounded-btn border px-1 py-px text-micro ${VERDICT_CLS[r.verdict.tone]}`}>
                {r.verdict.title}
              </span>
            </VerdictHover>
          ) : <span className="text-micro text-muted/50">三档都在中部</span>}
          {r.verdict_flipped && <span className="text-micro text-warning" title="这天通道档位换了一档">← 换档</span>}
        </span>

        {legs.map(([src, l]) => (
          <span key={src} className="flex items-center gap-1">
            <span className="text-micro text-muted">{src}</span>
            <LegAct leg={l} />
            <span className="font-mono text-micro tabular-nums text-muted"><LegFill leg={l} /></span>
            <span className={cn('font-mono text-micro tabular-nums', legResultCls(l))}><LegResult leg={l} /></span>
          </span>
        ))}
        {legs.length === 0 && <span className="text-micro text-muted/30">—</span>}
      </div>
    </div>
  )
}

// ===== 2 + 3. 两套买卖的对比 / 六个状态的历史表现 =====

function SummaryCard({ d, compact }: { d: StockReview; compact: boolean }) {
  const systems = [
    { name: '按转折买卖 · 六态', ft: d.flip_trades, basis: FLIP_BASIS },
    { name: '按档位买卖 · 通道', ft: d.verdict_trades, basis: VERDICT_BASIS },
  ]
  return (
    <div>
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className={TYPE.card}>两套买卖的对比</span>
        <span className="text-micro text-muted/60">同一只票, 两套口径各自的结果</span>
      </div>

      <div className="mt-1.5 divide-y divide-border/40 border-y border-border/50">
        {systems.map(({ name, ft, basis }) => (
          <SystemRow key={name} name={name} ft={ft} basis={basis} />
        ))}
      </div>

      <StateHistory d={d} compact={compact} />

      {!!d.channel && (
        <div className="mt-4"><EvidencePanel ch={d.channel} edge={d.verdict_edge} compact={compact} /></div>
      )}
    </div>
  )
}

function SystemRow({ name, ft, basis }: {
  name: string; ft: StockReview['flip_trades']; basis: string
}) {
  if (!ft) return null
  if (ft.reason) {
    return (
      <div className="py-2">
        <span className="text-xs font-semibold text-foreground">{name}</span>
        <p className="mt-0.5 text-micro leading-4 text-muted">{REASON_CN[ft.reason]}</p>
      </div>
    )
  }
  // 那几条「别当真」的提醒与数字同进同出(`tradeNotes` 的纪律): 数摆出来、提醒藏起来就是骗人
  const notes = tradeNotes(ft)
  return (
    <div className="py-2">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className="text-xs font-semibold text-foreground" title={basis}>{name}</span>
        <Stat label="跟着做" tip={TRADE_STAT_TIPS.follow} value={pct(ft.follow)} tone={ft.follow} />
        <Stat label="一直拿着" tip={TRADE_STAT_TIPS.hold} value={pct(ft.hold)} tone={ft.hold} />
        <Stat label="多赚" tip={TRADE_STAT_TIPS.excess} value={pct(ft.excess)} tone={ft.excess} />
        <span className="whitespace-nowrap font-mono text-micro tabular-nums text-muted" title={TRADE_STAT_TIPS.trades}>
          买卖 {ft.trades} 次
        </span>
      </div>
      <p className="mt-0.5 text-micro leading-4 text-muted">规则: {basis}</p>
      {notes.map(t => <p key={t} className="mt-0.5 text-micro leading-4 text-warning">{t}</p>)}
    </div>
  )
}

function Stat({ label, tip, value, tone }: { label: string; tip: string; value: string; tone: number | null }) {
  return (
    <span className="whitespace-nowrap font-mono text-xs tabular-nums" title={tip}>
      <span className="text-micro text-muted">{label} </span>
      <span className={cn('font-semibold', chgCls(tone))}>{value}</span>
    </span>
  )
}

/**
 * 「这只票的表现」那一列: **只写客观情况**, 不写该拿该走(用户选的「只摆数」)。
 * 没有可说的就是一道横线 —— 数都在左边几列里了, 再用话复述一遍是重复。
 */
function factOf(s: ReviewStateHistory, days: number): string | null {
  if (s.n === 0) return `这 ${days} 天没出现过`
  if (s.done === 0) return s.current ? '只有眼下这一段, 还没走完' : null
  if (s.done < THIN) return `只走完 ${s.done} 段, 样本太少, 只作参考`
  return null
}

function StateHistory({ d, compact }: { d: StockReview; compact: boolean }) {
  const list = d.state_history ?? []
  if (!list.length) return null
  const cur = list.find(s => s.current)
  const maxDays = Math.max(1, ...list.map(s => s.days))
  const N = d.forward_days

  return (
    <div className={compact ? 'mt-5' : 'mt-6'}>
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <span className={TYPE.card}>六个状态在这只票上的历史表现</span>
          <span className="text-micro text-muted/60">同一个状态在不同股票上差别很大, 这里是这只票自己的记录 · 近 {d.days} 天</span>
        </div>
        <span className="font-mono text-micro text-muted">{d.start} → {d.end}</span>
      </div>

      {/* 怎么看: 只指出现在在哪一行、那一行的数 */}
      {cur && (
        <p className="mt-1.5 text-micro leading-4 text-secondary">
          怎么看: 先找到<b className="text-foreground">当前状态那一行</b>(下表高亮的「{cur.label}」)。
          这只票上它出现过 {cur.n} 次、共 {cur.days} 天
          {cur.done > 0 ? (
            <>
              ; 走完的 {cur.done} 段里, 段里平均 <b className={cn('font-mono', chgCls(cur.avg_ret))}>{pct(cur.avg_ret)}</b>
              {cur.avg_after != null && <>, 走完后 {N} 天平均 <b className={cn('font-mono', chgCls(cur.avg_after))}>{pct(cur.avg_after)}</b></>}
              , {cur.done} 段里 {cur.ret_win} 段收涨。
            </>
          ) : <>, 还没有走完的一段, 结果未知。</>}
        </p>
      )}

      <div className="mt-1.5 border-y border-border/50">
        {list.map(s => {
          const fact = factOf(s, d.days)
          return (
            <div key={s.key}
                 className={cn('border-b border-border/30 py-1.5 last:border-b-0', s.current && 'bg-warning/[0.08]')}>
              <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
                <span className="flex items-center gap-1.5">
                  <span className={cn('h-1.5 w-1.5 shrink-0 rounded-full', TREND_FILL[s.key])} />
                  <span className="text-micro text-foreground">{s.label}</span>
                  {s.current && <span className="text-micro text-muted">当前</span>}
                </span>
                <span className="font-mono text-micro tabular-nums text-secondary">出现过 {s.n || '—'} 次</span>
                <span className="flex items-center gap-1">
                  <span className="font-mono text-micro tabular-nums text-secondary">共 {s.days} 天</span>
                  <span className="h-1 w-16 shrink-0 overflow-hidden rounded-full bg-border/40">
                    <span className="block h-full rounded-full bg-muted/60" style={{ width: `${(s.days / maxDays) * 100}%` }} />
                  </span>
                </span>
              </div>
              <div className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5">
                <span className="whitespace-nowrap text-micro text-muted" title="从进入这个状态前一天收盘, 到它结束那天收盘; 走完的段平均">
                  这段里 <b className={cn('font-mono tabular-nums', chgCls(s.avg_ret))}>{pct(s.avg_ret)}</b>
                </span>
                <span className="whitespace-nowrap text-micro text-muted" title={`这个状态结束之后 ${N} 个交易日的平均涨跌`}>
                  走完后 {N} 天 <b className={cn('font-mono tabular-nums', chgCls(s.avg_after))}>{pct(s.avg_after)}</b>
                </span>
                <span className="whitespace-nowrap text-micro text-muted" title="走完的段里, 涨着结束的有几段">
                  收涨 <b className="font-mono tabular-nums text-secondary">{s.done ? `${s.ret_win}/${s.done}` : '—'}</b>
                </span>
                {fact && <span className="text-micro text-muted/70">{fact}</span>}
              </div>
            </div>
          )
        })}
      </div>

      <p className="mt-1.5 text-micro leading-4 text-muted/70">
        「这段里涨跌」= 从进入这个状态前一天收盘到它结束那天收盘;「走完后 {N} 天」= 这个状态结束之后 {N} 个交易日的平均涨跌;
        「收涨」= 走完的段里涨着结束的有几段。眼下还在走的那一段只计次数和天数。走完不到 {THIN} 段的, 数字只能当参考。
      </p>
    </div>
  )
}
