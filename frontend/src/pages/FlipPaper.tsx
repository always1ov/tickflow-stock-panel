/**
 * [fork 增强 R327] 转折模拟盘 —— 一个组合, 只按六态转折买卖。
 *
 * 用户: 「模拟盘页面大整改, 完全不需要我原来的了, 重新设计, 每天收盘价按照转折
 * 买卖, 所有票只看趋势状态的转折」。
 *
 * 替掉 R59 那套「AI 操盘手」(8 个操作员、每天定时问模型、账本落盘)。这一页要
 * 回答的是完全不同的一个问题: **我这套六态判定, 真按它做, 长期是赚是亏?**
 *
 * ## 版面顺序 = 读它的顺序
 *
 *   ① 结论    赚了多少 / 最大回撤 / 多少轮 / 胜率 —— 一眼就该看见的四个数
 *   ② 曲线    净值走势
 *   ③ 现在    还拿着哪几只(这是"接下来要盯的")
 *   ④ 流水    每一笔为什么买、为什么卖
 *   ⑤ 没做成  封板没买进 / 仓位满了 / 钱不够 —— **空栏必须自己解释**
 *   ⑥ 规则    口径, 从后端取, 不在这里誊抄
 *
 * 结论在最前, 规则在最后: 规则是查证用的, 不该天天占着首屏(R190 那条教训 ——
 * 「顶头那两个说明, 太多废话了」)。
 *
 * ## 参数一改就是另一条曲线
 *
 * 本金 / 同时持有上限 / 回溯年数都进 queryKey。这套后端是纯函数, 同样的参数必然
 * 同样的结果, 所以缓存可以放心留着。
 */
import { useMemo, useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { ChevronDown, Eye, Loader2, Sparkles, TrendingDown, TrendingUp, Wallet } from 'lucide-react'
import { api, type FlipOrder, type FlipPaper as FlipPaperData, type FlipRules,
  type FlipTodaySignal, type TodayOpportunity } from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import { PageHeader } from '@/components/PageHeader'
import { Hint } from '@/components/Hint'
import { Skeleton } from '@/components/data/Skeleton'
import { useECharts } from '@/pages/backtest/charts/useECharts'
import { cn } from '@/lib/cn'
import { storage } from '@/lib/storage'
import { refreshEvery, rhythmHint } from '@/lib/refreshRhythm'
import { useTodayOverview } from '@/lib/useSharedQueries'      // [R342] 把握分(只排序)
import { TodayHealthBar } from '@/components/today/TodayHealthBar'   // [R343] 数据自检条
import { ScoreCell } from '@/components/today/ScoreCell'             // [R345] 名次那一格
import { TrendCell } from '@/components/today/TrendCell'             // [R349] 走势那一格
import { TodayControls } from '@/components/today/TodayControls'     // [R347] 门槛/体检/筛选
import { toast } from '@/components/Toast'

/** [R343] 姿态四档的配色 —— 与今日总览那张卡同一套语义, 不另立一份说法。 */
const POSTURE_TONE: Record<string, string> = {
  进攻: 'bg-bull/15 text-bull',
  谨慎: 'bg-warning/15 text-warning',
  防守: 'bg-bear/15 text-bear',
  观察: 'bg-muted/15 text-muted',
}

const CAPITAL_OPTIONS = [100_000, 500_000, 1_000_000, 5_000_000]
const POSITION_OPTIONS = [3, 5, 10, 20]
// [R339] 用户: 「回溯时间太长了, 只看近三年和短周期」。
//
// 砍掉 5 年、补进半年。**R332 里我为「不许砍短」写过守卫, 这次是用户当面推翻它**
// —— 那条守卫的论点(回溯给的是样本量)没有错, 只是它不该替用户做决定; 现在守卫
// 改成钉新口径, 并且把样本量那件事**摆到界面上说**, 而不是靠一条测试替他拦着。
//
// 半年 ≈ 120 个交易日。转折是低频信号, 这个窗口里可能只有两三次完整买卖 ——
// 胜率、最大回撤在那种样本量下**不是"不好看", 是不成立**。所以下面的统计里
// 完整买卖少于 10 次会明说, 见 `Summary`。
const YEAR_OPTIONS = [0.5, 1, 2, 3]

/** 回溯档位的写法: 不足一年按月说 —— 「0.5 年」没人这么讲话。 */
const fmtYears = (v: number) => (v < 1 ? `${Math.round(v * 12)} 个月` : `${v} 年`)

/** 没做成的原因 —— 逐条翻译。**空栏必须自己解释**: 读的人分不清"没有"和"算不出来" */
const WHY_CN: Record<string, string> = {
  sealed: '封板挂不进去',
  no_slot: '仓位已满',
  no_cash: '现金不够一手',
  voided: '一直封到反向转折, 这张单作废',
}

const REASON_CN: Record<string, string> = {
  no_data: '自选里的票都取不到日线, 一天也跑不了',
  no_flip: '这段时间里一次转折都没有 —— 不是亏了, 是压根没动过手',
  no_watchlist: '自选是空的 —— 先去自选页加几只票',
}

function pct(v: number | null | undefined, digits = 2): string {
  if (v == null) return '—'
  return `${v >= 0 ? '+' : ''}${(v * 100).toFixed(digits)}%`
}

function money(v: number | null | undefined): string {
  if (v == null) return '—'
  return v.toLocaleString('zh-CN', { maximumFractionDigits: 0 })
}

/**
 * [R328] 标的那一格 —— **名称与代码相同时只印一个**。
 *
 * 维表里查不到名称的票(退市、新股还没进维表), 后端会退回代码。那时照旧
 * 「名称 + 代码」两栏渲染, 印出来就是「000636.SZ 000636.SZ」—— 同一个字符串
 * 重复两遍, 看着像渲染坏了。
 */
function SymbolCell({ symbol, name }: { symbol: string; name: string }) {
  const named = name && name !== symbol
  return (
    <>
      <span className="font-medium">{named ? name : symbol}</span>
      {named && <span className="ml-1.5 font-mono text-[10px] text-muted">{symbol}</span>}
    </>
  )
}

export function FlipPaper() {
  const navigate = useNavigate()
  const [capital, setCapital] = useState(1_000_000)
  const [maxPositions, setMaxPositions] = useState(10)
  const [years, setYears] = useState(2)

  const q = useQuery({
    queryKey: QK.flipPaper(capital, maxPositions, years),
    queryFn: () => api.flipPaper({ capital, maxPositions, years }),
    staleTime: 5 * 60_000,
    // [R333] 自己刷, 不等人点。走 `derived` 档: 这一页的主体是日线派生的回测,
    // 收盘落盘才会变; 但「今天该挂什么单」那一块带实时叠加层, 盘中是会动的 ——
    // 所以盘中 5 分钟, 盘后 1 小时。
    refetchInterval: refreshEvery('derived'),
    refetchOnWindowFocus: true,
  })
  const rules = useQuery({
    queryKey: QK.flipPaperRules,
    queryFn: () => api.flipPaperRules(),
    staleTime: 24 * 3600_000,
    // 规则口径改了要重新部署才生效 —— 轮询它没有意义
    refetchInterval: refreshEvery('static'),
  })

  const d = q.data

  // [R342] 把握分只用来**排序与标注**, 不参与"能不能动手"。取自今日总览那份
  // 打分(与今日总览页共享同一份缓存, 不多打一次接口)。
  const today = useTodayOverview()
  const ov = today.data
  // [R345] 存整条 —— 「名次」那一格要画三条维度条, 只留分数与名次画不出来。
  const conv = useMemo(() => {
    const m = new Map<string, TodayOpportunity>()
    for (const o of ov?.opportunities ?? []) {
      if (o.rank == null) continue
      m.set(o.symbol, o)
    }
    return m
  }, [ov])

  // [R343] AI 导读 —— 手动点一次才跑。失败必须在页面上留痕: toast 一闪即逝,
  // 用户会以为"点了没反应"。
  const [brief, setBrief] = useState<string | null>(null)
  const [aiError, setAiError] = useState<string | null>(null)
  const aiMut = useMutation({
    mutationFn: () => api.todayAi(),
    onMutate: () => setAiError(null),
    onSuccess: (r) => {
      if (r.error) { setAiError(r.error); toast(r.error, 'error'); return }
      setBrief(r.brief || null)
    },
    onError: (e: Error) => {
      setAiError(`AI 分析失败: ${e.message}`)
      toast(`AI 分析失败: ${e.message}`, 'error')
    },
  })

  // [R344] **名单只由六态选, 前端不合成任何一行。**
  //
  // 用户: 「我的本意是不看我的自选了, 打分系统针对六态选出来的进行二次排序」。
  //
  // R343 那一版往名单里塞了「打分候选」—— 打分选出来但六态没选中的票。方向是反的:
  // **那正是"打分自己选票"**, 而这套系统里选票这件事只归六态。打分的位置在它后面,
  // 不在它旁边。守卫直接钉"`rows` 只能是后端给的那份, 前端不许合成"。

  const w = ov?.weather
  // [R346] 主线用**品红**, 沿用今日总览那张卡的语义(那儿是 `text-fuchsia-300`
  // 配 `bg-fuchsia-400/15`)。上一版我给了个 `text-secondary` —— 那是灰阶不是颜色。
  //
  // **停更要变灰**: 原卡片对 `stale` 是换成 `text-muted` 并把标题改成
  // 「主线(数据已停更)」。丢掉这一层的话, 一份几天前的主线会**长得跟今天的一模一样**
  // —— 那比不显示更糟。
  const ml = ov?.meso?.mainline
  const mainline = ml?.rows?.[0]?.member ?? null
  const mlStale = !!ml?.stale
  const shownBrief = brief ?? ov?.ai?.brief ?? null
  return (
    <div className="flex h-full flex-col">
      <PageHeader
        title="转折模拟盘"
        // [R343] 市场状态并进页头 —— 定基调的东西不该自己占一张卡。
        // 姿态是结论, 给它徽章的位置; 多空比与主线是依据, 跟在副标题里。
        titleExtra={w && (
          <span className={cn('shrink-0 rounded px-1.5 py-0.5 text-[11px] font-medium',
            POSTURE_TONE[w.posture] ?? POSTURE_TONE.观察)}
            title={w.posture_reason || undefined}>
            {w.posture}
          </span>
        )}
        // [R345] **多空要分红绿。** 并进页头时我把整行压成了一条灰字 ——
        // 数字还在, 但"多 81 / 空 90"这种对照**靠颜色才读得快**, 全灰之后得逐字
        // 读完才知道哪边多。配色沿用今日总览那张卡的语义(`text-bull` 红涨 /
        // `text-bear` 绿跌), **不另立一份说法**。
        // 刷新节奏保持 muted: 它是这一行里最不重要的东西, 该往后退。
        subtitle={w
          ? (
            <>
              多 <span className="text-bull">{w.bull}</span>
              <span className="mx-0.5">/</span>
              空 <span className="text-bear">{w.bear}</span>
              <span className="mx-1">·</span>
              转多 <span className="text-bull">{w.new_bull}</span>
              {' '}转空 <span className="text-bear">{w.new_bear}</span>
              {mainline && <>
                <span className="mx-1">·</span>
                {mlStale ? '主线(停更)' : '主线'}{' '}
                <span className={mlStale ? 'text-muted' : 'text-fuchsia-300'}
                      title={mlStale
                        ? `主线数据停在 ${ml?.date},已经 ${ml?.age_days} 天没更新 —— 只作展示`
                        : `按 ${ml?.date} 的涨停梯队聚合`}>
                  {mainline}
                </span>
              </>}
              <span className="mx-1">·</span>
              {rhythmHint('derived')}
            </>
          )
          : `非真实资金 · 只按六态转折买卖 · ${rhythmHint('derived')}`}
        right={
          <div className="flex flex-wrap items-center gap-1.5 text-[10px]">
            <Picker label="本金" value={capital} options={CAPITAL_OPTIONS}
                    onChange={setCapital} fmt={money} />
            <Picker label="最多持有" value={maxPositions} options={POSITION_OPTIONS}
                    onChange={setMaxPositions} fmt={(v) => `${v} 只`} />
            <Picker label="回溯" value={years} options={YEAR_OPTIONS}
                    onChange={setYears} fmt={fmtYears} />
            {/* [R343] AI 导读收进页头一个按钮 —— 手动点一次才跑, 不自动 */}
            <button
              type="button"
              onClick={() => aiMut.mutate()}
              disabled={aiMut.isPending}
              className="inline-flex items-center gap-1 rounded-btn border border-border px-1.5 py-0.5 text-muted transition-colors hover:bg-elevated/60 hover:text-foreground disabled:opacity-50 cursor-pointer"
            >
              {aiMut.isPending
                ? <Loader2 className="h-3 w-3 animate-spin" />
                : <Sparkles className="h-3 w-3" />}
              AI 导读
            </button>
          </div>
        }
      />

      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto px-3 pb-4 pt-3 lg:px-4">
        {/* [R343] 自检条排在最顶且**不进任何折叠** —— 它一切正常时一个像素都不占,
            而它要说的是「你正在看的数字是几天前的」, 那句话被折起来就没有意义了。 */}
        {!!ov?.health && <TodayHealthBar h={ov.health} />}
        {aiError && (
          <div className="rounded-card border border-danger/40 bg-danger/10 px-4 py-2 text-xs text-danger">
            {aiError}
          </div>
        )}
        {shownBrief && (
          <p className="max-w-[80ch] rounded-card border border-border/60 bg-surface/40 px-4 py-2.5 text-[12px] leading-[1.8] text-foreground">
            {shownBrief}
          </p>
        )}

        {/* [R347] 门槛 / 体检 / 板块筛选 —— 与今日总览共用那一份实现。用户:
            「门槛的东西非常重要, 体检和筛选功能也要能保留」。
            **它只作用于打分那一层**: 板块过滤改的是哪些票拿得到名次, 门槛改的是
            谁进候选池 —— 也就是只影响本页信号的**先后与标注**, 不影响谁在名单上
            (名单只由六态选, R344), 更不影响谁能出手。守卫钉着这条。 */}
        {ov && <TodayControls d={ov} refetch={() => today.refetch()} isFetching={today.isFetching} />}

        {q.isLoading && <LoadingSkeleton />}
        {q.isError && (
          <div className="rounded-card border border-danger/40 bg-danger/10 px-4 py-3 text-xs text-danger">
            跑不动:{(q.error as Error)?.message}
          </div>
        )}

        {d && d.reason && (
          <div className="rounded-card border border-warning/30 bg-warning/10 px-4 py-3 text-xs text-warning">
            {REASON_CN[d.reason] ?? d.reason}
          </div>
        )}

        {d && !d.reason && (
          <>
            <TodaySignals rows={d.today ?? []} conviction={conv} />
            <Summary d={d} />
            <NavChart d={d} />
            <Holdings d={d} onOpen={(s) => navigate(`/stock-analysis?symbol=${s}`)} />
            <Orders orders={d.orders} />
            <Skipped d={d} />
          </>
        )}


        {/* 规则排在最后 —— 查证用的, 不该天天占首屏 */}
        {rules.data && <Rules r={rules.data} d={d} />}
      </div>
    </div>
  )
}

/**
 * [R329] 今日信号 —— 「收盘前五分钟该挂什么单」。
 *
 * 用户唯一的要求: **一定要根据转折才能出手**。所以这一块的版面把三档拉得很开:
 *
 *   已转折    整行高亮 + 一个动作徽标(买入 / 清仓)—— 这是今天真要做的
 *   盘中越线  无动作, 一句「收盘还站在这边才算数」—— 盘中价会变回去
 *   只是盯着  最暗的一档, 只报距离
 *
 * **后两档连动作徽标的位置都没有**, 不是"灰掉"而是根本不渲染 —— 灰掉的按钮
 * 仍然在暗示"这里本来有个动作"。
 *
 * [R338] 中间插一段**「手上这些」**。用户: 「有买入就要有卖出」。
 *
 * 在这之前, 这一块每天只长出买入 —— 不是判据坏了(转空要卖的代码一直在, 也一直
 * 有守卫), 而是**版面让卖出没有位置**: 买入的候选是全部自选(几十上百只), 卖出
 * 的候选只有模拟盘手上那几只, 两边天生不对等; 而手上那几只**离卖出线还有多远**
 * 被折进了「只是盯着」, 跟几十只不相干的票混在一起, 行上连"我拿着这只"都不标。
 * 于是卖出只在真触发的那一天冒出来一次, 其余每天看上去都只有买入。
 *
 * 所以这一段**常驻、不折叠**: 手上的票天天都该看见它的离场线。它**不带动作
 * 徽标** —— 没转折就不出手, 那条铁律没有因为这段而松动一毫米。
 *
 * [R342/R344] **两段式: 六态负责「选」, 打分负责「排」。**
 *
 * 用户: 「打分系统针对六态选出来的进行二次排序」。
 *
 *     第一段  六态选出今天有话说的票, 并分进四档(能不能成交)
 *     第二段  打分在每一档内部重排先后
 *
 * **界线**: 四档的边界(能不能动手 / 今天会不会成交 / 拿没拿着)**只由六态定**,
 * 打分一分都不参与 —— `isLive` 那一行有守卫钉着。打分只管进了同一档之后谁排前面。
 *
 * 这件事在这之前**根本没人回答**: 后端那句 `out.sort(...)` 的末位键是
 * `r["symbol"]`, 而已转折那一档 `gap_pct` 恒为 None, 于是 6 笔买入的先后
 * **实际是按股票代码的字母序**。六笔单子摆在面前, 版面对"先做哪个"一个字都没说。
 *
 * 分**不改变名单**: 没进候选池的票(没过打分那三道硬门槛)照样在名单里, 只排在本档
 * 末尾 —— 它被六态选中了就是选中了, 打分够不够是另一个问题。而反过来,
 * **打分选出来但六态没选中的票一行都不进来**(R344 删掉了 R343 合成的那些)。
 */
function TodaySignals({ rows, conviction }: {
  rows: FlipTodaySignal[]
  conviction: Map<string, TodayOpportunity>
}) {
  // [R331] 用户: 「今天该挂什么单显得太多了, 需要折叠展开的功能」。
  //
  // **折叠边界落在「今天是否可能成交」上**, 不是随便砍前 N 条:
  //
  //   常驻  已转折要动手  —— 今天真要挂的单
  //   常驻  盘中越线      —— 收盘还站在这边就成交, 今天就要盯
  //   常驻  手上这些      —— [R338] 拿着的票, 离场线天天要看见
  //   收起  只是盯着      —— 还差几个点, 今天大概率不用动
  //
  // 「盯着」那一段的条数随自选规模走(5% 以内就进名单), 自选上百只时它会把真要
  // 动手的那两三行淹掉 —— 而那两三行正是这个区块存在的全部理由。
  //
  // **要动手的永远不进折叠区**, 这一条有守卫钉着: 折叠是为了让信号更显眼,
  // 把信号自己折起来就本末倒置了。
  const [watchOpen, setWatchOpen] = useState(() => storage.flipTodayWatchOpen.get(false))
  const toggleWatch = () => {
    setWatchOpen((v) => {
      storage.flipTodayWatchOpen.set(!v)
      return !v
    })
  }

  // **一个判据, 三段分流。** 常驻/折叠的边界只由 `isLive` 这一个函数说了算 ——
  // 以前是把同一段条件正着写一遍、反着再写一遍, 改一边漏一边就会出现"两边都收
  // 它"或"两边都不收它"的票, 而且不报错。
  const isLive = (r: FlipTodaySignal) => (r.stage === 'flipped' && !!r.act) || r.stage === 'crossing'
  const live = rows.filter(isLive)
  const rest = rows.filter((r) => !isLive(r))
  const mine = rest.filter((r) => r.held)   // [R338] 手上拿着的, 常驻
  const idle = rest.filter((r) => !r.held)  // 其余, 折叠
  const actCount = live.filter((r) => r.stage === 'flipped' && r.act).length

  // [R344] **两段式: 六态负责「选」, 打分负责「排」。**
  //
  // 用户: 「打分系统针对六态选出来的进行二次排序」。
  //
  // R343 我把这条理解成了「六态排不动了才轮到打分」—— 方向反了。正确的分工是
  // 两段, 不是二选一:
  //
  //     第一段  六态选出今天有话说的那些票, 并把它们分进四档(能不能成交)
  //     第二段  打分在**每一档内部**重排先后
  //
  // 四档的**边界仍然只由六态定**(能不能动手 / 今天会不会成交 / 拿没拿着) ——
  // 打分一分都不参与那个判定, `isLive` 那一行有守卫钉着。打分只管进了同一档之后
  // 谁排前面。
  //
  // 没进候选池的(拿不到名次)一律排到本档末尾, 但**仍在名单里** —— 它被六态选中
  // 了就是选中了, 打分够不够是另一个问题。
  //
  // **只重排, 不增删。** `slice()` 先拷一份 —— 直接 sort 会就地改上面那个 filter
  // 的产物, 而 React 的 props 数组不该被下游改。
  const rank = (r: FlipTodaySignal) => conviction.get(r.symbol)?.rank ?? Number.MAX_SAFE_INTEGER
  const byRank = (rs: FlipTodaySignal[]) => rs.slice().sort((a, b) => rank(a) - rank(b))
  const ordered = byRank(live)
  const mineSorted = byRank(mine)
  const idleSorted = byRank(idle)
  const scored = live.filter((r) => conviction.has(r.symbol)).length

  return (
    <section className="overflow-hidden rounded-card border border-border/60 bg-surface/40">
      <SectionHead
        title="今天该挂什么单"
        note={[
          actCount ? `${actCount} 笔要动手` : '今天没有要动手的',
          // [R342] 说明白这个顺序是谁排的 —— 不说的话读的人不知道该不该照着做
          actCount && scored ? '按把握分排序' : null,
          mine.length ? `手上 ${mine.length} 只` : null,
        ].filter(Boolean).join(' · ')}
        hint={'**只有真转折才出手。**\n\n已转折 = 最新那根已落盘的日 K 让状态翻了面, 这才是动作。\n盘中越线 = 按此刻现价当收盘算会翻面 —— **不是出手理由**, 盘中价会变回去,\n14:30 跌破、14:58 拉回来的那天根本没有转折。\n\n触发价是作者的六态每天给的 flip_up / flip_down, 开盘前就定死,\n所以尾盘盯着它挂单是做得到的。\n\n「手上这些」是模拟盘现在拿着的票与各自的离场线 —— 常驻不折叠,\n买入天天有、卖出只在触发那天冒一次, 中间这段空白正是它补的。\n\n最下面「只是盯着」默认收起 —— 它随自选规模走, 摊开会把真要动手的淹掉。'}
      />

      {rows.length === 0 ? (
        <div className="px-4 py-5 text-xs text-muted">
          自选里没有一只处在转折边上 —— <b className="text-secondary">今天不用动</b>。
        </div>
      ) : (
        <>
          {ordered.length > 0 && (
            <div className="divide-y divide-border/30">
              {ordered.map((r) => <SignalRow key={r.symbol} r={r} c={conviction.get(r.symbol)} />)}
            </div>
          )}
          {ordered.length === 0 && (
            <div className="px-4 py-3 text-xs text-muted">
              今天没有要动手的 —— <b className="text-secondary">管住手</b>。
            </div>
          )}

          {/* [R338] 手上这些 —— **常驻, 没有折叠开关**。
              买入天天长出来, 卖出只在真触发那天冒一次; 中间那段空白就是这里补的。
              不带动作徽标: 没转折就不出手, 这一段只回答「离场线在哪、还有多远」。 */}
          {mine.length > 0 && (
            <>
              <div className="flex items-center gap-1.5 border-t border-border/40 bg-elevated/20 px-4 py-2 text-[11px] text-secondary">
                <Wallet className="h-3 w-3" />
                手上这些 · 跌破离场线才清仓
                <span className="ml-auto text-muted opacity-70">{mine.length} 只</span>
              </div>
              <div className="divide-y divide-border/30">
                {mineSorted.map((r) => <SignalRow key={r.symbol} r={r} c={conviction.get(r.symbol)} />)}
              </div>
            </>
          )}

          {idle.length > 0 && (
            <>
              <button
                type="button"
                onClick={toggleWatch}
                aria-expanded={watchOpen}
                className="flex w-full items-center gap-1.5 border-t border-border/40 px-4 py-2 text-[11px] text-muted transition-colors hover:bg-elevated/40 hover:text-foreground cursor-pointer"
              >
                <ChevronDown className={cn('h-3 w-3 transition-transform duration-expand ease-smooth',
                  watchOpen && 'rotate-180')} />
                {watchOpen ? '收起' : '展开'}「只是盯着」的 {idle.length} 只
                <span className="ml-auto opacity-70">今天大概率不用动</span>
              </button>
              {watchOpen && (
                /* 限高 + 自己滚: 盯着的票可能几十只, 让它把整页顶长等于没折叠 */
                <div className="max-h-64 divide-y divide-border/30 overflow-y-auto">
                  {idleSorted.map((r) => <SignalRow key={r.symbol} r={r} c={conviction.get(r.symbol)} />)}
                </div>
              )}
            </>
          )}
        </>
      )}
    </section>
  )
}

/** [R339] 离清仓线多近才算"贴着了"。**只用来上色, 不产生任何动作。** */
const NEAR_EXIT = 0.02

function SignalRow({ r, c }: { r: FlipTodaySignal; c?: TodayOpportunity }) {
  const actionable = r.stage === 'flipped' && !!r.act
  // [R349] 「走势」那一格整格移植过来(用户: 「这一列也要有」)。
  //
  // **它单独占一行, 不跟六态那句挤在一起** —— 两者回答的不是同一个问题:
  //
  //     六态那句   今天要不要动手(已转折 / 盘中越线 / 还差多少)
  //     走势那格   凭什么是这一只(位置贵不贵 / 有没有量 / 离关键点多远)
  //
  // 挤进同一行的话, 一行里会出现两套判据的措辞并排, 读的人得先分清哪句是哪套。
  // 分两行, 上面一行是本页的主线, 下面一行是打分那一层的依据。
  //
  // 只在这只票**进了候选池**时才有 —— 没有名次就没有这些读数, 不留空位。
  // [R339] 用户: 「卖出也要上色, 这样看起来醒目」。
  //
  // 在这之前**买卖两种要动手的行共用同一个灰蓝底** `bg-accent/[0.06]` —— 徽标
  // 虽然分了红绿, 但一行里最先被看见的是整条底色, 而底色对买和卖说的是同一句话。
  // 现在底色跟着方向走, 并在左边加一道 2px 的色条: 扫一眼就知道今天是要买还是要卖,
  // 不用先去读徽标上那两个字。
  //
  // **另加一档"贴着清仓线"**: 手上的票离离场线 2% 以内时同样上琥珀色 —— 卖出这一侧
  // 真正该醒目的不只是"今天要卖", 还有"明后天很可能要卖"。这一档**不带动作徽标**,
  // 上色不是出手理由(铁律没动, 守卫钉着)。
  const sell = actionable && r.act === 'sell'
  const buy = actionable && r.act === 'buy'
  const nearExit = !actionable && r.held && r.gap_pct != null
    && Math.abs(r.gap_pct) <= NEAR_EXIT
  return (
    <div className={cn('border-l-2 px-4 py-2.5',
      buy && 'border-l-bull bg-bull/[0.07]',
      sell && 'border-l-bear bg-bear/[0.10]',
      nearExit && 'border-l-warning bg-warning/[0.07]',
      !actionable && !nearExit && 'border-l-transparent')}>
      {/* [R350] 用户: 「你排版不对, 中间这么多空间」。
          **两个毛病, 同一个根**: 原来是 `flex` + 触发价上一个 `ml-auto`。
          在 2000px 宽屏上 `ml-auto` 把价格甩到最右边, 中间就空出一大条;
          而 flex 各行按自己的内容宽度排, **行与行之间列也对不齐** ——
          「离清仓线还有 10.0%」和「还差 15.2%」起点不同, 眼睛得逐行重找。
          改成**定宽网格**: 每一列宽度固定, 行与行天然对齐, 一列扫到底。
          再加一道 `max-w-[72rem]` —— 超宽屏上不再把一行内容拉成横贯两米,
          左右都留白比中间空一条好读得多。 */}
      <div className="grid max-w-[72rem] grid-cols-[minmax(9rem,12rem)_4.5rem_3.5rem_minmax(0,1fr)_auto] items-center gap-x-3 text-xs">
        <span className="truncate">
          <SymbolCell symbol={r.symbol} name={r.name} />
        </span>

        {actionable ? (
          <span className={cn('inline-flex items-center justify-center gap-1 rounded px-1.5 py-0.5 text-[11px] font-medium',
            r.act === 'buy' ? 'bg-bull/15 text-bull' : 'bg-bear/15 text-bear')}>
            {r.act === 'buy' ? <TrendingUp className="h-3 w-3" /> : <TrendingDown className="h-3 w-3" />}
            {r.act === 'buy' ? '买入' : '清仓'}
          </span>
        ) : (
          /* 后两档**不渲染动作位** —— 灰掉的徽标仍在暗示这里本来有个动作。
             [R338] 手上拿着的换个标记: 同样没有动作, 但"我拿着它"与"我在看它"
             是两件事, 一眼要能分开。 */
          r.held ? (
            <span className="inline-flex items-center gap-1 text-[10px] text-secondary">
              <Wallet className="h-3 w-3" />持有
            </span>
          ) : (
            <span className="inline-flex items-center gap-1 text-[10px] text-muted">
              <Eye className="h-3 w-3" />盯着
            </span>
          )
        )}

        {/* [R345] 「名次」那一格整格移植自今日总览 —— 用户: 「这一列要移植」。
            **不是只搬个数字**: 名次下面那三条维度条(红=趋势 45% / 蓝=量能 30% /
            黄=位置 25%)才是它能被读懂的原因 —— 离开那三条颜色, 上面那个名次
            就只是个号码, 说不出"为什么是这个名次"。
            它**不是动作**: 拿不到名次的票照样在名单里, 只是排在本档末尾。
            [R350] 这一格无论有没有都占住那 3.5rem —— 空着也要占位, 否则有名次的
            行和没名次的行后面所有列全都错开。 */}
        {c?.rank != null ? (
          <ScoreCell o={c} rank={c.rank} total={c.rank_total ?? 0} />
        ) : actionable ? (
          <span className="text-center text-[9px] leading-tight text-muted/60"
                title="没过打分那三道硬门槛, 所以没有名次 —— 但它转折了, 该动手还是要动手">
            没进
            <br />候选池
          </span>
        ) : <span />}

        <span className="min-w-0 truncate text-[11px] text-secondary">
          {r.stage === 'flipped' && <>已转折 · 现在是{r.state_cn}</>}
          {r.stage === 'crossing' && (
            <>按现价会转折 —— <b className="text-warning">收盘还站在这边才算数</b></>
          )}
          {/* [R338] 拿着的票问的是"什么时候卖", 不是"什么时候买" —— 同一个距离,
              说法要对上它在你这儿的身份 */}
          {r.stage === 'watch' && r.gap_pct != null && (
            r.held
              ? <b className={cn(nearExit && 'text-warning')}>
                  离清仓线还有 {(Math.abs(r.gap_pct) * 100).toFixed(1)}%
                </b>
              : <>还差 {(Math.abs(r.gap_pct) * 100).toFixed(1)}% 到触发价</>
          )}
        </span>

        {/* [R350] 不再 `ml-auto` —— 它是网格的最后一列, 位置由栅格决定 */}
        <span className="whitespace-nowrap text-right text-[10px] tabular-nums text-muted">
          {r.flip_price != null && <>
            触发 {r.flip_price.toFixed(2)}
            {r.ref_price != null && <> · 现 {r.ref_price.toFixed(2)}</>}
            {!r.live && <span className="ml-1 text-warning/70">昨收口径</span>}
          </>}
        </span>
      </div>

      {/* [R349] 走势 —— 打分那一层的依据, 单独一行。
          [R350] 缩进对齐到**状态文字那一列**(标的 12rem + 动作 4.5rem + 名次 3.5rem
          + 三道 gap 2.25rem ≈ 22.25rem), 而不是原来那个拍脑袋的 3.75rem ——
          它现在压在标的名下面, 看着像是标的的一部分。 */}
      {c && (
        <div className="mt-1 max-w-[72rem] pl-[22.25rem] text-[11px]">
          <TrendCell o={c} />
        </div>
      )}
    </div>
  )
}

function Picker<T extends number>({ label, value, options, onChange, fmt }: {
  label: string; value: T; options: readonly T[]
  onChange: (v: T) => void; fmt: (v: T) => string
}) {
  return (
    <label className="inline-flex items-center gap-1 text-muted">
      {label}
      <select
        value={value}
        onChange={(e) => onChange(Number(e.target.value) as T)}
        className="rounded-btn border border-border bg-base px-1.5 py-0.5 text-[10px] text-foreground cursor-pointer"
      >
        {options.map((o) => <option key={o} value={o}>{fmt(o)}</option>)}
      </select>
    </label>
  )
}

/**
 * [R332] 「近一月 / 近三月」—— 用户: 「回溯是回溯, 时间跨度太长了, 看看怎么设计
 * 能兼容注重当下」。
 *
 * **回溯那个参数不动。** 它给的是样本量: 转折是低频信号, 窗口短了只剩两三次
 * 转折, 胜率和回撤都说明不了任何事。但两年的总收益回答不了"我最近做得怎么样"
 * —— 一段半年前的暴涨能把最近三个月的亏损盖得严严实实。
 *
 * 所以**同一条净值曲线切一段再算一次**, 不重跑、不多打一次接口。
 *
 * 起点取"该窗口第一个交易日的前一天" —— 收益要算这一段**期间**的变化, 拿窗口
 * 内第一天的净值当起点会把那一天自己的涨跌吃掉。
 */
function windowRet(nav: FlipPaperData['nav'], days: number): number | null {
  if (nav.length < 2) return null
  const i = Math.max(0, nav.length - 1 - days)
  const base = nav[i].nav
  if (!base) return null
  return nav[nav.length - 1].nav / base - 1
}

function Summary({ d }: { d: FlipPaperData }) {
  const s = d.stats
  // 20 / 60 个交易日 ≈ 一个月 / 三个月。**按交易日数不按自然日**: 这条曲线
  // 本来就是逐交易日的, 拿自然日去切还要先做一次日历换算, 凭空多一层会漂的东西。
  const m1 = windowRet(d.nav, 20)
  const m3 = windowRet(d.nav, 60)
  const enough = d.nav.length
  return (
    <>
      {/* 当下那一行排在长期之前 —— 用户每天打开最先要问的是"最近怎么样" */}
      <section className="grid grid-cols-2 divide-x divide-y divide-border/30 overflow-hidden rounded-card border border-border/60 bg-surface/40 sm:grid-cols-4 sm:divide-y-0">
        <Stat label="近一月" value={enough >= 21 ? pct(m1) : '—'}
              tone={m1 != null && m1 >= 0 ? 'bull' : 'bear'}
              sub={enough >= 21 ? '最近 20 个交易日' : `只有 ${enough} 天, 不够一个月`}
              hint={'**同一条净值曲线上切一段算的**, 不是另跑一次回测 ——\n回溯那个参数给的是样本量, 这两格回答的是"我最近做得怎么样"。\n\n天数不够时空着而不是拿全程凑数: 「算不出来」与「没赚到」是两件事。'} />
        <Stat label="近三月" value={enough >= 61 ? pct(m3) : '—'}
              tone={m3 != null && m3 >= 0 ? 'bull' : 'bear'}
              sub={enough >= 61 ? '最近 60 个交易日' : `只有 ${enough} 天, 不够三个月`} />
        <Stat label="现在拿着" value={`${d.positions.length} 只`}
              sub={`仓位 ${d.nav.length ? pct((d.nav[d.nav.length - 1].market_value / d.nav[d.nav.length - 1].nav), 0) : '—'} · 现金 ${money(d.nav.at(-1)?.cash)}`}
              hint={'这是**当下**的仓位, 与上面那两格一样看的是现在;\n下面那一排才是整个回溯窗口的长期成绩。'} />
        <Stat label="最后一天" value={d.as_of ?? '—'}
              sub={`回溯 ${d.nav[0]?.date ?? '—'} 起`}
              hint={'日 K 要等收盘后落盘 —— 所以这里通常是上一个交易日,\n今天的要等 20:00 之后才会进来。'} />
      </section>

      {/* 长期成绩 —— 回溯窗口整段 */}
      <section className="grid grid-cols-2 divide-x divide-y divide-border/30 overflow-hidden rounded-card border border-border/60 bg-surface/40 sm:grid-cols-4 sm:divide-y-0">
        <Stat label="总收益" value={pct(s.total_ret)} tone={s.total_ret >= 0 ? 'bull' : 'bear'}
              sub={`本金 ${money(d.capital)} · ${s.days} 个交易日`} />
        <Stat label="最大回撤" value={pct(s.max_drawdown)} tone="bear"
              sub="净值从高点回落最深的一次" />
        <Stat label="完整买卖" value={`${s.round_trips} 轮`}
              sub={`买 ${s.buys} 次 · 卖 ${s.sells} 次`}
              hint={'一次买入到卖出算一轮。**还拿着的那几只不算** —— 没兑现的盈亏\n不该混进胜负(与复盘页「只数已兑现」同一条纪律)。'} />
        {/* [R339] 回溯能选到半年了, 而半年里转折可能只发生两三次。**样本量不够时
            要自己说出来** —— 一个「67%」摆在那儿, 读的人不会自己去想它背后是 3 轮
            还是 300 轮。10 轮是个朴素的门槛: 不是"到了就可信", 是"没到就别当数"。 */}
        <Stat
          label="胜率"
          value={s.win_rate == null ? '—' : `${(s.win_rate * 100).toFixed(0)}%`}
          tone={s.round_trips > 0 && s.round_trips < 10 ? 'warn' : undefined}
          sub={s.win_rate == null
            ? '一轮都没兑现, 算不出来'
            : s.round_trips < 10
              ? `只有 ${s.round_trips} 轮, 样本太少不当数`
              : `${s.win} 胜 / ${s.round_trips} 轮`}
          hint={'空着不是 0 —— 「算不出来」与「一次没赢过」是两件事。\n\n**轮数少于 10 时这一格会标黄**: 转折是低频信号, 回溯窗口短了\n可能只剩两三次完整买卖, 那种样本量下的胜率不是"不好看", 是**不成立**。\n想要能看的胜率就把回溯拉长 —— 这两件事没法兼得。'}
        />
      </section>
    </>
  )
}

function Stat({ label, value, sub, tone, hint }: {
  label: string; value: string; sub?: string
  /** [R339] 多一档 warn: 数字算得出来但**样本量撑不住它** —— 与涨跌无关 */
  tone?: 'bull' | 'bear' | 'warn'; hint?: string
}) {
  return (
    <div className="px-4 py-2.5">
      <div className="flex items-center gap-0.5 text-[10px] text-muted">
        {label}
        {hint && <Hint title={hint} />}
      </div>
      <div className={cn('mt-0.5 text-lg font-semibold tabular-nums',
        tone === 'bull' && 'text-bull', tone === 'bear' && 'text-bear',
        tone === 'warn' && 'text-warning')}>
        {value}
      </div>
      {sub && <div className={cn('mt-0.5 text-[10px]',
        tone === 'warn' ? 'text-warning/80' : 'text-muted')}>{sub}</div>}
    </div>
  )
}

function NavChart({ d }: { d: FlipPaperData }) {
  const option = useMemo(() => {
    if (!d.nav.length) return null
    // [R332] **默认只框最近 120 个交易日(约半年), 但整段都在, 拖得回去。**
    //
    // 回溯两年时, 半年前的一段暴涨会把最近几个月压成一条平线 —— 图上什么都看
    // 不出来。dataZoom 让默认视野落在当下, 而长期那条线一拖就回来, 两件事不用
    // 二选一。窗口不足 120 天时 start=0, 也就是整段都显示。
    const total = d.nav.length
    const startPct = total > 120 ? ((total - 120) / total) * 100 : 0
    return {
      grid: { left: 56, right: 16, top: 16, bottom: 52 },
      tooltip: { trigger: 'axis' as const },
      xAxis: { type: 'category' as const, data: d.nav.map((p) => p.date),
               axisLabel: { fontSize: 10 } },
      yAxis: { type: 'value' as const, scale: true,
               axisLabel: { fontSize: 10, formatter: (v: number) => money(v) } },
      dataZoom: [
        { type: 'inside' as const, start: startPct, end: 100 },
        { type: 'slider' as const, start: startPct, end: 100, height: 18, bottom: 8 },
      ],
      series: [{
        type: 'line' as const, name: '净值', data: d.nav.map((p) => p.nav),
        showSymbol: false, lineStyle: { width: 1.5 },
        areaStyle: { opacity: 0.08 },
      }],
    }
  }, [d.nav])
  const ref = useECharts(option, [option])
  if (!d.nav.length) return null
  return (
    <section className="overflow-hidden rounded-card border border-border/60 bg-surface/40">
      <SectionHead title="净值走势"
                   note={`默认看最近半年 · 拖下面那条可回到 ${d.nav[0]?.date} 起的全程`} />
      <div ref={ref} className="h-[280px] w-full" />
    </section>
  )
}

function Holdings({ d, onOpen }: { d: FlipPaperData; onOpen: (s: string) => void }) {
  return (
    <section className="overflow-hidden rounded-card border border-border/60 bg-surface/40">
      <SectionHead
        title="现在拿着"
        note={`${d.positions.length} 只 · 现金 ${money(d.nav.at(-1)?.cash)}`}
        hint={'这几只就是接下来要盯的 —— 它们各自下一次转空时, 这套规则会清掉。'}
      />
      {d.positions.length === 0 ? (
        <div className="px-4 py-5 text-xs text-muted">
          当前空仓 —— 自选里没有一只处在多头侧。<b className="text-secondary">空仓也是一种仓位</b>。
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[560px] text-xs">
            <thead className="text-[10px] text-muted">
              <tr className="text-left">
                <th className="px-4 py-1.5 font-normal">标的</th>
                <th className="px-2 py-1.5 text-right font-normal">股数</th>
                <th className="px-2 py-1.5 text-right font-normal">成本</th>
                <th className="px-2 py-1.5 text-right font-normal">现价</th>
                <th className="px-2 py-1.5 text-right font-normal">市值</th>
                <th className="px-2 py-1.5 text-right font-normal">浮盈</th>
              </tr>
            </thead>
            <tbody>
              {d.positions.map((p) => (
                <tr key={p.symbol} className="border-t border-border/30 hover:bg-elevated/40">
                  <td className="px-4 py-1.5">
                    <button onClick={() => onOpen(p.symbol)}
                            className="text-left hover:text-accent cursor-pointer">
                      <SymbolCell symbol={p.symbol} name={p.name} />
                    </button>
                  </td>
                  <td className="px-2 py-1.5 text-right tabular-nums">{p.shares.toLocaleString()}</td>
                  <td className="px-2 py-1.5 text-right tabular-nums">{p.cost?.toFixed(2) ?? '—'}</td>
                  <td className="px-2 py-1.5 text-right tabular-nums">{p.last.toFixed(2)}</td>
                  <td className="px-2 py-1.5 text-right tabular-nums">{money(p.market_value)}</td>
                  <td className={cn('px-2 py-1.5 text-right tabular-nums font-medium',
                    (p.pnl ?? 0) >= 0 ? 'text-bull' : 'text-bear')}>
                    {pct(p.pnl_pct)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}

function Orders({ orders }: { orders: FlipOrder[] }) {
  const [all, setAll] = useState(false)
  // 最近的排前面 —— 流水要回答"最近做了什么"
  const rows = useMemo(() => [...orders].reverse(), [orders])
  const shown = all ? rows : rows.slice(0, 30)
  return (
    <section className="overflow-hidden rounded-card border border-border/60 bg-surface/40">
      <SectionHead
        title="成交流水"
        note={`${orders.length} 笔 · 最近的在前`}
        right={rows.length > 30 && (
          <button onClick={() => setAll((v) => !v)}
                  className="text-[10px] text-muted hover:text-foreground cursor-pointer">
            {all ? '只看最近 30 笔' : `展开全部 ${rows.length} 笔`}
          </button>
        )}
      />
      {rows.length === 0 ? (
        <div className="px-4 py-5 text-xs text-muted">这段时间一次转折都没有, 所以一笔都没做。</div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[640px] text-xs">
            <thead className="text-[10px] text-muted">
              <tr className="text-left">
                <th className="px-4 py-1.5 font-normal">日期</th>
                <th className="px-2 py-1.5 font-normal">标的</th>
                <th className="px-2 py-1.5 font-normal">动作</th>
                <th className="px-2 py-1.5 font-normal">因为</th>
                <th className="px-2 py-1.5 text-right font-normal">成交价</th>
                <th className="px-2 py-1.5 text-right font-normal">金额</th>
              </tr>
            </thead>
            <tbody>
              {shown.map((o, i) => (
                <tr key={`${o.date}-${o.symbol}-${i}`} className="border-t border-border/30">
                  <td className="px-4 py-1.5 font-mono text-[10px] text-muted">
                    {o.date}
                    {o.delayed && (
                      <span className="ml-1 text-warning"
                            title={`信号在 ${o.signal_date}, 那几天封板挂不进去, 顺延到这天才成交`}>
                        ·延
                      </span>
                    )}
                  </td>
                  <td className="px-2 py-1.5">
                    <SymbolCell symbol={o.symbol} name={o.name} />
                  </td>
                  <td className="px-2 py-1.5">
                    <span className={cn('inline-flex items-center gap-0.5 rounded px-1.5 py-0.5 text-[10px] font-medium',
                      o.act === 'buy' ? 'bg-bull/15 text-bull' : 'bg-bear/15 text-bear')}>
                      {o.act === 'buy' ? <TrendingUp className="h-2.5 w-2.5" /> : <TrendingDown className="h-2.5 w-2.5" />}
                      {o.act === 'buy' ? '买入' : '清仓'}
                    </span>
                  </td>
                  <td className="px-2 py-1.5 text-[10px] text-secondary">
                    {o.reason}
                    {o.state_cn && <span className="ml-1 text-muted">({o.state_cn})</span>}
                  </td>
                  <td className="px-2 py-1.5 text-right tabular-nums">{o.price.toFixed(2)}</td>
                  <td className="px-2 py-1.5 text-right tabular-nums text-muted">{money(o.amount)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}

function Skipped({ d }: { d: FlipPaperData }) {
  if (!d.skipped.length && !d.missing.length) return null
  const byReason = d.skipped.reduce<Record<string, number>>((acc, s) => {
    acc[s.reason] = (acc[s.reason] ?? 0) + 1
    return acc
  }, {})
  return (
    <section className="overflow-hidden rounded-card border border-border/60 bg-surface/40">
      <SectionHead
        title="有信号但没做成"
        note={`${d.skipped.length} 次`}
        hint={'这一栏存在的理由: **不说出来的话, 曲线会显得比实际更"顺"**。\n有信号却没动手的次数, 与做成的那些同样是这套打法的一部分。'}
      />
      <div className="space-y-1.5 px-4 py-2.5 text-[11px]">
        {Object.entries(byReason).map(([r, n]) => (
          <div key={r} className="flex items-center gap-2">
            <span className="min-w-[9rem] text-secondary">{WHY_CN[r] ?? r}</span>
            <span className="tabular-nums text-muted">{n} 次</span>
          </div>
        ))}
        {d.missing.length > 0 && (
          <div className="flex items-start gap-2 pt-1">
            <span className="min-w-[9rem] shrink-0 text-warning">取不到日线</span>
            <span className="text-muted">
              {d.missing.join('、')} —— 这几只没进这次模拟, 不是它们没信号
            </span>
          </div>
        )}
        {d.pending.length > 0 && (
          <div className="flex items-start gap-2 pt-1">
            <span className="min-w-[9rem] shrink-0 text-secondary">还在等成交</span>
            <span className="text-muted">
              {d.pending.map((p) => `${p.name}(${p.act === 'buy' ? '买' : '卖'})`).join('、')}
            </span>
          </div>
        )}
      </div>
    </section>
  )
}

function Rules({ r, d }: { r: FlipRules; d?: FlipPaperData }) {
  return (
    <section className="overflow-hidden rounded-card border border-border/60 bg-surface/40">
      <SectionHead title="这套规则" note="口径 —— 与后端同一份, 不是这里另写的" />
      <div className="space-y-2 px-4 py-3 text-[11px] leading-relaxed">
        <Rule k="信号" v={r.signal} />
        <Rule k="成交" v={r.execute} />
        <Rule k="方向" v={r.direction.join('; ')} />
        <Rule k="仓位" v={`${r.sizing} —— 现在是 ${d?.max_positions ?? '—'} 只`} />
        <Rule k="标的" v={`${r.universe}${d ? ` —— 现在 ${d.symbols.length} 只` : ''}`} />
        <Rule k="不做空" v={r.short} />
        <Rule k="成本" v={`佣金 ${(r.costs.commission * 10000).toFixed(1)}‱ 双边 · 印花税 ${(r.costs.stamp_tax * 10000).toFixed(1)}‱ 卖出单边 · 滑点 ${r.costs.slippage_bps}bp · ${r.costs.lot} 股一手`} />
        <div className="mt-2 space-y-1.5 border-t border-border/40 pt-2 text-muted">
          <p>{r.caveat}</p>
          <p>{r.vs_flip_trades}</p>
          <p>{r.why_no_state}</p>
        </div>
      </div>
    </section>
  )
}

function Rule({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex gap-2">
      <span className="min-w-[3.5rem] shrink-0 text-muted">{k}</span>
      <span className="text-secondary">{v}</span>
    </div>
  )
}

function SectionHead({ title, note, right, hint }: {
  title: string; note?: string; right?: React.ReactNode; hint?: string
}) {
  return (
    <div className="flex items-center gap-2 border-b border-border/40 px-4 py-2.5">
      <span className="text-sm font-medium text-foreground">{title}</span>
      {hint && <Hint title={hint} />}
      {note && <span className="text-[10px] text-muted">{note}</span>}
      {right && <span className="ml-auto">{right}</span>}
    </div>
  )
}

function LoadingSkeleton() {
  return (
    <div role="status" aria-label="正在算" className="space-y-3">
      <div className="grid grid-cols-2 divide-x divide-y divide-border/30 overflow-hidden rounded-card border border-border/60 bg-surface/40 sm:grid-cols-4 sm:divide-y-0">
        {Array.from({ length: 4 }, (_, i) => (
          <div key={i} className="space-y-1.5 px-4 py-2.5">
            <Skeleton w="w-12" h="h-2.5" />
            <Skeleton w="w-16" h="h-5" />
            <Skeleton w="w-20" h="h-2.5" />
          </div>
        ))}
      </div>
      <div className="rounded-card border border-border/60 bg-surface/40 p-4">
        <Skeleton h="h-[240px]" rounded="rounded" />
      </div>
    </div>
  )
}
