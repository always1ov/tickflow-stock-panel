/**
 * [fork 增强] R117 外部网页抓取模式的**固定版式**渲染器。
 *
 * 页面结构就这三块, 不随数据变: KPI 卡 → 若干张表 → 备注。AI 按后端那份固定
 * 提示词往这个结构里填, 所以这里只认已经归一化好的 ExtSpec —— 校验与上限都在
 * 后端 `services/external_view.normalize_spec` 做完了。
 *
 * 一切值都当**纯文本**渲染: 外部站点的内容不可信, 绝不 dangerouslySetInnerHTML。
 */
import { cn } from '@/lib/cn'
import { cellToneClass, formatCell, type ExtSection, type ExtSpec, type ExtStat } from '@/lib/externalView'
import { TYPE } from '@/components/ui'

function StatCard({ label, value, hint, tone }: ExtStat) {
  return (
    <div className="rounded-card border border-border bg-surface px-4 py-3">
      <div className="text-xs text-muted">{label}</div>
      <div className={cn('mt-1 text-xl font-semibold tabular-nums', cellToneClass(value, tone))}>{value || '—'}</div>
      {hint && <div className="mt-1 text-xs text-muted">{hint}</div>}
    </div>
  )
}

function SectionTable({ section }: { section: ExtSection }) {
  return (
    <section className="rounded-card border border-border bg-surface">
      {(section.title || section.note) && (
        <div className="flex flex-wrap items-baseline justify-between gap-2 border-b border-border px-4 py-2.5">
          {section.title && <h2 className={TYPE.card}>{section.title}</h2>}
          {section.note && <span className="text-xs text-muted">{section.note}</span>}
        </div>
      )}
      {section.rows.length === 0 ? (
        <div className="px-4 py-8 text-center text-xs text-muted">这张表没有数据</div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-full text-xs">
            <thead>
              <tr className="border-b border-border text-xs text-muted">
                {section.columns.map(col => (
                  <th
                    key={col.key}
                    className={cn('whitespace-nowrap px-3 py-2 font-normal',
                      col.align === 'right' ? 'text-right' : col.align === 'center' ? 'text-center' : 'text-left')}
                  >
                    {col.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {section.rows.map((row, i) => (
                <tr key={i} className="border-b border-border/40 last:border-0 hover:bg-elevated/40">
                  {section.columns.map(col => (
                    <td
                      key={col.key}
                      className={cn('whitespace-nowrap px-3 py-1.5 tabular-nums',
                        col.align === 'right' ? 'text-right' : col.align === 'center' ? 'text-center' : 'text-left',
                        cellToneClass(row[col.key], col.tone))}
                    >
                      {formatCell(row[col.key], col)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}

export function ExternalViewRender({ view, compact = false }: { view: ExtSpec; compact?: boolean }) {
  return (
    <div className={cn('space-y-4', compact && 'space-y-3')}>
      {(view.title || view.subtitle || view.updated_at) && (
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          {view.title && <h1 className={TYPE.section}>{view.title}</h1>}
          {view.subtitle && <span className="text-xs text-secondary">{view.subtitle}</span>}
          {view.updated_at && <span className="text-xs text-muted">数据时间 {view.updated_at}</span>}
        </div>
      )}

      {view.stats.length > 0 && (
        <div className={cn('grid gap-3', compact
          ? 'grid-cols-2 md:grid-cols-4'
          : 'grid-cols-2 md:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-6')}>
          {view.stats.map((s, i) => <StatCard key={`${s.label}-${i}`} {...s} />)}
        </div>
      )}

      {view.sections.map((section, i) => <SectionTable key={i} section={section} />)}

      {view.notes.length > 0 && (
        <ul className="space-y-1 rounded-card border border-border bg-surface px-4 py-3 text-xs leading-5 text-muted">
          {view.notes.map((n, i) => <li key={i}>· {n}</li>)}
        </ul>
      )}
    </div>
  )
}
