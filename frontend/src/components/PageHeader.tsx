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
      {right && <div className="shrink-0">{right}</div>}
    </header>
  )
}
