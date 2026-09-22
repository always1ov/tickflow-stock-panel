/**
 * [R410] 钉住「斐波那契二型到底画哪几条线」。
 *
 * 用户: 「目标1目标2失效位这些表达没能让用户抓得住重点看得懂, 而且好多根线,
 * 好难抓住之前说的做不做在哪里做, 走不走这些」。
 *
 * 减线这件事有个**安静的坏法**: 规则写歪之后图上一样清爽, 只是**把该看的那条
 * 藏起来了** —— 密集带在远处、作废线在下面, 两条都是"离现价不近"的典型。
 * 屏幕上看不出区别(本来就是要少画), 只有真到了那个价位才发现图里没有它。
 * 所以这几条必须由测试说。
 */
import { describe, it, expect } from 'vitest'
import { thinFib2 } from './AnalysisKChart'
import type { PriceLevel } from './AnalysisKChart'
import { FIB2_ROLE_RETRACE, FIB2_ROLE_TARGET, FIB2_ROLE_VOID } from '@/lib/theme'

const CLOSE = 20

function retrace(value: number, strong = false): PriceLevel {
  return {
    value, label: strong ? '深回踩' : '浅回踩', type: 'fib2',
    side: value > CLOSE ? 'resistance' : 'support',
    strength: strong ? 'strong' : 'weak', color: FIB2_ROLE_RETRACE,
  }
}
const target = (value: number): PriceLevel => ({
  value, label: '第一站', type: 'fib2', side: 'resistance',
  strength: 'medium', color: FIB2_ROLE_TARGET,
})
const voidLine = (value: number): PriceLevel => ({
  value, label: '这组作废', type: 'fib2', side: 'support',
  strength: 'strong', color: FIB2_ROLE_VOID,
})

describe('thinFib2: 画哪几条', () => {
  it('远在天边的密集带一条都不许丢', () => {
    // 密集带在 12~12.5, 现价 20 —— 按"离现价最近"这条规则它们全都轮不上,
    // 而那恰恰是提前知道它在哪最有用的情况。
    const zone = { low: 12, high: 12.5 }
    const all = [
      retrace(12.1, true), retrace(12.4, true),
      retrace(19.5), retrace(19.2), retrace(18.8), retrace(18.1), retrace(17.4),
      retrace(20.6), retrace(21.2), retrace(22.5),
    ]
    const kept = thinFib2(all, CLOSE, zone, false).map(p => p.value)
    expect(kept).toContain(12.1)
    expect(kept).toContain(12.4)
  })

  it('作废线永远留着 —— 它是「走不走」的下界', () => {
    const all = [
      voidLine(9.9),
      ...[19.6, 19.3, 19.1, 18.7, 18.2, 17.5].map(v => retrace(v)),
    ]
    const kept = thinFib2(all, CLOSE, null, false)
    expect(kept.some(p => p.color === FIB2_ROLE_VOID)).toBe(true)
  })

  it('真的少画了 —— 远处那些单独的回踩位会被挡掉', () => {
    const all = [30, 28, 26, 24, 22, 21, 19, 18, 16, 14, 12, 10].map(v => retrace(v))
    const kept = thinFib2(all, CLOSE, null, false)
    expect(kept.length).toBeLessThan(all.length)
    // 上下各留几条 —— 不能只留一侧
    expect(kept.some(p => p.value > CLOSE)).toBe(true)
    expect(kept.some(p => p.value <= CLOSE)).toBe(true)
  })

  it('离现价最近的那几条一定在', () => {
    const all = [30, 28, 26, 24, 22, 21, 19, 18, 16, 14, 12, 10].map(v => retrace(v))
    const kept = thinFib2(all, CLOSE, null, false).map(p => p.value)
    expect(kept).toContain(21)   // 上方最近
    expect(kept).toContain(19)   // 下方最近
  })

  it('推算位默认不画, 开了才画', () => {
    const all = [retrace(19), retrace(18), target(25), target(30), target(38)]
    expect(thinFib2(all, CLOSE, null, false).some(p => p.color === FIB2_ROLE_TARGET)).toBe(false)
    expect(thinFib2(all, CLOSE, null, true).filter(p => p.color === FIB2_ROLE_TARGET))
      .toHaveLength(3)
  })

  it('推算位是按角色键挑的, 不是按标签文字', () => {
    // 后端改了界面名(而 R410 正是改了一轮), 按文字挑就会静默漏掉 ——
    // 这里故意给一个"名字完全不同但角色是推算位"的条目。
    const odd: PriceLevel = { ...target(25), label: '随便叫什么' }
    expect(thinFib2([retrace(19), odd], CLOSE, null, false)
      .some(p => p.color === FIB2_ROLE_TARGET)).toBe(false)
  })

  it('顺序照后端给的来 —— 下方文字行按它排, 顺序跳来跳去比多几条还难读', () => {
    const all = [retrace(21), retrace(19), retrace(22), retrace(18)]
    const kept = thinFib2(all, CLOSE, null, false)
    const idx = kept.map(p => all.indexOf(p))
    expect(idx).toEqual([...idx].sort((a, b) => a - b))
  })

  it('拿不到现价时不敢乱藏 —— 全画出来', () => {
    const all = [30, 28, 26, 24, 22, 21, 19, 18, 16, 14, 12, 10].map(v => retrace(v))
    expect(thinFib2(all, undefined, null, true)).toHaveLength(all.length)
  })
})
