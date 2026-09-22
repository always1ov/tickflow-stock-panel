/**
 * [R411] 钉住那一行字说的每一句都是**事实**, 而且**不含动词**。
 *
 * 这一行最容易发生的退化有两种, 屏幕上都看不出来:
 *   · 措辞里混进「可以买」「到位了」这类动作暗示 —— 用户明确选了「只报形态
 *     走到哪一步」, 二型从 R405 起的口径就是「只有位置, 没有动作」;
 *   · 上攻还在走的时候不说「位置每天都在变」—— 那时候聚焦点每创新高就抬一次,
 *     下面所有价位跟着挪, 照着它挂单是错的, 而图上完全看不出来。
 */
import { describe, it, expect } from 'vitest'
import { fib2Status } from './fib2Status'
import type { Fib2StatusInput, Fib2StatusLevel } from './fib2Status'
import { FIB2_ROLE_RETRACE, FIB2_ROLE_TARGET, FIB2_ROLE_VOID } from './theme'

const DATES = Array.from({ length: 10 }, (_, i) => `2026-09-${String(i + 1).padStart(2, '0')}`)

const retrace = (value: number, label = '深回踩'): Fib2StatusLevel =>
  ({ value, label, color: FIB2_ROLE_RETRACE })
const voidAt = (value: number): Fib2StatusLevel =>
  ({ value, label: '这组作废', color: FIB2_ROLE_VOID })

function input(over: Partial<Fib2StatusInput> = {}): Fib2StatusInput {
  return {
    dates: DATES,
    close: 20,
    thrust: { start: DATES[0], end: DATES[4], days: 11 },
    markers: [{ date: DATES[7], label: '首次回踩' }],
    zone: { low: 17, high: 17.4, strength: 3 },
    levels: [retrace(19), retrace(17.1), retrace(17.3), voidAt(16.5)],
    ...over,
  }
}

const line = (i: Partial<Fib2StatusInput> = {}) => (fib2Status(input(i)) ?? []).join(' · ')

describe('fib2Status: 只报形态走到哪一步', () => {
  it('没有上攻段就整条不显示', () => {
    expect(fib2Status(input({ thrust: null }))).toBeNull()
  })

  it('上攻还在走时必须说位置会变 —— 那时候照着它挂单是错的', () => {
    const s = line({ markers: [] })
    expect(s).toContain('还在走')
    expect(s).toContain('每天都在变')
  })

  it('上攻还在走时一个具体价位都不报 —— 那个数明天就不是它了', () => {
    // 冒烟时抓到的: 第一版一边说「位置每天都在变」, 一边接着报
    // 「下方最近 浅回踩 13.98」。既然结论是"现在还不能用", 就不该同时
    // 递出一个看起来能用的价格 —— 读的人会把它记住。
    const s = line({ markers: [] })
    expect(s).not.toMatch(/\d+\.\d\d/)
    expect(s).not.toContain('下方最近')
    expect(s).not.toContain('回踩密集带')
  })

  it('上攻结束后数回踩第几天', () => {
    // 首次回踩在下标 7, 一共 10 根 → 第 3 天
    expect(line()).toContain('回踩第 3 天')
    expect(line()).toContain('上攻 11 天已结束')
  })

  it('现价在密集带上方: 只报下方最近的那一条, 不报一串', () => {
    const s = line({ close: 20, zone: { low: 17, high: 17.4, strength: 3 } })
    expect(s).toContain('下方最近 深回踩 19.00')
    expect(s).not.toContain('17.10')     // 更远的那几条不进这句话
  })

  it('现价进了密集带就说在里面, 并说几条挤在一起', () => {
    const s = line({ close: 17.2 })
    expect(s).toContain('现价在回踩密集带内（3 条挤在一起）')
  })

  it('跌穿密集带但还没到作废线 —— 报作废线在哪', () => {
    const s = line({ close: 16.8 })
    expect(s).toContain('已跌穿回踩密集带')
    expect(s).toContain('这组作废 16.50')
  })

  it('跌破作废线就直说 —— 不会被"在密集带里"盖过去', () => {
    const s = line({ close: 16.0 })
    expect(s).toContain('已跌破这组作废 16.50')
    expect(s).not.toContain('回踩密集带内')
  })

  it('没有重合是一条读数, 要说出来', () => {
    const s = line({ zone: null })
    expect(s).toContain('没有重合')
  })

  it('推算位不参与这句话 —— 它默认不画, 也不该在文字里冒出来', () => {
    const s = line({
      close: 20,
      zone: null,
      levels: [retrace(19), { value: 25, label: '第一站', color: FIB2_ROLE_TARGET }],
    })
    expect(s).not.toContain('第一站')
    expect(s).not.toContain('25')
  })

  it('一个动词都没有 —— 不出买卖, 也不出"可以/应该/建议"', () => {
    const cases: Partial<Fib2StatusInput>[] = [
      {}, { markers: [] }, { close: 17.2 }, { close: 16.8 }, { close: 16.0 }, { zone: null },
    ]
    for (const c of cases) {
      const s = line(c)
      for (const w of ['买', '卖', '可以', '应该', '建议', '进场', '离场', '止盈', '止损']) {
        expect(s, `「${w}」出现在: ${s}`).not.toContain(w)
      }
    }
  })

  it('原书黑话一个都不许漏出来', () => {
    const cases: Partial<Fib2StatusInput>[] = [
      {}, { markers: [] }, { close: 17.2 }, { close: 16.0 }, { zone: null },
    ]
    for (const c of cases) {
      const s = line(c)
      for (const w of ['F3', 'F5', 'COP', 'OP', 'XOP', 'FOCUS', 'DMA']) {
        expect(s, `「${w}」出现在: ${s}`).not.toContain(w)
      }
    }
  })

  it('拿不到现价时只说上攻那一段, 不瞎编位置', () => {
    const s = line({ close: undefined })
    expect(s).toContain('上攻 11 天已结束')
    expect(s).not.toContain('下方最近')
    expect(s).not.toContain('回踩密集带内')
  })
})
