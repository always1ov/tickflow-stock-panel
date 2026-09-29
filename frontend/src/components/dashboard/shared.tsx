/**
 * 看板 widgets 公共层 — 数值格式化与轻量展示件。
 *
 * 从 pages/Dashboard.tsx 原样搬移(供 widgets.tsx 与 Dashboard 页共用),
 * 行为不变; A 股语义色约定: 红涨(text-bull)绿跌(text-bear)。
 */
import type { ReactNode } from 'react'
import { Activity } from 'lucide-react'
import { TYPE } from '@/components/ui'

export function n(v: number | null | undefined) {
  return typeof v === 'number' && Number.isFinite(v) ? v : null
}

export function scoreColor(v: number) {
  // A 股惯例: 强势=红, 弱式=绿
  if (v >= 70) return '#F04438'
  if (v >= 55) return '#FB923C'
  if (v >= 45) return '#F59E0B'
  if (v >= 30) return '#84CC16'
  return '#12B76A'
}

export function fmtPrice(v: number | null | undefined, digits = 2) {
  const x = n(v)
  return x == null ? '—' : x.toFixed(digits)
}

export function fmtIndexPct(v: number | null | undefined) {
  const x = n(v)
  if (x == null) return '—'
  return `${x >= 0 ? '+' : ''}${x.toFixed(2)}%`
}

export function fmtStockPct(v: number | null | undefined) {
  const x = n(v)
  if (x == null) return '—'
  return `${x >= 0 ? '+' : ''}${(x * 100).toFixed(2)}%`
}

export function pctClass(v: number | null | undefined) {
  const x = n(v)
  if (x == null || x === 0) return 'text-muted'
  return x > 0 ? 'text-bull' : 'text-bear'
}

export function quoteAge(ms?: number | null) {
  if (ms == null) return '—'
  if (ms < 1000) return `${Math.round(ms)}ms`
  const s = Math.round(ms / 1000)
  if (s < 60) return `${s}s`
  return `${Math.floor(s / 60)}m${s % 60}s`
}

export function compactCount(v: number | null | undefined) {
  const x = n(v)
  if (x == null) return '—'
  if (x >= 1000) return `${(x / 1000).toFixed(1)}k`
  return x.toFixed(0)
}

export function SectionTitle({ icon: Icon, title, hint }: { icon: typeof Activity; title: string; hint?: ReactNode }) {
  return (
    <div className="mb-2 flex items-center justify-between gap-2">
      <div className="flex items-center gap-1.5">
        <Icon className="h-4 w-4 text-accent" />
        {/* [R453] 卡片标题是 L3(15px) —— 原来 13px, 与卡片里的内容一样大 */}
        <h2 className={TYPE.card}>{title}</h2>
      </div>
      {hint && <span className="font-mono text-micro text-muted">{hint}</span>}
    </div>
  )
}

export function MiniMetric({ label, value, cls = 'text-foreground' }: { label: string; value: string; cls?: string }) {
  return (
    <div className="rounded-btn bg-elevated/45 px-2 py-1.5 border border-border/40">
      <div className="text-micro text-muted">{label}</div>
      <div className={`mt-0.5 font-mono text-xs font-semibold ${cls}`}>{value}</div>
    </div>
  )
}

export function KpiCell({ label, value, sub, tone = 'neutral' }: { label: ReactNode; value: ReactNode; sub?: string; tone?: 'bull' | 'bear' | 'accent' | 'neutral' }) {
  const isPlain = typeof value === 'string' || typeof value === 'number'
  const color = tone === 'bull' ? 'text-bull' : tone === 'bear' ? 'text-bear' : tone === 'accent' ? 'text-accent' : 'text-foreground'
  return (
    <div className="min-w-0 overflow-hidden rounded-btn border border-border bg-surface/80 px-2 py-1 shadow-[0_1px_2px_oklch(var(--border)/0.4)] backdrop-blur-sm transition-ui hover:border-accent/30 hover:shadow-[0_2px_8px_oklch(var(--accent)/0.15)]">
      <div className="flex items-center gap-1 text-xs text-muted">{label}</div>
      {/* [R453] 读数级 21px; [R523] 手机两列时 18px —— 「2100/200/2900」13 个字 21px 塞不进半屏, 尾巴被截 */}
      <div className={`mt-1 truncate font-mono text-lg font-semibold leading-none tabular-nums sm:text-xl ${isPlain ? color : 'text-foreground'}`}>{value}</div>
      {sub && <div className="mt-1 truncate text-micro text-muted">{sub}</div>}
    </div>
  )
}
