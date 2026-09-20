import { cn } from '@/lib/cn'

interface Props {
  title: string
  subtitle?: React.ReactNode
  /** 标题右侧、subtitle 之前的额外节点(如状态徽标) */
  titleExtra?: React.ReactNode
  right?: React.ReactNode
  className?: string
}

export function PageHeader({ title, subtitle, titleExtra, right, className }: Props) {
  return (
    <header
      className={cn(
        'min-h-[52px] px-4 py-2 border-b border-border flex items-center justify-between gap-4',
        className,
      )}
    >
      <div className="flex min-w-0 items-center gap-2.5">
        <h1 className="shrink-0 text-lg font-semibold leading-tight tracking-tight">{title}</h1>
        {titleExtra}
        {subtitle && <span className="min-w-0 truncate text-xs leading-[18px] text-muted">{subtitle}</span>}
      </div>
      {/* [R374] 窄屏兜底: 工具栏多个按钮 + date input 等组合, 默认 shrink-0
          会顶破 375px。改为 flex-wrap + 允许压缩 — left 已经 min-w-0 + truncate,
          窄屏上 left 优先压短, right 内部自然换行, 整行不会被外层 flex 撑出去。
          gap-y-1 让换行不致把 PageHeader 撑太高。 */}
      {right && (
        <div className="flex min-w-0 flex-wrap items-center justify-end gap-x-2 gap-y-1">
          {right}
        </div>
      )}
    </header>
  )
}
