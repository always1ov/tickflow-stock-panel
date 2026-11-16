import { describe, expect, it } from 'vitest'
import { computeAtrBandSeries, computeEnergyInertia, computeInstitutionSeries, ATR_BAND_COLORS, ENERGY_COLORS, tdxEma, tdxSma } from './chart-indicators'
import type { OHLC } from './chart-types'

const row = (i: number, close: number, high = close + 0.5, low = close - 0.5): OHLC => ({
  date: `2026-${String(Math.floor(i / 28) + 1).padStart(2, '0')}-${String((i % 28) + 1).padStart(2, '0')}`,
  open: close, high, low, close,
})

describe('[R714] 通达信公式的最小实现', () => {
  it('SMA(X,N,M) 是加权递推, 不是简单均线', () => {
    expect(tdxSma([10, 20], 3, 1)).toEqual([10, (20 + 2 * 10) / 3])
  })

  it('EMA(X,N) 首值取 X, α=2/(N+1)', () => {
    const out = tdxEma([1, 2, 3], 3)
    expect(out[0]).toBe(1)
    expect(out[1]).toBeCloseTo(1.5)
    expect(out[2]).toBeCloseTo(2.25)
  })

  it('价格不动时振幅为 0, 按通达信的 0 处理, 不产生 NaN', () => {
    const points = computeInstitutionSeries(Array.from({ length: 60 }, (_, i) => row(i, 10, 10, 10)))
    expect(points).toHaveLength(60)
    for (const point of points) {
      expect(Number.isFinite(point.inst)).toBe(true)
      expect(Number.isFinite(point.trend)).toBe(true)
      expect(point.mainForce).toBe(false)
      expect(point.mainSignal).toBe(false)
    }
  })

  it('机构线/机构趋势落在 0~100, 且趋势是机构线的 EMA', () => {
    const rows = Array.from({ length: 120 }, (_, i) => row(i, 10 + i * 0.2 + Math.sin(i / 3)))
    const points = computeInstitutionSeries(rows)
    for (const point of points) {
      expect(point.inst).toBeGreaterThanOrEqual(0)
      expect(point.inst).toBeLessThanOrEqual(100)
      expect(point.trend).toBeGreaterThanOrEqual(0)
      expect(point.trend).toBeLessThanOrEqual(100)
    }
    expect(points[0].trend).toBeCloseTo(points[0].inst)
  })

  it('暴跌后单日急拉触发主力, FILTER(主力,10) 保证 10 天内只报一次', () => {
    const rows: OHLC[] = []
    for (let i = 0; i < 90; i++) rows.push(row(i, 100 - i * 0.6))
    for (let i = 0; i < 6; i++) rows.push(row(90 + i, 46 + i * 4))
    const points = computeInstitutionSeries(rows)
    const signals = points.flatMap((point, i) => point.mainSignal ? [i] : [])
    expect(points.some(point => point.mainForce)).toBe(true)
    expect(signals.length).toBeGreaterThan(0)
    for (let k = 1; k < signals.length; k++) expect(signals[k] - signals[k - 1]).toBeGreaterThanOrEqual(10)
    for (const point of points) if (point.mainSignal) expect(point.mainForce).toBe(true)
  })
})

describe('[R753] 通达信「能量惯性」副图', () => {
  const bar = (i: number, close: number, high: number, low: number, volume = 100): OHLC =>
    ({ ...row(i, close, high, low), volume })

  it('能量 = SQRT(VOL) * (C - (H+L)/2) / ((H+L)/2)', () => {
    const points = computeEnergyInertia([bar(0, 10.5, 11, 9, 100), bar(1, 9.5, 11, 9, 400)])
    expect(points[0].energy).toBeCloseTo(0.5)   // sqrt(100) * 0.5/10
    expect(points[1].energy).toBeCloseTo(-1)    // sqrt(400) * -0.5/10
  })

  it('平滑能量与能量惯性是连续两次 EMA16, 首值取第一根', () => {
    const bars = Array.from({ length: 40 }, (_, i) => bar(i, 10 + Math.sin(i / 2), 10.5, 9.5, 100 + i * 10))
    const points = computeEnergyInertia(bars)
    const smooth = tdxEma(points.map(p => p.energy), 16)
    const inertia = tdxEma(smooth, 16)
    points.forEach((point, i) => {
      expect(point.smooth).toBeCloseTo(smooth[i])
      expect(point.inertia).toBeCloseTo(inertia[i])
    })
  })

  it('无量 / 高低为 0 时按 0 处理, 不产生 NaN', () => {
    const points = computeEnergyInertia([bar(0, 10, 0, 0, 0), bar(1, 10, 11, 9, 0)])
    for (const point of points) {
      expect(point.energy).toBe(0)
      expect(Number.isFinite(point.inertia)).toBe(true)
    }
  })

  it('从负翻正那一根才算上穿(等于 0 不算)', () => {
    const bars = [
      ...Array.from({ length: 40 }, (_, i) => bar(i, 9.5, 11, 9, 100)),
      ...Array.from({ length: 40 }, (_, i) => bar(40 + i, 10.5, 11, 9, 100)),
    ]
    const points = computeEnergyInertia(bars)
    // 公式写的是 `能量惯性>0 AND REF(能量惯性,1)<0`, 严格不等号
    const expected = points.map((point, i) => i > 0 && point.inertia > 0 && points[i - 1].inertia < 0)
    expect(points.map(point => point.crossUp)).toEqual(expected)
    expect(points.some(point => point.crossUp)).toBe(true)
  })

  it('颜色按通达信 BBGGRR 序: 惯性≥0 红→黄, <0 蓝→青(贴 0 轴的是黄/青)', () => {
    expect(ENERGY_COLORS.positive.dark).toEqual(['#CC0000', '#FF6600', '#FF9900', '#FFCC00', '#FFFF00'])
    expect(ENERGY_COLORS.negative.dark).toEqual(['#0033FF', '#0066FF', '#0099FF', '#00CCFF', '#00FFFF'])
    // COLOR0000CC 是深红不是蓝, COLOR00FFFF 是黄不是青 —— R753 首版按 RGB 直读把正负搞反了
    expect(ENERGY_COLORS.positive.dark[0]).not.toBe('#0000CC')
    expect(ENERGY_COLORS.positive.dark[4]).toBe('#FFFF00')
    expect(ENERGY_COLORS.negative.dark[4]).toBe('#00FFFF')
  })
})

describe('[R722] 通达信「ATR 原始版」副图', () => {
  // H=11 / L=9 / C=10: 每天 TR 恒为 2, 振幅不动时 DEV 为 0、五条线并成一条
  const flat = (count: number) => Array.from({ length: count }, (_, i) => row(i, 10, 11, 9))

  it('S / BASIS 按 20 / 34 根简单均线, 不足窗口不出值', () => {
    const points = computeAtrBandSeries(flat(60))
    expect(points[18].atr).toBeNull()
    expect(points[19].atr).toBe(2)
    expect(points[51].basis).toBeNull()
    expect(points[52].basis).toBe(2)
    expect(points[52].upper).toBe(2)
    expect(points[52].lower).toBe(2)
    expect(points[52].refMid).toBe(2)
    expect(points.every(point => !point.crossUp)).toBe(true)
  })

  it('S 上穿 REFMID 的那一根给出信号, 不重复报', () => {
    const points = computeAtrBandSeries([...flat(60), row(60, 20, 21, 19)])
    expect(points[60].atr).toBeCloseTo((19 * 2 + 11) / 20)
    expect(points[60].crossUp).toBe(true)
    expect(points.filter(point => point.crossUp)).toHaveLength(1)
  })

  // [R755] 两只箭头上穿同画在一个 pane 里, 同色就分不清是哪只指标发出来的
  it('ATR 的上穿箭头与能量惯性不同色, 且跟着发出信号的 S 线走', () => {
    expect(ATR_BAND_COLORS.icon).toEqual(ATR_BAND_COLORS.atr)
    expect(ATR_BAND_COLORS.icon.dark).not.toBe(ENERGY_COLORS.icon.dark)
    expect(ATR_BAND_COLORS.icon.light).not.toBe(ENERGY_COLORS.icon.light)
  })
})
