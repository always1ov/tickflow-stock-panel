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

// [R42] Keltner 位置配色。破上轨/贴上轨用暖色(偏贵), 破下轨/贴下轨用冷色(偏便宜),
// 通道内保持中性 —— 位置是事实, 不替用户下买卖判断。
const KELTNER_CLS: Record<KeltnerBand['pos'], string> = {
  above: 'border-red-400/40 bg-red-400/10 text-red-400',
  near_upper: 'border-amber-400/40 bg-amber-400/10 text-amber-400',
  inside: 'border-border bg-base text-muted',
  near_lower: 'border-sky-400/40 bg-sky-400/10 text-sky-300',
  below: 'border-emerald-400/40 bg-emerald-400/10 text-emerald-400',
}

/**
 * 一档 Keltner 通道的单元格。
 *
 * 显示"贴上轨"这种五档文字, 悬停给出真实的上下轨价、通道内位置百分比,
 * 以及"还差几个 ATR 到轨" —— 只给一个标签等于让用户盲信一个没法复核的判断。
 * 该档算不出来(新股不够 120 根 / 均线列缺失)时显示 "—", 不编一个数出来。
 */
/**
 * [R198] 三档竖排成一格。短/中/长本来就是**同一个指标在三个尺度上的读数**
 * (共用同一个 ATR 分母), 拆成三列是把一件事摊成三份看; 合成一格之后每行三条,
 * 上下一对比就知道三个尺度是不是同向 —— 那正是这套指标最该被读出来的东西。
 *
 * 原来的 `KeltnerCell`(单档一列)随之删掉, 没有留下没人调的死代码。
 * 悬停照旧给真实的上下轨价、通道内位置、还差几个 ATR 到轨 —— 只给一个标签
 * 等于让用户盲信一个没法复核的判断。该档算不出来时显示 "—", 不编一个数出来。
 */
export function ChannelStackCell({ kc, close }: {
  kc?: { s?: KeltnerBand; m?: KeltnerBand; l?: KeltnerBand } | null
  close?: number | null
}) {
  const rows: [string, KeltnerBand | undefined][] = [
    ['短期', kc?.s], ['中期', kc?.m], ['长期', kc?.l],
  ]
  return (
    <td className={`${TD_BASE} whitespace-nowrap px-1.5`}>
      <div className="inline-flex flex-col items-center gap-0.5">
        {rows.map(([tag, band]) => (
          <span key={tag} className="flex items-center gap-1">
            <span className="w-6 text-right text-[9px] text-muted/60">{tag}</span>
            {band
              ? (
                <span
                  className={`inline-flex whitespace-nowrap rounded border px-1 py-0.5 text-[10px] ${KELTNER_CLS[band.pos]}`}
                  title={
                    `${band.band_cn}通道 ${band.lower.toFixed(2)} ~ ${band.upper.toFixed(2)}`
                    + `${close != null ? `,收盘 ${close.toFixed(2)}` : ''}\n`
                    + `在这条通道里的位置 ${Math.round(band.pct * 100)}%(0% 贴下沿 / 100% 贴上沿)\n`
                    + `离上沿还有 ${band.to_upper_atr ?? '—'} 倍日常波动 · 离下沿还有 ${band.to_lower_atr ?? '—'} 倍日常波动\n`
                    + `${band.hint}\n一律按收盘算 —— 盘中拿实时价去比昨天的通道, 会半新半旧`
                  }
                >
                  {band.pos_cn}
                </span>
              )
              : <span className="text-[10px] text-muted/30">—</span>}
          </span>
        ))}
      </div>
    </td>
  )
}

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
  L.push('', '—— 量化波动通道 ——')
  const a = geo.accel
  if (a?.level_cn) {
    L.push(`最近这十天比前一段${a.gain_atr >= 0 ? '多' : '少'}走了 ${Math.abs(a.gain_atr).toFixed(1)} 倍日常波动(${a.level_cn})`)
  }
  if (geo.torn) L.push(`短线和长线离得太远(差 ${Math.abs(geo.spread).toFixed(1)} 倍日常波动),已经没有共同认可的合理价`)
  else if (geo.nested) L.push(`三条线几乎挤在一块(只差 ${Math.abs(geo.spread).toFixed(1)} 倍日常波动)`)
  else if (geo.compress != null) {
    L.push(`三条线还有 ${(geo.compress * 100).toFixed(0)}% 重合,`
      + (geo.spread >= 0
        ? `短线高出长线 ${geo.spread.toFixed(1)} 倍日常波动`
        : `短线低于长线 ${Math.abs(geo.spread).toFixed(1)} 倍日常波动`))
  }
  L.push(`眼下价格离各自中线:短期 ${geo.d.s.toFixed(1)} / 中期 ${geo.d.m.toFixed(1)} / 长期 ${geo.d.l.toFixed(1)} 倍日常波动(正的偏贵、负的偏便宜)`)
  if (runs?.compress_days) L.push(`三条线已经这样挤在一起 ${runs.compress_days} 天`)
  if (runs?.compress_avg != null) L.push(`整个季度平均重合 ${(runs.compress_avg * 100).toFixed(0)}%`)
  if (energy) {
    const sh = energy.share
    L.push(`波动主要来自:${energy.dominant_cn}`)
    L.push(`几天的短波动 ${(sh.s * 100).toFixed(0)}% / 一波行情的主体 ${(sh.m * 100).toFixed(0)}% / 长期老趋势 ${(sh.l * 100).toFixed(0)}%`)
    L.push('(三份各 33% 是「就是一路匀速走」的样子,偏离 33% 的那部分才是信息)')
  }
  if (runs?.above_run) L.push(`连着 ${runs.above_run} 天站在短线上沿之外`)
  if (runs?.below_run) L.push(`连着 ${runs.below_run} 天掉在短线下沿之外`)
  if (ev?.why) L.push('', `事件:${ev.cn} —— ${ev.why}`)
  if (ev?.combo_note) {
    L.push('', `组合「${ev.combo_note.combo}」补充 · ${ev.combo_note.title}`, ev.combo_note.detail)
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
export function VerdictCell({ v, ev, geo, runs, energy, ph, onOpen }: {
  v?: KeltnerVerdict | null
  ev?: ChannelEvent | null
  geo?: ChannelGeometry | null
  runs?: ChannelRuns | null
  energy?: BandEnergy | null
  ph?: ChannelPhase | null
  onOpen: () => void
}) {
  const evLine = ev && ev.code !== 'none' ? (
    <span className={`block truncate text-[9px] leading-tight ${EVENT_CLS[ev.code] ?? 'text-muted'}`}
          title={`${ev.cn} —— ${ev.why}`}>
      {ev.cn}{ev.confirmed ? '' : '?'}
    </span>
  ) : null
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
      <td className={`${TD_BASE} whitespace-nowrap px-1.5`}>
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
        {evLine}
      </td>
    )
  }
  return (
    <td className={`${TD_BASE} whitespace-nowrap px-1.5`}>
      <VerdictHover v={v} note={"点击摊开这只票过去每一档结论 —— 出现在哪几天、当时说了什么、之后走成什么样。"
        + geoLines(geo, ev, runs, energy, ph)}>
        <button
          onClick={onOpen}
          className={`inline-flex cursor-pointer whitespace-nowrap rounded border px-1 py-0.5 text-[10px] transition-colors hover:brightness-125 ${VERDICT_CLS[v.tone]}`}
        >
          {v.title}
        </button>
      </VerdictHover>
      {evLine}
    </td>
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
 * 「通道态势」列 —— 现在处在哪一段、走到哪一步、还有没有劲。
 *
 * ## [R209] 这一列重做过一次, 原因值得记下来
 *
 * 上一版摆的是三行:「下跌中 / 短线低 1.7 倍波动 / 速度没变」。用户:
 * 「通道态势这一列得重新做, 看不懂这样的表述」。**问题不在措辞, 在种类** ——
 * 后两行是**测量值**, 而这一列的位置(挨着「贵不贵」和「怎么办」)决定了它
 * 该出结论。「1.7 倍日常波动」这个单位再准确, 扫表的人也换算不出它意味着什么。
 *
 * 现在两行, 都是判断, **一个数字都没有**:
 *
 *     下跌中              ← 处在哪一段(七档之一, 带方向)
 *     走到中段 · 速度平稳   ← 走到哪一步了 + 还有没有劲
 *
 * 「走到哪一步」的门槛直接用打分那一层已经在用的那三个(SPREAD_LAUNCH /
 * SPREAD_MATURE / TORN_ATR), 不另编一套 —— 界面上说「走了很长」的那一刻,
 * 打分那边也正好在扣分, 两边永远对得上。
 *
 * 数字全部退到悬停: 扫表时用不上, 要核对时又必须有。点开是 27 种组合速查。
 *
 * ## 为什么是这几个量, 不是全部
 *
 * 几何层一共算出十来个。逐个问"它能不能改变我今天的动作":
 *   · **阶段**     能 —— 唯一直接回答「现在该盯什么」的, 一个词顶三个数。
 *   · **三线间距** 能 —— 但它的价值在**排序**(升序扫是「刚立住的」, 降序扫是
 *                  「走得最远该收的」), 所以留作排序键, 显示上收成「走到哪一步」。
 *   · **快慢**     能 —— 与间距正交: 间距说走了多远, 快慢说还有没有劲。
 *   · **挤了几天** 只在「横着憋」那一档有意义 —— 退到悬停。
 *
 * 明确不进这一列的: 压缩指数(与间距单调对应, 同一件事投两次票)、频段能量
 * (回答「这波是谁在推」, 属于研究不属于今天的动作)、离各自中线(与旁边
 * 「量化通道」列讲的是同一件事)、三档位置码(已由「贵不贵」列翻成人话)。
 */
export function ChannelStateCell({ geo, runs, ph, onOpenCombo }: {
  geo?: ChannelGeometry | null
  runs?: ChannelRuns | null
  ph?: ChannelPhase | null
  /** 点开 27 种组合速查(带这只票的读数与高亮) */
  onOpenCombo?: () => void
}) {
  if (!geo || !ph) {
    return <td className={`${TD_BASE} px-1.5`}><span className="text-[10px] text-muted/30">—</span></td>
  }
  // 悬停里才给数字 —— 扫表时用不上, 要核对时又必须有
  const gap = geo.spread >= 0
    ? `短线高出长线 ${geo.spread.toFixed(1)} 倍日常波动`
    : `短线低于长线 ${Math.abs(geo.spread).toFixed(1)} 倍日常波动`
  const tip = [`${ph.cn} —— ${ph.why}`, `该盯什么:${ph.watch}`, '', gap,
    runs?.compress_days ? `三条线已经这样挤在一起 ${runs.compress_days} 天` : '',
    '', '点开看 27 种组合系统各怎么说'].filter(Boolean).join('\n')
  return (
    <td className={`${TD_BASE} whitespace-nowrap px-1.5`}>
      <button type="button" onClick={onOpenCombo} title={tip}
              className="inline-flex cursor-pointer flex-col items-center gap-0.5 leading-tight transition-colors duration-hover hover:brightness-125">
        <span className={`text-[11px] font-medium ${PHASE_TEXT[ph.code] ?? 'text-muted'}`}>
          {ph.cn}
        </span>
        <span className="text-[9px] text-muted">
          {ph.maturity_cn} · {ph.pace_cn}
        </span>
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
export function PlaybookCell({ p }: { p?: Playbook | null }) {
  if (!p) {
    return <td className={`${TD_BASE} px-2`}><span className="text-[10px] text-muted/30">—</span></td>
  }
  const more = p.conflicts.length && p.level !== 'conflict'
  return (
    <td className={`${TD_BASE} px-2`}>
      <div className="inline-flex max-w-[13rem] flex-col items-center gap-0.5 leading-tight">
        <span className={`inline-flex whitespace-nowrap rounded border px-1.5 py-0.5 text-[10px] ${PLAY_CLS[p.tone] ?? PLAY_CLS.muted}`}
              title={p.why}>
          {p.headline}
          {p.price != null && <span className="ml-1 font-mono tabular-nums opacity-80">{p.price.toFixed(2)}</span>}
        </span>
        <span className="line-clamp-2 text-[9px] text-muted" title={p.why}>{p.why}</span>
        {/* 不在分歧档时, 分歧仍然作为一行小字带出来 —— 它任何时候都值得知道 */}
        {!!more && (
          <span className="text-[9px] text-amber-300/80"
                title={p.conflicts.join('\n')}>
            另有 {p.conflicts.length} 处判定不一致
          </span>
        )}
      </div>
    </td>
  )
}
