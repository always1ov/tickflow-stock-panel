import { CheckCircle2, XCircle, Loader2, AlertCircle } from 'lucide-react'
import { formatDuration } from '@/lib/format'
import { cn } from '@/lib/cn'
import { TYPE } from '@/components/ui'

export function SectionTitle({ icon: Icon, children }: { icon: React.ComponentType<{ className?: string }>; children: React.ReactNode }) {
  return (
    // [R465] 数据页的分区标题落 L2(与个股弹窗「现状」「复盘」同级), 原来是 12px 灰色大写字距
    <h2 className={cn('flex items-center gap-2', TYPE.section)}>
      <Icon className="h-4 w-4 text-secondary" />
      {children}
    </h2>
  )
}

export function HistoryRow({ job, onClick }: { job: any; onClick: () => void }) {
  const statusIcon = {
    succeeded: { icon: CheckCircle2, color: 'text-bear' },
    failed:    { icon: XCircle, color: 'text-danger' },
    running:   { icon: Loader2, color: 'text-accent', spinning: true },
    pending:   { icon: Loader2, color: 'text-muted', spinning: true },
  }[job.status as 'succeeded'] ?? { icon: AlertCircle, color: 'text-muted' }
  const Icon = statusIcon.icon

  return (
    <button
      onClick={onClick}
      className="w-full px-5 py-3 hover:bg-elevated/50 transition-colors duration-hover ease-smooth text-left flex items-center justify-between gap-4"
    >
      <div className="flex items-center gap-3 min-w-0">
        <Icon className={`h-4 w-4 shrink-0 ${statusIcon.color} ${(statusIcon as any).spinning ? 'animate-spin' : ''}`} />
        <div className="min-w-0">
          <div className="font-mono text-xs text-foreground">{job.id}</div>
          <div className="text-xs text-muted">
            {job.started_at ? new Date(job.started_at).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }) : '—'}
            {' · '}
            {job.duration_s != null ? formatDuration(job.duration_s) : '...'}
          </div>
        </div>
      </div>
      <div className="text-right shrink-0">
        {job.result && (() => {
          const r = job.result as Record<string, any>
          const parts: string[] = []
          if (r.daily_days != null) parts.push(`日K ${r.daily_days}日`)
          if (r.enriched_days != null) parts.push(`enriched ${r.enriched_days}行`)
          if (r.minute_rows != null) parts.push(`分钟K ${r.minute_rows}行`)
          if (r.earliest_after && r.earliest_before) {
            const a = String(r.earliest_after).slice(0, 10)
            const b = String(r.earliest_before).slice(0, 10)
            const days = r.daily_days ?? r.minute_days ?? 0
            parts.push(days <= 1 ? a : `${a}~${b}`)
          }
          return parts.length > 0 ? (
            <div className="text-xs text-secondary font-mono">{parts.join(' · ')}</div>
          ) : null
        })()}
        {job.error && (
          <div className="text-xs text-danger truncate max-w-xs">{job.error}</div>
        )}
      </div>
    </button>
  )
}
