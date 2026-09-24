/**
 * [R485] 庄现 —— 在量化MACD 副图上画一个狗头。**画法的唯一产地, 冻结。**
 *
 * 用户: 「现在想办法移植到量化macd里面, 当作辅助指标不在动了, 就算我以后微调量化macd
 * 也不动这些了」;「庄现用狗头 doge 这样更有含义」。
 *
 * 所以这里**不 import `quantMacdSeries`、不读 DIFF / DEA**: 狗头贴着副图底边画在
 * 那一天的正下方, 位置只看「哪一天」, 与量化MACD 的数值无关 —— 那边以后怎么调,
 * 狗头的位置和出现的日子都不跟着变。算法在后端 `indicators/zhuang_xian.py`。
 *
 * 只是标记: 不可点、没有悬停说明(界面上不讲算法), 不进任何判定。
 * 颜色是柴犬的黄褐 / 米白 / 深褐 —— 全站禁粉(AGENTS.md 第 15 条), 这里一样不沾。
 */

/** 狗头边长(px) */
export const DOGE_SIZE = 18
/** 离副图底边留的空隙(px) */
const BOTTOM_GAP = 2

/** 柴犬头: 两只耳朵、黄褐的脸、米白的嘴套和眉斑、眼睛、鼻子、一道嘴。 */
export const DOGE_SVG =
  "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'>" +
  "<path d='M4 2 L13 10 L5 14 Z' fill='#B8732E'/>" +
  "<path d='M28 2 L19 10 L27 14 Z' fill='#B8732E'/>" +
  "<path d='M6 5 L11 10 L7 12 Z' fill='#7A4A1C'/>" +
  "<path d='M26 5 L21 10 L25 12 Z' fill='#7A4A1C'/>" +
  "<ellipse cx='16' cy='17.5' rx='12.5' ry='11.5' fill='#D99A4E'/>" +
  "<ellipse cx='16' cy='23' rx='8.5' ry='6.5' fill='#F5E6C8'/>" +
  "<ellipse cx='10.5' cy='12.6' rx='2.3' ry='1.3' fill='#F5E6C8'/>" +
  "<ellipse cx='21.5' cy='12.6' rx='2.3' ry='1.3' fill='#F5E6C8'/>" +
  "<circle cx='11.5' cy='16' r='1.7' fill='#2B1B0E'/>" +
  "<circle cx='21.5' cy='16' r='1.7' fill='#2B1B0E'/>" +
  "<ellipse cx='16' cy='20.4' rx='2.5' ry='1.8' fill='#2B1B0E'/>" +
  "<path d='M13 24 Q16 26.5 19 24' stroke='#2B1B0E' stroke-width='1.2' fill='none' stroke-linecap='round'/>" +
  '</svg>'

export const DOGE_IMAGE = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(DOGE_SVG)}`

/**
 * 按日期把后端那份对到图上的 x 轴: 返回出庄现那几天在 `dates` 里的下标。
 * 图上有、后端没有的日子(更早的历史、二型的「未来」空槽)一律不画。
 */
export function zhuangXianIndexes(
  dates: string[],
  q: { dates: string[]; zhuang?: (number | null)[] } | undefined,
): number[] {
  if (!q?.zhuang) return []
  const on = new Set(q.dates.filter((_, i) => q.zhuang![i] === 1))
  const out: number[] = []
  dates.forEach((d, i) => { if (on.has(d)) out.push(i) })
  return out
}

/** 狗头系列: 每个出庄现的日子一个, 贴着所在副图的底边、水平居中于那一天。 */
export function zhuangXianSeries(
  indexes: number[],
  axis: { xAxisIndex: number; yAxisIndex: number },
): Record<string, unknown> {
  return {
    type: 'custom', ...axis, name: '庄现', z: 6, animation: false, silent: true,
    clip: false, encode: { x: 0 },
    renderItem: (
      params: { coordSys: { y: number; height: number } },
      api: { value: (d: number) => number; coord: (v: [number, number]) => number[] },
    ) => {
      const x = api.coord([api.value(0), 0])[0]
      const { y, height } = params.coordSys
      return {
        type: 'image',
        style: {
          image: DOGE_IMAGE,
          x: x - DOGE_SIZE / 2, y: y + height - DOGE_SIZE - BOTTOM_GAP,
          width: DOGE_SIZE, height: DOGE_SIZE,
        },
      }
    },
    data: indexes.map(i => [i]),
  }
}
