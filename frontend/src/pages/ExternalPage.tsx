import { ExternalLink, Globe2, Settings } from 'lucide-react'
import { Link } from 'react-router-dom'
import { PageHeader } from '@/components/PageHeader'
import { buttonClass } from '@/components/ui'
import { usePreferences } from '@/lib/useSharedQueries'

/** 只取域名做副标题；地址不合法时原样显示，避免整页因为一条脏数据崩掉 */
function hostOf(raw: string): string {
  try {
    return new URL(raw).host
  } catch {
    return raw
  }
}

/**
 * [R611] 外链导航：只列链接，点开新标签。
 * 不再内嵌 iframe，也不做抓取 + AI 整理 —— 页面自身零外部请求。
 */
export function ExternalPage() {
  const { data: prefs, isLoading } = usePreferences()
  const name = prefs?.external_page_name || '外链导航'
  const links = prefs?.external_links ?? []

  if (isLoading) {
    return <div className="grid h-full place-items-center text-sm text-muted">正在加载链接…</div>
  }

  return (
    <div className="flex h-full min-h-0 flex-col bg-base">
      <PageHeader
        title={name}
        subtitle={links.length > 0 ? `${links.length} 个链接` : '还没有链接'}
        right={(
          <Link
            to="/settings?tab=ext-pages"
            className="inline-flex items-center gap-1.5 rounded-btn border border-border bg-surface px-2.5 py-1.5 text-xs text-secondary hover:text-foreground"
          >
            <Settings className="h-3.5 w-3.5" />管理链接
          </Link>
        )}
      />
      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
        <div className="mx-auto w-full max-w-wide">
          {links.length === 0 ? (
            <div className="rounded-card border border-dashed border-border bg-surface p-10 text-center">
              <Globe2 className="mx-auto h-9 w-9 text-muted" />
              <h2 className="mt-4 text-title font-semibold text-foreground">还没有添加链接</h2>
              <p className="mt-2 text-xs leading-6 text-muted">
                在设置里把常看的站点加进来，这里会按卡片列出来，点一下就在新标签打开。
              </p>
              <Link to="/settings?tab=ext-pages" className={buttonClass({ variant: 'primary' }, 'mt-5 gap-1.5')}>
                <Settings className="h-3.5 w-3.5" />去添加
              </Link>
            </div>
          ) : (
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {links.map(link => (
                <a
                  key={link.url}
                  href={link.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="group flex items-start gap-3 rounded-card border border-border bg-surface p-4 transition-ui duration-hover hover:border-accent/40 hover:bg-accent/[0.03]"
                >
                  <Globe2 className="mt-0.5 h-4 w-4 shrink-0 text-muted group-hover:text-accent" />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-medium text-foreground">{link.name || link.url}</span>
                    <span className="mt-1 block truncate text-micro text-muted">{hostOf(link.url)}</span>
                  </span>
                  <ExternalLink className="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted group-hover:text-accent" />
                </a>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
