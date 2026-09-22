/**
 * [R401] 钉住「图例在手机上排得下一行」。
 *
 * 这条守卫钉的是**一个会随内容变化而重新破掉的不变式**: 今天六个图例项刚好
 * 排得下, 明天有人加第七条曲线, 图例又会折到第二行、又一次画进绘图区 ——
 * 而那件事**在桌面上看不出来**(桌面宽一倍, 七八个也排得下)。
 * 所以它必须由测试说, 不能靠下一个人碰巧用手机打开过这一页。
 */
import { describe, it, expect } from 'vitest'
import { legendItemWidth, legendRows, COMPACT_LEGEND } from './echartsLegend'
import { PHASE_LEGEND, TREND_LEGEND } from '@/pages/Regime'

/**
 * 375px 手机上这两张图的可用宽度:
 *   375 − 页面左右留白 12×2(PageShell 的 `px-3`) − 卡片内边距 12×2(`p-3`) = 327
 * 这是**最窄的一档** —— 比 375 更窄的手机基本不存在, 再宽只会更宽松。
 */
const NARROW_CHART_WIDTH = 327

describe('图例在最窄的手机上也排得下一行', () => {
  it('环境综合分趋势(六项)', () => {
    expect(legendRows(TREND_LEGEND, NARROW_CHART_WIDTH, COMPACT_LEGEND)).toBe(1)
  })

  it('情绪周期时间轴(五项)', () => {
    expect(legendRows(PHASE_LEGEND, NARROW_CHART_WIDTH, COMPACT_LEGEND)).toBe(1)
  })

  it('还剩一项的余量; 第八项就折行 —— 这条是留给下一个加曲线的人的', () => {
    // **边界是量出来的**: 同样 327px, 真浏览器里跑 ECharts 的结果是
    // 7 项跨度 292px 仍一行、8 项 2 行, 与下面这两条断言一致。
    // 不是"多加就一定不行", 而是"多加之前回来量一次": 折了行就得同时把
    // `LEGEND_GRID_TOP` 往下调, 否则第二行会画进绘图区。
    expect(legendRows([...TREND_LEGEND, '换手'], NARROW_CHART_WIDTH, COMPACT_LEGEND)).toBe(1)
    expect(legendRows([...TREND_LEGEND, '换手', '情绪'], NARROW_CHART_WIDTH, COMPACT_LEGEND)).toBe(2)
  })

  it('用 ECharts 的默认取值就会折行 —— 这正是这次修的那个 bug', () => {
    // 默认 itemWidth=25 / itemGap=10。真浏览器里量过: 六项里「趋势」被挤到
    // 第二行 y=29, 而 grid.top 当时是 36 —— 第二行就落进了绘图区。
    expect(legendRows(TREND_LEGEND, NARROW_CHART_WIDTH)).toBe(2)
  })
})

describe('项宽的算法', () => {
  it('中文按一个字宽, 数字/字母按六成', () => {
    const cn = legendItemWidth('赚钱', 10, 10)       // 10 + 5 + 2×10
    const en = legendItemWidth('ab', 10, 10)         // 10 + 5 + 2×6
    expect(cn).toBe(35)
    expect(en).toBe(27)
    expect(cn).toBeGreaterThan(en)
  })

  it('混排按字符逐个算 —— 「2板+」是数字+中文+符号', () => {
    // 10 + 5 + (6 + 10 + 6) = 37
    expect(legendItemWidth('2板+', 10, 10)).toBe(37)
  })

  it('空列表是 0 行, 不是 1 行', () => {
    expect(legendRows([], NARROW_CHART_WIDTH, COMPACT_LEGEND)).toBe(0)
  })

  it('一项再长也只占一行 —— 排不下也不该报成两行', () => {
    expect(legendRows(['非常非常非常长的一个图例名'], 40, COMPACT_LEGEND)).toBe(1)
  })
})
