// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import type { LevelType, PriceLevel } from './analysis-chart-model'

const plots = vi.hoisted(() => ({ current: [] as any[] }))

vi.mock('@/components/charts/FinancialPlot', () => ({
  FinancialPlot: (props: any) => {
    plots.current.push(props)
    return <output data-testid="plot" />
  },
}))
vi.mock('@/lib/theme', () => ({
  useTheme: () => 'dark',
  useChartTheme: () => ({
    text: '#A1A1AA', textStrong: '#E4E4E7', grid: 'rgba(255,255,255,0.06)', border: '#27272A',
    crosshair: 'rgba(255,255,255,0.25)', crosshairLabelBg: '#333', tooltipBg: 'rgba(24,24,27,0.95)',
    tooltipBorder: 'rgba(255,255,255,0.1)', tooltipText: '#E4E4E7', infoBarBg: 'rgba(39,39,42,0.6)',
    zoomFill: 'rgba(255,255,255,0.06)', fillSubtle: 'rgba(255,255,255,0.04)',
  }),
  levelColors: () => ({
    sr: '#F97316', pivot: '#8B5CF6', extreme: '#EAB308', boll: '#F97316',
    keltner_s: '#06B6D4', keltner_m: '#22D3EE', keltner_l: '#67E8F9',
    atr_stop: '#EF4444', gap: '#3730A3', fib: '#F59E0B', round: '#71717A',
    livermore: '#1D4ED8', fib2: '#6A0DAD',
  }),
  useLevelColors: () => ({}),
  fib2RoleColor: (color: string) => color,
  LEVEL_CURVE_COLOR: {},
  FIB2_ROLE_TARGET: '#0369A1',
  QUANT_MACD_COLORS: { red: '#FF0000', darkRed: '#CC0000', green: '#00FF00', yellow: '#FFFF00', icon2: '#00DC00', paneBg: '#000000' },
  TREND_QUANT_COLORS: { red: '#FF0000', green: '#00FF00', yellow: '#FFFF00', white: '#FFFFFF', lightRed: '#FF8080', avg: '#B84DFF', xichou: '#00FF00', text: '#FFFFFF', paneBg: '#000000' },
}))

import { AnalysisKChart } from './AnalysisKChart'

const DATES = ['2026-10-29', '2026-10-30', '2026-11-02']
const rows = DATES.map((date, index) => ({
  date, open: 10 + index, high: 11 + index, low: 9 + index, close: 10.5 + index, volume: 1000 + index,
}))
const levels: Record<LevelType, PriceLevel[]> = {
  sr: [{ value: 12.4, label: '成交密集区', type: 'sr', side: 'resistance', strength: 'strong' }],
  pivot: [
    { value: 10.2, label: '枢轴位 P', type: 'pivot', side: 'neutral', rank: 0 },
    { value: 10.6, label: '压力位 R1', type: 'pivot', side: 'resistance', rank: 1 },
    { value: 11.1, label: '压力位 R2', type: 'pivot', side: 'resistance', rank: 2 },
  ],
  boll: [
    { value: 12.3, label: '布林上轨', type: 'boll', side: 'neutral' },
    { value: 10.8, label: '布林中轨', type: 'boll', side: 'neutral' },
    { value: 9.3, label: '布林下轨', type: 'boll', side: 'neutral' },
  ],
  extreme: [], keltner_s: [], keltner_m: [], keltner_l: [], atr_stop: [], gap: [], fib: [], round: [],
  livermore: [], fib2: [],
}
const series = {
  boll: { upper: [12.1, 12.2, 12.3], lower: [9.5, 9.4, 9.3], mid: [10.8, 10.8, 10.8] },
  keltner_s: { upper: [11.8, 11.9, 12.0], lower: [9.9, 10.0, 10.1] },
}

let host: HTMLDivElement
let root: Root
beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })
  plots.current.length = 0
  host = document.createElement('div')
  document.body.append(host)
  root = createRoot(host)
})
afterEach(async () => {
  await act(async () => root.unmount())
  host.remove()
})

// fork 默认只开量化通道短期(曲线, 没有价位线); 这里显式带上压力支撑与枢轴点,
// 才能同时验证价位线 / 右侧标签 / 悬浮高亮。
const renderChart = async (props: Partial<Parameters<typeof AnalysisKChart>[0]> = {}) => act(async () => root.render(
  <AnalysisKChart rows={rows} levels={levels} series={series} seriesDates={DATES} height={480}
                  defaultLevelTypes={['sr', 'pivot', 'keltner_s']} {...props} />,
))
const lastPlot = () => plots.current.at(-1)!
const button = (text: string) => [...host.querySelectorAll('button')].find(item => item.textContent === text)!

it('renders a lightweight plot with candle, two subpanes and the configured level groups', async () => {
  await renderChart()
  const plot = lastPlot()
  expect(plot.series.map((item: any) => item.id)).toEqual([
    'price', 'curve:keltner_s_upper', 'curve:keltner_s_lower', 'tq:empty', 'qm:empty',
  ])
  // 现价贴签排在最后
  expect(plot.annotations.priceLines.filter((line: any) => !line.noLine).map((line: any) => line.value))
    .toEqual([12.4, 10.2, 10.6, 12.5])
  expect(plot.visibleBars).toBe(120)
  expect(plot.rightOffsetPixels).toBe(148)
  expect(plot.paneTitles).toEqual(['', '趋势量化', '量化MACD'])
  expect(host.textContent).toContain('当前价')
  expect(host.textContent).toContain('压力位 ↑')
})

it('switches level groups and pivot ranks from the toolbar', async () => {
  await renderChart()
  await act(async () => button('26日布林3').click())
  expect(lastPlot().series.map((item: any) => item.id)).toContain('curve:boll_upper')
  expect(lastPlot().annotations.priceLines.map((line: any) => line.label)).toContain('26日布林上轨 12.30')
  await act(async () => button('2').click())
  expect(lastPlot().annotations.priceLines.map((line: any) => line.value)).toContain(11.1)
})

it('highlights the level under the crosshair and clears it when the pointer leaves', async () => {
  await renderChart()
  await act(async () => lastPlot().onCrosshairMove({ time: '2026-10-30', price: 12.42, pixelsPerPrice: 0.01 }))
  const hitLine = () => lastPlot().annotations.priceLines.find((line: any) => line.value === 12.4)
  expect(hitLine()).toMatchObject({ width: 2, opacity: 1 })
  await act(async () => lastPlot().onCrosshairMove(null))
  expect(hitLine()).toMatchObject({ width: 1, opacity: 0.9 })
})

it('[R630] 量化MACD 纵轴恒含 0(原文 scale: false), 副图不写刻度', async () => {
  await renderChart({
    quantMacd: {
      symbol: '603083.SH', dates: DATES, diff: [-1.2, -0.8, -0.3], dea: [-1.0, -0.9, -0.6],
      yellow: [null, -0.2, null], gold_icon: [null, null, null], dead_icon: [null, null, null],
    },
  })
  const plot = lastPlot()
  const zero = plot.series.find((item: any) => item.id === 'qm:scale_zero')
  expect(zero).toMatchObject({ pane: 2 })
  expect(zero.data.map((point: any) => point.value)).toEqual([0, 0, 0])
  expect(plot.hidePaneAxis).toBe(true)
})

it('forwards date clicks to the caller', async () => {
  const onDateClick = vi.fn()
  await renderChart({ onDateClick })
  await act(async () => lastPlot().onSelect('2026-10-30'))
  expect(onDateClick).toHaveBeenCalledWith('2026-10-30')
})
