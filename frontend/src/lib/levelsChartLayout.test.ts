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
      // [R486] 主图下面先是趋势量化, 再是量化MACD。[R558] 每张副图顶上多一条 18px 标题带
      expect(L.trendTop).toBe(16 + L.mainH + 14 + 18)
      expect(L.subTop).toBe(L.trendTop + L.trendH + 14 + 18)
    }
  })

  it('[R486] 趋势量化比量化MACD 高出两条字道(R559), 主图不因它变矮', () => {
    for (const h of [320, 520, 720]) {
      const L = levelsChartLayout(h)
      expect(L.trendH).toBe(L.subH + 50)
      expect(L.mainH).toBe(legacyMain(h))
    }
  })

  // [R558] 40% / 130~200 → 48% / 160~220。用户: 「感觉空间有点挤, 有些东西看不清楚了」
  it('副图: 主图的 48%, 限 160~220(R422「副图调得太高了」→ R558「空间有点挤」)', () => {
    expect(levelsChartLayout(520).subH).toBe(175)   // 个股预览: 主图 364
    expect(levelsChartLayout(720).subH).toBe(220)   // 最大化: 主图 564, 封顶
    expect(levelsChartLayout(320).subH).toBe(160)   // 窄屏: 保底
    expect(subPaneHeight(1000)).toBe(220)
    // 副图始终比主图矮一大截
    for (const h of [320, 520, 720]) {
      const L = levelsChartLayout(h)
      if (L.mainH >= 334) expect(L.subH).toBeLessThanOrEqual(L.mainH * 0.48 + 0.5)
    }
  })
})
