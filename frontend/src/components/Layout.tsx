import { useEffect, useLayoutEffect, useMemo, useRef, useState, Suspense } from 'react'
import { NavLink, Outlet, useNavigate, useLocation } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { useQuoteStream, useQuoteStreamStatus } from '@/lib/useQuoteStream'
import { ToastContainer, toast } from '@/components/Toast'
import { AlertToastContainer } from '@/components/AlertToast'
import { AiAnalysisHost } from '@/components/financials/AiAnalysisHost'
import { AiReportBubble } from '@/components/financials/AiReportBubble'
import { StockAnalysisHost } from '@/components/stock-analysis/StockAnalysisHost'
import { StockAnalysisBubble } from '@/components/stock-analysis/StockAnalysisBubble'
import {
  useCapabilityMatrix,
  useSettings,
  usePreferences,
  useQuoteStatus,
  useVersion,
} from '@/lib/useSharedQueries'
import {
  useToggleRealtimeQuotes,
} from '@/lib/useSharedMutations'
import { QK } from '@/lib/queryKeys'
import {
  Siren,
  Star,
  ScanSearch,
  History,
  Bot,
  Pickaxe,
  FileText,
  Settings,
  DatabaseZap,
  Database,
  Loader2,
  LayoutDashboard,
  Tags,
  TrendingUp,
  Flame,
  BarChart3,
  Gauge,
  Sparkles,
  Layers3,
  Landmark,
  RadioTower,
  CheckCircle2,
  BookOpenCheck,
  NotebookPen,
  ChevronRight,
  ChevronDown,
  Sun,
  Moon,
  X,
  WifiOff,
  PanelLeftClose,
  PanelLeftOpen,
  Sunrise,
  Globe2,
} from 'lucide-react'
import { Logo } from './Logo'
import { api, type CapabilityMatrix, type IndexQuote } from '@/lib/api'
import { cn } from '@/lib/cn'
import { resolveWatchlistGroupColor } from '@/lib/watchlist-group-colors'
import { computeGroupPcts, groupPctColor, groupPctTitle } from '@/lib/watchlistGroupStats'
import { fmtPct } from '@/lib/format'
import { toggleTheme, useTheme } from '@/lib/theme'
import { setCurrentTotal as setAlertTotal, useUnreadAlerts } from '@/lib/monitorBadge'
import { ExtensionSlot } from '@/extensions/ExtensionSlot'
import { getFrontendExtensionNavigation } from '@/extensions/registry'
import { BROWSE_GROUP, BROWSE_GROUP_ID, splitBrowseGroup } from '@/lib/navGroups'

// 品牌色 — 只用于 logo / brand 区域,不影响功能语义色
const BRAND = '#8B5CF6'

const CORE_INDEXES = [
  { symbol: '000001.SH', name: '上证指数' },
  { symbol: '399001.SZ', name: '深证成指' },
  { symbol: '399006.SZ', name: '创业板指' },
  { symbol: '000680.SH', name: '科创综指' },
] as const

type CoreIndex = (typeof CORE_INDEXES)[number]

const nav = [
  // [fork 增强] 今日总览: 决策汇聚层, 放首位
  { to: '/today',           label: '今日总览', icon: Sunrise },
  { to: '/watchlist',  label: '自选',   icon: Star },
  { to: '/screener',   label: '策略',   icon: ScanSearch },
  { to: '/backtest',   label: '回测', icon: History },
  { to: '/mining',     label: '挖掘', icon: Pickaxe },
  // [R59] AI 操盘手: 让模型用本系统的信息模拟交易, 长期观察这套信息够不够用
  { to: '/paper-trading', label: 'AI 操盘手', icon: Bot },
  { to: '/stock-analysis',    label: '个股分析', icon: TrendingUp },
  // [R67] 分组本身也是菜单里的一行 —— 排序时它整块走, 后面的成员是它的子项
  { to: BROWSE_GROUP_ID,    label: BROWSE_GROUP.label, icon: Layers3 },
  { to: '/dashboard',       label: '看板',     icon: LayoutDashboard },
  { to: '/limit-ladder', label: '连板梯队', icon: Flame },
  { to: '/concept-analysis', label: '概念分析', icon: Layers3 },
  { to: '/industry-analysis', label: '行业分析', icon: Landmark },
  { to: '/financials', label: '财务分析', icon: FileText },
  { to: '/monitor', label: '监控中心', icon: RadioTower },
  { to: '/regime', label: '市场环境', icon: Gauge },
  { to: '/abnormal', label: '异动监控', icon: Siren },
  { to: '/review',      label: '复盘',   icon: BookOpenCheck },
  // [fork 增强] R93 使用观察笔记
  { to: '/usage-notes', label: '我的使用观察', icon: NotebookPen },
  { to: '/indices', label: '指数', icon: BarChart3 },
  { to: '/data',       label: '数据',   icon: Database },
] as const

/**
 * [R57] 「盘面参考」分组 —— 这几页是看的, 不是用来做决定的。
 *
 * 看板 / 连板梯队 / 概念分析 / 行业分析都是展示型的: 打开看两眼有概念, 但不
 * 产出任何可执行的东西(不给候选、不进把握分、不驱动仓位)。和今日总览/自选/
 * 回测这些平铺在一起, 每次找常用的那几个都要从它们中间扫过去。
 *
 * [R64] 看板一并收进来, 同时把它从根路径挪到 /dashboard —— 一个展示型的页面
 * 不该是每次打开应用第一眼看到的那一页。根路径现在去今日总览。
 *
 * 所以收进一个默认折叠的分组, 而不是删掉 —— 它们各自还有用处(比如「AI 打板
 * 复盘」要读连板梯队的数据), 只是不该占主视野。想彻底不要, 设置→菜单里
 * 本来就能隐藏。
 *
 * [R67] 分组的定义移到 lib/navGroups.ts —— 「设置 → 菜单」那一页要和这里用
 * 同一份, 否则一边把它当一行、另一边当四行, 拖出来的顺序对不上。
 */

/** 亮/暗主题切换 — 状态存 localStorage, 生效见 lib/theme.ts */
function ThemeToggle() {
  const theme = useTheme()
  const dark = theme === 'dark'
  return (
    <button
      onClick={() => toggleTheme()}
      className="flex items-center justify-center rounded-btn p-2 text-foreground/80 transition-colors duration-150 ease-smooth hover:bg-elevated hover:text-foreground cursor-pointer"
      title={dark ? '切换到亮色模式' : '切换到暗色模式'}
    >
      {dark ? <Sun className="h-4 w-4 shrink-0" /> : <Moon className="h-4 w-4 shrink-0" />}
    </button>
  )
}

function fmtIndexValue(v: number | null | undefined) {
  if (v == null || Number.isNaN(Number(v))) return '--'
  return Number(v).toFixed(2)
}

function fmtIndexPct(v: number | null | undefined) {
  if (v == null || Number.isNaN(Number(v))) return '--'
  return `${Number(v) >= 0 ? '+' : ''}${Number(v).toFixed(2)}%`
}

function indexPctClass(v: number | null | undefined) {
  if (v == null || Number.isNaN(Number(v))) return 'text-muted'
  const n = Number(v)
  if (n === 0) return 'text-foreground'
  return n > 0 ? 'text-bull' : 'text-bear'
}

/** 监控中心未读徽标 — 仅在非监控页且有未读时显示。 */
function MonitorBadge({ active }: { active: boolean }) {
  const unread = useUnreadAlerts()
  // 尊重用户设置: 可在菜单设置里关闭数字提示
  const badgeEnabled = (() => {
    try { return localStorage.getItem('monitor_badge_enabled') !== '0' } catch { return true }
  })()
  if (active || unread <= 0 || !badgeEnabled) return null
  return (
    <span className="inline-flex h-4 min-w-4 items-center justify-center rounded-full bg-danger px-1 text-[9px] font-bold text-white animate-pulse">
      {unread > 99 ? '99+' : unread}
    </span>
  )
}

function SidebarIndexQuotes({ rows, items, globalRows }: {
  rows: IndexQuote[] | undefined
  items: CoreIndex[]
  /** [R102] 全球指数(独立数据源) — 与 A 股指数同格显示, 数据链各自独立 */
  globalRows?: { key: string; name: string; last: number; change_pct?: number | null; updated_at?: number; trading?: boolean }[]
}) {
  const globals = globalRows ?? []
  if (items.length === 0 && globals.length === 0) return null
  const quoteBySymbol = new Map((rows ?? []).map(q => [q.symbol, q]))
  return (
    <div className="mt-2 grid grid-cols-2 gap-1.5 border-t border-border/60 pt-2">
      {items.map(item => {
        const q = quoteBySymbol.get(item.symbol)
        const value = q?.last_price ?? q?.close
        const pct = q?.change_pct
        return (
          <NavLink
            key={item.symbol}
            to={`/indices?symbol=${encodeURIComponent(item.symbol)}`}
            className="block rounded bg-elevated/60 px-2 py-1.5 transition-colors hover:bg-elevated"
            title={`${item.name} ${item.symbol}`}
          >
            <div className="flex items-center justify-between gap-1">
              <span className="text-[10px] text-secondary">{item.name}</span>
              <span className={`text-[10px] font-mono ${indexPctClass(pct)}`}>{fmtIndexPct(pct)}</span>
            </div>
            <div className={`mt-0.5 truncate font-mono text-[10px] ${indexPctClass(pct)}`}>
              {fmtIndexValue(value)}
            </div>
          </NavLink>
        )
      })}
      {globals.map(q => {
        const pct = q.change_pct != null ? q.change_pct * 100 : null
        const staleMin = q.updated_at ? (Date.now() / 1000 - q.updated_at) / 60 : null
        const trading = q.trading !== false
        return (
          <div
            key={q.key}
            className={cn('rounded bg-elevated/60 px-2 py-1.5', !trading && 'opacity-70')}
            title={`${q.name}(全球·独立源) — ${trading ? '交易中, 实时刷新' : '当前休市, 显示最后成交值'}${
              staleMin != null && staleMin > 1 ? ` · ${Math.round(staleMin)} 分钟前` : ''}`}
          >
            <div className="flex items-center justify-between gap-1">
              <span className="flex min-w-0 items-center gap-1 text-[10px] text-secondary">
                {/* 交易中: 绿点脉冲(在实时跳); 休市: 灰点 */}
                <span className={cn('h-1 w-1 shrink-0 rounded-full',
                  trading ? 'bg-bull animate-pulse' : 'bg-muted/40')} />
                <span className="truncate">{q.name}</span>
              </span>
              <span className={`text-[10px] font-mono ${indexPctClass(pct)}`}>{fmtIndexPct(pct)}</span>
            </div>
            <div className={`mt-0.5 truncate font-mono text-[10px] ${indexPctClass(pct)}`}>
              {fmtIndexValue(q.last)}
            </div>
          </div>
        )
      })}
    </div>
  )
}

// ===== 数据源能力健康卡 =====
// 能力路由架构下的侧栏状态: 不再展示「主数据源 + TickFlow 档位」(单源时代遗留 —
// 五个能力各自路由, 拿日K的源代表全局是随意的), 改为回答「各能力当前是否都有源在供」。
// 档位/订阅信息归设置页 TickFlow 介绍卡 (档位词仅出现在 TickFlow 专属界面的设计规则)。
// 单能力方格: 可用=绿 / 日K缺失=红 / 其他缺失=琥珀 (与悬浮卡中同色, 一眼对应)
function capSquareCls(c: { id: string; usable: boolean }) {
  return c.usable ? 'bg-accent' : c.id === 'daily' ? 'bg-danger' : 'bg-warning/80'
}

function DataSourceHealthBadge({ matrix }: { matrix: CapabilityMatrix | undefined }) {
  const caps = matrix?.capabilities ?? []
  const loading = caps.length === 0
  const usableCount = caps.filter(c => c.usable).length
  const down = caps.filter(c => !c.usable)
  // 日K是核心能力 (其他一切派生于它): 挂了用危险色; 一般缺项琥珀; 全可用绿
  const level = loading
    ? 'loading'
    : down.length === 0 ? 'ok' : down.some(c => c.id === 'daily') ? 'danger' : 'warn'
  const countCls = level === 'ok' ? 'text-accent/80'
    : level === 'danger' ? 'text-danger'
    : level === 'warn' ? 'text-warning'
    : 'text-muted'

  // 悬浮卡: 侧栏 aside 是 overflow-hidden, 用 fixed 定位逃逸裁剪 (坐标取自徽标实时位置)。
  // 徽标靠近屏幕顶部时居中定位会把卡片上半截推出视口 → 渲染后按实际高度钳制进视口。
  const linkRef = useRef<HTMLAnchorElement>(null)
  const popRef = useRef<HTMLDivElement>(null)
  const closeTimer = useRef<number | undefined>(undefined)
  const [popPos, setPopPos] = useState<{ left: number; top: number } | null>(null)
  const openPop = () => {
    window.clearTimeout(closeTimer.current)
    const rect = linkRef.current?.getBoundingClientRect()
    if (rect) setPopPos({ left: rect.right, top: rect.top + rect.height / 2 })
  }
  const closePop = () => {
    closeTimer.current = window.setTimeout(() => setPopPos(null), 80)
  }
  useEffect(() => () => window.clearTimeout(closeTimer.current), [])
  useLayoutEffect(() => {
    if (!popPos || !popRef.current) return
    const h = popRef.current.offsetHeight
    const margin = 8
    const minCenter = margin + h / 2
    const maxCenter = window.innerHeight - margin - h / 2
    const clamped = Math.min(maxCenter, Math.max(minCenter, popPos.top))
    if (clamped !== popPos.top) setPopPos({ ...popPos, top: clamped })
  }, [popPos])

  return (
    <>
      <NavLink
        ref={linkRef}
        to="/settings?tab=data-sources"
        aria-label={`数据源能力 ${usableCount}/${caps.length || 5} 可用, 点击前往数据源配置`}
        onMouseEnter={openPop}
        onMouseLeave={closePop}
        onFocus={openPop}
        onBlur={closePop}
        onKeyDown={e => { if (e.key === 'Escape') setPopPos(null) }}
        className="group relative flex items-center gap-2 overflow-hidden rounded-md py-1.5 pl-2.5 pr-2 transition-colors duration-150 hover:bg-elevated/70"
      >
        <span className="pointer-events-none absolute inset-y-1.5 left-0 w-[2px] rounded-full bg-accent/50 transition-colors group-hover:bg-accent" />
        <DatabaseZap className="h-3.5 w-3.5 shrink-0 text-muted group-hover:text-accent transition-colors" />
        {/* 能力方格 (按注册顺序: 实时/日K/分钟/除权/财务), 与悬浮卡逐格同色对应 */}
        <span className="flex items-center gap-1 shrink-0">
          {loading
            ? Array.from({ length: 5 }, (_, i) => (
                <span key={i} className="h-2 w-2 rounded-[2px] bg-muted animate-pulse" />
              ))
            : caps.map(c => (
                <span key={c.id} className={`h-2 w-2 rounded-[2px] ${capSquareCls(c)}`} />
              ))}
        </span>
        {!loading && (
          <span className={`ml-auto text-[10px] font-mono font-bold leading-none shrink-0 ${countCls}`}>
            {usableCount}/{caps.length}
          </span>
        )}
      </NavLink>
      {popPos && (
        <div
          ref={popRef}
          className="fixed z-50 -translate-y-1/2 pl-3"
          style={{ left: popPos.left, top: popPos.top }}
          onMouseEnter={() => window.clearTimeout(closeTimer.current)}
          onMouseLeave={closePop}
        >
          <motion.div
            initial={{ opacity: 0, x: -6 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.15, ease: [0.16, 1, 0.3, 1] }}
            className="w-64 rounded-md border border-border bg-surface py-2.5 pl-3 pr-3.5 shadow-2xl shadow-black/40"
          >
            <div className="mb-2 flex items-center justify-between">
              <span className="flex items-center gap-1.5 text-xs font-medium text-foreground">
                <DatabaseZap className="h-3.5 w-3.5 text-accent" />
                数据源能力
              </span>
              <span className={`text-[10px] font-mono font-bold ${countCls}`}>
                {loading ? '获取中…' : `${usableCount}/${caps.length} 可用`}
              </span>
            </div>
            <div className="space-y-1.5 border-t border-border/60 pt-2">
              {loading ? (
                <div className="py-0.5 text-[11px] text-muted">正在获取能力路由状态…</div>
              ) : caps.map(c => (
                <div key={c.id} className="flex min-w-0 items-center gap-2">
                  <span className={`h-2 w-2 shrink-0 rounded-[2px] ${capSquareCls(c)}`} />
                  <span className="shrink-0 text-xs font-medium text-secondary">{c.label}</span>
                  <span className="ml-auto flex min-w-0 shrink items-center gap-1.5">
                    {c.usable ? (
                      <>
                        <span className="truncate text-[11px] text-muted">{c.effective_display}</span>
                        <CheckCircle2 className="h-3 w-3 shrink-0 text-accent" />
                      </>
                    ) : (
                      <span className="text-[11px] text-muted/70">未接入</span>
                    )}
                  </span>
                </div>
              ))}
            </div>
            {/* 分时有分钟K功能替身 (intraday_monitor_support 三路可达), 不单独占能力格, 在此备注 */}
            <div className="mt-1.5 text-[10px] leading-relaxed text-muted/70">
              分时信号监控可由分钟 K 数据驱动，不单独设能力格
            </div>
            <div className="mt-2 flex items-center gap-1 border-t border-border/60 pt-1.5 text-[10px] text-muted">
              点击前往数据源配置
              <ChevronRight className="h-3 w-3" />
            </div>
          </motion.div>
        </div>
      )}
    </>
  )
}

function AIConfigBadge({ configured, model }: { configured?: boolean; model?: string }) {
  // [R109] 显示"当前实际在用的那一档" —— 全系统 AI 走档位表(第 1 档优先, 用不了
  // 自动顺位)。[R114] 点开是下拉快切: 选谁就把谁提到第 1 位并保存, 与「设置 →
  // AI 设置」共用同一 queryKey, 两边永远同一份顺序。
  const qc = useQueryClient()
  const btnRef = useRef<HTMLButtonElement>(null)
  const [menuPos, setMenuPos] = useState<{ left: number; top: number } | null>(null)
  const profilesQ = useQuery({
    queryKey: QK.aiProfiles,
    queryFn: api.aiProfiles,
    staleTime: 60_000,
  })
  const rows = profilesQ.data?.profiles ?? []
  const managed = rows.filter(p => !p.synthesized)
  const enabled = managed.filter(p => p.enabled)
  const primary = enabled[0]
  // 表里排第一但没勾「启用」的档位: 调用链会跳过它, 徽标也不能显示它 ——
  // 但用户多半以为"拖上去就是首选", 这里必须点破, 否则看起来就是"没跟着切换"
  const topRow = managed[0]
  const topDisabled = topRow && !topRow.enabled ? (topRow.label?.trim() || topRow.model) : null

  const shownModel = primary ? (primary.label?.trim() || primary.model) : model
  const isConfigured = managed.length > 0 ? enabled.length > 0 : configured
  const fallbackCount = enabled.length > 1 ? enabled.length - 1 : 0
  const descText = isConfigured ? (shownModel || '已接入模型') : '接入策略生成模型'

  // 切档: 把选中项提到第 1 位(其余保持原相对顺序)后整表保存。
  // api_key 回传空串即可 —— 后端按 id 对号沿用原 key(见 save_ai_profiles)。
  const switchTo = useMutation({
    mutationFn: async (id: string) => {
      const picked = managed.find(p => p.id === id)
      if (!picked) return
      const next = [picked, ...managed.filter(p => p.id !== id)]
      await api.saveAiProfiles(next.map(p => ({ ...p, enabled: p.id === id ? true : p.enabled })))
    },
    onSuccess: () => {
      setMenuPos(null)
      qc.invalidateQueries({ queryKey: QK.aiProfiles })
      qc.invalidateQueries({ queryKey: QK.settings })
      toast('已切换首选 AI 档位', 'success')
    },
    onError: (e: any) => toast(String(e?.message ?? '切换失败'), 'error'),
  })

  const toggleMenu = () => {
    if (menuPos) { setMenuPos(null); return }
    const rect = btnRef.current?.getBoundingClientRect()
    if (rect) setMenuPos({ left: rect.left, top: rect.bottom + 4 })
  }
  useEffect(() => {
    if (!menuPos) return
    const onDoc = () => setMenuPos(null)
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setMenuPos(null) }
    window.addEventListener('click', onDoc)
    window.addEventListener('keydown', onKey)
    return () => { window.removeEventListener('click', onDoc); window.removeEventListener('keydown', onKey) }
  }, [menuPos])

  return (
    <>
      <button
        ref={btnRef}
        onClick={e => { e.stopPropagation(); toggleMenu() }}
        title={managed.length > 0 ? '点击快速切换首选 AI 档位' : `AI 配置 — ${descText}`}
        className="group relative flex w-full items-center gap-2 overflow-hidden rounded-md py-1.5 pl-2.5 pr-2 text-left transition-colors duration-150 hover:bg-elevated/70"
      >
        <span className="pointer-events-none absolute inset-y-1.5 left-0 w-[2px] rounded-full bg-purple-400/50 transition-colors group-hover:bg-purple-400" />
        <Sparkles className="h-3.5 w-3.5 shrink-0 text-muted group-hover:text-purple-400 transition-colors" />
        {isConfigured ? (
          <>
            <span className="truncate text-[11px] font-medium text-secondary group-hover:text-foreground transition-colors">
              {shownModel || '已接入模型'}
            </span>
            {fallbackCount > 0 && (
              <span className="shrink-0 font-mono text-[9px] leading-none text-muted/70" title="备用档位数(前一档用不了时自动顺位)">
                +{fallbackCount}
              </span>
            )}
            {topDisabled && (
              <span className="shrink-0 text-[9px] leading-none text-warning" title={`表里第 1 档「${topDisabled}」未启用, 已跳过`}>
                ⚠
              </span>
            )}
            {managed.length > 1 && (
              <ChevronDown className="h-3 w-3 shrink-0 text-muted/50 transition-colors group-hover:text-muted" />
            )}
          </>
        ) : (
          <>
            <span className="text-[11px] text-secondary group-hover:text-foreground transition-colors">AI 配置</span>
            <span className="ml-auto text-[11px] font-mono leading-none text-muted">未配置</span>
          </>
        )}
        <span className={`ml-auto h-1.5 w-1.5 rounded-full shrink-0 ${isConfigured ? 'bg-bear' : 'bg-warning'}`} />
      </button>

      {/* 下拉: 侧栏 overflow-hidden, 用 fixed 逃逸裁剪 */}
      {menuPos && (
        <div
          onClick={e => e.stopPropagation()}
          style={{ left: menuPos.left, top: menuPos.top }}
          className="fixed z-[60] w-60 rounded-card border border-border bg-surface p-1 shadow-xl"
        >
          <div className="px-2 py-1 text-[9px] text-muted">
            首选档位 · 用不了时自动顺位试下一档
          </div>
          {managed.length === 0 ? (
            <div className="px-2 py-2 text-[10px] text-muted">还没有档位 —— 去 AI 设置里添加</div>
          ) : managed.map((p, i) => {
            const label = p.label?.trim() || p.model
            const isPrimary = primary?.id === p.id
            return (
              <button
                key={p.id}
                onClick={() => !isPrimary && switchTo.mutate(p.id)}
                disabled={switchTo.isPending}
                className={cn(
                  'flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-[11px] transition-colors disabled:opacity-60',
                  isPrimary ? 'bg-accent/10 text-accent' : 'text-secondary hover:bg-elevated hover:text-foreground',
                )}
              >
                <span className="w-3 shrink-0 text-center font-mono text-[9px] text-muted">{i + 1}</span>
                <span className="min-w-0 flex-1 truncate">{label}</span>
                {!p.enabled && <span className="shrink-0 text-[9px] text-warning">未启用</span>}
                {isPrimary && <CheckCircle2 className="h-3 w-3 shrink-0" />}
              </button>
            )
          })}
          <div className="mt-1 border-t border-border/60 pt-1">
            <NavLink
              to="/settings?tab=ai"
              onClick={() => setMenuPos(null)}
              className="block rounded px-2 py-1.5 text-[10px] text-muted transition-colors hover:bg-elevated hover:text-foreground"
            >
              管理档位(增删 / 改 Key / 排序) →
            </NavLink>
          </div>
        </div>
      )}
    </>
  )
}

type NavItem = { to: string; label: string; icon: typeof Gauge; badge?: string }

/** 普通菜单项 —— 顶层和「盘面参考」组里用的是同一个, 免得两处样式各走各的。 */
function PlainNavLink({ item, collapsed, indent, dataSyncing, dataSyncJustDone }: {
  item: NavItem
  collapsed: boolean
  indent?: boolean
  dataSyncing?: boolean
  dataSyncJustDone?: boolean
}) {
  const { to, label, icon: Icon, badge } = item
  return (
    <div className={indent && !collapsed ? 'pl-3' : undefined}>
      <NavLink
        to={to}
        title={collapsed ? label : undefined}
        className={({ isActive }) =>
          cn(
            'group relative flex items-center rounded-btn text-sm transition-all duration-150 ease-smooth',
            collapsed ? 'justify-center px-0 py-2' : 'gap-2.5 px-3 py-1.5',
            isActive
              ? 'bg-elevated text-foreground font-medium'
              : 'text-foreground/75 hover:bg-elevated/70 hover:text-foreground',
          )
        }
      >
        {({ isActive }) => (
          <>
            {/* active 左侧 accent 竖条指示 */}
            <span
              className={cn(
                'pointer-events-none absolute left-0 top-1/2 h-4 -translate-y-1/2 w-[2.5px] rounded-full bg-accent transition-opacity duration-150',
                isActive ? 'opacity-100 shadow-[0_0_8px_rgba(59,130,246,0.6)]' : 'opacity-0',
              )}
            />
            <Icon className={cn('h-4 w-4 shrink-0 transition-colors', isActive ? 'text-accent' : 'text-foreground/60 group-hover:text-foreground/85')} />
            {!collapsed && <span className="flex-1">{label}</span>}
            {!collapsed && badge && (
              <span className="ml-auto inline-flex items-center rounded-full border border-amber-400/30 bg-amber-400/10 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wider text-amber-400 shrink-0">
                {badge}
              </span>
            )}
            {/* 数据同步状态: 同步中转圈, 刚完成显示绿色对勾闪烁 3 秒 */}
            {to === '/data' && dataSyncing && !collapsed && (
              <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin text-accent" />
            )}
            {to === '/data' && !dataSyncing && dataSyncJustDone && !collapsed && (
              <CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-bull animate-pulse" />
            )}
            {/* 监控中心徽标: 仅非监控页且有未读时显示 */}
            {to === '/monitor' && !collapsed && <MonitorBadge active={isActive} />}
          </>
        )}
      </NavLink>
    </div>
  )
}

export function Layout() {
  // ===== 共享 hooks (替代内联 useQuery) =====
  const { data: settingsState } = useSettings()
  const { data: matrix } = useCapabilityMatrix()
  const { data: versionData } = useVersion()
  const { data: prefs } = usePreferences()
  // 数据源列表 (用于实时行情状态显示当前数据源名称)
  const { data: dataSources } = useQuery({
    queryKey: QK.dataSources,
    queryFn: api.dataSources,
    staleTime: 60_000,
  })
  // poll=true: 全局唯一开启条件轮询 (非交易时段 60s 兜底, 交易时段靠 SSE)
  const { data: quoteStatus } = useQuoteStatus({ poll: true })
  const { data: analysisMenus } = useQuery({
    queryKey: QK.analysisMenus,
    queryFn: api.analysisMenus,
  })

  // 自选分组 — 仅当用户开启「显示在侧边栏」时拉取
  const groupsInNav = prefs?.watchlist_groups_in_nav ?? false
  const location = useLocation()
  const { data: watchlistGroupsData } = useQuery({
    queryKey: QK.watchlistGroups,
    queryFn: api.watchlistGroups,
    enabled: groupsInNav,
    staleTime: 60_000,
  })
  const watchlistGroups = watchlistGroupsData?.groups ?? []
  // 自选二级菜单展开状态 — 默认当前在自选页时展开
  const [watchlistNavExpanded, setWatchlistNavExpanded] = useState(location.pathname === '/watchlist')

  // 侧边栏收起状态 — 持久化到 localStorage
  const [navCollapsed, setNavCollapsed] = useState(() => {
    if (typeof window !== 'undefined' && window.matchMedia('(max-width: 767px)').matches) return true
    try { return localStorage.getItem('tf-nav-collapsed') === '1' } catch { return false }
  })

  // [R57] 「盘面参考」分组默认折叠 —— 展示型的几页不该占主视野
  const [browseOpen, setBrowseOpen] = useState(() => {
    try { return localStorage.getItem('tf-nav-browse-open') === '1' } catch { return false }
  })
  useEffect(() => {
    try { localStorage.setItem('tf-nav-browse-open', browseOpen ? '1' : '0') } catch { /* 忽略 */ }
  }, [browseOpen])

  // 分组等权平均涨跌幅 — 复用 watchlist/enriched 查询缓存(与自选页同 key,
  // 盘中随 SSE 刷新)。可见性门控: 子菜单实际可见(侧栏展开 + 二级菜单展开)
  // 时才拉取, 收起状态下不为隐藏 UI 发请求。
  const navGroupPctVisible = groupsInNav && !navCollapsed && watchlistNavExpanded
  const { data: navWatchlist } = useQuery({
    queryKey: QK.watchlist,
    queryFn: api.watchlistList,
    enabled: navGroupPctVisible,
    staleTime: 60_000,
  })
  const { data: navEnriched } = useQuery({
    queryKey: QK.watchlistEnriched(undefined),
    queryFn: () => api.watchlistEnriched(),
    enabled: navGroupPctVisible,
    staleTime: 60_000,
  })
  const navGroupPcts = useMemo(
    () => computeGroupPcts(
      navWatchlist?.symbols ?? [],
      new Map((navEnriched?.rows ?? []).map((r: any) => [r.symbol as string, r])),
    ),
    [navWatchlist, navEnriched],
  )

  // 数据同步状态轮询: 有活跃 job 时「数据」菜单项显示转圈
  const { data: pipelineJobs } = useQuery({
    queryKey: QK.pipelineJobs,
    queryFn: () => api.pipelineJobs(1),
    refetchInterval: (query) => (query.state.data?.active_id ? 2000 : 15000),
    refetchIntervalInBackground: true,
  })
  const isDataSyncing = !!pipelineJobs?.active_id

  // 数据同步完成的"瞬时反馈": isDataSyncing 从 true→false 时显示绿色对勾,
  // 闪烁约 3 秒后自动消失。
  const [dataSyncJustDone, setDataSyncJustDone] = useState(false)
  const prevSyncingRef = useRef(false)
  useEffect(() => {
    // 仅在"刚结束"(true→false)且非首次挂载时触发
    if (prevSyncingRef.current && !isDataSyncing) {
      setDataSyncJustDone(true)
      const t = setTimeout(() => setDataSyncJustDone(false), 3000)
      prevSyncingRef.current = isDataSyncing
      return () => clearTimeout(t)
    }
    prevSyncingRef.current = isDataSyncing
  }, [isDataSyncing])

  const qc = useQueryClient()
  const navigate = useNavigate()
  const version = versionData?.version
  const realtimeEnabled = prefs?.realtime_quotes_enabled ?? false
  // [R118] 自动开关: 开着的话后端守护线程按「交易日 + 09:15~15:05」自己开关行情。
  // 边沿触发 —— 中途手动改了就听手动的, 到下一个边界再回到自动节奏。
  const realtimeAuto = prefs?.realtime_auto ?? false
  // 自选实时模式限制提示: 可手动关闭, 不持久化 (刷新后恢复显示)
  const [dismissFreeHint, setDismissFreeHint] = useState(false)
  useEffect(() => {
    const compact = window.matchMedia('(max-width: 767px)')
    const syncSidebarWithViewport = (event: MediaQueryListEvent | MediaQueryList) => {
      if (event.matches) {
        setNavCollapsed(true)
        return
      }
      try { setNavCollapsed(localStorage.getItem('tf-nav-collapsed') === '1') } catch {}
    }
    syncSidebarWithViewport(compact)
    compact.addEventListener('change', syncSidebarWithViewport)
    return () => compact.removeEventListener('change', syncSidebarWithViewport)
  }, [])
  const toggleNavCollapsed = () => {
    setNavCollapsed(prev => {
      const next = !prev
      try { localStorage.setItem('tf-nav-collapsed', next ? '1' : '0') } catch {}
      return next
    })
  }
  const indicesPinned = prefs?.indices_nav_pinned ?? true
  const sidebarIndexSymbols = prefs?.sidebar_index_symbols ?? CORE_INDEXES.map(p => p.symbol)
  const sidebarIndexes = CORE_INDEXES.filter(item => sidebarIndexSymbols.includes(item.symbol))
  // 卡片数据：固定显示时也拉取（即使实时行情关闭）
  const showSidebarQuotes = indicesPinned || realtimeEnabled
  const { data: sidebarIndexQuotes } = useQuery({
    queryKey: [...QK.indexQuotes, 'sidebar', sidebarIndexSymbols.join(',')] as const,
    queryFn: () => api.indexQuotes(sidebarIndexes.map(p => p.symbol)),
    enabled: showSidebarQuotes && sidebarIndexes.length > 0,
    placeholderData: (prev) => prev,
  })

  // SSE: 行情更新时自动刷新相关 queries + 告警通知
  useQuoteStream(realtimeEnabled, prefs?.sse_refresh_pages)
  // 实时 SSE 连接状态 — 断开时底部显示提示, 提示可能漏策略告警
  const streamStatus = useQuoteStreamStatus()

  const toggleQuote = useToggleRealtimeQuotes()
  const isRunning = quoteStatus?.running ?? false
  const isTrading = quoteStatus?.is_trading_hours ?? false
  // 管道/数据修正运行期间实时行情被临时暂停 — 此时禁止开启
  const isPaused = quoteStatus?.paused ?? false
  // 实时模式以 quote_status 为准 (数据源无关): none=不可用 / watchlist=自选实时 / full_market=全市场
  const quoteMode = quoteStatus?.mode ?? 'none'
  const realtimeUnavailable = quoteMode === 'none'
  const isWatchlistMode = quoteMode === 'watchlist'
  const realtimeModeLabel = isWatchlistMode ? '自选股' : '全市场'
  // 当前实时行情数据源名称 (custom 时显示源名, tickflow 时不显示)
  const realtimeProvider = prefs?.realtime_data_provider
  const realtimeProviderName = realtimeProvider && realtimeProvider !== 'tickflow'
    ? (dataSources?.custom?.find(s => s.name === realtimeProvider)?.display_name || realtimeProvider)
    : null
  // [R102] A 股卡自身的可用性条件(全球卡不受其影响)
  const cnQuotesOk = !isWatchlistMode && (!realtimeUnavailable || !!realtimeProviderName)
  const globalIdxQuery = useQuery({
    queryKey: QK.globalIndices,
    queryFn: api.globalIndices,
    // [R112] 有市场在交易时就跟 A 股同频刷(8s), 全部休市时退到 60s ——
    // 休市值静止, 高频拉只是白打上游
    refetchInterval: (q: any) => (q?.state?.data?.items ?? []).some((i: any) => i.trading) ? 8000 : 60000,
    placeholderData: (prev: { items: import('@/lib/api').GlobalIndexQuote[] } | undefined) => prev,
    enabled: showSidebarQuotes && !navCollapsed,
  })
  const realtimeToggleDisabled = toggleQuote.isPending || isPaused
  const realtimeActive = realtimeEnabled && isRunning && isTrading
  const realtimeStatusLabel = toggleQuote.isPending
    ? '正在更新'
    : isPaused
      ? '同步期间暂停'
      : realtimeActive
        ? '运行中'
        : realtimeEnabled
          ? (isTrading ? '正在连接' : '等待交易时段')
          : '已关闭'
  const realtimeStatusClass = realtimeActive
    ? 'text-accent'
    : realtimeEnabled || isPaused
      ? 'text-warning/80'
      : 'text-muted'
  const realtimeIndicatorClass = realtimeActive
    ? 'bg-accent animate-pulse'
    : realtimeEnabled || isPaused
      ? 'bg-warning/70'
      : 'bg-muted'
  const toggleRealtimeAuto = useMutation({
    mutationFn: (next: boolean) => api.updateRealtimeAuto(next),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: QK.preferences })
      toast(res.realtime_auto ? `已开启自动行情(${res.window})` : '已关闭自动行情', 'success')
    },
  })
  const realtimeToggleTitle = isPaused
    ? '数据同步运行中，实时行情已临时暂停'
    : toggleQuote.isPending
      ? '正在更新实时行情设置'
      : realtimeEnabled
        ? '关闭实时行情'
        : '开启实时行情'

  // 轮询触发记录总数 → 更新监控中心徽标 (每 15 秒; 后台标签页由 SSE 事件驱动, 不轮询)
  const alertsTotalQuery = useQuery({
    queryKey: ['alerts-total'],
    queryFn: () => api.alertsList({ days: 7, limit: 1 }),
    refetchInterval: 15000,
    select: (data) => data.total,
  })
  // 只在拿到真实总数时同步徽标 (避免 data=undefined 时传 0 重置 lastSeen)
  const alertsTotal = alertsTotalQuery.data
  useEffect(() => {
    if (alertsTotal != null) setAlertTotal(alertsTotal)
  }, [alertsTotal])

  // 合并内置页面 + 可见的扩展分析菜单
  const analysisNav: NavItem[] = (analysisMenus?.items ?? [])
    .filter(m => m.visible)
    .map(m => ({ to: `/analysis/${m.id}`, label: m.label, icon: m.icon === 'tags' ? Tags : BarChart3 }))
  const extensionNav: NavItem[] = getFrontendExtensionNavigation().map(item => ({
    to: item.route.path,
    label: item.label,
    icon: item.icon,
    badge: item.badge,
  }))
  const externalPageNav: NavItem[] = prefs?.external_page_enabled && prefs.external_page_url
    ? [{ to: '/external-page', label: prefs.external_page_name || '利弗莫尔趋势', icon: Globe2 }]
    : []

  const allNav: NavItem[] = [...nav, ...externalPageNav, ...analysisNav, ...extensionNav]
  const savedOrder = prefs?.nav_order ?? []

  const navItems = savedOrder.length > 0
    ? (() => {
        const byTo = new Map(allNav.map(n => [n.to, n]))
        const ordered = (savedOrder
          .map(id => byTo.get(id) ?? byTo.get(`/analysis/${id}`))
          .filter(Boolean)) as typeof allNav
        const seen = new Set(ordered.map(n => n.to))
        const merged = [...ordered]
        for (const item of allNav) {
          if (seen.has(item.to)) continue
          // 未保存过排序的新条目: 内置页插回默认位置(排在已保存的默认前驱之后),
          // 分析/扩展菜单仍追加到末尾
          const defaultIndex = nav.findIndex(n => n.to === item.to)
          let anchor = -1
          if (defaultIndex > 0) {
            for (let i = defaultIndex - 1; i >= 0 && anchor < 0; i -= 1) {
              anchor = merged.findIndex(n => n.to === nav[i].to)
            }
          }
          if (anchor >= 0) merged.splice(anchor + 1, 0, item)
          else if (defaultIndex >= 0) merged.unshift(item)
          else merged.push(item)
        }
        return merged
      })()
    : allNav

  const hiddenIds = new Set(prefs?.nav_hidden ?? [])
  const shownNavItems = navItems.filter(n => !hiddenIds.has(n.to) && !hiddenIds.has(n.to.replace(/^\/analysis\//, '')))
  // [R67] 成员从顶层抽出来, 只在分组行下面出现 —— 分组行自己排在哪, 整块就在哪。
  const { top: visibleNavItems, members: browseItems } = splitBrowseGroup(shownNavItems, n => n.to)
  const browsePaths = browseItems.map(n => n.to)
  // 所有成员全隐藏了就别留一个空表头
  const showBrowseGroup = browsePaths.length > 0

  const handleToggle = async (enabled: boolean) => {
    // 开启时重新校验实时权限 (以 quote_status 的数据源无关判定为准)
    if (enabled) {
      const fresh = await qc.fetchQuery({
        queryKey: QK.quoteStatus,
        queryFn: api.quoteStatus,
      })
      if (!fresh.realtime_allowed) {
        toast('当前数据源无实时行情能力, 请先配置数据源', 'error')
        return
      }
    }
    await toggleQuote.mutateAsync(enabled)
    // 仅在交易时段立即获取一次行情
    if (enabled && isTrading) {
      api.intradayRefresh().catch(() => {})
    }
  }

  return (
    <div
      className="h-screen grid bg-base text-foreground overflow-hidden transition-[grid-template-columns] duration-200 ease-smooth"
      style={{ gridTemplateColumns: navCollapsed ? '3.5rem 1fr' : '14rem 1fr' }}
    >
      <aside className="border-r border-border bg-surface flex flex-col h-full min-h-0 overflow-hidden">
        <div className={cn('border-b border-border shrink-0', navCollapsed ? 'px-2 pt-3 pb-2' : 'px-4 pt-4 pb-3')}>
          {/* Brand block — 收起时只显 logo 居中 */}
          <div className={cn('flex', navCollapsed ? 'flex-col items-center gap-2' : 'items-center gap-2')}>
            <Logo
              size={navCollapsed ? 24 : 26}
              className="shrink-0 drop-shadow-[0_0_8px_rgba(139,92,246,0.4)]"
              style={{ color: BRAND }}
            />
            {!navCollapsed && (
              <div
                className="text-sm font-semibold tracking-[0.06em] text-foreground whitespace-nowrap"
                style={{ textShadow: `0 0 10px ${BRAND}44` }}
              >
                牛来
              </div>
            )}
            {/* 收起/展开 按钮 */}
            <button
              onClick={toggleNavCollapsed}
              className={cn(
                'flex items-center rounded-btn text-muted hover:text-foreground hover:bg-elevated/60 transition-colors duration-150 ease-smooth',
                navCollapsed ? 'justify-center p-1.5' : 'ml-auto p-1.5',
              )}
              title={navCollapsed ? '展开菜单' : '收起菜单'}
            >
              {navCollapsed
                ? <PanelLeftOpen className="h-3.5 w-3.5 shrink-0" />
                : <PanelLeftClose className="h-3.5 w-3.5 shrink-0" />
              }
            </button>
          </div>

            {/* 状态卡 — 收起时隐藏 */}
            {!navCollapsed && (
              <div className="mt-2.5 border-t border-border/60 pt-1">
                <DataSourceHealthBadge matrix={matrix} />
              <div className="mx-2 border-t border-border/45" aria-hidden="true" />
              <AIConfigBadge
                configured={settingsState?.ai_configured ?? settingsState?.has_ai_key}
                model={settingsState?.ai_model}
              />
            </div>
          )}
          {/* [R102] 指数报价 — A 股与全球指数同格同开关(showSidebarQuotes), 数据链各自独立:
              A 股来自行情主链, 全球来自独立新浪源; A 股实时不可用时全球卡照常显示 */}
          {!navCollapsed && showSidebarQuotes && (
            <SidebarIndexQuotes
              rows={cnQuotesOk ? sidebarIndexQuotes?.rows : undefined}
              items={cnQuotesOk ? sidebarIndexes : []}
              globalRows={globalIdxQuery.data?.items}
            />
          )}
        </div>

        <nav className="flex-1 min-h-0 overflow-y-auto px-2 py-2.5 space-y-0.5">
          {visibleNavItems.map((item) => {
            const { to, label, icon: Icon } = item
            // 「自选」项 — 开启分组侧栏且未整体收起时, 渲染为可展开父项 + 二级分组
            const isWatchlistExpandable = to === '/watchlist' && groupsInNav && !navCollapsed && watchlistGroups.length > 0
            // [R67] 「盘面参考」是菜单里实实在在的一行, 它排在哪整块就在哪 ——
            // 不再去猜"哪一页碰巧排最前"当表头, 成员也不会被中间的菜单切开。
            if (to === BROWSE_GROUP_ID) {
              if (!showBrowseGroup) return null
              return (
                <div key={to}>
                  <button
                    onClick={() => setBrowseOpen(v => !v)}
                    title={navCollapsed ? BROWSE_GROUP.label : BROWSE_GROUP.hint}
                    className={cn(
                      'group relative flex w-full items-center rounded-btn text-sm transition-all duration-150 ease-smooth',
                      navCollapsed ? 'justify-center px-0 py-2' : 'gap-2.5 px-3 py-1.5',
                      browsePaths.includes(location.pathname)
                        ? 'bg-elevated text-foreground font-medium'
                        : 'text-foreground/55 hover:bg-elevated/70 hover:text-foreground',
                    )}
                  >
                    <Layers3 className="h-4 w-4 shrink-0 text-foreground/50" />
                    {!navCollapsed && (
                      <>
                        <span className="flex-1 text-left">{BROWSE_GROUP.label}</span>
                        <span className="shrink-0 font-mono text-[10px] text-muted">{browsePaths.length}</span>
                        {browseOpen
                          ? <ChevronDown className="h-3.5 w-3.5 shrink-0 text-muted" />
                          : <ChevronRight className="h-3.5 w-3.5 shrink-0 text-muted" />}
                      </>
                    )}
                  </button>
                  {browseOpen && (
                    <div className="mt-0.5 space-y-0.5">
                      {browseItems.map(m => (
                        <PlainNavLink key={m.to} item={m} collapsed={navCollapsed} indent />
                      ))}
                    </div>
                  )}
                </div>
              )
            }
            return (
              <div key={to}>
                {isWatchlistExpandable ? (
                  /* 可展开的自选父项 — 点击切换展开, 不直接跳页 */
                  <button
                    onClick={() => setWatchlistNavExpanded(v => !v)}
                    className={cn(
                      'group relative flex w-full items-center gap-2.5 rounded-btn px-3 py-1.5 text-sm transition-all duration-150 ease-smooth',
                      location.pathname === '/watchlist'
                        ? 'bg-elevated text-foreground font-medium'
                        : 'text-foreground/75 hover:bg-elevated/70 hover:text-foreground',
                    )}
                  >
                    <span
                      className={cn(
                        'pointer-events-none absolute left-0 top-1/2 h-4 -translate-y-1/2 w-[2.5px] rounded-full bg-accent transition-opacity duration-150',
                        location.pathname === '/watchlist' ? 'opacity-100 shadow-[0_0_8px_rgba(59,130,246,0.6)]' : 'opacity-0',
                      )}
                    />
                    <Icon className={cn('h-4 w-4 shrink-0 transition-colors', location.pathname === '/watchlist' ? 'text-accent' : 'text-foreground/60 group-hover:text-foreground/85')} />
                    <span className="flex-1 text-left">{label}</span>
                    {watchlistNavExpanded
                      ? <ChevronDown className="h-3.5 w-3.5 shrink-0 text-muted" />
                      : <ChevronRight className="h-3.5 w-3.5 shrink-0 text-muted" />
                    }
                  </button>
                ) : (
                  <PlainNavLink
                    item={item}
                    collapsed={navCollapsed}
                    dataSyncing={isDataSyncing}
                    dataSyncJustDone={dataSyncJustDone}
                  />
                )}

                {/* 自选分组二级子菜单 — 展开时显示 */}
                {isWatchlistExpandable && watchlistNavExpanded && (
                  <div className="mt-0.5 space-y-0.5">
                    <NavLink
                      to="/watchlist"
                      className={({ isActive }) => cn(
                        'flex items-center gap-2 rounded-btn py-1.5 pl-9 pr-3 text-[12px] transition-colors duration-150 ease-smooth',
                        isActive && !location.search
                          ? 'text-accent font-medium'
                          : 'text-foreground/60 hover:text-foreground hover:bg-elevated/50',
                      )}
                    >
                      <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-muted" />
                      <span>全部</span>
                      {(() => {
                        const info = navGroupPcts['all']
                        return info && info.pct != null ? (
                          <span className={`ml-auto font-mono text-[10px] tabular-nums ${groupPctColor(info.pct)}`} title={groupPctTitle(info)}>
                            {fmtPct(info.pct)}
                          </span>
                        ) : null
                      })()}
                    </NavLink>
                    {watchlistGroups.map(group => {
                      const color = resolveWatchlistGroupColor(group.color)
                      const groupPath = `/watchlist?group=${group.id}`
                      const isGroupActive = location.pathname === '/watchlist' && location.search === `?group=${group.id}`
                      const pctInfo = navGroupPcts[group.id]
                      return (
                        <NavLink
                          key={group.id}
                          to={groupPath}
                          className={cn(
                            'flex items-center gap-2 rounded-btn py-1.5 pl-9 pr-3 text-[12px] transition-colors duration-150 ease-smooth',
                            isGroupActive
                              ? 'text-accent font-medium'
                              : 'text-foreground/60 hover:text-foreground hover:bg-elevated/50',
                          )}
                        >
                          <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${color.dot}`} />
                          <span className="truncate">{group.name}</span>
                          {pctInfo && pctInfo.pct != null && (
                            <span className={`ml-auto font-mono text-[10px] tabular-nums ${groupPctColor(pctInfo.pct)}`} title={groupPctTitle(pctInfo)}>
                              {fmtPct(pctInfo.pct)}
                            </span>
                          )}
                        </NavLink>
                      )
                    })}
                  </div>
                )}
              </div>
            )
          })}
          <ExtensionSlot
            name="layout.navigation.extra"
            context={{ collapsed: navCollapsed, pathname: location.pathname }}
            compact
          />
        </nav>

        {/* 全局行情开关 — 收起时只显示状态指示点 */}
        {navCollapsed ? (
          <div className="border-t border-border px-2 py-2.5 shrink-0 flex justify-center">
            <button
              onClick={() => handleToggle(!realtimeEnabled)}
              disabled={realtimeToggleDisabled}
              aria-label={realtimeToggleTitle}
              aria-busy={toggleQuote.isPending}
              title={realtimeToggleTitle}
              className="flex items-center justify-center rounded-btn p-1.5 transition-colors hover:bg-elevated/70 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <span className={`inline-block h-2 w-2 rounded-full ${realtimeIndicatorClass}`} />
            </button>
          </div>
        ) : (
        <div className="border-t border-border px-3 py-2.5 shrink-0">
          {realtimeUnavailable && !realtimeProviderName ? (
            <div>
              <div className="flex items-center justify-between">
                <span className="text-xs text-secondary truncate">实时行情</span>
                <span className="text-[10px] text-muted/80 bg-elevated px-1.5 py-0.5 rounded">
                  不可用
                </span>
              </div>
              <div className="mt-1.5 text-[10px] leading-snug text-muted">
                当前数据源无实时行情权限,
                <button
                  type="button"
                  onClick={() => navigate('/settings?tab=data-sources&highlight=data-sources')}
                  className="mx-0.5 text-accent/80 hover:text-accent hover:underline"
                >
                  去配置数据源
                </button>
              </div>
            </div>
          ) : (
            /* 实时可用 — 开关 + 跳转设置 */
            <div className="flex items-center gap-2">
              <div className="flex min-w-0 flex-1 items-center gap-2">
                <span className={`inline-block h-2 w-2 shrink-0 rounded-full ${realtimeIndicatorClass}`} />
                <div className="min-w-0">
                  <div className="text-xs font-medium leading-none text-foreground">实时行情</div>
                  <div className="mt-1 flex min-w-0 items-center gap-1 text-[10px] leading-none">
                    <span className="truncate text-muted">{realtimeProviderName || realtimeModeLabel}</span>
                    <span className="shrink-0 text-border" aria-hidden="true">·</span>
                    <span className={`shrink-0 ${realtimeStatusClass}`}>{realtimeStatusLabel}</span>
                    {realtimeAuto && (
                      <>
                        <span className="shrink-0 text-border" aria-hidden="true">·</span>
                        <span className="shrink-0 text-accent/80">自动</span>
                      </>
                    )}
                  </div>
                </div>
              </div>
              <div className="flex shrink-0 items-center gap-1">
                {/* [R118] 自动开关: 交易日 09:15 自动开、15:05 自动关(收盘定版没完成会延后到 15:40) */}
                <button
                  type="button"
                  role="switch"
                  aria-checked={realtimeAuto}
                  aria-label="按交易日自动开关行情"
                  onClick={() => toggleRealtimeAuto.mutate(!realtimeAuto)}
                  disabled={toggleRealtimeAuto.isPending || realtimeUnavailable}
                  title={realtimeAuto
                    ? '自动开关已开启：交易日 09:15 自动开、15:05 自动关。中途手动改动在当天有效，次日恢复自动'
                    : '开启后按交易日自动开关行情，不用每天手动点'}
                  className={cn(
                    'flex h-7 items-center rounded-btn px-1.5 text-[10px] font-medium transition-colors',
                    realtimeAuto
                      ? 'bg-accent/15 text-accent hover:bg-accent/25'
                      : 'text-muted hover:bg-elevated hover:text-foreground',
                    (toggleRealtimeAuto.isPending || realtimeUnavailable) && 'cursor-not-allowed opacity-50',
                  )}
                >
                  自动
                </button>
                <button
                  onClick={() => navigate('/settings?tab=monitoring&highlight=quotes')}
                  aria-label="打开实时监控设置"
                  className="flex h-7 w-7 items-center justify-center rounded-btn text-muted transition-colors hover:bg-elevated hover:text-foreground"
                  title="实时监控设置"
                >
                  <Settings className="h-3.5 w-3.5" />
                </button>
                <button
                  type="button"
                  role="switch"
                  aria-checked={realtimeEnabled}
                  aria-label={realtimeToggleTitle}
                  aria-busy={toggleQuote.isPending}
                  onClick={() => handleToggle(!realtimeEnabled)}
                  disabled={realtimeToggleDisabled}
                  title={realtimeToggleTitle}
                  className={cn(
                    'relative inline-flex h-5 w-9 items-center rounded-full border transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/40 focus-visible:ring-offset-1 focus-visible:ring-offset-surface',
                    realtimeEnabled
                      ? 'border-accent/50 bg-accent shadow-[0_0_6px_rgba(59,130,246,0.25)]'
                      : 'border-border bg-elevated hover:border-muted',
                    realtimeToggleDisabled ? 'cursor-not-allowed opacity-50' : 'cursor-pointer',
                  )}
                >
                  <span className={cn(
                    'inline-block h-3.5 w-3.5 rounded-full border border-black/5 bg-white shadow-sm transition-transform duration-200',
                    realtimeEnabled ? 'translate-x-[18px]' : 'translate-x-0.5',
                  )} />
                </button>
              </div>
            </div>
          )}

          {/* 状态提示 */}
          {realtimeEnabled
            && (!realtimeUnavailable || realtimeProviderName)
            && (isPaused || (isWatchlistMode && !dismissFreeHint && !realtimeProviderName))
            && (
              <div className="mt-1.5 text-[10px] leading-snug space-y-0.5">
                {isWatchlistMode && !dismissFreeHint && !realtimeProviderName && (
                  <div className="flex items-start gap-1 text-amber-400/80">
                    <span className="flex-1">自选实时模式监控前 5 只，全市场实时依赖数据源支持</span>
                    <button
                      onClick={() => setDismissFreeHint(true)}
                      className="text-amber-400/50 hover:text-amber-400 shrink-0 transition-colors"
                      title="关闭提示"
                    >
                      <X className="h-2.5 w-2.5" />
                    </button>
                  </div>
                )}
                {isPaused && (
                  <div className="text-warning/80">数据同步运行中，实时行情已临时暂停</div>
                )}
              </div>
            )}
        </div>
        )}

        <div className={cn('border-t border-border py-3 shrink-0', navCollapsed ? 'px-2 flex flex-col items-center gap-1' : 'px-2')}>
          <div className={navCollapsed ? 'flex flex-col items-center gap-1' : 'flex items-center gap-1'}>
            <ThemeToggle />
            <NavLink
              to="/settings"
              title={navCollapsed ? '设置' : undefined}
              className={({ isActive }) =>
                cn(
                  'group relative flex items-center rounded-btn text-sm transition-all duration-150 ease-smooth',
                  navCollapsed ? 'justify-center px-0 py-2' : 'flex-1 gap-2.5 px-3 py-1.5',
                  isActive
                    ? 'bg-elevated text-foreground font-medium'
                    : 'text-foreground/75 hover:bg-elevated/70 hover:text-foreground',
                )
              }
            >
              {({ isActive }) => (
                <>
                  <span
                    className={cn(
                      'pointer-events-none absolute left-0 top-1/2 h-4 -translate-y-1/2 w-[2.5px] rounded-full bg-accent transition-opacity duration-150',
                      isActive ? 'opacity-100 shadow-[0_0_8px_rgba(59,130,246,0.6)]' : 'opacity-0',
                    )}
                  />
                  <Settings className={cn('h-4 w-4 shrink-0 transition-colors', isActive ? 'text-accent' : 'text-foreground/60 group-hover:text-foreground/85')} />
                  {!navCollapsed && <span>设置</span>}
                  {!navCollapsed && version && (
                    <span className="ml-auto font-mono text-[10px] text-muted/50 select-none shrink-0">
                      {version}
                    </span>
                  )}
                </>
              )}
            </NavLink>
          </div>
        </div>
      </aside>

      <motion.main
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
        className="h-full overflow-auto scrollbar-gutter-stable"
      >
        {streamStatus === 'reconnecting' && (
          <div
            role="status"
            aria-live="polite"
            className="fixed bottom-4 left-1/2 z-[9998] flex -translate-x-1/2 items-center gap-1.5 rounded-full border border-warning/30 bg-warning/10 px-2.5 py-1 text-[11px] font-medium text-warning shadow-lg backdrop-blur-md"
          >
            <WifiOff className="h-3 w-3 shrink-0 animate-pulse" />
            与服务连接已断开 · 正在重连
          </div>
        )}
        <Suspense
          fallback={
            <div className="flex items-center justify-center py-24">
              <Loader2 className="h-5 w-5 animate-spin text-muted" />
            </div>
          }
        >
          <Outlet />
        </Suspense>
      </motion.main>
      <ToastContainer />
      <AlertToastContainer />
      <AiAnalysisHost />
      <AiReportBubble />
      <StockAnalysisHost />
      <StockAnalysisBubble />
    </div>
  )
}
