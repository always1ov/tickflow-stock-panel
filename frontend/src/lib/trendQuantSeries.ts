/**
 * [R486] 趋势量化副图 —— 把后端算好的逐根数值, 照原文的画线语句翻成 ECharts 系列。
 * **画法的唯一产地。** 算法在后端 `indicators/trend_quant.py`。
 *
 * 用户: 「在量化macd上方加个副图, 先还原做出来再说, 名称就叫趋势量化」。
 *
 * 原文里画东西的语句, 按原文的先后(后画的盖在上面):
 *
 *   超买:3.2,COLORYELLOW;  超卖:0.5,COLORYELLOW;            两条水平线
 *   平均线:EMA(波动线,3);                                  输出线(原文无色)
 *   STICKLINE(平均线>=昨天, 波动线, 昨天波动线, 2, 0) 红 / 否则绿   短柱
 *   DRAWTEXT 极底(1.75 红) / 升 / 顶 / 下(在平均线处, 原文无色)
 *   DRAWTEXT 建仓(0.75 红) / 逃(3.1 黄) / 见底(1 浅红) / 绝底(1 红)
 *   STICKLINE(VAR17, 0.53, 吸筹, 1, 0) 白                    细白柱
 *   吸筹:VAR17/CDXS+0.53;                                  输出线(原文无色)
 *
 * 不引用量化MACD 的画法 —— 两张副图各自一份, 哪张以后调了都不牵连另一张。
 */
import { TREND_QUANT_COLORS as C } from '@/lib/theme'

/** 后端 `/trend-quant` 的逐根数值(对齐前)。`null` = 那一根不画。 */
export interface TrendQuantData {
  dates: string[]
  wave: (number | null)[]
  wave_prev: (number | null)[]
  avg: (number | null)[]
  stick_up: (number | null)[]
  xichou: (number | null)[]
  xichou_bar: (number | null)[]
  marks: Record<TrendMarkKey, (number | null)[]>
}

export type TrendMarkKey = 'jidi' | 'sheng' | 'ding' | 'xia' | 'jiancang' | 'tao' | 'jiandi' | 'juedi'

/**
 * 八种字: 写什么、原文写在多高、什么颜色, 以及 [R559] 写进哪条字道。
 * `at` 是原文 DRAWTEXT 的高度(`'avg'` = 当天平均线处), R559 起**不再照它画**, 只留作出处;
 * `lane` 是现在的位置: 卖出一侧(顶 / 逃 / 下)在图顶上的字道, 买入一侧在图底下的字道。
 *
 * [R620] `short`: 最挤的窗口下只写一个字。用户: 「建仓 / 见底 / 极底 / 绝底还是让人看不清对应哪一天」——
 * 两个字有 26px 宽, 密集时只能往右让位, 让完就看不准是哪天了; 一个字 11px, 让位少得多。
 * [R621] 但全称更直观, 所以默认仍写全称, 只有 250 日这种一格 2px 的窗口才缩成单字 ——
 * 判据与图例同源, 见 `markLabel`。
 */
export const TREND_MARKS: {
  key: TrendMarkKey; text: string; short: string; at: number | 'avg'; color: string; lane: 'top' | 'bottom'
}[] = [
  { key: 'jidi', text: '极底', short: '极', at: 1.75, color: C.red, lane: 'bottom' },
  { key: 'sheng', text: '升', short: '升', at: 'avg', color: C.text, lane: 'bottom' },
  { key: 'ding', text: '顶', short: '顶', at: 'avg', color: C.text, lane: 'top' },
  { key: 'xia', text: '下', short: '下', at: 'avg', color: C.text, lane: 'top' },
  { key: 'jiancang', text: '建仓', short: '建', at: 0.75, color: C.red, lane: 'bottom' },
  { key: 'tao', text: '逃', short: '逃', at: 3.1, color: C.yellow, lane: 'top' },
  { key: 'jiandi', text: '见底', short: '见', at: 1, color: C.lightRed, lane: 'bottom' },
  { key: 'juedi', text: '绝底', short: '绝', at: 1, color: C.red, lane: 'bottom' },
]

/** [R620] 图例里那行单字的悬停说明: 极=极底 …… 其余四个字就是本字 */
export const TREND_MARK_SHORT_HELP = TREND_MARKS
  .filter(m => m.short !== m.text)
  .map(m => `${m.short}=${m.text}`)
  .join(' · ') + '（顶 / 逃 / 下 / 升 就是本字）'

/**
 * [R621] 图上写全称还是单字 —— **只此一个判据**, 画字与图例同源。
 *
 * 用户: 「按这个方案来」—— R620 的备选: 宽窗口恢复全称(建仓 / 见底 / 极底 / 绝底 更直观),
 * 只有最密的 250 日窗口才缩成单字。
 *
 * 60 / 120 日窗口一格约 4.5px 以上, 两个字 26px 还排得开(三行 + 让位兜底见 packLaneTexts);
 * 250 日一格只 2px 出头, 两个字必然连成一片, 那时才用 `short`。
 */
export const TREND_MARK_FULL_BARS = 120

/** 某一根 K 线窗口下, 这个信号该写什么字。 */
export function markLabel(mark: { text: string; short: string }, visibleBars: number): string {
  return visibleBars <= TREND_MARK_FULL_BARS ? mark.text : mark.short
}

/**
 * [R555] 副图左上角的图例 + 悬停说明 —— 三种线各代表什么。**只此一个产地**。
 *
 * 用户: 「我好像发现有绿线和紫线, 都代表什么含义。我想加点注释」。原文里这三样都没有注释,
 * 其中绿线最容易看错: 平时它贴在 0.53, 紧挨着 0.5 那条黄线, 看着像一条平的绿线。
 * 说明只讲**这条线是怎么来的、怎么读**, 不添判定 —— 公式是作者的, 冻结。
 */
export const TREND_QUANT_LEGEND: { name: string; color: string; desc: string; labelledOnLine?: true }[] = [
  {
    name: '平均线', color: C.avg,
    desc: '红绿短柱(波动线)的 3 日均线。波动线 = 收盘价落在「近 10 日最低 ~ 近 25 日最高」'
      + '之间的哪个位置, 折成 0~4 再平滑: 越靠上越接近近期高点。平均线向上时短柱画红, 向下画绿。',
  },
  {
    name: '吸筹', color: C.xichou,
    desc: '平时贴在 0.53 不动(紧挨下面那条黄线, 所以看着像一条平的绿线)。'
      + '只有最低价打到近 38 日新低的那几天才拱起来, 下面配白色细柱, 之后几天慢慢落回; '
      + '拱多高看最近最低价跌得有多急(原公式叫「主力吸货」), 高低是和这只票上市以来最高的那一次比。',
  },
  {
    name: '超买 / 超卖', color: C.yellow, labelledOnLine: true,
    desc: '两条固定参考线。波动线靠近 3.2 = 收盘在近期区间的高位, 靠近 0.5 = 在近期区间的低位。',
  },
]

/** 悬停说明的全文(三段 + R620 的八种字缩写对照) */
export const TREND_QUANT_HELP = TREND_QUANT_LEGEND.map(l => `${l.name}: ${l.desc}`).join('\n\n')
  + `\n\n信号字: ${TREND_MARK_SHORT_HELP}。60 / 120 日窗口写全称, 250 日窗口缩成单字。`

/** 原文两种柱宽: 2(红绿短柱)与 1(吸筹白柱)。按量化MACD 实测的「宽度 2 = 间距 66%」折算。 */
export const TQ_STICK2 = 0.66
export const TQ_STICK1 = 0.33

export interface TrendQuantAligned {
  wave: (number | null)[]
  wave_prev: (number | null)[]
  avg: (number | null)[]
  stick_up: (number | null)[]
  xichou: (number | null)[]
  xichou_bar: (number | null)[]
  marks: Record<TrendMarkKey, boolean[]>
}

/** 按日期对到图上的 x 轴。图上有、后端没有的日子一律不画。 */
export function alignTrendQuant(dates: string[], q: TrendQuantData | undefined): TrendQuantAligned {
  const idx = new Map((q?.dates ?? []).map((d, i) => [d, i]))
  const pick = (arr: (number | null)[] | undefined) => dates.map(d => {
    const i = idx.get(d)
    return i == null || !arr ? null : (arr[i] ?? null)
  })
  const marks = {} as Record<TrendMarkKey, boolean[]>
  for (const m of TREND_MARKS) marks[m.key] = pick(q?.marks?.[m.key]).map(v => v === 1)
  return {
    wave: pick(q?.wave), wave_prev: pick(q?.wave_prev), avg: pick(q?.avg),
    stick_up: pick(q?.stick_up), xichou: pick(q?.xichou), xichou_bar: pick(q?.xichou_bar),
    marks,
  }
}

/**
 * [R559] 字道。用户对 R558 的截图: 「字还是重叠」。
 *
 * R558 只让字与字互相避让, 字本身仍写在原文的高度上(平均线处、0.75、1、3.1 ……), 那些高度正是
 * 线和柱子所在的地方 —— 「顶」压着紫线, 「建仓」压着绿线和柱子, 同一天连出两个字就竖着贴在一起。
 * 所以把字从图里挪出去: 图顶上一条字道放卖出一侧(顶 / 逃 / 下), 图底下一条放买入一侧(升 / 建仓 /
 * 见底 / 绝底 / 极底), 每个字**水平对准它那一天**; 字道分行, 画的时候按真实像素宽度排, 挤不下
 * 才换下一行。出不出字、在哪一天, 一概不变; 变的只是竖直位置。
 *
 * [R619] 两行 → 三行, 并改掉"两行都占满就强行压进最空那行"的兜底 —— 用户: 「顶部和底部字还是会
 * 重叠」。120 日窗口下相邻两根只隔约 4.5px, 而「建仓 / 见底 / 极底 / 绝底」有 26px 宽, 两行装不下
 * 一串挨着的信号; 强行压进去就是在已有字上再盖一个。现在: 先按横坐标排序(调用方是按"哪种字"分批给
 * 的, 不是时间序), 三行都放不下时允许往右挪几像素, 连挪都放不下就**不画**这个字 —— 宁可少一个,
 * 也不让两个叠在一起。
 *
 * [R629] 三行 → 两行, 并把留白从 22 收到 6 —— **副图高度不再动**, 改的是副图内部的预算。
 * 用户: 「趋势量化的里面显示的内容压得很扁……设计个方案处理趋势量化的完整显示问题」。
 * 按 R626 的副图 166px 算, 原来的预算表是: 标题带 18 + 顶字道 3+3×14+4 + 底字道 22+3×14+4 = 135,
 * 留给 0~4 走势的只剩 **31px**(7.75px/单位), 线和柱子自然糊成一条。
 * 现在: 18 + (2+2×13+4) + (6+2×13+4) = 86, 走势区 **80px**(20px/单位, 2.6 倍)。
 * 两行会不会丢信号? 不会重叠(打包算法逐行放, 放不下才跳过), 且 R621 的「全称排不下改单字重排」
 * 兜底仍在 —— 密集窗口里偶尔少一个字, 换来整条走势可读。这两个常量与 `tqYRange` 同源, 改一处即生效。
 *
 * 字道贴着副图底边画。
 */
export const LANE_FONT = 11
export const LANE_ROW_H = 13
export const LANE_ROWS = 2
export const LANE_TOP_PAD = 2
export const LANE_BOTTOM_PAD = 6   // 字道与副图底边之间的留白([R629] 22 → 6: 那段白不承载任何图元)
export const LANE_HALO = { stroke: '#000000', lineWidth: 3 }
/** [R619] 两行都放不下时, 最多把字往右让这么多像素(120 日窗口下约 2 根 K 线, 看不出来) */
export const LANE_NUDGE_MAX = 8

/** 两条字道一共占掉的高度(px, 不含标题带) —— 副图因此加高这么多, 图本身不被挤小 */
export const TQ_LANES_H = LANE_TOP_PAD + LANE_ROWS * LANE_ROW_H + LANE_BOTTOM_PAD + LANE_ROWS * LANE_ROW_H

/** [R629] 走势区(0~4 那一段)在 `paneH` 高的副图里能分到多少像素 —— 单测钉住「不被字道吃掉」。 */
export function tqPlotHeight(paneH: number, headerPx = 0): number {
  return Math.max(1, paneH - headerPx - LANE_TOP_PAD - LANE_ROWS * LANE_ROW_H - 4
    - LANE_BOTTOM_PAD - LANE_ROWS * LANE_ROW_H - 4)
}

/**
 * 纵轴上下界: 波动线恒在 0~4(收盘不会跑出近 10 日最低 / 近 25 日最高), 把字道那几十像素换算成
 * 数值加到两头。副图高不同(个股预览 / 最大化 / 窄屏), 换算出来的上下界也不同。
 *
 * [R616] `headerPx`: 副图顶上给 pane 标题留的像素。lightweight 版标题画在图里(R565 画在图外),
 * 顶字道因此整体下移这么多 —— 纵轴范围必须同步, 否则柱子会顶进标题。
 */
export function tqYRange(paneH: number, headerPx = 0): { min: number; max: number } {
  const topPx = headerPx + LANE_TOP_PAD + LANE_ROWS * LANE_ROW_H + 4
  const bottomPx = LANE_BOTTOM_PAD + LANE_ROWS * LANE_ROW_H + 4
  const perUnit = tqPlotHeight(paneH, headerPx) / 4
  return { min: -bottomPx / perUnit, max: 4 + topPx / perUnit }
}

/** 字宽(px): 11px 字号, 汉字 11px, 外加描边 */
const laneTextW = (t: string) => [...t].length * LANE_FONT + 4

/** [R619] 待排的一个字: 哪条道、横坐标对准哪一天、占多宽 */
export interface LaneDraft<T> {
  lane: 'top' | 'bottom'
  x: number
  w: number
  item: T
}

/** [R620] 排好的一个字: `x` 是让位后的真实中心, `anchorX` 始终是那一天的位置(画日期锚点用) */
export interface LanePlaced<T> {
  lane: 'top' | 'bottom'
  row: number
  x: number
  anchorX: number
  item: T
}

/**
 * [R619] 字道排版 —— 两条字道唯一的排法, ECharts 旧路径与 lightweight 现行路径都走这里。
 *
 * 输入可以乱序(现行代码按 mark 类型分批生成), 这里先按横坐标从左到右排。每字先找一行
 * (上一字的右边界不越过本字左边界); 三行都放不下时, 往右让不超过 `LANE_NUDGE_MAX` 像素,
 * 挑让得最少的那行; 还是放不下就跳过。返回的 `x` 是挪过之后的真实中心, `anchorX` 不挪。
 */
export function packLaneTexts<T>(
  drafts: LaneDraft<T>[], rows = LANE_ROWS,
): LanePlaced<T>[] {
  const out: LanePlaced<T>[] = []
  const right: Record<'top' | 'bottom', number[]> = {
    top: Array(rows).fill(-Infinity), bottom: Array(rows).fill(-Infinity),
  }
  const sorted = [...drafts].sort((a, b) => a.x - b.x)
  for (const d of sorted) {
    let left = d.x - d.w / 2
    const rs = right[d.lane]
    let row = rs.findIndex(r => r <= left)
    if (row < 0) {
      let bestShift = Infinity
      for (let i = 0; i < rows; i++) {
        const shift = rs[i] - left
        if (shift <= LANE_NUDGE_MAX && shift < bestShift) { row = i; bestShift = shift }
      }
      if (row < 0) continue
      left += bestShift
    }
    rs[row] = left + d.w
    out.push({ lane: d.lane, row, x: left + d.w / 2, anchorX: d.x, item: d.item })
  }
  return out
}

/**
 * 把可见范围里的字排进两条字道。`xs[i]` 是第 i 根的像素横坐标, 看不见的给 null。
 * 返回 [字, 横坐标, 第几行] —— 纯函数, 单测用。
 */
export function laneLayout(
  marks: Record<TrendMarkKey, boolean[]>, xs: (number | null)[],
): { m: (typeof TREND_MARKS)[number]; x: number; row: number }[] {
  const drafts: LaneDraft<(typeof TREND_MARKS)[number]>[] = []
  for (let i = 0; i < xs.length; i++) {
    const x = xs[i]
    if (x == null) continue
    for (const m of TREND_MARKS) {
      if (!marks[m.key][i]) continue
      drafts.push({ lane: m.lane, x, w: laneTextW(m.short), item: m })
    }
  }
  return packLaneTexts(drafts).map(({ item: m, x, row }) => ({ m, x, row }))
}
