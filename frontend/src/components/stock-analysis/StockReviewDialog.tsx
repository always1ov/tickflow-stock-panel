/**
 * [R48] 逐日复盘弹窗 —— 决策台「趋势」「结论」两列点进去看的就是这个。
 *
 * [R51] 两列点开的**不是同一张表**。原来两边都弹出同一份逐日表格, 结论那一列
 * 点进去只是在趋势表最右边多一个 4 字徽标, 等于把列里已经有的东西又抄了一遍。
 * 现在分成两个视图, 各答各的问题:
 *
 *   · 趋势视图(从「趋势」列点进来): 这个状态是怎么走到今天的。一张逐日表 ——
 *     日期/收盘/涨跌(带涨停标)/状态/结论, 转折那天单独标出来。
 *   · 结论视图(从「结论」列点进来): 把每天的**悬停卡片**摊开。徽标背后那三段
 *     (怎么做/为什么/依据)才是这一列真正的内容, 复盘时要看的正是它们。
 *     连续同一档的天合并成一段 —— 「强势深调」连着 4 天时铺 4 张一模一样的
 *     卡片才是真的重复; 合成一段再标出天数, 反而看得出这一档持续了多久。
 *
 * [R52] 趋势表里保留「结论」徽标列, 与结论视图不冲突: 那边是摊开的卡片流
 * (每一档说了什么、之后走成什么样), 这里只是让状态和当天的通道位置能横着
 * 对上一眼 —— "这个板是在什么位置上出的"、"转折那天通道在哪"。当初判定它
 * 重复, 是因为那时结论视图跟趋势表长得一模一样; 现在两边内容已经分开了。
 *
 * 两个视图共用同一份数据(一次请求), 顶部可以互相切换 —— 从哪一列进来只决定
 * 默认落在哪个视图, 不把人锁死。
 *
 * ## [R228] 27 种组合速查并了进来, 成为第三个页签
 *
 * 用户: 「这两个弹窗也整合到一起, 外部入口就变成一个按钮了, 这样打开好看」。
 *
 * 原来是**两个各自铺满屏幕的模态**, 而且从决策台「走势」那一格里用两个挨着的
 * 按钮分别打开 —— 点六态徽标出复盘、点它右边的阶段出组合速查。这两个按钮长得
 * 不像按钮, 也没有任何东西告诉人它们通向不同的地方。
 *
 * 三个页签讲的其实是同一只票的同一件事, 只是切法不同:
 *
 *     趋势状态   六态在时间轴上怎么走的        (纵向 · 六态)
 *     通道结论   通道结论在时间轴上怎么走的     (纵向 · 通道)
 *     组合速查   通道的 27 格里我在哪一格       (横向 · 通道)
 *
 * 并进来之后, 组合速查的 `geo`/`runs` 直接取复盘接口的 `channel` —— 不再由
 * 决策台把行数据透传进来。`review_service._channel` 的末日读数与逐日表末行
 * 走同一条路, 所以三个页签看到的是同一天的同一份读数, 不会出现"这个弹窗说
 * 挤了 12 天, 那个说 9 天"。
 */
import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { CalendarRange, Loader2, X } from 'lucide-react'
import { api, type KeltnerVerdict, type ReviewRow, type StockReview } from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import { cn } from '@/lib/cn'
import { storage } from '@/lib/storage'
import { trendBadgeCls } from '@/components/stock-analysis/TrendStateBar'
import { VerdictHover } from '@/components/stock-analysis/VerdictHover'
import { ComboView } from '@/components/stock-analysis/decision-board/ComboView'
import { FlipTradesBar, FlipTradeCells, FlipTradeLine, legsByFlipDate } from '@/components/stock-analysis/FlipTradesPanel'
import { ReviewHelpSheet, HelpButton } from '@/components/stock-analysis/ReviewHelpSheet'
import { HeadRow, HEAD_CARD } from '@/components/stock-analysis/ReviewHeadRow'
import { StateTimeline } from '@/components/stock-analysis/StateTimeline'
import { ReviewDisclosure } from '@/components/stock-analysis/ReviewDisclosure'
import {
  BAND_CN, TREND_LEGEND, VERDICT_BAR, VERDICT_LEGEND,
  rangeHint, trendCells, verdictCells,
} from '@/lib/reviewTimeline'

export type ReviewTab = 'trend' | 'verdict' | 'combo'

// 与决策台「结论」列同一套配色 —— 两处不一样的话, 翻历史时得先在脑子里做一次换算
const VERDICT_CLS: Record<KeltnerVerdict['tone'], string> = {
  sell: 'border-red-400/40 bg-red-400/10 text-red-400',
  buy: 'border-sky-400/40 bg-sky-400/10 text-sky-300',
  hold: 'border-amber-400/40 bg-amber-400/10 text-amber-400',
  avoid: 'border-border bg-base text-muted',
  watch: 'border-border bg-elevated/60 text-secondary',
}

const RANGES = [60, 120, 250] as const

function pct(v: number | null | undefined, digits = 1): string {
  return v == null ? '—' : `${v > 0 ? '+' : ''}${(v * 100).toFixed(digits)}%`
}

// A股习惯: 涨红跌绿
function chgCls(v: number | null | undefined): string {
  if (v == null || v === 0) return 'text-muted'
  return v > 0 ? 'text-red-400' : 'text-emerald-400'
}

/** 涨停/跌停/炸板标。连板时把第几个板写出来 —— 复盘时"3 板"和"1 板"完全是两回事 */
function LimitTag({ r }: { r: ReviewRow }) {
  if (r.limit_up) {
    return (
      <span
        className="ml-1 inline-flex whitespace-nowrap rounded border border-red-400/50 bg-red-400/15 px-1 text-[9px] text-red-300"
        title={`涨停${r.limit_streak > 1 ? ` · 第 ${r.limit_streak} 个板` : ''}`}
      >
        {r.limit_streak > 1 ? `${r.limit_streak}板` : '涨停'}
      </span>
    )
  }
  if (r.limit_down) {
    return <span className="ml-1 inline-flex rounded border border-emerald-400/50 bg-emerald-400/15 px-1 text-[9px] text-emerald-300">跌停</span>
  }
  if (r.broken_limit_up) {
    return (
      <span
        className="ml-1 inline-flex whitespace-nowrap rounded border border-amber-400/40 bg-amber-400/10 px-1 text-[9px] text-amber-300"
        title="炸板 —— 盘中最高触及涨停但收盘没封住"
      >
        炸板
      </span>
    )
  }
  return null
}

/** 连续同一档结论合成一段。rows 是新→旧, 段内也保持这个顺序。 */
type Segment = { v: KeltnerVerdict; rows: ReviewRow[] }

function toSegments(rows: ReviewRow[]): Segment[] {
  const out: Segment[] = []
  let prevIdx = -2      // 上一条有结论的行在 rows 里的下标
  rows.forEach((r, i) => {
    if (!r.verdict) return
    const last = out[out.length - 1]
    // 只有**紧挨着**的同一档才并段。中间隔了没有结论的日子就是两次独立出现,
    // 并起来会把"这一档连着出现了几天"说多。
    if (last && last.v.code === r.verdict.code && prevIdx === i - 1) last.rows.push(r)
    else out.push({ v: r.verdict, rows: [r] })
    prevIdx = i
  })
  return out
}

export function StockReviewDialog({ symbol, name, tab: initialTab, onClose }: {
  symbol: string
  name: string
  /** 从哪一列点进来 —— 只决定默认视图 */
  tab: ReviewTab
  onClose: () => void
}) {
  const [tab, setTab] = useState<ReviewTab>(initialTab)
  const [days, setDays] = useState<number>(120)
  // 趋势视图专用: 只看有事的日子。120 行里找那几天转折是不现实的
  const [onlyMarked, setOnlyMarked] = useState(false)
  // [R292] 「说明」抽屉在**弹窗这一层**, 两个页签共用 —— 它讲的是六态与结论
  // 两边的词, 每个页签各挂一份就成了同一份东西的两个副本。
  const [help, setHelp] = useState(false)

  const q = useQuery({
    queryKey: QK.stockReview(symbol, days),
    queryFn: () => api.stockReview(symbol, days),
    staleTime: 5 * 60_000,
  })
  const d: StockReview | undefined = q.data

  const trendRows = useMemo(() => {
    const all = d?.rows ?? []
    if (!onlyMarked) return all
    return all.filter((r) => r.limit_up || r.limit_down || r.broken_limit_up || r.trend?.flipped)
  }, [d, onlyMarked])

  const segments = useMemo(() => toSegments(d?.rows ?? []), [d])

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4" onClick={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        className="flex max-h-[88vh] w-full max-w-5xl flex-col overflow-hidden rounded-lg border border-border bg-surface shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between gap-3 border-b border-border/60 px-4 py-3">
          <div className="flex min-w-0 items-baseline gap-2.5">
            <CalendarRange className="h-4 w-4 self-center shrink-0 text-sky-400" />
            <span className="shrink-0 text-sm font-medium text-foreground">{name} 复盘</span>
            <span className="shrink-0 font-mono text-[10px] text-muted">{symbol}</span>
            {d && !d.error && (
              <span className="truncate text-[10px] text-muted">
                {d.start} ~ {d.end} · {d.days} 个交易日
                {tab === 'trend' && ` · 六态阈值 ${(d.threshold * 100).toFixed(0)}%${d.threshold_source !== 'default' ? `(${d.threshold_source})` : ''}`}
                {tab === 'combo' && ' · 27 种组合,系统对每一种怎么说'}
              </span>
            )}
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <div className="flex overflow-hidden rounded-btn border border-border/60">
              {/* [R223] 页签名改回「通道结论」。用户: 「名称改回原来的通道结论」。
                  R200 那轮清行话时把它换成了「这个价贵不贵」—— 那是在解释它**说什么**,
                  可页签要的是**这一栏叫什么**, 换掉之后反而对不上这一层在别处的名字
                  (`keltner.verdict` / 感叹号说明 / 复盘统计口径都叫通道结论)。 */}
              {/* [R228] 第三个页签「组合速查」—— 原来是另一个铺满屏幕的模态。
                  三个页签的排序是有讲究的: 前两个是**纵向**(同一个判定在时间轴上
                  怎么走的), 第三个是**横向**(同一天里 27 格各是什么样)。 */}
              {([['trend', '趋势状态'], ['verdict', '通道结论'], ['combo', '组合速查']] as const).map(([k, label]) => (
                <button
                  key={k}
                  onClick={() => setTab(k)}
                  className={`px-2.5 py-1 text-[10px] transition-colors cursor-pointer ${
                    tab === k ? 'bg-sky-400/15 text-sky-300' : 'text-muted hover:text-foreground'}`}
                >
                  {label}
                </button>
              ))}
            </div>
            <div className="flex overflow-hidden rounded-btn border border-border/60">
              {RANGES.map((n) => (
                <button
                  key={n}
                  onClick={() => setDays(n)}
                  className={`px-2 py-1 text-[10px] transition-colors cursor-pointer ${
                    days === n ? 'bg-sky-400/15 text-sky-300' : 'text-muted hover:text-foreground'}`}
                >
                  {n}日
                </button>
              ))}
            </div>
            <button onClick={onClose} className="text-muted hover:text-foreground"><X className="h-4 w-4" /></button>
          </div>
        </div>

        {/* [R228] 组合速查**不等这次请求**: 27 格的表是恒定的、另一个 query、
            缓存一天, 而它只用 channel 里的末日读数去高亮"你在哪一格"。
            让它陪着复盘转圈是白等 —— 表先出来, 读数带随后补上。 */}
        {tab === 'combo' ? (
          // [R294] 组合速查也搬进 `relative` 容器 —— 「说明」抽屉挂在这一层,
          // 留在外面的话切到这一页那个按钮就点了没反应。
          <div className="relative flex min-h-0 flex-1 flex-col">
            <ComboView geo={d?.channel?.geo} runs={d?.channel?.runs} rows={d?.rows ?? []}
                       days={d?.days ?? 0} onHelp={() => setHelp(true)} />
            <ReviewHelpSheet open={help} onClose={() => setHelp(false)} />
          </div>
        ) : (
          // [R292] **这一层 `relative` 是「说明」抽屉的定位祖先。**
          // R289 漏了它(那次的改动只在内存里做了没落盘), 于是抽屉的
          // `absolute inset-0` 一路冒到最外层那个 `fixed inset-0` 上 ——
          // 用户看到的「点进去全屏了」就是这么来的。
          <div className="relative flex min-h-0 flex-1 flex-col">
            {q.isLoading && (
              <div className="flex items-center justify-center gap-2 py-16 text-xs text-muted">
                <Loader2 className="h-4 w-4 animate-spin" /> 正在回算 {days} 个交易日…
              </div>
            )}
            {q.isError && <div className="px-4 py-16 text-center text-xs text-red-400">复盘数据加载失败</div>}
            {d?.error && <div className="px-4 py-16 text-center text-xs text-muted">{d.error}</div>}

            {d && !d.error && tab === 'trend' && (
              <TrendView d={d} rows={trendRows} onlyMarked={onlyMarked}
                         onToggleMarked={() => setOnlyMarked((v) => !v)}
                         onHelp={() => setHelp(true)} />
            )}
            {d && !d.error && tab === 'verdict' && (
              <VerdictView d={d} segments={segments} onHelp={() => setHelp(true)} />
            )}
            {/* 抽屉挂在页签内容之后、`relative` 容器之内 —— 它盖住的是**正文**,
                页签与日期档照样能点(翻着说明换页签是常事)。 */}
            <ReviewHelpSheet open={help} onClose={() => setHelp(false)} />
          </div>
        )}
      </div>
    </div>
  )
}

// ===== 趋势视图: 这个状态是怎么走到今天的 =====

function TrendView({ d, rows, onlyMarked, onToggleMarked, onHelp }: {
  d: StockReview
  rows: ReviewRow[]
  onlyMarked: boolean
  onToggleMarked: () => void
  onHelp: () => void
}) {
  const legs = legsByFlipDate(d.flip_trades)
  const bull = d.now?.side === '多头'
  const gap = (line: number | null | undefined) =>
    line == null || !d.now?.close ? null : (line - d.now.close) / d.now.close
  const dn = gap(d.now?.flip_down)
  const up = gap(d.now?.flip_up)
  const st = d.stats
  const limits = st.limit_ups + st.broken_limit_ups + st.limit_downs

  return (
    <>
      <div className={HEAD_CARD}>
        {/* 用户: 「在趋势状态里面, 功能按转折买卖部分才是重点」 —— 所以它是第一行。
            外面那张表(决策台「走势」列)回答"今天怎么样", 点进来回答"这套转折
            在这只票上到底赚不赚钱"。 */}
        <HeadRow label="按转折买卖">
          <FlipTradesBar
            ft={d.flip_trades}
            title=""
            basis="转折次日开盘进出 · 转多买入、转空清仓(不做空)"
          />
        </HeadRow>

        {d.now && (
          <HeadRow label="现在">
            <span className="flex flex-wrap items-baseline gap-x-3 gap-y-1 text-[10px]">
              <b className={cn('font-medium', bull ? 'text-red-400' : 'text-emerald-400')}>
                {d.now.state_cn} 第 {d.now.day} 天
              </b>
              {/* 复盘完总得知道接下来盯什么 —— 决策台那一列给不出这两个价 */}
              {d.now.flip_down != null && (
                <span className="font-mono text-emerald-400/90" title="收盘跌破这个价转弱">
                  跌破 {d.now.flip_down.toFixed(2)}
                  {dn != null && <span className="ml-1 opacity-70">{(dn * 100).toFixed(1)}%</span>}
                </span>
              )}
              {d.now.flip_up != null && (
                <span className="font-mono text-red-400/90" title="收盘站上这个价转强">
                  站上 {d.now.flip_up.toFixed(2)}
                  {up != null && <span className="ml-1 opacity-70">+{(up * 100).toFixed(1)}%</span>}
                </span>
              )}
            </span>
          </HeadRow>
        )}

        {/* [R292] 涨跌停计数与状态色带搬进这张卡 —— 用户点名要这两样。
            **只留计数, 不留那四张大卡片**: 同样三个数, 一行小字说得完。 */}
        <HeadRow label={`这 ${d.days} 天`}>
          <div className="text-[10px] text-muted">
            {limits > 0 ? (
              <span className="flex flex-wrap gap-x-3">
                <span className="text-red-400/90">涨停 {st.limit_ups}</span>
                {st.max_streak > 1 && <span>最高 {st.max_streak} 连板</span>}
                <span className="text-amber-400/90" title="盘中最高触及涨停但收盘没封住">炸板 {st.broken_limit_ups}</span>
                <span className="text-emerald-400/90">跌停 {st.limit_downs}</span>
              </span>
            ) : <span>没有涨跌停</span>}
          </div>
          <div className="-mx-1 mt-1.5">
            <StateTimeline
              hint={rangeHint(d.rows)}
              legend={TREND_LEGEND}
              bands={[{ cells: trendCells(d.rows) }]}
            />
          </div>
        </HeadRow>
      </div>

      <div className="flex items-center justify-end gap-2 px-4 pt-2">
        <button
          onClick={onToggleMarked}
          title="只留下有涨跌停、或趋势翻转的那些天 —— 其余日子状态没变, 复盘时没有信息"
          className={`rounded-btn border px-2 py-1 text-[10px] transition-colors cursor-pointer ${
            onlyMarked ? 'border-sky-400/40 bg-sky-400/15 text-sky-300' : 'border-border/60 text-muted hover:text-foreground'}`}
        >
          只看有事的日子
        </button>
        <HelpButton onClick={onHelp} />
      </div>

      {/* ── 正文: 逐日表, 转折那几行内联带上这一笔做了什么 ── */}
      <div className="mt-2 min-h-0 flex-1 overflow-auto border-t border-border/60">
        <table className="w-full text-xs">
          <thead className="sticky top-0 z-10 bg-surface">
            <tr className="border-b border-border/60 text-[10px] text-muted">
              <th className="whitespace-nowrap px-3 py-2 text-left font-normal">日期</th>
              <th className="whitespace-nowrap px-2 py-2 text-right font-normal">收盘</th>
              <th className="whitespace-nowrap px-2 py-2 text-right font-normal">涨跌</th>
              <th className="whitespace-nowrap px-3 py-2 text-left font-normal">六态状态</th>
              {/* [R289] 这三列就是原来「每一段」那张表, 并过来了 */}
              <th className="whitespace-nowrap px-2 py-2 text-left font-normal" title="按转折买卖: 这次转折的次日开盘该干什么">动作</th>
              <th className="whitespace-nowrap px-2 py-2 text-right font-normal" title="成交日与成交价 → 了结日与了结价, 都是开盘价">成交 → 了结</th>
              <th className="whitespace-nowrap px-2 py-2 text-right font-normal" title="多头段是真赚到的; 空头段是空仓期间股价的涨跌, 不是你的盈亏">结果</th>
              {/* [R258] 列头从「贵不贵」改成「结论」。用户: 「别用这么傻逼的描述」。
                  这一层在别处一律叫**通道结论**(`keltner.verdict` / 决策台那一列 /
                  上方那个页签 / 复盘统计口径), 只有这里自己起了个口语名字。
                  一个东西在界面上有两个名字, 读的人得先确认它们是不是一回事。 */}
              <th className="whitespace-nowrap px-2 py-2 text-center font-normal" title="当天三档通道合起来给出的那一句结论 —— 与决策台「结论」列同一句话, 悬停看完整卡片">结论</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr
                key={r.date}
                className={`border-b border-border/30 hover:bg-elevated/30 ${r.trend?.flipped ? 'bg-amber-400/[0.05]' : ''}`}
              >
                <td className="whitespace-nowrap px-3 py-1.5 font-mono text-[10px] text-secondary">{r.date}</td>
                <td className="whitespace-nowrap px-2 py-1.5 text-right font-mono tabular-nums text-foreground">{r.close.toFixed(2)}</td>
                <td className={`whitespace-nowrap px-2 py-1.5 text-right font-mono tabular-nums ${chgCls(r.change_pct)}`}>
                  {pct(r.change_pct, 2)}
                  <LimitTag r={r} />
                </td>
                <td className="whitespace-nowrap px-3 py-1.5">
                  {r.trend ? (
                    <>
                      <span
                        className={`inline-flex whitespace-nowrap rounded border px-1.5 py-0.5 text-[10px] ${trendBadgeCls(r.trend.state)}`}
                        title={`${r.trend.state_cn}(${r.trend.state_en})`}
                      >
                        {r.trend.state_cn} 第 {r.trend.day} 天
                      </span>
                      {r.trend.flipped && (
                        <span className="ml-1.5 text-[9px] text-amber-400" title="这天六态状态发生了翻转">
                          ← 转折
                        </span>
                      )}
                    </>
                  ) : <span className="text-[10px] text-muted/40">—</span>}
                </td>
                <FlipTradeCells leg={legs.get(r.date)} />
                {/* [R52] 结论列在这张表里保留 —— 与「结论」视图不冲突: 那边是摊开的
                    卡片流(每一档说了什么、之后走成什么样), 这里只是让状态和当天的
                    通道位置能横着对上一眼("这个板是在什么位置上出的")。 */}
                <td className="whitespace-nowrap px-2 py-1.5 text-center">
                  {r.verdict ? (
                    <VerdictHover v={r.verdict} note={`${r.date} 当天的读数。收盘口径。`}>
                      <span className={`inline-flex cursor-help whitespace-nowrap rounded border px-1 py-0.5 text-[10px] ${VERDICT_CLS[r.verdict.tone]}`}>
                        {r.verdict.title}
                      </span>
                    </VerdictHover>
                  ) : <span className="text-[10px] text-muted/40">—</span>}
                </td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr><td colSpan={8} className="px-3 py-10 text-center text-[11px] text-muted">这段时间里没有涨跌停, 状态也没翻转过</td></tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="border-t border-border/60 px-4 py-2 text-[10px] leading-relaxed text-muted">
        收盘口径, 与决策台「趋势」列同一个状态机、同一个阈值(含你自己调过的那个)。
        {/* [R258] 「这个价贵不贵」是 R200 那轮清行话时的旧页签名, R223 已经改回
            「通道结论」—— 这句脚注一直指着一个**不存在的页签**。 */}
        「结论」列悬停看完整卡片, 要摊开每一档说了什么、之后走成什么样, 切到上方的「通道结论」。
      </div>
    </>
  )
}


/** [R293] 阶段的纯文字色。整块卡的边框+底色那套已随 VerdictHeader 一起撤了 */
const PHASE_TEXT_CLS: Record<string, string> = {
  coiling: 'text-secondary', launching: 'text-red-300', advancing: 'text-red-300',
  stalling: 'text-amber-300', overextended: 'text-amber-300',
  declining: 'text-emerald-300', unclear: 'text-muted',
}

/** [R293] 语气的纯文字色与大白话名 —— 与 `VERDICT_CLS` 同一套语义, 不同用法 */
const VERDICT_TEXT_CLS: Record<string, string> = {
  buy: 'text-sky-300', hold: 'text-amber-400', sell: 'text-red-400',
  avoid: 'text-muted', watch: 'text-secondary',
}
const TONE_CN: Record<string, string> = {
  buy: '偏买', hold: '拿着', sell: '偏卖', avoid: '回避', watch: '等着',
}


function EvidencePanel({ ch, edge }: {
  ch: NonNullable<StockReview['channel']>
  edge: StockReview['verdict_edge']
}) {
  const { explain, phase } = ch
  const [open, setOpen] = useState(() => storage.reviewEvidenceOpen.get(false))
  const rows = explain?.length ?? 0
  if (!rows && !phase?.why && !edge) return null
  return (
    <ReviewDisclosure
      label={rows > 0 ? `依据 · ${rows} 项读数` : '依据'}
      note="(上面两条结论就是从这些读数出来的)"
      defaultOpen={open}
      onOpenChange={(v) => { setOpen(v); storage.reviewEvidenceOpen.set(v) }}
    >
        <div className="space-y-2">
          {!!phase?.why && (
            <p className="text-[10px] leading-relaxed text-secondary">
              <span className="text-muted">阶段判定:</span> {phase.why}
            </p>
          )}
          {!!edge && (
            <p className="text-[10px] leading-relaxed text-secondary">
              <span className="text-muted">通道结论:</span> {edge.text}
            </p>
          )}
          {rows > 0 && (
            <div className="overflow-hidden rounded-card border border-border/50">
              {explain!.map((r, i) => (
                <div key={r.label}
                     className={cn('flex items-start gap-2 px-3 py-1.5',
                       i % 2 ? 'bg-elevated/20' : 'bg-elevated/35')}>
                  <span className="w-14 shrink-0 text-[10px] text-muted">{r.label}</span>
                  <span className="w-20 shrink-0 font-mono text-[11px] tabular-nums text-foreground/90">
                    {r.value}
                  </span>
                  <span className="min-w-0 flex-1 text-[10px] leading-relaxed text-secondary">
                    {r.why}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
    </ReviewDisclosure>
  )
}


function VerdictView({ d, segments, onHelp }: {
  d: StockReview; segments: Segment[]; onHelp: () => void
}) {
  const legs = legsByFlipDate(d.verdict_trades)
  const ph = d.channel?.phase
  // 各档出现了几段 —— 与趋势那边「涨停 N · 跌停 N」同一个角色: 一行小字说完
  // 「这半年都出过什么」。**按语气分而不是按十档分**: 十个数一行放不下, 而且
  // 用户真正要找的是"偏买的那几段"。
  const byTone = segments.reduce<Record<string, number>>((acc, sg) => {
    acc[sg.v.tone] = (acc[sg.v.tone] ?? 0) + 1
    return acc
  }, {})

  return (
    <>
      <div className={HEAD_CARD}>
        {/* 用户: 「核心是按结论买卖」—— 与趋势那边一样, 它是第一行 */}
        <HeadRow label="按结论买卖">
          <FlipTradesBar
            ft={d.verdict_trades}
            title=""
            basis="结论换档的次日开盘进出 · 偏买建仓、偏卖与回避清仓(不做空)"
            caveat={'「拿着」「等着」「三档都在中部」都不动手 —— 那是作者写的原话(「拿着, 别在这加仓」'
                    + '「等短期入场点」), 不是买卖信号。另: 「该止盈了」原话是「可落袋一部分」、'
                    + '「大顶区域」是「动仓位基调」, 这里一律按清空模拟, 比原话重。'}
          />
        </HeadRow>

        {!!ph && (
          <HeadRow label="现在">
            <div className="text-[10px]">
              <span className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                <b className={cn('font-medium', PHASE_TEXT_CLS[ph.code] ?? 'text-secondary')}>{ph.cn}</b>
                {d.channel!.event.code !== 'none' && (
                  <span className="text-muted">
                    {d.channel!.event.cn}{d.channel!.event.confirmed ? '' : '(未确认)'}
                  </span>
                )}
              </span>
              {/* **这一栏唯一的行动指引。** 别的都能收, 它不行 —— 收起来这一页
                  就只剩「现在处在下跌中」这种定性词, 没有一条能照着做的(R269)。 */}
              <p className="mt-1 leading-relaxed text-secondary">
                <span className="text-muted">该盯什么: </span>{ph.watch}
              </p>
              {/* [R269] 27 格组合的那条注记是**判定的一部分**, 不许在重排里蒸发 ——
                  「中中上」「中中下」两格底层返回无结论, 而它们恰恰是"大级别到位、
                  等一个入场点"的另一半, 全靠这条注记说出来。 */}
              {!!d.channel?.event.combo_note && (
                <p className="mt-1 leading-relaxed text-muted">
                  组合「{d.channel.event.combo_note.combo}」· {d.channel.event.combo_note.title}:
                  {d.channel.event.combo_note.detail}
                </p>
              )}
            </div>
          </HeadRow>
        )}

        <HeadRow label={`这 ${d.days} 天`}>
          <div className="flex flex-wrap gap-x-3 text-[10px] text-muted">
            <span>{segments.length} 段结论</span>
            {(['buy', 'hold', 'watch', 'sell', 'avoid'] as const)
              .filter((t) => byTone[t])
              .map((t) => (
                <span key={t} className={VERDICT_TEXT_CLS[t]}>{TONE_CN[t]} {byTone[t]} 段</span>
              ))}
          </div>
          <div className="-mx-1 mt-1.5">
            <StateTimeline
              hint={rangeHint(d.rows)}
              legend={VERDICT_LEGEND}
              bands={[{ cells: verdictCells(d.rows) }]}
            />
          </div>
        </HeadRow>
      </div>

      {/* [R269] 「依据」——**默认收起的一条**, 约 20px。用户嫌的是压着正文的
          常驻块, 而它本来就是收起来的; 那三样读数是 R212 改了三版才定下来的。 */}
      {!!d.channel && <EvidencePanel ch={d.channel} edge={d.verdict_edge} />}

      <div className="flex justify-end px-4 pt-2">
        <HelpButton onClick={onHelp} />
      </div>

      <div className="mt-2 min-h-0 flex-1 overflow-auto border-t border-border/60 p-4">
        {segments.length === 0 && (
          <div className="py-14 text-center text-[11px] text-muted">
            这段时间里三档通道一直在中部 —— 位置上没有可说的, 听趋势和信号的
          </div>
        )}
        <div className="space-y-2.5">
          {segments.map((seg) => (
            <SegmentCard key={seg.rows[0].date} seg={seg} forwardDays={d.forward_days}
                         leg={legs.get(seg.rows[seg.rows.length - 1].date)} />
          ))}
        </div>
      </div>

      <div className="border-t border-border/60 px-4 py-2 text-[10px] leading-relaxed text-muted">
        每一段就是决策台「结论」列当时悬停会看到的那张卡片。一律按收盘算, 用的是同一套通道。
        历史是按<b className="text-secondary">当前</b>复权价重新算的 —— 期间除过权的话,
        同一天今天算出来的通道会和当时屏幕上略有出入, 复盘看的是形态与节奏。
      </div>
    </>
  )
}

function SegmentCard({ seg, forwardDays, leg }: {
  seg: Segment; forwardDays: number
  /** [R293] 这一段起头那次换档触发的那一笔 —— 段首日就是它的触发日 */
  leg?: NonNullable<StockReview['verdict_trades']>['legs'][number]
}) {
  const { v, rows } = seg
  const newest = rows[0]              // rows 是新→旧
  const oldest = rows[rows.length - 1]
  const span = rows.reduce((a, r) => a * (1 + (r.change_pct ?? 0)), 1) - 1
  const limitUps = rows.filter((r) => r.limit_up).length
  const bands = (['s', 'm', 'l'] as const).filter((k) => oldest.bands[k])

  return (
    <div className="flex overflow-hidden rounded-lg border border-border/60 bg-elevated/20">
      <div className={`w-1 shrink-0 ${VERDICT_BAR[v.tone]}`} />
      <div className="min-w-0 flex-1 px-3 py-2.5">
        <div className="flex flex-wrap items-baseline gap-2">
          <span className={`inline-flex shrink-0 whitespace-nowrap rounded border px-1.5 py-0.5 text-[11px] ${VERDICT_CLS[v.tone]}`}>
            {v.title}
          </span>
          <span className="shrink-0 font-mono text-[10px] text-secondary">
            {rows.length > 1 ? `${oldest.date} ~ ${newest.date}` : newest.date}
          </span>
          <span className="shrink-0 text-[10px] text-muted">{rows.length} 天</span>
          <span className={`shrink-0 font-mono text-[10px] ${chgCls(span)}`} title="这一段期间的累计涨跌">
            期间 {pct(span)}
          </span>
          {limitUps > 0 && (
            <span className="shrink-0 rounded border border-red-400/50 bg-red-400/15 px-1 text-[9px] text-red-300">
              含 {limitUps} 次涨停
            </span>
          )}
          <span
            className={`ml-auto shrink-0 font-mono text-[10px] ${chgCls(newest.fwd)}`}
            title={newest.fwd == null
              ? `这一段结束还不到 ${forwardDays} 个交易日, 结果未知`
              : `这一档最后一次出现(${newest.date})之后 ${forwardDays} 个交易日的涨跌`}
          >
            之后{forwardDays}日 {newest.fwd == null ? '待定' : pct(newest.fwd)}
          </span>
        </div>

        {/* [R293] 这一段里手上做了什么。用户: 「关注重点是『调整到位』和这些
            状态期间的买卖」—— 那就长在这一段自己的卡片上, 而不是让人去另一张
            表里按日期找回来。段首日就是那一笔的触发日, 所以两边天然对齐。 */}
        <FlipTradeLine leg={leg} />

        {/* 徽标背后的三段 —— 这才是「结论」列真正的内容 */}
        <div className="mt-2 rounded border border-border/60 bg-base/60 px-2 py-1.5">
          <div className="text-[9px] text-muted">怎么做</div>
          <div className="mt-0.5 text-[11px] leading-snug text-foreground">{v.action}</div>
        </div>
        <div className="mt-1.5 text-[10px] leading-relaxed text-secondary">{v.detail}</div>
        <div className="mt-1.5 flex flex-wrap items-baseline gap-1.5">
          <span className="text-[9px] text-muted">依据</span>
          <span className="text-[10px] text-secondary">{v.bands_text}</span>
          <span className="text-[9px] text-muted/70">·</span>
          {bands.map((k) => (
            <span key={k} className="rounded border border-border/60 px-1 text-[9px] text-muted">
              {BAND_CN[k]}{oldest.bands[k]!.pos_cn}
            </span>
          ))}
        </div>
      </div>
    </div>
  )
}
