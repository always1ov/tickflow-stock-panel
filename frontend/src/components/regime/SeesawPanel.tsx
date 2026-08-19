import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Repeat, Sparkles, Loader2, History, ChevronDown } from 'lucide-react'
import { api, type SeesawPair, type SeesawEntry } from '@/lib/api'
import { toast } from '@/components/Toast'
import { cn } from '@/lib/cn'

/**
 * [fork 增强] R28 板块跷跷板 —— 资金在两条主线之间来回搬的检测。
 *
 * 两层:
 *  - 规则层(免费): 后端用主线日度强度算出候选对, 开页即有, 不花 AI。
 *  - AI 层(点按钮): 甄别哪几对是真跷跷板、当下轮到谁、对手盘什么条件接力,
 *    结果滚动留档 30 天 —— 单看今天没意义, 要知道最近来回切了几轮。
 */

const CARD = 'rounded-card border border-border bg-surface/80 shadow-[0_1px_2px_hsl(var(--border)/0.4)] backdrop-blur-sm'
const COLOR_A = '#f59e0b'
const COLOR_B = '#38bdf8'

/** 双线迷你走势: 两条主线的日度强度叠在一起, 交替形态一眼可见(0 = 当天没上榜)。 */
function DualSpark({ a, b }: { a: number[]; b: number[] }) {
  const n = Math.max(a.length, b.length)
  if (n < 2) return null
  const pts = (xs: number[]) =>
    xs.map((v, i) => `${(i / (n - 1)) * 100},${33 - Math.max(0, Math.min(100, v)) / 100 * 30}`).join(' ')
  return (
    <svg viewBox="0 0 100 34" preserveAspectRatio="none" className="h-9 w-full">
      <polyline points={pts(a)} fill="none" stroke={COLOR_A} strokeWidth={1} vectorEffect="non-scaling-stroke" />
      <polyline points={pts(b)} fill="none" stroke={COLOR_B} strokeWidth={1} vectorEffect="non-scaling-stroke" />
    </svg>
  )
}

function PairCard({ p, verdict, note }: { p: SeesawPair; verdict?: string; note?: string }) {
  const leaderIsA = p.leader === p.a
  return (
    <div className="rounded-lg border border-border/60 bg-base/40 p-2.5">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <span className="inline-flex items-center gap-1 text-xs font-medium">
          <span style={{ color: COLOR_A }}>{p.a}</span>
          <Repeat className="h-3 w-3 text-muted" />
          <span style={{ color: COLOR_B }}>{p.b}</span>
        </span>
        <span className="rounded border border-border px-1.5 py-px font-mono text-[10px] text-secondary"
          title="跷跷板分: 反向程度 + 来回轮数 + 双方活跃度">
          {p.score} 分
        </span>
        <span className="rounded border border-border/60 px-1.5 py-px font-mono text-[10px] text-muted"
          title="窗口内领先方换手次数 —— 来回才算跷跷板, 一次性此消彼长不算">
          来回 {p.flips} 轮
        </span>
        {verdict && (
          <span className={cn('rounded px-1.5 py-px text-[10px]',
            verdict === '成立'
              ? 'border border-emerald-400/40 bg-emerald-400/10 text-emerald-400'
              : 'border border-amber-400/40 bg-amber-400/10 text-amber-400')}>
            AI {verdict}
          </span>
        )}
        <span className="ml-auto rounded px-1.5 py-px text-[10px]"
          style={{ color: leaderIsA ? COLOR_A : COLOR_B, backgroundColor: (leaderIsA ? COLOR_A : COLOR_B) + '18' }}>
          当下{p.leader}占优 · 已 {p.lead_days} 天
        </span>
      </div>
      {p.series_a && p.series_b && (
        <div className="mt-1.5"><DualSpark a={p.series_a} b={p.series_b} /></div>
      )}
      <p className="mt-1 text-[10px] leading-relaxed text-secondary">{p.hint}</p>
      {note && <p className="mt-0.5 text-[10px] leading-relaxed text-accent/90">AI: {note}</p>}
    </div>
  )
}

export function SeesawPanel({ kind }: { kind: 'concept' | 'industry' }) {
  const qc = useQueryClient()
  const [showHistory, setShowHistory] = useState(false)
  const [openDay, setOpenDay] = useState<string | null>(null)

  const q = useQuery({
    queryKey: ['regime-seesaw', kind],
    queryFn: () => api.regimeSeesaw(kind),
    staleTime: 5 * 60_000,
  })

  const detect = useMutation({
    mutationFn: () => api.regimeSeesawDetect(kind),
    onSuccess: (res) => {
      if (res.error) toast(res.error, 'error')
      else toast(`已识别 ${res.ai?.picks?.length ?? 0} 对跷跷板, 已存入 30 天留档`, 'success')
      qc.invalidateQueries({ queryKey: ['regime-seesaw', kind] })
    },
    onError: (e: any) => toast(e?.message ?? '识别失败', 'error'),
  })

  const pairs = q.data?.pairs ?? []
  const history = q.data?.history ?? []
  const latest = q.data?.latest ?? null
  // AI 结论按 pair 对齐到规则候选上; 只有当天的结论才贴, 隔夜的放历史里看
  const aiByPair = new Map(
    (latest?.as_of === q.data?.as_of ? latest?.ai?.picks ?? [] : []).map(p => [p.pair, p]),
  )

  return (
    <div className={cn(CARD, 'p-3')}>
      <div className="flex items-center gap-2">
        <span className="h-3 w-0.5 rounded-full bg-gradient-to-b from-accent to-accent/30" />
        <Repeat className="h-3.5 w-3.5 text-accent" />
        <h2 className="text-xs font-semibold text-foreground">板块跷跷板</h2>
        <span className="hidden text-[9px] text-muted sm:inline">
          一边熄火往往就是另一边点火 · 近 {q.data?.window ?? 0} 个交易日
        </span>
        <button
          onClick={() => setShowHistory(v => !v)}
          className={cn('ml-auto inline-flex items-center gap-1 rounded-btn border px-2 py-0.5 text-[10px] transition-colors',
            showHistory ? 'border-accent/50 text-accent' : 'border-border bg-base text-secondary hover:text-accent')}
          title="最近 30 天的识别留档 —— 看这对板块来回切了几轮、上一轮哪天换的手"
        >
          <History className="h-3 w-3" /> 30 天留档{history.length ? ` · ${history.length}` : ''}
        </button>
        <button
          onClick={() => detect.mutate()}
          disabled={detect.isPending}
          className="inline-flex items-center gap-1 rounded-btn border border-accent/40 bg-accent/10 px-2 py-0.5 text-[10px] text-accent transition-colors hover:bg-accent/20 disabled:opacity-60"
          title="让 AI 看真实日度强度序列, 甄别哪几对是真跷跷板、当下轮到谁(会调用 AI)"
        >
          {detect.isPending ? <Loader2 className="h-3 w-3 animate-spin" /> : <Sparkles className="h-3 w-3" />}
          AI 一键识别跷跷板
        </button>
      </div>

      {/* AI 结论(最近一次) */}
      {latest?.ai?.summary && (
        <p className="mt-2 rounded-lg border border-accent/25 bg-accent/[0.06] px-2.5 py-2 text-[11px] leading-relaxed text-secondary">
          <span className="mr-1 text-accent">AI</span>{latest.ai.summary}
          <span className="ml-1.5 font-mono text-[9px] text-muted">
            {latest.as_of ?? ''}{latest.as_of !== q.data?.as_of ? ' · 非最新交易日, 建议重新识别' : ''}
          </span>
        </p>
      )}

      {/* 规则候选 */}
      <div className="mt-2 space-y-1.5">
        {pairs.length === 0 ? (
          <p className="py-4 text-center text-[10px] text-muted">
            {q.isLoading ? '加载中…' : (q.data?.error ?? '近期没有明显的跷跷板 —— 板块各走各的, 或主线数据不足')}
          </p>
        ) : pairs.map(p => (
          <PairCard key={p.pair} p={p}
            verdict={aiByPair.get(p.pair)?.verdict}
            note={aiByPair.get(p.pair)?.note} />
        ))}
      </div>

      {/* 30 天留档 */}
      {showHistory && (
        <div className="mt-2 border-t border-border/60 pt-2">
          {history.length === 0 ? (
            <p className="py-3 text-center text-[10px] text-muted">还没有留档 —— 点一次「AI 一键识别」就会开始按天记录</p>
          ) : (
            <div className="max-h-[300px] space-y-1 overflow-auto">
              {history.map((h: SeesawEntry) => {
                const key = `${h.as_of}-${h.created_at}`
                const open = openDay === key
                const top = h.pairs?.[0]
                return (
                  <div key={key} className="rounded border border-border/50 bg-base/30">
                    <button onClick={() => setOpenDay(open ? null : key)}
                      className="flex w-full items-center gap-2 px-2 py-1.5 text-left">
                      <ChevronDown className={cn('h-3 w-3 shrink-0 text-muted transition-transform', !open && '-rotate-90')} />
                      <span className="font-mono text-[10px] text-secondary">{h.as_of ?? '—'}</span>
                      <span className="truncate text-[10px] text-foreground">
                        {top ? `${top.a} ↔ ${top.b}` : '无候选'}
                      </span>
                      {top && <span className="shrink-0 font-mono text-[9px] text-muted">当下 {top.leader}</span>}
                      <span className="ml-auto shrink-0 text-[9px] text-muted">
                        {h.pairs?.length ?? 0} 对{h.ai?.picks?.length ? ` · AI 认 ${h.ai.picks.length}` : ''}
                      </span>
                    </button>
                    {open && (
                      <div className="space-y-1 border-t border-border/40 px-2 py-1.5">
                        {h.ai?.summary && <p className="text-[10px] leading-relaxed text-secondary">{h.ai.summary}</p>}
                        {(h.pairs ?? []).map(p => (
                          <div key={p.pair} className="flex flex-wrap items-center gap-x-2 text-[10px]">
                            <span style={{ color: COLOR_A }}>{p.a}</span>
                            <span className="text-muted">↔</span>
                            <span style={{ color: COLOR_B }}>{p.b}</span>
                            <span className="font-mono text-muted">{p.score} 分 · 来回 {p.flips} 轮</span>
                            <span className="text-secondary">当下 {p.leader}(已 {p.lead_days} 天)</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
