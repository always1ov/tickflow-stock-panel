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
  /**
   * [R488] 庄现: 出现的那一根为 1, 其余 null。**另一个冻结的独立指标**(后端
   * `indicators/zhuang_xian.py`), 只是借这张副图显示狗头 —— 画法在 `lib/zhuangXianSeries.ts`,
   * 这个文件不画它。可选: 旧缓存里没有。
   */
  zhuang?: (number | null)[]
}

export type TrendMarkKey = 'jidi' | 'sheng' | 'ding' | 'xia' | 'jiancang' | 'tao' | 'jiandi' | 'juedi'

/** 八种字: 写什么、写在多高、什么颜色。`at: 'avg'` = 写在当天平均线的高度。 */
export const TREND_MARKS: { key: TrendMarkKey; text: string; at: number | 'avg'; color: string }[] = [
  { key: 'jidi', text: '极底', at: 1.75, color: C.red },
  { key: 'sheng', text: '升', at: 'avg', color: C.text },
  { key: 'ding', text: '顶', at: 'avg', color: C.text },
  { key: 'xia', text: '下', at: 'avg', color: C.text },
  { key: 'jiancang', text: '建仓', at: 0.75, color: C.red },
  { key: 'tao', text: '逃', at: 3.1, color: C.yellow },
  { key: 'jiandi', text: '见底', at: 1, color: C.lightRed },
  { key: 'juedi', text: '绝底', at: 1, color: C.red },
]

/**
 * [R555] 副图左上角的图例 + 悬停说明 —— 三种线各代表什么。**只此一个产地**。
 *
 * 用户: 「我好像发现有绿线和紫线, 都代表什么含义。我想加点注释」。原文里这三样都没有注释,
 * 其中绿线最容易看错: 平时它贴在 0.53, 紧挨着 0.5 那条黄线, 看着像一条平的绿线。
 * 说明只讲**这条线是怎么来的、怎么读**, 不添判定 —— 公式是作者的, 冻结。
 */
export const TREND_QUANT_LEGEND: { name: string; color: string; desc: string }[] = [
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
    name: '超买 3.2 / 超卖 0.5', color: C.yellow,
    desc: '两条固定参考线。波动线靠近 3.2 = 收盘在近期区间的高位, 靠近 0.5 = 在近期区间的低位。',
  },
]

/** 悬停说明的全文(三段) */
export const TREND_QUANT_HELP = TREND_QUANT_LEGEND.map(l => `${l.name}: ${l.desc}`).join('\n\n')

/** 图例一行的宽度估算: 9px 字号下汉字按 9px、其余按 5px */
const textW = (t: string) => [...t].reduce((w, ch) => w + (/[\u4e00-\u9fff]/.test(ch) ? 9 : 5), 0)
const SWATCH = 12
const ITEM_GAP = 12

/**
 * 图例: 每项 = 一小段该色的线 + 灰字名称, 画在「趋势量化」四个字右边。
 * 名称用中性色 —— 紫只许用在图里的线上(AGENTS.md 硬约束第 15 条), 所以色只落在那段线上。
 */
export function trendQuantLegendGraphic(left: number, top: number, textColor: string): {
  graphic: Record<string, unknown>[]
  width: number
} {
  const graphic: Record<string, unknown>[] = []
  let x = left
  for (const l of TREND_QUANT_LEGEND) {
    graphic.push({ type: 'line', x, y: top + 6, silent: true,
                   shape: { x1: 0, y1: 0, x2: SWATCH, y2: 0 }, style: { stroke: l.color, lineWidth: 2 } })
    graphic.push({ type: 'text', left: x + SWATCH + 4, top: top + 1, silent: true,
                   style: { text: l.name, fill: textColor, fontSize: 9 } })
    x += SWATCH + 4 + textW(l.name) + ITEM_GAP
  }
  return { graphic, width: x - left - ITEM_GAP }
}

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

type Api = {
  value: (d: number) => number
  coord: (v: [number, number]) => number[]
  size: (v: [number, number]) => number[] | number
}

/** 竖着的一截柱子: 从 lo 到 hi, 宽度按 K 线间距的比例, 至少 1px。 */
function stickRenderer(ratio: number, colorOf: (v: number) => string) {
  return (_p: unknown, api: Api) => {
    const i = api.value(0), lo = api.value(1), hi = api.value(2), c = api.value(3)
    const a = api.coord([i, lo]), b = api.coord([i, hi])
    const band = api.size([1, 0])
    const w = Math.max(1, (Array.isArray(band) ? band[0] : band) * ratio)
    return {
      type: 'rect',
      shape: { x: a[0] - w / 2, y: Math.min(a[1], b[1]), width: w, height: Math.max(1, Math.abs(a[1] - b[1])) },
      style: { fill: colorOf(c) },
    }
  }
}

const NONE = '-'

/** 返回这张副图的全部系列, 顺序即原文画的先后。 */
export function trendQuantSeries(
  a: TrendQuantAligned,
  axis: { xAxisIndex: number; yAxisIndex: number },
): Record<string, unknown>[] {
  const n = a.avg.length
  const line = { type: 'line', ...axis, animation: false, silent: true, symbol: 'none' }
  const hline = (v: number) => Array.from({ length: n }, () => v)

  const sticks: [number, number, number, number][] = []
  a.stick_up.forEach((u, i) => {
    const w = a.wave[i], p = a.wave_prev[i]
    if (u != null && w != null && p != null) sticks.push([i, p, w, u])
  })
  const whites: [number, number, number, number][] = []
  a.xichou_bar.forEach((b, i) => {
    const x = a.xichou[i]
    if (b === 1 && x != null) whites.push([i, 0.53, x, 0])
  })
  const texts: Record<string, unknown>[] = TREND_MARKS.map((m, k) => ({
    type: 'scatter', ...axis, name: m.text, animation: false, silent: true, z: 5 + k * 0.01,
    symbolSize: 0,
    data: a.marks[m.key].map((on, i) => {
      if (!on) return NONE
      const y = m.at === 'avg' ? a.avg[i] : m.at
      return y == null ? NONE : [i, y]
    }),
    // 通达信的 DRAWTEXT: 字从那一根往右写, 纵向居中在那个数值上
    label: { show: true, position: 'right', distance: -2, formatter: m.text,
             color: m.color, fontSize: 12 },
  }))

  return [
    { ...line, name: '超买', z: 2, lineStyle: { color: C.yellow, width: 1 }, data: hline(3.2) },
    { ...line, name: '超卖', z: 2, lineStyle: { color: C.yellow, width: 1 }, data: hline(0.5) },
    { ...line, name: '平均线', z: 3, lineStyle: { color: C.avg, width: 1 },
      data: a.avg.map(v => v ?? NONE) },
    {
      type: 'custom', ...axis, name: '波动', z: 4, animation: false, silent: true, clip: true,
      encode: { x: 0, y: [1, 2] },
      renderItem: stickRenderer(TQ_STICK2, u => (u === 1 ? C.red : C.green)),
      data: sticks,
    },
    ...texts,
    {
      type: 'custom', ...axis, name: '吸筹柱', z: 6, animation: false, silent: true, clip: true,
      encode: { x: 0, y: [1, 2] },
      renderItem: stickRenderer(TQ_STICK1, () => C.white),
      data: whites,
    },
    { ...line, name: '吸筹', z: 7, lineStyle: { color: C.xichou, width: 1 },
      data: a.xichou.map(v => v ?? NONE) },
  ]
}
