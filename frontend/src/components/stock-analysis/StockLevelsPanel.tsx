import { useEffect } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, LineChart, Loader2 } from 'lucide-react'
import { EmptyState } from '@/components/EmptyState'
import { api } from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import { AnalysisKChart, type LevelType, type PriceLevel } from './AnalysisKChart'
import { TrendStateBar, useStockTrend } from './TrendStateBar'

interface StockLevelsPanelProps {
  symbol: string
  height?: number
  bare?: boolean
}

/**
 * 个股分析页与通用个股详情共用的关键价位主体。
 * 查询键、单票实时刷新与六态失效顺序保持一致，避免两个入口形成不同口径。
 */
export function StockLevelsPanel({ symbol, height = 480, bare = false }: StockLevelsPanelProps) {
  const kline = useQuery({
    queryKey: QK.analysisKline(symbol),
    queryFn: () => api.klineDaily(symbol, 250, undefined, undefined, { refreshLive: true }),
    enabled: !!symbol,
    staleTime: 15_000,
    refetchOnMount: 'always',
  })

  const levelsQ = useQuery({
    queryKey: QK.stockLevels(symbol),
    queryFn: () => api.stockAnalysisLevels(symbol, 250),
    enabled: !!symbol,
    staleTime: 60_000,
  })

  const trendQ = useStockTrend(symbol)
  const qc = useQueryClient()
  const klineUpdatedAt = kline.dataUpdatedAt

  // 日 K 的 refresh_live 可能刚启动后台单票刷新。先让趋势和价位跟随同一份日 K，
  // 再按 started 状态补取新蜡烛；该顺序沿用原个股分析弹窗的稳定实现。
  useEffect(() => {
    if (!klineUpdatedAt || !symbol) return
    qc.invalidateQueries({ queryKey: QK.stockTrend(symbol) })
    qc.invalidateQueries({ queryKey: QK.stockLevels(symbol) })
  }, [klineUpdatedAt, symbol, qc])

  const liveRefresh = kline.data?.live_refresh
  useEffect(() => {
    if (liveRefresh !== 'started' || !symbol) return
    const timers = [1500, 4000].map(ms => setTimeout(
      () => qc.invalidateQueries({ queryKey: QK.analysisKline(symbol) }), ms))
    return () => timers.forEach(clearTimeout)
  }, [liveRefresh, klineUpdatedAt, symbol, qc])

  if (kline.isLoading) {
    return <div className="flex items-center justify-center py-20"><Loader2 className="h-5 w-5 animate-spin text-muted" /></div>
  }

  if (kline.isError) {
    return (
      <EmptyState
        icon={AlertTriangle}
        title="日 K 数据加载失败"
        hint="请检查网络或数据源配置后重试。"
      />
    )
  }

  const rows = kline.data?.rows ?? []
  if (rows.length === 0) {
    return <EmptyState icon={LineChart} title="暂无日 K 数据" hint="该标的尚未同步日 K,请先在数据页或自选页同步。" />
  }

  const levels = (levelsQ.data?.levels ?? {}) as Record<LevelType, PriceLevel[]>
  const trendRanges = (trendQ.data?.segments ?? []).map(segment => ({
    start: segment.start_date,
    end: segment.end_date,
    color: segment.side === 'bull' ? 'rgba(239,68,68,0.05)' : 'rgba(34,197,94,0.05)',
  }))

  const last = rows[rows.length - 1]
  const prev = rows[rows.length - 2]
  const isUp = prev ? last.close >= prev.close : last.close >= last.open

  const body = (
    <div className={bare ? 'space-y-2' : 'space-y-2 p-3'}>
      <TrendStateBar symbol={symbol} trend={trendQ.data} />
      <AnalysisKChart
        rows={rows}
        levels={levels}
        series={levelsQ.data?.series}
        seriesDates={levelsQ.data?.dates}
        ranges={trendRanges}
        // [R405] 斐波那契二型里画不成横线的那几样; 显隐由图内那个开关管。
        // (这儿只能写 `//`: 属性列表不是 JSX 子节点位置, `{/* */}` 在这儿是语法错 ——
        //  R401 在同一个坑里栽过一次。)
        fib2={levelsQ.data?.fib2}
        height={height}
      />
    </div>
  )

  if (bare) return body

  return (
    <div className="overflow-hidden rounded-card border border-border/60 bg-surface/40">
      <div className="border-b border-border/40 px-4 py-3">
        <div className="flex items-center justify-between gap-2">
          <div className="flex min-w-0 items-center gap-2">
            <LineChart className="h-4 w-4 shrink-0 text-sky-400" />
            <span className="text-sm font-medium text-foreground">关键价位分析</span>
          </div>
          <div className="flex shrink-0 items-baseline gap-2">
            <span className="text-[10px] text-muted">{rows.length} 个交易日</span>
            <span className="text-[10px] text-muted/60">·</span>
            <span className="text-[10px] text-muted">当前价</span>
            <span className={`font-mono text-base font-bold ${isUp ? 'text-bull' : 'text-bear'}`}>
              {levelsQ.data?.close?.toFixed(2) ?? '—'}
            </span>
          </div>
        </div>
      </div>
      {body}
    </div>
  )
}

/** 顶栏行情摘要。与 StockLevelsPanel 共享查询键，不产生额外网络请求。 */
export function StockLevelsPriceTag({ symbol }: { symbol: string }) {
  const kline = useQuery({
    queryKey: QK.analysisKline(symbol),
    queryFn: () => api.klineDaily(symbol, 250, undefined, undefined, { refreshLive: true }),
    enabled: !!symbol,
    staleTime: 15_000,
    refetchOnMount: 'always',
  })
  const levelsQ = useQuery({
    queryKey: QK.stockLevels(symbol),
    queryFn: () => api.stockAnalysisLevels(symbol, 250),
    enabled: !!symbol,
    staleTime: 60_000,
  })
  const rows = kline.data?.rows ?? []
  if (rows.length === 0) return null
  const last = rows[rows.length - 1]
  const prev = rows[rows.length - 2]
  const isUp = prev ? last.close >= prev.close : last.close >= last.open
  return (
    <span className="hidden items-baseline gap-2 sm:flex">
      <span className="text-[10px] text-muted">{rows.length} 个交易日</span>
      <span className="text-[10px] text-muted/60">·</span>
      <span className={`font-mono text-base font-bold ${isUp ? 'text-bull' : 'text-bear'}`}>
        {levelsQ.data?.close?.toFixed(2) ?? '—'}
      </span>
    </span>
  )
}
