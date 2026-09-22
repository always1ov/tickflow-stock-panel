/** [R420] 「未来」区: 格子铺满、交界线、看得清。 */
import { describe, it, expect } from 'vitest'
import { FUTURE_LABEL, FUTURE_ZONE, futureSlotRenderer } from './futureZone'

// 假坐标系: 每格 16px, 第 i 格中心在 i*16+8; 绘图区 y=10, 高 300
const api = (i: number) => ({
  value: () => i,
  coord: ([x]: [number, number]) => [x * 16 + 8, 0],
  size: () => [16, 0],
})
const ps = (k: number) => ({ dataIndex: k, coordSys: { y: 10, height: 300 } })
type G = { children: any[] }

describe('斐波那契二型「未来」区', () => {
  const r = futureSlotRenderer('dark', 3, '#fafafa')

  it('三格首尾相接铺满 —— R413 用 markArea 只盖到第一格中间到第三格中间', () => {
    const rects = [0, 1, 2].map(k => (r(ps(k), api(100 + k)) as G).children[0])
    expect(rects[0].shape.x).toBe(100 * 16)                          // 从第一格左沿起
    for (const k of [0, 1]) {
      expect(rects[k].shape.x + rects[k].shape.width).toBe(rects[k + 1].shape.x)  // 无缝
    }
    expect(rects[2].shape.x + rects[2].shape.width).toBe(103 * 16)  // 到第三格右沿止
    for (const x of rects) expect(x.shape).toMatchObject({ y: 10, height: 300 })
  })

  it('只在第一格左沿画一条「今天 | 未来」交界竖虚线', () => {
    const lines = [0, 1, 2].flatMap(k =>
      (r(ps(k), api(100 + k)) as G).children.filter(c => c.type === 'line'))
    expect(lines).toHaveLength(1)
    expect(lines[0].shape).toMatchObject({ x1: 1600, x2: 1600, y1: 10, y2: 310 })
    expect(lines[0].style.lineDash).toBeTruthy()
  })

  it('标签只写一次, 在中间那格, 用传进来的主文字色', () => {
    const texts = [0, 1, 2].flatMap(k =>
      (r(ps(k), api(100 + k)) as G).children.filter(c => c.type === 'text'))
    expect(texts).toHaveLength(1)
    expect(texts[0].style).toMatchObject({ text: FUTURE_LABEL, fill: '#fafafa' })
  })

  it('底色比 R413 深: 暗色 ≥ 10% 白(原 5%), 亮色 ≥ 8%(原 5%); 仍是中性色', () => {
    const a = (s: string) => Number(s.match(/,\s*([\d.]+)\)$/)![1])
    expect(a(FUTURE_ZONE.dark.fill)).toBeGreaterThanOrEqual(0.10)
    expect(a(FUTURE_ZONE.light.fill)).toBeGreaterThanOrEqual(0.08)
    for (const t of ['dark', 'light'] as const) {
      const [r0, g, b] = FUTURE_ZONE[t].fill.match(/\d+/g)!.map(Number)
      expect(Math.max(r0, g, b) - Math.min(r0, g, b)).toBeLessThanOrEqual(22)   // 无色相
    }
  })
})

describe('二型角色色: 换色前缓存里的旧键', () => {
  it('旧的洋红键 #E01DB5 按回撤位上色, 不原样画成洋红', async () => {
    const { fib2RoleColor, FIB2_ROLE_RETRACE, LEVEL_PALETTE } = await import('./theme')
    for (const t of ['light', 'dark'] as const) {
      expect(fib2RoleColor('#E01DB5', t)).toBe(LEVEL_PALETTE.fib2[t])
      expect(fib2RoleColor('#e01db5', t)).toBe(LEVEL_PALETTE.fib2[t])
      expect(fib2RoleColor(FIB2_ROLE_RETRACE, t)).toBe(LEVEL_PALETTE.fib2[t])
    }
  })

  it('标签短到三格放得下(默认缩放下三格约 23px, 9px 字最多两个)', () => {
    expect(FUTURE_LABEL.length).toBeLessThanOrEqual(2)
  })
})
