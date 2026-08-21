import { useState, useMemo, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Star, Wallet, Sparkles, Loader2, ArrowUp, ArrowDown, RefreshCw, FileText, TrendingUp, Download } from 'lucide-react'
import { api, type ExitLine, type KeltnerBand, type KeltnerBands, type KeltnerVerdict, type TrendInfo } from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import { toast } from '@/components/Toast'
import { useHistoryReports, openHistoryReport, loadHistory } from '@/lib/stockAnalysisStore'
import { trendBadgeCls } from '@/components/stock-analysis/TrendStateBar'
import { TrendSummaryDialog } from '@/components/stock-analysis/TrendSummaryDialog'

type Position = { held: boolean; cost: number | null; weight?: number | null; updated_at: string }
type WatchPoint = { direction: 'up' | 'down'; price: number; label?: string; action?: string; reason?: string }
type Signal = { signal: string; confidence: number; reason: string; close: number | null; created_at: string; watch_points?: WatchPoint[] }
type SortKey = 'name' | 'close' | 'changePct' | 'held' | 'cost' | 'pnl' | 'exit'
  | 'trend' | 'ks' | 'km' | 'kl' | 'verdict' | 'confidence' | 'signal' | 'report'
const SIGNAL_RANK: Record<string, number> = { buy: 0, sell: 1, hold: 2, watch: 3 }
// [fork 增强] 六态排序权重:多头在前(上涨趋势 → 下跌趋势)
const TREND_RANK: Record<string, number> = { UT: 0, NR: 1, SR: 2, SREA: 3, NREA: 4, DT: 5 }

// AI 信号 → 展示标签/配色。买入=红(A股涨红), 卖出=绿, 持有=琥珀, 观望=灰。
const SIGNAL_META: Record<string, { label: string; cls: string }> = {
  buy: { label: '买入', cls: 'border-red-400/40 bg-red-400/10 text-red-400' },
  sell: { label: '卖出', cls: 'border-emerald-400/40 bg-emerald-400/10 text-emerald-400' },
  hold: { label: '持有', cls: 'border-amber-400/40 bg-amber-400/10 text-amber-400' },
  watch: { label: '观望', cls: 'border-border bg-base text-muted' },
}

// [R42] Keltner 位置配色。破上轨/贴上轨用暖色(偏贵), 破下轨/贴下轨用冷色(偏便宜),
// 通道内保持中性 —— 位置是事实, 不替用户下买卖判断。
const KELTNER_CLS: Record<KeltnerBand['pos'], string> = {
  above: 'border-red-400/40 bg-red-400/10 text-red-400',
  near_upper: 'border-amber-400/40 bg-amber-400/10 text-amber-400',
  inside: 'border-border bg-base text-muted',
  near_lower: 'border-sky-400/40 bg-sky-400/10 text-sky-300',
  below: 'border-emerald-400/40 bg-emerald-400/10 text-emerald-400',
}

/**
 * 一档 Keltner 通道的单元格。
 *
 * 显示"贴上轨"这种五档文字, 悬停给出真实的上下轨价、通道内位置百分比,
 * 以及"还差几个 ATR 到轨" —— 只给一个标签等于让用户盲信一个没法复核的判断。
 * 该档算不出来(新股不够 120 根 / 均线列缺失)时显示 "—", 不编一个数出来。
 */
function KeltnerCell({ band, close }: { band?: KeltnerBand; close: number | null }) {
  if (!band) {
    return <td className="whitespace-nowrap px-1.5 py-2.5 text-center"><span className="text-[10px] text-muted/40">—</span></td>
  }
  const pct = Math.round(band.pct * 100)
  return (
    <td className="whitespace-nowrap px-1.5 py-2.5 text-center">
      <span
        className={`inline-flex whitespace-nowrap rounded border px-1 py-0.5 text-[10px] ${KELTNER_CLS[band.pos]}`}
        title={
          `${band.band_cn}通道 ${band.lower.toFixed(2)} ~ ${band.upper.toFixed(2)}` +
          `${close != null ? `,收盘 ${close.toFixed(2)}` : ''}\n` +
          `通道内位置 ${pct}%(0% 贴下轨 / 100% 贴上轨)\n` +
          `距上轨 ${band.to_upper_atr ?? '—'} 个 ATR · 距下轨 ${band.to_lower_atr ?? '—'} 个 ATR\n` +
          `${band.hint}\n收盘口径 —— 通道要用 ATR 与均线, 实时价比昨天的通道会半新半旧`
        }
      >
        {band.pos_cn}
      </span>
    </td>
  )
}

// [R44] 三档组合的结论配色。tone 由后端给, 界面不自己判 ——
// 决策台、今日总览、悬停提示必须说同一句话。
const VERDICT_CLS: Record<KeltnerVerdict['tone'], string> = {
  sell: 'border-red-400/40 bg-red-400/10 text-red-400',
  buy: 'border-sky-400/40 bg-sky-400/10 text-sky-300',
  hold: 'border-amber-400/40 bg-amber-400/10 text-amber-400',
  avoid: 'border-border bg-base text-muted',
  // [R45] 观察档: 还不到动手的时候, 用最淡的一档, 跟四个动作档区分开
  watch: 'border-border bg-elevated/60 text-secondary',
}

/**
 * 「通道结论」单元格 —— 三档组合翻成一句人话。
 *
 * 徽标只放 4-6 字的结论标题, 悬停给完整的一句话 + 为什么 + 哪几档共振。
 * 短期档在通道中部时显示 "—": 那时这一列确实没有信息, 硬凑一句反而误导。
 */
function VerdictCell({ v }: { v?: KeltnerVerdict | null }) {
  if (!v) {
    return (
      <td className="whitespace-nowrap px-1.5 py-2.5 text-center">
        <span className="text-[10px] text-muted/40" title="短期通道在中部 —— 位置上没有可说的, 听趋势和信号的">—</span>
      </td>
    )
  }
  return (
    <td className="whitespace-nowrap px-1.5 py-2.5 text-center">
      <span
        className={`inline-flex whitespace-nowrap rounded border px-1 py-0.5 text-[10px] ${VERDICT_CLS[v.tone]}`}
        title={`${v.action}\n\n${v.detail}\n\n依据:${v.bands_text}\n\n注意:这是「位置」结论, 说的是贵不贵, 不是会不会继续涨。清仓与否看止盈线/生命线, 优先级在通道之上。`}
      >
        {v.title}
      </span>
    </td>
  )
}

// ===== [R46] 自包含 HTML 导出 =====
// 只导出「结论」列有内容的行 —— 三档都在通道中部的票没有位置信息,
// 导出来只是占地方。导出件里第一行就写清导出了几只、总共几只, 免得
// 看到 148 只自选导出 4 行时以为漏了。
//
// 与今日总览的导出同一套排版: 浅色、内联样式、无脚本无外链, 存档/打印/
// 转发都不依赖这个应用。

type ExportRow = {
  symbol: string; name: string; close: number | null; changePct: number | null
  held: boolean; pnl: number | null
  trend?: TrendInfo; kc?: KeltnerBands
}

const esc = (v: unknown) =>
  String(v ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c] as string))

// 导出件是浅色排版, 深色下的配色搬过去看不清 —— 这里单独给一套。
const EXPORT_TONE: Record<KeltnerVerdict['tone'], string> = {
  sell: 'background:#fdecec;color:#c0392b',
  buy: 'background:#e6f4fb;color:#1c6ea4',
  hold: 'background:#fdf0e3;color:#c78326',
  avoid: 'background:#f0f1f3;color:#8a919f',
  watch: 'background:#f0f1f3;color:#5b6472',
}

function buildBoardHtml(rows: ExportRow[], total: number): string {
  const bull = '#d03050'
  const bear = '#18a058'
  const pos = (b?: KeltnerBand) => (b ? esc(b.pos_cn) : '—')
  const body = rows.map(r => {
    const v = r.kc?.verdict
    return `
      <tr>
        <td class="name"><b>${esc(r.name)}</b> <span class="sym">${esc(r.symbol)}</span></td>
        <td class="num">${r.close?.toFixed(2) ?? '—'}</td>
        <td class="num" style="color:${(r.changePct ?? 0) > 0 ? bull : (r.changePct ?? 0) < 0 ? bear : '#8a919f'}">${
          r.changePct != null ? (r.changePct * 100).toFixed(2) + '%' : '—'}</td>
        <td>${r.held ? '持有' : '—'}</td>
        <td class="num" style="color:${r.pnl == null ? '#8a919f' : r.pnl > 0 ? bull : bear}">${
          r.pnl != null ? (r.pnl * 100).toFixed(1) + '%' : '—'}</td>
        <td style="color:${r.trend?.side === '多头' ? bull : bear}">${
          r.trend ? `${esc(r.trend.state_cn)} ${r.trend.duration}天` : '—'}</td>
        <td>${pos(r.kc?.s)}</td><td>${pos(r.kc?.m)}</td><td>${pos(r.kc?.l)}</td>
        <td>${v ? `<span class="tag" style="${EXPORT_TONE[v.tone]}">${esc(v.title)}</span>` : '—'}</td>
        <td class="act">${v ? esc(v.action) : ''}<span class="why">${v ? esc(v.detail) : ''}</span></td>
      </tr>`
  }).join('')

  return `<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>自选决策台 · 通道结论</title>
<style>
  body{margin:0;padding:32px 24px;background:#f7f8fa;color:#1f2329;font:14px/1.6 -apple-system,'PingFang SC','Microsoft YaHei',sans-serif}
  .wrap{max-width:1100px;margin:0 auto}
  h1{font-size:20px;margin:0 0 4px}
  .meta{color:#8a919f;font-size:12px;margin-bottom:16px}
  .note{background:#fff;border:1px solid #e5e6eb;border-radius:8px;padding:10px 14px;font-size:12px;color:#4e5666;margin-bottom:16px;line-height:1.7}
  table{width:100%;border-collapse:collapse;background:#fff;border:1px solid #e5e6eb;border-radius:8px;overflow:hidden}
  th{font-size:12px;font-weight:500;color:#8a919f;text-align:left;padding:8px 10px;border-bottom:1px solid #e5e6eb;background:#fafbfc;white-space:nowrap}
  td{padding:8px 10px;border-bottom:1px solid #f0f1f3;font-size:13px;white-space:nowrap;vertical-align:top}
  td.name{white-space:normal}
  td.act{white-space:normal;min-width:16rem}
  tr:last-child td{border-bottom:none}
  .num{font-variant-numeric:tabular-nums;text-align:right}
  th.num,td.num{text-align:right}
  .sym{color:#a0a6b1;font-size:11px}
  .tag{border-radius:3px;padding:1px 6px;font-size:11px;white-space:nowrap;display:inline-block}
  .why{display:block;color:#8a919f;font-size:11px;margin-top:3px;line-height:1.6}
  .foot{margin-top:16px;color:#a0a6b1;font-size:11px;line-height:1.8}
  @media print{body{background:#fff;padding:0}}
</style>
</head>
<body>
<div class="wrap">
  <h1>自选决策台 · 通道结论</h1>
  <div class="meta">导出 ${rows.length} 只(自选共 ${total} 只)· 生成于 ${esc(new Date().toLocaleString('zh-CN'))}</div>
  <div class="note">
    只列出「结论」列有内容的标的 —— 三档通道都在中部的票没有位置信息, 不占篇幅。<br>
    通道口径:短期 MA20±2ATR / 中期 MA60±2.5ATR / 长期 MA120±3ATR,<b>收盘价</b>判定。<br>
    结论说的是<b>位置</b>(贵不贵), 不是会不会继续涨。清仓与否看止盈线与生命线, 优先级在通道之上。
  </div>
  <table>
    <thead><tr>
      <th>标的</th><th class="num">现价</th><th class="num">涨跌</th><th>仓位</th>
      <th class="num">浮盈</th><th>趋势</th>
      <th>短通道</th><th>中通道</th><th>长通道</th><th>结论</th><th>怎么办</th>
    </tr></thead>
    <tbody>${body}</tbody>
  </table>
  <div class="foot">
    本页为自包含 HTML(无脚本、无外链), 可直接存档、打印或转发。<br>
    数据来自 TickFlow, 仅供研究参考, 不构成投资建议。
  </div>
</div>
</body>
</html>`
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
export function WatchlistDecisionBoard({ currentSymbol, onSelect }: {
  currentSymbol: string
  onSelect: (symbol: string, name: string) => void
}) {
  const qc = useQueryClient()
  const [heldOnly, setHeldOnly] = useState(false)
  // [fork 增强] 六态汇总弹窗
  const [showTrendSummary, setShowTrendSummary] = useState(false)
  // 排序:默认按置信度降序(信号最强的排前面;未分析的始终垫底)
  const [sort, setSort] = useState<{ key: SortKey; dir: 'asc' | 'desc' }>({ key: 'confidence', dir: 'desc' })
  const toggleSort = (key: SortKey) =>
    setSort((s) => (s.key === key ? { key, dir: s.dir === 'asc' ? 'desc' : 'asc' } : { key, dir: key === 'name' ? 'asc' : 'desc' }))
  const caret = (key: SortKey) =>
    sort.key === key ? (sort.dir === 'asc' ? <ArrowUp className="h-2.5 w-2.5" /> : <ArrowDown className="h-2.5 w-2.5" />) : null
  const thBtn = 'inline-flex items-center gap-0.5 hover:text-foreground cursor-pointer'

  const enriched = useQuery({
    queryKey: QK.watchlistEnriched(),
    queryFn: () => api.watchlistEnriched(),
    staleTime: 30_000,
  })
  const positionsQ = useQuery({
    queryKey: ['watchlist-positions'],
    queryFn: () => api.watchlistPositions(),
    staleTime: 30_000,
  })
  // 下面这几个 `?? {}` 都要包 useMemo: 否则每次渲染都是新对象,
  // 会让 rows 的 useMemo 依赖每帧都变, 记忆化等于没做。
  const positions = useMemo(() => positionsQ.data?.positions ?? {}, [positionsQ.data])

  const signalsQ = useQuery({
    queryKey: ['stock-signals'],
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

  // [fork 增强] 持仓出场线(仅持有+填成本的票有;后端顺带把线同步为监控规则)
  const heldWithCost = Object.values(positions).some((p) => p.held && p.cost)
  const exitLinesQ = useQuery({
    queryKey: ['watchlist-exit-lines'],
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
    qc.invalidateQueries({ queryKey: ['watchlist-positions'] })
    qc.invalidateQueries({ queryKey: ['stock-signals'] })
  }

  const setPos = useMutation({
    mutationFn: ({ symbol, held, cost, weight }: { symbol: string; held: boolean; cost: number | null; weight?: number | null }) =>
      api.setWatchlistPosition(symbol, held, cost, weight),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['watchlist-positions'] })
      qc.invalidateQueries({ queryKey: ['watchlist-exit-lines'] })
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
        qc.invalidateQueries({ queryKey: ['stock-signals'] })
      }
    }
    await Promise.all(Array.from({ length: Math.min(3, syms.length) }, () => worker()))
    setProgress(null)
    qc.invalidateQueries({ queryKey: ['stock-signals'] })
    if (failed) {
      toast(
        `AI 分析完成:成功 ${syms.length - failed} 只,失败 ${failed} 只${firstErr ? ` — ${firstErr}` : ''}`,
        failed === syms.length ? 'error' : 'success',
      )
    }
  }
  const allSyms = () => (enriched.data?.rows ?? []).map((r: any) => String(r.symbol))
  const runAll = () => runBatch(allSyms())
  // 只分析标记为「持有」的自选 —— 省 AI 调用, 持仓优先
  const runHeld = () => runBatch(allSyms().filter((sym: string) => positions[sym]?.held))

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
        return { symbol, name: r.name ?? symbol, close, changePct: r.change_pct ?? null, held: !!pos?.held, cost, weight: pos?.weight ?? null, pnl, sig, trend, exit, kc }
      })
      .filter((r) => (heldOnly ? r.held : true))
  }, [enriched.data, positions, signals, heldOnly, trends, exitLines, keltner])

  const sortedRows = useMemo(() => {
    const val = (r: (typeof rows)[number]): string | number | null => {
      switch (sort.key) {
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

  // [R46] 导出用的行: 只留「结论」列有内容的。三档都在通道中部的票没有位置
  // 信息, 导出来只是占地方。按当前排序导出 —— 你在界面上怎么排, 导出件就怎么排。
  const exportRows = useMemo(
    () => sortedRows.filter((r) => r.kc?.verdict),
    [sortedRows],
  )
  const exportHtml = () => {
    if (!exportRows.length) {
      toast('当前没有「结论」列有内容的标的 —— 三档通道都在中部时不导出', 'error')
      return
    }
    const blob = new Blob([buildBoardHtml(exportRows, rows.length)], { type: 'text/html;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `自选决策台_通道结论_${new Date().toISOString().slice(0, 10).replace(/-/g, '')}.html`
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
        </span>
        <button
          onClick={refreshAll}
          disabled={refreshing}
          title="刷新行情/仓位/信号快照(不调用 AI、不计费)"
          className="ml-auto inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full border border-border bg-base text-muted hover:text-foreground disabled:opacity-60 transition-colors cursor-pointer"
        >
          <RefreshCw className={`h-3 w-3 ${refreshing ? 'animate-spin' : ''}`} />
          刷新
        </button>
        <button
          onClick={exportHtml}
          disabled={!exportRows.length}
          title={exportRows.length
            ? `导出为自包含 HTML(可存档/分享)。只导出「结论」列有内容的 ${exportRows.length} 只 —— 三档都在通道中部的票没有位置信息, 不占篇幅`
            : '当前没有「结论」列有内容的标的'}
          className="inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full border border-sky-400/30 bg-sky-400/10 text-sky-300 hover:bg-sky-400/20 disabled:opacity-50 transition-colors cursor-pointer"
        >
          <Download className="h-3 w-3" />
          导出 HTML
          {exportRows.length > 0 && <span className="opacity-70">{exportRows.length}</span>}
        </button>
        <button
          onClick={() => setShowTrendSummary(true)}
          title="全部自选的六态趋势纵览(零 AI 成本),可导出 HTML"
          className="inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full border border-sky-400/30 bg-sky-400/10 text-sky-300 hover:bg-sky-400/20 transition-colors cursor-pointer"
        >
          <TrendingUp className="h-3 w-3" />
          六态汇总
        </button>
        <button
          onClick={() => setHeldOnly((v) => !v)}
          className={`text-[10px] px-2 py-0.5 rounded-full border transition-colors cursor-pointer ${
            heldOnly ? 'border-accent/40 bg-accent/10 text-accent' : 'border-border bg-base text-muted hover:text-foreground'
          }`}
        >
          只看持有
        </button>
        {heldCount > 0 && (
          <button
            onClick={runHeld}
            disabled={!!progress}
            title="只对标记为「持有」的自选生成 AI 买卖信号(省调用, 持仓优先)"
            className="inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full border border-amber-400/30 bg-amber-400/10 text-amber-300 hover:bg-amber-400/20 disabled:opacity-60 transition-colors cursor-pointer"
          >
            {progress ? <Loader2 className="h-3 w-3 animate-spin" /> : <Sparkles className="h-3 w-3" />}
            AI 分析持有
          </button>
        )}
        <button
          onClick={runAll}
          disabled={!!progress}
          title="对全部自选逐只生成 AI 买卖信号(会调用 AI,按只计费)"
          className="inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full border border-sky-400/30 bg-sky-400/10 text-sky-300 hover:bg-sky-400/20 disabled:opacity-60 transition-colors cursor-pointer"
        >
          {progress ? <Loader2 className="h-3 w-3 animate-spin" /> : <Sparkles className="h-3 w-3" />}
          {progress ? `分析中 ${progress.done}/${progress.total}` : 'AI 分析全部'}
        </button>
      </div>

      {/* [fork 增强] 六态汇总弹窗:全部自选(不受"只看持有"过滤)+ 批量趋势 */}
      {showTrendSummary && (
        <TrendSummaryDialog
          items={((enriched.data?.rows ?? []) as any[]).map((r: any) => ({
            symbol: String(r.symbol),
            name: String(r.name ?? r.symbol),
            close: typeof r.close === 'number' ? r.close : null,
          }))}
          trends={trends}
          onClose={() => setShowTrendSummary(false)}
        />
      )}

      {/* [R28] 关键价位改弹窗后, 页面里已没有 K 线图要让位 —— 表格直接吃满剩余视口高度 */}
      <div className="overflow-auto border-t border-border/60 max-h-[calc(100vh-210px)]">
          <table className="w-full text-xs">
            {/* 列宽按比例显式分配。不写的话浏览器会把富余空间全塞给 max-content 最大的
                那一列(AI 信号), 别的列挤在一起; 写死 px 又不随视口走。

                分配原则: 前半段(标的~止盈线)是查对用的, 给到"完整显示不换行"就够;
                后半段(趋势/三档通道/结论/AI 信号)才是要盯的, 富余空间往那边给。

                这些列全是 nowrap 且内容宽度固定(输入框、徽标、等宽数字), 所以百分比
                调小**不会压字** —— 内容宽度是硬底线, 百分比只决定"能不能多吃富余空间"。 */}
            <colgroup>
              <col style={{ width: '8%' }} />{/* 标的 */}
              <col style={{ width: '3.5%' }} />{/* 现价 */}
              <col style={{ width: '3.5%' }} />{/* 涨跌 */}
              <col style={{ width: '3%' }} />{/* 仓位 */}
              <col style={{ width: '6%' }} />{/* 成本(两个输入框) */}
              <col style={{ width: '3.5%' }} />{/* 浮盈 */}
              <col style={{ width: '5%' }} />{/* 止盈线(两行) */}
              <col style={{ width: '6%' }} />{/* 趋势 */}
              <col style={{ width: '4%' }} />{/* 短通道 */}
              <col style={{ width: '4%' }} />{/* 中通道 */}
              <col style={{ width: '4%' }} />{/* 长通道 */}
              <col style={{ width: '6%' }} />{/* 结论 */}
              <col style={{ width: '3%' }} />{/* 置信 */}
              <col style={{ width: '4.5%' }} />{/* 报告 */}
              <col />{/* AI 信号: 不给宽度, 吃掉剩下的 —— 只有它是整段文字 */}
            </colgroup>
            <thead className="sticky top-0 bg-surface/95 backdrop-blur text-[10px] text-muted">
              <tr className="text-left">
                <th className="whitespace-nowrap px-4 py-2.5 font-normal"><button onClick={() => toggleSort('name')} className={thBtn}>标的{caret('name')}</button></th>
                <th className="whitespace-nowrap px-2 py-2.5 font-normal text-right"><button onClick={() => toggleSort('close')} className={thBtn}>现价{caret('close')}</button></th>
                <th className="whitespace-nowrap px-2 py-2.5 font-normal text-right"><button onClick={() => toggleSort('changePct')} className={thBtn}>涨跌{caret('changePct')}</button></th>
                <th className="whitespace-nowrap px-2 py-2.5 font-normal text-center"><button onClick={() => toggleSort('held')} className={thBtn}>仓位{caret('held')}</button></th>
                <th className="whitespace-nowrap px-2 py-2.5 font-normal text-right"><button onClick={() => toggleSort('cost')} className={thBtn} title="持仓成本价(仅持有且填了成本的票有)">成本{caret('cost')}</button></th>
                <th className="whitespace-nowrap px-2 py-2.5 font-normal text-right"><button onClick={() => toggleSort('pnl')} className={thBtn}>浮盈{caret('pnl')}</button></th>
                <th className="whitespace-nowrap px-2 py-2.5 font-normal text-right"><button onClick={() => toggleSort('exit')} className={thBtn} title="ATR 三阶段出场线(止损/保本/移动止盈),仅持有+填成本的票有;跌破自动推送。按「离触发还有多远」排序 —— 线价本身不同票差几十倍没有可比性">止盈线{caret('exit')}</button></th>
                <th className="whitespace-nowrap px-2 py-2.5 font-normal text-center"><button onClick={() => toggleSort('trend')} className={thBtn} title="六态趋势(利弗莫尔,日线收盘价判定):多头在前">趋势{caret('trend')}</button></th>
                {/* [R42] Keltner 三档: 一眼看出这只票贴着哪条轨。收盘口径, 与个股分析图表同一组公式 */}
                <th className="whitespace-nowrap px-1.5 py-2.5 font-normal text-center"><button onClick={() => toggleSort('ks')} className={thBtn} title="短期通道 = MA20 ± 2×ATR(约一个月)。按通道内位置排序:升序=最贴下轨的在前(低吸候选), 降序=最贴上轨的在前(高抛候选)">短通道{caret('ks')}</button></th>
                <th className="whitespace-nowrap px-1.5 py-2.5 font-normal text-center"><button onClick={() => toggleSort('km')} className={thBtn} title="中期通道 = MA60 ± 2.5×ATR(一个季度)。按通道内位置排序">中通道{caret('km')}</button></th>
                <th className="whitespace-nowrap px-1.5 py-2.5 font-normal text-center"><button onClick={() => toggleSort('kl')} className={thBtn} title="长期通道 = MA120 ± 3×ATR(半年,牛熊边界)。按通道内位置排序">长通道{caret('kl')}</button></th>
                <th className="whitespace-nowrap px-1.5 py-2.5 font-normal text-center"><button onClick={() => toggleSort('verdict')} className={thBtn} title="三档组合的结论。排序把「该减的」和「该吸的」分到两头:降序=偏卖在前, 升序=偏买在前">结论{caret('verdict')}</button></th>
                <th className="whitespace-nowrap px-2 py-2.5 font-normal text-right"><button onClick={() => toggleSort('confidence')} className={thBtn}>置信{caret('confidence')}</button></th>
                <th className="whitespace-nowrap px-2 py-2.5 font-normal text-center"><button onClick={() => toggleSort('report')} className={thBtn} title="最近一份 AI 分析报告(点击单元格直接打开)">报告{caret('report')}</button></th>
                <th className="whitespace-nowrap px-4 py-2.5 font-normal text-left"><button onClick={() => toggleSort('signal')} className={thBtn}>AI 信号{caret('signal')}</button></th>
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 ? (
                <tr><td colSpan={15} className="px-4 py-6 text-center text-muted">自选为空 —— 去自选页添加标的</td></tr>
              ) : sortedRows.map((r) => {
                const active = r.symbol === currentSymbol
                const up = (r.changePct ?? 0) > 0
                const down = (r.changePct ?? 0) < 0
                return (
                  <tr key={r.symbol} className={`border-t border-border/30 hover:bg-elevated/40 ${active ? 'bg-accent/[0.06]' : ''}`}>
                    {/* 点标的即切换分析(免搜索) */}
                    <td className="whitespace-nowrap px-4 py-2.5">
                      {/* min-h 给整行一个下限: AI 信号列 1 行和 3 行的行高原来差一倍,
                          一屏扫下来参差得厉害。定住下限后只剩"多出来的那几行"的差异 */}
                      <button onClick={() => onSelect(r.symbol, r.name)} className="flex min-h-[2.25rem] items-center gap-1.5 text-left cursor-pointer group">
                        {active && <Star className="h-2.5 w-2.5 text-accent shrink-0" />}
                        <span className="font-medium text-foreground group-hover:text-sky-300 transition-colors truncate max-w-[110px]">{r.name}</span>
                        <span className="text-[9px] font-mono text-muted">{r.symbol}</span>
                      </button>
                    </td>
                    <td className="whitespace-nowrap px-2 py-2.5 text-right font-mono tabular-nums text-foreground">{r.close != null ? r.close.toFixed(2) : '—'}</td>
                    <td className={`whitespace-nowrap px-2 py-2.5 text-right font-mono tabular-nums ${up ? 'text-red-400' : down ? 'text-emerald-400' : 'text-muted'}`}>
                      {r.changePct != null ? `${(r.changePct * 100).toFixed(2)}%` : '—'}
                    </td>
                    {/* 仓位:持有/空仓 切换 */}
                    <td className="whitespace-nowrap px-2 py-2.5 text-center">
                      <button
                        onClick={() => setPos.mutate({ symbol: r.symbol, held: !r.held, cost: r.cost, weight: r.weight })}
                        className={`whitespace-nowrap text-[10px] px-1.5 py-0.5 rounded border transition-colors cursor-pointer ${
                          r.held ? 'border-amber-400/40 bg-amber-400/10 text-amber-400' : 'border-border bg-base text-muted hover:border-amber-400/30'
                        }`}
                      >
                        {r.held ? '持有' : '空仓'}
                      </button>
                    </td>
                    {/* 成本+仓位%:仅持有时可填。生命线=20日线, 自动计算无需手填;
                        仓位% 供今日总览算组合总仓位/净值回撤, 不填不影响其他功能 */}
                    <td className="whitespace-nowrap px-2 py-2.5 text-right">
                      {r.held ? (
                        <span className="inline-flex items-center gap-1">
                          <input
                            type="number"
                            defaultValue={r.cost ?? ''}
                            placeholder="成本"
                            onBlur={(e) => {
                              const v = e.target.value === '' ? null : Number(e.target.value)
                              if (v !== r.cost) setPos.mutate({ symbol: r.symbol, held: true, cost: v, weight: r.weight })
                            }}
                            className="w-16 h-6 px-1 rounded bg-base border border-border text-[11px] font-mono text-right text-foreground focus:outline-none focus:border-accent/50"
                          />
                          <input
                            type="number"
                            min={0} max={100}
                            defaultValue={r.weight ?? ''}
                            placeholder="仓%"
                            title="仓位比例(占总资金 %),可选 —— 填了之后今日总览能算组合总仓位、净值回撤纪律与超配提醒"
                            onBlur={(e) => {
                              const v = e.target.value === '' ? null : Number(e.target.value)
                              if (v !== r.weight) setPos.mutate({ symbol: r.symbol, held: true, cost: r.cost, weight: v })
                            }}
                            className="w-12 h-6 px-1 rounded bg-base border border-border text-[11px] font-mono text-right text-foreground focus:outline-none focus:border-accent/50"
                          />
                        </span>
                      ) : <span className="text-muted">—</span>}
                    </td>
                    {/* 浮盈 */}
                    <td className={`whitespace-nowrap px-2 py-2.5 text-right font-mono tabular-nums ${r.pnl == null ? 'text-muted' : r.pnl > 0 ? 'text-red-400' : r.pnl < 0 ? 'text-emerald-400' : 'text-muted'}`}>
                      {r.pnl != null ? `${(r.pnl * 100).toFixed(1)}%` : '—'}
                    </td>
                    {/* [fork 增强] 持仓出场线:当前生效线位 + 距离; 逼近变琥珀, 跌破变红 */}
                    <td className="whitespace-nowrap px-2 py-2.5 text-right">
                      {r.exit ? (
                        <span
                          className={`inline-flex flex-col items-end text-[10px] font-mono leading-tight ${
                            r.exit.triggered ? 'text-red-400' : r.exit.distance_pct > -0.03 ? 'text-amber-300' : 'text-muted'
                          }`}
                          title={`${r.exit.stage_cn} · ${r.exit.line_cn}\n成本 ${r.exit.cost ?? '—'} · 浮盈 ${r.exit.profit_atr ?? '—'}×ATR · 持仓最高 ${r.exit.highest_close ?? '—'}\n跌破 ${r.exit.line.toFixed(2)} → ${r.exit.action}(k=${r.exit.k}, ATR14=${r.exit.atr})${r.exit.lifeline ? `\n生命线(20日线) ${r.exit.lifeline.toFixed(2)} — 收盘跌破无条件清仓` : ''}`}
                        >
                          <span>{r.exit.line.toFixed(2)}</span>
                          <span className="whitespace-nowrap text-[9px] opacity-80">
                            {r.exit.stage === 'fatal' ? '生命线破位!' : r.exit.triggered ? '已触发' : `距 ${(r.exit.distance_pct * 100).toFixed(1)}%`}
                          </span>
                        </span>
                      ) : (
                        <span className="text-[10px] text-muted/40">—</span>
                      )}
                    </td>
                    {/* [fork 增强] 六态趋势(利弗莫尔):状态全名 + 持续天数, 悬停看关键点/操作建议 */}
                    <td className="whitespace-nowrap px-2 py-2.5 text-center">
                      {r.trend ? (
                        <span
                          className={`inline-flex whitespace-nowrap rounded border px-1.5 py-0.5 text-[10px] ${trendBadgeCls(r.trend.state)}`}
                          title={`${r.trend.state_cn}(${r.trend.state_en})· 第 ${r.trend.duration} 天,自 ${r.trend.since}\n${
                            // [R29] 先给翻转触发价(真正要盯的位), 关键点/高低水位作参考
                            [r.trend.flip_down != null ? `跌破 ${r.trend.flip_down.toFixed(2)} 转弱` : '',
                             r.trend.flip_up != null ? `站上 ${r.trend.flip_up.toFixed(2)} 转强` : '']
                              .filter(Boolean).join(' / ') || '暂无翻转触发价'
                          }\n参考:本轮最高收盘 ${r.trend.leg_high?.toFixed(2) ?? '—'} · 上关键点 ${r.trend.up_pivot?.toFixed(2) ?? '—'} / 下关键点 ${r.trend.dn_pivot?.toFixed(2) ?? '—'}\n${r.trend.action}${r.trend.signal ? `\n近期信号:${r.trend.signal} — ${r.trend.signal_desc}` : ''}\n出场优先级:组合回撤风控 > 生命线(20日线) > 止盈线(ATR) > 六态转弱${r.trend.intraday ? '\n⚠ 盘中临时口径:实时价只参与状态判定, 收盘确认为准;上面的价位一律按已收盘日线算' : ''}`}
                        >
                          {r.trend.state_cn} {r.trend.duration}天{r.trend.intraday ? <span className="ml-0.5 opacity-70">*</span> : null}
                        </span>
                      ) : (
                        <span className="text-[10px] text-muted/40">—</span>
                      )}
                    </td>
                    {/* [R42] Keltner 三档位置 */}
                    <KeltnerCell band={r.kc?.s} close={r.close} />
                    <KeltnerCell band={r.kc?.m} close={r.close} />
                    <KeltnerCell band={r.kc?.l} close={r.close} />
                    <VerdictCell v={r.kc?.verdict} />
                    {/* 置信度(独立列, 可排序) */}
                    <td className="whitespace-nowrap px-2 py-2.5 text-right font-mono tabular-nums text-muted">
                      {r.sig ? `${r.sig.confidence}%` : '—'}
                    </td>
                    {/* 历史报告: 最近一份的时间(+份数), 点击直接打开报告弹窗 */}
                    <td className="whitespace-nowrap px-2 py-2.5 text-center">
                      {(() => {
                        const rep = reportsBySymbol.get(r.symbol)
                        if (!rep) return <span className="text-[10px] text-muted/40">—</span>
                        return (
                          <button
                            onClick={() => openHistoryReport(rep.latest.id)}
                            title={`打开最近报告(${new Date(rep.latest.created_at).toLocaleString()})${rep.count > 1 ? ` · 共 ${rep.count} 份` : ''}`}
                            className="inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded border border-violet-400/30 bg-violet-400/10 text-violet-300 hover:bg-violet-400/20 transition-colors cursor-pointer"
                          >
                            <FileText className="h-2.5 w-2.5" />
                            {fmtAgo(rep.latest.created_at)}
                            {rep.count > 1 && <span className="text-violet-300/60">·{rep.count}</span>}
                          </button>
                        )
                      })()}
                    </td>
                    {/* AI 信号:徽标 + 时间 + 理由整段换行(不截断) */}
                    <td className="px-4 py-2.5 align-middle">
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
    </div>
  )
}
