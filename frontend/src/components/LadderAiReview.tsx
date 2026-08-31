/**
 * [R50] 「AI 打板复盘」—— 把当日连板梯队快照交给 AI, 按打板战法
 * (情绪周期 / 龙头 / 二进三 / 反包)输出候选分组。
 *
 * 原来叫「AI 战法」, 挂在连板梯队页的表头上。搬到复盘页有两个理由:
 *   · 它做的事就是复盘 —— 盘后拿当日梯队回看情绪走到哪一档、谁是龙头、
 *     明天该盯什么。放在梯队页等于让人先切页面再复盘。
 *   · 复盘页本来就有一份「AI 大盘复盘」。大盘那条线看指数与情绪, 这条线
 *     看梯队与打板, 两份报告并排才构成一次完整的盘后复盘。
 * 名字也跟着改: 在复盘页上「AI 战法」看不出和旁边那份报告是什么关系,
 * 「打板复盘」与「大盘复盘」一对照就清楚了。
 *
 * 这个组件自带梯队查询 —— 复盘页没有梯队数据, 让它去 props 里传等于把
 * 两个页面绑死。ext 字段配置(题材/行业)与梯队页共读同一份 localStorage,
 * 所以喂给 AI 的题材和梯队页上显示的是同一批。
 */
import { useMemo, useState, useEffect, useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Loader2, Send, Sparkles, X } from 'lucide-react'
import { api } from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import { SeesawPanel } from '@/components/regime/SeesawPanel'
import { buildExtColumnsParam, getExtTags, loadExtFields } from '@/lib/ladderExtFields'

type AiPayload = { date: string; stats: Record<string, unknown>; tiers: unknown[] }

/**
 * 触发按钮 + 弹窗。`date` 留空则跟随后端的最新交易日。
 *
 * 梯队数据只在按钮被点开之后才拉 —— 复盘页进来先看的是大盘报告,
 * 没点开就先拉一份梯队等于每次进页面白花一次请求。
 */
export function LadderAiReview({ date }: { date?: string }) {
  const [open, setOpen] = useState(false)
  const extFields = useMemo(loadExtFields, [])
  const extColumnsParam = useMemo(() => buildExtColumnsParam(extFields), [extFields])

  const { data, isLoading } = useQuery({
    queryKey: [...QK.limitLadder(date || undefined), extColumnsParam, 'up'],
    queryFn: () => api.limitLadder(date || undefined, extColumnsParam, 'up'),
    staleTime: 5 * 60_000,
    enabled: open,
  })

  const payload: AiPayload = useMemo(() => {
    const rawTiers = data?.tiers ?? []
    const allStocks = rawTiers.flatMap(t => t.stocks)
    const stats = {
      limit_up: data?.counts?.up ?? 0,
      limit_down: data?.counts?.down ?? 0,
      broken: allStocks.filter(st => st.status === 'broken').length,
      failed: allStocks.filter(st => st.status === 'failed').length,
      max_boards: rawTiers.reduce((m, t) => Math.max(m, t.boards), 0),
    }
    const tiers = rawTiers.map(t => ({
      boards: t.boards,
      count: t.count,
      stocks: t.stocks.slice(0, 25).map(st => ({
        symbol: st.symbol,
        name: st.name,
        boards: t.boards,
        status: st.status,
        change_pct: st.change_pct,
        sealed_status: st.sealed_status,
        is_one_word: st.is_one_word,
        concepts: getExtTags(st, extFields.concept).slice(0, 4).join('/') || undefined,
      })),
    }))
    return { date: data?.as_of ?? date ?? '', stats, tiers }
  }, [data, date, extFields.concept])

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        title="AI 按打板战法(情绪周期/龙头/二进三/反包)复盘当日连板梯队, 输出候选清单; 弹窗内含「板块跷跷板」标签页"
        className="inline-flex items-center gap-1 h-7 px-2.5 rounded-full text-xs font-medium text-amber-400 border border-amber-400/25 bg-amber-400/5 hover:bg-amber-400/15 transition-colors cursor-pointer"
      >
        <Sparkles className="h-3.5 w-3.5" />
        AI 打板复盘
      </button>
      {open && (
        <LadderAiDialog payload={payload} loadingLadder={isLoading} onClose={() => setOpen(false)} />
      )}
    </>
  )
}

// ===== AI 打板复盘弹窗 =====
// 行为约定(用户明确要求): 打开 = 查看(默认展示最近一份存档, 没有就显示空态);
// 生成 = 只在用户点「生成清单/重新生成」时才调 AI —— 打开/刷新绝不自动触发, 不重复计费。
function LadderAiDialog({ payload, loadingLadder, onClose }: {
  payload: AiPayload
  loadingLadder: boolean
  onClose: () => void
}) {
  const [chat, setChat] = useState<{ role: 'user' | 'assistant'; content: string }[]>([])
  const [question, setQuestion] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [reportId, setReportId] = useState<string | null>(null)
  const autoLoadedRef = useRef(false)

  // 历史存档列表(后端 ladder_ai_reports.json, 保留 30 份)
  const historyQ = useQuery({ queryKey: QK.ladderAiReports, queryFn: () => api.ladderAiReports() })
  const reports = historyQ.data?.reports ?? []

  // 打开时: 只"查看"—— 自动载入最近一份存档(优先今天的), 不触发生成
  useEffect(() => {
    if (autoLoadedRef.current || reports.length === 0 || chat.length > 0) return
    autoLoadedRef.current = true
    const todays = reports.find(r => r.date === payload.date)
    const r = todays ?? reports[0]
    setReportId(r.id)
    setChat([{ role: 'assistant', content: r.text }])
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reports])

  const generate = () => {
    if (loading) return
    setLoading(true)
    setError('')
    setChat([])
    setReportId(null)
    api.ladderAiReview(payload)
      .then(res => {
        setChat([{ role: 'assistant', content: res.text }])
        setReportId(res.report_id)
        historyQ.refetch()
      })
      .catch(e => setError(String((e as Error)?.message || 'AI 生成失败')))
      .finally(() => setLoading(false))
  }

  const loadReport = (id: string) => {
    const r = reports.find(x => x.id === id)
    if (!r) return
    setReportId(r.id)
    setChat([{ role: 'assistant', content: r.text }])
    setError('')
  }

  const ask = async () => {
    const q = question.trim()
    if (!q || loading || chat.length === 0) return
    setQuestion('')
    const next = [...chat, { role: 'user' as const, content: q }]
    setChat(next)
    setLoading(true)
    try {
      // 追问: 传 report_id, 后端复用该报告存档的快照, 保证问的是"那份清单当时的盘面"
      const res = await api.ladderAiReview(payload, next, reportId ?? undefined)
      setChat([...next, { role: 'assistant', content: res.text }])
    } catch (e) {
      setError(String((e as Error)?.message || 'AI 追问失败'))
    } finally {
      setLoading(false)
    }
  }

  const removeReport = async (id: string) => {
    try {
      await api.ladderAiDeleteReport(id)
      historyQ.refetch()
      if (reportId === id) { setChat([]); setReportId(null) }
    } catch { /* 静默 */ }
  }

  // [R108b] 弹窗内标签: 打板复盘 / 板块跷跷板 —— 用户定案两件事共用这一个弹窗
  const [tab, setTab] = useState<'ladder' | 'seesaw'>('ladder')
  const [seesawKind, setSeesawKind] = useState<'concept' | 'industry'>('concept')

  const viewingReport = reports.find(r => r.id === reportId)
  // 梯队还没到就不能生成 —— 拿一份空快照去调 AI 会得到一份煞有介事的空报告
  const ladderReady = payload.tiers.length > 0

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/55 p-4 backdrop-blur-sm" onClick={onClose}>
      <div role="dialog" aria-modal="true" className="flex max-h-[84vh] w-full max-w-2xl flex-col overflow-hidden rounded-lg border border-border bg-surface shadow-2xl" onClick={e => e.stopPropagation()}>
        <header className="flex items-center gap-2.5 border-b border-border/60 px-5 py-3.5">
          <span className="grid h-8 w-8 shrink-0 place-items-center rounded-md border border-amber-400/25 bg-amber-400/10 text-amber-400">
            <Sparkles className="h-4 w-4" />
          </span>
          <div className="flex-1 min-w-0">
            <h2 className="text-sm font-medium text-foreground">
              {tab === 'ladder'
                ? <>AI 打板复盘 · {viewingReport ? `${viewingReport.date} 存档` : (payload.date || '—')}</>
                : '板块跷跷板'}
            </h2>
            <p className="text-[11px] text-muted truncate">
              {tab === 'ladder'
                ? '打开即查看存档 · 生成需手动点击 · 带置信度 —— 高风险, 仅为复盘参考'
                : '来自「市场环境」页主线强度数据 · 识别资金在两个板块间来回切换 —— 一边熄火往往是另一边点火'}
            </p>
          </div>
          <div className="flex items-center rounded-btn border border-border bg-base/60 p-0.5">
            {([['ladder', '打板复盘'], ['seesaw', '跷跷板']] as const).map(([k, label]) => (
              <button key={k} onClick={() => setTab(k)}
                className={k === tab
                  ? 'h-6 rounded-[5px] bg-amber-400/15 px-2.5 text-[11px] font-medium text-amber-300'
                  : 'h-6 rounded-[5px] px-2.5 text-[11px] font-medium text-muted hover:text-secondary transition-colors'}>
                {label}
              </button>
            ))}
          </div>
          {tab === 'seesaw' && (
            <div className="flex items-center rounded-btn border border-border bg-base/60 p-0.5">
              {([['concept', '概念'], ['industry', '行业']] as const).map(([k, label]) => (
                <button key={k} onClick={() => setSeesawKind(k)}
                  className={k === seesawKind
                    ? 'h-6 rounded-[5px] bg-accent/15 px-2.5 text-[11px] font-medium text-accent'
                    : 'h-6 rounded-[5px] px-2.5 text-[11px] font-medium text-muted hover:text-secondary transition-colors'}>
                  {label}
                </button>
              ))}
            </div>
          )}
          {/* 历史存档: 选择回看, 可续问 */}
          {tab === 'ladder' && reports.length > 0 && (
            <select
              value={reportId ?? ''}
              onChange={e => e.target.value && loadReport(e.target.value)}
              disabled={loading}
              title="回看历史打板复盘(选中后可继续追问当时的盘面)"
              className="h-7 max-w-[150px] rounded border border-border bg-base px-1.5 text-[11px] text-foreground focus:outline-none focus:border-amber-400/50 disabled:opacity-50 cursor-pointer"
            >
              <option value="" disabled>历史 ({reports.length})</option>
              {reports.map(r => (
                <option key={r.id} value={r.id}>{r.date} · {new Date(r.created_at).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}</option>
              ))}
            </select>
          )}
          {tab === 'ladder' && reportId && (
            <button onClick={() => removeReport(reportId)} disabled={loading} title="删除当前查看的这份存档"
              className="text-[11px] px-2 h-7 rounded border border-border bg-base text-muted hover:text-danger hover:border-danger/40 disabled:opacity-50 transition-colors cursor-pointer">
              删除
            </button>
          )}
          {/* 生成: 唯一会调 AI 的入口 */}
          {tab === 'ladder' && (
          <button onClick={generate} disabled={loading || loadingLadder || !ladderReady}
            title={ladderReady ? '对当日梯队生成新清单(调用 AI, 结果自动存档)' : '当日梯队数据还没就绪 —— 拿空快照生成只会得到一份空报告'}
            className="inline-flex items-center gap-1 text-[11px] px-2.5 h-7 rounded border border-amber-400/30 bg-amber-400/10 text-amber-300 hover:bg-amber-400/20 disabled:opacity-50 transition-colors cursor-pointer">
            {(loading && chat.length === 0) || loadingLadder ? <Loader2 className="h-3 w-3 animate-spin" /> : <Sparkles className="h-3 w-3" />}
            {chat.length > 0 || reports.some(r => r.date === payload.date) ? '重新生成' : '生成清单'}
          </button>
          )}
          <button onClick={onClose} className="text-muted hover:text-foreground transition-colors cursor-pointer"><X className="h-4 w-4" /></button>
        </header>
        {tab === 'seesaw' ? (
          <div className="flex-1 overflow-auto px-5 py-3">
            <SeesawPanel kind={seesawKind} embedded />
          </div>
        ) : (
        <>
        <div className="flex-1 overflow-auto p-5 space-y-2">
          {chat.length === 0 && !loading && (
            <div className="py-10 text-center text-xs text-muted">
              {reports.length === 0
                ? <>还没有任何打板复盘存档。<br /><span className="text-muted/60">点右上角「生成清单」对当日({payload.date || '最新交易日'})梯队生成第一份(会调用 AI)。</span></>
                : <>选择上方「历史」回看存档, 或点「重新生成」出一份新的。</>}
            </div>
          )}
          {chat.map((m, i) => (
            <div key={i} className={m.role === 'assistant'
              ? 'rounded-lg border border-border/60 bg-elevated/30 px-4 py-3 text-xs leading-relaxed text-secondary whitespace-pre-wrap'
              : 'rounded-lg border border-amber-400/25 bg-amber-400/[0.06] px-4 py-2 text-xs text-amber-200 ml-10'}>
              {m.content}
            </div>
          ))}
          {loading && (
            <div className="flex items-center gap-1.5 py-4 text-xs text-muted"><Loader2 className="h-3.5 w-3.5 animate-spin" />AI {chat.length === 0 ? '正在结合市场环境/主线排行按战法复盘…(生成中请勿关闭, 完成后自动存档)' : '思考中…'}</div>
          )}
          {error && <div className="text-xs text-danger">{error}</div>}
        </div>
        <div className="border-t border-border/60 p-3 flex items-center gap-2">
          <input
            value={question}
            onChange={e => setQuestion(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') ask() }}
            disabled={loading || chat.length === 0}
            placeholder="继续追问, 如: 二进三里哪只封单最扎实? 明天集合竞价该盯什么?"
            className="flex-1 h-8 rounded-lg border border-border bg-base px-3 text-xs text-foreground placeholder:text-muted/50 focus:outline-none focus:border-amber-400/50 disabled:opacity-50"
          />
          <button onClick={ask} disabled={loading || !question.trim() || chat.length === 0}
            className="inline-flex items-center gap-1 h-8 px-3 rounded-lg border border-amber-400/30 bg-amber-400/10 text-amber-300 text-xs hover:bg-amber-400/20 disabled:opacity-40 transition-colors cursor-pointer">
            <Send className="h-3 w-3" />
            追问
          </button>
        </div>
        </>
        )}
      </div>
    </div>
  )
}
