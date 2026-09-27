import { useSyncExternalStore } from 'react'

/**
 * 响应式媒体查询 hook — 视口变化触发重渲染, 服务器端渲染恒返回 false。
 * 侧边栏用它区分桌面三态 (展开/图标条/隐藏) 与移动端抽屉两种交互模型。
 */
export function useMediaQuery(query: string): boolean {
  // [R545] 没有 matchMedia 的环境(jsdom 单测、个别内嵌 WebView)按「不匹配」处理, 不整页抛错
  const supported = typeof window !== 'undefined' && typeof window.matchMedia === 'function'
  return useSyncExternalStore(
    (onChange) => {
      if (!supported) return () => {}
      const mql = window.matchMedia(query)
      mql.addEventListener('change', onChange)
      return () => mql.removeEventListener('change', onChange)
    },
    () => (supported ? window.matchMedia(query).matches : false),
    () => false,
  )
}

/** ≥768px 视口 (桌面布局)。 */
export function useIsDesktop(): boolean {
  return useMediaQuery('(min-width: 768px)')
}
