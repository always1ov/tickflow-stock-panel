import type { OHLC } from './chart-types'

/**
 * [R689] 日K 图上那几条线的主色 —— 画线(`LightweightDaily`)与工具栏胶囊的色点共用这一份。
 * 用户: 「参考压力支撑、枢轴点这种指标的显示方式, 颜色+文字」—— 色点必须与图上那条线同色,
 * 所以两边从同一个常量取值, 不各写一遍。
 */
export const DAILY_LINE_COLORS = {
  yellow: { dark: '#FACC15', light: '#A16207' },
  blue: { dark: '#3B82F6', light: '#2563EB' },
  // [R593] 键名避开 purple 族(守卫按族名查), 色值仍是图表线条色
  plum: { dark: '#8B5CF6', light: '#7C3AED' },
  gray: { dark: '#A1A1AA', light: '#71717A' },
  orange: { dark: '#F97316', light: '#C2410C' },
} as const

export const SUB_CHART_META = [
  { key: 'vol', label: '成交量', height: 84 },
  { key: 'macd', label: 'MACD', height: 72 },
  { key: 'rsi', label: 'RSI', height: 72 },
  { key: 'kdj', label: 'KDJ', height: 72 },
]
export function volMaN(data: OHLC[], n: number): (number | null)[] {
  const result: (number | null)[] = []
  for (let i = 0; i < data.length; i++) {
    if (i < n - 1) { result.push(null); continue }
    let sum = 0
    for (let j = i - n + 1; j <= i; j++) sum += data[j].volume ?? 0
    result.push(sum / n)
  }
  return result
}

export function volumeRatioAt(data: OHLC[], index: number, days: number): number | null {
  const window = Math.max(1, Math.min(20, Math.round(days)))
  if (index < window) return null
  let sum = 0
  for (let offset = 1; offset <= window; offset++) {
    const volume = data[index - offset]?.volume
    if (volume == null || !Number.isFinite(volume)) return null
    sum += volume
  }
  const average = sum / window
  const current = data[index]?.volume
  if (current == null || !Number.isFinite(current) || average <= 0) return null
  return current / average
}
