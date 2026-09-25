/**
 * 宏观分析页(原「市场环境」页, 路由仍是 /regime) — 市场环境: 「现在」一张卡 + 环境综合分趋势。
 * [R503] 市场环境与情绪周期两组上下同时铺开(原来页签切换), 共用页头的时间范围。
 * [R505] 市场环境精简成两块。[R506] 情绪周期整组撤掉(后端照算, 页面不再显示), 「当前主线」
 * 从转折页页头搬进「现在」卡。
 *
 * 数据来源: 后端 regime_builder 批算的时序表(每日离散状态 + 多维指标)。
 * 不复刻 Dashboard 的当日总览(那是单日快照), 聚焦历史趋势与状态分布。
 *
 * 时间范围: 1年(250交易日) / 2年(500) / 自定义(1~1000天) / 全部(走日期范围)。
 * 美化对齐 Dashboard 设计语言: 半透明 surface 卡片 + 渐变竖条标题 + 语义色。
 */
import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import * as echarts from 'echarts'
import {
  Activity, RefreshCw, Loader2, Gauge, TrendingUp, TrendingDown, Minus,
  Pencil, Filter, X, Layers,
} from 'lucide-react'
import {
  api, type RegimeRow, type RegimeState, type MainlineFilter,
  REGIME_STATE_LABELS, REGIME_STATE_COLORS,
} from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import { useChartTheme } from '@/lib/theme'
import { COMPACT_LEGEND, LEGEND_GRID_TOP } from '@/lib/echartsLegend'
import { toast } from '@/components/Toast'
import { Modal } from '@/components/Modal'
import { cn } from '@/lib/cn'
import { PageShell } from '@/components/PageShell'
import { SEG, SEG_ITEM, SEG_OFF, SEG_ON, TYPE, buttonClass } from '@/components/ui'


/**
 * [R401] 趋势图的图例项。**单独列出来是为了让守卫数得着** ——
 * 写在 option 里的话, 哪天有人加第七条曲线, 图例又会在手机上折成两行、
 * 又一次画进绘图区, 而那件事在桌面上看不出来。
 * `test_regime_legend_fits.py` 按最窄那档宽度算过, 加项会当场红。
 */
export const TREND_LEGEND = ['综合分', '涨停数', '赚钱', '投机', '抗跌', '趋势']

// ── 时间范围 ──────────────────────────────────────────────
// 1年=250 交易日, 2年=500 交易日; 自定义 1~1000; 全部走 start/end 日期范围。
type RangePreset = '1y' | '2y' | 'all' | { custom: number }

const RANGE_LABEL: Record<'1y' | '2y' | 'all', string> = {
  '1y': '1年', '2y': '2年', all: '全部',
}

/** 把 preset 解析成 (start?, end?, limit?) 三元组供 history 接口使用。 */
function resolveHistoryRange(
  preset: RangePreset,
  coverage: { earliest_date: string | null; latest_date: string | null } | undefined,
): { start?: string; end?: string; limit?: number } {
  if (preset === '1y') return { limit: 250 }
  if (preset === '2y') return { limit: 500 }
  if (preset === 'all') {
    // 全部: 用 coverage 实际日期范围, 不传 limit
    return { start: coverage?.earliest_date ?? undefined, end: coverage?.latest_date ?? undefined }
  }
  // 自定义天数
  return { limit: Math.max(1, Math.min(1000, preset.custom)) }
}

/** 时间范围折成的"天数": 趋势图默认视窗与标题展示用。 */
function resolveDays(
  preset: RangePreset,
  coverage: { rows: number } | undefined,
): number {
  if (preset === '1y') return 250
  if (preset === '2y') return 500
  if (preset === 'all') return coverage?.rows && coverage.rows > 0 ? coverage.rows : 1000
  return Math.max(1, Math.min(1000, preset.custom))
}

function isPresetKey(p: RangePreset, k: '1y' | '2y' | 'all'): boolean {
  return p === k
}

// ── EChart hook ───────────────────────────────────────────
function useEChart(
  option: echarts.EChartsOption | null,
  deps: unknown[],
  onReady?: (inst: echarts.ECharts) => void,
) {
  const ref = useRef<HTMLDivElement>(null)
  const instRef = useRef<echarts.ECharts | null>(null)
  useEffect(() => {
    const onResize = () => instRef.current?.resize()
    window.addEventListener('resize', onResize)
    return () => {
      window.removeEventListener('resize', onResize)
      instRef.current?.dispose()
      instRef.current = null
    }
  }, [])
  useEffect(() => {
    if (!ref.current) return
    // 惰性 init: 图表容器可能条件渲染晚于组件挂载 (如情绪周期图依赖异步查询结果,
    // 冷加载时首帧 rows 为空 → div 不在 DOM, 仅挂载时跑一次的 init 会扑空)。
    // 数据到达后 option 变化触发本 effect, 此时 div 已挂载 — 补建实例再 setOption。
    if (!instRef.current) {
      instRef.current = echarts.init(ref.current, undefined, { renderer: 'canvas' })
      onReady?.(instRef.current)
    }
    if (option) {
      instRef.current.setOption(option, { notMerge: true })
      // 画布尺寸按容器当前实际尺寸重算。[R503] 原来两组页签切换时容器会经历
      // display:none → 可见, 靠调用方把 view 传进 deps 触发这里; 页签撤了, 留着 resize 兜底。
      instRef.current.resize()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [option, ...deps])
  return ref
}

// ── 页内通用 SectionTitle (对齐 Dashboard 渐变竖条风格) ────
function SectionTitle({ icon: Icon, title, hint }: { icon: typeof Activity; title: string; hint?: ReactNode }) {
  // [R401] 手机上标题被腰斩:「环境综合」换行「分趋势」。
  // 原因和那两排药丸一样 —— 右边的 `hint` 是同一行里的兄弟, 它一长(这一张图
  // 的说明有三小句), 标题就被压到只剩四个字宽(实测 375px 下 h2 只有 59px)。
  // 标题**不许断**, 说明**可以断**, 而这一行**可以换行** —— 说明放不下就
  // 整块挪到下一行去, 不去挤标题。
  return (
    <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
      <Icon className="h-4 w-4 shrink-0 text-accent" />
      {/* [R457] 卡片标题 L3(15px), 装饰小竖条撤了 —— 与大盘同一套 */}
      <h2 className={cn('shrink-0 whitespace-nowrap', TYPE.card)}>{title}</h2>
      {hint != null && <span className="ml-auto min-w-0 text-micro text-muted font-mono">{hint}</span>}
    </div>
  )
}

// ── [R503] 两组内容的组标题 —— 比卡片标题(SectionTitle, L3)高一级(L2) ──
// 两组同时铺开之后, 读的人得一眼分清自己在看哪一组; 原来这件事由页签做。
// 同 SectionTitle 的 R401 规矩: 标题不许断, 说明放不下就整块换行。
function GroupTitle({ id, icon: Icon, title, hint }: { id: string; icon: typeof Activity; title: string; hint: string }) {
  return (
    <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5 border-b border-border pb-1.5">
      <Icon className="h-4 w-4 shrink-0 translate-y-0.5 text-accent" />
      <h2 id={id} className={cn('shrink-0 whitespace-nowrap', TYPE.section)}>{title}</h2>
      <span className="min-w-0 text-micro text-muted">{hint}</span>
    </div>
  )
}

// ── 卡片容器样式 (Dashboard 同款) ─────────────────────────
const cardCls = 'rounded-card border border-border bg-surface'   // [R457] 实边框实底, 与全站卡片同一套

// ── 主组件 ────────────────────────────────────────────────
export function Regime() {
  const qc = useQueryClient()
  const [range, setRange] = useState<RangePreset>('1y')
  const [customOpen, setCustomOpen] = useState(false)
  const ct = useChartTheme()

  // coverage: "全部"模式 + 标题展示依赖
  const coverage = useQuery({
    queryKey: QK.regimeCoverage,
    queryFn: () => api.regimeCoverage(),
    staleTime: 5 * 60 * 1000,
  })

  const days = resolveDays(range, coverage.data)
  const histRange = resolveHistoryRange(range, coverage.data)

  // queryKey 用 range 的完整三元组区分: limit / start+end(全部) / custom天数
  const history = useQuery({
    queryKey: ['regime-history', range] as const,
    queryFn: () => api.regimeHistory(histRange.start, histRange.end, histRange.limit),
    staleTime: 5 * 60 * 1000,
  })
  const [recomputing, setRecomputing] = useState(false)
  // [R506] 当前主线 —— 原在转折页页头。与今日总览同一个后端函数出(停更判定只在那一处),
  // 不随页头的时间范围变: 它说的就是「今天」。
  const mainlineNow = useQuery({
    queryKey: QK.todayMainline,
    queryFn: () => api.todayMainline(),
    staleTime: 5 * 60 * 1000,
  })
  const [filterOpen, setFilterOpen] = useState(false)
  const ml = mainlineNow.data?.mainline ?? null

  const rows: RegimeRow[] = history.data?.rows ?? []
  // [fork 增强] 当日数据未落盘时, 末行是重算产生的"空数据行"(0板0家) ——
  // 拿它当「最新状态」会凭空多出一天弱势。「现在」卡用最近一个"数据齐"的定稿日。
  const lastRaw = rows.length > 0 ? rows[rows.length - 1] : null
  const lastUnsettled = !!(lastRaw
    && (lastRaw.max_consecutive ?? 0) === 0
    && (lastRaw.first_board ?? 0) === 0
    && (lastRaw.ge2_count ?? 0) === 0
    && (lastRaw.limit_up ?? 0) === 0)
  const settledRows = lastUnsettled ? rows.slice(0, -1) : rows
  const latest = settledRows.length > 0 ? settledRows[settledRows.length - 1] : null

  // ── 当前势头: 末尾连续同态天数 + score 5日斜率(改善/恶化) + 上次弱势距今 ──
  const momentum = useMemo(() => {
    if (rows.length === 0) return null
    const lastState = rows[rows.length - 1].state
    // 末尾连续同态天数
    let streak = 1
    for (let i = rows.length - 2; i >= 0; i--) {
      if (rows[i].state === lastState) streak++
      else break
    }
    // score 5日斜率(正=改善, 负=恶化)
    const recent = rows.slice(-5)
    const slope = recent.length >= 2
      ? (recent[recent.length - 1].score - recent[0].score) / (recent.length - 1)
      : 0
    // 上次弱势(weak/lean_weak)距今天数
    let lastWeakGap = 0
    for (let i = rows.length - 1; i >= 0; i--) {
      if (rows[i].state === 'weak' || rows[i].state === 'lean_weak') {
        lastWeakGap = rows.length - 1 - i
        break
      }
    }
    return { streak, state: lastState, slope, lastWeakGap }
  }, [rows])




  // 趋势图: 综合分主线 + 4 子维度曲线(可切换) + 状态背景色带 + 涨停数柱状
  const trendOption = useMemo<echarts.EChartsOption | null>(() => {
    if (rows.length === 0) return null
    const dates = rows.map(r => r.date)
    const scores = rows.map(r => r.score)
    const limitUps = rows.map(r => r.limit_up)
    const profit = rows.map(r => r.profit_score ?? null)
    const speculation = rows.map(r => r.speculation_score ?? null)
    const resilience = rows.map(r => r.resilience_score ?? null)
    const trend = rows.map(r => r.trend_score ?? null)

    // 状态背景色带: 合并连续同状态日期段, 每段用状态色低透明度着色
    const stateBands: any[] = []
    let bandStart = rows[0]?.date
    let prevState = rows[0]?.state
    rows.forEach((r, i) => {
      if (r.state !== prevState || i === rows.length - 1) {
        const bandEnd = i === rows.length - 1 ? r.date : rows[i - 1].date
        if (prevState && REGIME_STATE_COLORS[prevState as RegimeState]) {
          stateBands.push([
            { xAxis: bandStart, itemStyle: { color: REGIME_STATE_COLORS[prevState as RegimeState], opacity: 0.08 } },
            { xAxis: bandEnd },
          ])
        }
        bandStart = r.date
        prevState = r.state
      }
    })

    const subLineStyle = { width: 1.2, type: 'dotted' as const, opacity: 0.8 }

    return {
      backgroundColor: 'transparent',
      tooltip: { trigger: 'axis', backgroundColor: ct.tooltipBg, borderColor: ct.tooltipBorder, textStyle: { color: ct.tooltipText } },
      // [R401] 同上 —— 这张图就是用户截图里图例压住轴名的那一张。
      legend: {
        data: TREND_LEGEND,
        textStyle: { color: ct.text, fontSize: COMPACT_LEGEND.fontSize }, top: 0,
        itemWidth: COMPACT_LEGEND.itemWidth,
        itemHeight: COMPACT_LEGEND.itemHeight,
        itemGap: COMPACT_LEGEND.itemGap,
        // 默认只显示综合分 + 涨停数(简洁); 4 个子维度默认隐藏, 点图例展开看驱动因素
        selected: { '综合分': true, '涨停数': true, '赚钱': false, '投机': false, '抗跌': false, '趋势': false },
      },
      grid: { left: 48, right: 64, top: LEGEND_GRID_TOP, bottom: 56 },
      xAxis: {
        type: 'category', data: dates, boundaryGap: false,
        axisLabel: { color: ct.text, fontSize: 10, formatter: (v: string) => v.slice(5) },
        axisLine: { lineStyle: { color: ct.grid } },
      },
      yAxis: [
        { type: 'value', name: '涨停', position: 'left', axisLabel: { color: ct.text, fontSize: 10 }, splitLine: { show: false }, nameTextStyle: { color: ct.text } },
        { type: 'value', name: '综合分', min: 0, max: 100, position: 'right', axisLabel: { color: ct.text, fontSize: 10 }, splitLine: { lineStyle: { color: ct.grid } }, nameTextStyle: { color: ct.text } },
      ],
      dataZoom: [
        { type: 'inside', start: Math.max(0, 100 - (60 / days) * 100) },
        { type: 'slider', bottom: 8, height: 16, borderColor: ct.border, fillerColor: ct.zoomFill, textStyle: { color: ct.text } },
      ],
      series: [
        // 涨停数柱状(半透明背景, 左轴)
        { name: '涨停数', type: 'bar', data: limitUps, yAxisIndex: 0, barMaxWidth: 6,
          itemStyle: { color: REGIME_STATE_COLORS.strong, opacity: 0.35 }, z: 1 },
        // 4 子维度曲线(右轴=综合分): 帮助理解综合分由什么驱动(点图例可切换)
        { name: '赚钱', type: 'line', data: profit, smooth: true, symbol: 'none', yAxisIndex: 1,
          lineStyle: { ...subLineStyle, color: '#f59e0b' }, z: 2 },
        { name: '投机', type: 'line', data: speculation, smooth: true, symbol: 'none', yAxisIndex: 1,
          lineStyle: { ...subLineStyle, color: '#06b6d4' }, z: 2 },
        { name: '抗跌', type: 'line', data: resilience, smooth: true, symbol: 'none', yAxisIndex: 1,
          lineStyle: { ...subLineStyle, color: '#10b981' }, z: 2 },
        { name: '趋势', type: 'line', data: trend, smooth: true, symbol: 'none', yAxisIndex: 1,
          lineStyle: { ...subLineStyle, color: '#3b82f6' }, z: 2 },
        // 综合分主线(加粗置顶, 右轴) + 状态背景色带 + 阈值横虚线
        { name: '综合分', type: 'line', data: scores, smooth: true, symbol: 'none', yAxisIndex: 1,
          lineStyle: { width: 1.5, color: ct.textStrong }, areaStyle: { opacity: 0.06 }, z: 3,
          markArea: { silent: true, data: stateBands },
          markLine: {
            silent: true,
            symbol: 'none',
            lineStyle: { type: 'dashed', width: 1.5 },
            label: { position: 'end', fontSize: 10, fontWeight: 'bold', padding: [2, 4], borderRadius: 3 },
            data: [
              { yAxis: 70, lineStyle: { color: REGIME_STATE_COLORS.strong },
                label: { formatter: '强势 70', color: '#fff', backgroundColor: REGIME_STATE_COLORS.strong } },
              { yAxis: 55, lineStyle: { color: REGIME_STATE_COLORS.lean_strong },
                label: { formatter: '偏强 55', color: '#fff', backgroundColor: REGIME_STATE_COLORS.lean_strong } },
              { yAxis: 45, lineStyle: { color: REGIME_STATE_COLORS.range },
                label: { formatter: '震荡 45', color: '#fff', backgroundColor: REGIME_STATE_COLORS.range } },
              { yAxis: 30, lineStyle: { color: REGIME_STATE_COLORS.lean_weak },
                label: { formatter: '偏弱 30', color: '#fff', backgroundColor: REGIME_STATE_COLORS.lean_weak } },
            ],
          } },
      ],
    }
  }, [rows, days, ct])
  const trendRef = useEChart(trendOption, [trendOption])



  const handleRecompute = async () => {
    setRecomputing(true)
    try {
      const r = await api.regimeRecompute()
      if ((r as any).ok === false) {
        toast(`重算失败 · ${(r as any).error ?? '未知原因'}`, 'error')
        return
      }
      const warn = (r as any).warnings as string[] | null | undefined
      if (warn?.length) {
        toast(`重算完成(附加步骤有失败):${warn.join(';')}`, 'error')
      } else {
        toast(r.computed > 0 ? `重算完成 · 新增 ${r.computed} 天` : '重算完成 · 数据已是最新', 'success')
      }
      await Promise.all([
        qc.invalidateQueries({ queryKey: ['regime-history'] }),
        qc.invalidateQueries({ queryKey: ['regime-latest'] }),
        qc.invalidateQueries({ queryKey: ['regime-phases'] }),
        qc.invalidateQueries({ queryKey: ['regime-mainline'] }),
        qc.invalidateQueries({ queryKey: QK.todayMainline }),
        qc.invalidateQueries({ queryKey: QK.regimeCoverage }),
      ])
    } catch (e) {
      toast(`重算失败 · ${String((e as Error)?.message || e)}`, 'error')
    } finally {
      setRecomputing(false)
    }
  }

  // 自定义按钮标签
  const customLabel = typeof range === 'object'
    ? `自定义 ${range.custom}天`
    : '自定义'

  return (
    // [R60] 这一页原来手搓了一个渐变条头部 + 自己的 1440px 限宽, 和别的页
    // 在标题字号、边界、留白上都对不上。头部交给 PageShell, 页内不再自成一套。
    <PageShell
      // [R503] 菜单「市场环境」改名「宏观分析」—— 页名跟菜单走; 「市场环境」仍是下面第一组的名字
      title="宏观分析"
      titleExtra={<Activity className="h-4 w-4 text-accent" />}
      subtitle="市场环境 · 当前主线 · 综合分趋势"
      right={(
          // [R401] 与下面视图药丸同一个毛病、同一个修法: 定高药丸 + 允许被压扁
          // = 字换行之后画到药丸外面。这一组在窄屏上还会和重算按钮争宽度。
          // (这里只能写 `//`: 括号里是**表达式位置**, `{/* */}` 只在 JSX 子节点
          //  位置合法 —— R395 在同一个坑里栽过一次, 这次一次写对。)
          <div className="flex flex-wrap items-center gap-2">
            {/* 时间范围按钮组 */}
            <div className={SEG}>
              {(['1y', '2y', 'all'] as const).map(k => (
                <button
                  key={k}
                  onClick={() => setRange(k)}
                  className={cn(SEG_ITEM, 'shrink-0 whitespace-nowrap', isPresetKey(range, k) ? SEG_ON : SEG_OFF)}
                >
                  {RANGE_LABEL[k]}
                </button>
              ))}
              <button
                onClick={() => setCustomOpen(true)}
                className={cn(SEG_ITEM, 'shrink-0 whitespace-nowrap', typeof range === 'object' ? SEG_ON : SEG_OFF)}
              >
                {typeof range === 'object' && <Pencil className="h-3 w-3 shrink-0" />}
                {customLabel}
              </button>
            </div>
            {/* 重算 */}
            <button onClick={handleRecompute} disabled={recomputing}
              className={buttonClass({}, 'shrink-0 gap-1.5')}>
              {recomputing ? <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5 shrink-0" />}
              {recomputing ? '重算中…' : '重算'}
            </button>
          </div>
      )}
    >
      {/* [R503] 两组内容原来是同页切换(页签: 市场环境 / 情绪周期), 后来上下同时铺开、共用时间范围。
          [R506] 情绪周期整组撤掉 —— 它全部由涨停梯队算出, 衡量的是打板情绪; 用户试用一段时间
          判定对趋势持仓没用, 且与综合分的「投机」维是同一批数。后端照算(对话里 AI 助手的 get_regime 工具还读阶段), 页面不再显示。 */}
      {/* ══ 市场环境: 「现在」一张卡 + 环境综合分趋势 ══ */}
      <section className="space-y-4" aria-labelledby="macro-regime">
      <GroupTitle id="macro-regime" icon={Activity} title="市场环境" hint="每日环境状态 · 赚钱效应 · 趋势分析" />

      {/* ── [R505] 「现在」一张卡: 最新状态 + 当前势头 + 四维拆解 ([R506] + 当前主线) ──
          原来是四张卡 + 状态时间轴 + 状态分布饼图 + 日历热力图。后三块与趋势图的
          背景色带是同一份「每天哪一档」画了四遍; 「状态转换次数」是纯统计, 不指向任何动作。
          留下的三样都是**解读**: 现在在哪一档、在变好还是变坏、是哪一维在拉。 */}
      {latest ? (
        <div className={cn(cardCls, 'grid gap-3 p-3 sm:grid-cols-[auto_auto_auto_1fr] sm:items-center sm:gap-0 sm:divide-x sm:divide-border')}>
          <div className="sm:pr-5">
            <div className="flex items-center gap-1.5 text-micro text-muted">
              <Gauge className="h-3 w-3" /> 最新状态 · {latest.date}
            </div>
            <div className="mt-1 flex items-baseline gap-2">
              <span className="text-2xl font-bold" style={{ color: REGIME_STATE_COLORS[latest.state] }}>
                {REGIME_STATE_LABELS[latest.state]}
              </span>
              <span className="text-sm text-muted">{latest.score} 分</span>
            </div>
          </div>

          <div className="sm:px-5">
            <div className="flex items-center gap-1.5 text-micro text-muted">
              {(() => {
                const TrendIcon = (momentum?.slope ?? 0) > 0.5 ? TrendingUp : (momentum?.slope ?? 0) < -0.5 ? TrendingDown : Minus
                return <TrendIcon className={`h-3 w-3 ${(momentum?.slope ?? 0) > 0.5 ? 'text-bull' : (momentum?.slope ?? 0) < -0.5 ? 'text-bear' : 'text-muted'}`} />
              })()} 当前势头
            </div>
            {momentum ? (
              <>
                <div className="mt-1 text-sm font-semibold text-foreground">
                  连续 <span style={{ color: REGIME_STATE_COLORS[momentum.state] }}>{momentum.streak}</span> 天{REGIME_STATE_LABELS[momentum.state]}
                </div>
                <div className="mt-0.5 text-micro text-muted">
                  5日{(momentum.slope > 0 ? '改善' : momentum.slope < 0 ? '恶化' : '持平')}
                  {momentum.lastWeakGap > 0 && ` · 上次弱势 ${momentum.lastWeakGap} 天前`}
                </div>
              </>
            ) : <div className="mt-1 text-sm text-muted">—</div>}
          </div>

          {/* [R506] 当前主线 —— 从转折页页头搬来, 色与停更规矩原样带过来:
              主线用琥珀(看盘软件里「领涨/焦点」的通行色, 不占红绿, R421 起替代品红);
              **停更要变灰并改标题** —— 几天前的主线长得跟今天的一模一样, 比不显示更糟。 */}
          <div className="min-w-0 sm:px-5">
            <div className="flex items-center gap-1.5 text-micro text-muted">
              <Layers className="h-3 w-3" /> {ml?.stale ? '当前主线(停更)' : '当前主线'}
              <button
                type="button"
                onClick={() => setFilterOpen(v => !v)}
                aria-expanded={filterOpen}
                title="主线过滤: 宽基概念屏蔽 / 统计剔除 ST"
                className={cn('ml-1 inline-flex items-center gap-0.5 rounded-btn border px-1.5 py-px text-micro transition-colors',
                  filterOpen ? 'border-accent/50 text-accent' : 'border-border bg-base text-secondary hover:text-accent')}
              >
                <Filter className="h-2.5 w-2.5" /> 过滤
              </button>
            </div>
            {ml ? (
              <>
                <div className={cn('mt-1 truncate text-sm font-semibold', ml.stale ? 'text-muted' : 'text-amber-300')}
                  title={ml.stale
                    ? `主线数据停在 ${ml.date},已经 ${ml.age_days} 天没更新 —— 只作展示`
                    : `按 ${ml.date} 的涨停梯队聚合`}>
                  {ml.rows[0].member}
                </div>
                <div className="mt-0.5 truncate text-micro text-muted">
                  {ml.rows.length > 1 ? `其后 ${ml.rows.slice(1, 3).map(r => r.member).join(' · ')}` : ml.date}
                </div>
              </>
            ) : <div className="mt-1 text-sm text-muted">{mainlineNow.isLoading ? '…' : '暂无主线数据'}</div>}
          </div>

          <div className="min-w-0 sm:pl-5">
            <div className="flex items-center gap-1.5 text-micro text-muted">
              <Activity className="h-3 w-3" /> 四维拆解 · 是哪一维在拉高或拖低
            </div>
            {/* [R511] 用户:「四个维度用回之前四行的样子」—— 回到 R505 之前那张小卡的排法: 一维一行,
                四行上下叠, 条子撑满。R505 并卡后这一栏是 1fr, 宽屏上会很宽, 所以整组封顶 max-w-xs
                (320px), 条长与原来四张并排小卡里的那一张相当。
                [R510] 轨道底色用 --elevated —— 原来是 --base, R501 之后页底是纯白, 轨道在白卡上
                看不见, 于是 0 分那一维什么都没画, 像坏了。 */}
            <div className="mt-1.5 max-w-xs space-y-1">
              {([
                { label: '赚钱', val: latest.profit_score, color: '#f59e0b' },
                { label: '投机', val: latest.speculation_score, color: '#06b6d4' },
                { label: '抗跌', val: latest.resilience_score, color: '#10b981' },
                { label: '趋势', val: latest.trend_score, color: '#3b82f6' },
              ] as const).map(d => (
                <div key={d.label} className="flex items-center gap-1.5" title={`${d.label} ${d.val != null ? Math.round(d.val) : '—'} / 100`}>
                  <span className="w-6 shrink-0 text-micro text-muted">{d.label}</span>
                  <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-elevated">
                    <div className="h-full rounded-full"
                      style={{ width: `${d.val ?? 0}%`, backgroundColor: d.color }} />
                  </div>
                  <span className="w-5 shrink-0 text-right text-micro font-mono text-muted">{d.val != null ? Math.round(d.val) : '—'}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      ) : (
        <div className="rounded-card border border-dashed border-border p-8 text-center text-sm text-muted">
          {history.isLoading ? '加载中…' : '暂无环境数据，请先运行盘后管道或点击「重算」'}
        </div>
      )}
      {filterOpen && (
        <MainlineFilterPanel
          filter={mainlineNow.data?.filter ?? undefined}
          onDone={async () => {
            await qc.invalidateQueries({ queryKey: QK.todayMainline })
            await qc.invalidateQueries({ queryKey: ['regime-history'] })
          }}
        />
      )}

      {/* ── 趋势图: 这一组的主体, 独占整行(原来右边三分之一给了状态分布饼图) ── */}
      <div className={cn(cardCls, 'p-3')}>
        <SectionTitle icon={Activity} title="环境综合分趋势"
          hint="综合分(粗) · 赚钱/投机/抗跌/趋势(细, 可点图例切换) · 背景色=状态" />
        <div ref={trendRef} className="mt-2 h-[340px]" />
      </div>

      </section>{/* /市场环境 */}

      {/* ── 自定义天数弹窗 ── */}
      {customOpen && (
        <CustomDaysModal
          current={typeof range === 'object' ? range.custom : 120}
          onClose={() => setCustomOpen(false)}
          onApply={(d) => { setRange({ custom: d }); setCustomOpen(false) }}
        />
      )}
    </PageShell>
  )
}

// ── 主线过滤设置面板 ──────────────────────────────────────
// 宽基/风格标签(融资融券/沪深股通等数千成分)会霸占主线榜首。默认按成员数
// 上限过滤; 用户可调阈值并按名称屏蔽特定概念, 保存后自动重算主线。
// ST 剔除开关联动市场环境与主线的统计口径 — 切换时额外触发 regime 全量重算。
function MainlineFilterPanel({ filter, onDone }: {
  filter: MainlineFilter | undefined
  onDone: () => Promise<void>
}) {
  const [minMembers, setMinMembers] = useState(String(filter?.min_members ?? 4))
  const [maxMembers, setMaxMembers] = useState(String(filter?.max_members ?? 600))
  const [blacklist, setBlacklist] = useState<string[]>(filter?.blacklist ?? [])
  const [excludeSt, setExcludeSt] = useState(filter?.exclude_st ?? true)
  const [input, setInput] = useState('')
  const [saving, setSaving] = useState(false)

  const addTag = () => {
    const v = input.trim()
    if (v && !blacklist.includes(v)) setBlacklist([...blacklist, v])
    setInput('')
  }

  const save = async () => {
    setSaving(true)
    try {
      await api.mainlineFilterUpdate({
        min_members: Math.max(1, Number(minMembers) || 4),
        max_members: Math.max(50, Number(maxMembers) || 600),
        blacklist,
        exclude_st: excludeSt,
      })
      const stChanged = excludeSt !== (filter?.exclude_st ?? true)
      if (stChanged) {
        // 口径切换影响市场环境的统计(涨停/连板剔除 ST), 需全量重算 regime+主线(较重, 需等待)
        await api.regimeRecompute()
        toast('过滤已保存, 主线与市场环境已全量重算', 'success')
      } else {
        await api.regimeMainlineRecompute()
        toast('过滤已保存, 主线已重算', 'success')
      }
      await onDone()
    } catch (e) {
      toast(`保存失败 · ${String((e as Error)?.message || e)}`, 'error')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="rounded-card border border-border bg-surface p-3">
      <div className="flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1">
          <span className="text-micro text-muted">成员数上限(过滤宽基标签)</span>
          <input type="number" min={50} max={5000} value={maxMembers}
            onChange={e => setMaxMembers(e.target.value)}
            className="h-7 w-24 rounded-input border border-border bg-base px-2 text-xs text-foreground outline-none focus:border-accent" />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-micro text-muted">成员数下限</span>
          <input type="number" min={1} max={200} value={minMembers}
            onChange={e => setMinMembers(e.target.value)}
            className="h-7 w-20 rounded-input border border-border bg-base px-2 text-xs text-foreground outline-none focus:border-accent" />
        </label>
        <div className="flex min-w-[220px] flex-1 flex-col gap-1">
          <span className="text-micro text-muted">按名称屏蔽(回车添加)</span>
          <div className="flex items-center gap-1.5">
            <input value={input} onChange={e => setInput(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); addTag() } }}
              placeholder="如: 融资融券、沪股通"
              className="h-7 flex-1 rounded-input border border-border bg-base px-2 text-xs text-foreground outline-none focus:border-accent" />
          </div>
          {blacklist.length > 0 && (
            <div className="mt-1 flex flex-wrap gap-1">
              {blacklist.map(b => (
                <span key={b} className="inline-flex items-center gap-1 rounded bg-accent/10 px-1.5 py-px text-micro text-accent">
                  {b}
                  <button onClick={() => setBlacklist(blacklist.filter(x => x !== b))} className="hover:text-foreground">
                    <X className="h-2.5 w-2.5" />
                  </button>
                </span>
              ))}
            </div>
          )}
        </div>
        <button onClick={save} disabled={saving}
          className="h-7 rounded-btn bg-accent px-3 text-xs font-medium text-white hover:bg-accent/90 disabled:opacity-50">
          {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : '保存并重算'}
        </button>
      </div>
      <div className="mt-2 flex items-center gap-2 border-t border-border/60 pt-2">
        <button
          type="button"
          role="switch"
          aria-checked={excludeSt}
          aria-label="统计剔除 ST 股"
          onClick={() => setExcludeSt(v => !v)}
          className={cn(
            'relative inline-flex h-4.5 w-8 items-center rounded-full border transition-ui duration-expand',
            excludeSt ? 'border-accent/50 bg-accent' : 'border-border bg-elevated hover:border-muted',
          )}
        >
          <span className={cn(
            'inline-block h-3 w-3 rounded-full border border-black/5 bg-white shadow-sm transition-transform duration-expand',
            excludeSt ? 'translate-x-[17px]' : 'translate-x-0.5',
          )} />
        </button>
        <span className="text-xs text-secondary">
          统计剔除 ST 股
          <span className="ml-1.5 text-micro text-muted">主线 + 市场环境统一口径; 切换后自动全量重算(约 1-2 分钟)</span>
        </span>
      </div>
      <div className="mt-1.5 text-micro text-muted">
        说明: 成分股数超过上限的概念(如 融资融券~7700家/沪深股通~3300家)视为宽基/风格标签, 不参与主线排名;
        风险警示股(名称含 ST)不参与涨停梯队统计 — 主板 5% 便宜板时代曾系统性霸榜, 且 ST 是状态桶而非题材。修改后自动重算全部历史(秒级~分钟级)。
      </div>
    </div>
  )
}

// ── 自定义天数输入弹窗 ────────────────────────────────────
function CustomDaysModal({ current, onClose, onApply }: {
  current: number
  onClose: () => void
  onApply: (days: number) => void
}) {
  const [val, setVal] = useState(String(current))
  const inputRef = useRef<HTMLInputElement>(null)

  const apply = () => {
    const n = Math.max(1, Math.min(1000, Math.floor(Number(val) || 0)))
    if (Number.isNaN(n) || n < 1) {
      toast('请输入 1 ~ 1000 之间的天数', 'error')
      return
    }
    onApply(n)
  }

  return (
    <Modal onClose={onClose} ariaLabel="自定义天数" initialFocusRef={inputRef}
      panelClassName="w-[88vw] max-w-xs bg-surface border border-border rounded-card shadow-xl p-4">
      <div className="space-y-3">
        <div>
          <div className="text-xs font-medium text-foreground">自定义天数</div>
          <div className="mt-0.5 text-micro text-muted">范围 1 ~ 1000 个交易日</div>
        </div>
        <input
          ref={inputRef}
          type="number"
          min={1}
          max={1000}
          value={val}
          onChange={e => setVal(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') apply() }}
          className="h-8 w-full rounded-input border border-border bg-base px-2.5 text-sm text-foreground outline-none focus:border-accent"
        />
        {/* 快捷预设 */}
        <div className="flex flex-wrap gap-1.5">
          {[60, 90, 180, 365].map(d => (
            <button key={d} onClick={() => setVal(String(d))}
              className="h-6 rounded-btn border border-border bg-base px-2 text-xs text-secondary hover:text-accent hover:border-accent/40 transition-colors">
              {d}天
            </button>
          ))}
        </div>
        <div className="flex justify-end gap-2 pt-1">
          <button onClick={onClose}
            className="h-7 rounded-btn px-3 text-xs text-secondary hover:text-foreground transition-colors">
            取消
          </button>
          <button onClick={apply}
            className="h-7 rounded-btn bg-accent px-3 text-xs font-medium text-white hover:bg-accent/90 transition-colors">
            应用
          </button>
        </div>
      </div>
    </Modal>
  )
}
