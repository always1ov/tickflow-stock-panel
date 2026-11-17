/**
 * A 区 · 事实仪表 (R791) — 复盘页第一屏的「今天发生了什么」。
 *
 * 只放**事实读数**(规则口径, 全部来自 core / breadth 两个切片接口),
 * 不放任何 LLM 摘录 —— 判断与计划只在 C 区正文里, 避免两套结论打架(单一产地)。
 *
 * 三段: 情绪(分数/较上次/六维) · 指数与涨跌结构 · 连板高度与均线站位。
 */
import { AlertTriangle, Gauge } from 'lucide-react'

import type { AiReviewReportMeta, OverviewBreadth, OverviewCore } from '@/lib/api'
import { cn } from '@/lib/cn'
import { fmtBigNum } from '@/lib/format'
import { fmtArchivedAt, fmtPctAlready, indexShort, pctClass, scoreColor } from './shared'

export interface FactsBarProps {
  core?: OverviewCore
  breadth?: OverviewBreadth
  /** 上一篇归档(按 as_of 早于当前) — 给「情绪较上次」 */
  prevMeta?: AiReviewReportMeta | null
  loading?: boolean
  error?: boolean
  onRetry?: () => void
}

function Cell({ label, children, className }: {
  label: string
  children: React.ReactNode
  className?: string
}) {
  return (
    <div className={cn('min-w-0', className)}>
      <div className="text-micro text-muted">{label}</div>
      <div className="mt-0.5 flex items-baseline gap-1.5">{children}</div>
    </div>
  )
}

function Value({ v, cls, unit }: { v: React.ReactNode; cls?: string; unit?: string }) {
  return (
    <>
      <span className={cn('font-mono text-sm font-semibold tabular-nums', cls ?? 'text-foreground')}>{v}</span>
      {unit && <span className="text-micro text-muted">{unit}</span>}
    </>
  )
}

export function FactsBar({ core, breadth, prevMeta, loading, error, onRetry }: FactsBarProps) {
  if (loading && !core) {
    return (
      <div className="grid animate-pulse gap-3 rounded-card border border-border bg-surface/80 p-3.5 lg:grid-cols-3">
        <div className="h-14 rounded-btn bg-elevated/60" />
        <div className="h-14 rounded-btn bg-elevated/60" />
        <div className="h-14 rounded-btn bg-elevated/60" />
      </div>
    )
  }

  if (error && !core) {
    return (
      <div className="flex items-center gap-2 rounded-card border border-dashed border-border bg-surface/50 px-4 py-3 text-xs text-muted">
        <AlertTriangle className="h-3.5 w-3.5" />事实读数暂不可用
        {onRetry && <button onClick={onRetry} className="ml-auto text-micro text-accent hover:underline">重试</button>}
      </div>
    )
  }

  if (!core) return null

  const score = core.emotion?.score ?? null
  const emoColor = scoreColor(score)
  const prevScore = prevMeta?.emotion_score ?? null
  const delta = score != null && prevScore != null ? score - prevScore : null
  const indices = (core.indices ?? []).slice(0, 4)
  const limit = breadth?.limit
  const tiers = (limit?.tiers ?? []).slice(0, 3)
  const radar = (breadth?.radar ?? []).slice(0, 6)

  return (
    <section className="rounded-card border border-border bg-surface/80">
      <div className="grid gap-x-5 gap-y-3 px-3.5 py-3 lg:grid-cols-[minmax(0,1.05fr)_minmax(0,1.25fr)_minmax(0,1fr)]">
        {/* ── 情绪 ── */}
        <div className="flex min-w-0 items-start gap-3">
          <span
            className="grid h-11 w-11 shrink-0 place-items-center rounded-btn font-mono text-base font-bold tabular-nums"
            style={{ color: emoColor, backgroundColor: `${emoColor}1a` }}
          >
            {score ?? '—'}
          </span>
          <div className="min-w-0 flex-1">
            <div className="flex items-baseline gap-2">
              <span className="text-xs font-medium text-foreground">{core.emotion?.label ?? '情绪'}</span>
              <span className="text-micro text-muted">情绪温度</span>
              {delta != null && (
                <span
                  className={cn('font-mono text-micro tabular-nums', delta > 0 ? 'text-bull' : delta < 0 ? 'text-bear' : 'text-muted')}
                  title={`较 ${prevMeta?.as_of} 归档的情绪分`}
                >
                  较上次 {delta > 0 ? '+' : ''}{delta}
                </span>
              )}
            </div>
            {/* 六维微条: 只做扫描, 细读去证据带「情绪」Tab */}
            <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1">
              {radar.length === 0 ? (
                <span className="text-micro text-muted">六维待加载</span>
              ) : radar.map(r => (
                <span key={r.key} className="inline-flex items-center gap-1" title={`${r.label} ${r.value}`}>
                  <span className="text-micro text-muted">{r.label}</span>
                  <span className="h-1 w-6 overflow-hidden rounded-full bg-elevated">
                    <span
                      className="block h-full rounded-full"
                      style={{ width: `${Math.max(4, Math.min(100, r.value))}%`, backgroundColor: scoreColor(r.value) }}
                    />
                  </span>
                  <span className="font-mono text-micro tabular-nums text-secondary">{Math.round(r.value)}</span>
                </span>
              ))}
            </div>
          </div>
        </div>

        {/* ── 指数 + 涨跌结构 ── */}
        <div className="grid min-w-0 grid-cols-2 gap-x-5 gap-y-2 sm:grid-cols-4 lg:border-x lg:border-border/70 lg:px-5">
          {indices.map(idx => (
            <Cell key={idx.symbol} label={indexShort(idx.name, idx.symbol)}>
              <Value v={fmtPctAlready(idx.change_pct, 2, true)} cls={pctClass(idx.change_pct)} />
            </Cell>
          ))}
          <Cell label="涨 / 跌">
            <Value v={breadth?.breadth.up ?? '—'} cls="text-bull" />
            <span className="text-micro text-muted">/</span>
            <Value v={breadth?.breadth.down ?? '—'} cls="text-bear" />
          </Cell>
          <Cell label="涨停 / 封板">
            <Value v={limit?.limit_up ?? '—'} cls="text-bull" />
            <span className="text-micro text-muted">/</span>
            <Value v={limit?.seal_rate == null ? '—' : limit.seal_rate.toFixed(0)} unit="%" cls="text-foreground" />
          </Cell>
          <Cell label="成交额">
            <Value v={breadth ? fmtBigNum(breadth.amount.total) : '—'} />
          </Cell>
          <Cell label="均线站位">
            <Value v={breadth?.trend.above_ma5_pct == null ? '—' : breadth.trend.above_ma5_pct.toFixed(0)} unit="% MA5" />
            <span className="text-micro text-muted">·</span>
            <Value v={breadth?.trend.above_ma20_pct == null ? '—' : breadth.trend.above_ma20_pct.toFixed(0)} unit="% MA20" cls="text-secondary" />
          </Cell>
        </div>

        {/* ── 连板 + 上次复盘 ── */}
        <div className="flex min-w-0 flex-col justify-between gap-1.5">
          <Cell label="连板高度 / 梯队">
            <Value v={limit ? `${limit.max_boards} 板` : '—'} cls="text-foreground" />
            <span className="truncate text-micro text-secondary">
              {tiers.length ? tiers.map(t => `${t.boards}×${t.count}`).join('  ') : '—'}
            </span>
          </Cell>
          <Cell label="炸板 / 跌停">
            <Value v={limit?.broken ?? '—'} cls="text-secondary" />
            <span className="text-micro text-muted">/</span>
            <Value v={limit?.limit_down ?? '—'} cls="text-bear" />
          </Cell>
          <div className="flex items-center gap-1 text-micro text-muted">
            <Gauge className="h-3 w-3" />
            {prevMeta
              ? <>上次复盘 <span className="font-mono text-secondary">{fmtArchivedAt(prevMeta.created_at)}</span> · 情绪 {prevScore ?? '—'}</>
              : '还没有上一篇复盘可对照'}
          </div>
        </div>
      </div>
    </section>
  )
}
