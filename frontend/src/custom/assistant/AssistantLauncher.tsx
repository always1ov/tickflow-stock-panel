/**
 * AI 助手宿主 — 挂载于 layout.navigation.extra 插槽(全站常驻渲染点),
 * 但不在侧栏菜单里渲染任何入口。负责全局快捷键 ⌘K/Ctrl+K、按当前路由上报页面上下文。
 *
 * [R502 · fork] 悬浮球、AI 配置徽标旁的小入口、右缘滑入的抽屉三件套都去掉了 ——
 * 对话搬进 Minds 页的「对话」一栏(见 extension.tsx 的 minds.chat 插槽), 入口就是
 * 左侧菜单的 Minds。⌘K/Ctrl+K 从「开关抽屉」改成「跳到那一栏」; Esc 没有要关的东西了。
 */
import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import type { FrontendSlotContextMap } from '@/extensions/types'
import { setPageContext } from './store'

// 插槽注册表把组件 props 定为所有插槽上下文的联合类型(保守契约);
// 本组件只在 layout.navigation.extra 渲染, 在此收窄到该插槽的上下文。
type NavigationContext = FrontendSlotContextMap['layout.navigation.extra']
type AnySlotContext = FrontendSlotContextMap[keyof FrontendSlotContextMap]

/** Minds 页「对话」一栏的地址 —— 快捷键跳过去的地方。 */
export const CHAT_PATH = '/minds?tab=chat'

// 与核心侧栏导航文案保持一致的轻量映射(仅用于上下文提示, 展示不走这里)。
const PAGE_LABELS: Record<string, string> = {
  '/': '看板',
  '/watchlist': '自选',
  '/screener': '策略',
  '/factors': '因子',
  '/backtest': '回测',
  '/stock-analysis': '个股分析',
  '/limit-ladder': '连板梯队',
  '/concept-analysis': '概念分析',
  '/industry-analysis': '行业分析',
  '/financials': '财务分析',
  '/monitor': '监控中心',
  '/regime': '市场环境',
  '/abnormal': '异动监控',
  '/lots': '持仓提醒',
  '/signals': '信号库',
  '/review': '复盘',
  '/indices': '指数',
  '/data': '数据',
  '/settings': '设置',
}

export function AssistantLauncher(props: AnySlotContext) {
  const { pathname } = props as NavigationContext
  const navigate = useNavigate()

  useEffect(() => {
    setPageContext({ page: PAGE_LABELS[pathname] ?? '' })
  }, [pathname])

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault()
        // 已在 Minds 里就替换当前记录, 不在历史里堆一串同一个地址;
        // 换了记录 location.key 就变, 输入框据此重新聚焦(见 AssistantDrawer 的 InputArea)。
        navigate(CHAT_PATH, { replace: pathname === '/minds' })
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [navigate, pathname])

  return null
}
