/**
 * [fork 增强] 今日总览 —— 决策汇聚层。
 *
 * 把六态趋势/AI 信号预案/持仓出场线/监控触发聚合成一屏, 版面顺序:
 * 市场状态(定基调) → 需要行动(持仓风险) → 持仓体检 → 值得关注(买什么)。
 *
 * [R179] 风险排在机会前面。改之前是「值得关注」在上、「需要行动」在下, 而机会区
 * 有 300 行 —— 一句「已跌破生命线, 按纪律无条件清仓」要往下滚过整张机会表才看得见。
 * 道理很直白: **错过一个机会损失的是机会, 错过一条止损损失的是钱。**
 * (这个优先级其实早就写在代码里了 —— 区块注释一直是「① 行动区」「② 机会区」,
 *  只是版面没兑现。)
 * 行动区与持仓体检仍然相邻 —— 两者都是持仓管理, 连着看不用来回滚, 所以是
 * 整块一起上移, 不是把行动区单独插到中间。
 * 没有另做顶部横幅: 那会把同样的内容说两遍, 而重排一分不多花。
 *
 * 数据全部来自既有模块,零新计算;AI 导读可选(手动点击,一次调用)。
 * 注意 AI 导读是**手动**生成的 —— 它虽然收到了行动区内容并被要求点名最需处理的
 * 1-2 件事, 但没点生成时它就是空的, 所以规则层的行动区必须自己站在显眼位置,
 * 不能指望 AI 那段话兜底。
 */
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import {
  AlertTriangle, BarChart3, CheckCircle2, Download, Loader2, RefreshCw,
  SlidersHorizontal, Sparkles, Sunrise, Target,
} from 'lucide-react'
import {
  api, TODAY_BOARDS, type SignalAiSchedule, type TodayAiSchedule,
  type TodayPick, type TodayPrefs,
} from '@/lib/api'
import { toast } from '@/components/Toast'
import { PageShell } from '@/components/PageShell'
import { ScoreLedgerDialog } from '@/components/ScoreLedgerDialog'
import { QK } from '@/lib/queryKeys'
import { cn } from '@/lib/cn'
// [R167] 以下五块从本文件拆出 —— 拆前 1922 行, 一个文件装下了导出、表格、面板、
// 弹窗和页面本体。缝按"对外暴露什么"划: 每个模块只导出 1~2 个组件, 其余是内部实现。
import { buildTodayHtml } from '@/lib/todayHtmlExport'
import { VerdictTag } from '@/components/today/VerdictTag'
import { LotBadge } from '@/components/today/LotBadge'   // [R169] 批次派生成本 / 到期提醒小标
import { OpportunityTable, GateFunnel } from '@/components/today/OpportunityTable'
import { AiPickPanel } from '@/components/today/AiPickPanel'
import { MarketStatusCard } from '@/components/today/MarketStatusCard'
import { AiAskDialog } from '@/components/today/AiAskDialog'

// [R179] 行动区四档配色。fatal 是"无条件清仓"那一档 —— 用最重的红并让整行的
// 标的名也跟着变红, 它必须一眼从其余项里跳出来; low 是已发生过的监控记录,
// 整行压暗, 因为它不是此刻要处理的事。
const ACTION_DOT: Record<string, string> = {
  fatal: 'bg-red-500 ring-2 ring-red-500/30',
  high: 'bg-red-400',
  mid: 'bg-amber-300',
  low: 'bg-muted/50',
}


// [R218] 「参与打分的因子」勾选面板(R204)在这里删掉了。用户: 「不搞自选了」。
//
// R204 加它是为了对付「因子越多挤得越狠」—— 少平均几个, 带宽就回来了。
// 那个道理本身没错(实测 10 因子 p10~p90 = 23 分, 8 因子 = 26 分), 但用户
// 不要这个旋钮。**带宽的出路仍然在名次与分位** —— R201 早就改成那样了,
// 绝对分本来就不适合当筛选旋钮。
//
// 一起删干净的还有: today_prefs 的 factors 字段、today.factor_catalog()、
// score_opportunities 的 factors 形参、opportunity_score 的 enabled_weights /
// MIN_ENABLED / score_candidate(enabled=)。**留一半是最糟的选择** ——
// 这一轮已经在四处「没人调的代码看起来像在用」上栽过跟头(_conflicts 规则②、
// PH_LAUNCHING、lib/button.ts、_VERDICT_SCORE)。
//
// 想要回来: git revert 这次提交, 上面每一处都是整块加的。


export function Today() {
  const qc = useQueryClient()
  const navigate = useNavigate()
  const q = useQuery({
    queryKey: QK.todayOverview,
    queryFn: () => api.todayOverview(),
    staleTime: 60_000,
    // [R27] 每小时自动刷新一次: 盘后数据落盘/定时 AI 跑完后不必手点
    refetchInterval: 60 * 60 * 1000,
    refetchOnWindowFocus: true,
  })
  // AI 导读+优选合一: 一次调用同时产出导读正文与量价优选结果。
  // [R27] 结果已落盘, 页面进来先显示缓存(state 为 null 时回落到 q.data.ai),
  // 刷新/次日进来不再空白, 定时任务的产出也能直接看到。
  const [brief, setBrief] = useState<string | null>(null)
  const [picks, setPicks] = useState<TodayPick[] | null>(null)
  const [analyzed, setAnalyzed] = useState(0)
  // 失败必须在页面上留痕(toast 一闪即逝, 用户会以为"点了没反应")
  const [aiError, setAiError] = useState<string | null>(null)
  const aiMut = useMutation({
    mutationFn: (note?: string) => api.todayAi(note),
    onMutate: () => setAiError(null),
    onSuccess: (r) => {
      if (r.error) { setAiError(r.error); toast(r.error, 'error'); return }
      setBrief(r.brief || null)
      setPicks(r.picks ?? [])
      setAnalyzed(r.analyzed ?? 0)
      // [R121] 刚落了一条台账 → 命中率重取(样本数会变)
      qc.invalidateQueries({ queryKey: QK.todayAiTrackRecord })
      const v = r.verify
      if (v?.rejected) toast(`AI 优选有 ${v.rejected} 条数字对不上日K, 已驳回`, 'error')
      else if (v?.doubtful) toast(`AI 优选有 ${v.doubtful} 条存疑, 已标出`, 'error')
    },
    onError: (e: Error) => {
      setAiError(`AI 分析失败: ${e.message}`)
      toast(`AI 分析失败: ${e.message}`, 'error')
    },
  })
  // [R27] AI 定时配置(门槛面板内)
  const todayAiSched = useQuery({
    queryKey: QK.todayAiSchedule,
    queryFn: () => api.todayAiScheduleGet(),
    staleTime: 5 * 60_000,
  })
  const signalAiSched = useQuery({
    queryKey: QK.signalAiSchedule,
    queryFn: () => api.signalAiScheduleGet(),
    staleTime: 5 * 60_000,
  })
  const todayAiSchedMut = useMutation({
    mutationFn: (body: TodayAiSchedule) => api.todayAiScheduleSet(body),
    onSuccess: (r) => {
      todayAiSched.refetch()
      toast(r.enabled
        ? `定时导读·优选已开启:工作日 ${String(r.hour).padStart(2, '0')}:${String(r.minute).padStart(2, '0')}`
        : '定时导读·优选已关闭', 'success')
    },
    onError: (e: Error) => toast(e.message, 'error'),
  })
  const signalAiSchedMut = useMutation({
    mutationFn: (body: SignalAiSchedule) => api.signalAiScheduleSet(body),
    onSuccess: (r) => {
      signalAiSched.refetch()
      toast(r.enabled
        ? `定时个股信号已开启:工作日 ${String(r.hour).padStart(2, '0')}:${String(r.minute).padStart(2, '0')} · ${r.scope === 'held' ? '只跑持有' : '全部自选'} · 间隔 ${r.gap_seconds}秒`
        : '定时个股信号已关闭', 'success')
    },
    onError: (e: Error) => toast(e.message, 'error'),
  })

  const [prefsOpen, setPrefsOpen] = useState(false)
  const [ledgerOpen, setLedgerOpen] = useState(false)   // [R133] 把握分体检弹窗
  // [R147] AI 分析前的补充说明弹窗。lastNote 只为"重试"沿用上一次问的话
  const [askOpen, setAskOpen] = useState(false)
  const [lastNote, setLastNote] = useState('')
  // 滑块拖动中的即时值(null = 用服务端返回的偏好); 松手才落库
  const [minPct, setMinPct] = useState<number | null>(null)
  // [R140] 板块过滤的**乐观值**。null = 用服务端偏好。
  //
  // 原来按钮亮不亮完全取决于 `d.prefs.boards`, 而那要等一次 PUT + 一次 GET
  // 回来才更新 —— 中间那段时间按钮纹丝不动, 看起来就是"点了没反应", 于是
  // 用户会再点一次(第二次读到的还是旧的 boardFilter, 于是又发了一遍同样的
  // 请求, 屏幕上叠出两个一样的 toast)。先本地亮起来, 服务端回来再对齐。
  const [boardDraft, setBoardDraft] = useState<string[] | null>(null)
  const prefsMut = useMutation({
    mutationFn: (body: Partial<TodayPrefs>) => api.todaySavePrefs(body),
    onSuccess: async (p, vars) => {
      toast(
        'boards' in vars
          ? (p.boards.length ? `只看:${p.boards.join('、')}` : '板块过滤已取消,全部板块都看')
          : `门槛已保存:只看历史前 ${100 - p.min_hist_pct}%,最多 ${p.max_show} 条`,
        'success')
      setMinPct(null)
      setPicks(null)  // 候选集变了, 旧的 AI 优选结果不再对应
      // 等这次重取真的落地再撤掉乐观值 —— 提前撤会让按钮闪回旧状态
      await q.refetch()
      setBoardDraft(null)
    },
    onError: (e: Error) => {
      toast(`保存失败: ${e.message}`, 'error')
      setMinPct(null)
      setBoardDraft(null)   // 存失败就退回服务端的真实值, 不留一个假的高亮
    },
  })

  // [R19] 确定性刷新: 先全量拉一遍自选实时(轮转覆盖到每一只), 再刷新总览
  const refreshMut = useMutation({
    mutationFn: async () => {
      let live: Awaited<ReturnType<typeof api.intradayRefreshFull>> | null = null
      try {
        live = await api.intradayRefreshFull()
      } catch { /* 实时服务不可用(未开实时/未配 key)→ 只刷收盘数据 */ }
      await q.refetch()
      return live
    },
    onSuccess: (live) => {
      if (live?.live_count) {
        toast(
          live.full_coverage === false
            ? `实时已拉取 ${live.live_count} 只(额度有限未全覆盖,其余轮转中)`
            : `实时已全量同步 ${live.live_count} 只`,
          'success',
        )
      }
    },
  })

  const goStock = (symbol: string, name: string) =>
    navigate(`/stock-analysis?symbol=${encodeURIComponent(symbol)}&name=${encodeURIComponent(name)}`)

  const d = q.data
  // 本次会话生成过就用 state, 否则用服务端缓存(手动/定时生成的都在里面)
  const aiCache = d?.ai ?? null
  const shownBrief = brief ?? aiCache?.brief ?? null
  const shownPicks = picks ?? aiCache?.picks ?? null
  // [R40] 板块过滤当前值。空 = 全看; 由服务端偏好驱动, 刷新/换设备都保持。
  // [R140] 落库期间用乐观值, 否则按钮要等一次往返才亮 —— 看起来像点了没反应。
  const boardFilter = boardDraft ?? d?.prefs?.boards ?? []
  /** 切换某个板块(传 null = 全部)。本地先切, 再落库。 */
  const toggleBoard = (b: string | null) => {
    const next = b === null ? []
      : boardFilter.includes(b) ? boardFilter.filter(x => x !== b) : [...boardFilter, b]
    setBoardDraft(next)
    prefsMut.mutate({ boards: next })
  }
  const shownAnalyzed = picks ? analyzed : (aiCache?.analyzed ?? 0)
  // 本次会话问过就用本次的, 否则用缓存里存的那句
  const shownNote = (picks ? lastNote : (aiCache?.note ?? '')) || ''
  const aiMeta = brief ? null : aiCache   // 缓存来源与时间(自己刚生成的不必标注)
  // [R37] 中观快照。提出来是为了在 JSX 的 map 回调里也保住类型收窄
  const meso = d?.meso ?? null
  const mainline = meso?.mainline ?? null

  // [R60] 页头交给 PageShell —— 这一页原来手搓了一个 h1 + 自己的 1500px 限宽,
  // 于是它和别的页在同一块屏幕上的边界、留白、标题字号都对不上。
  const asOfLine = d?.as_of ? (
    <>
      数据截至 {d.as_of} · 自选 {d.watchlist_total} 只(其中 {d.trend_total} 只有趋势判定)
      {d.live ? (
        <span
          className="ml-1.5 text-emerald-400"
          title={`实时叠加层已覆盖 ${d.live_count} 只自选;六态/距离为盘中临时口径,纪律判定(生命线/出场线触发)仍以收盘为准`}
        >
          ● 实时中({d.live_count} 只)
        </span>
      ) : (
        <span className="ml-1.5 text-amber-300/80" title="当前为上一交易日收盘数据">
          收盘口径 —— 打开左下角「实时行情」开关后,盘中这里就是实时数据
        </span>
      )}
    </>
  ) : undefined

  return (
    <PageShell
      title="今日总览"
      titleExtra={<Sunrise className="h-4 w-4 text-amber-300" />}
      subtitle={asOfLine}
      right={(
        <div className="flex items-center gap-2">
          <button
            onClick={() => {
              if (!d) return
              const html = buildTodayHtml(d, shownBrief, shownPicks)
              const blob = new Blob([html], { type: 'text/html;charset=utf-8' })
              const url = URL.createObjectURL(blob)
              const a = document.createElement('a')
              a.href = url
              a.download = `今日总览_${(d.as_of ?? new Date().toISOString().slice(0, 10)).replace(/-/g, '')}.html`
              a.click()
              URL.revokeObjectURL(url)
            }}
            disabled={!d}
            title="导出为自包含 HTML 页面(可存档/分享;已生成 AI 导读会一并带上)"
            className="inline-flex items-center gap-1 rounded-btn border border-sky-400/30 bg-sky-400/10 px-2.5 py-1 text-[10px] text-sky-300 hover:bg-sky-400/20 disabled:opacity-50 transition-colors cursor-pointer"
          >
            <Download className="h-3 w-3" />
            导出 HTML
          </button>
          <button
            onClick={() => setAskOpen(true)}
            disabled={aiMut.isPending || !d}
            title="一次生成盘前导读, 并调取候选的日 K 与量能做横向对比选出 1-3 只(耗时约十几秒)。点开可以先写一句这次想让它重点看什么,不写直接开始也行"
            className="inline-flex items-center gap-1 rounded-btn border border-violet-400/30 bg-violet-400/10 px-2.5 py-1 text-[10px] text-violet-300 hover:bg-violet-400/20 disabled:opacity-50 transition-colors cursor-pointer"
          >
            {aiMut.isPending ? <Loader2 className="h-3 w-3 animate-spin" /> : <Sparkles className="h-3 w-3" />}
            AI 导读·优选
          </button>
          <button
            onClick={() => refreshMut.mutate()}
            disabled={refreshMut.isPending || q.isFetching}
            title="先把全部自选的实时行情立即拉一遍(轮转全覆盖),再刷新本页 —— 实时行情未开启时仅刷新收盘数据"
            className="inline-flex items-center gap-1 rounded-btn border border-border bg-base px-2.5 py-1 text-[10px] text-muted hover:text-foreground disabled:opacity-50 transition-colors cursor-pointer"
          >
            <RefreshCw className={`h-3 w-3 ${(refreshMut.isPending || q.isFetching) ? 'animate-spin' : ''}`} />
            {refreshMut.isPending ? '同步中…' : '刷新'}
          </button>
        </div>
      )}
    >
      {/* [R122] 时段提示条并入下方「市场天气」横幅 —— 三条通栏横幅(时段/天气/中观)
          在首屏堆掉近三分之一高度, 而时段只是一句"现在该怎么用这页"的说明,
          不值得独占一条。现在它是天气条右上角的一个徽章, 悬停看全文。 */}

      {aiError && (
        <div className="flex items-start justify-between gap-3 rounded-lg border border-red-400/30 bg-red-400/[0.07] px-4 py-3 text-xs text-red-300">
          <span>AI 导读·优选没有成功:{aiError}</span>
          <button
            onClick={() => aiMut.mutate(lastNote || undefined)}
            disabled={aiMut.isPending}
            title={lastNote ? `沿用上次的补充说明:${lastNote}` : undefined}
            className="shrink-0 rounded border border-red-400/40 px-2 py-0.5 text-[10px] hover:bg-red-400/10 disabled:opacity-50 cursor-pointer"
          >
            重试
          </button>
        </div>
      )}
      {/* [R142] 导读是**正文**, 按正文排版, 不按标签排版:
          · 行宽卡到 80ch —— 整屏宽(1600px+)的一行中文最难读, 眼睛回行会跑错行;
          · 字号 12→13px、行高 1.8 —— 这是唯一需要逐字读完的一段;
          · 正文用满对比度(原来 foreground/90 是把主角调暗), 生成来源退到标题行。*/}
      {shownBrief && (
        <div className="rounded-lg border border-violet-400/20 bg-violet-400/[0.06] px-4 py-3">
          <div className="mb-1 flex flex-wrap items-baseline gap-x-2">
            <span className="inline-flex items-center gap-1.5 text-[10px] font-medium text-violet-300">
              <Sparkles className="h-3.5 w-3.5" />
              AI 导读
            </span>
            {/* [R147] 当时问了什么必须跟着结论一起显示 —— 一句「今天只看半导体」
                产出的窄结论, 隔天不标出来就会被读成"今天全市场就这几只" */}
            {shownNote && (
              <span
                title="这次分析带了这句补充说明 —— 结论的范围与措辞受它影响"
                className="max-w-[40ch] truncate rounded bg-violet-400/15 px-1.5 py-0.5 text-[10px] text-violet-300"
              >
                问了:{shownNote}
              </span>
            )}
            {aiMeta && (
              <span
                className="whitespace-nowrap text-[10px] text-muted"
                title={`生成于 ${new Date(aiMeta.created_at).toLocaleString('zh-CN')}${aiMeta.as_of ? ` · 基于 ${aiMeta.as_of} 数据` : ''}`}
              >
                {aiMeta.source === 'scheduled' ? '定时生成' : '上次生成'}
                {aiMeta.as_of && aiMeta.as_of !== d?.as_of && (
                  <span className="text-amber-300"> · 数据已更新,建议重新生成</span>
                )}
              </span>
            )}
          </div>
          <p className="max-w-[80ch] text-[13px] leading-[1.8] text-foreground">{shownBrief}</p>
        </div>
      )}

      {q.isLoading && (
        <div className="flex items-center justify-center py-16"><Loader2 className="h-5 w-5 animate-spin text-muted" /></div>
      )}
      {q.isError && (
        <div className="rounded-lg border border-red-400/30 bg-red-400/10 px-4 py-3 text-xs text-red-400">
          总览加载失败:{(q.error as Error)?.message}
        </div>
      )}

      {d && (
        <>
          {/* [R142] 市场状态 —— 原「市场天气」+「中观」合并。见组件上方注释 */}
          <MarketStatusCard d={d} meso={meso} mainline={mainline} />

          {/* ① 行动区 */}
          <section className="rounded-lg border border-border/60 bg-surface/40 overflow-hidden">
            <div className="flex items-center gap-2 border-b border-border/40 px-4 py-2.5">
              <AlertTriangle className="h-4 w-4 text-red-400" />
              <span className="text-sm font-medium text-foreground">需要行动</span>
              <span className="text-[10px] text-muted">{d.actions.length} 项</span>
              <span
                title={d.live
                  ? '距离/价格按盘中最新价计算;"已跌破→清仓"的纪律判定仍以收盘为准'
                  : `所有距离/价格为 ${d.as_of ?? '上一交易日'} 收盘快照 —— 盘中已变化的不会反映,打开左下角「实时行情」后自动实时`}
                className={`rounded border px-1.5 py-0.5 text-[9px] ${d.live ? 'border-emerald-400/30 bg-emerald-400/10 text-emerald-400' : 'border-amber-400/30 bg-amber-400/10 text-amber-300'}`}
              >
                {d.live ? '分数收盘口径 · 盘中列实时' : `昨收快照 ${d.as_of ?? ''}`}
              </span>
            </div>
            {d.actions.length === 0 ? (
              <div className="flex items-center gap-2 px-4 py-5 text-xs text-muted">
                <CheckCircle2 className="h-4 w-4 text-emerald-400" />
                今日无需操作 —— 这本身就是有价值的信息,管住手
              </div>
            ) : (
              <ul className="grid lg:grid-cols-2 -mb-px">
                {d.actions.map((a, i) => (
                  <li key={i} className="border-b border-border/30 lg:odd:border-r">
                    <button
                      onClick={() => a.symbol && goStock(a.symbol, a.name)}
                      className="flex w-full items-start gap-2.5 px-4 py-2.5 text-left hover:bg-elevated/40 transition-colors cursor-pointer"
                    >
                      <span className={`mt-0.5 h-1.5 w-1.5 shrink-0 rounded-full ${ACTION_DOT[a.severity] ?? 'bg-amber-300'}`} />
                      <span className={`text-xs leading-relaxed ${a.severity === 'low' ? 'opacity-70' : ''}`}>
                        <span className={`font-medium ${a.severity === 'fatal' ? 'text-red-400' : 'text-foreground'}`}>{a.name}</span>
                        {a.symbol && a.symbol !== a.name && <span className="ml-1.5 text-[9px] font-mono text-muted">{a.symbol}</span>}
                        <span className="ml-2 text-foreground/80">{a.text}</span>
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </section>

          {/* ④ 持仓体检 */}
          <section className="rounded-lg border border-border/60 bg-surface/40 overflow-hidden">
            <div className="flex flex-wrap items-center gap-2 border-b border-border/40 px-4 py-2.5">
              <span className="text-sm font-medium text-foreground">持仓体检</span>
              <span className="text-[10px] text-muted">{d.holdings.length} 只(已触发/最接近出场线的排前面)</span>
              {d.portfolio && (
                <span className={`ml-auto text-[10px] ${d.portfolio.triggered > 0 ? 'text-red-400' : 'text-muted'}`}>
                  组合:平均浮盈{' '}
                  <span className={d.portfolio.avg_pnl == null ? '' : d.portfolio.avg_pnl > 0 ? 'text-red-400' : 'text-emerald-400'}>
                    {d.portfolio.avg_pnl != null ? `${(d.portfolio.avg_pnl * 100).toFixed(1)}%` : '—'}
                  </span>
                  {' '}· 已触发出场 {d.portfolio.triggered} · 逼近出场线 {d.portfolio.near_exit} · 空头趋势 {d.portfolio.bearish}
                  {d.portfolio.total_weight != null && (
                    <span title="由各持仓「仓位%」汇总;超过姿态基调或回撤超纪律线会进「需要行动」">
                      {' '}· 总仓位 {(d.portfolio.total_weight / 10).toFixed(1)}成
                      {d.portfolio.posture_cap != null && `(基调≤${d.portfolio.posture_cap * 10}成)`}
                      {d.portfolio.drawdown != null && ` · 距净值高点 -${(d.portfolio.drawdown * 100).toFixed(1)}%`}
                    </span>
                  )}
                </span>
              )}
            </div>
            {d.holdings.length === 0 ? (
              <div className="px-4 py-5 text-xs text-muted">
                暂无持仓标记 —— 在个股分析页决策台把持有的票标「持有」并填成本,这里就会出现仓位全景
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[720px] text-xs">
                  <thead className="text-[10px] text-muted">
                    <tr className="text-left">
                      <th className="px-4 py-1.5 font-normal">标的</th>
                      <th className="px-2 py-1.5 font-normal text-right">现价</th>
                      <th className="px-2 py-1.5 font-normal text-right">仓位</th>
                      <th className="px-2 py-1.5 font-normal text-right">浮盈</th>
                      <th className="px-2 py-1.5 font-normal text-right">出场线</th>
                      <th className="px-2 py-1.5 font-normal text-center">阶段</th>
                      <th className="px-2 py-1.5 font-normal text-center">趋势</th>
                      <th className="px-2 py-1.5 font-normal text-center">AI 信号</th>
                      <th className="px-4 py-1.5 font-normal text-center">操作建议</th>
                    </tr>
                  </thead>
                  <tbody>
                    {d.holdings.map((h) => (
                      <tr
                        key={h.symbol}
                        onClick={() => goStock(h.symbol, h.name)}
                        className="border-t border-border/30 hover:bg-elevated/40 cursor-pointer"
                      >
                        <td className="px-4 py-1.5">
                          <span className="font-medium text-foreground">{h.name}</span>
                          {h.symbol !== h.name && <span className="ml-1.5 text-[9px] font-mono text-muted">{h.symbol}</span>}
                          <VerdictTag v={h.heat?.verdict} holding />
                          <LotBadge h={h} />
                        </td>
                        <td className="px-2 py-1.5 text-right font-mono">{h.close?.toFixed(2) ?? '—'}</td>
                        {/* [R215] 决策台的「仓%」输入框撤了(用户: 「不需要仓位比例」),
                            所以这里不能再让人去那儿填。以前填过的照常显示。 */}
                        <td className="px-2 py-1.5 text-right font-mono text-muted"
                            title="仓位比例(占总资金 %)。已经不再提供填写入口, 这里显示的是以前填过的值">
                          {h.weight != null ? `${h.weight}%` : '—'}
                        </td>
                        <td className={`px-2 py-1.5 text-right font-mono ${h.pnl_pct == null ? 'text-muted' : h.pnl_pct > 0 ? 'text-red-400' : h.pnl_pct < 0 ? 'text-emerald-400' : 'text-muted'}`}>
                          {h.pnl_pct != null ? `${(h.pnl_pct * 100).toFixed(1)}%` : '—'}
                        </td>
                        <td className={`px-2 py-1.5 text-right font-mono ${h.exit_triggered ? 'text-red-400' : (h.distance_pct ?? -1) > -0.03 ? 'text-amber-300' : 'text-muted'}`}>
                          {h.line != null ? `${h.line.toFixed(2)}${h.exit_triggered ? ' 已触发' : h.distance_pct != null ? ` · 距${(Math.abs(h.distance_pct) * 100).toFixed(1)}%` : ''}` : '—'}
                        </td>
                        <td className="px-2 py-1.5 text-center text-[10px] text-muted">{h.stage_cn ?? '—'}</td>
                        <td className="px-2 py-1.5 text-center text-[10px]">
                          {h.trend_cn ? (
                            <span className={h.trend_side === '多头' ? 'text-red-400' : 'text-emerald-400'}>
                              {h.trend_cn} 已{h.trend_duration}天{h.trend_duration_capped ? '以上' : ''}
                            </span>
                          ) : '—'}
                        </td>
                        <td className="px-2 py-1.5 text-center text-[10px] text-muted">{h.signal ?? '—'}</td>
                        <td className="px-4 py-1.5 text-center text-[10px]" title={h.stance_why}>
                          <span className={
                            h.stance === '离场' ? 'font-semibold text-red-400'
                              : h.stance === '减仓' ? 'text-amber-300'
                                : h.stance === '加仓' ? 'text-red-300'
                                  : 'text-muted'
                          }>
                            {h.stance}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
          {/* ② 机会区(已按把握分筛选排序; AI 优选可再精选) */}
          <section className="rounded-lg border border-border/60 bg-surface/40 overflow-hidden">
            <div className="flex flex-wrap items-center gap-2 border-b border-border/40 px-4 py-2.5">
              <Target className="h-4 w-4 text-red-400" />
              <span className="text-sm font-medium text-foreground">值得关注</span>
              <span
                title={d.live
                  ? '把握分与三维度是收盘口径,盘中不变(决策基准);「盘中」列是实时价与变化,不进评分。带「盘中·待收盘确认」标的候选是盘中新冒出来的信号,收盘可能收回去'
                  : `所有价格与位置为 ${d.as_of ?? '上一交易日'} 收盘快照 —— 打开左下角「实时行情」后多出一列「盘中」`}
                className={`rounded border px-1.5 py-0.5 text-[9px] ${d.live ? 'border-emerald-400/30 bg-emerald-400/10 text-emerald-400' : 'border-amber-400/30 bg-amber-400/10 text-amber-300'}`}
              >
                {d.live ? '分数收盘口径 · 盘中列实时' : `昨收快照 ${d.as_of ?? ''}`}
              </span>
              <span className="text-[10px] text-muted">
                {d.opportunities.length} 项 ·{' '}
                <span title={'把握分 = √(质地 × 时机) × 置信,先过三道硬门槛才打分。\n'
                  + '质地(月计变化): 趋势模板 / 相对强度 / 六态状态\n'
                  + '时机(逐日变化): 新鲜度 / 通道位置 / 量比 / 换手率\n'
                  + '曲线全是区间最优(量比峰在 1.3~2.5、通道位置甜区 50%~65%),不是越大越好 —— 要的是有苗头,不是已经涨完的。\n'
                  + '量化波动通道那一组读数(阶段/事件/三线间距/快慢)**不进把握分**,只作背景。\n\n'
                  + '[R220] 门槛的单位是**历史分位**,不是绝对分。绝对分挤在中间一段'
                  + '(多因子平均出来的必然结果),拖到哪儿都差不多;分位天然均匀,每一格都有抓手,'
                  + '而且跨日可比 —— 熊市里「今天最好的也只排到历史第 20 百分位」这句话才说得出来。\n'
                  + '够格的不足 3 只时会保底摆出几只并标明「没到门槛」,页面不会空。'}>
                  {!d.hist_pct_ready
                    ? '门槛待命中(台账还没攒够)'
                    : d.prefs.min_hist_pct > 0
                      ? `只看历史前 ${100 - d.prefs.min_hist_pct}% 的`
                      : '未设门槛'}
                </span>
                {d.opportunities_filtered > 0 && `(${d.opportunities_filtered} 只没够上)`}
                {boardFilter.length > 0 && (
                  <span
                    className="text-sky-300"
                    title="板块过滤在服务端于截断前生效 —— 显示的是该板块内把握分最高的前几只, 不是从已截断的列表里再挑"
                  >
                    {' '}· 只看 {boardFilter.join('、')}
                  </span>
                )}
                {d.position_hint && (
                  <span title="由当前姿态决定的总仓位建议上限(进攻8成/谨慎5成/防守2成/观察3成)——所有持仓加起来别超过这个数">
                    {' '}· 总仓位基调 ≤{d.position_hint.posture_cap * 10}成
                  </span>
                )}
              </span>
              {/* [R40] 板块筛选。过滤在后端做 —— 前端筛的话会漏掉被 max_show 截掉的票,
                  看到的"主板机会"是残缺的而你不会知道 */}
              <div className="flex items-center gap-1">
                <button
                  onClick={() => toggleBoard(null)}
                  disabled={prefsMut.isPending}
                  title="不过滤, 所有板块都看"
                  className={`rounded-btn border px-2 py-0.5 text-[10px] transition-colors cursor-pointer disabled:opacity-50 ${
                    boardFilter.length === 0
                      ? 'border-sky-400/40 bg-sky-400/15 text-sky-300'
                      : 'border-border bg-base text-muted hover:text-foreground'
                  }`}
                >
                  全部
                </button>
                {/* [R140] 正在落库/重取时给个明确的进行态。/api/today 要跑
                    Keltner 批量、MA120 批量、几十只的历史胜率, 一次好几秒 ——
                    没有这个提示, 那几秒就是"点了没反应", 用户会重复点。 */}
                {TODAY_BOARDS.map((b) => {
                  const on = boardFilter.includes(b)
                  return (
                    <button
                      key={b}
                      onClick={() => toggleBoard(b)}
                      disabled={prefsMut.isPending}
                      title={`${on ? '取消' : '只看'}${b}(可多选)`}
                      className={`rounded-btn border px-2 py-0.5 text-[10px] transition-colors cursor-pointer disabled:opacity-50 ${
                        on
                          ? 'border-sky-400/40 bg-sky-400/15 text-sky-300'
                          : 'border-border bg-base text-muted hover:text-foreground'
                      }`}
                    >
                      {b}
                    </button>
                  )
                })}
                {(prefsMut.isPending || (boardDraft !== null && q.isFetching)) && (
                  <span className="inline-flex items-center gap-1 pl-1 text-[10px] text-muted">
                    <Loader2 className="h-3 w-3 animate-spin" />
                    筛选中
                  </span>
                )}
              </div>
              <div className="ml-auto flex items-center gap-2">
                {/* [R133] 门槛旁边就是体检 —— 调门槛前先看"这个门槛值不值",
                    两个按钮挨着放, 才不会出现凭感觉拧滑块的情况 */}
                <button
                  onClick={() => setLedgerOpen(true)}
                  title="把握分体检: 完整候选池的分层胜率/名次段/因子归因, 并可一键导出给外部做调参"
                  className="inline-flex items-center gap-1 rounded-btn border border-border bg-base px-2.5 py-1 text-[10px] text-muted transition-colors cursor-pointer hover:text-foreground"
                >
                  <BarChart3 className="h-3 w-3" />
                  体检
                </button>
                <button
                  onClick={() => setPrefsOpen((v) => !v)}
                  title="调整显示门槛(把握分下限与最多显示条数)"
                  className={`inline-flex items-center gap-1 rounded-btn border px-2.5 py-1 text-[10px] transition-colors cursor-pointer ${
                    prefsOpen ? 'border-sky-400/40 bg-sky-400/15 text-sky-300'
                      : 'border-border bg-base text-muted hover:text-foreground'
                  }`}
                >
                  <SlidersHorizontal className="h-3 w-3" />
                  门槛
                </button>
              </div>
            </div>
            {prefsOpen && (
              <div className="flex flex-wrap items-center gap-x-5 gap-y-3 border-b border-border/40 bg-base/40 px-4 py-3">
                {/* [R220] 门槛的单位从绝对把握分换成了历史分位。
                    绝对分那个旋钮几乎没有作用(实测 60 分只挡掉约 1.6% 的候选),
                    因为分数被"平均"挤在中间一段;分位天然均匀,拖到哪儿都真的在挡人。
                    台账没攒够时**禁用并说明**,而不是让人拖一个没反应的旋钮。 */}
                <label className={cn('flex items-center gap-2 text-[11px] text-muted',
                                     !d.hist_pct_ready && 'opacity-60')}>
                  <span className="whitespace-nowrap">入选门槛</span>
                  <input
                    type="range" min={0} max={90} step={5}
                    disabled={!d.hist_pct_ready}
                    value={minPct ?? d.prefs.min_hist_pct}
                    onChange={(e) => setMinPct(Number(e.target.value))}
                    onPointerUp={() => {
                      if (minPct != null && minPct !== d.prefs.min_hist_pct) prefsMut.mutate({ min_hist_pct: minPct })
                    }}
                    className="w-36 accent-sky-400 cursor-pointer disabled:cursor-not-allowed"
                  />
                  <span className="w-24 whitespace-nowrap font-mono text-foreground">
                    {(minPct ?? d.prefs.min_hist_pct) > 0
                      ? `历史前 ${100 - (minPct ?? d.prefs.min_hist_pct)}%`
                      : '不过滤'}
                  </span>
                  {!d.hist_pct_ready && (
                    <span className="text-[10px] text-amber-300/80"
                          title="分位要跟历史比才算得出来。台账攒够约一个月的记录(400 条)之后这个门槛自动开始起作用 —— 在那之前它谁也不挡, 而不是偷偷把页面挡空。">
                      台账还没攒够,暂不起作用
                    </span>
                  )}
                </label>
                <label className="flex items-center gap-2 text-[11px] text-muted">
                  <span className="whitespace-nowrap">最多显示</span>
                  <input
                    type="number" min={1} max={50}
                    defaultValue={d.prefs.max_show}
                    onBlur={(e) => {
                      const v = Number(e.target.value)
                      if (v && v !== d.prefs.max_show) prefsMut.mutate({ max_show: v })
                    }}
                    className="w-14 rounded border border-border bg-surface px-2 py-1 font-mono text-foreground outline-none focus:border-sky-400/50"
                  />
                  <span>条</span>
                </label>
                <label className="flex items-center gap-2 text-[11px] text-muted" title="单只票最多占总资金的比例;建议仓位 = 上限 × 把握分系数 × 波动率压缩">
                  <span className="whitespace-nowrap">单票上限</span>
                  <input
                    type="number" min={5} max={100} step={5}
                    defaultValue={d.prefs.max_single}
                    onBlur={(e) => {
                      const v = Number(e.target.value)
                      if (v && v !== d.prefs.max_single) prefsMut.mutate({ max_single: v })
                    }}
                    className="w-14 rounded border border-border bg-surface px-2 py-1 font-mono text-foreground outline-none focus:border-sky-400/50"
                  />
                  <span>%</span>
                </label>
                <label className="flex items-center gap-2 text-[11px] text-muted" title="能接受的单日波动;票的日波幅(ATR/价)超过它时按比例压低建议仓位,只压不加">
                  <span className="whitespace-nowrap">目标日波动</span>
                  <input
                    type="number" min={1} max={10}
                    defaultValue={d.prefs.target_vol}
                    onBlur={(e) => {
                      const v = Number(e.target.value)
                      if (v && v !== d.prefs.target_vol) prefsMut.mutate({ target_vol: v })
                    }}
                    className="w-14 rounded border border-border bg-surface px-2 py-1 font-mono text-foreground outline-none focus:border-sky-400/50"
                  />
                  <span>%</span>
                </label>
                <label className="flex items-center gap-2 text-[11px] text-muted" title="组合净值从高点回撤超过此值 → 需要行动区置顶'纪律性降仓'提醒(需在决策台填各持仓的仓位%)">
                  <span className="whitespace-nowrap">回撤纪律线</span>
                  <input
                    type="number" min={3} max={30}
                    defaultValue={d.prefs.max_drawdown}
                    onBlur={(e) => {
                      const v = Number(e.target.value)
                      if (v && v !== d.prefs.max_drawdown) prefsMut.mutate({ max_drawdown: v })
                    }}
                    className="w-14 rounded border border-border bg-surface px-2 py-1 font-mono text-foreground outline-none focus:border-sky-400/50"
                  />
                  <span>%</span>
                </label>
                <label className="flex items-center gap-2 text-[11px] text-muted" title="建仓路径第一步: 试仓占目标仓位的比例(买'对不对')">
                  <span className="whitespace-nowrap">试仓</span>
                  <input
                    type="number" min={10} max={60} step={5}
                    defaultValue={d.prefs.pyramid_probe}
                    onBlur={(e) => {
                      const v = Number(e.target.value)
                      if (v && v !== d.prefs.pyramid_probe) prefsMut.mutate({ pyramid_probe: v })
                    }}
                    className="w-14 rounded border border-border bg-surface px-2 py-1 font-mono text-foreground outline-none focus:border-sky-400/50"
                  />
                  <span>%</span>
                </label>
                <label className="flex items-center gap-2 text-[11px] text-muted" title="建仓路径第二步: 站稳关键点 N 日后加至目标仓位的比例(买'稳不稳'), 第三步回踩不破上满">
                  <span className="whitespace-nowrap">确认加至</span>
                  <input
                    type="number" min={40} max={90} step={5}
                    defaultValue={d.prefs.pyramid_confirm}
                    onBlur={(e) => {
                      const v = Number(e.target.value)
                      if (v && v !== d.prefs.pyramid_confirm) prefsMut.mutate({ pyramid_confirm: v })
                    }}
                    className="w-14 rounded border border-border bg-surface px-2 py-1 font-mono text-foreground outline-none focus:border-sky-400/50"
                  />
                  <span>%</span>
                </label>
                <label className="flex items-center gap-2 text-[11px] text-muted" title="'站稳'的定义: 收盘连续 N 日守住关键点才执行加仓">
                  <span className="whitespace-nowrap">站稳</span>
                  <input
                    type="number" min={1} max={5}
                    defaultValue={d.prefs.pyramid_days}
                    onBlur={(e) => {
                      const v = Number(e.target.value)
                      if (v && v !== d.prefs.pyramid_days) prefsMut.mutate({ pyramid_days: v })
                    }}
                    className="w-14 rounded border border-border bg-surface px-2 py-1 font-mono text-foreground outline-none focus:border-sky-400/50"
                  />
                  <span>日</span>
                </label>
                <span className="text-[10px] text-muted/70">
                  把握分调高更严格;单票上限与目标日波动决定「建议仓位」;试仓/确认加至/站稳决定「建仓路径」。卖出提醒不受任何门槛影响。
                </span>
                {/* [R27] AI 定时自动运行 */}
                <div className="flex w-full flex-wrap items-center gap-x-5 gap-y-2 border-t border-border/40 pt-3">
                  <label className="flex items-center gap-2 text-[11px] text-muted" title="工作日到点自动生成导读·优选并存下来, 次日进页面直接看结果">
                    <input
                      type="checkbox"
                      checked={todayAiSched.data?.enabled ?? false}
                      onChange={(e) => todayAiSchedMut.mutate({
                        enabled: e.target.checked,
                        hour: todayAiSched.data?.hour ?? 18,
                        minute: todayAiSched.data?.minute ?? 30,
                      })}
                      className="h-3.5 w-3.5 accent-violet-500"
                    />
                    <span className="whitespace-nowrap">定时导读·优选</span>
                    <input
                      type="time"
                      value={`${String(todayAiSched.data?.hour ?? 18).padStart(2, '0')}:${String(todayAiSched.data?.minute ?? 30).padStart(2, '0')}`}
                      onChange={(e) => {
                        const [h, m] = e.target.value.split(':').map(Number)
                        if (!Number.isNaN(h)) todayAiSchedMut.mutate({
                          enabled: todayAiSched.data?.enabled ?? false, hour: h, minute: m,
                        })
                      }}
                      className="rounded border border-border bg-surface px-1.5 py-0.5 font-mono text-foreground outline-none focus:border-violet-400/50"
                    />
                  </label>
                  <label className="flex items-center gap-2 text-[11px] text-muted" title="工作日到点批量刷新个股 AI 信号; 每只之间留间隔, 不会打满接口">
                    <input
                      type="checkbox"
                      checked={signalAiSched.data?.enabled ?? false}
                      onChange={(e) => signalAiSchedMut.mutate({
                        ...(signalAiSched.data ?? { hour: 19, minute: 0, scope: 'held' as const, gap_seconds: 20 }),
                        enabled: e.target.checked,
                      })}
                      className="h-3.5 w-3.5 accent-violet-500"
                    />
                    <span className="whitespace-nowrap">定时个股信号</span>
                    <input
                      type="time"
                      value={`${String(signalAiSched.data?.hour ?? 19).padStart(2, '0')}:${String(signalAiSched.data?.minute ?? 0).padStart(2, '0')}`}
                      onChange={(e) => {
                        const [h, m] = e.target.value.split(':').map(Number)
                        if (!Number.isNaN(h) && signalAiSched.data) {
                          signalAiSchedMut.mutate({ ...signalAiSched.data, hour: h, minute: m })
                        }
                      }}
                      className="rounded border border-border bg-surface px-1.5 py-0.5 font-mono text-foreground outline-none focus:border-violet-400/50"
                    />
                    <select
                      value={signalAiSched.data?.scope ?? 'held'}
                      onChange={(e) => signalAiSched.data && signalAiSchedMut.mutate({
                        ...signalAiSched.data, scope: e.target.value as 'held' | 'watchlist',
                      })}
                      className="rounded border border-border bg-surface px-1.5 py-0.5 text-foreground outline-none focus:border-violet-400/50"
                    >
                      <option value="held">只跑持有</option>
                      <option value="watchlist">全部自选</option>
                    </select>
                    <span className="whitespace-nowrap">间隔</span>
                    <input
                      type="number" min={5} max={300}
                      value={signalAiSched.data?.gap_seconds ?? 20}
                      onChange={(e) => signalAiSched.data && signalAiSchedMut.mutate({
                        ...signalAiSched.data, gap_seconds: Number(e.target.value) || 20,
                      })}
                      className="w-14 rounded border border-border bg-surface px-1.5 py-0.5 font-mono text-foreground outline-none focus:border-violet-400/50"
                    />
                    <span>秒/只</span>
                  </label>
                  <span className="text-[10px] text-muted/70">
                    建议放在盘后日线落盘之后(17:30~20:00);个股多时用「只跑持有」更省
                  </span>
                </div>
                {prefsMut.isPending && <Loader2 className="h-3 w-3 animate-spin text-muted" />}
              </div>
            )}
            {shownPicks && (
              <AiPickPanel
                picks={shownPicks}
                analyzed={shownAnalyzed}
                opportunities={d.opportunities}
                onOpen={goStock}
              />
            )}
            <GateFunnel gates={d.gates} />
            {d.opportunities.length === 0 ? (
              /* [R210] 空页必须自己说清是空在哪一步。候选池空 / 门槛全挡 /
                 板块过滤滤没了, 对用户是完全不同的三件事 —— 最后那种一键就能撤,
                 原来却和前两种共用一句「今日没有把握足够的买入机会」。 */
              <div className="space-y-2 px-4 py-5 text-xs leading-relaxed text-muted">
                <p>{d.opportunities_empty_why ?? '今天没有一只票走到可以看的位置 —— 等待比出手更常见。'}</p>
                {boardFilter.length > 0 && (
                  <button
                    onClick={() => toggleBoard(null)}
                    className="rounded-btn border border-accent/40 px-2 py-1 text-[11px] text-accent transition-colors hover:bg-accent/10"
                  >
                    去掉板块过滤,看全部
                  </button>
                )}
              </div>
            ) : (
              <OpportunityTable
                live={d.live}
                rows={d.opportunities}
                pickedSymbols={new Set((shownPicks ?? []).filter(p => p.verdict !== '驳回').map(p => p.symbol))}
                onOpen={goStock}
              />
            )}
          </section>

        </>
      )}
      {ledgerOpen && <ScoreLedgerDialog onClose={() => setLedgerOpen(false)} />}
      {askOpen && (
        <AiAskDialog
          initial={lastNote}
          pending={aiMut.isPending}
          onClose={() => setAskOpen(false)}
          onStart={(note) => { setLastNote(note); setAskOpen(false); aiMut.mutate(note || undefined) }}
        />
      )}
    </PageShell>
  )
}
