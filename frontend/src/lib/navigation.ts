import type { ReactNode } from 'react'
import { BarChart3, Brain, Globe2, Tags } from 'lucide-react'
import {
  IconWatchlist, IconStrategy, IconFactors, IconBacktest, IconStockFocus,
  IconLadder, IconConcept, IconIndustry, IconFinancials, IconMonitor,
  IconDashboard, IconRegime, IconAlert, IconPaper, IconSignals, IconReview,
  IconIndices, IconData, type BrandIconProps,
} from '@/components/BrandIcons'
import type { AnalysisMenu } from './api'
import { getFrontendExtensionNavigation } from '@/extensions/registry'

export type NavigationEntry = {
  id: string; to: string; label: string; icon: (props: BrandIconProps) => ReactNode
  type: 'builtin' | 'analysis' | 'extension'
  visible: boolean; arch?: 'core' | 'ext'; badge?: string; extensionId?: string
}

/**
 * [R598] 核心菜单沿用 fork 口径 (上游 v0.3.36 把此表抽成文件夹式导航的条目源)。
 * 根路径 `/` 在本 fork 指向虚拟账户 (R564)，因此固定置顶项由 navLayout 的
 * `HOME_NAV_ID` 指定为 `/paper`，这里不再保留上游的 `/`「看板」行。
 * 图标沿用 fork 已对齐的品牌图标族；「Minds」上游没有，用 lucide Brain 之外的
 * 品牌图标没有对应项，改由 extension 注册前的内置条目提供。
 */
export const CORE_NAVIGATION: NavigationEntry[] = [
  // [R561 同步上游] 图标使用上游 v0.3.2 的品牌图标族(描边跟随文字色, 不带紫)
  { id: '/watchlist', label: '自选', icon: IconWatchlist },
  { id: '/screener', label: '策略', icon: IconStrategy },
  { id: '/factors', label: '因子', icon: IconFactors },
  { id: '/backtest', label: '回测', icon: IconBacktest },
  { id: '/stock-analysis', label: '个股分析', icon: IconStockFocus },
  { id: '/dashboard', label: '看板', icon: IconDashboard },
  { id: '/limit-ladder', label: '连板梯队', icon: IconLadder },
  { id: '/concept-analysis', label: '概念分析', icon: IconConcept },
  { id: '/industry-analysis', label: '行业分析', icon: IconIndustry },
  { id: '/financials', label: '财务分析', icon: IconFinancials },
  { id: '/monitor', label: '监控中心', icon: IconMonitor },
  { id: '/regime', label: '宏观分析', icon: IconRegime },   // [R503] 原「市场环境」; 路由不变
  { id: '/abnormal', label: '异动监控', icon: IconAlert },
  // [R561] 上游 v0.3.2 的虚拟账户。上游菜单叫「模拟盘」, 本 fork 叫「虚拟账户」
  { id: '/paper', label: '虚拟账户', icon: IconPaper },
  { id: '/signals', label: '信号库', icon: IconSignals },
  { id: '/review', label: '复盘', icon: IconReview },
  // [fork 增强] R93 使用观察笔记 → [R180] 消息面 → [R502] Minds
  { id: '/minds', label: 'Minds', icon: Brain },
  { id: '/indices', label: '指数', icon: IconIndices },
  { id: '/data', label: '数据', icon: IconData },
].map(x => ({ ...x, to: x.id, type: 'builtin' as const, visible: true, arch: 'core' as const }))

/** [R117] 外部网页固定契约 —— 启用时作为一个扩展域页面进菜单。 */
export type ExternalPageNav = { enabled: boolean; name: string; url: string }

/** 宿主与管理页共用来源及 ID，分析页历史裸 ID 只在兼容读取时转换。 */
export function getNavigationEntries(
  menus: readonly AnalysisMenu[] = [],
  externalPage?: ExternalPageNav,
): NavigationEntry[] {
  const entries: NavigationEntry[] = [
    ...CORE_NAVIGATION,
    ...(externalPage?.enabled && externalPage.url
      ? [{
          id: '/external-page', to: '/external-page',
          label: externalPage.name || '利弗莫尔趋势', icon: Globe2,
          type: 'extension' as const, visible: true, arch: 'ext' as const,
        }]
      : []),
    ...menus.map(m => ({
      id: `/analysis/${m.id}`, to: `/analysis/${m.id}`, label: m.label,
      type: 'analysis' as const, visible: m.visible,
      icon: m.icon === 'tags' ? Tags : BarChart3, arch: 'ext' as const,
    })),
    ...getFrontendExtensionNavigation().map(item => ({
      id: item.route.path, to: item.route.path, label: item.label, icon: item.icon,
      type: 'extension' as const, visible: true, arch: 'ext' as const,
      badge: item.badge, extensionId: item.extensionId,
    })),
  ]
  return [...new Map(entries.map(x => [x.id, x])).values()]
}
