/**
 * [fork 增强 R287] 复盘·趋势状态那一栏的「按转折买卖」。
 *
 * 用户: 「我想统计每两个转折之间的收益, 也就是说出现转折我第二天开盘就买或者卖,
 * 这个根据转折后的状态判断, 就在趋势状态这个页面显示统计」。
 *
 * ## 为什么它排在「分档依据」下面、「依据」上面
 *
 * 这一页从上到下是 **结论 → 证据 → 原始记录**:
 *
 *   现在(NowCard)        今天在哪一段、盯哪个价
 *   状态时间轴            这半年整体怎么走的
 *   分档依据(OutcomeChips) 各状态之后 **5 日** 平均怎么走      ← 固定窗口的测量
 *   **按转折买卖(这一件)**  真按它做, 拿到下次转折为止是赚是亏  ← 兑现后的成绩单
 *   依据(TrendStatsPanel)  涨跌停计数、封板率                  ← 背景资料
 *   逐日表                 原始记录
 *
 * 它必须在「分档依据」**之后**: 那一栏是这一栏的输入直觉(状态之后一般怎么走),
 * 而这一栏是把那个直觉真的执行一遍之后的结果。它必须在「依据」**之前**: 这是
 * 结论级的东西, 而「依据」是背景资料。
 *
 * 两栏量的**不是同一件事**, 所以并排放着不算重复:
 * 分档依据把每一段都截成 5 天; 这一栏是拿到下次转折为止, 一段可能 3 天也可能
 * 40 天。用户的哲学是「尽可能减少买卖次数, 趋势为王」—— 5 日窗口恰恰量不到
 * 「拿住」这件事值多少钱。
 *
 * ## 三条不许含糊的地方
 *
 * 1. **空头段不是盈亏。** A 股散户做不了空, 那一段是空仓期。所以空头段的数字
 *    一律写成「躲开 x%」/「踏空 x%」, **不用涨跌红绿**, 免得被读成赚了赔了。
 * 2. **撞上涨跌停的成交要标出来。** 转折日常常就是跌停日(截图那只票 120 天里
 *    跌停 6 次), 次日开盘要是继续一字, 那一笔根本成交不了, 而统计照样会拿那个
 *    开盘价给你算一个漂亮的"躲开 10%"。不标就是骗自己。
 * 3. **空栏要自己解释。** 分不清"这段时间确实没转折"和"数据缺了算不出来",
 *    是这个仓库反复吃过的亏。
 *
 * 动效: 一个都没加 —— 折叠复用既有的 `ReviewDisclosure`(它只有雪佛龙的
 * `transition-transform`)。这一栏是读数, 不是需要"活起来"的东西。
 */
import type { StockReview } from '@/lib/api'
import { cn } from '@/lib/cn'
import { ReviewDisclosure } from '@/components/stock-analysis/ReviewDisclosure'

type FlipTrades = NonNullable<StockReview['flip_trades']>
type Leg = FlipTrades['legs'][number]

function pct(v: number | null | undefined, digits = 1): string {
  return v == null ? '—' : `${v > 0 ? '+' : ''}${(v * 100).toFixed(digits)}%`
}

// A股习惯: 涨红跌绿。与本页其余读数同一套 —— 两处不同色的话, 同一个正数
// 在这一栏是红、在逐日表是绿, 读的人得先确认哪个是涨。
function chgCls(v: number | null | undefined): string {
  if (v == null || v === 0) return 'text-muted'
  return v > 0 ? 'text-red-400' : 'text-emerald-400'
}

/** 空仓段那一格的话。**故意不带正负号也不带红绿** —— 见文件头第 1 条。 */
function idleText(ret: number): string {
  return ret <= 0 ? `躲开 ${(-ret * 100).toFixed(1)}%` : `踏空 ${(ret * 100).toFixed(1)}%`
}

const ACT_CLS: Record<Leg['act'], string> = {
  买入: 'border-red-400/45 bg-red-400/10 text-red-300',
  卖出: 'border-emerald-400/45 bg-emerald-400/10 text-emerald-300',
  // 「持有」「空仓」= 这次转折不用动手。**刻意是灰的** —— 它们不是操作,
  // 上了色就会被数进"我这半年买卖了几次"里。
  持有: 'border-border/60 text-muted',
  空仓: 'border-border/60 text-muted',
}

const REASON_CN: Record<NonNullable<FlipTrades['reason']>, string> = {
  no_flip: '这段时间里六态一次都没转折 —— 没有可统计的买卖',
  no_open: '缺开盘价, 这一栏算不出来(次日开盘是唯一能执行的时机)',
}

export function FlipTradesPanel({ ft }: { ft?: FlipTrades | null }) {
  if (!ft) return null

  if (ft.reason) {
    return (
      <div className="mx-4 mt-3 rounded-btn border border-border/60 px-3 py-2 text-[10px] text-muted">
        <span className="text-secondary">按转折买卖</span> · {REASON_CN[ft.reason]}
      </div>
    )
  }

  const notes = [
    ft.thin && `只走完 ${ft.bull.scored} 段多头, 样本太少, 这几个数只能当参考`,
    !!ft.blocked && `其中 ${ft.blocked} 笔的成交日当天涨停或跌停 —— 未必真成交得到这个价`,
    !!ft.pending && `${ft.pending} 那次转折的次日还没到, 没算进去`,
    !!ft.skipped.length && `有 ${ft.skipped.length} 次转折因为缺开盘价没能执行`,
  ].filter(Boolean) as string[]

  return (
    <div className="mx-4 mt-3 rounded-btn border border-border/60 bg-elevated/20 px-3 py-2.5">
      <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
        <span className="text-[11px] text-secondary">按转折买卖</span>
        <span className="text-[10px] text-muted">
          转折次日开盘进出 · 转多买入、转空清仓(不做空)
        </span>
      </div>

      {/* 三个数一行。**「跟着做」最大** —— 它就是用户带着的那个问题的答案,
          另外两个是它的参照物。 */}
      <div className="mt-2 flex flex-wrap items-baseline gap-x-6 gap-y-1.5">
        <Stat label="跟着做" value={ft.follow} big
              title="只把已经走完的多头段复利叠起来。空仓期不算收益。" />
        <Stat label="一直拿着" value={ft.hold}
              title="同一段区间买了就不动 —— 与「跟着做」同起点同终点, 所以能直接比。" />
        <Stat label="多赚" value={ft.excess}
              title="跟着做 − 一直拿着。正的才说明这套转折在这只票上真的帮上忙了。" />
      </div>

      <p className="mt-1.5 text-[10px] leading-relaxed text-muted">
        {/* 「买卖 N 次」是用户交易哲学里最在意的数, 所以摆在最前面。
            它**不等于段数** —— 连着的多头段(比如自然回升转上涨趋势)是一次持仓。 */}
        买卖 <b className="text-secondary">{ft.trades}</b> 次 · 多头 {ft.bull.n} 段
        {ft.bull.scored > 0 && <>(走完 {ft.bull.scored} 段, {ft.bull.win} 段收涨)</>}
        {ft.from_date && ` · ${ft.from_date} → ${ft.to_date}`}
      </p>

      {notes.map((t) => (
        <p key={t} className="mt-1 text-[10px] leading-relaxed text-amber-300/90">{t}</p>
      ))}

      <ReviewDisclosure
        label="每一段"
        note={`· ${ft.legs.length} 段, 与逐日表上标「转折」的那些天一一对应`}
        className="mx-0 mt-2"
      >
        <LegTable legs={ft.legs} />
      </ReviewDisclosure>
    </div>
  )
}

function Stat({ label, value, big, title }: {
  label: string; value: number | null; big?: boolean; title: string
}) {
  return (
    <span className="inline-flex items-baseline gap-1.5" title={title}>
      <span className="text-[10px] text-muted">{label}</span>
      <b className={cn('font-mono tabular-nums', big ? 'text-lg' : 'text-sm', chgCls(value))}>
        {pct(value)}
      </b>
    </span>
  )
}

function LegTable({ legs }: { legs: Leg[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-[10px]">
        <thead>
          <tr className="border-b border-border/60 text-muted">
            <th className="whitespace-nowrap py-1 pr-2 text-left font-normal">转折日</th>
            <th className="whitespace-nowrap px-2 py-1 text-left font-normal">动作</th>
            <th className="whitespace-nowrap px-2 py-1 text-left font-normal">转成什么</th>
            <th className="whitespace-nowrap px-2 py-1 text-right font-normal">成交</th>
            <th className="whitespace-nowrap px-2 py-1 text-right font-normal">了结</th>
            <th className="whitespace-nowrap px-2 py-1 text-right font-normal">持</th>
            <th className="whitespace-nowrap py-1 pl-2 text-right font-normal">结果</th>
          </tr>
        </thead>
        <tbody>
          {legs.map((l) => (
            <tr key={l.flip_date} className="border-b border-border/30 last:border-0">
              <td className="whitespace-nowrap py-1 pr-2 font-mono text-secondary">{l.flip_date}</td>
              <td className="whitespace-nowrap px-2 py-1">
                <span className={cn('inline-flex rounded border px-1 py-px', ACT_CLS[l.act])}>
                  {l.act}
                </span>
                {/* 撞板标记就挂在动作旁边 —— 它说的正是"这个动作未必做得成" */}
                {l.blocked && (
                  <span className="ml-1 text-amber-400"
                        title="成交日当天涨停或跌停, 未必真成交得到这个价">·封</span>
                )}
              </td>
              <td className="whitespace-nowrap px-2 py-1 text-muted">{l.state_cn}</td>
              <td className="whitespace-nowrap px-2 py-1 text-right font-mono tabular-nums text-secondary">
                {l.enter_date.slice(5)} {l.enter_price.toFixed(2)}
              </td>
              <td className="whitespace-nowrap px-2 py-1 text-right font-mono tabular-nums text-muted">
                {l.exit_date.slice(5)} {l.exit_price.toFixed(2)}
                {l.open_ended && <span className="ml-1 text-amber-400/80" title="这一段还没走完 —— 按最后一天收盘价记, 不进胜负统计">未完</span>}
              </td>
              <td className="whitespace-nowrap px-2 py-1 text-right font-mono tabular-nums text-muted">{l.bars}</td>
              {/* 多头段是真金白银 → 涨红跌绿; 空头段是空仓期 → 灰字写「躲开/踏空」。
                  同一列两套写法是**故意的**: 它们根本不是同一种数。 */}
              <td className={cn('whitespace-nowrap py-1 pl-2 text-right font-mono tabular-nums',
                                l.side === '多头' ? chgCls(l.ret) : 'text-muted')}>
                {l.side === '多头' ? pct(l.ret) : idleText(l.ret)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
