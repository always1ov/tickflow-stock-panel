import type { ComponentType } from 'react'
import type { LucideIcon } from 'lucide-react'

export const FRONTEND_EXTENSION_API_VERSION = 1 as const

export interface FrontendSlotContextMap {
  'layout.navigation.extra': {
    collapsed: boolean
    pathname: string
  }
  /** 个股详情对话框底部扩展区 (日K/分时图表下方) */
  'stock-preview.footer': {
    symbol: string
    name: string | null
    view: 'daily' | 'intraday'
  }
  /** 自选页工具栏扩展区 (按钮行末尾) */
  'watchlist.toolbar': {
    /** 当前筛选/排序后视图中的标的 */
    symbols: string[]
    /** [R508] 自选页现在是 grid(按小分队) | table(一张表); card 已撤, 留在联合类型里只为不破坏已有扩展的类型 */
    viewMode: 'table' | 'card' | 'grid'
    selectedGroup: string
    /** 刷新自选增强数据 (扩展修改数据后调用) */
    refresh: () => void
  }
  /**
   * [R502] Minds 页「对话」一栏的正文区(占满该栏)。没有扩展注册时那一栏显示未安装提示。
   * 真实用例: AI 助手扩展从悬浮抽屉搬进这里 —— 核心页面不 import 扩展目录, 删扩展仍是整体卸载。
   */
  'minds.chat': Record<string, never>
}

export type FrontendSlotName = keyof FrontendSlotContextMap

export type FrontendSlotRegistration<K extends FrontendSlotName = FrontendSlotName> = {
  name: K
  id: string
  order?: number
  component: ComponentType<FrontendSlotContextMap[K]>
}

export interface FrontendExtensionRoute {
  id: string
  path: `/${string}`
  component: ComponentType
}

export interface FrontendExtensionNavigation {
  id: string
  routeId: string
  label: string
  icon: LucideIcon
  order?: number
  badge?: string
}

export interface FrontendExtension {
  id: string
  apiVersion: typeof FRONTEND_EXTENSION_API_VERSION
  routes?: FrontendExtensionRoute[]
  navigation?: FrontendExtensionNavigation[]
  slots?: FrontendSlotRegistration[]
}

export interface FrontendExtensionModule {
  default: FrontendExtension
}

export interface FrontendExtensionLoadError {
  source: string
  extensionId?: string
  error: string
}
