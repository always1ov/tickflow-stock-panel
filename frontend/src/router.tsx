import { lazy } from 'react'
import { createBrowserRouter, Navigate, useSearchParams } from 'react-router-dom'
import { Layout } from './components/Layout'
import { Onboarding } from './pages/Onboarding'
import { Auth } from './pages/Auth'
import { useSettings } from './lib/useSharedQueries'
import { Logo } from './components/Logo'
import { ExtensionBoundary } from './extensions/ExtensionBoundary'
import { RouteErrorPage } from './components/PageErrorBoundary'
import {
  finalizeFrontendExtensions,
  getFrontendExtensionLoadErrors,
  getFrontendExtensionRoutes,
} from './extensions/registry'

// 代码分割: 页面全部 lazy 加载, 避免首屏打包所有页面 (ECharts / lightweight-charts /
// framer-motion 等重库) → 大幅减小首屏 bundle。命名导出用 .then 映射为 default。
// Layout / Onboarding / Auth 为应用外壳与入口, 保持同步加载。
const Watchlist = lazy(() => import('./pages/Watchlist').then(m => ({ default: m.Watchlist })))
const Screener = lazy(() => import('./pages/Screener').then(m => ({ default: m.Screener })))
const Backtest = lazy(() => import('./pages/Backtest').then(m => ({ default: m.Backtest })))
const Factors = lazy(() => import('./pages/Factors').then(m => ({ default: m.Factors })))
const Financials = lazy(() => import('./pages/Financials').then(m => ({ default: m.Financials })))
const Data = lazy(() => import('./pages/Data').then(m => ({ default: m.Data })))
const Monitor = lazy(() => import('./pages/Monitor').then(m => ({ default: m.Monitor })))
// [R170] 仓位中心: 「我的批次」(真钱) 与「AI 操盘手」(模拟盘) 的双 tab 外壳
// [R327] AI 操盘手换成转折模拟盘 —— 纯规则, 没有 AI
const FlipPaper = lazy(() => import('./pages/FlipPaper').then(m => ({ default: m.FlipPaper })))
const Lots = lazy(() => import('./pages/Lots').then(m => ({ default: m.Lots })))   // [R183] 上游批次登记, 保留路由
const Dashboard = lazy(() => import('./pages/Dashboard').then(m => ({ default: m.Dashboard })))
const AnalysisDetail = lazy(() => import('./pages/AnalysisDetail').then(m => ({ default: m.AnalysisDetail })))
const ConceptAnalysis = lazy(() => import('./pages/ConceptAnalysis').then(m => ({ default: m.ConceptAnalysis })))
const IndustryAnalysis = lazy(() => import('./pages/IndustryAnalysis').then(m => ({ default: m.IndustryAnalysis })))
const StockAnalysis = lazy(() => import('./pages/StockAnalysis').then(m => ({ default: m.StockAnalysis })))
const Signals = lazy(() => import('./pages/Signals').then(m => ({ default: m.Signals })))
const Review = lazy(() => import('./pages/Review').then(m => ({ default: m.Review })))
const LimitUpLadder = lazy(() => import('./pages/LimitUpLadder').then(m => ({ default: m.LimitUpLadder })))
const Indices = lazy(() => import('./pages/Indices').then(m => ({ default: m.Indices })))
const Branding = lazy(() => import('./pages/Branding').then(m => ({ default: m.Branding })))
const Settings = lazy(() => import('./pages/Settings').then(m => ({ default: m.Settings })))
const Regime = lazy(() => import('./pages/Regime').then(m => ({ default: m.Regime })))
const AbnormalMoves = lazy(() => import('./pages/AbnormalMoves').then(m => ({ default: m.AbnormalMoves })))
const Dev = lazy(() => import('./pages/Dev').then(m => ({ default: m.Dev })))
const ExternalPage = lazy(() => import('./pages/ExternalPage').then(m => ({ default: m.ExternalPage })))
// [fork 增强] R93 使用观察笔记
const UsageNotes = lazy(() => import('./pages/UsageNotes').then(m => ({ default: m.UsageNotes })))

const CORE_ROUTE_PATHS = new Set([
  '/',
  '/dashboard',
  '/onboarding',
  '/login',
  '/overview',
  '/today',
  '/analysis',
  '/analysis/:menuId',
  '/concept-analysis',
  '/industry-analysis',
  '/stock-analysis',
  '/review',
  '/watchlist',
  '/screener',
  '/backtest',
  '/factors',
  '/mining',
  '/paper-trading',
  '/lots',            // [R170] 上游加 /lots 路由时漏了这一条; 它现在托管仓位中心
  '/financials',
  '/data',
  '/monitor',
  '/limit-ladder',
  '/indices',
  '/regime',
  '/abnormal',
  '/branding',
  '/settings',
  '/dev',
  '/external-page',
  '/usage-notes',
  '/settings/keys',
  '/settings/ai',
  '/settings/queries',
])

// [R153] 扩展注册表的 finalize / 取路由挪进了 createAppRouter() —— 见文件尾。

// 旧链接兼容: 挖掘已并入因子页 (/factors?tab=mining), 保留 run/candidate 等参数重定向
function MiningRedirect() {
  const [searchParams] = useSearchParams()
  const search = searchParams.toString()
  return <Navigate to={`/factors?tab=mining${search ? `&${search}` : ''}`} replace />
}

// 首次使用守卫 —— 未完成向导则重定向到 /onboarding
// 只挂在根路由上;/onboarding 本身不被守卫,避免循环重定向。
// settings 由 Layout 预取,守卫判定不产生额外请求。
function OnboardingGuard({ children }: { children: React.ReactNode }) {
  const settings = useSettings()

  // 仅首次加载(本地无缓存)时显示占位。
  // 后台重取 (isFetching) 时本地已有上一份缓存可用, 直接放行, 避免切页时整屏 logo 闪烁。
  // 防误重定向已由 Onboarding/AI 等处 invalidate 前的 setQueryData 同步缓存兜底。
  if (settings.isLoading) {
    return (
      <div className="min-h-screen bg-base grid place-items-center">
        <div className="flex flex-col items-center gap-3 text-muted">
          <Logo size={28} className="text-foreground" />
          <div className="text-xs">加载中…</div>
        </div>
      </div>
    )
  }

  // 查询出错或字段缺失时不拦截 —— 宁可放行,也不把用户卡在空白页
  if (settings.data && settings.data.onboarding_completed === false) {
    return <Navigate to="/onboarding" replace />
  }

  return <>{children}</>
}

// [R153] 从「模块顶层立即建路由」改成「调用时建」。
// 目的是让 main.tsx 可以**静态** import 本模块 —— Vite 因此把它并进入口 chunk,
// 浏览器少一次"先下入口、执行到 import() 才知道还要下路由"的串行往返。
// 顺序约束没变: 扩展注册表必须先 load 完再 finalize —— 原来靠"动态 import 排在
// await 之后"保证, 现在靠"main.tsx 在 await 之后才调用本函数"保证, 更直白。
export function createAppRouter() {
  finalizeFrontendExtensions(CORE_ROUTE_PATHS)
  const frontendExtensionRoutes = getFrontendExtensionRoutes()
  const frontendExtensionErrors = getFrontendExtensionLoadErrors()
  if (frontendExtensionErrors.length > 0) {
    console.error('部分前端扩展加载失败', frontendExtensionErrors)
  }
  // [R321] 三条顶层路由各挂一个 errorElement: 正文区的错由 Layout 里的
  // PageErrorBoundary 先接; 这里接的是**壳自己崩**与 404 —— 那两种情形下没有壳可用。
  return createBrowserRouter([
  { path: '/onboarding', element: <Onboarding />, errorElement: <RouteErrorPage /> },
  { path: '/login', element: <Auth />, errorElement: <RouteErrorPage /> },
  {
    path: '/',
    element: (
      <OnboardingGuard>
        <Layout />
      </OnboardingGuard>
    ),
    errorElement: <RouteErrorPage />,
    children: [
      // [R64] 看板从根路径挪到 /dashboard, 根路径改去决策汇聚层 —— 看板是
      // 展示型的(看一眼有概念, 但不产出可执行的东西), 不该是每次打开应用
      // 第一眼看到的那一页。
      //
      // [R351] 那个决策汇聚层从今日总览换成了模拟盘: 今日总览的内容已经
      // 逐块融进模拟盘(R341~R350), 这一页删掉了。
      { index: true, element: <Navigate to="/lots" replace /> },
      { path: 'dashboard', element: <Dashboard /> },
      { path: 'overview', element: <Navigate to="/dashboard" replace /> },
      // [R351] 今日总览删了, 但**路由保留成重定向** —— 书签、菜单设置里存的
      // 旧路径不能断(R170 对 /paper-trading 立的同一条规矩)。
      { path: 'today', element: <Navigate to="/lots" replace /> },
      { path: 'analysis', element: <Navigate to="/settings?tab=ext-pages" replace /> },
      { path: 'analysis/:menuId', element: <AnalysisDetail /> },
      { path: 'concept-analysis', element: <ConceptAnalysis /> },
      { path: 'industry-analysis', element: <IndustryAnalysis /> },
      { path: 'stock-analysis', element: <StockAnalysis /> },
      { path: 'review', element: <Review /> },
      { path: 'watchlist', element: <Watchlist /> },
      { path: 'screener', element: <Screener /> },
      { path: 'backtest', element: <Backtest /> },
      { path: 'factors', element: <Factors /> },
      // 上游把挖掘并进了因子页; 这条重定向让老书签(带 run/candidate 参数)仍然可用
      { path: 'mining', element: <MiningRedirect /> },
      // [R170] AI 操盘手并入仓位中心。路由保留并重定向: 书签、菜单设置里存的旧路径不能断。
      { path: 'paper-trading', element: <Navigate to="/lots" replace /> },   // [R327] 旧入口照旧指过来
      { path: 'financials', element: <Financials /> },
      { path: 'data', element: <Data /> },
      { path: 'monitor', element: <Monitor /> },
      // [R327] /lots 现在是**转折模拟盘**。路由保留不改名: 书签、菜单设置里
      // 存的都是这个路径, 改名等于把用户存的入口作废。
      { path: 'lots', element: <FlipPaper /> },
      // 上游的批次登记页保留一条自己的路由 —— 代码一行没动, 只是不在导航里。
      // 哪天想用回真钱批次登记, 它原封不动还在。
      { path: 'lots-registry', element: <Lots /> },
      { path: 'signals', element: <Signals /> },
      { path: 'limit-ladder', element: <LimitUpLadder /> },
      { path: 'indices', element: <Indices /> },
      { path: 'regime', element: <Regime /> },
      { path: 'abnormal', element: <AbnormalMoves /> },
      { path: 'external-page', element: <ExternalPage /> },
      { path: 'usage-notes', element: <UsageNotes /> },
      { path: 'branding', element: <Branding /> },
      { path: 'settings', element: <Settings /> },
      // 隐藏路由：开发者工具（不暴露在菜单，仅供调试）
      { path: 'dev', element: <Dev /> },
      // 旧路由兼容重定向
      { path: 'settings/keys', element: <Navigate to="/settings?tab=data-sources" replace /> },
      { path: 'settings/ai', element: <Navigate to="/settings?tab=ai" replace /> },
      { path: 'settings/queries', element: <Navigate to="/settings?tab=queries" replace /> },
      ...frontendExtensionRoutes.map(route => {
        const ExtensionPage = route.component
        return {
          path: route.path.slice(1),
          element: (
            <ExtensionBoundary extensionId={route.extensionId}>
              <ExtensionPage />
            </ExtensionBoundary>
          ),
        }
      }),
    ],
  },
  ])
}
