import React from 'react'
import ReactDOM from 'react-dom/client'
import { RouterProvider } from 'react-router-dom'
import { QueryClient, QueryClientProvider, QueryCache } from '@tanstack/react-query'
import { MotionConfig } from 'framer-motion'
import { initializeFrontendExtensions } from './extensions/bootstrap'
import { createAppRouter } from './router'
import { api } from './lib/api'
import { QK } from './lib/queryKeys'
import './index.css'

// 全局认证拦截: 任何 query/mutation 收到 401 (未登录/会话过期) → 跳登录页。
// api.ts 的 request() 已对 401 静默 (不弹 toast), 这里统一负责跳转。
// 排除 /login 自身的请求, 避免登录页请求失败又跳登录形成死循环。
const _redirectToLogin = (() => {
  let redirecting = false
  return (err: unknown) => {
    if (redirecting) return
    if (!(err instanceof Error)) return
    const msg = err.message || ''
    // 401 (未登录/会话过期) → 跳登录页
    // 403 未初始化 (面板未设密码, 公网访问) → 也跳登录页(显示设密码提示)
    const is401 = msg.includes('未登录') || msg.includes('会话已过期') || msg.includes('401')
    const isNotInit = msg.includes('尚未初始化访问密码') || msg.includes('NOT_INITIALIZED')
    if (!is401 && !isNotInit) return
    // 已在登录页则不跳(避免死循环)
    if (window.location.pathname === '/login') return
    redirecting = true
    const redirect = encodeURIComponent(window.location.pathname + window.location.search)
    window.location.href = `/login?redirect=${redirect}`
  }
})()

const queryClient = new QueryClient({
  queryCache: new QueryCache({
    onError: (err) => _redirectToLogin(err),
  }),
  defaultOptions: {
    queries: {
      staleTime: 5_000,           // 5s 内复用,与 §4.2 Repository 不变量一致
      refetchOnWindowFocus: false,
    },
    mutations: {
      onError: (err) => _redirectToLogin(err),
    },
  },
})

// [R153] 启动并行化 —— 只改"什么时候开始", 不改"拿到什么"。
// 原来的启动是一条串行链: 入口 JS → (执行到才发现要)路由 chunk → 渲染守卫 →
// 这时才发 /api/settings → 通过后渲染 Layout → 这时才发现要 Today chunk →
// Today 挂载后才发 /api/today(这一条要好几秒)。每一环都在等上一环。
// 下面三件事把能提前的全部提前, 与 JS 下载/求值并行:
//   1. /api/settings 立刻发 —— 守卫用的是同一个 queryKey + queryFn, 到时直接
//      复用这个在途请求, 语义一字不差。
//   2. 落地在 /today 时把 /api/today 也立刻发, 并把 Today 的 chunk 预取下来。
//      staleTime 与 Today.tsx 里那条 useQuery 一致(60s), 不会造成二次拉取。
//   3. 路由模块改成静态 import(见 router.tsx createAppRouter), 少一次串行往返。
// 登录页不预取: 未登录时 401 的跳转逻辑虽会自我保护, 但没必要制造这次请求。
const _path = window.location.pathname
if (_path !== '/login') {
  void queryClient.prefetchQuery({ queryKey: QK.settings, queryFn: api.settings })
}
// [R351] 首屏预热跟着首页走: 今日总览删了, 落地页现在是模拟盘。
// `/api/today` 那份数据**仍然要预热** —— 模拟盘拿它做把握分排序与页头的市场状态。
if (_path === '/' || _path === '/lots' || _path === '/today') {
  void queryClient.prefetchQuery({
    queryKey: QK.todayOverview,
    queryFn: () => api.todayOverview(),
    staleTime: 60_000,
  })
  import('./pages/FlipPaper').catch(() => { /* 真正需要时 lazy() 会再试, 这里只是预热 */ })
}

async function bootstrap() {
  await initializeFrontendExtensions()
  const router = createAppRouter()
  ReactDOM.createRoot(document.getElementById('root')!).render(
    <React.StrictMode>
      {/* [R168] 让 115 处 framer-motion 动效也听系统的「减少动态效果」。
          index.css 里那条 prefers-reduced-motion 全局兜底**管不到这些** ——
          它只压 CSS transition/animation, 而 framer-motion 是用 JS 逐帧改行内
          style, 媒体查询碰不到。reducedMotion="user" 打开后, framer-motion 会
          自动把位移与缩放去掉、只留透明度过渡, 正好是无障碍指南要的"更少更轻,
          而不是全关"。
          放在 main.tsx 不额外增加首屏体积: framer-motion 本来就在入口 chunk 里
          (router.tsx 同步 import 了 Layout, Layout 里有 motion), 见 R153。 */}
      <MotionConfig reducedMotion="user">
        <QueryClientProvider client={queryClient}>
          <RouterProvider router={router} />
        </QueryClientProvider>
      </MotionConfig>
    </React.StrictMode>,
  )
}

void bootstrap()

/**
 * [fork R366] 注册 service worker —— 装成主屏 app 的前提条件之一。
 *
 * 它做什么(以及**不做什么**)见 `public/sw.js`: 只缓存带哈希的构建产物与页面
 * 外壳, **`/api/**` 一个字节都不碰**。
 *
 * ## 为什么放在 bootstrap 之后、而且不 await
 *
 * 注册是纯副作用, 页面不依赖它 —— 挡在首屏前面只会让首屏慢。失败也不该影响
 * 任何事: 没有 HTTPS 的环境(比如直接用 IP 访问)注册必然失败, 那时这个面板
 * 照常是个网页, 只是装不到主屏。所以 catch 掉, 不弹 toast、不报错。
 *
 * 开发时不注册: vite dev 的模块是不带哈希的, 缓存住会得到"改了代码没反应"这种
 * 最难查的现象。
 */
if (import.meta.env.PROD && 'serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch(() => {
      /* 装不上就算了 —— 这个面板本来就是个网页, SW 只是让它能上主屏 */
    })
  })
}
