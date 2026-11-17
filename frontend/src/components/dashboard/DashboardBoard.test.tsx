// @vitest-environment jsdom
/**
 * [R790] 固定版式看板 — 状态带 / 榜单 10 条 / 热度 Tab 切换 / 收盘后监控折叠。
 */
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { DashboardBoard, type DashboardBoardProps } from './DashboardBoard'

vi.mock('@/lib/api', () => ({ api: { klineDaily: vi.fn(async () => ({ symbol: 'x', rows: [] })) } }))
vi.mock('@/components/SectorRotationCard', () => ({ SectorRotationCard: () => <div>轮动矩阵</div> }))
vi.mock('@/components/dashboard/widgets', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/components/dashboard/widgets')>()
  return { ...actual, MonitorWidget: () => <div>监控列表</div> }
})

const rows = Array.from({ length: 10 }, (_, i) => ({
  symbol: `60000${i}.SH`,
  name: `票${i + 1}`,
  close: 10 + i,
  change_pct: i / 10,
  amount: 1_000 * (i + 1),
  turnover_rate: 1 + i,
}))

const core = {
  as_of: '2026-01-05',
  quote_status: { running: true, mode: 'full_market' },
  indices: [
    { symbol: '000001.SH', name: '上证指数', last_price: 3200, change_pct: 0.5 },
    { symbol: '399001.SZ', name: '深证成指', last_price: 10000, change_pct: -0.2 },
    { symbol: '399006.SZ', name: '创业板指', last_price: 2000, change_pct: 1.1 },
    { symbol: '000300.SH', name: '沪深300', last_price: 3800, change_pct: 0.3 },
  ],
  emotion: { score: 58, label: '中性' },
} as unknown as DashboardBoardProps['core']

const breadth = {
  as_of: '2026-01-05',
  breadth: { total: 3, up: 2, down: 1, flat: 0, up_pct: 66.7, down_pct: 33.3, avg_pct: 1.2, median_pct: 0.8, strong_up: 12, strong_down: 3 },
  amount: { total: 1e12, avg: 2e8 },
  boards: [],
  limit: { limit_up: 40, broken: 3, failed: 2, limit_down: 1, max_boards: 5, seal_rate: 80, tiers: [], sealed_ready: true },
  distribution: [{ label: '0~2%', count: 2, pct: 66.7 }],
  trend: { above_ma5: 2, above_ma20: 2, above_ma60: 1, above_ma5_pct: 66.7, above_ma20_pct: 66.7, above_ma60_pct: 33.3, new_high: 1, new_low: 0 },
  activity: { avg_turnover: 1.2, high_turnover: 1, high_vol_ratio: 20, vol_ratio: 1.1 },
  radar: [{ key: 'breadth', label: '广度', value: 60 }],
} as unknown as DashboardBoardProps['breadth']

const baseProps: DashboardBoardProps = {
  core,
  breadth,
  ranks: { as_of: '2026-01-05', kind: 'gain', rows } as DashboardBoardProps['ranks'],
  heat: {
    as_of: '2026-01-05',
    kind: 'concept',
    leading: [
      { name: '机器人', count: 8, avg_pct: 3.2, up_count: 8, down_count: 0, amount: 1e9, leader: { symbol: '600001.SH', name: '甲', change_pct: 5 } },
    ],
    lagging: [
      { name: '白酒', count: 6, avg_pct: -2.1, up_count: 0, down_count: 6, amount: 4e8, leader: { symbol: '600002.SH', name: '乙', change_pct: -3 } },
    ],
  } as DashboardBoardProps['heat'],
  heatKind: 'concept',
  rankKind: 'gain',
  onHeatKindChange: vi.fn(),
  onRankKindChange: vi.fn(),
  hasDepth: true,
  intraday: true,
  historical: false,
  phaseLabel: '主升',
  phaseColor: '#ef4444',
  phaseIntraday: true,
  activeSymbol: () => undefined,
  openStock: vi.fn(),
  openDimension: vi.fn(),
  openAlert: vi.fn(),
}

let host: HTMLDivElement
let root: Root
let client: QueryClient

beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })
  vi.clearAllMocks()
  host = document.createElement('div')
  document.body.append(host)
  root = createRoot(host)
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
})

afterEach(async () => {
  await act(async () => root.unmount())
  client.clear()
  host.remove()
})

async function render(props: DashboardBoardProps = baseProps) {
  await act(async () => root.render(
    <MemoryRouter><QueryClientProvider client={client}><DashboardBoard {...props} /></QueryClientProvider></MemoryRouter>,
  ))
}

async function clickByText(text: string, index = 0) {
  const buttons = [...host.querySelectorAll('button')].filter(b => b.textContent?.includes(text))
  await act(async () => { buttons[index]?.click() })
}

describe('DashboardBoard 固定版式', () => {
  it('状态带渲染四大指数与市场阶段, 榜单渲染 10 条', async () => {
    await render()
    expect(host.textContent).toContain('上证指数')
    expect(host.textContent).toContain('创业板指')
    expect(host.textContent).toContain('主升')
    expect(host.textContent).toContain('票10')
    expect(host.textContent).not.toContain('票11')
    expect(host.textContent).toContain('轮动矩阵')
  })

  it('热度区切换概念/行业会回调', async () => {
    await render()
    await clickByText('行业')
    expect(baseProps.onHeatKindChange).toHaveBeenCalledWith('industry')
  })

  it('收盘后监控中心默认折叠, 可展开', async () => {
    await render({ ...baseProps, intraday: false })
    expect(host.textContent).toContain('收盘后已折叠')
    expect(host.textContent).not.toContain('监控列表')
    await clickByText('收盘后已折叠')
    expect(host.textContent).toContain('监控列表')
  })
})
