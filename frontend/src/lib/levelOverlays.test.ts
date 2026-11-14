import { describe, expect, it } from 'vitest'
import type { KlineRow, LevelSeries, PriceLevel } from '@/lib/api'
import type { LevelType } from '@/components/stock-analysis/analysis-chart-model'
import { levelCurveSeries, levelPriceLines } from '@/lib/levelOverlays'

const level = (type: LevelType, value: number, extra: Partial<PriceLevel> = {}): PriceLevel => ({
  value, label: `${type} ${value}`, type, side: 'neutral', ...extra,
})

function levels(entries: Partial<Record<LevelType, PriceLevel[]>>) {
  return entries as Record<LevelType, PriceLevel[]>
}

const row = (date: string, close: number): KlineRow => ({
  date, open: close, high: close + 1, low: close - 1, close, volume: 100,
} as KlineRow)

describe('[R653] 关键价位主图指标并进日K', () => {
  it('只收开着的价位组, 枢轴点按档位过滤', () => {
    const lines = levelPriceLines(levels({
      sr: [level('sr', 10)],
      pivot: [level('pivot', 20, { rank: 0 }), level('pivot', 21, { rank: 2 })],
      round: [level('round', 30)],
    }), new Set<LevelType>(['sr', 'pivot']), 1)
    expect(lines.map(line => line.value)).toEqual([10, 20])
    expect(lines.every(line => line.opacity === 0.9)).toBe(true)
  })

  it('通道组不出横线(它们走曲线), 弱强度线会被淡化', () => {
    const lines = levelPriceLines(levels({
      keltner_s: [level('keltner_s', 10)],
      extreme: [level('extreme', 12, { strength: 'weak' })],
    }), new Set<LevelType>(['keltner_s', 'extreme']), 1, { extreme: '#EAB308' })
    expect(lines).toHaveLength(1)
    expect(lines[0].color).toBe('#EAB308BF')
  })

  it('通道曲线只取主图那几条, 且日期与 K 线对齐', () => {
    const series: LevelSeries = { keltner_s: { upper: [11, 12], lower: [9, 10] } }
    const curves = levelCurveSeries({
      rows: [row('2026-11-10', 10), row('2026-11-11', 10.5), row('2026-11-12', 11)],
      series,
      seriesDates: ['2026-11-11', '2026-11-12'],
      active: new Set<LevelType>(['keltner_s']),
    })
    expect(curves.map(item => item.id)).toEqual(['curve:keltner_s_upper', 'curve:keltner_s_lower'])
    expect(curves[0].pane).toBe(0)
    expect(curves[0].data.map(point => ('value' in point ? point.value ?? null : null))).toEqual([null, 11, 12])
  })

  it('没开曲线组 / 没数据时返回空, 不影响日K 原有画法', () => {
    expect(levelCurveSeries({ rows: [row('2026-11-10', 10)], active: new Set<LevelType>() })).toEqual([])
    expect(levelPriceLines(undefined, new Set<LevelType>(['sr']), 1)).toEqual([])
  })
})
