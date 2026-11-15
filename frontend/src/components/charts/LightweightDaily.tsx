import { useMemo, useState } from 'react'
import type { SeriesMarker, Time } from 'lightweight-charts'
import type { ChartMarker, DailyChartProps, OHLC } from '@/lib/chart-types'
import { DAILY_LINE_COLORS, SUB_CHART_META, computeInstitutionSeries, volMaN, volumeRatioAt } from '@/lib/chart-indicators'
import { CHART_COLORS as C, lineData, validDailyRows, type PlotSeries } from '@/lib/lightweight-model'
import { fmtVolume, fmtPct, pricePrecision } from '@/lib/format'
import { CHART_LAYOUT, plotPaneHeights } from '@/lib/chart-layout'
import {
  quantPaneReadouts, quantPaneSeries, quantPaneTitle, trendPaneReadouts, trendPaneSeries, trendPaneTitle,
} from '@/lib/analysisPanes'
import { LEVEL_PALETTE, useChartTheme, useTheme, type Theme } from '@/lib/theme'
import { FinancialPlot } from './FinancialPlot'
import type { AnnotationData } from './ChartAnnotations'
import type { PaneDecorData, DecorItem } from './SubPaneDecor'

const fields = {
  macd: [['macd_dif', 'DIF', 'yellow'], ['macd_dea', 'DEA', 'plum']],
  rsi: [['rsi_6', 'RSI6', 'yellow'], ['rsi_14', 'RSI14', 'blue'], ['rsi_24', 'RSI24', 'plum']],
  kdj: [['kdj_k', 'K', 'yellow'], ['kdj_d', 'D', 'blue'], ['kdj_j', 'J', 'plum']],
} as const
// [R689] 均线五色与工具栏胶囊的色点共用同一份(`lib/chart-indicators`), 这里只补涨跌两色
const LINE_COLORS = {
  ...DAILY_LINE_COLORS,
  up: { dark: C.up, light: C.up },
  down: { dark: C.down, light: '#15803D' },
} as const
const maFields = [['ma5', 'gray'], ['ma10', 'blue'], ['ma20', 'orange'], ['ma60', 'plum']] as const
// [R704] 用户: 「默认开启所有MA价格显示变成只默认开启显示MA20和26日布林轨道的价格」——
// 换手下一行是固定读数, 与工具栏开关无关; 布林中轨就是 MA20 附近那个数, 不重复写。
// [R705] 用户: 「换手下一行的『26日布林』都删掉『26日』」—— 这一处读数只写「布林上轨 / 布林下轨」。
// [R713] 用户: 「MA们都放到布林轨前面」—— 四条均线全写出来, 排在上/下轨之前, 顺序 MA5 → MA60。
const READOUT_MA = maFields
const READOUT_BOLL = [['boll_upper', '布林上轨'], ['boll_lower', '布林下轨']] as const
/** [R714] 通达信 COLOr 常量按 BGR 排: COLOR0000FF = 红, COLOR00FF00 = 绿, COLORWHITE = 白。 */
const INST_COLORS = { up: '#FF0000', down: '#00FF00', text: '#FFFFFF' } as const

const price = (v: number | null | undefined, digits = 2) => v != null && Number.isFinite(v)
  ? (Number(v.toFixed(digits)) === 0 ? 0 : v).toFixed(digits) : '—'
const volume = (v: number | null | undefined) => v != null && Number.isFinite(v) && v >= 0 ? fmtVolume(v) : '—'
const EVENT_COLORS = {
  limit_up: { body: { dark: '#FACC15', light: '#CA8A04' }, label: { dark: '#FACC15', light: '#A16207' } },
  limit_down: { body: { dark: '#22D3EE', light: '#0891B2' }, label: { dark: '#67E8F9', light: '#0E7490' } },
  limit_down_recovery: { body: { dark: '#60A5FA', light: '#2563EB' }, bullBody: { dark: '#2DD4BF', light: '#0D9488' },
    label: { dark: '#93C5FD', light: '#1D4ED8' }, bullLabel: { dark: '#5EEAD4', light: '#0F766E' } },
  broken_limit_up: { body: { dark: '#8B5CF6', light: '#7C3AED' }, bullBody: { dark: '#A1887F', light: '#8D6E63' },
    label: { dark: '#A78BFA', light: '#7C3AED' } },
} as const
type EventMarker = ChartMarker & { event: NonNullable<ChartMarker['event']> }
const isEvent = (marker: ChartMarker): marker is EventMarker => marker.event === 'limit_up' || marker.event === 'broken_limit_up' || marker.event === 'limit_down' || marker.event === 'limit_down_recovery'
const EVENT_PRIORITY = { limit_down: 3, broken_limit_up: 2, limit_up: 1, limit_down_recovery: 0 } as const
const eventBodyColor = (event: EventMarker, row: OHLC, theme: Theme) => (event.event === 'broken_limit_up' || event.event === 'limit_down_recovery') && row.close > row.open
  ? EVENT_COLORS[event.event].bullBody[theme] : EVENT_COLORS[event.event].body[theme]
const eventTextColor = (event: EventMarker, row: OHLC, theme: Theme) => event.event === 'limit_down_recovery'
  ? EVENT_COLORS.limit_down_recovery[row.close > row.open ? 'bullLabel' : 'label'][theme]
  : event.event === 'limit_down' ? EVENT_COLORS.limit_down.label[theme] : eventBodyColor(event, row, theme)

export function LightweightDaily({ data, assetType, symbol = '', height = 480, activeIndicators = [], showMA = true, showInfoBar = true,
  markers = [], ranges, priceLines, showMarkers = true, markerStyle = 'candle', volumeCompare = { enabled: true, days: 1 }, addedDate,
  linkedPrice, onDateClick, onPriceDoubleClick, visibleBars, stockInfo, analysisPanes = [], maKeys,
  readoutExtra, dimLines = false,
  levelSeries = [], levelLines = [], levelRanges = [], levelLabels = [], levelVerticals = [],
  levelFuture = null, onCrosshairMove }: DailyChartProps) {
  const rows = useMemo(() => validDailyRows(data), [data])
  const precision = pricePrecision(assetType)
  const theme = useTheme()
  const ct = useChartTheme()
  const color = (key: keyof typeof LINE_COLORS) => LINE_COLORS[key][theme]
  // [R652] 均线逐条可控: 传了 maKeys 就只画列出来的那几条, 没传沿用 showMA 的四条全开/全关。
  const visibleMA = useMemo(
    () => maKeys ? maFields.filter(([key]) => maKeys.includes(key)) : showMA ? maFields : [],
    [maKeys, showMA])
  const volumeMAs = useMemo(() => ({ 5: volMaN(rows, 5), 10: volMaN(rows, 10) }), [rows])
  // [R714] 主力COME: 数值按通达信公式算, 画法(红空心柱/绿实心柱/红主力柱/白字)见下面 instDecor
  const instSeries = useMemo(() => computeInstitutionSeries(rows), [rows])
  const instDecor = useMemo<PaneDecorData>(() => {
    const items: DecorItem[] = []
    rows.forEach((row, idx) => {
      const point = instSeries[idx]
      if (point.inst > point.trend) {
        // STICKLINE(机构线-机构趋势>0, 机构线, 机构趋势, 3, 1), COLOR0000FF —— 空心
        items.push({ kind: 'hollow', time: row.date, from: point.trend, to: point.inst, color: INST_COLORS.up, widthPx: 3, dashed: false })
      } else if (point.inst < point.trend) {
        // STICKLINE(机构线-机构趋势<0, 机构线, 机构趋势, 3, 0), COLOR00FF00 —— 实心
        items.push({ kind: 'stick', time: row.date, from: point.trend, to: point.inst, color: INST_COLORS.down, widthPx: 3 })
      }
    })
    // STICKLINE(主力, 0, 50, 3, 0), COLORRED —— 画在上面那组之后, 与公式顺序一致
    rows.forEach((row, idx) => {
      if (instSeries[idx].mainForce) items.push({ kind: 'stick', time: row.date, from: 0, to: 50, color: INST_COLORS.up, widthPx: 3 })
    })
    // DRAWTEXT(主力信号, 60, '主力COME'), COLORWHITE
    rows.forEach((row, idx) => {
      if (instSeries[idx].mainSignal) items.push({ kind: 'note', time: row.date, value: 60, text: '主力COME', color: INST_COLORS.text })
    })
    return { items }
  }, [rows, instSeries])
  const scope = `${symbol}:${rows[0]?.date ?? ''}:${ranges?.map(range => `${range.start}:${range.end}`).join(';') ?? ''}`
  const [hover, setHover] = useState<{ scope: string; time: string } | null>(null)
  const index = hover?.scope === scope ? rows.findIndex(d => d.date === hover.time) : -1
  const i = index >= 0 ? index : rows.length - 1
  const current = rows[i], previous = rows[i - 1]
  const events = useMemo(() => {
    const result = new Map<string, EventMarker>()
    for (const marker of markers) if (isEvent(marker)) {
      const existing = result.get(marker.date)
      if (!existing || EVENT_PRIORITY[marker.event] > EVENT_PRIORITY[existing.event]) result.set(marker.date, marker)
    }
    return result
  }, [markers])
  // [R693] 用户: 「切换圆点和颜色不能导致主图高度有变化」—— 这段读数两种显示方式都出。
  // 原来只有「颜色」模式才显示, 那一段文字会让读数条在窄窗里多折一行, 整块高度就跟着跳;
  // 显示方式只该影响图上怎么画, 不该影响读数条的内容。
  const currentEvent = showMarkers && current ? events.get(current.date) : undefined
  const selected = useMemo(() => activeIndicators.filter(key => SUB_CHART_META.some(d => d.key === key)), [activeIndicators])
  const model = useMemo(() => {
    const series: PlotSeries[] = [{ id: 'price', type: 'Candlestick', pane: 0, data: rows.map(r => {
      const event = showMarkers && markerStyle === 'candle' ? events.get(r.date) : undefined
      return { time: r.date, open: r.open, high: r.high, low: r.low, close: r.close,
        ...(event ? { color: eventBodyColor(event, r, theme) } : {}),
      }
    }) }]
    const addLine = (id: string, values: ReturnType<typeof lineData>, color: string, pane = 0,
      options: Pick<PlotSeries, 'range' | 'precision' | 'priceFormat'> = {}) => {
      series.push({ id, type: 'Line', pane, data: values, color, ...options })
    }
    // [R709] 用户: 「悬浮的时候MA也在主图显示了」—— 悬停某个价位点位时, 价位线压到 12%,
    // 均线还是全亮, 对比之下像多画了一条。这里给均线同一档压暗(35%), 退出悬停恢复原色。
    for (const [key, token] of visibleMA) addLine(key, lineData(rows, key), dimLines ? `${color(token)}59` : color(token))
    selected.forEach((key, offset) => {
      const pane = offset + 1
      if (key === 'vol') {
        series.push({ id: 'volume', type: 'Volume', pane, priceFormat: 'volume', data: rows.map(r => ({
          time: r.date, value: r.volume ?? 0, color: r.close >= r.open ? 'rgba(199,64,64,0.55)' : 'rgba(45,155,101,0.55)',
        })) })
        for (const [n, token] of [[5, 'yellow'], [10, 'plum']] as const) {
          const ma = volumeMAs[n]
          addLine(`vol${n}`, rows.map((r, i) => ma[i] == null ? { time: r.date } : { time: r.date, value: ma[i]! }), color(token), pane, { priceFormat: 'volume' })
        }
      } else if (key === 'inst') {
        // 公式里 机构线 / 机构趋势 都是 `:=` 变量、不画线; 只留一条透明线把副图刻度钉在 0~100
        addLine('inst_scale', rows.map(r => ({ time: r.date, value: 50 })), 'rgba(0,0,0,0)', pane, { range: { min: 0, max: 100 } })
      } else {
        const lines = fields[key as keyof typeof fields]
        for (const [field, label, token] of lines) addLine(label, lineData(rows, field), color(token), pane,
          { range: key === 'rsi' ? { min: 0, max: 100 } : undefined, precision: key === 'macd' ? 3 : 1 })
        if (key === 'macd') series.push({ id: 'macd_hist', type: 'Histogram', pane, precision: 3, data: rows.map(r => r.macd_hist == null || !Number.isFinite(r.macd_hist) ? { time: r.date } : {
          time: r.date, value: r.macd_hist, color: `${color(r.macd_hist >= 0 ? 'up' : 'down')}99`,
        }) })
      }
    })
    return series
  }, [rows, visibleMA, selected, activeIndicators, events, markerStyle, showMarkers, theme, volumeMAs, dimLines])

  // [R649] 底部并入的分析副图(趋势量化 / 量化MACD): 排在各指标副图之后, 高度由调用方算好。
  // 与关键价位那张图同一份画法(`lib/analysisPanes.ts`), 这里只负责 pane 下标与版面。
  const analysis = useMemo(() => {
    const base = selected.length + 1
    const dates = rows.map(row => row.date)
    const bars = typeof visibleBars === 'number' ? visibleBars : rows.length
    const series: PlotSeries[] = []
    const decor: PaneDecorData[] = []
    const titles: string[] = []
    const readouts: NonNullable<AnnotationData['readouts']>[] = []
    const insets: number[] = []
    const headers: number[] = []
    const hidden: number[] = []
    analysisPanes.forEach((pane, offset) => {
      const index = base + offset
      hidden.push(index)
      insets.push(pane.topInset ?? 0)
      headers.push(pane.headerH ?? 0)
      if (pane.kind === 'trend') {
        const result = trendPaneSeries(dates, pane.data, !!pane.error, pane.height, bars, index)
        series.push(...result.series)
        decor.push(result.decor)
        titles.push(trendPaneTitle(!!pane.error))
        readouts.push(trendPaneReadouts(bars, pane.data, !!pane.error, ct.text))
      } else {
        const result = quantPaneSeries(dates, pane.data, !!pane.error, index)
        series.push(...result.series)
        decor.push(result.decor)
        titles.push(quantPaneTitle(!!pane.error))
        readouts.push(quantPaneReadouts(pane.data, !!pane.error, ct.text))
      }
    })
    return { series, decor, titles, readouts, insets, headers, hidden }
  }, [analysisPanes, rows, selected.length, visibleBars, ct.text])
  // [R654] 二型的「未来」三个空槽: 蜡烛时间轴往后多三格, 末尾三个位移均线值才画得出来。
  const plottedModel = useMemo(() => levelFuture
    ? model.map(item => item.id === 'price'
      ? { ...item, data: [...item.data, ...levelFuture.dates.map(time => ({ time }))] }
      : item)
    : model, [model, levelFuture])
  const plotSeries = useMemo(
    () => [...plottedModel, ...analysis.series, ...levelSeries],
    [plottedModel, analysis.series, levelSeries])

  const plotHeight = Math.max(260, height - (showInfoBar ? CHART_LAYOUT.readout : 0))
  const paneHeights = useMemo(() => {
    const reserved = analysisPanes.reduce((sum, pane) => sum + pane.height, 0)
    return [
      ...plotPaneHeights(Math.max(120, plotHeight - reserved), selected.length),
      ...analysisPanes.map(pane => pane.height),
    ]
  }, [plotHeight, selected.length, analysisPanes])
  const chartMarkers = useMemo<SeriesMarker<Time>[]>(() => showMarkers ? markers
    .filter(m => rows.some(r => r.date === m.date) && !(isEvent(m) && markerStyle === 'candle'))
    .sort((a, b) => a.date.localeCompare(b.date)).map(m => {
      const appearance: Pick<SeriesMarker<Time>, 'shape' | 'size'> = isEvent(m)
        ? { shape: 'circle', size: 0 }
        : { shape: m.kind === 'neutral' ? 'circle' : m.kind === 'buy' ? 'arrowUp' : 'arrowDown' }
      return {
        time: m.date, position: m.above || (m.kind === 'sell' && m.event !== 'limit_down' && m.event !== 'limit_down_recovery') ? 'aboveBar' : 'belowBar',
        color: isEvent(m) && (!m.color || m.color === EVENT_COLORS[m.event].body.dark)
          ? EVENT_COLORS[m.event].label[theme] : m.color ?? (m.kind === 'buy' ? C.up : m.kind === 'sell' ? C.down : '#F59E0B'),
        text: m.label ?? '', ...appearance,
      }
    }) : [], [markers, showMarkers, rows, markerStyle, theme])
  const annotations = useMemo(() => {
    const addedRow = addedDate ? rows.filter(r => r.date <= addedDate).at(-1) : null
    const verticals = addedRow ? [{ time: addedRow.date, label: '自选', color: '#3B82F6' }] : []
    return { dates: [...rows.map(r => r.date), ...(levelFuture?.labels ?? [])],
      ranges: [...(ranges ?? []), ...levelRanges],
      priceLines: [...(priceLines ?? []), ...levelLines],
      labels: levelLabels,
      verticals: [...verticals, ...levelVerticals],
    }
  }, [rows, ranges, priceLines, addedDate, levelLines, levelRanges, levelLabels, levelVerticals, levelFuture])
  const volumeLabels = useMemo(() => volumeCompare.enabled ? rows.flatMap((row, idx) => {
    const ratio = volumeRatioAt(rows, idx, volumeCompare.days)
    return ratio == null ? [] : [{ time: row.date, value: row.volume ?? 0, text: `${ratio.toFixed(1)}x` }]
  }) : [], [rows, volumeCompare.enabled, volumeCompare.days])
  const paneTitles = useMemo(
    () => ['', ...selected.map(key => SUB_CHART_META.find(d => d.key === key)!.label), ...analysis.titles],
    [selected, analysis.titles])
  const paneReadouts = useMemo(() => [[], ...selected.map(key => {
    const result: NonNullable<AnnotationData['readouts']> = []
    if (key === 'vol') {
      result.push({ text: `量 ${volume(current?.volume)}`, color: current ? color(current.close >= current.open ? 'up' : 'down') : undefined })
      for (const [n, token] of [[5, 'yellow'], [10, 'plum']] as const) result.push({ text: `VOL${n} ${volume(volumeMAs[n][i])}`, color: color(token) })
      if (volumeCompare.enabled) {
        const ratio = volumeRatioAt(rows, i, volumeCompare.days)
        result.push({ text: `量比 ${ratio == null ? '—' : `${ratio.toFixed(2)}x`}` })
      }
    } else if (key === 'inst') {
      // 通达信不显示这两条线的数值, 这里沿用副图读数习惯补上, 方便对照柱子
      const point = instSeries[i]
      result.push({ text: `机构线 ${price(point?.inst, 1)}` })
      result.push({ text: `趋势 ${price(point?.trend, 1)}` })
      if (point?.mainForce) result.push({ text: '主力', color: INST_COLORS.up })
    } else {
      for (const [field, label, token] of fields[key as keyof typeof fields]) result.push({ text: `${label} ${price(current?.[field], key === 'macd' ? 3 : 1)}`, color: color(token) })
      if (key === 'macd') result.push({ text: `MACD ${price(current?.macd_hist, 3)}`,
        color: current?.macd_hist == null || !Number.isFinite(current.macd_hist) ? undefined : color(current.macd_hist >= 0 ? 'up' : 'down') })
    }
    return result
  }), ...analysis.readouts], [selected, current, rows, i, volumeCompare.days, volumeCompare.enabled, theme, volumeMAs, instSeries, analysis.readouts])
  const change = previous?.close ? current.close / previous.close - 1 : null
  const turnover = stockInfo?.float_shares && current?.volume != null ? current.volume * 100 / stockInfo.float_shares : null

  return <div className="min-w-0" data-testid="lightweight-daily">
    {showInfoBar && <div className="min-h-[46px] border-b border-border/50 px-3 py-1 text-micro font-mono tabular-nums xl:h-[46px]">
      <div className="flex min-h-5 flex-wrap items-center gap-x-3 gap-y-1">
        <span className="font-medium text-foreground">{current?.date ?? '—'}</span>
        {currentEvent && <span style={{ color: eventTextColor(currentEvent, current, theme) }} title="阴阳按收盘价与开盘价判断，影线保留原来的涨跌色">
          {currentEvent.event === 'limit_down' ? '跌停' : currentEvent.event === 'broken_limit_up' || currentEvent.event === 'limit_down_recovery'
            ? `${currentEvent.event === 'broken_limit_up' ? '炸板' : '翘板'} · ${current.close > current.open ? '收阳' : current.close < current.open ? '收阴' : '开收同价'}`
            : currentEvent.label && /^\d+$/.test(currentEvent.label) ? `${currentEvent.label}连板` : '涨停'}
        </span>}
        {([['开', current?.open], ['高', current?.high], ['低', current?.low], ['收', current?.close]] as const).map(([name, value]) =>
          <span key={name} className="text-muted">{name} <span className="text-secondary">{price(value, precision)}</span></span>)}
        {change != null && <span style={{ color: change >= 0 ? C.up : C.down }}>{fmtPct(change)}</span>}
        {turnover != null && <span className="text-muted">换手 {fmtPct(turnover)}</span>}
        {/* [R696] 用户: 「异动 / 自选 / 回测 8% / 全部清除挪到换手后面, 保持右对齐」——
            ml-auto 把它们推到读数条右端, 不跟着「换手」贴在一起。 */}
        {readoutExtra && <div className="ml-auto flex items-center gap-1.5 pl-2">{readoutExtra}</div>}
      </div>
      <div className="mt-0.5 flex min-h-4 flex-wrap gap-x-4 gap-y-1 text-micro">
        {/* [R702] 用户: 「不能删除换手下面那一行原来显示的标签……原来日K里面怎么显示就怎么显示」——
            均线读数恢复成原来的「MA5 43.70」格式, 保留在换手下面这一行
            [R703] 不管有没有开 MA 开关都显示; [R704] 固定四条均线 + 布林上下轨; [R713] 均线全体排在布林轨前面。 */}
        {READOUT_MA.map(([field, token]) => <span key={field} style={{ color: color(token) }}>{field.toUpperCase()} {price(current?.[field], precision)}</span>)}
        {READOUT_BOLL.map(([field, label]) => <span key={field} style={{ color: LEVEL_PALETTE.boll[theme] }}>{label} {price(current?.[field], precision)}</span>)}
        {index >= 0 && previous && <span className="text-secondary">至今 <span style={{ color: rows.at(-1)!.close >= previous.close ? C.up : C.down }}>{fmtPct(rows.at(-1)!.close / previous.close - 1)}</span> · 周期 {rows.length - index}</span>}
      </div>
    </div>}
    <FinancialPlot scope={scope} series={plotSeries} height={plotHeight} paneHeights={paneHeights} pricePrecision={precision}
      paneTopInsets={[0, ...selected.map(() => 0), ...analysis.insets]}
      paneHeaderHeights={[0, ...selected.map(() => 0), ...analysis.headers]}
      paneDecor={[undefined, ...selected.map(key => key === 'inst' ? instDecor : undefined), ...analysis.decor]}
      hidePaneAxis={analysis.hidden.length ? analysis.hidden : undefined}
      markers={chartMarkers} annotations={annotations} volumeLabels={volumeLabels} paneTitles={paneTitles} paneReadouts={paneReadouts}
      linkedPrice={linkedPrice} visibleBars={visibleBars} currentPrice={rows.at(-1)?.close}
      onCrosshairMove={onCrosshairMove}
      onHover={time => setHover(time ? { scope, time } : null)} onSelect={onDateClick} onPriceDoubleClick={onPriceDoubleClick} />
  </div>
}
