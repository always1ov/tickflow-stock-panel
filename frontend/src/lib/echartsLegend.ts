/**
 * [R401] 图例要占几行 —— **ECharts 不会告诉 `grid`, 只能自己算。**
 *
 * ## 这是在修什么
 *
 * 用户手机截图上, 环境综合分趋势那张图的图例是这样的:
 *
 *     涨停  综合分  涨停数  赚钱  投机   ← 「涨停」是左轴名, 和图例压在一起
 *     180   抗跌   趋势    综合分       ← 第二行图例又压住了右轴名和刻度
 *
 * 根因不是"字太多", 是**图例换了行而 `grid.top` 没跟着变**: 六个图例项在
 * 手机宽度上排不下, ECharts 自动折成两行, 而 `grid.top` 写死 36 —— 只够一行。
 * 第二行就画到了绘图区里, 和轴名、刻度叠在一起。桌面上排得下一行, 所以
 * **这个毛病只在窄屏出现**, 在开发机上一眼看不到。
 *
 * ## 为什么是"算"而不是"量"
 *
 * option 是在 `useMemo` 里算的, 那时图表容器还没布局, 量不到真实宽度; 等量到
 * 了再 `setOption` 一次又会多一次重绘。而图例的排布规则是确定的, 算得出来。
 *
 * ## ECharts 的排布规则(v5, horizontal)
 *
 * 一个图例项的宽 = `itemWidth` + 5(图标与文字之间) + 文字宽; 项与项之间再加
 * `itemGap`。放不下就换行。中文在 `fontSize` 下基本是**一个字一个字宽**,
 * 拉丁字母约六成 —— 这里按最坏情况(全中文)算, 宁可高估。
 */

/** 单个图例项的宽度(含图标与图标→文字的间隙, 不含项间距)。 */
export function legendItemWidth(label: string, fontSize: number, itemWidth: number): number {
  let text = 0
  for (const ch of label) {
    // 中文/全角按一个字宽; 其余(数字、字母、`+`)按六成
    text += /[\u3000-\u9fff\uff00-\uffef]/.test(ch) ? fontSize : fontSize * 0.6
  }
  return itemWidth + 5 + text
}

/**
 * 这组图例在 `width` 像素里会排成几行。
 *
 * `width` 传**绘图容器的宽度**(图例横向铺满容器, 不受 `grid.left/right` 限制)。
 */
export function legendRows(
  labels: string[],
  width: number,
  { fontSize = 10, itemWidth = 25, itemGap = 10 }: {
    fontSize?: number; itemWidth?: number; itemGap?: number
  } = {},
): number {
  if (labels.length === 0) return 0
  let rows = 1
  let used = 0
  for (const label of labels) {
    const w = legendItemWidth(label, fontSize, itemWidth)
    // 第一项不加项间距; 之后每项前面都有一个 itemGap
    const need = used === 0 ? w : itemGap + w
    if (used > 0 && used + need > width) {
      rows++
      used = w
    } else {
      used += need
    }
  }
  return rows
}

/**
 * 紧凑图例的一套取值。**默认值(25/10)是为桌面图表定的**, 在手机上会把
 * 六个项挤到第二行去; 收到 10/6 之后同样六项在 327px(375 手机的图表可用宽)
 * 里排得下一行。图标从 25px 收到 10px 只是把那一小段色条变短, 读图例靠的是
 * 颜色和文字, 不是色条有多长。
 */
export const COMPACT_LEGEND = { fontSize: 10, itemWidth: 10, itemHeight: 8, itemGap: 6 } as const

/**
 * 一行紧凑图例时 `grid.top` 要留多少。
 *
 * **这个数是量出来的, 不是算出来的** —— 因为要让开的不止图例, 还有**轴名**:
 * `yAxis.name` 画在 `grid.top - nameGap` 处, `grid.top` 太小它就被顶进图例那
 * 一行里。用户截图上「涨停」压着「综合分」、「投机」压着右边的「综合分」,
 * 就是这么来的。
 *
 * 在 327px(375 手机上这张图的可用宽)逐档量过, 同一套紧凑图例 + 默认 nameGap:
 *
 *     grid.top=36  →  三处重叠(涨停×综合分 / 抗跌×综合分 / 综合分×趋势)
 *     grid.top=44  →  零重叠
 *     grid.top≥48  →  零重叠(只是白留更多)
 *
 * 取 44: 刚好够, 再大就是白扔绘图高度。宽屏上图例本来就排得下一行, 这个值
 * 同样成立 —— 所以两档宽度用同一个数, 不做响应式分支。
 */
export const LEGEND_GRID_TOP = 44
