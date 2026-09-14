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
 *     通道档位   通道档位在时间轴上怎么走的     (纵向 · 通道)
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
import { comboHistory } from '@/components/stock-analysis/decision-board/ComboView'
import { FlipTradesBar, FlipTradeCells, legsByFlipDate } from '@/components/stock-analysis/FlipTradesPanel'
import { HeadRow, SubRow, HEAD_CARD } from '@/components/stock-analysis/ReviewHeadRow'
import { StateTimeline } from '@/components/stock-analysis/StateTimeline'
import { ReviewDisclosure } from '@/components/stock-analysis/ReviewDisclosure'
import {
  // [R295] `BAND_CN` 与 `VERDICT_BAR` 跟着 `SegmentCard` 一起退了 ——
  // 前者是那张卡上的三档名, 后者是卡片左边那条色条。
  BAND_CN, POS_LEGEND, TREND_LEGEND, VERDICT_LEGEND,
  bandCells, rangeHint, trendCells, verdictCells,
} from '@/lib/reviewTimeline'

// [R228 加, R296 删] 'combo' 那个页签没了 —— 用户: 「组合速查合并到通道结论
// 里面去」。穷举 125 种三档位置验过: 通道档位是那 27 格的**纯函数**, 两个页签
// 监控的是同一个对象的两层。**外部调用方传 'combo' 也不会炸**: 它在下面被
// 归一成 'verdict', 见 `StockReviewDialog` 的第一行。
export type ReviewTab = 'trend' | 'verdict' | 'combo'

// 与决策台「结论」列同一套配色 —— 两处不一样的话, 翻历史时得先在脑子里做一次换算
const VERDICT_CLS: Record<KeltnerVerdict['tone'], string> = {
  sell: 'border-red-400/40 bg-red-400/10 text-red-400',
  buy: 'border-sky-400/40 bg-sky-400/10 text-sky-300',
  hold: 'border-amber-400/40 bg-amber-400/10 text-amber-400',
  avoid: 'border-border bg-base text-muted',
  watch: 'border-border bg-elevated/60 text-secondary',
}

/**
 * [R313] 细分档的悬停说明 —— **一处定义**。

 * 它出现在两处(「现在」那一行、逐日表每一行), 两处必须说同一句话:
 * 同一个注记两种解释, 正是这仓库反复在治的那种病。
 */
const SUB_STATE_TIP = '六态里更细的那一档 —— 只是标注, 不是状态。\n'
  + '它不参与多空判断、不触发转折、不进打分。\n\n'
  + '次级回升:这一段反弹的高点还没超过上一段回升的高点(力度更弱)。\n'
  + '次级回撤:这一段回落的低点还没跌破上一段回撤的低点(还没破位)。'

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
  // [R296] 'combo' 归一到 'verdict' —— 那一页并进去了。**不删这个入参值**:
  // 决策台那边可能还有地方带着它进来, 悄悄报错不如悄悄落到对的页上。
  const [tab, setTab] = useState<'trend' | 'verdict'>(
    initialTab === 'trend' ? 'trend' : 'verdict')
  const [days, setDays] = useState<number>(120)
  // 趋势视图专用: 只看有事的日子。120 行里找那几天转折是不现实的
  const [onlyMarked, setOnlyMarked] = useState(false)
  // [R329] 「说明」页签删掉了。用户: 「这个位置的说明按钮可以删除了, 外面设置
  // 旁边已经有一个了」—— R323 在侧栏给了词表一个全局入口, 这里就成了第二个
  // 通往同一份内容的门。**代价是 27 格速查表的「你在这一格」高亮没了**:
  // 全局入口那边没有"当前是哪只票"这个上下文。这是用户看过之后的取舍。

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

              </span>
            )}
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <div className="flex overflow-hidden rounded-btn border border-border/60">
              {/* [R223] 页签名改回「通道档位」。用户: 「名称改回原来的通道结论」。
                  R200 那轮清行话时把它换成了「这个价贵不贵」—— 那是在解释它**说什么**,
                  可页签要的是**这一栏叫什么**, 换掉之后反而对不上这一层在别处的名字
                  (`keltner.verdict` / 感叹号说明 / 复盘统计口径都叫通道档位)。 */}
              {/* [R228] 第三个页签「组合速查」—— 原来是另一个铺满屏幕的模态。
                  三个页签的排序是有讲究的: 前两个是**纵向**(同一个判定在时间轴上
                  怎么走的), 第三个是**横向**(同一天里 27 格各是什么样)。 */}
              {([['trend', '趋势状态'], ['verdict', '通道档位']] as const).map(([k, label]) => (
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

        {/* [R301] 三个页签, 三块正文 —— **「说明」不再是盖上来的一层**。
            用户: 「说明点击后不是弹窗, 和趋势状态一样内容区域显示」。

            **它单独一支, 而且排在加载判断之前**: 那张词表是恒定的(另一个 query、
            缓存一天), 与这只票、与这次回算都无关。塞进下面那一支的话, 点「说明」
            会先看到「正在回算 120 个交易日…」——**等一个它根本不需要的东西**。
            R228 给 27 格速查表定的就是这条, 这里沿用。 */}
        <div className="flex min-h-0 flex-1 flex-col">
          {(
            <>
              {q.isLoading && (
                <div className="flex items-center justify-center gap-2 py-16 text-xs text-muted">
                  <Loader2 className="h-4 w-4 animate-spin" /> 正在回算 {days} 个交易日…
                </div>
              )}
              {q.isError && <div className="px-4 py-16 text-center text-xs text-red-400">复盘数据加载失败</div>}
              {d?.error && <div className="px-4 py-16 text-center text-xs text-muted">{d.error}</div>}

              {d && !d.error && tab === 'trend' && (
                <TrendView d={d} rows={trendRows} onlyMarked={onlyMarked}
                           onToggleMarked={() => setOnlyMarked((v) => !v)} />
              )}
              {d && !d.error && tab === 'verdict' && (
                <VerdictView d={d} segments={segments} />
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}

// ===== 趋势视图: 这个状态是怎么走到今天的 =====

function TrendView({ d, rows, onlyMarked, onToggleMarked }: {
  d: StockReview
  rows: ReviewRow[]
  onlyMarked: boolean
  onToggleMarked: () => void
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
            basis="转折次日开盘进出 · 转多买入、转空清仓(不做空)"
          />
        </HeadRow>

        {d.now && (
          <HeadRow label="现在">
            <span className="flex flex-wrap items-baseline gap-x-3 gap-y-1 text-[10px]">
              <b className={cn('font-medium', bull ? 'text-red-400' : 'text-emerald-400')}>
                {d.now.state_cn} 第 {d.now.day} 天
              </b>
              {/* [R313] 同上 —— 注记, 不是状态 */}
              {d.now.sub_state_cn && (
                <span className="text-[10px] text-muted/60" title={SUB_STATE_TIP}>
                  ({d.now.sub_state_cn})
                </span>
              )}
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
              {/* [R52 加, R295 删, R296 恢复] 「结论」那一列回来了 —— 用户:
                  「趋势状态删除的那一列我需要恢复」。
                  它在这里的价值是**横着对上一眼**: 同一行里六态说什么、通道位置
                  说什么。这一页有它自己的按转折买卖, 那一页有按档位买卖 ——
                  两套判定各管各的, 而这一列让人不必切页签就知道另一套怎么说。 */}
              {/* [R258] 名字必须与「通道档位」那一页、决策台那一列逐字一致 ——
                  同一层判定在界面上只许一个名字。R296 恢复这一列时差点又叫回
                  「结论」, 那样两张表并排放着就是同一样东西两个名字。 */}
              <th className="whitespace-nowrap px-2 py-2 text-center font-normal" title="当天三档通道合起来给出的那一句结论 —— 与决策台「档位」列同一句话, 悬停看完整卡片">通道档位</th>
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
                      {/* [R313] 细分档。**挂在状态旁边当注记, 不替换它** ——
                          用户: 「只是显示, 不触发转折不参与评分」。所以它既不
                          换徽标的词、也不换徽标的色(色编的是多空, 而细分档
                          不改多空), 只在后面缀一个更暗的小字。 */}
                      {r.trend.sub_state_cn && (
                        <span className="ml-1 text-[9px] text-muted/60" title={SUB_STATE_TIP}>
                          ({r.trend.sub_state_cn})
                        </span>
                      )}
                      {r.trend.flipped && (
                        <span className="ml-1.5 text-[9px] text-amber-400" title="这天六态状态发生了翻转">
                          ← 转折
                        </span>
                      )}
                    </>
                  ) : <span className="text-[10px] text-muted/40">—</span>}
                </td>
                <FlipTradeCells leg={legs.get(r.date)} />
                {/* [R296] 恢复。**排在成交三格之后** —— 这一页的主线是六态与
                    按转折买卖, 通道档位是"顺带对一眼"的旁证, 不该插进主线中间。 */}
                <td className="whitespace-nowrap px-2 py-1.5 text-center">
                  {r.verdict ? (
                    <VerdictHover v={r.verdict} note="收盘口径">
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
            「通道档位」—— 那句脚注一直指着一个**不存在的页签**。
            [R295] 同一个病的第二次: 「结论」那一列删掉之后, "悬停看完整卡片"就
            指着一列不存在的东西了, 跟着改。 */}
        「通道档位」列悬停看完整卡片; 要摊开每一档说了什么、之后走成什么样, 切到上方的「通道档位」那一页。
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
              <span className="text-muted">通道档位:</span> {edge.text}
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


function VerdictView({ d, segments }: {
  d: StockReview; segments: Segment[]
}) {
  // [R295] 与「趋势状态」那张表同一个开关。用户: 「通道结论那部分也想要这样的记录」
  const [onlyMarked, setOnlyMarked] = useState(false)
  const legs = legsByFlipDate(d.verdict_trades)
  const rows = onlyMarked ? d.rows.filter((r) => r.verdict_flipped) : d.rows
  // [R296] 「组合速查」并进来的两样: 你在哪一格 + 这一格历来。
  // 它们是**这只票的事**, 所以常驻; 那 27 格谱系是恒定的参考, 进「说明」抽屉。
  const here = d.channel?.geo?.combo ?? null
  const hist = comboHistory(d.rows, here)
  // [R302] 今天那一档。`rows` 是新→旧, 所以第一行就是今天。
  const now = d.rows[0]?.verdict ?? null
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
        <HeadRow label="按档位买卖">
          {/* [R302] 那段 ~100 字的口径偏差**从正文降进「说明」页**。用户:
              「检查通道档位页面有没有废话, 没水平没用的内容就不要显示出来了」。

              **它不随票变** —— 每一只票、每一次打开印的都是同一段, 而且用的是
              琥珀警告色, 于是每张卡顶上常年挂着一块与这只票无关的黄字。这与
              R299 在决策台清掉的是同一类(`why` 讲这只票 / `note` 讲这套系统)。

              **不是删掉**: `thin`(样本太少)、`delayed`(撞一字板顺延)那几条**是这只票的**,
              照旧留在正文 —— 把数字摆出来而把"这个数不能当真"藏起来才是骗人
              (`tradeNotes` 那条纪律)。挪走的只有恒定的那一段。 */}
          <FlipTradesBar
            ft={d.verdict_trades}
            basis="换档次日开盘进出 · 偏买建仓、偏卖与回避清仓(不做空);「拿着」「等着」不动手 —— 口径与作者原话的出入见「说明」"
          />
        </HeadRow>

        {!!ph && (
          <HeadRow label="现在">
            <div className="text-[10px]">
              <span className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                {/* [R302] **今天那一档结论补回来了, 而且排在最前面。**
                    用户: 「都围绕位置展开」。

                    **这一页叫「通道档位」, 而它的头部卡里原来根本没有今天那一档
                    结论** —— 要知道今天是「候选池」还是「大顶区域」, 得往下翻到
                    那张 120 行表格的第一行去找。查这一页时才发现的: 头一位摆的是
                    「阶段」(上升中/横盘中), 那是另一个读数, 而且它和结论**在抢
                    同一件事**(R257 为一模一样的毛病把「阶段」从走势列撤过)。

                    现在顺序是 **这一档 → 从哪三格来的 → 阶段 → 事件**:
                    结论第一、它的坐标第二、背景往后 —— 这就是"围绕位置展开"。 */}
                {!!now && (
                  <VerdictHover v={now} note="今天这一档。收盘口径。">
                    <b className={`inline-flex cursor-help whitespace-nowrap rounded border px-1.5 py-0.5 font-medium ${VERDICT_CLS[now.tone]}`}>
                      {now.title}
                      {!!now.days && (
                        <span className="ml-1 opacity-70"
                              title={now.since ? `自 ${now.since} 起连着 ${now.days} 个交易日${now.capped ? '以上' : ''}` : undefined}>
                          已{now.days}天{now.capped ? '+' : ''}
                        </span>
                      )}
                    </b>
                  </VerdictHover>
                )}
                {/* [R296] 三档组合码 —— 结论是它的纯函数(R296 穷举 125 种验过),
                    所以紧跟在结论后面: 一眼看得出"这一档是从哪三格出来的"。 */}
                {here ? (
                  <span className="font-mono text-secondary" title="三档各在自己通道的上/中/下 —— 27 格速查表的行号, 完整的一览在「说明」里">
                    {here}
                  </span>
                ) : (
                  /* [R294] 「今天定不了这一格」与下面那句「没进过这一格 —— 头一回」
                     **是两件事**: 一个是三档缺了一档算不出来, 一个是这只票确实
                     没走到过。合成一句的话, 数据缺失会被读成"这是个罕见位置"。 */
                  <span className="text-muted/60" title="三档里有一档今天定不出位置(数据不够), 不是这个位置罕见">
                    今天定不了这一格
                  </span>
                )}
                <span className={PHASE_TEXT_CLS[ph.code] ?? 'text-secondary'}>{ph.cn}</span>
                {d.channel!.event.code !== 'none' && (
                  <span className="text-muted">
                    {d.channel!.event.cn}{d.channel!.event.confirmed ? '' : '(未确认)'}
                  </span>
                )}
              </span>
              {/* **这一栏唯一的行动指引。** 别的都能收, 它不行 —— 收起来这一页
                  就只剩「现在处在下跌中」这种定性词, 没有一条能照着做的(R269)。 */}
              <SubRow label="该盯什么"><span className="text-secondary">{ph.watch}</span></SubRow>
              {/* [R296] 这一格在这只票身上历来什么光景 —— 从「组合速查」并过来的。
                  按**段**不按天(R177): 一段连着 8 天算 1 次, 按天算的话那 8 天的
                  前瞻窗口互相重叠, 次数会被撑大。 */}
              {!!here && (
                <SubRow label="这一格历来">
                  {hist && hist.segs > 0 ? (
                    <>
                      这 {d.days} 天里进过 <b className="text-secondary">{hist.segs}</b> 段、共 {hist.days} 天
                      {hist.scored > 0 ? (
                        <>, 走完的 {hist.scored} 段之后 {d.forward_days} 日平均{' '}
                          <b className={cn('font-mono', chgCls(hist.avg))}>{pct(hist.avg)}</b>, {hist.win} 段收涨</>
                      ) : <>, 还没有走完 {d.forward_days} 个交易日的段, 结果未知</>}
                    </>
                  ) : <>这 {d.days} 天里没进过这一格 —— 头一回</>}
                </SubRow>
              )}

              {/* [R269] 27 格组合的那条注记是**判定的一部分**, 不许在重排里蒸发 ——
                  「中中上」「中中下」两格底层返回无结论, 而它们恰恰是"大级别到位、
                  等一个入场点"的另一半, 全靠这条注记说出来。 */}
              {!!d.channel?.event.combo_note && (
                <SubRow label={`组合 ${d.channel.event.combo_note.combo}`}>
                  <b className="font-medium text-secondary">{d.channel.event.combo_note.title}</b>:{' '}
                  {d.channel.event.combo_note.detail}
                </SubRow>
              )}
            </div>
          </HeadRow>
        )}

        <HeadRow label={`这 ${d.days} 天`}>
          <div className="flex flex-wrap gap-x-3 text-[10px] text-muted">
            <span>{segments.length} 段档位</span>
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
          {/* [R296] 三档**各自**那三条带子 —— 从「组合速查」并过来的。
              **与上面那条不是一回事**: 上面画的是三档合成后的那一句结论, 这里
              画的是三档各自在哪。「短档先动、中档跟上、长档最后翻」这种节奏,
              合成后的单条带子看不出来(R273 的原话)。 */}
          <div className="-mx-1 mt-1">
            <StateTimeline
              className="mx-0"
              hint=""
              legend={POS_LEGEND}
              bands={(['s', 'm', 'l'] as const).map((k) => ({
                label: BAND_CN[k].slice(0, 2),
                cells: bandCells(d.rows, k),
              }))}
            />
          </div>
        </HeadRow>
      </div>

      {/* [R269] 「依据」——**默认收起的一条**, 约 20px。用户嫌的是压着正文的
          常驻块, 而它本来就是收起来的; 那三样读数是 R212 改了三版才定下来的。 */}
      {!!d.channel && <EvidencePanel ch={d.channel} edge={d.verdict_edge} />}

      <div className="flex items-center justify-end gap-2 px-4 pt-2">
        <button
          onClick={() => setOnlyMarked((v) => !v)}
          title="只留下档位换过的那些天 —— 其余日子档位没变, 复盘时没有信息"
          className={`rounded-btn border px-2 py-1 text-[10px] transition-colors cursor-pointer ${
            onlyMarked ? 'border-sky-400/40 bg-sky-400/15 text-sky-300' : 'border-border/60 text-muted hover:text-foreground'}`}
        >
          只看换档的日子
        </button>
      </div>

      {/* [R295] 正文换成**与「趋势状态」同一形状的逐日记录表**。
          用户指着那张表说: 「通道结论那部分也想要这样的记录」。

          原来这里是一张张段落卡片。换成表之后**内容一样没丢**:
            怎么做 / 为什么 / 依据 → 结论徽标的悬停(与决策台「结论」列同一张卡)
            那一段做了什么         → 换档行内联的三列(动作 / 成交→了结 / 结果)
          **两页于是可以左右对照着看**: 同一天六态说什么、通道说什么、各自该
          动手没有 —— 那正是这个弹窗一直缺的一步。 */}
      <div className="mt-2 min-h-0 flex-1 overflow-auto border-t border-border/60">
        <table className="w-full text-xs">
          <thead className="sticky top-0 z-10 bg-surface">
            <tr className="border-b border-border/60 text-[10px] text-muted">
              <th className="whitespace-nowrap px-3 py-2 text-left font-normal">日期</th>
              <th className="whitespace-nowrap px-2 py-2 text-right font-normal">收盘</th>
              <th className="whitespace-nowrap px-2 py-2 text-right font-normal">涨跌</th>
              {/* [R302] 表头 title 里原来还写着「与决策台「档位」列同一句话」——
                  **那是讲给读代码的人听的**, 对着屏幕的人不关心它在别处叫什么。
                  只留"这个数是什么、怎么看"。 */}
              <th className="whitespace-nowrap px-3 py-2 text-left font-normal" title="当天三档通道合起来给出的那一句结论, 悬停看完整卡片">通道档位</th>
              <th className="whitespace-nowrap px-2 py-2 text-left font-normal" title="按档位买卖: 这次换档的次日开盘该干什么">动作</th>
              <th className="whitespace-nowrap px-2 py-2 text-right font-normal" title="成交日与成交价 → 了结日与了结价, 都是开盘价">成交 → 了结</th>
              <th className="whitespace-nowrap px-2 py-2 text-right font-normal" title="多头段是真赚到的; 空头段是空仓期间股价的涨跌, 不是你的盈亏">结果</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr
                key={r.date}
                className={`border-b border-border/30 hover:bg-elevated/30 ${r.verdict_flipped ? 'bg-amber-400/[0.05]' : ''}`}
              >
                <td className="whitespace-nowrap px-3 py-1.5 font-mono text-[10px] text-secondary">{r.date}</td>
                <td className="whitespace-nowrap px-2 py-1.5 text-right font-mono tabular-nums text-foreground">{r.close.toFixed(2)}</td>
                <td className={`whitespace-nowrap px-2 py-1.5 text-right font-mono tabular-nums ${chgCls(r.change_pct)}`}>
                  {pct(r.change_pct, 2)}
                  <LimitTag r={r} />
                </td>
                <td className="whitespace-nowrap px-3 py-1.5">
                  {r.verdict ? (
                    <VerdictHover v={r.verdict} note="收盘口径">
                      <span className={`inline-flex cursor-help whitespace-nowrap rounded border px-1.5 py-0.5 text-[10px] ${VERDICT_CLS[r.verdict.tone]}`}>
                        {r.verdict.title}
                      </span>
                    </VerdictHover>
                  ) : <span className="text-[10px] text-muted/40">三档都在中部</span>}
                  {r.verdict_flipped && (
                    <span className="ml-1.5 text-[9px] text-amber-400" title="这天通道档位换了一档">
                      ← 换档
                    </span>
                  )}
                </td>
                <FlipTradeCells leg={legs.get(r.date)} />
              </tr>
            ))}
            {rows.length === 0 && (
              <tr><td colSpan={7} className="px-3 py-10 text-center text-[11px] text-muted">这段时间里档位一次都没换过</td></tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="border-t border-border/60 px-4 py-2 text-[10px] leading-relaxed text-muted">
        「通道档位」列悬停看完整卡片 —— 与决策台「档位」列是同一张。一律按收盘算, 用的是同一套通道。
        历史是按<b className="text-secondary">当前</b>复权价重新算的 —— 期间除过权的话,
        同一天今天算出来的通道会和当时屏幕上略有出入, 复盘看的是形态与节奏。
      </div>
    </>
  )
}

// [R52 加, R295 删] `SegmentCard`(一段结论一张卡)在这里删掉了。
// 用户指着「趋势状态」那张逐日表: 「通道结论那部分也想要这样的记录」——
// 于是这一页的正文换成了同一形状的表。**卡片上的内容一样没丢**:
//   怎么做 / 为什么 / 依据  → 结论徽标的悬停(与决策台「结论」列同一张卡)
//   那一段做了什么          → 换档行内联的三列(动作 / 成交→了结 / 结果)
// 留着卡片就是同一条时间轴印两遍, 而且两处哪天不同步了没人会发现。
