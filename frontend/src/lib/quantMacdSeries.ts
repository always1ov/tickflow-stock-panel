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
 * 照原文的几件事:
 *
 * - **STICKLINE 的第 5 个参数**: 0 = 实心, 非 0 = 空心 —— DIFF 实心、DEA 空心、
 *   黄柱实心。
 * - **宽度都是 2**, 所以三种柱子**同宽、叠在同一个位置**。通达信的宽度以 10 为
 *   一个 K 线间距, 2 就是间距的 20%。
 * - **画的先后 = 原文语句的先后**: DIFF → DEA → 图标 → 黄柱, 后画的盖在上面。
 *   黄柱是最后一条语句, 所以它盖在 DIFF 实心柱的下四分之一上 —— 这也是原文的样子。
 * - **图标**: 通达信图标 1 是红色向上箭头、2 是绿色向下箭头。
 *
 * 颜色取 `lib/theme.ts` 的 `QUANT_MACD_COLORS`: 逐字照抄通达信, 亮暗两套主题
 * 同一份 —— 用户: 「颜色和柱子类型都得一样」。
 *
 * **只画原文画的, 不多一样也不少一样**: 没有 0 轴线、没有背景横线、没有悬停提示,
 * 原文没有的一律不加。
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

/** 通达信 STICKLINE 宽度 2 / 标准间距 10。 */
export const STICK_WIDTH = '20%'

const NONE = '-' // ECharts 里"这一根不画"

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
    // 三种柱子叠在同一个位置 —— 原文三条 STICKLINE 画的是同一根 K 线的位置
    barGap: '-100%',
  }
  return [
    {
      ...bar, name: 'DIFF', z: 2,
      data: a.diff.map(v => v == null ? NONE : {
        value: v,
        itemStyle: { color: v >= 0 ? C.red : C.green },
      }),
    },
    {
      ...bar, name: 'DEA', z: 3,
      data: a.dea.map(v => v == null ? NONE : {
        value: v,
        // 空心: 不填充, 只描边
        itemStyle: { color: 'transparent', borderColor: v >= 0 ? C.darkRed : C.green, borderWidth: 1 },
      }),
    },
    {
      type: 'scatter', ...axis, name: '金叉', animation: false, silent: true, z: 4,
      symbol: 'arrow', symbolSize: 9,
      itemStyle: { color: C.red },
      data: a.gold_icon.map(v => v == null ? NONE : v),
    },
    {
      type: 'scatter', ...axis, name: '死叉', animation: false, silent: true, z: 4,
      symbol: 'arrow', symbolSize: 9, symbolRotate: 180,
      itemStyle: { color: C.green },
      data: a.dead_icon.map(v => v == null ? NONE : v),
    },
    {
      ...bar, name: '共振', z: 5,
      itemStyle: { color: C.yellow },
      data: a.yellow.map(v => v == null ? NONE : v),
    },
  ]
}
