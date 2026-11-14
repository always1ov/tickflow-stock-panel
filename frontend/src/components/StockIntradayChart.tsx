import { lazy, Suspense, useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Loader2 } from 'lucide-react'
import { api, type MinuteKlineRow } from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import { klineMinuteQueryOptions, minuteRefetchInterval } from '@/lib/kline'
import { minuteEmptyText, minuteFetchErrorText, type DailySummary } from '@/lib/intraday-chart'
import type { ChartRenderer } from '@/lib/chart-types'

const EChartsIntraday = lazy(() => import('./EChartsIntraday').then(m => ({ default: m.EChartsIntraday })))
const LightweightIntraday = lazy(() => import('./charts/LightweightIntraday').then(m => ({ default: m.LightweightIntraday })))

interface Props {
  symbol: string
  renderer?: ChartRenderer
  date: string | null
  height?: number
  prevClose?: number
  dailySummary?: DailySummary
  className?: string
  onPriceHover?: (price: number | null) => void
  onPriceDoubleClick?: (price: number, currentPrice: number) => void
  currentPrice?: number
  priceLines?: { value: number; label?: string; color?: string }[]
  /** 自动刷新间隔(ms)。undefined/0 = 不轮询(默认)。个股对话框盘中实时刷新时传入。 */
  refetchIntervalMs?: number
  /**
   * [R625] 分钟数据确认拿不到(数据源未提供 / 指数)时通知外层。
   * 个股弹窗据此收起空的分时列, 让日K占满宽度; 详情页不传, 行为不变。
   */
  onSourceEmptyChange?: (empty: boolean) => void
}

export function StockIntradayChart({
  symbol,
  renderer = 'echarts',
  date,
  height = 520,
  prevClose,
  dailySummary,
  className,
  onPriceHover,
  onPriceDoubleClick,
  currentPrice,
  priceLines,
  refetchIntervalMs,
  onSourceEmptyChange,
}: Props) {
  const qc = useQueryClient()
  const [minuteDismissed, setMinuteDismissed] = useState(false)
  // [R624] 空态里点过「获取/重新获取」的那一天: 结果只对这一天成立, 换日期就作废,
  // 否则上一天的失败原因会被带到下一天的空态里。
  const [attemptDate, setAttemptDate] = useState<string | null>(null)

  const minute = useQuery({
    // 轮询上下文 (个股详情) 传 live: 当日盘中后端直接实时拉取最新K,
    // 避免读到分钟增量落盘的上一轮本地分区; 历史日期后端自行忽略 live。
    ...klineMinuteQueryOptions(symbol, date ?? undefined, refetchIntervalMs != null),
    enabled: !!symbol && !!date,
    refetchInterval: minuteRefetchInterval(refetchIntervalMs),
  })

  const fetchMinute = useMutation({
    mutationFn: () => api.syncMinuteSingle(symbol),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['kline-minute', symbol] })
      qc.invalidateQueries({ queryKey: QK.klineMinute(symbol, date ?? '') })
      qc.resetQueries({ queryKey: QK.minuteBatch(), exact: true })
      setMinuteDismissed(false)
    },
  })

  const minuteRows: MinuteKlineRow[] = useMemo(() => minute.data?.rows ?? [], [minute.data?.rows])
  // source=none 表示本地无数据且 TickFlow 也拉不到 (停牌/复牌延迟/非交易日)
  // 此时不弹"是否获取"询问窗, 只做静态提示, 避免误导用户去拉明知拉不到的数据
  const sourceIsNone = minute.data?.source === 'none'
  // 指数分钟K无本地存储且不支持落库获取 (后端 sync_minute_single 显式拒绝), 不显示获取按钮
  const isIndex = minute.data?.asset_type === 'index'
  const Chart = renderer === 'lightweight' ? LightweightIntraday : EChartsIntraday
  const chartHeight = renderer === 'lightweight' && minute.data?.source === 'local_partial' ? Math.max(260, height - 32) : height

  useEffect(() => {
    setMinuteDismissed(false)
    setAttemptDate(null)
    onPriceHover?.(null)
  }, [date, onPriceHover])

  // [R625] 「拿不到」要区分于「还没取」: 只有加载完且数据源确认没有(或指数)才算空,
  // 「是否立即获取」那种还能取的状态不算 —— 收起来会把获取入口一起藏掉。
  const sourceEmpty = !minute.isLoading && minuteRows.length === 0 && (isIndex || sourceIsNone)
  useEffect(() => { onSourceEmptyChange?.(sourceEmpty) }, [sourceEmpty, onSourceEmptyChange])

  if (!symbol || !date) return null

  return (
    <div className={className} style={{ height: renderer === 'lightweight' && minuteRows.length > 0 ? undefined : height, minHeight: height, flexShrink: 0 }}>
      {minute.isLoading && <div className="text-xs text-muted py-2">分时加载中…</div>}
      {!minute.isLoading && minuteRows.length === 0 && (
        <div className="flex h-full flex-col items-center justify-center gap-3">
          {fetchMinute.isPending ? (
            <div className="flex items-center gap-2 text-xs text-accent">
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              <span>正在获取分钟K数据…</span>
            </div>
          ) : isIndex ? (
            // 指数: 分钟K仅支持实时读取, 无落库获取入口
            <div className="text-xs text-muted">{minuteEmptyText('指数')}</div>
          ) : sourceIsNone ? (
            // 数据源确认无此日分钟数据 (停牌/复牌延迟等): 静态提示 + 保留重试
            <>
              <div className="text-xs text-muted">{minuteEmptyText('该日', true)}</div>
              <button
                onClick={() => { setAttemptDate(date); fetchMinute.mutate() }}
                className="px-4 py-1.5 rounded-btn bg-elevated text-secondary text-xs font-medium hover:bg-elevated/80 transition-colors duration-hover"
              >
                重新获取
              </button>
            </>
          ) : minuteDismissed ? (
            <>
              <div className="text-xs text-muted">{minuteEmptyText('该日')}</div>
              <button
                onClick={() => setMinuteDismissed(false)}
                className="px-4 py-1.5 rounded-btn bg-accent/90 text-on-accent text-xs font-medium hover:bg-accent transition-colors duration-hover"
              >
                获取分钟K
              </button>
            </>
          ) : (
            <>
              <div className="text-sm text-foreground">是否立即获取最近5日分钟K？</div>
              <div className="flex items-center gap-3">
                <button
                  onClick={() => { setAttemptDate(date); fetchMinute.mutate() }}
                  className="px-4 py-1.5 rounded-btn bg-accent/90 text-on-accent text-xs font-medium hover:bg-accent transition-colors duration-hover"
                >
                  确定
                </button>
                <button
                  onClick={() => setMinuteDismissed(true)}
                  className="px-4 py-1.5 rounded-btn bg-elevated text-secondary text-xs hover:bg-elevated/80 transition-colors duration-hover"
                >
                  取消
                </button>
              </div>
            </>
          )}
          {/* [R624] 以前点完按钮页面内没有任何反馈: 失败只弹一条全局 toast,
              成功但数据源一根没写入则画面一点不变 —— 用户只会以为按钮坏了。 */}
          {attemptDate === date && !fetchMinute.isPending && (
            fetchMinute.isError
              ? <div className="max-w-full px-4 text-center text-micro text-danger">{minuteFetchErrorText(fetchMinute.error)}</div>
              : fetchMinute.data?.rows === 0
                ? <div className="max-w-full px-4 text-center text-micro text-muted">已请求获取, 数据源没有该日的分钟K</div>
                : null
          )}
        </div>
      )}
      {minuteRows.length > 0 && (
        <>
          {minute.data?.source === 'local_partial' && (
            <div className="mb-1 flex items-center gap-2 rounded-btn border border-warning/30 bg-warning/5 px-2 py-1 text-micro text-warning">
              <span>
                该日分钟数据不完整：{minute.data.actual ?? minuteRows.length}/{minute.data.expected ?? 240} 根
              </span>
              <button
                type="button"
                onClick={() => fetchMinute.mutate()}
                disabled={fetchMinute.isPending}
                className="ml-auto shrink-0 rounded-btn border border-warning/40 px-1.5 py-0.5 hover:bg-warning/10 disabled:opacity-50"
              >
                {fetchMinute.isPending ? '补齐中…' : '尝试补齐'}
              </button>
            </div>
          )}
          <Suspense fallback={<div className="text-xs text-muted py-4">正在加载图表…</div>}>
          <Chart
            assetType={minute.data?.asset_type}
            symbol={symbol}
            data={minuteRows}
            height={chartHeight}
            prevClose={minute.data?.prev_close ?? prevClose}
            dailySummary={dailySummary}
            date={date}
            priceLimit={minute.data?.price_limit ?? undefined}
            onPriceHover={onPriceHover}
            onPriceDoubleClick={onPriceDoubleClick}
            currentPrice={currentPrice}
            priceLines={priceLines}
          />
          </Suspense>
        </>
      )}
    </div>
  )
}
