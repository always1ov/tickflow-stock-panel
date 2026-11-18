/**
 * D 区 · 复盘档案带 (R791) — 横向时间轴, 取代右侧 21rem 常驻历史栏。
 *
 * 复盘的价值在对比, 不在单篇阅读: 色块 = 当天情绪分, 旁边是四大指数涨跌,
 * 「对照」拉出最近两篇的 定调 / 明日计划 / 风险 三段原文(只摘录, 不做语义 diff)。
 *
 * 数据只用 meta(不含正文); 正文与对照都按 id 按需拉。
 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { AnimatePresence, motion } from 'framer-motion'
import { History, RefreshCw, Scale, Trash2, X } from 'lucide-react'

import { api, type AiReviewReport, type AiReviewReportMeta } from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import { cn } from '@/lib/cn'
import { Button } from '@/components/ui'
import { fmtArchivedAt, parseIndexPcts, pctClass, scoreColor, shortenIndexNames } from './shared'

/** 对照三段: 只按标题关键词摘原文, 缺哪段就写「原文未包含」 */
const COMPARE_SECTIONS: { key: string; label: string; re: RegExp }[] = [
  { key: 'thesis', label: '一句话定调', re: /定调|总结|结论/ },
  { key: 'plan', label: '明日计划', re: /明日|次日|交易计划/ },
  { key: 'risk', label: '风险提示', re: /风险/ },
]

function sectionText(content: string, re: RegExp): string {
  const lines = content.split('\n')
  const start = lines.findIndex(l => /^#{2,3}\s+/.test(l) && re.test(l))
  if (start < 0) return ''
  const out: string[] = []
  for (const line of lines.slice(start + 1)) {
    if (/^#{1,3}\s+/.test(line)) break
    out.push(line)
  }
  return out.join('\n').trim()
}

function CompareColumn({ report }: { report?: AiReviewReport }) {
  if (!report) {
    return <div className="h-24 animate-pulse rounded-btn bg-elevated/60" />
  }
  return (
    <div className="min-w-0 space-y-2">
      {COMPARE_SECTIONS.map(s => {
        const text = sectionText(report.content, s.re)
        return (
          <div key={s.key}>
            <div className="text-micro text-muted">{s.label}</div>
            <p className="mt-0.5 line-clamp-4 whitespace-pre-wrap text-xs leading-relaxed text-secondary">
              {text || '原文未包含'}
            </p>
          </div>
        )
      })}
    </div>
  )
}

export interface ArchiveStripProps {
  reports: AiReviewReportMeta[]
  loading?: boolean
  selectedId?: string | null
  generating?: boolean
  onView: (id: string) => void
  onBackToGenerating: () => void
  onDelete: (id: string) => void
}

export function ArchiveStrip({
  reports, loading, selectedId, generating, onView, onBackToGenerating, onDelete,
}: ArchiveStripProps) {
  const [confirmId, setConfirmId] = useState<string | null>(null)
  const [compareOpen, setCompareOpen] = useState(false)
  // 对照默认最近两篇; 用户可从档案带里改选(点击项即切换该侧)
  const [pair, setPair] = useState<[string | null, string | null]>([null, null])
  const leftId = pair[0] ?? reports[0]?.id ?? null
  const rightId = pair[1] ?? reports[1]?.id ?? null

  const leftQ = useQuery({
    queryKey: QK.reviewReportDetail(leftId ?? ''),
    queryFn: () => api.reviewReportDetail(leftId!),
    enabled: compareOpen && !!leftId,
    staleTime: 60_000,
  })
  const rightQ = useQuery({
    queryKey: QK.reviewReportDetail(rightId ?? ''),
    queryFn: () => api.reviewReportDetail(rightId!),
    enabled: compareOpen && !!rightId,
    staleTime: 60_000,
  })
  const left = leftQ.data?.report
  const right = rightQ.data?.report

  return (
    <section className="rounded-card border border-border bg-surface/80">
      <div className="flex items-center gap-2 border-b border-border px-3 py-2">
        <History className="h-3.5 w-3.5 text-accent" />
        <span className="text-xs font-medium text-foreground">复盘档案</span>
        <span className="font-mono text-micro text-muted">({reports.length})</span>
        <div className="ml-auto flex items-center gap-1">
          <Button
            size="xs"
            onClick={() => setCompareOpen(true)}
            disabled={reports.length < 2}
            className="text-micro"
            title={reports.length < 2 ? '至少两篇才能对照' : '选两篇对照 定调 / 明日计划 / 风险'}
          >
            <Scale className="h-3 w-3" />对照
          </Button>
        </div>
      </div>

      {loading ? (
        <div className="flex gap-2 overflow-hidden px-3 py-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="h-14 w-24 shrink-0 animate-pulse rounded-btn bg-elevated/60" />
          ))}
        </div>
      ) : reports.length === 0 && !generating ? (
        <div className="px-3 py-6 text-center text-xs text-muted">暂无历史复盘 · 生成完成后自动归档</div>
      ) : (
        <div className="flex gap-1.5 overflow-x-auto px-3 py-2.5">
          {generating && (
            <button
              onClick={onBackToGenerating}
              className={cn(
                'flex w-24 shrink-0 flex-col items-start gap-0.5 rounded-btn border px-2 py-1.5 text-left transition-colors',
                selectedId == null ? 'border-accent/40 bg-accent/10' : 'border-border hover:bg-elevated/60',
              )}
            >
              <span className="inline-flex items-center gap-1 text-micro font-medium text-accent">
                <RefreshCw className="h-3 w-3 animate-spin" />生成中
              </span>
              <span className="text-micro text-muted">AI 正在复盘今日盘面</span>
            </button>
          )}
          {reports.map(r => {
            const color = scoreColor(r.emotion_score)
            const pcts = parseIndexPcts(shortenIndexNames(r.summary ?? '').split('|')[0])
            const selected = selectedId === r.id
            return (
              <div
                key={r.id}
                className={cn(
                  'group relative w-28 shrink-0 rounded-btn border px-2 py-1.5 transition-colors',
                  selected ? 'border-accent/40 bg-accent/10' : 'border-border hover:bg-elevated/60',
                )}
              >
                <button
                  type="button"
                  onClick={() => { onView(r.id); setPair([r.id, rightId]) }}
                  className="block w-full text-left"
                  title={`${r.as_of} · ${r.emotion_label ?? ''}${r.created_at ? ` · 归档 ${fmtArchivedAt(r.created_at)}` : ''}`}
                >
                  <span className="flex items-center gap-1.5">
                    <span
                      className="grid h-6 w-6 shrink-0 place-items-center rounded-btn font-mono text-micro font-bold tabular-nums"
                      style={{ color, backgroundColor: `${color}1a` }}
                    >
                      {r.emotion_score ?? '—'}
                    </span>
                    <span className="font-mono text-micro text-foreground">{r.as_of}</span>
                  </span>
                  <span className="mt-1 flex flex-wrap gap-x-1 gap-y-0.5">
                    {pcts.length === 0 ? (
                      <span className="truncate text-micro text-muted">{r.emotion_label ?? '—'}</span>
                    ) : pcts.map(p => (
                      <span key={p.name} className="inline-flex items-center gap-0.5 text-micro">
                        <span className="text-muted">{p.name}</span>
                        <span className={cn('font-mono tabular-nums', pctClass(p.pctNum))}>{p.pctStr}</span>
                      </span>
                    ))}
                  </span>
                </button>
                {confirmId === r.id ? (
                  <span className="mt-1 flex items-center gap-1">
                    <Button
                      variant="danger"
                      size="xs"
                      onClick={() => { onDelete(r.id); setConfirmId(null) }}
                      className="text-micro"
                    >
                      确认删除
                    </Button>
                    <Button
                      variant="ghost"
                      size="xs"
                      onClick={() => setConfirmId(null)}
                      className="text-micro"
                    >
                      取消
                    </Button>
                  </span>
                ) : (
                  <button
                    onClick={() => setConfirmId(r.id)}
                    className="absolute right-1 top-1 p-0.5 text-muted opacity-0 transition-colors hover:text-bear focus:opacity-100 group-hover:opacity-100"
                    title="删除"
                  >
                    <Trash2 className="h-3 w-3" />
                  </button>
                )}
              </div>
            )
          })}
        </div>
      )}

      {/* 对照抽屉: 只读原文摘录, 不做语义 diff */}
      <AnimatePresence>
        {compareOpen && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15, ease: 'easeOut' }}
            className="fixed inset-0 z-50 flex items-end justify-center bg-black/50 p-0 sm:p-4"
            onClick={() => setCompareOpen(false)}
          >
            <motion.div
              initial={{ y: 24, opacity: 0 }}
              animate={{ y: 0, opacity: 1 }}
              exit={{ y: 24, opacity: 0 }}
              transition={{ duration: 0.18, ease: 'easeOut' }}
              className="max-h-[80vh] w-full max-w-3xl overflow-y-auto rounded-t-dialog border border-border bg-surface p-4 shadow-2xl sm:rounded-dialog"
              onClick={e => e.stopPropagation()}
            >
              <div className="mb-3 flex items-center gap-2">
                <Scale className="h-4 w-4 text-accent" />
                <h3 className="text-sm font-medium text-foreground">复盘对照</h3>
                <span className="text-micro text-muted">三段原文摘录 · 不做语义判定</span>
                <Button icon variant="ghost" size="xs" onClick={() => setCompareOpen(false)} className="ml-auto">
                  <X className="h-4 w-4" />
                </Button>
              </div>
              <div className="grid gap-4 sm:grid-cols-2">
                {[{ id: leftId, q: leftQ, report: left }, { id: rightId, q: rightQ, report: right }].map((side, i) => (
                  <div key={i} className="min-w-0 rounded-btn border border-border/60 p-2.5">
                    <select
                      value={side.id ?? ''}
                      onChange={e => {
                        const next = e.target.value || null
                        setPair(prev => (i === 0 ? [next, prev[1]] : [prev[0], next]))
                      }}
                      className="mb-2 w-full rounded-btn border border-border bg-base px-2 py-1 text-xs text-foreground outline-none focus:border-accent/50"
                    >
                      {reports.map(r => (
                        <option key={r.id} value={r.id}>{r.as_of} · 情绪 {r.emotion_score ?? '—'}</option>
                      ))}
                    </select>
                    {side.q.isLoading ? <div className="h-24 animate-pulse rounded-btn bg-elevated/60" /> : (
                      <CompareColumn report={side.report} />
                    )}
                  </div>
                ))}
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </section>
  )
}
