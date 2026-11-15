// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import type { KlineRow } from '@/lib/api'
import { StockDailyKChart } from './StockDailyKChart'
import { LEVEL_GROUPS } from './stock-analysis/analysis-chart-model'

const fixture = vi.hoisted(() => ({ rows: [
  { date: '2026-11-03', open: 10, high: 11, low: 10, close: 11, volume: 100, signal_limit_up: true, consecutive_limit_ups: 3 },
  { date: '2026-11-04', open: 11, high: 12, low: 10, close: 10.5, volume: 100, signal_limit_up: true, signal_broken_limit_up: true },
  { date: '2026-11-05', open: 10.5, high: 11, low: 10, close: 10.8, volume: 100 },
  { date: '2026-11-06', open: 10.2, high: 11.88, low: 9.72, close: 9.72, volume: 100, signal_limit_down: true, signal_broken_limit_up: true },
] as KlineRow[] }))
vi.mock('@tanstack/react-query', () => ({
  useQuery: () => ({ data: fixture, isLoading: false, isError: false }),
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
}))
vi.mock('@/lib/kline', async importOriginal => ({
  ...await importOriginal<typeof import('@/lib/kline')>(), klineDailyQueryOptions: vi.fn(() => ({})),
}))
// [R696] 异动 / 自选 / 回测 / 全部清除 已挪到读数条右端, 由图表组件负责挂出来 ——
// 这里照原样渲染 readoutExtra, 让那几颗按钮仍在 DOM 里可点; JSON 里剔掉它(React 元素没法断言)。
vi.mock('./charts/LightweightDaily', () => ({
  LightweightDaily: (props: any) => (
    <div>
      <output>{JSON.stringify(props, (key, value) => key === 'readoutExtra' ? undefined : value)}</output>
      {props.readoutExtra}
    </div>
  ),
}))
vi.mock('./EChartsCandlestick', () => ({ EChartsCandlestick: (props: any) => <output>{JSON.stringify(props)}</output> }))

let host: HTMLDivElement, root: Root
const originalRows = fixture.rows
beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })
  // [R667] 工具栏改为 ResizeObserver 实测高度, jsdom 没有这个 API —— 空实现兜底,
  // 回调不触发, 高度保持初始的 40px(与真实一排时一致)。
  if (typeof globalThis.ResizeObserver === 'undefined') {
    globalThis.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} } as unknown as typeof ResizeObserver
  }
  localStorage.clear()
  fixture.rows = originalRows
  host = document.createElement('div'); document.body.append(host); root = createRoot(host)
})
afterEach(async () => { await act(async () => root.unmount()); host.remove(); localStorage.clear() })
const props = () => JSON.parse(host.querySelector('output')!.textContent!)
const render = async (extra: Partial<Parameters<typeof StockDailyKChart>[0]> = {}) => act(async () => {
  root.render(<StockDailyKChart symbol="605365.SH" renderer="lightweight" {...extra} />)
})

it('[R706] 两排价位开关各自按逻辑顺序排列, 合起来正好铺满所有价位类型', async () => {
  await render()
  const mainRow = [...host.querySelectorAll('span')].find(span => span.textContent === '主图指标')!.parentElement!
  const keys = (buttons: Element[]) => buttons
    .map(button => LEVEL_GROUPS.find(group => button.textContent!.trim().startsWith(group.label))?.key)
    .filter(Boolean)
  const main = keys([...mainRow.querySelectorAll('button')])
  const sub = keys([...host.querySelector('[data-testid="level-toolbar"]')!.querySelectorAll('button')])
  expect(main).toEqual(['sr', 'extreme', 'pivot', 'round', 'gap'])
  expect(sub).toEqual(['boll', 'keltner_s', 'keltner_m', 'keltner_l', 'atr_stop', 'fib', 'fib2', 'livermore'])
  // 漏一类那颗按钮就从界面上消失了, 这里守住「不重不漏」
  expect([...main, ...sub].sort()).toEqual(LEVEL_GROUPS.map(group => group.key).sort())
})

it('identifies limit events from existing signals, prioritizing a limit-down close over a broken limit-up', async () => {
  await render({ markers: [{ date: '2026-11-05', kind: 'buy', label: '策略买点' }] })
  expect(props().markers).toEqual([
    expect.objectContaining({ label: '策略买点' }),
    expect.objectContaining({ date: '2026-11-03', event: 'limit_up', label: '3', color: '#FACC15' }),
    expect.objectContaining({ date: '2026-11-04', event: 'broken_limit_up', label: '炸', color: '#8B5CF6' }),
    expect.objectContaining({ date: '2026-11-06', event: 'limit_down', kind: 'sell', above: false, label: '跌', color: '#22D3EE' }),
  ])
  expect(props().markers[0].event).toBeUndefined()
})

it.each([
  ['bearish recovery', { open: 4.75, signal_limit_down_recovery: false }, 'limit_down_recovery'],
  ['bullish recovery', { open: 4.6, signal_limit_down_recovery: true }, 'limit_down_recovery'],
  ['doji recovery', { open: 4.7 }, 'limit_down_recovery'],
  ['no custom signal', { signal_limit_down_recovery: undefined }, 'limit_down_recovery'],
  ['not touching the raw limit', { raw_low: 9.01 }, undefined],
  ['still at the raw limit', { raw_close: 9.005 }, undefined],
  ['no-limit day overrides old signal', { limit_down_price: null, signal_limit_down_recovery: true }, undefined],
  ['invalid raw price', { raw_low: NaN, signal_limit_down_recovery: true }, undefined],
  ['missing raw price', { raw_close: undefined }, undefined],
  ['legacy recovery signal', { raw_low: undefined, raw_close: undefined, limit_down_price: undefined, signal_limit_down_recovery: true }, 'limit_down_recovery'],
  ['legacy absent signal', { raw_low: undefined, raw_close: undefined, limit_down_price: undefined }, undefined],
  ['sealed limit-down wins', { signal_limit_down: true }, 'limit_down'],
  ['broken limit-up wins a two-sided touch', { signal_broken_limit_up: true }, 'broken_limit_up'],
  ['sealed limit-up wins', { signal_limit_up: true }, 'limit_up'],
] as [string, Partial<KlineRow>, string | undefined][])('identifies %s from raw limit metadata without changing signal definitions', async (_name, patch, event) => {
  const row: KlineRow = { date: '2026-11-05', open: 4.75, high: 5, low: 4.5, close: 4.7, volume: 100,
    raw_low: 9, raw_close: 9.4, limit_down_price: 9.005, ...patch }
  fixture.rows = [row]
  await render()
  expect(props().markers.map((marker: { event?: string }) => marker.event)).toEqual(event ? [event] : [])
  expect(fixture.rows[0]).toEqual(row)
  await render({ renderer: 'echarts' })
  expect(props().markers.some((marker: { event?: string }) => marker.event === 'limit_down_recovery')).toBe(false)
  await render({ showLimitMarkers: false })
  expect(props().markers).toEqual([])
})

it('[R694] 异动只剩一颗开关: 显示方式固定为颜色, 关掉就不画标记', async () => {
  await render()
  // 「圆点 / 颜色」两个显示方式已撤掉: 工具栏里没有那颗分段按钮, 也不再往图表传显示方式
  expect(host.querySelector('[aria-label="异动显示方式"]')).toBeNull()
  expect(props().markerStyle).toBeUndefined()
  const toggle = [...host.querySelectorAll('button')].find(button => button.textContent === '异动')!
  await act(async () => toggle.click())
  expect(props().showMarkers).toBe(false)
  await act(async () => toggle.click())
  expect(props().showMarkers).toBe(true)
  await render({ showMarkerToggle: false })
  expect([...host.querySelectorAll('button')].some(button => button.textContent === '异动')).toBe(false)
  // ECharts 那条老路径照旧: 不认异动着色, 只留炸板标记
  await render({ renderer: 'echarts' })
  expect(props().markers.some((marker: { event?: string }) => marker.event === 'limit_down')).toBe(false)
  expect(props().markers).toContainEqual(expect.objectContaining({ date: '2026-11-06', event: 'broken_limit_up' }))
})

it('[R649] 趋势量化 / 量化MACD 两张副图默认不画, 点开后才追加到日K底部', async () => {
  await render()
  expect(props().analysisPanes).toEqual([])
  const pill = (label: string) => [...host.querySelectorAll('button')].find(button => button.textContent === label)!
  await act(async () => pill('趋势量化').click())
  expect(props().analysisPanes.map((pane: any) => pane.kind)).toEqual(['trend'])
  await act(async () => pill('量化MACD').click())
  expect(props().analysisPanes.map((pane: any) => pane.kind)).toEqual(['trend', 'quant'])
  expect(props().analysisPanes.every((pane: any) => pane.height > 0)).toBe(true)
  // ECharts 渲染没有这两张副图, 工具栏也不给开关
  await render({ renderer: 'echarts' })
  expect(props().analysisPanes).toEqual([])
  expect([...host.querySelectorAll('button')].some(button => button.textContent === '趋势量化')).toBe(false)
})

it('[R655] 四条主图均线默认只开 MA20, 每条都能单独关掉再打开', async () => {
  await render()
  expect(props().maKeys).toEqual(['ma20'])
  const pill = (label: string) => [...host.querySelectorAll('button')].find(button => button.textContent === label)!
  await act(async () => pill('MA20').click())
  expect(props().maKeys).toEqual([])
  await act(async () => pill('MA20').click())
  expect(props().maKeys).toEqual(['ma20'])
  await act(async () => pill('MA5').click())
  expect([...props().maKeys].sort()).toEqual(['ma20', 'ma5'])
  // ECharts 画不了单条均线: 不给这四个开关, 仍按 showMA 整组
  await render({ renderer: 'echarts' })
  expect(props().maKeys).toBeUndefined()
  expect([...host.querySelectorAll('button')].some(button => button.textContent === 'MA5')).toBe(false)
})

it('[R657] 日K 里指标开关键与价位开关键同一尺寸(跟原来那颗指标胶囊一样)', async () => {
  await render()
  const byLabel = (label: string) => [...host.querySelectorAll('button')]
    .find(button => button.textContent?.trim() === label)!
  const indicator = byLabel('成交量')
  const level = host.querySelector('[data-testid="level-toolbar"] button')
  expect(level).not.toBeNull()
  for (const button of [indicator, level!]) {
    expect(button.className).toContain('text-micro')
    expect(button.className).toContain('px-2')
    expect(button.className).toContain('py-0.5')
    // 方按钮那档(h-8/px-2.5/text-xs)不能漏进日K
    expect(button.className).not.toContain('h-8')
    expect(button.className).not.toContain('px-2.5')
    expect(button.className).not.toContain('text-xs')
  }
})

it('[R659] 日K 不再提供原 MACD 副图入口, 量化MACD 仍在', async () => {
  await render()
  const labels = [...host.querySelectorAll('button')].map(button => button.textContent?.trim())
  expect(labels).not.toContain('MACD')
  expect(labels).toContain('量化MACD')
})

it('[R660] 价位开关状态可用外部那一份(与关键价位共用), 回测弹窗可整排关掉', async () => {
  await render({
    levelControls: {
      activeTypes: new Set(['sr']), toggleType: vi.fn(), clearAll: vi.fn(), pivotRank: 1, setPivotRank: vi.fn(),
      fib2Grain: 'coarse', setFib2Grain: vi.fn(), fib2ShowTargets: false, setFib2ShowTargets: vi.fn(),
    } as any,
  })
  const byLabel = (label: string) => [...host.querySelectorAll('button')]
    .find(button => button.textContent?.includes(label))!
  expect(byLabel('压力支撑').getAttribute('aria-pressed')).toBe('true')
  expect(byLabel('枢轴点').getAttribute('aria-pressed')).toBe('false')
  // [R705] 压力支撑/枢轴点/前高前低/整数关口/缺口位挪到主图指标那一行, 不再在这排价位开关里
  const levelRow = host.querySelector('[data-testid="level-toolbar"]')!
  expect(levelRow.textContent).not.toContain('压力支撑')
  expect(levelRow.textContent).toContain('26日布林')
  await render({ showLevelToolbar: false })
  expect(host.querySelector('[data-testid="level-toolbar"]')).toBeNull()
  expect(host.textContent).not.toContain('压力支撑')
  expect(host.textContent).not.toContain('26日布林')
})

it('[R651] 空间不够只压两张分析副图, 主图与指标副图的高度不动', async () => {
  const openPanes = async (options: any) => {
    await render(options)
    for (const label of ['趋势量化', '量化MACD']) {
      const pill = [...host.querySelectorAll('button')].find(button => button.textContent === label)!
      await act(async () => pill.click())
    }
    const panes: any[] = props().analysisPanes
    return {
      heights: panes.map(pane => pane.height),
      // 去掉分析副图后剩下的那截 = 主图 + 指标副图, 必须与 maxHeight 无关
      base: props().height - panes.reduce((sum, pane) => sum + pane.height, 0),
    }
  }
  const roomy = await openPanes({ maxHeight: 2400 })
  const tight = await openPanes({ maxHeight: 700 })
  expect(tight.base).toBe(roomy.base)
  expect(tight.heights.reduce((a, b) => a + b, 0)).toBeLessThan(roomy.heights.reduce((a, b) => a + b, 0))
  expect(Math.min(...tight.heights)).toBeGreaterThanOrEqual(100)
})
