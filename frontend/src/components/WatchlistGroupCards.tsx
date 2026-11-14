import React, { useCallback, useMemo, useState } from 'react'
import { ChevronDown, ChevronRight, Crown } from 'lucide-react'
import type { WatchlistGroup, WatchlistGroupLeader } from '@/lib/api'
import { fmtAssetPrice, fmtPct, priceColorClass } from '@/lib/format'
import { cn } from '@/lib/cn'
import {
  rowPct,
  groupPctColor,
  groupMetricTitle,
  groupMetricValue,
  sortGroupKeys,
  orderGroupRows,
  defaultLeaderLabel,
  GROUP_LEADER_MAX,
  GROUP_METRICS,
  type GroupPctMap,
  type GroupPctInfo,
  type GroupStatsConfig,
  type GroupStatsConfigPatch,
  type GroupMetric,
} from '@/lib/watchlistGroupStats'
import {
  resolveWatchlistGroupColor,
  type WatchlistGroupColorOption,
} from '@/lib/watchlist-group-colors'
import { boardTag } from '@/components/stock-table/primitives'
import { GroupStatsSettings } from '@/components/GroupStatsSettings'

/**
 * 自选「分组卡片」视图 — 每个分组一张卡, 组内按涨跌幅降序排列,
 * 默认展示前 N 名 (N 在设置弹层可调), 可展开查看全部。卡片自身顺序、
 * 头部数值与显示条数跟随「指标 + 排序」配置 (与分组统计条共享,
 * 由自选页统一持有并持久化)。数据全部来自自选页既有查询
 * (enriched 行 + 分组归属), 不产生额外请求。
 *
 * [R631] 分组代表(龙头/大哥): 每组最多 3 位, 成员行悬停皇冠可设置;
 * 已设代表置顶、行内带标签徽标, 卡片头部另有一行摘要。
 */

interface GroupCardData {
  /** 'ungrouped' 或分组 id */
  key: string
  name: string
  color: WatchlistGroupColorOption | null
  /** 组内成员 (已按涨跌幅降序, 代表置顶) */
  rows: any[]
  /** [R631] 分组代表, 顺序即主次 */
  leaders: WatchlistGroupLeader[]
  /** [R631] 分组 id; null = 未分组, 不提供代表功能 */
  groupId: string | null
}

/** 代表标签快捷选项 (也可沿用后端默认标签) */
const LEADER_LABEL_PRESETS = ['龙头', '大哥', '中军', '先锋']

const GroupCard = React.memo(function GroupCard({
  data,
  pctInfo,
  metric,
  topN,
  showColorBar,
  showRank,
  expanded,
  onToggle,
  onPreview,
  onOpen,
  onSetLeaders,
}: {
  data: GroupCardData
  pctInfo?: GroupPctInfo
  metric: GroupMetric
  /** 默认展示的成员条数 (来自持久化配置) */
  topN: number
  /** 头部是否显示分组颜色底条 (来自持久化配置) */
  showColorBar: boolean
  /** 成员行是否显示序号 (来自持久化配置) */
  showRank: boolean
  expanded: boolean
  onToggle: (key: string) => void
  onPreview: (symbol: string, name: string) => void
  onOpen: (key: string) => void
  /** [R631] 设定分组代表 (顺序即主次, 最多 3 位) */
  onSetLeaders: (groupId: string, leaders: WatchlistGroupLeader[]) => void
}) {
  const [editingLeader, setEditingLeader] = useState<string | null>(null)
  const visible = expanded ? data.rows : data.rows.slice(0, topN)
  const hasMore = data.rows.length > topN
  const color = data.color
  // 头部数值跟随所选指标; 上涨占比以 0.5 为强弱轴染色
  const v = groupMetricValue(pctInfo, metric)
  const signed = metric === 'up_ratio' ? (v == null ? null : v - 0.5) : v
  const valueLabel = v == null
    ? '—'
    : metric === 'up_ratio'
      ? `${(v * 100).toFixed(0)}%`
      : fmtPct(v)

  const leaders = data.leaders
  const rowBySymbol = useMemo(
    () => new Map<string, any>(data.rows.map((row: any) => [row.symbol, row])),
    [data.rows],
  )
  const leaderLabelBySymbol = useMemo(
    () => new Map(leaders.map(leader => [leader.symbol, leader.label])),
    [leaders],
  )
  const leadersFull = leaders.length >= GROUP_LEADER_MAX

  const applyLeaders = useCallback((next: WatchlistGroupLeader[]) => {
    if (!data.groupId) return
    onSetLeaders(data.groupId, next)
  }, [data.groupId, onSetLeaders])

  const addLeader = useCallback((symbol: string) => {
    if (leaders.some(leader => leader.symbol === symbol)) return
    if (leaders.length >= GROUP_LEADER_MAX) return
    applyLeaders([...leaders, { symbol, label: defaultLeaderLabel(leaders.length) }])
  }, [leaders, applyLeaders])

  const removeLeader = useCallback((symbol: string) => {
    applyLeaders(leaders.filter(leader => leader.symbol !== symbol))
    setEditingLeader(null)
  }, [leaders, applyLeaders])

  const changeLeaderLabel = useCallback((symbol: string, label: string) => {
    applyLeaders(leaders.map(leader => (leader.symbol === symbol ? { ...leader, label } : leader)))
    setEditingLeader(null)
  }, [leaders, applyLeaders])

  return (
    <div className="flex flex-col self-start w-full overflow-hidden rounded-card border border-border bg-surface">
      {/* 头部: 色点 + 名称 + 指标数值居左, 总数 + 涨跌家数居右; 点击钻取该分组 */}
      <button
        type="button"
        onClick={() => onOpen(data.key)}
        className={`group flex w-full flex-col gap-0.5 border-b border-border/60 px-3 py-2 text-left transition-colors hover:bg-elevated/60 ${showColorBar && color ? color.background : ''}`}
        title={`查看「${data.name}」分组列表`}
      >
        <span className="flex w-full items-center gap-1.5">
          <span className={`h-2 w-2 shrink-0 rounded-full ${color ? color.dot : 'bg-muted/60'}`} />
          <span className={`truncate text-xs font-medium ${color ? color.text : 'text-foreground'}`}>
            {data.name}
          </span>
          {pctInfo && pctInfo.sampled > 0 && (
            <span
              className={`shrink-0 font-mono text-xs font-semibold tabular-nums ${groupPctColor(signed)}`}
              title={groupMetricTitle(pctInfo, metric)}
            >
              {valueLabel}
            </span>
          )}
          <span className="ml-auto flex shrink-0 items-center gap-1.5" title={groupMetricTitle(pctInfo, metric)}>
            <span className="font-mono text-micro tabular-nums text-muted">{data.rows.length}</span>
            {pctInfo && pctInfo.sampled > 0 && (
              <span className="text-micro tabular-nums">
                <span className="text-bull">{pctInfo.up}涨</span>
                <span className="mx-0.5 text-muted/40">/</span>
                <span className="text-bear">{pctInfo.down}跌</span>
              </span>
            )}
          </span>
          <ChevronRight className="h-3.5 w-3.5 shrink-0 text-muted/60 transition-transform group-hover:translate-x-0.5" />
        </span>
        {/* [R631] 代表摘要: 最多显示前 2 位, 其余以 +N 概括 */}
        {leaders.length > 0 && (
          <span className="flex w-full flex-wrap items-center gap-x-2 gap-y-0.5 pl-3.5 text-micro leading-tight">
            {leaders.slice(0, 2).map(leader => {
              const row = rowBySymbol.get(leader.symbol)
              const pct = rowPct(row)
              return (
                <span key={leader.symbol} className="inline-flex min-w-0 items-center gap-1">
                  <span className="shrink-0 font-medium text-amber-400">{leader.label}</span>
                  <span className="min-w-0 truncate text-secondary">
                    {row?.rt_name ?? row?.name ?? leader.symbol}
                  </span>
                  {pct != null && (
                    <span className={`shrink-0 font-mono tabular-nums ${priceColorClass(pct)}`}>
                      {fmtPct(pct)}
                    </span>
                  )}
                </span>
              )
            })}
            {leaders.length > 2 && <span className="shrink-0 text-muted">+{leaders.length - 2}</span>}
          </span>
        )}
      </button>

      {/* 组内榜单: 代表置顶, 其余按涨跌幅降序 */}
      {data.rows.length === 0 ? (
        <div className="px-3 py-4 text-center text-micro text-muted">暂无标的</div>
      ) : (
        <div className="flex flex-col">
          {visible.map((r: any, i: number) => {
            const pct = rowPct(r)
            const price = r.rt_price ?? r.close
            const cls = priceColorClass(pct)
            const board = boardTag(r.symbol)
            const leaderLabel = leaderLabelBySymbol.get(r.symbol)
            const isLeader = leaderLabel != null
            const editing = editingLeader === r.symbol
            return (
              <div key={r.symbol} className="group/row flex flex-col">
                <div className="flex items-center transition-colors duration-150 hover:bg-elevated/50">
                  <button
                    type="button"
                    onClick={() => onPreview(r.symbol, r.rt_name ?? r.name ?? '')}
                    className="flex min-w-0 flex-1 items-center gap-2 py-[5px] pl-3 text-left"
                    title={`${r.symbol} ${r.rt_name ?? r.name ?? ''}`}
                  >
                    {showRank && (
                      <span className="w-4 shrink-0 text-right font-mono text-micro leading-none tabular-nums text-muted/70">
                        {i + 1}
                      </span>
                    )}
                    <span className="shrink-0 font-mono text-xs text-foreground">{r.symbol}</span>
                    <span className="flex min-w-0 flex-1 items-center gap-1">
                      <span className="min-w-0 truncate text-xs text-secondary">{r.rt_name ?? r.name}</span>
                      {/* [R631] 代表徽标占位优先于板块标 (卡片较窄, 两者同时出现会把名称挤没) */}
                      {isLeader ? (
                        <span className="shrink-0 rounded-btn bg-amber-400/15 px-1 text-micro font-bold leading-[16px] text-amber-400">
                          {leaderLabel}
                        </span>
                      ) : board && (
                        <span className={`shrink-0 inline-flex items-center justify-center px-1 h-[16px] rounded-btn text-micro font-bold leading-none ${board.color}`}>
                          {board.label}
                        </span>
                      )}
                    </span>
                    <span className={`shrink-0 font-mono text-xs tabular-nums ${cls}`}>{fmtAssetPrice(price, r.asset_type)}</span>
                    <span className={`w-[52px] shrink-0 text-right font-mono text-xs font-medium tabular-nums ${cls}`}>
                      {fmtPct(pct)}
                    </span>
                  </button>
                  {/* [R631] 皇冠: 悬停出现; 已是代表时点击可改标签/取消 */}
                  {data.groupId && (
                    <button
                      type="button"
                      onClick={() => (isLeader ? setEditingLeader(editing ? null : r.symbol) : addLeader(r.symbol))}
                      disabled={!isLeader && leadersFull}
                      className={cn(
                        'mr-1 shrink-0 rounded-btn p-1 transition-colors duration-150',
                        isLeader
                          ? 'text-amber-400 hover:bg-amber-400/10'
                          : leadersFull
                            ? 'cursor-not-allowed text-muted/40 md:opacity-40'
                            : 'text-muted/60 opacity-100 hover:bg-amber-400/10 hover:text-amber-400 focus-visible:opacity-100 md:opacity-0 md:group-hover/row:opacity-100',
                      )}
                      title={
                        isLeader
                          ? `「${leaderLabel}」· 点击修改标签或取消代表`
                          : leadersFull
                            ? `每组最多 ${GROUP_LEADER_MAX} 位代表`
                            : '设为本组代表'
                      }
                      aria-label={isLeader ? `修改${leaderLabel}标签` : '设为本组代表'}
                    >
                      <Crown className={cn('h-3 w-3', isLeader && 'fill-current')} />
                    </button>
                  )}
                </div>
                {/* [R631] 代表标签编辑: 快捷标签 + 取消代表 */}
                {editing && (
                  <div className="flex flex-wrap items-center gap-1 border-t border-border/40 bg-elevated/30 px-2 py-1.5">
                    <span className="mr-0.5 text-micro text-muted">代表标签</span>
                    {LEADER_LABEL_PRESETS.map(label => (
                      <button
                        key={label}
                        type="button"
                        onClick={() => changeLeaderLabel(r.symbol, label)}
                        className={cn(
                          'rounded-btn border px-1.5 py-0.5 text-micro transition-colors duration-150',
                          label === leaderLabel
                            ? 'border-amber-400/50 bg-amber-400/15 text-amber-400'
                            : 'border-border text-secondary hover:border-amber-400/40 hover:text-amber-400',
                        )}
                      >
                        {label}
                      </button>
                    ))}
                    <button
                      type="button"
                      onClick={() => removeLeader(r.symbol)}
                      className="ml-auto rounded-btn px-1.5 py-0.5 text-micro text-muted transition-colors duration-150 hover:bg-elevated hover:text-bear"
                    >
                      取消代表
                    </button>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}

      {/* 展开/收起 */}
      {hasMore && (
        <button
          type="button"
          onClick={() => onToggle(data.key)}
          className="flex items-center justify-center gap-1 border-t border-border/60 px-3 py-1.5 text-micro text-muted transition-colors hover:bg-elevated/60 hover:text-foreground"
        >
          {expanded ? '收起' : `显示全部 ${data.rows.length} 只`}
          <ChevronDown className={`h-3 w-3 transition-transform ${expanded ? '' : 'rotate-180'}`} />
        </button>
      )}
    </div>
  )
})

interface WatchlistGroupCardsProps {
  groups: WatchlistGroup[]
  /** enriched 全量行 (未经过分组/板块筛选) */
  rows: any[]
  /** symbol -> 所属分组 id 列表 (空数组 = 未分组), 来自自选列表查询 */
  groupBySymbol: Map<string, string[]>
  /** 分组等权涨跌幅统计 */
  pcts: GroupPctMap
  onPreview: (symbol: string, name: string) => void
  /** 钻取分组 (切换到该分组的卡片列表) */
  onOpenGroup: (groupId: string) => void
  /** [R631] 设定分组代表 (顺序即主次, 最多 3 位) */
  onSetLeaders: (groupId: string, leaders: WatchlistGroupLeader[]) => void
  config: GroupStatsConfig
  onConfigChange: (patch: GroupStatsConfigPatch) => void
}

export function WatchlistGroupCards({
  groups,
  rows,
  groupBySymbol,
  pcts,
  onPreview,
  onOpenGroup,
  onSetLeaders,
  config,
  onConfigChange,
}: WatchlistGroupCardsProps) {
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set())

  const toggleExpanded = useCallback((key: string) => {
    setExpanded(prev => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }, [])

  // 分桶 + 组内按涨跌幅降序 + 代表置顶: 仅在 enriched 行或分组归属变化时重算,
  // 每组数组引用稳定, 配合 GroupCard memo 避免无关卡片重渲染。
  const cards = useMemo<GroupCardData[]>(() => {
    const buckets = new Map<string, any[]>()
    for (const group of groups) buckets.set(group.id, [])
    buckets.set('ungrouped', [])
    for (const r of rows) {
      // 多组并存: 一股可同时出现在多个分组卡片中
      const gids = groupBySymbol.get(r.symbol)
      if (!gids || gids.length === 0) {
        buckets.get('ungrouped')?.push(r)
      } else {
        for (const gid of gids) buckets.get(gid)?.push(r)
      }
    }
    const sorted = new Map<string, any[]>()
    for (const [key, list] of buckets) {
      sorted.set(key, [...list].sort((a, b) => {
        const pa = rowPct(a)
        const pb = rowPct(b)
        if (pa == null && pb == null) return 0
        if (pa == null) return 1
        if (pb == null) return -1
        return pb - pa
      }))
    }
    const result: GroupCardData[] = groups.map(group => ({
      key: group.id,
      name: group.name,
      color: resolveWatchlistGroupColor(group.color),
      // [R631] 代表按设定顺序置顶, 其余保持涨跌幅排序
      rows: orderGroupRows(sorted.get(group.id) ?? [], group.leaders),
      leaders: group.leaders ?? [],
      groupId: group.id,
    }))
    // 未分组仅在非空时展示; [R631] 未分组不提供代表功能
    const ungrouped = sorted.get('ungrouped') ?? []
    if (ungrouped.length > 0) {
      result.push({ key: 'ungrouped', name: '未分组', color: null, rows: ungrouped, leaders: [], groupId: null })
    }
    return result
  }, [groups, rows, groupBySymbol])

  // 卡片顺序跟随「指标 + 排序」配置 (与分组统计条同源)
  const ordered = useMemo(
    () => sortGroupKeys(cards, c => c.key, pcts, config),
    [cards, pcts, config],
  )

  if (cards.length === 0) return null

  const metricLabel = GROUP_METRICS.find(m => m.id === config.metric)?.label ?? ''

  return (
    <div>
      <div className="mb-2 flex items-center justify-between">
        <div className="text-micro uppercase tracking-wider text-muted">分组卡片 · {metricLabel}</div>
        <GroupStatsSettings config={config} onChange={onConfigChange} ariaLabel="分组卡片设置" showCardLimit />
      </div>
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
        {ordered.map(card => (
          <GroupCard
            key={card.key}
            data={card}
            pctInfo={pcts[card.key]}
            metric={config.metric}
            topN={config.cardTopN}
            showColorBar={config.cardColorBar}
            showRank={config.cardRank}
            expanded={expanded.has(card.key)}
            onToggle={toggleExpanded}
            onPreview={onPreview}
            onOpen={onOpenGroup}
            onSetLeaders={onSetLeaders}
          />
        ))}
      </div>
    </div>
  )
}
