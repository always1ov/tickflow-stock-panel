// @vitest-environment jsdom
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { EChartsCandlestick, SUB_CHARTS, type OHLC } from './EChartsCandlestick'
import { ENERGY_BANDS, ENERGY_COLORS, computeEnergyInertia } from '@/lib/chart-indicators'
import { getTheme } from '@/lib/theme'

const chart = vi.hoisted(() => ({
  handlers: {} as Record<string, (event?: any) => void>,
  setOption: vi.fn(),
  on: vi.fn(),
  off: vi.fn(),
  dispatchAction: vi.fn(),
  resize: vi.fn(),
  dispose: vi.fn(),
  getZr: () => ({ on: vi.fn(), off: vi.fn() }),
  getOption: () => ({ dataZoom: [{ start: 0, end: 100 }] }),
  containPixel: () => false,
  convertFromPixel: () => [0, 0],
}))

vi.mock('echarts', () => ({ init: () => chart }))

// 超过 COMPACT_THRESHOLD(60): 切标的后 dataZoom 一响就会走紧凑态转换, 进而重写 markPoint
const DAYS = Array.from({ length: 62 }, (_, i) =>
  new Date(Date.UTC(2024, 0, 1 + i)).toISOString().slice(0, 10))
const rows = (base: number): OHLC[] =>
  DAYS.map(date => ({ date, open: base, high: base + 1, low: base - 1, close: base, volume: 1 }))

let host: HTMLDivElement
let root: ReturnType<typeof createRoot>

beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })
  vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} })
  chart.handlers = {}
  chart.setOption.mockClear()
  chart.on.mockImplementation((name: string, callback: (event?: any) => void) => {
    chart.handlers[name] = callback
  })
  host = document.createElement('div')
  document.body.appendChild(host)
  root = createRoot(host)
})

afterEach(async () => {
  await act(async () => root.unmount())
  host.remove()
  vi.unstubAllGlobals()
})

/** 最后一次 setOption 里 K 线的 markPoint (买卖箭头来源) */
function lastMarkPoint(): string {
  const option = chart.setOption.mock.calls.at(-1)?.[0] as any
  const k = option?.series?.find((s: any) => s.name === 'K')
  return JSON.stringify(k?.markPoint ?? null)
}

/** 模拟竖虚线命中某根 K 线 (鼠标在数据区内移动时 echarts 派发的事件) */
async function hoverCandle(index: number) {
  await act(async () => { chart.handlers.updateAxisPointer?.({ axesInfo: [{ value: index }] }) })
}

it('ETF 日K信息栏和价格轴保留三位, 切换股票后恢复两位', async () => {
  const data = [{ date: '2026-11-05', open: 0.751, high: 0.828, low: 0.747, close: 0.827, ma5: 0.801 }]
  await act(async () => root.render(<EChartsCandlestick data={data} assetType="etf" height={400} />))
  expect(host.textContent).toContain('0.827')
  expect(host.textContent).toContain('MA5:0.801')
  expect(chart.setOption.mock.calls.at(-1)![0].yAxis[0].axisLabel.formatter(0.827)).toBe('0.827')
  await act(async () => root.render(<EChartsCandlestick data={data} assetType="stock" height={400} />))
  expect(host.textContent).toContain('0.83')
  expect(chart.setOption.mock.calls.at(-1)![0].yAxis[0].axisLabel.formatter(0.827)).toBe('0.83')
})

it('切标的后响应 dataZoom 仍用当前标的的买卖标记, 不回退到上一只', async () => {
  const render = async (symbol: string, data: OHLC[], markerLabel: string, markerDate: string) => {
    await act(async () => root.render(
      <EChartsCandlestick
        data={data}
        markers={[{ date: markerDate, kind: 'buy', label: markerLabel }]}
        symbol={symbol}
        height={400}
        showInfoBar={false}
        visibleBars="all"
        activeIndicators={['vol']}
      />,
    ))
  }

  await render('600000', rows(10), 'A-BUY', DAYS[10])
  await render('000001', rows(100), 'B-SELL', DAYS[20])

  // 切换标的后图表实例被复用, dataZoom 监听仍是最初注册的那个; 首次 setOption 已是当前标的
  expect(lastMarkPoint()).toContain('B-SELL')

  await act(async () => { chart.handlers.dataZoom?.() })

  expect(lastMarkPoint()).toContain('B-SELL')
  expect(lastMarkPoint()).not.toContain('A-BUY')
})

it('切股后鼠标未离开图表, 竖虚线重新命中即恢复「至今/周期」', async () => {
  const render = async (symbol: string) => {
    await act(async () => root.render(
      <EChartsCandlestick data={rows(10)} symbol={symbol} height={400} visibleBars="all" />,
    ))
  }

  await render('600000')
  const surface = host.firstElementChild as HTMLElement
  await act(async () => { surface.dispatchEvent(new MouseEvent('mouseenter')) })
  await hoverCandle(30)
  expect(host.textContent).toContain('至今')

  // 切股: 上一只的悬停上下文作废, 清掉「至今/周期」
  await render('000001')
  expect(host.textContent).not.toContain('至今')

  // 鼠标没离开图表区 (只是切股), 竖虚线重新命中即恢复, 不靠 mouseenter
  await hoverCandle(20)
  expect(host.textContent).toContain('至今')
  expect(host.textContent).toContain('周期')

  // 移出图表区 → 重新收起
  await act(async () => { surface.dispatchEvent(new MouseEvent('mouseleave')) })
  expect(host.textContent).not.toContain('至今')
})

it('[R753] 能量惯性: 五段位置/正负取色/零轴箭头/输出线全按公式', () => {
  const def = SUB_CHARTS.find(s => s.key === 'energy')!
  const rows = DAYS.slice(0, 60).map((date, i) => ({ date, open: 10, high: 11, low: 9, close: i < 30 ? 9.5 : 10.5, volume: 90_000 }))
  const points = computeEnergyInertia(rows)
  const [custom, line] = def.buildSeries(rows, { compact: false, volumeCompare: { enabled: true, days: 1 } }) as any[]
  const theme = getTheme()
  // 「能量惯性:」是冒号输出线, 通达信会画; 同时负责撑开 Y 轴
  expect(line.name).toBe('能量惯性线')
  expect(line.lineStyle).toMatchObject({ width: 1 })
  expect(line.lineStyle.opacity).not.toBe(0)
  expect(line.data).toEqual(points.map(p => p.inertia))
  // 0 轴必须在刻度里; 全 0 时不让刻度塌掉
  expect(def.yAxisConfig!.min({ min: 3 })).toBe(0)
  expect(def.yAxisConfig!.max({ max: -2 })).toBe(0)
  expect(def.yAxisConfig!.min({ min: 0 })).toBe(-1)
  expect(def.yAxisConfig!.max({ max: 0 })).toBe(1)

  const paint = (inertia: number, crossUp = false) => custom.renderItem({}, {
    value: (dim: number) => [0, inertia, crossUp ? 1 : 0][dim],
    coord: ([, value]: [number, number]) => [10, 100 - value * 100],
  })
  const check = (inertia: number) => {
    const children = paint(inertia).children
    expect(children).toHaveLength(5)
    const palette = (inertia >= 0 ? ENERGY_COLORS.positive : ENERGY_COLORS.negative)[theme]
    ENERGY_BANDS.forEach(([near, far], band) => {
      const a = 100 - (inertia - inertia * near) * 100
      const b = 100 - (inertia - inertia * far) * 100
      expect(children[band].shape.x).toBe(8.5)
      expect(children[band].shape.width).toBe(3)
      expect(children[band].shape.y).toBeCloseTo(Math.min(a, b), 6)
      expect(children[band].shape.height).toBeCloseTo(Math.abs(a - b), 6)
      expect(children[band].style.fill).toBe(palette[band])
    })
    return children
  }
  // 正支全在 0 轴上方, 第五段贴 0 轴(黄), 第一段最远(深红); 负支镜像
  const positive = check(0.5)
  expect(positive.every((r: any) => r.shape.y + r.shape.height <= 100)).toBe(true)
  expect(Math.max(...positive.map((r: any) => r.shape.y + r.shape.height))).toBeCloseTo(97.5, 6)
  const negative = check(-0.5)
  expect(negative.every((r: any) => r.shape.y >= 100)).toBe(true)
  expect(Math.min(...negative.map((r: any) => r.shape.y))).toBeCloseTo(102.5, 6)
  // 惯性恰为 0: 一根柱都不画
  expect(paint(0).children).toHaveLength(0)
  // DRAWICON 箭头钉 0 轴, 尖朝上
  const arrow = paint(0.5, true).children.at(-1)
  expect(arrow.type).toBe('polygon')
  expect(arrow.shape.points).toEqual([[10, 92], [6, 100], [14, 100]])
  expect(arrow.style.fill).toBe(ENERGY_COLORS.icon[theme])
})
