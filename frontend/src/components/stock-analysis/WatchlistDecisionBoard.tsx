import { useState, useMemo, useEffect, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Star, Wallet, Sparkles, Loader2, ArrowUp, ArrowDown, RefreshCw, FileText, Download, Bell } from 'lucide-react'
import { api, type ChannelEvent, type ChannelPhase, type EffectivePosition, type Playbook, type ExitLine, type KeltnerBands, type TrendInfo, type Urgency } from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import { pickStale, SIGNAL_TTL_HOURS } from '@/lib/signalFreshness'   // [R131] 增量分析判据
import { toast } from '@/components/Toast'
import { useHistoryReports, openHistoryReport, loadHistory } from '@/lib/stockAnalysisStore'
import { trendBadgeCls } from '@/components/stock-analysis/TrendStateBar'
import { StockReviewDialog, type ReviewTab } from '@/components/stock-analysis/StockReviewDialog'
// [R167] 导出与两个单元格从本文件拆出 —— 拆前 933 行, 顶部堆着两张配色表和一整份
// HTML 导出模板, 主组件被压在后面。
import { storage } from '@/lib/storage'
import { buildBoardHtml } from '@/lib/decisionBoardHtmlExport'
import { DEFAULT_EXPORT_KEYS } from '@/lib/decisionBoardExportColumns'
import { ExportColumnsDialog } from '@/components/stock-analysis/decision-board/ExportColumnsDialog'
import { ChannelStateCell, ConclusionCell, NUM, TD_BASE } from '@/components/stock-analysis/decision-board/cells'
import { ComboTableDialog } from '@/components/stock-analysis/decision-board/ComboTableDialog'
import { LotsLink } from '@/components/stock-analysis/decision-board/LotsLink'
import { GlossaryButton } from '@/components/stock-analysis/decision-board/GlossaryDialog'
// [R169] 合并视图(手填 ⊕ 上游批次登记), 字段说明见 api.ts 的 EffectivePosition
type Position = EffectivePosition
type WatchPoint = { direction: 'up' | 'down'; price: number; label?: string; action?: string; reason?: string }
type Signal = { signal: string; confidence: number; reason: string; close: number | null; created_at: string; watch_points?: WatchPoint[] }
type SortKey = 'play' | 'urgency' | 'name' | 'close' | 'changePct' | 'held' | 'cost' | 'pnl' | 'exit'
  | 'trend' | 'ks' | 'km' | 'kl' | 'spread' | 'verdict' | 'confidence' | 'signal' | 'report'
const SIGNAL_RANK: Record<string, number> = { buy: 0, sell: 1, hold: 2, watch: 3 }
/**
 * [R194] 决策台的列宽表 —— colgroup 与空表提示的 colSpan 同源。
 *
 * 不写宽度的话浏览器会把富余空间全塞给 max-content 最大的那一列(AI 信号),
 * 别的列挤在一起; 写死 px 又不随视口走。
 *
 * 分配原则: 前半段(该动~止盈线)是查对用的, 给到"完整显示不换行"就够;
 * 后半段(趋势/三档通道/结论/AI 信号)才是要盯的, 富余空间往那边给。
 * 这些列内容宽度固定(输入框、徽标、等宽数字), 所以百分比调小**不会压字** ——
 * 内容宽度是硬底线, 百分比只决定"能不能多吃富余空间"。
 *
 * **顺序必须与 thead 里的 <th> 一一对应。**
 */
const BOARD_COLS = [
  { label: '标的', w: '9%' },
  // [R212] 「现价」「涨跌」合成一列。用户: 「这两列合成为『现价/涨跌』这样为一列」。
  // 两个数天生一起读 —— 拆成两列只是让眼睛多跳一次。
  { label: '现价/涨跌', w: '6%' },
  { label: '仓位', w: '3%' },
  { label: '成本', w: '6%' },        // 两个输入框
  { label: '浮盈', w: '3.5%' },
  // [R212] 「止盈线」那一列撤掉了。用户: 「止盈线这一列不要了」。
  // **信息没丢**: 出场线破了或逼近, 「结论」列会直接判成「按纪律走」/「盯着」
  // 并把线价写在徽标上 —— 那比单独一列更早进视线。排序键与判定都还在。
  // [R211] 「量化通道」(测量) + 「通道态势」(结论) + 「趋势」(六态) 三列并一列。
  // 六态与通道阶段答的是同一个问题(往哪走), 只是方法不同 —— 放一格里,
  // 它们什么时候一致、什么时候打架, 上下一对就看见了。
  { label: '走势', w: '11%' },
  // [R212] 「贵不贵」(位置) + 「怎么办」(动作) 合成一列, 竖排, 摆在 AI 之前。
  // 用户: 「贵不贵在上换行怎么办在下」「结论这行放在 ai 分析前一列」。
  // 顺序是有讲究的: 上面是事实(这个价算贵还是便宜), 下面是结论(所以今天该干嘛)。
  { label: '结论', w: '16%' },
  { label: 'AI 分析', w: '7%' },     // R130 上下两行: 报告胶囊 / ✨分析 + 🔔提醒
  { label: 'AI 信号', w: '' },       // 不给宽度, 吃掉剩下的 —— 只有它是整段文字
] as const

// [fork 增强] 六态排序权重:多头在前(上涨趋势 → 下跌趋势)
const TREND_RANK: Record<string, number> = { UT: 0, NR: 1, SR: 2, SREA: 3, NREA: 4, DT: 5 }

// AI 信号 → 展示标签/配色。买入=红(A股涨红), 卖出=绿, 持有=琥珀, 观望=灰。
const SIGNAL_META: Record<string, { label: string; cls: string }> = {
  buy: { label: '买入', cls: 'border-red-400/40 bg-red-400/10 text-red-400' },
  sell: { label: '卖出', cls: 'border-emerald-400/40 bg-emerald-400/10 text-emerald-400' },
  hold: { label: '持有', cls: 'border-amber-400/40 bg-amber-400/10 text-amber-400' },
  watch: { label: '观望', cls: 'border-border bg-base text-muted' },
}

function fmtAgo(iso?: string): string {
  if (!iso) return ''
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000)
  if (s < 60) return '刚刚'
  if (s < 3600) return `${Math.floor(s / 60)}分前`
  if (s < 86400) return `${Math.floor(s / 3600)}小时前`
  return `${Math.floor(s / 86400)}天前`
}

/** 自选决策台 —— 个股分析页的整页主体: 一行一只自选, 点标的即弹出关键价位分析,
 *  并可标记仓位/成本、纵观对比浮盈。[R28] 起不再折叠(整页就它一个, 没有要让位的东西)。 */
export function WatchlistDecisionBoard({ currentSymbol, onSelect, onPreview, onAnalyze, onPriceAlert, locateNonce }: {
  currentSymbol: string
  /** [R157] 页头「定位」按钮每按一次 +1: 把当前个股那一行滚到视野正中并闪一下 */
  locateNonce?: number
  onSelect: (symbol: string, name: string) => void
  /** [R103] 点标的名称时打开整合版个股弹窗(最近查看+随意切换); 未传时退回仅选中 */
  onPreview?: (symbol: string, name: string) => void
  /** [R106] 行内 AI 分析(原页头「AI 个股分析」按钮, 整合进 AI 分析列, 每个标的都有) */
  onAnalyze?: (symbol: string, name: string) => void
  /** [R106] 行内点位提醒(原页头「点位提醒」按钮, 同上) */
  onPriceAlert?: (symbol: string, name: string) => void
}) {
  const qc = useQueryClient()
  const [heldOnly, setHeldOnly] = useState(false)
  // [R157] 定位当前个股: 行引用 + 闪烁高亮 + "行还没渲染出来"时的待定位
  const rowRefs = useRef<Record<string, HTMLTableRowElement | null>>({})
  const pendingLocate = useRef<{ symbol: string; explicit: boolean } | null>(null)
  const [flash, setFlash] = useState<string | null>(null)
  const flashTimer = useRef<number | undefined>(undefined)
  // [R182] 导出选列。六态汇总弹窗已并进导出 —— 勾上趋势那几列就是它。
  const [exportOpen, setExportOpen] = useState(false)
  const [exportCols, setExportCols] = useState<string[]>(
    () => storage.boardExportCols.get(DEFAULT_EXPORT_KEYS) ?? DEFAULT_EXPORT_KEYS)
  const setCols = (keys: string[]) => {
    setExportCols(keys)
    storage.boardExportCols.set(keys)
  }
  // [R48] 逐日复盘弹窗 —— 「趋势」「结论」两列点进来的就是它。
  // [R51] tab 记住是从哪一列进来的: 两列点开看的不是同一张表(见 StockReviewDialog)
  const [review, setReview] = useState<{ symbol: string; name: string; tab: ReviewTab } | null>(null)
  // 排序:默认按置信度降序(信号最强的排前面;未分析的始终垫底)
  // [R178] 默认按「该动了」排, 不再按 AI 置信度。
  //
  // 置信度是"AI 有多确定", 不是"这只有多急" —— 一只 AI 95% 确信「观望」的票
  // 会压在一只刚跌破止损线的票上面。而且拿 AI 决定用户先看谁, 跟本项目别处
  // 立的规矩是矛盾的(台账「只记不反馈」、R175「AI 只念表」)。
  // 升序 = 最急的在最上面(order 越小越急)。
  // 默认顺序 = 「该动了」判定从急到缓。「走势」表头循环一圈之后回到它。
  const DEFAULT_SORT = { key: 'urgency' as SortKey, dir: 'asc' as const }
  const [sort, setSort] = useState<{ key: SortKey; dir: 'asc' | 'desc' }>(DEFAULT_SORT)
  // [R203] 27 种组合速查 —— 存整行, 因为弹窗要拿这只票的 geo/runs 做读数带与高亮
  const [combo, setCombo] = useState<{ name: string; geo?: KeltnerBands['geo']; runs?: KeltnerBands['runs'] } | null>(null)
  // 「只看要动的」—— 自选一多, 默认列 80 行本身就是噪音
  const [actionableOnly, setActionableOnly] = useState(false)
  const toggleSort = (key: SortKey) =>
    setSort((s) => (s.key === key ? { key, dir: s.dir === 'asc' ? 'desc' : 'asc' } : { key, dir: key === 'name' ? 'asc' : 'desc' }))
  // [R211] 「走势」表头点击 = 依次轮换五个排序目标, **走完一圈回到默认顺序**。
  // 用户: 「点击应该是一直循环所有形态, 其中包括遍历完成后会轮到取消所有形态
  // 变成原来的样子」。所以这里不走 toggleSort 的"再点一下翻方向"—— 五个目标
  // 各自带一个天然合理的方向(见下), 循环里第六站是"取消"。
  const TREND_SORTS: { key: SortKey; dir: 'asc' | 'desc' }[] = [
    { key: 'trend', dir: 'desc' },    // 六态: 多头在前
    { key: 'spread', dir: 'asc' },    // 间距: 刚从挤在一起走出来的在前(找起点)
    { key: 'ks', dir: 'asc' },        // 三档: 最便宜的在前(低吸候选)
    { key: 'km', dir: 'asc' },
    { key: 'kl', dir: 'asc' },
  ]
  const cycleTrendSort = () => {
    const i = TREND_SORTS.findIndex(x => x.key === sort.key)
    // 不在这一圈里 → 从头开始; 走到最后一个 → 取消, 回默认顺序
    setSort(i < 0 ? TREND_SORTS[0]
      : i === TREND_SORTS.length - 1 ? DEFAULT_SORT
        : TREND_SORTS[i + 1])
  }
  const caret = (key: SortKey) =>
    sort.key === key ? (sort.dir === 'asc' ? <ArrowUp className="h-2.5 w-2.5" /> : <ArrowDown className="h-2.5 w-2.5" />) : null
  const thBtn = 'inline-flex items-center gap-0.5 hover:text-foreground cursor-pointer'

  const enriched = useQuery({
    queryKey: QK.watchlistEnriched(),
    queryFn: () => api.watchlistEnriched(),
    staleTime: 30_000,
  })
  const positionsQ = useQuery({
    queryKey: QK.watchlistPositions,
    queryFn: () => api.watchlistPositions(),
    staleTime: 30_000,
  })
  // 下面这几个 `?? {}` 都要包 useMemo: 否则每次渲染都是新对象,
  // 会让 rows 的 useMemo 依赖每帧都变, 记忆化等于没做。
  const positions = useMemo(() => positionsQ.data?.positions ?? {}, [positionsQ.data])

  const signalsQ = useQuery({
    queryKey: QK.stockSignals,
    queryFn: () => api.stockSignals(),
    staleTime: 30_000,
    // [R27] 每小时自动拉一次: 定时任务批量刷完信号后, 页面开着也能自动看到新结果
    refetchInterval: 60 * 60 * 1000,
  })
  const signals = useMemo(() => signalsQ.data?.signals ?? {}, [signalsQ.data])

  // [fork 增强] 六态趋势列 —— 批量一次拉取,零 AI 成本,基于日线收盘价
  const trendSyms = useMemo(
    () => ((enriched.data?.rows ?? []) as any[]).map((r) => String(r.symbol)).sort().join(','),
    [enriched.data],
  )
  const trendsQ = useQuery({
    queryKey: QK.stockTrends(trendSyms),
    queryFn: () => api.stockTrends(trendSyms.split(',')),
    enabled: trendSyms.length > 0,
    staleTime: 5 * 60_000,
  })
  const trends: Record<string, TrendInfo> = useMemo(() => trendsQ.data?.trends ?? {}, [trendsQ.data])

  // [R42] Keltner 三档位置 —— 与趋势列同一批标的, 收盘口径。
  // 通道要 ATR 与均线, 实时叠加层只有价格 —— 拿实时价比昨天的通道会得到半新半旧的判定
  const keltnerQ = useQuery({
    queryKey: QK.stockKeltner(trendSyms),
    queryFn: () => api.stockKeltner(trendSyms.split(',')),
    enabled: trendSyms.length > 0,
    staleTime: 5 * 60_000,
  })
  const keltner: Record<string, KeltnerBands> = useMemo(
    () => keltnerQ.data?.keltner ?? {}, [keltnerQ.data])

  // [R178] 「该动了」判定 —— 决策台的默认顺序由它定, 不再由 AI 置信度定。
  // 判定全在后端(纯规则、有测试), 这边只负责按 order/distance 排。
  const urgencyQ = useQuery({
    queryKey: QK.stockUrgency(trendSyms),
    queryFn: () => api.stockUrgency(trendSyms.split(',')),
    enabled: trendSyms.length > 0,
    staleTime: 60_000,     // 比通道短: 距离随实时价动, 陈旧的紧迫度会误导
  })
  const urgency: Record<string, Urgency> = useMemo(
    () => urgencyQ.data?.urgency ?? {}, [urgencyQ.data])
  // [R195] 通道事件与「该动了」同一个端点返回 —— 那里已经同时拿着六态与三档,
  // 事件必须三样齐全(位置 × 方向 × 确认)才判得出, 所以合在那儿算
  const events: Record<string, ChannelEvent> = useMemo(
    () => urgencyQ.data?.event ?? {}, [urgencyQ.data])
  // [R200] 阶段判定同一趟返回。事件是"今天发生了什么", 阶段是"整体走到哪一段、
  // 该盯什么" —— 后者才是能照着做的那句, 之前只有复盘弹窗看得到。
  const phases: Record<string, ChannelPhase> = useMemo(
    () => urgencyQ.data?.phase ?? {}, [urgencyQ.data])
  // [R205] 「怎么办」与「该动了」同一趟返回 —— 它就是在那份判定之上再合成一层
  const plays: Record<string, Playbook> = useMemo(
    () => urgencyQ.data?.playbook ?? {}, [urgencyQ.data])

  // [fork 增强] 持仓出场线(仅持有+填成本的票有;后端顺带把线同步为监控规则)
  const heldWithCost = Object.values(positions).some((p) => p.held && p.cost)
  const exitLinesQ = useQuery({
    queryKey: QK.watchlistExitLines,
    queryFn: () => api.watchlistExitLines(),
    enabled: heldWithCost,
    staleTime: 5 * 60_000,
  })
  const exitLines: Record<string, ExitLine> = useMemo(() => exitLinesQ.data?.lines ?? {}, [exitLinesQ.data])

  // 历史报告整合: 每只自选显示最近一份 AI 分析报告(时间+份数), 点击直接打开报告弹窗。
  // 数据来自 stockAnalysisStore(个股分析页挂载时已 loadHistory, 此处再调一次是安全去重)。
  const { reports } = useHistoryReports()
  useEffect(() => { loadHistory() }, [])
  const reportsBySymbol = useMemo(() => {
    const m = new Map<string, { latest: (typeof reports)[number]; count: number }>()
    for (const r of reports) {  // reports 已按 created_at 降序 → 首见即最新
      const cur = m.get(r.symbol)
      if (cur) cur.count += 1
      else m.set(r.symbol, { latest: r, count: 1 })
    }
    return m
  }, [reports])

  // 手动刷新:重新拉取行情/仓位/信号(不调用 AI、不计费)。盘中本就 SSE 自动刷新,
  // 这个按钮主要给收盘后/关闭实时时,想一键看最新盘后快照用。
  const refreshing = enriched.isFetching || positionsQ.isFetching || signalsQ.isFetching
  const refreshAll = () => {
    qc.invalidateQueries({ queryKey: QK.watchlistEnriched() })
    qc.invalidateQueries({ queryKey: QK.watchlistPositions })
    qc.invalidateQueries({ queryKey: QK.stockSignals })
  }

  const setPos = useMutation({
    mutationFn: ({ symbol, held, cost, weight }: { symbol: string; held: boolean; cost: number | null; weight?: number | null }) =>
      api.setWatchlistPosition(symbol, held, cost, weight),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: QK.watchlistPositions })
      qc.invalidateQueries({ queryKey: QK.watchlistExitLines })
    },
  })

  // 「分析全部/持有」—— 逐只并发(限 3)调用信号接口, 每完成一只即刷新, 显示进度。
  const [progress, setProgress] = useState<{ done: number; total: number } | null>(null)
  const runBatch = async (syms: string[]) => {
    if (progress) return
    if (!syms.length) {
      // 静默 return 会让按钮看起来"点了没反应" —— 空列表必须说明原因
      toast('没有可分析的标的:行情数据未就绪或自选为空(只看持有时需先标记持有)', 'error')
      return
    }
    setProgress({ done: 0, total: syms.length })
    let done = 0
    let failed = 0
    let firstErr = ''
    let idx = 0
    const worker = async () => {
      while (idx < syms.length) {
        const s = syms[idx++]
        try {
          // 注意: 后端信号接口失败时返回 200 + {error} 而非抛 HTTP 错误,
          // 必须检查响应体 —— 否则 AI 挂掉时(如 503)整批"成功"但信号纹丝不动
          const res = await api.generateStockSignal(s)
          if (res?.error) {
            failed++
            if (!firstErr) firstErr = res.error
          }
        } catch (e: any) {
          // 单只失败不阻断, 但必须计数并保留首个错误 —— 全军覆没时(如 AI Key
          // 失效/未配置)若静默吞掉, 用户看到的就是"点了没反应"
          failed++
          if (!firstErr) firstErr = e?.message ?? String(e)
        }
        done++
        setProgress({ done, total: syms.length })
        qc.invalidateQueries({ queryKey: QK.stockSignals })
      }
    }
    await Promise.all(Array.from({ length: Math.min(3, syms.length) }, () => worker()))
    setProgress(null)
    qc.invalidateQueries({ queryKey: QK.stockSignals })
    if (failed) {
      toast(
        `AI 分析完成:成功 ${syms.length - failed} 只,失败 ${failed} 只${firstErr ? ` — ${firstErr}` : ''}`,
        failed === syms.length ? 'error' : 'success',
      )
    }
  }
  const allSyms = () => (enriched.data?.rows ?? []).map((r: any) => String(r.symbol))
  const heldSyms = () => allSyms().filter((sym: string) => positions[sym]?.held)

  // [R131] 批量分析改**增量**: 只跑"需要重算"的。判据见 lib/signalFreshness ——
  // 主要看信号有没有见过最新那根 K 线, 数据没更新就没必要再花一次调用。
  // 单只想强制重跑, 点行内那个 ✨(它不走这套过滤)。
  const staleAll = useMemo(
    () => pickStale(allSyms(), signals, enriched.data?.as_of),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [enriched.data, signals],
  )
  const staleHeld = useMemo(
    () => pickStale(heldSyms(), signals, enriched.data?.as_of),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [enriched.data, signals, positions],
  )

  /** 跑增量批量, 并在结果里如实说明跳过了多少 */
  const runIncremental = (stale: string[], total: number, what: string) => {
    if (!total) {
      toast(`没有可分析的标的:行情数据未就绪或自选为空${what === '持有' ? '(只看持有时需先标记持有)' : ''}`, 'error')
      return
    }
    if (!stale.length) {
      toast(`${what}的 ${total} 只都已是最新分析(基于当前数据基准日), 无需重算`, 'success')
      return
    }
    const skipped = total - stale.length
    if (skipped > 0) toast(`跳过 ${skipped} 只已是最新的, 开始分析 ${stale.length} 只`, 'success')
    runBatch(stale)
  }
  const runAll = () => runIncremental(staleAll, allSyms().length, '全部')
  const runHeld = () => runIncremental(staleHeld, heldSyms().length, '持有')

  const rows = useMemo(() => {
    const src = enriched.data?.rows ?? []
    return src
      .map((r: any) => {
        const symbol = String(r.symbol)
        const pos: Position | undefined = positions[symbol]
        const sig: Signal | undefined = signals[symbol]
        const close = typeof r.close === 'number' ? r.close : null
        const cost = pos?.cost ?? null
        const pnl = pos?.held && cost && cost > 0 && close != null ? (close - cost) / cost : null
        const trend: TrendInfo | undefined = trends[symbol]
        const exit: ExitLine | undefined = exitLines[symbol]
        const kc: KeltnerBands | undefined = keltner[symbol]
        return {
          symbol, name: r.name ?? symbol, close, changePct: r.change_pct ?? null,
          held: !!pos?.held, cost, weight: pos?.weight ?? null, pnl, sig, trend, exit, kc,
          urg: urgency[symbol],
          ev: events[symbol],
          ph: phases[symbol],
          play: plays[symbol],
          // [R169] 成本来源与批次信息 —— 让"这个成本是我填的还是批次算的"一眼可辨
          costSource: pos?.cost_source ?? null,
          lotCost: pos?.lot_cost ?? null,
          costDriftPct: pos?.cost_drift_pct ?? null,
          lotCount: pos?.lot_count ?? 0,
        }
      })
      .filter((r) => (heldOnly ? r.held : true))
      // [R178] 「要动的」= 前四档(已触发/逼近/刚变盘/到轨), 无事档不算。
      // 判定还没回来时不过滤 —— 宁可多显示, 不能让表在加载中看起来是空的。
      .filter((r) => (actionableOnly ? (r.urg ? r.urg.level !== 'idle' : true) : true))
  }, [enriched.data, positions, signals, heldOnly, actionableOnly, trends, exitLines, keltner, urgency, events])

  const sortedRows = useMemo(() => {
    const val = (r: (typeof rows)[number]): string | number | null => {
      switch (sort.key) {
        // [R178] 档位为主、同档内离触发多近为辅。合成一个可比的数:
        // order*1000 + 距离(百分点), 距离缺失的排在同档最后。
        // 这样同为「逼近」时, 离线 0.3% 的会排在 1.4% 前面。
        case 'urgency': {
          if (!r.urg) return null
          const d = r.urg.distance == null ? 999 : Math.min(r.urg.distance * 100, 998)
          return r.urg.order * 1000 + d
        }
        // [R205] 「怎么办」按急迫程度排 —— order 越小越该先看
        case 'play': return r.play ? r.play.order : 9
        case 'name': return r.name
        case 'close': return r.close
        case 'changePct': return r.changePct
        case 'held': return r.held ? 1 : 0
        case 'cost': return r.cost
        case 'pnl': return r.pnl
        // 止盈线按"离触发还有多远"排, 不按线价 —— 线价本身没有可比性
        // (不同票价格量级差几十倍), 距离才是要盯的那个数
        case 'exit': return r.exit ? r.exit.distance_pct : null
        case 'trend': return r.trend ? -(TREND_RANK[r.trend.state] ?? 9) : null
        // 三档通道按通道内位置排(0=贴下轨, 1=贴上轨, 轨外会越界)。
        // 升序 = 最便宜的在前(低吸候选), 降序 = 最贵的在前(高抛候选)
        case 'ks': return r.kc?.s?.pct ?? null
        case 'km': return r.kc?.m?.pct ?? null
        case 'kl': return r.kc?.l?.pct ?? null
        // 结论按后端给的 rank 排(越大越偏卖): 降序把该减的顶到最上面,
        // 升序把该吸的顶上来。权重由后端定, 界面不自己编一套。
        // [R201] 三线间距。升序 = 刚从挤在一起走出来的排前面(找起点),
        // 降序 = 走得最远的排前面(找该收的)。带符号, 空头排列自然沉底。
        case 'spread': return r.kc?.geo?.spread ?? null
        case 'verdict': return r.kc?.verdict?.rank ?? null
        case 'confidence': return r.sig?.confidence ?? null
        case 'signal': return r.sig ? (SIGNAL_RANK[r.sig.signal] ?? 9) : null
        case 'report': {
          const rep = reportsBySymbol.get(r.symbol)
          return rep ? new Date(rep.latest.created_at).getTime() : null
        }
      }
    }
    const arr = [...rows]
    arr.sort((a, b) => {
      const av = val(a), bv = val(b)
      if (av == null && bv == null) return 0
      if (av == null) return 1  // 空值(未分析/无数据)始终垫底
      if (bv == null) return -1
      const c = typeof av === 'string' ? av.localeCompare(String(bv)) : (av as number) - (bv as number)
      return sort.dir === 'asc' ? c : -c
    })
    return arr
  }, [rows, sort, reportsBySymbol])

  const heldCount = Object.values(positions).filter((p) => p.held).length
  // 「要动的」有几只 —— 显示在开关上, 用户不点也能一眼知道今天有没有事
  const actionCount = useMemo(
    () => Object.values(urgency).filter((u) => u.level !== 'idle').length, [urgency])

  // ===== [R157] 定位当前个股 =====
  // 用户: 「加个定位当前个股的功能, 任何适合被选中的都要能当前页面显示, 我不想每次
  // 都找半天」。150 行的表, 搜索框选中一只票之后它在哪一行只能靠肉眼扫。
  //
  // 两条路径, 一个函数:
  //   · 自动 —— currentSymbol 一变(搜索/URL ?symbol=/上次记忆/行内点击)就把那一行
  //     滚进视野。用 `nearest`: 已经看得见的不动(行内点击时不该把表格跳一下)。
  //   · 手动 —— 页头「定位」按钮: 滚到正中 + 闪一下, 让眼睛一下落到它身上。
  // 行还没渲染出来(数据没到 / 刚切换筛选)时记成待定位, rows 一出来就补做。
  const scrollToRow = (sym: string, explicit: boolean) => {
    const el = rowRefs.current[sym]
    if (!el) return false
    el.scrollIntoView({ block: explicit ? 'center' : 'nearest', behavior: 'smooth' })
    setFlash(sym)
    if (flashTimer.current) window.clearTimeout(flashTimer.current)
    flashTimer.current = window.setTimeout(() => setFlash(null), explicit ? 1800 : 1000)
    return true
  }
  const locate = (sym: string, explicit: boolean) => {
    if (!sym) return
    if (scrollToRow(sym, explicit)) return
    // 行不在当前可见列表里 —— 分清是哪种"不在", 别静默
    const loaded = !!enriched.data
    const inWatchlist = (enriched.data?.rows ?? []).some((r: any) => String(r.symbol) === sym)
    if (!loaded) {                       // 数据还没到: 等 rows 出来再滚
      pendingLocate.current = { symbol: sym, explicit }
      return
    }
    if (!inWatchlist) {
      if (explicit) toast(`${sym} 不在自选里, 决策台没有它这一行`, 'error')
      return
    }
    if (heldOnly) {                      // 被「只看持有」挡住了: 切回全部再定位
      pendingLocate.current = { symbol: sym, explicit: true }
      setHeldOnly(false)
      toast('这只票不是持有 —— 已切回「全部」并定位', 'success')
    }
  }
  // 行渲染出来之后补做待定位(数据首次到达 / 切换筛选 / 排序变化)
  useEffect(() => {
    const p = pendingLocate.current
    if (p && rowRefs.current[p.symbol]) {
      pendingLocate.current = null
      scrollToRow(p.symbol, p.explicit)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sortedRows])
  // 自动: 选中谁就让谁在视野里
  useEffect(() => {
    if (currentSymbol) locate(currentSymbol, false)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentSymbol])
  // 手动: 页头「定位」
  useEffect(() => {
    if (locateNonce && currentSymbol) locate(currentSymbol, true)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [locateNonce])
  useEffect(() => () => { if (flashTimer.current) window.clearTimeout(flashTimer.current) }, [])

  // [R46] 导出用的行: 只留「结论」列有内容的。三档都在通道中部的票没有位置
  // 信息, 导出来只是占地方。按当前排序导出 —— 你在界面上怎么排, 导出件就怎么排。
  // [R182] 导出**当前列表所见**, 不再另加筛选条件。
  //
  // 以前写死"只导有结论的", R178 又补了"或要动的" —— 那是因为列写死在模板里,
  // 只能靠行筛选控制篇幅。现在列可选了, 导多少由「只看要动的」「只看持有」这两个
  // 已有的开关决定就够了: **屏幕上看到什么就导出什么**, 不再有第三套隐藏规则。
  const exportRows = sortedRows
  const exportHtml = () => {
    if (!exportRows.length) {
      toast('当前没有要动的、也没有「结论」列有内容的标的 —— 无可导出', 'error')
      return
    }
    const blob = new Blob([buildBoardHtml(exportRows, rows.length, exportCols)], { type: 'text/html;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `自选决策台_${new Date().toISOString().slice(0, 10).replace(/-/g, '')}.html`
    a.click()
    URL.revokeObjectURL(url)
    toast(`已导出 ${exportRows.length} 只(自选共 ${rows.length} 只)`, 'success')
  }

  return (
    <div className="rounded-xl border border-border/60 bg-surface/40 overflow-hidden">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1.5 px-4 py-2.5">
        {/* 决策台就是整页主体, 没有要让位的东西 —— 不再提供折叠 */}
        <span className="flex shrink-0 items-center gap-2">
          <Wallet className="h-3.5 w-3.5 text-sky-400" />
          <span className="text-xs font-medium text-foreground">自选决策台</span>
          <span className="text-[10px] text-muted">{rows.length} 只 · 持有 {heldCount}</span>
          {/* [R198] 角上的感叹号 —— 点开只讲这些词怎么读, 不讲怎么算出来的 */}
          <GlossaryButton />
        </span>
        <button
          onClick={() => setActionableOnly((v) => !v)}
          title={'只留下有触发的那几只: 出场线已破/逼近、离趋势翻转价 2% 以内、今日刚翻转、'
            + '短期通道到轨。判定是纯规则的(与推送焦点名单同一套到轨口径), AI 不参与。\n'
            + '自选一多, 默认列出全部本身就是噪音 —— 绝大多数票今天确实不需要你看。'}
          className={`text-[10px] px-2 py-0.5 rounded-btn border transition-colors cursor-pointer ${
            actionableOnly ? 'border-amber-400/40 bg-amber-400/10 text-amber-400' : 'border-border bg-base text-muted hover:text-foreground'
          }`}
        >
          只看要动的{actionCount > 0 && <span className="opacity-70">·{actionCount}</span>}
        </button>
        <button
          onClick={() => setHeldOnly((v) => !v)}
          className={`text-[10px] px-2 py-0.5 rounded-btn border transition-colors cursor-pointer ${
            heldOnly ? 'border-accent/40 bg-accent/10 text-accent' : 'border-border bg-base text-muted hover:text-foreground'
          }`}
        >
          只看持有
        </button>
        <span className="mx-0.5 h-3 w-px shrink-0 bg-border/60" aria-hidden />
        <button
          onClick={refreshAll}
          disabled={refreshing}
          title="刷新行情/仓位/信号快照(不调用 AI、不计费)"
          className="ml-auto inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-btn border border-border bg-base text-muted hover:text-foreground disabled:opacity-60 transition-colors cursor-pointer"
        >
          <RefreshCw className={`h-3 w-3 ${refreshing ? 'animate-spin' : ''}`} />
          刷新
        </button>
        <button
          onClick={() => setExportOpen(true)}
          disabled={!exportRows.length}
          title={exportRows.length
            ? `导出当前列表所见的 ${exportRows.length} 只为自包含 HTML(可存档/打印/转发)。\n`
              + `点开可以选导哪些列 —— 原「六态汇总」就是其中一个预设。\n`
              + `导出的读法与屏幕一致(通道列写「贴上轨」而不是 0.87)。`
            : '当前列表是空的'}
          className="inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-btn border border-sky-400/30 bg-sky-400/10 text-sky-300 hover:bg-sky-400/20 disabled:opacity-50 transition-colors cursor-pointer"
        >
          <Download className="h-3 w-3" />
          导出
          {exportRows.length > 0 && <span className="opacity-70">{exportRows.length}·{exportCols.length}列</span>}
        </button>
        <span className="mx-0.5 h-3 w-px shrink-0 bg-border/60" aria-hidden />
        {heldCount > 0 && (
          <button
            onClick={runHeld}
            disabled={!!progress}
            title={`只对标记为「持有」的自选生成 AI 买卖信号(省调用, 持仓优先)。`
              + `\n[R131] 只跑需要重算的 ${staleHeld.length} 只 —— 信号已看过最新一根 K 线的会跳过`
              + `\n(数据没更新时重跑, 喂给 AI 的还是同一份输入; 超过 ${SIGNAL_TTL_HOURS} 小时仍会重算)`
              + `\n想强制重跑某一只, 点它那行的 ✨`}
            className="inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-btn border border-amber-400/30 bg-amber-400/10 text-amber-300 hover:bg-amber-400/20 disabled:opacity-60 transition-colors cursor-pointer"
          >
            {progress ? <Loader2 className="h-3 w-3 animate-spin" /> : <Sparkles className="h-3 w-3" />}
            AI 分析持有{staleHeld.length > 0 && <span className="text-amber-300/70">·{staleHeld.length}</span>}
          </button>
        )}
        <button
          onClick={runAll}
          disabled={!!progress}
          title={`对自选逐只生成 AI 买卖信号(会调用 AI, 按只计费)。`
            + `\n[R131] 只跑需要重算的 ${staleAll.length} 只 —— 信号已看过最新一根 K 线的会跳过`
            + `\n(数据没更新时重跑, 喂给 AI 的还是同一份输入, 花钱买不到新信息; 超过 ${SIGNAL_TTL_HOURS} 小时仍会重算)`
            + `\n想强制重跑某一只, 点它那行的 ✨`}
          className="inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-btn border border-sky-400/30 bg-sky-400/10 text-sky-300 hover:bg-sky-400/20 disabled:opacity-60 transition-colors cursor-pointer"
        >
          {progress ? <Loader2 className="h-3 w-3 animate-spin" /> : <Sparkles className="h-3 w-3" />}
          {progress
            ? `分析中 ${progress.done}/${progress.total}`
            : <>AI 分析全部{staleAll.length > 0 && <span className="text-sky-300/70">·{staleAll.length}</span>}</>}
        </button>
      </div>

      {/* [R48] 逐日复盘: 趋势 / 三档结论 / 涨停按同一条时间轴排开 */}
      {combo && (
        <ComboTableDialog name={combo.name} geo={combo.geo} runs={combo.runs}
                          onClose={() => setCombo(null)} />
      )}
      {review && (
        <StockReviewDialog symbol={review.symbol} name={review.name} tab={review.tab} onClose={() => setReview(null)} />
      )}

      {/* [R28] 关键价位改弹窗后, 页面里已没有 K 线图要让位 —— 表格直接吃满剩余视口高度 */}
      <div className="overflow-auto border-t border-border/60 max-h-[calc(100vh-210px)]">
          <table className="w-full text-xs">
            {/* [R194] 列宽表驱动(宽度与分配原则见 BOARD_COLS)。R178 加「该动」列时**只加了 <th> 没加 <col>**,
                15 对 16, 从那天起每个宽度都串了一位(R193 才发现); R184/R189 改列数
                时又要手动同步 colSpan。改成从 BOARD_COLS 渲染之后, colgroup 与
                colSpan 同源, 只剩「th 数量要跟上」这一处需要人盯。 */}
            <colgroup>
              {BOARD_COLS.map(c => (
                <col key={c.label} style={c.w ? { width: c.w } : undefined} />
              ))}
            </colgroup>
            <thead className="sticky top-0 bg-surface/95 backdrop-blur text-[10px] text-muted">
              <tr className="text-left">
                <th className="whitespace-nowrap px-3 py-2.5 font-normal text-center"><button onClick={() => toggleSort('name')} className={thBtn} title="标的名称;第二行是「该动了」判定 —— 已触发 > 逼近 > 刚变盘 > 到轨 > 无事,纯规则,AI 不参与">标的{caret('name')}</button></th>
                <th className="whitespace-nowrap px-2 py-2.5 font-normal text-center">
                  <button onClick={() => toggleSort(sort.key === 'close' ? 'changePct' : 'close')}
                          className={`${thBtn} whitespace-nowrap`}
                          title="现价与当日涨跌。点这里在「现价」「涨跌」之间轮换排序目标, 再点同一个翻方向">
                    现价/涨跌
                    {(['close', 'changePct'] as const).includes(sort.key as 'close')
                      && <span className="ml-0.5 text-[9px] text-accent">
                        {sort.key === 'close' ? '价' : '涨跌'}
                      </span>}
                    {caret(sort.key)}
                  </button>
                </th>
                <th className="whitespace-nowrap px-2 py-2.5 font-normal text-center"><button onClick={() => toggleSort('held')} className={thBtn}>仓位{caret('held')}</button></th>
                <th className="whitespace-nowrap px-2 py-2.5 font-normal text-center"><button onClick={() => toggleSort('cost')} className={thBtn} title="持仓成本价(仅持有且填了成本的票有)">成本{caret('cost')}</button></th>
                <th className="whitespace-nowrap px-2 py-2.5 font-normal text-center"><button onClick={() => toggleSort('pnl')} className={thBtn}>浮盈{caret('pnl')}</button></th>
                {/* [R42] Keltner 三档: 一眼看出这只票贴着哪条轨。收盘口径, 与个股分析图表同一组公式 */}
                {/* [R198] 三档合一。排序键仍是三个 —— 点表头在 短→中→长 之间轮换,
                    再点同一个翻方向。合并的是显示不是能力。 */}
                <th className="whitespace-nowrap px-1.5 py-2.5 font-normal text-center">
                  {/* [R211] 排序标记压成同一行的一个小字。原来那个彩色徽标会换行,
                      表头看着就断成两截 —— 用户: 「量化通道我不喜欢这样搞, 不美观」。
                      现在只在名字后面缀一个 6px 的目标名 + 箭头, 永不换行。 */}
                  <button
                    onClick={cycleTrendSort}
                    className={`${thBtn} whitespace-nowrap`}
                    title={'三行: 六态趋势 / 通道给的阶段·走到哪一步 / 还有没有劲。\n\n'
                      + '点这里依次轮换五个排序目标, **再点一下取消排序、回到默认顺序**:\n'
                      + '  六态 —— 多头在前\n'
                      + '  间距 —— 升序是刚走出来的(找起点), 降序是走得最远的(找该收的)\n'
                      + '  短期 / 中期 / 长期 —— 各自在通道里的高低, 升序最便宜在前'}>
                    走势
                    {(['trend', 'spread', 'ks', 'km', 'kl'] as const).includes(sort.key as 'trend')
                      && <span className="ml-0.5 text-[9px] text-accent">
                        {{ trend: '六态', spread: '间距', ks: '短', km: '中', kl: '长' }[sort.key as 'trend']}
                      </span>}
                    {caret(sort.key)}
                  </button>
                </th>
                <th className="whitespace-nowrap px-2 py-2.5 font-normal text-center">
                  <button onClick={() => toggleSort(sort.key === 'verdict' ? 'play' : 'verdict')}
                          className={`${thBtn} whitespace-nowrap`}
                          title={'两行: 上面「贵不贵」是这个价现在算贵还是算便宜(位置),\n'
                            + '下面「怎么办」是把五套判定合成的一句话(动作)。\n\n'
                            + '点这里在「贵不贵」「怎么办」之间轮换排序目标, 再点同一个翻方向。\n'
                            + '「怎么办」按急迫程度排: 按纪律走 > 今天就得动 > 先别动 > 盯着 > 留意 > 没事。'}>
                    结论
                    {(['verdict', 'play'] as const).includes(sort.key as 'verdict')
                      && <span className="ml-0.5 text-[9px] text-accent">
                        {sort.key === 'verdict' ? '贵不贵' : '怎么办'}
                      </span>}
                    {caret(sort.key)}
                  </button>
                </th>
                <th className="whitespace-nowrap px-2 py-2.5 font-normal text-center"><button onClick={() => toggleSort('report')} className={thBtn} title="最近一份 AI 分析报告(点击胶囊打开) · ✨生成/更新分析 · 🔔点位提醒">AI 分析{caret('report')}</button></th>
                <th className="whitespace-nowrap px-4 py-2.5 font-normal text-left"><button onClick={() => toggleSort('signal')} className={thBtn}>AI 信号{caret('signal')}</button></th>
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 ? (
                <tr><td colSpan={BOARD_COLS.length} className="px-4 py-6 text-center text-muted">自选为空 —— 去自选页添加标的</td></tr>
              ) : sortedRows.map((r) => {
                const active = r.symbol === currentSymbol
                // [R169] 只有手填的成本才回写。r.cost 可能是批次派生值, 回写它等于
                // 把派生固化成手填, 之后改批次就不跟着动了。
                const up = (r.changePct ?? 0) > 0
                const down = (r.changePct ?? 0) < 0
                const manualCost = r.costSource === 'manual' ? r.cost : null
                const flashing = r.symbol === flash
                return (
                  // [R157] ref 供定位滚动; scroll-mt 避开 sticky 表头; 定位到时整行闪一下
                  <tr
                    key={r.symbol}
                    ref={(el) => { rowRefs.current[r.symbol] = el }}
                    className={`scroll-mt-10 border-t border-border/30 transition-colors duration-500 hover:bg-elevated/40 ${
                      flashing ? 'bg-accent/25' : active ? 'bg-accent/[0.10]' : ''}`}
                  >
                    {/* 点标的即切换分析(免搜索) */}
                    {/* [R157b] 当前个股整行常驻高亮 + 左侧一道靛蓝边: 搜索后先弹出关键价位
                        弹窗, 闪烁那 1.8 秒多半被弹窗盖住, 关掉弹窗还得一眼认得出它在哪 */}
                    {/* [R209] 「该动了」那两行从这里撤掉了。用户: 「已经有怎么办的列了,
                        标的里面的那些就不多余了」—— **说得对, 那是同一句话印了两遍**:
                        「怎么办」列本来就是把「该动了」合成进去的一层(它是五套判定里的
                        一套), 于是同一只票的「生命线跌破 399.85 已跌破 3.6%」左右各印
                        一份。R198 当初把它挪进标的格是为了省一列, 现在收敛层顶上了,
                        它就成了纯重复。
                        判定本身一个字没动 —— 排序键、「只看要动的」筛选照旧走它。 */}
                    <td className={`${TD_BASE} px-3 text-center border-l-2 ${active ? 'border-l-accent' : 'border-l-transparent'}`}>
                      <button onClick={() => (onPreview ?? onSelect)(r.symbol, r.name)}
                              className="mx-auto flex min-h-[2.25rem] flex-col items-center justify-center gap-0.5 text-center cursor-pointer group">
                        <span className="flex items-center gap-1.5">
                          {active && <Star className="h-2.5 w-2.5 shrink-0 text-accent" />}
                          <span className="max-w-[110px] truncate font-medium text-foreground transition-colors group-hover:text-sky-300">{r.name}</span>
                          <span className={`${NUM} text-[9px] text-muted`}>{r.symbol}</span>
                        </span>
                      </button>
                    </td>
                    {/* [R212] 现价与涨跌并成一格 —— 两个数天生一起读 */}
                    <td className={`${TD_BASE} ${NUM} whitespace-nowrap px-2`}>
                      <span className="text-foreground">{r.close != null ? r.close.toFixed(2) : '—'}</span>
                      <span className={`ml-1.5 text-[10px] ${up ? 'text-red-400' : down ? 'text-emerald-400' : 'text-muted'}`}>
                        {r.changePct != null ? `${r.changePct > 0 ? '+' : ''}${(r.changePct * 100).toFixed(2)}%` : '—'}
                      </span>
                    </td>
                    {/* 仓位:持有/空仓 切换。
                        [R169] 写回时一律用 manualCost 而不是 r.cost —— r.cost 可能是批次
                        派生出来的, 直接回写会把"批次算的"固化成"我填的", 之后改批次就不
                        跟着动了。派生值必须保持派生。 */}
                    <td className={`${TD_BASE} whitespace-nowrap px-2 text-center`}>
                      <button
                        onClick={() => setPos.mutate({ symbol: r.symbol, held: !r.held, cost: manualCost, weight: r.weight })}
                        className={`whitespace-nowrap text-[10px] px-1.5 py-0.5 rounded border transition-colors cursor-pointer ${
                          r.held ? 'border-amber-400/40 bg-amber-400/10 text-amber-400' : 'border-border bg-base text-muted hover:border-amber-400/30'
                        }`}
                      >
                        {r.held ? '持有' : '空仓'}
                      </button>
                      {/* [R212] 仓% 从「成本」格挪到这里。用户: 「成本这一列去掉仓位比例」。
                          **不是删掉这个能力** —— 今日总览的组合总仓位、净值回撤纪律、
                          超配提醒全靠它, 没别的地方能填。挪到「仓位」格才是它本来的位置:
                          持有与否 + 占多少仓, 本来就是同一件事的两半。 */}
                      {r.held && (
                        <input
                          type="number" min={0} max={100}
                          defaultValue={r.weight ?? ''}
                          placeholder="仓%"
                          title="仓位比例(占总资金 %),可选 —— 填了之后今日总览能算组合总仓位、净值回撤纪律与超配提醒。批次页给不出这个数(它不知道总资金),只能在这里填。"
                          onBlur={(e) => {
                            const v = e.target.value === '' ? null : Number(e.target.value)
                            if (v !== r.weight) setPos.mutate({ symbol: r.symbol, held: true, cost: manualCost, weight: v })
                          }}
                          className={`mt-1 w-12 h-5 px-1 rounded bg-base border border-border text-[10px] ${NUM} text-right text-foreground focus:outline-none focus:border-accent/50`}
                        />
                      )}
                    </td>
                    {/* 成本+仓位%:仅持有时可填。生命线=20日线, 自动计算无需手填;
                        仓位% 供今日总览算组合总仓位/净值回撤, 不填不影响其他功能。

                        [R169] 成本框只装**手填值**: 批次页登记过而这里没填的, 走
                        placeholder 显示批次加权均价(带「批」字), 一眼能分清"我填的"
                        和"批次算的"。想改成自己的口径就直接往里敲, 敲了即变手填。 */}
                    <td className={`${TD_BASE} whitespace-nowrap px-2`}>
                      {r.held ? (
                        <span className="inline-flex items-center gap-1">
                          <input
                            type="number"
                            defaultValue={manualCost ?? ''}
                            placeholder={r.costSource === 'lots' && r.lotCost != null ? `批 ${r.lotCost.toFixed(2)}` : '成本'}
                            title={r.costSource === 'lots' && r.lotCost != null
                              ? `成本来自「持仓提醒」页的 ${r.lotCount} 笔批次(数量加权均价 ${r.lotCost.toFixed(2)})。这里留空即跟随批次; 填了数字则以填的为准。`
                              : '买入成本(手填)'}
                            onBlur={(e) => {
                              const v = e.target.value === '' ? null : Number(e.target.value)
                              if (v !== manualCost) setPos.mutate({ symbol: r.symbol, held: true, cost: v, weight: r.weight })
                            }}
                            className={`w-16 h-6 px-1 rounded bg-base border text-[11px] ${NUM} text-right text-foreground focus:outline-none focus:border-accent/50 ${
                              r.costSource === 'lots' ? 'border-accent/35 placeholder:text-accent/70' : 'border-border'
                            }`}
                          />
                          <LotsLink symbol={r.symbol} lotCount={r.lotCount} driftPct={r.costDriftPct} lotCost={r.lotCost} />
                        </span>
                      ) : (
                        // 空仓但批次还挂着 —— 多半是卖出后忘了删批次, 那两条监控规则还在跑
                        r.lotCount > 0
                          ? <LotsLink symbol={r.symbol} lotCount={r.lotCount} driftPct={null} lotCost={null} stale />
                          : <span className="text-muted">—</span>
                      )}
                    </td>
                    {/* 浮盈 */}
                    <td className={`${TD_BASE} ${NUM} whitespace-nowrap px-2 ${r.pnl == null ? 'text-muted' : r.pnl > 0 ? 'text-red-400' : r.pnl < 0 ? 'text-emerald-400' : 'text-muted'}`}>
                      {r.pnl != null ? `${(r.pnl * 100).toFixed(1)}%` : '—'}
                    </td>
                    {/* [R42] Keltner 三档位置 */}
                    <ChannelStateCell
                      trend={r.trend} trendCls={r.trend ? trendBadgeCls(r.trend.state) : undefined}
                      geo={r.kc?.geo} runs={r.kc?.runs} ph={r.ph} kc={r.kc} close={r.close}
                      onOpenReview={() => setReview({ symbol: r.symbol, name: r.name, tab: 'trend' })}
                      onOpenCombo={() => setCombo({ name: r.name, geo: r.kc?.geo, runs: r.kc?.runs })} />
                    {/* [R212] 结论 = 贵不贵(位置, 上) + 怎么办(动作, 下), 竖排一格 */}
                    <ConclusionCell v={r.kc?.verdict} ev={r.ev} geo={r.kc?.geo} runs={r.kc?.runs}
                                    energy={r.kc?.energy} ph={r.ph} p={r.play}
                                    onOpen={() => setReview({ symbol: r.symbol, name: r.name, tab: 'verdict' })} />
                    {/* [R106] AI 分析列: 报告胶囊(点开最近报告) + ✨生成/更新分析 + 🔔点位提醒
                        —— 原页头两个按钮整合到这里, 每个标的都有自己的一对动作 */}
                    <td className={`${TD_BASE} whitespace-nowrap px-2 text-center`}>
                      {/* [R130] 上下结构: 报告胶囊一行、两个动作一行。
                          原来三件横排挤在 7% 宽的列里, 胶囊里的「17天前」被压得
                          几乎贴着图标。竖过来之后胶囊能吃满列宽, 图标也不再被挤,
                          顺带把两个图标按钮的点击区从 p-1 放大到 6×6。 */}
                      <div className="inline-flex flex-col items-center gap-1">
                        {(() => {
                          const rep = reportsBySymbol.get(r.symbol)
                          if (!rep) return null
                          return (
                            <button
                              onClick={() => openHistoryReport(rep.latest.id)}
                              title={`打开最近报告(${new Date(rep.latest.created_at).toLocaleString()})${rep.count > 1 ? ` · 共 ${rep.count} 份` : ''}`}
                              className="inline-flex w-full items-center justify-center gap-1 rounded-btn border border-violet-400/30 bg-violet-400/10 px-1.5 py-0.5 text-[10px] text-violet-300 transition-colors duration-hover hover:bg-violet-400/20 cursor-pointer"
                            >
                              <FileText className="h-2.5 w-2.5 shrink-0" />
                              {fmtAgo(rep.latest.created_at)}
                              {rep.count > 1 && <span className="text-violet-300/60">·{rep.count}</span>}
                            </button>
                          )
                        })()}
                        <div className="flex items-center gap-1.5">
                          {onAnalyze && (
                            <button
                              onClick={() => onAnalyze(r.symbol, r.name)}
                              title={`对 ${r.name} 生成/更新 AI 四维分析`}
                              aria-label={`对 ${r.name} 生成 AI 分析`}
                              className="grid h-6 w-6 place-items-center rounded-btn text-sky-300/60 transition-colors duration-hover hover:bg-sky-400/10 hover:text-sky-300"
                            >
                              <Sparkles className="h-3 w-3" />
                            </button>
                          )}
                          {onPriceAlert && (
                            <button
                              onClick={() => onPriceAlert(r.symbol, r.name)}
                              title={`为 ${r.name} 设置价格点位提醒`}
                              aria-label={`为 ${r.name} 设置点位提醒`}
                              className="grid h-6 w-6 place-items-center rounded-btn text-sky-300/60 transition-colors duration-hover hover:bg-sky-400/10 hover:text-sky-300"
                            >
                              <Bell className="h-3 w-3" />
                            </button>
                          )}
                        </div>
                      </div>
                    </td>
                    {/* AI 信号:徽标 + 时间 + 理由整段换行(不截断)。
                        [R211] **这一列靠左**。用户: 「ai 信号这一列里面的文字都是
                        靠左对齐才好看」—— 说得对: 别的列是短标签, 居中让它们各自
                        落在自己那一格的正中; 这一列是整段会换行的文字, 居中之后
                        每一行的起点都不一样, 读起来像被撕开的。 */}
                    <td className={`${TD_BASE} px-4 !text-left`}>
                      {r.sig ? (
                        <div className="flex flex-col gap-0.5">
                          <div className="flex items-center gap-1.5">
                            <span className={`text-[10px] px-1.5 py-0.5 rounded border ${SIGNAL_META[r.sig.signal]?.cls ?? 'border-border text-muted'}`}>
                              {SIGNAL_META[r.sig.signal]?.label ?? r.sig.signal}
                            </span>
                            <span className="text-[9px] text-muted/50">{fmtAgo(r.sig.created_at)}</span>
                          </div>
                          {r.sig.reason && (
                            <span className="text-[10px] text-muted/80 leading-snug whitespace-normal break-words">{r.sig.reason}</span>
                          )}
                          {/* [fork 增强] 到价预案:AI watch_points(涨至/跌至 → 对应操作),提前有准备 */}
                          {(r.sig.watch_points ?? []).length > 0 && (
                            <div className="flex flex-wrap gap-x-2.5 gap-y-0.5 mt-0.5">
                              {(r.sig.watch_points ?? []).map((p, i) => (
                                <span
                                  key={i}
                                  className="inline-flex items-center gap-1 text-[10px] font-mono whitespace-nowrap"
                                  title={p.reason ? `${p.label ?? ''} — ${p.reason}` : p.label}
                                >
                                  <span className={p.direction === 'up' ? 'text-red-400' : 'text-emerald-400'}>
                                    {p.direction === 'up' ? '↑涨至' : '↓跌至'} {p.price.toFixed(2)}
                                  </span>
                                  {p.action && <span className="text-foreground/80">{p.action}</span>}
                                </span>
                              ))}
                            </div>
                          )}
                        </div>
                      ) : (
                        <span className="text-[10px] text-muted/50">未分析</span>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
      </div>

      {exportOpen && (
        <ExportColumnsDialog
          keys={exportCols}
          onChange={setCols}
          rowCount={exportRows.length}
          onClose={() => setExportOpen(false)}
          onExport={() => { exportHtml(); setExportOpen(false) }}
        />
      )}
    </div>
  )
}
