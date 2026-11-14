/**
 * [R415] 钉住「量化MACD 副图的画法照原文」。
 *
 * 数值对不对由后端那组测试(与独立的逐行翻译逐根比对)管; 这里管的是**画出来的
 * 样子**有没有抄错 —— 那类错屏幕上最难看出来: 空心画成实心、等于 0 的那根颜色
 * 判反、黄柱被压在底下、`:=` 的 MACD 柱多画了一套……看着都"像个 MACD"。
 *
 * [R638] 原先这里断言的是 ECharts 版的系列数组(itemStyle / renderItem / symbol),
 * 那套构造器在 R616 换成 lightweight 后已无人调用, 测试守的是一条死路。现在只断言
 * 真正还在产码里用的东西: 对齐函数、色表、柱宽比例、图标路径、图例键与读数字段同名。
 */
import { describe, it, expect } from 'vitest'
import {
  alignQuantMacd, diffExposed, HOLLOW_DASH, ICON_DOWN, ICON_H, ICON_UP,
  STICK_RATIO, QUANT_MACD_HELP, QUANT_MACD_LEGEND,
} from './quantMacdSeries'
import { QUANT_MACD_COLORS } from './theme'

describe('量化MACD: 画法照原文', () => {
  const C = QUANT_MACD_COLORS

  it('DIFF 只画露在 DEA 空心柱外面的那一截(通达信空心柱会盖住底下的 DIFF)', () => {
    // 同侧更长露一截 / 同侧不够长全盖住 / 两侧分开整根露着 / 一样长刚好盖满
    expect(diffExposed(0.5, 0.2)).toEqual([0.2, 0.5])
    expect(diffExposed(-0.5, -0.2)).toEqual([-0.2, -0.5])
    expect(diffExposed(0.2, 0.5)).toBeNull()          // 死叉后: 只剩 DEA 的框
    expect(diffExposed(-0.2, -0.5)).toBeNull()
    expect(diffExposed(0.3, 0.3)).toBeNull()
    expect(diffExposed(0.3, -0.1)).toEqual([0, 0.3])  // 两侧分开: 空心柱盖的是另一侧
    expect(diffExposed(-0.3, 0.1)).toEqual([0, -0.3])
    expect(diffExposed(0.3, 0)).toEqual([0, 0.3])
    expect(diffExposed(0.3, null)).toEqual([0, 0.3])
    expect(diffExposed(null, 0.3)).toBeNull()
  })

  it('DEA 空心柱用 1 点 1 空的点线边框(通达信截图实测)', () => {
    expect(HOLLOW_DASH).toEqual([1, 1])
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
      paneBg: '#000000',  // 通达信的底色; 亮色主题下副图铺这个底
    })
  })

  it('三种柱子同宽: 宽度 = 通达信截图实测的 66%', () => {
    expect(STICK_RATIO).toBe(0.66)
    // DIFF 的实心矩形、DEA 的空心框、共振黄柱都按这个比例算宽(PaneDecor 的 stick/hollow)
    expect(C.yellow).toBe('#FFFF00')
  })

  it('图标 1 红色朝上、图标 2 绿色朝下, 顶端对准数值', () => {
    // 朝上那个: 最高点(y=0)在箭头尖; 朝下那个: 最低点(y=18)在箭头尖 —— 都在水平中线上
    expect(ICON_UP).toMatch(/^path:\/\/M6\.5,0 /)
    expect(ICON_DOWN).toMatch(/L6\.5,18 /)
    expect(ICON_H).toBe(18)
    expect(C.red).toBe('#FF0000')
    expect(C.icon2).toBe('#00DC00')
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

  it('[R560] 图例五项, 与对齐出来的五组数一一对应; 悬停说明五段', () => {
    const a = alignQuantMacd([], undefined)
    expect(QUANT_MACD_LEGEND.map(l => l.name)).toEqual(['DIFF', 'DEA', '共振', '金叉', '死叉'])
    // 图例五项 ↔ 读数字段的五个来源; 多一项是空图例, 少一项是有线没名字
    expect(Object.keys(a)).toEqual(['diff', 'dea', 'yellow', 'gold_icon', 'dead_icon'])
    expect(QUANT_MACD_LEGEND).toHaveLength(Object.keys(a).length)
    expect(QUANT_MACD_HELP.split('\n\n')).toHaveLength(5)
  })
})
