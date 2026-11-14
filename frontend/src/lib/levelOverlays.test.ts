import { describe, expect, it } from 'vitest'
import type { KlineRow } from '@/lib/api'
import type { LevelType } from '@/components/stock-analysis/analysis-chart-model'
import { levelFib2Overlay, levelLastPriceLine, withFib2Future } from '@/lib/levelOverlays'

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
    expect(overlay.ranges).toEqual([{ start: '2026-11-02', end: '2026-11-06', label: '单边上攻 5 天', color: 'rgba(210,70,59,0.20)' }])
    expect(overlay.priceLines.map(line => line.label)).toEqual([
      '回踩密集带下沿 11.50', '回踩密集带上沿 11.80 · 3 条挤在一起',
    ])
    expect(overlay.labels).toHaveLength(1)
    expect(overlay.future?.dates).toEqual(['2026-11-16', '2026-11-17', '2026-11-18'])
    expect(overlay.verticals).toEqual([{ time: '2026-11-16', label: '未来', color: '#E4E4E7' }])
    expect(withFib2Future([
      { id: 'curve:fib2_dma3', type: 'Line', pane: 0, data: [{ time: '2026-11-13', value: 12 }] },
      { id: 'curve:boll_upper', type: 'Line', pane: 0, data: [{ time: '2026-11-13', value: 13 }] },
    ] as any, overlay.future)[0].data).toHaveLength(4)
  })

  it('[R654] 二型没开时整块为空', () => {
    const overlay = levelFib2Overlay({
      active: new Set<LevelType>(), fib2: { thrust: null, dma3_future: [1] }, rows: [row('2026-11-13', 12)],
      theme: 'dark', fibColor: '#8B5CF6', textColor: '#fff',
    })
    expect(overlay).toEqual({ priceLines: [], ranges: [], labels: [], verticals: [], future: null })
    expect(levelLastPriceLine(12.345, '#fff')).toEqual([
      { value: 12.345, label: '现价 12.35', color: '#fff', opacity: 0.45, labelPriority: 4 },
    ])
    expect(levelLastPriceLine(null, '#fff')).toEqual([])
  })
})
