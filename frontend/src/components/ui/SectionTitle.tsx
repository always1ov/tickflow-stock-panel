/**
 * [R431 → R449] 分区标题(L2): 标题 + 一句副标题 + 一道细线拉满。
 *
 * 原来在 `components/stock-preview/`, 只给个股弹窗用; R449 全站迁移时挪到这里,
 * 各页面的分区都用它 —— 同一个层级只许长一个样子。字号从 15px 提到 18px:
 * 弹窗里分区标题原来比卡片标题(16px)还小, 层级是反的。
 */
import type { ReactNode } from 'react'
import { cn } from '@/lib/cn'
import { TYPE } from './type'

export function SectionTitle({ title, sub, right, className }: {
  title: ReactNode
  sub?: ReactNode
  /** 细线右边那一格(按钮、切换这类), 不传就不画 */
  right?: ReactNode
  className?: string
}) {
  return (
    <div className={cn('flex items-center gap-3', className)}>
      <span className={cn('shrink-0', TYPE.section)}>{title}</span>
      {sub != null && <span className="shrink-0 text-xs text-muted">{sub}</span>}
      <span className="h-px flex-1 bg-border/70" aria-hidden="true" />
      {right}
    </div>
  )
}
