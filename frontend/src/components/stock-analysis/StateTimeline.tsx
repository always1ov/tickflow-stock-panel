/**
 * [fork 增强 R273] 状态色带时间轴 —— 一条(或几条)带子把整段时间铺开。
 *
 * 用户: 「这三个部分搞状态时间轴, 类似图片的」(指市场环境页那条)。
 *
 * ## 它补的是复盘弹窗缺的那一层
 *
 * 三个页签原本都是「今天怎么样」+「逐日/逐段明细」。**中间缺一层全景**: 这半年
 * 到底是多头段落多还是空头段落多、切换得频不频、最近这一段在整段里算长还是算短 ——
 * 这些问题逐日表回答不了(120 行滚下来记不住), 结论卡也回答不了(它只说今天)。
 * 一条色带扫一眼就有答案, 而它只占约 40px。
 *
 * ## 两个必须做对的地方
 *
 * - **左边是早、右边是晚。** 复盘接口的 `rows` 是**新→旧**(表格要把最近的排在最前),
 *   直接铺出来时间轴就是倒着的 —— 而人读时间轴一律从左往右。调用方负责传按时间
 *   正序的格子。
 * - **格子最小宽度不能小于 1px。** 250 天挤在一条里, 用纯 `flex-1` 在窄容器上会被
 *   压成 0 宽而整段消失。`min-w-[2px]` + 允许横向滚动, 宁可能滚也不能不见。
 */
import type { ReactNode } from 'react'
import { cn } from '@/lib/cn'

export interface TimelineCell {
  /** React key —— 一般用日期 */
  key: string
  /** 这一格的底色(Tailwind bg-* 类) */
  cls: string
  /** 悬停说明 */
  title: string
}

export interface TimelineBand {
  /** 左侧标签; 单条带子时留空 */
  label?: string
  cells: TimelineCell[]
}

interface Props {
  /** 右上角那行小字, 一般是「起 → 止 · N 天」 */
  hint?: ReactNode
  bands: TimelineBand[]
  legend: { cls: string; label: string }[]
  /** 带子高度; 多条并排时自动矮一些 */
  className?: string
}

export function StateTimeline({ hint, bands, legend, className }: Props) {
  const total = bands.reduce((n, b) => n + b.cells.length, 0)
  if (!total) return null
  const multi = bands.length > 1
  return (
    <div className={cn('mx-4 mt-2 rounded-lg border border-border/50 bg-elevated/20 px-3 py-2', className)}>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <span className="text-[10px] text-muted">状态时间轴</span>
        {/* 图例和标题挤在同一行 —— 单独占一行的话, 三个页签就一共多花 48px */}
        <span className="flex flex-wrap items-center gap-x-2.5 gap-y-0.5">
          {legend.map(l => (
            <span key={l.label} className="inline-flex items-center gap-1 text-[9px] text-muted">
              <i className={cn('inline-block h-2 w-2 rounded-sm', l.cls)} />
              {l.label}
            </span>
          ))}
        </span>
        {!!hint && <span className="ml-auto shrink-0 font-mono text-[9px] text-muted/70">{hint}</span>}
      </div>
      <div className="mt-1.5 space-y-1">
        {bands.map((b, i) => (
          <div key={b.label ?? i} className="flex items-center gap-2">
            {multi && (
              <span className="w-6 shrink-0 text-right text-[9px] text-muted">{b.label}</span>
            )}
            <div className={cn('flex min-w-0 flex-1 overflow-hidden rounded',
              multi ? 'h-2.5' : 'h-5')}>
              {b.cells.map(c => (
                <div
                  key={c.key}
                  title={c.title}
                  className={cn('min-w-[2px] flex-1 transition-opacity hover:opacity-70', c.cls)}
                />
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
