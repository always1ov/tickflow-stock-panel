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
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { ChevronDown, Eye, RefreshCw, TrendingDown, TrendingUp, Wallet } from 'lucide-react'
import { api, type FlipOrder, type FlipPaper as FlipPaperData, type FlipRules,
  type FlipTodaySignal, type TodayOpportunity } from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import { getFlipHoldingDays } from '@/lib/flipHoldingDays'
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
import { LevelsDialog } from '@/components/stock-analysis/LevelsDialog' // [R363] 点标的弹日 K
import { StockReviewDialog } from '@/components/stock-analysis/StockReviewDialog' // [R364] 点动作弹复盘

/** [R343] 姿态四档的配色 —— 与今日总览那张卡同一套语义, 不另立一份说法。 */
const POSTURE_TONE: Record<string, string> = {
  进攻: 'bg-bull/15 text-bull',
  谨慎: 'bg-warning/15 text-warning',
  防守: 'bg-bear/15 text-bear',
  观察: 'bg-muted/15 text-muted',
}

// [R339/R353/R357] 回溯的上下界。R339 把档位砍到「半年~三年」, R353 改成可输入,
// 于是"档位"这个概念没有了 —— 边界改由输入框的 min/max 表达, 与后端
// `flip_paper.MIN_YEARS` / `MAX_YEARS` 对齐(守卫逐值钉着两边相等)。
//
// R339 那条论证仍然成立, 而且现在更要紧: 半年 ≈ 120 个交易日, 转折是低频信号,
// 那个窗口里可能只有两三次完整买卖 —— 胜率与最大回撤在那种样本量下**不是
// "不好看", 是不成立**。既然现在能填任意值, 这句话更得让人看见: 完整买卖少于
// 10 次时胜率会标黄并写明, 见 `Summary`。
const YEARS_MIN = 0.5
const YEARS_MAX = 3
const YEARS_DEFAULT = 1

/**
 * [R357] **收上限之后, 存着的旧值必须钳一道。**
 *
 * 上限从 10 收到 3, 而 R353 把这三个参数落了 localStorage —— 之前填过 5 年的人
 * 存里躺着一个 `5`, 打开页面直接送进 `queryKey` 打给后端, 换回一个 422
 * 「Input should be less than or equal to 3」。**输入框的 `max` 救不了它**:
 * 那道钳位只在人去改这个框时才发生, 而这个人根本没打算改它。
 *
 * 所以钳在**读出来的那一刻**, 不是等着谁去动那个框。
 */
function clampYears(v: unknown): number {
  const n = Number(v)
  if (!Number.isFinite(n)) return YEARS_DEFAULT
  return Math.min(YEARS_MAX, Math.max(YEARS_MIN, n))
}

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
  // [R353] 三个参数可自己填, 并且**记住** —— 每次打开都退回默认值等于没配过。
  const [capital, setCapital] = useState(() => storage.flipCapital.get(1_000_000))
  const [maxPositions, setMaxPositions] = useState(() => storage.flipMaxPositions.get(10))
  // [R357] 读出来先钳 —— 存里可能躺着收上限之前填的 5 年 / 10 年, 见 `clampYears`
  const [years, setYears] = useState(() => clampYears(storage.flipYears.get(YEARS_DEFAULT)))
  const putCapital = (v: number) => { storage.flipCapital.set(v); setCapital(v) }
  const putMaxPositions = (v: number) => { storage.flipMaxPositions.set(v); setMaxPositions(v) }
  const putYears = (v: number) => { storage.flipYears.set(v); setYears(v) }

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

  // [R344] **名单只由六态选, 前端不合成任何一行。**
  //
  // 用户: 「我的本意是不看我的自选了, 打分系统针对六态选出来的进行二次排序」。
  //
  // R343 那一版往名单里塞了「打分候选」—— 打分选出来但六态没选中的票。方向是反的:
  // **那正是"打分自己选票"**, 而这套系统里选票这件事只归六态。打分的位置在它后面,
  // 不在它旁边。守卫直接钉"`rows` 只能是后端给的那份, 前端不许合成"。

  /**
   * [R365] 手动刷新。用户: 「除了自动定时我还要手动按钮有时候我想看实时情况会点一下」。
   *
   * **自动那一档一个字没动**(盘中 5 分钟 / 盘后 1 小时, `refreshEvery('derived')`)
   * —— 这个按钮是补一条**当场要看**的路, 不是替掉节奏。
   *
   * **两个查询一起重取。** 这一页的数字来自两份互不相干的请求: 模拟盘自己那份
   * (回测 + 今日信号, 带实时叠加层)与今日总览那份(打分 / 多空比 / 主线 / 自检条)。
   * 只刷其中一个的话, 按钮说的是"刷新"而实际只刷了半页 —— 而另外半页看上去
   * 也没坏, 没有任何东西会提示你它是旧的。
   *
   * **在飞就禁用。** 模拟盘那一趟是几百只票的六态 + 一整轮回测, 秒级。不禁的话
   * 连点几下就是几趟全量重算堆在后端。
   */
  const refreshing = q.isFetching || today.isFetching
  const refreshAll = () => { void q.refetch(); void today.refetch() }

  // [R358] 成绩那一块并进筛选卡 —— 先在这里算好, 两条渲染路径共用同一个
  // (筛选条在 / 不在)。跑不动时 `reason` 那条横幅另有位置, 这里给 null。
  const summary = d && !d.reason ? <Summary d={d} /> : null

  /**
   * [R359] 卡里那一块 = **参数条 + 成绩**。用户: 「这两个部分整合到一个卡片放在
   * 顶部」, 追问后明确「参数框也并进来, 标题行留在外面」。
   *
   * **参数条必须排在成绩正上方**: 本金 / 最多持有 / 回溯**就是算出下面那些数字
   * 的那三个输入**。它原来在页头最右边, 与它决定的东西隔着大半个屏幕。
   *
   * **而且参数条不跟着 `summary` 一起消失**: `summary` 在跑不动时是 null, 可
   * 那正是最需要这三个框的时候 —— 回溯填过头、本金填成 0, 修的办法就是改它们。
   * 把参数条塞进 `Summary` 里, 出错时它会跟着一起不见, 于是**没有任何办法把
   * 页面救回来**, 只能清 localStorage。所以两者在这里并列, 不是嵌套。
   */
  const cardBody = (
    <div className="space-y-3">
      <ParamBar capital={capital} maxPositions={maxPositions} years={years}
                onCapital={putCapital} onMaxPositions={putMaxPositions} onYears={putYears} />
      {summary}
    </div>
  )

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
        // [R365] 手动刷新 —— 副标题那句说的是「它自己什么时候刷」, 这个按钮
        // 回答的是「我现在就要刷」。两件事挨着放。
        // (标签之间不能用 `{/* */}`, 那是子节点的写法 —— 这里要用 `//`,
        //  与上面 titleExtra / subtitle 那两段注释同一个写法。)
        right={
          <button
            type="button"
            onClick={refreshAll}
            disabled={refreshing}
            title="立刻重取一次(模拟盘 + 打分两份一起) —— 自动刷新的节奏不受影响"
            className="inline-flex items-center gap-1 rounded-btn border border-border bg-base px-2.5 py-1 text-[11px] text-muted transition-colors cursor-pointer hover:text-foreground disabled:opacity-60"
          >
            <RefreshCw className={cn('h-3 w-3', refreshing && 'animate-spin')} />
            {refreshing ? '刷新中' : '刷新'}
          </button>
        }
      />

      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto px-3 pb-4 pt-3 lg:px-4">
        {/* [R343] 自检条排在最顶且**不进任何折叠** —— 它一切正常时一个像素都不占,
            而它要说的是「你正在看的数字是几天前的」, 那句话被折起来就没有意义了。 */}
        {!!ov?.health && <TodayHealthBar h={ov.health} />}
        {/* [R347] 门槛 / 体检 / 板块筛选 —— 与今日总览共用那一份实现。用户:
            「门槛的东西非常重要, 体检和筛选功能也要能保留」。
            **它只作用于打分那一层**: 板块过滤改的是哪些票拿得到名次, 门槛改的是
            谁进候选池 —— 也就是只影响本页信号的**先后与标注**, 不影响谁在名单上
            (名单只由六态选, R344), 更不影响谁能出手。守卫钉着这条。 */}
        {/* [R358] 成绩与净值图**并进筛选那张卡**。用户: 「净值走势图和这两行收益
            都融合到页面开头的第一个卡片里面」→「我是想合并到筛选的卡片里面」。

            **`ov` 拿不到时要有退路。** 筛选条吃的是今日总览那份数据(打分那一层),
            而成绩吃的是模拟盘自己那份 —— 两份是各自独立的请求。挂在 `ov &&` 里
            的话, **打分那一层一挂, 整段成绩跟着一起消失**, 而它明明算出来了。
            那种消失不报错、也看不出是哪儿出的问题。 */}
        {ov
          ? <TodayControls d={ov} refetch={() => today.refetch()}
                           isFetching={today.isFetching} extra={cardBody} />
          : (
            <div className="rounded-card border border-border/60 bg-surface/40 px-4 py-3">
              {cardBody}
            </div>
          )}

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
            {/* [R358] 成绩与净值图搬到筛选那张卡里了 —— 见上面那段 */}
            {/* [R381] 「现在拿着」与「成交流水」并排 —— 两张都是 `min-w-[640px]`
                的窄表, 单列铺在 1600px 上时右边一半是空的, 而它们又都是"回头看"
                的东西, 本来就该放在一屏里对照着看(拿着的这几只, 是哪天买进来的)。

                **断点是算出来的**: 内容区 ≈ 视口 − 侧栏 224 − 左右留白 32,
                两列 640 + 12 的间隙要 1292 → 视口 ≥ 1548, 取 1560。
                侧栏收起时会更宽松, 那只会更好看。**万一还是窄了也不会坏** ——
                两张表自己带 `overflow-x-auto`, 最坏是卡片内部出现横向滚动条,
                不是版面塌掉。
                `items-start`: 两张表行数天生不对等(拿着几只 / 流水几十笔),
                拉成等高会让短的那张下面挂一大片空白。

                **第一版只是把两张表并排, 截图一看左边空了七百多像素** ——
                「拿着 6 只」对「流水 30 笔」, 右边排到底左边早就完了。所以把
                「有信号但没做成」也收进左列, 右列让流水竖跨两行。

                **第二版又推翻了一次。** 先试的是「按 `col-start`/`row-start` 摆位,
                DOM 顺序不动」—— 想法是让手机上的阅读顺序一个字不变。结果右列那块
                `row-span-2` 把第一行撑高了, 左列两块中间裂开一道四百像素的缝:
                跨行元素比它跨的两行都高时, 多出来的高度要分摊回那两行, 而分摊
                不听我的。**摆位摆不出来就别硬摆** —— 改成左列一个容器装两块,
                右列装流水, 高度各自算, 那道缝自然没有了。

                代价是单列时顺序变成 拿着 → 没做成 → 流水(原来流水在中间)。
                **这个代价是划算的**: 「没做成」是一句话的小结, 「流水」是几十行
                的长表, 短的放前面本来就更好读; 而真正有顺序讲究的是「规则排在
                最后」那一条, 它没动。 */}
            <div className="grid gap-3 min-[1560px]:grid-cols-2 min-[1560px]:items-start">
              <div className="min-w-0 space-y-3">
                <Holdings d={d} onOpen={(s) => navigate(`/stock-analysis?symbol=${s}`)} />
                <Skipped d={d} />
              </div>
              <div className="min-w-0">
                <Orders orders={d.orders} />
              </div>
            </div>
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
  /**
   * [R363] 关键价位弹窗。用户: 「点击这两列都要能像个股分析页面那样弹出弹窗」。
   *
   * **弹窗挂在这一层, 不是每行一个。** 三档几十上百行, 每行各挂一个
   * `<LevelsDialog>` 就是几十上百个常驻的 `AnimatePresence` 与 Esc 监听 ——
   * 而同一时刻只可能开着一个。行只负责报"点了谁"。
   *
   * `null` = 没开。弹窗常驻挂载、由 symbol 是否为 null 驱动, 关闭时退场动画
   * 才播得完(这是那个组件自己的约定, 不是这里的选择)。
   */
  const [levels, setLevels] = useState<{ symbol: string; name: string } | null>(null)
  const openLevels = (symbol: string, name: string) => setLevels({ symbol, name })
  /**
   * [R364] 逐日复盘弹窗 —— 动作那一格点开的就是它(用户: 「买入弹出的应该是
   * 这个弹窗」)。**与关键价位那个各是各的**, 两列点开不是同一张表(决策台 R51)。
   *
   * 两个弹窗**各存各的 state**, 不合成一个带 kind 的: 合起来的话"当前开着哪一个"
   * 与"开的是哪只票"就绑死在一起, 而它们本来就是两条互不相干的路; 更要紧的是
   * 那种写法下, 哪天想让两个都能开着(比如对着复盘看 K 线)要整个重写。
   */
  const [review, setReview] = useState<{ symbol: string; name: string } | null>(null)
  const openReview = (symbol: string, name: string) => setReview({ symbol, name })
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
  // [R355] 用户: 「这部分也想能折叠展开」。
  //
  // **R338 我为这一段写过「不许折叠」的守卫**, 理由是: 买入天天长出来, 卖出只在
  // 真触发那天冒一次, 折起来就等于又回到只剩买入。用户当面推翻它 —— 那条理由
  // 没有错, 但它不该替用户决定版面。
  //
  // 守卫因此**不是删掉而是换了个钉法**: 折叠可以, 但**折叠条本身必须把卖出侧的
  // 读数带上**(拿着几只 / 其中几只已经贴到离场线)。收起来之后那一行仍然在说
  // 「你手上有 10 只, 2 只快到线了」—— 那才是 R338 真正要保的东西, 而不是"不许折"。
  // 默认**展开**: 它是卖出那一侧唯一天天有位置的东西。
  const [mineOpen, setMineOpen] = useState(() => storage.flipMineOpen.get(true))
  const toggleMine = () => {
    setMineOpen((v) => {
      storage.flipMineOpen.set(!v)
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
  // [R355] 折叠条上那个「N 只贴近离场线」。**判据与行上那一档是同一条**
  // (`NEAR_EXIT`)—— 两处各写一份的话, 会出现"条上说 2 只、展开却只有 1 行标黄"。
  const mineNear = mine.filter((r) => r.gap_pct != null && Math.abs(r.gap_pct) <= NEAR_EXIT).length

  // [R383] **这一屏的形状** —— 三格各自"整屏有没有内容", 从**全部行**算一次,
  // 三段共用同一份。分段各算各的话, 「要动手」那段和「只是盯着」那段会用上
  // 不同的栅格, 上下两段列对不齐, 而且不报错。
  const shape: RowShape = {
    rank: rows.some((r) => conviction.get(r.symbol)?.rank != null),
    trend: rows.some((r) => conviction.has(r.symbol)),
  }
  // 走势那一列整屏都空时, 一行 620px 就排完了 —— 而宽屏上有 1600+。
  // 这种时候把行**排成两列**: 32 行的滚动直接砍一半。
  // 走势有内容时行本来就要吃满宽度, 保持单列。
  // 断点与 R381 那处并排用同一个(内容区 ≈ 视口 − 侧栏 224 − 留白 32)。
  const twoCol = !shape.trend
  const listCls = cn('divide-border/30', twoCol
    ? 'min-[1560px]:grid min-[1560px]:grid-cols-2'
    : 'divide-y')
  /** 两列时分隔线画在每个格子上 —— `divide-y` 在两列栅格里只会横着画, 竖缝没人画。 */
  const cellCls = (i: number) => twoCol
    ? cn('min-w-0 border-b border-border/30',
         i % 2 === 0 && 'min-[1560px]:border-r min-[1560px]:border-border/30')
    : undefined

  return (
    <>
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
            <div className={listCls}>
              {ordered.map((r, i) => (
                <div key={r.symbol} className={cellCls(i)}>
                  <SignalRow r={r} c={conviction.get(r.symbol)} shape={shape}
                             onOpen={openLevels} onReview={openReview} />
                </div>
              ))}
            </div>
          )}
          {ordered.length === 0 && (
            <div className="px-4 py-3 text-xs text-muted">
              今天没有要动手的 —— <b className="text-secondary">管住手</b>。
            </div>
          )}

          {/* [R338 → R355] 手上这些 —— 可折叠, 但**折叠条自己就是摘要**。
              买入天天长出来, 卖出只在真触发那天冒一次; 中间那段空白就是这里补的。
              所以收起来之后, 这一行仍然要说清「拿着几只、几只快到线了」——
              否则就是把 R338 做的事整个撤回去。
              不带动作徽标: 没转折就不出手, 这一段只回答「离场线在哪、还有多远」。 */}
          {mine.length > 0 && (
            <>
              <button
                type="button"
                onClick={toggleMine}
                aria-expanded={mineOpen}
                className="flex w-full items-center gap-1.5 border-t border-border/40 bg-elevated/20 px-4 py-2 text-[11px] text-secondary transition-colors hover:bg-elevated/40 cursor-pointer"
              >
                <ChevronDown className={cn('h-3 w-3 shrink-0 text-muted transition-transform duration-expand ease-smooth',
                  mineOpen && 'rotate-180')} />
                <Wallet className="h-3 w-3" />
                手上这些 · 跌破离场线才清仓
                <span className="ml-auto flex items-center gap-2 text-muted">
                  {/* 收起来也要看得见的那两个数 —— 卖出这一侧全靠它们 */}
                  {mineNear > 0 && (
                    <span className="text-warning">{mineNear} 只贴近离场线</span>
                  )}
                  <span className="opacity-70">{mine.length} 只</span>
                </span>
              </button>
              {mineOpen && (
                <div className={listCls}>
                  {mineSorted.map((r, i) => (
                    <div key={r.symbol} className={cellCls(i)}>
                      <SignalRow r={r} c={conviction.get(r.symbol)} shape={shape}
                                 onOpen={openLevels} onReview={openReview} />
                    </div>
                  ))}
                </div>
              )}
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
                <div className={cn('max-h-64 overflow-y-auto', listCls)}>
                  {idleSorted.map((r, i) => (
                    <div key={r.symbol} className={cellCls(i)}>
                      <SignalRow r={r} c={conviction.get(r.symbol)} shape={shape}
                                 onOpen={openLevels} onReview={openReview} />
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
        </>
      )}
    </section>
    {/* [R363] 与个股分析页**同一个组件** —— 那边点标的弹的就是它(R28)。
        一页只挂这一个: 同一时刻只可能开着一个弹窗。 */}
    <LevelsDialog symbol={levels?.symbol ?? null} name={levels?.name ?? ''}
                  onClose={() => setLevels(null)} />
    {/* [R364] 逐日复盘 —— 与决策台「趋势」列点开的**是同一个组件**。
        `tab="trend"` 落在趋势状态那一页: 动作那一格问的是「这个买入怎么来的」,
        答案是那张逐日表上的转折与买卖, 不是三档结论。
        它的 `symbol` 是必填的, 所以按决策台那边同一个写法条件渲染。 */}
    {review && (
      <StockReviewDialog symbol={review.symbol} name={review.name} tab="trend"
                         onClose={() => setReview(null)} />
    )}
    </>
  )
}

/** [R339] 离清仓线多近才算"贴着了"。**只用来上色, 不产生任何动作。** */
const NEAR_EXIT = 0.02

/**
 * [R383] 宽屏那套栅格 —— **按「这一屏到底有没有那些内容」选**, 不是写死一套。
 *
 * R356 定下定宽网格时的立论是「行与行天然对齐, 一列扫到底」—— 那条立论没错,
 * 但它要的是**行与行之间**对齐, 不是某一列必须占住某个绝对宽度。实机量出来的
 * 后果是: 一整屏 32 行全是「没进候选池」时, 走势那一格**独占 1068px 而且是空的**
 * (行宽 1688, 63% 在那儿闲着), 触发价那格也是空的 —— 而左边的内容 620px 就排完了。
 *
 * 所以: 整屏都没有的那一列, 宽度给 0。**同一屏里所有行用同一套模板**, 行与行
 * 照旧对齐 —— 变的是"这一屏需要几列", 不是"每行各自算各自的"。
 */
const ROW_GRID = {
  /** 这一屏有走势读数 —— 它吃 `1fr`, 行铺满整宽(R356 那版) */
  wide: 'sm:grid-cols-[3.5rem_minmax(9rem,11rem)_4.5rem_minmax(7rem,16rem)_minmax(0,1fr)_auto]',
  /** 整屏都没有走势 —— 那一格收成 0。触发价那列是 `auto`, 空着自己就收, 不用另开一套 */
  narrow: 'sm:grid-cols-[3.5rem_minmax(9rem,11rem)_4.5rem_minmax(7rem,16rem)_0_auto]',
} as const

/** 这一屏的行里, 哪几格真有东西 —— 决定用哪套栅格、要不要撑行高、能不能排两列。 */
export interface RowShape {
  /** 有没有任何一行拿得到名次(名次那一格是三行高的, 它决定要不要撑行高) */
  rank: boolean
  /** 有没有任何一行有走势读数 */
  trend: boolean
}

function SignalRow({ r, c, shape, onOpen, onReview }: {
  r: FlipTodaySignal; c?: TodayOpportunity
  /** [R383] 这一屏的形状 —— 同一屏所有行共用一份, 所以行与行仍然对齐 */
  shape: RowShape
  /** [R363] 点标的那一格 —— 弹关键价位(日 K + 压力支撑), 不跳页 */
  onOpen: (symbol: string, name: string) => void
  /** [R364] 点动作那一格 —— 弹逐日复盘。**与上面不是同一张表**, 见那一格的注释 */
  onReview: (symbol: string, name: string) => void
}) {
  const actionable = r.stage === 'flipped' && !!r.act
  // [R349 → R356] 「走势」那一格整格移植过来(用户: 「这一列也要有」)。
  //
  // 它与六态那句回答的不是同一个问题:
  //
  //     六态那句   今天要不要动手(已转折 / 盘中越线 / 还差多少)
  //     走势那格   凭什么是这一只(位置贵不贵 / 有没有量 / 离关键点多远)
  //
  // **R349 我据此把它放成第二行**, 怕两套判据的措辞并排读的人分不清哪句是哪套。
  // 那个顾虑本身没错, 但**分列同样能分清** —— 而分行要付的代价是行高随内容变
  // (有走势的行两行高, 没走势的一行高), 一屏扫下去参差不齐。代价更大。
  //
  // R356 起它是网格的**第五列**: 界线由栅格划, 不由换行划。
  // 只在这只票**进了候选池**时才有读数 —— 但**格子照样占住**, 见下面那段。
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
      {/* [R350 → R356] **定宽网格**: 每一列宽度固定, 行与行天然对齐, 一列扫到底。
          (R350 的起因: 原来是 `flex` + 触发价上一个 `ml-auto`, 宽屏上价格被甩到
          最右、中间空一条, 而各行按自己内容宽度排, 列也对不齐。)

          [R356] 用户: 「后面还有不少空间, 利用起来一行显示完整, 每行个股行高要一样」。
          **两处跟着改**:
          ① 去掉 `max-w-[72rem]` 并把走势并进同一行 —— 右边那片空地正好装它;
          ② 行高由 `min-h-[3.5rem]` 定死。名次那一格本身有三行高(名次/分/三条),
             而没进候选池的票只有两行字 —— **不定死的话, 行高就跟着"这只票有没有
             进候选池"变**, 一屏扫下去参差不齐。这正是用户说的第二件事。 */}
      {/* [R366] **同一串格子, 两套栅格。** 用户: 「手机端我只需要模拟盘页面和
          模拟盘里面的那两个弹窗」。

          六列那条最窄也要 3.5+9+4.5+7 rem 加五道间距 ≈ **444px**, 而手机竖屏
          是 390px —— 横向必然撑破。

          **没有另写一份手机版的行。** 六个格子、次序、内容全都没动, 只是窄屏
          换一张三列的栅格, 靠 `row-span` / `col-span` 让它们自己落成一张卡:

              [名次] 中际旭创 300308.SZ  [买入]
              [    ] 已转折 · 现在是自然回升
              走势词 …
              触发 82.50 · 现 83.10

          另写一份的代价是**两套版面各自演化**, 哪天只改了一边, 手机上看到的与
          电脑上不是同一件事, 而两边都不报错 —— 这仓库从 R212 起一直在躲这个坑。

          `min-h` 与 `items-center` 只在宽屏生效: 卡片式那版行高本来就随内容,
          定死反而会在只有两行字时留一截空。

          [R381] **六态那一列的上限 9rem → 16rem。** 用户: 「合理利用显示空间」。
          9rem = 144px 装不下「按现价会转折 —— 收盘还站在这边才算数」, 于是盘中
          越线那几行**一直被截成「…收盘还...」** —— 而截断的那半句正是这一档唯一
          要说的话(收盘站不住就不算数)。更别扭的是: 它右边那格(走势)在没进候选池
          的行上是**空的**, 宽屏上白白空着六百来像素, 左边却在截字。
          16rem = 256px 刚好装下那句话(20 个字 × 11px)。**仍然是定宽列不是 `1fr`**,
          行与行照旧对齐; `truncate` 也留着 —— 窄屏上它还得兜底。 */}
      <div className={cn(
        'grid grid-cols-[3.5rem_minmax(0,1fr)_auto] gap-x-3 gap-y-1 text-xs sm:items-center sm:gap-y-0',
        shape.trend ? ROW_GRID.wide : ROW_GRID.narrow,
        // [R383] 行高只在**真有名次**时撑 —— 名次那一格是三行高(名次/分/三条维度),
        // 撑行高是为了让"有名次"和"没名次"的行一样高。整屏都没名次时, 每行只有
        // 两行字, 再撑 3.5rem 就是每行白送 26px: 32 行就是 800 多像素的滚动。
        shape.rank && 'sm:min-h-[3.5rem]',
      )}>
        {/* [R345] 「名次」那一格整格移植自今日总览 —— 用户: 「这一列要移植」。
            **不是只搬个数字**: 名次下面那三条维度条(红=趋势 45% / 蓝=量能 30% /
            黄=位置 25%)才是它能被读懂的原因 —— 离开那三条颜色, 上面那个名次
            就只是个号码, 说不出"为什么是这个名次"。
            它**不是动作**: 拿不到名次的票照样在名单里, 只是排在本档末尾。
            [R350] 这一格无论有没有都占住那 3.5rem —— 空着也要占位, 否则有名次的
            行和没名次的行后面所有列全都错开。
            [R360] **挪到标的前面, 成了整行的第一格**(用户: 「这列内容统一放到
            股票名称前面」)。它原来夹在动作与六态之间, 而它回答的是「凭什么是
            这一只」—— 那个问题得在读到代码之前就摆在眼前, 排在后面等于先认票
            再补理由。 */}
        {/* 窄屏竖跨两行 —— 右边那两行(标的+动作 / 六态)共用它这一格 */}
        <div className="row-span-2 sm:row-span-1">
        {c?.rank != null ? (
          <ScoreCell o={c} rank={c.rank} total={c.rank_total ?? 0} />
        ) : actionable ? (
          <span className="text-center text-[9px] leading-tight text-muted/60"
                title="没过打分那三道硬门槛, 所以没有名次 —— 但它转折了, 该动手还是要动手">
            没进
            <br />候选池
          </span>
        ) : <span />}
        </div>

        {/* [R363] 标的可点 —— 弹关键价位(日 K + 压力支撑 + 六态趋势条),
            与个股分析页点标的弹出来的**是同一个组件**(R28 那一个, 已摘成共用)。
            不跳页: 跳走之后回来, 折叠状态、滚动位置、这一屏的上下文全没了。 */}
        <button type="button" onClick={() => onOpen(r.symbol, r.name)}
                title={`看 ${r.name} 的日 K 与关键价位`}
                className="cursor-pointer truncate text-left transition-colors hover:text-sky-300">
          <SymbolCell symbol={r.symbol} name={r.name} />
        </button>

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

        {/* [R364] **六态那句可点, 弹逐日复盘。**
            用户: 「还是别点买入了, 点「已转折 · 现在是自然回升」这样更合理」。

            R363 我把这个入口挂在了动作那一格上, 并为此写了一整段"别让它看起来
            像下单按钮"的辩解 —— 用户直接把它挪开了。**要辩解才站得住的设计,
            多半本来就不该那么放**: 一个印着「买入」两个字的格子, 无论加多少
            title 都在暗示点它会下单。

            挪到这里反而**更对得上内容**: 这一格印的就是「已转折 · 现在是自然
            回升」, 而复盘弹窗那张逐日表正是把每一天的六态与转折排开 —— 点一句
            状态, 看这个状态是怎么走到今天的。这也正是决策台 R51 的规矩:

                标的那格   这只票现在贵不贵、关键价位在哪  → 关键价位(日 K)
                六态那句   这个状态是怎么走到今天的        → 逐日复盘(趋势页)

            **动作那一格因此退回不可点**, 一个像素没动。 */}
        <button type="button" onClick={() => onReview(r.symbol, r.name)}
                title={`看 ${r.name} 的逐日复盘 —— 这个状态是怎么走到今天的`}
                className="col-span-2 min-w-0 cursor-pointer truncate text-left text-[11px] text-secondary transition-colors hover:text-sky-300 sm:col-span-1">
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
        </button>

        {/* [R356] 走势并进同一行的第五列 —— 原来它是第二行, 害得行高随内容变。
            没进候选池的票这一格是空的, 但**格子照样占住**, 行高不受影响。 */}
        <span className="col-span-3 min-w-0 text-[11px] sm:col-span-1">
          {c && <TrendCell o={c} />}
        </span>

        {/* [R350] 不再 `ml-auto` —— 它是网格的最后一列, 位置由栅格决定 */}
        <span className="col-span-3 whitespace-nowrap text-left text-[10px] tabular-nums text-muted sm:col-span-1 sm:text-right">
          {r.flip_price != null && <>
            触发 {r.flip_price.toFixed(2)}
            {r.ref_price != null && <> · 现 {r.ref_price.toFixed(2)}</>}
            {!r.live && <span className="ml-1 text-warning/70">昨收口径</span>}
          </>}
        </span>
      </div>
    </div>
  )
}

/**
 * [R353] 可输入的参数格。用户: 「这里我要能配置而不是选择或者默认」。
 *
 * 原来是三个 `<select>`, 只能在几个写死的档位里挑 —— 本金想填 30 万、最多持有
 * 想填 7 只、回溯想填 18 个月, 一个都做不到。
 *
 * ## 为什么不是「边敲边生效」
 *
 * 这三个值都进 `queryKey`。直接绑 `onChange` 的话, **敲「100000」这七个字符会
 * 依次触发七次请求**, 而每次请求是全部自选的六态 + 一整轮回测 —— 打到后端就是
 * 七次全量重算。所以本地先存草稿, **失焦或回车才提交**。
 *
 * ## 越界怎么办
 *
 * 钳到合法区间而不是报错或者置空: 后端的边界是硬的(本金 > 0、最多持有 1~50、
 * 回溯 0.5~10 年), 填了 999 只就钳成 50 —— **让人看见它被钳到哪儿**, 比弹一句
 * 「超出范围」再把输入清空有用得多。填了不是数字的东西就退回当前值。
 *
 * `step` 给出这一栏的自然粒度(本金 5 万、持有 1 只、回溯半年), 上下箭头与滚轮
 * 因此是可用的 —— 想微调的人不必每次都全选重打。
 *
 * ## 这里**没有**格式化钩子, 是故意的
 *
 * [R354] 第一版给它开了个 `fmt`, 本金那格传的是千分位的 `money()` —— 于是
 * `value` 收到的是 `"1,000,000"`, 而 **`<input type="number">` 认不了带逗号的
 * 字符串, 直接渲染成一个空框**。用户截图里那个空的本金框就是这么来的:
 * 值一直在(查询照常按 100 万跑), 只是**看上去像没填**。
 *
 * 教训不是"把逗号去掉"而是**别给数字输入框留格式化的口子** —— 数字要好读就
 * 换单位(本金因此改成以「万」计), 不是往框里塞排版。
 */
function NumberField({ label, value, onChange, min, max, step, width = 'w-20', suffix, title }: {
  label: string
  value: number
  onChange: (v: number) => void
  min: number
  max: number
  step: number
  width?: string
  /** 单位, 跟在输入框右边 —— 放进框里会被光标挤 */
  suffix?: string
  /** [R366] 悬停/长按的说明 —— 窄屏藏起来的那句话挂在这儿 */
  title?: string
}) {
  const [draft, setDraft] = useState<string | null>(null)
  const commit = () => {
    if (draft === null) return
    const n = Number(draft)
    setDraft(null)
    if (!Number.isFinite(n)) return          // 不是数字 —— 退回当前值, 不清空
    const clamped = Math.min(max, Math.max(min, n))
    if (clamped !== value) onChange(clamped)
  }
  return (
    <label title={title} className="inline-flex items-center gap-1 text-muted">
      {label}
      <input
        type="number"
        inputMode="decimal"
        min={min}
        max={max}
        step={step}
        value={draft ?? String(value)}
        onFocus={() => setDraft(String(value))}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === 'Enter') { e.currentTarget.blur() }
          if (e.key === 'Escape') { setDraft(null); e.currentTarget.blur() }
        }}
        title={`${min} ~ ${max}${suffix ?? ''} —— 超出会被钳到边界; 回车或点别处生效`}
        className={cn(width, 'rounded-btn border border-border bg-base px-1.5 py-0.5 text-right text-[10px] text-foreground outline-none focus:border-accent/50')}
      />
      {suffix && <span className="text-[10px]">{suffix}</span>}
    </label>
  )
}

/**
 * [R332 → R357] 逐月收益那一条。用户: 「最好是每个月的收益单独计算」。
 *
 * ## R332 那两格为什么退役
 *
 * R332 给的是「近一月 / 近三月」两个**滚动窗口**(最近 20 / 60 个交易日)。
 * 它当时要解决的问题没有错 —— 两年的总收益回答不了"我最近做得怎么样"。
 * 但那两个窗口**重叠**: 近三月把近一月整个包在里面。
 *
 *     九月 +10% / 八月 -4% / 七月 -4%   →   印出来是「近一月 +10% / 近三月 +2%」
 *
 * 读的人**没有任何办法**从这两个数里还原出七月和八月各自发生了什么 —— 而
 * 「哪个月在亏」正是按月看的全部意义。改成自然月之后每个数只属于它自己那一段。
 *
 * ## 数不在这里算
 *
 * 逐月收益由后端 `flip_portfolio._monthly` 给(基准取上月末、首尾标残月那两条
 * 都在那儿, 有守卫钉着)。**前端不自己再切一遍曲线** —— 同一件事两处算, 哪天
 * 基准口径改了必然漂, 而且不会有任何东西报错。
 */
/**
 * [R359] 参数条 —— 本金 / 最多持有 / 回溯。用户: 「参数框也并进来」。
 *
 * 它原来在**页头最右边**, 与它算出来的那些数字隔着大半个屏幕: 改完一个框, 眼睛
 * 要横穿整页才看得到结果变了什么。现在它就贴在成绩上方。
 *
 * **这三个框是这一页唯一喂进回测的输入** —— 同一张卡里那排板块/门槛不是同一回事:
 * 那些只改打分那一层的标注(谁拿得到名次), **一分钱都不进回测**。所以这一条
 * 单独一行、与筛选条之间隔着分隔线, 不与板块按钮并排 —— 并排会让人以为筛掉
 * 几个板块曲线也会跟着变。行尾那句话把这件事直接说出来: 两样东西并进同一张卡
 * 之后, "它们互不相干"这件事不说就没人知道。
 */
function ParamBar({ capital, maxPositions, years, onCapital, onMaxPositions, onYears }: {
  capital: number; maxPositions: number; years: number
  onCapital: (v: number) => void
  onMaxPositions: (v: number) => void
  onYears: (v: number) => void
}) {
  return (
    <div className="flex flex-wrap items-center gap-1.5 text-[10px]">
      {/* [R353] 三个都改成可输入。上下界与后端逐个对齐:
          本金 > 0(给 1 万下限, 再低连一手都买不起);
          最多持有 1~50(`flip_portfolio.MAX_POSITIONS_CAP`);
          回溯 0.5~3 年(`flip_paper.MIN_YEARS` / `MAX_YEARS`)。
          **前端钳到同一个区间, 不是等后端 422** —— 那种报错只会说
          「Input should be less than or equal to 50」, 读的人不知道该填多少。 */}
      {/* [R354] 本金**以「万」计**。用户: 「我实际本金不超 100 万, 要合适我真实情况」。
          原来按元填, 100 万写成 1000000 —— 七位数在一个小框里既难读也难改,
          而且上限给到了 1 亿, 与真实量级差两个数量级。
          换成万之后数字只剩三位, 一眼就是「100 万」; 区间 1~1000 万留了余量
          但不再荒唐, 步进 5 万是散户实际会调的粒度。
          **换算只在这一处**: 存进 state 与送给后端的仍然是元。 */}
      <NumberField label="本金" value={Math.round(capital / 10_000)}
                   onChange={(v) => onCapital(v * 10_000)}
                   min={1} max={1000} step={5} width="w-16" suffix="万" />
      <NumberField label="最多持有" value={maxPositions} onChange={onMaxPositions}
                   min={1} max={50} step={1} width="w-14" suffix="只" />
      {/* [R366] 那句「筛选不进回测」在窄屏是藏起来的, 所以挂一份到这里的 title 上
          —— 藏起来不等于没说过 */}
      <NumberField label="回溯" value={years} onChange={onYears}
                   min={YEARS_MIN} max={YEARS_MAX} step={0.5} width="w-14" suffix="年"
                   title="回溯几年。板块与门槛只改打分的标注, 不进这条曲线" />
      {/* [R366] 窄屏藏掉这句 —— 手机上一行只放得下那三个框, 这句会换行占掉一整行。
          **它不是可有可无**(R359 特意加的), 所以不是删: 宽屏照旧, 窄屏挪进
          「回溯」那个框的 title 里, 长按仍看得到。 */}
      <span className="ml-auto hidden text-muted/70 sm:inline">
        上面那排板块与门槛只改打分的标注, 不进这条曲线
      </span>
    </div>
  )
}

function MonthStrip({ months }: { months: FlipPaperData['monthly'] }) {
  if (!months.length) return null
  // 最大月度波动 —— 柱高按它归一, 于是**柱子之间可比**。拿固定刻度的话,
  // 一个 ±2% 的年份会所有柱子都贴着底, 什么也看不出来。
  const peak = Math.max(...months.map((m) => Math.abs(m.ret)), 0.01)
  return (
    /* [R358] 这一块现在长在筛选那张卡**里面** —— 自己不再是一张卡, 不然就是
       卡中卡(一圈边框套一圈边框)。 */
    <section className="overflow-hidden">
      <div className="mb-2 flex items-center gap-0.5 text-[10px] text-muted">
        逐月收益
        <Hint title={'**每个月单独算, 月与月之间不重叠** —— 这个月的收益 =\n月末净值 / 上月末净值 - 1(第一个月的基准是本金)。\n\n基准取**上月最后一天**而不是本月第一天: 收益要算这一段期间的变化,\n拿本月第一个交易日当基准会把那一天自己的涨跌吃掉。\n\n**打叉的是残月**: 回测窗口从月中切进来(第一个月),\n或者这个月还没走完(最后一个月)—— 它们不该拿去和整月比。'} />
        <span className="ml-1 opacity-70">{months.length} 个月 · 柱高按最大月度波动归一</span>
      </div>
      <div className="flex items-end gap-1 overflow-x-auto">
        {months.map((m) => {
          const up = m.ret >= 0
          return (
            <div key={m.month} className="flex min-w-[2.75rem] flex-1 flex-col items-center gap-1"
                 title={`${m.month} · ${m.days} 个交易日${m.partial ? '(残月)' : ''}\n月末净值 ${money(m.nav)}`}>
              <span className={cn('text-[10px] font-semibold tabular-nums',
                up ? 'text-bull' : 'text-bear', m.partial && 'opacity-60')}>
                {pct(m.ret, 1)}
              </span>
              {/* 柱子从中线往上/往下长 —— 亏的月份自己往下掉, 不用先读那个负号 */}
              <div className="flex h-8 w-full flex-col justify-center">
                <div className="flex h-4 items-end">
                  {up && <div className={cn('w-full rounded-t-sm bg-bull/60', m.partial && 'opacity-50')}
                              style={{ height: `${Math.max(2, (m.ret / peak) * 100)}%` }} />}
                </div>
                <div className="flex h-4 items-start">
                  {!up && <div className={cn('w-full rounded-b-sm bg-bear/60', m.partial && 'opacity-50')}
                               style={{ height: `${Math.max(2, (-m.ret / peak) * 100)}%` }} />}
                </div>
              </div>
              <span className={cn('text-[9px] tabular-nums text-muted', m.partial && 'opacity-60')}>
                {/* 一月与跨年的那个月印出年份, 其余只印月 —— 一排 12 格里
                    「2026-01」占的宽是「03」的三倍, 而年份一年只需要说一次 */}
                {m.month.endsWith('-01') ? m.month.replace('-', '/') : m.month.slice(5)}
                {m.partial && <span className="text-warning/70" title="残月">✕</span>}
              </span>
            </div>
          )
        })}
      </div>
    </section>
  )
}

/**
 * [R358] 成绩那一块 —— **整块并进筛选那张卡**。
 *
 * 用户: 「净值走势图和这两行收益都融合到页面开头的第一个卡片里面」→
 * 「我是想合并到筛选的卡片里面」。
 *
 * 在这之前它是**三张各自独立的卡**(逐月 / 两行读数 / 净值图)竖着摞在页面中段,
 * 三圈边框、三个背景、三段外边距。并进去之后卡壳只剩一层, 内部用分隔线分块。
 *
 * ## 净值图默认收起, 而且是**真的不挂载**
 *
 * 用户要的是默认收起。这里有个会**静默失败**的坑: `useECharts` 的初始化 effect
 * 依赖数组是 `[]`, 而且 `if (!chartRef.current) return` —— 图表的 div 若在首次
 * 渲染时不存在, 那个 effect 就地返回, **之后再也不会重跑**。于是拿 `hidden`
 * 之类的办法藏起来再展开, 展开后是一片空白: 不报错、控制台干净、数据也都在。
 *
 * 所以折叠必须**连 `<NavChart>` 一起不渲染**, 展开时整个组件重新挂载, init
 * effect 才会带着一个真实的 ref 跑一遍。守卫钉着这条。
 */
function Summary({ d }: { d: FlipPaperData }) {
  const s = d.stats
  const [navOpen, setNavOpen] = useState(() => storage.flipNavOpen.get(false))
  const toggleNav = () => setNavOpen((v) => { storage.flipNavOpen.set(!v); return !v })
  return (
    <div className="space-y-3">
      {/* [R357] 逐月排在最前 —— 用户每天打开最先要问的是"最近哪个月在亏" */}
      <MonthStrip months={d.monthly} />

      {/* [R362] **六格并成一行**(用户: 「把图片显示的内容用一行显示」)。
          原来是两排: 上排两格说"当下"(现在拿着 / 最后一天), 下排四格说"整段"
          (总收益 / 最大回撤 / 完整买卖 / 胜率)。分两排的立论是 R332 立的
          ——「当下排在整段之前」, 那条**次序**仍然在(两格仍排在四格左边),
          只是不再靠换行来表达: 六格一行, 左两格当下、右四格整段, 中间由分隔线划。
          分两排真正的代价是**上排那两格各占半屏**, 一个「10 只」霸着 1000px。

          窄屏仍然换行: 2 格 → 3 格 → 6 格。`divide-y` 只在换行的档位上要,
          六格一行时关掉, 否则会在唯一那一行下面画一条多余的线。 */}
      <section className="grid grid-cols-2 divide-x divide-y divide-border/30 overflow-hidden rounded-card border border-border/40 bg-base/30 sm:grid-cols-3 lg:grid-cols-6 lg:divide-y-0">
        <Stat label="现在拿着" value={`${d.positions.length} 只`}
              sub={`仓位 ${d.nav.length ? pct((d.nav[d.nav.length - 1].market_value / d.nav[d.nav.length - 1].nav), 0) : '—'} · 现金 ${money(d.nav.at(-1)?.cash)}`}
              hint={'这是**当下**的仓位, 与上面那条逐月一样看的是现在;\n同一行右边那四格才是整个回溯窗口的成绩。'} />
        <Stat label="最后一天" value={d.as_of ?? '—'}
              sub={`回溯 ${d.nav[0]?.date ?? '—'} 起`}
              hint={'日 K 要等收盘后落盘 —— 所以这里通常是上一个交易日,\n今天的要等 20:00 之后才会进来。'} />
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

      {/* [R358] 净值走势 —— **默认收起**(用户点的名)。
          折叠条上带着这条曲线自己的读数(起止那一段), 上面那排数字它不重复。 */}
      {!!d.nav.length && (
        <section className="overflow-hidden rounded-card border border-border/40 bg-base/30">
          {/* 折叠条的样子与 R355「只是盯着」那条**同一套**: 旋转的 ChevronDown +
              「收起/展开」+ 右边一句摘要。同一页上两种折叠长两个样, 读的人要认两次。 */}
          <button
            type="button"
            onClick={toggleNav}
            aria-expanded={navOpen}
            className="flex w-full items-center gap-1.5 px-3 py-2 text-[11px] text-muted transition-colors hover:bg-elevated/40 hover:text-foreground cursor-pointer"
          >
            <ChevronDown className={cn('h-3 w-3 transition-transform duration-expand ease-smooth',
              navOpen && 'rotate-180')} />
            {navOpen ? '收起' : '展开'}净值走势
            <span className="ml-auto opacity-70">
              {d.nav[0]?.date} → {d.as_of ?? d.nav.at(-1)?.date}
            </span>
          </button>
          {/* **连组件一起不渲染, 不是藏起来** —— `useECharts` 的 init effect 依赖
              数组是 `[]` 且 ref 为空就地返回, 藏起来再展开会是一片空白且不报错。
              见 `Summary` 的 docstring。 */}
          {navOpen && <NavChart d={d} />}
        </section>
      )}
    </div>
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
    /* [R358] 标题与卡壳都归折叠条了 —— 这里只剩图本身。
       **这个组件只在展开时才被挂载**(见 `Summary`), 所以 `useECharts` 的 init
       effect 一定是带着真实的 ref 跑的。 */
    <>
      <div className="border-t border-border/40 px-3 pb-1 pt-2 text-[10px] text-muted">
        默认看最近半年 · 拖下面那条可回到 {d.nav[0]?.date} 起的全程
      </div>
      <div ref={ref} className="h-[280px] w-full" />
    </>
  )
}

function Holdings({ d, onOpen }: { d: FlipPaperData; onOpen: (s: string) => void }) {
  const holdingDays = useMemo(
    () => getFlipHoldingDays(d.orders, d.nav, d.as_of),
    [d.orders, d.nav, d.as_of],
  )
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
          <table className="w-full min-w-[640px] text-xs">
            <thead className="text-[10px] text-muted">
              <tr className="text-left">
                <th className="px-4 py-1.5 font-normal">标的</th>
                <th className="w-24 whitespace-nowrap px-2 py-1.5 text-right font-normal"
                    title="买入当天算第 1 个交易日，统计至模拟盘最后一天；清仓后重置">
                  持有天数
                </th>
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
                  <td className="whitespace-nowrap px-2 py-1.5 text-right tabular-nums text-secondary">
                    {holdingDays.has(p.symbol) ? `${holdingDays.get(p.symbol)} 天` : '—'}
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
      {/* [R381] 「原因 + N 次」每行只有十几个字, 单列排下来右边整片是空的。
          改成两列 —— 每一行的内容一个字没动。
          下面两条(取不到日线 / 还在等成交)的值是一串股票名, 会很长,
          所以**它们不进多列**, 各自独占一整行。

          **列数只到 2, 不跟着视口往上加。** 这一块从 R381 起活在宽屏的**半幅
          左列**里, 而 `sm:`/`xl:` 这些断点量的是**视口**不是它自己的宽度 ——
          第一版写到 `2xl:grid-cols-4`, 1600px 上实际只有 650px 可用, 四列挤得
          「6 次」两个字都拆行了。容器查询能量准, 但为这一块引一套新机制不值,
          两列在半幅和全幅下都站得住。

          原因那几句长短不一(「封板挂不进去」 vs 「一直封到反向转折, 这张单作废」),
          所以次数靠右对齐、标签占剩下的宽 —— 标签自己换行, 次数永远在同一条竖线上。 */}
      <div className="px-4 py-2.5 text-[11px]">
        <div className="grid gap-x-8 gap-y-1.5 sm:grid-cols-2">
          {Object.entries(byReason).map(([r, n]) => (
            <div key={r} className="flex items-baseline justify-between gap-3">
              <span className="min-w-0 text-secondary">{WHY_CN[r] ?? r}</span>
              <span className="shrink-0 tabular-nums text-muted">{n} 次</span>
            </div>
          ))}
        </div>
        {d.missing.length > 0 && (
          <div className="flex items-start gap-2 pt-2">
            <span className="min-w-[9rem] shrink-0 text-warning">取不到日线</span>
            <span className="text-muted">
              {d.missing.join('、')} —— 这几只没进这次模拟, 不是它们没信号
            </span>
          </div>
        )}
        {d.pending.length > 0 && (
          <div className="flex items-start gap-2 pt-2">
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
      {/* [R381] 这一段是全页最浪费的一块: 七条「标签 + 一行值」竖着排在 1600px 上,
          每行右边空掉三分之二, 还把下面的东西挤出首屏。改成两列 / 宽屏三列。
          **口径一个字没改**, 七条还是那七条, 次序也没动 —— 这是查证用的清单,
          顺序本身就是信息(先说信号怎么来, 再说怎么成交)。多列按**列优先**
          没有意义, 所以用默认的行优先: 从左到右读, 和原来从上到下读是同一串。

          「成本」那条值最长(佣金/印花税/滑点/一手), 让它在多列时独占一整行,
          免得它一个人把整行的行高撑成两倍。

          底下三段告诫是成段的话, 不是清单 —— 它们走自己的两列, 且保持顺序。 */}
      <div className="px-4 py-3 text-[11px] leading-relaxed">
        <div className="grid gap-x-8 gap-y-2 md:grid-cols-2 2xl:grid-cols-3">
          <Rule k="信号" v={r.signal} />
          <Rule k="成交" v={r.execute} />
          <Rule k="方向" v={r.direction.join('; ')} />
          <Rule k="仓位" v={`${r.sizing} —— 现在是 ${d?.max_positions ?? '—'} 只`} />
          <Rule k="标的" v={`${r.universe}${d ? ` —— 现在 ${d.symbols.length} 只` : ''}`} />
          <Rule k="不做空" v={r.short} />
          <div className="md:col-span-2 2xl:col-span-3">
            <Rule k="成本" v={`佣金 ${(r.costs.commission * 10000).toFixed(1)}‱ 双边 · 印花税 ${(r.costs.stamp_tax * 10000).toFixed(1)}‱ 卖出单边 · 滑点 ${r.costs.slippage_bps}bp · ${r.costs.lot} 股一手`} />
          </div>
        </div>
        <div className="mt-3 grid gap-x-8 gap-y-1.5 border-t border-border/40 pt-2.5 text-muted xl:grid-cols-2">
          <p>{r.caveat}</p>
          <p>{r.vs_flip_trades}</p>
          <p className="xl:col-span-2">{r.why_no_state}</p>
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
      {/* [R362] 六格 —— **跟着 `Summary` 那一排走**。少画两格就是先许诺一个版面
          再食言(与下面净值图那块同一条纪律)。栅格断点也要逐个对上, 否则骨架
          在窄屏上换行的位置与真东西不一样, 数据到位时版面会跳一下。 */}
      <div className="grid grid-cols-2 divide-x divide-y divide-border/30 overflow-hidden rounded-card border border-border/60 bg-surface/40 sm:grid-cols-3 lg:grid-cols-6 lg:divide-y-0">
        {Array.from({ length: 6 }, (_, i) => (
          <div key={i} className="space-y-1.5 px-4 py-2.5">
            <Skeleton w="w-12" h="h-2.5" />
            <Skeleton w="w-16" h="h-5" />
            <Skeleton w="w-20" h="h-2.5" />
          </div>
        ))}
      </div>
      {/* [R358] **那块 240px 的曲线骨架撤掉了。**
          净值图现在默认收起 —— 画一块曲线大小的灰块, 等数据到了那儿却是一条
          折叠条, 就是**先许诺一个版面然后食言**, 比直接转圈更糟。
          换成一条折叠条大小的骨架, 与真到位的东西对得上。 */}
      <div className="rounded-card border border-border/40 bg-base/30 px-3 py-2">
        <Skeleton w="w-32" h="h-3" />
      </div>
    </div>
  )
}
