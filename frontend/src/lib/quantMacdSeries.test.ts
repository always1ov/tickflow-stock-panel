/**
 * [R415] 钉住「量化MACD 副图的画法照原文」。
 *
 * 数值对不对由后端那组测试(与独立的逐行翻译逐根比对)管; 这里管的是**画出来的
 * 样子**有没有抄错 —— 那类错屏幕上最难看出来: 空心画成实心、等于 0 的那根颜色
 * 判反、黄柱被压在底下、`:=` 的 MACD 柱多画了一套……看着都"像个 MACD"。
 */
import { describe, it, expect } from 'vitest'
import {
  alignQuantMacd, diffExposed, HOLLOW_DASH, ICON_DOWN, ICON_H, ICON_UP, quantMacdSeries, renderDiffRect,
  STICK_RATIO, STICK_WIDTH,
} from './quantMacdSeries'
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
  const s = quantMacdSeries(A, ax)
  const byName = (n: string) => s.find(x => x.name === n)!
  const C = QUANT_MACD_COLORS

  it('只画原文里画的那五样 —— `:=` 的 MACD 柱不画', () => {
    expect(s.map(x => x.name)).toEqual(['DIFF', 'DEA', '金叉', '死叉', '共振'])
    expect(s.some(x => /MACD|柱1|OBV/.test(String(x.name)))).toBe(false)
  })

  it('画的先后 = 原文语句的先后: DIFF → DEA → 图标 → 黄柱', () => {
    const z = s.map(x => x.z as number)
    expect(z).toEqual([...z].sort((a, b) => a - b))
    expect(byName('共振').z).toBeGreaterThan(byName('金叉').z as number)
  })

  it('DIFF 只画露在 DEA 空心柱外面的那一截(通达信空心柱会盖住底下的 DIFF)', () => {
    // 第 0 根同在负侧且 DIFF 更长 → 露出 DEA→DIFF; 第 1 根 DEA=0 → 整根(高 0);
    // 第 2 根同在正侧 → 露出 DEA→DIFF; 第 3 根无值 → 不画
    expect(byName('DIFF').data).toEqual([[0, -0.1, -0.2], [1, 0, 0], [2, 0.2, 0.3]])
  })

  it('露出来的那一截: 同侧更长露一截 / 同侧不够长全盖住 / 两侧分开整根露着', () => {
    expect(diffExposed(0.5, 0.2)).toEqual([0.2, 0.5])
    expect(diffExposed(-0.5, -0.2)).toEqual([-0.2, -0.5])
    expect(diffExposed(0.2, 0.5)).toBeNull()          // 死叉后: 只剩 DEA 的框
    expect(diffExposed(-0.2, -0.5)).toBeNull()
    expect(diffExposed(0.3, 0.3)).toBeNull()          // 一样长: 刚好盖满
    expect(diffExposed(0.3, -0.1)).toEqual([0, 0.3])  // 两侧分开: 空心柱盖的是另一侧
    expect(diffExposed(-0.3, 0.1)).toEqual([0, -0.3])
    expect(diffExposed(0.3, 0)).toEqual([0, 0.3])
    expect(diffExposed(0.3, null)).toEqual([0, 0.3])
    expect(diffExposed(null, 0.3)).toBeNull()
  })

  it('DIFF 那一截画成实心矩形: 宽度同别的柱子, ≥0 红 <0 绿', () => {
    // 假坐标系: 每根间距 10px, 纵向 1 个单位 = 100px, 0 在 y=100
    const api = (v: number[]) => ({
      value: (d: number) => v[d],
      coord: ([x, y]: [number, number]) => [x * 10 + 5, 100 - y * 100],
      size: () => [10, 0],
    })
    const up = renderDiffRect(null, api([2, 0.2, 0.3]))
    expect(up.shape.width).toBeCloseTo(10 * STICK_RATIO)
    expect(up.shape.x + up.shape.width / 2).toBeCloseTo(25)       // 居中在那根 K 线上
    expect(up.shape.y).toBeCloseTo(70)
    expect(up.shape.height).toBeCloseTo(10)                       // 只有 0.2→0.3 那一截
    expect(up.style.fill).toBe(C.red)
    const dn = renderDiffRect(null, api([0, -0.1, -0.2]))
    expect(dn.shape.y).toBeCloseTo(110)
    expect(dn.shape.height).toBeCloseTo(10)
    expect(dn.style.fill).toBe(C.green)
    // 颜色看 DIFF 本身, 不看那一截从哪起: DEA 在正侧、DIFF 在负侧时整根从 0 起,
    // 按起点(0)判会误判成红
    expect(renderDiffRect(null, api([1, 0, -0.3])).style.fill).toBe(C.green)
  })

  it('DEA 空心: 不填充只描边; ≥0 深红, <0 绿 —— 等于 0 那根算深红', () => {
    const d = byName('DEA').data as Pt[]
    for (const p of d.slice(0, 3)) {
      expect(p).toMatchObject({ itemStyle: { color: 'transparent' } })
    }
    for (const p of d.slice(0, 3)) {
      // 点线边框(1 点 1 空), 通达信截图实测
      expect(p).toMatchObject({ itemStyle: { borderType: HOLLOW_DASH, borderWidth: 1 } })
    }
    expect(HOLLOW_DASH).toEqual([1, 1])
    expect(d[0]).toMatchObject({ itemStyle: { borderColor: C.green } })
    expect(d[1]).toMatchObject({ itemStyle: { borderColor: C.darkRed } })   // DEA == 0
    expect(d[2]).toMatchObject({ itemStyle: { borderColor: C.darkRed } })
  })

  it('COLOR0000CC 是深红不是蓝(通达信 BBGGRR 序)', () => {
    const hex = QUANT_MACD_COLORS.darkRed.replace('#', '')
    const [r, g, b] = [0, 2, 4].map(i => parseInt(hex.slice(i, i + 2), 16))
    expect(r).toBe(0xCC)
    expect(g).toBe(0)
    expect(b).toBe(0)
  })

  it('逐字照抄通达信的颜色, 亮暗主题同一份(用户: 「颜色和柱子类型都得一样」)', () => {
    // 不按主题分: 这张表只有一份, 画法函数也不收主题参数 —— 想给亮色另配一套,
    // 得先改掉这里, 让「和通达信不一样」成为一个看得见的决定
    expect(QUANT_MACD_COLORS).toEqual({
      red: '#FF0000', darkRed: '#CC0000', green: '#00FF00', yellow: '#FFFF00',
      icon2: '#00DC00',   // 2 号图标自带的绿, 对着通达信截图量的
    })
  })

  it('三种柱子同宽、叠在同一个位置(原文宽度都是 2); 宽度 = 通达信截图实测的 66%', () => {
    expect(STICK_RATIO).toBe(0.66)
    expect(STICK_WIDTH).toBe('66%')
    for (const n of ['DEA', '共振']) {
      expect(byName(n).barWidth).toBe(STICK_WIDTH)
      expect(byName(n).barGap).toBe('-100%')
    }
    // DIFF 是自画的矩形, 宽度走同一个 STICK_RATIO(见上一条)
    expect(byName('DIFF').renderItem).toBe(renderDiffRect)
  })

  it('黄柱、金叉、死叉只在后端给了值的那几根出现, 高度原样', () => {
    expect(byName('共振').data).toEqual(['-', '-', 0.05, '-'])
    expect(byName('金叉').data).toEqual(['-', '-', 0.2, '-'])
    expect(byName('死叉').data).toEqual([-0.11, '-', '-', '-'])
  })

  it('图标 1 红色朝上、图标 2 绿色朝下, 都带箭杆, 图标顶端对准数值', () => {
    expect(byName('金叉')).toMatchObject({ symbol: ICON_UP, itemStyle: { color: C.red } })
    expect(byName('死叉')).toMatchObject({ symbol: ICON_DOWN, itemStyle: { color: C.icon2 } })
    for (const n of ['金叉', '死叉']) {
      expect(byName(n).symbolOffset).toEqual([0, ICON_H / 2])
      expect(byName(n).symbolRotate ?? 0).toBe(0)
    }
    // 朝上那个: 最高点(y=0)在箭头尖; 朝下那个: 最低点(y=18)在箭头尖 —— 都在水平中线上
    expect(ICON_UP).toMatch(/^path:\/\/M6\.5,0 /)
    expect(ICON_DOWN).toMatch(/L6\.5,18 /)
  })

  it('只画原文里的东西: 没有悬停提示、没有额外的线', () => {
    for (const x of s) expect(x.silent).toBe(true)
    expect(s.every(x => ['bar', 'scatter', 'custom'].includes(x.type as string))).toBe(true)
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
