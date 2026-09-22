/**
 * [R420] 斐波那契二型的「未来」区 —— 位移均线露到最后一根之外的那几格。
 *
 * 用户: 「斐波那契二型的未来区域是灰色, k线也是灰色看不清了, 想办法解决」。
 * R413 的画法有两处毛病:
 *
 * 1. **只盖住了 3 格里的 2 格**: 用 markArea 从「未来1」画到「未来3」, 而类目轴上
 *    这两个值落在格子**中间** —— 第一格左半、第三格右半都没盖到。
 * 2. **太淡且一片灰**: 暗色下底色只有 5% 白, 标签是灰字, 穿过它的现价虚线也是灰,
 *    暗色主题的二型均线又是浅粉 —— 整块混成一片灰。
 *
 * 现在逐格画满(每格一个矩形, 宽 = 一个 K 线间距, 拼起来正好铺满), 底色加深一档,
 * 在「今天」与「未来」的交界画一条竖虚线, 标签用主文字色; 均线在未来这段另加粗
 * (见 AnalysisKChart)。底色**仍是中性色** —— 「还没发生」不该带涨跌或任何价位组
 * 的颜色含义。
 */
import type { Theme } from '@/lib/theme'

export const FUTURE_ZONE: Record<Theme, { fill: string; divider: string }> = {
  dark:  { fill: 'rgba(255,255,255,0.10)', divider: 'rgba(255,255,255,0.55)' },
  light: { fill: 'rgba(34,39,56,0.08)',    divider: 'rgba(34,39,56,0.45)' },
}

// 只写「未来」: 默认缩放下 3 格一共才二十来像素, R413 的「未来(均线已知)」
// 放不下(出图被格子右沿切掉); 分两行也还是切。"均线已知"由那段加粗的均线自己说明。
export const FUTURE_LABEL = '未来'

interface SlotApi {
  value: (d: number) => number
  coord: (v: [number, number]) => number[]
  size: (v: [number, number]) => number[] | number
}
interface SlotParams { dataIndex: number; coordSys: { y: number; height: number } }

/**
 * 每个未来格子的画法。第 0 格左沿画交界竖虚线, 中间那格顶上写标签。
 * `count` 是未来格子数, `labelColor` 用主文字色。
 */
export function futureSlotRenderer(theme: Theme, count: number, labelColor: string) {
  const Z = FUTURE_ZONE[theme]
  const mid = Math.floor(count / 2)
  return (params: SlotParams, api: SlotApi) => {
    const x = api.coord([api.value(0), 0])[0]
    const band = api.size([1, 0])
    const w = Array.isArray(band) ? band[0] : band
    const { y, height } = params.coordSys
    const children: Record<string, unknown>[] = [
      { type: 'rect', shape: { x: x - w / 2, y, width: w, height }, style: { fill: Z.fill } },
    ]
    if (params.dataIndex === 0) {
      children.push({
        type: 'line', shape: { x1: x - w / 2, y1: y, x2: x - w / 2, y2: y + height },
        style: { stroke: Z.divider, lineWidth: 1, lineDash: [4, 3] },
      })
    }
    if (params.dataIndex === mid) {
      children.push({
        type: 'text', x, y: y + 4,
        style: { text: FUTURE_LABEL, fill: labelColor, fontSize: 9, lineHeight: 11,
                 align: 'center', verticalAlign: 'top' },
      })
    }
    return { type: 'group', children }
  }
}
