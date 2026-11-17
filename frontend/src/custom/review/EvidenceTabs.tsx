/**
 * B 区 · 证据带 (R791) — 四个 Tab: 主线 / 连板 / 资金 / 情绪。
 *
 * 全部复用后端已有读数(heat / breadth.limit / dragon-tiger / auction-benchmark),
 * 不在这里做二次判定。Tab 选择记到 localStorage —— 只记 Tab, 不记布局(固定版式)。
 *
 * 原首屏「龙虎榜」大卡整体降级为「资金」Tab 的内容; 盘前风向标同样放在这里。
 */
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ChevronRight, Compass, Layers, Trophy } from 'lucide-react'

import {
  api, type AuctionBenchmarkPayload, type OverviewBreadth, type OverviewHeat,
  type OverviewDimensionRankItem,
} from '@/lib/api'
import { cn } from '@/lib/cn'
import { TYPE } from '@/components/ui'
import { fmtPct, priceColorClass } from '@/lib/format'
import { DragonTigerCard } from './DragonTigerPanel'
import { fmtPctAlready, pctClass, scoreColor } from './shared'

type TabKey = 'mainline' | 'ladder' | 'money' | 'emotion'

const TABS: { key: TabKey; label: string }[] = [
  { key: 'mainline', label: '主线' },
  { key: 'ladder', label: '连板' },
  { key: 'money', label: '资金' },
  { key: 'emotion', label: '情绪' },
]

const TAB_STORAGE_KEY = 'review-evidence-tab'

function readTab(): TabKey {
  const v = typeof localStorage === 'undefined' ? null : localStorage.getItem(TAB_STORAGE_KEY)
  return TABS.some(t => t.key === v) ? (v as TabKey) : 'mainline'
}

export interface EvidenceTabsProps {
  breadth?: OverviewBreadth
  concept?: OverviewHeat
  industry?: OverviewHeat
  heatLoading?: boolean
  /** 龙虎榜 / 风向标跟随复盘目标日 */
  dtDate?: string
  onOpenStock: (symbol: string) => void
}

// ── 主线: 领涨 / 领跌榜 ─────────────────────────────────────────────

function RankList({ title, items, onOpenStock }: {
  title: string
  items: OverviewDimensionRankItem[]
  onOpenStock: (symbol: string) => void
}) {
  return (
    <div className="min-w-0 flex-1">
      <div className="mb-1 text-micro text-muted">{title}</div>
      {items.length === 0 ? (
        <div className="rounded-btn border border-dashed border-border py-3 text-center text-micro text-muted">—</div>
      ) : (
        <div className="space-y-0.5">
          {items.map((it, idx) => (
            <div key={`${it.name}-${idx}`} className="flex items-center gap-2 rounded-btn px-1 py-1 text-xs transition-colors hover:bg-elevated/50">
              <span className="w-4 shrink-0 text-center font-mono text-micro text-muted/70">{idx + 1}</span>
              <span className="min-w-0 flex-1 truncate text-foreground" title={it.name}>{it.name}</span>
              {it.leader?.symbol && (
                <button
                  type="button"
                  onClick={() => onOpenStock(it.leader!.symbol!)}
                  className="max-w-24 shrink-0 truncate text-micro text-muted transition-colors hover:text-accent"
                  title={`龙头 ${it.leader.name ?? it.leader.symbol} ${fmtPctAlready(it.leader.change_pct, 2, true)}`}
                >
                  {it.leader.name ?? it.leader.symbol}
                </button>
              )}
              <span className="w-14 shrink-0 text-right font-mono text-micro tabular-nums text-muted/70">{it.count}只</span>
              <span className={cn('w-16 shrink-0 text-right font-mono text-xs font-semibold tabular-nums', pctClass(it.avg_pct))}>
                {fmtPctAlready(it.avg_pct, 2, true)}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function MainlinePanel({ concept, industry, loading, onOpenStock }: {
  concept?: OverviewHeat
  industry?: OverviewHeat
  loading?: boolean
  onOpenStock: (symbol: string) => void
}) {
  if (loading && !concept && !industry) {
    return <div className="h-40 animate-pulse rounded-btn bg-elevated/60" />
  }
  const groups: { label: string; heat?: OverviewHeat }[] = [
    { label: '概念', heat: concept },
    { label: '行业', heat: industry },
  ]
  return (
    <div className="space-y-4">
      {groups.map(g => (
        <div key={g.label}>
          <div className="mb-1.5 flex items-center gap-2">
            <Layers className="h-3 w-3 text-muted" />
            <span className={cn(TYPE.card, 'text-foreground')}>{g.label}</span>
            <span className="text-micro text-muted">按平均涨幅</span>
          </div>
          <div className="flex flex-col gap-3 sm:flex-row">
            <RankList title="领涨 Top5" items={(g.heat?.leading ?? []).slice(0, 5)} onOpenStock={onOpenStock} />
            <RankList title="领跌 Top5" items={(g.heat?.lagging ?? []).slice(0, 5)} onOpenStock={onOpenStock} />
          </div>
        </div>
      ))}
    </div>
  )
}

// ── 连板: 梯队分布 ─────────────────────────────────────────────────

function LadderPanel({ breadth, onOpenStock }: { breadth?: OverviewBreadth; onOpenStock: (symbol: string) => void }) {
  const limit = breadth?.limit
  if (!limit) {
    return <div className="h-32 animate-pulse rounded-btn bg-elevated/60" />
  }
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-x-5 gap-y-1.5 text-xs">
        <span className="text-secondary">最高 <span className="font-mono font-semibold text-foreground">{limit.max_boards} 板</span></span>
        <span className="text-secondary">涨停 <span className="font-mono font-semibold text-bull">{limit.limit_up}</span></span>
        <span className="text-secondary">炸板 <span className="font-mono font-semibold text-secondary">{limit.broken}</span></span>
        <span className="text-secondary">封板率 <span className="font-mono font-semibold text-foreground">{(limit.seal_rate ?? 0).toFixed(0)}%</span></span>
        <span className="text-secondary">跌停 <span className="font-mono font-semibold text-bear">{limit.limit_down}</span></span>
      </div>
      {limit.tiers.length === 0 ? (
        <div className="rounded-btn border border-dashed border-border py-4 text-center text-xs text-muted">今日无连板梯队</div>
      ) : (
        <div className="space-y-1.5">
          {limit.tiers.map(t => (
            <div key={t.boards} className="flex items-start gap-2 rounded-btn bg-elevated/30 px-2 py-1.5">
              <span className="w-12 shrink-0 font-mono text-xs font-semibold text-foreground">{t.boards} 板</span>
              <span className="w-8 shrink-0 font-mono text-micro text-muted">×{t.count}</span>
              <div className="flex min-w-0 flex-wrap gap-1">
                {(t.stocks ?? []).map(s => (
                  <button
                    key={s.symbol}
                    type="button"
                    onClick={() => onOpenStock(s.symbol)}
                    className="rounded-btn border border-border/60 bg-surface/60 px-1.5 py-0.5 text-micro text-foreground transition-colors hover:border-accent/40 hover:text-accent"
                  >
                    {s.name ?? s.symbol}
                  </button>
                ))}
                {(t.stocks?.length ?? 0) < t.count && (
                  <span className="py-0.5 text-micro text-muted">等 {t.count} 只</span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ── 资金: 龙虎榜 + 盘前风向标 ──────────────────────────────────────

const CHASE_RISK_PCT = 5

function AuctionPanel({ date, onOpenStock }: { date?: string; onOpenStock: (symbol: string) => void }) {
  const q = useQuery<AuctionBenchmarkPayload>({
    queryKey: ['auction-benchmark', date ?? 'latest'],
    queryFn: () => api.auctionBenchmark(date),
    staleTime: 5 * 60_000,
    retry: 1,
  })
  const d = q.data

  if (q.isLoading) return <div className="h-16 animate-pulse rounded-btn bg-elevated/60" />
  if (d?.state === 'source_unavailable') {
    return (
      <div className="flex items-center gap-2 rounded-btn border border-dashed border-border px-3 py-2 text-xs text-muted">
        <Compass className="h-3.5 w-3.5" />盘前风向标需要 fuyao 数据源
        <Link to="/settings?tab=data-sources" className="ml-auto inline-flex items-center gap-0.5 text-micro text-accent hover:underline">
          前往配置 <ChevronRight className="h-3 w-3" />
        </Link>
      </div>
    )
  }
  if (!d || d.state === 'no_data') {
    return (
      <div className="flex items-center gap-2 rounded-btn border border-border px-3 py-2 text-xs text-muted">
        <Compass className="h-3.5 w-3.5" />盘前风向标暂不可用
        <button onClick={() => q.refetch()} className="ml-auto text-micro text-accent hover:underline">重试</button>
      </div>
    )
  }

  const items = d.items ?? []
  return (
    <div className="rounded-btn border border-border/60">
      <div className="flex items-center gap-2 border-b border-border/50 px-2.5 py-1.5">
        <Compass className="h-3.5 w-3.5 text-muted" />
        <span className="text-xs font-medium text-foreground">盘前风向标</span>
        <span className="text-micro text-muted">
          {d.trade_date} · {items.length} 只{d.state === 'fallback_prev' ? ' · 显示上一期' : ''}
        </span>
        <span className="ml-auto text-micro text-muted/70">次日无优势 · 仅当日观察</span>
      </div>
      {items.length === 0 ? (
        <p className="px-3 py-2 text-center text-xs text-muted">本期无名单数据</p>
      ) : (
        <div className="grid gap-1 p-1.5 sm:grid-cols-2">
          {items.map(i => (
            <button
              key={i.thscode}
              type="button"
              onClick={() => onOpenStock(i.thscode)}
              className="flex items-center gap-2 rounded-btn px-1.5 py-1 text-left text-xs transition-colors hover:bg-elevated/60"
              title={i.tags?.length ? i.tags.join(' · ') : undefined}
            >
              <span className="min-w-0 flex-1 truncate text-foreground">{i.name ?? i.ticker ?? i.thscode}</span>
              <span className={cn('font-mono text-micro tabular-nums', pctClass(i.auction_pct))}>
                竞价 {fmtPctAlready(i.auction_pct, 2, true)}
              </span>
              <span className={cn('font-mono text-micro tabular-nums', priceColorClass(i.day0_oc ?? null))}>
                当日 {fmtPct(i.day0_oc ?? null)}
              </span>
              {(i.auction_pct ?? 0) >= CHASE_RISK_PCT && (
                <span className="rounded-btn border border-warning/30 bg-warning/10 px-1 text-micro text-warning" title="高开 ≥5%: 60 日回测当日开盘买均值 -1.97%">
                  追高
                </span>
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

function MoneyPanel({ dtDate, onOpenStock }: { dtDate?: string; onOpenStock: (symbol: string) => void }) {
  return (
    <div className="space-y-2">
      <DragonTigerCard date={dtDate} onOpenStock={onOpenStock} />
      <AuctionPanel date={dtDate} onOpenStock={onOpenStock} />
    </div>
  )
}

// ── 情绪: 六维 + 分布 + 量能 ───────────────────────────────────────

function EmotionPanel({ breadth }: { breadth?: OverviewBreadth }) {
  if (!breadth) return <div className="h-32 animate-pulse rounded-btn bg-elevated/60" />
  const radar = breadth.radar ?? []
  const dist = breadth.distribution ?? []
  const trend = breadth.trend
  const act = breadth.activity

  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <div>
        <div className="mb-1.5 text-micro text-muted">六维读数</div>
        <div className="space-y-1">
          {radar.map(r => (
            <div key={r.key} className="flex items-center gap-2">
              <span className="w-16 shrink-0 text-micro text-secondary">{r.label}</span>
              <span className="h-1.5 min-w-0 flex-1 overflow-hidden rounded-full bg-elevated">
                <span
                  className="block h-full rounded-full"
                  style={{ width: `${Math.max(2, Math.min(100, r.value))}%`, backgroundColor: scoreColor(r.value) }}
                />
              </span>
              <span className="w-7 shrink-0 text-right font-mono text-micro tabular-nums text-secondary">{Math.round(r.value)}</span>
            </div>
          ))}
        </div>
      </div>
      <div className="space-y-3">
        <div>
          <div className="mb-1.5 text-micro text-muted">涨跌分布</div>
          <div className="flex gap-0.5">
            {dist.map(d => (
              <span
                key={d.label}
                className="flex min-w-0 flex-col items-center"
                style={{ flexGrow: Math.max(d.count, 1) }}
                title={`${d.label} ${d.count} 只 (${d.pct}%)`}
              >
                <span className={cn('h-2 w-full rounded-btn', d.label.startsWith('-') ? 'bg-bear/50' : 'bg-bull/50')} />
                <span className="mt-0.5 truncate text-micro text-muted">{d.label}</span>
              </span>
            ))}
          </div>
        </div>
        <div className="flex flex-wrap gap-x-4 gap-y-1 text-micro text-secondary">
          <span>MA5 上方 <span className="font-mono text-foreground">{trend.above_ma5_pct.toFixed(0)}%</span></span>
          <span>MA20 上方 <span className="font-mono text-foreground">{trend.above_ma20_pct.toFixed(0)}%</span></span>
          <span>新高 <span className="font-mono text-bull">{trend.new_high}</span></span>
          <span>新低 <span className="font-mono text-bear">{trend.new_low}</span></span>
        </div>
        <div className="flex flex-wrap gap-x-4 gap-y-1 text-micro text-secondary">
          <span>平均换手 <span className="font-mono text-foreground">{act.avg_turnover.toFixed(2)}%</span></span>
          <span>高换手 <span className="font-mono text-foreground">{act.high_turnover}</span></span>
          <span>放量 <span className="font-mono text-foreground">{act.vol_ratio}</span></span>
        </div>
      </div>
    </div>
  )
}

// ── 容器 ──────────────────────────────────────────────────────────

export function EvidenceTabs({ breadth, concept, industry, heatLoading, dtDate, onOpenStock }: EvidenceTabsProps) {
  const [tab, setTab] = useState<TabKey>(readTab)
  const change = (k: TabKey) => {
    setTab(k)
    try { localStorage.setItem(TAB_STORAGE_KEY, k) } catch { /* 隐私模式忽略 */ }
  }

  return (
    <section className="rounded-card border border-border bg-surface/80">
      <div className="flex items-center gap-2 border-b border-border px-3 py-2">
        <div className="flex items-center gap-0.5 rounded-btn bg-base/70 p-0.5">
          {TABS.map(t => (
            <button
              key={t.key}
              type="button"
              onClick={() => change(t.key)}
              className={cn(
                'rounded-btn px-2.5 py-1 text-xs transition-colors',
                tab === t.key ? 'bg-foreground font-medium text-surface' : 'text-secondary hover:text-foreground',
              )}
            >
              {t.label}
            </button>
          ))}
        </div>
        <span className="ml-auto inline-flex items-center gap-1 text-micro text-muted">
          <Trophy className="h-3 w-3" />证据区 · 只放事实读数
        </span>
      </div>
      <div className="px-3 py-3">
        {tab === 'mainline' && (
          <MainlinePanel concept={concept} industry={industry} loading={heatLoading} onOpenStock={onOpenStock} />
        )}
        {tab === 'ladder' && <LadderPanel breadth={breadth} onOpenStock={onOpenStock} />}
        {tab === 'money' && <MoneyPanel dtDate={dtDate} onOpenStock={onOpenStock} />}
        {tab === 'emotion' && <EmotionPanel breadth={breadth} />}
      </div>
    </section>
  )
}
