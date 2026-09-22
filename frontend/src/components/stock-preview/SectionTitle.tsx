/**
 * [R431] 个股弹窗重做后每一块顶上那一行: 标题 + 一句副标题 + 一道细线拉满。
 * 「图表与价位」「复盘」都用它 —— 同一个弹窗里区块标题只许长一个样子。
 */
import type { ReactNode } from 'react'

export function SectionTitle({ title, sub }: { title: string; sub?: ReactNode }) {
  return (
    <div className="flex items-center gap-3">
      <span className="shrink-0 text-sm font-semibold text-foreground">{title}</span>
      {sub != null && <span className="shrink-0 text-xs text-muted">{sub}</span>}
      <span className="h-px flex-1 bg-border/70" aria-hidden="true" />
    </div>
  )
}
