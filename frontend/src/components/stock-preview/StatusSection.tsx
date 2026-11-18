/**
 * [R433] 个股弹窗重做第四块:「现状」—— 走到哪一步、在什么位置。紧跟在头部「结论」之后。
 *
 * 用户的排版图里这一块下面还有一整块「做不做 / 条件清单 / 在哪做 / 何时走」, 那是
 * **一整套新的买卖判定**, 用户选的是「先做现状, 规则写成草案给你审」—— 所以这里只有
 * 现成的读数, 一个新判定都没有:
 *
 *   趋势状态      六态(`useStockTrend`)。[R551] 图上方原来还有一条六态条, 与这一格逐字重复
 *                 (用户圈出「重复了」), 已撤; 它独有的回测调参入口、转折信号搬到这一格,
 *                 操作建议与关键点参考数放进状态名的悬停。
 *                 [R679] 回测调参再往上搬一层到弹窗头部(自选于左边) —— 用户:
 *                 「左里面的回测调参按钮放到上里面的自选于的前面」。
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
 * (收盘口径)。两者分别与六态条(独立的关键价位弹窗里还有)、下面的复盘表是同一份数, 不另算。
 */
import type { ReactNode } from 'react'
import type { StockReview } from '@/lib/api'
import { cn } from '@/lib/cn'
import { BAND_CN, POS_FILL } from '@/lib/reviewTimeline'
import { TrendSignalBadge, trendPivotTitle, useStockTrend } from '@/components/stock-analysis/TrendStateBar'
import { useStockReview } from '@/components/stock-analysis/StockReviewDialog'

export function StatusSection({ symbol, days }: {
  symbol: string
  days: number
}) {
  const review = useStockReview(symbol, days).data
  const d = review && !review.error ? review : undefined
  return (
    <section>
      {/* [R677] 用户: 「『现状 / 走到哪一步、在什么位置』是一整行内容不要」——
          连标题带副标题整行撤掉, 左栏从「趋势状态 · 六态」直接开始。
          [R673] 这四格也不再罩卡框: 左栏本身已是独立分栏, 再罩一层圆角边框只是白白
          吃掉一圈 16px(用户: 「左中右里面的内容没必要再套一层框框住, 这样很浪费空间」)
          [R680] 五段竖排压成三段(方案 A): 趋势状态 / 跌破·站上并列 / 通道阶段;
          三档位置搬到右栏, 和价位梯队放在一起(位置类归位置栏)。
          [R681] 用户: 「左里面恢复以前的布局, 但样式保持现在」——
          回到 R680 之前的一列五段(趋势状态 / 跌破 / 站上 / 通道阶段 / 三档位置),
          无标题、无卡框的样式照旧; 右栏只留价位阶梯。
          [R682] 用户: 「跌破转弱站上转强都不要了, 剩下的趋势六态和通道阶段内容合并到右里面,
          从此左中右布局变成左右布局」—— 两格翻转价撤掉, 本组件改挂在右栏顶部。
          [R707] 用户: 「恢复左中右布局, 左里面放『趋势状态 · 六态』和『通道阶段』」，
          随后补一句「上中下轨也放到左里面」—— 本组件整块回到左栏, 三格齐全,
          右栏回到只放价位阶梯。 */}
      {/* [R840] 左栏排版重排: 两格读数(趋势 / 通道)并排一行, 三档位置单独一条并加分隔线 ——
          原来三段竖排 gap-y-5, 左栏宽只有 300~520 时大片空白被竖着浪费掉。 */}
      <div className="grid grid-cols-1 gap-y-3">
        <div className="grid grid-cols-[minmax(0,1fr)_auto] items-start gap-x-4">
          <TrendCell symbol={symbol} />
          <ChannelCell d={d} />
        </div>
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
    <Cell label={<>趋势状态 · 六态{t.intraday && <span className="ml-1.5 text-warning" title="实时价参与了六态判定, 收盘价可能改变结论 —— 定稿以收盘为准">盘中口径</span>}</>}>
      <div className="flex items-baseline gap-2">
        {/* [R551] 悬停: 操作建议 + 两条翻转价背后的参考数 —— 原来印在图上方六态条里, 那条已撤。
            [R682] 「跌破转弱 / 站上转强」两格按用户要求撤掉, 两个翻转价还能从悬停里看到。 */}
        <span className={cn('text-xl font-semibold', bull ? 'text-bull' : 'text-bear')}
              title={`${t.action}\n\n${trendPivotTitle(t)}`}>{t.state_cn}</span>
        {/* [R249] 「已 N 天」—— 与决策台徽标、六态条同一个说法 */}
        <span className="text-sm text-secondary">已 <span className="font-mono">{t.duration}</span> 天</span>
        <TrendSignalBadge trend={t} />
      </div>
      <div className="mt-0.5 text-micro text-muted">
        自 {t.since}{t.entered_from_cn && <> 由「{t.entered_from_cn}」转入</>}
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
    <div className="min-w-0 border-t border-border/40 pt-3">
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
