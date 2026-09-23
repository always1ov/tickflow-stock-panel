import { useState, useRef, useEffect, useMemo, useCallback } from 'react'
import { useNavigate, useSearchParams, Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { motion, AnimatePresence } from 'framer-motion'
import { AlertTriangle, RadioTower, Plus, Trash2, Settings2, Zap, Bell, ListChecks, BellRing, TrendingUp, TrendingDown, Flame, Tags } from 'lucide-react'
import { PageHeader } from '@/components/PageHeader'
import { EmptyState } from '@/components/EmptyState'
import { Skeleton } from '@/components/data/Skeleton'
import { api, type MonitorRule, type AlertEvent, type MonitorCondition, type MonitorExtFieldItem } from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import { fmtPrice, fmtPct } from '@/lib/format'
import { useDialogBackdrop } from '@/lib/useDialogBackdrop'
import { cn } from '@/lib/cn'
import { cnSignal } from '@/lib/signals'
import { useCustomSignalNames } from '@/lib/useCustomSignalNames'
import { LEGACY_STRATEGY_NOTIFY_EVENTS, STRATEGY_NOTIFY_EVENT_OPTIONS, strategyEventMeta, strategyName } from '@/lib/strategyMonitorEvents'
import { boardTag } from '@/components/stock-table/primitives'
import { resolveWatchlistGroupColor } from '@/lib/watchlist-group-colors'
import { markSeen, resetBadge, leaveMonitorPage } from '@/lib/monitorBadge'
import { RuleEditor } from '@/components/monitor/RuleEditor'
import { FocusBar } from '@/components/monitor/FocusBar'
import { toast } from '@/components/Toast'
import { StockPreviewDialog } from '@/components/StockPreviewDialog'
import { toNavItems, type NavItem } from '@/lib/listNav'
import { DimensionMembersDialog, type DimensionKind, type DimensionMembersTarget } from '@/components/DimensionMembersDialog'
import { usePreferences, useQuoteStatus } from '@/lib/useSharedQueries'
import { SELECTED, TYPE, buttonClass } from '@/components/ui'

const TYPE_LABEL: Record<string, string> = {
  signal: '信号', price: '价格/涨跌', market: '市场异动', strategy: '策略监控', sector: '板块监控',
  abnormal: '异动监控', volume_delta: '轮询放量', date: '日期提醒',
}

/** 严重级别 → 左侧色条 + 图标 */
const SEVERITY_CONFIG: Record<string, { bar: string; icon: any; iconCls: string }> = {
  info:     { bar: 'bg-accent/40',       icon: Bell,        iconCls: 'text-accent' },
  warn:     { bar: 'bg-warning',          icon: TrendingUp,  iconCls: 'text-warning' },
  critical: { bar: 'bg-danger',           icon: Flame,       iconCls: 'text-danger' },
}
const SOURCE_BADGE_STYLE: Record<string, string> = {
  strategy: 'bg-warning/10 text-warning border-warning/20',
  signal:   'bg-accent/10 text-accent border-accent/20',
  price:    'bg-emerald-400/10 text-emerald-400 border-emerald-400/20',
  market:   'bg-purple-500/10 text-purple-400 border-purple-500/20',
  sector:   'bg-cyan-500/10 text-cyan-700 border-cyan-500/20 dark:text-cyan-300',
  abnormal: 'bg-orange-500/10 text-orange-500 border-orange-500/20 dark:text-orange-400',
  volume_delta: 'bg-indigo-500/10 text-indigo-500 border-indigo-500/20 dark:text-indigo-300',
  date:     'bg-violet-500/10 text-violet-500 border-violet-500/20 dark:text-violet-300',
}

/**
 * 渲染策略类消息 — 策略名黄色、进入红/移出绿 (A 股红涨绿跌惯例)、其余白色。
 */
function renderMessage(source: string, message: string) {
  if (source !== 'strategy') {
    return <span className="text-secondary">{message}</span>
  }
  const m = message.match(/^(策略「)([^」]+)(」)(新入选|进入|移出)( .*)$/)
  if (!m) return <span className="text-foreground">{message}</span>
  const [, pre, strategyName, mid, direction, post] = m
  return (
    <>
      <span className="text-foreground/80">{pre}</span>
      <span className="text-warning font-medium">{strategyName}</span>
      <span className="text-foreground/80">{mid}</span>
      <span className={direction === '移出' ? 'text-bear font-medium' : 'text-danger font-medium'}>{direction}</span>
      <span className="text-foreground/80">{post}</span>
    </>
  )
}

/**
 * 从事件行中取出 ext 字段标签 (行业/概念), 按 item 配置裁剪 (maxTags/hiddenIndices)。
 */
function getExtTags(ev: Record<string, unknown>, item: MonitorExtFieldItem | null): string[] {
  if (!item?.field) return []
  const key = item.field.replace('.', '__')
  const v = ev[key]
  if (v == null) return []
  const str = String(v)
  if (!str) return []
  let tags = str.split(/[、,，;；\-]/).map(s => s.trim()).filter(Boolean)
  const maxTags = item.maxTags ?? 0
  if (maxTags > 0) tags = tags.slice(0, maxTags)
  const hidden = item.hiddenIndices
  if (hidden?.length) tags = tags.filter((_, i) => !hidden.includes(i))
  return tags
}

/** 个股通知的 ext 标签行 (行业/概念), 无数据返回 null */
function AlertExtTags({ ev, fields, onTagClick }: {
  ev: Record<string, unknown>
  fields: { concept: MonitorExtFieldItem | null; industry: MonitorExtFieldItem | null }
  onTagClick: (kind: DimensionKind, value: string, sourceField?: string) => void
}) {
  const conceptTags = getExtTags(ev, fields.concept)
  const industryTags = getExtTags(ev, fields.industry)
  if (conceptTags.length === 0 && industryTags.length === 0) return null
  return (
    <div className="mt-1 flex flex-wrap items-center gap-1 pl-0.5">
      {industryTags.map((t, i) => (
        <button
          key={`i${i}`}
          onClick={event => { event.stopPropagation(); onTagClick('industry', t, fields.industry?.field) }}
          className="rounded bg-sky-500/10 px-1 py-px text-micro leading-tight text-sky-700 hover:brightness-95 dark:text-sky-400"
        >
          {t}
        </button>
      ))}
      {conceptTags.map((t, i) => (
        <button
          key={`c${i}`}
          onClick={event => { event.stopPropagation(); onTagClick('concept', t, fields.concept?.field) }}
          className="rounded bg-orange-500/10 px-1 py-px text-micro leading-tight text-orange-700 hover:brightness-95 dark:text-orange-400"
        >
          {t}
        </button>
      ))}
    </div>
  )
}

export function Monitor() {
  const qc = useQueryClient()
  const [editorOpen, setEditorOpen] = useState(false)
  const [editingRule, setEditingRule] = useState<MonitorRule | null>(null)
  const [editorPreset, setEditorPreset] = useState<Partial<MonitorRule> | null>(null)

  // 深链: /monitor?new=abnormal (异动监控页「告警规则」入口) → 直接弹出预置类型的编辑器
  const [searchParams, setSearchParams] = useSearchParams()
  useEffect(() => {
    const kind = searchParams.get('new')
    if (kind === 'abnormal') {
      setEditingRule(null)
      setEditorPreset({ type: 'abnormal', threshold_pct: 70, direction: 'both', abnormal_window: 'any', scope: 'all' })
      setEditorOpen(true)
      setSearchParams({}, { replace: true })
    }
  }, [searchParams, setSearchParams])

  // 触发记录: 过滤 + 统计 (提升到主组件, 供 header 行使用)
  const [filter, setFilter] = useState<'all' | 'strategy' | 'signal' | 'price' | 'market' | 'sector' | 'abnormal' | 'volume_delta' | 'date'>('all')
  // [R160] 触发记录默认只看焦点内的; 切「含焦点外」能看到被静音的那些(灰显)
  const [focusOnly, setFocusOnly] = useState(true)
  const [confirmClear, setConfirmClear] = useState(false)
  const [confirmClearRules, setConfirmClearRules] = useState(false)
  // [fork 增强] 批量设置推送渠道
  const [batchChannelsOpen, setBatchChannelsOpen] = useState(false)

  // 全局 ext 字段配置 (监控中心个股通知带行业/概念标签)
  const { data: prefs } = usePreferences()
  // 实时行情可用性: mode=none 表示当前生效数据源完全无法提供实时行情
  // (TickFlow 无有效 Key, 或路由源未就绪) — 监控/预警收不到最新价, 顶部提示去数据源配置。
  const { data: quoteStatus } = useQuoteStatus()
  const realtimeUnavailable = quoteStatus?.mode === 'none'
  const monitorExtFields = prefs?.monitor_ext_fields ?? {
    concept: { field: 'ext_gn_ths.所属概念' },
    industry: { field: 'ext_hy_ths.所属同花顺行业' },
  }
  const [extConfigOpen, setExtConfigOpen] = useState(false)
  const extColumnsParam = useMemo(() => {
    const parts = [monitorExtFields.concept?.field, monitorExtFields.industry?.field].filter(Boolean) as string[]
    return parts.length > 0 ? parts.join(',') : undefined
  }, [monitorExtFields])

  const alertsQuery = useQuery({
    queryKey: [...QK.alerts(filter === 'all' ? undefined : filter), extColumnsParam ?? '', focusOnly ? 'focus' : 'all'],
    queryFn: () => api.alertsList({ days: 7, limit: 500, source: filter === 'all' ? undefined : filter, extColumns: extColumnsParam, focus: focusOnly }),
    // 10s 轮询仅作 SSE strategy_alert 事件的兜底; 后台标签页不再拉 500 条全量
    refetchInterval: 10000,
  })
  const total = alertsQuery.data?.total ?? 0

  // 规则个数
  const rulesQuery = useQuery({ queryKey: QK.monitorRules, queryFn: api.monitorRulesList })
  const rulesCount = rulesQuery.data?.rules.length ?? 0

  // 清除全部规则 (逐条删除)
  const clearRulesMut = useMutation({
    mutationFn: async () => {
      const rules = rulesQuery.data?.rules ?? []
      await Promise.all(rules.map(r => api.monitorRuleDelete(r.id)))
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: QK.monitorRules })
      setConfirmClearRules(false)
    },
  })

  // 进入监控页: 清零未读徽标 + 记录"进入时刻", 之后新增的记录会闪烁
  // 离开监控页: 停止同步, 之后新增才计入未读
  const enterTsRef = useRef<number>(Date.now())
  useEffect(() => {
    enterTsRef.current = Date.now()
    markSeen()
    return () => leaveMonitorPage()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <div className="flex flex-col h-full">
      <PageHeader title="监控中心" subtitle="实时信号与规则管理" />
      {realtimeUnavailable && (
        <div className="px-3 pb-1 lg:px-4">
          <div className="mx-auto flex max-w-[1440px] items-center gap-2.5 rounded-xl border border-warning/30 bg-warning/[0.06] px-4 py-2.5">
            <AlertTriangle className="h-4 w-4 shrink-0 text-warning" />
            <span className="text-xs leading-relaxed text-secondary">
              实时行情当前不可用 — 监控与预警收不到最新价。可接入提供实时行情的数据源。
            </span>
            <Link
              to="/settings?tab=data-sources"
              className={buttonClass({}, 'ml-auto shrink-0 border-warning/40 bg-warning/10 font-medium text-warning hover:bg-warning/20')}
            >
              前往数据源配置
            </Link>
          </div>
        </div>
      )}
      {/* [R159] 推送焦点名单: 自选太多时, 谁值得推送 */}
      <FocusBar />
      {/* [R60] 统一页面留白 */}
      <div className="min-h-0 flex-1 px-3 pb-4 pt-3 lg:px-4">
        <div className="mx-auto flex h-full w-full max-w-[1440px] flex-col gap-3 lg:flex-row">
          {/* 左栏: 触发记录 */}
          <section className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-xl border border-border bg-surface/40 shadow-lg shadow-black/5">
            <div className="flex items-center gap-3 border-b border-border/60 bg-surface/60 px-4 py-2.5">
              <SectionHeader icon={BellRing} title="触发记录" />
              {/* 过滤标签 */}
              <div className="flex flex-wrap items-center gap-0.5">
                {(['all', 'strategy', 'signal', 'price', 'market', 'sector', 'abnormal', 'volume_delta', 'date'] as const).map(f => (
                  <button
                    key={f}
                    onClick={() => setFilter(f)}
                    // [R454] 可点的控件按正文级 13px; 选中是全站那套反相
                    className={cn(
                      'h-7 rounded-btn border px-2 text-xs transition-colors cursor-pointer',
                      filter === f ? SELECTED : 'border-transparent text-muted hover:bg-elevated hover:text-foreground',
                    )}
                  >
                    {f === 'all' ? '全部' : TYPE_LABEL[f]}
                  </button>
                ))}
                {/* [R160] 焦点开关: 默认只看焦点内; 焦点外的仍记录, 切过去灰显 */}
                <button
                  onClick={() => setFocusOnly(v => !v)}
                  title={focusOnly ? '当前只看焦点内(持有 / 计划中 / 钉住)。点击含焦点外的' : '当前含焦点外的(灰显)。点击只看焦点内'}
                  className={buttonClass({ selected: focusOnly }, 'ml-1 h-7 px-2')}
                >
                  {focusOnly ? '只看焦点' : '含焦点外'}
                </button>
              </div>
              {/* 数量 + 清空 + 字段配置 */}
              <div className="ml-auto flex items-center gap-2 shrink-0">
                <button
                  onClick={() => setExtConfigOpen(true)}
                  title="配置行业/概念标签"
                  className={cn(
                    'inline-flex h-6 w-6 items-center justify-center rounded-lg border transition-ui cursor-pointer',
                    extConfigOpen ? 'border-accent/40 text-accent' : 'border-border/60 bg-surface text-muted hover:border-accent/40 hover:text-accent',
                  )}
                >
                  <Tags className="h-3.5 w-3.5" />
                </button>
                <span className="rounded-md bg-elevated/50 px-1.5 py-0.5 text-micro font-medium text-muted">{total}</span>
                {total > 0 && (
                  <button
                    onClick={() => setConfirmClear(true)}
                    className="inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-micro text-muted transition-colors hover:bg-danger/10 hover:text-danger cursor-pointer"
                  >
                    <Trash2 className="h-2.5 w-2.5" />清空
                  </button>
                )}
              </div>
            </div>
            <div className="min-h-0 flex-1 overflow-auto p-3.5">
              <AlertsList alertsQuery={alertsQuery} confirmClear={confirmClear} setConfirmClear={setConfirmClear} total={total} enterTs={enterTsRef.current} monitorExtFields={monitorExtFields} />
            </div>
          </section>

          {/* 右栏: 监控规则 */}
          <section className="flex min-h-0 w-full flex-col overflow-hidden rounded-xl border border-border bg-surface/40 shadow-lg shadow-black/5 lg:w-[400px] lg:shrink-0">
            <div className="flex items-center gap-3 border-b border-border/60 bg-surface/60 px-4 py-2.5">
              <SectionHeader icon={ListChecks} title="监控规则" />
              <span className="rounded-md bg-elevated/50 px-1.5 py-0.5 text-micro font-medium text-muted">{rulesCount}</span>
              <div className="ml-auto flex items-center gap-1">
                <button
                  onClick={() => setBatchChannelsOpen(true)}
                  disabled={rulesCount === 0}
                  title="批量设置推送渠道(飞书/企微/钉钉)—— 一次改所有规则, 不用逐条打开"
                  className="inline-flex h-6 w-6 items-center justify-center rounded-lg border border-border/60 bg-surface text-muted transition-ui hover:border-sky-400/40 hover:text-sky-300 disabled:opacity-30 disabled:cursor-not-allowed cursor-pointer"
                >
                  <BellRing className="h-3.5 w-3.5" />
                </button>
                <button
                  onClick={() => { setEditingRule(null); setEditorPreset(null); setEditorOpen(true) }}
                  title="新建规则"
                  className="inline-flex h-6 w-6 items-center justify-center rounded-lg border border-border/60 bg-surface text-muted transition-ui hover:border-accent/40 hover:text-accent hover:shadow-sm cursor-pointer"
                >
                  <Plus className="h-3.5 w-3.5" />
                </button>
                <button
                  onClick={() => setConfirmClearRules(true)}
                  disabled={rulesCount === 0}
                  title="清除全部规则"
                  className="inline-flex h-6 w-6 items-center justify-center rounded-lg border border-border/60 bg-surface text-muted transition-ui hover:border-danger/40 hover:text-danger disabled:opacity-30 disabled:cursor-not-allowed cursor-pointer"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </div>
            </div>
            <div className="min-h-0 flex-1 overflow-auto p-3.5">
              <RulesList
                rulesQuery={rulesQuery}
                onEdit={(r) => { setEditingRule(r); setEditorOpen(true) }}
              />
            </div>
          </section>
        </div>
      </div>

      <RuleEditorDialog
        open={editorOpen}
        rule={editingRule}
        preset={editorPreset}
        onClose={() => { setEditorOpen(false); setEditingRule(null); setEditorPreset(null) }}
      />

      <BatchChannelsDialog
        open={batchChannelsOpen}
        rulesCount={rulesCount}
        prefs={prefs}
        onClose={() => setBatchChannelsOpen(false)}
      />

      <ConfirmDialog
        open={confirmClearRules}
        title="清除全部监控规则?"
        message={`将删除全部 ${rulesCount} 条规则,此操作不可撤销。`}
        confirmText="清除"
        danger
        onCancel={() => setConfirmClearRules(false)}
        onConfirm={() => clearRulesMut.mutate()}
        pending={clearRulesMut.isPending}
      />

      <MonitorExtConfigDialog
        open={extConfigOpen}
        fields={monitorExtFields}
        onClose={() => setExtConfigOpen(false)}
      />
    </div>
  )
}

function SectionHeader({ icon: Icon, title }: { icon: any; title: string }) {
  return (
    <div className="flex items-center gap-1.5 shrink-0">
      <Icon className="h-4 w-4 text-accent" />
      <h2 className={cn('whitespace-nowrap', TYPE.card)}>{title}</h2>
    </div>
  )
}

// ── 触发记录列表 ──────────────────────────────────────
function AlertsList({ alertsQuery, confirmClear, setConfirmClear, total, enterTs, monitorExtFields }: {
  alertsQuery: ReturnType<typeof useQuery>
  confirmClear: boolean
  setConfirmClear: (v: boolean) => void
  total: number
  enterTs: number
  monitorExtFields: { concept: MonitorExtFieldItem | null; industry: MonitorExtFieldItem | null }
}) {
  const qc = useQueryClient()
  const navigate = useNavigate()
  const [confirmTs, setConfirmTs] = useState<number | null>(null)
  const resetTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const [previewEv, setPreviewEv] = useState<AlertEvent | null>(null)
  const [memberPreview, setMemberPreview] = useState<{ symbol: string; name?: string } | null>(null)
  const [previewNavList, setPreviewNavList] = useState<NavItem[]>([])
  const [dimensionTarget, setDimensionTarget] = useState<DimensionMembersTarget | null>(null)
  const customNames = useCustomSignalNames()

  const clearMut = useMutation({
    mutationFn: api.alertsClear,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['alerts'] }); setConfirmClear(false); resetBadge() },
  })
  const delMut = useMutation({
    mutationFn: (ts: number) => api.alertDelete(ts),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['alerts'] }),
  })

  // 点击删除: 第一次进入确认态, 第二次真删, 3 秒后自动复位
  const handleClickDelete = (ts: number) => {
    if (confirmTs === ts) {
      // 第二次点击 → 真删
      if (resetTimer.current) clearTimeout(resetTimer.current)
      setConfirmTs(null)
      delMut.mutate(ts)
    } else {
      // 第一次点击 → 进入确认态, 3 秒后自动复位
      setConfirmTs(ts)
      if (resetTimer.current) clearTimeout(resetTimer.current)
      resetTimer.current = setTimeout(() => setConfirmTs(null), 3000)
    }
  }

  const events = (alertsQuery.data as any)?.alerts ?? []

  // 切股导航列表: 有 symbol 的触发记录 (按展示顺序)
  const alertsNavItems = useMemo(
    () => toNavItems(events.filter((ev: AlertEvent) => ev.symbol)),
    [events],
  )
  const handlePreviewEvent = useCallback((ev: AlertEvent) => {
    setPreviewEv(ev)
    setPreviewNavList(alertsNavItems)
  }, [alertsNavItems])
  // 弹窗内切股: 来自成分弹窗则更新 memberPreview, 否则按 symbol 找到对应事件 (保住 triggerInfo)
  const handleNavigate = useCallback((sym: string, name?: string) => {
    if (memberPreview) { setMemberPreview({ symbol: sym, name }); return }
    const ev = events.find((e: AlertEvent) => e.symbol === sym)
    if (ev) setPreviewEv(ev)
  }, [memberPreview, events])

  return (
    <div className="space-y-3">
      {alertsQuery.isLoading ? (
        <div className="space-y-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} h="h-14" rounded="rounded-card" />
          ))}
        </div>
      ) : events.length === 0 ? (
        <EmptyState
          icon={Bell}
          title="暂无触发记录"
          hint="监控规则命中后,触发记录会出现在这里。可在右侧配置规则,或在标的详情页加入监控。"
        />
      ) : (
        <div className="space-y-2">
              {events.map((ev: any, i: number) => {
            const sev = SEVERITY_CONFIG[ev.severity ?? 'info'] ?? SEVERITY_CONFIG.info
            const SevIcon = sev.icon
            const isNew = ev.ts > enterTs
            return (
              <motion.div
                key={`${ev.ts}-${ev.symbol ?? ''}-${ev.rule_name ?? ''}`}
                initial={isNew ? { opacity: 0, y: -8, scale: 0.98 } : { opacity: 0, y: 4 }}
                animate={isNew ? {
                  opacity: [0, 1, 1, 0.85, 1],
                  scale: [0.98, 1, 1, 1.01, 1],
                  y: [-8, 0, 0, 0, 0],
                } : { opacity: 1, y: 0 }}
                transition={isNew ? { duration: 1.2, times: [0, 0.2, 0.5, 0.75, 1] } : { duration: 0.2, delay: Math.min(i * 0.02, 0.2) }}
                className={cn(
                  'group relative flex items-start gap-3 overflow-hidden rounded-lg border bg-surface pl-3.5 pr-3 py-2.5 shadow-sm transition-ui duration-expand hover:border-border hover:shadow-md hover:shadow-black/10 hover:-translate-y-px',
                  isNew ? 'border-accent/60 ring-1 ring-accent/30' : 'border-border/50',
                  ev.focus_muted && 'opacity-55 saturate-50',   // [R160] 焦点外: 只记录, 灰显
                )}
                title={ev.focus_muted ? '焦点外: 只记录, 没弹窗/没推送/不计徽标。想推就在「推送焦点」里钉住它' : undefined}
              >
                <div className={cn('absolute left-0 top-0 h-full w-0.5', sev.bar)} />
                <div className={cn('mt-px shrink-0', sev.iconCls)}>
                  <SevIcon className="h-4 w-4" />
                </div>
                <div className="min-w-0 flex-1">
                  {ev.source === 'strategy' ? (() => {
                    const sname = strategyName(ev.message ?? '')
                    const eventMeta = strategyEventMeta(ev.type)
                    const _pct = ev.change_pct ?? 0
                    return (
                      <>
                        <div className="flex items-center gap-2 flex-wrap">
                          {ev.symbol && (() => {
                            const board = boardTag(ev.symbol)
                            return (
                              <button
                                onClick={() => handlePreviewEvent(ev)}
                                className="inline-flex items-center gap-1.5 rounded hover:bg-elevated/50 px-1 -mx-1 transition-colors cursor-pointer"
                                title="点击查看日K"
                              >
                                <span className="font-mono text-xs font-medium text-foreground hover:text-accent">{ev.symbol}</span>
                                {board && (
                                  <span className={`inline-flex items-center justify-center h-3.5 w-3.5 rounded text-micro font-bold leading-none border ${board.color}`}>
                                    {board.label}
                                  </span>
                                )}
                                {ev.name && <span className="text-xs text-secondary truncate max-w-[8rem] hover:text-foreground">{ev.name}</span>}
                              </button>
                            )
                          })()}
                          {ev.price != null && (
                            <span className={cn('inline-flex items-center gap-0.5 text-xs font-mono', _pct >= 0 ? 'text-danger' : 'text-bear')}>
                              {_pct >= 0 ? <TrendingUp className="h-2.5 w-2.5" /> : <TrendingDown className="h-2.5 w-2.5" />}
                              {fmtPrice(ev.price)}
                            </span>
                          )}
                          {ev.change_pct != null && (
                            <span className={cn('text-xs font-mono font-medium',
                              _pct >= 0 ? 'text-danger' : 'text-bear')}>
                              {fmtPct(_pct)}
                            </span>
                          )}
                          <span className={cn('rounded border px-1.5 py-0.5 text-micro font-medium', SOURCE_BADGE_STYLE.strategy)}>
                            {sname}
                          </span>
                        </div>
                        {ev.symbol ? (
                          <div className="mt-1 flex min-w-0 items-center gap-1.5">
                            <span className={cn('shrink-0 text-xs font-medium', eventMeta.className)}>
                              {eventMeta.action}
                            </span>
                            {sname
                              ? <span className="text-xs font-medium text-warning">「{sname}」</span>
                              : ev.message && <span className="truncate text-micro text-muted">{ev.message}</span>}
                          </div>
                        ) : (
                          <div className="mt-1 truncate text-xs text-muted">{ev.message}</div>
                        )}
                        {ev.signals && ev.signals.length > 0 && (
                          <div className="mt-1.5 flex flex-wrap gap-1">
                            {ev.signals.map((signal: string) => (
                              <span key={signal} className="rounded bg-accent/8 px-1.5 py-0.5 text-micro text-accent/70">{cnSignal(signal, customNames)}</span>
                            ))}
                          </div>
                        )}
                      </>
                    )
                  })() : (
                    <>
                      <div className="flex items-center gap-2 flex-wrap">
                        {ev.source === 'sector' && (
                          <button
                            onClick={() => {
                              if (ev.sector_kind === 'index' && ev.symbol) {
                                navigate(`/indices?symbol=${encodeURIComponent(ev.symbol)}`)
                              } else if (ev.sector_source_field && ev.sector_value) {
                                setDimensionTarget({
                                  kind: ev.sector_kind as DimensionKind,
                                  value: ev.sector_value,
                                  sourceField: ev.sector_source_field,
                                })
                              }
                            }}
                            className="inline-flex items-center gap-1.5 rounded px-1 -mx-1 text-xs font-medium text-foreground transition-colors hover:bg-elevated/50 hover:text-accent cursor-pointer"
                            title={ev.sector_kind === 'index' ? '打开指数详情' : '查看成分股'}
                          >
                            <Tags className="h-3.5 w-3.5 text-cyan-600 dark:text-cyan-300" />
                            <span>{ev.sector_name ?? ev.name}</span>
                            {ev.symbol && <span className="font-mono text-micro text-muted">{ev.symbol}</span>}
                          </button>
                        )}
                        {ev.symbol && ev.source !== 'sector' && (() => {
                          const board = boardTag(ev.symbol)
                          return (
                            <button
                              onClick={() => handlePreviewEvent(ev)}
                              className="inline-flex items-center gap-1.5 rounded hover:bg-elevated/50 px-1 -mx-1 transition-colors cursor-pointer"
                              title="点击查看日K"
                            >
                              <span className="font-mono text-xs font-medium text-foreground hover:text-accent">{ev.symbol}</span>
                              {board && (
                                <span className={`inline-flex items-center justify-center h-3.5 w-3.5 rounded text-micro font-bold leading-none border ${board.color}`}>
                                  {board.label}
                                </span>
                              )}
                              {ev.name && <span className="text-xs text-secondary truncate max-w-[8rem] hover:text-foreground">{ev.name}</span>}
                            </button>
                          )
                        })()}
                        {ev.price != null && (
                          <span className={cn('inline-flex items-center gap-0.5 text-xs font-mono', (ev.change_pct ?? 0) >= 0 ? 'text-danger' : 'text-bear')}>
                            {(ev.change_pct ?? 0) >= 0 ? <TrendingUp className="h-2.5 w-2.5" /> : <TrendingDown className="h-2.5 w-2.5" />}
                            {fmtPrice(ev.price)}
                          </span>
                        )}
                        {ev.change_pct != null && (
                          <span className={cn('text-xs font-mono font-medium',
                            ev.change_pct >= 0 ? 'text-danger' : 'text-bear')}>
                            {fmtPct(ev.change_pct)}
                          </span>
                        )}
                        <span className={cn('rounded border px-1.5 py-0.5 text-micro font-medium', SOURCE_BADGE_STYLE[ev.source] ?? 'bg-elevated text-muted border-border')}>
                          {(() => {
                            // 优先用规则名 (如 "策略监控 · 空中加油" → "空中加油"); 退回到 type 标签
                            const rn = ev.rule_name ?? ''
                            const dotIdx = rn.indexOf(' · ')
                            return dotIdx >= 0 ? rn.slice(dotIdx + 3) : (rn || (TYPE_LABEL[ev.source] ?? ev.source))
                          })()}
                        </span>
                      </div>
                      {/* 详情行: 实际命中信号为主 (有 signals 时); 无 truth 命中则回退条件摘要 */}
                      {ev.signals && ev.signals.length > 0 ? (
                        <div className="mt-1 flex flex-wrap items-center gap-x-1.5 gap-y-1 text-xs">
                          <span className="text-muted">命中</span>
                          {ev.signals.map((s: string, j: number) => (
                            <span key={j} className="rounded bg-accent/10 px-1.5 py-0.5 text-micro font-medium text-accent">{cnSignal(s, customNames)}</span>
                          ))}
                          {ev.price != null && (
                            <>
                              <span className="text-muted">·</span>
                              <span className="text-muted">现价</span>
                              <span className="font-mono text-foreground/90">{fmtPrice(ev.price)}</span>
                            </>
                          )}
                        </div>
                      ) : (ev.conditions && ev.conditions.length > 0) ? (
                        <div className="mt-1 flex flex-wrap items-center gap-x-1.5 gap-y-0.5 text-xs">
                          <span className="text-muted">命中</span>
                          {ev.conditions.map((c: MonitorCondition, ci: number) => (
                            <span key={ci} className="inline-flex items-center gap-0.5">
                              {ci > 0 && <span className="text-secondary">{ev.logic === 'or' ? '或' : '且'}</span>}
                              {c.op === 'truth' ? (
                                <span className="text-accent/80">{cnSignal(c.field, customNames)}</span>
                              ) : (
                                <span className="text-foreground/80 font-mono">{cnSignal(c.field, customNames)}{c.op}{c.value}</span>
                              )}
                            </span>
                          ))}
                          {ev.price != null && (
                            <>
                              <span className="text-muted">·</span>
                              <span className="text-muted">现价</span>
                              <span className="font-mono text-foreground/90">{fmtPrice(ev.price)}</span>
                            </>
                          )}
                        </div>
                      ) : (
                        <div className="mt-1 flex items-center gap-2">
                          <span className="text-xs">{renderMessage(ev.source, ev.message)}</span>
                        </div>
                      )}
                      {/* 规则全量条件 (次要灰字): 已有命中信号主行时展示, 供回溯规则定义 */}
                      {ev.signals && ev.signals.length > 0 && ev.conditions && ev.conditions.length > 0 && (
                        <div className="mt-1 flex flex-wrap items-center gap-x-1 gap-y-0.5 text-micro text-muted/70">
                          <span>规则</span>
                          {ev.conditions.map((c: MonitorCondition, ci: number) => (
                            <span key={ci} className="inline-flex items-center gap-0.5">
                              {ci > 0 && <span>{ev.logic === 'or' ? '或' : '且'}</span>}
                              {c.op === 'truth' ? (
                                <span>{cnSignal(c.field, customNames)}</span>
                              ) : (
                                <span className="font-mono">{cnSignal(c.field, customNames)}{c.op}{c.value}</span>
                              )}
                            </span>
                          ))}
                        </div>
                      )}
                    </>
                  )}
                  <AlertExtTags
                    ev={ev}
                    fields={monitorExtFields}
                    onTagClick={(kind, value, sourceField) => {
                      if (sourceField) setDimensionTarget({ kind, value, sourceField })
                    }}
                  />
                </div>
                <div className="flex shrink-0 flex-col items-end gap-1">
                  <span className="text-micro text-muted/60 font-mono">
                    {new Date(ev.ts).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })}
                  </span>
                  {confirmTs === ev.ts ? (
                    // 确认态: 红色实心按钮 (原删除图标位置), 再点确认删除
                    <button
                      onClick={() => handleClickDelete(ev.ts)}
                      title="再次点击确认删除"
                      className="inline-flex items-center gap-1 rounded-md bg-danger/15 px-1.5 py-0.5 text-micro font-medium text-danger border border-danger/30 animate-pulse cursor-pointer"
                    >
                      <Trash2 className="h-2.5 w-2.5" />确认
                    </button>
                  ) : (
                    <button
                      onClick={() => handleClickDelete(ev.ts)}
                      disabled={delMut.isPending}
                      title="删除"
                      className="rounded p-1 text-muted/0 transition-colors group-hover:text-muted/40 hover:!text-danger hover:bg-danger/10 cursor-pointer"
                    >
                      <Trash2 className="h-3 w-3" />
                    </button>
                  )}
                </div>
              </motion.div>
            )
          })}
        </div>
      )}

      <ConfirmDialog
        open={confirmClear}
        title="清空全部触发记录?"
        message={`将删除全部 ${total} 条记录,此操作不可撤销。`}
        confirmText="清空"
        danger
        onCancel={() => setConfirmClear(false)}
        onConfirm={() => clearMut.mutate()}
        pending={clearMut.isPending}
      />

      <StockPreviewDialog
        symbol={memberPreview?.symbol ?? previewEv?.symbol ?? null}
        name={memberPreview?.name ?? previewEv?.name ?? undefined}
        triggerInfo={previewEv ? {
          price: previewEv.price ?? null,
          changePct: previewEv.change_pct ?? null,
          ts: previewEv.ts,
          signals: previewEv.signals,
          message: previewEv.message,
        } : null}
        navList={previewNavList}
        onNavigate={handleNavigate}
        onClose={() => { setPreviewEv(null); setMemberPreview(null); setPreviewNavList([]) }}
      />

      <DimensionMembersDialog
        target={dimensionTarget}
        onClose={() => setDimensionTarget(null)}
        onStockClick={(symbol, name, navList) => {
          setDimensionTarget(null)
          setMemberPreview({ symbol, name })
          setPreviewNavList(navList ?? alertsNavItems)
        }}
      />
    </div>
  )
}

// ── 监控规则列表 ──────────────────────────────────────
function RulesList({ rulesQuery, onEdit }: {
  rulesQuery: ReturnType<typeof useQuery>
  onEdit: (rule: MonitorRule) => void
}) {
  const qc = useQueryClient()
  const [confirmId, setConfirmId] = useState<string | null>(null)
  const [previewSymbol, setPreviewSymbol] = useState<string | null>(null)
  const resetTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const customNames = useCustomSignalNames()

  const rules: MonitorRule[] = (rulesQuery.data as any)?.rules ?? []

  // 分组作用域规则: 拉取分组定义与成员, 展示分组名/成员数 chip (点击跳转自选页对应分组)
  const hasGroupRules = rules.some(r => r.scope === 'watchlist_group')
  const groupsQ = useQuery({
    queryKey: QK.watchlistGroups,
    queryFn: api.watchlistGroups,
    enabled: hasGroupRules,
  })
  const watchlistQ = useQuery({
    queryKey: QK.watchlist,
    queryFn: api.watchlistList,
    enabled: hasGroupRules,
  })
  const groupMeta = useMemo(() => {
    const meta: Record<string, { name: string; color: string; count: number }> = {}
    for (const g of groupsQ.data?.groups ?? []) {
      meta[g.id] = { name: g.name, color: g.color, count: 0 }
    }
    for (const entry of watchlistQ.data?.symbols ?? []) {
      for (const gid of entry.group_ids ?? []) {
        if (meta[gid]) meta[gid].count += 1
      }
    }
    return meta
  }, [groupsQ.data, watchlistQ.data])

  // 收集所有规则的股票代码, 批量查名称
  const allSymbols = useMemo(() => {
    const set = new Set<string>()
    for (const r of rules) {
      if (r.scope === 'symbols') r.symbols.forEach(s => set.add(s))
    }
    return Array.from(set)
  }, [rules])
  const namesQuery = useQuery({
    queryKey: ['instrument-names', allSymbols.join(',')],
    queryFn: () => api.instrumentNames(allSymbols),
    enabled: allSymbols.length > 0,
    staleTime: 300000,
  })
  const symbolNames = namesQuery.data?.names ?? {}

  // 策略规则即使限定了个股作用域，标题也应显示策略名，而不是第一只股票。
  // 复用策略页的完整策略池查询，兼容日线、分钟和自定义策略；旧规则名不规范时
  // 也能用 strategy_id 找回当前真实名称。
  const hasStrategyRules = rules.some(r => r.type === 'strategy' && !!r.strategy_id)
  const strategiesQ = useQuery({
    queryKey: QK.screenerStrategies('all', 'all'),
    queryFn: () => api.screenerStrategies(undefined, 'all'),
    enabled: hasStrategyRules,
    staleTime: 60_000,
  })
  const strategyNames = useMemo(() => {
    const names: Record<string, string> = {}
    for (const strategy of strategiesQ.data?.presets ?? []) names[strategy.id] = strategy.name
    return names
  }, [strategiesQ.data])
  // 切股导航列表: 个股规则 (取第一个 symbol, 按展示顺序)
  const rulesNavItems = useMemo(
    () => rules
      .filter(r => r.scope === 'symbols' && r.symbols.length > 0)
      .map(r => ({ symbol: r.symbols[0], name: symbolNames[r.symbols[0]] ?? undefined })),
    [rules, symbolNames],
  )

  const del = useMutation({
    mutationFn: api.monitorRuleDelete,
    onSuccess: () => qc.invalidateQueries({ queryKey: QK.monitorRules }),
  })
  const toggleEnabled = (rule: MonitorRule) => {
    const { runtime_warning: _runtimeWarning, ...persistedRule } = rule
    api.monitorRuleSave({ ...persistedRule, enabled: !rule.enabled }).then(() =>
      qc.invalidateQueries({ queryKey: QK.monitorRules }),
    )
  }

  // 点击删除: 第一次进入确认态, 第二次真删, 3 秒后自动复位
  const handleClickDelete = (id: string) => {
    if (confirmId === id) {
      if (resetTimer.current) clearTimeout(resetTimer.current)
      setConfirmId(null)
      del.mutate(id)
    } else {
      setConfirmId(id)
      if (resetTimer.current) clearTimeout(resetTimer.current)
      resetTimer.current = setTimeout(() => setConfirmId(null), 3000)
    }
  }

  return (
    <div className="space-y-2.5">
      {rulesQuery.isLoading ? (
        <div className="space-y-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} h="h-16" rounded="rounded-card" />
          ))}
        </div>
      ) : rules.length === 0 ? (
        <EmptyState
          icon={RadioTower}
          title="暂无监控规则"
          hint="点击标题栏「+」新建规则,或在标的详情页点「加监控」快速添加。"
        />
      ) : (
        rules.map(r => {
          // 名称截取: "策略监控 · MACD金叉" → "MACD金叉", "信号监控 · 300750.SZ" → "信号监控"
          const dotIdx = r.name.indexOf(' · ')
          const displayName = dotIdx >= 0 ? r.name.slice(dotIdx + 3) : r.name
          const strategyDisplayName = r.type === 'strategy' && r.strategy_id
            ? (strategyNames[r.strategy_id] ?? (dotIdx >= 0 ? displayName : r.strategy_id))
            : displayName
          return (
            <motion.div
              key={r.id}
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.2 }}
              className={cn(
                'group relative overflow-hidden rounded-lg border pl-3.5 pr-2.5 py-2 shadow-sm transition-ui duration-expand hover:shadow-md hover:shadow-black/10',
                r.enabled
                  ? 'border-border/50 bg-surface hover:border-accent/30'
                  : 'border-border/30 bg-surface/40 opacity-70 hover:opacity-100',
              )}
            >
              {/* 左侧状态条 */}
              <div className={cn('absolute left-0 top-0 h-full w-0.5', r.enabled ? 'bg-accent/50' : 'bg-border')} />

              {/* 第一行: 分类标签 + 名称 + 操作按钮 */}
              <div className="flex items-center justify-between gap-2">
                <div className="flex min-w-0 items-center gap-2">
                  <span className={cn('shrink-0 rounded px-1.5 py-0.5 text-micro font-semibold', SOURCE_BADGE_STYLE[r.type] ?? 'bg-elevated text-muted')}>
                    {TYPE_LABEL[r.type]}
                  </span>
                  {r.lot_id && (
                    <span className="shrink-0 rounded px-1.5 py-0.5 text-micro font-semibold bg-emerald-400/10 text-emerald-500" title="由「持仓提醒」页托管, 请在持仓提醒页修改或删除">批次</span>
                  )}
                  {r.asset_type === 'index' && (
                    <span className="shrink-0 rounded px-1.5 py-0.5 text-micro font-semibold bg-sky-500/10 text-sky-400">指数</span>
                  )}
                  {/* 策略类型始终显示策略名；其他个股类型才显示可点击的代码+名称。 */}
                  {r.type === 'strategy' ? (
                    <h3
                      className={cn('truncate text-xs font-medium', r.enabled ? 'text-foreground' : 'text-muted')}
                      title={strategyDisplayName}
                    >
                      {strategyDisplayName}
                    </h3>
                  ) : r.scope === 'symbols' && r.symbols.length > 0 ? (
                    <button
                      onClick={() => setPreviewSymbol(r.symbols[0])}
                      className="inline-flex items-center gap-1 min-w-0 hover:bg-elevated/50 rounded px-0.5 transition-colors cursor-pointer"
                      title={`查看 ${r.symbols[0]} 日K`}
                    >
                      <span className="font-mono text-xs font-medium text-foreground hover:text-accent">{r.symbols[0]}</span>
                      {symbolNames[r.symbols[0]] && <span className="text-xs text-secondary truncate">{symbolNames[r.symbols[0]]}</span>}
                    </button>
                  ) : r.scope === 'watchlist_group' && r.group_id ? (
                    (() => {
                      const meta = groupMeta[r.group_id]
                      if (!meta) {
                        return <span className="text-xs text-warning truncate" title={r.name}>分组已删除</span>
                      }
                      return (
                        <Link
                          to={`/watchlist?group=${r.group_id}`}
                          className="inline-flex min-w-0 items-center gap-1.5 rounded px-0.5 transition-colors hover:bg-elevated/50 cursor-pointer"
                          title={`「${meta.name}」分组 · 当前 ${meta.count} 只 · 点击查看分组`}
                        >
                          <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${resolveWatchlistGroupColor(meta.color).dot}`} />
                          <span className="truncate text-xs font-medium text-foreground hover:text-accent">{meta.name}</span>
                          <span className="shrink-0 font-mono text-micro tabular-nums text-muted">{meta.count}只</span>
                          <span className="shrink-0 text-micro text-muted/60">· 分组作用域</span>
                        </Link>
                      )
                    })()
                  ) : (
                    <h3 className={cn('text-xs font-medium truncate', r.enabled ? 'text-foreground' : 'text-muted')}>{displayName}</h3>
                  )}
                  {!r.enabled && <span className="shrink-0 text-micro text-secondary">· 停用</span>}
                </div>
                <div className="flex items-center gap-0.5 shrink-0">
                  {r.lot_id ? (
                    <span
                      className="inline-flex items-center rounded-md border border-border/60 bg-elevated/60 px-1.5 py-0.5 text-micro text-secondary"
                      title="由「持仓提醒」页生成的规则, 该页托管; 启停/修改/删除请到持仓提醒页"
                    >
                      批次托管
                    </span>
                  ) : (
                    <>
                      <button
                        onClick={() => toggleEnabled(r)}
                        title={r.enabled ? '停用' : '启用'}
                        className={cn(
                          'p-1 rounded-md transition-ui cursor-pointer',
                          r.enabled ? 'text-accent hover:bg-accent/10' : 'text-muted hover:bg-elevated hover:text-accent',
                        )}
                      >
                        <Zap className="h-3.5 w-3.5" />
                      </button>
                      <button
                        onClick={() => onEdit(r)}
                        className="p-1 rounded-md text-secondary transition-ui hover:bg-accent/10 hover:text-accent cursor-pointer"
                        title="编辑"
                      >
                        <Settings2 className="h-3.5 w-3.5" />
                      </button>
                      {confirmId === r.id ? (
                        <button
                          onClick={() => handleClickDelete(r.id)}
                          title="再次点击确认删除"
                          className="inline-flex items-center gap-1 rounded-md bg-danger/15 px-1.5 py-0.5 text-micro font-medium text-danger border border-danger/30 animate-pulse cursor-pointer"
                        >
                          <Trash2 className="h-2.5 w-2.5" />确认
                        </button>
                      ) : (
                        <button
                          onClick={() => handleClickDelete(r.id)}
                          disabled={del.isPending}
                          className="p-1 rounded-md text-secondary transition-ui hover:bg-danger/10 hover:text-danger cursor-pointer"
                          title="删除"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      )}
                    </>
                  )}
                </div>
              </div>

              {r.runtime_warning && (
                <div className="mt-1 flex items-center gap-1 text-micro text-warning">
                  <AlertTriangle className="h-3 w-3 shrink-0" />
                  <span className="truncate" title={r.runtime_warning}>{r.runtime_warning}</span>
                </div>
              )}

              {/* 第二行: 类型摘要 */}
              {r.type === 'sector' ? (
                <div className="mt-1 flex min-w-0 flex-wrap items-center gap-1 pl-0.5">
                  {(r.sector_targets ?? []).slice(0, 3).map(target => (
                    <span key={target.key} className="max-w-28 truncate rounded bg-cyan-500/8 px-1.5 py-0.5 text-micro text-cyan-700 dark:text-cyan-300">
                      {target.name}
                    </span>
                  ))}
                  {(r.sector_targets?.length ?? 0) > 3 && (
                    <span className="text-micro text-muted">+{(r.sector_targets?.length ?? 0) - 3}</span>
                  )}
                  <span className="text-micro text-secondary">·</span>
                  <span className="text-micro text-secondary">
                    {r.sector_trigger === 'momentum' ? `${r.window_minutes ?? 5}分钟异动` : '涨跌幅'}
                    {r.direction === 'down' ? ' ≤ -' : ' ≥ '}{r.threshold_pct ?? 1}%
                  </span>
                </div>
              ) : r.type === 'abnormal' ? (
                <div className="mt-1 flex min-w-0 flex-wrap items-center gap-1 pl-0.5">
                  <span className="rounded bg-orange-500/8 px-1.5 py-0.5 text-micro text-orange-500 dark:text-orange-400">
                    接近度 ≥ {r.threshold_pct ?? 70}%
                  </span>
                  <span className="rounded bg-elevated px-1.5 py-0.5 text-micro text-secondary">
                    {r.abnormal_window && r.abnormal_window !== 'any' ? `${r.abnormal_window.toUpperCase()} 窗口` : '全部窗口'}
                  </span>
                  <span className="rounded bg-elevated px-1.5 py-0.5 text-micro text-secondary">
                    {r.direction === 'up' ? '涨势偏离' : r.direction === 'down' ? '跌势偏离' : '涨跌双向'}
                  </span>
                </div>
              ) : r.type === 'date' ? (
                <div className="mt-1 flex items-center gap-1 pl-0.5 text-micro text-secondary">
                  <span>提醒 {r.remind_date ?? ''}</span>
                  {(r.lead_days ?? 0) > 0 && <span>· 提前{r.lead_days}天</span>}
                  <span>· 仅交易日盘中评估</span>
                </div>
              ) : r.type === 'volume_delta' ? (
                <div className="mt-1 flex min-w-0 flex-wrap items-center gap-1 pl-0.5">
                  <span className="rounded bg-indigo-500/8 px-1.5 py-0.5 text-micro font-mono text-indigo-500 dark:text-indigo-300">
                    {r.metric === 'amount'
                      ? `单轮增量 ≥ ${Math.round((r.threshold_amount ?? 1e6) / 1e4).toLocaleString()} 万元`
                      : `单轮增量 ≥ ${(r.threshold_volume ?? 9000).toLocaleString()} 手`}
                  </span>
                  <span className="rounded bg-elevated px-1.5 py-0.5 text-micro text-secondary">
                    冷却 {Math.round((r.cooldown_seconds ?? 300) / 60)} 分钟
                  </span>
                  {r.basic_filter && Object.values(r.basic_filter).some(v => v !== null && v !== false) && (
                    <span className="rounded bg-elevated px-1.5 py-0.5 text-micro text-secondary">
                      基础过滤{r.basic_filter.exclude_st ? ' · 剔除ST' : ''}
                    </span>
                  )}
                </div>
              ) : r.type === 'strategy' && r.strategy_id ? (
                <div className="mt-1 flex flex-wrap items-center gap-1 pl-0.5">
                  {(r.score_min != null || r.score_max != null) && (
                    <span className="rounded bg-warning/10 px-1.5 py-0.5 text-micro font-mono text-warning">
                      评分 {r.score_min ?? 0}–{r.score_max ?? 100}
                    </span>
                  )}
                  {(r.notify_events ?? LEGACY_STRATEGY_NOTIFY_EVENTS).map(event => {
                    const option = STRATEGY_NOTIFY_EVENT_OPTIONS.find(item => item.key === event)
                    return option ? (
                      <span key={event} className="rounded bg-elevated px-1.5 py-0.5 text-micro text-secondary">
                        {option.label}
                      </span>
                    ) : null
                  })}
                </div>
              ) : r.conditions.length > 0 && (
                <div className="mt-0.5 flex items-center gap-1 pl-0.5">
                  <span className="text-micro text-secondary shrink-0">条件</span>
                  <span className="min-w-0 flex flex-wrap items-center gap-x-1 gap-y-0.5 text-micro">
                    {r.conditions.slice(0, 3).map((c, i) => (
                      <span key={i} className="inline-flex items-center gap-0.5">
                        {i > 0 && <span className="text-secondary">{r.logic === 'and' ? '且' : '或'}</span>}
                        {c.op === 'truth' ? (
                          <span className="text-accent/80">{cnSignal(c.field, customNames)}</span>
                        ) : (
                          <span className="text-foreground/80 font-mono">{cnSignal(c.field, customNames)}{c.op}{c.value}</span>
                        )}
                      </span>
                    ))}
                    {r.conditions.length > 3 && <span className="text-secondary">+{r.conditions.length - 3}</span>}
                  </span>
                </div>
              )}
            </motion.div>
          )
        })
      )}

      <StockPreviewDialog
        symbol={previewSymbol}
        name={previewSymbol ? symbolNames[previewSymbol] : undefined}
        navList={rulesNavItems}
        onNavigate={(sym) => setPreviewSymbol(sym)}
        onClose={() => setPreviewSymbol(null)}
      />
    </div>
  )
}

// ── 规则编辑对话框 ────────────────────────────────────
function RuleEditorDialog({ open, rule, preset, onClose }: {
  open: boolean
  rule: MonitorRule | null
  preset?: Partial<MonitorRule> | null
  onClose: () => void
}) {
  const backdrop = useDialogBackdrop(onClose)
  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-50 flex items-start justify-center overflow-auto bg-black/40 backdrop-blur-sm p-4"
          {...backdrop}
        >
          <motion.div
            initial={{ opacity: 0, scale: 0.96, y: 8 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.96, y: 8 }}
            transition={{ duration: 0.15 }}
            className="mt-4 w-full max-w-3xl"
            onClick={e => e.stopPropagation()}
          >
            <RuleEditor
              rule={rule}
              preset={preset ?? undefined}
              onClose={onClose}
              onSaved={onClose}
            />
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}

// ── 确认对话框 ────────────────────────────────────────
/** [fork 增强] 批量设置推送渠道: 一次改所有监控规则, 不用逐条打开点钉钉 */
function BatchChannelsDialog({ open, rulesCount, prefs, onClose }: {
  open: boolean
  rulesCount: number
  prefs: ReturnType<typeof usePreferences>['data']
  onClose: () => void
}) {
  const qc = useQueryClient()
  const [channels, setChannels] = useState<string[]>([])
  const [mode, setMode] = useState<'set' | 'add' | 'remove'>('add')
  const mut = useMutation({
    mutationFn: () => api.monitorRulesBatchChannels({ channels, mode }),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: QK.monitorRules })
      toast(`已更新 ${r.updated} 条规则的推送渠道`, 'success')
      onClose()
    },
    onError: (e: Error) => toast(`批量设置失败: ${e.message}`, 'error'),
  })
  const channelDefs = [
    { key: 'feishu', label: '飞书', configured: !!prefs?.feishu_webhook_url },
    { key: 'wecom', label: '企业微信', configured: !!prefs?.wecom_webhook_url },
    { key: 'dingtalk', label: '钉钉', configured: !!prefs?.dingtalk_webhook_url },
  ]
  const modeDefs = [
    { key: 'add' as const, label: '追加所选', hint: '在各规则原有渠道上加上所选(最常用)' },
    { key: 'set' as const, label: '设为所选', hint: '所有规则的渠道整体替换为所选(可清空)' },
    { key: 'remove' as const, label: '移除所选', hint: '从各规则里去掉所选渠道' },
  ]
  const canApply = mode === 'set' || channels.length > 0
  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4"
          onClick={onClose}
        >
          <motion.div
            initial={{ opacity: 0, scale: 0.96 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.96 }}
            transition={{ duration: 0.15 }}
            className="w-full max-w-sm rounded-2xl border border-border bg-surface p-5 shadow-2xl"
            onClick={e => e.stopPropagation()}
          >
            <h3 className={TYPE.section}>批量设置推送渠道</h3>
            <p className="mt-1.5 text-xs text-muted">作用于全部 {rulesCount} 条监控规则;站内通知恒开,不受影响。</p>
            <div className="mt-3 flex flex-wrap gap-3">
              {channelDefs.map(c => (
                <label key={c.key} className={cn('inline-flex items-center gap-2 text-xs', c.configured ? 'text-foreground' : 'text-muted/50')}>
                  <input
                    type="checkbox"
                    checked={channels.includes(c.key)}
                    disabled={!c.configured}
                    onChange={() => setChannels(cur => cur.includes(c.key) ? cur.filter(x => x !== c.key) : [...cur, c.key])}
                    className="h-3.5 w-3.5 accent-sky-500"
                  />
                  {c.label}
                  {!c.configured && <span className="text-micro">未配置</span>}
                </label>
              ))}
            </div>
            <div className="mt-3 space-y-1.5">
              {modeDefs.map(m => (
                <label key={m.key} className="flex items-start gap-2 text-xs text-foreground cursor-pointer">
                  <input type="radio" name="batch-ch-mode" checked={mode === m.key} onChange={() => setMode(m.key)} className="mt-0.5 h-3.5 w-3.5 accent-sky-500" />
                  <span>
                    {m.label}
                    <span className="ml-1.5 text-micro text-muted">{m.hint}</span>
                  </span>
                </label>
              ))}
            </div>
            {mode === 'set' && channels.length === 0 && (
              <p className="mt-2 text-micro text-warning">当前选择会清空所有规则的外部推送渠道(只留站内)。</p>
            )}
            <div className="mt-4 flex justify-end gap-2">
              <button onClick={onClose} className="px-3 py-1.5 rounded-btn bg-elevated text-secondary text-xs cursor-pointer">取消</button>
              <button
                onClick={() => mut.mutate()}
                disabled={mut.isPending || !canApply}
                className="px-3 py-1.5 rounded-btn bg-accent text-base text-xs font-medium disabled:opacity-50 cursor-pointer"
              >
                {mut.isPending ? '应用中…' : `应用到 ${rulesCount} 条规则`}
              </button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}


function ConfirmDialog({ open, title, message, confirmText, danger, pending, onCancel, onConfirm }: {
  open: boolean
  title: string
  message: string
  confirmText?: string
  danger?: boolean
  pending?: boolean
  onCancel: () => void
  onConfirm: () => void
}) {
  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4"
          onClick={onCancel}
        >
          <motion.div
            initial={{ opacity: 0, scale: 0.96 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.96 }}
            transition={{ duration: 0.15 }}
            className="w-full max-w-sm rounded-2xl border border-border bg-surface p-5 shadow-2xl"
            onClick={e => e.stopPropagation()}
          >
            <h3 className={TYPE.section}>{title}</h3>
            <p className="mt-1.5 text-xs text-muted">{message}</p>
            <div className="mt-4 flex justify-end gap-2">
              <button onClick={onCancel} className="px-3 py-1.5 rounded-btn bg-elevated text-secondary text-xs cursor-pointer">取消</button>
              <button
                onClick={onConfirm}
                disabled={pending}
                className={cn(
                  'px-3 py-1.5 rounded-btn text-xs font-medium disabled:opacity-50 cursor-pointer',
                  danger ? 'bg-danger text-base' : 'bg-accent text-base',
                )}
              >
                {confirmText ?? '确定'}
              </button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}

/** 监控中心 ext 字段配置弹窗: 选概念/行业字段, 保存到 preferences.monitor_ext_fields */
function MonitorExtConfigDialog({ open, fields, onClose }: {
  open: boolean
  fields: { concept: MonitorExtFieldItem | null; industry: MonitorExtFieldItem | null }
  onClose: () => void
}) {
  const qc = useQueryClient()
  const [concept, setConcept] = useState<MonitorExtFieldItem | null>(fields.concept)
  const [industry, setIndustry] = useState<MonitorExtFieldItem | null>(fields.industry)
  useEffect(() => { setConcept(fields.concept); setIndustry(fields.industry) }, [fields.concept, fields.industry])

  const schema = useQuery({
    queryKey: QK.extDataSchemaAll,
    queryFn: api.extDataSchemaAll,
    enabled: open,
    staleTime: 60_000,
  })
  // 下拉选项: 按扩展表分组 → [{ group: 表名, options: [{value, label}] }]
  const groups = useMemo(() => {
    return (schema.data?.items ?? []).map(tbl => ({
      group: tbl.label || tbl.id,
      options: tbl.columns.map(col => ({
        value: `${tbl.id}.${col.name}`,
        label: col.label || col.name,
      })),
    }))
  }, [schema.data])

  const handleSave = async () => {
    await api.updateRealtimeMonitorConfig({ monitor_ext_fields: { concept, industry } })
    qc.invalidateQueries({ queryKey: QK.preferences })
    onClose()
  }

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4"
          onClick={onClose}
        >
          <motion.div
            initial={{ opacity: 0, scale: 0.96 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.96 }}
            transition={{ duration: 0.15 }}
            className="w-full max-w-md rounded-2xl border border-border bg-surface p-5 shadow-2xl max-h-[85vh] overflow-y-auto"
            onClick={e => e.stopPropagation()}
          >
            <div className="flex items-center gap-2 mb-4">
              <Tags className="h-4 w-4 text-accent" />
              <h3 className={TYPE.section}>个股通知标签配置</h3>
            </div>
            <p className="text-xs text-muted mb-4">选择在触发记录和推送通知中显示的行业/概念字段,留空则不显示。</p>
            <div className="space-y-4">
              <ExtFieldSection label="行业字段" value={industry} onChange={setIndustry} groups={groups} loading={schema.isLoading} />
              <ExtFieldSection label="概念字段" value={concept} onChange={setConcept} groups={groups} loading={schema.isLoading} />
            </div>
            <div className="mt-5 flex justify-end gap-2">
              <button onClick={onClose} className="px-3 py-1.5 rounded-btn text-xs text-secondary hover:text-foreground transition-colors cursor-pointer">取消</button>
              <button onClick={handleSave} className="px-3 py-1.5 rounded-btn text-xs font-medium bg-accent text-base cursor-pointer">保存</button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}

/** 单个 ext 字段配置区: 字段下拉 + 显示前N个 + 隐藏指定位置 */
function ExtFieldSection({ label, value, onChange, groups, loading }: {
  label: string
  value: MonitorExtFieldItem | null
  onChange: (v: MonitorExtFieldItem | null) => void
  groups: { group: string; options: { value: string; label: string }[] }[]
  loading: boolean
}) {
  const field = value?.field ?? ''
  const maxTags = value?.maxTags ?? 0
  const hidden = value?.hiddenIndices ?? []

  // 选/换字段时, 保留已有 maxTags/hiddenIndices 配置
  const pickField = (f: string | null) => {
    onChange(f ? { field: f, maxTags: value?.maxTags, hiddenIndices: value?.hiddenIndices } : null)
  }
  const setMaxTags = (n: number) => {
    onChange({ field, maxTags: n, hiddenIndices: n > 0 ? hidden.filter(i => i < n) : undefined })
  }
  const toggleHidden = (i: number) => {
    const next = hidden.includes(i) ? hidden.filter(x => x !== i) : [...hidden, i]
    onChange({ field, maxTags, hiddenIndices: next.length ? next : undefined })
  }

  return (
    <div className="space-y-2">
      <label className="text-xs text-secondary block">{label}</label>
      <div className="flex items-center gap-2">
        <select
          value={field}
          onChange={e => pickField(e.target.value || null)}
          disabled={loading}
          className="flex-1 min-w-0 h-8 bg-elevated border border-border rounded text-xs text-foreground px-2 focus:outline-none focus:border-accent/50"
        >
          <option value="">不显示</option>
          {groups.map(g => (
            <optgroup key={g.group} label={g.group}>
              {g.options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
            </optgroup>
          ))}
        </select>
        {field && (
          <button onClick={() => onChange(null)} title="清除" className="shrink-0 p-1 rounded text-muted hover:text-danger transition-colors cursor-pointer">
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        )}
      </div>
      {field && (
        <div className="flex items-center gap-2 pl-0.5">
          <span className="text-micro text-muted shrink-0">显示前N个</span>
          <input
            type="number" min={0} max={20}
            value={maxTags || ''}
            onChange={e => setMaxTags(e.target.value ? Number(e.target.value) : 0)}
            placeholder="不限"
            className="w-14 h-6 bg-elevated border border-border rounded text-xs text-foreground px-1.5 focus:outline-none focus:border-accent/50"
          />
          <span className="text-micro text-muted/60">留空=全部</span>
        </div>
      )}
      {field && maxTags > 0 && (
        <div className="flex items-center gap-2 pl-0.5">
          <span className="text-micro text-muted shrink-0">隐藏位置</span>
          <div className="flex flex-wrap gap-1">
            {Array.from({ length: maxTags }, (_, i) => (
              <button
                key={i}
                onClick={() => toggleHidden(i)}
                className={`w-5 h-5 rounded text-micro font-medium transition-colors cursor-pointer ${
                  hidden.includes(i) ? 'bg-elevated text-muted line-through' : 'bg-accent/15 text-accent'
                }`}
              >{i + 1}</button>
            ))}
          </div>
          <span className="text-micro text-muted/60">点数字划掉=隐藏该位置</span>
        </div>
      )}
    </div>
  )
}
