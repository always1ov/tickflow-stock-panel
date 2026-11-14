/**
 * [R640] 钉住 `PaneDecor` 的 `label` 图元(参考线右端名字)的**画法**。
 *
 * 之前的守卫只断言 `AnalysisKChart` 里 push 了那两条 `kind: 'label'` —— 只要有人把
 * 绘制分支挪到柱子前面、或者把 x 从"右边贴边"改成跟日期走, 字符串断言照样绿。
 * 这里用一个记账版 canvas context 跑真实的 `draw`, 断言真正落到画布上的坐标与顺序。
 */
import { describe, expect, it } from 'vitest'
import { LANE_HALO } from '@/lib/trendQuantSeries'
import { PaneDecor, type DecorItem } from './SubPaneDecor'

const WIDTH = 300
const HEIGHT = 120
/** 假 series 的纵向换算: 超买线 3.2 在 y=34, 超卖线 0.5 在 y=96。 */
const Y: Record<number, number> = { 3.2: 34, 0.5: 96 }
const DATE_X = 50

interface Call {
  op: string
  args: unknown[]
  align?: string
  baseline?: string
  color?: string
  width?: number
}

function makeCanvas() {
  const calls: Call[] = []
  const ctx = {
    font: '', textAlign: '', textBaseline: '', fillStyle: '', strokeStyle: '',
    lineWidth: 1, globalAlpha: 1,
    save() {}, restore() {}, beginPath() {}, rect() {}, clip() {},
    translate() {}, fill() {}, stroke() {}, moveTo() {}, lineTo() {}, setLineDash() {},
    measureText: (text: string) => ({ width: text.length * 6 }),
    fillRect: (...args: unknown[]) => { calls.push({ op: 'fillRect', args, color: ctx.fillStyle }) },
    strokeRect: (...args: unknown[]) => { calls.push({ op: 'strokeRect', args }) },
    fillText(text: string, x: number, y: number) {
      calls.push({
        op: 'fillText', args: [text, x, y],
        align: ctx.textAlign, baseline: ctx.textBaseline, color: ctx.fillStyle,
      })
    },
    strokeText(text: string, x: number, y: number) {
      calls.push({
        op: 'strokeText', args: [text, x, y],
        color: ctx.strokeStyle, width: ctx.lineWidth,
      })
    },
  }
  return { ctx, calls }
}

function draw(items: DecorItem[]) {
  const { ctx, calls } = makeCanvas()
  const decor = new PaneDecor()
  decor.attached({
    chart: {
      timeScale: () => ({
        timeToCoordinate: (time: string) => (time === '2026-01-05' ? DATE_X : null),
        options: () => ({ barSpacing: 10 }),
      }),
    },
    series: { priceToCoordinate: (value: number) => Y[value] ?? null },
    requestUpdate: () => {},
  } as never)
  decor.update({ items })
  const view = decor.paneViews()[0]!
  view.renderer()!.draw({
    useMediaCoordinateSpace: (cb: (scope: unknown) => void) => cb({
      context: ctx, mediaSize: { width: WIDTH, height: HEIGHT },
    }),
  } as never)
  return calls
}

describe('[R640] PaneDecor 的 label 图元: 贴右边、对准线的高度、最后画', () => {
  it('名字贴副图右边 4px, 纵向对准它那条线的值; 右对齐 + 垂直居中', () => {
    const calls = draw([{ kind: 'label', value: 3.2, text: '超买', color: '#FFFF00' }])
    const fill = calls.find(c => c.op === 'fillText' && c.args[0] === '超买')!
    expect(fill.args[1]).toBe(WIDTH - 4)
    expect(fill.args[2]).toBe(34)
    expect(fill.align).toBe('right')
    expect(fill.baseline).toBe('middle')
    expect(fill.color).toBe('#FFFF00')
  })

  it('不跟日期走: 同一条副图上的柱子在 x=50, 名字仍在 x=296', () => {
    const calls = draw([
      { kind: 'stick', time: '2026-01-05', from: 0.5, to: 3.2, color: '#00FF00', ratio: 0.66 },
      { kind: 'label', value: 0.5, text: '超卖', color: '#FFFF00' },
    ])
    expect(calls.find(c => c.op === 'fillRect')!.args[0]).toBeCloseTo(DATE_X - 10 * 0.66 / 2)
    const fill = calls.find(c => c.op === 'fillText' && c.args[0] === '超卖')!
    expect(fill.args[1]).toBe(WIDTH - 4)
    expect(fill.args[2]).toBe(96)
  })

  it('压在柱子和信号字上面: 先画柱子, 再写名字', () => {
    const calls = draw([
      { kind: 'stick', time: '2026-01-05', from: 0.5, to: 3.2, color: '#00FF00', ratio: 0.66 },
      { kind: 'text', time: '2026-01-05', text: '顶', color: '#FF0000', lane: 'top' },
      { kind: 'label', value: 3.2, text: '超买', color: '#FFFF00' },
    ])
    const stick = calls.findIndex(c => c.op === 'fillRect')
    const text = calls.findIndex(c => c.op === 'fillText' && c.args[0] === '顶')
    const label = calls.findIndex(c => c.op === 'fillText' && c.args[0] === '超买')
    expect(stick).toBeLessThan(label)
    expect(text).toBeLessThan(label)
  })

  it('垫一层黑描边当光晕(白底黄字才看得见), 描边先于填色', () => {
    const calls = draw([{ kind: 'label', value: 3.2, text: '超买', color: '#FFFF00' }])
    const stroke = calls.find(c => c.op === 'strokeText' && c.args[0] === '超买')!
    const fill = calls.find(c => c.op === 'fillText' && c.args[0] === '超买')!
    expect(stroke.color).toBe(LANE_HALO.stroke)
    expect(stroke.width).toBe(LANE_HALO.lineWidth)
    expect(calls.indexOf(stroke)).toBeLessThan(calls.indexOf(fill))
  })

  it('[R641] 名字脚下先铺半透明暗底, 让挤过来的信号字不透过来', () => {
    const calls = draw([{ kind: 'label', value: 3.2, text: '超买', color: '#FFFF00' }])
    const bgIndex = calls.findIndex(c => c.op === 'fillRect' && c.color === 'rgba(0, 0, 0, 0.55)')
    expect(bgIndex).toBeGreaterThanOrEqual(0)
    const bg = calls[bgIndex]!
    // 右边贴到 width-1, 横向盖住整段文字(两侧各 3px)
    expect((bg.args[0] as number) + (bg.args[2] as number)).toBeCloseTo(WIDTH - 1)
    expect(calls.findIndex(c => c.op === 'strokeText')).toBeGreaterThan(bgIndex)
  })

  it('这个值画不出来(priceToCoordinate 返回 null)就跳过, 不抛错', () => {
    const calls = draw([{ kind: 'label', value: 9.9, text: '超买', color: '#FFFF00' }])
    expect(calls.some(c => c.op === 'fillText' || c.op === 'strokeText')).toBe(false)
  })
})
