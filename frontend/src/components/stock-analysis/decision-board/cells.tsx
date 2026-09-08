/**
 * [fork 增强] 决策台的两个只读单元格: Keltner 三档位置 / 三档组合结论。
 *
 * [R167] 从 WatchlistDecisionBoard.tsx 拆出。各自带着自己的配色表 —— 配色表是
 * 实现细节, 不该摆在 933 行主文件的顶部让人以为是全局约定。
 */
import type { BandEnergy, ChannelEvent, ChannelGeometry, ChannelPhase, ChannelRuns, KeltnerBand, KeltnerVerdict, Urgency } from '@/lib/api'
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
  else if (geo.compress != null) L.push(`三条线还有 ${(geo.compress * 100).toFixed(0)}% 重合,首尾相差 ${geo.spread.toFixed(1)} 倍日常波动`)
  L.push(`眼下价格离各自中线:短期 ${geo.d.s.toFixed(1)} / 中期 ${geo.d.m.toFixed(1)} / 长期 ${geo.d.l.toFixed(1)} 倍日常波动(正的偏贵、负的偏便宜)`)
  if (runs?.compress_days) L.push(`已经这样挤了 ${runs.compress_days} 天`)
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
    return (
      <td className={`${TD_BASE} whitespace-nowrap px-1.5`}>
        <button
          onClick={onOpen}
          className="cursor-pointer text-[10px] text-muted/40 hover:text-sky-300"
          title={"短期通道在中部 —— 位置上没有可说的, 听趋势和信号的。点击翻这只票过去出过哪些结论"
            + geoLines(geo, ev, runs, energy, ph)}
        >
          —
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



// [R178] 「该动了」配色。急的用暖色、无事的彻底压暗 —— 这一列的作用是让眼睛
// 在 80 行里一秒找到该看的那几行, 所以对比要拉开, 不能像别的列那样克制。
const URGENCY_CLS: Record<Urgency['level'], string> = {
  triggered: 'border-red-400/50 bg-red-400/15 text-red-400 font-medium',
  near: 'border-amber-400/40 bg-amber-400/10 text-amber-400',
  flip: 'border-violet-400/40 bg-violet-400/10 text-violet-300',
  band: 'border-sky-400/30 bg-sky-400/5 text-sky-300/90',
  idle: 'border-transparent text-muted/30',
}

// [R193] 方向标。**档位管急不急, 方向管买还是卖 —— 两个正交的维度**,
// 原来只显示了前者。同样一个琥珀色的「逼近」, 可能是"再跌一点就破止损"
// 也可能是"再涨一点就转强", 不标方向的话扫表时长得一模一样。
const SIDE_CLS: Record<string, string> = {
  sell: 'border-rose-400/50 bg-rose-400/15 text-rose-300',
  buy: 'border-sky-400/50 bg-sky-400/15 text-sky-300',
  info: 'border-border/50 text-muted/70',
}

/**
 * 「该动了」单元格。
 *
 * [R193] 用户: 「这一列要把话说清楚, 太简洁了, 这也不行, 会误人子弟」。
 *
 * 原来只画一个「逼近 0.5%」的胶囊, 其余全在悬停的 title 里。**一列 80 行是
 * 用来扫的, 扫的时候没人会悬停** —— 所以那句解释等于不存在, 而缺了它,
 * 「该卖」和「该买」在这一列里完全同形。这是这一列唯一一处真会害人的地方。
 *
 * 现在单元格自己说三件事:
 *   ① 档位 + 距离   —— 有多急(已触发那一档给的是"已经破了多少", 不再是假的 0.0%)
 *   ② 方向          —— 买还是卖, 单独一个色块, 不靠语义色去暗示
 *   ③ 哪条线 / 该干嘛 —— 带上具体价位, 能直接照着挂单
 *
 * 判定还没回来时显示 "—" 而不是"无事" —— 那是两件事, 混在一起会让人以为
 * 今天真没事。每一档背后都是一条写死的规则(见 services/watchlist_urgency.py),
 * 这里显示的是后端给的原话, 前端不自己编。
 */
/**
 * [R198] 「该动了」由**独立一列**改成挂在标的名字下面的一行。
 *
 * 判定一个字没改(见 services/watchlist_urgency.py), 换的只是位置: 自选一多,
 * 左右对眼比上下读一行累得多 —— 「这只票该动」和「这只票叫什么」本来就该
 * 挨在一起。R193 那条纪律照旧: **方向要直接写出来**, 不能只给一个档位 ——
 * 同样是「逼近」, 可能是"再跌一点破止损"也可能是"再涨一点转强", 两个相反的
 * 动作不标方向就长得一模一样。
 */
export function UrgencyLine({ u }: { u?: Urgency }) {
  if (!u || u.level === 'idle') return null
  const side = u.side ?? 'info'
  return (
    <div className="mt-0.5 flex flex-col items-center gap-0.5" title={u.reason}>
      <span className="flex items-center gap-1">
        <span className={`inline-flex items-center gap-1 whitespace-nowrap rounded border px-1.5 py-0.5 text-[10px] ${URGENCY_CLS[u.level]}`}>
          {u.label}
          {u.distance != null && (
            <span className={`${NUM} opacity-70`}>{(u.distance * 100).toFixed(1)}%</span>
          )}
        </span>
        {!!u.side_cn && (
          <span className={`inline-flex shrink-0 rounded border px-1 py-0.5 text-[10px] font-medium ${SIDE_CLS[side]}`}>
            {u.side_cn}
          </span>
        )}
      </span>
      {!!u.what && <span className="text-[9px] leading-tight text-secondary/90">{u.what}</span>}
      {!!u.action && <span className="text-[9px] leading-tight text-muted/80">{u.action}</span>}
    </div>
  )
}
