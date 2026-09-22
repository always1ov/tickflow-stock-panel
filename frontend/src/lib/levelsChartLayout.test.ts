/** [R419] 钉住「主图不许变矮」—— 副图加高只能让整张图变长, 不能从主图里抠。 */
import { describe, it, expect } from 'vitest'
import { levelsChartLayout, subPaneHeight } from './levelsChartLayout'

// R415 之前(成交量副图 90px 那一版)的主图高度, 原样照抄那时的算式
const legacyMain = (h: number) => h - 16 - 8 - 90 - 12 - 22 - 8

describe('关键价位图版面', () => {
  it('主图与换掉成交量之前逐像素相同(用户: 「不能让主图变矮」)', () => {
    for (const h of [320, 480, 520, 720]) {
      expect(levelsChartLayout(h).mainH).toBe(legacyMain(h))
    }
  })

  it('副图在主图之外另加, 整张图因此变长(弹窗里往下滚)', () => {
    for (const h of [320, 520, 720]) {
      const L = levelsChartLayout(h)
      expect(L.total).toBeGreaterThan(h)
      expect(L.total).toBe(L.subTop + L.subH + 26 + 22 + 8)
      expect(L.subTop).toBe(16 + L.mainH + 14)
    }
  })

  it('副图: 主图的 40%, 限 130~200(用户: 「副图调得太高了」)', () => {
    expect(levelsChartLayout(520).subH).toBe(146)   // 个股预览: 主图 364
    expect(levelsChartLayout(720).subH).toBe(200)   // 最大化: 主图 564, 封顶
    expect(levelsChartLayout(320).subH).toBe(130)   // 窄屏: 保底
    expect(subPaneHeight(1000)).toBe(200)
    // 副图始终比主图矮一大截
    for (const h of [320, 520, 720]) {
      const L = levelsChartLayout(h)
      if (L.mainH >= 325) expect(L.subH).toBeLessThanOrEqual(L.mainH * 0.4 + 0.5)
    }
  })
})
