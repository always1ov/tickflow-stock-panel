/**
 * [R814] 工具条 —— 一行操作按钮的容器。
 *
 * 现状的问题不是"按钮长得不一样", 是**同一排按钮各自长高**: 每颗按钮自己写
 * `py-1.5` / `h-7` / `h-8`, 一行里三种高度, 而且换行后间距也不一致。
 *
 * 规矩只有三条:
 *   1. 一行里的按钮**统一 `size="sm"`**(32px), 不再各自给高;
 *   2. 按钮之间 `gap-g2`(4px), 组与组之间 `gap-g3`(6px);
 *   3. 组之间要分隔时用 `<ToolbarDivider>`, 不要用竖线字符或空 span 撑开。
 *
 * 这里只管排版, 不管按钮长什么样 —— 按钮仍然从 `buttonClass()` 取。
 */
import { cn } from '@/lib/cn'

/** 整行: 放不下就换行, 不横向滚动(横向滚动会藏住后半截按钮)。 */
export const TOOLBAR = 'flex flex-wrap items-center gap-g3'

/** 一组同义操作(「日/周/月」这类)。 */
export const TOOLBAR_GROUP = 'inline-flex shrink-0 items-center gap-g2'

export function Toolbar({ className, ...rest }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn(TOOLBAR, className)} {...rest} />
}

export function ToolbarGroup({ className, ...rest }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn(TOOLBAR_GROUP, className)} {...rest} />
}

/** 组间竖分隔: 高度跟着 32px 控件走, 不写死成撑满整行。 */
export function ToolbarDivider({ className }: { className?: string }) {
  return <span aria-hidden="true" className={cn('mx-g2 h-4 w-px shrink-0 bg-border', className)} />
}
