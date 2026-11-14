import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ExternalLink, Globe2, Layers3, Pencil, Plus, Save, Trash2, X } from 'lucide-react'
import {
  api,
  type AnalysisColumn, type AnalysisMenu, type ExtDataConfig, type ExtDataField,
  type ExternalLinkItem,
} from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import { Skeleton } from '@/components/data/Skeleton'
import { sanitizeExtUrl } from '@/components/dashboard/layout'
import { SettingsCard } from './SettingsCard'

function dtypeToColumnType(dtype: string): AnalysisColumn['type'] {
  return dtype === 'int' || dtype === 'float' ? 'number' : 'string'
}

function buildColumn(field: ExtDataField): AnalysisColumn {
  return {
    field: field.name,
    label: field.label || field.name,
    type: dtypeToColumnType(field.dtype),
    precision: field.dtype === 'float' ? 2 : null,
    sortable: field.dtype === 'int' || field.dtype === 'float',
    visible: true,
  }
}

function firstMatchingField(config: ExtDataConfig | undefined, keywords: string[]) {
  if (!config) return ''
  for (const keyword of keywords) {
    const lower = keyword.toLowerCase()
    const matched = config.fields.find(f => f.name.toLowerCase().includes(lower) || f.label.toLowerCase().includes(lower))
    if (matched) return matched.name
  }
  return config.fields.find(f => !['symbol', 'code'].includes(f.name) && f.dtype === 'string')?.name ?? ''
}

const EXTERNAL_LINKS_LIMIT = 60

/**
 * [R611] 外链导航设置 —— 只维护一份链接清单。
 * 后端不再抓页面、也不再调 AI 整理; 页面就是一个纯链接目录, 点开走新标签。
 */
function ExternalLinkSettings() {
  const qc = useQueryClient()
  const prefs = useQuery({ queryKey: QK.preferences, queryFn: api.preferences })
  const [enabled, setEnabled] = useState(true)
  const [name, setName] = useState('外链导航')
  const [links, setLinks] = useState<ExternalLinkItem[]>([])
  const [error, setError] = useState('')

  useEffect(() => {
    if (!prefs.data) return
    setEnabled(prefs.data.external_page_enabled)
    setName(prefs.data.external_page_name)
    setLinks(prefs.data.external_links ?? [])
  }, [prefs.data])

  const patch = (index: number, field: keyof ExternalLinkItem, value: string) => {
    setLinks(rows => rows.map((row, i) => (i === index ? { ...row, [field]: value } : row)))
  }

  const save = useMutation({
    mutationFn: () => {
      const trimmedName = name.trim()
      if (!trimmedName) throw new Error('请输入页面名称')
      const cleaned: ExternalLinkItem[] = []
      links.forEach((row, index) => {
        const url = row.url.trim()
        if (!url) {
          if (row.name.trim()) throw new Error(`第 ${index + 1} 条链接缺少网址`)
          return
        }
        try {
          const parsed = new URL(url)
          if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') throw new Error()
        } catch {
          throw new Error(`第 ${index + 1} 条链接的网址无效，需要完整的 http(s) 地址`)
        }
        cleaned.push({ name: row.name.trim(), url })
      })
      return api.updateExternalPage({ enabled, name: trimmedName, links: cleaned })
    },
    onSuccess: () => {
      setError('')
      qc.invalidateQueries({ queryKey: QK.preferences })
    },
    onError: err => setError(String((err as Error)?.message ?? err)),
  })

  return (
    <SettingsCard
      icon={Globe2}
      title="外链导航"
      desc="把常看的站点收进来，菜单里会多出一页按卡片列出这些链接，点开在新标签打开。面板不会抓取对方页面，也不会把 TickFlow 数据、API Key 或登录凭据转发出去。"
      right={(
        <button
          type="button"
          onClick={() => setEnabled(value => !value)}
          className={`shrink-0 inline-flex items-center gap-2 rounded-btn border px-3 py-1.5 text-xs transition-colors ${enabled ? 'border-accent/40 bg-accent/10 text-accent' : 'border-border bg-surface text-foreground'}`}
        >
          <span className={`h-2 w-2 rounded-full ${enabled ? 'bg-accent' : 'bg-muted'}`} />
          {enabled ? '已启用' : '已停用'}
        </button>
      )}
    >
      <div className="grid grid-cols-1 gap-3 md:grid-cols-[minmax(12rem,0.7fr)_minmax(20rem,2fr)]">
        <label className="space-y-1.5">
          <span className="text-xs text-muted">页面名称</span>
          <input value={name} maxLength={40} onChange={e => setName(e.target.value)} className="h-9 w-full rounded-btn border border-border bg-base px-3 text-xs text-foreground" />
        </label>
        <div className="flex items-end gap-2 text-xs text-muted">
          <span className="pb-2">共 {links.length} / {EXTERNAL_LINKS_LIMIT} 条链接</span>
        </div>
      </div>

      <div className="mt-4 space-y-2">
        {links.length === 0 && (
          <div className="rounded-btn border border-dashed border-border px-3 py-6 text-center text-xs text-muted">
            还没有链接，点下面的「添加链接」开始。
          </div>
        )}
        {links.map((row, index) => (
          <div key={index} className="grid grid-cols-1 gap-2 md:grid-cols-[minmax(8rem,0.8fr)_minmax(16rem,2fr)_auto]">
            <input
              value={row.name}
              maxLength={40}
              onChange={e => patch(index, 'name', e.target.value)}
              placeholder="名称（可留空，显示网址）"
              className="h-9 w-full rounded-btn border border-border bg-base px-3 text-xs text-foreground"
            />
            <input
              value={row.url}
              maxLength={2048}
              onChange={e => patch(index, 'url', e.target.value)}
              placeholder="https://example.com/"
              className="h-9 w-full rounded-btn border border-border bg-base px-3 text-xs text-foreground"
            />
            <button
              type="button"
              onClick={() => setLinks(rows => rows.filter((_, i) => i !== index))}
              className="inline-flex h-9 items-center justify-center gap-1.5 rounded-btn border border-border px-3 text-xs text-secondary hover:border-danger/40 hover:text-danger"
              title="删除这一条"
            >
              <Trash2 className="h-3.5 w-3.5" />删除
            </button>
          </div>
        ))}
      </div>

      {error && <div className="mt-3 rounded-btn border border-danger/30 bg-danger/5 px-3 py-2 text-xs text-danger whitespace-pre-wrap break-words">{error}</div>}

      <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => setLinks(rows => (rows.length >= EXTERNAL_LINKS_LIMIT ? rows : [...rows, { name: '', url: '' }]))}
            disabled={links.length >= EXTERNAL_LINKS_LIMIT}
            className="inline-flex items-center gap-1.5 rounded-btn border border-border bg-surface px-3 py-1.5 text-xs text-foreground hover:text-foreground disabled:opacity-50"
          >
            <Plus className="h-3.5 w-3.5" />添加链接
          </button>
          <Link to="/external-page" className="inline-flex items-center gap-1.5 rounded-btn border border-border bg-elevated px-3 py-1.5 text-xs text-secondary hover:text-foreground">
            <ExternalLink className="h-3.5 w-3.5" />打开页面
          </Link>
        </div>
        <button onClick={() => save.mutate()} disabled={save.isPending || prefs.isLoading} className="inline-flex items-center gap-1.5 rounded-btn bg-accent/90 px-3 py-1.5 text-xs font-medium text-on-accent hover:bg-accent disabled:opacity-50">
          <Save className="h-3.5 w-3.5" />{save.isPending ? '保存中…' : '保存设置'}
        </button>
      </div>
    </SettingsCard>
  )
}

export function SettingsExtPagesPanel() {
  const qc = useQueryClient()
  const menus = useQuery({ queryKey: QK.analysisMenus, queryFn: api.analysisMenus })
  const extData = useQuery({ queryKey: QK.extData, queryFn: api.extDataList })
  const configs = extData.data?.items ?? []
  const menuItems = menus.data?.items ?? []

  const [showForm, setShowForm] = useState(false)
  const [editingMenu, setEditingMenu] = useState<AnalysisMenu | null>(null)
  const [id, setId] = useState('')
  const [label, setLabel] = useState('')
  const [dataSource, setDataSource] = useState('')
  const [template, setTemplate] = useState<'dimension_rank' | 'ranking' | 'table' | 'url'>('dimension_rank')
  const [embedUrl, setEmbedUrl] = useState('')
  const [dimensionField, setDimensionField] = useState('')
  const [rankField, setRankField] = useState('')
  const [selectedColumns, setSelectedColumns] = useState<string[]>([])
  const [error, setError] = useState('')

  const activeConfig = configs.find(c => c.id === dataSource) ?? configs[0]
  const fields = activeConfig?.fields ?? []
  const numericFields = useMemo(() => fields.filter(f => f.dtype === 'int' || f.dtype === 'float'), [fields])

  const resetForm = () => {
    const cfg = configs[0]
    setEditingMenu(null)
    setId('')
    setLabel('')
    setDataSource(cfg?.id ?? '')
    setTemplate('dimension_rank')
    setEmbedUrl('')
    setDimensionField(firstMatchingField(cfg, ['概念', 'industry', '行业', 'sector']))
    setRankField('')
    setSelectedColumns(cfg?.fields.filter(f => !['symbol', 'code'].includes(f.name)).slice(0, 6).map(f => f.name) ?? [])
    setError('')
  }

  const editMenu = (menu: AnalysisMenu) => {
    const cfg = configs.find(c => c.id === menu.data_source)
    setEditingMenu(menu)
    setId(menu.id)
    setLabel(menu.label)
    setDataSource(menu.data_source)
    setTemplate(menu.template)
    setEmbedUrl(menu.url ?? '')
    setDimensionField(menu.dimension_field ?? firstMatchingField(cfg, ['概念', 'industry', '行业', 'sector']))
    setRankField(menu.rank_field ?? '')
    setSelectedColumns(menu.detail_columns.map(c => c.field))
    setError('')
    setShowForm(true)
  }

  const save = useMutation({
    mutationFn: () => {
      if (!id.trim()) throw new Error('请输入菜单标识')
      if (!label.trim()) throw new Error('请输入菜单名称')

      // url 嵌入型: 不绑数据源, 只需消毒后的地址 (与渲染端 ExtUrlEmbed 同一 sanitize)
      if (template === 'url') {
        const safe = sanitizeExtUrl(embedUrl)
        if (!safe) throw new Error('嵌入地址无效: 仅支持 http(s)、长度 ≤500, 且不能嵌入本站自身')
        return api.analysisMenuSave(id.trim(), {
          label: label.trim(),
          icon: 'link',
          data_source: '',
          template: 'url',
          url: safe,
          dimension_field: null,
          rank_field: null,
          group_columns: [],
          detail_columns: [],
          default_sort: null,
          visible: editingMenu?.visible ?? true,
          order: editingMenu?.order ?? menuItems.length + 100,
        })
      }

      const cfg = activeConfig
      if (!cfg) throw new Error('请选择扩展数据源')
      if (template === 'dimension_rank' && !dimensionField) throw new Error('请选择分组字段')
      if (template === 'ranking' && !rankField) throw new Error('请选择排名字段')

      const detailColumns = selectedColumns
        .map(name => cfg.fields.find(f => f.name === name))
        .filter(Boolean)
        .map(f => buildColumn(f as ExtDataField))
      const groupColumns: AnalysisColumn[] = template === 'dimension_rank'
        ? [
            { field: '__dimension', label: cfg.fields.find(f => f.name === dimensionField)?.label || '分组', type: 'string', visible: true },
            { field: '__count', label: '股票数', type: 'number', sortable: true, visible: true },
            ...detailColumns.filter(c => c.type === 'number').slice(0, 2).map(c => ({ ...c, label: `平均${c.label || c.field}`, aggregate: 'avg' as const })),
          ]
        : []

      return api.analysisMenuSave(id.trim(), {
        label: label.trim(),
        icon: template === 'dimension_rank' ? 'tags' : 'chart',
        data_source: cfg.id,
        template,
        dimension_field: template === 'dimension_rank' ? dimensionField : null,
        rank_field: template === 'ranking' ? rankField : null,
        group_columns: groupColumns,
        detail_columns: detailColumns,
        default_sort: template === 'ranking' && rankField ? { field: rankField, order: 'desc' } : null,
        visible: editingMenu?.visible ?? true,
        order: editingMenu?.order ?? menuItems.length + 100,
      })
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: QK.analysisMenus })
      setShowForm(false)
      resetForm()
    },
    onError: (err) => setError(String((err as any)?.message ?? err)),
  })

  const del = useMutation({
    mutationFn: api.analysisMenuDelete,
    onSuccess: () => qc.invalidateQueries({ queryKey: QK.analysisMenus }),
  })

  return (
    <div className="space-y-6">
      <ExternalLinkSettings />
      {/* [R535] 设置区统一卡头: 大号开篇并入说明 */}
      <SettingsCard
        icon={Layers3}
        title="扩展页面"
        desc="把扩展数据配置成左侧分析菜单：选数据源、模板、分组字段和列表列后，系统生成一个可访问的动态分析页。也可直接填网址创建 URL 嵌入页；要导入 .tsx 源码页面请到「页面插件」区块的「导入源码」。"
        right={(
          <div className="flex shrink-0 flex-wrap gap-2">
            <button
              onClick={() => { resetForm(); setTemplate('url'); setShowForm(true) }}
              className="inline-flex items-center justify-center gap-1.5 rounded-btn border border-border px-3 py-1.5 text-xs font-medium text-secondary hover:border-accent/60 hover:text-accent transition-colors"
            >
              <ExternalLink className="h-3.5 w-3.5" />
              新建 URL 页
            </button>
            <button
              onClick={() => { resetForm(); setShowForm(true) }}
              className="inline-flex items-center justify-center gap-1.5 rounded-btn bg-accent/90 px-3 py-1.5 text-xs font-medium text-on-accent hover:bg-accent transition-colors"
            >
              <Plus className="h-3.5 w-3.5" />
              新建页面
            </button>
          </div>
        )}
      >
      {showForm && (
        <div className="mt-5 rounded-card border border-border bg-base p-5 space-y-4">
          <div className="flex items-center justify-between gap-3">
            <div>
              <h3 className="text-sm font-medium text-foreground">{editingMenu ? '编辑扩展页面' : '新建扩展页面'}</h3>
              <p className="mt-1 text-micro text-muted">菜单标识保存后不可在此处直接修改，如需更换标识请新建页面。</p>
            </div>
            <button onClick={() => { setShowForm(false); setError('') }} className="rounded-btn p-1 text-secondary hover:bg-elevated hover:text-foreground">
              <X className="h-4 w-4" />
            </button>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <label className="space-y-1.5">
              <span className="text-micro text-muted">菜单标识</span>
              <input
                value={id}
                disabled={!!editingMenu}
                onChange={e => setId(e.target.value.replace(/[^a-zA-Z0-9_]/g, ''))}
                placeholder="如 concept_hot"
                className="h-9 w-full rounded-btn border border-border bg-base px-3 text-xs text-foreground disabled:opacity-60"
              />
            </label>
            <label className="space-y-1.5">
              <span className="text-micro text-muted">菜单名称</span>
              <input value={label} onChange={e => setLabel(e.target.value)} placeholder="如 概念热度" className="h-9 w-full rounded-btn border border-border bg-base px-3 text-xs text-foreground" />
            </label>
            {template === 'url' ? (
              <label className="space-y-1.5">
                <span className="text-micro text-muted">嵌入地址</span>
                <input
                  value={embedUrl}
                  onChange={e => setEmbedUrl(e.target.value)}
                  placeholder="https://example.com/page"
                  className="h-9 w-full rounded-btn border border-border bg-base px-3 text-xs text-foreground"
                />
                <span className="block text-micro text-muted/70">仅 http(s)、≤500 字符，不支持嵌入本站；部分站点可拒绝被嵌入</span>
              </label>
            ) : (
              <label className="space-y-1.5">
                <span className="text-micro text-muted">扩展数据源</span>
                <select
                  value={dataSource || activeConfig?.id || ''}
                  onChange={e => {
                    const cfg = configs.find(c => c.id === e.target.value)
                    setDataSource(e.target.value)
                    setDimensionField(firstMatchingField(cfg, ['概念', 'industry', '行业', 'sector']))
                    setRankField('')
                    setSelectedColumns(cfg?.fields.filter(f => !['symbol', 'code'].includes(f.name)).slice(0, 6).map(f => f.name) ?? [])
                  }}
                  className="h-9 w-full rounded-btn border border-border bg-base px-3 text-xs text-foreground"
                >
                  {configs.map(cfg => <option key={cfg.id} value={cfg.id}>{cfg.label}</option>)}
                </select>
              </label>
            )}
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <label className="space-y-1.5">
              <span className="text-micro text-muted">模板</span>
              <select value={template} onChange={e => setTemplate(e.target.value as any)} className="h-9 w-full rounded-btn border border-border bg-base px-3 text-xs text-foreground">
                <option value="dimension_rank">维度热度榜</option>
                <option value="ranking">指标排名榜</option>
                <option value="table">明细表</option>
                <option value="url">URL 嵌入</option>
              </select>
            </label>
            <label className="space-y-1.5">
              <span className="text-micro text-muted">分组字段</span>
              <select value={dimensionField} onChange={e => setDimensionField(e.target.value)} disabled={template !== 'dimension_rank'} className="h-9 w-full rounded-btn border border-border bg-base px-3 text-xs text-foreground disabled:opacity-50">
                <option value="">请选择</option>
                {fields.map(f => <option key={f.name} value={f.name}>{f.label || f.name}</option>)}
              </select>
            </label>
            <label className="space-y-1.5">
              <span className="text-micro text-muted">排名字段</span>
              <select value={rankField} onChange={e => setRankField(e.target.value)} disabled={template !== 'ranking'} className="h-9 w-full rounded-btn border border-border bg-base px-3 text-xs text-foreground disabled:opacity-50">
                <option value="">请选择</option>
                {numericFields.map(f => <option key={f.name} value={f.name}>{f.label || f.name}</option>)}
              </select>
            </label>
          </div>

          {template !== 'url' && (
            <div>
              <div className="text-micro text-muted mb-2">列表列配置</div>
              <div className="flex flex-wrap gap-2">
                {fields.filter(f => !['symbol', 'code'].includes(f.name)).map(f => {
                  const active = selectedColumns.includes(f.name)
                  return (
                    <button
                      key={f.name}
                      onClick={() => setSelectedColumns(cols => active ? cols.filter(c => c !== f.name) : [...cols, f.name])}
                      className={`rounded-full border px-3 py-1 text-micro transition-colors ${active ? 'border-accent/40 bg-accent/10 text-accent' : 'border-border bg-elevated/40 text-foreground hover:bg-elevated'}`}
                    >
                      {f.label || f.name}
                    </button>
                  )
                })}
              </div>
            </div>
          )}

          {error && <div className="rounded-btn border border-danger/30 bg-danger/5 px-3 py-2 text-xs text-danger">{error}</div>}

          <div className="flex justify-end gap-2">
            <button onClick={() => { setShowForm(false); setError('') }} className="px-4 py-1.5 rounded-btn bg-surface border border-border text-foreground text-xs">取消</button>
            <button onClick={() => save.mutate()} disabled={save.isPending} className="inline-flex items-center gap-1.5 px-4 py-1.5 rounded-btn bg-accent/90 text-on-accent text-xs font-medium disabled:opacity-50">
              <Save className="h-3.5 w-3.5" />保存
            </button>
          </div>
        </div>
      )}
      <div className="mt-4 grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        {menuItems.map(menu => (
          <div key={menu.id} className="rounded-card border border-border bg-surface p-4">
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="text-sm font-medium text-foreground">{menu.label}</h3>
                  {menu.builtin && <span className="rounded-btn bg-accent/10 px-1.5 py-0.5 text-micro text-accent">默认</span>}
                  {!menu.visible && <span className="rounded-btn bg-muted/10 px-1.5 py-0.5 text-micro text-muted">已隐藏</span>}
                </div>
                <p className="mt-1 text-micro text-muted font-mono">{menu.id}</p>
              </div>
              <div className="flex items-center gap-1">
                <button onClick={() => editMenu(menu)} className="p-1 rounded-btn text-secondary hover:text-accent hover:bg-accent/10" title="编辑">
                  <Pencil className="h-3.5 w-3.5" />
                </button>
                {!menu.builtin && (
                  <button onClick={() => del.mutate(menu.id)} disabled={del.isPending} className="p-1 rounded-btn text-secondary hover:text-danger hover:bg-danger/10" title="删除">
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                )}
              </div>
            </div>
            <div className="mt-3 space-y-1 text-micro text-secondary">
              {menu.template === 'url' ? (
                <div className="break-all">地址：<span className="font-mono text-muted">{menu.url}</span></div>
              ) : (
                <>
                  <div>数据源：<span className="font-mono text-muted">{menu.data_source}</span></div>
                  {menu.dimension_field && <div>分组字段：{menu.dimension_field}</div>}
                  <div>列表列：{menu.detail_columns.length} 个</div>
                </>
              )}
              <div>模板：{menu.template}</div>
            </div>
            <Link to={`/analysis/${menu.id}`} className="mt-4 inline-flex w-full items-center justify-center gap-1.5 rounded-btn border border-border bg-elevated px-3 py-1.5 text-xs text-foreground hover:bg-border/30 transition-colors">
              <ExternalLink className="h-3.5 w-3.5" />
              打开分析页
            </Link>
          </div>
        ))}
        {menus.isLoading &&
          Array.from({ length: 3 }).map((_, i) => (
            <div key={`sk-${i}`} className="rounded-card border border-border bg-surface p-4 space-y-3">
              <Skeleton w="w-1/2" h="h-4" />
              <Skeleton w="w-1/3" h="h-3" />
              <Skeleton h="h-8" rounded-btn="rounded-btn" />
            </div>
          ))}
        {!menus.isLoading && menuItems.length === 0 && (
          <div className="rounded-card border border-border bg-surface px-5 py-10 text-center text-sm text-muted md:col-span-2 xl:col-span-3">暂无扩展页面，点击右上角新建。</div>
        )}
      </div>
      </SettingsCard>
    </div>
  )
}
