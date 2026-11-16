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
import { useEffect, useMemo, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Sparkles } from 'lucide-react'
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
/** [R769] 天数档位与「涨幅RPS轮动分析」弹窗同一套，两处看到的口径必须能对上 */
const DAY_PRESETS = [7, 12, 20, 30]

/**
 * [R773] 矩阵工具栏：天数 / 范围 / AI 三个入口。
 *
 * 它原来是矩阵上方独占一行的控件条（26px + 下方留白 4px）。用户：「按钮们放到刷新按钮
 * 前面」—— 这三个按钮和刷新/配置本来就是同一类「改口径、刷数据」的动作，分居上下两行
 * 要来回扫两次。现在整条搬进页头右侧，放在刷新按钮之前，矩阵上方那 30px 还给表格。
 *
 * 单独导出而不是留在矩阵里：它现在渲染在页头，和矩阵不再有 DOM 上的父子关系；
 * 但仍属于「这张矩阵的口径」，所以和矩阵放在同一个文件，改一处就同时看到两边。
 */
export function SectorHeatmapToolbar({
  days,
  topN,
  showAll,
  totalCount = 0,
  onDaysChange,
  onShowAllChange,
  onOpenAi,
}: {
  days: number
  topN: number
  /** 受控：前 N 名 / 全部名次，状态在页面里 */
  showAll: boolean
  /**
   * 榜单总行数（= 行业/概念总数）。由矩阵从接口数据里回报，页头只负责显示 ——
   * 页头自己的 `stats.length` 是本地分组算出来的、与轮动接口的总数不一定相等，
   * 拿它拼「全部 N」会说假话。
   */
  totalCount?: number
  onDaysChange?: (days: number) => void
  onShowAllChange?: (showAll: boolean) => void
  /** 打开 AI 轮动分析，带上当前看的天数 */
  onOpenAi?: (days: number) => void
}) {
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <div className="flex items-center rounded-btn border border-border bg-base/60 p-0.5">
        {DAY_PRESETS.map(d => (
          <button
            key={d}
            onClick={() => onDaysChange?.(d)}
            className={cn(
              'h-5 rounded-[5px] px-2 text-micro tabular-nums transition-colors',
              days === d ? 'bg-foreground font-medium text-surface' : 'text-secondary hover:text-foreground',
            )}
          >
            {d}日
          </button>
        ))}
      </div>
      <div className="flex items-center rounded-btn border border-border bg-base/60 p-0.5">
        <button
          onClick={() => onShowAllChange?.(false)}
          className={cn(
            'h-5 rounded-[5px] px-2 text-micro tabular-nums transition-colors',
            !showAll ? 'bg-foreground font-medium text-surface' : 'text-secondary hover:text-foreground',
          )}
        >
          前 {topN}
        </button>
        <button
          onClick={() => onShowAllChange?.(true)}
          className={cn(
            'h-5 rounded-[5px] px-2 text-micro tabular-nums transition-colors',
            showAll ? 'bg-foreground font-medium text-surface' : 'text-secondary hover:text-foreground',
          )}
        >
          全部 {totalCount || '—'}
        </button>
      </div>
      {onOpenAi && (
        <button
          onClick={() => onOpenAi(days)}
          className="inline-flex h-6 items-center gap-1 rounded-btn border border-border px-2 text-micro text-secondary transition-colors hover:bg-elevated hover:text-foreground"
          title="让 AI 读这张矩阵, 出一份轮动研判"
        >
          <Sparkles className="h-3 w-3" />
          AI 轮动分析
        </button>
      )}
    </div>
  )
}

export function SectorRankHeatmap({
  kind,
  level,
  days = DEFAULT_DAYS,
  topN = DEFAULT_TOP_N,
  showAll = false,
  selectedKey = null,
  onSelect,
  onTotalChange,
}: {
  kind: 'concept' | 'industry'
  /** 行业层级；概念维度传 undefined */
  level?: number
  days?: number
  topN?: number
  /** [R769] 受控: 前 N 名 / 全部名次, 状态在页面里(页头副标题要跟着说真话) */
  showAll?: boolean
  selectedKey?: string | null
  onSelect?: (name: string) => void
  /** [R773] 把榜单总行数回报给页头工具栏（「全部 N」那个数只有这里才有真值） */
  onTotalChange?: (total: number) => void
}) {
  const lvParam = kind === 'industry' ? level : undefined
  const { data, isLoading, error } = useQuery({
    queryKey: [...QK.rpsRotation(days), kind, lvParam],
    queryFn: () => api.rpsRotation(days, kind, lvParam),
    staleTime: 5 * 60 * 1000,
  })

  const dates = useMemo(() => data?.dates ?? [], [data])
  /** 当日榜单总行数(= 行业/概念总数), 全部模式的行数与色阶分档都取它 */
  const totalRows = data?.columns?.[dates[0]]?.length ?? 0
  const rows = useMemo(
    () => buildRankRows(dates, data?.columns ?? {}, showAll ? totalRows || topN : topN),
    [dates, data, topN, showAll, totalRows],
  )
  const label = kind === 'industry' ? '行业' : '概念'

  // [R773] 榜单总行数回报给页头的「全部 N」。页头自己的 stats.length 是本地分组算的,
  // 与这张表的总行数不是同一个数, 只有这里的数据才是真值。
  useEffect(() => {
    if (totalRows) onTotalChange?.(totalRows)
  }, [totalRows, onTotalChange])

  // [R768] 行高按容器实测高度算: 45 行正好铺满剩余可视区, 页面不出滚动条。
  // 固定行高做不到这件事 —— 窗口一变就得靠内部滚动兜底, 那正是用户不要的。
  // [R769] 全部模式例外: 257 行本来就装不进一屏, 固定行高 + 矩阵区自己滚。
  const scrollRef = useRef<HTMLDivElement>(null)
  // [R770] 行高与「前45 / 全部」无关: 永远按"45 行铺满容器"算一次, 两种模式共用。
  // 原来全部模式写死 17、前 45 模式按实测算, 只要容器高度不是 45 的整数倍, 切一下就跳 1px。
  const [rowH, setRowH] = useState(17)

  useEffect(() => {
    const el = scrollRef.current
    if (!el) return
    const measure = () => {
      const theadH = el.querySelector('thead')?.getBoundingClientRect().height ?? 20
      // 分母固定用 topN(数据不足时才用实际行数), 不看当前渲染了几行
      const n = Math.min(topN, totalRows || topN) || 1
      // [R771] 不取整: 取整必然在底部留下 0~n px 的白条, 用户要的是「利用完底部空间」。
      // 保留 2 位小数, 45~48 行加起来正好等于容器可用高度; 差值 <0.5 不回写, 免得 ResizeObserver 抖。
      const h = Math.round(((el.clientHeight - theadH) / n) * 100) / 100
      setRowH(prev => (Math.abs(prev - h) < 0.5 ? prev : Math.max(14, Math.min(28, h))))
    }
    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(el)
    return () => ro.disconnect()
  }, [topN, totalRows, rows.length])

  return (
    // [R767] 去掉卡片外壳(rounded-card + 边框 + 底色): 这一页就是「页头 + 矩阵」的上下结构,
    // 表格自己铺满内容区, 不再套一层框。
    // [R773] 工具栏已搬到页头右侧, 这里只剩表格本身, 30px 还给行高。
    <div className="flex min-h-0 w-full flex-1 flex-col">
      {isLoading ? (
        <div className="px-3 py-6 text-center text-micro text-muted">正在计算{label}排名…</div>
      ) : error ? (
        <div className="px-3 py-6 text-center text-micro text-muted">
          排名数据读取失败：{error instanceof Error ? error.message : '未知错误'}
        </div>
      ) : rows.length === 0 ? (
        <div className="px-3 py-6 text-center text-micro text-muted">最近 {days} 个交易日没有排名数据</div>
      ) : (
        // [R763] 高密度模式: 格内只留名次(涨幅进悬停), 45 行一屏不滚
        // [R768] 前 N 名模式: 行高按容器实测, 45 行铺满剩余高度, 页面不出滚动条
        // [R769] 全部模式: 257 行装不下一屏, 改成矩阵区自己滚(页面整体仍不滚)
        <div
          ref={scrollRef}
          className={cn('min-h-0 flex-1', showAll ? 'overflow-auto' : 'overflow-hidden')}
        >
          {/* [R761] table-fixed + 零内边距: 每个日期列宽严格相等, 色块铺满整格、格与格之间
              不留空隙(只留 1px 分隔线), 与参考图一致 —— 之前 px-[3px] 留出的 6px 缝
              在 30 列下会把格子挤成方块。 */}
          <table className="w-full table-fixed border-collapse">
            <thead className="sticky top-0 z-20">
              <tr>
                {/* [R766] 卡片头那行(标题 + 长说明 + 色阶图例, 34px)整行删除:
                    天数/前 N 挪进页面副标题, 10 档色阶并进「名称」表头, 完整说明进 title。
                    首行数据从 y=126 提到 y=92, 多露两行。 */}
                <th
                  className="sticky left-0 z-30 w-36 border-r border-b border-border/60 bg-surface px-2 py-0.5 text-left text-micro font-normal text-muted"
                  title={`${label}排名热力图 · 最近 ${dates.length || days} 个交易日 · 格内为当日涨幅名次（悬停看涨幅）· ${showAll ? `全部 ${totalRows} 名` : `前 ${topN} 名`}`}
                >
                  <div className="flex items-center justify-between gap-1">
                    <span>名称</span>
                    <span className="flex items-center gap-px">
                      {RANK_BAND_COLORS.map(color => (
                        <span key={color} className="h-2 w-1.5" style={{ backgroundColor: color }} />
                      ))}
                    </span>
                  </div>
                </th>
                {dates.map(date => (
                  <th
                    key={date}
                    className="border-r border-b border-border/60 bg-surface py-0.5 text-center text-micro font-normal text-muted tabular-nums"
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
                  <tr key={row.name} style={{ height: rowH }} className="border-b border-border/25">
                    <td className="sticky left-0 z-10 border-r border-border/25 bg-surface p-0">
                      <div style={{ height: rowH - 1 }} className="flex items-center gap-1 px-1">
                        <span className="w-4 shrink-0 text-right text-micro text-muted tabular-nums">
                          {row.rank}
                        </span>
                        <button
                          onClick={() => onSelect?.(row.name)}
                          className={cn(
                            'min-w-0 flex-1 truncate text-left text-micro',
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
                            onClick={() => onSelect?.(row.name)}
                            className="flex w-full cursor-pointer items-center justify-center text-micro font-medium leading-none tabular-nums hover:brightness-110"
                            style={{
                              height: rowH - 1,
                              backgroundColor: rankColor(cell.rank, showAll ? totalRows : 50),
                              color: rankTextColor(cell.rank, showAll ? totalRows : 50),
                            }}
                            title={`${row.name} · ${dates[i]} · 第 ${cell.rank} 名 · ${formatRankDelta(cell.pct)}%`}
                          >
                            {cell.rank}
                          </div>
                        ) : (
                          <div style={{ height: rowH - 1 }} className="flex w-full items-center justify-center text-micro text-muted/40">
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
