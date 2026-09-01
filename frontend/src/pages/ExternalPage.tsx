import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { AlertTriangle, ExternalLink, Globe2, RefreshCw, Settings, Sparkles } from 'lucide-react'
import { Link } from 'react-router-dom'
import { PageHeader } from '@/components/PageHeader'
import { ExternalViewRender } from '@/components/ExternalViewRender'
import { api } from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import { usePreferences } from '@/lib/useSharedQueries'

function validExternalUrl(raw: string | undefined): string | undefined {
  if (!raw) return undefined
  try {
    const url = new URL(raw)
    return url.protocol === 'http:' || url.protocol === 'https:' ? url.toString() : undefined
  } catch {
    return undefined
  }
}

function fmtTime(epoch?: number): string {
  if (!epoch) return ''
  return new Date(epoch * 1000).toLocaleTimeString('zh-CN', { hour12: false })
}

/** [R146] 「多久以前」比一个时刻更有用 —— 你要判断的是这份整理还新不新鲜 */
function fmtAge(epoch?: number): string {
  if (!epoch) return ''
  const mins = Math.floor((Date.now() / 1000 - epoch) / 60)
  if (mins < 1) return '刚刚'
  if (mins < 60) return `${mins} 分钟前`
  const hrs = Math.floor(mins / 60)
  return hrs < 24 ? `${hrs} 小时前` : `${Math.floor(hrs / 24)} 天前`
}

/**
 * [R117] 抓取模式: 后端抓原文 → 面板自己的 AI 按固定提示词整理 → 固定版式。
 * 不再用 iframe 内嵌整站, 所以对方禁不禁 iframe、是不是 SPA 都无所谓。
 * AI 结果按「地址 + 原文哈希 + 提示词」缓存在后端, 页面来回切不会重复花钱;
 * 想重新解析点「重新解析」(force)。
 */
function FetchModeBody({ hint }: { hint: string }) {
  const q = useQuery({
    queryKey: QK.externalPageView(hint),
    queryFn: () => api.externalPageView({ hint }),
    // [R146] 与后端「最近一次结果」的有效期对齐(30 分钟)。后端在这个窗口内
    // 连页面都不抓, 前端也就没必要反复发这个请求。
    staleTime: 30 * 60 * 1000,
    refetchOnWindowFocus: false,
    retry: false,
  })
  const [refreshing, setRefreshing] = useState(false)

  const reparse = async () => {
    setRefreshing(true)
    try {
      await api.externalPageView({ hint, force: true })
      await q.refetch()
    } finally {
      setRefreshing(false)
    }
  }

  if (q.isLoading) {
    return (
      <div className="grid h-full place-items-center text-sm text-muted">
        <div className="flex items-center gap-2">
          <Sparkles className="h-4 w-4 animate-pulse" />正在抓取并让 AI 整理这个页面…
        </div>
      </div>
    )
  }

  if (q.isError) {
    return (
      <div className="mx-auto max-w-2xl px-4 py-10">
        <div className="rounded-card border border-danger/30 bg-danger/5 p-5">
          <div className="flex items-center gap-2 text-sm font-medium text-danger">
            <AlertTriangle className="h-4 w-4" />这个页面没能整理出来
          </div>
          <p className="mt-2 whitespace-pre-wrap break-words text-xs leading-6 text-secondary">
            {String((q.error as Error)?.message ?? q.error)}
          </p>
          <div className="mt-4 flex flex-wrap gap-2">
            <button
              onClick={() => q.refetch()}
              className="inline-flex items-center gap-1.5 rounded-btn border border-border bg-surface px-3 py-1.5 text-xs text-secondary hover:text-foreground"
            >
              <RefreshCw className="h-3.5 w-3.5" />重试
            </button>
            <Link
              to="/settings?tab=ext-pages"
              className="inline-flex items-center gap-1.5 rounded-btn bg-accent px-3 py-1.5 text-xs font-medium text-base"
            >
              <Settings className="h-3.5 w-3.5" />去设置里改地址或提示
            </Link>
          </div>
        </div>
      </div>
    )
  }

  const data = q.data!
  return (
    <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
      <ExternalViewRender view={data.spec} />
      <div className="mt-5 flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-border pt-3 text-[11px] text-muted">
        {/* [R146] 把"多久以前"放在最前面。这一页现在**默认给的是缓存**,
            所以第一眼要能判断这份整理还新不新鲜 —— 时刻不如时长直观。 */}
        <span className="text-secondary">
          AI 整理于 {fmtTime(data.generated_at)}
          <span className="ml-1 text-muted">({fmtAge(data.generated_at)})</span>
        </span>
        <span>抓取 {fmtTime(data.fetched_at)}</span>
        {data.from_cache && (
          <span title="30 分钟内再打开这一页直接给这份结果 —— 不再抓取, 也不再调 AI。想立刻重来点右边的「重新解析」">
            缓存复用{data.cache_kind === 'source' ? '(原文未变)' : ''}
          </span>
        )}
        {data.model && <span>档位 {data.model}</span>}
        <span>原文 {data.source_chars} 字</span>
        <button
          onClick={reparse}
          disabled={refreshing}
          className="inline-flex items-center gap-1 text-accent hover:underline disabled:opacity-50"
        >
          <Sparkles className="h-3 w-3" />{refreshing ? '重新解析中…' : '重新解析(会再调一次 AI)'}
        </button>
        <span className="text-muted/70">
          外部数据仅供参考 —— 由 AI 从第三方页面整理而来, 与 A 股主链的行情/落盘完全无关
        </span>
      </div>
    </div>
  )
}

export function ExternalPage() {
  const { data: prefs, isLoading } = usePreferences()
  const [frameVersion, setFrameVersion] = useState(0)
  const [frameLoading, setFrameLoading] = useState(true)
  const url = useMemo(() => validExternalUrl(prefs?.external_page_url), [prefs?.external_page_url])
  const name = prefs?.external_page_name || '外部网页'
  const enabled = Boolean(prefs?.external_page_enabled && url)
  const host = url ? new URL(url).host : ''
  const isFetchMode = prefs?.external_page_mode === 'fetch'

  if (isLoading) {
    return <div className="grid h-full place-items-center text-sm text-muted">正在加载外部网页配置…</div>
  }

  if (!enabled) {
    return (
      <div className="grid h-full place-items-center px-6">
        <div className="max-w-md rounded-card border border-border bg-surface p-8 text-center">
          <Globe2 className="mx-auto h-9 w-9 text-muted" />
          <h1 className="mt-4 text-lg font-semibold text-foreground">外部网页未启用</h1>
          <p className="mt-2 text-sm leading-6 text-muted">请先在扩展页面设置中填写完整的 HTTP(S) 地址并启用。</p>
          <Link to="/settings?tab=ext-pages" className="mt-5 inline-flex items-center gap-1.5 rounded-btn bg-accent px-3 py-2 text-xs font-medium text-base">
            <Settings className="h-3.5 w-3.5" />前往设置
          </Link>
        </div>
      </div>
    )
  }

  return (
    <div className="flex h-full min-h-0 flex-col bg-base">
      <PageHeader
        title={name}
        subtitle={host}
        right={(
          <div className="flex items-center gap-2">
            {isFetchMode
              ? <span className="hidden items-center gap-1 text-[11px] text-muted lg:inline-flex"><Sparkles className="h-3 w-3" />抓取 + AI 整理</span>
              : <span className="hidden text-[11px] text-muted lg:inline">若页面空白，请用新窗口打开</span>}
            {!isFetchMode && (
              <button
                type="button"
                onClick={() => { setFrameLoading(true); setFrameVersion(v => v + 1) }}
                className="inline-flex items-center gap-1.5 rounded-btn border border-border bg-surface px-2.5 py-1.5 text-xs text-secondary hover:text-foreground"
              >
                <RefreshCw className="h-3.5 w-3.5" />刷新
              </button>
            )}
            <a
              href={url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 rounded-btn border border-border bg-surface px-2.5 py-1.5 text-xs text-secondary hover:text-foreground"
            >
              <ExternalLink className="h-3.5 w-3.5" />新窗口
            </a>
            <Link
              to="/settings?tab=ext-pages"
              className="rounded-btn border border-border bg-surface p-1.5 text-muted hover:text-foreground"
              title="外部网页设置"
            >
              <Settings className="h-3.5 w-3.5" />
            </Link>
          </div>
        )}
      />
      {isFetchMode ? (
        <FetchModeBody hint={prefs?.external_page_ai_hint ?? ''} />
      ) : (
        <div className="relative min-h-0 flex-1 bg-surface">
          {frameLoading && (
            <div className="absolute inset-0 z-10 grid place-items-center bg-base text-sm text-muted">正在载入 {name}…</div>
          )}
          <iframe
            key={frameVersion}
            src={url}
            title={name}
            className="h-full w-full border-0 bg-white"
            loading="eager"
            referrerPolicy="strict-origin-when-cross-origin"
            sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-popups-to-escape-sandbox allow-downloads"
            allow="fullscreen; clipboard-read; clipboard-write"
            onLoad={() => setFrameLoading(false)}
          />
        </div>
      )}
    </div>
  )
}
