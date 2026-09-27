import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Activity, Loader2, Lock, RefreshCw } from 'lucide-react'
import { api, type IndexInstrument, type KlineRow, type MinuteKlineRow } from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import { useCapabilities } from '@/lib/useSharedQueries'
import { EChartsCandlestick, type OHLC } from '@/components/EChartsCandlestick'
import { EChartsIntraday } from '@/components/EChartsIntraday'
import { PageShell } from '@/components/PageShell'
import { buttonClass } from '@/components/ui'
import { useMediaQuery } from '@/lib/useMediaQuery'

function defaultRange() {
  const now = new Date()
  const end = now.toISOString().slice(0, 10)
  const s = new Date(now)
  s.setMonth(s.getMonth() - 6)
  return { start: s.toISOString().slice(0, 10), end }
}

function toOHLC(rows: KlineRow[]): OHLC[] {
  return rows
    .filter(r => r?.date != null && r.open != null && r.close != null)
    .map(r => ({
      date: typeof r.date === 'string' ? r.date.slice(0, 10) : String(r.date),
      open: Number(r.open),
      high: Number(r.high),
      low: Number(r.low),
      close: Number(r.close),
      volume: Number(r.volume ?? 0),
      ma5: r.ma5 != null ? Number(r.ma5) : null,
      ma10: r.ma10 != null ? Number(r.ma10) : null,
      ma20: r.ma20 != null ? Number(r.ma20) : null,
      ma60: r.ma60 != null ? Number(r.ma60) : null,
      macd_dif: r.macd_dif != null ? Number(r.macd_dif) : null,
      macd_dea: r.macd_dea != null ? Number(r.macd_dea) : null,
      macd_hist: r.macd_hist != null ? Number(r.macd_hist) : null,
      rsi_6: r.rsi_6 != null ? Number(r.rsi_6) : null,
      rsi_14: r.rsi_14 != null ? Number(r.rsi_14) : null,
      rsi_24: r.rsi_24 != null ? Number(r.rsi_24) : null,
      kdj_k: r.kdj_k != null ? Number(r.kdj_k) : null,
      kdj_d: r.kdj_d != null ? Number(r.kdj_d) : null,
      kdj_j: r.kdj_j != null ? Number(r.kdj_j) : null,
      // [R528] 图表画的是 26 日布林(接口现场算的 boll26_*), 不是 enriched 那组 20 日列
      boll_upper: r.boll26_upper != null ? Number(r.boll26_upper) : null,
      boll_mid: r.boll26_mid != null ? Number(r.boll26_mid) : null,
      boll_lower: r.boll26_lower != null ? Number(r.boll26_lower) : null,
    }))
}

function fmtPct(v: number | null | undefined) {
  if (v == null || Number.isNaN(Number(v))) return '--'
  return `${Number(v).toFixed(2)}%`
}

function fmtNum(v: number | null | undefined, digits = 2) {
  if (v == null || Number.isNaN(Number(v))) return '--'
  return Number(v).toFixed(digits)
}

const PINNED_INDEXES = [
  { symbol: '000001.SH', name: '上证指数' },
  { symbol: '399001.SZ', name: '深证成指' },
  { symbol: '399006.SZ', name: '创业板指' },
  { symbol: '000680.SH', name: '科创综指' },
]

export function Indices() {
  const qc = useQueryClient()
  const [searchParams, setSearchParams] = useSearchParams()
  const symbolParam = searchParams.get('symbol') ?? ''
  const [selected, setSelected] = useState<string>(symbolParam)
  const [range, setRange] = useState(defaultRange)
  const [selectedDate, setSelectedDate] = useState<string | null>(null)
  const [linkedPrice, setLinkedPrice] = useState<number | null>(null)

  // 分时数据依赖分钟K批量数据 (kline.minute.batch)
  const caps = useCapabilities()
  const hasMinuteCap = !!caps.data?.capabilities?.['kline.minute.batch']
  // [R545] 手机上日K与分时上下叠, 各自全宽; 叠起来后矮一点, 两张图一屏半看完
  const isNarrow = useMediaQuery('(max-width: 767px)')
  const chartH = isNarrow ? 420 : 620

  // 指数标的固定核心四只 (产品契约, 不再提供全指数搜索/浏览)
  const topRows: IndexInstrument[] = PINNED_INDEXES.map(p => ({
    symbol: p.symbol, name: p.name, asset_type: 'index' as const,
  }))

  const selectedSymbol = selected || topRows[0]?.symbol || ''

  useEffect(() => {
    if (symbolParam && symbolParam !== selected) setSelected(symbolParam)
  }, [selected, symbolParam])

  const selectIndex = (symbol: string) => {
    setSelected(symbol)
    setSearchParams({ symbol })
  }

  const quotes = useQuery({
    queryKey: QK.indexQuotes,
    queryFn: () => api.indexQuotes(),
    placeholderData: (prev) => prev,
  })

  const daily = useQuery({
    queryKey: QK.indexDaily(selectedSymbol, range.start, range.end),
    queryFn: () => api.indexDaily(selectedSymbol, 180, range),
    enabled: !!selectedSymbol,
    placeholderData: (prev) => prev,
  })

  const minute = useQuery({
    queryKey: QK.indexMinute(selectedSymbol, selectedDate ?? ''),
    queryFn: () => api.indexMinute(selectedSymbol, selectedDate ?? undefined),
    enabled: !!selectedSymbol && !!selectedDate && hasMinuteCap,
  })

  const syncDaily = useMutation({
    mutationFn: () => api.syncIndexDaily(365),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: QK.indexQuotes })
      qc.invalidateQueries({ queryKey: ['index-daily'] })
    },
  })

  const quoteBySymbol = useMemo(() => {
    const m = new Map<string, any>()
    for (const q of quotes.data?.rows ?? []) m.set(q.symbol, q)
    return m
  }, [quotes.data?.rows])
  const selectedQuote = selectedSymbol ? quoteBySymbol.get(selectedSymbol) : null
  const selectedQuoteValue = selectedQuote?.last_price ?? selectedQuote?.price ?? selectedQuote?.close
  const selectedQuotePct = selectedQuote?.change_pct ?? selectedQuote?.pct

  const chartRows = useMemo(() => toOHLC(daily.data?.rows ?? []), [daily.data?.rows])
  const selectedInfo = topRows.find(r => r.symbol === selectedSymbol) || daily.data?.index_info
  const minuteRows: MinuteKlineRow[] = minute.data?.symbol === selectedSymbol
    && minute.data?.date === selectedDate && daily.data?.symbol === selectedSymbol
    ? minute.data.rows : []
  const selectedIdx = selectedDate ? chartRows.findIndex(r => r.date === selectedDate) : -1
  const prevClose = selectedIdx > 0
    ? chartRows[selectedIdx - 1].close
    : chartRows.length >= 2
      ? chartRows[chartRows.length - 2].close
      : undefined

  useEffect(() => {
    setSelectedDate(null)
    setLinkedPrice(null)
  }, [selectedSymbol])

  useEffect(() => {
    if ((!selectedDate || !chartRows.some(r => r.date === selectedDate)) && chartRows.length > 0 && daily.data?.symbol === selectedSymbol) {
      setSelectedDate(chartRows[chartRows.length - 1].date)
    }
  }, [chartRows, daily.data?.symbol, selectedDate, selectedSymbol])
  const renderIndexItem = (item: IndexInstrument) => {
    const q = quoteBySymbol.get(item.symbol)
    const pct = q?.change_pct ?? q?.pct
    const current = q?.last_price ?? q?.price ?? q?.close
    const active = item.symbol === selectedSymbol
    return (
      <button
        key={item.symbol}
        onClick={() => selectIndex(item.symbol)}
        className={`w-full rounded-card border px-3 py-2 text-left transition-colors ${active ? 'border-foreground bg-surface text-foreground' : 'border-border bg-surface text-secondary hover:bg-elevated'}`}
      >
        <div className="flex items-center justify-between gap-2">
          <span className="truncate text-xs font-medium">{item.name || item.symbol}</span>
          <span className={`text-micro font-mono ${Number(pct ?? 0) >= 0 ? 'text-bull' : 'text-bear'}`}>{fmtPct(pct)}</span>
        </div>
        <div className="mt-0.5 flex items-center justify-between text-micro font-mono text-muted">
          <span>{item.symbol}</span>
          <span>{fmtNum(current)}</span>
        </div>
      </button>
    )
  }

  return (
    // [R60] 原来手搓了一个 h1 + p-4 的壳, 标题字号和留白都和别的页对不上
    <PageShell
      title="指数"
      // [R545] 原副标题「独立 kline_index_* parquet，不进入股票选股和策略链路」是写给开发者看的
      subtitle="上证 · 深证 · 创业板 · 科创 四只核心指数的日K与分时"
      width="full"
      right={(
        <div className="flex items-center gap-2">
          <button
            onClick={() => syncDaily.mutate()}
            disabled={syncDaily.isPending}
            className={buttonClass({ variant: 'primary' }, 'gap-1.5')}
          >
            {syncDaily.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
            同步指数日K
          </button>
        </div>
      )}
    >
      {/* [R374] 窄屏堆叠: 原 grid-cols-[15rem_1fr] 固定 240px 左栏, 手机上堆到顶部。
          [R545] 四只指数用一整列 240px 竖着排, 下面大半截是空的, 图表只剩剩下的宽度 ——
          改成顶上一排四格(名称 / 代码 / 点位 / 涨跌一样不少), 图表吃满整宽。 */}
      <div className="space-y-4">
        <div className="grid grid-cols-2 gap-2 lg:grid-cols-4">
          {topRows.map(renderIndexItem)}
        </div>

        <main className="min-w-0 rounded-card border border-border bg-surface p-3">
          <div className="mb-3 flex items-center justify-between gap-3">
            <div className="min-w-0">
              {/* [R402] 手机上指数名被压成 4px 宽 —— 也就是**一个字都看不见**。
                  `truncate` 里含 `overflow:hidden`, 而 flex 项一旦 overflow 不是
                  visible, 它的自动最小尺寸就变成 0 —— 于是它可以被旁边那三段
                  (代码/点位/涨跌幅)挤到没有。那三段都是短数字, 谁也不肯让,
                  最后让的全是标题。
                  改成: 整行可换行 + 标题不许被压, 放不下就整段挪到下一行。 */}
              <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
                <Activity className="h-4 w-4 shrink-0 text-accent" />
                <h2 className="shrink-0 truncate text-sm font-semibold text-foreground">
                  {selectedInfo?.name || selectedSymbol || '未选择指数'}
                </h2>
                {selectedSymbol && <span className="font-mono text-xs text-muted">{selectedSymbol}</span>}
                {selectedSymbol && <span className="font-mono text-xs text-foreground">{fmtNum(selectedQuoteValue)}</span>}
                {selectedSymbol && <span className={`font-mono text-xs ${Number(selectedQuotePct ?? 0) >= 0 ? 'text-bull' : 'text-bear'}`}>{fmtPct(selectedQuotePct)}</span>}
              </div>
              {/* [R545] 原「实时缓存 N 只指数 · 日K来源 x」—— 缓存条数是给开发者看的, 只留来源 */}
              <div className="mt-1 text-xs text-muted">日K来源 {daily.data?.source ?? '--'}</div>
            </div>
            {/* [R374] date inputs 窄屏换行: 两个 input + "至" 标签在窄屏挤,
                shrink-0 会顶破主区。加 flex-wrap 后窄屏自动第二行。 */}
            <div className="flex flex-wrap items-center gap-2 text-xs">
              <input
                type="date"
                value={range.start}
                onChange={e => setRange(r => ({ ...r, start: e.target.value }))}
                className="rounded-btn border border-border bg-base px-2 py-1 text-secondary outline-none focus:border-accent"
              />
              <span className="text-muted">至</span>
              <input
                type="date"
                value={range.end}
                onChange={e => setRange(r => ({ ...r, end: e.target.value }))}
                className="rounded-btn border border-border bg-base px-2 py-1 text-secondary outline-none focus:border-accent"
              />
            </div>
          </div>

          {daily.isLoading && <div className="py-10 text-center text-sm text-muted">日K加载中…</div>}
          {daily.isError && <div className="py-4 text-sm text-danger">指数日K加载失败</div>}
          {!daily.isLoading && !daily.isError && chartRows.length === 0 && (
            <div className="rounded-card bg-elevated p-6 text-center text-sm text-muted">
              暂无日K数据。可以先同步指数日K，或选择其他指数。
            </div>
          )}
          {chartRows.length > 0 && (
            <div className="flex flex-col gap-3 md:flex-row md:items-start">
              <div className="min-w-0 flex-1">
                <EChartsCandlestick
                  data={chartRows}
                  height={chartH}
                  showMA={true}
                  showInfoBar={true}
                  showMarkers={false}
                  symbol={selectedSymbol}
                  linkedPrice={linkedPrice}
                  onDateClick={(date) => {
                    setSelectedDate(date)
                    setLinkedPrice(null)
                  }}
                  visibleBars={48}
                  activeIndicators={['vol', 'macd']}
                />
              </div>
              <div className="min-w-0 flex-1 border-border max-md:border-t max-md:pt-3 md:border-l md:pl-3" style={{ height: chartH }}>
                {!hasMinuteCap ? (
                  <div className="flex h-full flex-col items-center justify-center gap-2 text-center">
                    <Lock className="h-5 w-5 text-muted" />
                    <div className="text-xs text-secondary">指数分时数据不可用</div>
                    <div className="text-micro text-muted">分钟K(批量)数据不可用</div>
                  </div>
                ) : (
                  <>
                    {minute.isLoading && <div className="py-2 text-xs text-muted">分时加载中…</div>}
                    {!minute.isLoading && minuteRows.length === 0 && (
                      <div className="flex h-full items-center justify-center text-xs text-muted">
                        暂无分时数据
                      </div>
                    )}
                    {minuteRows.length > 0 && (
                      <EChartsIntraday
                        key={`${selectedSymbol}:${selectedDate}`}
                        data={minuteRows}
                        height={chartH}
                        prevClose={prevClose}
                        date={selectedDate ?? undefined}
                        showLimitLines={false}
                        showAvgLine={false}
                        onPriceHover={setLinkedPrice}
                      />
                    )}
                  </>
                )}
              </div>
            </div>
          )}
        </main>
      </div>
    </PageShell>
  )
}
