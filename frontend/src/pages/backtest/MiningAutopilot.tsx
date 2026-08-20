import { useEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import {
  Bot, ChevronDown, ExternalLink, Info, LoaderCircle, Lock, Play, Rocket, Square,
} from 'lucide-react'
import { toast } from '@/components/Toast'
import { api, type AutopilotIteration, type AutopilotSession } from '@/lib/api'

/**
 * [fork 增强] R31 AI 自动挖掘 —— 拿上一轮结果反馈给 AI, 由它重配参数再跑一轮。
 *
 * 手动与自动共用后端同一个 step 入口:
 *   手动 = 点一次「AI 再调一轮」调一次 step
 *   自动 = 这里定时轮询 step(勾上开关即可)
 *
 * 界面必须如实呈现两件事, 否则这个功能就是在骗人:
 *   1. 终检窗口是锁定的, 循环看不到 —— 顶部常驻说明
 *   2. 迭代次数越多, 搜索窗口的指标越该打折 —— 收工时显示 confidence_note
 */

const INPUT = 'h-8 w-full rounded-input border border-border bg-surface px-2 text-xs text-foreground outline-none transition-colors focus:border-accent'
const LABEL = 'mb-1 block text-[10px] font-medium text-secondary'
const POLL_MS = 15_000

const STATUS_LABEL: Record<AutopilotSession['status'], string> = {
  open: '进行中',
  satisfied: 'AI 认为够好了',
  exhausted: '已用满轮数',
  failed: '中止',
}
const STATUS_CLS: Record<AutopilotSession['status'], string> = {
  open: 'bg-accent/10 text-accent',
  satisfied: 'bg-success/10 text-success',
  exhausted: 'bg-warning/10 text-warning',
  failed: 'bg-danger/10 text-danger',
}

function yearsAgo(years: number) {
  const d = new Date()
  d.setFullYear(d.getFullYear() - years)
  return d.toISOString().slice(0, 10)
}

function num(v: unknown, digits = 2) {
  return typeof v === 'number' && Number.isFinite(v) ? v.toFixed(digits) : '—'
}

function pct(v: unknown, digits = 1) {
  return typeof v === 'number' && Number.isFinite(v) ? `${(v * 100).toFixed(digits)}%` : '—'
}

export function MiningAutopilot() {
  const queryClient = useQueryClient()
  const [, setSearchParams] = useSearchParams()
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [auto, setAuto] = useState(false)
  const [openIter, setOpenIter] = useState<number | null>(null)
  const [form, setForm] = useState({
    start: yearsAgo(5),
    end: new Date().toISOString().slice(0, 10),
    holdoutDays: 365,
    profile: 'balanced' as 'balanced' | 'strict',
    maxIterations: 6,
  })

  const sessions = useQuery({
    queryKey: ['mining-autopilot-sessions'],
    queryFn: () => api.miningAutopilotSessions(),
    staleTime: 30_000,
  })
  // 未手动选择时跟随最新会话 —— 刷新页面回来还是这一个
  const active: AutopilotSession | undefined = useMemo(() => {
    const items = sessions.data?.items ?? []
    return sessionId ? items.find(s => s.session_id === sessionId) : items[0]
  }, [sessions.data, sessionId])

  const refresh = () => queryClient.invalidateQueries({ queryKey: ['mining-autopilot-sessions'] })

  const start = useMutation({
    mutationFn: () => api.miningAutopilotStart({
      start: form.start, end: form.end, holdout_days: form.holdoutDays,
      budget_profile: form.profile, max_iterations: form.maxIterations,
    }),
    onSuccess: s => { setSessionId(s.session_id); refresh(); toast('会话已开, 点「AI 再调一轮」开跑', 'success') },
    onError: e => toast(String((e as Error).message || e), 'error'),
  })

  const step = useMutation({
    mutationFn: (id: string) => api.miningAutopilotStep(id),
    onSuccess: res => {
      refresh()
      if (res.action === 'error') { setAuto(false); toast(res.message, 'error') }
      else if (res.action === 'done') { setAuto(false); toast(res.message, 'success') }
    },
    onError: e => { setAuto(false); toast(String((e as Error).message || e), 'error') },
  })

  // 自动模式 = 定时轮询同一个 step; 上一轮还在跑时后端返回 running, 不会重复起 run
  const stepRef = useRef(step)
  stepRef.current = step
  useEffect(() => {
    if (!auto || !active || active.status !== 'open') return
    const id = active.session_id
    const timer = setInterval(() => {
      if (!stepRef.current.isPending) stepRef.current.mutate(id)
    }, POLL_MS)
    return () => clearInterval(timer)
  }, [auto, active])

  const busy = step.isPending || start.isPending
  const closed = !!active && active.status !== 'open'

  return (
    <section className="rounded-card border border-border bg-surface">
      <header className="flex flex-wrap items-center gap-x-2 gap-y-1.5 border-b border-border px-3 py-2">
        <Bot className="h-3.5 w-3.5 shrink-0 text-accent" />
        <h2 className="shrink-0 text-xs font-semibold text-foreground">AI 自动挖掘</h2>
        <span className="text-[9px] text-muted">跑 → AI 看结果 → 改配置 → 再跑，直到 AI 认为够好</span>
      </header>

      {/* 终检窗口说明: 常驻, 不折叠 —— 这是这个功能能不能信的前提 */}
      <div className="flex gap-2 border-b border-border bg-elevated/40 px-3 py-2">
        <Lock className="mt-px h-3 w-3 shrink-0 text-warning" />
        <p className="text-[10px] leading-4 text-secondary">
          区间会切成两段：<span className="text-foreground">搜索窗口</span>给 AI 反复试，
          <span className="text-warning">终检窗口</span>全程锁定、循环看不到。
          AI 选出赢家后<span className="text-foreground">停在那里等你人工确认发布</span>，
          发布后才在终检窗口跑一次——那个数字才是没被挑拣过的。
          反复读样本外指标再改配置重跑，试的次数够多必然撞上一个「过门槛」的，那不是策略行。
        </p>
      </div>

      {/* 开新会话 */}
      <div className="grid grid-cols-2 gap-2 border-b border-border px-3 py-2.5 sm:grid-cols-5">
        <label><span className={LABEL}>开始</span>
          <input type="date" className={INPUT} value={form.start}
            onChange={e => setForm({ ...form, start: e.target.value })} /></label>
        <label><span className={LABEL}>结束</span>
          <input type="date" className={INPUT} value={form.end}
            onChange={e => setForm({ ...form, end: e.target.value })} /></label>
        <label><span className={LABEL}>终检窗口(天)</span>
          <input type="number" min={180} max={1095} className={INPUT} value={form.holdoutDays}
            onChange={e => setForm({ ...form, holdoutDays: Number(e.target.value) })} /></label>
        <label>
          <span className={LABEL} title="探索档结果不能发布, 所以自动循环不提供">档位</span>
          <select className={INPUT} value={form.profile}
            onChange={e => setForm({ ...form, profile: e.target.value as 'balanced' | 'strict' })}>
            <option value="balanced">均衡(需 ~3.2 年搜索窗口)</option>
            <option value="strict">严格(需 ~4.8 年搜索窗口)</option>
          </select>
        </label>
        <label><span className={LABEL}>最多几轮</span>
          <input type="number" min={1} max={20} className={INPUT} value={form.maxIterations}
            onChange={e => setForm({ ...form, maxIterations: Number(e.target.value) })} /></label>
      </div>
      <div className="flex flex-wrap items-center gap-2 border-b border-border px-3 py-2">
        <button type="button" disabled={busy} onClick={() => start.mutate()}
          className="inline-flex h-8 items-center gap-1.5 rounded-btn border border-border px-3 text-xs text-secondary transition-colors hover:border-accent/40 hover:text-accent disabled:opacity-50">
          {start.isPending ? <LoaderCircle className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />}
          开新会话
        </button>
        {active && !closed && (
          <>
            <button type="button" disabled={busy}
              onClick={() => step.mutate(active.session_id)}
              className="inline-flex h-8 items-center gap-1.5 rounded-btn bg-accent px-3 text-xs font-semibold text-white transition-opacity disabled:opacity-50">
              {step.isPending ? <LoaderCircle className="h-3.5 w-3.5 animate-spin" /> : <Bot className="h-3.5 w-3.5" />}
              AI 再调一轮
            </button>
            <button type="button" onClick={() => setAuto(v => !v)}
              className={`inline-flex h-8 items-center gap-1.5 rounded-btn border px-3 text-xs transition-colors ${
                auto ? 'border-warning/50 bg-warning/10 text-warning' : 'border-border text-secondary hover:border-accent/40 hover:text-accent'
              }`}
              title={`自动模式每 ${POLL_MS / 1000} 秒推进一次, 跑到 AI 满意或用满轮数为止`}>
              {auto ? <Square className="h-3.5 w-3.5" /> : <Play className="h-3.5 w-3.5" />}
              {auto ? '停止自动' : '自动跑到满意'}
            </button>
          </>
        )}
        {active && (
          <span className={`ml-auto shrink-0 rounded-full px-2 py-px text-[10px] font-medium ${STATUS_CLS[active.status]}`}>
            {STATUS_LABEL[active.status]} · 第 {active.iterations.length}/{active.max_iterations} 轮
          </span>
        )}
      </div>

      {!active ? (
        <div className="px-3 py-8 text-center text-[11px] text-muted">
          还没有会话 —— 设好区间点「开新会话」。区间要够长：均衡档的搜索窗口需约 3.2 年，
          再加上终检窗口，总共建议 5 年以上。
        </div>
      ) : (
        <>
          <div className="border-b border-border px-3 py-2 text-[10px] text-muted">
            搜索窗口 <span className="font-mono text-secondary">{active.search_start} → {active.search_end}</span>
            <span className="mx-2 text-muted/50">|</span>
            <Lock className="mr-1 inline h-2.5 w-2.5 text-warning" />
            终检窗口 <span className="font-mono text-warning">{active.holdout_start} → {active.holdout_end}</span>
          </div>

          {/* 收工卡: 赢家 + 可信度提示 + 人工发布 */}
          {closed && (
            <div className="border-b border-border bg-elevated/30 px-3 py-2.5">
              {active.winner ? (
                <>
                  <div className="flex flex-wrap items-center gap-2">
                    <Rocket className="h-3.5 w-3.5 shrink-0 text-accent" />
                    <span className="text-xs font-semibold text-foreground">
                      赢家：{String(active.winner.name ?? active.winner.signature ?? '—')}
                    </span>
                    <span className="font-mono text-[10px] text-muted">
                      Sharpe {num(active.winner['样本外Sharpe'])} · 回撤 {pct(active.winner['最大回撤'])}
                      · 成交 {String(active.winner['成交笔数'] ?? '—')} 笔
                    </span>
                  </div>
                  {active.confidence_note && (
                    <p className="mt-1.5 flex gap-1.5 text-[10px] leading-4 text-warning">
                      <Info className="mt-px h-3 w-3 shrink-0" />
                      {active.confidence_note}
                    </p>
                  )}
                  <p className="mt-1.5 text-[10px] leading-4 text-secondary">
                    下一步：在下方工作台里打开这一轮，点<span className="text-foreground">「显式发布」</span>人工确认。
                    系统不会替你发布；发布后才会在终检窗口跑一次定生死。
                  </p>
                  {/* 直达: 工作台的 run/candidate 都由 URL 驱动, 一键定位到赢家那一轮 */}
                  {active.winner.run_id && (
                    <button type="button"
                      onClick={() => {
                        const params = new URLSearchParams()
                        params.set('run', String(active.winner?.run_id ?? ''))
                        if (active.winner?.signature) params.set('candidate', String(active.winner.signature))
                        setSearchParams(params, { replace: true })
                        toast('已在下方工作台定位到赢家候选', 'success')
                      }}
                      className="mt-2 inline-flex h-7 items-center gap-1.5 rounded-btn border border-accent/40 bg-accent/10 px-2.5 text-[10px] font-medium text-accent transition-colors hover:bg-accent/20">
                      <ExternalLink className="h-3 w-3" />
                      在工作台里打开这个候选
                    </button>
                  )}
                </>
              ) : (
                <p className="text-[10px] text-danger">
                  没有产生可用赢家{active.fail_reason ? ` —— ${active.fail_reason}` : ''}
                </p>
              )}
            </div>
          )}

          {/* 逐轮记录 */}
          <div className="max-h-[26rem] overflow-auto">
            {active.iterations.length === 0 ? (
              <div className="px-3 py-6 text-center text-[11px] text-muted">
                还没跑过 —— 点「AI 再调一轮」开始第 1 轮
              </div>
            ) : [...active.iterations].reverse().map(it => (
              <IterationRow key={it.iteration} it={it}
                open={openIter === it.iteration}
                onToggle={() => setOpenIter(openIter === it.iteration ? null : it.iteration)} />
            ))}
          </div>
        </>
      )}
    </section>
  )
}

function IterationRow({ it, open, onToggle }: {
  it: AutopilotIteration; open: boolean; onToggle: () => void
}) {
  const running = ['queued', 'running', 'cancelling'].includes(it.status)
  const factors = (it.config.factor_names as string[] | undefined) ?? []
  return (
    <div className="border-b border-border/60 last:border-0">
      <button type="button" onClick={onToggle}
        className="flex w-full items-center gap-2 px-3 py-2 text-left hover:bg-elevated/50">
        <ChevronDown className={`h-3 w-3 shrink-0 text-muted transition-transform ${open ? '' : '-rotate-90'}`} />
        <span className="shrink-0 text-[10px] font-semibold text-foreground">第 {it.iteration} 轮</span>
        {running && <LoaderCircle className="h-3 w-3 shrink-0 animate-spin text-accent" />}
        <span className="min-w-0 flex-1 truncate text-[10px] text-secondary">
          {it.ai?.verdict || (running ? '挖掘进行中…' : it.status)}
        </span>
        <span className="shrink-0 font-mono text-[9px] text-muted">
          {String(it.config.budget_profile ?? '')} · {factors.length} 因子
        </span>
      </button>
      {open && (
        <div className="space-y-2 bg-base/40 px-3 py-2">
          <div className="text-[10px] text-muted">
            因子：<span className="font-mono text-secondary">{factors.join(', ') || '—'}</span>
          </div>
          <div className="font-mono text-[9px] text-muted">
            组合上限 {String(it.config.max_combination_factors ?? '—')} · beam {String(it.config.beam_width ?? '—')}
            · 相关阈值 {String(it.config.correlation_threshold ?? '—')}
            {it.run_id && <> · run {it.run_id.slice(0, 8)}</>}
          </div>
          {it.candidates.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[520px] text-left text-[10px]">
                <thead>
                  <tr className="text-[9px] text-muted">
                    <th className="py-1 pr-2 font-medium">候选</th>
                    <th className="py-1 pr-2 font-medium">达标</th>
                    <th className="py-1 pr-2 text-right font-medium">Sharpe</th>
                    <th className="py-1 pr-2 text-right font-medium">回撤</th>
                    <th className="py-1 pr-2 text-right font-medium">正收益折</th>
                    <th className="py-1 text-right font-medium">成交</th>
                  </tr>
                </thead>
                <tbody>
                  {it.candidates.map((c, i) => (
                    <tr key={i} className="border-t border-border/40">
                      <td className="py-1 pr-2 text-foreground">{String(c['name'] ?? '—')}</td>
                      <td className="py-1 pr-2">
                        <span className={c['达标'] ? 'text-success' : 'text-warning'}>
                          {c['达标'] ? '达标' : '未达标'}
                        </span>
                      </td>
                      <td className="py-1 pr-2 text-right font-mono">{num(c['样本外Sharpe'])}</td>
                      <td className="py-1 pr-2 text-right font-mono">{pct(c['最大回撤'])}</td>
                      <td className="py-1 pr-2 text-right font-mono">{pct(c['正收益折占比'], 0)}</td>
                      <td className="py-1 text-right font-mono">{String(c['成交笔数'] ?? '—')}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {it.ai?.reason && (
            <p className="text-[10px] leading-4 text-accent/90">下一轮怎么改：{it.ai.reason}</p>
          )}
        </div>
      )}
    </div>
  )
}
