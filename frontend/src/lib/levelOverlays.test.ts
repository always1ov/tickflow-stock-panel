import { describe, expect, it } from 'vitest'
import type { KlineRow } from '@/lib/api'
import type { LevelType } from '@/components/stock-analysis/analysis-chart-model'
import { levelFib2Overlay, withFib2Future } from '@/lib/levelOverlays'

const row = (date: string, close: number): KlineRow => ({
  date, open: close, high: close + 1, low: close - 1, close, volume: 100,
} as KlineRow)

describe('[R653] 关键价位主图指标并进日K', () => {

  it('[R654] 二型叠加: 上攻段底色 / 回踩带 / 首次回踩标记 / 未来三槽', () => {
    const rows = [row('2026-11-02', 10), row('2026-11-06', 11), row('2026-11-13', 12)]
    const overlay = levelFib2Overlay({
      active: new Set<LevelType>(['fib2']),
      fib2: {
        thrust: { start: '2026-11-02', end: '2026-11-06', days: 5 },
        markers: [{ date: '2026-11-13', label: '首次回踩' }],
        dma3_future: [12.1, 12.2, 12.3],
      },
      fib2Zone: { low: 11.5, high: 11.8, strength: 3 },
      rows,
      lastClose: 12,
      theme: 'dark',
      fibColor: '#8B5CF6',
      textColor: '#E4E4E7',
    })
    expect(overlay.ranges).toEqual([{
      start: '2026-11-02', end: '2026-11-06', label: '单边上攻 5 天', color: 'rgba(210,70,59,0.20)',
      // [R727] 补回基线的虚线边框 + 红色加粗标签
      borderColor: 'rgba(210,70,59,0.45)', borderType: 'dashed', labelColor: '#D2463B', labelBold: true,
    }])
    expect(overlay.priceLines.map(line => line.label)).toEqual(['', ''])
    // [R727] 回踩密集带底色带: 0.30 + 0.12×(3-1) = 0.54, 0.85 边框, 带内写区间与条数
    expect(overlay.bands).toEqual([{
      low: 11.5, high: 11.8,
      color: 'rgba(139,92,246,0.54)', borderColor: 'rgba(139,92,246,0.85)',
      label: '回踩密集带 11.50~11.80 · 3 条挤在一起', labelColor: '#8B5CF6', labelBold: true,
    }])
    // [R725] 首次回踩还原成三角, 不再写「首次回踩」四个字(R701 主图不写指标文字)
    expect(overlay.labels).toEqual([{ time: '2026-11-13', value: 13, text: '▼', color: '#8B5CF6' }])
    expect(overlay.future?.dates).toEqual(['2026-11-16', '2026-11-17', '2026-11-18'])
    expect(overlay.verticals).toEqual([{ time: '2026-11-16', label: '未来', color: '#E4E4E7' }])
    // [R726] 未来段单画一条加粗实线(不并入历史段), 从最后一根真实 K 线接上
    const curves = withFib2Future([
      { id: 'curve:fib2_dma3', type: 'Line', pane: 0, color: '#6A0DADCC', data: [{ time: '2026-11-13', value: 12 }] },
      { id: 'curve:boll_upper', type: 'Line', pane: 0, data: [{ time: '2026-11-13', value: 13 }] },
    ] as any, overlay.future)
    expect(curves.map(curve => curve.id)).toEqual(['curve:fib2_dma3', 'curve:boll_upper', 'curve:fib2_dma3_future'])
    expect(curves[0].data).toHaveLength(1)
    expect(curves[2]).toMatchObject({ lineWidth: 2, color: '#6A0DAD' })
    expect(curves[2].data).toEqual([
      { time: '2026-11-13', value: 12 },
      { time: '2026-11-16', value: 12.1 },
      { time: '2026-11-17', value: 12.2 },
      { time: '2026-11-18', value: 12.3 },
    ])
  })

  it('[R654] 二型没开时整块为空', () => {
    const overlay = levelFib2Overlay({
      active: new Set<LevelType>(), fib2: { thrust: null, dma3_future: [1] }, rows: [row('2026-11-13', 12)],
      theme: 'dark', fibColor: '#8B5CF6', textColor: '#fff',
    })
    expect(overlay).toEqual({ priceLines: [], ranges: [], labels: [], verticals: [], bands: [], future: null })
  })
})
