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
 * 动效: 一个都没加 —— 这一栏是读数, 不是需要"活起来"的东西。
 */
import type { StockReview } from '@/lib/api'
import { cn } from '@/lib/cn'

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

/**
 * [R288] 两个页签共用一处实现 —— 用户: 「通道结论这个部分也能这样搞类似的统计吗」。
 *
 * 差别全在文案(什么算一次变化、变化之后按什么动手), 版面与配色一个字不改:
 * **两栏量的是同一件事**(真按它做赚了多少), 长得不一样只会让人以为它们不可比。
 */
/**
 * 那几条「别当真」的提醒。**与数字同进同出** —— 数字在正文、提醒收进别处,
 * 就等于把 +143% 摆出来而把「样本太少」藏起来, 那是骗人。
 *
 * [R302] `caveat` 那个入参删了。它当初装的是「按结论买卖」的**口径偏差**
 * (「拿着」不动手、卖出侧比作者原话重), 而这条纪律守的是**这只票的**警告:
 * 样本太少、撞上涨跌停、最后一次还没执行 —— 这些每只票各不相同, 不说就是骗人。
 * 口径偏差正相反, 它**每只票都一样**, 常驻正文只是每张卡顶上挂一块恒定的黄字。
 * 它搬到「说明」页的「通道结论」那一节去了, 正文那一行指过去。
 */
export function tradeNotes(ft: FlipTrades): string[] {
  return [
    ft.thin && `只走完 ${ft.bull.scored} 段多头, 样本太少, 这几个数只能当参考`,
    !!ft.blocked && `其中 ${ft.blocked} 笔的成交日当天涨停或跌停 —— 未必真成交得到这个价`,
    !!ft.pending && `${ft.pending} 那次变化的次日还没到, 没算进去`,
    !!ft.skipped.length && `有 ${ft.skipped.length} 次变化因为缺开盘价没能执行`,
  ].filter(Boolean) as string[]
}


/**
 * [R289] 压成一条的「按…买卖」—— 正文里常驻的就是这一条。
 *
 * 用户: 「我只关注最核心的东西 …… 比如按照转折点买卖和底部部分可以融合到一起
 * 显示」。融合的做法是: **摘要留在正文顶上一行, 每一段那张表整个并进逐日表** ——
 * 那两张表本来就是同一条时间轴(逐日表里标「转折」的行, 正是每一段的起点),
 * 拆成两张等于让人左右对眼去把日子接起来。
 */
export function FlipTradesBar({ ft, basis }: {
  ft?: FlipTrades | null
  basis: string
}) {
  if (!ft) return null
  // [R301] `title` 这个入参删了 —— 两个调用方一直传的都是空串, 而这一栏的
  // 标题本来就写在 `HeadRow` 的左栏里(「按转折买卖」/「按结论买卖」)。
  // 留着就是"看起来在用、其实永远是空"的那类死参数。
  if (ft.reason) return <div className="text-[10px] text-muted">{REASON_CN[ft.reason]}</div>
  const notes = tradeNotes(ft)
  return (
    <div>
      {/* [R301] **四个数排成等宽格子**, 不再是一条 `flex-wrap` 的杂排。
          用户: 「内容显示整理好划分好卡片布局, 现在的显示不对齐」。

          原来这一行把三种字号(`text-lg` / `text-sm` / `text-[10px]`)、四个
          长短不一的标签、外加 `basis` 一整句话全塞进同一条 `items-baseline`
          里 —— **没有任何两样东西的边是对齐的**, 而且 `text-lg` 那个数把整行
          撑高, 后面几个数被顶得偏下。

          改成 `grid-cols-4`: 每格上标签下数值, 于是**标签与标签一条线、数值与
          数值一条线**。四个数字号统一(`text-base`), 「跟着做」靠**它排第一 +
          着色 + 加粗**来突出 —— 用更大的字号做强调, 代价正好是把这一行的
          基线打散, 而这一行的毛病就是基线散。 */}
      <div className="grid grid-cols-2 gap-x-3 gap-y-1.5 sm:grid-cols-4">
        <Stat label="跟着做" value={ft.follow} lead
              title="只把已经走完的多头段复利叠起来。空仓期不算收益。" />
        <Stat label="一直拿着" value={ft.hold}
              title="同一段区间买了就不动 —— 与「跟着做」同起点同终点, 所以能直接比。" />
        <Stat label="多赚" value={ft.excess}
              title="跟着做 − 一直拿着。正的才说明这套判定在这只票上真的帮上忙了。" />
        <div title="真正下过单的次数。连着的多头段是一次持仓, 不是两次买卖">
          <div className="text-[10px] text-muted">买卖</div>
          <div className="font-mono text-base tabular-nums text-secondary">{ft.trades} 次</div>
        </div>
      </div>
      {/* 口径**自己一行**。原来它跟在四个数后面挤在同一条 flex 里, 一句话把那
          一行撑到换行, 数值就再也排不齐了 —— 它是脚注, 不是第五个指标。 */}
      <p className="mt-1.5 text-[10px] leading-relaxed text-muted">{basis}</p>
      {notes.map((t) => (
        <p key={t} className="mt-1 text-[10px] leading-relaxed text-amber-300/90">{t}</p>
      ))}
    </div>
  )
}


/** 按「触发这一笔的那一天」索引 —— 逐日表就是拿这个把两张表接起来的 */
export function legsByFlipDate(ft?: FlipTrades | null): Map<string, Leg> {
  return new Map((ft?.legs ?? []).map((l) => [l.flip_date, l]))
}


/**
 * [R289] 并进逐日表的那三格。**只有三格**, 因为原来那张表里另外两列是重复的:
 * 「转折日」就是这一行自己的日期,「变成什么」就是同一行的六态状态列。
 * 融合本来就该把重复的挤掉, 不然只是把两张表并排贴在一起。
 */
export function FlipTradeCells({ leg }: { leg?: Leg }) {
  if (!leg) {
    return (
      <>
        <td /><td /><td />
      </>
    )
  }
  return (
    <>
      <td className="whitespace-nowrap px-2 py-1.5">
        <span className={cn('inline-flex rounded border px-1 py-px text-[10px]', ACT_CLS[leg.act])}>
          {leg.act}
        </span>
        {leg.blocked && (
          <span className="ml-1 text-[9px] text-amber-400"
                title="成交日当天涨停或跌停, 未必真成交得到这个价">·封</span>
        )}
      </td>
      <td className="whitespace-nowrap px-2 py-1.5 text-right font-mono text-[10px] tabular-nums text-muted">
        <span className="text-secondary">{leg.enter_date.slice(5)} {leg.enter_price.toFixed(2)}</span>
        <span className="mx-1 opacity-50">→</span>
        {leg.exit_date.slice(5)} {leg.exit_price.toFixed(2)}
        {leg.open_ended && (
          <span className="ml-1 text-amber-400/80"
                title="这一段还没走完 —— 按最后一天收盘价记, 不进胜负统计">未完</span>
        )}
      </td>
      {/* 多头段是真金白银 → 涨红跌绿; 空头段是空仓期 → 灰字写「躲开/踏空」。
          同一列两套写法是**故意的**: 它们根本不是同一种数。 */}
      <td className={cn('whitespace-nowrap px-2 py-1.5 text-right font-mono text-[10px] tabular-nums',
                        leg.side === '多头' ? chgCls(leg.ret) : 'text-muted')}>
        {leg.side === '多头' ? pct(leg.ret) : idleText(leg.ret)}
        <span className="ml-1 opacity-50">{leg.bars}天</span>
      </td>
    </>
  )
}


/** 一格 = 上标签下数值。**四格同字号** —— 「跟着做」是主角, 但它靠排第一 +
 *  着色 + 加粗突出, 不靠更大的字号(R301: 大一号的代价正好是把这一排的基线
 *  打散, 而"不对齐"就是用户指出来的毛病)。 */
function Stat({ label, value, lead, title }: {
  label: string; value: number | null
  /** 这一格是这排数里的主角 —— 靠加粗与位置突出, **不靠更大的字号** */
  lead?: boolean
  title: string
}) {
  return (
    <div title={title}>
      <div className={cn('text-[10px]', lead ? 'text-secondary' : 'text-muted')}>{label}</div>
      <div className={cn('font-mono text-base tabular-nums', lead && 'font-semibold', chgCls(value))}>
        {pct(value)}
      </div>
    </div>
  )
}


/**
 * [R293] 并进「通道结论」卡片的那一行 —— 与逐日表那三格是**同一份内容**,
 * 只是从 `<td>` 换成了行内排版(卡片不是表格)。
 *
 * 用户: 「通道结论这部分的关注重点是『调整到位』和这些状态期间的买卖」;
 * 「你可以理解为核心是按结论买卖」—— 那就把"这一段里手上做了什么、结果如何"
 * 直接长在那一段的卡片上, 而不是让人在另一张表里按日期找回来。
 */
export function FlipTradeLine({ leg }: { leg?: Leg }) {
  if (!leg) return null
  return (
    <div className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 rounded border border-border/60 bg-base/60 px-2 py-1">
      <span className="text-[9px] text-muted">按结论买卖</span>
      <span className={cn('inline-flex rounded border px-1 py-px text-[10px]', ACT_CLS[leg.act])}>
        {leg.act}
      </span>
      {leg.blocked && (
        <span className="text-[9px] text-amber-400"
              title="成交日当天涨停或跌停, 未必真成交得到这个价">·封</span>
      )}
      <span className="font-mono text-[10px] tabular-nums text-muted">
        <span className="text-secondary">{leg.enter_date.slice(5)} {leg.enter_price.toFixed(2)}</span>
        <span className="mx-1 opacity-50">→</span>
        {leg.exit_date.slice(5)} {leg.exit_price.toFixed(2)}
        {leg.open_ended && (
          <span className="ml-1 text-amber-400/80"
                title="这一段还没走完 —— 按最后一天收盘价记, 不进胜负统计">未完</span>
        )}
      </span>
      {/* 多头段是真金白银 → 涨红跌绿; 空头段是空仓期 → 灰字写「躲开/踏空」。
          与逐日表那一列**同一套写法**: 它们根本不是同一种数。 */}
      <span className={cn('ml-auto font-mono text-[10px] tabular-nums',
                          leg.side === '多头' ? chgCls(leg.ret) : 'text-muted')}>
        {leg.side === '多头' ? pct(leg.ret) : idleText(leg.ret)}
        <span className="ml-1 opacity-50">{leg.bars}天</span>
      </span>
    </div>
  )
}

// [R287 加, R293 删] `FlipTradesPanel`(整块面板 + 「每一段」折叠表)在这里删掉了。
// 两个页签现在都是**摘要压成一条 + 明细并进正文**: 趋势状态并进逐日表(R289),
// 通道结论并进那一张张段落卡片(R293)。留着那块面板就是同一份明细印两处。
