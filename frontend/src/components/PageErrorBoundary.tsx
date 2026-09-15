/**
 * [fork 增强 R321] 防白屏 —— 一页渲染崩了, 只坏这一页, 侧栏与别的页照常。
 *
 * 之前整个应用没有任何一层 ErrorBoundary(只有扩展页有自己那层)。React 的规矩是
 * 渲染期抛错、又没有边界接住 → **整棵树卸载**, 用户看到的就是一张白页, 唯一能
 * 做的是刷新, 而且不知道是哪一页坏的。一个接口少回一个字段就够触发这条路。
 *
 * 两层, 各接各的:
 *
 *   · `PageErrorBoundary` —— 包在 Layout 的 `<Outlet/>` 外面(Suspense 之外, 所以
 *     lazy chunk 下载失败也归它)。坏了只换掉正文区, 壳还在。**按路径复位**:
 *     `resetKey` 一变(用户点了别的页)就清掉错误重新渲染 —— 边界不复位的话,
 *     点到哪一页都还是那张错误卡, 比白屏好不了多少。
 *   · `RouteErrorPage` —— 挂在 router 的 `errorElement` 上, 接 Layout 自己崩、
 *     以及没匹配到路由的 404。这一层没有壳可用(壳就是崩的那个), 所以整页画。
 *
 * 错误卡不做动效: 它是坏消息, 不该"登场"。
 */
import { Component, type ErrorInfo, type ReactNode } from 'react'
import { Link, isRouteErrorResponse, useRouteError } from 'react-router-dom'
import { AlertTriangle, RefreshCw, RotateCcw } from 'lucide-react'

/**
 * 部署过后老页面里的 lazy() 去拿一个已经不存在的 chunk —— 各浏览器的报错原文不同,
 * 这里只认几个稳定的片段。这种错**刷新一下就好**, 要与真正的渲染 bug 分开说。
 */
export function isStaleChunkError(err: unknown): boolean {
  if (!(err instanceof Error)) return false
  const m = `${err.name} ${err.message}`
  return m.includes('ChunkLoadError')
    || m.includes('dynamically imported module')
    || m.includes('Importing a module script failed')
    || m.includes('Loading chunk')
}

function describe(err: unknown): string {
  if (err instanceof Error) return err.message || err.name
  if (typeof err === 'string') return err
  try { return JSON.stringify(err) } catch { return String(err) }
}

export function ErrorCard({ error, onRetry, homeLink }: {
  error: unknown
  /** 给了就画「重试」—— 只有边界那一层能原地重试; 路由那层没有可回退的树 */
  onRetry?: () => void
  /** 给了就画「回到模拟盘」—— 只在没有壳的整页错误上要 */
  homeLink?: boolean
}) {
  const stale = isStaleChunkError(error)
  return (
    <div
      role="alert"
      className="mx-auto my-16 w-[92vw] max-w-md rounded-card border border-border bg-surface p-5 shadow-sm"
    >
      <div className="flex items-start gap-3">
        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warning" />
        <div className="min-w-0 flex-1">
          <div className="text-sm font-medium text-foreground">
            {stale ? '页面代码已更新, 刷新一下就好' : '这一页出了点问题'}
          </div>
          <p className="mt-1 text-xs leading-relaxed text-secondary">
            {stale
              ? '服务端刚部署了新版本, 浏览器里还是旧的一份, 两边对不上。刷新后就是新版。'
              : '只是这一页没画出来 —— 其他页面不受影响, 侧栏照常可用。'}
          </p>
          {!stale && (
            <pre className="mt-2 max-h-24 overflow-auto whitespace-pre-wrap break-all rounded-btn bg-elevated/60 px-2 py-1.5 font-mono text-[10px] leading-relaxed text-muted">
              {describe(error)}
            </pre>
          )}
          <div className="mt-3 flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => window.location.reload()}
              className="inline-flex items-center gap-1 rounded-btn border border-accent/40 bg-accent/10 px-2.5 py-1 text-xs text-accent hover:bg-accent/20 transition-colors cursor-pointer"
            >
              <RefreshCw className="h-3 w-3" />刷新页面
            </button>
            {onRetry && !stale && (
              <button
                type="button"
                onClick={onRetry}
                className="inline-flex items-center gap-1 rounded-btn border border-border px-2.5 py-1 text-xs text-secondary hover:bg-elevated hover:text-foreground transition-colors cursor-pointer"
              >
                <RotateCcw className="h-3 w-3" />重试
              </button>
            )}
            {homeLink && (
              <Link
                to="/lots"
                className="inline-flex items-center rounded-btn border border-border px-2.5 py-1 text-xs text-secondary hover:bg-elevated hover:text-foreground transition-colors"
              >
                回到模拟盘
              </Link>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

interface Props {
  children: ReactNode
  /** 一变就复位 —— Layout 传的是 `location.pathname` */
  resetKey: string
}

interface State {
  error: unknown | null
}

export class PageErrorBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: unknown): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('页面渲染失败', error, info.componentStack)
  }

  componentDidUpdate(prev: Props) {
    // 换了页就放手让新页渲染; 新页要是也崩, 会再进一次 getDerivedStateFromError。
    if (this.state.error !== null && prev.resetKey !== this.props.resetKey) {
      this.setState({ error: null })
    }
  }

  render() {
    if (this.state.error === null) return this.props.children
    return <ErrorCard error={this.state.error} onRetry={() => this.setState({ error: null })} />
  }
}

/** router `errorElement`: Layout 自己崩了、或路径没匹配到 —— 没有壳, 整页画。 */
export function RouteErrorPage() {
  const err = useRouteError()
  const notFound = isRouteErrorResponse(err) && err.status === 404
  if (!notFound) console.error('路由级错误', err)
  return (
    <div className="min-h-screen bg-base">
      {notFound ? (
        <div role="alert" className="mx-auto my-16 w-[92vw] max-w-md rounded-card border border-border bg-surface p-5 shadow-sm">
          <div className="text-sm font-medium text-foreground">没有这一页</div>
          <p className="mt-1 text-xs leading-relaxed text-secondary">
            地址 <span className="font-mono text-muted">{window.location.pathname}</span> 不对应任何页面 —— 可能是旧书签。
          </p>
          <div className="mt-3">
            <Link
              to="/lots"
              className="inline-flex items-center rounded-btn border border-accent/40 bg-accent/10 px-2.5 py-1 text-xs text-accent hover:bg-accent/20 transition-colors"
            >
              回到模拟盘
            </Link>
          </div>
        </div>
      ) : (
        <ErrorCard error={err} homeLink />
      )}
    </div>
  )
}
