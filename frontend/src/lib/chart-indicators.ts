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
  // [R760] 只给图表线条用(MA60 / DEA / RSI24 / KDJ-J 与它们图例上的同色小字、工具栏色点);
  // 界面元素(边框、底色、按钮)不许借用这个值 —— 《前端没有紫》守卫按文件放行这两个 hex,
  // 拿去做界面就绕过了那道红线。
  plum: { dark: '#8B5CF6', light: '#7C3AED' },
  gray: { dark: '#A1A1AA', light: '#71717A' },
  orange: { dark: '#F97316', light: '#C2410C' },
} as const

export const SUB_CHART_META = [
  // [R752] 用户: 「副图指标成交量重新命名」「一看就能看懂成交量叠加了什么」——
  // R723 之后这只副图里除了量柱, 还叠了「ATR原始」那五条线(ATR20 / BASIS / ±2σ 通道 / REFMID),
  // 只叫「成交量」看不出叠加物。胶囊只有 65px 宽(R669), 再长的名字会被挤出按钮, 所以取「量能 ATR」。
  { key: 'vol', label: '量能 ATR', height: 84 },
  { key: 'macd', label: 'MACD', height: 72 },
  { key: 'rsi', label: 'RSI', height: 72 },
  { key: 'kdj', label: 'KDJ', height: 72 },
  // [R753] 用户: 「用这个指标替换原来的副图指标成交量, 完美复刻」—— 通达信「能量惯性」。
  // 日K 的这只副图原来画量柱(R723 之后还叠了 ATR 五线), 现在整只换成能量惯性;
  // `vol` 仍保留给指数页(那边还在用 `['vol', 'macd']`)。
  // [R754] 用户: 「量能惯性命名改成量能惯性+ATR趋势」—— 五条 ATR 线叠在这只副图里,
  // 名字得带出来, 否则看图形的人不知道副图上那几条线是什么。
  { key: 'energy', label: '量能惯性+ATR趋势', height: 96 },
  // [R714] 用户: 「新增一个副图指标, 再完美复刻」—— 通达信「主力COME」, 只有柱和字, 见下面计算。
  { key: 'inst', label: '主力COME', height: 96 },
  // [R723] 用户: 「刚刚的『ATR原始』叠加到成交量上去」—— 它不再单独占一只副图, 五条线
  // 画进成交量那只 pane(见 LightweightDaily), 所以这里下掉它的注册项与入口胶囊。
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
/**
 * [R753] 通达信「能量惯性」的 STICKLINE 分段 —— 每一段是 (惯性 - 惯性×近端, 惯性 - 惯性×远端),
 * 正负两支各五段, 远端到 0.95、近端贴着 0.05, 段间留 0.05 的缝。公式顺序: 先近后远。
 */
export const ENERGY_BANDS = [
  [0.05, 0.15],
  [0.2, 0.35],
  [0.4, 0.55],
  [0.6, 0.75],
  [0.8, 0.95],
] as const

/**
 * [R753] 公式里的 COLOR 常量 —— 通达信一律按 **BBGGRR** 排, 与本项目 `QUANT_MACD_COLORS`
 * (R415)、`INST_COLORS` (R714) 同一约定:
 *
 *   COLOR0000CC → #CC0000 深红    COLOR0066FF → #FF6600   COLOR0099FF → #FF9900
 *   COLOR00CCFF → #FFCC00         COLOR00FFFF → #FFFF00 黄
 *   COLORFF3300 → #0033FF 蓝      COLORFF6600 → #0066FF   COLORFF9900 → #0099FF
 *   COLORFFCC00 → #00CCFF         COLORFFFF00 → #00FFFF 青
 *
 * 所以: 惯性 ≥0 是「红→黄」(贴 0 轴的是黄), 惯性 <0 是「蓝→青」(贴 0 轴的是青)。
 * 用户: 「买卖量能的颜色搞反了, 我通达信里面显示上涨是黄色」—— 首版按 RGB 直读,
 * 正负两支正好上下颠倒, 这里是修正后的取色。
 *
 * 暗色用公式换算后的原色; 亮色换成同色相深一档(与 `ATR_BAND_COLORS` 同一做法),
 * 否则 #FFFF00 / #00FFFF 落在白底上等于没画。
 */
export const ENERGY_COLORS = {
  positive: {
    dark: ['#CC0000', '#FF6600', '#FF9900', '#FFCC00', '#FFFF00'],
    light: ['#B91C1C', '#C2410C', '#B45309', '#A16207', '#854D0E'],
  },
  negative: {
    dark: ['#0033FF', '#0066FF', '#0099FF', '#00CCFF', '#00FFFF'],
    light: ['#1E3A8A', '#1D4ED8', '#0369A1', '#0891B2', '#0E7490'],
  },
  /** DRAWICON(...,0,1) —— 1 号是红色向上箭头(与量化MACD 实测同一枚) */
  icon: { dark: '#EF4444', light: '#DC2626' },
  /**
   * `能量惯性:` 用的是冒号, 通达信会把它当输出线画出来(公式没写颜色)。
   * 通达信默认输出线是白色; 亮色主题换成深灰, 避免白线消失。
   */
  line: { dark: '#FFFFFF', light: '#334155' },
} as const

export interface EnergyPoint {
  /** 能量 := SQRT(VOL) * ((CLOSE-(HIGH+LOW)/2) / ((HIGH+LOW)/2)) */
  energy: number
  /** 平滑能量 := EMA(能量,16) */
  smooth: number
  /** 能量惯性 := EMA(平滑能量,16) */
  inertia: number
  /** DRAWICON(能量惯性>0 AND REF(能量惯性,1)<0,0,1): 从负翻正那一根 */
  crossUp: boolean
}

/**
 * [R753] 通达信「能量惯性」, 逐行照搬:
 *
 *   能量:=SQRT(VOL)*(((CLOSE-(HIGH+LOW)/2))/((HIGH+LOW)/2));
 *   平滑能量:=EMA(能量,16);
 *   能量惯性:EMA(平滑能量,16);
 *   DRAWICON(能量惯性>0 AND REF(能量惯性,1)<0,0,1);
 *   STICKLINE(能量惯性>=0, 惯性-惯性*0.05, 惯性-惯性*0.15, 3, 0), COLOR0000CC;
 *   …… (正负各五段, 见 `ENERGY_BANDS` / `ENERGY_COLORS`)
 *
 * `能量惯性` 那一行是冒号, 通达信会把它作为输出线画出来(颜色取 `ENERGY_COLORS.line`);
 * `:=` 的中间变量都不画线。画法交给调用方(见 LightweightDaily / EChartsCandlestick)。
 * 两个 EMA 都是通达信口径(α=2/(N+1), 首值取 X), 与 `tdxEma` 同一实现;
 * 除零(高开低全为 0 / 无量)按通达信的 0 处理。
 */
export function computeEnergyInertia(rows: OHLC[], n = 16): EnergyPoint[] {
  const energy = rows.map(row => {
    const mid = (row.high + row.low) / 2
    const volume = row.volume
    if (!(mid > 0) || volume == null || !Number.isFinite(volume) || volume <= 0) return 0
    return Math.sqrt(volume) * (row.close - mid) / mid
  })
  const smooth = tdxEma(energy, n)
  const inertia = tdxEma(smooth, n)
  return rows.map((_, i) => ({
    energy: energy[i],
    smooth: smooth[i],
    inertia: inertia[i],
    // 严格大于 / 严格小于: 通达信写的就是 `>0 AND REF(...)<0`, 等于 0 不算上穿
    crossUp: i > 0 && inertia[i] > 0 && inertia[i - 1] < 0,
  }))
}

/**
 * [R722] 通达信「ATR 原始版 - 副图」的配色。**暗色取公式原色**, 亮色换成同色相的深一档
 * (与 `DAILY_LINE_COLORS` 同一做法), 否则 `#00FF00` 落在白底上几乎看不见。
 * 公式里 `COLOR0000FF` 按用户自己的说法是「蓝线」(S), `COLORFF8800` 是 BASIS 橙 ——
 * 这里按 RGB 直读取色; 若按 BGR 读会变成 S 红、BASIS 蓝, 与用户描述对不上。
 */
export const ATR_BAND_COLORS = {
  atr: { dark: '#3B82F6', light: '#2563EB' },
  basis: { dark: '#FF8800', light: '#C2410C' },
  band: { dark: '#808080', light: '#6B7280' },
  refMid: { dark: '#00FF00', light: '#15803D' },
  /**
   * [R755] 用户: 「出来的都是红箭头, 需要区分是哪个指标出来的箭头」—— 能量惯性的上穿箭头
   * 已占住通达信 1 号的红色, ATR 这枚(DRAWICON(CROSS(S,REFMID),REFMID,1)) 撞成同色就分不清了。
   * 箭头跟着「发出信号的那条线」上色: S 是蓝线, 所以 ATR 这枚用蓝; 能量惯性那枚保持红。
   * 同一常量也喂读数条里的「上穿」二字, 文字与箭头永远对得上。
   */
  icon: { dark: '#3B82F6', light: '#2563EB' },
} as const

export interface AtrBandPoint {
  /** S = ATR20 */
  atr: number | null
  /** BASIS = ATR20 的 34 日简单均线 */
  basis: number | null
  upper: number | null
  lower: number | null
  /** REFMID = (LOWER + BASIS) / 2 —— 蓝线上穿这条线就是信号 */
  refMid: number | null
  /** DRAWICON 的条件: CROSS(S, REFMID) */
  crossUp: boolean
}

/**
 * [R722] 通达信「ATR 原始版 - 副图」的取数, 逐句照抄公式:
 *
 *   TR1:=MAX(MAX(H-L,ABS(REF(C,1)-H)),ABS(REF(C,1)-L));
 *   ATR20:=MA(TR1,20);  SVAL:=ATR20;
 *   BASISV:=MA(SVAL,34);  DEV:=2.0*STD(SVAL,34);
 *   UPPERV:=BASISV+DEV;  LOWERV:=BASISV-DEV;
 *   REFMIDV:=(LOWERV+BASISV)/2;
 *   DRAWICON(CROSS(SVAL,REFMIDV),REFMIDV,1);
 *
 * 三点口径: ①`MA` 是简单均线, 不足 N 根不出值(与 `volMaN` 一致, 通达信也从第 N 根才画);
 * ②`STD` 是**估算标准差**(除以 N-1), 不是总体标准差; ③首根的 `REF(C,1)` 不存在, TR 取 H-L。
 *
 * 用法(用户原话): 出现信号 + 缎带收束 / 长期贴下轨, 说明将有一波单边行情,
 * 方向另结合 MA/EMA 判断 —— 指标本身不带方向, 全品种通用(可用于做空)。
 */
export function computeAtrBandSeries(rows: OHLC[], n = 20, bbLen = 34, bbMult = 2): AtrBandPoint[] {
  const tr = rows.map((row, i) => {
    const hl = row.high - row.low
    const prevClose = i > 0 ? rows[i - 1].close : null
    return prevClose == null ? hl : Math.max(hl, Math.abs(prevClose - row.high), Math.abs(prevClose - row.low))
  })
  const mean = (values: (number | null)[], window: number) => values.map((_, i) => {
    if (i < window - 1) return null
    let sum = 0
    for (let j = i - window + 1; j <= i; j++) {
      const value = values[j]
      if (value == null) return null
      sum += value
    }
    return sum / window
  })
  const atr = mean(tr, n)
  const basis = mean(atr, bbLen)
  const dev = atr.map((value, i) => {
    if (value == null || i < bbLen - 1) return null
    let sum = 0
    for (let j = i - bbLen + 1; j <= i; j++) sum += atr[j]!
    const avg = sum / bbLen
    let squares = 0
    for (let j = i - bbLen + 1; j <= i; j++) squares += (atr[j]! - avg) ** 2
    return Math.sqrt(squares / (bbLen - 1))
  })
  const upper = basis.map((mid, i) => mid == null || dev[i] == null ? null : mid + bbMult * dev[i]!)
  const lower = basis.map((mid, i) => mid == null || dev[i] == null ? null : mid - bbMult * dev[i]!)
  const refMid = lower.map((low, i) => low == null || basis[i] == null ? null : (low + basis[i]!) / 2)
  return rows.map((_, i) => ({
    atr: atr[i], basis: basis[i], upper: upper[i], lower: lower[i], refMid: refMid[i],
    crossUp: i > 0 && atr[i] != null && refMid[i] != null && atr[i - 1] != null && refMid[i - 1] != null
      && atr[i]! > refMid[i]! && atr[i - 1]! <= refMid[i - 1]!,
  }))
}

export function volMaN(data: OHLC[], n: number): (number | null)[] {  const result: (number | null)[] = []
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
