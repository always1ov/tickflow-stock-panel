/**
 * [fork R562] 逐月收益那一排 —— 转折模拟盘的月度格子(R357 / R498)搬进虚拟账户, 所有账户都有。
 *
 * 口径在 `lib/paperMonthly.ts`; 这里只画。转折模拟盘删掉之后这是唯一的一份
 * (第 3 步之前模拟盘页里还有一份同样的, 随那一页一起删)。
 */
import { useLayoutEffect, useRef } from 'react'
import { Hint } from '@/components/Hint'
import { cn } from '@/lib/cn'
import type { MonthReturn } from '@/lib/paperMonthly'

function pct(v: number): string {
  return `${v >= 0 ? '+' : ''}${(v * 100).toFixed(1)}%`
}

export function MonthStrip({ months }: { months: MonthReturn[] }) {
  // [R498] 放不下时先露出最近的月份: 一挂上就滚到最右, 往左拖看更早的。
  // 瞬时定位, 不做滚动动画(数据不加装饰性动效)。
  const scrollRef = useRef<HTMLDivElement>(null)
  useLayoutEffect(() => {
    const el = scrollRef.current
    if (el) el.scrollLeft = el.scrollWidth
  }, [months])
  if (!months.length) return null
  // 柱高按最大月度波动归一 —— 柱子之间可比; 固定刻度下 ±2% 的年份会全贴着底
  const peak = Math.max(...months.map((m) => Math.abs(m.ret)), 0.01)
  return (
    <section className="overflow-hidden">
      <div className="mb-2 flex items-center gap-0.5 text-micro text-muted">
        逐月收益
        <Hint title={'**每个月单独算, 月与月之间不重叠** —— 这个月的收益 =\n月末净值 / 上月末净值 - 1(第一个月的基准是本金)。\n\n净值是每个交易日盘后定版的那一行。\n\n**打叉的是残月**: 开户那个月从月中算起,\n或者这个月还没走完 —— 它们不该拿去和整月比。'} />
        <span className="ml-1 opacity-70">{months.length} 个月 · 柱高按最大月度波动归一</span>
      </div>
      <div ref={scrollRef} className="flex items-end gap-1 overflow-x-auto">
        {months.map((m) => {
          const up = m.ret >= 0
          return (
            <div key={m.month} className="flex min-w-[2.75rem] max-w-16 flex-1 flex-col items-center gap-1"
                 title={`${m.month} · ${m.days} 个交易日${m.partial ? '(残月)' : ''}\n月末净值 ${m.nav.toLocaleString('zh-CN', { maximumFractionDigits: 0 })}`}>
              <span className={cn('text-micro font-semibold tabular-nums',
                up ? 'text-bull' : 'text-bear', m.partial && 'opacity-60')}>
                {pct(m.ret)}
              </span>
              {/* 柱子从中线往上/往下长 —— 亏的月份自己往下掉 */}
              <div className="flex h-8 w-full flex-col justify-center">
                <div className="flex h-4 items-end">
                  {up && <div className={cn('w-full rounded-t-sm bg-bull/60', m.partial && 'opacity-50')}
                              style={{ height: `${Math.max(2, (m.ret / peak) * 100)}%` }} />}
                </div>
                <div className="flex h-4 items-start">
                  {!up && <div className={cn('w-full rounded-b-sm bg-bear/60', m.partial && 'opacity-50')}
                               style={{ height: `${Math.max(2, (-m.ret / peak) * 100)}%` }} />}
                </div>
              </div>
              <span className={cn('text-micro tabular-nums text-muted', m.partial && 'opacity-60')}>
                {m.month.endsWith('-01') ? m.month.replace('-', '/') : m.month.slice(5)}
                {m.partial && <span className="text-warning/70" title="残月">✕</span>}
              </span>
            </div>
          )
        })}
      </div>
    </section>
  )
}
