/**
 * [R431] 个股弹窗重做第三块:「复盘」。
 *
 * 用户给的排版图, 从上到下三样:
 *   1. 逐日复盘 —— 旧复盘页「趋势状态」那一页的逐日表, 逐格照抄, 只换样式
 *      (R431 并表 → R442 拆回两张 → R444 只留趋势状态, 见下方「1. 逐日复盘」);
 *   2. 两套买卖的对比 —— 跟着做 / 一直拿着 / 多赚 / 买卖次数 / 规则, 一套一行
 *      ([R441] 「按档位买卖 · 通道」那一行删了, 只剩六态);
 *   3. 六个状态在这只票上的历史表现 —— **只摆数, 不下结论**(用户选的):
 *      图里那一列「一进这档就该走, 不抢反弹」是建议, 而自然回撤在上升趋势里并不
 *      算坏, 写「该走」就是多给一次卖出理由(交易哲学: 趋势没坏就不给卖出理由)。
 *      所以「这只票的表现」只写客观情况, 「怎么看」只指出现在在哪一行、那一行的数。
 *
 * 旧的复盘页(旧顶栏「复盘」)原样留着, 等用户说删再删。那一页的「现在」行
 * (跌破 / 站上价、该盯什么、这一格历来)与两条状态色带, 这张图里没有 ——
 * 删旧的时候要先问它们去哪。[R438] 其中「这一格历来」用户已经说了「没用了」, 不用问。
 *
 * 数据与旧页同一个查询(`useStockReview`), 天数跟头部的 60 / 120 / 250 日走。
 *
 * [R440] 用户: 「逐日复盘可以保留样式, 但是内容必须和以前一模一样, 不多也不少」。
 * R440 只把改写过的几句换回原话, 仍是一张并表; R442 连并表一起撤了。
 */
import { useMemo, useState } from 'react'
import { Loader2 } from 'lucide-react'
import type { ReviewRow, ReviewStateHistory, StockReview } from '@/lib/api'
import { cn } from '@/lib/cn'
import { TREND_FILL } from '@/lib/reviewTimeline'
import { trendBadgeCls } from '@/components/stock-analysis/TrendStateBar'
import { VerdictHover } from '@/components/stock-analysis/VerdictHover'
import {
  EvidencePanel, FLIP_BASIS, LimitTag, SUB_STATE_TIP, VERDICT_CLS,
  chgCls, pct, useStockReview,
} from '@/components/stock-analysis/StockReviewDialog'
import {
  FlipTradeCells, REASON_CN, TRADE_STAT_TIPS, legsByFlipDate, tradeNotes,
} from '@/components/stock-analysis/FlipTradesPanel'
import { PILL, PILL_IDLE, PILL_ON } from './pill'
import { SectionTitle, TYPE } from '@/components/ui'

/** 走完不到这么多段, 「这只票的表现」就提醒样本太少(与图里脚注同一个数) */
const THIN = 3

export function ReviewSection({ symbol, days }: { symbol: string; days: number }) {
  const q = useStockReview(symbol, days)
  const d: StockReview | undefined = q.data
  const ok = !!d && !d.error

  return (
    <section>
      <SectionTitle title="复盘" sub={ok ? `这 ${d.days} 天两套口径各自的结果` : undefined} />
      <div className="mt-3 space-y-4">
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
        {ok && <DailyCard d={d} />}
        {ok && <SummaryCard d={d} />}
      </div>
    </section>
  )
}

// ===== 1. 逐日复盘 =====
//
// [R442] 用户: 「逐日复盘并没有和之前一模一样」。R431 把旧复盘页「趋势状态」「通道档位」
// 两个页签的逐日表并成了一张, 光换回原话(R440)不够 —— 并表本身就改了内容。
// [R444] 用户: 「我只看转折所以我有趋势状态就行了, 通道已经在结果列有显示」——
// 只留旧「趋势状态」页那张表(它最后一列就是通道档位), 「通道档位」那一页与页签撤了。
// 表、筛选开关、脚注逐格照抄旧页(`StockReviewDialog` 的 TrendView), 只换样式;
// 守卫把新旧去掉 className 之后逐字比对。

const TH = 'whitespace-nowrap px-2 py-2 font-normal'
const TD = 'whitespace-nowrap px-2 py-2'
const BADGE = 'inline-flex whitespace-nowrap rounded-btn border px-1.5 py-0.5 text-micro'
const MARK = 'ml-1.5 text-micro text-warning'
const DASH = 'text-micro text-muted/40'

function DailyCard({ d }: { d: StockReview }) {
  // 趋势视图专用: 只看有事的日子(与旧页同一个判据)
  const [onlyMarked, setOnlyMarked] = useState(false)
  const trendRows = useMemo(() => {
    const all = d?.rows ?? []
    if (!onlyMarked) return all
    return all.filter((r) => r.limit_up || r.limit_down || r.broken_limit_up || r.trend?.flipped)
  }, [d, onlyMarked])

  return (
    <div className="rounded-card border border-border bg-surface">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 px-4 py-3">
        <span className={TYPE.card}>逐日复盘</span>
        {/* 旧「趋势状态」页页头那一句 */}
        <span className="text-micro text-muted">
          {d.start} ~ {d.end} · {d.days} 个交易日
          {` · 六态阈值 ${(d.threshold * 100).toFixed(0)}%${d.threshold_source !== 'default' ? `(${d.threshold_source})` : ''}`}
        </span>
      </div>
      <TrendTable d={d} rows={trendRows} onlyMarked={onlyMarked}
                  onToggleMarked={() => setOnlyMarked((v) => !v)} />
    </div>
  )
}

/** 旧「趋势状态」页那张逐日表 */
function TrendTable({ d, rows, onlyMarked, onToggleMarked }: {
  d: StockReview
  rows: ReviewRow[]
  onlyMarked: boolean
  onToggleMarked: () => void
}) {
  const legs = legsByFlipDate(d.flip_trades)
  return (
    <>
      <div className="flex items-center justify-end gap-2 px-4 pb-3">
        <button
          onClick={onToggleMarked}
          title="只留下有涨跌停、或趋势翻转的那些天 —— 其余日子状态没变, 复盘时没有信息"
          className={`${PILL} ${onlyMarked ? PILL_ON : PILL_IDLE}`}
        >
          只看有事的日子
        </button>
      </div>

      <div className="max-h-[560px] overflow-auto border-t border-border/60">
        <table className="w-full text-xs">
          <thead className="sticky top-0 z-10 bg-elevated">
            <tr className="text-micro text-muted">
              <th className={`${TH} pl-4 text-left`}>日期</th>
              <th className={`${TH} text-right`}>收盘</th>
              <th className={`${TH} text-right`}>涨跌</th>
              <th className={`${TH} px-3 text-left`}>六态状态</th>
              <th className={`${TH} text-left`} title="按转折买卖: 这次转折的次日开盘该干什么">动作</th>
              <th className={`${TH} text-right`} title="成交日与成交价 → 了结日与了结价, 都是开盘价">成交 → 了结</th>
              <th className={`${TH} text-right`} title="多头段是真赚到的; 空头段是空仓期间股价的涨跌, 不是你的盈亏">结果</th>
              <th className={`${TH} pr-4 text-center`} title="当天三档通道合起来给出的那一句结论 —— 与决策台「档位」列同一句话, 悬停看完整卡片">通道档位</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr
                key={r.date}
                className={cn('border-b border-border/30', r.trend?.flipped && 'bg-warning/[0.06]')}
              >
                <td className={`${TD} pl-4 font-mono text-secondary`}>{r.date}</td>
                <td className={`${TD} text-right font-mono font-medium tabular-nums text-foreground`}>{r.close.toFixed(2)}</td>
                <td className={`${TD} text-right font-mono tabular-nums ${chgCls(r.change_pct)}`}>
                  {pct(r.change_pct, 2)}
                  <LimitTag r={r} />
                </td>
                <td className={`${TD} px-3`}>
                  {r.trend ? (
                    <>
                      <span
                        className={`${BADGE} ${trendBadgeCls(r.trend.state)}`}
                        title={`${r.trend.state_cn}(${r.trend.state_en})`}
                      >
                        {r.trend.state_cn} 第 {r.trend.day} 天
                      </span>
                      {r.trend.sub_state_cn && (
                        <span className="ml-1 text-micro text-muted/60" title={SUB_STATE_TIP}>
                          ({r.trend.sub_state_cn})
                        </span>
                      )}
                      {r.trend.flipped && (
                        <span className={MARK} title="这天六态状态发生了翻转">
                          ← 转折
                        </span>
                      )}
                    </>
                  ) : <span className={DASH}>—</span>}
                </td>
                <FlipTradeCells leg={legs.get(r.date)} />
                <td className={`${TD} pr-4 text-center`}>
                  {r.verdict ? (
                    <VerdictHover v={r.verdict} note="收盘口径">
                      <span className={`${BADGE} cursor-help ${VERDICT_CLS[r.verdict.tone]}`}>
                        {r.verdict.title}
                      </span>
                    </VerdictHover>
                  ) : <span className={DASH}>—</span>}
                </td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr><td colSpan={8} className="px-4 py-10 text-center text-xs text-muted">这段时间里没有涨跌停, 状态也没翻转过</td></tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="px-4 py-3 text-micro leading-5 text-muted">
        收盘口径, 与决策台「趋势」列同一个状态机、同一个阈值(含你自己调过的那个)。
        「通道档位」列悬停看完整卡片。
      </div>
    </>
  )
}

// ===== 2 + 3. 按转折买卖(R441 起只剩这一套) / 六个状态的历史表现 =====

function SummaryCard({ d }: { d: StockReview }) {
  const systems = [
    { name: '按转折买卖 · 六态', ft: d.flip_trades, basis: FLIP_BASIS },
    // [R441] 「按档位买卖 · 通道」那一行删了(用户指着它: 「删除」)。
    // 逐日表里通道那一笔笔动作不动 —— 那是旧「通道档位」表的原有内容(R440)
  ]
  return (
    <div className="rounded-card border border-border bg-surface p-4">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border/60 text-micro text-muted">
            <th className="py-2 pr-3 text-left font-normal">口径</th>
            <th className="px-3 py-2 text-right font-normal" title={TRADE_STAT_TIPS.follow}>跟着做</th>
            <th className="px-3 py-2 text-right font-normal" title={TRADE_STAT_TIPS.hold}>一直拿着</th>
            <th className="px-3 py-2 text-right font-normal" title={TRADE_STAT_TIPS.excess}>多赚</th>
            <th className="px-3 py-2 text-right font-normal" title={TRADE_STAT_TIPS.trades}>买卖</th>
            <th className="py-2 pl-3 text-left font-normal">规则</th>
          </tr>
        </thead>
        <tbody>
          {systems.map(({ name, ft, basis }) => (
            <SystemRow key={name} name={name} ft={ft} basis={basis} />
          ))}
        </tbody>
      </table>

      <StateHistory d={d} />

      {!!d.channel && <div className="mt-2"><EvidencePanel ch={d.channel} edge={d.verdict_edge} /></div>}
    </div>
  )
}

function SystemRow({ name, ft, basis }: {
  name: string; ft: StockReview['flip_trades']; basis: string
}) {
  const head = <td className="whitespace-nowrap py-3 pr-3 font-semibold text-foreground">{name}</td>
  if (!ft) return null
  if (ft.reason) {
    return (
      <tr className="border-b border-border/40">
        {head}
        <td colSpan={5} className="px-3 py-3 text-xs text-muted">{REASON_CN[ft.reason]}</td>
      </tr>
    )
  }
  // 那几条「别当真」的提醒与数字同进同出(`tradeNotes` 的纪律): 数摆出来、提醒藏起来就是骗人
  const notes = tradeNotes(ft)
  const num = (v: number | null) => (
    <td className={cn('whitespace-nowrap px-3 py-3 text-right font-mono text-lg font-semibold tabular-nums', chgCls(v))}>
      {pct(v)}
    </td>
  )
  return (
    <>
      <tr className={cn(!notes.length && 'border-b border-border/40')}>
        {head}
        {num(ft.follow)}
        {num(ft.hold)}
        {num(ft.excess)}
        <td className="whitespace-nowrap px-3 py-3 text-right font-mono tabular-nums text-secondary">{ft.trades} 次</td>
        <td className="py-3 pl-3 text-xs text-muted">{basis}</td>
      </tr>
      {notes.length > 0 && (
        <tr className="border-b border-border/40">
          <td />
          <td colSpan={5} className="px-3 pb-3 text-micro leading-5 text-warning">
            {notes.map(t => <p key={t}>{t}</p>)}
          </td>
        </tr>
      )}
    </>
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

function StateHistory({ d }: { d: StockReview }) {
  const list = d.state_history ?? []
  if (!list.length) return null
  const cur = list.find(s => s.current)
  const maxDays = Math.max(1, ...list.map(s => s.days))
  const N = d.forward_days

  return (
    <div className="mt-6">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <span className={TYPE.card}>六个状态在这只票上的历史表现</span>
          <span className="text-xs text-muted">同一个状态在不同股票上差别很大, 这里是这只票自己的记录 · 近 {d.days} 天</span>
        </div>
        <span className="font-mono text-xs text-muted">{d.start} → {d.end}</span>
      </div>

      {/* 怎么看: 只指出现在在哪一行、那一行的数 —— 不说该拿该走 */}
      {cur && (
        <p className="mt-3 rounded-btn border border-warning/30 bg-warning/[0.06] px-3 py-2 text-xs leading-5 text-secondary">
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

      <table className="mt-3 w-full text-xs">
        <thead>
          <tr className="border-b border-border/60 text-micro text-muted">
            <th className="px-3 py-2 text-left font-normal">状态</th>
            <th className="px-2 py-2 text-right font-normal">出现过</th>
            <th className="px-3 py-2 text-left font-normal">共多少天</th>
            <th className="px-2 py-2 text-right font-normal" title="从进入这个状态前一天收盘, 到它结束那天收盘; 走完的段平均">这段里涨跌</th>
            <th className="px-2 py-2 text-right font-normal" title={`这个状态结束之后 ${N} 个交易日的平均涨跌`}>走完后 {N} 天</th>
            <th className="px-2 py-2 text-right font-normal" title="走完的段里, 涨着结束的有几段">收涨段数</th>
            <th className="px-3 py-2 text-left font-normal">这只票的表现</th>
          </tr>
        </thead>
        <tbody>
          {list.map(s => {
            const fact = factOf(s, d.days)
            return (
              <tr key={s.key} className={cn('border-b border-border/30', s.current && 'bg-warning/[0.08]')}>
                <td className="whitespace-nowrap px-3 py-2">
                  <span className="inline-flex items-center gap-2">
                    <span className={cn('h-2.5 w-2.5 shrink-0 rounded-full', TREND_FILL[s.key])} />
                    <span className="text-foreground">{s.label}</span>
                    {s.current && <span className="text-micro text-muted">当前</span>}
                  </span>
                </td>
                <td className="px-2 py-2 text-right font-mono tabular-nums text-secondary">{s.n || '—'}</td>
                <td className="px-3 py-2">
                  <span className="flex items-center gap-2">
                    <span className="h-1.5 w-24 shrink-0 overflow-hidden rounded-full bg-border/40">
                      <span className="block h-full rounded-full bg-muted/60" style={{ width: `${(s.days / maxDays) * 100}%` }} />
                    </span>
                    <span className="font-mono tabular-nums text-secondary">{s.days}</span>
                  </span>
                </td>
                <td className={cn('px-2 py-2 text-right font-mono tabular-nums', chgCls(s.avg_ret))}>{pct(s.avg_ret)}</td>
                <td className={cn('px-2 py-2 text-right font-mono tabular-nums', chgCls(s.avg_after))}>{pct(s.avg_after)}</td>
                <td className="px-2 py-2 text-right font-mono tabular-nums text-secondary">
                  {s.done ? `${s.ret_win}/${s.done}` : '—'}
                </td>
                <td className="px-3 py-2 text-muted">{fact ?? '—'}</td>
              </tr>
            )
          })}
        </tbody>
      </table>

      <p className="mt-2 text-micro leading-5 text-muted">
        「这段里涨跌」= 从进入这个状态前一天收盘到它结束那天收盘;「走完后 {N} 天」= 这个状态结束之后 {N} 个交易日的平均涨跌;
        「收涨段数」= 走完的段里涨着结束的有几段。眼下还在走的那一段只计次数和天数。走完不到 {THIN} 段的, 数字只能当参考。
      </p>
    </div>
  )
}
