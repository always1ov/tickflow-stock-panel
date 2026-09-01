import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ExternalLink, Globe2, Pencil, Plus, Save, ShieldCheck, Sparkles, Trash2, X } from 'lucide-react'
import {
  api,
  type AnalysisColumn, type AnalysisMenu, type ExtDataConfig, type ExtDataField,
  type ExternalPageRaw, type ExternalPageView,   // [R117]
} from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import { Skeleton } from '@/components/data/Skeleton'
import { ExternalViewRender } from '@/components/ExternalViewRender'   // [R117] 试运行预览

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

/**
 * [R117] 外部网页设置 —— 两种形态二选一:
 *   iframe: 上游原行为, 整站塞进 iframe(对方禁 iframe 就白屏)
 *   fetch:  后端抓原文 → **面板自己的 AI** 按固定提示词整理成表格 → 固定版式
 * 用户不需要写任何代码, 想要什么用一句大白话写在「想看什么」里。
 */
function ExternalWebsiteSettings() {
  const qc = useQueryClient()
  const prefs = useQuery({ queryKey: QK.preferences, queryFn: api.preferences })
  const [enabled, setEnabled] = useState(true)
  const [mode, setMode] = useState<'iframe' | 'fetch'>('iframe')
  const [name, setName] = useState('利弗莫尔趋势')
  const [url, setUrl] = useState('https://livermore-trend-dashboard-tigergu.netlify.app/')
  const [hint, setHint] = useState('')
  const [error, setError] = useState('')
  const [preview, setPreview] = useState<ExternalPageView | null>(null)
  const [rawPeek, setRawPeek] = useState<ExternalPageRaw | null>(null)

  useEffect(() => {
    if (!prefs.data) return
    setEnabled(prefs.data.external_page_enabled)
    setMode(prefs.data.external_page_mode ?? 'iframe')
    setName(prefs.data.external_page_name)
    setUrl(prefs.data.external_page_url)
    setHint(prefs.data.external_page_ai_hint ?? '')
  }, [prefs.data])

  const checkUrl = () => {
    const trimmedUrl = url.trim()
    try {
      const parsed = new URL(trimmedUrl)
      if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') throw new Error()
    } catch {
      throw new Error('请输入完整的 HTTP 或 HTTPS 网站地址')
    }
    return trimmedUrl
  }

  const save = useMutation({
    mutationFn: () => {
      const trimmedName = name.trim()
      if (!trimmedName) throw new Error('请输入页面名称')
      return api.updateExternalPage({ enabled, name: trimmedName, url: checkUrl(), mode, ai_hint: hint.trim() })
    },
    onSuccess: () => {
      setError('')
      qc.invalidateQueries({ queryKey: QK.preferences })
    },
    onError: err => setError(String((err as Error)?.message ?? err)),
  })

  // 只抓原文不调 AI —— 先确认这个地址能不能抓通、抓回来是不是有用的东西
  const peek = useMutation({
    mutationFn: async () => api.externalPageRaw({ url: checkUrl() }),
    onSuccess: d => { setError(''); setPreview(null); setRawPeek(d) },
    onError: err => setError(String((err as Error)?.message ?? err)),
  })

  // 试运行 = 真调一次 AI, 结果就是页面上会看到的样子
  const tryRun = useMutation({
    mutationFn: async () => api.externalPageView({ url: checkUrl(), hint: hint.trim(), force: true }),
    onSuccess: d => { setError(''); setRawPeek(null); setPreview(d) },
    onError: err => setError(String((err as Error)?.message ?? err)),
  })

  return (
    <section className="rounded-2xl border border-border bg-surface p-6 bg-[radial-gradient(circle_at_top_right,rgba(34,211,238,0.12),transparent_38%)]">
      <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
        <div className="max-w-2xl">
          <div className="flex items-center gap-2 text-[10.5px] font-semibold uppercase tracking-wider text-cyan-400/80">
            <Globe2 className="h-3.5 w-3.5" />外部网页
          </div>
          <h2 className="mt-2 text-xl font-semibold tracking-tight text-foreground">把一个外部网页变成「盘面参考」里的一页</h2>
          <p className="mt-2 text-sm leading-6 text-secondary">
            两种做法二选一：直接内嵌整站，或者由后端抓回原文、交给面板里配置的 AI 整理成统一表格再显示。
            无论哪种，牛来都不会把 TickFlow 数据、API Key 或登录凭据转发给对方。
          </p>
        </div>
        <button
          type="button"
          onClick={() => setEnabled(value => !value)}
          className={`inline-flex items-center gap-2 rounded-btn border px-3 py-1.5 text-xs transition-colors ${enabled ? 'border-success/40 bg-success/10 text-success' : 'border-border bg-elevated text-muted'}`}
        >
          <span className={`h-2 w-2 rounded-full ${enabled ? 'bg-success' : 'bg-muted'}`} />
          {enabled ? '已启用' : '已停用'}
        </button>
      </div>

      <div className="mt-5 grid grid-cols-1 gap-3 md:grid-cols-2">
        {([
          { key: 'fetch' as const, icon: Sparkles, title: '抓取 + AI 整理', desc: '后端取回原文，AI 按固定结构整理成 KPI 卡 + 表格。对方禁 iframe、是 SPA 都不影响；每次解析会调一次 AI（同一份原文有缓存）。' },
          { key: 'iframe' as const, icon: Globe2, title: '内嵌整站', desc: '把对方页面原样塞进 iframe。省事，但对方禁止 iframe 时会白屏，也没法只挑关键信息。' },
        ]).map(opt => (
          <button
            key={opt.key}
            type="button"
            onClick={() => setMode(opt.key)}
            className={`rounded-card border p-3 text-left transition-colors ${mode === opt.key ? 'border-accent/50 bg-accent/5' : 'border-border bg-base hover:bg-elevated/40'}`}
          >
            <div className={`flex items-center gap-1.5 text-xs font-medium ${mode === opt.key ? 'text-accent' : 'text-foreground'}`}>
              <opt.icon className="h-3.5 w-3.5" />{opt.title}
              {mode === opt.key && <span className="ml-auto text-[10px]">当前</span>}
            </div>
            <p className="mt-1.5 text-[11px] leading-5 text-muted">{opt.desc}</p>
          </button>
        ))}
      </div>

      <div className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-[minmax(12rem,0.7fr)_minmax(20rem,2fr)]">
        <label className="space-y-1.5">
          <span className="text-[11px] text-muted">页面名称</span>
          <input value={name} maxLength={40} onChange={e => setName(e.target.value)} className="h-9 w-full rounded-btn border border-border bg-base px-3 text-xs text-foreground" />
        </label>
        <label className="space-y-1.5">
          <span className="text-[11px] text-muted">网站地址</span>
          <input value={url} onChange={e => setUrl(e.target.value)} placeholder="https://example.com/" className="h-9 w-full rounded-btn border border-border bg-base px-3 text-xs text-foreground" />
        </label>
      </div>

      {mode === 'fetch' && (
        <div className="mt-4 space-y-2">
          <label className="space-y-1.5 block">
            <span className="text-[11px] text-muted">想从这一页看到什么（用大白话写，会拼进 AI 的提示词；留空则由 AI 自己判断）</span>
            <textarea
              value={hint}
              maxLength={2000}
              rows={3}
              onChange={e => setHint(e.target.value)}
              placeholder={'例如：只要涨幅榜前 20 名，列出代码、名称、涨幅、成交额；顶部给我多头家数和空头家数两个数字。'}
              className="w-full rounded-btn border border-border bg-base px-3 py-2 text-xs leading-6 text-foreground"
            />
          </label>
          <div className="rounded-btn border border-border/60 bg-base/60 px-3 py-2 text-[11px] leading-5 text-muted">
            AI 会被要求只输出固定结构：<span className="text-secondary">标题 · 顶部 KPI 卡 · 若干张表（列头/对齐/单位/涨跌染色）· 备注</span>。
            页面就按这个结构渲染，所以改提示词就能改看到的东西，不需要写代码。
            涨跌幅这类列会自动按正负红涨绿跌。原文超过 12000 字会被截断后再送 AI。
          </div>
        </div>
      )}

      {error && <div className="mt-3 rounded-btn border border-danger/30 bg-danger/5 px-3 py-2 text-xs text-danger whitespace-pre-wrap break-words">{error}</div>}

      {rawPeek && (
        <div className="mt-3 rounded-card border border-border bg-base/60 p-3">
          <div className="text-[11px] text-muted">
            抓通了：HTTP {rawPeek.status} · {rawPeek.content_type || '未知类型'} · {rawPeek.bytes} 字节 · 清洗后 {rawPeek.source_chars} 字
          </div>
          <pre className="mt-2 max-h-56 overflow-auto whitespace-pre-wrap break-all rounded bg-elevated/40 p-2 text-[10.5px] leading-5 text-secondary">{rawPeek.preview.slice(0, 2000)}</pre>
        </div>
      )}

      {preview && (
        <div className="mt-3 rounded-card border border-accent/30 bg-base/60 p-3">
          <div className="mb-2 flex flex-wrap items-center gap-x-3 text-[11px] text-muted">
            <span className="text-accent">试运行结果（页面上就是这个样子）</span>
            {preview.model && <span>档位 {preview.model}</span>}
            <span>原文 {preview.source_chars} 字</span>
          </div>
          <ExternalViewRender view={preview.spec} compact />
        </div>
      )}

      <div className="mt-4 flex flex-col gap-3 text-[11px] text-muted sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-1.5">
          <ShieldCheck className="h-3.5 w-3.5" />
          {mode === 'fetch'
            ? '服务端代抓只允许公网地址（内网/环回一律拒绝），单页上限 2MB。'
            : '目标网站若禁止 iframe，会显示空白，此时可使用页面内的“新窗口”按钮。'}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {mode === 'fetch' && (
            <>
              <button onClick={() => peek.mutate()} disabled={peek.isPending} className="inline-flex items-center gap-1.5 rounded-btn border border-border bg-elevated px-3 py-1.5 text-xs text-secondary hover:text-foreground disabled:opacity-50">
                <ExternalLink className="h-3.5 w-3.5" />{peek.isPending ? '抓取中…' : '只抓原文看看'}
              </button>
              <button onClick={() => tryRun.mutate()} disabled={tryRun.isPending} className="inline-flex items-center gap-1.5 rounded-btn border border-accent/40 bg-accent/10 px-3 py-1.5 text-xs text-accent disabled:opacity-50">
                <Sparkles className="h-3.5 w-3.5" />{tryRun.isPending ? 'AI 整理中…' : '试运行(调一次 AI)'}
              </button>
            </>
          )}
          {prefs.data?.external_page_enabled && prefs.data.external_page_url && (
            <Link to="/external-page" className="inline-flex items-center gap-1.5 rounded-btn border border-border bg-elevated px-3 py-1.5 text-xs text-secondary hover:text-foreground">
              <ExternalLink className="h-3.5 w-3.5" />打开页面
            </Link>
          )}
          <button onClick={() => save.mutate()} disabled={save.isPending || prefs.isLoading} className="inline-flex items-center gap-1.5 rounded-btn bg-accent px-3 py-1.5 text-xs font-medium text-base disabled:opacity-50">
            <Save className="h-3.5 w-3.5" />{save.isPending ? '保存中…' : '保存设置'}
          </button>
        </div>
      </div>
    </section>
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
  const [template, setTemplate] = useState<'dimension_rank' | 'ranking' | 'table'>('dimension_rank')
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
    setDimensionField(menu.dimension_field ?? firstMatchingField(cfg, ['概念', 'industry', '行业', 'sector']))
    setRankField(menu.rank_field ?? '')
    setSelectedColumns(menu.detail_columns.map(c => c.field))
    setError('')
    setShowForm(true)
  }

  const save = useMutation({
    mutationFn: () => {
      const cfg = activeConfig
      if (!cfg) throw new Error('请选择扩展数据源')
      if (!id.trim()) throw new Error('请输入菜单标识')
      if (!label.trim()) throw new Error('请输入菜单名称')
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
    <div className="max-w-6xl space-y-6">
      <ExternalWebsiteSettings />
      <section className="rounded-2xl border border-border bg-surface p-6 bg-[radial-gradient(circle_at_top_right,rgba(139,92,246,0.14),transparent_38%)]">
        <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
          <div>
            <div className="text-[10.5px] font-semibold uppercase tracking-wider text-accent/80">扩展页面</div>
            <h2 className="mt-2 text-2xl font-semibold tracking-tight text-foreground">把扩展数据配置成左侧分析菜单</h2>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-secondary">
              选择扩展数据源、分析模板、分组字段和列表列后，系统会生成一个可访问的动态分析页面。
            </p>
          </div>
          <button
            onClick={() => { resetForm(); setShowForm(true) }}
            className="inline-flex items-center justify-center gap-1.5 rounded-btn bg-accent/90 px-3 py-1.5 text-xs font-medium text-base hover:bg-accent transition-colors"
          >
            <Plus className="h-3.5 w-3.5" />
            新建页面
          </button>
        </div>
      </section>

      {showForm && (
        <section className="rounded-card border border-border bg-surface p-5 space-y-4">
          <div className="flex items-center justify-between gap-3">
            <div>
              <h3 className="text-sm font-medium text-foreground">{editingMenu ? '编辑扩展页面' : '新建扩展页面'}</h3>
              <p className="mt-1 text-[11px] text-muted">菜单标识保存后不可在此处直接修改，如需更换标识请新建页面。</p>
            </div>
            <button onClick={() => { setShowForm(false); setError('') }} className="rounded p-1 text-muted hover:bg-elevated hover:text-foreground">
              <X className="h-4 w-4" />
            </button>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <label className="space-y-1.5">
              <span className="text-[11px] text-muted">菜单标识</span>
              <input
                value={id}
                disabled={!!editingMenu}
                onChange={e => setId(e.target.value.replace(/[^a-zA-Z0-9_]/g, ''))}
                placeholder="如 concept_hot"
                className="h-9 w-full rounded-btn border border-border bg-base px-3 text-xs text-foreground disabled:opacity-60"
              />
            </label>
            <label className="space-y-1.5">
              <span className="text-[11px] text-muted">菜单名称</span>
              <input value={label} onChange={e => setLabel(e.target.value)} placeholder="如 概念热度" className="h-9 w-full rounded-btn border border-border bg-base px-3 text-xs text-foreground" />
            </label>
            <label className="space-y-1.5">
              <span className="text-[11px] text-muted">扩展数据源</span>
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
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <label className="space-y-1.5">
              <span className="text-[11px] text-muted">模板</span>
              <select value={template} onChange={e => setTemplate(e.target.value as any)} className="h-9 w-full rounded-btn border border-border bg-base px-3 text-xs text-foreground">
                <option value="dimension_rank">维度热度榜</option>
                <option value="ranking">指标排名榜</option>
                <option value="table">明细表</option>
              </select>
            </label>
            <label className="space-y-1.5">
              <span className="text-[11px] text-muted">分组字段</span>
              <select value={dimensionField} onChange={e => setDimensionField(e.target.value)} disabled={template !== 'dimension_rank'} className="h-9 w-full rounded-btn border border-border bg-base px-3 text-xs text-foreground disabled:opacity-50">
                <option value="">请选择</option>
                {fields.map(f => <option key={f.name} value={f.name}>{f.label || f.name}</option>)}
              </select>
            </label>
            <label className="space-y-1.5">
              <span className="text-[11px] text-muted">排名字段</span>
              <select value={rankField} onChange={e => setRankField(e.target.value)} disabled={template !== 'ranking'} className="h-9 w-full rounded-btn border border-border bg-base px-3 text-xs text-foreground disabled:opacity-50">
                <option value="">请选择</option>
                {numericFields.map(f => <option key={f.name} value={f.name}>{f.label || f.name}</option>)}
              </select>
            </label>
          </div>

          <div>
            <div className="text-[11px] text-muted mb-2">列表列配置</div>
            <div className="flex flex-wrap gap-2">
              {fields.filter(f => !['symbol', 'code'].includes(f.name)).map(f => {
                const active = selectedColumns.includes(f.name)
                return (
                  <button
                    key={f.name}
                    onClick={() => setSelectedColumns(cols => active ? cols.filter(c => c !== f.name) : [...cols, f.name])}
                    className={`rounded-btn border px-3 py-1 text-[11px] transition-colors ${active ? 'border-accent/40 bg-accent/10 text-accent' : 'border-border bg-elevated/40 text-secondary hover:bg-elevated'}`}
                  >
                    {f.label || f.name}
                  </button>
                )
              })}
            </div>
          </div>

          {error && <div className="rounded-btn border border-danger/30 bg-danger/5 px-3 py-2 text-xs text-danger">{error}</div>}

          <div className="flex justify-end gap-2">
            <button onClick={() => { setShowForm(false); setError('') }} className="px-4 py-1.5 rounded-btn bg-elevated text-secondary text-xs">取消</button>
            <button onClick={() => save.mutate()} disabled={save.isPending} className="inline-flex items-center gap-1.5 px-4 py-1.5 rounded-btn bg-accent/90 text-base text-xs font-medium disabled:opacity-50">
              <Save className="h-3.5 w-3.5" />保存
            </button>
          </div>
        </section>
      )}

      <section className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        {menuItems.map(menu => (
          <div key={menu.id} className="rounded-card border border-border bg-surface p-4">
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="text-sm font-medium text-foreground">{menu.label}</h3>
                  {menu.builtin && <span className="rounded bg-accent/10 px-1.5 py-0.5 text-[10px] text-accent">默认</span>}
                  {!menu.visible && <span className="rounded bg-muted/10 px-1.5 py-0.5 text-[10px] text-muted">已隐藏</span>}
                </div>
                <p className="mt-1 text-[11px] text-muted font-mono">{menu.id}</p>
              </div>
              <div className="flex items-center gap-1">
                <button onClick={() => editMenu(menu)} className="p-1 rounded text-muted hover:text-accent hover:bg-accent/10" title="编辑">
                  <Pencil className="h-3.5 w-3.5" />
                </button>
                {!menu.builtin && (
                  <button onClick={() => del.mutate(menu.id)} disabled={del.isPending} className="p-1 rounded text-muted hover:text-danger hover:bg-danger/10" title="删除">
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                )}
              </div>
            </div>
            <div className="mt-3 space-y-1 text-[11px] text-secondary">
              <div>数据源：<span className="font-mono text-muted">{menu.data_source}</span></div>
              <div>模板：{menu.template}</div>
              {menu.dimension_field && <div>分组字段：{menu.dimension_field}</div>}
              <div>列表列：{menu.detail_columns.length} 个</div>
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
              <Skeleton h="h-8" rounded="rounded-btn" />
            </div>
          ))}
        {!menus.isLoading && menuItems.length === 0 && (
          <div className="rounded-card border border-border bg-surface px-5 py-10 text-center text-sm text-muted md:col-span-2 xl:col-span-3">暂无扩展页面，点击右上角新建。</div>
        )}
      </section>
    </div>
  )
}
