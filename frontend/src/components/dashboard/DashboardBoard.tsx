/**
 * 市场看板固定版式 (R790) — 取代原 12 列可拖拽网格。
 *
 * 结构: 状态带 (指数 + 市场阶段 + 新鲜度) → 左列 (热度榜 / 盘中轮动 / 广度与
 * 赚钱效应 / 榜单 Tab) + 右列 (涨停梯队 / 监控中心)。桌面双列, 移动单列。
 *
 * 数据由 Dashboard 页按区块并行取回后切片传入; 每个区块独立骨架与降级,
 * 互不阻塞。纯展示, 不自行拉取 overview 数据 (监控中心仍自带告警查询)。
 */
import { useMemo, useState, type ReactNode } from 'react'
import { useQueries } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { Activity, ArrowUpRight, BellRing, ChevronDown, Flame, Gauge, Sparkles } from 'lucide-react'
import {
  api, type AlertEvent, type IndexQuote, type OverviewBreadth, type OverviewCore,
  type OverviewHeat, type OverviewHeatKind, type OverviewRankKind, type OverviewRanks,
} from '@/lib/api'
import type { DimensionMembersTarget } from '@/components/DimensionMembersDialog'
import type { NavItem } from '@/lib/listNav'
import { SealedBadge } from '@/components/SealedBadge'
import { SectorRotationCard } from '@/components/SectorRotationCard'
import { cn } from '@/lib/cn'
import { TYPE } from '@/components/ui'
import { fmtBigNum } from '@/lib/format'
import {
  SectionTitle, MiniMetric, KpiCell, fmtPrice, fmtStockPct, pctClass,
} from './shared'
import { EmotionScoreConfigDialog } from './EmotionScoreConfigDialog'
import {
  IndexTicker, BreadthBar, DistributionBars, EmotionRadar, LadderMini, StockList,
  RankColumn, MonitorWidget, stockListNav, rankNav,
} from './widgets'

export interface DashboardBoardProps {
  core?: OverviewCore
  breadth?: OverviewBreadth
  ranks?: OverviewRanks
  heat?: OverviewHeat
  heatKind: OverviewHeatKind
  rankKind: OverviewRankKind
  onHeatKindChange: (kind: OverviewHeatKind) => void
  onRankKindChange: (kind: OverviewRankKind) => void
  /** 五档能力: 决定涨停封板徽标是否降级 */
  hasDepth: boolean
  /** 盘中: 监控中心默认展开, 新鲜度标「实时」 */
  intraday: boolean
  /** 已选历史日期: 所有区块标「历史快照」 */
  historical: boolean
  /** 市场阶段 (盘中取实时阶段, 收盘取定稿阶段) */
  phaseLabel?: string
  phaseColor?: string
  phaseIntraday?: boolean
  activeSymbol: (source: string) => string | undefined
  openStock: (source: string, symbol: string, name?: string, navList?: NavItem[]) => void
  openDimension: (target: DimensionMembersTarget) => void
  openAlert: (event: AlertEvent, navList?: NavItem[]) => void
  /** 分区查询失败: 该区块显示「—」与重试, 其余区块不受影响 */
  errors?: Partial<Record<'core' | 'breadth' | 'ranks' | 'heat', boolean>>
  onRetry?: (section: 'core' | 'breadth' | 'ranks' | 'heat') => void
}

const RANK_OPTIONS: readonly { value: OverviewRankKind; label: string }[] = [
  { value: 'gain', label: '涨幅' },
  { value: 'loss', label: '跌幅' },
  { value: 'amount', label: '成交额' },
  { value: 'active', label: '换手' },
]

const HEAT_OPTIONS: readonly { value: OverviewHeatKind; label: string }[] = [
  { value: 'concept', label: '概念' },
  { value: 'industry', label: '行业' },
]

const RANK_LIMIT = 10

function Section({ children, className }: { children: ReactNode; className?: string }) {
  return <section className={cn('rounded-card border border-border bg-surface p-2', className)}>{children}</section>
}

function SectionHead({ icon: Icon, title, hint, right }: {
  icon: typeof Flame
  title: string
  hint?: string
  right?: ReactNode
}) {
  return (
    <div className="mb-1.5 flex items-center justify-between gap-2">
      <div className="flex min-w-0 items-center gap-1.5">
        <Icon className="h-3.5 w-3.5 shrink-0 text-muted" />
        <h2 className={cn(TYPE.card, 'truncate')}>{title}</h2>
        {hint && <span className="truncate text-micro text-muted">{hint}</span>}
      </div>
      <div className="flex shrink-0 items-center gap-1.5">{right}</div>
    </div>
  )
}

/** 数据新鲜度: 数据时间 + 实时/收盘快照/历史快照/日更。 */
function FreshnessTag({ asOf, state }: { asOf?: string | null; state: string }) {
  const live = state === '实时'
  return (
    <span className="inline-flex items-center gap-1 font-mono text-micro text-muted" title="数据时间与口径">
      {live && <span className="h-1.5 w-1.5 rounded-full bg-bull" />}
      {asOf ? `${asOf} · ` : ''}{state}
    </span>
  )
}

function Tabs({ value, options, onChange }: {
  value: string
  options: readonly { value: string; label: string }[]
  onChange: (value: string) => void
}) {
  return (
    <div className="inline-flex items-center gap-0.5 rounded-btn border border-border bg-elevated/50 p-0.5">
      {options.map(opt => (
        <button
          key={opt.value}
          onClick={() => onChange(opt.value)}
          className={cn(
            'rounded-btn px-1.5 py-0.5 text-micro transition-colors',
            value === opt.value ? 'bg-accent/15 text-accent' : 'text-muted hover:text-foreground',
          )}
        >{opt.label}</button>
      ))}
    </div>
  )
}

function Skeleton({ className = 'h-16' }: { className?: string }) {
  return <div className={cn('animate-pulse rounded-btn bg-elevated/60', className)} />
}

function Empty({ children }: { children: ReactNode }) {
  return <div className="rounded-btn border border-dashed border-border py-4 text-center text-xs text-muted">{children}</div>
}

/** 分区降级: 请求失败时显示占位与重试, 不阻塞其它区块。 */
function SectionFallback({ error, onRetry, className = 'h-32' }: {
  error?: boolean
  onRetry?: () => void
  className?: string
}) {
  if (!error) return <Skeleton className={className} />
  return (
    <div className={cn('flex flex-col items-center justify-center gap-1 rounded-btn border border-dashed border-border text-xs text-muted', className)}>
      <span>—</span>
      {onRetry && <button onClick={onRetry} className="text-accent hover:underline">重试</button>}
    </div>
  )
}

function PhaseBadge({ label, color, intraday }: { label: string; color: string; intraday: boolean }) {
  return (
    <span
      className="inline-flex items-center gap-1 rounded-btn border px-1.5 py-0.5 text-micro font-medium"
      style={{ borderColor: `${color}55`, backgroundColor: `${color}14`, color }}
      title={intraday ? '盘中实时阶段' : '收盘定稿阶段'}
    >
      <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: color }} />
      {label}{intraday ? ' · 盘中' : ''}
    </span>
  )
}

function StatusBand({ props }: { props: DashboardBoardProps }) {
  const { core, intraday, historical, phaseLabel, phaseColor, phaseIntraday } = props
  const quoteRunning = !!core?.quote_status?.running
  const state = historical ? '历史快照' : intraday && quoteRunning ? '实时' : '收盘快照'
  const indices: IndexQuote[] = core?.indices ?? []
  return (
    <Section>
      <SectionHead
        icon={Gauge}
        title="市场状态"
        hint={`情绪 ${core?.emotion?.label ?? '—'} ${core?.emotion?.score ?? '—'}`}
        right={
          <>
            {phaseLabel && phaseColor && (
              <PhaseBadge label={phaseLabel} color={phaseColor} intraday={!!phaseIntraday} />
            )}
            <FreshnessTag asOf={core?.as_of} state={state} />
          </>
        }
      />
      {core ? (
        <div className="grid grid-cols-2 gap-1 md:grid-cols-4">
          {indices.map(item => <IndexTicker key={item.symbol} item={item} />)}
        </div>
      ) : <Skeleton className="h-12" />}
    </Section>
  )
}

/** 涨跌分布 + 广度条 + 均/中位涨跌 */
function BreadthPanel({ data }: { data: OverviewBreadth }) {
  const b = data.breadth
  return (
    <div className="space-y-1.5">
      <SectionTitle icon={Activity} title="涨跌分布" hint={`上涨率 ${b.up_pct.toFixed(1)}%`} />
      <DistributionBars rows={data.distribution} />
      <BreadthBar data={b} />
      <div className="grid grid-cols-3 gap-1.5">
        <MiniMetric label="平均涨幅" value={fmtStockPct(b.avg_pct ?? 0)} cls={pctClass(b.avg_pct ?? 0)} />
        <MiniMetric label="中位涨幅" value={fmtStockPct(b.median_pct ?? 0)} cls={pctClass(b.median_pct ?? 0)} />
        <MiniMetric label="强势/弱势" value={`${b.strong_up ?? 0}/${b.strong_down ?? 0}`} cls="text-foreground" />
        <MiniMetric label="成交额" value={fmtBigNum(data.amount.total)} cls="text-accent" />
        <MiniMetric label="平均成交额" value={fmtBigNum(data.amount.avg)} cls="text-foreground" />
        <MiniMetric label="站上MA20" value={`${data.trend.above_ma20_pct.toFixed(0)}%`} cls="text-accent" />
      </div>
    </div>
  )
}

function KpiStrip({ props }: { props: DashboardBoardProps }) {
  const { breadth, hasDepth } = props
  if (!breadth) return <Skeleton className="h-12" />
  const { breadth: b, limit, amount, activity } = breadth
  const sealedReady = !!limit.sealed_ready
  const isSealedDegrade = !hasDepth || !sealedReady
  const topBoards = limit.tiers.find(t => t.boards === limit.max_boards)
  const topNames = topBoards?.stocks ?? []
  return (
    <div className="grid grid-cols-2 gap-1 sm:grid-cols-3 xl:grid-cols-6">
      <KpiCell
        label="个股涨 / 平 / 跌"
        value={<><span className="text-bull">{b.up}</span><span className="text-muted">/</span><span className="text-muted">{b.flat}</span><span className="text-muted">/</span><span className="text-bear">{b.down}</span></>}
        sub={`上涨率 ${b.up_pct.toFixed(1)}%`}
      />
      <KpiCell
        label="强势 / 弱势"
        value={<><span className="text-bull">{b.strong_up ?? 0}</span><span className="text-muted">/</span><span className="text-bear">{b.strong_down ?? 0}</span></>}
        sub="涨跌 ≥3%"
      />
      <KpiCell
        label={<span className="inline-flex items-center gap-1">涨停 / 跌停<SealedBadge degraded={isSealedDegrade} hasDepth={hasDepth} isHistorical={false} sealedReady={sealedReady} sealedCountsUp={{ real: limit.limit_up, fake: limit.fake_up ?? 0, pending: 0 }} sealedCountsDown={{ real: limit.limit_down, fake: limit.fake_down ?? 0, pending: 0 }} rawUp={limit.limit_up + (limit.fake_up ?? 0)} rawDown={limit.limit_down + (limit.fake_down ?? 0)} invalidateKeys={['overview-breadth', 'limit-ladder']} /></span>}
        value={<><span className="text-bull">{limit.limit_up}</span><span className="text-muted">/</span><span className="text-bear">{limit.limit_down}</span></>}
        sub={`封板率 ${(limit.seal_rate ?? 0).toFixed(0)}%`}
      />
      <KpiCell
        label="最高连板"
        value={`${limit.max_boards || 0}板`}
        sub={topNames.length > 0 && topNames.length <= 3
          ? topNames.map(s => s.name || s.symbol).join(' · ')
          : `梯队 ${limit.tiers.length}`}
        tone="accent"
      />
      <KpiCell label="成交额" value={fmtBigNum(amount.total)} sub={`均额 ${fmtBigNum(amount.avg)}`} />
      <KpiCell
        label="换手 / 量比"
        value={`${fmtPrice(activity.avg_turnover, 1)}% / ${fmtPrice(activity.vol_ratio, 2)}`}
        sub={`高换手 ${activity.high_turnover} · 放量占比 ${fmtPrice(activity.high_vol_ratio, 1)}%`}
        tone="accent"
      />
    </div>
  )
}

function EmotionBlock({ props }: { props: DashboardBoardProps }) {
  const [configOpen, setConfigOpen] = useState(false)
  const score = props.core?.emotion?.score ?? 50
  const radar = props.breadth?.radar
  if (!radar) return <Skeleton className="h-32" />
  return (
    <>
      <SectionTitle
        icon={Sparkles}
        title="情绪雷达"
        hint={`情绪评分 ${score}`}
        onConfig={() => setConfigOpen(true)}
        configTitle="配置情绪评分的计算方式"
      />
      <EmotionRadar radar={radar} score={score} />
      {configOpen && <EmotionScoreConfigDialog onClose={() => setConfigOpen(false)} />}
    </>
  )
}

/** 领涨股近 20 日收盘迷你折线 (复用日K查询, 10 分钟缓存) */
function Sparkline({ values }: { values: number[] }) {
  if (values.length < 2) return null
  const w = 44
  const h = 14
  const min = Math.min(...values)
  const max = Math.max(...values)
  const span = max - min || 1
  const points = values.map((v, i) =>
    `${(i / (values.length - 1)) * w},${h - 1 - ((v - min) / span) * (h - 2)}`,
  ).join(' ')
  const up = values[values.length - 1] >= values[0]
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} aria-hidden className="overflow-visible">
      <polyline points={points} fill="none" strokeWidth={1.2} className={up ? 'stroke-bull' : 'stroke-bear'} />
    </svg>
  )
}

function HeatSection({ props }: { props: DashboardBoardProps }) {
  const { heat, heatKind, onHeatKindChange, openStock, openDimension, activeSymbol, errors, onRetry } = props
  const leading = heat?.leading ?? []
  const symbols = useMemo(
    () => leading.slice(0, 5).map(r => r.leader?.symbol).filter((s): s is string => !!s),
    [leading],
  )
  const sparkQueries = useQueries({
    queries: symbols.map(symbol => ({
      queryKey: ['dashboard-heat-spark', symbol] as const,
      queryFn: () => api.klineDaily(symbol, 20),
      staleTime: 600_000,
      retry: false,
    })),
  })
  const sparkBySymbol = useMemo(() => {
    const map = new Map<string, number[]>()
    symbols.forEach((symbol, i) => {
      const rows = sparkQueries[i]?.data?.rows
      if (rows && rows.length > 1) map.set(symbol, rows.slice(-20).map(r => r.close))
    })
    return map
  }, [symbols, sparkQueries])

  const configUrl = heatKind === 'concept' ? '/concept-analysis' : '/industry-analysis'
  return (
    <Section>
      <SectionHead
        icon={Flame}
        title="热度榜"
        hint={heatKind === 'concept' ? '概念领涨 / 领跌' : '行业领涨 / 领跌'}
        right={
          <>
            <Tabs
              value={heatKind}
              options={HEAT_OPTIONS}
              onChange={v => onHeatKindChange(v as OverviewHeatKind)}
            />
            <FreshnessTag asOf={heat?.as_of} state="日更" />
          </>
        }
      />
      {!heat ? <SectionFallback error={errors?.heat} onRetry={() => onRetry?.('heat')} className="h-40" /> : (
        leading.length === 0 && (heat.lagging?.length ?? 0) === 0 ? (
          <Empty>
            暂无{heatKind === 'concept' ? '概念' : '行业'}热度数据，
            <Link to={configUrl} className="text-accent hover:underline">去配置扩展数据</Link>
          </Empty>
        ) : (
          <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
            <RankColumn
              title="领涨"
              tone="bull"
              rows={leading}
              onStockClick={(symbol, name) => openStock(heatKind, symbol, name, rankNav(heat))}
              onDimensionClick={openDimension}
              activeSymbol={activeSymbol(heatKind)}
              renderTrailing={row => {
                const symbol = row.leader?.symbol
                const values = symbol ? sparkBySymbol.get(symbol) : undefined
                return values ? <Sparkline values={values} /> : null
              }}
            />
            <RankColumn
              title="领跌"
              tone="bear"
              rows={heat.lagging ?? []}
              onStockClick={(symbol, name) => openStock(heatKind, symbol, name, rankNav(heat))}
              onDimensionClick={openDimension}
              activeSymbol={activeSymbol(heatKind)}
            />
          </div>
        )
      )}
    </Section>
  )
}

function RotationSection({ heatKind, onHeatKindChange }: {
  heatKind: OverviewHeatKind
  onHeatKindChange: (kind: OverviewHeatKind) => void
}) {
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between gap-2">
        <Tabs value={heatKind} options={HEAT_OPTIONS} onChange={v => onHeatKindChange(v as OverviewHeatKind)} />
        <span className="text-micro text-muted">{heatKind === 'concept' ? '概念切换 · 盘中轮动' : '行业切换 · 盘中轮动'}</span>
      </div>
      <SectorRotationCard kind={heatKind} />
    </div>
  )
}

function EmotionSection({ props }: { props: DashboardBoardProps }) {
  const { breadth, historical, errors, onRetry } = props
  return (
    <Section>
      <SectionHead
        icon={Activity}
        title="广度与赚钱效应"
        right={<FreshnessTag asOf={breadth?.as_of} state={historical ? '历史快照' : '快照'} />}
      />
      {!breadth && errors?.breadth ? (
        <SectionFallback error onRetry={() => onRetry?.('breadth')} className="h-40" />
      ) : (
        <div className="space-y-2">
          <KpiStrip props={props} />
          <div className="grid gap-2 md:grid-cols-2">
            {breadth ? <BreadthPanel data={breadth} /> : <Skeleton className="h-32" />}
            <EmotionBlock props={props} />
          </div>
        </div>
      )}
    </Section>
  )
}

function RanksSection({ props }: { props: DashboardBoardProps }) {
  const { ranks, rankKind, onRankKindChange, openStock, activeSymbol, historical, errors, onRetry } = props
  const rows = ranks?.rows ?? []
  const title = RANK_OPTIONS.find(o => o.value === rankKind)?.label ?? '榜单'
  return (
    <Section>
      <SectionHead
        icon={ArrowUpRight}
        title={`${title}榜`}
        hint={`前 ${RANK_LIMIT} 名`}
        right={
          <>
            <Tabs
              value={rankKind}
              options={RANK_OPTIONS}
              onChange={v => onRankKindChange(v as OverviewRankKind)}
            />
            <FreshnessTag asOf={ranks?.as_of} state={historical ? '历史快照' : '快照'} />
          </>
        }
      />
      {!ranks ? <SectionFallback error={errors?.ranks} onRetry={() => onRetry?.('ranks')} className="h-56" /> : (
        <StockList
          title={title}
          rows={rows}
          mode={rankKind}
          limit={RANK_LIMIT}
          embedded
          onStockClick={(symbol, name) => openStock(rankKind, symbol, name, stockListNav(rows, RANK_LIMIT))}
          activeSymbol={activeSymbol(rankKind)}
        />
      )}
    </Section>
  )
}

function LadderSection({ props }: { props: DashboardBoardProps }) {
  const { breadth, historical, errors, onRetry } = props
  return (
    <Section>
      <SectionHead
        icon={Flame}
        title="涨停梯队"
        right={<FreshnessTag asOf={breadth?.as_of} state={historical ? '历史快照' : '快照'} />}
      />
      {breadth
        ? <LadderMini limit={breadth.limit} />
        : <SectionFallback error={errors?.breadth} onRetry={() => onRetry?.('breadth')} className="h-40" />}
    </Section>
  )
}

function MonitorSection({ props }: { props: DashboardBoardProps }) {
  const { intraday, openAlert, activeSymbol } = props
  const [expanded, setExpanded] = useState(intraday)
  const collapsed = !intraday && !expanded
  return (
    <Section>
      <SectionHead
        icon={BellRing}
        title="监控中心"
        right={
          <>
            <FreshnessTag state={intraday ? '实时' : '收盘快照'} />
            <Link to="/monitor" className="inline-flex items-center gap-0.5 text-micro text-muted hover:text-accent">
              全部 <ArrowUpRight className="h-3 w-3" />
            </Link>
          </>
        }
      />
      {collapsed ? (
        <button
          onClick={() => setExpanded(true)}
          className="flex w-full items-center justify-center gap-1 rounded-btn border border-dashed border-border py-2 text-xs text-muted hover:border-accent/40 hover:text-accent"
        >
          收盘后已折叠 <ChevronDown className="h-3 w-3" /> 展开
        </button>
      ) : (
        <>
          <MonitorWidget onStockClick={openAlert} activeSymbol={activeSymbol('alert')} />
          {!intraday && (
            <button
              onClick={() => setExpanded(false)}
              className="mt-1 flex w-full items-center justify-center gap-1 rounded-btn py-1 text-micro text-muted hover:text-accent"
            >
              收起 <ChevronDown className="h-3 w-3 rotate-180" />
            </button>
          )}
        </>
      )}
    </Section>
  )
}

export function DashboardBoard(props: DashboardBoardProps) {
  return (
    <div className="space-y-2">
      <StatusBand props={props} />
      <div className="grid grid-cols-1 gap-2 lg:grid-cols-12">
        <div className="space-y-2 lg:col-span-8">
          <HeatSection props={props} />
          <RotationSection heatKind={props.heatKind} onHeatKindChange={props.onHeatKindChange} />
          <EmotionSection props={props} />
          <RanksSection props={props} />
        </div>
        <div className="space-y-2 lg:col-span-4">
          <LadderSection props={props} />
          <MonitorSection props={props} />
        </div>
      </div>
    </div>
  )
}
