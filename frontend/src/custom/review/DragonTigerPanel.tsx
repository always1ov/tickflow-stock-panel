/**
 * 龙虎榜卡片 (fuyao 专有) — 资金动向上下文。
 *
 * [R791] 从 Page.tsx 整体搬出: 复盘页改版后, 这张卡不再是首屏第二个位置,
 * 而是证据带「资金」Tab 的内容。数据与降级逻辑一个字节没改
 * (当日未发布回退上一期 / 未配置数据源引导 / 空 thscode 兜底)。
 */
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { motion, AnimatePresence } from 'framer-motion'
import { ChevronDown, ChevronRight, ChevronUp, Trophy } from 'lucide-react'

import { api, type DragonTigerStockItem } from '@/lib/api'
import { cn } from '@/lib/cn'
import { fmtPct, fmtVolume, priceColorClass } from '@/lib/format'
import { boardTag } from '@/components/stock-table/primitives'

// ================================================================
// 龙虎榜卡片 (fuyao 专有) —— 资金动向上下文, 市场摘要条之下
// 视觉对齐 MarketSummaryBar: 8x8 徽章 + rounded-card + surface 底。
// 收起态: 奖杯徽章头部 + 净买/机构 Top3 排名药丸;
// 展开态: 分段式三榜 tab, 股票表净买额带比例条, 游资席位带奖牌。
// 状态: 当日未发布自动显示上一期 (fallback_prev); fuyao 未配置降级提示。
// ================================================================
type _DtTabKey = 'all' | 'org' | 'hot_money'
const _DT_TABS: { key: _DtTabKey; label: string }[] = [
  { key: 'all', label: '全部' },
  { key: 'org', label: '机构' },
  { key: 'hot_money', label: '游资' },
]

function _dtSorted(items: DragonTigerStockItem[], key: 'net_value' | 'org_net_value', asc = false): DragonTigerStockItem[] {
  const s = [...items].sort((a, b) => (b[key] ?? -Infinity) - (a[key] ?? -Infinity))
  return asc ? s.reverse() : s
}

/** 榜单标的代码: 后端已归一非空, 此处兜底旧缓存/异常数据源的 null thscode。 */
function _dtCode(i: DragonTigerStockItem): string {
  const code = i.thscode
  if (typeof code === 'string' && code.trim()) return code
  return i.ticker ?? ''
}

/** 榜单标的展示名: 名称优先, 无名称时退代码/ticker。 */
function _dtLabel(i: DragonTigerStockItem): string {
  return i.name ?? (_dtCode(i) || '—')
}

/** 排名序号色: 前三用暖色系奖牌感, 其余弱化 */
// [R543] 前三原是金 / 银 / 铜三色奖牌(琥珀 / 锌灰 / 橙, 写死的调色板), 收成一种强调: 前三反相, 其余弱化
function _rankCls(idx: number): string {
  if (idx < 3) return 'bg-foreground text-surface'
  return 'bg-elevated text-muted/70'
}

function _DtPill({ item, idx, value, onOpenStock }: {
  item: DragonTigerStockItem
  idx: number
  value: number | null | undefined
  onOpenStock: (s: string) => void
}) {
  const code = _dtCode(item)
  const label = _dtLabel(item)
  return (
    <button
      type="button"
      onClick={() => code && onOpenStock(code)}
      className="group inline-flex items-center gap-1.5 rounded-btn border border-border/60 bg-surface py-0.5 pl-0.5 pr-2.5 transition-ui hover:border-accent/40 hover:bg-elevated/70"
      title={`查看 ${label} · 净买 ${fmtVolume(value ?? null)}`}
    >
      <span className={cn('grid h-[18px] w-[18px] min-w-[18px] place-items-center rounded-full font-mono text-micro font-bold leading-none', _rankCls(idx))}>
        {idx + 1}
      </span>
      <span className="text-xs text-foreground/90 transition-colors group-hover:text-accent">
        {label}
      </span>
      {(() => { const b = boardTag(code); return b && (
        <span className={`inline-flex items-center rounded-btn border px-1 text-micro font-bold leading-tight ${b.color}`}>
          {b.label}
        </span>
      ) })()}
      <span className={cn('font-mono text-micro tabular-nums', priceColorClass(value ?? null))}>
        {fmtVolume(value ?? null)}
      </span>
    </button>
  )
}

function _DtSummaryRow({ label, items, pick, onOpenStock }: {
  label?: string
  items: DragonTigerStockItem[]
  pick: (i: DragonTigerStockItem) => number | null | undefined
  onOpenStock: (s: string) => void
}) {
  if (!items.length) return null
  return (
    <div className="flex min-w-0 flex-wrap items-center gap-1.5">
      {/* 固定宽度标签槽: 无标签行(净卖)也占位, 保证四行药丸左缘对齐 */}
      <span className="flex w-16 shrink-0">
        {label && (
          <span className="rounded-btn bg-base/70 px-2 py-0.5 text-micro font-medium tracking-wide text-muted">
            {label}
          </span>
        )}
      </span>
      {items.map((i, idx) => (
        <_DtPill key={`${_dtCode(i)}-${idx}`} item={i} idx={idx} value={pick(i)} onOpenStock={onOpenStock} />
      ))}
    </div>
  )
}

/** 可排序列 key — 与 DragonTigerStockItem 数值字段对应 */
type _DtSortKey = 'change' | 'net_value' | 'net_rate' | 'org_net_value' | 'buy_value' | 'sell_value'

/** 排序表头: 点击切换列/方向, 箭头指示当前排序 (hover 才显隐未激活箭头) */
function _DtTh({ label, sortKey, sort, onSort, className }: {
  label: string
  sortKey: _DtSortKey
  sort: { key: _DtSortKey; desc: boolean }
  onSort: (k: _DtSortKey) => void
  className?: string
}) {
  const active = sort.key === sortKey
  return (
    <button
      type="button"
      onClick={() => onSort(sortKey)}
      className={cn('inline-flex items-center gap-0.5 transition-colors hover:text-foreground', active && 'text-foreground', className)}
    >
      {label}
      {active ? (
        sort.desc
          ? <ChevronDown className="h-2.5 w-2.5 opacity-80" />
          : <ChevronUp className="h-2.5 w-2.5 opacity-80" />
      ) : (
        <ChevronDown className="h-2.5 w-2.5 opacity-0 transition-opacity group-hover:opacity-40" />
      )}
    </button>
  )
}

function DtStockTable({ items, tab, onOpenStock }: {
  items: DragonTigerStockItem[]
  tab: _DtTabKey
  onOpenStock: (s: string) => void
}) {
  const isOrg = tab === 'org'
  const [sort, setSort] = useState<{ key: _DtSortKey; desc: boolean }>({ key: isOrg ? 'org_net_value' : 'net_value', desc: true })
  const onSort = (k: _DtSortKey) =>
    setSort(s => (s.key === k ? { key: k, desc: !s.desc } : { key: k, desc: true }))
  const sorted = [...items].sort((a, b) => {
    const av = a[sort.key] ?? null
    const bv = b[sort.key] ?? null
    if (av == null && bv == null) return 0
    if (av == null) return 1 // 空值恒垫底, 不随方向翻转
    if (bv == null) return -1
    return (av - bv) * (sort.desc ? -1 : 1)
  })
  const maxAbs = Math.max(1e-12, ...items.map(i => Math.abs(i.net_value ?? 0)))
  return (
    <div className="overflow-hidden rounded-btn border border-border/60">
      {/* 表头 */}
      <div className={cn(
        'group flex items-center gap-2 bg-elevated/50 px-2.5 py-1.5 text-micro font-medium uppercase tracking-wider text-muted/70',
      )}>
        <span className="w-5 shrink-0 text-center">#</span>
        <span className="w-14 shrink-0"><_DtTh label="涨跌幅" sortKey="change" sort={sort} onSort={onSort} /></span>
        <span className="min-w-0 flex-1">股票</span>
        <span className="w-24 shrink-0"><_DtTh label="净买额" sortKey="net_value" sort={sort} onSort={onSort} className="w-full justify-end" /></span>
        <span className="w-14 shrink-0"><_DtTh label="占比" sortKey="net_rate" sort={sort} onSort={onSort} className="w-full justify-end" /></span>
        {isOrg && <span className="w-20 shrink-0"><_DtTh label="机构净买" sortKey="org_net_value" sort={sort} onSort={onSort} className="w-full justify-end" /></span>}
        <span className="w-20 shrink-0"><_DtTh label="买入额" sortKey="buy_value" sort={sort} onSort={onSort} className="w-full justify-end" /></span>
        <span className="w-20 shrink-0"><_DtTh label="卖出额" sortKey="sell_value" sort={sort} onSort={onSort} className="w-full justify-end" /></span>
        <span className="w-11 shrink-0 text-right">榜期</span>
      </div>
      {sorted.map((i, idx) => {
        const barPct = Math.max(2, Math.min(100, (Math.abs(i.net_value ?? 0) / maxAbs) * 100))
        const positive = (i.net_value ?? 0) >= 0
        const code = _dtCode(i)
        const label = _dtLabel(i)
        return (
          <button
            key={`${code}-${i.range_days ?? 1}`}
            type="button"
            onClick={() => code && onOpenStock(code)}
            className="flex w-full items-center gap-2 border-t border-border/30 px-2.5 py-2 text-left text-xs transition-colors hover:bg-accent/[0.05]"
            title={`查看 ${label} 详情`}
          >
            <span className={cn('w-5 shrink-0 text-center font-mono text-micro tabular-nums', idx < 3 ? 'text-warning/90' : 'text-muted/50')}>
              {idx + 1}
            </span>
            <span className={cn('w-14 shrink-0 font-mono tabular-nums', priceColorClass(i.change ?? null))}>
              {fmtPct(i.change ?? null, 1)}
            </span>
            <span className="min-w-0 flex-1">
              <span className="text-foreground">{label}</span>
              <span className="ml-1.5 font-mono text-micro text-muted">{i.ticker ?? code}</span>
              {(() => { const b = boardTag(code); return b && (
                <span className={`ml-1 inline-flex items-center rounded-btn border px-1 text-micro font-bold leading-tight ${b.color}`}>
                  {b.label}
                </span>
              ) })()}
              {i.hot_rank != null && i.hot_rank > 0 && i.hot_rank <= 99 && (
                <span
                  className={cn(
                    'ml-1.5 inline-flex items-center rounded-btn px-1 text-micro font-medium leading-tight',
                    i.hot_rank <= 10
                      ? 'border border-warning/30 bg-warning/10 text-warning'
                      : 'border border-border bg-elevated/50 text-muted/80',
                  )}
                  title={`同花顺人气第 ${i.hot_rank} 名`}
                >
                  人气{i.hot_rank}
                </span>
              )}
            </span>
            {/* 净买额: 比例条 + 数值 (红买绿卖, 长度=绝对值占榜首比例) */}
            <span className="relative w-24 shrink-0">
              <span
                aria-hidden
                className={cn(
                  'absolute inset-y-[3px] right-0 rounded-[3px]',
                  positive ? 'bg-bull/10' : 'bg-bear/10',
                )}
                style={{ width: `${barPct}%` }}
              />
              <span className={cn('relative block text-right font-mono tabular-nums', priceColorClass(i.net_value ?? null))}>
                {fmtVolume(i.net_value ?? null)}
              </span>
            </span>
            <span className="w-14 shrink-0 text-right font-mono tabular-nums text-secondary">
              {i.net_rate == null ? '—' : `${(i.net_rate * 100).toFixed(1)}%`}
            </span>
            {isOrg && (
              <span className={cn('w-20 shrink-0 text-right font-mono tabular-nums', priceColorClass(i.org_net_value ?? null))}>
                {fmtVolume(i.org_net_value ?? null)}
              </span>
            )}
            <span className="w-20 shrink-0 text-right font-mono tabular-nums text-muted">{fmtVolume(i.buy_value ?? null)}</span>
            <span className="w-20 shrink-0 text-right font-mono tabular-nums text-muted">{fmtVolume(i.sell_value ?? null)}</span>
            <span className="w-11 shrink-0 text-right">
              <span className={cn(
                'inline-flex rounded-btn px-1 text-micro leading-tight',
                i.range_days === 3
                  ? 'border border-sky-500/25 bg-sky-500/10 text-sky-400/90'
                  : 'border border-border/60 bg-elevated/50 text-muted/80',
              )}>
                {i.range_days === 3 ? '3日' : '当日'}
              </span>
            </span>
          </button>
        )
      })}
    </div>
  )
}

function _DtSeatList({ seats, onOpenStock }: {
  seats: { name?: string | null; buying?: number | null; rows?: DragonTigerStockItem[] | null }[]
  onOpenStock: (s: string) => void
}) {
  if (!seats.length) {
    return <p className="py-4 text-center text-xs text-muted">本期无游资上榜数据</p>
  }
  return (
    <div className="grid gap-1.5">
      {seats.map((s, idx) => (
        <div
          key={`${s.name}-${idx}`}
          className="flex items-start gap-2.5 rounded-btn border border-border/50 bg-elevated/30 px-2.5 py-2 transition-colors hover:border-accent/25"
        >
          <span className={cn('grid h-5 w-5 shrink-0 place-items-center rounded-full font-mono text-micro font-bold leading-none', _rankCls(idx))}>
            {idx + 1}
          </span>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-baseline gap-x-2.5 gap-y-0.5">
              <span className="text-xs font-medium text-foreground" title={s.name ?? ''}>{s.name ?? '—'}</span>
              <span className={cn('font-mono text-micro tabular-nums', priceColorClass(s.buying ?? null))}>
                {fmtVolume(s.buying ?? null)}
              </span>
            </div>
            <div className="mt-1 flex min-w-0 flex-wrap items-center gap-1.5">
              {(s.rows ?? []).map((r, ri) => {
                const code = _dtCode(r)
                return (
                <button
                  key={`${s.name}-${code}-${ri}`}
                  type="button"
                  onClick={() => code && onOpenStock(code)}
                  className="inline-flex items-baseline gap-1.5 rounded-btn border border-border/60 bg-surface/60 px-2 py-0.5 text-micro transition-ui hover:border-accent/40 hover:text-accent"
                  title={`查看 ${_dtLabel(r)} 详情`}
                >
                  <span>{_dtLabel(r)}</span>
                  {(() => { const b = boardTag(code); return b && (
                    <span className={`inline-flex items-center self-center rounded-btn border px-1 text-micro font-bold leading-tight ${b.color}`}>
                      {b.label}
                    </span>
                  ) })()}
                  <span className={cn('font-mono text-micro tabular-nums', priceColorClass(r.hot_money_item_net_value ?? r.net_value ?? null))}>
                    {fmtVolume(r.hot_money_item_net_value ?? r.net_value ?? null)}
                  </span>
                </button>
                )
              })}
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}

/** 追高风险阈值: 60日回测高开≥5%子集当日开盘买 -1.97% (温和高开才是名单 alpha 来源) */

export function DragonTigerCard({ date, onOpenStock }: {
  date?: string
  onOpenStock: (symbol: string) => void
}) {
  const [expanded, setExpanded] = useState(false)
  const [tab, setTab] = useState<_DtTabKey>('all')
  const q = useQuery({
    queryKey: ['dragon-tiger', date ?? 'latest'],
    queryFn: () => api.dragonTiger(date),
    staleTime: 5 * 60_000,
    retry: 1,
  })
  const d = q.data

  if (q.isLoading) {
    return (
      <div className="flex items-center gap-3 rounded-card border border-border bg-surface/80 px-4 py-3">
        <span className="grid h-8 w-8 shrink-0 animate-pulse place-items-center rounded-btn bg-elevated">
          <Trophy className="h-4 w-4 text-muted/50" />
        </span>
        <div className="flex items-center gap-2">
          <span className="h-3 w-14 animate-pulse rounded-full bg-elevated/80" />
          <span className="h-3 w-24 animate-pulse rounded-full bg-elevated/60" />
          <span className="h-3 w-20 animate-pulse rounded-full bg-elevated/40" />
        </div>
      </div>
    )
  }

  // fuyao 未配置: 显式降级提示 (不用死区块, 给配置入口)
  if (d?.state === 'source_unavailable') {
    return (
      <div className="flex items-center gap-3 rounded-card border border-dashed border-border bg-surface/50 px-4 py-3">
        <span className="grid h-8 w-8 shrink-0 place-items-center rounded-btn bg-elevated/60">
          <Trophy className="h-4 w-4 text-muted/50" />
        </span>
        <span className="text-xs text-muted">龙虎榜需要 fuyao 数据源 (同花顺特色数据)</span>
        <Link to="/settings?tab=data-sources" className="ml-auto inline-flex items-center gap-0.5 text-micro text-accent hover:underline">
          前往配置 <ChevronRight className="h-3 w-3" />
        </Link>
      </div>
    )
  }

  // 拉取失败: 轻提示 + 重试 (不占复盘页视觉重量)
  if (!d || d.state === 'no_data') {
    return (
      <div className="flex items-center gap-3 rounded-card border border-border bg-surface/50 px-4 py-3">
        <span className="grid h-8 w-8 shrink-0 place-items-center rounded-btn bg-elevated/60">
          <Trophy className="h-4 w-4 text-muted/50" />
        </span>
        <span className="text-xs text-muted">龙虎榜暂不可用{d?.message ? ` (${d.message.slice(0, 40)})` : ''}</span>
        <button onClick={() => q.refetch()} className="ml-auto text-micro text-accent hover:underline">重试</button>
      </div>
    )
  }

  const allItems = d.all?.stock_items ?? []
  const orgItems = d.org?.stock_items ?? []
  const seats = d.hot_money?.hot_money_items ?? []
  const topBuy = _dtSorted(allItems.filter(i => (i.net_value ?? 0) > 0), 'net_value').slice(0, 5)
  const topOrg = _dtSorted(orgItems, 'org_net_value').slice(0, 5)
  const topSell = _dtSorted(allItems.filter(i => (i.net_value ?? 0) < 0), 'net_value', true).slice(0, 5)
  const botOrg = _dtSorted(orgItems.filter(i => (i.org_net_value ?? 0) < 0), 'org_net_value', true).slice(0, 5)
  const isFallback = d.state === 'fallback_prev'

  return (
    <div className="rounded-card border border-border bg-surface/80">
      {/* 头部: 奖杯徽章 + 概要, 常驻可点击展开 */}
      <button
        type="button"
        onClick={() => setExpanded(v => !v)}
        className="group flex w-full items-center gap-3 px-4 py-3 text-left"
      >
        <span className="grid h-8 w-8 shrink-0 place-items-center rounded-btn bg-warning/15 text-warning ring-1 ring-warning/20">
          <Trophy className={cn('h-4 w-4 transition-transform group-hover:scale-110', expanded && 'scale-110')} />
        </span>
        <span className="leading-tight">
          <span className="flex items-center gap-2">
            <span className="text-xs font-semibold text-foreground">龙虎榜</span>
            {isFallback && (
              <span
                className="rounded-btn border border-warning/30 bg-warning/10 px-1.5 py-px text-micro leading-tight text-warning"
                title="当日榜单未发布(约17:00后), 已自动显示上一期"
              >
                当日未发布 · 显示上一期
              </span>
            )}
          </span>
          <span className="mt-0.5 block text-micro text-muted">
            {/* [R132] 交易日的龙虎榜不可能是 0 只 —— 真出现 0 就是没发布/没拿到,
                不能拿「0 只上榜」糊过去(那和"今天确实没人上榜"分不出来)。
                后端现在会把空榜按未发布处理并回退上一期, 这里是最后一道兜底文案。 */}
            {d.trade_date} · {allItems.length > 0
              ? `${d.all?.stock_count ?? allItems.length} 只上榜`
              : '榜单尚未发布(通常收盘后才出)'} · 点击{expanded ? '收起' : '查看三榜明细'}
          </span>
        </span>
        <span className="ml-auto flex items-center gap-1.5">
          <ChevronDown className={cn('h-4 w-4 text-muted transition-transform duration-expand group-hover:text-secondary', expanded && 'rotate-180')} />
        </span>
      </button>

      {/* 收起态: 排名药丸摘要 */}
      {!expanded && (
        <div className="flex flex-col gap-1.5 px-4 pb-3">
          <_DtSummaryRow label="净买 Top5" items={topBuy} pick={i => i.net_value} onOpenStock={onOpenStock} />
          <_DtSummaryRow items={topSell} pick={i => i.net_value} onOpenStock={onOpenStock} />
          <_DtSummaryRow label="机构 Top5" items={topOrg} pick={i => i.org_net_value} onOpenStock={onOpenStock} />
          <_DtSummaryRow items={botOrg} pick={i => i.org_net_value} onOpenStock={onOpenStock} />
        </div>
      )}

      {/* 展开态: 分段式 tab + 三榜内容 */}
      <AnimatePresence initial={false}>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.18, ease: 'easeOut' }}
            className="overflow-hidden"
          >
            <div className="border-t border-border/60 px-4 py-3">
              {/* 分段式 tab */}
              <div className="mb-2.5 inline-flex items-center gap-0.5 rounded-btn border border-border/50 bg-base/70 p-0.5">
                {_DT_TABS.map(t => (
                  <button
                    key={t.key}
                    type="button"
                    onClick={() => setTab(t.key)}
                    className={cn(
                      'rounded-btn px-3 py-1 text-xs transition-ui',
                      tab === t.key
                        ? 'bg-foreground font-medium text-surface shadow-sm'
                        : 'text-secondary hover:text-foreground',
                    )}
                  >
                    {t.label}
                  </button>
                ))}
              </div>

              {tab === 'hot_money' ? (
                <_DtSeatList seats={seats} onOpenStock={onOpenStock} />
              ) : (
                <DtStockTable
                  key={tab}
                  items={_dtSorted(tab === 'org' ? orgItems : allItems, tab === 'org' ? 'org_net_value' : 'net_value')}
                  tab={tab}
                  onOpenStock={onOpenStock}
                />
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
