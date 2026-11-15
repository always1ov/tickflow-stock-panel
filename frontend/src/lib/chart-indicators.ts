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
  // [R714] 用户: 「新增一个副图指标, 再完美复刻」—— 通达信「主力COME」, 只有柱和字, 见下面计算。
  { key: 'inst', label: '主力COME', height: 96 },
]

/** [R714] 通达信 SMA(X,N,M): Y=(M·X+(N-M)·Y')/N, 首值取 X —— 不是简单均线, 不能拿 rolling mean 顶替。 */
export function tdxSma(values: number[], n: number, m: number): number[] {
  const out: number[] = []
  let prev: number | null = null
  for (const value of values) {
    prev = prev == null ? value : (m * value + (n - m) * prev) / n
    out.push(prev)
  }
  return out
}

/** [R714] 通达信 EMA(X,N): α=2/(N+1), 首值取 X。 */
export function tdxEma(values: number[], n: number): number[] {
  const alpha = 2 / (n + 1)
  let prev: number | null = null
  return values.map(value => {
    prev = prev == null ? value : alpha * value + (1 - alpha) * prev
    return prev
  })
}

export interface InstPoint {
  /** 机构线 = EMA((加权价-34日最低)/(34日最高-34日最低)*100, 8) */
  inst: number
  /** 机构趋势 = EMA(机构线, 13) */
  trend: number
  /** 主力 = EMA(55日低位,3)<=13 AND 指标变化率>13 */
  mainForce: boolean
  /** 主力信号 = 主力 AND FILTER(主力, 10) —— 10 天内只报一次 */
  mainSignal: boolean
}

/**
 * [R714] 用户给的通达信公式, 逐行照搬:
 *
 *   机构线:=EMA((加权价-LLV(L,34))/(HHV(H,34)-LLV(L,34))*100,8);
 *   机构趋势:=EMA(机构线,13);
 *   五十五日低位:=3*SMA((C-LLV(L,55))/(HHV(H,55)-LLV(L,55))*100,5,1)
 *                -2*SMA(SMA((C-LLV(L,55))/(HHV(H,55)-LLV(L,55))*100,5,1),3,1);
 *   指标变化率:=(EMA(五十五日低位,3)-REF(EMA(五十五日低位,3),1))/REF(EMA(五十五日低位,3),1)*100;
 *   主力:=EMA(五十五日低位,3)<=13 AND 指标变化率>13;
 *   主力信号:=主力 AND FILTER(主力,10);
 *
 * 公式里 `:=` 只赋值不画线 —— 机构线 / 机构趋势 / 五十五日低位在通达信里**不显示**,
 * 能看到的只有 STICKLINE 柱体和 DRAWTEXT 的「主力COME」, 所以这里只回传算好的数值,
 * 画什么由调用方按公式里的 STICKLINE / DRAWTEXT 决定(见 LightweightDaily 的 paneDecor)。
 * HHV/LLV 在数据不足 N 根时按已有根数计算, 除零按通达信的 0 处理。
 */
export function computeInstitutionSeries(rows: OHLC[]): InstPoint[] {
  const highMax = (window: number, i: number) => {
    let max = -Infinity
    for (let j = Math.max(0, i - window + 1); j <= i; j++) max = Math.max(max, rows[j].high)
    return max
  }
  const lowMin = (window: number, i: number) => {
    let min = Infinity
    for (let j = Math.max(0, i - window + 1); j <= i; j++) min = Math.min(min, rows[j].low)
    return min
  }
  const pct = (num: number, den: number) => den > 0 ? num / den * 100 : 0
  const weighted = rows.map(r => (2 * r.close + r.high + r.low) / 4)
  const instRaw = rows.map((_, i) => {
    const low = lowMin(34, i), high = highMax(34, i)
    return pct(weighted[i] - low, high - low)
  })
  const rsv55 = rows.map((r, i) => {
    const low = lowMin(55, i), high = highMax(55, i)
    return pct(r.close - low, high - low)
  })
  const inst = tdxEma(instRaw, 8)
  const trend = tdxEma(inst, 13)
  const sma5 = tdxSma(rsv55, 5, 1)
  const sma3 = tdxSma(sma5, 3, 1)
  const low55 = sma5.map((value, i) => 3 * value - 2 * sma3[i])
  const ema3 = tdxEma(low55, 3)
  let lastSignal = -Infinity
  return rows.map((_, i) => {
    const prev = i > 0 ? ema3[i - 1] : null
    const rate = prev != null && prev > 0 ? (ema3[i] - prev) / prev * 100 : 0
    const mainForce = ema3[i] <= 13 && rate > 13
    // FILTER(主力,10): 成立后 10 个周期内不再重复报
    const mainSignal = mainForce && i - lastSignal >= 10
    if (mainSignal) lastSignal = i
    return { inst: inst[i], trend: trend[i], mainForce, mainSignal }
  })
}
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
