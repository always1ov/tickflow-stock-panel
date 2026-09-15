/**
 * [fork 增强] 今日总览 —— 决策汇聚层。
 *
 * 版面顺序: 市场状态(定基调) → 值得关注(买什么)。
 *
 * [R340] **「需要行动」与「持仓体检」整块删掉**(用户: 「今日总览里面, 我截图的
 * 这部分都可以删除了」)。这两块是 R7/R8 那一套 ATR 出场线纪律的门面 ——
 * 生命线(20 日线)跌破就清仓、三阶段止损/保本/移动止盈。它们没坏, 但**与这套
 * 系统现在走的路是两条**: R327 起模拟盘只认六态转折, R329 那条铁律是「一定要
 * 根据转折才能出手」, R338 又把「手上这些 · 跌破离场线才清仓」做进了模拟盘。
 * 同一屏上摆两套互相不认的离场纪律, 读的人每天要先决定信哪一个 —— 那不是信息,
 * 是负担。
 *
 * **后端一个字没动**: `/api/today` 照旧算并返回 actions / holdings / portfolio,
 * 只是这一页不再渲染。要恢复就把两个 section 加回来, 数据一直在。
 * (代价是这几项仍在每次请求里白算 —— 知情保留, 换的是随时能改回来。)
 *
 * [R179] 那条「风险排在机会前面」的排序论证随被删的区块一起退役: 页面上已经
 * 没有风险区了。它的精神搬去了模拟盘 —— 那一页「今天该挂什么单」就在最顶上。
 *
 * 数据全部来自既有模块,零新计算;AI 导读可选(手动点击,一次调用)。
 */
import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { Download, Loader2, RefreshCw, Sparkles, Sunrise, Target } from 'lucide-react'
import { api, type TodayPick } from '@/lib/api'
import { toast } from '@/components/Toast'
import { PageShell } from '@/components/PageShell'
import { QK } from '@/lib/queryKeys'
// [R167] 以下五块从本文件拆出 —— 拆前 1922 行, 一个文件装下了导出、表格、面板、
// 弹窗和页面本体。缝按"对外暴露什么"划: 每个模块只导出 1~2 个组件, 其余是内部实现。
import { buildTodayHtml } from '@/lib/todayHtmlExport'
import { OpportunityTable, GateFunnel } from '@/components/today/OpportunityTable'
import { AiPickPanel } from '@/components/today/AiPickPanel'
import { MarketStatusCard } from '@/components/today/MarketStatusCard'
import { TodaySkeleton } from '@/components/today/TodaySkeleton'   // [R324] 首次加载骨架
import { AiAskDialog } from '@/components/today/AiAskDialog'
import { TodayHealthBar } from '@/components/today/TodayHealthBar'   // [R341] 拆出去了, 模拟盘也用
import { TodayControls } from '@/components/today/TodayControls'     // [R347] 门槛/体检/筛选
import { useTodayOverview } from '@/lib/useSharedQueries'            // [R342] 节奏一处定义


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
  // [R342] 节奏收到 useTodayOverview 一处定义 —— 三个调用方共用
  const q = useTodayOverview()
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
  // [R147] AI 分析前的补充说明弹窗。lastNote 只为"重试"沿用上一次问的话
  const [askOpen, setAskOpen] = useState(false)
  const [lastNote, setLastNote] = useState('')
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
  // [R347] 板块过滤的**写**已经归 `TodayControls`(与模拟盘共用那一份)。
  // 这一页只剩两处**读**: 状态行里那句「只看 X」, 与机会区空掉时那个「去掉过滤」。
  // 后者直接打一次接口再重取 —— 不为一个按钮把整套乐观值逻辑再抄一遍回来。
  const boardFilter = d?.prefs?.boards ?? []
  const clearBoards = async () => {
    try {
      await api.todaySavePrefs({ boards: [] })
      await q.refetch()
    } catch (e) {
      toast(`保存失败: ${(e as Error).message}`, 'error')
    }
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

      {/* [R274] 自检条 —— **正常时一个像素都不占**, 出问题才现身。
          这一页的构建过程里十几处 try/except 原本只写日志就继续: 页面照常渲染,
          那个区块只是空的, 而看的人分不出「今天真没有」和「算挂了」。 */}
      {!!d?.health && <TodayHealthBar h={d.health} />}

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

      {/* [R324] 首次加载画版面的骨架, 不再是一个居中转圈 —— 内容填进来不跳。
          只在 isLoading(本地没有任何缓存)时出现; 后台重取时上一份还在。 */}
      {q.isLoading && <TodaySkeleton />}
      {q.isError && (
        <div className="rounded-lg border border-red-400/30 bg-red-400/10 px-4 py-3 text-xs text-red-400">
          总览加载失败:{(q.error as Error)?.message}
        </div>
      )}

      {d && (
        <>
          {/* [R142] 市场状态 —— 原「市场天气」+「中观」合并。见组件上方注释 */}
          <MarketStatusCard d={d} meso={meso} mainline={mainline} />

          {/* [R347] 门槛 / 体检 / 板块筛选 —— 一处实现, 与模拟盘共用 */}
          <TodayControls d={d} refetch={() => q.refetch()} isFetching={q.isFetching} />

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
              {/* [R347] 板块筛选 / 体检 / 门槛整组抽成 `TodayControls` —— 模拟盘也要用,
                  手抄一遍必漂。见那个文件顶部说明。 */}
            </div>
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
                    onClick={clearBoards}
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


/**
 * [R274] 今日总览自检条。
 *
 * 三种情况分开说, 因为处置不一样:
 *
 *   整块没了    界面上那一块是空的 —— 醒目, 并说清是哪一块
 *   少个标      主体还在, 只是少一列注记 —— 提一句, 不打断
 *   数据陈了    什么都没报错, 但整页数字是几天前的(收盘后管道没跑) ——
 *               这一条最阴: 页面看起来完全正常, 而你在用过期数字做决定
 *
 * **一切正常时不渲染任何东西。** 常驻一条"运行正常"的绿条, 看两天就成了背景板,
 * 真出问题那天照样会被忽略。
 */
