import { useMemo, useState } from 'react'
import { ExternalLink, Globe2, RefreshCw, Settings } from 'lucide-react'
import { Link } from 'react-router-dom'
import { PageHeader } from '@/components/PageHeader'
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

export function ExternalPage() {
  const { data: prefs, isLoading } = usePreferences()
  const [frameVersion, setFrameVersion] = useState(0)
  const [frameLoading, setFrameLoading] = useState(true)
  const url = useMemo(() => validExternalUrl(prefs?.external_page_url), [prefs?.external_page_url])
  const name = prefs?.external_page_name || '外部网页'
  const enabled = Boolean(prefs?.external_page_enabled && url)
  const host = url ? new URL(url).host : ''

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
            <span className="hidden text-[11px] text-muted lg:inline">若页面空白，请用新窗口打开</span>
            <button
              type="button"
              onClick={() => { setFrameLoading(true); setFrameVersion(v => v + 1) }}
              className="inline-flex items-center gap-1.5 rounded-btn border border-border bg-surface px-2.5 py-1.5 text-xs text-secondary hover:text-foreground"
            >
              <RefreshCw className="h-3.5 w-3.5" />刷新
            </button>
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
    </div>
  )
}
