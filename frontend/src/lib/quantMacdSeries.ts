/**
 * [R415] 量化MACD 副图 —— 把后端算好的逐根数值, 照原文的 STICKLINE / DRAWICON
 * 翻成 ECharts 的系列。**画法的唯一产地。**
 *
 * 原文里画东西的只有这几行(`:=` 的中间变量一律不画, 见后端模块说明):
 *
 *   STICKLINE(DIFF< 0,0,DIFF,2,0),COLORGREEN;    DIFF 实心柱: <0 绿
 *   STICKLINE(DIFF>=0,0,DIFF,2,0),COLORRED;      DIFF 实心柱: ≥0 红   ← 等于 0 算红
 *   STICKLINE(DEA>=0,0,DEA,2,-1),COLOR0000CC;    DEA 空心柱: ≥0 深红  ← 等于 0 算深红
 *   STICKLINE(DEA< 0,0,DEA,2,-1),COLORGREEN;     DEA 空心柱: <0 绿
 *   DRAWICON(CROSS(DIFF,DEA),柱2,1);             金叉图标 1
 *   DRAWICON(CROSS(DEA,DIFF),DEA*1.1,2);         死叉图标 2
 *   STICKLINE(...,0,DEA/4,2,0),COLORYELLOW;      黄柱(实心)
 *
 * [R417] 下面几条**全部是对着用户发来的通达信截图逐像素量出来的**, 不是按文档推的
 * (R415 按文档推, 柱宽和空心柱都推错了):
 *
 * - **柱宽 66%**: 截图里 K 线间距 15.1px, 实心柱 10px。通达信手册说「宽度 10 为
 *   标准间距」, 照字面 2 就是 20% —— 与实际显示不符, 以实测为准。
 * - **空心柱会盖住底下的东西**: 通达信画空心柱是先用底色把整块填掉、再描边。
 *   DIFF 实心柱先画、DEA 空心柱后画, 所以 DIFF 只露出**超出 DEA 的那一截**;
 *   DIFF 没 DEA 长时整根被盖住, 只看得见 DEA 的框。截图里「上面一截实心、下面
 *   一个空框」就是这么来的。这里不去猜页面底色是什么, 而是直接只画露出来的那一截
 *   (`diffExposed`) —— 结果与"先画再盖"逐像素相同。
 * - **空心柱的边框是点线**(1 点 1 空), 不是实线。
 * - **图标**: 带箭杆的箭头, 约 13×18px, **图标顶端对准数值**、水平居中于那根 K 线;
 *   1 号红色朝上, 2 号绿色朝下。2 号的绿比柱子的绿暗一档(截图三个死叉箭头都在
 *   #00DC00 附近, 而绿柱是 #00FF00) —— 那是通达信图标自带的颜色。
 * - **画的先后 = 原文语句的先后**: DIFF → DEA → 图标 → 黄柱, 后画的盖在上面。
 *
 * 颜色取 `lib/theme.ts` 的 `QUANT_MACD_COLORS`: 逐字照抄通达信, 亮暗两套主题
 * 同一份 —— 用户: 「颜色和柱子类型都得一样」。
 *
 * **只画原文画的, 不多一样也不少一样**: 没有悬停提示, 原文没有的一律不加。
 */
import { QUANT_MACD_COLORS } from '@/lib/theme'

export interface QuantMacdAligned {
  diff: (number | null)[]
  dea: (number | null)[]
  yellow: (number | null)[]
  gold_icon: (number | null)[]
  dead_icon: (number | null)[]
}

/**
 * 按日期把后端那份(约 400 根)对到图上的 x 轴。图上有、后端没有的那几根
 * (主图更早的日期、二型开着时右边的「未来」空槽)一律 null —— 不画, 不补。
 */
export function alignQuantMacd(
  dates: string[],
  q: { dates: string[] } & QuantMacdAligned | undefined,
): QuantMacdAligned {
  const idx = new Map((q?.dates ?? []).map((d, i) => [d, i]))
  const pick = (arr: (number | null)[] | undefined) => dates.map(d => {
    const i = idx.get(d)
    return i == null || !arr ? null : (arr[i] ?? null)
  })
  return {
    diff: pick(q?.diff), dea: pick(q?.dea), yellow: pick(q?.yellow),
    gold_icon: pick(q?.gold_icon), dead_icon: pick(q?.dead_icon),
  }
}

/** 柱宽占 K 线间距的比例 —— 实测: 10px / 15.1px。三种柱子同宽(原文宽度都是 2)。 */
export const STICK_RATIO = 0.66
export const STICK_WIDTH = `${STICK_RATIO * 100}%`

/** 空心柱的边框: 1 点 1 空的点线(实测, 见 DEA 那一条的说明)。 */
export const HOLLOW_DASH = [1, 1]

/** 图标外框(px), 实测。 */
export const ICON_W = 13
export const ICON_H = 18
/** 1 号图标: 红色朝上箭头(箭头在上、箭杆在下)。坐标系 13×18。 */
export const ICON_UP = 'path://M6.5,0 L13,9 L7.5,9 L7.5,18 L5.5,18 L5.5,9 L0,9 Z'
/** 2 号图标: 绿色朝下箭头(箭杆在上、箭头在下)。 */
export const ICON_DOWN = 'path://M5.5,0 L7.5,0 L7.5,9 L13,9 L6.5,18 L0,9 L5.5,9 Z'

/**
 * DIFF 实心柱被 DEA 空心柱盖住之后, 还露在外面的那一截 `[起, 止]`; 全被盖住为 null。
 *
 * - DEA 与 DIFF **同在 0 的一侧**且 DIFF 更长: 露出 DEA→DIFF 那一截;
 * - 同侧但 DIFF 不比 DEA 长: 整根被盖住;
 * - **分在 0 的两侧**(或 DEA 为 0): 空心柱盖的是另一侧, DIFF 整根都露着。
 */
export function diffExposed(diff: number | null, dea: number | null): [number, number] | null {
  if (diff == null) return null
  if (dea == null || dea === 0 || (diff >= 0) !== (dea >= 0)) return [0, diff]
  return Math.abs(diff) > Math.abs(dea) ? [dea, diff] : null
}

const NONE = '-' // ECharts 里"这一根不画"

/** DIFF 那一截的画法: 一个实心矩形, 宽度与别的柱子同一个比例。颜色按 DIFF 本身的正负。 */
export function renderDiffRect(
  _params: unknown,
  api: {
    value: (d: number) => number
    coord: (v: [number, number]) => number[]
    size: (v: [number, number]) => number[] | number
  },
) {
  const i = api.value(0), lo = api.value(1), hi = api.value(2)
  const a = api.coord([i, lo]), b = api.coord([i, hi])
  const band = api.size([1, 0])
  const w = (Array.isArray(band) ? band[0] : band) * STICK_RATIO
  return {
    type: 'rect',
    shape: { x: a[0] - w / 2, y: Math.min(a[1], b[1]), width: w, height: Math.abs(a[1] - b[1]) },
    style: { fill: hi >= 0 ? QUANT_MACD_COLORS.red : QUANT_MACD_COLORS.green },
  }
}

/**
 * 返回五个系列, 顺序即画的先后(= 原文语句的先后)。
 * `axis` 是这张副图所在的坐标轴下标。
 */
export function quantMacdSeries(
  a: QuantMacdAligned,
  axis: { xAxisIndex: number; yAxisIndex: number },
): Record<string, unknown>[] {
  const C = QUANT_MACD_COLORS
  const bar = {
    type: 'bar', ...axis, animation: false, silent: true,
    barWidth: STICK_WIDTH,
    // 柱子叠在同一个位置 —— 原文几条 STICKLINE 画的是同一根 K 线的位置
    barGap: '-100%',
  }
  const icon = {
    type: 'scatter', ...axis, animation: false, silent: true, z: 4,
    symbolSize: [ICON_W, ICON_H],
    // 图标顶端对准数值: 往下挪半个图标高
    symbolOffset: [0, ICON_H / 2],
  }
  const diffData: [number, number, number][] = []
  a.diff.forEach((v, i) => {
    const seg = diffExposed(v, a.dea[i])
    if (seg) diffData.push([i, seg[0], seg[1]])
  })
  return [
    {
      type: 'custom', ...axis, name: 'DIFF', z: 2, animation: false, silent: true,
      clip: true, encode: { x: 0, y: [1, 2] },
      renderItem: renderDiffRect,
      data: diffData,
    },
    {
      ...bar, name: 'DEA', z: 3,
      data: a.dea.map(v => v == null ? NONE : {
        value: v,
        // 空心: 只描边。框里面本来就没画 DIFF(见 `diffExposed`), 看到的就是底色。
        // 边框是**点线**(1 点 1 空): 截图里空心框的两条竖边亮度按 3 像素一个周期
        // 起伏、且两条边同相 —— 实线怎么缩放都出不来这种纵向起伏, 正是 1 点 1 空
        // 的点线被截图缩到 2/3 之后的样子。
        itemStyle: {
          color: 'transparent', borderColor: v >= 0 ? C.darkRed : C.green,
          borderWidth: 1, borderType: HOLLOW_DASH,
        },
      }),
    },
    {
      ...icon, name: '金叉', symbol: ICON_UP,
      itemStyle: { color: C.red },
      data: a.gold_icon.map(v => v == null ? NONE : v),
    },
    {
      ...icon, name: '死叉', symbol: ICON_DOWN,
      itemStyle: { color: C.icon2 },
      data: a.dead_icon.map(v => v == null ? NONE : v),
    },
    {
      ...bar, name: '共振', z: 5,
      itemStyle: { color: C.yellow },
      data: a.yellow.map(v => v == null ? NONE : v),
    },
  ]
}
