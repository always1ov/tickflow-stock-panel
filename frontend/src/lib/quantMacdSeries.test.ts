/**
 * [R415] 钉住「量化MACD 副图的画法照原文」。
 *
 * 数值对不对由后端那组测试(与独立的逐行翻译逐根比对)管; 这里管的是**画出来的
 * 样子**有没有抄错 —— 那类错屏幕上最难看出来: 空心画成实心、等于 0 的那根颜色
 * 判反、黄柱被压在底下、`:=` 的 MACD 柱多画了一套……看着都"像个 MACD"。
 */
import { describe, it, expect } from 'vitest'
import { alignQuantMacd, quantMacdSeries, STICK_WIDTH } from './quantMacdSeries'
import { QUANT_MACD_COLORS } from './theme'

const A = {
  diff: [-0.2, 0, 0.3, null],
  dea: [-0.1, 0, 0.2, null],
  yellow: [null, null, 0.05, null],
  gold_icon: [null, null, 0.2, null],
  dead_icon: [-0.11, null, null, null],
}
const ax = { xAxisIndex: 1, yAxisIndex: 1 }
type Pt = { value: number; itemStyle: Record<string, unknown> } | '-'

describe('量化MACD: 画法照原文', () => {
  const s = quantMacdSeries(A, 'dark', ax)
  const byName = (n: string) => s.find(x => x.name === n)!
  const C = QUANT_MACD_COLORS.dark

  it('只画原文里画的那五样 —— `:=` 的 MACD 柱不画', () => {
    expect(s.map(x => x.name)).toEqual(['DIFF', 'DEA', '金叉', '死叉', '共振'])
    expect(s.some(x => /MACD|柱1|OBV/.test(String(x.name)))).toBe(false)
  })

  it('画的先后 = 原文语句的先后: DIFF → DEA → 图标 → 黄柱', () => {
    const z = s.map(x => x.z as number)
    expect(z).toEqual([...z].sort((a, b) => a - b))
    expect(byName('共振').z).toBeGreaterThan(byName('金叉').z as number)
  })

  it('DIFF 实心: ≥0 红, <0 绿 —— 等于 0 那根算红(原文 DIFF>=0)', () => {
    const d = byName('DIFF').data as Pt[]
    expect(d[0]).toMatchObject({ itemStyle: { color: C.green } })
    expect(d[1]).toMatchObject({ itemStyle: { color: C.red } })    // DIFF == 0
    expect(d[2]).toMatchObject({ itemStyle: { color: C.red } })
    expect(d[3]).toBe('-')
  })

  it('DEA 空心: 不填充只描边; ≥0 深红, <0 绿 —— 等于 0 那根算深红', () => {
    const d = byName('DEA').data as Pt[]
    for (const p of d.slice(0, 3)) {
      expect(p).toMatchObject({ itemStyle: { color: 'transparent' } })
    }
    expect(d[0]).toMatchObject({ itemStyle: { borderColor: C.green } })
    expect(d[1]).toMatchObject({ itemStyle: { borderColor: C.darkRed } })   // DEA == 0
    expect(d[2]).toMatchObject({ itemStyle: { borderColor: C.darkRed } })
  })

  it('COLOR0000CC 是深红不是蓝(通达信 BBGGRR 序)', () => {
    for (const t of ['dark', 'light'] as const) {
      const hex = QUANT_MACD_COLORS[t].darkRed.replace('#', '')
      const [r, g, b] = [0, 2, 4].map(i => parseInt(hex.slice(i, i + 2), 16))
      expect(r).toBeGreaterThan(150)
      expect(g).toBe(0)
      expect(b).toBe(0)
    }
  })

  it('暗色主题逐字照抄通达信的四个颜色', () => {
    expect(QUANT_MACD_COLORS.dark).toEqual({
      red: '#FF0000', darkRed: '#CC0000', green: '#00FF00', yellow: '#FFFF00',
    })
  })

  it('三种柱子同宽、叠在同一个位置(原文宽度都是 2)', () => {
    for (const n of ['DIFF', 'DEA', '共振']) {
      expect(byName(n).barWidth).toBe(STICK_WIDTH)
      expect(byName(n).barGap).toBe('-100%')
    }
  })

  it('黄柱、金叉、死叉只在后端给了值的那几根出现, 高度原样', () => {
    expect(byName('共振').data).toEqual(['-', '-', 0.05, '-'])
    expect(byName('金叉').data).toEqual(['-', '-', 0.2, '-'])
    expect(byName('死叉').data).toEqual([-0.11, '-', '-', '-'])
  })

  it('金叉红色向上、死叉绿色向下(通达信图标 1 / 2)', () => {
    expect(byName('金叉')).toMatchObject({ symbol: 'arrow', itemStyle: { color: C.red } })
    expect(byName('金叉').symbolRotate ?? 0).toBe(0)
    expect(byName('死叉')).toMatchObject({ symbol: 'arrow', symbolRotate: 180, itemStyle: { color: C.green } })
  })

  it('亮色主题下每个颜色在白底上都看得见(≥3:1) —— 只压了绿和黄', () => {
    const lum = (hex: string) => {
      const [r, g, b] = [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16) / 255)
        .map(c => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4))
      return 0.2126 * r + 0.7152 * g + 0.0722 * b
    }
    const bg = lum('#F6F7FB')
    for (const [k, hex] of Object.entries(QUANT_MACD_COLORS.light)) {
      const c = (bg + 0.05) / (lum(hex) + 0.05)
      expect(c, `${k} ${hex} 对白底只有 ${c.toFixed(2)}`).toBeGreaterThanOrEqual(3)
    }
    // 两个红在白底上本来就够, 原样不动
    expect(QUANT_MACD_COLORS.light.red).toBe(QUANT_MACD_COLORS.dark.red)
    expect(QUANT_MACD_COLORS.light.darkRed).toBe(QUANT_MACD_COLORS.dark.darkRed)
  })
})

describe('量化MACD: 按日期对到图上的 x 轴', () => {
  const q = {
    dates: ['2026-09-01', '2026-09-02', '2026-09-03'],
    diff: [1, 2, 3], dea: [0.5, 1, 1.5], yellow: [null, 0.25, null],
    gold_icon: [null, 1, null], dead_icon: [null, null, null],
  }

  it('按日期取, 不按下标取 —— 图上更早的日期与「未来」空槽一律不画', () => {
    const a = alignQuantMacd(['2026-08-31', '2026-09-02', '2026-09-03', '未来1'], q)
    expect(a.diff).toEqual([null, 2, 3, null])
    expect(a.dea).toEqual([null, 1, 1.5, null])
    expect(a.yellow).toEqual([null, 0.25, null, null])
    expect(a.gold_icon).toEqual([null, 1, null, null])
  })

  it('数据还没到: 整张副图留白, 长度仍与 x 轴一致', () => {
    const a = alignQuantMacd(['2026-09-01', '2026-09-02'], undefined)
    for (const v of Object.values(a)) expect(v).toEqual([null, null])
  })
})
