/**
 * [fork 增强] 决策台的两个只读单元格: Keltner 三档位置 / 三档组合结论。
 *
 * [R167] 从 WatchlistDecisionBoard.tsx 拆出。各自带着自己的配色表 —— 配色表是
 * 实现细节, 不该摆在 933 行主文件的顶部让人以为是全局约定。
 */
import type { BandEnergy, ChannelEvent, ChannelGeometry, ChannelPhase, ChannelRuns, KeltnerBand, KeltnerVerdict, Playbook } from '@/lib/api'
import { VerdictHover } from '@/components/stock-analysis/VerdictHover'

/**
 * [R194] 决策台单元格的统一基线。**整张表只有这一处定义垂直对齐与行内边距。**
 *
 * 上一版参差的原因就是没有这一处: 行内 td 写 `py-2.5` 走默认居中、Keltner 与
 * 结论写 `px-1.5 py-2.5`、R193 的「该动」写 `py-1.5 align-top` —— 三套各写各的。
 * 平时看不出来, 一旦某行的「该动」是三行、「AI 信号」是三行, 单行的那几列
 * (现价/涨跌/浮盈/置信)就飘到了行的**垂直中间**, 而多行的那几列贴着顶,
 * 一屏扫下来没有任何一条共同的基线。
 *
 * [R198] 由 `align-top` 改成 `align-middle text-center` —— 用户: 「内容都要
 * 居中对齐每一行每一列」。
 *
 * R194 当时选顶对齐, 是因为那时只有三列天然多行、行高差得远, 居中会让
 * "这一行从哪儿开始读"每行都不一样。R198 把「该动」并进标的、三档并成一列
 * 之后, **多行的格子反而每行都有且行数接近**, 居中于是成了更稳的选择:
 * 每一格都落在自己那一行的正中。
 *
 * 水平方向一并统一成居中并写进这个常量, 于是表头与单元格天然对齐 ——
 * R194 那种"逐列核对表头与单元格是否同向"的活儿从此不存在。
 */
export const TD_BASE = 'align-middle py-2 text-center'

/**
 * 数字列的统一写法。`tabular-nums` 是**列对齐的关键**: 没有它, 比例字形下
 * `1` 比 `8` 窄, 386.50 与 1088.00 的小数点在列里就对不齐, 一列数字看着像
 * 波浪线。只给 `font-mono` 不够 —— 有些等宽字体的数字仍走比例宽度。
 */
export const NUM = 'font-mono tabular-nums'

// [R211] `ChannelStackCell`(三档竖排那一列)在这里删掉了 —— 它并进了
// `ChannelStateCell`。用户: 「趋势通道和通道态势可以放在一起吗」。
//
// **本来就该合**: 两列讲的是同一套指标的两个层次(一个是测量, 一个是从它推出来
// 的结论), 拆成两列等于让人左右对眼去把结论和它的依据接起来。
//
// 合的时候顺手改了一处: 三档位置**只印到边的那几档**。多数票三档都在通道中部,
// 把三个「通道内」逐行印出来是纯噪声 —— 恰恰是"哪一档到边了"才带信息。
// 完整的三档轨价与位置百分比留在悬停。

// [R44] 三档组合的结论配色。tone 由后端给, 界面不自己判 ——
// 决策台、今日总览、悬停提示必须说同一句话。
const VERDICT_CLS: Record<KeltnerVerdict['tone'], string> = {
  sell: 'border-red-400/40 bg-red-400/10 text-red-400',
  buy: 'border-sky-400/40 bg-sky-400/10 text-sky-300',
  hold: 'border-amber-400/40 bg-amber-400/10 text-amber-400',
  avoid: 'border-border bg-base text-muted',
  // [R45] 观察档: 还不到动手的时候, 用最淡的一档, 跟四个动作档区分开
  watch: 'border-border bg-elevated/60 text-secondary',
}

// [R195] 事件配色。**已确认与未确认必须一眼分得开** —— 「突破尝试」与
// 「突破站稳」差的就是那两天, 把它们画成一样就是在鼓励追第一天的假突破。
const EVENT_CLS: Record<string, string> = {
  main_advance: 'text-red-300 font-medium',      // 主升浪: 五条全中
  trend_accel: 'text-red-400/85',
  breakout_hold: 'text-red-400/85',
  breakout_try: 'text-amber-400/80',             // 未确认 —— 暖色但不实
  pullback_end: 'text-amber-400/80',
  coiling: 'text-secondary/80',
  exhausting: 'text-amber-300',
  bounce_cap: 'text-emerald-400/85',
  shakeout: 'text-amber-400/80',
  breakdown_try: 'text-emerald-400/70',
  breakdown_hold: 'text-emerald-400/85',
  none: 'text-muted/40',
}

/** 几何量摊成悬停里的几行 —— 速度/加速度/压缩/排列, 外加 27 组合的补充注记。 */
function geoLines(geo?: ChannelGeometry | null, ev?: ChannelEvent | null,
                  runs?: ChannelRuns | null, energy?: BandEnergy | null,
                  ph?: ChannelPhase | null): string {
  if (!geo) return ''
  const L: string[] = []
  // [R200] 阶段摆在最前面。悬停这一片本来全是测量 —— 先给一句"现在处在哪一段、
  // 该盯什么", 后面那些数才有落点。这句话之前只有复盘弹窗里有。
  if (ph) L.push('', `【${ph.cn}】${ph.why}`, `该盯什么:${ph.watch}`)

  // [R219] **一个话题一行, 不许拆到上下两处。** 用户: 「每一列的内容应该就是
  // 一部分, 而不是内容上面一部分下面一部分」。
  //
  // 原来这段是流水账: 快慢在最上面, 「三条线还有 X% 重合」在第三行, 而同属
  // 重合这个话题的「已经这样 N 天」「这季平均 Y%」掉到第五、六行, 中间隔着
  // 「价格离各自中线」。读的人得自己把同一件事从两处捡回来拼上。
  //
  // 现在每行以 [话题] 开头, 同一话题的数全在那一行里, 顺序也按"先看什么"排:
  // 位置 → 间距 → 重合 → 快慢 → 起伏 → 在轨外。
  L.push('', '—— 量化波动通道 ——')
  const at2 = (x: number) => `${x >= 0 ? '' : '-'}${Math.abs(x).toFixed(1)}`
  L.push(`[位置] 价格离各自中线:短期 ${at2(geo.d.s)} / 中期 ${at2(geo.d.m)} / 长期 ${at2(geo.d.l)} 倍日常波动(正的偏贵、负的偏便宜)`)
  L.push('[间距] ' + (geo.torn
    ? `短线和长线离得太远(差 ${Math.abs(geo.spread).toFixed(1)} 倍日常波动),已经没有共同认可的合理价`
    : geo.nested
      ? `三条线几乎挤在一块,只差 ${Math.abs(geo.spread).toFixed(1)} 倍日常波动`
      : geo.spread >= 0
        ? `短线高出长线 ${geo.spread.toFixed(1)} 倍日常波动`
        : `短线低于长线 ${Math.abs(geo.spread).toFixed(1)} 倍日常波动`))
  // 重合的三个数原来散在三处 —— 它们回答的是同一个问题, 并成一行
  if (geo.compress != null || runs?.compress_days || runs?.compress_avg != null) {
    L.push('[重合] ' + [
      geo.compress != null ? `三条线还有 ${(geo.compress * 100).toFixed(0)}% 重合` : '',
      runs?.compress_days ? `已经这样 ${runs.compress_days} 天` : '',
      runs?.compress_avg != null ? `整个季度平均 ${(runs.compress_avg * 100).toFixed(0)}%` : '',
    ].filter(Boolean).join(' · '))
  }
  const a = geo.accel
  if (a?.level_cn) {
    L.push(`[快慢] 最近这十天比前一段${a.gain_atr >= 0 ? '多' : '少'}走了 ${Math.abs(a.gain_atr).toFixed(1)} 倍日常波动(${a.level_cn})`)
  }
  if (energy) {
    const sh = energy.share
    // [R219] 尾注跟着 R217 改基准一起更正 —— 原来写「各 33% 是一路匀速走的
    // 样子」, 那是**老基准**的说法。现在的零假设是"这只票什么也没发生"。
    L.push(`[起伏] 主要来自${energy.dominant_cn}${energy.lead_cn ? `(${energy.lead_cn})` : ''}`
      + ` —— 短波动 ${(sh.s * 100).toFixed(0)}% / 行情主体 ${(sh.m * 100).toFixed(0)}%`
      + ` / 老趋势 ${(sh.l * 100).toFixed(0)}%(和纯噪声比,各 33% 是不偏不倚)`)
  }
  if (runs?.above_run || runs?.below_run) {
    L.push('[在轨外] ' + (runs.above_run
      ? `连着 ${runs.above_run} 天站在短线上沿之外`
      : `连着 ${runs.below_run} 天掉在短线下沿之外`))
  }
  if (ev?.why) L.push('', `【事件】${ev.cn} —— ${ev.why}`)
  if (ev?.combo_note) {
    L.push('', `【组合补充】「${ev.combo_note.combo}」· ${ev.combo_note.title}`, ev.combo_note.detail)
  }
  return L.join('\n')
}

/**
 * 「通道结论」单元格 —— 三档组合翻成一句人话。
 *
 * 徽标只放 4-6 字的结论标题, 悬停给分段排版的完整卡片(R49, 见 VerdictHover),
 * 点击翻这只票的逐日复盘(R48) —— 这一列说的话在它身上过去好不好使, 只有
 * 翻历史才知道。短期档在通道中部时显示 "—": 那时这一列确实没有信息。
 *
 * [R195] 徽标下面多一行**事件**。结论说的是"位置", 事件说的是"这是什么事" ——
 * 同一个「短线冲高」, 在上涨趋势里是趋势内加速、在下跌趋势里是反弹撞阻力,
 * 位置那一层分不出来。**摆在明面上而不是塞进悬停**: R193 的教训是一列 80 行
 * 是用来扫的, 扫的时候没人会悬停。未确认的事件用虚一档的颜色, 因为
 * 「突破尝试」与「突破站稳」差的就是那两天。
 */
function VerdictInner({ v, ev, geo, runs, energy, ph, onOpen }: {
  v?: KeltnerVerdict | null
  ev?: ChannelEvent | null
  geo?: ChannelGeometry | null
  runs?: ChannelRuns | null
  energy?: BandEnergy | null
  ph?: ChannelPhase | null
  onOpen: () => void
}) {
  // [R217] 事件那一行**不在这里出了**。用户: 「每一列的内容应该就是一部分,
  // 而不是内容上面一部分下面一部分」—— 原来这一列会摞到五层(结论徽标 / 事件行 /
  // 怎么办徽标 / 两行折行的理由 / 另有 N 处), 每行高度还不一样, 于是上一行的
  // 尾巴挂到下一行的表头底下, 行与行糊成一片。
  // 现在整列固定两行, 事件并进第二行那句话里, 见 ConclusionCell。
  if (!v) {
    // [R203] 底层在三格上返回「无结论」, 其中**两格是有信息的**:
    // 「中中上」= 长期到了上沿而中短期都休整完了, 「中中下」= 长期到了下沿
    // 而中短期已经企稳。它们正是「大级别位置到了、等一个入场点」的另一半。
    //
    // 底层是禁止改的, 所以这里不去改判定 —— 改的是**显示**: 补充层已经给这
    // 两格写了注记, 那就把注记的标题当徽标摆出来, 而不是一个 "—"。
    // 只有「中中中」是真的零信息(价格在三条通道都认可的区间里), 它照旧显示 "—"。
    const note = ev?.combo_note
    return (
        <button
          onClick={onOpen}
          className={note
            ? 'inline-flex cursor-pointer whitespace-nowrap rounded border border-border bg-elevated/60 px-1 py-0.5 text-[10px] text-secondary transition-colors hover:brightness-125'
            : 'cursor-pointer text-[10px] text-muted/40 hover:text-sky-300'}
          title={(note
            ? `${note.title}:${note.detail}\n\n底层判定在这一格是空的 —— 这句话来自补充层。`
            : '三档都在通道中部 —— 位置上真的没有可说的, 听趋势和信号的')
            + '。点击翻这只票过去出过哪些结论'
            + geoLines(geo, ev, runs, energy, ph)}
        >
          {note ? note.title : '—'}
        </button>
    )
  }
  return (
      <VerdictHover v={v} note={"点击摊开这只票过去每一档结论 —— 出现在哪几天、当时说了什么、之后走成什么样。"
        + geoLines(geo, ev, runs, energy, ph)}>
        <button
          onClick={onOpen}
          className={`inline-flex cursor-pointer whitespace-nowrap rounded border px-1 py-0.5 text-[10px] transition-colors hover:brightness-125 ${VERDICT_CLS[v.tone]}`}
        >
          {v.title}
          {/* [R233] 用户: 「『候选、调到位了』也是要显示这个状态持续多少天了」。
              六态徽标一直带着天数, 而它旁边的结论只有 4 个字 —— 于是「调到位了」
              看不出是今天刚到位, 还是已经这样磨了三周。这两种要做的事完全不同。 */}
          {/* [R236/R237] 状态时长。列很窄, 起始日等细节放悬停(见 VerdictHover)。
              不精确时画淡并加 `?`: 「至少 1 天」和「数出来就是第 1 天」
              不是一回事, 不能长得一样。

              [R238] **那个「已」字不是修饰, 是这句话的全部意思。**
              用户: 「我不是要历史总数哦」—— 光写「候选池 75天」可以读成
              "历史上累计 75 天处于候选池", 而这里说的是"已经连着 75 天"。
              一字之差是两个完全不同的数, 徽标上必须自己说清楚, 不能指望
              用户去悬停里确认。 */}
          {v.days != null && (
            <span className={v.days_exact === false ? 'ml-0.5 opacity-40' : 'ml-0.5 opacity-70'}
                  title={v.days_exact === false
                    ? '这只票的历史不够长,只能确认到今天 —— 实际可能已经连着很多天'
                    : `自 ${v.since ?? '—'} 起,已连着 ${v.days} 个交易日`}>
              已{v.capped ? '超过' : ''}{v.days}天{v.days_exact === false ? '?' : ''}
            </span>
          )}
        </button>
      </VerdictHover>
  )
}

// ===== [R46] 自包含 HTML 导出 =====
// 只导出「结论」列有内容的行 —— 三档都在通道中部的票没有位置信息,
// 导出来只是占地方。导出件里第一行就写清导出了几只、总共几只, 免得
// 看到 148 只自选导出 4 行时以为漏了。
//
// 与今日总览的导出同一套排版: 浅色、内联样式、无脚本无外链, 存档/打印/
// 转发都不依赖这个应用。



// [R209] 「该动了」的单元格(UrgencyLine)与它那两张配色表在这里删掉了。
//
// 用户: 「已经有怎么办的列了, 标的里面的那些就不多余了」。**同一句话印了两遍** ——
// 「怎么办」列本来就是把「该动了」当成五套判定之一合成进去的, 于是同一只票的
// 「生命线跌破 399.85 已跌破 3.6%」左右各印一份。
//
// R193 那条纪律没有丢, 只是搬了家: **方向要直接写出来**(「逼近·买」而不是光一个
// 「逼近」)现在由 PlaybookCell 的标题承担 —— 同样是「逼近」, 可能是再跌一点破止损,
// 也可能是再涨一点转强, 两个相反的动作不标方向就长得一模一样。
//
// 判定本身(services/watchlist_urgency.py)一个字没动, 排序键与「只看要动的」筛选
// 照旧走它。删掉的只是这一处重复的显示 —— 按 R198 立的规矩: 不留没人调的死代码。

// [R201] 阶段配色 —— 与复盘弹窗那张 PHASE_CLS 同一套语义, 只是这里要更淡:
// 决策台一屏 80 行, 整列都是实色会盖过「该动了」那一列的红。
const PHASE_TEXT: Record<string, string> = {
  coiling: 'text-secondary',
  launching: 'text-red-300',
  advancing: 'text-red-400',
  stalling: 'text-amber-300',
  overextended: 'text-amber-400',
  declining: 'text-emerald-400',
  unclear: 'text-muted',
}

/**
 * 「走势」列 —— 一只票的方向, 两套判定叠在一格里。
 *
 * ## [R211] 这一列吞并了另外两列, 每一次都有理由
 *
 *   · 「量化通道」(三档原始位置) —— 它是**测量**, 而这一列是从它推出来的
 *     **结论**。拆成两列等于让人左右对眼去把结论和它的依据接起来。
 *     三档位置退到悬停: 「贵不贵」那一列已经把它翻成一句结论了。
 *   · 「趋势」(六态) —— 用户: 「趋势和通道态势整合一起」。两者答的是同一个
 *     问题(这只票往哪走), 只是**方法不同**: 六态看关键点, 通道看三条线的
 *     相对位置。放在一格里, 它们什么时候一致、什么时候打架, 上下一对就看见了。
 *     (真打架时「怎么办」那一列会直接判成「先别动」, 这里只是让人能核对。)
 *
 * 三行, 从上到下是「谁说的」→「走到哪」→「还有没有劲」:
 *
 *     上涨趋势 15天        ← 六态(作者的判定, 点开是逐日复盘)
 *     上升中 · 走到中段     ← 通道给的阶段 + 走到哪一步
 *     速度平稳             ← 还有没有劲
 *
 * **一个数字都没有。** 数字全在悬停里 —— 扫表时用不上, 要核对时又必须有。
 *
 * ## [R228] 整格**一个**点击目标, 不再是两个
 *
 * 用户: 「这两个弹窗也整合到一起, 外部入口就变成一个按钮了, 这样打开好看」。
 *
 * 原来这一格里有两个挨着的按钮: 六态徽标进逐日复盘、右边的阶段进 27 种组合
 * 速查。**它们通向两个不同的全屏模态, 而格子里没有任何东西说得出这件事** ——
 * 两段文字长得一样、挨在一起, 谁也猜不到点左半边和点右半边打开的不是同一个东西。
 *
 * 现在两个弹窗并成了一个(见 `StockReviewDialog` 的三个页签), 这一格也就
 * 只剩一个按钮: 整格可点, 落在「趋势状态」页签, 通道那两个页签在弹窗顶上换。
 * 悬停也跟着并成一份 —— 原来是两半各自一份提示, 鼠标从左挪到右提示整个换掉。
 */
export function ChannelStateCell({ trend, geo, runs, ph, kc, close, trendCls,
                                  onOpenReview }: {
  /** [R211] 六态趋势 —— 合过来的那一列。作者的判定, 只读不改 */
  trend?: { state: string; state_cn: string; duration: number; since?: string
            action?: string; intraday?: boolean } | null
  geo?: ChannelGeometry | null
  runs?: ChannelRuns | null
  ph?: ChannelPhase | null
  kc?: { s?: KeltnerBand; m?: KeltnerBand; l?: KeltnerBand } | null
  close?: number | null
  /** 六态徽标的配色(由 TrendStateBar 那套给, 两处必须同色) */
  trendCls?: string
  /** [R228] 整格点开 → 复盘弹窗(趋势 / 通道结论 / 组合速查 三个页签) */
  onOpenReview?: () => void
  /** 追加类名(结论区分界线之类) */
  cls?: string
}) {
  // 三档位置只在悬停里给 —— 「贵不贵」列已经把它翻成一句结论了
  const at = ([['短期', kc?.s], ['中期', kc?.m], ['长期', kc?.l]] as const)
    .filter(([, b]) => b && b.pos !== 'inside')
  const gap = !geo ? '' : geo.spread >= 0
    ? `短线高出长线 ${geo.spread.toFixed(1)} 倍日常波动`
    : `短线低于长线 ${Math.abs(geo.spread).toFixed(1)} 倍日常波动`
  // [R228] 一份悬停, 按「六态怎么说 → 通道怎么说 → 依据」排。
  // 原来是两半各一份: 鼠标从徽标挪到阶段, 提示整个换掉一份, 而这一格
  // 讲的本来就是同一只票的方向。末尾那句从「点这两行…」改成整格的去处。
  const tip = [
    trend ? `【六态】${trend.state_cn} · 第 ${trend.duration} 天`
      + (trend.since ? `,自 ${trend.since}` : '') : '',
    trend?.action ?? '',
    ...(ph ? ['', `【通道】${ph.cn} —— ${ph.why}`, `该盯什么:${ph.watch}`] : []),
    // 第三行那句(三个尺度对齐到第几步)原来自带一份悬停, 一并收进来
    ph?.align ? `【${ph.align.cn}】${ph.align.why}` : (ph ? `快慢:${ph.pace_cn}` : ''),
    '', gap,
    at.length ? '现在到边的:' + at.map(([t, b]) => `${t}${b!.pos_cn}`).join('、') : '三档都在通道中部',
    runs?.compress_days ? `三条线已经这样挤在一起 ${runs.compress_days} 天` : '',
    '',
    ...([['短期', kc?.s], ['中期', kc?.m], ['长期', kc?.l]] as const)
      .filter(([, b]) => b)
      .map(([t, b]) => `${t}通道 ${b!.lower.toFixed(2)} ~ ${b!.upper.toFixed(2)}`
        + `,现在${b!.pos_cn}(位置 ${Math.round(b!.pct * 100)}%)`),
    close != null ? `收盘 ${close.toFixed(2)}` : '',
    '', '点开:逐日复盘 / 通道结论 / 27 种组合速查'].filter(Boolean).join('\n')
  return (
    // [R217] 与「结论」列同一个形状: **固定两行**, 高度对齐, 行与行不再糊在一起。
    //   行 1: 六态徽标 + 阶段·成熟度(原来阶段自己占一行)
    //   行 2: 快慢一行
    // 用户: 「每一列的内容应该就是一部分, 而不是内容上面一部分下面一部分」。
    <td className={`${TD_BASE} whitespace-nowrap px-1.5`}>
      {/* [R228] **整格一个 button**。原来格子里有两个 button, 通向两个不同的
          全屏模态, 而外观上分不出来。合并之后按钮边界与格子边界重合, 悬停整格
          一起亮 —— "这一格可以点开"这件事本身第一次是看得见的。
          内部的徽标一律降成 span: button 里套 button 是非法 HTML。 */}
      <button type="button" onClick={onOpenReview} title={tip}
              className="mx-auto flex w-full cursor-pointer flex-col items-center gap-0.5 rounded-btn px-1 py-0.5 leading-tight transition-colors duration-hover hover:bg-elevated/40">
        <span className="flex flex-wrap items-center justify-center gap-1">
          {trend ? (
            <span className={`inline-flex whitespace-nowrap rounded border px-1.5 py-0.5 text-[10px] ${trendCls ?? ''}`}>
              {trend.state_cn} {trend.duration}天{trend.intraday ? <span className="ml-0.5 opacity-70">*</span> : null}
            </span>
          ) : <span className="text-[10px] text-muted/30">—</span>}
          {!!ph && (
            <span className={`whitespace-nowrap text-[10px] ${PHASE_TEXT[ph.code] ?? 'text-muted'}`}>
              {ph.cn} · {ph.maturity_cn}
            </span>
          )}
        </span>
        {/* [R224] 第二行给「三个尺度走到第几步」, 而不是一个警告。
            R223 那版是成对冲突检查, 实测超过一半的行挂警告 —— 那是噪声。
            三者是滞后阶梯(价格最快→六态→均线最慢), 不一致 = 转折还没走完。 */}
        {ph?.align ? (
          <span className={`text-[9px] ${
            ph.align.level === 3 ? 'text-red-400/80'
              : ph.align.level === 0 ? 'text-emerald-400/80'
              : ph.align.level === null ? 'text-muted' : 'text-amber-300/85'}`}>
            {ph.align.cn}
          </span>
        ) : (
          <span className="text-[9px] text-muted">
            {ph ? ph.pace_cn : <span className="text-transparent select-none">·</span>}
          </span>
        )}
      </button>
    </td>
  )
}

// [R205] 「怎么办」配色。**只有两档是红的** —— 纪律已破和今天已触发。
// 分歧档刻意用琥珀而不是红: 它说的是"别动", 不是"快动", 用红会被读反。
const PLAY_CLS: Record<string, string> = {
  danger: 'border-red-400/45 bg-red-400/10 text-red-400',
  warn: 'border-amber-400/40 bg-amber-400/10 text-amber-300',
  info: 'border-sky-400/30 bg-sky-400/[0.07] text-sky-300',
  muted: 'border-border/50 text-muted/50',
}

/**
 * [R205] 「怎么办」列 —— **整张表唯一的收敛层**, 所以放在最左边。
 *
 * 决策台上有五套彼此平行的判定(该动了 / 六态 / 通道结论 / 通道阶段 / AI 信号),
 * 每一套单独看都对, 摆在一起就是让用户每天在脑子里做一次五路合成。这一列
 * 替他做完那次合成: 一句话说该怎么办, 一行小字说凭什么。
 *
 * **最值钱的是「先别动」那一档。** 系统原来从不说这五套什么时候互相矛盾 ——
 * 而那恰恰是最该停手的时刻, 却是最容易被忽略的时刻(界面把它们并排摆着,
 * 谁都不提一句)。分歧档刻意排在「逼近」之前: 「还差 1.2% 到买点」这种话
 * 会诱人下手, 判定打架时不该让它出现在标题上。
 *
 * 这一列**不产生任何新判定** —— 每句话都能追到某一层的原话。
 */
function PlaybookInner({ p }: { p?: Playbook | null }) {
  if (!p) return <span className="text-[10px] text-muted/30">—</span>
  return (
      <span className={`inline-flex whitespace-nowrap rounded border px-1.5 py-0.5 text-[10px] ${PLAY_CLS[p.tone] ?? PLAY_CLS.muted}`}
            title={p.why}>
        {p.headline}
        {p.price != null && <span className="ml-1 font-mono tabular-nums opacity-80">{p.price.toFixed(2)}</span>}
      </span>
  )
}

/**
 * [R212] 「结论」列 —— 贵不贵在上、怎么办在下, 合成一格。
 *
 * 用户: 「怎么办和贵不贵合成为一列叫做结论, 贵不贵在上换行怎么办在下」。
 *
 * 我先前主张分成两列并排, 理由是"它们打架时最该被看见"。**竖排同样看得见** ——
 * 上下两行落在同一格里, 一眼就能对上; 而且省一列。所以按用户说的合。
 *
 * 顺序是有讲究的: 上面「贵不贵」是**位置**(这个价现在算贵还是便宜),
 * 下面「怎么办」是**动作**(所以今天该干嘛) —— 从事实到结论, 自上而下读。
 */
export function ConclusionCell({ v, ev, geo, runs, energy, ph, p, onOpen }: {
  v?: KeltnerVerdict | null
  ev?: ChannelEvent | null
  geo?: ChannelGeometry | null
  runs?: ChannelRuns | null
  energy?: BandEnergy | null
  ph?: ChannelPhase | null
  p?: Playbook | null
  onOpen: () => void
}) {
  // [R217] **整列固定两行**, 见下面的说明。
  //   行 1: 贵不贵 · 怎么办 两个徽标横排
  //   行 2: 一行说明(截断), 事件与"另有 N 处分歧"都并进这一行
  const evOn = ev && ev.code !== 'none'
  const more = p && p.conflicts.length && p.level !== 'conflict'
  const line2 = [
    evOn ? `${ev!.cn}${ev!.confirmed ? '' : '?'}` : '',
    p?.why || '',
    more ? `(另有 ${p!.conflicts.length} 处判定不一致)` : '',
  ].filter(Boolean).join(' · ')
  const tip = [
    evOn ? `${ev!.cn}${ev!.confirmed ? '' : '(未确认)'} —— ${ev!.why}` : '',
    p?.why || '',
    more ? '另有判定不一致:\n' + p!.conflicts.join('\n') : '',
  ].filter(Boolean).join('\n\n')
  return (
    <td className={`${TD_BASE} px-2`}>
      <div className="mx-auto flex max-w-[15rem] flex-col items-center gap-0.5 leading-tight">
        <span className="flex flex-wrap items-center justify-center gap-1">
          <VerdictInner v={v} ev={ev} geo={geo} runs={runs} energy={energy} ph={ph} onOpen={onOpen} />
          <PlaybookInner p={p} />
        </span>
        {line2 ? (
          <span className={`w-full truncate text-[9px] ${evOn ? EVENT_CLS[ev!.code] ?? 'text-muted' : 'text-muted'}`}
                title={tip}>
            {line2}
          </span>
        ) : <span className="text-[9px] text-transparent select-none">·</span>}
      </div>
    </td>
  )
}
