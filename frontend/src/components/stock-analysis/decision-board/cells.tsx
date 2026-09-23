/**
 * [fork 增强] 决策台的两个只读单元格: Keltner 三档位置 / 三档组合结论。
 *
 * [R167] 从 WatchlistDecisionBoard.tsx 拆出。各自带着自己的配色表 —— 配色表是
 * 实现细节, 不该摆在 933 行主文件的顶部让人以为是全局约定。
 */
import type { BandEnergy, ChannelEvent, ChannelGeometry, ChannelPhase, ChannelRuns, KeltnerBand } from '@/lib/api'
import { POS_TEXT } from '@/lib/reviewTimeline'

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
// `ChannelStateCell`(R425 起叫 `TrendSegment`)。用户: 「趋势通道和通道态势可以放在一起吗」。
//
// **本来就该合**: 两列讲的是同一套指标的两个层次(一个是测量, 一个是从它推出来
// 的结论), 拆成两列等于让人左右对眼去把结论和它的依据接起来。
//
// 合的时候顺手改了一处: 三档位置**只印到边的那几档**。多数票三档都在通道中部,
// 把三个「通道内」逐行印出来是纯噪声 —— 恰恰是"哪一档到边了"才带信息。
// 完整的三档轨价与位置百分比留在悬停。

// [R44 加, R308 删] `VERDICT_CLS`(那十档判定的徽标配色)在这里删掉了 ——
// 用户: 「位置列我只需要知道当前短期通道位置和短中长的轨道组合」, 于是决策台上
// 不再印那个徽标, 这份配色在本文件没有第二个调用方。复盘弹窗那边有它自己的一份
// (它那儿还在印徽标), 不是同一处的重复。

// [R310] 「怎么办」列整个删掉了(用户: 「那就删除了怎么办」), 于是跟着它的
// 这些东西也没了读者, 一并删除 —— 留着就是死代码:
//
//   · PlayCell / PlaybookInner / PLAY_CLS  —— 那一列本身与它的徽标配色
//   · Qualifier / PACE_CLS                 —— 「走到哪一步」「快慢」两个刻度
//   · MATURITY_TIP / PACE_TIP              —— 上面那两个的悬停说明
//   · EVENT_CLS                            —— 事件配色(事件本身还在, 见
//     `geoLines` 里的【事件】—— 那是悬停, 不需要配色)
//
// **判定层一个字没动**: `services/stock_playbook.py` 与它那 36 条测试照旧,
// 接口也照旧返回 `playbook`, 只是前端不再取用。
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
 * 「通道档位」页)。一列说这一档是什么、今天该干嘛, 另一列说这一段走到什么程度 ——
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
 *
 * [R425] 这件事又往外推了一层: 「走势」与「位置」两**列**也通向同一个弹窗,
 * 于是两列并成一格, 按钮搬到外壳 `TrendPositionCell` 上, 这里退成左半边的内容
 * (名字也从 `ChannelStateCell` 改成 `TrendSegment` —— 它已经不是一个格子了)。
 */
export function TrendSegment({ trend, geo, runs, ph, kc, close, trendCls }: {
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
        + `,现在${b!.pos_cn}(位置 ${Math.round(b!.pct * 100)}/100)`),
    close != null ? `收盘 ${close.toFixed(2)}` : '',
    '', OPEN_HINT].filter(Boolean).join('\n')
  return (
    // [R217] **固定两行**, 高度对齐, 行与行不再糊在一起。
    //   行 1: 六态徽标
    //   行 2: 转折后第 N 天
    // [R425] 不再自己占一格、不再自己是按钮 —— 与「位置」并进 `TrendPositionCell`
    // 那一个按钮里, 这里只交出左半边的两行(fragment, 由外壳的 2×2 网格排位,
    // 左右同一行共用行高, 两条基线才齐)。悬停仍各半一份: 左半讲方向的依据。
    <>
        <span title={tip} className="flex flex-wrap items-center justify-center gap-1">
          {trend ? (
            <span className={`inline-flex whitespace-nowrap rounded border px-1.5 py-0.5 text-xs ${trendCls ?? ''}`}>
              {/* [R290] 天数从徽标上**搬到了第二行**, 换成「转折后第 N 天」——
                  用户: 「这类词统一改成出现转折后的第几天」。
                  徽标上不再留一份: 同一个数印两遍, 读的人得先确认是不是一回事
                  (R249 立的正是这条规矩, 这里是同一条规矩换了个说法执行)。 */}
              {trend.state_cn}{trend.intraday ? <span className="ml-0.5 opacity-70">*</span> : null}
            </span>
          ) : <span className="text-xs text-muted/30">—</span>}
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
          <span className={`inline-flex whitespace-nowrap rounded border px-1.5 py-px text-xs ${
            trend.flipped
              ? 'border-amber-400/45 bg-amber-400/10 font-medium text-amber-300'
              : 'border-transparent text-muted'}`}
                title={trend.flipped
                  ? '今天六态状态发生了翻转 —— 昨天还不是这个状态'
                  : '从六态转折那天算起, 到今天第几个交易日'}>
            {trend.flipped ? '今天转折' : <>转折后第 {trend.duration} 天</>}
          </span>
        ) : (
          <span className="text-transparent select-none text-xs">·</span>
        )}
    </>
  )
}

// [R205] 「怎么办」配色。**只有两档是红的** —— 纪律已破和今天已触发。
// 分歧档刻意用琥珀而不是红: 它说的是"别动", 不是"快动", 用红会被读反。
/**
 * [R308 → R315 → R316] 「位置」列 —— **一个位置名 + 一句能交易的距离。**
 *
 * 用户看过两版之后定的这一版:「只说短期 + 一句能交易的距离」。
 *
 * ## 前两版为什么不行
 *
 * R311/R314 那版是 `贴下轨 6/100` 外加 `短期 / 短中长` 两个尺度标签 ——
 * **拿词去解释版面**, 用户一句「这样表达很 low」毙了, 说得对。
 *
 * R315 换成横轨 + 三个点, 用户说「更加看不懂了」。复盘原因: 一条 7px 高的
 * 线, 两端那两道端帽在真实渲染里几乎看不见, 于是**那条轨没有任何刻度可言**;
 * 而 `-3%` / `134%` 这种越界百分比, 在没有参照物时比 `6/100` 还费解。
 * **图形不是万能药 —— 一个画不清楚的图, 比一句写清楚的话差得多。**
 *
 * ## 这一版
 *
 *     破下轨              ← 位置名, 按位置上色; 扫表时只看这一行的颜色
 *     低于下轨 1.1%       ← 离那条轨还有多远, 价格口径
 *
 * 关键是第二行**换了口径**: 不再是"通道刻度 0~100"(抽象、会越界), 而是
 * **价格百分比** —— 「低于下轨 1.1%」是一个能直接下单的数, 不需要先在脑子里
 * 把通道宽度换算一遍。
 *
 * 口径用仓库已有的那条: **(线 − 现价) / 现价**, 与出场线的 `distance_pct`、
 * 六态的翻转距离**逐字相同**(R178 立的)。不另起一套 —— 同一个"还差多远"
 * 在一个界面上有两种算法, 是这仓库反复在治的那种病。
 *
 * 看**哪条轨**由位置名决定, 不另判一次:
 *
 *     破上轨   → 上轨, 「高出上轨 X%」
 *     贴上轨   → 上轨, 「距上轨 X%」
 *     通道内   → **更近的那一条**(先撞上的就是它)
 *     贴下轨   → 下轨, 「距下轨 X%」
 *     破下轨   → 下轨, 「低于下轨 X%」
 *
 * ## 三档组合去哪了
 *
 * 进悬停 —— 用户选的就是「只说短期」。悬停里三档各自一行, 带位置名、
 * 价格距离与轨价, 外加 27 格那个组合码(它的用处是去速查表查行号,
 * 那是点开之后的事)。
 */
export function PositionSegment({ kc, geo, ev, runs, energy, ph, stateRun, close }: {
  kc?: { s?: KeltnerBand; m?: KeltnerBand; l?: KeltnerBand } | null
  geo?: ChannelGeometry | null
  ev?: ChannelEvent | null
  runs?: ChannelRuns | null
  energy?: BandEnergy | null
  ph?: ChannelPhase | null
  /** [R246 → R308] 这个三档组合连着多久 —— 后端按 `state_key(bands)` 数的。
      不占正文的行, 只进悬停; 不印的话就是把一个后端还在算的数悄悄丢掉。 */
  stateRun?: { days: number; since?: string; capped?: boolean } | null
  /** [R316] 算价格距离要用它。**不拿 `pct` 反推** —— `pct` 后端只留三位小数,
      反推出来的收盘价会和真实值差几分钱, 而这一列印的是要拿去下单的数。 */
  close?: number | null
}) {
  const s = kc?.s
  const combo = geo?.combo ?? null
  const near = railGap(s, close)
  const tip = [
    s ? `短期通道 ${s.pos_cn} —— ${near ? near.full : '离轨距离算不出来(缺现价)'}`
      : '短期通道这一档今天算不出来',
    '',
    '距离口径: (轨价 − 现价) / 现价 —— 与出场线、六态翻转距离**同一个算法**,',
    '也就是"现价还要动多少个百分点才碰到那条轨"。',
    '',
    '三档各自的位置:',
    ...(['s', 'm', 'l'] as const)
      .map((k, i2) => {
        const b = kc?.[k]
        if (!b) return `  ${'短中长'[i2]}期 —— 算不出来`
        const g = railGap(b, close)
        return `  ${'短中长'[i2]}期 ${b.pos_cn}`
          + (g ? ` · ${g.full}` : '')
          + `(轨 ${b.lower.toFixed(2)} ~ ${b.upper.toFixed(2)})`
      }),
    '',
    combo
      ? `三档组合码「${combo}」—— 27 格速查表的行号`
        + (stateRun ? `, 已连着 ${stateRun.days} 天${stateRun.capped ? '以上' : ''}`
                      + (stateRun.since ? `(自 ${stateRun.since} 起)` : '') : '')
      : '三档里缺了一档, 这个组合今天定不了(不是"罕见组合", 是算不出来)',
    '',
    OPEN_HINT,
  ].filter(Boolean).join('\n') + geoLines(geo, ev, runs, energy, ph)

  return (
    // [R425] 右半边的两行(fragment)。按钮在外壳 `TrendPositionCell` 上, 这里只画内容。
    <>
        {/* 第一行: 位置名。**扫 166 行时只看这一行的颜色** ——
            红 = 在上轨那一侧, 蓝 = 在下轨那一侧, 灰 = 通道内。 */}
        <span title={tip} className={`text-xs ${s ? POS_TEXT[s.pos] ?? 'text-muted' : 'text-muted/30'}`}>
          {s ? s.pos_cn : '—'}
        </span>
        {/* 第二行: 离那条轨还有多远, **价格口径**。
            它是这一格真正能拿去下单的那个数, 所以数字用等宽 + tabular-nums,
            整列小数点上下对齐; 措辞压暗, 不跟第一行抢。 */}
        {near ? (
          <span title={tip} className="text-micro text-muted">
            {near.label}
            <span className="ml-1 font-mono tabular-nums text-secondary">{near.pct}%</span>
          </span>
        ) : (
          <span className="text-micro text-muted/30">—</span>
        )}
    </>
  )
}

/** [R425] 两半共用的去处说明 —— 一个按钮只有一个去处, 两份悬停就得说同一句。 */
const OPEN_HINT = '点开:复盘(逐日趋势 / 通道档位 / 27 种组合速查, 在弹窗顶上切)'

/**
 * [R425] 「走势/位置」—— 原来的「走势」「位置」两列并成**一格、一个按钮**。
 *
 * 用户: 「个股分析页面的走势列和通道列合并成一个按钮入口」。
 *
 * 两格原本就通向**同一个**复盘弹窗(R228 把两个弹窗并成一个三页签的之后),
 * 只是落在不同的页签 —— 两个挨着的按钮、一个去处, 正是 R228 当年在走势列
 * 内部治过的那个毛病, 这回发生在两列之间。合并之后:
 *
 *     上涨趋势        破上轨          ← 左: 六态 / 右: 短期通道位置
 *     转折后第 5 天   高出上轨 1.1%   ← 左: 离转折多远 / 右: 离那条轨多远
 *
 * - **一个按钮**, 边界与格子重合, 悬停整格一起亮; 点开落在「趋势」页签
 *   (方向是先读的那件事), 通道档位在弹窗顶上切。
 * - 两半各自保留自己的悬停 —— 讲的是两件事(方向的依据 / 位置的依据),
 *   鼠标停在哪半就说哪半; 去处那句两半一样(`OPEN_HINT`)。
 * - 行对齐: 两半各交出固定两行, 外壳是 2 行 × 2 列的网格(按列排), 左右同一行
 *   共用行高、垂直居中 —— 左边的徽标带边框比右边的位置名高, 各自竖排时第一行
 *   会一高一低(出图看到的), 网格里就齐了。
 */
export function TrendPositionCell({ trend, trendCls, geo, runs, ph, kc, close, ev, energy,
                                    stateRun, onOpen }: {
  trend?: Parameters<typeof TrendSegment>[0]['trend']
  trendCls?: string
  geo?: ChannelGeometry | null
  runs?: ChannelRuns | null
  ph?: ChannelPhase | null
  kc?: { s?: KeltnerBand; m?: KeltnerBand; l?: KeltnerBand } | null
  close?: number | null
  ev?: ChannelEvent | null
  energy?: BandEnergy | null
  stateRun?: { days: number; since?: string; capped?: boolean } | null
  onOpen: () => void
}) {
  return (
    <td className={`${TD_BASE} whitespace-nowrap px-1.5`}>
      {/* 整格**一个** button; 内部两半都是 span —— button 里套 button 是非法 HTML */}
      <button type="button" onClick={onOpen}
              className="mx-auto grid w-full cursor-pointer grid-flow-col grid-rows-2 items-center justify-center justify-items-center gap-x-3 gap-y-0.5 rounded-btn px-1 py-0.5 leading-snug transition-colors duration-hover hover:bg-elevated/40">
        <TrendSegment trend={trend} trendCls={trendCls} geo={geo} runs={runs} ph={ph} kc={kc} close={close} />
        <PositionSegment kc={kc} geo={geo} ev={ev} runs={runs} energy={energy} ph={ph}
                         stateRun={stateRun} close={close} />
      </button>
    </td>
  )
}


/**
 * [R316] 离**在场的那条轨**还有多远 —— 价格口径。
 *
 * 口径 `(轨价 − 现价) / 现价` 与出场线的 `distance_pct`、六态的翻转距离
 * 逐字相同(R178 立的)。**方向由措辞承担**(高出 / 低于 / 距), 所以数字取绝对值
 * —— 「低于下轨 -1.1%」是双重否定, 读的人要在脑子里再翻一次。
 *
 * 看哪条轨**不另判一次**, 直接跟着位置名走; 只有「通道内」没有指定轨,
 * 那时取**更近的那一条** —— 先撞上的就是它。
 */
function railGap(b?: KeltnerBand | null, close?: number | null):
    { label: string; pct: string; full: string } | null {
  if (!b || close == null || !(close > 0)) return null
  const mk = (label: string, raw: number) => {
    const pct = (Math.abs(raw) * 100).toFixed(1)
    return { label, pct, full: `${label} ${pct}%` }
  }
  if (b.pos === 'above') return mk('高出上轨', (close - b.upper) / close)
  if (b.pos === 'below') return mk('低于下轨', (b.lower - close) / close)
  const up = (b.upper - close) / close
  const down = (close - b.lower) / close
  return up <= down ? mk('距上轨', up) : mk('距下轨', down)
}




