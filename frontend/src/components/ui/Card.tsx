/**
 * [R400 · 阶段三 3.2] 卡片外壳。
 *
 * 现状是 `rounded-card border border-border/60 bg-surface/40` 这一串在几十处
 * 手抄, 每处的边框透明度、底色透明度、内边距都略有出入 —— 于是同一屏上的
 * 几张卡深浅不一, 看起来像三套东西。
 *
 * **方向 A 的卡是"仪表面板的一格", 不是"浮起来的卡片"**: 6px 圆角、1px 边框、
 * **无投影**(R399 已把 `shadow-card` 指向 `--shadow-flat`), 层级完全靠
 * base / surface / elevated 三档明度差。所以这里不提供任何 shadow 选项 ——
 * 要浮起来的是弹窗和下拉, 它们不用这个组件。
 */
import { cn } from '@/lib/cn'

export type CardPadding = 'none' | 'tight' | 'md'

/** 纵向比横向紧一档 —— 卡在纵向堆叠, 上下留白会累加, 横向不会。 */
const PADDING: Record<CardPadding, string> = {
  none: '',
  tight: 'px-s2 py-s1',   // 16 / 8  —— 工具条、筛选条
  md: 'px-s2 py-s2',      // 16 / 16 —— 有正文的内容卡
}

export function Card({ padding = 'md', className, ...rest }: {
  padding?: CardPadding
} & React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn('rounded-card border border-border/60 bg-surface/40',
                    PADDING[padding], className)}
      {...rest}
    />
  )
}

/**
 * 同一张卡里的第二块。**分隔线比卡边框再淡一档**(`/40` vs `/60`): 卡里面的
 * 分界不该和卡与页面的分界一样重, 否则一张卡看起来像两张。
 */
export function CardSection({ padding = 'md', className, ...rest }: {
  padding?: CardPadding
} & React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn('border-t border-border/40', PADDING[padding], className)}
      {...rest}
    />
  )
}
