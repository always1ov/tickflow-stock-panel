/**
 * [R433] 个股弹窗重做第四块:「现状」—— 走到哪一步、在什么位置。紧跟在头部「结论」之后。
 *
 * 用户的排版图里这一块下面还有一整块「做不做 / 条件清单 / 在哪做 / 何时走」, 那是
 * **一整套新的买卖判定**, 用户选的是「先做现状, 规则写成草案给你审」—— 所以这里只有
 * 现成的读数, 一个新判定都没有:
 *
 *   趋势状态      六态, 与图上方那条六态条同一个查询(`useStockTrend`)
 *   跌破转弱 / 站上转强   同上, 距离是后端给的带符号的数
 *   通道阶段      上升中 / 下跌中 / 横盘中 …(`channel.phase.cn`)
 *   三档位置      短 / 中 / 长期各在自己通道的上轨 / 中轨 / 下轨哪一格, 色与时间轴
 *                 同一份(`POS_FILL`), 名字是后端给的 `pos_cn`
 *
 * [R438] 原来最前面还有一格「这一格历来」(27 格里今天这一格历来进过几段、走完后怎么样)。
 * 用户: 「这没用了, 删掉」。
 *
 * [R445] 用户在截图上打码: 通道那一格的档位徽标、三字组合码、「该盯什么」那一句, 连同
 * 格与格之间的分隔竖线, 「删除掉 ... 然后排版好显示」。那一格只剩阶段, 标题跟着从
 * 「通道档位」改叫「通道阶段」(档位是「短线回调」「候选池」那一类, 阶段是另一个读数,
 * 同一个标题底下换了东西就是一个名字两个意思)。四块等分一行、同一个结构:
 * 顶上一行小标题, 下面读数, 顶端对齐; 窄屏两块一行。[R448] 三档位置那一块不要小标题。
 *
 * 六态走的是六态接口(开实时行情时是盘中口径, 会标出来), 通道那几样走复盘接口
 * (收盘口径)。两者分别与图上方的六态条、下面的复盘表是同一份数, 不另算。
 */
import type { ReactNode } from 'react'
import type { StockReview } from '@/lib/api'
import { cn } from '@/lib/cn'
import { BAND_CN, POS_FILL } from '@/lib/reviewTimeline'
import { useStockTrend } from '@/components/stock-analysis/TrendStateBar'
import { pct, useStockReview } from '@/components/stock-analysis/StockReviewDialog'
import { SectionTitle } from '@/components/ui'

export function StatusSection({ symbol, days }: { symbol: string; days: number }) {
  const review = useStockReview(symbol, days).data
  const d = review && !review.error ? review : undefined
  return (
    <section>
      <SectionTitle title="现状" sub="走到哪一步、在什么位置" />
      <div className="mt-3 grid grid-cols-1 items-start gap-x-8 gap-y-5 rounded-card border border-border bg-surface p-4 sm:grid-cols-2 lg:grid-cols-4">
        <TrendCell symbol={symbol} />
        <ChannelCell d={d} />
        <BandsCell d={d} />
      </div>
    </section>
  )
}

/** 一格 = 顶上一行小标题 + 下面的读数 */
function Cell({ label, children, className }: { label: ReactNode; children: ReactNode; className?: string }) {
  return (
    <div className={cn('min-w-0', className)}>
      <div className="text-micro text-muted">{label}</div>
      <div className="mt-1">{children}</div>
    </div>
  )
}

const Pending = () => <div className="text-xs text-muted">…</div>

// ── 趋势状态 + 跌破转弱 / 站上转强 ──
function TrendCell({ symbol }: { symbol: string }) {
  const t = useStockTrend(symbol).data
  if (!t || t.error) {
    return <Cell label="趋势状态 · 六态">{t?.error ? <div className="text-xs text-muted">{t.error}</div> : <Pending />}</Cell>
  }
  const bull = t.side === '多头'
  return (
    <>
      <Cell label={<>趋势状态 · 六态{t.intraday && <span className="ml-1.5 text-warning" title="实时价参与了六态判定, 收盘价可能改变结论 —— 定稿以收盘为准">盘中口径</span>}</>}>
        <div className="flex items-baseline gap-2">
          <span className={cn('text-xl font-semibold', bull ? 'text-bull' : 'text-bear')}>{t.state_cn}</span>
          {/* [R249] 「已 N 天」—— 与决策台徽标、六态条同一个说法 */}
          <span className="text-sm text-secondary">已 <span className="font-mono">{t.duration}</span> 天</span>
        </div>
        <div className="mt-0.5 text-micro text-muted">
          自 {t.since}{t.entered_from_cn && <> 由「{t.entered_from_cn}」转入</>}
        </div>
      </Cell>
      <div className="flex flex-wrap gap-x-8 gap-y-5">
        {t.flip_down != null && (
          <FlipCell label="跌破转弱" price={t.flip_down} dist={t.flip_down_distance_pct} tone="bear" />
        )}
        {t.flip_up != null && (
          <FlipCell label="站上转强" price={t.flip_up} dist={t.flip_up_distance_pct} tone="bull" />
        )}
      </div>
    </>
  )
}

function FlipCell({ label, price, dist, tone }: {
  label: string; price: number; dist?: number | null; tone: 'bull' | 'bear'
}) {
  return (
    <Cell label={label}>
      <div className="flex items-baseline gap-2"
           title={tone === 'bull' ? '收盘站上这个价转强' : '收盘跌破这个价转弱'}>
        <span className={cn('font-mono text-xl font-semibold tabular-nums', tone === 'bull' ? 'text-bull' : 'text-bear')}>
          {price.toFixed(2)}
        </span>
        {/* 后端给的是带符号的距离: (线 − 现价) / 现价 */}
        {dist != null && <span className="font-mono text-sm tabular-nums text-muted">{pct(dist)}</span>}
      </div>
    </Cell>
  )
}

// ── 通道阶段 ──
function ChannelCell({ d }: { d?: StockReview }) {
  const ph = d?.channel?.phase ?? null
  return (
    <Cell label="通道阶段">
      {!d ? <Pending /> : (
        <span className="text-xl font-semibold text-foreground">{ph?.cn ?? '—'}</span>
      )}
    </Cell>
  )
}

// ── 三档位置 ──
const SLOT: Record<string, 0 | 1 | 2> = { above: 0, near_upper: 0, inside: 1, near_lower: 2, below: 2 }

function BandsCell({ d }: { d?: StockReview }) {
  const bands = d?.rows[0]?.bands
  if (!bands) return null
  return (
    // [R448] 不要小标题 —— 用户: 「删掉三档位置这四个字」。上轨 / 中轨 / 下轨与短中长期已经说清楚了
    <div className="min-w-0">
      <div className="flex items-start gap-2">
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
    </div>
  )
}
