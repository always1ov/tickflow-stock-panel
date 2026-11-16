import { describe, expect, it } from 'vitest'
import {
  RANK_BAND_COLORS,
  buildRankRows,
  formatRankDelta,
  rankColor,
  rankTextColor,
} from './rankHeatmap'

const dates = ['2026-11-13', '2026-11-12', '2026-11-11']
const columns = {
  // 每列各自按涨幅降序：下标 + 1 就是当日名次
  '2026-11-13': [
    ['影视院线', 0.0522],
    ['半导体', 0.0311],
    ['银行', 0.0104],
  ] as [string, number][],
  '2026-11-12': [
    ['半导体', 0.0402],
    ['影视院线', 0.0121],
    ['银行', -0.0068],
  ] as [string, number][],
  '2026-11-11': [
    ['银行', 0.0088],
    ['影视院线', -0.002],
    ['半导体', -0.021],
  ] as [string, number][],
}

describe('buildRankRows', () => {
  it('行按最新一日的榜单顺序，格子按各日名次回填', () => {
    const rows = buildRankRows(dates, columns)
    expect(rows.map(r => r.name)).toEqual(['影视院线', '半导体', '银行'])
    expect(rows.map(r => r.rank)).toEqual([1, 2, 3])
    // 影视院线：11-13 第 1、11-12 第 2、11-11 第 2
    expect(rows[0].cells.map(c => c?.rank)).toEqual([1, 2, 2])
    expect(rows[0].cells[0]?.pct).toBeCloseTo(0.0522)
    expect(rows[2].cells.map(c => c?.rank)).toEqual([3, 3, 1])
  })

  it('某日榜单里没有这个板块时留 null 而不是编一个名次', () => {
    const rows = buildRankRows(['2026-11-13', '2026-11-10'], columns)
    expect(rows[0].cells[1]).toBeNull()
  })

  it('topN 只截行，不裁格子', () => {
    const rows = buildRankRows(dates, columns, 2)
    expect(rows).toHaveLength(2)
    expect(rows[1].cells).toHaveLength(3)
  })

  it('没有日期时返回空数组', () => {
    expect(buildRankRows([], {})).toEqual([])
  })
})

describe('rankColor', () => {
  it('10 档、每 5 名一档，首档深红末档深绿', () => {
    expect(rankColor(1)).toBe('#E53935')
    expect(rankColor(5)).toBe('#E53935')
    expect(rankColor(6)).toBe('#F4511E')
    expect(rankColor(15)).toBe('#F57C00')
    expect(rankColor(20)).toBe('#F79803')
    expect(rankColor(35)).toBe('#CDDC39')
    expect(rankColor(50)).toBe('#2E7D31')
    // 正好 10 档，且每档 5 个名次
    expect(new Set(RANK_BAND_COLORS).size).toBe(10)
    expect(new Set(Array.from({ length: 50 }, (_, i) => rankColor(i + 1))).size).toBe(10)
  })

  it('超出 1..50 的名次夹在两端', () => {
    expect(rankColor(0)).toBe(rankColor(1))
    expect(rankColor(254)).toBe(rankColor(50))
  })

  it('传入总行数时按总量均分 10 档，榜尾不再挤成一片同色', () => {
    // 257 行 → 每档 26 名
    expect(rankColor(1, 257)).toBe('#E53935')
    expect(rankColor(26, 257)).toBe('#E53935')
    expect(rankColor(27, 257)).toBe('#F4511E')
    expect(rankColor(257, 257)).toBe('#2E7D31')
    expect(new Set(Array.from({ length: 257 }, (_, i) => rankColor(i + 1, 257))).size).toBe(10)
    // 中间四档的深色字跟着档位走，不是固定 16~35 名
    expect(rankTextColor(79, 257)).toBe('#1F2A37')
    expect(rankTextColor(78, 257)).toBe('#FFFFFF')
  })
})

describe('rankTextColor', () => {
  it('中间四档（16~35 名）底色太亮用深色字，其余用白字', () => {
    expect(rankTextColor(1)).toBe('#FFFFFF')
    expect(rankTextColor(15)).toBe('#FFFFFF')
    expect(rankTextColor(16)).toBe('#1F2A37')
    expect(rankTextColor(35)).toBe('#1F2A37')
    expect(rankTextColor(36)).toBe('#FFFFFF')
    expect(rankTextColor(254)).toBe('#FFFFFF')
  })
})

describe('formatRankDelta', () => {
  it('一位小数带符号，接近 0 的负数也保留 -0.0（与参考图一致）', () => {
    expect(formatRankDelta(0.016)).toBe('+1.6')
    expect(formatRankDelta(0.0004)).toBe('+0.0')
    expect(formatRankDelta(-0.0004)).toBe('-0.0')
    expect(formatRankDelta(-0.0098)).toBe('-1.0')
  })
})
