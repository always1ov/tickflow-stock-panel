/**
 * [R419] 关键价位图的纵向版面 —— 主图高度与 R415 之前**逐像素相同**, 量化MACD 副图
 * 在它之外另加, 整张图因此变长, 弹窗内容往下滚着看。
 *
 * 用户: 「不能让主图变矮」「副图调高行不行」「可以搞整个弹窗内容滚动往下看」。
 *
 * 为什么副图要高: 金叉 / 死叉图标按原文画在 DEA 与 DEA×1.1 处、从那一点往下挂,
 * 图标是固定像素; DEA 的 10% 换成像素要看副图多高 —— 副图矮, 图标就显得深深插进
 * 柱子里(通达信里也会插进去, 只是它那张副图高, 插得浅)。
 *
 * `height` 仍是调用方原来给的那个数(个股预览 520 / 最大化 720 / 窄屏 320),
 * **意思变了**: 以前是整张图的高, 现在只用来定主图 —— 按 R415 之前的算法
 * (减去原来成交量那一套 156px), 所以主图与换成交量之前一模一样。
 *
 *   [16 顶部] [主图] [14 间距] [副图] [26 日期刻度] [22 缩放条] [8 底部]
 *
 * [R486] 主图与量化MACD 之间再插一张「趋势量化」, 与量化MACD 同高。用户: 「在量化macd
 * 上方加个副图」。主图高度仍一像素不动, 多出来的照旧让整张图变长、弹窗往下滚:
 *
 *   [16] [主图] [14] [趋势量化] [14] [量化MACD] [26 日期刻度] [22 缩放条] [8]
 */
export const PAD_TOP = 16
export const GAP_MAIN_SUB = 14      // 主图 ↔ 副图(两边纵轴刻度不上下相撞)
export const GAP_SUB_SLIDER = 26    // 副图 ↔ 缩放条: 日期刻度在这一段里
export const SLIDER_H = 22
export const PAD_BOTTOM = 8

/** R415 之前主图以外占掉的高度: 16 顶 + 8 间距 + 90 成交量 + 12 间距 + 22 缩放条 + 8 底。 */
export const LEGACY_NON_MAIN = 156

/**
 * 副图高度: 主图的 40%, 限 130~200。
 *
 * [R422] R419 首版给的是 55%、限 180~300, 用户: 「副图调得太高了, 你要合理调啊」——
 * 最大化时副图 300px 快赶上主图一半, 看盘的重心被拉走了。40% 让副图明显比
 * R418 的 90~130 高(图标不再深插进柱子), 又始终比主图矮一大截。
 */
export function subPaneHeight(mainH: number): number {
  return Math.round(Math.min(200, Math.max(130, mainH * 0.4)))
}

export interface LevelsChartLayout {
  mainH: number
  /** [R486] 趋势量化副图(主图正下方) */
  trendH: number
  trendTop: number
  /** 量化MACD 副图(最下面那张) */
  subH: number
  subTop: number
  /** 整张图(画布)的高度 —— 比调用方给的 `height` 高, 多出来的靠弹窗滚动 */
  total: number
}

export function levelsChartLayout(height: number): LevelsChartLayout {
  const mainH = height - LEGACY_NON_MAIN
  const subH = subPaneHeight(mainH)
  const trendH = subH
  const trendTop = PAD_TOP + mainH + GAP_MAIN_SUB
  const subTop = trendTop + trendH + GAP_MAIN_SUB
  const total = subTop + subH + GAP_SUB_SLIDER + SLIDER_H + PAD_BOTTOM
  return { mainH, trendH, trendTop, subH, subTop, total }
}
