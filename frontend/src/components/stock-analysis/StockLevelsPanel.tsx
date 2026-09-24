import { useEffect } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, LineChart, Loader2 } from 'lucide-react'
import { EmptyState } from '@/components/EmptyState'
import { api } from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import { AnalysisKChart, type LevelType, type PriceLevel } from './AnalysisKChart'
import type { LevelControls } from './levelControls'
import { TrendStateBar, useStockTrend } from './TrendStateBar'

interface StockLevelsPanelProps {
  symbol: string
  height?: number
  bare?: boolean
  /** [R430] 开关由外面持有(个股弹窗右侧那张列表); 见 `AnalysisKChart` 同名入参 */
  controls?: LevelControls
  /** [R430] 默认显示最近多少根 K 线 */
  visibleBars?: number
}

/**
 * 关键价位用的日 K(250 根, 带单票实时刷新)。[R430] 抽成 hook: 个股弹窗的头部与
 * 右侧价位列表也要读这一份 —— 同一个查询键, 不多发请求, 选项也只写一处。
 */
export function useAnalysisKline(symbol: string) {
  return useQuery({
    queryKey: QK.analysisKline(symbol),
    queryFn: () => api.klineDaily(symbol, 250, undefined, undefined, { refreshLive: true }),
    enabled: !!symbol,
    staleTime: 15_000,
    refetchOnMount: 'always',
  })
}

/** 关键价位本身。[R430] 同上, 右侧价位列表按它数每一类有几条 */
export function useStockLevels(symbol: string) {
  return useQuery({
    queryKey: QK.stockLevels(symbol),
    queryFn: () => api.stockAnalysisLevels(symbol, 250),
    enabled: !!symbol,
    staleTime: 60_000,
  })
}

/**
 * 个股分析页与通用个股详情共用的关键价位主体。
 * 查询键、单票实时刷新与六态失效顺序保持一致，避免两个入口形成不同口径。
 */
export function StockLevelsPanel({ symbol, height = 480, bare = false, controls, visibleBars }: StockLevelsPanelProps) {
  const kline = useAnalysisKline(symbol)

  const levelsQ = useStockLevels(symbol)

  // [R415] 副图的量化MACD。独立一支请求: 它要约 1000 根历史预热 EMA,
  // 而主图只取 250 根 —— 两者口径不同, 不能从主图那份日 K 里现算。
  const qmacdQ = useQuery({
    queryKey: QK.stockQuantMacd(symbol),
    queryFn: () => api.stockQuantMacd(symbol),
    enabled: !!symbol,
    staleTime: 15_000,
  })

  // [R486] 量化MACD 上方的「趋势量化」。同样独立一支: 它要从上市第一根算起
  const tquantQ = useQuery({
    queryKey: QK.stockTrendQuant(symbol),
    queryFn: () => api.stockTrendQuant(symbol),
    enabled: !!symbol,
    staleTime: 15_000,
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
    // [R415] 副图跟主图同一根实时蜡烛走, 不然盘中两张图差一根
    qc.invalidateQueries({ queryKey: QK.stockQuantMacd(symbol) })
    qc.invalidateQueries({ queryKey: QK.stockTrendQuant(symbol) })
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
        // [R412] 只为图内那个「回测这三档」按钮用
        symbol={symbol}
        // [R415] 副图: 用户自己的量化MACD, 取代原来的成交量
        quantMacd={qmacdQ.data}
        // [R426] 取数失败要说出来 —— 原来失败时副图只剩标题, 看着像"这只票没有信号"
        quantMacdError={qmacdQ.isError}
        // [R486] 量化MACD 上方的第二张副图
        trendQuant={tquantQ.data}
        trendQuantError={tquantQ.isError}
        controls={controls}
        visibleBars={visibleBars}
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
            <span className="text-micro text-muted">{rows.length} 个交易日</span>
            <span className="text-micro text-muted/60">·</span>
            <span className="text-micro text-muted">当前价</span>
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
  const kline = useAnalysisKline(symbol)
  const levelsQ = useStockLevels(symbol)
  const rows = kline.data?.rows ?? []
  if (rows.length === 0) return null
  const last = rows[rows.length - 1]
  const prev = rows[rows.length - 2]
  const isUp = prev ? last.close >= prev.close : last.close >= last.open
  return (
    <span className="hidden items-baseline gap-2 sm:flex">
      <span className="text-micro text-muted">{rows.length} 个交易日</span>
      <span className="text-micro text-muted/60">·</span>
      <span className={`font-mono text-base font-bold ${isUp ? 'text-bull' : 'text-bear'}`}>
        {levelsQ.data?.close?.toFixed(2) ?? '—'}
      </span>
    </span>
  )
}
