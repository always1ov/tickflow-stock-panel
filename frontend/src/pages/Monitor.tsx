/**
 * [R524] 监控中心 —— 三栏: 触发记录 / 监控规则 / 焦点名单。
 *
 * 用户: 「监控中心页面也要整改」。原来是三层叠在一屏里: 推送焦点条(折叠) + 左栏触发记录(卡片, 一条三四行)
 * + 右栏 400px 监控规则(卡片, 一条两行), 手机上更糟 —— 记录那一栏是 `flex-1 min-h-0`, 规则栏 13 条把它
 * 挤成 0 高, **整段消失**。现在:
 *   · 分栏条跟 Minds / 模拟盘同一份 `PageTabs`, 当前栏写在 `?tab=`;
 *   · 触发记录按日分组, 一条一行(时间 · 谁 · 价 · 规则 · 命中), 类型筛选只列有记录的类型并带计数;
 *   · 监控规则一条一行, 13 条一屏放完;
 *   · 焦点名单整栏摊开(原来折在条里), 「推送焦点」改叫「焦点名单」—— CONTEXT.md 里一直是这个名字。
 */
import { useState, useRef, useEffect, useMemo, useCallback } from 'react'
import { useNavigate, useSearchParams, Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { motion, AnimatePresence } from 'framer-motion'
import { AlertTriangle, RadioTower, Plus, Trash2, Settings2, Zap, Bell, ListChecks, BellRing, Tags, Crosshair } from 'lucide-react'
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
import { LEGACY_STRATEGY_NOTIFY_EVENTS, STRATEGY_NOTIFY_EVENT_OPTIONS, strategyEventMeta } from '@/lib/strategyMonitorEvents'
import { boardTag } from '@/components/stock-table/primitives'
import { resolveWatchlistGroupColor } from '@/lib/watchlist-group-colors'
import { markSeen, resetBadge, leaveMonitorPage } from '@/lib/monitorBadge'
import { RuleEditor } from '@/components/monitor/RuleEditor'
import { FocusPanel } from '@/components/monitor/FocusPanel'
import { toast } from '@/components/Toast'
import { StockPreviewDialog } from '@/components/StockPreviewDialog'
import { toNavItems, type NavItem } from '@/lib/listNav'
import { DimensionMembersDialog, type DimensionKind, type DimensionMembersTarget } from '@/components/DimensionMembersDialog'
import { usePreferences, useQuoteStatus } from '@/lib/useSharedQueries'
import { PageTabs, usePageTab, type PageTabDef } from '@/components/PageTabs'
import { SELECTED, TYPE, buttonClass } from '@/components/ui'

export type MonitorTab = 'alerts' | 'rules' | 'focus'

export const MONITOR_TABS: Record<MonitorTab, PageTabDef> = {
  alerts: { title: '触发记录', icon: BellRing },
  rules: { title: '监控规则', icon: ListChecks },
  focus: { title: '焦点名单', icon: Crosshair },
}

type AlertSource = 'strategy' | 'signal' | 'price' | 'market' | 'sector' | 'abnormal' | 'volume_delta' | 'date'
/** 类型筛选的排列顺序 —— 只画有记录的那些 */
const SOURCE_ORDER: AlertSource[] = ['strategy', 'signal', 'price', 'market', 'sector', 'abnormal', 'volume_delta', 'date']

const TYPE_LABEL: Record<string, string> = {
  signal: '信号', price: '价格/涨跌', market: '市场异动', strategy: '策略监控', sector: '板块监控',
  abnormal: '异动监控', volume_delta: '轮询放量', date: '日期提醒',
}

/** 严重级别 → 行首的点。info 是常态, 灰; warn / critical 才上色 */
const SEVERITY_DOT: Record<string, string> = {
  info: 'bg-muted/40',
  warn: 'bg-warning',
  critical: 'bg-danger',
}
const SOURCE_BADGE_STYLE: Record<string, string> = {
  strategy: 'bg-warning/10 text-warning border-warning/20',
  signal:   'bg-accent/10 text-accent border-accent/20',
  price:    'bg-emerald-400/10 text-emerald-400 border-emerald-400/20',
  market:   'bg-sky-500/10 text-sky-400 border-sky-500/20',
  sector:   'bg-cyan-500/10 text-cyan-700 border-cyan-500/20 dark:text-cyan-300',
  abnormal: 'bg-orange-500/10 text-orange-500 border-orange-500/20 dark:text-orange-400',
  volume_delta: 'bg-teal-500/10 text-teal-500 border-teal-500/20 dark:text-teal-300',
  date:     'bg-secondary/10 text-secondary border-border',
}

/** 图标按钮 —— 工具条右侧那几颗 */
const ICON_BTN = 'inline-flex h-7 w-7 items-center justify-center rounded-btn border border-border/60 bg-surface text-muted transition-colors hover:border-accent/40 hover:text-accent disabled:cursor-not-allowed disabled:opacity-30 cursor-pointer'

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

/** 个股通知的 ext 标签 (行业/概念), 无数据返回 null。[R524] 从彩色小块改成灰字, 一行里彩的只留规则徽标 */
function AlertExtTags({ ev, fields, onTagClick }: {
  ev: Record<string, unknown>
  fields: { concept: MonitorExtFieldItem | null; industry: MonitorExtFieldItem | null }
  onTagClick: (kind: DimensionKind, value: string, sourceField?: string) => void
}) {
  const industryTags = Array.from(new Set(getExtTags(ev, fields.industry)))
  // [R525] 行业与概念指到同一个字段(或同一个词两边都有)时只印一次 —— 原来彩块分蓝橙还分得出, 改灰字后重复就成了看着像 bug
  const conceptTags = Array.from(new Set(getExtTags(ev, fields.concept))).filter(t => !industryTags.includes(t))
  if (conceptTags.length === 0 && industryTags.length === 0) return null
  const tagCls = 'rounded px-0.5 text-micro leading-tight text-muted transition-colors hover:bg-elevated hover:text-foreground cursor-pointer'
  return (
    <span className="inline-flex flex-wrap items-center gap-x-1 gap-y-0.5">
      {industryTags.map((t, i) => (
        <button key={`i${i}`} onClick={event => { event.stopPropagation(); onTagClick('industry', t, fields.industry?.field) }} className={tagCls}>{t}</button>
      ))}
      {conceptTags.map((t, i) => (
        <button key={`c${i}`} onClick={event => { event.stopPropagation(); onTagClick('concept', t, fields.concept?.field) }} className={tagCls}>{t}</button>
      ))}
    </span>
  )
}

/** 触发记录查询 —— 全部与按类型筛选共用一份, 键不同 */
function useAlertsQuery(source: AlertSource | undefined, focusOnly: boolean, extColumnsParam: string | undefined) {
  return useQuery({
    queryKey: [...QK.alerts(source), extColumnsParam ?? '', focusOnly ? 'focus' : 'all'],
    queryFn: () => api.alertsList({ days: 7, limit: 500, source, extColumns: extColumnsParam, focus: focusOnly }),
    // 10s 轮询仅作 SSE strategy_alert 事件的兜底; 后台标签页不再拉 500 条全量
    refetchInterval: 10000,
  })
}

export function Monitor() {
  const qc = useQueryClient()
  const [activeTab, changeTab] = usePageTab(MONITOR_TABS, 'alerts')
  const [editorOpen, setEditorOpen] = useState(false)
  const [editingRule, setEditingRule] = useState<MonitorRule | null>(null)
  const [editorPreset, setEditorPreset] = useState<Partial<MonitorRule> | null>(null)

  // 深链: /monitor?new=abnormal (异动监控页「告警规则」入口) → 切到规则栏并直接弹出预置类型的编辑器
  const [searchParams, setSearchParams] = useSearchParams()
  useEffect(() => {
    const kind = searchParams.get('new')
    if (kind === 'abnormal') {
      setEditingRule(null)
      setEditorPreset({ type: 'abnormal', threshold_pct: 70, direction: 'both', abnormal_window: 'any', scope: 'all' })
      setEditorOpen(true)
      setSearchParams({ tab: 'rules' }, { replace: true })
    }
  }, [searchParams, setSearchParams])

  // 触发记录: 类型筛选 + 焦点开关
  const [filter, setFilter] = useState<'all' | AlertSource>('all')
  // [R160] 触发记录默认只看焦点内的; 切「含焦点外」能看到被静音的那些(灰显)
  const [focusOnly, setFocusOnly] = useState(true)
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

  // 「全部」那一份一直拉着: 分栏上的总数、类型筛选的计数都从它来; 选了类型再多拉一份该类型的
  const allQuery = useAlertsQuery(undefined, focusOnly, extColumnsParam)
  const alertsQuery = useAlertsQuery(filter === 'all' ? undefined : filter, focusOnly, extColumnsParam)
  const total = allQuery.data?.total ?? 0
  const sourceCounts = useMemo(() => {
    const counts: Partial<Record<AlertSource, number>> = {}
    for (const ev of allQuery.data?.alerts ?? []) {
      const s = ev.source as AlertSource
      counts[s] = (counts[s] ?? 0) + 1
    }
    return counts
  }, [allQuery.data])

  // 规则个数
  const rulesQuery = useQuery({ queryKey: QK.monitorRules, queryFn: api.monitorRulesList })
  const rulesCount = rulesQuery.data?.rules.length ?? 0

  // 焦点名单: 分栏上挂「过推送门的」那几档(持有 + 计划中 + 贴轨), 观察档不算
  const focusQuery = useQuery({ queryKey: QK.focus, queryFn: api.focusList, staleTime: 30_000 })
  const focusCount = focusQuery.data
    ? (focusQuery.data.counts.held ?? 0) + (focusQuery.data.counts.plan ?? 0) + (focusQuery.data.counts.band ?? 0)
    : undefined

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

  // 进入监控页: 清零未读徽标 + 记录"进入时刻", 之后新增的记录会高亮
  // 离开监控页: 停止同步, 之后新增才计入未读
  const enterTsRef = useRef<number>(Date.now())
  useEffect(() => {
    enterTsRef.current = Date.now()
    markSeen()
    return () => leaveMonitorPage()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const counts: Partial<Record<MonitorTab, number>> = { alerts: total, rules: rulesCount, focus: focusCount }

  return (
    <div className="flex h-full flex-col">
      <PageHeader
        title="监控中心"
        className="shrink-0 flex-wrap gap-x-4 gap-y-2"
        right={<PageTabs tabs={MONITOR_TABS} active={activeTab} onChange={changeTab} counts={counts} label="监控中心分栏" />}
      />
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
      <main className="min-h-0 flex-1 overflow-y-auto px-3 pb-4 pt-3 lg:px-4">
        <div className="mx-auto w-full max-w-[1440px]">
          {activeTab === 'alerts' && (
            <AlertsTab
              alertsQuery={alertsQuery}
              loading={alertsQuery.isLoading || allQuery.isLoading}
              total={total}
              sourceCounts={sourceCounts}
              filter={filter}
              setFilter={setFilter}
              focusOnly={focusOnly}
              setFocusOnly={setFocusOnly}
              enterTs={enterTsRef.current}
              monitorExtFields={monitorExtFields}
              onOpenExtConfig={() => setExtConfigOpen(true)}
              extConfigOpen={extConfigOpen}
            />
          )}
          {activeTab === 'rules' && (
            <RulesTab
              rulesQuery={rulesQuery}
              rulesCount={rulesCount}
              onNew={() => { setEditingRule(null); setEditorPreset(null); setEditorOpen(true) }}
              onEdit={(r) => { setEditingRule(r); setEditorOpen(true) }}
              onBatchChannels={() => setBatchChannelsOpen(true)}
              onClearAll={() => setConfirmClearRules(true)}
            />
          )}
          {activeTab === 'focus' && <FocusPanel />}
        </div>
      </main>

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

// ── 触发记录栏 ──────────────────────────────────────
function AlertsTab({ alertsQuery, loading, total, sourceCounts, filter, setFilter, focusOnly, setFocusOnly, enterTs, monitorExtFields, onOpenExtConfig, extConfigOpen }: {
  alertsQuery: ReturnType<typeof useAlertsQuery>
  loading: boolean
  total: number
  sourceCounts: Partial<Record<AlertSource, number>>
  filter: 'all' | AlertSource
  setFilter: (f: 'all' | AlertSource) => void
  focusOnly: boolean
  setFocusOnly: (fn: (v: boolean) => boolean) => void
  enterTs: number
  monitorExtFields: { concept: MonitorExtFieldItem | null; industry: MonitorExtFieldItem | null }
  onOpenExtConfig: () => void
  extConfigOpen: boolean
}) {
  const [confirmClear, setConfirmClear] = useState(false)
  // 只画有记录的类型; 当前选中的哪怕清零了也留着, 不然按钮在手底下消失
  const sources = SOURCE_ORDER.filter(s => (sourceCounts[s] ?? 0) > 0 || s === filter)
  const chipCls = (on: boolean) => cn(
    'inline-flex h-7 items-center gap-1 rounded-btn border px-2 text-xs transition-colors cursor-pointer',
    on ? SELECTED : 'border-transparent text-muted hover:bg-elevated hover:text-foreground',
  )
  return (
    <div>
      <div className="mb-2 flex flex-wrap items-center gap-x-3 gap-y-2">
        <div className="flex min-w-0 flex-wrap items-center gap-0.5">
          <button onClick={() => setFilter('all')} className={chipCls(filter === 'all')}>
            全部<span className="text-micro tabular-nums opacity-70">{total}</span>
          </button>
          {sources.map(s => (
            <button key={s} onClick={() => setFilter(s)} className={chipCls(filter === s)}>
              {TYPE_LABEL[s]}<span className="text-micro tabular-nums opacity-70">{sourceCounts[s] ?? 0}</span>
            </button>
          ))}
        </div>
        <div className="ml-auto flex shrink-0 items-center gap-1.5">
          {/* [R160] 焦点开关: 默认只看焦点内; 焦点外的仍记录, 切过去灰显 */}
          <button
            onClick={() => setFocusOnly(v => !v)}
            title={focusOnly ? '当前只看焦点内(持有 / 计划中 / 钉住)。点击含焦点外的' : '当前含焦点外的(灰显)。点击只看焦点内'}
            className={buttonClass({ selected: focusOnly }, 'h-7 px-2')}
          >
            {focusOnly ? '只看焦点' : '含焦点外'}
          </button>
          <button onClick={onOpenExtConfig} title="配置行业/概念标签" className={cn(ICON_BTN, extConfigOpen && 'border-accent/40 text-accent')}>
            <Tags className="h-3.5 w-3.5" /><span className="sr-only">配置行业/概念标签</span>
          </button>
          <button onClick={() => setConfirmClear(true)} disabled={total === 0} title="清空触发记录" className={cn(ICON_BTN, 'hover:border-danger/40 hover:text-danger')}>
            <Trash2 className="h-3.5 w-3.5" /><span className="sr-only">清空触发记录</span>
          </button>
        </div>
      </div>
      <AlertsList alertsQuery={alertsQuery} loading={loading} confirmClear={confirmClear} setConfirmClear={setConfirmClear} total={total} enterTs={enterTs} monitorExtFields={monitorExtFields} />
    </div>
  )
}

/** 日分组的标题: 今天 / 昨天 / 周几, 后面跟日期 */
function dayLabel(ts: number, now: Date): string {
  const d = new Date(ts)
  const key = (x: Date) => `${x.getFullYear()}-${x.getMonth()}-${x.getDate()}`
  const yesterday = new Date(now); yesterday.setDate(now.getDate() - 1)
  const md = `${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
  if (key(d) === key(now)) return `今天 ${md}`
  if (key(d) === key(yesterday)) return `昨天 ${md}`
  return `${'周日周一周二周三周四周五周六'.slice(d.getDay() * 2, d.getDay() * 2 + 2)} ${md}`
}
const dayKey = (ts: number) => { const d = new Date(ts); return `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}` }
const hhmm = (ts: number) => new Date(ts).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', hour12: false })

/** 规则徽标上的悬停文本: 规则的全部条件 —— 以前单独占一行灰字, 现在收进悬停 */
function ruleConditionsText(ev: AlertEvent, customNames: Record<string, string> | undefined): string | undefined {
  if (!ev.conditions?.length) return ev.rule_name || undefined
  const joiner = ev.logic === 'or' ? ' 或 ' : ' 且 '
  const body = ev.conditions.map(c => c.op === 'truth' ? cnSignal(c.field, customNames) : `${cnSignal(c.field, customNames)}${c.op}${c.value}`).join(joiner)
  return `${ev.rule_name ? ev.rule_name + '\n' : ''}规则: ${body}`
}

// ── 触发记录列表 ──────────────────────────────────────
function AlertsList({ alertsQuery, loading, confirmClear, setConfirmClear, total, enterTs, monitorExtFields }: {
  alertsQuery: ReturnType<typeof useAlertsQuery>
  loading: boolean
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
      if (resetTimer.current) clearTimeout(resetTimer.current)
      setConfirmTs(null)
      delMut.mutate(ts)
    } else {
      setConfirmTs(ts)
      if (resetTimer.current) clearTimeout(resetTimer.current)
      resetTimer.current = setTimeout(() => setConfirmTs(null), 3000)
    }
  }

  const events: AlertEvent[] = alertsQuery.data?.alerts ?? []

  // 切股导航列表: 有 symbol 的触发记录 (按展示顺序)
  const alertsNavItems = useMemo(
    () => toNavItems(events.filter((ev): ev is AlertEvent & { symbol: string } => !!ev.symbol)),
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

  const now = new Date()

  return (
    <div>
      {loading ? (
        <div className="space-y-2">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} h="h-8" rounded="rounded-card" />
          ))}
        </div>
      ) : events.length === 0 ? (
        <EmptyState
          icon={Bell}
          title="暂无触发记录"
          hint="监控规则命中后, 触发记录会出现在这里。可在「监控规则」栏配置规则, 或在标的详情页加入监控。"
        />
      ) : (
        <ul>
          {events.map((ev, i) => {
            const newDay = i === 0 || dayKey(ev.ts) !== dayKey(events[i - 1].ts)
            return (
              <AlertRow
                key={`${ev.ts}-${ev.symbol ?? ''}-${ev.rule_name ?? ''}`}
                ev={ev}
                dayHeader={newDay ? dayLabel(ev.ts, now) : null}
                isNew={ev.ts > enterTs}
                customNames={customNames}
                monitorExtFields={monitorExtFields}
                confirming={confirmTs === ev.ts}
                deleting={delMut.isPending}
                onDelete={() => handleClickDelete(ev.ts)}
                onPreview={() => handlePreviewEvent(ev)}
                onSector={() => {
                  if (ev.sector_kind === 'index' && ev.symbol) {
                    navigate(`/indices?symbol=${encodeURIComponent(ev.symbol)}`)
                  } else if (ev.sector_source_field && ev.sector_value) {
                    setDimensionTarget({ kind: ev.sector_kind as DimensionKind, value: ev.sector_value, sourceField: ev.sector_source_field })
                  }
                }}
                onTag={(kind, value, sourceField) => { if (sourceField) setDimensionTarget({ kind, value, sourceField }) }}
              />
            )
          })}
        </ul>
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

/**
 * 一条触发记录 = 一行: 时间 · 谁 · 价 涨跌 · 规则徽标 · 命中了什么 · 行业/概念。
 * 手机上「命中」那一段换到第二行, 对齐在「谁」的下面。
 * 只有进页之后新到的那条才有入场动效(淡入 + 上移 4px, 200ms, ease-out); 其余一律静止 —— 这是数据表, 不是海报。
 */
function AlertRow({ ev, dayHeader, isNew, customNames, monitorExtFields, confirming, deleting, onDelete, onPreview, onSector, onTag }: {
  ev: AlertEvent
  dayHeader: string | null
  isNew: boolean
  customNames: Record<string, string> | undefined
  monitorExtFields: { concept: MonitorExtFieldItem | null; industry: MonitorExtFieldItem | null }
  confirming: boolean
  deleting: boolean
  onDelete: () => void
  onPreview: () => void
  onSector: () => void
  onTag: (kind: DimensionKind, value: string, sourceField?: string) => void
}) {
  const pct = ev.change_pct ?? 0
  const pctCls = pct >= 0 ? 'text-danger' : 'text-bear'
  const board = ev.symbol ? boardTag(ev.symbol) : null
  const badgeLabel = (() => {
    // 优先用规则名 (如 "策略监控 · 空中加油" → "空中加油"); 退回到 type 标签
    // [R525] 规则名可能是三段("持仓出场 · 000657.SZ · 生命线(20日线) 60.30"): 第一段是类型, 代码那段跟左边「谁」重复,
    // 都剥掉; 什么都不剩("价格提醒 · 300059.SZ")就退回类型名
    const parts = (ev.rule_name ?? '').split(' · ')
    const rest = parts.slice(1).filter(p => p && p !== ev.symbol)
    if (rest.length > 0) return rest.join(' · ')
    return parts[0] && parts.length === 1 && parts[0] !== ev.symbol ? parts[0] : (TYPE_LABEL[ev.source] ?? ev.source)
  })()
  const eventMeta = ev.source === 'strategy' ? strategyEventMeta(ev.type) : null
  const hasSignals = !!ev.signals && ev.signals.length > 0
  const hasConds = !!ev.conditions && ev.conditions.length > 0

  return (
    <>
      {dayHeader && (
        // [R525] 不粘住: 粘住的分组条在手机上压在行文字上(外层滚动容器不是这一层), 分组条本来就每段可见, 不需要粘
        <li className="px-1 pb-1 pt-3 text-micro font-medium text-muted first:pt-0">{dayHeader}</li>
      )}
      <motion.li
        initial={isNew ? { opacity: 0, transform: 'translateY(-4px)' } : false}
        animate={{ opacity: 1, transform: 'translateY(0px)' }}
        transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
        className={cn(
          'group relative flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-border/50 py-1.5 pl-4 pr-1',
          isNew && 'bg-accent/[0.05]',
          ev.focus_muted && 'opacity-55',   // [R160] 焦点外: 只记录, 灰显
        )}
        title={ev.focus_muted ? '焦点外: 只记录, 没弹窗/没推送/不计徽标。想推就在「焦点名单」里钉住它' : undefined}
      >
        <span aria-hidden className={cn('absolute left-1 top-1/2 h-1.5 w-1.5 -translate-y-1/2 rounded-full sm:top-[15px] sm:translate-y-0', SEVERITY_DOT[ev.severity ?? 'info'] ?? SEVERITY_DOT.info)} />
        <span className="w-10 shrink-0 font-mono text-xs tabular-nums text-muted">{hhmm(ev.ts)}</span>

        {/* 谁 */}
        <div className="flex min-w-0 grow basis-0 items-center sm:w-52 sm:grow-0 sm:basis-auto">
          {ev.source === 'sector' ? (
            <button
              onClick={onSector}
              className="inline-flex min-w-0 items-center gap-1.5 rounded px-1 -mx-1 text-xs font-medium text-foreground transition-colors hover:bg-elevated/50 hover:text-accent cursor-pointer"
              title={ev.sector_kind === 'index' ? '打开指数详情' : '查看成分股'}
            >
              <Tags className="h-3.5 w-3.5 shrink-0 text-cyan-600 dark:text-cyan-300" />
              <span className="truncate">{ev.sector_name ?? ev.name}</span>
              {ev.symbol && <span className="shrink-0 font-mono text-micro text-muted">{ev.symbol}</span>}
            </button>
          ) : ev.symbol ? (
            <button
              onClick={onPreview}
              className="inline-flex min-w-0 items-center gap-1.5 rounded px-1 -mx-1 transition-colors hover:bg-elevated/50 cursor-pointer"
              title="点击查看日K"
            >
              <span className="font-mono text-xs font-medium text-foreground hover:text-accent">{ev.symbol}</span>
              {board && (
                <span className={`inline-flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded border text-micro font-bold leading-none ${board.color}`}>
                  {board.label}
                </span>
              )}
              {ev.name && <span className="truncate text-xs text-secondary hover:text-foreground">{ev.name}</span>}
            </button>
          ) : null}
        </div>

        {/* 删除: 手机上一直淡淡地在, 宽屏悬停才出现 */}
        <span className="ml-auto flex shrink-0 items-center sm:order-last">
          {confirming ? (
            <button
              onClick={onDelete}
              title="再次点击确认删除"
              className="inline-flex items-center gap-1 rounded-md border border-danger/30 bg-danger/15 px-1.5 py-0.5 text-micro font-medium text-danger cursor-pointer"
            >
              <Trash2 className="h-2.5 w-2.5" />确认
            </button>
          ) : (
            <button
              onClick={onDelete}
              disabled={deleting}
              title="删除"
              className="rounded p-1 text-muted opacity-60 transition-colors hover:bg-danger/10 hover:text-danger focus-visible:opacity-100 sm:opacity-0 sm:group-hover:opacity-100 cursor-pointer"
            >
              <Trash2 className="h-3 w-3" />
            </button>
          )}
        </span>

        {/* [R525] 手机上第二行: 价 涨跌 · 规则 · 命中 · 行业/概念 一起从「谁」的下面流过去(名字不再被价格挤掉);
            宽屏这层壳 display:contents 消失, 价与详情各归各的列 */}
        <div className="order-last flex min-w-0 basis-full flex-wrap items-center gap-x-2 gap-y-1 pl-[3.25rem] text-xs sm:contents">
          {(ev.price != null || ev.change_pct != null) && (
            <span className={cn('flex shrink-0 items-center gap-1.5 font-mono text-xs tabular-nums sm:w-28', pctCls)}>
              {ev.price != null && <span>{fmtPrice(ev.price)}</span>}
              {ev.change_pct != null && <span className="font-medium">{fmtPct(ev.change_pct)}</span>}
            </span>
          )}

        {/* 规则 · 命中了什么 · 行业/概念 */}
        <div className="contents sm:flex sm:min-w-0 sm:basis-0 sm:grow sm:flex-wrap sm:items-center sm:gap-x-2 sm:gap-y-1 sm:text-xs">
          <span
            className={cn('shrink-0 rounded border px-1.5 py-px text-micro font-medium', SOURCE_BADGE_STYLE[ev.source] ?? 'bg-elevated text-muted border-border')}
            title={ruleConditionsText(ev, customNames)}
          >
            {badgeLabel}
          </span>
          {eventMeta && ev.symbol && (
            <span className={cn('shrink-0 font-medium', eventMeta.className)}>{eventMeta.action}</span>
          )}
          {hasSignals ? (
            <>
              {!eventMeta && <span className="text-muted">命中</span>}
              {ev.signals!.map((s, j) => (
                <span key={j} className="rounded bg-accent/10 px-1.5 py-px text-micro font-medium text-accent">{cnSignal(s, customNames)}</span>
              ))}
            </>
          ) : hasConds ? (
            <>
              <span className="text-muted">命中</span>
              {ev.conditions!.map((c: MonitorCondition, ci: number) => (
                <span key={ci} className="inline-flex items-center gap-1">
                  {ci > 0 && <span className="text-secondary">{ev.logic === 'or' ? '或' : '且'}</span>}
                  {c.op === 'truth' ? (
                    <span className="text-accent/80">{cnSignal(c.field, customNames)}</span>
                  ) : (
                    <span className="font-mono text-foreground/80">{cnSignal(c.field, customNames)}{c.op}{c.value}</span>
                  )}
                </span>
              ))}
            </>
          ) : (eventMeta && ev.symbol) ? null : (
            <span className="min-w-0 truncate">{renderMessage(ev.source, ev.message)}</span>
          )}
          <AlertExtTags ev={ev} fields={monitorExtFields} onTagClick={onTag} />
        </div>
        </div>
      </motion.li>
    </>
  )
}

// ── 监控规则栏 ──────────────────────────────────────
function RulesTab({ rulesQuery, rulesCount, onNew, onEdit, onBatchChannels, onClearAll }: {
  rulesQuery: ReturnType<typeof useQuery<{ rules: MonitorRule[] }>>
  rulesCount: number
  onNew: () => void
  onEdit: (rule: MonitorRule) => void
  onBatchChannels: () => void
  onClearAll: () => void
}) {
  return (
    <div>
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <button onClick={onNew} className={buttonClass({ variant: 'primary' }, 'h-7 gap-1 px-2.5')}>
          <Plus className="h-3.5 w-3.5" />新建规则
        </button>
        <div className="ml-auto flex shrink-0 items-center gap-1.5">
          <button
            onClick={onBatchChannels}
            disabled={rulesCount === 0}
            title="批量设置推送渠道(飞书/企微/钉钉)—— 一次改所有规则, 不用逐条打开"
            className={ICON_BTN}
          >
            <BellRing className="h-3.5 w-3.5" /><span className="sr-only">批量设置推送渠道</span>
          </button>
          <button onClick={onClearAll} disabled={rulesCount === 0} title="清除全部规则" className={cn(ICON_BTN, 'hover:border-danger/40 hover:text-danger')}>
            <Trash2 className="h-3.5 w-3.5" /><span className="sr-only">清除全部规则</span>
          </button>
        </div>
      </div>
      <RulesList rulesQuery={rulesQuery} onEdit={onEdit} />
    </div>
  )
}

// ── 监控规则列表 ──────────────────────────────────────
function RulesList({ rulesQuery, onEdit }: {
  rulesQuery: ReturnType<typeof useQuery<{ rules: MonitorRule[] }>>
  onEdit: (rule: MonitorRule) => void
}) {
  const qc = useQueryClient()
  const [confirmId, setConfirmId] = useState<string | null>(null)
  const [previewSymbol, setPreviewSymbol] = useState<string | null>(null)
  const resetTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const customNames = useCustomSignalNames()

  const rules: MonitorRule[] = rulesQuery.data?.rules ?? []

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

  const pill = 'rounded bg-elevated px-1.5 py-px text-micro text-secondary'

  return (
    <div>
      {rulesQuery.isLoading ? (
        <div className="space-y-2">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} h="h-8" rounded="rounded-card" />
          ))}
        </div>
      ) : rules.length === 0 ? (
        <EmptyState
          icon={RadioTower}
          title="暂无监控规则"
          hint="点「新建规则」, 或在标的详情页点「加监控」快速添加。"
        />
      ) : (
        <ul>
          {rules.map(r => {
            // 名称截取: "策略监控 · MACD金叉" → "MACD金叉", "信号监控 · 300750.SZ" → "信号监控"
            const dotIdx = r.name.indexOf(' · ')
            const displayName = dotIdx >= 0 ? r.name.slice(dotIdx + 3) : r.name
            const strategyDisplayName = r.type === 'strategy' && r.strategy_id
              ? (strategyNames[r.strategy_id] ?? (dotIdx >= 0 ? displayName : r.strategy_id))
              : displayName
            return (
              <li
                key={r.id}
                className={cn(
                  'group flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-border/50 py-1.5 pl-1 pr-1',
                  !r.enabled && 'opacity-60 hover:opacity-100',
                )}
              >
                {/* 类型 */}
                <span className="flex w-[4.5rem] shrink-0 items-center gap-1">
                  <span className={cn('rounded px-1.5 py-px text-micro font-semibold', SOURCE_BADGE_STYLE[r.type] ?? 'bg-elevated text-muted')}>
                    {TYPE_LABEL[r.type]}
                  </span>
                </span>

                {/* 对象: 策略名 / 个股 / 分组 / 规则名 */}
                <div className="flex min-w-0 grow basis-0 items-center gap-1.5 sm:w-60 sm:grow-0 sm:basis-auto">
                  {r.lot_id && (
                    <span className="shrink-0 rounded bg-emerald-400/10 px-1.5 py-px text-micro font-semibold text-emerald-500" title="由「持仓提醒」页托管, 请在持仓提醒页修改或删除">批次</span>
                  )}
                  {r.asset_type === 'index' && (
                    <span className="shrink-0 rounded bg-sky-500/10 px-1.5 py-px text-micro font-semibold text-sky-400">指数</span>
                  )}
                  {/* 策略类型始终显示策略名；其他个股类型才显示可点击的代码+名称。 */}
                  {r.type === 'strategy' ? (
                    <h3 className={cn('truncate text-xs font-medium', r.enabled ? 'text-foreground' : 'text-muted')} title={strategyDisplayName}>
                      {strategyDisplayName}
                    </h3>
                  ) : r.scope === 'symbols' && r.symbols.length > 0 ? (
                    <button
                      onClick={() => setPreviewSymbol(r.symbols[0])}
                      className="inline-flex min-w-0 items-center gap-1 rounded px-0.5 transition-colors hover:bg-elevated/50 cursor-pointer"
                      title={`查看 ${r.symbols[0]} 日K`}
                    >
                      <span className="font-mono text-xs font-medium text-foreground hover:text-accent">{r.symbols[0]}</span>
                      {symbolNames[r.symbols[0]] && <span className="truncate text-xs text-secondary">{symbolNames[r.symbols[0]]}</span>}
                    </button>
                  ) : r.scope === 'watchlist_group' && r.group_id ? (
                    (() => {
                      const meta = groupMeta[r.group_id]
                      if (!meta) {
                        return <span className="truncate text-xs text-warning" title={r.name}>分组已删除</span>
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
                        </Link>
                      )
                    })()
                  ) : (
                    <h3 className={cn('truncate text-xs font-medium', r.enabled ? 'text-foreground' : 'text-muted')}>{displayName}</h3>
                  )}
                  {!r.enabled && <span className="shrink-0 text-micro text-secondary">· 停用</span>}
                </div>

                {/* 操作 */}
                <div className="ml-auto flex shrink-0 items-center gap-0.5 sm:order-last">
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
                          'rounded-md p-1 transition-colors cursor-pointer',
                          r.enabled ? 'text-accent hover:bg-accent/10' : 'text-muted hover:bg-elevated hover:text-accent',
                        )}
                      >
                        <Zap className="h-3.5 w-3.5" />
                      </button>
                      <button
                        onClick={() => onEdit(r)}
                        className="rounded-md p-1 text-secondary transition-colors hover:bg-accent/10 hover:text-accent cursor-pointer"
                        title="编辑"
                      >
                        <Settings2 className="h-3.5 w-3.5" />
                      </button>
                      {confirmId === r.id ? (
                        <button
                          onClick={() => handleClickDelete(r.id)}
                          title="再次点击确认删除"
                          className="inline-flex items-center gap-1 rounded-md border border-danger/30 bg-danger/15 px-1.5 py-0.5 text-micro font-medium text-danger cursor-pointer"
                        >
                          <Trash2 className="h-2.5 w-2.5" />确认
                        </button>
                      ) : (
                        <button
                          onClick={() => handleClickDelete(r.id)}
                          disabled={del.isPending}
                          className="rounded-md p-1 text-secondary transition-colors hover:bg-danger/10 hover:text-danger cursor-pointer"
                          title="删除"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      )}
                    </>
                  )}
                </div>

                {/* 摘要: 这条规则盯什么 */}
                <div className="order-last flex min-w-0 basis-full flex-wrap items-center gap-1 pl-[5.25rem] sm:order-none sm:basis-0 sm:grow sm:pl-0">
                  {r.runtime_warning && (
                    <span className="inline-flex min-w-0 items-center gap-1 text-micro text-warning" title={r.runtime_warning}>
                      <AlertTriangle className="h-3 w-3 shrink-0" />
                      <span className="truncate">{r.runtime_warning}</span>
                    </span>
                  )}
                  {r.type === 'sector' ? (
                    <>
                      {(r.sector_targets ?? []).slice(0, 3).map(target => (
                        <span key={target.key} className="max-w-28 truncate rounded bg-cyan-500/8 px-1.5 py-px text-micro text-cyan-700 dark:text-cyan-300">
                          {target.name}
                        </span>
                      ))}
                      {(r.sector_targets?.length ?? 0) > 3 && (
                        <span className="text-micro text-muted">+{(r.sector_targets?.length ?? 0) - 3}</span>
                      )}
                      <span className="text-micro text-secondary">
                        {r.sector_trigger === 'momentum' ? `${r.window_minutes ?? 5}分钟异动` : '涨跌幅'}
                        {r.direction === 'down' ? ' ≤ -' : ' ≥ '}{r.threshold_pct ?? 1}%
                      </span>
                    </>
                  ) : r.type === 'abnormal' ? (
                    <>
                      <span className="rounded bg-orange-500/8 px-1.5 py-px text-micro text-orange-500 dark:text-orange-400">
                        接近度 ≥ {r.threshold_pct ?? 70}%
                      </span>
                      <span className={pill}>
                        {r.abnormal_window && r.abnormal_window !== 'any' ? `${r.abnormal_window.toUpperCase()} 窗口` : '全部窗口'}
                      </span>
                      <span className={pill}>
                        {r.direction === 'up' ? '涨势偏离' : r.direction === 'down' ? '跌势偏离' : '涨跌双向'}
                      </span>
                    </>
                  ) : r.type === 'date' ? (
                    <span className="text-micro text-secondary">
                      提醒 {r.remind_date ?? ''}
                      {(r.lead_days ?? 0) > 0 && ` · 提前${r.lead_days}天`}
                      {' · 仅交易日盘中评估'}
                    </span>
                  ) : r.type === 'volume_delta' ? (
                    <>
                      <span className="rounded bg-teal-500/10 px-1.5 py-px font-mono text-micro text-teal-500 dark:text-teal-300">
                        {r.metric === 'amount'
                          ? `单轮增量 ≥ ${Math.round((r.threshold_amount ?? 1e6) / 1e4).toLocaleString()} 万元`
                          : `单轮增量 ≥ ${(r.threshold_volume ?? 9000).toLocaleString()} 手`}
                      </span>
                      <span className={pill}>冷却 {Math.round((r.cooldown_seconds ?? 300) / 60)} 分钟</span>
                      {r.basic_filter && Object.values(r.basic_filter).some(v => v !== null && v !== false) && (
                        <span className={pill}>基础过滤{r.basic_filter.exclude_st ? ' · 剔除ST' : ''}</span>
                      )}
                    </>
                  ) : r.type === 'strategy' && r.strategy_id ? (
                    <>
                      {(r.score_min != null || r.score_max != null) && (
                        <span className="rounded bg-warning/10 px-1.5 py-px font-mono text-micro text-warning">
                          评分 {r.score_min ?? 0}–{r.score_max ?? 100}
                        </span>
                      )}
                      {(r.notify_events ?? LEGACY_STRATEGY_NOTIFY_EVENTS).map(event => {
                        const option = STRATEGY_NOTIFY_EVENT_OPTIONS.find(item => item.key === event)
                        return option ? <span key={event} className={pill}>{option.label}</span> : null
                      })}
                    </>
                  ) : r.conditions.length > 0 && (
                    <span className="flex min-w-0 flex-wrap items-center gap-x-1 gap-y-0.5 text-micro">
                      <span className="shrink-0 text-secondary">条件</span>
                      {r.conditions.slice(0, 3).map((c, i) => (
                        <span key={i} className="inline-flex items-center gap-0.5">
                          {i > 0 && <span className="text-secondary">{r.logic === 'and' ? '且' : '或'}</span>}
                          {c.op === 'truth' ? (
                            <span className="text-accent/80">{cnSignal(c.field, customNames)}</span>
                          ) : (
                            <span className="font-mono text-foreground/80">{cnSignal(c.field, customNames)}{c.op}{c.value}</span>
                          )}
                        </span>
                      ))}
                      {r.conditions.length > 3 && <span className="text-secondary">+{r.conditions.length - 3}</span>}
                    </span>
                  )}
                </div>
              </li>
            )
          })}
        </ul>
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
