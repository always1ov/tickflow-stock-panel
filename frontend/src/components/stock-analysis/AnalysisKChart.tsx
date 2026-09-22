import { useEffect, useRef, useMemo, useState } from 'react'
import { chartTheme, FIB2_ROLE_TARGET, QUANT_MACD_COLORS, fib2RoleColor, getTheme, levelColors, useLevelColors, useTheme } from '@/lib/theme'
import * as echarts from 'echarts'
import type { ECharts, EChartsOption } from 'echarts'
import type { Fib2Grain, Fib2Overlay, KlineRow, LevelSeries, QuantMacdResult } from '@/lib/api'
import { alignQuantMacd, quantMacdSeries } from '@/lib/quantMacdSeries'
import { levelsChartLayout, PAD_BOTTOM, SLIDER_H } from '@/lib/levelsChartLayout'
import { fib2Status } from '@/lib/fib2Status'
import { Fib2GrainDialog } from './Fib2GrainDialog'

/**
 * 个股分析专用日 K 图表。
 *
 * 与 StockDailyKChart/EChartsCandlestick 刻意不复用:
 *   - 那套图表面向「行情浏览」,强调全套指标副图(MA/MACD/KDJ/BOLL)、涨停标记等;
 *   - 本图表面向「分析决策」,核心是【关键价位】(压力/支撑/密集区/枢轴/前高前低),
 *     通过开关按钮控制各价位组的显隐,布局更简洁(主图 + 一张副图)。
 *   - [R415] 副图原来是成交量, 现在是用户自己的「量化MACD」(通达信公式逐行复刻,
 *     算法在后端 `indicators/quant_macd.py`, 画法在 `lib/quantMacdSeries.ts`)。
 *
 * 预留接口(类型已定义,渲染逻辑留 hook,后续实现):
 *   - markers: 日期标记点(新闻/暴雷/利好 → markPoint)
 *   - ranges:  区间高亮(事件区间 → markArea)
 *   - onDateClick: 点击日期回调(后续接消息面时间轴)
 *   - 指标副图: 后续如需 MACD/KDJ,按 SUB_CHARTS 模式扩展
 */

// ===== 配色(红涨绿跌, 双主题通用); 画布轴/网格主题相关色走 CT() =====
const THEME = {
  bull: '#C74040',
  bear: '#2D9B65',
}

/** 当前主题的图表调色板 (buildOption 渲染时调用; 切换由组件 effect 触发重建)。 */
const CT = () => chartTheme(getTheme())

// ===== 价位类型(与后端 levels.py 的 LEVEL_TYPES 对齐) =====
export type LevelType = 'sr' | 'pivot' | 'extreme' | 'boll' | 'keltner_s' | 'keltner_m' | 'keltner_l' | 'atr_stop' | 'gap' | 'fib' | 'round' | 'livermore' | 'fib2'

export interface PriceLevel {
  value: number
  label: string
  type: LevelType
  side: 'resistance' | 'support' | 'neutral'
  strength?: 'strong' | 'medium' | 'weak'
  /** 档位(仅 pivot 有):0=P, 1=R1/S1, 2=R2/S2, 3=R3/S3 */
  rank?: number
  /**
   * [R405] 这一条线自己的角色, 盖过所在组的颜色。
   *
   * 加这个是为了斐波那契二型: 它一组里有**三种意思不同**的线 ——
   * 回踩位、上攻推算位一/二/三、这组作废。规格 §12 说得很明白:
   * 「每种颜色全站只表达一种含义」, 全涂成一个色等于把三件事说成一件。
   * 别的组不传这个字段, 行为与以前一字不差。
   *
   * [R409] **它是角色标识, 不是最终颜色。** 值是后端
   * `indicators/dinapoli.py` 那三个常量之一(恰好写成 hex, 且恰好就是亮色
   * 那一份); 画之前一律过 `fib2RoleColor()` 换成当前主题该用的值 ——
   * 后端不知道用户开的是亮色还是暗色, 它发不出"按主题分两套"的颜色。
   */
  color?: string
}

/**
 * 价位组开关配置:label = 按钮文案。
 *
 * [R409] **颜色不在这里了。** 原来每组在这一行写死一个 hex, 结果是:
 * 压力支撑与布林带写成了同一个值(重叠时完全分不出谁是谁), 亮色主题下
 * 四个组对白底的对比度只有 1.35~2.01(等于没画), ATR 波动通道离 K 线的
 * 涨红只有 ΔE 5~6(一条指标线长得像一根阳线)。
 *
 * 现在配色**按主题分两套**, 单一产地是 `lib/theme.ts` 的 `LEVEL_PALETTE`
 * (为什么这么排、量到了什么数, 都写在那儿)。这里只留"有哪些组、叫什么"。
 */
export const LEVEL_GROUPS: { key: LevelType; label: string }[] = [
  { key: 'sr',       label: '压力支撑' },
  { key: 'pivot',    label: '枢轴点' },
  { key: 'extreme',  label: '前高前低' },
  { key: 'boll',     label: '布林带' },          // MA20±2σ 曲线
  { key: 'keltner_s',label: '量化通道短期' },     // MA20±2ATR 曲线
  { key: 'keltner_m',label: '量化通道中期' },     // MA60±2.5ATR 曲线
  { key: 'keltner_l',label: '量化通道长期' },     // MA120±3ATR 曲线
  { key: 'atr_stop', label: 'ATR波动通道' },
  { key: 'gap',      label: '缺口位' },
  { key: 'fib',      label: '斐波那契一型' },
  { key: 'round',    label: '整数关口' },
  // [fork 增强] 六态关键点(利弗莫尔上/下关键点,趋势确认/否决价)
  { key: 'livermore', label: '六态关键点' },
  // [R405 · fork 增强] 斐波那契二型(帝纳波利点位)。按一下出来: 回踩位、
  // 这组作废、二型均线、上攻段底色、回踩密集带、首次回踩标记;
  // 上攻推算位一/二/三另有开关, 默认不画(R410)。
  // **只有位置, 没有动作** —— 和六态/量化通道撞不撞由用户自己看。
  // [R410] 用户: 「目标1目标2失效位这些表达没能让用户抓得住重点看得懂,
  // 而且好多根线」—— 改名与减线都在这一轮, 理由写在 `dinapoli.to_levels`
  // 与本文件的 `thinFib2`。
  { key: 'fib2',     label: '斐波那契二型' },
  // [R403] 「持仓止盈」这一组从图上撤了(用户: 「持仓止盈可以删除掉了」)。
  // **只撤图上的线** —— 决策台的止盈线列、盘中推送、AI 持仓上下文照旧, 见后端
  // `indicators/levels.py` 的 LEVEL_TYPES。
]

// 通道曲线元数据(单一数据源):供 buildOption 画线 + 右侧面板取最新值共用。
//   alignedKey: alignedSeries 中的 key(由 series.boll/keltner/atr 对齐而来)
//   group:      属于哪个价位开关组(开关该组即开关这条曲线)
//   endLabel:   右侧端点标签(显示最新值的文字)
//
// [R409] **`color` 这一列去掉了** —— 每条曲线用它所属组的颜色, 由
// `LEVEL_PALETTE` 一处给。原来这里另写了三个 hex(布林中轨 #FB923C、
// ATR上轨 #F87171、二型均线 #8A8578), 于是同一个开关底下**冒出了组色之外的
// 颜色**: 开关上的小圆点是一种色、图上的线是另一种, 而且那三个 hex 谁也没管,
// 与别的组撞不撞没人知道(实测 ATR上轨 #F87171 离 K 线涨红只有 ΔE 6)。
// 上/下轨靠位置就分得开, 中轨靠实线(`dashed: false`)分得开, 不需要再换色。
const CURVE_DEFS: { alignedKey: string; group: LevelType; endLabel: string; dashed?: boolean }[] = [
  { alignedKey: 'boll_upper',     group: 'boll',      endLabel: '布林上轨', dashed: true },
  { alignedKey: 'boll_lower',     group: 'boll',      endLabel: '布林下轨', dashed: true },
  { alignedKey: 'boll_mid',       group: 'boll',      endLabel: '布林中轨', dashed: false },
  { alignedKey: 'keltner_s_upper',group: 'keltner_s', endLabel: '短期上沿', dashed: true },
  { alignedKey: 'keltner_s_lower',group: 'keltner_s', endLabel: '短期下沿', dashed: true },
  { alignedKey: 'keltner_m_upper',group: 'keltner_m', endLabel: '中期上沿', dashed: true },
  { alignedKey: 'keltner_m_lower',group: 'keltner_m', endLabel: '中期下沿', dashed: true },
  { alignedKey: 'keltner_l_upper',group: 'keltner_l', endLabel: '长期上沿', dashed: true },
  { alignedKey: 'keltner_l_lower',group: 'keltner_l', endLabel: '长期下沿', dashed: true },
  { alignedKey: 'atr_stop',       group: 'atr_stop',  endLabel: 'ATR下轨', dashed: true },
  { alignedKey: 'atr_tp',         group: 'atr_stop',  endLabel: 'ATR上轨', dashed: true },
  // [R405] 叫「二型均线」不叫「短期均线」: 后者在 `lib/signals.ts` 里已经指 MA5,
  // 而这条是 3 日均线往后移 3 根 —— 同名两物正是名词表要防的。
  { alignedKey: 'fib2_dma3',      group: 'fib2',      endLabel: '二型均线', dashed: false },
]

// 默认不打开任何价位组 —— 价位怎么看是用户的判断, 系统不替他预设。
// 开关全排在图上方, 想看哪组点哪组。
// [R403] 这儿原来写着「14 个开关」, 而当时实际是 13 个, 撤掉持仓止盈之后是 12 ——
// **数字写死在注释里必然过期**, 所以不再写数, 要数就数上面 LEVEL_GROUPS。

// ===== 预留:标记 / 区间(后续新闻面、事件区间用) =====
export interface ChartMarker {
  date: string
  label?: string
  color?: string
  above?: boolean
}
export interface ChartRange {
  start: string
  end: string
  label?: string
  color?: string
}

interface Props {
  rows: KlineRow[]
  levels?: Record<LevelType, PriceLevel[]>
  /** 带状曲线指标(布林带/Keltner/ATR)的每日序列 —— 画成跟随时间漂移的曲线 */
  series?: LevelSeries
  /** series 数据对应的日期数组(与 series 各数组对齐) */
  seriesDates?: string[]
  /** 默认开启的价位组; 不传 = 全部不开 */
  defaultLevelTypes?: LevelType[]
  /** 预留:新闻/暴雷/利好日期标记 */
  markers?: ChartMarker[]
  /** 预留:事件区间高亮 */
  ranges?: ChartRange[]
  /**
   * [R405] 斐波那契二型里画不成横线的那几样(回踩密集带色带 / 上攻段底色 /
   * 首次回踩标记)。**整块跟着「斐波那契二型」那个开关走** —— 开关没开就一样
   * 都不画, 免得图上留下几块没人认领的色带。
   */
  fib2?: Fib2Overlay
  /** [R412] 标的代码 —— 只为「粗细档回测」那个按钮用; 不传就不显示那个按钮 */
  symbol?: string
  /** [R415] 副图「量化MACD」的逐根数值; 没到就先空着(副图留白, 主图照画) */
  quantMacd?: QuantMacdResult
  /** 预留:点击某根 K 线 */
  onDateClick?: (date: string) => void
  /**
   * [R419] 主图按这个高度算(与 R415 之前一样); 量化MACD 副图在它之外另加,
   * 所以整张图比它高。见 `lib/levelsChartLayout.ts`。
   */
  height?: number
  className?: string
}


export function AnalysisKChart({
  rows,
  levels,
  series,
  seriesDates,
  // [R208] 默认勾上**量化通道短期**。用户: 「关键价位的指标默认选量化通道短期」。
  //
  // 原来默认是空的 —— 图上一条线都没有, 每次打开都要自己点一次。而这十几个
  // 价位组里, 短期通道是唯一**每天都在动、且决策台整张表都在用**的那一个
  // (「贵不贵」「该动了」「通道态势」三列的位置判定都以它为准), 所以它是
  // 最该默认在场的。别的组按需再点。
  defaultLevelTypes = ['keltner_s'],
  markers,
  ranges,
  fib2,
  symbol,
  quantMacd,
  onDateClick,
  height = 460,
  className,
}: Props) {
  const chartRef = useRef<HTMLDivElement>(null)
  const chartInstRef = useRef<ECharts | null>(null)
  /** seriesIndex → levelKey 映射, buildOption 填充, ECharts hover 事件反查 */
  const seriesKeyMapRef = useRef<Map<number, string>>(new Map())
  // 主题: buildOption 内部用 CT() 动态取色, 这里只负责切换时触发重建
  const theme = useTheme()
  const [activeTypes, setActiveTypes] = useState<Set<LevelType>>(new Set(defaultLevelTypes))
  /** 枢轴点显示到第几档:1=只P+R1/S1, 2=到R2/S2, 3=全档(R3/S3) */
  const [pivotRank, setPivotRank] = useState<1 | 2 | 3>(1)
  /**
   * [R406] 斐波那契二型的粗细档。**与枢轴点那个「档位」是同一个套路**:
   * 一组价位里"显示到多细"由用户当场定, 而不是藏进配置。
   *
   * 差别在于枢轴点那个是前端过滤(每条线自带 rank), 这个是后端一次算三份 ——
   * 摆点认得多细会改变算出来的线本身, 过滤不出来。
   */
  // [R410] 默认档 `mid` → `coarse`。用户: 「好多根线, 好难抓住…做不做在哪里做,
  // 走不走这些」。实测中档 12 条、粗档 7 条 —— 默认少掉四成, 想看细的随时点。
  const [fib2Grain, setFib2Grain] = useState<Fib2Grain>('coarse')
  /**
   * [R410] 上方那三条推算位默认不画。它们回答的是"涨上去以后会路过哪",
   * 与当下要抓的「在哪里做 / 走不走」无关 —— 先让图安静下来, 想看再点。
   */
  const [fib2ShowTargets, setFib2ShowTargets] = useState(false)
  /** [R412] 粗细档回测弹窗开着没有 */
  const [fib2FitOpen, setFib2FitOpen] = useState(false)
  /** 双向联动高亮: hover 价位标签 ↔ hover 下方文字行。值为 levelKey, null=无高亮 */
  const [hoveredKey, setHoveredKey] = useState<string | null>(null)

  // 数据预处理 + 带状曲线序列对齐(后端 series 的日期范围可能与 rows 不同,需映射)
  // [R406] 选中档的线顶掉默认那一组。后端 `levels.fib2` 给的是中档, 这里按用户
  // 选的档换掉 —— 切档因此不用重新请求, 点一下当场变。
  const fib2Zone = fib2?.grain?.[fib2Grain]?.zone ?? null
  const fib2Raw = fib2?.grain?.[fib2Grain]?.levels ?? null
  const fib2Shown = useMemo(
    () => (fib2Raw ? thinFib2(fib2Raw, rows.at(-1)?.close, fib2Zone, fib2ShowTargets) : null),
    [fib2Raw, rows, fib2Zone, fib2ShowTargets])
  const effLevels = useMemo(
    () => (fib2Shown && levels ? { ...levels, fib2: fib2Shown } : levels),
    [levels, fib2Shown])
  // [R411] 那一行「形态走到哪一步」。**读的是整档 `fib2Raw` 而不是画出来的
  // `fib2Shown`** —— 减线藏掉的那几条不该让这句话也跟着变, 它说的是形态,
  // 不是"图上现在画了几条"。
  const fib2Line = useMemo(() => fib2Status({
    dates: rows.map(r => (typeof r.date === 'string' ? r.date.slice(0, 10) : String(r.date))),
    close: rows.at(-1)?.close,
    thrust: fib2?.thrust,
    markers: fib2?.markers,
    zone: fib2Zone,
    levels: fib2Raw ?? [],
  }), [rows, fib2, fib2Zone, fib2Raw])

  const { dates: baseDates, candle, dateIndex, zoomStart: baseZoom,
          alignedSeries: baseSeries } = useMemo(() => {
    const dates = rows.map(r => (typeof r.date === 'string' ? r.date.slice(0, 10) : String(r.date)))
    const candle = rows.map(r => [r.open, r.close, r.low, r.high])
    const dateIndex = new Map(dates.map((d, i) => [d, i]))
    // 默认显示最近 6 个月 ≈ 120 个交易日;数据不足则全部显示
    const showBars = 120
    const zoomStart = dates.length > showBars ? Math.round((1 - showBars / dates.length) * 100) : 0

    // 把后端 series(按 seriesDates 对齐)映射到前端 rows 的 dates 顺序
    const alignedSeries: Record<string, (number | null)[]> = {}
    if (series && seriesDates && seriesDates.length > 0) {
      // 构建 seriesDates 索引
      const sIdx = new Map(seriesDates.map((d, i) => [d, i]))
      // 通用对齐:给定 series 里某条数组,返回与 rows dates 对齐的版本
      const align = (arr: (number | null)[] | undefined): (number | null)[] => {
        if (!arr) return dates.map(() => null)
        return dates.map(d => {
          const i = sIdx.get(d)
          return i != null ? arr[i] : null
        })
      }
      if (series.boll) {
        alignedSeries['boll_upper'] = align(series.boll.upper)
        alignedSeries['boll_lower'] = align(series.boll.lower)
        if (series.boll.mid) alignedSeries['boll_mid'] = align(series.boll.mid)
      }
      if (series.keltner_s) {
        alignedSeries['keltner_s_upper'] = align(series.keltner_s.upper)
        alignedSeries['keltner_s_lower'] = align(series.keltner_s.lower)
      }
      if (series.keltner_m) {
        alignedSeries['keltner_m_upper'] = align(series.keltner_m.upper)
        alignedSeries['keltner_m_lower'] = align(series.keltner_m.lower)
      }
      if (series.keltner_l) {
        alignedSeries['keltner_l_upper'] = align(series.keltner_l.upper)
        alignedSeries['keltner_l_lower'] = align(series.keltner_l.lower)
      }
      if (series.atr) {
        alignedSeries['atr_stop'] = align(series.atr.stop_loss)
        alignedSeries['atr_tp'] = align(series.atr.take_profit)
      }
      if (series.fib2) {
        alignedSeries['fib2_dma3'] = align(series.fib2.dma3)
      }
    }

    return { dates, candle, dateIndex, zoomStart, alignedSeries }
  }, [rows, series, seriesDates])

  /**
   * [R413] 「未来」区 —— 位移均线平移之后**露到最后一根之外**的那 3 个值。
   *
   * 它不是未来函数, 恰恰相反: 用的全是已经收盘的数据, 只是画到了右边
   * (见后端 `dinapoli.displaced_sma` 的说明)。R405 就把数据发过来了, 一直没画,
   * 因为画它要**往右扩几个空槽**, 而 x 轴是所有价位组共用的。
   *
   * 用户定的做法: 「避开影响就独立显示, 只为了看看而已, 别影响六态那些」。
   * 所以这里的关键不是怎么画, 而是**什么时候不画**:
   *
   *     二型开关没开 → `futureDates` 为空 → dates/缩放/曲线全部原样,
   *     整张图与加这段之前**逐字节相同**。
   *
   * 这样六态的分段底色、关键点线、所有别的组都碰不到 —— 它们只在二型开着的
   * 时候才会跟着多出 3 个槽, 而那时候用户本来就在看二型。
   */
  const futureVals = activeTypes.has('fib2') ? (fib2?.dma3_future ?? []) : []
  const { dates, zoomStart, alignedSeries, futureDates } = useMemo(() => {
    if (!futureVals.length) {
      return { dates: baseDates, zoomStart: baseZoom,
               alignedSeries: baseSeries, futureDates: [] as string[] }
    }
    const futureDates = futureVals.map((_, i) => `未来${i + 1}`)
    const dates = [...baseDates, ...futureDates]
    // 二型均线是**唯一**有未来值的曲线; 别的曲线数组短 3 格, ECharts 画到
    // 最后一个有值的点就停 —— 那正是对的, 它们本来就不知道明天。
    const alignedSeries = { ...baseSeries }
    if (alignedSeries['fib2_dma3']) {
      alignedSeries['fib2_dma3'] = [...alignedSeries['fib2_dma3'], ...futureVals]
    }
    // 默认视窗仍然给 120 根**真实** K 线 —— 不补这一下, 多出来的空槽会把
    // 真实 K 线挤掉 3 根。
    const showBars = 120 + futureDates.length
    const zoomStart = dates.length > showBars
      ? Math.round((1 - showBars / dates.length) * 100) : 0
    return { dates, zoomStart, alignedSeries, futureDates }
  }, [baseDates, baseZoom, baseSeries, futureVals])

  // [R409] 当前主题下的价位组配色。单一产地在 `lib/theme.ts`;
  // `theme` 已经在 buildOption 的 useMemo 依赖里, 切主题会整张图重建。
  const LC = levelColors(theme)
  // [R419] 纵向版面(主图原高 + 副图另加), 见 `lib/levelsChartLayout.ts`
  const layout = levelsChartLayout(height)
  const targetColor = fib2RoleColor(FIB2_ROLE_TARGET, theme)

  // 构建 option
  const buildOption = (): EChartsOption => {
    const priceLines = collectPriceLines(effLevels, activeTypes, pivotRank, LC, theme)

    // 三段布局:主图 / 量化MACD / 缩放条,从上到下累加,各段之间留间距,互不遮挡
    //   [16 顶部] [mainH 主图] [14 间距] [subH 量化MACD] [26 日期+间距] [SLIDER_H 缩放条] [8 底部]
    //
    // [R415] 日期刻度从主图底下挪到副图底下, 间距跟着改。原来刻度夹在主图与
    // 成交量之间, 成交量柱从底部往上长, 顶上那条被刻度压住看不出来; 换成量化MACD
    // 以后 0 轴与叉点图标都贴近副图顶部, 出图就被日期字压住了。
    // [R419] 数值统一由 `levelsChartLayout` 出: 主图与 R415 之前一样高, 副图另加。
    const { mainH, subH, subTop } = layout
    const sliderBottom = PAD_BOTTOM

    // 预留:markPoint(新闻标记)
    const markPointData: any[] = (markers ?? [])
      .filter(m => dateIndex.has(m.date))
      .map(m => ({
        coord: [m.date, rows[dateIndex.get(m.date)!].high],
        symbol: 'pin', symbolSize: 32,
        itemStyle: { color: m.color ?? '#EAB308' },
        label: { show: !!m.label, formatter: m.label ?? '', fontSize: 9, color: '#fff' },
      }))

    // 预留:markArea(事件区间)
    const markAreaData: any[] = (ranges ?? [])
      .filter(r => dateIndex.has(r.start) && dateIndex.has(r.end))
      .map(r => [{
        xAxis: r.start, name: r.label ?? '',
        itemStyle: { color: r.color ?? 'rgba(234,179,8,0.08)' },
        label: r.label ? { show: true, position: 'insideTop', distance: 6, color: '#EAB308', fontSize: 10 } : undefined,
      }, { xAxis: r.end }])

    // [R405] 斐波那契二型的三样"画不成横线"的东西。**整块跟着那一个开关走** ——
    // 开关没开就一样都不画, 图上不会留下没人认领的色带。
    const fib2On = activeTypes.has('fib2')
    // 两套主题分开给: 暗底上要更亮才浮得起来, 亮底上同样的值会糊成一片
    const isDark = getTheme() === 'dark'
    if (fib2On && fib2) {
      // 上攻段底色: 纵向铺满, 横向只盖推进那一段(xAxis 两端 = 日期区间)
      const th = fib2.thrust
      if (th && dateIndex.has(th.start) && dateIndex.has(th.end)) {
        markAreaData.push([{
          xAxis: th.start, name: `单边上攻 ${th.days} 天`,
          // [R407] 规格写的 6% 是在原型图的**白底**上定的, 放到实际主题上
          // (尤其暗色)几乎看不见。加深并补一圈虚线边框, 段的起止才看得出来。
          itemStyle: {
            color: isDark ? 'rgba(210,70,59,0.20)' : 'rgba(210,70,59,0.13)',
            borderColor: isDark ? 'rgba(210,70,59,0.45)' : 'rgba(210,70,59,0.32)',
            borderWidth: 1, borderType: 'dashed',
          },
          label: { show: true, position: 'insideTop', distance: 6,
                   color: '#D2463B', fontSize: 10, fontWeight: 'bold' },
        }, { xAxis: th.end }])
      }
      // 强支撑区: 横向铺满, 纵向只盖那个价格带(yAxis 两端 = 价格区间)。
      // 透明度随重合条数走 —— 规格 §9: 1/2/3 条对应 20%/35%/50%。
      const z = fib2Zone
      if (z && z.high > 0) {
        // [R407] 底色加深并补一圈实边框。用户: 「新指标的背景色看不清太淡了」。
        // 这个区常常只有两三条线的厚度 —— 光靠半透明填充, 在蜡烛底下几乎看不出
        // 边界在哪。重合越多越浓(这是它唯一的"强度"表达), 但起点比规格高一档。
        const alpha = Math.min(0.55, 0.30 + 0.12 * Math.max(0, z.strength - 1))
        // [R409] 底色跟着组色走(二型整组从金挪到洋红, 免得和一型的金撞)
        const zc = LC.fib2
        // 两条回撤挤得很近时色带会薄到看不见 —— 规格 §9 要求最小高度,
        // 这里按价格给个下限(现价的千分之三), 比按像素算简单且不依赖坐标系。
        const thin = Math.max(0, (rows.at(-1)?.close ?? z.high) * 0.003 - (z.high - z.low)) / 2
        // [R410] 「强支撑区」里的「支撑」已经被「压力支撑」那一组占用了 ——
        // 同一个词两件事。改叫「回踩密集带」: 说的就是它本来的意思, 且不撞名。
        markAreaData.push([{
          // [R413] **标上上下沿价格。** 用户: 这是"唯一真会拿来挂单的东西",
          // 而在此之前这块色带上一个数字都没有 —— 读不出价就挂不了单。
          yAxis: z.low - thin,
          name: `回踩密集带 ${z.low.toFixed(2)}~${z.high.toFixed(2)} · ${z.strength} 条挤在一起`,
          itemStyle: {
            color: withAlpha(zc, alpha),
            borderColor: withAlpha(zc, 0.85), borderWidth: 1,
          },
          label: { show: true, position: 'insideTopLeft', distance: 4,
                   color: zc, fontSize: 9,
                   fontWeight: 'bold' },
        }, { yAxis: z.high + thin }])
      }
      // 首次回踩
      for (const m of fib2.markers ?? []) {
        const i = dateIndex.get(m.date)
        if (i == null) continue
        markPointData.push({
          coord: [m.date, rows[i].high],
          symbol: 'triangle', symbolSize: 9, symbolRotate: 180,
          symbolOffset: [0, -10],
          itemStyle: { color: LC.fib2 },
          label: { show: true, formatter: m.label, position: 'top',
                   fontSize: 9, color: LC.fib2 },
        })
      }
    }

    // [R413] 「未来」区的灰底。**没画成 3 根灰蜡烛**, 因为未来的开/高/低/收
    // 根本不存在 —— 画出来就是编的, 而一根编出来的蜡烛在图上和真的长得一样。
    // 这里只给 3 个空槽 + 一块中性灰底, 让人一眼看出"这一段还没发生",
    // 均线自然探进去。
    if (futureDates.length) {
      markAreaData.push([{
        xAxis: futureDates[0], name: '未来(均线已知)',
        itemStyle: { color: isDark ? 'rgba(255,255,255,0.05)' : 'rgba(34,39,56,0.05)' },
        label: { show: true, position: 'insideTop', distance: 4,
                 color: CT().text, fontSize: 9 },
      }, { xAxis: futureDates[futureDates.length - 1] }])
    }

    // [R413] 现价贴签。用户: 「用来量『还差多少到位』」—— 在此之前只有 hover
    // 时的十字线, 手一移开就没了, 而"离那条线还差多少"是要反复看的。
    const lastClose = rows.at(-1)?.close
    const nowLine = lastClose != null && Number.isFinite(lastClose) ? {
      silent: true, symbol: 'none', animation: false,
      z: 3,
      data: [{ yAxis: lastClose }],
      lineStyle: { color: CT().text, width: 1, type: 'dashed' as const, opacity: 0.45 },
      label: {
        // **单独占右边预留带的一列**, 不和价位标签抢位置。
        //
        // 前两版都出过图才发现不行: 放绘图区里(`insideStartTop`)会被贴得近的
        // 价位线穿过去 —— 价位线和它在同一片画布上, 调 z/zlevel 压不住;
        // 放左边(`start`)会被切掉 —— 左边距只有 56px, 刚够 y 轴刻度。
        // 右边预留带 144px, 价位标签从 +6 起最宽约 66px, 所以让到 +78
        // 就是一条干净的列。**这是结构上不重叠, 不是靠图层压。**
        show: true, position: 'end' as const, distance: 78,
        formatter: () => `现价 ${lastClose.toFixed(2)}`,
        color: CT().textStrong, fontSize: 9,
        fontFamily: 'JetBrains Mono, monospace',
        // **不透明底**: 信息条那个 85% 的底在别的价位线贴得很近时压不住,
        // 出图时「现价 15.50」被两条 15.7x 的虚线穿过去了。
        backgroundColor: CT().tooltipBg, borderColor: CT().tooltipBorder,
        borderWidth: 1, padding: [2, 5], borderRadius: 2,
      },
    } : undefined

    const qmacdSeries = quantMacdSeries(alignQuantMacd(dates, quantMacd),
                                        { xAxisIndex: 1, yAxisIndex: 1 })
    const series: any[] = [
      {
        name: 'K', type: 'candlestick', data: candle, animation: false,
        markLine: nowLine,
        // z=2 让蜡烛始终在价位线(z=1)之上, hover 高亮价位线时不会被遮挡/变淡
        z: 2,
        itemStyle: {
          color: THEME.bull, color0: THEME.bear,
          borderColor: THEME.bull, borderColor0: THEME.bear,
        },
        markPoint: markPointData.length ? { data: markPointData, animation: false } : undefined,
        markArea: markAreaData.length ? { silent: true, data: markAreaData } : undefined,
      },
      // [R415] 副图: 量化MACD。按日期对齐到 `dates` —— 含二型的「未来」空槽,
      // 那几格是 null, 不画。
      ...qmacdSeries,
    ]

    // 价位水平线 —— 用 line series(恒定值)画水平线,endLabel 显示标签文字;
    // 与通道曲线一致,标签落在右侧 grid.right 预留带(外侧),不压蜡烛。
    // hoveredKey 非空时:命中线加粗高亮,其它线淡化(opacity 0.15),形成聚焦效果。
    const dimming = hoveredKey != null
    for (const p of priceLines) {
      const k = levelKey(p.type, p.value)
      const hit = hoveredKey === k
      // [R409] 常态不透明度 0.7 → 0.9。叠在 strengthColor 的透明度之上,
      // 原来最弱的一档实际只有 0.39 —— 那正是「颜色浅」的一半来源。
      const opacity = dimming ? (hit ? 1 : 0.12) : 0.9
      const width = hit ? 2 : 1
      series.push({
        name: p.label, type: 'line', silent: false, animation: false,
        symbol: 'none',
        data: dates.map(() => p.value),
        // 默认 z=1 在蜡烛(z=2)之下; 命中时 zlevel=10 提到独立顶层, 标签不再被遮挡
        z: 1,
        zlevel: hit ? 10 : 0,
        lineStyle: { width, color: p.color, type: 'dashed', opacity },
        itemStyle: { color: p.color },
        endLabel: {
          show: true,
          formatter: () => `${p.label} ${p.value.toFixed(2)}`,
          color: p.color, fontSize: hit ? 10 : 9, fontFamily: 'JetBrains Mono, monospace',
          fontWeight: hit ? 'bold' : 'normal',
          backgroundColor: hit ? CT().tooltipBg : CT().infoBarBg,
          borderColor: hit ? p.color : 'transparent',
          borderWidth: hit ? 1 : 0,
          padding: [2, 5], borderRadius: 2,
          distance: 6,
        },
      })
    }

    // 带状曲线指标(布林带 / Keltner通道 / ATR波动通道) —— 跟随行情漂移的曲线
    // 单一数据源 CURVE_DEFS 驱动:每条曲线带 endLabel(右侧端点标签),显示最新数值
    for (const def of CURVE_DEFS) {
      if (!activeTypes.has(def.group)) continue
      const data = alignedSeries[def.alignedKey]
      if (!data || !data.some(v => v != null)) continue
      // 取最后一个有效值作为右侧端点显示文字
      let lastVal: number | null = null
      for (let i = data.length - 1; i >= 0; i--) {
        if (data[i] != null) { lastVal = data[i]; break }
      }
      // 曲线 key 用 group(同组上下轨联动),hover 命中时高亮
      const hit = hoveredKey === def.group
      // [R409] 曲线用所属组的颜色 —— 开关上的小圆点与图上的线必须是同一个色
      const curveColor = LC[def.group]
      const opacity = dimming ? (hit ? 1 : 0.12) : 0.9
      const width = hit ? 1.8 : 1
      series.push({
        name: def.endLabel, type: 'line', data: data.map(v => v ?? '-'),
        smooth: true, symbol: 'none', silent: false, animation: false,
        z: 1,
        zlevel: hit ? 10 : 0,
        lineStyle: { width, color: curveColor, type: def.dashed === false ? 'solid' : 'dashed', opacity },
        itemStyle: { color: curveColor },
        // 右侧端点标签:显示该通道的最新数值,距绘图区右缘留 6px 间距
        endLabel: lastVal != null ? {
          show: true,
          formatter: () => `${lastVal!.toFixed(2)}`,
          color: curveColor, fontSize: hit ? 10 : 9, fontFamily: 'JetBrains Mono, monospace',
          fontWeight: hit ? 'bold' : 'normal',
          backgroundColor: hit ? CT().tooltipBg : CT().infoBarBg,
          borderColor: hit ? curveColor : 'transparent',
          borderWidth: hit ? 1 : 0,
          padding: [2, 5], borderRadius: 2,
          distance: 6,
        } : undefined,
      })
    }

    // 填充 seriesIndex → levelKey 映射(K 线与副图那几条不参与联动)
    const keyMap = new Map<number, string>()
    // series[0]=K线, 接着是副图的 qmacdSeries.length 条, 之后才是按
    // priceLines + CURVE_DEFS 顺序 push 的。**起点必须跟着副图条数走** ——
    // 写死一个数, 副图多一条, 悬停价位线就会高亮到隔壁那条上去。
    let si = 1 + qmacdSeries.length
    for (const p of priceLines) {
      keyMap.set(si++, levelKey(p.type, p.value))
    }
    for (const def of CURVE_DEFS) {
      if (!activeTypes.has(def.group)) continue
      const data = alignedSeries[def.alignedKey]
      if (!data || !data.some(v => v != null)) continue
      keyMap.set(si++, def.group)
    }
    seriesKeyMapRef.current = keyMap

    return {
      animation: false,
      backgroundColor: 'transparent',
      // grid.right 留出足够宽度给价位标签文字区:蜡烛只占左侧主区域,
      // 价位线右端的标签文字显示在这条预留带里,不压在蜡烛上。
      // 预留 ~144px:最长标签(如「成交密集区(POC) 12.34」)约 13 字符,fontSize 9 等宽。
      grid: [
        { left: 56, right: 144, top: 16, height: mainH },
        // [R418] 亮色主题下副图铺通达信的黑底 —— 颜色照抄通达信, 纯黄在白底上看不见
        { left: 56, right: 144, top: subTop, height: subH,
          show: !isDark, backgroundColor: QUANT_MACD_COLORS.paneBg, borderWidth: 0 },
      ],
      xAxis: [
        {
          type: 'category', data: dates, boundaryGap: true,
          axisLine: { lineStyle: { color: CT().grid } },
          // [R415] 日期刻度只在最底下那张图(量化MACD)下面写一次
          axisLabel: { show: false },
          splitLine: { show: false },
          axisPointer: { show: true, label: { show: false } },
        },
        {
          type: 'category', gridIndex: 1, data: dates, boundaryGap: true,
          axisLabel: { color: CT().text, fontSize: 10 },
          // [R415] 不画轴线: 这条类目轴的轴线默认落在 0 处, 在副图里就是一条
          // 0 轴横线 —— 原文没画这条线, 不能多画。
          axisLine: { show: false }, axisTick: { show: false },
        },
      ],
      yAxis: [
        { scale: true, splitLine: { lineStyle: { color: CT().grid } },
          axisLabel: { color: CT().text, fontSize: 10, fontFamily: 'JetBrains Mono, monospace' } },
        // [R415] 不开 scale: 原文每根柱子都从 0 画起(STICKLINE 的第二个参数),
        // 开了 scale 在全是正值的那一段 0 会掉出坐标轴, 柱子就没了根。
        { scale: false, gridIndex: 1, splitNumber: 2,
          // 副图不画背景横线
          splitLine: { show: false },
          axisLabel: { color: CT().text, fontSize: 9, fontFamily: 'JetBrains Mono, monospace',
                       formatter: (v: number) => fmtSub(v) } },
      ],
      dataZoom: [
        { type: 'inside', xAxisIndex: [0, 1], start: zoomStart, end: 100 },
        { type: 'slider', xAxisIndex: [0, 1], bottom: sliderBottom, height: SLIDER_H, start: zoomStart, end: 100,
          borderColor: 'transparent', fillerColor: CT().zoomFill,
          handleStyle: { color: '#52525B' }, textStyle: { color: CT().text, fontSize: 10 } },
      ],
      // 不弹 hover tooltip(用户要求);但保留十字线 axisPointer 作为缩放/定位参照
      tooltip: { show: false },
      axisPointer: { link: [{ xAxisIndex: 'all' }] },
      // [R415] 副图左上角的名字 —— 否则换掉成交量之后, 这块图是什么没有任何地方说
      graphic: [{
        type: 'text', left: 60, top: subTop + 2, silent: true,
        // 亮色主题下它落在黑底上, 用浅灰才看得见
        style: { text: '量化MACD', fill: isDark ? CT().text : '#B4B4B4', fontSize: 9 },
      }],
      series,
    }
  }

  // 初始化 + 数据更新
  useEffect(() => {
    if (!chartRef.current) return
    if (!chartInstRef.current) {
      chartInstRef.current = echarts.init(chartRef.current, undefined, { renderer: 'canvas' })
      chartInstRef.current.on('click', (params: any) => {
        // 预留:点击 K 线(非 markPoint/markLine)回调
        if (params.componentType === 'series' && params.seriesType === 'candlestick' && onDateClick) {
          onDateClick(dates[params.dataIndex])
        }
      })
      // hover 价位线/曲线 endLabel → 联动高亮(与下方文字行双向联动)
      chartInstRef.current.on('mouseover', (params: any) => {
        if (params.componentType === 'series') {
          const k = seriesKeyMapRef.current.get(params.seriesIndex as number)
          if (k) setHoveredKey(k)
        }
      })
      chartInstRef.current.on('globalout', () => setHoveredKey(null))
    }
    // [R419] 画布高度跟着 `height`(最大化 / 还原)变, 先让 ECharts 量一次新尺寸;
    // 尺寸没变时这一下什么也不做
    chartInstRef.current.resize()
    chartInstRef.current.setOption(buildOption(), true)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rows, levels, series, seriesDates, activeTypes, pivotRank, markers, ranges, fib2, fib2Grain, effLevels, fib2Zone, height, theme, hoveredKey, quantMacd])

  // resize
  useEffect(() => {
    const inst = chartInstRef.current
    if (!inst) return
    const onResize = () => inst.resize()
    window.addEventListener('resize', onResize)
    return () => { window.removeEventListener('resize', onResize); inst.dispose(); chartInstRef.current = null }
  }, [])

  const toggleType = (t: LevelType) => {
    setActiveTypes(prev => {
      const next = new Set(prev)
      if (next.has(t)) next.delete(t)
      else next.add(t)
      return next
    })
  }


  return (
    <div className={className}>
      {/* 价位开关按钮组: 14 个价位组全排开, 一行放不下就整块换行
          (chip 自身 nowrap, 只在 chip 之间断行) */}
      {levels && (
        <div className="flex flex-wrap content-start items-center gap-1.5 mb-2">
          <span className="text-[10px] text-muted mr-1 shrink-0">关键价位</span>
          {/* 全部价位组一次排开(不折叠)—— 开关本身就是一眼扫过去挑, 藏起来反而要多点一次 */}
          {LEVEL_GROUPS.map(g => {
            const active = activeTypes.has(g.key)
            // 枢轴点数量按当前档位过滤显示;其他组显示原始数量。
            // [R406] 读 effLevels 而不是 levels —— 二型切了粗细档, 开关上那个数
            // 必须跟着变, 否则显示的是中档的条数而图上画的是另一档。
            const raw = effLevels?.[g.key] ?? []
            const count = g.key === 'pivot'
              ? raw.filter(p => p.rank === undefined || p.rank <= pivotRank).length
              : raw.length
            // [R410] 二型现在只画其中一部分(密集带里的 + 作废线 + 离现价最近的
            // 几条), **所以要如实写出藏了几条**, 否则用户会以为这一档就这么多线。
            // 能不能点也按**整档**算, 不按画出来的那几条算。
            const total = g.key === 'fib2' ? (fib2Raw?.length ?? 0) : raw.length
            const title = g.key === 'fib2' && total > count
              ? `${g.label}: 画了 ${count} 条 / 这一档共 ${total} 条`
                + `\n只画「挤在一起的」「这组作废」和「离现价最近的几条」——`
                + `\n其余的对当下没有意义。想全看就切到更细的档。`
              : `${g.label} (${count} 个)`
            return (
              <button
                key={g.key}
                onClick={() => toggleType(g.key)}
                disabled={total === 0}
                title={title}
                className={`inline-flex shrink-0 whitespace-nowrap items-center gap-1 h-6 px-2 rounded-md text-[10px] font-medium border transition-ui disabled:opacity-30 disabled:cursor-not-allowed ${
                  active
                    ? 'text-foreground'
                    : 'text-muted bg-base/40 border-border/30 hover:border-border/60'
                }`}
                style={active ? { borderColor: LC[g.key] + '66', backgroundColor: LC[g.key] + '1a' } : undefined}
              >
                <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: active ? LC[g.key] : '#52525B' }} />
                {g.label}
                <span className="opacity-50">{count}</span>
              </button>
            )
          })}

          {/* 枢轴点档位选择器 —— 仅当枢轴点开启时显示 */}
          {activeTypes.has('pivot') && (levels.pivot?.length ?? 0) > 0 && (
            <div className="inline-flex shrink-0 items-center gap-0.5 ml-1 pl-2 border-l border-border/40">
              <span className="text-micro text-muted mr-1">档位</span>
              {([1, 2, 3] as const).map(r => (
                <button
                  key={r}
                  onClick={() => setPivotRank(r)}
                  title={r === 1 ? 'P + R1/S1(3 个)' : r === 2 ? '到 R2/S2(5 个)' : '全档 R3/S3(7 个)'}
                  // [R409] 选中态跟着枢轴点那一组的颜色走。原来写死 #8B5CF6
                  // (旧组色), 改了组色这里就会是"选择器一个紫、图上的线另一个紫"
                  className={`h-6 px-2 rounded-btn text-micro font-mono border transition-ui ${
                    pivotRank === r
                      ? 'text-foreground'
                      : 'text-muted bg-base/40 border-border/30 hover:border-border/60'
                  }`}
                  style={pivotRank === r
                    ? { borderColor: LC.pivot + '66', backgroundColor: LC.pivot + '26', color: LC.pivot }
                    : undefined}
                >
                  {r}
                </button>
              ))}
            </div>
          )}

          {/* [R406] 斐波那契二型的粗细档 —— 仅当这一组开启时显示。
              原书没定「多小的回调算噪音」, 这个旋钮就是在回答它;
              它不出买卖信号, 没有可回测的目标函数, 所以哪一档合适**用眼睛定**。 */}
          {activeTypes.has('fib2') && fib2?.grain && (
            <div className="inline-flex shrink-0 items-center gap-0.5 ml-1 pl-2 border-l border-border/40">
              <span className="text-micro text-muted mr-1">粗细</span>
              {([['coarse', '粗'], ['mid', '中'], ['fine', '细']] as const).map(([k, cn]) => (
                <button
                  key={k}
                  onClick={() => setFib2Grain(k)}
                  title={k === 'coarse'
                    ? '只认大级别回调 —— 线少而稳, 重合更难出现但出现了更硬'
                    : k === 'mid'
                      ? '默认档'
                      : '小回调也算 —— 线多而密, 更容易看到重合'}
                  // [R409] 同上: 选中态用二型的组色, 不再另写一个 hex
                  className={`h-6 px-2 rounded-btn text-micro border transition-ui whitespace-nowrap ${
                    fib2Grain === k
                      ? 'text-foreground'
                      : 'text-muted bg-base/40 border-border/30 hover:border-border/60'
                  }`}
                  style={fib2Grain === k
                    ? { borderColor: LC.fib2 + '66', backgroundColor: LC.fib2 + '26', color: LC.fib2 }
                    : undefined}
                >
                  {cn}
                  <span className="ml-1 opacity-50 font-mono">
                    {fib2.grain?.[k]?.levels.length ?? 0}
                  </span>
                </button>
              ))}
              {/* [R410] 上方那三条推算位单独一个开关, 默认关。
                  它们回答「涨上去会路过哪」, 与当下的「在哪里做 / 走不走」无关;
                  默认画出来只是让图更挤。收进开关而不是删掉 —— 数据本来就在,
                  想看一眼是一次点击的事。 */}
              <button
                onClick={() => setFib2ShowTargets(v => !v)}
                title={'上攻推算位一 / 二 / 三\n'
                  + '由这一波的起点、最高点、回踩最低点三点推算, 是"涨上去会路过哪",\n'
                  + '不是"该不该去" —— 默认不画, 免得和眼下要看的位置混在一起。'}
                className={`h-6 px-2 rounded-btn text-micro border transition-ui whitespace-nowrap ml-0.5 ${
                  fib2ShowTargets
                    ? 'text-foreground'
                    : 'text-muted bg-base/40 border-border/30 hover:border-border/60'
                }`}
                style={fib2ShowTargets
                  // 推算位在图上是蓝的, 开关就得是蓝的 —— 用组色(洋红)会让
                  // 「开关什么颜色、线什么颜色」对不上, 那正是 R409 要除掉的毛病
                  ? { borderColor: targetColor + '66', backgroundColor: targetColor + '26', color: targetColor }
                  : undefined}
              >
                上攻推算位
              </button>
              {/* [R412] 粗细档回测。用户:「粗中细我看不懂, 这个调优能不能交给 ai
                  就像我六态设置了一个回测按钮」。**评的是「线画得准不准」**,
                  不是「跟着做赚不赚」—— 这一组不出买卖信号, 没有收益可算。 */}
              {symbol && (
                <button
                  onClick={() => setFib2FitOpen(true)}
                  title={'回看这只票近三年每一次上攻, 看当时画出来的线有没有说中\n'
                    + '之后实际回踩的最低点 —— 评的是「线画得准不准」, 不是「赚不赚」。'}
                  className="ml-0.5 h-6 rounded-btn border border-border/30 bg-base/40 px-2 text-micro text-muted transition-ui hover:border-border/60 hover:text-foreground"
                >
                  回测这三档
                </button>
              )}
            </div>
          )}
        </div>
      )}
      {/* [R411] 形态走到哪一步 —— 把图上那四样(上攻段底色 / ▼首次回踩 /
          回踩位与密集带 / 作废线)串成一句话。它们本来就是**一个有先后顺序的
          形态**, 只是图上按位置摆着, 顺序要用户自己在脑子里拼。

          **只报事实, 一个动词都没有**(用户在这一处明确选的): 不出「等待/买入」,
          也不可能出「卖出」—— 二型的卖出逻辑是那三条推算位, 而那半套与
          「趋势没坏就不给卖出理由」冲突, 已经定了不用。措辞的唯一产地在
          `lib/fib2Status.ts`。 */}
      {activeTypes.has('fib2') && fib2Line && (
        <div className="mb-2 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-micro leading-5">
          <span className="h-1.5 w-1.5 shrink-0 rounded-full" style={{ backgroundColor: LC.fib2 }} />
          {fib2Line.map((seg, i) => (
            <span key={seg} className={i === 0 ? 'text-secondary' : 'text-muted'}>
              {i > 0 && <span className="mr-2 opacity-40">·</span>}
              {seg}
            </span>
          ))}
        </div>
      )}
      {fib2FitOpen && symbol && (
        <Fib2GrainDialog
          symbol={symbol}
          current={fib2Grain}
          onPick={setFib2Grain}
          onClose={() => setFib2FitOpen(false)}
        />
      )}
      {/* 图表:右侧预留带(grid.right 预留)显示价位标签文字,不压蜡烛 */}
      {/* [R419] 画布高 = 主图(原高) + 副图, 比 `height` 高; 弹窗内容区本身可滚动 */}
      <div ref={chartRef} style={{ width: '100%', height: layout.total }} />

      {/* 价位统计面板:把当前开启的点位按"压力 / 支撑"结构化列出 */}
      {effLevels && (
        <LevelOverview
          levels={effLevels}
          activeTypes={activeTypes}
          pivotRank={pivotRank}
          close={rows.length ? rows[rows.length - 1].close : undefined}
          hoveredKey={hoveredKey}
          onHover={setHoveredKey}
        />
      )}
    </div>
  )
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
  onHover: (k: string | null) => void
}) {
  const theme = useTheme()
  const palette = useLevelColors()
  // 收集当前显示的点位(同 collectPriceLines 的过滤逻辑)
  const visible: PriceLevel[] = []
  for (const g of LEVEL_GROUPS) {
    if (!activeTypes.has(g.key)) continue
    for (const p of levels[g.key] ?? []) {
      if (p.type === 'pivot' && p.rank !== undefined && p.rank > pivotRank) continue
      visible.push(p)
    }
  }
  if (visible.length === 0) return null

  // 按方向分两组:压力位(在当前价之上) / 支撑位(之下),各自按距当前价远近排序
  const cur = close ?? visible[0].value
  const resistances = visible
    .filter(p => p.side === 'resistance')
    .sort((a, b) => a.value - b.value)        // 由近及远(低→高)
  const supports = visible
    .filter(p => p.side === 'support')
    .sort((a, b) => b.value - a.value)         // 由近及远(高→低)
  const neutrals = visible.filter(p => p.side === 'neutral')

  const fmtPct = (v: number) => {
    if (!cur) return ''
    const pct = ((v - cur) / cur) * 100
    const sign = pct >= 0 ? '+' : ''
    return `${sign}${pct.toFixed(1)}%`
  }

  const Row = ({ p }: { p: PriceLevel }) => {
    // [R409] 下方文字行的小圆点必须与图上那条线同色 —— 它是"这一行说的是哪条线"
    // 的唯一线索。取值走同一个产地(LEVEL_PALETTE), 二型那三种线走角色映射。
    const color = (p.color ? fib2RoleColor(p.color, theme) : palette[p.type]) ?? CT().text
    const k = levelKey(p.type, p.value)
    const hit = hoveredKey === k
    const dim = hoveredKey != null && !hit
    return (
      <div
        onMouseEnter={() => onHover(k)}
        onMouseLeave={() => onHover(null)}
        className={`flex items-center gap-2 py-0.5 px-1.5 -mx-1.5 rounded transition-colors cursor-default ${
          hit ? 'bg-elevated/60' : ''
        }`}
        style={dim ? { opacity: 0.35 } : undefined}
      >
        <span className="h-1.5 w-1.5 rounded-full shrink-0 transition-transform" style={{ backgroundColor: color, transform: hit ? 'scale(1.5)' : 'scale(1)' }} />
        <span className={`text-[11px] w-24 shrink-0 truncate ${hit ? 'text-foreground font-medium' : 'text-secondary'}`}>{p.label}</span>
        <span className={`text-[11px] font-mono ${hit ? 'text-foreground font-bold' : 'text-foreground'}`}>{p.value.toFixed(2)}</span>
        <span className="text-[9px] font-mono text-muted">{fmtPct(p.value)}</span>
      </div>
    )
  }

  return (
    <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-1 rounded-lg border border-border/40 bg-base/20 px-3 py-2">
      {/* 当前价 */}
      <div className="sm:col-span-2 flex items-center gap-2 pb-1 border-b border-border/30 mb-0.5">
        <span className="text-[10px] text-muted">当前价</span>
        <span className="text-xs font-mono font-medium text-foreground">{cur.toFixed(2)}</span>
      </div>
      {/* 压力位(从近到远,即从低到高)倒序展示:最高的在最上 */}
      {resistances.length > 0 && (
        <div>
          <div className="text-[10px] font-medium text-bear mb-0.5">压力位 ↑</div>
          {[...resistances].reverse().map((p, i) => <Row key={`r-${i}`} p={p} />)}
        </div>
      )}
      {/* 支撑位 + 中性(枢轴位 P) */}
      <div>
        {supports.length > 0 && (
          <>
            <div className="text-[10px] font-medium text-bull mb-0.5">支撑位 ↓</div>
            {supports.map((p, i) => <Row key={`s-${i}`} p={p} />)}
          </>
        )}
        {neutrals.length > 0 && (
          <div className={supports.length > 0 ? 'mt-2' : ''}>
            {supports.length === 0 && <div className="text-[10px] font-medium text-muted mb-0.5">枢轴位</div>}
            {neutrals.map((p, i) => <Row key={`n-${i}`} p={p} />)}
          </div>
        )}
      </div>
    </div>
  )
}

// ===== 工具:收集要画的水平价位线(按开启的组 + 档位 + 强度配色) =====
// 注意:带状指标(布林带/Keltner/ATR)改用曲线渲染,不在此画水平线,避免重复。
function collectPriceLines(
  levels: Record<LevelType, PriceLevel[]> | undefined,
  active: Set<LevelType>,
  pivotRank: 1 | 2 | 3,
  palette: Record<string, string>,
  theme: 'dark' | 'light',
): { value: number; label: string; color: string; type: string }[] {
  if (!levels) return []
  const out: { value: number; label: string; color: string; type: string }[] = []
  for (const g of LEVEL_GROUPS) {
    if (!active.has(g.key)) continue
    for (const p of levels[g.key] ?? []) {
      // 枢轴点:按档位过滤(rank>P 的,只显示到选定的档位)
      if (p.type === 'pivot' && p.rank !== undefined && p.rank > pivotRank) continue
      // 波动通道类(boll / keltner三档 / atr_stop)整组走曲线渲染,不画水平线;
      // sr 组现为成交密集区水平点,直接画线即可,无需特判。
      if (p.type === 'boll' || p.type === 'keltner_s' || p.type === 'keltner_m'
          || p.type === 'keltner_l' || p.type === 'atr_stop') continue
      // [R409] 后端发来的 `color`(只有斐波那契二型会发)是**角色标识**, 不是
      // 最终颜色 —— 两套主题要用两个值, 而后端不知道当前是哪套。
      const base = p.color ? fib2RoleColor(p.color, theme) : palette[g.key]
      out.push({ value: p.value, label: p.label, color: strengthColor(p.strength, base), type: p.type })
    }
  }
  return out
}

function strengthColor(strength: string | undefined, base: string): string {
  // 强度靠透明度表达: 实色 / 次之 / 再次之。
  //
  // [R409] **原来是 D9(85%) 与 8C(55%)。** 而画线时还叠了一层
  // `opacity: 0.9`(原 0.7), 于是"弱"这一档实际落到 0.55×0.7 ≈ 0.39 ——
  // 用户那句「不能搞浅色」里最淡的一档就是它。现在收窄到 E6/BF, 叠完
  // 仍有 0.72, 强弱还是看得出来, 但没有一条线淡到要凑近看。
  if (strength === 'weak') return base + 'BF'
  if (strength === 'medium') return base + 'E6'
  return base
}

/**
 * [R410] 斐波那契二型的线太多, 这里决定**画哪几条**。
 *
 * 用户: 「好多根线, 好难抓住之前说的做不做在哪里做, 走不走这些」。细档能出到
 * 14 条回踩位 + 3 条推算位 + 作废线 + 均线, 将近二十根 —— 用户要在里面自己
 * 找出"该看的那几条", 而这套东西的价值本来只在其中很少几条上。
 *
 * 留下的三类, 正好对着用户问的三件事:
 *
 *   · **密集带里的**(后端已标成 `strong`)—— 帝纳波利的全部意思就在"几条挤在
 *     一起"这件事上, 单独一条本来就弱。这是「在哪里做」。**不论多远都留**:
 *     密集带离现价远不代表它不重要, 恰恰是提前知道它在哪才有用。
 *   · **作废线**(`strong`)—— 「走不走」的下界, 永远留。
 *   · **离现价最近的几条**(上下各 `NEAR_EACH_SIDE` 条)—— 眼下真会碰到的。
 *     远在天边的回踩位对当下没有意义。
 *
 * 上攻推算位一/二/三另由开关管, 默认不画 —— **按角色键过滤, 不按
 * 标签文字**, 否则后端改个名前端就会静默漏掉。
 *
 * **不改后端**: 后端照旧把整档算全发过来, 这里只决定画不画 —— 于是切档、
 * 开关推算位都是零延迟, 也不会因为"藏起来了"就把数据丢掉(开关上会如实写
 * 显示了几条、一共几条)。
 */
const NEAR_EACH_SIDE = 3

export function thinFib2(
  all: PriceLevel[],
  close: number | undefined,
  zone: { low: number; high: number } | null,
  showTargets: boolean,
): PriceLevel[] {
  const kept = showTargets ? all : all.filter(p => p.color !== FIB2_ROLE_TARGET)
  if (close == null || !Number.isFinite(close)) return kept
  const keep = new Set<PriceLevel>()
  for (const p of kept) {
    // 密集带里的 + 作废线: 后端给的都是 strong, 一律留
    if (p.strength === 'strong') keep.add(p)
    if (zone && p.value >= zone.low && p.value <= zone.high) keep.add(p)
  }
  // 再补上离现价最近的几条(上下各几条), 已经留下的不重复占名额
  for (const dir of [1, -1]) {
    const side = kept
      .filter(p => (dir > 0 ? p.value > close : p.value <= close))
      .sort((a, b) => Math.abs(a.value - close) - Math.abs(b.value - close))
    let n = 0
    for (const p of side) {
      if (n >= NEAR_EACH_SIDE) break
      if (!keep.has(p)) n++
      keep.add(p)
    }
  }
  // 保持后端给的原顺序 —— 下方文字行按它排, 顺序跳来跳去比多几条还难读
  return kept.filter(p => keep.has(p))
}


/** `#RRGGBB` + 0~1 的透明度 → `rgba(...)`。色带/标记用, 只接受 6 位 hex。 */
function withAlpha(hex: string, alpha: number): string {
  const n = parseInt(hex.slice(1), 16)
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${alpha})`
}

/** 价位唯一标识: 同类型同价格视为同一点位(用于联动高亮)。 */
function levelKey(type: string, value: number): string {
  return `${type}-${value.toFixed(2)}`
}

/** [R415] 副图刻度: DIFF/DEA 是价格差, 两位小数够看; 0 就写 0 */
function fmtSub(v: number): string {
  return v === 0 ? '0' : v.toFixed(2)
}
