/**
 * [R508 · fork 增强] 自选「按小分队」网格 —— 这一页的默认视图。
 *
 * 用户: 「我感觉你改过后还是每个个股占用很多空间」, 看过两版密排后选了「A 默认, 保留切换按钮」。
 *
 * 每个分组一小块: 头一行是组名 · 只数 · 组内等权涨跌, 下面每只票一行
 * (名称 + 代码 / 现价 / 涨跌幅 / 加入以来)。用户的分组正好每组三只, 1440 宽三列,
 * 一屏能放下 60~70 只, 整个池子一屏半看完 —— 原来的表格一屏 14 只, 卡片视图一屏 30 只。
 *
 * 数据全部来自自选页已有的两份查询(自选条目 + enriched 行), **零额外请求**;
 * 块内按今日涨跌降序(强的在上), 块的顺序可切「分组顺序 / 今日涨跌」。
 * 只做看: 点一行开个股弹窗, 点组名进那个分组; 增删改分组仍在「一张表」视图里。
 *
 * 行是数据不是装饰: 没有入场动画, 没有 hover 位移, 只有底色变化(R7 那条规矩)。
 */
import { useMemo } from 'react'
import type { WatchlistEntry, WatchlistGroup } from '@/lib/api'
import { fmtPct, fmtPrice, priceColorClass } from '@/lib/format'
import { rowPct, groupPctColor } from '@/lib/watchlistGroupStats'
import { resolveWatchlistGroupColor } from '@/lib/watchlist-group-colors'
import { cn } from '@/lib/cn'
import type { WatchlistGroupFilter } from './WatchlistGroups'

export type GridSort = 'order' | 'pct'

interface Props {
  groups: WatchlistGroup[]
  entries: WatchlistEntry[]
  /** 经过筛选与排序的行(与「一张表」同一份) —— 筛选条件对两种视图一视同仁 */
  rows: any[]
  selected: WatchlistGroupFilter
  sort: GridSort
  onPreview: (symbol: string, name: string) => void
  onOpenGroup: (group: WatchlistGroupFilter) => void
}

interface Block {
  id: WatchlistGroupFilter
  name: string
  color: ReturnType<typeof resolveWatchlistGroupColor> | null
  rows: any[]
  /** 块内等权平均涨跌(小数); 没有一只有涨跌时为 null */
  pct: number | null
}

function meanPct(rows: any[]): number | null {
  const vals = rows.map(rowPct).filter((v): v is number => v != null)
  if (vals.length === 0) return null
  return vals.reduce((a, b) => a + b, 0) / vals.length
}

/** 把一份行按分组切成块。一只票属于两个组就在两个块里各出现一次(与分组条的计数同口径)。 */
export function buildBlocks(
  groups: WatchlistGroup[], entries: WatchlistEntry[], rows: any[],
  selected: WatchlistGroupFilter, sort: GridSort,
): Block[] {
  const gids = new Map(entries.map(e => [e.symbol, e.group_ids ?? []]))
  const bySymbolPct = (a: any, b: any) => (rowPct(b) ?? -Infinity) - (rowPct(a) ?? -Infinity)
  const blocks: Block[] = []
  for (const g of groups) {
    if (selected !== 'all' && selected !== g.id) continue
    const members = rows.filter(r => (gids.get(r.symbol) ?? []).includes(g.id)).sort(bySymbolPct)
    if (members.length === 0) continue
    blocks.push({ id: g.id, name: g.name, color: resolveWatchlistGroupColor(g.color), rows: members, pct: meanPct(members) })
  }
  if (selected === 'all' || selected === 'ungrouped') {
    const loose = rows.filter(r => (gids.get(r.symbol) ?? []).length === 0).sort(bySymbolPct)
    if (loose.length > 0) blocks.push({ id: 'ungrouped', name: '未分组', color: null, rows: loose, pct: meanPct(loose) })
  }
  if (sort === 'pct') {
    // 「未分组」不参与排, 永远垫底 —— 它不是一个小分队
    const ranked = blocks.filter(b => b.id !== 'ungrouped')
      .sort((a, b) => (b.pct ?? -Infinity) - (a.pct ?? -Infinity))
    const loose = blocks.find(b => b.id === 'ungrouped')
    return loose ? [...ranked, loose] : ranked
  }
  return blocks
}

export function WatchlistGroupGrid({ groups, entries, rows, selected, sort, onPreview, onOpenGroup }: Props) {
  const blocks = useMemo(() => buildBlocks(groups, entries, rows, selected, sort), [groups, entries, rows, selected, sort])

  if (blocks.length === 0) {
    return <div className="rounded-btn border border-dashed border-border py-6 text-center text-xs text-muted">没有匹配的自选 —— 换个分组或清空筛选</div>
  }

  return (
    <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
      {blocks.map(b => (
        <section key={b.id} className="overflow-hidden rounded-card border border-border bg-surface" aria-label={b.name}>
          <button
            type="button"
            onClick={() => onOpenGroup(b.id)}
            title={b.id === 'ungrouped' ? '只看未分组' : `只看「${b.name}」`}
            className="flex h-7 w-full items-center gap-1.5 border-b border-border bg-elevated/50 px-2 text-left text-xs transition-colors duration-hover ease-smooth hover:bg-elevated"
          >
            {b.color && <span className={cn('h-1.5 w-1.5 shrink-0 rounded-full', b.color.dot)} />}
            <span className="truncate font-medium text-foreground">{b.name}</span>
            <span className="font-mono text-micro tabular-nums text-muted">{b.rows.length}</span>
            {b.pct != null && (
              <span className={cn('ml-auto font-mono text-xs tabular-nums', groupPctColor(b.pct))}>{fmtPct(b.pct)}</span>
            )}
          </button>
          <table className="w-full border-collapse text-xs">
            <tbody>
              {b.rows.map(r => {
                const pct = rowPct(r)
                const price = r.rt_price ?? r.close
                const name = r.rt_name ?? r.name ?? ''
                return (
                  <tr
                    key={r.symbol}
                    title={`${name || r.symbol} ${r.symbol}`}
                    onClick={() => onPreview(r.symbol, name)}
                    className="cursor-pointer border-t border-border/50 transition-colors duration-hover ease-smooth hover:bg-elevated/50"
                  >
                    <td className="max-w-0 truncate py-[3px] pl-2 pr-1 text-foreground">
                      {/* [R517] 代码不再跟在名字后面 —— 一行只留名称与三个数; 代码在悬停提示里, 点开弹窗也有 */}
                      {name || r.symbol}
                    </td>
                    <td className={cn('w-[22%] py-[3px] px-1 text-right font-mono tabular-nums', priceColorClass(pct))}>{fmtPrice(price)}</td>
                    <td className={cn('w-[20%] py-[3px] px-1 text-right font-mono tabular-nums', priceColorClass(pct))}>{pct != null ? fmtPct(pct) : '—'}</td>
                    <td className={cn('w-[20%] py-[3px] pl-1 pr-2 text-right font-mono tabular-nums', priceColorClass(r.pct_since_added))}
                        title="加入自选以来的涨跌">
                      {r.pct_since_added != null ? fmtPct(r.pct_since_added) : '—'}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </section>
      ))}
    </div>
  )
}
