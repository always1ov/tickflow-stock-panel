// @vitest-environment jsdom
/**
 * [R397] AI 助手抽屉宽度的钳制 —— **钉算术, 不钉类名**。
 *
 * 用户截图: 手机上打开助手, 标题只剩半个、每条快捷建议的首字都被切掉。
 * 实测原因是抽屉 `width: 480` 而屏幕只有 390 —— 右缘贴齐之后左边挂出去 90px。
 *
 * 根因在这个函数里: `maxWidth = Math.max(MIN_WIDTH, vw - 64)` 的那个 `Math.max`
 * 保证了"无论如何至少 480px", 于是视口比 480 还窄时它算出来仍是 480。
 * 而调用它的那个 resize 监听, 注释写着「保证面板不越出视口」——
 * **注释承诺的事, 代码做不到**。
 *
 * 这类 bug 扫源码是抓不到的(R386 同一族: 类名一个不少, 错的是算术),
 * 所以这里直接对函数喂各种视口宽度, 断言一条性质: **返回值永不超过视口**。
 */
import { describe, it, expect, afterEach } from 'vitest'
import { clampWidth, MIN_WIDTH } from './AssistantDrawer'

const realWidth = window.innerWidth
function setViewport(w: number) {
  Object.defineProperty(window, 'innerWidth', { value: w, configurable: true, writable: true })
}
afterEach(() => setViewport(realWidth))

describe('clampWidth', () => {
  // 真机常见宽度 + 刚好卡在下限两侧的几个
  const viewports = [320, 360, 375, 390, 414, 430, 479, 480, 481, 540, 768, 834, 1024, 1280, 1440, 1920]

  it('返回值永不超过视口 —— 这条破了, 抽屉就会挂出屏幕外', () => {
    for (const vw of viewports) {
      setViewport(vw)
      for (const want of [0, 100, MIN_WIDTH, 720, 2000]) {
        const got = clampWidth(want)
        expect(got, `视口 ${vw} 要 ${want} 得到 ${got}`).toBeLessThanOrEqual(vw)
      }
    }
  })

  it('窄屏铺满整屏 —— 手机上侧边抽屉本来就该是整页的', () => {
    for (const vw of [320, 360, 375, 390, 414, 430, 479]) {
      setViewport(vw)
      expect(clampWidth(720), `视口 ${vw}`).toBe(vw)
    }
  })

  it('宽屏照旧: 不低于下限, 且给主体留出 64px', () => {
    setViewport(1440)
    expect(clampWidth(720)).toBe(720)
    expect(clampWidth(100)).toBe(MIN_WIDTH)      // 低于下限抬回下限
    expect(clampWidth(9999)).toBe(1440 - 64)     // 超宽收到"留 64px"那一档
  })

  it('刚过下限的那一段也不许越界(这一段是老实现算得最离谱的地方)', () => {
    setViewport(500)
    // 老实现: max(480, 500-64)=480, 结果 480 —— 没越界但只剩 20px 上下文;
    // 关键是它在 390 那档会算出 480 直接越界。这里钉住"永不越界"这条性质。
    expect(clampWidth(720)).toBeLessThanOrEqual(500)
  })
})
