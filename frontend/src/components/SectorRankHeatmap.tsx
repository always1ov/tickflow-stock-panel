/**
 * [R761] 板块排名热力图 —— 用户给的参考图：行=标的、列=交易日、格子=当日排名 + 当日涨幅，
 * 底色按名次分 10 档从深红走到深绿。行业板块页原来的「热度分布」标签云原位换成它：
 * 行业名稳定、1 级 90 / 2 级 257 个，名次连续，色块能连成片，读起来不花。
 *
 * 数据只复用 `/api/rps/rotation`（与「涨幅RPS轮动」弹窗同一份，缓存键也共用），
 * 不新增后端接口：每列已按当日涨幅降序排好，排名 = 数组下标 + 1。
 *
 * 版式照参考图逐项量过：行高 37px、色块 44×30、色块间距 7px、格内两行（名次 + 涨幅）、
 * 行与行/列与列之间各一条浅分隔线；左侧「序号 + 板块名」一列钉住不动。
 * 参考图的「代码」列这里没有 —— 板块本身没有代码，硬造一列只会多一处假信息。
 */
import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import { cn } from '@/lib/cn'
import {
  formatRankDelta,
  RANK_BAND_COLORS,
  buildRankRows,
  rankColor,
  rankTextColor,
} from '@/lib/rankHeatmap'

/** 默认看最近 30 个交易日（参考图的列数），每页取当日排名前 50。 */
const DEFAULT_DAYS = 30
const DEFAULT_TOP_N = 50

export function SectorRankHeatmap({
  kind,
  level,
  days = DEFAULT_DAYS,
  topN = DEFAULT_TOP_N,
  selectedKey = null,
  onSelect,
}: {
  kind: 'concept' | 'industry'
  /** 行业层级；概念维度传 undefined */
  level?: number
  days?: number
  topN?: number
  selectedKey?: string | null
  onSelect?: (name: string) => void
}) {
  const lvParam = kind === 'industry' ? level : undefined
  const { data, isLoading, error } = useQuery({
    queryKey: [...QK.rpsRotation(days), kind, lvParam],
    queryFn: () => api.rpsRotation(days, kind, lvParam),
    staleTime: 5 * 60 * 1000,
  })

  const dates = useMemo(() => data?.dates ?? [], [data])
  const rows = useMemo(
    () => buildRankRows(dates, data?.columns ?? {}, topN),
    [dates, data, topN],
  )
  const label = kind === 'industry' ? '行业' : '概念'

  return (
    <div className="rounded-card border border-border bg-surface">
      <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1 border-b border-border/60 px-3 py-2">
        <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
          <span className="text-xs font-medium text-secondary">{label}排名热力图</span>
          <span className="text-micro text-muted">
            最近 {dates.length || days} 个交易日 · 格内上为当日涨幅名次、下为当日涨幅 · 前 {topN}
          </span>
        </div>
        <div className="flex items-center gap-1 text-micro text-muted">
          <span>1</span>
          {RANK_BAND_COLORS.map(color => (
            <span key={color} className="h-2.5 w-4" style={{ backgroundColor: color }} />
          ))}
          <span>50</span>
        </div>
      </div>

      {isLoading ? (
        <div className="px-3 py-6 text-center text-micro text-muted">正在计算{label}排名…</div>
      ) : error ? (
        <div className="px-3 py-6 text-center text-micro text-muted">
          排名数据读取失败：{error instanceof Error ? error.message : '未知错误'}
        </div>
      ) : rows.length === 0 ? (
        <div className="px-3 py-6 text-center text-micro text-muted">最近 {days} 个交易日没有排名数据</div>
      ) : (
        // [R762] 热力图现在是第一屏主角, 高度从 38rem 提到 40rem(一屏约 20 行)
        <div className="max-h-[40rem] overflow-auto">
          {/* [R761] table-fixed + 零内边距: 每个日期列宽严格相等, 色块铺满整格、格与格之间
              不留空隙(只留 1px 分隔线), 与参考图一致 —— 之前 px-[3px] 留出的 6px 缝
              在 30 列下会把格子挤成方块。 */}
          <table className="w-full table-fixed border-collapse">
            <thead className="sticky top-0 z-20">
              <tr>
                <th className="sticky left-0 z-30 w-36 border-r border-b border-border/60 bg-surface px-2 py-1.5 text-left text-micro font-normal text-muted">
                  名称
                </th>
                {dates.map(date => (
                  <th
                    key={date}
                    className="border-r border-b border-border/60 bg-surface py-1.5 text-center text-micro font-normal text-muted tabular-nums"
                  >
                    {date.slice(5)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map(row => {
                const active = selectedKey === row.name
                return (
                  <tr key={row.name} className="border-b border-border/25">
                    <td className="sticky left-0 z-10 border-r border-border/25 bg-surface p-0">
                      <div className="flex h-[30px] items-center gap-1.5 px-1">
                        <span className="w-5 shrink-0 text-right text-micro text-muted tabular-nums">
                          {row.rank}.
                        </span>
                        <button
                          onClick={() => onSelect?.(row.name)}
                          className={cn(
                            'min-w-0 flex-1 truncate text-left text-body',
                            active ? 'text-accent' : 'text-foreground hover:text-accent',
                          )}
                          title={row.name}
                        >
                          {row.name}
                        </button>
                      </div>
                    </td>
                    {row.cells.map((cell, i) => (
                      <td key={dates[i]} className="border-r border-border/25 p-0">
                        {cell ? (
                          <div
                            className="flex h-[30px] w-full flex-col items-center justify-center"
                            style={{
                              backgroundColor: rankColor(cell.rank),
                              color: rankTextColor(cell.rank),
                            }}
                            title={`${row.name} · ${dates[i]} · 第 ${cell.rank} 名 · ${formatRankDelta(cell.pct)}%`}
                          >
                            <span className="text-body font-semibold leading-none tabular-nums">
                              {cell.rank}
                            </span>
                            <span className="mt-0.5 text-micro leading-none tabular-nums">
                              {formatRankDelta(cell.pct)}
                            </span>
                          </div>
                        ) : (
                          <div className="flex h-[30px] w-full items-center justify-center text-micro text-muted/40">
                            —
                          </div>
                        )}
                      </td>
                    ))}
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
