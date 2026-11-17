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
 *
 * [R792] 用户: 「复盘部分简化保留重点」「内容都不可以折叠, 逐日复盘里面别搞滚动」——
 *   重点先行: 两套买卖对比 → 当前状态那只票上的记录 → 逐日明细 → 通道证据;
 *   全部常开不折叠(六态显示全表、逐日全部铺开), 去掉内滚与三段长脚注(细节留在 title 悬停)。
 *
 * [R793] 用户: 「复盘里面密密麻麻好多文字…出个简洁显示的方案, 但不能丢失原有所有显示内容」——
 *   三块全部改成「表头 + 单行多列」: 重复的「出现过/共/这段里/走完后」前缀收进表头,
 *   逐日每天从两行压成一行; 规则、成交价、样本提示等原文不删, 全部挂到 title 悬停。
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
        {ok && <SummaryCard d={d} compact={compact} />}
        {ok && <DailyCard d={d} />}
      </div>
    </section>
  )
}

// ===== 1. 逐日复盘 =====

function DailyCard({ d }: { d: StockReview }) {
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

      {/* [R792] 不做内滚: 逐日全部铺开, 交给弹窗整体滚动 */}
      <div className="mt-1.5 border-t border-border/60">
        <div className={cn(DAY_COLS, 'sticky top-0 z-10 border-b border-border/40 bg-surface py-1 text-micro text-muted')}>
          <span>日期</span>
          <span className="text-right">收盘</span>
          <span className="text-right">涨跌</span>
          <span>趋势</span>
          <span>档位</span>
          <span title="六态 / 通道这一天的动作、结果与持仓天数; 成交价与顺延见悬停">事件</span>
        </div>
        {rows.map(r => (
          <DayRow key={r.date} r={r} six={six.get(r.date)} ch={ch.get(r.date)} />
        ))}
        {rows.length === 0 && (
          <div className="px-2 py-10 text-center text-xs text-muted">这段时间里没有这类日子</div>
        )}
      </div>
    </div>
  )
}

/** 六列一行: 日期 · 收盘 · 涨跌 · 趋势 · 档位 · 事件(原两行压成一行)。 */
const DAY_COLS = 'grid grid-cols-[2.2rem_2.9rem_3.4rem_minmax(0,1fr)_minmax(0,4.2rem)_minmax(0,1.5fr)] items-baseline gap-x-1.5'

function legTip(src: string, l: Leg): string {
  const ret = l.side === '多头' ? pct(l.ret) : `空仓 ${pct(l.ret)}`
  return `${src} ${l.act}：${l.enter_date} ${l.enter_price.toFixed(2)} → ${l.exit_date} ${l.exit_price.toFixed(2)}`
    + `${l.open_ended ? '（这一段还没走完, 按最后一天收盘记）' : ''}，${ret}，${l.bars} 天`
    + `${l.delayed ? `，顺延 ${l.delayed} 个交易日成交` : ''}`
}

function DayRow({ r, six, ch }: { r: ReviewRow; six?: Leg; ch?: Leg }) {
  const legs = ([['六态', six], ['通道', ch]] as const)
    .filter((x): x is readonly ['六态' | '通道', Leg] => !!x[1])
  return (
    <div className={cn(
      DAY_COLS,
      'border-b border-border/30 py-1.5',
      (r.trend?.flipped || r.verdict_flipped) && 'bg-warning/[0.06]',
    )}>
      <span className="font-mono text-micro text-secondary">{r.date.slice(5)}</span>

      <span className="text-right font-mono text-micro font-medium tabular-nums text-foreground">
        {r.close.toFixed(2)}
      </span>

      <span className={cn('text-right font-mono text-micro tabular-nums', chgCls(r.change_pct))}>
        {pct(r.change_pct, 2)}<LimitTag r={r} />
      </span>

      <span className="flex min-w-0 flex-wrap items-center gap-x-1">
        {r.trend ? (
          <>
            <span className={cn('inline-flex whitespace-nowrap rounded-btn border px-1 py-px text-micro', trendBadgeCls(r.trend.state))}
                  title={`${r.trend.state_cn}(${r.trend.state_en})`}>
              {r.trend.state_cn} {r.trend.day}天
            </span>
            {r.trend.sub_state_cn && (
              <span className="text-micro text-muted/60" title={SUB_STATE_TIP}>({r.trend.sub_state_cn})</span>
            )}
            {r.trend.flipped && <span className="text-micro text-warning" title="这天六态状态发生了翻转">转折</span>}
          </>
        ) : <span className="text-micro text-muted/40">—</span>}
      </span>

      {/* 通道档位: 当天三档合起来的那一句结论 */}
      <span className="flex min-w-0 items-center gap-x-1">
        {r.verdict ? (
          <VerdictHover v={r.verdict} note="收盘口径">
            <span className={`inline-flex cursor-help whitespace-nowrap rounded-btn border px-1 py-px text-micro ${VERDICT_CLS[r.verdict.tone]}`}>
              {r.verdict.title}
            </span>
          </VerdictHover>
        ) : <span className="text-micro text-muted/50" title="三档都在中部">中部</span>}
        {r.verdict_flipped && <span className="text-micro text-warning" title="这天通道档位换了一档">换档</span>}
      </span>

      <span className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-0.5">
        {legs.length > 0 ? legs.map(([src, l]) => (
          <span key={src} className="flex min-w-0 flex-wrap items-center gap-x-1 gap-y-0" title={legTip(src, l)}>
            <span className="text-micro text-muted">{src === '六态' ? '六' : '通'}</span>
            <LegAct leg={l} />
            <span className="font-mono text-micro tabular-nums text-muted"><LegFill leg={l} /></span>
            <span className={cn('font-mono text-micro tabular-nums', legResultCls(l))}><LegResult leg={l} /></span>
          </span>
        )) : <span className="text-micro text-muted/30">—</span>}
      </span>
    </div>
  )
}

// ===== 2 + 3. 两套买卖的对比 / 六个状态的历史表现 =====

const SYS_COLS = 'grid grid-cols-[minmax(0,1fr)_3.8rem_3.8rem_3.8rem_2.6rem] items-baseline gap-x-1.5'

function SummaryCard({ d, compact }: { d: StockReview; compact: boolean }) {
  const systems = [
    { name: '按转折买卖 · 六态', ft: d.flip_trades, basis: FLIP_BASIS },
    { name: '按档位买卖 · 通道', ft: d.verdict_trades, basis: VERDICT_BASIS },
  ]
  // 提醒与数字同进同出(R440 tradeNotes 的纪律): 一条不删, 只从「每条一段」并成一行
  const notes = systems.flatMap(({ ft }, i) =>
    ft && !ft.reason ? tradeNotes(ft).map(t => ({ i, t })) : [])
  return (
    <div>
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className={TYPE.card}>两套买卖的对比</span>
        <span className="text-micro text-muted/60">同一只票, 两套口径各自的结果</span>
      </div>

      <div className="mt-1.5 border-y border-border/50">
        <div className={cn(SYS_COLS, 'border-b border-border/40 py-1 text-micro text-muted')}>
          <span title="每套口径的规则全文, 悬停口径名查看">口径</span>
          <span className="text-right" title={TRADE_STAT_TIPS.follow}>跟着做</span>
          <span className="text-right" title={TRADE_STAT_TIPS.hold}>一直拿着</span>
          <span className="text-right" title={TRADE_STAT_TIPS.excess}>多赚</span>
          <span className="text-right" title={TRADE_STAT_TIPS.trades}>买卖</span>
        </div>
        {systems.map(({ name, ft, basis }) => (
          <SystemRow key={name} name={name} ft={ft} basis={basis} />
        ))}
      </div>

      <p className="mt-1 text-micro leading-4 text-muted">规则：两套各自独立统计，完整口径见上方口径名悬停。</p>

      {notes.length > 0 && (
        <p className="mt-0.5 text-micro leading-4 text-warning">
          注意：{notes.map(({ i, t }) => `${i === 0 ? '①' : '②'}${t}`).join('；')}
        </p>
      )}

      <StateHistory d={d} compact={compact} />

      {!!d.channel && (
        <div className="mt-3 border-t border-border/40 pt-2">
          <div className="mb-1 text-micro text-muted">通道证据（三档明细）</div>
          <EvidencePanel ch={d.channel} edge={d.verdict_edge} compact={compact} />
        </div>
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
      <div className="border-b border-border/30 py-1.5 last:border-b-0">
        <span className="text-micro font-semibold text-foreground">{name}</span>
        <span className="ml-2 text-micro text-muted">{REASON_CN[ft.reason]}</span>
      </div>
    )
  }
  return (
    <div className={cn(SYS_COLS, 'border-b border-border/30 py-1.5 last:border-b-0')}>
      <span className="truncate text-micro font-semibold text-foreground" title={`${name}｜规则: ${basis}`}>
        {name}
      </span>
      <span className={cn('text-right font-mono text-micro tabular-nums', chgCls(ft.follow))}>
        <StatCell tip={TRADE_STAT_TIPS.follow} value={pct(ft.follow)} tone={ft.follow} />
      </span>
      <span className={cn('text-right font-mono text-micro tabular-nums', chgCls(ft.hold))}>
        <StatCell tip={TRADE_STAT_TIPS.hold} value={pct(ft.hold)} tone={ft.hold} />
      </span>
      <span className={cn('text-right font-mono text-micro tabular-nums', chgCls(ft.excess))}>
        <StatCell tip={TRADE_STAT_TIPS.excess} value={pct(ft.excess)} tone={ft.excess} />
      </span>
      <span className="text-right font-mono text-micro tabular-nums text-muted" title={TRADE_STAT_TIPS.trades}>
        {ft.trades} 次
      </span>
    </div>
  )
}

function StatCell({ tip, value }: { tip: string; value: string; tone: number | null }) {
  return <span title={tip}>{value}</span>
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

const STATE_COLS = 'grid grid-cols-[minmax(0,1fr)_2.6rem_4.6rem_3.6rem_3.6rem_2.8rem] items-baseline gap-x-1.5'

function StateHistory({ d, compact }: { d: StockReview; compact: boolean }) {
  const list = d.state_history ?? []
  if (!list.length) return null
  const maxDays = Math.max(1, ...list.map(s => s.days))
  const N = d.forward_days

  return (
    <div className={compact ? 'mt-5' : 'mt-6'}>
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <span className={TYPE.card}>六个状态在这只票上的历史表现</span>
          <span className="text-micro text-muted/60">这只票自己的记录 · 近 {d.days} 天</span>
        </div>
        <span className="font-mono text-micro text-muted">{d.start} → {d.end}</span>
      </div>

      {/* [R793] 表头承载原来每行重复的前缀词, 六态各占一行、不折叠; 当前状态高亮 */}
      <div className="mt-1.5 border-y border-border/50">
        <div className={cn(STATE_COLS, 'border-b border-border/40 py-1 text-micro text-muted')}>
          <span>状态</span>
          <span className="text-right" title="这个状态在近 N 天里出现过几次">次数</span>
          <span className="text-right" title="这个状态一共占了多少个交易日">天数</span>
          <span className="text-right" title="从进入这个状态前一天收盘, 到它结束那天收盘; 走完的段平均">段内</span>
          <span className="text-right" title={`这个状态结束之后 ${N} 个交易日的平均涨跌`}>后 {N} 天</span>
          <span className="text-right" title="走完的段里, 涨着结束的有几段">收涨</span>
        </div>
        {list.map(s => {
          const fact = factOf(s, d.days)
          const badge = s.n === 0 ? '无' : s.done === 0 ? '未走完' : (s.done < THIN ? '样本少' : null)
          return (
            <div key={s.key}
                 className={cn(STATE_COLS, 'border-b border-border/30 py-1.5 last:border-b-0', s.current && 'bg-warning/[0.08]')}>
              <span className="flex min-w-0 items-center gap-1">
                <span className={cn('h-1.5 w-1.5 shrink-0 rounded-full', TREND_FILL[s.key])} />
                <span className="truncate text-micro text-foreground" title={s.label}>{s.label}</span>
                {s.current && <span className="shrink-0 text-micro text-muted">当前</span>}
                {badge && <span className="shrink-0 text-micro text-muted/70" title={fact ?? undefined}>{badge}</span>}
              </span>
              <span className="text-right font-mono text-micro tabular-nums text-secondary">{s.n || '—'}</span>
              <span className="flex items-center justify-end gap-1">
                <span className="font-mono text-micro tabular-nums text-secondary">{s.days}</span>
                <span className="h-1 w-10 shrink-0 overflow-hidden rounded-full bg-border/40">
                  <span className="block h-full rounded-full bg-muted/60" style={{ width: `${(s.days / maxDays) * 100}%` }} />
                </span>
              </span>
              <span className={cn('text-right font-mono text-micro tabular-nums', chgCls(s.avg_ret))}>{pct(s.avg_ret)}</span>
              <span className={cn('text-right font-mono text-micro tabular-nums', chgCls(s.avg_after))}>{pct(s.avg_after)}</span>
              <span className="text-right font-mono text-micro tabular-nums text-secondary">
                {s.done ? `${s.ret_win}/${s.done}` : '—'}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}
