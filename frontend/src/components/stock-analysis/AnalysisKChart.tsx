import { useEffect, useMemo, useState } from 'react'
import type { AnnotationData } from '@/components/charts/ChartAnnotations'
import { FinancialPlot } from '@/components/charts/FinancialPlot'
import { CHART_LAYOUT, plotPaneHeights } from '@/lib/chart-layout'
import {
  FIB2_ROLE_TARGET, LEVEL_CURVE_COLOR, QUANT_MACD_COLORS, TREND_QUANT_COLORS,
  fib2RoleColor, levelColors, useChartTheme, useLevelColors, useTheme,
} from '@/lib/theme'
import { alignQuantMacd, QUANT_MACD_HELP, QUANT_MACD_LEGEND } from '@/lib/quantMacdSeries'
import { alignTrendQuant, TREND_QUANT_HELP, TREND_QUANT_LEGEND, type TrendQuantData } from '@/lib/trendQuantSeries'
import { zhuangXianIndexes } from '@/lib/zhuangXianSeries'
import type { Fib2Grain, Fib2Overlay, KlineRow, LevelSeries, QuantMacdResult } from '@/lib/api'
import type { PlotData, PlotSeries } from '@/lib/lightweight-model'
import { fib2Status } from '@/lib/fib2Status'
import { Fib2GrainDialog } from './Fib2GrainDialog'
import {
  DEFAULT_LEVEL_TYPES, FIB2_BACKTEST_TITLE, FIB2_GRAINS, FIB2_TARGETS_TITLE, PIVOT_RANK_TITLES,
  levelGroupStat, useLevelControls, type LevelControls,
} from './levelControls'
import { LevelToolbar } from './LevelToolbar'
import {
  ANALYSIS_LABEL_BAND_PX, LEVEL_GROUPS, buildAnalysisChartModel, hitTestAnalysis, levelKey, strengthColor,
  type ChartMarker, type ChartRange, type LevelType, type PriceLevel,
} from './analysis-chart-model'

/**
 * 个股分析专用日 K 图表(TradingView lightweight-charts)。
 *
 * [上游 v0.3.34] 渲染层换成 `FinancialPlot`; 价位线 / 通道曲线 / 右侧标签 / 十字线
 * 命中判断抽到 `analysis-chart-model.ts`, 可脱离画布单测。
 *
 * [fork 移植] 在上游 lightweight 渲染之上保留牛来的全部增强:
 *   - 两档副图(pane 1 趋势量化 / pane 2 量化MACD), 取数失败在副图标题与读出处明示
 *   - 斐波那契二型(上攻段 / 回踩密集带 / 首次回踩 / 未来 3 格)
 *   - 六态关键点(livermore)与二型(fib2)两个价位组
 *   - 枢轴档位、二型粗细档 / 上攻推算位 / 粗细档回测、形态状态行、价位统计面板
 *
 * 与旧 ECharts 版的差异(均为渲染能力取舍):
 *   - 量化MACD 的金叉 / 死叉箭头图标省略(lightweight 无对应图元);
 *   - 趋势量化的「升 / 顶 / 下」等文字标记、狗头图标省略(副图没有 custom 系列),
 *     竖直 / 水平位置改由阅读图例与线本身判断;
 *   - 趋势量化的红绿短柱、吸筹白柱用 Histogram 近似(以东财口径从 0 起画,
 *     原图是从昨值画到今值)。
 */

export type { ChartMarker, ChartRange, LevelType, PriceLevel }
export { LEVEL_GROUPS, levelKey, strengthColor }
export type { LevelControls }

// ===== 价位类型(与后端 levels.py 的 LEVEL_TYPES 对齐) =====
// 上游 11 类 + fork 的 livermore / fib2, 单一产地在 analysis-chart-model.ts。

/**
 * 图上**实际画的**那份价位: 二型按选中的粗细档换掉, 再减线。
 *
 * [R430] 个股弹窗右侧那张列表也按同一份数「画了几条」, 避免列表与图各算各的。
 */
export function useShownLevels(
  levels: Record<LevelType, PriceLevel[]> | undefined,
  fib2: Fib2Overlay | undefined,
  rows: KlineRow[],
  fib2Grain: Fib2Grain,
  fib2ShowTargets: boolean,
) {
  // [R406] 选中档的线顶掉默认那一组。后端一次给三档, 切档不用重新请求。
  const fib2Zone = fib2?.grain?.[fib2Grain]?.zone ?? null
  const fib2Raw = fib2?.grain?.[fib2Grain]?.levels ?? null
  const close = rows.at(-1)?.close
  const fib2Shown = useMemo(
    () => (fib2Raw ? thinFib2(fib2Raw, close, fib2Zone, fib2ShowTargets) : null),
    [fib2Raw, close, fib2Zone, fib2ShowTargets])
  const effLevels = useMemo(
    () => (fib2Shown && levels ? { ...levels, fib2: fib2Shown } : levels),
    [levels, fib2Shown])
  return { effLevels, fib2Raw, fib2Zone }
}

interface Props {
  rows: KlineRow[]
  levels?: Record<LevelType, PriceLevel[]>
  /** 带状曲线指标(布林带/Keltner/ATR)的每日序列 —— 画成跟随时间漂移的曲线 */
  series?: LevelSeries
  /** series 数据对应的日期数组(与 series 各数组对齐) */
  seriesDates?: string[]
  /** 默认开启的价位组; 不传 = 只开量化通道短期 */
  defaultLevelTypes?: LevelType[]
  /** [R430] 开关状态由外面持有(个股弹窗), 切视图再切回来开着的那几类还在 */
  controls?: LevelControls
  /** [R430] 默认显示最近多少根 K 线 */
  visibleBars?: number
  /** 预留:新闻/暴雷/利好日期标记 */
  markers?: ChartMarker[]
  /** 预留:事件区间高亮 */
  ranges?: ChartRange[]
  /** [R405] 斐波那契二型里画不成横线的那几样(密集带 / 上攻段 / 首次回踩 / 未来均线) */
  fib2?: Fib2Overlay
  /** [R412] 标的代码 —— 只为「粗细档回测」按钮用 */
  symbol?: string
  /** [R415] 副图「量化MACD」的逐根数值 */
  quantMacd?: QuantMacdResult
  /** [R426] 量化MACD 取数失败 —— 副图里明说, 不让空白冒充"没有信号" */
  quantMacdError?: boolean
  /** [R486] 副图「趋势量化」的逐根数值 */
  trendQuant?: TrendQuantData
  /** [R486] 趋势量化取数失败 —— 同样在副图里明说 */
  trendQuantError?: boolean
  /** 预留:点击某根 K 线 */
  onDateClick?: (date: string) => void
  /**
   * 主图按这个高度算; 两个副图在它之外另加, 所以整张图比它高。
   * 版面高度走 `plotPaneHeights` / `CHART_LAYOUT`。
   */
  height?: number
  className?: string
}

const QUANT_MACD_LEGEND_COLORS: Record<string, string> = {
  diff: QUANT_MACD_COLORS.red,
  dea: QUANT_MACD_COLORS.darkRed,
  yellow: QUANT_MACD_COLORS.yellow,
  gold: QUANT_MACD_COLORS.yellow,
  dead: QUANT_MACD_COLORS.green,
}

/** [R560] 量化MACD 图例: 名字 + 色块, 悬停看全量说明。 */
function quantMacdLegendGraphic() {
  return (
    <span title={QUANT_MACD_HELP} className="inline-flex flex-wrap items-center gap-x-2 gap-y-0.5">
      {QUANT_MACD_LEGEND.map(item => (
        <span key={item.key} title={`${item.name}: ${item.desc}`}
              className="inline-flex items-center gap-1 text-micro text-muted-foreground">
          <span className="h-1.5 w-2.5 rounded-[1px]" style={{ backgroundColor: QUANT_MACD_LEGEND_COLORS[item.key] }} />
          {item.name}
        </span>
      ))}
    </span>
  )
}

/** [R555] 趋势量化图例: 线上已写名字的那几根不重复印, 悬停仍给说明。 */
function trendQuantLegendGraphic() {
  return (
    <span title={TREND_QUANT_HELP} className="inline-flex flex-wrap items-center gap-x-2 gap-y-0.5">
      {TREND_QUANT_LEGEND.filter(item => !item.labelledOnLine).map(item => (
        <span key={item.name} title={`${item.name}: ${item.desc}`}
              className="inline-flex items-center gap-1 text-micro text-muted-foreground">
          <span className="h-0.5 w-2.5" style={{ backgroundColor: item.color }} />
          {item.name}
        </span>
      ))}
    </span>
  )
}

export function AnalysisKChart({
  rows,
  levels,
  series,
  seriesDates,
  // [R208] 默认勾上量化通道短期 —— 决策台整张表都在用它判位置。
  defaultLevelTypes = DEFAULT_LEVEL_TYPES,
  controls,
  visibleBars = 120,
  markers,
  ranges,
  fib2,
  symbol,
  quantMacd,
  quantMacdError = false,
  trendQuant,
  trendQuantError = false,
  onDateClick,
  height = 460,
  className,
}: Props) {
  const theme = useTheme()
  const ct = useChartTheme()
  // [R430] 开关状态: 外面传了就听外面的, 没传自己持有。
  const ownControls = useLevelControls(defaultLevelTypes)
  const ctl = controls ?? ownControls
  const { activeTypes, pivotRank, fib2Grain, fib2ShowTargets } = ctl

  const [fib2FitOpen, setFib2FitOpen] = useState(false)
  /** 双向联动高亮: hover 价位标签 ↔ hover 下方文字行。值为 levelKey, null=无高亮 */
  const [hoveredKey, setHoveredKey] = useState<string | null>(null)

  const { effLevels, fib2Raw, fib2Zone } = useShownLevels(levels, fib2, rows, fib2Grain, fib2ShowTargets)
  // [R411] 形态状态行读整档 `fib2Raw`(不是减线后的), 说的是形态不是"画了几条"。
  const fib2Line = useMemo(() => fib2Status({
    dates: rows.map(row => (typeof row.date === 'string' ? row.date.slice(0, 10) : String(row.date))),
    close: rows.at(-1)?.close,
    thrust: fib2?.thrust,
    markers: fib2?.markers,
    zone: fib2Zone,
    levels: fib2Raw ?? [],
  }), [rows, fib2, fib2Zone, fib2Raw])

  // [R409] 当前主题下的价位组配色; 单一产地在 lib/theme.ts。
  const LC = useMemo(() => levelColors(theme), [theme])
  const roleColor = useMemo(() => (role: string) => fib2RoleColor(role, theme), [theme])
  const targetColor = fib2RoleColor(FIB2_ROLE_TARGET, theme)

  const model = useMemo(() => buildAnalysisChartModel({
    rows, levels: effLevels, series, seriesDates, activeTypes, pivotRank, hoveredKey, markers, ranges,
    colors: { ...LC, ...LEVEL_CURVE_COLOR }, roleColor,
  }), [rows, effLevels, series, seriesDates, activeTypes, pivotRank, hoveredKey, markers, ranges, LC, roleColor])

  /**
   * [R413] 斐波那契二型的「未来」区 —— 位移均线露出最后一根之外的 3 个值。
   *
   * 数据全是已收盘的, 只是画到右边; 二型开关没开时整块为空, 图的其余部分
   * 与没有这段时完全一致。lightweight 的时间轴只接受真实日期, 所以末尾追加
   * 三个「下一个工作日」的空槽, 并把 `未来1..3` 作为右侧标签写进 annotations。
   */
  const futureVals = useMemo(
    () => (activeTypes.has('fib2') ? (fib2?.dma3_future ?? []) : []),
    [activeTypes, fib2])
  const future = useMemo(() => {
    if (!futureVals.length || !model.dates.length) return null
    const dates = nextBusinessDates(model.dates.at(-1)!, futureVals.length)
    if (dates.length !== futureVals.length) return null
    return { dates, labels: futureVals.map((_, index) => `未来${index + 1}`), values: futureVals }
  }, [futureVals, model.dates])

  // 主图 + 两个副图: 主图保持 `height` 的可视高度, 副图另加两格。
  const plotHeight = height + 2 * CHART_LAYOUT.subPaneSlot
  const paneHeights = useMemo(() => plotPaneHeights(plotHeight, 2), [plotHeight])

  // 取数失败 / 尚未到达时, 副图仍保留一块区域并写明状态。
  const trendTitle = trendQuantError ? '趋势量化 · 取数失败' : '趋势量化'
  const quantTitle = quantMacdError ? '量化MACD · 取数失败' : '量化MACD'
  const trendReadouts: AnnotationData['readouts'] = trendQuantError
    ? [{ text: '取数失败, 稍后刷新重试', color: ct.text }]
    : trendQuant
      ? [
        { text: '平均线', color: TREND_QUANT_COLORS.avg },
        { text: '吸筹', color: TREND_QUANT_COLORS.xichou },
        { text: '超买 3.2 / 超卖 0.5', color: TREND_QUANT_COLORS.yellow },
      ]
      : [{ text: '等待数据', color: ct.text }]
  const quantReadouts: AnnotationData['readouts'] = quantMacdError
    ? [{ text: '取数失败, 稍后刷新重试', color: ct.text }]
    : quantMacd
      ? [
        { text: 'DIFF', color: QUANT_MACD_COLORS.red },
        { text: 'DEA', color: QUANT_MACD_COLORS.darkRed },
        { text: '共振', color: QUANT_MACD_COLORS.yellow },
      ]
      : [{ text: '等待数据', color: ct.text }]

  const chartSeries = useMemo(() => {
    const main: PlotSeries[] = model.series
      .filter(item => item.id !== 'volume')
      .map(item => {
        if (!future) return item
        if (item.id === 'price') {
          return { ...item, data: [...item.data, ...future.dates.map(time => ({ time }))] }
        }
        if (item.id === 'curve:fib2_dma3') {
          return {
            ...item,
            data: [
              ...item.data,
              ...future.values.map((value, index) => ({ time: future.dates[index], value })),
            ],
          }
        }
        return item
      })
    return [
      ...main,
      ...trendPaneSeries(model.dates, trendQuant, trendQuantError),
      ...quantPaneSeries(model.dates, quantMacd, quantMacdError),
    ]
  }, [model, future, trendQuant, trendQuantError, quantMacd, quantMacdError])

  const annotations = useMemo<AnnotationData>(() => {
    const dates = future ? [...model.dates, ...future.labels] : model.dates
    const priceLines = [...(model.annotations.priceLines ?? [])]
    const extraRanges = [...(model.annotations.ranges ?? [])]
    const labels = [...(model.annotations.labels ?? [])]
    const verticals: NonNullable<AnnotationData['verticals']> = []

    // [R413] 现价贴签 —— 用来量「还差多少到位」。
    const lastClose = model.rows.at(-1)?.close
    if (lastClose != null && Number.isFinite(lastClose)) {
      priceLines.push({
        value: lastClose,
        label: `现价 ${lastClose.toFixed(2)}`,
        color: ct.text,
        opacity: 0.45,
        labelPriority: 4,
      })
    }

    if (activeTypes.has('fib2') && fib2) {
      // 上攻段: lightweight 没有价格区间填充, 用 annotations.ranges 铺竖向底色。
      const thrust = fib2.thrust
      const thrustStart = thrust ? normalizeDate(thrust.start) : null
      const thrustEnd = thrust ? normalizeDate(thrust.end) : null
      if (thrust && thrustStart && thrustEnd && model.dateIndex.has(thrustStart) && model.dateIndex.has(thrustEnd)) {
        extraRanges.push({
          start: thrustStart,
          end: thrustEnd,
          label: `单边上攻 ${thrust.days} 天`,
          color: theme === 'dark' ? 'rgba(210,70,59,0.20)' : 'rgba(210,70,59,0.13)',
        })
      }
      // 回踩密集带: 两条 priceLines 表示上下沿并带文字(lightweight 不支持价格区间填充)。
      const zone = fib2Zone
      if (zone && zone.high > 0) {
        const thin = Math.max(0, (lastClose ?? zone.high) * 0.003 - (zone.high - zone.low)) / 2
        priceLines.push({
          value: Math.max(0, zone.low - thin),
          label: `回踩密集带下沿 ${zone.low.toFixed(2)}`,
          color: LC.fib2,
          opacity: 0.9,
          labelPriority: 2,
        })
        priceLines.push({
          value: zone.high + thin,
          label: `回踩密集带上沿 ${zone.high.toFixed(2)} · ${zone.strength} 条挤在一起`,
          color: LC.fib2,
          opacity: 0.9,
          labelPriority: 2,
        })
      }
      // 首次回踩等标记
      for (const marker of fib2.markers ?? []) {
        const date = normalizeDate(marker.date)
        const index = date ? model.dateIndex.get(date) : undefined
        if (index == null) continue
        labels.push({
          time: model.rows[index].date,
          value: model.rows[index].high,
          text: marker.label,
          color: LC.fib2,
        })
      }
      // 「未来」分隔线 —— 只在真有未来均线值时出现。
      if (future) {
        verticals.push({ time: future.dates[0], label: '未来', color: ct.text })
      }
    }

    return {
      ...model.annotations,
      dates,
      priceLines,
      ...(extraRanges.length ? { ranges: extraRanges } : {}),
      ...(labels.length ? { labels } : {}),
      ...(verticals.length ? { verticals } : {}),
    }
  }, [model, future, activeTypes, fib2, fib2Zone, LC.fib2, ct.text, theme])

  // [R488] 狗头(庄现)只画在趋势量化的主线上, 不跨到量化MACD。
  const chartDates = useMemo(() => (future ? [...model.dates, ...future.labels] : model.dates), [model.dates, future])
  const zhuanMarkers = useMemo(() => zhuangXianIndexes(chartDates, trendQuant).map(index => ({
    time: chartDates[index],
    position: 'belowBar' as const,
    shape: 'circle' as const,
    text: '庄',
    color: TREND_QUANT_COLORS.avg,
    size: 1,
  })), [chartDates, trendQuant])

  const scope = `${symbol ?? ''}:${model.rows[0]?.date ?? ''}:${model.rows.length}:${visibleBars}:${future?.dates.length ?? 0}`

  // 切股 / 区间变化后清掉上一份数据的悬浮高亮
  useEffect(() => { setHoveredKey(null) }, [scope])
  // 关闭价位组后, 被关掉的点位不应继续高亮
  useEffect(() => {
    setHoveredKey(previous => previous != null && !model.hoverKeys.has(previous) ? null : previous)
  }, [model.hoverKeys])

  return (
    <div className={className}>
      {/* 开关由外面持有时(个股弹窗)画方形按钮那一排, 位置与老入口相同 */}
      {levels && controls && (
        <LevelToolbar groups={LEVEL_GROUPS} controls={controls} effLevels={effLevels}
                      fib2Raw={fib2Raw} fib2={fib2}
                      onOpenFit={symbol ? () => setFib2FitOpen(true) : undefined} />
      )}
      {levels && !controls && (
        <div className="flex flex-wrap content-start items-center gap-1.5 mb-2">
          <span className="text-micro text-muted mr-1 shrink-0">关键价位</span>
          {LEVEL_GROUPS.map(group => {
            const active = activeTypes.has(group.key)
            const { count, total, title } = levelGroupStat(group.key, group.label, effLevels, fib2Raw, pivotRank)
            return (
              <button
                key={group.key}
                onClick={() => ctl.toggleType(group.key)}
                disabled={total === 0}
                title={title}
                className={`inline-flex shrink-0 whitespace-nowrap items-center gap-1 h-6 px-2 rounded-btn text-micro font-medium border transition-ui disabled:opacity-30 disabled:cursor-not-allowed ${
                  active
                    ? 'text-foreground'
                    : 'text-muted bg-base/40 border-border/30 hover:border-border/60'
                }`}
                style={active ? { borderColor: LC[group.key] + '66', backgroundColor: LC[group.key] + '1a' } : undefined}
              >
                <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: active ? LC[group.key] : '#52525B' }} />
                {group.label}
                <span className="opacity-50">{count}</span>
              </button>
            )
          })}

          {/* 枢轴点档位选择器 —— 仅当枢轴点开启时显示 */}
          {activeTypes.has('pivot') && (levels.pivot?.length ?? 0) > 0 && (
            <div className="inline-flex shrink-0 items-center gap-0.5 ml-1 pl-2 border-l border-border/40">
              <span className="text-micro text-muted mr-1">档位</span>
              {([1, 2, 3] as const).map(rank => (
                <button
                  key={rank}
                  onClick={() => ctl.setPivotRank(rank)}
                  title={PIVOT_RANK_TITLES[rank]}
                  className={`h-6 px-2 rounded-btn text-micro font-mono border transition-ui ${
                    pivotRank === rank
                      ? 'text-foreground'
                      : 'text-muted bg-base/40 border-border/30 hover:border-border/60'
                  }`}
                  style={pivotRank === rank
                    ? { borderColor: LC.pivot + '66', backgroundColor: LC.pivot + '26', color: LC.pivot }
                    : undefined}
                >
                  {rank}
                </button>
              ))}
            </div>
          )}

          {/* [R406] 斐波那契二型的粗细档 —— 仅当这一组开启时显示 */}
          {activeTypes.has('fib2') && fib2?.grain && (
            <div className="inline-flex shrink-0 items-center gap-0.5 ml-1 pl-2 border-l border-border/40">
              <span className="text-micro text-muted mr-1">粗细</span>
              {FIB2_GRAINS.map(([key, cn, tip]) => (
                <button
                  key={key}
                  onClick={() => ctl.setFib2Grain(key)}
                  title={tip}
                  className={`h-6 px-2 rounded-btn text-micro border transition-ui whitespace-nowrap ${
                    fib2Grain === key
                      ? 'text-foreground'
                      : 'text-muted bg-base/40 border-border/30 hover:border-border/60'
                  }`}
                  style={fib2Grain === key
                    ? { borderColor: LC.fib2 + '66', backgroundColor: LC.fib2 + '26', color: LC.fib2 }
                    : undefined}
                >
                  {cn}
                  <span className="ml-1 opacity-50 font-mono">
                    {fib2.grain?.[key]?.levels.length ?? 0}
                  </span>
                </button>
              ))}
              <button
                onClick={() => ctl.setFib2ShowTargets(value => !value)}
                title={FIB2_TARGETS_TITLE}
                className={`h-6 px-2 rounded-btn text-micro border transition-ui whitespace-nowrap ml-0.5 ${
                  fib2ShowTargets
                    ? 'text-foreground'
                    : 'text-muted bg-base/40 border-border/30 hover:border-border/60'
                }`}
                style={fib2ShowTargets
                  ? { borderColor: targetColor + '66', backgroundColor: targetColor + '26', color: targetColor }
                  : undefined}
              >
                上攻推算位
              </button>
              {symbol && (
                <button
                  onClick={() => setFib2FitOpen(true)}
                  title={FIB2_BACKTEST_TITLE}
                  className="ml-0.5 h-6 rounded-btn border border-border/30 bg-base/40 px-2 text-micro text-muted transition-ui hover:border-border/60 hover:text-foreground"
                >
                  回测这三档
                </button>
              )}
            </div>
          )}
        </div>
      )}

      {/* [R411] 形态走到哪一步 —— 只报事实, 一个动词都没有 */}
      {activeTypes.has('fib2') && fib2Line && (
        <div className="mb-2 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-micro leading-5">
          <span className="h-1.5 w-1.5 shrink-0 rounded-full" style={{ backgroundColor: LC.fib2 }} />
          {fib2Line.map((segment, index) => (
            <span key={segment} className={index === 0 ? 'text-secondary' : 'text-muted'}>
              {index > 0 && <span className="mr-2 opacity-40">·</span>}
              {segment}
            </span>
          ))}
        </div>
      )}
      {fib2FitOpen && symbol && (
        <Fib2GrainDialog
          symbol={symbol}
          current={fib2Grain}
          onPick={ctl.setFib2Grain}
          onClose={() => setFib2FitOpen(false)}
        />
      )}

      {/* [R555/R560] 两个副图的图例并排放在图上方, 名字与悬停说明都在 */}
      <div className="mb-1 flex flex-wrap items-center gap-x-4 gap-y-1 text-micro">
        <span className="inline-flex items-center gap-2">
          <span className="text-muted">趋势量化</span>
          {trendQuantLegendGraphic()}
        </span>
        <span className="inline-flex items-center gap-2">
          <span className="text-muted">量化MACD</span>
          {quantMacdLegendGraphic()}
        </span>
      </div>

      {/* 图表:右侧留白带(rightOffsetPixels)显示价位/曲线标签,不压蜡烛 */}
      <FinancialPlot
        scope={scope}
        series={chartSeries}
        height={plotHeight}
        paneHeights={paneHeights}
        pricePrecision={2}
        visibleBars={visibleBars + (future?.dates.length ?? 0)}
        currentPrice={model.rows.at(-1)?.close}
        rightOffsetPixels={ANALYSIS_LABEL_BAND_PX}
        annotations={annotations}
        paneTitles={['', trendTitle, quantTitle]}
        paneReadouts={[[], trendReadouts, quantReadouts]}
        seriesMarkers={zhuanMarkers.length ? { 'tq:wave': zhuanMarkers } : undefined}
        onSelect={date => onDateClick?.(date)}
        onCrosshairMove={point => {
          if (!point) { setHoveredKey(null); return }
          const index = model.dateIndex.get(point.time) ?? -1
          const next = index < 0 ? null : hitTestAnalysis(model, point.price, point.pixelsPerPrice, index)
          setHoveredKey(previous => previous === next ? previous : next)
        }}
      />

      {/* 价位统计面板:把当前开启的点位按"压力 / 支撑"结构化列出 */}
      {effLevels && (
        <LevelOverview
          levels={effLevels}
          activeTypes={activeTypes}
          pivotRank={pivotRank}
          close={model.rows.length ? model.rows[model.rows.length - 1].close : undefined}
          hoveredKey={hoveredKey}
          onHover={setHoveredKey}
        />
      )}
    </div>
  )
}

// ===== 副图: 趋势量化 =====
function trendPaneSeries(dates: string[], trendQuant: TrendQuantData | undefined, error: boolean): PlotSeries[] {
  if (error || !trendQuant || dates.length === 0) return [emptyPaneSeries('tq:empty', 1, dates)]
  const data = alignTrendQuant(dates, trendQuant)
  const C = TREND_QUANT_COLORS
  if (!data.wave.some(value => value != null)) return [emptyPaneSeries('tq:empty', 1, dates)]

  // 红绿短柱: 原图从昨值画到今值, lightweight Histogram 只能从 0 起画,
  // 这里用「今值 - 昨值」的幅度 + stick_up 决定颜色做近似。
  const sticks: PlotData[] = data.wave.map((wave, index) => {
    const previous = data.wave_prev[index]
    const up = data.stick_up[index]
    if (wave == null || previous == null || up == null) return { time: dates[index] }
    return { time: dates[index], value: wave - previous, color: up === 1 ? C.red : C.green }
  })
  // 吸筹白柱: 原图从 0.53 画到吸筹值, 同理从 0 起画差值。
  const whites: PlotData[] = data.xichou.map((xichou, index) => {
    if (data.xichou_bar[index] !== 1 || xichou == null) return { time: dates[index] }
    return { time: dates[index], value: xichou - 0.53, color: C.white }
  })

  return [
    emptyPaneSeries('tq:base', 1, dates),
    { id: 'tq:ref_high', type: 'Line', pane: 1, color: C.yellow, data: dates.map(time => ({ time, value: 3.2 })) },
    { id: 'tq:ref_low', type: 'Line', pane: 1, color: C.yellow, data: dates.map(time => ({ time, value: 0.5 })) },
    { id: 'tq:wave', type: 'Line', pane: 1, color: C.red, lineWidth: 1, data: valuePoints(dates, data.wave) },
    { id: 'tq:wave_prev', type: 'Line', pane: 1, color: C.green, lineWidth: 1, data: valuePoints(dates, data.wave_prev) },
    { id: 'tq:avg', type: 'Line', pane: 1, color: C.avg, lineWidth: 1, data: valuePoints(dates, data.avg) },
    { id: 'tq:stick', type: 'Histogram', pane: 1, color: C.red, data: sticks },
    { id: 'tq:xichou_bar', type: 'Histogram', pane: 1, color: C.white, data: whites },
    { id: 'tq:xichou', type: 'Line', pane: 1, color: C.xichou, lineWidth: 1, data: valuePoints(dates, data.xichou) },
  ]
}

// ===== 副图: 量化MACD =====
function quantPaneSeries(dates: string[], quantMacd: QuantMacdResult | undefined, error: boolean): PlotSeries[] {
  if (error || !quantMacd || dates.length === 0) return [emptyPaneSeries('qm:empty', 2, dates)]
  const data = alignQuantMacd(dates, quantMacd)
  const C = QUANT_MACD_COLORS
  if (!data.diff.some(value => value != null)) return [emptyPaneSeries('qm:empty', 2, dates)]

  // 涨红跌绿: 正负两段拆成两条线, 另一段用空槽断开。
  return [
    emptyPaneSeries('qm:base', 2, dates),
    { id: 'qm:diff_up', type: 'Line', pane: 2, color: C.red, lineWidth: 1, data: splitBySign(dates, data.diff, true) },
    { id: 'qm:diff_down', type: 'Line', pane: 2, color: C.green, lineWidth: 1, data: splitBySign(dates, data.diff, false) },
    { id: 'qm:dea_up', type: 'Line', pane: 2, color: C.darkRed, lineWidth: 1, data: splitBySign(dates, data.dea, true) },
    { id: 'qm:dea_down', type: 'Line', pane: 2, color: C.green, lineWidth: 1, data: splitBySign(dates, data.dea, false) },
    // 黄柱 = DEA/4(共振), 从 0 起画, 只看出没出现。
    { id: 'qm:yellow', type: 'Histogram', pane: 2, color: C.yellow, data: valuePoints(dates, data.yellow) },
    // 金叉 / 死叉箭头图标: lightweight 无对应图元, 省略。
  ]
}

/** 一块空的副图仍保留 pane 与标题(取数失败 / 加载中时不让副图消失)。 */
function emptyPaneSeries(id: string, pane: number, dates: string[]): PlotSeries {
  return { id, type: 'Line', pane, color: 'transparent', lineWidth: 1, data: dates.map(time => ({ time })) }
}

function valuePoints(dates: string[], values: (number | null)[]): PlotData[] {
  return values.map((value, index) =>
    value == null || !Number.isFinite(value) ? { time: dates[index] } : { time: dates[index], value })
}

function splitBySign(dates: string[], values: (number | null)[], positive: boolean): PlotData[] {
  return values.map((value, index) => {
    if (value == null || !Number.isFinite(value) || (value >= 0) !== positive) return { time: dates[index] }
    return { time: dates[index], value }
  })
}

function normalizeDate(date: string): string {
  return typeof date === 'string' ? date.slice(0, 10) : ''
}

/** 从最后一根往后数 `count` 个工作日(不含节假日), 给二型的「未来」空槽用。 */
function nextBusinessDates(last: string, count: number): string[] {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(last)) return []
  const out: string[] = []
  const date = new Date(`${last}T00:00:00Z`)
  while (out.length < count) {
    date.setUTCDate(date.getUTCDate() + 1)
    const day = date.getUTCDay()
    if (day === 0 || day === 6) continue
    out.push(date.toISOString().slice(0, 10))
  }
  return out
}

// ===== 价位统计面板(图表下方,结构化文本展示) =====
function LevelOverview({
  levels, activeTypes, pivotRank, close, hoveredKey, onHover,
}: {
  levels: Record<LevelType, PriceLevel[]>
  activeTypes: Set<LevelType>
  pivotRank: 1 | 2 | 3
  close?: number
  hoveredKey: string | null
  onHover: (key: string | null) => void
}) {
  const theme = useTheme()
  const ct = useChartTheme()
  const palette = useLevelColors()
  // 收集当前显示的点位(同 collectPriceLines 的过滤逻辑)
  const visible: PriceLevel[] = []
  for (const group of LEVEL_GROUPS) {
    if (!activeTypes.has(group.key)) continue
    for (const point of levels[group.key] ?? []) {
      if (point.type === 'pivot' && point.rank !== undefined && point.rank > pivotRank) continue
      visible.push(point)
    }
  }
  if (visible.length === 0) return null

  // 按方向分两组:压力位(在当前价之上) / 支撑位(之下),各自按距当前价远近排序
  const cur = close ?? visible[0].value
  const resistances = visible
    .filter(point => point.side === 'resistance')
    .sort((a, b) => a.value - b.value)        // 由近及远(低→高)
  const supports = visible
    .filter(point => point.side === 'support')
    .sort((a, b) => b.value - a.value)         // 由近及远(高→低)
  const neutrals = visible.filter(point => point.side === 'neutral')

  const fmtPct = (value: number) => {
    if (!cur) return ''
    const pct = ((value - cur) / cur) * 100
    const sign = pct >= 0 ? '+' : ''
    return `${sign}${pct.toFixed(1)}%`
  }

  const Row = ({ point }: { point: PriceLevel }) => {
    const color = (point.color ? fib2RoleColor(point.color, theme) : palette[point.type]) ?? ct.text
    const key = levelKey(point.type, point.value)
    const hit = hoveredKey === key
    const dim = hoveredKey != null && !hit
    return (
      <div
        onMouseEnter={() => onHover(key)}
        onMouseLeave={() => onHover(null)}
        className={`flex items-center gap-2 py-0.5 px-1.5 -mx-1.5 rounded-btn transition-ui cursor-default ${
          hit ? 'bg-elevated/60' : ''
        }`}
        style={dim ? { opacity: 0.35 } : undefined}
      >
        <span className="h-1.5 w-1.5 rounded-full shrink-0 transition-transform" style={{ backgroundColor: color, transform: hit ? 'scale(1.5)' : 'scale(1)' }} />
        <span className={`text-xs w-24 shrink-0 truncate ${hit ? 'text-foreground font-medium' : 'text-secondary'}`}>{point.label}</span>
        <span className={`text-xs font-mono ${hit ? 'text-foreground font-bold' : 'text-foreground'}`}>{point.value.toFixed(2)}</span>
        <span className="text-micro font-mono text-muted">{fmtPct(point.value)}</span>
      </div>
    )
  }

  return (
    <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-1 rounded-card border border-border/40 bg-base/20 px-3 py-2">
      {/* 当前价 */}
      <div className="sm:col-span-2 flex items-center gap-2 pb-1 border-b border-border/30 mb-0.5">
        <span className="text-micro text-muted">当前价</span>
        <span className="text-xs font-mono font-medium text-foreground">{cur.toFixed(2)}</span>
      </div>
      {/* 压力位(从近到远,即从低到高)倒序展示:最高的在最上 */}
      {resistances.length > 0 && (
        <div>
          <div className="text-micro font-medium text-bear mb-0.5">压力位 ↑</div>
          {[...resistances].reverse().map((point, index) => <Row key={`r-${index}`} point={point} />)}
        </div>
      )}
      {/* 支撑位 + 中性(枢轴位 P) */}
      <div>
        {supports.length > 0 && (
          <>
            <div className="text-micro font-medium text-bull mb-0.5">支撑位 ↓</div>
            {supports.map((point, index) => <Row key={`s-${index}`} point={point} />)}
          </>
        )}
        {neutrals.length > 0 && (
          <div className={supports.length > 0 ? 'mt-2' : ''}>
            {supports.length === 0 && <div className="text-micro font-medium text-muted mb-0.5">枢轴位</div>}
            {neutrals.map((point, index) => <Row key={`n-${index}`} point={point} />)}
          </div>
        )}
      </div>
    </div>
  )
}

/**
 * [R410] 斐波那契二型的线太多, 这里决定**画哪几条**:
 * 密集带里的 / 作废线 / 离现价最近的几条(上下各 `NEAR_EACH_SIDE` 条)。
 * 上攻推算位另由开关管, 默认不画 —— 按角色键过滤, 不按标签文字。
 */
const NEAR_EACH_SIDE = 3

export function thinFib2(
  all: PriceLevel[],
  close: number | undefined,
  zone: { low: number; high: number } | null,
  showTargets: boolean,
): PriceLevel[] {
  const kept = showTargets ? all : all.filter(point => point.color !== FIB2_ROLE_TARGET)
  if (close == null || !Number.isFinite(close)) return kept
  const keep = new Set<PriceLevel>()
  for (const point of kept) {
    if (point.strength === 'strong') keep.add(point)
    if (zone && point.value >= zone.low && point.value <= zone.high) keep.add(point)
  }
  for (const direction of [1, -1]) {
    const side = kept
      .filter(point => (direction > 0 ? point.value > close : point.value <= close))
      .sort((a, b) => Math.abs(a.value - close) - Math.abs(b.value - close))
    let count = 0
    for (const point of side) {
      if (count >= NEAR_EACH_SIDE) break
      if (!keep.has(point)) count++
      keep.add(point)
    }
  }
  // 保持后端给的原顺序 —— 下方文字行按它排, 顺序跳来跳去比多几条还难读
  return kept.filter(point => keep.has(point))
}
