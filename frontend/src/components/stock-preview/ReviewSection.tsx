/**
 * [R431] 个股弹窗「复盘」。
 *
 * [R730] 用户: 「弹窗的复盘里面的东西, 重制一个方案, 然后重新排版」——
 *   中栏只有 ~780px, 旧版 8 列逐日表把「结果 / 通道档位」挤到横向滚动条外面,
 *   统计表又要滚到最后才看得到。改成从上到下一条线:
 *   1. 结论条 —— 两套口径的四个数(跟着做 / 一直拿着 / 多赚 / 买卖)提到最上面;
 *   2. 逐日复盘 —— 每条两行: 第一行行情与六态, 第二行只在有交易时出现(动作/成交→了结/结果),
 *      不再横向滚动; 内容与旧表逐项相同(列首的通道档位仍在最右);
 *   3. 六个状态的历史表现 —— 列数收窄。
 * [R731] 用户: 「再整理一次复盘并去掉没有价值的描述和内容」——
 *   删掉重复的解释性长句(两套口径副标题、逐日脚注、状态表怎么看/脚注、样本太少的逐行提醒),
 *   保留动态数字与悬停提示; 「依据」面板不再重复「上面两条结论」这种过时说明。
 *
 * 数据与旧页同一个查询(`useStockReview`), 天数跟头部的 60 / 120 / 250 日走。
 * 逐日复盘的内容口径仍以 R440「不多也不少」为准, 这里只改排版, 不改判定与文案。
 */
import { useMemo, useState } from 'react'
import { Loader2 } from 'lucide-react'
import type { ReviewRow, StockReview } from '@/lib/api'
import { cn } from '@/lib/cn'
import { TREND_FILL } from '@/lib/reviewTimeline'
import { trendBadgeCls } from '@/components/stock-analysis/TrendStateBar'
import { VerdictHover } from '@/components/stock-analysis/VerdictHover'
import {
  EvidencePanel, FLIP_BASIS, LimitTag, SUB_STATE_TIP, VERDICT_CLS,
  chgCls, pct, useStockReview,
} from '@/components/stock-analysis/StockReviewDialog'
import {
  LegAct, LegFill, LegResult, REASON_CN, TRADE_STAT_TIPS, legResultCls,
  legsByFlipDate, tradeNotes,
} from '@/components/stock-analysis/FlipTradesPanel'
import { PILL, PILL_IDLE, PILL_ON } from './pill'
import { SectionTitle, TYPE } from '@/components/ui'

/** 走完不到这么多段只作参考 —— 写进「收涨段数」表头的悬停提示 */
const THIN = 3

export function ReviewSection({ symbol, days }: { symbol: string; days: number }) {
  const q = useStockReview(symbol, days)
  const d: StockReview | undefined = q.data
  const ok = !!d && !d.error

  return (
    <section>
      <SectionTitle title="复盘" />
      <div className="mt-3 space-y-6">
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
        {ok && <VerdictStrip d={d} />}
        {ok && <DailyCard d={d} />}
        {ok && <StateHistory d={d} />}
        {ok && !!d.channel && <EvidencePanel ch={d.channel} edge={d.verdict_edge} />}
      </div>
    </section>
  )
}

// ===== 1. 结论条: 按转折买卖这一套的四个数 =====

function VerdictStrip({ d }: { d: StockReview }) {
  const ft = d.flip_trades
  return (
    <div className="rounded-card border border-border bg-surface/60 px-4 py-3">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <span className={TYPE.card}>按转折买卖 · 六态</span>
        <span className="text-micro text-muted">{FLIP_BASIS}</span>
      </div>

      {!ft ? null : ft.reason ? (
        <p className="mt-2 text-xs text-muted">{REASON_CN[ft.reason]}</p>
      ) : (
        <>
          <div className="mt-3 grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-4">
            <Stat label="跟着做" tip={TRADE_STAT_TIPS.follow} value={pct(ft.follow)} tone={ft.follow} />
            <Stat label="一直拿着" tip={TRADE_STAT_TIPS.hold} value={pct(ft.hold)} tone={ft.hold} />
            <Stat label="多赚" tip={TRADE_STAT_TIPS.excess} value={pct(ft.excess)} tone={ft.excess} />
            <div>
              <div className="text-micro text-muted" title={TRADE_STAT_TIPS.trades}>买卖</div>
              <div className="mt-0.5 font-mono text-lg font-semibold tabular-nums text-secondary">{ft.trades} 次</div>
            </div>
          </div>
          {tradeNotes(ft).map(t => <p key={t} className="mt-2 text-micro leading-5 text-warning">{t}</p>)}
        </>
      )}
    </div>
  )
}

function Stat({ label, tip, value, tone }: { label: string; tip: string; value: string; tone: number | null }) {
  return (
    <div>
      <div className="text-micro text-muted" title={tip}>{label}</div>
      <div className={cn('mt-0.5 font-mono text-lg font-semibold tabular-nums', chgCls(tone))}>{value}</div>
    </div>
  )
}

// ===== 2. 逐日复盘 =====
//
// [R442] 用户: 「逐日复盘并没有和之前一模一样」。R431 把旧复盘页「趋势状态」「通道档位」
// 两个页签的逐日表并成了一张, 光换回原话(R440)不够 —— 并表本身就改了内容。
// [R444] 用户: 「我只看转折所以我有趋势状态就行了, 通道已经在结果列有显示」——
// 只留旧「趋势状态」页那张表(它最后一列就是通道档位), 「通道档位」那一页与页签撤了。
// [R730] 只换排版: 八列收成「两条线」的列表, 判定、文案、脚注全部照旧。

function DailyCard({ d }: { d: StockReview }) {
  // 趋势视图专用: 只看有事的日子(与旧页同一个判据)
  const [onlyMarked, setOnlyMarked] = useState(false)
  const trendRows = useMemo(() => {
    const all = d?.rows ?? []
    if (!onlyMarked) return all
    return all.filter((r) => r.limit_up || r.limit_down || r.broken_limit_up || r.trend?.flipped)
  }, [d, onlyMarked])

  return (
    <div>
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 px-4">
        <span className={TYPE.card}>逐日复盘</span>
        {/* 旧「趋势状态」页页头那一句 */}
        <span className="text-micro text-muted">
          {d.start} ~ {d.end} · {d.days} 个交易日
          {` · 六态阈值 ${(d.threshold * 100).toFixed(0)}%${d.threshold_source !== 'default' ? `(${d.threshold_source})` : ''}`}
        </span>
        <button
          onClick={() => setOnlyMarked(v => !v)}
          title="只留下有涨跌停、或趋势翻转的那些天 —— 其余日子状态没变, 复盘时没有信息"
          className={`ml-auto ${PILL} ${onlyMarked ? PILL_ON : PILL_IDLE}`}
        >
          只看有事的日子
        </button>
      </div>

      <TrendList d={d} rows={trendRows} />

      <div className="px-4 pt-2 text-micro text-muted">
        收盘口径 · 悬停「通道档位」看完整卡片
      </div>
    </div>
  )
}

const ROW_GRID = 'grid grid-cols-[86px_76px_104px_minmax(0,1fr)_112px] items-center gap-x-2'

function TrendList({ d, rows }: { d: StockReview; rows: ReviewRow[] }) {
  const legs = legsByFlipDate(d.flip_trades)
  return (
    <div className="mt-2 max-h-[560px] overflow-auto border-t border-border/60">
      <div className={`${ROW_GRID} sticky top-0 z-10 border-b border-border/60 bg-elevated px-4 py-2 text-micro text-muted`}>
        <span title="日期">日期</span>
        <span className="text-right">收盘</span>
        <span className="text-right">涨跌</span>
        <span className="px-1" title="六态状态与转折">六态状态</span>
        <span className="text-center" title="当天三档通道合起来给出的那一句结论 —— 与决策台「档位」列同一句话, 悬停看完整卡片">通道档位</span>
      </div>

      {rows.map((r) => {
        const leg = legs.get(r.date)
        return (
          <div key={r.date} className={cn('border-b border-border/30 px-4 py-2', r.trend?.flipped && 'bg-warning/[0.06]')}>
            <div className={ROW_GRID}>
              <span className="whitespace-nowrap font-mono text-micro text-secondary">{r.date}</span>
              <span className="text-right font-mono text-xs font-medium tabular-nums text-foreground">{r.close.toFixed(2)}</span>
              <span className={cn('whitespace-nowrap text-right font-mono text-xs tabular-nums', chgCls(r.change_pct))}>
                {pct(r.change_pct, 2)}
                <LimitTag r={r} />
              </span>
              <span className="flex min-w-0 flex-wrap items-center gap-1.5">
                {r.trend ? (
                  <>
                    <span
                      className={`inline-flex whitespace-nowrap rounded-btn border px-1.5 py-0.5 text-micro ${trendBadgeCls(r.trend.state)}`}
                      title={`${r.trend.state_cn}(${r.trend.state_en})`}
                    >
                      {r.trend.state_cn} 第 {r.trend.day} 天
                    </span>
                    {r.trend.sub_state_cn && (
                      <span className="whitespace-nowrap text-micro text-muted/60" title={SUB_STATE_TIP}>
                        ({r.trend.sub_state_cn})
                      </span>
                    )}
                    {r.trend.flipped && (
                      <span className="whitespace-nowrap text-micro text-warning" title="这天六态状态发生了翻转">
                        ← 转折
                      </span>
                    )}
                  </>
                ) : <span className="text-micro text-muted/40">—</span>}
              </span>
              <span className="justify-self-center">
                {r.verdict ? (
                  <VerdictHover v={r.verdict} note="收盘口径">
                    <span className={`inline-flex max-w-[108px] cursor-help truncate rounded-btn border px-1.5 py-0.5 text-micro ${VERDICT_CLS[r.verdict.tone]}`}>
                      {r.verdict.title}
                    </span>
                  </VerdictHover>
                ) : <span className="text-micro text-muted/40">—</span>}
              </span>
            </div>

            {leg && (
              <div className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 rounded-btn bg-elevated/60 px-2 py-1 text-micro">
                <LegAct leg={leg} />
                <span className="font-mono tabular-nums text-muted"><LegFill leg={leg} /></span>
                <span className={cn('ml-auto font-mono tabular-nums', legResultCls(leg))}><LegResult leg={leg} /></span>
              </div>
            )}
          </div>
        )
      })}

      {rows.length === 0 && (
        <div className="px-4 py-10 text-center text-xs text-muted">这段时间里没有涨跌停, 状态也没翻转过</div>
      )}
    </div>
  )
}

// ===== 3. 六个状态在这只票上的历史表现 =====

const STATE_GRID = 'grid grid-cols-[minmax(0,1fr)_92px_120px_minmax(0,1fr)] items-center gap-x-3'

function StateHistory({ d }: { d: StockReview }) {
  const list = d.state_history ?? []
  if (!list.length) return null
  const maxDays = Math.max(1, ...list.map(s => s.days))
  const N = d.forward_days

  return (
    <div>
      <div className="flex flex-wrap items-baseline justify-between gap-x-4">
        <span className={TYPE.card}>六个状态的历史表现</span>
        <span className="font-mono text-xs text-muted">{d.start} → {d.end}</span>
      </div>

      <div className="mt-3 border-t border-border/60">
        <div className={`${STATE_GRID} border-b border-border/60 px-4 py-2 text-micro text-muted`}>
          <span>状态</span>
          <span className="text-right" title="这个状态出现过几次、一共多少天">出现 · 天数</span>
          <span
            className="text-right"
            title={`段内 = 进入这个状态前一天收盘 → 它结束那天收盘; 走完后 ${N} 天 = 状态结束之后 ${N} 个交易日的平均涨跌`}
          >
            段内 · 走完后 {N} 天
          </span>
          <span className="text-right" title={`走完的段里, 涨着结束的有几段(不到 ${THIN} 段只作参考)`}>收涨段数</span>
        </div>

        {list.map(s => (
          <div key={s.key} className={cn(`${STATE_GRID} border-b border-border/30 px-4 py-2`, s.current && 'bg-warning/[0.08]')}>
            <div className="flex min-w-0 items-center gap-2">
              <span className={cn('h-2.5 w-2.5 shrink-0 rounded-full', TREND_FILL[s.key])} />
              <span className="text-xs text-foreground">{s.label}</span>
              {s.current && <span className="text-micro text-muted">当前</span>}
              <span className="ml-1 h-1.5 w-20 shrink-0 overflow-hidden rounded-full bg-border/40">
                <span className="block h-full rounded-full bg-muted/60" style={{ width: `${(s.days / maxDays) * 100}%` }} />
              </span>
            </div>
            <div className="whitespace-nowrap text-right font-mono text-xs tabular-nums text-secondary">
              {s.n || '—'} 次 · {s.days} 天
            </div>
            <div className="whitespace-nowrap text-right font-mono text-xs tabular-nums">
              <span className={chgCls(s.avg_ret)}>{pct(s.avg_ret)}</span>
              <span className="mx-1 text-muted/40">·</span>
              <span className={chgCls(s.avg_after)}>{pct(s.avg_after)}</span>
            </div>
            <div className="whitespace-nowrap text-right font-mono text-xs tabular-nums text-secondary">
              {s.done ? `${s.ret_win}/${s.done}` : '—'}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
