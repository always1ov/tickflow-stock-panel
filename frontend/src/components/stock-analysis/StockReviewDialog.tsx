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
import { trendBadgeCls } from '@/components/stock-analysis/TrendStateBar'
import { VerdictHover } from '@/components/stock-analysis/VerdictHover'
import { ComboView } from '@/components/stock-analysis/decision-board/ComboView'

export type ReviewTab = 'trend' | 'verdict' | 'combo'

// 与决策台「结论」列同一套配色 —— 两处不一样的话, 翻历史时得先在脑子里做一次换算
const VERDICT_CLS: Record<KeltnerVerdict['tone'], string> = {
  sell: 'border-red-400/40 bg-red-400/10 text-red-400',
  buy: 'border-sky-400/40 bg-sky-400/10 text-sky-300',
  hold: 'border-amber-400/40 bg-amber-400/10 text-amber-400',
  avoid: 'border-border bg-base text-muted',
  watch: 'border-border bg-elevated/60 text-secondary',
}
const VERDICT_BAR: Record<KeltnerVerdict['tone'], string> = {
  sell: 'bg-red-400',
  buy: 'bg-sky-400',
  hold: 'bg-amber-400',
  avoid: 'bg-border',
  watch: 'bg-secondary/60',
}

const RANGES = [60, 120, 250] as const
const BAND_CN: Record<'s' | 'm' | 'l', string> = { s: '短期', m: '中期', l: '长期' }

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
          <ComboView geo={d?.channel?.geo} runs={d?.channel?.runs} />
        ) : (
          <>
            {q.isLoading && (
              <div className="flex items-center justify-center gap-2 py-16 text-xs text-muted">
                <Loader2 className="h-4 w-4 animate-spin" /> 正在回算 {days} 个交易日…
              </div>
            )}
            {q.isError && <div className="px-4 py-16 text-center text-xs text-red-400">复盘数据加载失败</div>}
            {d?.error && <div className="px-4 py-16 text-center text-xs text-muted">{d.error}</div>}

            {d && !d.error && tab === 'trend' && (
              <TrendView d={d} rows={trendRows} onlyMarked={onlyMarked} onToggleMarked={() => setOnlyMarked((v) => !v)} />
            )}
            {d && !d.error && tab === 'verdict' && <VerdictView d={d} segments={segments} />}
          </>
        )}
      </div>
    </div>
  )
}

// ===== 趋势视图: 这个状态是怎么走到今天的 =====

/**
 * [R177] 「回头看」小结: 每种状态/结论出现过几**段**、之后 N 日普遍怎么走。
 *
 * 单位是段不是天 —— 一段持续 8 天的上涨趋势算 1 次。按天算的话, 那 8 天各自
 * 的"之后 5 日"互相共享 4 天, n 会被撑大, 一个很薄的结论看着挺扎实。
 *
 * 样本本来就小(半年内同一档常是个位数), 所以: 只报次数和均值, 不折算成百分比
 * 胜率; 还没兑现的段照样计次数(它确实发生过), 但不进均值。
 */
function OutcomeChips({ items, forwardDays, hint }: {
  items: { key?: string; code?: string; label?: string; title?: string
           n: number; avg_days: number; scored: number
           avg_fwd: number | null; win: number
           tone?: KeltnerVerdict['tone'] }[]
  forwardDays: number
  hint: string
}) {
  if (items.length === 0) return null
  return (
    <div className="px-4 pt-4">
      <div className="mb-1.5 text-[10px] text-muted">{hint}</div>
      <div className="flex flex-wrap gap-1.5">
        {items.map((o) => {
          const id = o.key ?? o.code ?? ''
          const name = o.label ?? o.title ?? id
          const cls = o.tone ? VERDICT_CLS[o.tone] : 'border-border/60 bg-elevated/30 text-secondary'
          return (
            <span
              key={id}
              className={`inline-flex items-center gap-1.5 rounded border px-1.5 py-0.5 text-[10px] ${cls}`}
              title={
                `「${name}」在这只票上出现过 ${o.n} 段, 平均持续 ${o.avg_days} 天。`
                + (o.scored
                  ? `其中 ${o.scored} 段已够 ${forwardDays} 个交易日: 之后平均 ${pct(o.avg_fwd)}, ${o.win} 段收涨。`
                  : `还没有哪一段够 ${forwardDays} 个交易日, 结果未知。`)
                + ' 单位是段不是天 —— 段内每天的前瞻窗口互相重叠, 按天算会把同一次数很多遍。'
              }
            >
              {name}
              <span className="opacity-70">{o.n} 次</span>
              {o.scored > 0
                ? (
                  <>
                    <span className={`font-mono ${chgCls(o.avg_fwd)}`}>{pct(o.avg_fwd)}</span>
                    {/* [R191] 一致性摆到脸上, 不再只藏在悬停里。
                        「+7.9%」可能是一次 +40% 拉起来的, 也可能是四次都涨了两个点
                        —— 这两种情况该做的事完全不同, 而只给均值看不出是哪一种。 */}
                    <span className="font-mono opacity-55"
                          title={`${o.scored} 段已兑现, 其中 ${o.win} 段收涨 —— 均值容易被一两次极端行情带偏, 这个比才说明稳不稳`}>
                      {o.win}/{o.scored}
                    </span>
                  </>
                )
                : <span className="font-mono opacity-50">待定</span>}
            </span>
          )
        })}
      </div>
    </div>
  )
}

/**
 * [R191] 判定条 —— 这一栏唯一的**结论**。
 *
 * 其余四块(涨停计数、磨底、各状态 5 日均值、逐日表)全是测量: 摆的是数字, 得
 * 自己在脑子里换算才读得出该怎么办。而用户打开复盘带着的问题只有一个 ——
 * 「这套六态在**这只票**上灵不灵, 我该怎么用它」。
 *
 * 最关键的是它能认出**只有一半灵**的情况: 空头侧真跌、多头侧不涨, 意味着
 * 这只票的六态是离场信号而不是买入依据。这件事在四个并排的均值里看不出来,
 * 必须把同侧的段合起来才显形 —— 所以它得由系统算, 不能指望人去减。
 */
const EDGE_CLS: Record<string, string> = {
  both: 'border-red-400/40 bg-red-400/[0.07] text-red-300',
  offense: 'border-red-400/30 bg-red-400/[0.05] text-red-300/90',
  defense: 'border-amber-400/40 bg-amber-400/[0.07] text-amber-300',
  flat: 'border-border/60 bg-elevated/30 text-muted',
  inverted: 'border-emerald-400/40 bg-emerald-400/[0.07] text-emerald-300',
  thin: 'border-border/60 bg-elevated/20 text-muted',
}

function SideEdgeCard({ edge, forwardDays }: {
  edge: NonNullable<StockReview['side_edge']>
  forwardDays: number
}) {
  const sides: [string, { episodes: number; avg_fwd: number | null; win: number }][] = [
    ['多头侧 UT/NR/SR', edge.bull], ['空头侧 DT/NREA/SREA', edge.bear],
  ]
  return (
    <div className={cn('mx-4 mt-4 rounded-lg border px-3 py-2.5', EDGE_CLS[edge.level] ?? EDGE_CLS.flat)}>
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className="text-[10px] text-muted">六态在这只票上</span>
        <b className="text-[13px] font-semibold">{edge.label}</b>
        {edge.spread != null && (
          <span className="font-mono text-[10px] opacity-80"
                title={`多头侧平均 − 空头侧平均。两边差得越多, 说明六态在这只票上越有用`}>
            两边差 {(edge.spread * 100).toFixed(1)} 个点
          </span>
        )}
        {edge.level !== 'thin' && (
          <span className="ml-auto flex flex-wrap gap-x-3 text-[10px]">
            {sides.map(([name, v]) => (
              <span key={name} title={`${v.episodes} 段已够 ${forwardDays} 个交易日, 其中 ${v.win} 段收涨`}>
                <span className="text-muted">{name}</span>
                <b className={cn('ml-1 font-mono', chgCls(v.avg_fwd))}>{pct(v.avg_fwd)}</b>
                <span className="ml-1 opacity-60">{v.win}/{v.episodes}</span>
              </span>
            ))}
          </span>
        )}
      </div>
      <p className="mt-1 text-[10px] leading-relaxed opacity-90">{edge.text}</p>
    </div>
  )
}

/**
 * [R191] 「现在」条 —— 当前这一段与它自己的历史对上。
 *
 * 这些数原来全在页面上, 只是**散在三个地方**: 今天什么状态在表格第一行,
 * 这个状态平均持续多久在小结的悬停里, 翻转价压根没有。要回答「我现在在哪」
 * 得来回对三次。合成一句之后, 打开复盘第一眼就是答案。
 */
function NowCard({ now, forwardDays }: {
  now: NonNullable<StockReview['now']>
  forwardDays: number
}) {
  const bull = now.side === '多头'
  const gap = (line: number | null) =>
    line == null || !now.close ? null : (line - now.close) / now.close
  const dn = gap(now.flip_down)
  const up = gap(now.flip_up)
  return (
    <div className="mx-4 mt-3 rounded-lg border border-sky-400/30 bg-sky-400/[0.06] px-3 py-2.5">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 text-[11px]">
        <span className="text-[10px] text-muted">现在</span>
        <b className={cn('text-[13px] font-semibold', bull ? 'text-red-400' : 'text-emerald-400')}>
          {now.state_cn} 第 {now.day} 天
        </b>
        {now.avg_days != null && (
          <span className="text-muted"
                title="这只票上这个状态历史平均持续几天。不是预测 —— 只为回答「我在这一段的前段还是后段」">
            历史平均 {now.avg_days} 天{now.phase ? ` · 你在${now.phase}` : ''}
          </span>
        )}
        {/* 翻转价: 复盘完总得知道盯什么。距离按现价算, 与决策台同一口径 */}
        <span className="ml-auto flex flex-wrap gap-x-3 font-mono text-[10px]">
          {now.flip_down != null && (
            <span className="text-emerald-400/90" title="收盘跌破这个价转弱">
              跌破 {now.flip_down.toFixed(2)}
              {dn != null && <span className="ml-1 opacity-70">{(dn * 100).toFixed(1)}%</span>}
            </span>
          )}
          {now.flip_up != null && (
            <span className="text-red-400/90" title="收盘站上这个价转强">
              站上 {now.flip_up.toFixed(2)}
              {up != null && <span className="ml-1 opacity-70">+{(up * 100).toFixed(1)}%</span>}
            </span>
          )}
        </span>
      </div>
      <p className="mt-1 text-[10px] leading-relaxed text-muted">
        {now.scored > 0 ? (
          <>
            这只票历史上进入「{now.state_cn}」{now.n} 次,
            其中 {now.scored} 次已够 {forwardDays} 个交易日:
            之后平均 <b className={cn('font-mono', chgCls(now.avg_fwd))}>{pct(now.avg_fwd)}</b>,
            {now.scored} 次里 {now.win} 次收涨。
          </>
        ) : (
          <>这只票历史上进入「{now.state_cn}」{now.n} 次,还没有哪一次够 {forwardDays} 个交易日,结果未知。</>
        )}
      </p>
    </div>
  )
}

function TrendView({ d, rows, onlyMarked, onToggleMarked }: {
  d: StockReview
  rows: ReviewRow[]
  onlyMarked: boolean
  onToggleMarked: () => void
}) {
  return (
    <>
      {/* [R191] 结论在最上面, 测量在下面。
          原来顺序反过来: 打开先看见四个计数和一堆均值, 得自己换算才知道该怎么办。
          用户: 「不喜欢单纯的展示」—— 展示不是没用, 但它该在结论后面当依据。 */}
      {d.now && <NowCard now={d.now} forwardDays={d.forward_days} />}
      {d.side_edge && <SideEdgeCard edge={d.side_edge} forwardDays={d.forward_days} />}

      {/* [R188 加, R229 删]「磨底 N 天 / 箱体 / 红绿轮数 / 反复失败」那一块
          在这里删掉了。用户: 「红绿节拍移除掉」—— 整个规则层退役, 复盘接口
          不再返回 rhythm。 */}

      {/* ---- 以下是依据(测量), 摆在结论后面 ---- */}

      <div className="grid grid-cols-4 gap-3 px-4 pt-4">
        <div className="rounded-lg border border-red-400/20 bg-red-400/[0.05] px-4 py-3">
          <div className="text-[10px] text-muted">涨停</div>
          <div className="mt-1 font-mono text-2xl font-bold text-red-400">{d.stats.limit_ups}</div>
        </div>
        <div className="rounded-lg border border-border/60 bg-elevated/20 px-4 py-3">
          <div className="text-[10px] text-muted">最高连板</div>
          <div className="mt-1 font-mono text-2xl font-bold text-foreground">{d.stats.max_streak}</div>
        </div>
        <div className="rounded-lg border border-border/60 bg-elevated/20 px-4 py-3">
          <div className="text-[10px] text-muted" title="盘中最高触及涨停但收盘没封住">炸板</div>
          <div className="mt-1 font-mono text-2xl font-bold text-amber-400">{d.stats.broken_limit_ups}</div>
        </div>
        <div className="rounded-lg border border-emerald-400/20 bg-emerald-400/[0.05] px-4 py-3">
          <div className="text-[10px] text-muted">跌停</div>
          <div className="mt-1 font-mono text-2xl font-bold text-emerald-400">{d.stats.limit_downs}</div>
        </div>
      </div>

      {/* [R191] 封板率。「涨停 6 / 炸板 5」两个并排的计数要自己去除才读得出
          「这票封不住板」, 而那是这四张卡片里唯一能直接改变操作的信息。 */}
      {d.stats.seal && (
        <div className="px-4 pt-2 text-[10px] leading-relaxed text-muted">
          <span className={cn('font-mono',
            d.stats.seal.rate >= 0.75 ? 'text-red-400'
              : d.stats.seal.rate < 0.5 ? 'text-amber-400' : 'text-secondary')}>
            封板率 {(d.stats.seal.rate * 100).toFixed(0)}%
          </span>
          <span className="ml-2">{d.stats.seal.text}</span>
        </div>
      )}

      {/* 涨停出在什么状态下 —— 趋势里出的板和下跌途中的反抽完全是两回事 */}
      {d.stats.limit_up_states.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5 px-4 pt-2 text-[10px] text-muted">
          <span>涨停出现在:</span>
          {d.stats.limit_up_states.map((s) => (
            <span key={s.state_cn} className="rounded border border-border/60 bg-elevated/30 px-1.5 py-0.5 text-secondary">
              {s.state_cn} {s.n} 次
            </span>
          ))}
        </div>
      )}

      {/* [R177] 每种状态之后普遍怎么走 —— 上面「涨停出现在」回答的是另一个问题。
          [R191] 降到判定条下面: 它现在是 side_edge 那个结论的**分档依据**。 */}
      <OutcomeChips
        items={d.trend_outcomes ?? []}
        forwardDays={d.forward_days}
        hint={`分档依据 —— 各状态出现后 ${d.forward_days} 日表现(按段计, 一段=一次;样本小, 括号里是「几段收涨/几段已兑现」)`}
      />

      <div className="flex items-center justify-end px-4 pt-3">
        <button
          onClick={onToggleMarked}
          title="只留下有涨跌停、或趋势翻转的那些天 —— 其余日子状态没变, 复盘时没有信息"
          className={`rounded-btn border px-2 py-1 text-[10px] transition-colors cursor-pointer ${
            onlyMarked ? 'border-sky-400/40 bg-sky-400/15 text-sky-300' : 'border-border/60 text-muted hover:text-foreground'}`}
        >
          只看有事的日子
        </button>
      </div>

      <div className="mt-2 overflow-auto border-t border-border/60">
        <table className="w-full text-xs">
          <thead className="sticky top-0 z-10 bg-surface">
            <tr className="border-b border-border/60 text-[10px] text-muted">
              <th className="whitespace-nowrap px-3 py-2 text-left font-normal">日期</th>
              <th className="whitespace-nowrap px-2 py-2 text-right font-normal">收盘</th>
              <th className="whitespace-nowrap px-2 py-2 text-right font-normal">涨跌</th>
              <th className="whitespace-nowrap px-3 py-2 text-left font-normal">六态状态</th>
              <th className="whitespace-nowrap px-2 py-2 text-center font-normal" title="当天这个价位算贵还是算便宜 —— 与决策台「贵不贵」列同一句话, 悬停看完整卡片">贵不贵</th>
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
              <tr><td colSpan={5} className="px-3 py-10 text-center text-[11px] text-muted">这段时间里没有涨跌停, 状态也没翻转过</td></tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="border-t border-border/60 px-4 py-2 text-[10px] leading-relaxed text-muted">
        收盘口径, 与决策台「趋势」列同一个状态机、同一个阈值(含你自己调过的那个)。
        「贵不贵」列悬停看完整卡片, 要摊开每一档说了什么、之后走成什么样, 切到上方的「这个价贵不贵」。
      </div>
    </>
  )
}

// ===== 结论视图: 把每天的悬停卡片摊开 =====

/**
 * [R199] 「通道结论」栏的判定层 —— 结论在前, 数据降为依据。
 *
 * 用户: 「如何排版和内容的显示才能更有价值, 而不是展示单纯的数据,
 *        对我有指导性意义」。
 *
 * R198 我在这里摆了八个指标格 —— 那正是 R191 之前「趋势状态」栏犯过的错:
 * **全是测量, 没有一条是结论**。压缩 0.9 是好是坏? 分离度 2.4 呢? 单看每一个
 * 都答不了"我该怎么办"。
 *
 * 所以这一版分三层, 从上到下依次是:
 *   ① 现在处在哪一段(阶段判定) + 这一段该盯什么   ← 唯一的行动指引
 *   ② 位置结论在这只票上灵不灵(偏买档 vs 偏卖档)  ← 要不要信它
 *   ③ 那八个数                                    ← 前两条的依据
 */
const PHASE_CLS: Record<string, string> = {
  coiling: 'border-border/60 bg-elevated/40 text-secondary',
  launching: 'border-red-400/40 bg-red-400/[0.07] text-red-300',
  advancing: 'border-red-400/50 bg-red-400/10 text-red-300',
  stalling: 'border-amber-400/40 bg-amber-400/[0.07] text-amber-300',
  overextended: 'border-amber-400/50 bg-amber-400/10 text-amber-300',
  declining: 'border-emerald-400/40 bg-emerald-400/[0.07] text-emerald-300',
  unclear: 'border-border/60 bg-elevated/30 text-muted',
}

function PhaseCard({ ch }: { ch: NonNullable<StockReview['channel']> }) {
  const ph = ch.phase
  if (!ph) return null
  return (
    <div className={cn('mx-4 mt-4 rounded-lg border px-3 py-2.5', PHASE_CLS[ph.code] ?? PHASE_CLS.unclear)}>
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className="text-[10px] text-muted">现在处在</span>
        <b className="text-[13px] font-semibold">{ph.cn}</b>
        {ch.event.code !== 'none' && (
          <span className="text-[10px] opacity-90">
            {ch.event.cn}{ch.event.confirmed ? '' : '(未确认)'}
          </span>
        )}
      </div>
      <p className="mt-1 text-[10px] leading-relaxed opacity-90">{ph.why}</p>
      <p className="mt-1 text-[10px] leading-relaxed">
        <span className="text-muted">该盯什么:</span> {ph.watch}
      </p>
    </div>
  )
}

const EDGE_CLS2: Record<string, string> = {
  both: 'border-red-400/40 bg-red-400/[0.07] text-red-300',
  offense: 'border-red-400/30 bg-red-400/[0.05] text-red-300/90',
  defense: 'border-amber-400/40 bg-amber-400/[0.07] text-amber-300',
  flat: 'border-border/60 bg-elevated/30 text-muted',
  inverted: 'border-emerald-400/40 bg-emerald-400/[0.07] text-emerald-300',
  thin: 'border-border/60 bg-elevated/20 text-muted',
}

function VerdictEdgeCard({ e, forwardDays }: {
  e: NonNullable<StockReview['verdict_edge']>; forwardDays: number
}) {
  return (
    <div className={cn('mx-4 mt-3 rounded-lg border px-3 py-2.5', EDGE_CLS2[e.level] ?? EDGE_CLS2.flat)}>
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className="text-[10px] text-muted">位置结论在这只票上</span>
        <b className="text-[13px] font-semibold">{e.label}</b>
        {e.spread != null && (
          <span className="font-mono text-[10px] opacity-80" title="偏买档平均 − 偏卖档平均。两边差得越多, 说明这套位置结论越有用">
            两边差 {(e.spread * 100).toFixed(1)} 个点
          </span>
        )}
        {e.level !== 'thin' && (
          <span className="ml-auto flex flex-wrap gap-x-3 text-[10px]">
            {([['偏买档', e.buy], ['偏卖档', e.sell]] as const).map(([n, v]) => (
              <span key={n} title={`${v.episodes} 段已够 ${forwardDays} 个交易日, 其中 ${v.win} 段收涨`}>
                <span className="text-muted">{n}</span>
                <b className={cn('ml-1 font-mono', chgCls(v.avg_fwd))}>{pct(v.avg_fwd)}</b>
                <span className="ml-1 opacity-60">{v.win}/{v.episodes}</span>
              </span>
            ))}
          </span>
        )}
      </div>
      <p className="mt-1 text-[10px] leading-relaxed opacity-90">{e.text}</p>
    </div>
  )
}

/**
 * ③ 依据 —— **数据 + 一句解释**, 一行一条。
 *
 * ## [R212] 这一块改过三版, 每一版都错在同一个地方的不同侧面
 *
 *   v1  只给数字(`+1.4` `-1.3` `10%` `中下中`)。用户: 「用数字看不懂」——
 *       对的: 得先知道"多少算大"才读得出好坏, 而那正是不该逼人记的东西。
 *   v2  只给状态词(`比之前快` `走到中段` `完全分开`)。用户: 「仍旧看不懂,
 *       获取不到结论性信息」—— 也对: 「走到中段」**然后呢**? 该做的那一步
 *       合成仍然留给了用户。
 *   v3  用户自己给了答案: 「你干脆保持数据, 然后在后面加一行解释」。
 *
 * 三样缺一不可: **名称**(这个数在说什么)、**数值**(能核对)、**解释**(所以呢)。
 * 格子放不下第三样, 所以这里从格子墙改成了一张三列的表。
 *
 * 文案在后端(`keltner_geometry.explain`), 前端只排版 —— 「多少算大」的分界
 * 只该有一处定义。
 */
function ChannelPanel({ ch }: { ch: NonNullable<StockReview['channel']> }) {
  const { event, explain } = ch
  return (
    <div className="mx-4 mt-3 space-y-2">
      <div className="text-[10px] text-muted">依据(上面两条结论就是从这些读数出来的)</div>
      {/* [R212] **数据保留, 后面跟一句解释。** 用户: 「你干脆保持数据, 然后在
          后面加一行解释」。格子放不下第三样, 所以这里是表不是格子墙。 */}
      {!!explain?.length && (
        <div className="overflow-hidden rounded-card border border-border/50">
          {explain.map((r, i) => (
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
      {!!event.combo_note && (
        <p className="rounded border border-amber-400/30 bg-amber-400/[0.06] px-2.5 py-1.5 text-[10px] leading-relaxed text-amber-300/90">
          组合「{event.combo_note.combo}」· {event.combo_note.title}:{event.combo_note.detail}
        </p>
      )}
    </div>
  )
}

function VerdictView({ d, segments }: { d: StockReview; segments: Segment[] }) {
  return (
    <>
      {/* [R199] 三层, 从上到下: 现在在哪一段 → 这套结论灵不灵 → 依据 */}
      {!!d.channel && <PhaseCard ch={d.channel} />}
      {!!d.verdict_edge && <VerdictEdgeCard e={d.verdict_edge} forwardDays={d.forward_days} />}
      {!!d.channel && <ChannelPanel ch={d.channel} />}

      {/* 各档结论在这只票上过去好不好使 */}
      <OutcomeChips
        items={d.outcomes}
        forwardDays={d.forward_days}
        hint={`分档依据 —— 各档结论出现后 ${d.forward_days} 日表现(按段计, 一段=一次;括号里是「几段收涨/几段已兑现」)`}
      />

      <div className="mt-3 flex-1 overflow-auto border-t border-border/60 p-4">
        {segments.length === 0 && (
          <div className="py-14 text-center text-[11px] text-muted">
            这段时间里三档通道一直在中部 —— 位置上没有可说的, 听趋势和信号的
          </div>
        )}
        <div className="space-y-2.5">
          {segments.map((seg) => <SegmentCard key={seg.rows[0].date} seg={seg} forwardDays={d.forward_days} />)}
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

/**
 * 一段结论 = 决策台上当时悬停会看到的那张卡片, 加上"这几天实际走了什么"。
 *
 * 「之后 N 日」取这一段**最后一天**的前瞻收益 —— 一档结论连着出现几天时,
 * 真正该问的是"它最后一次说完之后怎么样了", 拿段首那天算等于把段内的涨跌
 * 也算进兑现里。
 */
function SegmentCard({ seg, forwardDays }: { seg: Segment; forwardDays: number }) {
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
