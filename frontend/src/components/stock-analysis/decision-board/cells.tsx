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
// [R283] `py-2` → `py-2.5`, 并把多行格子的 `leading-snug` 换成 `leading-snug`。
// 用户: 「页面整体看起来有点压抑」。**压抑有一半来自行高不是字号** —— 字号整档
// 调大之后行距不跟着松, 反而比原来更挤。
export const TD_BASE = 'align-middle py-2.5 text-center'

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
/**
 * [R298] 「现在处在哪一段 · 该盯什么」——**全系统这一处产地。**
 *
 * 用户问「结论列和走势列有必要合并吗」, 查下来两列不该合(两套判定, 打架时要
 * 上下对得出来), **但它们的悬停里确实各印了一份这两句话**: 走势列写
 * `【通道】上升中 —— why`, 结论列写 `【上升中】why` —— 同两句、两个格式、
 * 两个产地。这是本仓库反复清的那一类(R296 `LiveStrip` vs `EvidencePanel`、
 * R249 天数印两遍), 这次借这个问题一并收成一处。
 *
 * 阶段是**通道层**的读数(`phase(geo, runs)`), 所以格式跟着「结论」列那一份走。
 */
function phaseLines(ph?: ChannelPhase | null): string[] {
  if (!ph) return []
  return ['', `【${ph.cn}】${ph.why}`, `该盯什么:${ph.watch}`]
}


function geoLines(geo?: ChannelGeometry | null, ev?: ChannelEvent | null,
                  runs?: ChannelRuns | null, energy?: BandEnergy | null,
                  ph?: ChannelPhase | null): string {
  if (!geo) return ''
  const L: string[] = []
  // [R200] 阶段摆在最前面。悬停这一片本来全是测量 —— 先给一句"现在处在哪一段、
  // 该盯什么", 后面那些数才有落点。这句话之前只有复盘弹窗里有。
  L.push(...phaseLines(ph))

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
/**
 * [R246] 天数徽标: `已N天`, 是下界时加 `+`。
 *
 * 「已」字不是修饰, 是这句话的全部意思 —— 光写「候选池 25天」可以读成"历史上
 * 累计 25 天处于候选池", 而这里说的是"已经**连着** 25 天"。一字之差是两个数。
 *
 * `+` = 数到头了(序列到尽头, 或再往前那天算不出来), 真实天数只多不少。
 */
function Days({ d }: { d?: { days?: number; since?: string; capped?: boolean } | null }) {
  if (!d?.days) return null
  return (
    <span className="ml-0.5 opacity-70"
          title={d.since ? `自 ${d.since} 起, 连着 ${d.days} 个交易日${d.capped ? '以上' : ''}。中间断一天就从头重新起算` : undefined}>
      已{d.days}天{d.capped ? '+' : ''}
    </span>
  )
}


function VerdictInner({ v, ev, geo, runs, energy, ph, stateRun, onOpen }: {
  v?: KeltnerVerdict | null
  /** [R246] 没结论那一格的时长 */
  stateRun?: { days: number; since?: string; capped?: boolean } | null
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
            ? 'inline-flex cursor-pointer whitespace-nowrap rounded border border-border bg-elevated/60 px-1 py-0.5 text-[12px] text-secondary transition-colors hover:brightness-125'
            : 'cursor-pointer text-[12px] text-muted/40 hover:text-sky-300'}
          title={(note
            ? `${note.title}:${note.detail}\n\n底层判定在这一格是空的 —— 这句话来自补充层。`
            : '三档都在通道中部 —— 位置上真的没有可说的, 听趋势和信号的')
            + '。点击翻这只票过去出过哪些结论'
            + geoLines(geo, ev, runs, energy, ph)}
        >
          {/* [R256] 「中中中」那一格原来印一个光秃秃的 `—`, 旁边却跟着「已N天」——
              读起来是「什么都没有, 已经 1 天」。用户: 「有的个股怎么没显示完整」。
              27 种组合里**只有这一格**是这样(120 格有结论、4 格有补充层注记)。
              它其实是有含义的: 价格落在三条通道都认可的公共区间里 —— 那不是
              「没数据」, 是「位置上没有可说的」。给它一个名字, 与别的格一致。
              **底层判定一个字没动**, 改的只是这一格印什么(与 R203 同一条路子)。 */}
          {note ? note.title : '通道中部'}
          <Days d={stateRun} />
        </button>
    )
  }
  return (
      <VerdictHover v={v} note={"点击摊开这只票过去每一档结论 —— 出现在哪几天、当时说了什么、之后走成什么样。"
        + geoLines(geo, ev, runs, energy, ph)}>
        <button
          onClick={onOpen}
          className={`inline-flex cursor-pointer whitespace-nowrap rounded border px-1 py-0.5 text-[12px] transition-colors hover:brightness-125 ${VERDICT_CLS[v.tone]}`}
        >
          {v.title}
          <Days d={v} />
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

// [R261] 那张「阶段配色」表在这里删掉了 —— **它是 R257 留下的错**。
//
// R257 把这一行的文字从「阶段」换成了「走了多远」(成熟度), 却**忘了换配色**:
// 颜色仍按阶段码取, 于是同一句「走到中段」在上升中的票上是红的、在下跌中的
// 票上是绿的、在横盘中的票上是近白的。用户: 「趋势列的描述都没有统一颜色,
// 有些是白色字体」—— **颜色在说阶段, 文字在说走了多远, 两码事。**
//
// 成熟度是一句**事实读数**(这一段走了多远), 不是判断, 所以统一给次要色。
// 那张表改完就没人用了, 按守则一并删, 不留死代码。


/**
 * [R277 → R297] 「进度」列(成熟度 + 快慢)**并进「结论」列了**, 不再是独立一列。
 *
 * 用户: 「个股分析页面的进度列和结论列看看怎么合并和显示哪些内容」。
 *
 * ## 本来就是一层
 *
 * 两列同源(都从 `phase()`/`geo` 出), 而且**点开去的是同一个地方**(复盘弹窗的
 * 「通道结论」页)。一列说这一档是什么、今天该干嘛, 另一列说这一段走到什么程度 ——
 * 后者是前者的**刻度**, 不是第四条结论。这与 R211「测量与结论拆两列等于让人
 * 左右对眼把结论和它的依据接起来」是同一条理由, 只是这次轮到它自己。
 *
 * ## 怎么并的: **不摞行, 各自归队**
 *
 * 直接摞上去就是五行 —— 那正是 R217 撤过的病(行与行糊成一片)。**行数一行没加**,
 * 进度那两个读数各自并进已有的两行里, 每一行都因此成了一句完整的话:
 *
 *     超买回落 已3天  走到中段     ← 哪一档 · 走了多久 · 走了多远(同一个"到什么程度")
 *     该止盈了 41.20  正在放慢     ← 今天该干嘛 · 这个判断还稳不稳(前瞻的那一半)
 *     突破确认? · 生命线跌破 …     ← 事件 · 理由(原样)
 *
 * R217 那个坑的病根是**行数**与行高参差, 不是每行的内容量 —— 所以这么并是安全的。
 *
 * ## 为什么这两个读数原本该在一格里(R277 的论证, 原样保留)
 *
 * 分离度与加速度**不是两件事, 是同一件事的一阶与二阶**。实测(合成路径, 真均线):
 *
 *     匀速涨 0.10/天  → 间距 5.000, 加速度 0.0000    (第 150/300/399 天都是 5.000)
 *     匀速涨 0.20/天  → 间距 10.00, 加速度 0.0000    (速度翻倍, 间距正好翻倍)
 *     越涨越快        → 间距 8.084, 加速度 +0.0079
 *     还在涨但越涨越慢 → 间距 1.916, 加速度 -0.0079
 *
 * 也就是 **间距 = 50 × 速度 ÷ ATR**, 而加速度是这个速度的变化率。一个是读数、
 * 一个是读数在往哪走 —— 按 R219 的「一个话题一行, 不许拆到上下两处」, 它们
 * 本来就该同格。而在此之前**加速度在决策台上根本看不见**: 走势列那一行写的是
 * `align ? align : pace_cn`, 而 `alignment()` 几乎永远非空, 于是快慢那一支
 * 轮不上; 悬停里被同一个三元顶掉。它只剩「结论」列悬停里的一行。
 *
 * ## 两条沿用的规矩
 *
 * - **数字全部退到悬停**(R209)。「间距 2.4 倍日常波动」再准确, 扫表的人也换算
 *   不出它意味着什么 —— 正文给档位, 数字给要核对的人。
 * - **成熟度是事实读数, 统一次要色**(R261)。挂条件配色会让同一句「走到中段」
 *   在不同票上是不同颜色, 那是颜色在说另一件事。快慢不一样 —— 它**是**判断
 *   (在往多头还是空头变), 所以按方向上色。
 */
/**
 * [R278] 快慢的配色**按 `level`(也就是 a1 的符号)取, 不按那句话取**。
 *
 * R277 这里是按词映射的, 其中两个词的颜色与符号是反的:
 * 「跌势在缓」(a1>0) 给了琥珀、「正在放慢」(a1<0) 也给了琥珀。
 *
 * 按符号取则**四个象限全对**, 而且不需要知道方向 —— A 股红涨绿跌:
 *
 *     a1 > 0  往上使劲  → 红   (涨势里=还在加速; 跌势里=跌势在缓, 都是偏多的一侧)
 *     a1 < 0  往下使劲  → 绿   (涨势里=正在放慢; 跌势里=跌得更急, 都是偏空的一侧)
 *
 * 这也正是 `ComboView` 一直在用的规则 —— 那边的颜色从来没错过, 错的只有词:
 * **颜色编的是符号, 词描述的是大小**, 而这个量的意义在符号上。
 */
const PACE_CLS: Record<string, string> = {
  accel: 'text-red-400/85',
  decel: 'text-emerald-400/85',
  steady: 'text-muted',
}

// [R297] 「进度」并进「结论」之后, 那两个读数在这里的角色是**刻度而不是结论**,
// 所以它们不戴徽标: 一行里只有一枚带框的东西, 那枚就是这一行在说的那件事。
// 成熟度统一次要色(R261: 它是事实读数, 挂条件配色等于让颜色说另一件事);
// 快慢照旧按 `level` 上色(R278: 它**是**判断 —— 在往多头还是空头变)。
const MATURITY_TIP = '这一段走到哪一步了(刚起步 / 走到中段 / 走了很长 / 走过头了)。'
  + '\n量的是这一段走得多远, 不是走了多少天 —— 一只慢牛走三年也可以一直是「刚起步」。'
  + '\n数字在这一格的悬停里(那一行以 [间距] 开头)。'
const PACE_TIP = '这个速度还撑不撑得住(还在加速 / 速度平稳 / 正在放慢;跌势里换成跌势在缓 / 跌得更急)。'
  + '\n它是上一行那个读数的变化率 —— 上面说现在多快, 这里说这个速度在往哪变。'
  + '\n红=往上使劲, 绿=往下使劲。数字在这一格的悬停里(那一行以 [快慢] 开头)。'

function Qualifier({ text, title, cls = 'text-muted' }: {
  text?: string | null; title: string; cls?: string
}) {
  // [R299] 缝隙由它自己带(`ml-1.5`), 不由网格的 `gap-x` 给 —— 没有刻度的时候
  // 那道缝会把整格挤偏, 而这一列本来就该是"有就贴上、没有就当它不存在"。
  // 空的时候仍要占住格子(返回 `null` 会让下一行的徽标补进来, 整个错位)。
  if (!text) return <span aria-hidden />
  return (
    <span className={`ml-1.5 justify-self-start whitespace-nowrap text-[11px] ${cls}`}
          title={title}>{text}</span>
  )
}

// [R277 加, R297 删] `SpreadCell`(「进度」那一列的单元格)在这里删掉了。
// 它的两个读数并进了 `ConclusionCell` 的前两行(见上面那段说明), 悬停里的
// 数字本来就已经在「结论」列的 `geoLines()` 里(`[间距]` 与 `[快慢]` 两行)——
// **那份重复是这次合并顺带清掉的**: 同一个量原来一列印档位、另一列悬停印数字。

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
            action?: string; intraday?: boolean
            /** [R286] 今天就是转折日 —— 后端给的读数, 不在这里推 */
            flipped?: boolean } | null
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
    trend ? `【六态】${trend.state_cn} · 已${trend.duration}天`
      + (trend.since ? `,自 ${trend.since}` : '')
      // [R286] 转折日在悬停里也说一句 —— 可见行只放得下两个字
      + (trend.flipped ? ',今天就是转折日' : '') : '',
    trend?.action ?? '',
    // [R298] 原来这里另写了一份(`【通道】阶段名 —— why`), 与「结论」列 `geoLines()`
    // 里那份**是同两句话、两个格式、两个产地**。走同一个 `phaseLines`。
    ...phaseLines(ph),
    // 第三行那句(三个尺度对齐到第几步)原来自带一份悬停, 一并收进来
    // [R277] 悬停里那个 `: 快慢:${ph.pace_cn}` 回退也去掉了 —— 与可见行同一个理由:
    // 它几乎轮不上(align 基本永远非空), 而快慢现在有自己的列。
    ph?.align ? `【${ph.align.cn}】${ph.align.why}` : '',
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
              className="mx-auto flex w-full cursor-pointer flex-col items-center gap-0.5 rounded-btn px-1 py-0.5 leading-snug transition-colors duration-hover hover:bg-elevated/40">
        <span className="flex flex-wrap items-center justify-center gap-1">
          {trend ? (
            <span className={`inline-flex whitespace-nowrap rounded border px-1.5 py-0.5 text-[12px] ${trendCls ?? ''}`}>
              {/* [R290] 天数从徽标上**搬到了第二行**, 换成「转折后第 N 天」——
                  用户: 「这类词统一改成出现转折后的第几天」。
                  徽标上不再留一份: 同一个数印两遍, 读的人得先确认是不是一回事
                  (R249 立的正是这条规矩, 这里是同一条规矩换了个说法执行)。 */}
              {trend.state_cn}{trend.intraday ? <span className="ml-0.5 opacity-70">*</span> : null}
            </span>
          ) : <span className="text-[12px] text-muted/30">—</span>}
          {/* [R286 加, R291 撤] 第一行那枚「转折」小标撤掉了。用户看着截图说
              「显示不好看, 想想怎么设计今天就是转折的场景」——
              **毛病是同一件事说了两遍**: 上面一枚琥珀「转折」, 下面一行琥珀
              「转折后第 1 天」, 中间还夹着一个绿色徽标, 一个小格子里三种颜色、
              两份同样的意思。
              第二行本来就是"离转折多远"这个槽位, 转折当天它自己变成那句话就够了
              (见下面)。**信息一点没少, 少的是重复。** */}
        </span>
        {/* [R277] 「走了多远」(成熟度)那一行**搬到独立的「间距」列**去了 ——
            用户: 「那把走势列的分离度拆分出来成为完整的一列」。见 SpreadCell。
            这一列于是回到只讲**方向**: 六态说什么 + 三个尺度转到第几步。
            [R257] 「阶段」那个词仍然不印在徽标上(它和六态抢方向), 完整说明在悬停。 */}
        {/* [R224] 第二行给「三个尺度走到第几步」, 而不是一个警告。
            R223 那版是成对冲突检查, 实测超过一半的行挂警告 —— 那是噪声。
            三者是滞后阶梯(价格最快→六态→均线最慢), 不一致 = 转折还没走完。
            [R277] 原来这里是 `align ? align : pace_cn`。**那个回退基本走不到** ——
            `alignment()` 只要六态/位置/间距三样都在就返回非空, 于是快慢那一支
            几乎永远轮不上, 加速度在这一列上等于不显示(悬停里也被同一个三元顶掉)。
            现在快慢有了自己的位置(间距列), 这里不再回退到它 —— 回退过去只会让
            同一个读数在两列里各印一遍。算不出来就留空, 不拿别的东西冒充。 */}
        {/* [R290] 这一行原来印的是**三个尺度对齐到第几步**(「正在转多」那类词)。
            用户: 「外面不再是显示"正在转多"这样的的字眼了, 这类词统一改成出现
            转折后的第几天」。
            换成天数是**降噪也是升信息**: 「正在转多」是一个推断(而且与徽标上的
            六态抢方向, R257 为同一个毛病撤过「阶段」), 而"转折之后走了几天"是
            一个事实, 并且直接回答扫这一列时真正想问的那句话 ——
            「这只票刚转, 还是已经走了一段?」
            三尺度对齐没删, 降进悬停当依据(R270「收起来, 不删」同一条路子)。 */}
        {/* [R291] 转折当天**点亮成一枚芯片**, 平常是一枚同尺寸的透明框。
            两点讲究:
            ① **同一个盒子**(同样的 `px-1.5 py-px` 与边框宽度), 只是边框与底色
               在平常那天是透明的 —— 于是**行高一格都不跳**, 一列扫下来
               第二行的基线是齐的(R217「固定两行」那条规矩)。
            ② 转折那天写「今天转折」而不是「转折后第 1 天」。两句话是同一个数,
               但前者是大白话 —— 用户为这件事纠正过好几次(R206 档位名改大白话、
               R284「别人看了会看不懂」、R285「加多两个字表述清楚」)。
            琥珀色与复盘逐日表那个「转折」标记同色, 两个页面同一件事同一个颜色。 */}
        {trend ? (
          <span className={`inline-flex whitespace-nowrap rounded border px-1.5 py-px text-[11px] ${
            trend.flipped
              ? 'border-amber-400/45 bg-amber-400/10 font-medium text-amber-300'
              : 'border-transparent text-muted'}`}
                title={trend.flipped
                  ? '今天六态状态发生了翻转 —— 昨天还不是这个状态'
                  : '从六态转折那天算起, 到今天第几个交易日'}>
            {trend.flipped ? '今天转折' : <>转折后第 {trend.duration} 天</>}
          </span>
        ) : (
          <span className="text-transparent select-none text-[11px]">·</span>
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
  if (!p) return <span className="text-[12px] text-muted/30">—</span>
  return (
      <span className={`inline-flex whitespace-nowrap rounded border px-1.5 py-0.5 text-[12px] ${PLAY_CLS[p.tone] ?? PLAY_CLS.muted}`}
            title={[p.why, p.note].filter(Boolean).join('\n\n')}>
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
export function ConclusionCell({ v, ev, geo, runs, energy, ph, p, stateRun, onOpen }: {
  v?: KeltnerVerdict | null
  /** [R246] 没结论那一格的时长 */
  stateRun?: { days: number; since?: string; capped?: boolean } | null
  ev?: ChannelEvent | null
  geo?: ChannelGeometry | null
  runs?: ChannelRuns | null
  energy?: BandEnergy | null
  ph?: ChannelPhase | null
  p?: Playbook | null
  onOpen: () => void
}) {
  // [R217 → R255 → R297] 三行, 每行"判定 + 它的刻度":
  //   行 1: 结论徽标(含已N天) + 走到哪一步
  //   行 2: 怎么办徽标(含价) + 快慢
  //   行 3: 事件 · 理由 · 另有 N 处分歧(整段折行)
  const evOn = ev && ev.code !== 'none'
  const more = p && p.conflicts.length && p.level !== 'conflict'
  // [R299] 第三行**只在真有话说的时候才出现**。用户: 「没帮助的东西就不要显示了」。
  //
  // 「没事」那一档的 `why` 已经在后端挪进 `note` 了(它只是把「没事」换个说法再
  // 讲一遍), 于是这一行自然消失 —— 一张 166 行的表里, 没事的那些行不该和要动的
  // 一样占三行。这里**不判断档位**, 只判断"有没有内容": 判据留在后端一处,
  // 前端再写一个 `level === 'idle'` 就是同一个规则两处定义(R286 立过)。
  const line2 = [
    evOn ? `${ev!.cn}${ev!.confirmed ? '' : '?'}` : '',
    p?.why || '',
    more ? `(另有 ${p!.conflicts.length} 处判定不一致)` : '',
  ].filter(Boolean).join(' · ')
  const tip = [
    evOn ? `${ev!.cn}${ev!.confirmed ? '' : '(未确认)'} —— ${ev!.why}` : '',
    p?.why || '',
    p?.note || '',
    more ? '另有判定不一致:\n' + p!.conflicts.join('\n') : '',
  ].filter(Boolean).join('\n\n')
  return (
    // [R255] 排版跟「AI 信号」那一列对齐。用户: 「结论列也要像 ai 信号列那样排版」。
    //
    //   贵不贵 已N天      ← 一行
    //   怎么办            ← 一行
    //   说明文字…         ← 整段折行, 不再单行截断
    //
    // R217 当初把这一列压成**固定两行**(徽标横排 + 说明截断), 是因为那时它会摞到
    // 五层、每行高度还不一样, 行与行糊成一片。**那个顾虑现在不成立了**: 隔壁
    // AI 信号列 R253 起就是固定竖排三行到价预案, 行高本来就由它撑着 —— 结论列
    // 竖排不会再让任何一行变高, 反而两列的读法终于一致(都是从上往下一件一件读)。
    //
    // [R255 → R298] **左对齐改回居中。** 用户: 「每列都居中对齐好」。
    //
    // R255 那句理由(「竖排之后居中会让三行的左边缘参差不齐」)在**当时**是对的:
    // 那一版三行分别是徽标 / 徽标 / 一整段折行说明, 三种宽度差得很远。
    // R297 之后前两行各自变成「徽标 + 一个短词」, 宽度接近了, 而第三行绝大多数
    // 情况是**一行以内**(事件 4 字 + why 二十来字, 23rem 装得下)——
    // 参差的前提没了, 而整张表除这一列外都是居中的。
    //
    // 这一列于是回到 `TD_BASE` 的默认(居中), 不再自己覆写; 容器加 `mx-auto`
    // 与 `items-center` —— 光有 `text-center` 不够: 带 `max-w` 的块级容器
    // 不会自己居中, 而 `items-start` 会把两行徽标钉在左边。
    <td className={`${TD_BASE} px-2`}>
      {/* [R283] `max-w-[15rem]`(240px) → `19rem`(304px)。**这个上限才是「结论」
          一直被挤的真原因** —— 这一列 18% 宽在常见视口上有 300px 出头, 而内容被
          硬卡在 240px, 光加列宽一点用都没有。两者得一起动。 */}
      {/* [R299] 两行**共用一条中轴**。用户看着截图: 「排版不好看」。
          
          R298 居中之后每一行各自居中, 而两行宽度不一样 ——「候选池 已1天+」比
          「没事」宽出一大截, 于是徽标和刻度四个边缘全是散的, 看着像随手堆的。
          
          改成两列网格: **判定靠右、刻度靠左**, 整个网格居中。于是
          
              候选池 已1天+│走了很长
                    没事  │速度平稳
          
          中间那条缝成了一条真的竖线, 两行锁在一起 —— 居中的同时有了对齐。
          列宽用 `max-content`, 所以缝的位置由内容自己定, 不用写死任何数字。
          
          `gap-x` 故意不写, 改成刻度自己带 `ml-1.5` —— 没有刻度那一列时
          (`ph` 为空), 写 `gap-x` 会留下一道空隙把整格挤偏。 */}
      <div className="mx-auto grid max-w-[23rem] justify-center gap-y-0.5 leading-snug
                      grid-cols-[max-content_max-content]">
        {/* [R297] 行1 = 哪一档 + **走到什么程度**。
            「已N天」与「走到中段」是**同一个问题的两把尺**(走了多久 / 走了多远),
            所以它们贴着同一枚徽标, 而不是各占一行。 */}
        <span className="justify-self-end">
          <VerdictInner v={v} ev={ev} geo={geo} runs={runs} energy={energy} ph={ph}
                        stateRun={stateRun} onOpen={onOpen} />
        </span>
        <Qualifier text={ph?.maturity_cn} title={MATURITY_TIP} />
        {/* [R297] 行2 = 今天该干嘛 + **这个判断还稳不稳**。
            快慢是**前瞻的那一半**: 「该止盈了 · 正在放慢」与「该止盈了 · 还在加速」
            是两句不同的话, 而动作那一枚徽标自己说不出这个差别。 */}
        <span className="justify-self-end">
          <PlaybookInner p={p} />
        </span>
        <Qualifier text={ph?.pace_cn} title={PACE_TIP}
                   cls={PACE_CLS[geo?.accel?.level ?? ''] ?? 'text-muted'} />
        {line2 && (
          <span className={`col-span-2 whitespace-normal break-words text-center text-[11px] leading-snug ${
            evOn ? EVENT_CLS[ev!.code] ?? 'text-muted' : 'text-muted'}`}
                title={tip}>
            {line2}
          </span>
        )}
      </div>
    </td>
  )
}
