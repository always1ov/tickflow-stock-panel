/**
 * [R814] 全站唯一的徽标(计数、分类、状态角标)。
 *
 * 现状: `bg-elevated px-1.5 py-0.5 text-micro text-muted` 这一串手抄 45 处,
 * 高度、内边距、字色各处略有出入 —— 同一屏上几个徽标不一边高, 看起来像三套东西。
 *
 * **徽标不是按钮**: 它没有 hover、不可点、不做按下反馈。所以这里不带任何交互态,
 * 也不复用 `buttonClass()` —— 复用过来就会有人顺手给它加 onClick, 然后它看起来
 * 就变成一颗按钮了。要可点的胶囊请用 `<Button size="xs">`。
 *
 * 色只给语义, 不给"好看": `bull` / `bear` 只用于行情涨跌, 不许拿去做普通状态色。
 */
import { cn } from '@/lib/cn'

export type BadgeTone =
  | 'neutral' | 'accent' | 'accent-soft' | 'danger' | 'warning' | 'bull' | 'bear'

const BASE =
  'inline-flex h-5 shrink-0 items-center gap-g3 whitespace-nowrap rounded-btn ' +
  'px-g3 text-micro font-medium'

/**
 * [R824] 除 `accent` 外一律是「10% 底 + 同色字」, **不是实心填充**:
 * 实心色块多了整屏会变成色卡, 而徽标是辅助读数, 不该和按钮抢注意力。
 *
 * `accent-soft` 是 R823 报上来的缺口: 因子库「虚拟」、规则来源「内置」这类
 * **弱强调**原先就是 `bg-accent/10 text-accent`, 迁到 Badge 后只剩实心 accent,
 * 一个字号 11px 的标签被填成实心色块, 比旁边的正文还抢眼。
 */
const TONE: Record<BadgeTone, string> = {
  neutral: 'bg-elevated text-foreground',
  accent: 'bg-accent text-on-accent',
  'accent-soft': 'bg-accent/10 text-accent',
  danger: 'bg-danger/10 text-danger',
  warning: 'bg-warning/10 text-warning',
  bull: 'bg-bull/10 text-bull',
  bear: 'bg-bear/10 text-bear',
}

export function Badge({ tone = 'neutral', className, ...rest }: {
  tone?: BadgeTone
} & React.HTMLAttributes<HTMLSpanElement>) {
  return <span className={cn(BASE, TONE[tone], className)} {...rest} />
}
