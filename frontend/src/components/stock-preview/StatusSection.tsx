/**
 * [R433] 个股弹窗重做第四块:「现状」—— 走到哪一步、在什么位置。紧跟在头部「结论」之后。
 *
 * 用户的排版图里这一块下面还有一整块「做不做 / 条件清单 / 在哪做 / 何时走」, 那是
 * **一整套新的买卖判定**, 用户选的是「先做现状, 规则写成草案给你审」—— 所以这里只有
 * 现成的读数, 一个新判定都没有:
 *
 *   这一格历来    27 格里今天这一格, 这只票历来进过几段、走完后怎么样(`comboHistory`,
 *                 与旧复盘页「这一格历来」同一个函数)
 *   趋势状态      六态, 与图上方那条六态条同一个查询(`useStockTrend`)
 *   跌破转弱 / 站上转强   同上, 距离是后端给的带符号的数
 *   通道档位      今天那一档 + 三字组合码 + 阶段, 下面是「该盯什么」——
 *                 那是通道这一层唯一能照着做的一句(R269: 别的都能收, 它不行)
 *   三档位置      短 / 中 / 长期各在自己通道的上轨 / 中轨 / 下轨哪一格, 色与时间轴
 *                 同一份(`POS_FILL`), 名字是后端给的 `pos_cn`
 *
 * 六态走的是六态接口(开实时行情时是盘中口径, 会标出来), 通道那几样走复盘接口
 * (收盘口径)。两者分别与图上方的六态条、下面的复盘表是同一份数, 不另算。
 */
import type { ReactNode } from 'react'
import type { StockReview } from '@/lib/api'
import { cn } from '@/lib/cn'
import { BAND_CN, POS_FILL } from '@/lib/reviewTimeline'
import { comboHistory } from '@/components/stock-analysis/decision-board/ComboView'
import { useStockTrend } from '@/components/stock-analysis/TrendStateBar'
import { VERDICT_CLS, chgCls, pct, useStockReview } from '@/components/stock-analysis/StockReviewDialog'
import { SectionTitle } from './SectionTitle'

export function StatusSection({ symbol, days }: { symbol: string; days: number }) {
  const review = useStockReview(symbol, days).data
  const d = review && !review.error ? review : undefined
  return (
    <section>
      <SectionTitle title="现状" sub="走到哪一步、在什么位置" />
      <div className="mt-3 flex flex-wrap items-stretch gap-x-6 gap-y-4 rounded-card border border-border bg-surface p-4">
        <HistoryCell d={d} />
        <TrendCell symbol={symbol} />
        <ChannelCell d={d} />
        <BandsCell d={d} />
      </div>
    </section>
  )
}

/** 一格 = 顶上一行小标题 + 下面的读数。格与格之间一道竖线(换行后不画) */
function Cell({ label, children, className }: { label: ReactNode; children: ReactNode; className?: string }) {
  return (
    <div className={cn('min-w-0', className)}>
      <div className="text-micro text-muted">{label}</div>
      <div className="mt-1">{children}</div>
    </div>
  )
}

function Num({ value, caption, cls }: { value: ReactNode; caption: string; cls?: string }) {
  return (
    <div>
      <div className={cn('font-mono text-lg font-semibold tabular-nums text-foreground', cls)}>{value}</div>
      <div className="text-micro text-muted">{caption}</div>
    </div>
  )
}

const Pending = () => <div className="text-xs text-muted">…</div>

// ── 这一格历来 ──
function HistoryCell({ d }: { d?: StockReview }) {
  if (!d) return <Cell label="这一格历来"><Pending /></Cell>
  const here = d.channel?.geo?.combo ?? null
  const hist = comboHistory(d.rows, here)
  const N = d.forward_days
  return (
    <Cell label={`这一格历来(近 ${d.days} 天)`}>
      {!here ? (
        // [R294] 与「头一回」是两件事: 这里是三档缺一档算不出来, 不是位置罕见
        <div className="text-xs text-muted" title="三档里有一档今天定不出位置(数据不够), 不是这个位置罕见">今天定不了这一格</div>
      ) : !hist || hist.segs === 0 ? (
        <div className="text-xs text-muted">这 {d.days} 天里没进过这一格 —— 头一回</div>
      ) : (
        <div className="flex items-start gap-5">
          <Num value={`${hist.segs} 段`} caption={`共 ${hist.days} 天`} />
          <Num value={hist.scored ? pct(hist.avg) : '—'} cls={chgCls(hist.avg)}
               caption={hist.scored ? `走完后 ${N} 天` : `还没有走完 ${N} 天的段`} />
          <Num value={hist.scored ? `${hist.win}/${hist.scored} 段` : '—'} caption="走完后收涨" />
        </div>
      )}
    </Cell>
  )
}

// ── 趋势状态 + 跌破转弱 / 站上转强 ──
function TrendCell({ symbol }: { symbol: string }) {
  const t = useStockTrend(symbol).data
  if (!t || t.error) {
    return <Cell label="趋势状态 · 六态">{t?.error ? <div className="text-xs text-muted">{t.error}</div> : <Pending />}</Cell>
  }
  const bull = t.side === '多头'
  return (
    <>
      <Cell label={<>趋势状态 · 六态{t.intraday && <span className="ml-1.5 text-warning" title="实时价参与了六态判定, 收盘价可能改变结论 —— 定稿以收盘为准">盘中口径</span>}</>}
            className="md:border-l md:border-border/60 md:pl-6">
        <div className="flex items-baseline gap-2">
          <span className={cn('text-xl font-semibold', bull ? 'text-bull' : 'text-bear')}>{t.state_cn}</span>
          {/* [R249] 「已 N 天」—— 与决策台徽标、六态条同一个说法 */}
          <span className="text-sm text-secondary">已 <span className="font-mono">{t.duration}</span> 天</span>
        </div>
        <div className="mt-0.5 text-micro text-muted">
          自 {t.since}{t.entered_from_cn && <> 由「{t.entered_from_cn}」转入</>}
        </div>
      </Cell>
      <div className="flex items-center gap-2">
        {t.flip_down != null && (
          <FlipBox label="跌破转弱" price={t.flip_down} dist={t.flip_down_distance_pct} tone="bear" />
        )}
        {t.flip_up != null && (
          <FlipBox label="站上转强" price={t.flip_up} dist={t.flip_up_distance_pct} tone="bull" />
        )}
      </div>
    </>
  )
}

function FlipBox({ label, price, dist, tone }: {
  label: string; price: number; dist?: number | null; tone: 'bull' | 'bear'
}) {
  return (
    <div className={cn('rounded-btn border px-3 py-2',
      tone === 'bull' ? 'border-bull/30 bg-bull/[0.06]' : 'border-bear/30 bg-bear/[0.06]')}
         title={tone === 'bull' ? '收盘站上这个价转强' : '收盘跌破这个价转弱'}>
      <div className="text-micro text-muted">{label}</div>
      <div className="mt-0.5 flex items-baseline gap-1.5">
        <span className={cn('font-mono text-lg font-semibold tabular-nums', tone === 'bull' ? 'text-bull' : 'text-bear')}>
          {price.toFixed(2)}
        </span>
        {/* 后端给的是带符号的距离: (线 − 现价) / 现价 */}
        {dist != null && <span className="font-mono text-micro tabular-nums text-muted">{pct(dist)}</span>}
      </div>
    </div>
  )
}

// ── 通道档位 ──
function ChannelCell({ d }: { d?: StockReview }) {
  if (!d) return <Cell label="通道档位" className="md:border-l md:border-border/60 md:pl-6"><Pending /></Cell>
  const now = d.rows[0]?.verdict ?? null          // rows 新 → 旧, 第一行就是最近一个交易日
  const here = d.channel?.geo?.combo ?? null
  const ph = d.channel?.phase ?? null
  return (
    <Cell label="通道档位" className="min-w-[14rem] flex-1 md:border-l md:border-border/60 md:pl-6">
      <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
        {now ? (
          <span className={`inline-flex whitespace-nowrap rounded-btn border px-2 py-0.5 text-sm font-medium ${VERDICT_CLS[now.tone]}`}>
            {now.title}
          </span>
        ) : <span className="text-sm text-muted">三档都在中部</span>}
        {here && (
          <span className="font-mono text-sm text-secondary" title="三档各在自己通道的上 / 中 / 下 —— 27 格速查表的行号">{here}</span>
        )}
        {ph && <span className="text-sm text-secondary">{ph.cn}</span>}
      </div>
      {/* 通道这一层唯一能照着做的一句 —— 收起来就只剩定性词了(R269) */}
      {ph?.watch && <div className="mt-1 text-xs leading-5 text-muted">该盯什么: <span className="text-secondary">{ph.watch}</span></div>}
    </Cell>
  )
}

// ── 三档位置 ──
const SLOT: Record<string, 0 | 1 | 2> = { above: 0, near_upper: 0, inside: 1, near_lower: 2, below: 2 }

function BandsCell({ d }: { d?: StockReview }) {
  const bands = d?.rows[0]?.bands
  if (!bands) return null
  return (
    <div className="flex items-start gap-2 md:border-l md:border-border/60 md:pl-6">
      <div className="flex flex-col gap-1 pt-px text-micro leading-none text-muted" aria-hidden="true">
        <span className="flex h-2.5 items-center">上轨</span>
        <span className="flex h-2.5 items-center">中轨</span>
        <span className="flex h-2.5 items-center">下轨</span>
      </div>
      {(['s', 'm', 'l'] as const).map(k => {
        const b = bands[k]
        const slot = b ? SLOT[b.pos] : undefined
        return (
          <div key={k} className="flex flex-col items-center" title={b ? `${BAND_CN[k]}: ${b.pos_cn}` : `${BAND_CN[k]}: 算不出来`}>
            <div className="flex flex-col gap-1">
              {[0, 1, 2].map(i => (
                <span key={i} className={cn('h-2.5 w-10', i === slot && b ? POS_FILL[b.pos] : 'bg-border/40')} />
              ))}
            </div>
            <span className="mt-1.5 text-micro text-secondary">{BAND_CN[k]}</span>
            <span className="text-micro text-muted">{b?.pos_cn ?? '—'}</span>
          </div>
        )
      })}
    </div>
  )
}
