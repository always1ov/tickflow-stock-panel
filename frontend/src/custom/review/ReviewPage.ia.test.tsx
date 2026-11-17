// @vitest-environment jsdom
// [R791] 复盘页改版验收: 七种状态都能读 —— 加载 / 无数据 / 空态 / 生成中 / 完成 /
// 失败 / 查看历史, 外加档案带「对照」抽屉。只钉信息架构与文案, 不钉样式细节。
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

import type { AiReviewReportMeta, OverviewBreadth, OverviewCore, OverviewHeat } from '@/lib/api'

const core: OverviewCore = {
  as_of: '2026-11-17',
  quote_status: { is_trading_hours: false },
  indices: [
    { symbol: '000001', name: '上证指数', change_pct: 1.02 } as OverviewCore['indices'][number],
    { symbol: '399001', name: '深证成指', change_pct: 1.11 } as OverviewCore['indices'][number],
  ],
  emotion: { score: 62, label: '偏暖' },
}

const breadth = {
  as_of: '2026-11-17',
  breadth: { total: 5200, up: 2411, down: 2563, flat: 226, up_pct: 46, down_pct: 49 },
  amount: { total: 1.21e12, avg: 0 },
  boards: [],
  distribution: [{ label: '0~3%', count: 1200, pct: 23 }],
  trend: { above_ma5: 0, above_ma20: 0, above_ma60: 0, above_ma5_pct: 58, above_ma20_pct: 47, above_ma60_pct: 40, new_high: 30, new_low: 12 },
  activity: { avg_turnover: 3.2, high_turnover: 120, high_vol_ratio: 40, vol_ratio: 80 },
  radar: [{ key: 'breadth', label: '广度', value: 62 }],
  limit: { limit_up: 58, broken: 12, failed: 3, limit_down: 4, max_boards: 5, seal_rate: 71, tiers: [{ boards: 5, count: 2, stocks: [{ symbol: '600001.SH', name: '测试龙头' }] }] },
} as unknown as OverviewBreadth

const heat: OverviewHeat = {
  as_of: '2026-11-17',
  kind: 'concept',
  leading: [{ name: '半导体', count: 42, avg_pct: 3.1, up_count: 40, down_count: 2, amount: 0, leader: { symbol: '600001.SH', name: '测试龙头', change_pct: 9.9 } }],
  lagging: [],
}

const reportsMeta: AiReviewReportMeta[] = [
  { id: 'mkr_2', as_of: '2026-11-17', summary: '上+1.02%、深+1.11% | 情绪 62', emotion_score: 62, emotion_label: '偏暖', focus: '', created_at: '2026-11-17T15:12:00' },
  { id: 'mkr_1', as_of: '2026-11-14', summary: '上-0.40% | 情绪 47', emotion_score: 47, emotion_label: '震荡', focus: '', created_at: '2026-11-14T15:10:00' },
]

const fullReport = {
  id: 'mkr_1', as_of: '2026-11-14', emotion_score: 47, emotion_label: '震荡',
  created_at: '2026-11-14T15:10:00', summary: '', focus: '',
  content: '## 一句话定调\n缩量整理, 主线未散。\n\n## 明日计划\n等量能。\n\n## 风险提示\n外围扰动。',
}

let mockState: { phase: string; content: string; error: string; meta: unknown } = {
  phase: 'idle', content: '', error: '', meta: null,
}
let mockCore: OverviewCore | null = core

const apiMock = {
  overviewCore: vi.fn(async () => mockCore),
  overviewBreadth: vi.fn(async () => breadth),
  overviewHeat: vi.fn(async () => heat),
  reviewReportsListMeta: vi.fn(async () => ({ reports: reportsMeta })),
  reviewReportDetail: vi.fn(async () => ({ report: fullReport })),
  reviewReportDelete: vi.fn(async () => ({ ok: true })),
  reviewReportSave: vi.fn(async () => ({ ok: true })),
  dragonTiger: vi.fn(async () => ({ state: 'no_data' })),
  auctionBenchmark: vi.fn(async () => ({ state: 'no_data' })),
  getMarketRecapPrompt: vi.fn(async () => ({ custom: '', default: '', customized: false })),
  updateMarketRecapPrompt: vi.fn(async () => ({ ok: true })),
  updateReviewSchedule: vi.fn(async () => ({ ok: true })),
  updateReviewPush: vi.fn(async () => ({ ok: true })),
}

vi.mock('@/lib/api', () => ({ api: apiMock }))
vi.mock('@/lib/useReviewStore', () => ({ useReviewState: () => mockState }))
vi.mock('@/lib/useSharedQueries', () => ({
  usePreferences: () => ({
    data: { review_schedule: { enabled: false, hour: 15, minute: 10 }, review_push_channels: [] },
    isLoading: false,
  }),
}))

// Page 必须在 mock 之后引入
const { ReviewPage } = await import('./Page')

let host: HTMLDivElement
let root: Root
let client: QueryClient

beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })
  // jsdom 没实现 scrollIntoView, 流式自动跟随会调用它
  Element.prototype.scrollIntoView = vi.fn()
  mockState = { phase: 'idle', content: '', error: '', meta: null }
  mockCore = core
  apiMock.overviewCore.mockImplementation(async () => mockCore)
  host = document.createElement('div')
  document.body.append(host)
  root = createRoot(host)
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
})

afterEach(async () => {
  await act(async () => root.unmount())
  client.clear()
  host.remove()
  vi.clearAllMocks()
})

async function render() {
  await act(async () => root.render(
    <MemoryRouter>
      <QueryClientProvider client={client}>
        <ReviewPage />
      </QueryClientProvider>
    </MemoryRouter>,
  ))
  // 等查询落地
  await act(async () => { await new Promise(r => setTimeout(r, 60)) })
}

it('加载中: 只给一行加载提示, 不闪空白', async () => {
  mockCore = null
  apiMock.overviewCore.mockImplementationOnce(() => new Promise(() => {}))
  await render()
  expect(host.textContent).toContain('加载市场数据')
})

it('无数据: 引导去数据页同步', async () => {
  mockCore = { ...core, as_of: null }
  await render()
  expect(host.textContent).toContain('暂无市场数据')
  expect(host.textContent).toContain('前往数据页同步')
})

it('空态: 事实仪表与档案带都已就位, 正文只占一行', async () => {
  await render()
  expect(host.textContent).toContain('62')
  expect(host.textContent).toContain('偏暖')
  expect(host.textContent).toContain('收盘定稿')
  expect(host.textContent).toContain('还没有今日复盘')
  expect(host.textContent).toContain('报告包含: 一句话定调')
  // 档案 meta 查询(不含正文)确实被调用
  expect(apiMock.reviewReportsListMeta).toHaveBeenCalled()
})

it('生成中: 正文流式追加, 目录跟着长出来, 档案带出现「生成中」', async () => {
  mockState = { phase: 'streaming', content: '## 一句话定调\n今天放量。', error: '', meta: null }
  await render()
  expect(host.textContent).toContain('AI 正在复盘')
  expect(host.textContent).toContain('一句话定调')
  expect(host.textContent).toContain('生成中')
})

it('失败: 给出原因与重新生成', async () => {
  mockState = { phase: 'error', content: '', error: '模型超时', meta: null }
  await render()
  expect(host.textContent).toContain('复盘失败')
  expect(host.textContent).toContain('模型超时')
  expect(host.textContent).toContain('重新生成')
})

it('查看历史: 面包屑可返回, 正文按 id 拉全文', async () => {
  await render()
  const item = [...host.querySelectorAll('button')].find(b => b.textContent?.includes('2026-11-14'))
  expect(item).toBeDefined()
  await act(async () => { item!.click() })
  await act(async () => { await new Promise(r => setTimeout(r, 60)) })
  expect(apiMock.reviewReportDetail).toHaveBeenCalledWith('mkr_1')
  expect(host.textContent).toContain('正在查看')
  expect(host.textContent).toContain('返回最新')
  expect(host.textContent).toContain('缩量整理')
})

it('生成途中翻历史: 面包屑保留, 并给「生成中 · 切回」入口', async () => {
  mockState = { phase: 'streaming', content: '## 一句话定调\n今天放量。', error: '', meta: null }
  await render()
  const item = [...host.querySelectorAll('button')].find(b => b.textContent?.includes('2026-11-14'))
  expect(item).toBeDefined()
  await act(async () => { item!.click() })
  await act(async () => { await new Promise(r => setTimeout(r, 60)) })
  expect(host.textContent).toContain('正在查看')
  expect(host.textContent).toContain('生成中 · 切回')
  expect(host.textContent).toContain('缩量整理')
})

it('对照: 抽屉拉最近两篇原文, 三段标题齐全', async () => {
  await render()
  const btn = [...host.querySelectorAll('button')].find(b => b.textContent?.trim() === '对照')
  expect(btn).toBeDefined()
  await act(async () => { btn!.click() })
  await act(async () => { await new Promise(r => setTimeout(r, 60)) })
  expect(host.textContent).toContain('复盘对照')
  for (const label of ('一句话定调|明日计划|风险提示').split('|')) {
    expect(host.textContent).toContain(label)
  }
})
