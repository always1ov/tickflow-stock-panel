/**
 * [fork 增强] 六态市场状态汇总 —— 一键纵览全部自选的利弗莫尔六态,
 * 并可导出为干净的自包含 HTML 页面(内联样式,无外部依赖,可存档/分享)。
 *
 * 数据零成本:直接复用决策台已拉取的批量趋势结果,不触发 AI。
 */
import { useMemo, useState } from 'react'
import { ArrowDown, ArrowUp, Download, TrendingUp, X } from 'lucide-react'
import { type LivermoreState, type TrendInfo } from '@/lib/api'
import { trendBadgeCls } from '@/components/stock-analysis/TrendStateBar'

export interface TrendSummaryItem {
  symbol: string
  name: string
  close: number | null
}

// 状态元数据(顺序即多头→空头;文案沿用引入代码包的原版表达)
const STATES: { key: LivermoreState; cn: string; side: 'bull' | 'bear' }[] = [
  { key: 'UT', cn: '上涨趋势', side: 'bull' },
  { key: 'NR', cn: '自然回升', side: 'bull' },
  { key: 'SR', cn: '次级回升', side: 'bull' },
  { key: 'SREA', cn: '次级回撤', side: 'bear' },
  { key: 'NREA', cn: '自然回撤', side: 'bear' },
  { key: 'DT', cn: '下跌趋势', side: 'bear' },
]
const STATE_ORDER: Record<string, number> = Object.fromEntries(STATES.map((s, i) => [s.key, i]))

export function TrendSummaryDialog({ items, trends, onClose }: {
  items: TrendSummaryItem[]
  trends: Record<string, TrendInfo>
  onClose: () => void
}) {
  const [tab, setTab] = useState<'all' | LivermoreState>('all')
  const [durDir, setDurDir] = useState<'desc' | 'asc'>('desc')

  const enriched = useMemo(() => {
    const withTrend = items
      .filter((i) => trends[i.symbol])
      .map((i) => ({ ...i, trend: trends[i.symbol] }))
    const missing = items.filter((i) => !trends[i.symbol])
    return { withTrend, missing }
  }, [items, trends])

  const counts = useMemo(() => {
    const c: Record<string, number> = {}
    for (const s of STATES) c[s.key] = 0
    let bull = 0
    let bear = 0
    for (const r of enriched.withTrend) {
      c[r.trend.state] = (c[r.trend.state] ?? 0) + 1
      if (r.trend.side === '多头') bull++
      else bear++
    }
    return { byState: c, bull, bear }
  }, [enriched.withTrend])

  const asOf = useMemo(() => {
    let d = ''
    for (const r of enriched.withTrend) if (r.trend.as_of > d) d = r.trend.as_of
    return d
  }, [enriched.withTrend])

  const rows = useMemo(() => {
    const filtered = tab === 'all'
      ? enriched.withTrend
      : enriched.withTrend.filter((r) => r.trend.state === tab)
    return [...filtered].sort((a, b) => {
      const so = (STATE_ORDER[a.trend.state] ?? 9) - (STATE_ORDER[b.trend.state] ?? 9)
      if (tab === 'all' && so !== 0) return so
      const d = a.trend.duration - b.trend.duration
      return durDir === 'desc' ? -d : d
    })
  }, [enriched.withTrend, tab, durDir])

  const exportHtml = () => {
    const html = buildExportHtml(enriched.withTrend, enriched.missing, counts, asOf)
    const blob = new Blob([html], { type: 'text/html;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `六态汇总_${(asOf || new Date().toISOString().slice(0, 10)).replace(/-/g, '')}.html`
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4" onClick={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        className="flex max-h-[88vh] w-full max-w-4xl flex-col overflow-hidden rounded-lg border border-border bg-surface shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-border/60 px-4 py-3">
          <div className="flex items-baseline gap-2.5">
            <TrendingUp className="h-4 w-4 self-center text-sky-400" />
            <span className="text-sm font-medium text-foreground">六态市场状态汇总</span>
            <span className="text-[10px] text-muted">统计日 {asOf || '—'} · 基于利弗莫尔六态判定,阈值每票独立配置</span>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={exportHtml}
              className="inline-flex items-center gap-1 rounded-btn border border-sky-400/30 bg-sky-400/10 px-2.5 py-1 text-[10px] text-sky-300 hover:bg-sky-400/20 transition-colors cursor-pointer"
              title="导出为自包含 HTML 页面(可存档/分享)"
            >
              <Download className="h-3 w-3" />
              导出 HTML
            </button>
            <button onClick={onClose} className="text-muted hover:text-foreground"><X className="h-4 w-4" /></button>
          </div>
        </div>

        {/* 统计卡片 */}
        <div className="grid grid-cols-3 gap-3 px-4 pt-4">
          <div className="rounded-lg border border-border/60 bg-elevated/20 px-4 py-3">
            <div className="text-[10px] text-muted">标的总数</div>
            <div className="mt-1 text-2xl font-mono font-bold text-foreground">{items.length}</div>
          </div>
          <div className="rounded-lg border border-red-400/20 bg-red-400/[0.05] px-4 py-3">
            <div className="text-[10px] text-muted">多头(上涨趋势 / 自然回升 / 次级回升)</div>
            <div className="mt-1 text-2xl font-mono font-bold text-red-400">{counts.bull}</div>
          </div>
          <div className="rounded-lg border border-emerald-400/20 bg-emerald-400/[0.05] px-4 py-3">
            <div className="text-[10px] text-muted">空头(次级回撤 / 自然回撤 / 下跌趋势)</div>
            <div className="mt-1 text-2xl font-mono font-bold text-emerald-400">{counts.bear}</div>
          </div>
        </div>

        {/* 状态页签 */}
        <div className="flex flex-wrap items-center gap-1.5 px-4 pt-3">
          <button
            onClick={() => setTab('all')}
            className={`rounded-btn border px-2.5 py-0.5 text-[11px] transition-colors cursor-pointer ${
              tab === 'all' ? 'border-accent/50 bg-accent/10 text-accent' : 'border-border text-muted hover:text-foreground'
            }`}
          >
            全部 {enriched.withTrend.length}
          </button>
          {STATES.map((s) => (
            <button
              key={s.key}
              onClick={() => setTab(s.key)}
              className={`rounded-btn border px-2.5 py-0.5 text-[11px] transition-colors cursor-pointer ${
                tab === s.key
                  ? trendBadgeCls(s.key)
                  : 'border-border text-muted hover:text-foreground'
              }`}
            >
              {s.cn} {counts.byState[s.key] ?? 0}
            </button>
          ))}
          {enriched.missing.length > 0 && (
            <span className="ml-auto text-[10px] text-muted/60" title={enriched.missing.map((m) => m.name).join('、')}>
              未判定 {enriched.missing.length}(日 K 不足)
            </span>
          )}
        </div>

        {/* 表格 */}
        <div className="mt-3 flex-1 overflow-auto border-t border-border/60">
          <table className="w-full min-w-[700px] text-xs">
            <thead className="sticky top-0 bg-surface/95 backdrop-blur text-[10px] text-muted">
              <tr className="text-left">
                <th className="px-4 py-1.5 font-normal">股票名称</th>
                <th className="px-2 py-1.5 font-normal text-right">现价</th>
                <th className="px-2 py-1.5 font-normal text-center">所处状态</th>
                <th className="px-2 py-1.5 font-normal text-right">
                  <button
                    onClick={() => setDurDir((d) => (d === 'desc' ? 'asc' : 'desc'))}
                    className="inline-flex items-center gap-0.5 hover:text-foreground cursor-pointer"
                  >
                    持续时间 {durDir === 'desc' ? <ArrowDown className="h-2.5 w-2.5" /> : <ArrowUp className="h-2.5 w-2.5" />}
                  </button>
                </th>
                {/* [R29] 换成翻转触发价: 趋势途中上关键点=本轮最高收盘, 贴着现价没参考价值 */}
                <th className="px-2 py-1.5 font-normal text-right" title="收盘跌破即转弱(上涨/回升态: 本轮最高×(1-阈值); 回撤态: 下关键点)">跌破转弱</th>
                <th className="px-2 py-1.5 font-normal text-right" title="收盘站上即转强(回撤/下跌态: 本轮最低×(1+阈值); 回升态: 上关键点)">站上转强</th>
                <th className="px-4 py-1.5 font-normal text-center">近期信号</th>
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 ? (
                <tr><td colSpan={7} className="px-4 py-6 text-center text-muted">该状态下暂无标的</td></tr>
              ) : rows.map((r) => (
                <tr key={r.symbol} className="border-t border-border/30 hover:bg-elevated/40">
                  <td className="px-4 py-1.5">
                    <span className="font-medium text-foreground">{r.name}</span>
                    <span className="ml-1.5 text-[9px] font-mono text-muted">{r.symbol}</span>
                  </td>
                  <td className="px-2 py-1.5 text-right font-mono tabular-nums text-foreground">{r.close != null ? r.close.toFixed(2) : '—'}</td>
                  <td className="px-2 py-1.5 text-center">
                    <span className={`inline-flex whitespace-nowrap rounded border px-1.5 py-0.5 text-[10px] ${trendBadgeCls(r.trend.state)}`}>
                      {r.trend.state_cn}
                    </span>
                  </td>
                  <td className="px-2 py-1.5 text-right font-mono tabular-nums text-foreground">{r.trend.duration} 交易日</td>
                  <td className="px-2 py-1.5 text-right font-mono tabular-nums text-emerald-400/80"
                    title={`本轮最高收盘 ${r.trend.leg_high?.toFixed(2) ?? '—'} · 上关键点 ${r.trend.up_pivot?.toFixed(2) ?? '—'}`}>
                    {r.trend.flip_down?.toFixed(2) ?? '—'}
                  </td>
                  <td className="px-2 py-1.5 text-right font-mono tabular-nums text-red-400/80"
                    title={`本轮最低收盘 ${r.trend.leg_low?.toFixed(2) ?? '—'} · 下关键点 ${r.trend.dn_pivot?.toFixed(2) ?? '—'}`}>
                    {r.trend.flip_up?.toFixed(2) ?? '—'}
                  </td>
                  <td className="px-4 py-1.5 text-center">
                    {r.trend.signal ? (
                      <span className="text-[10px] text-amber-300" title={r.trend.signal_desc ?? undefined}>{r.trend.signal}</span>
                    ) : (
                      <span className="text-[10px] text-muted/40">—</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}

// ================================================================
// 自包含 HTML 导出(内联样式,浅色排版,无脚本无外链)
// ================================================================

function esc(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

function buildExportHtml(
  rows: (TrendSummaryItem & { trend: TrendInfo })[],
  missing: TrendSummaryItem[],
  counts: { byState: Record<string, number>; bull: number; bear: number },
  asOf: string,
): string {
  const sorted = [...rows].sort((a, b) => {
    const so = (STATE_ORDER[a.trend.state] ?? 9) - (STATE_ORDER[b.trend.state] ?? 9)
    return so !== 0 ? so : b.trend.duration - a.trend.duration
  })
  const bullColor = '#d03050'
  const bearColor = '#18a058'
  const stateColor = (s: LivermoreState) =>
    STATES.find((x) => x.key === s)?.side === 'bull' ? bullColor : bearColor
  const trs = sorted.map((r) => `
      <tr>
        <td>${esc(r.name)} <span class="sym">${esc(r.symbol)}</span></td>
        <td class="num">${r.close != null ? r.close.toFixed(2) : '—'}</td>
        <td><b style="color:${stateColor(r.trend.state)}">${esc(r.trend.state_cn)}</b></td>
        <td class="num">${r.trend.duration} 交易日</td>
        <td class="num">${esc(r.trend.since)}</td>
        <td class="num" style="color:${bearColor}">${r.trend.flip_down?.toFixed(2) ?? '—'}</td>
        <td class="num" style="color:${bullColor}">${r.trend.flip_up?.toFixed(2) ?? '—'}</td>
        <td>${r.trend.signal ? `<b>${esc(r.trend.signal)}</b> <span class="dim">${esc(r.trend.signal_desc ?? '')}</span>` : '—'}</td>
      </tr>`).join('')
  const chips = STATES.map((s) =>
    `<span class="chip"><i style="background:${s.side === 'bull' ? bullColor : bearColor}"></i>${s.cn} ${counts.byState[s.key] ?? 0}</span>`).join('')
  const missNote = missing.length
    ? `<p class="dim" style="margin-top:8px">未判定 ${missing.length} 只(日 K 不足):${esc(missing.map((m) => m.name).join('、'))}</p>`
    : ''
  return `<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>六态市场状态汇总 · ${esc(asOf)}</title>
<style>
  body{margin:0;padding:32px 24px;background:#f7f8fa;color:#1f2329;font:14px/1.6 -apple-system,'PingFang SC','Microsoft YaHei',sans-serif}
  .wrap{max-width:960px;margin:0 auto}
  h1{font-size:20px;margin:0 0 4px}
  .meta{color:#8a919f;font-size:12px;margin-bottom:20px}
  .cards{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:16px}
  .card{background:#fff;border:1px solid #e5e6eb;border-radius:8px;padding:14px 16px}
  .card .t{font-size:12px;color:#8a919f}
  .card .v{font-size:26px;font-weight:700;font-variant-numeric:tabular-nums;margin-top:2px}
  .chips{margin:0 0 14px;display:flex;flex-wrap:wrap;gap:8px}
  .chip{font-size:12px;color:#4e5666;background:#fff;border:1px solid #e5e6eb;border-radius:999px;padding:2px 10px;display:inline-flex;align-items:center;gap:6px}
  .chip i{width:8px;height:8px;border-radius:50%;display:inline-block}
  table{width:100%;border-collapse:collapse;background:#fff;border:1px solid #e5e6eb;border-radius:8px;overflow:hidden}
  th{font-size:12px;font-weight:500;color:#8a919f;text-align:left;padding:9px 12px;border-bottom:1px solid #e5e6eb;background:#fafbfc}
  td{padding:9px 12px;border-bottom:1px solid #f0f1f3;font-size:13px}
  tr:last-child td{border-bottom:none}
  .num{font-variant-numeric:tabular-nums;text-align:right}
  th.num,td.num{text-align:right}
  .sym{color:#a0a6b1;font-size:11px;margin-left:4px}
  .dim{color:#8a919f;font-size:12px}
  .foot{margin-top:18px;color:#a0a6b1;font-size:11px}
  @media print{body{background:#fff;padding:0}}
</style>
</head>
<body>
<div class="wrap">
  <h1>市场状态汇总</h1>
  <div class="meta">统计日 ${esc(asOf)} · 基于利弗莫尔六态判定(阈值每票独立配置)· 窗口近 180 个交易日 · 只认日线收盘价</div>
  <div class="cards">
    <div class="card"><div class="t">标的总数</div><div class="v">${rows.length + missing.length}</div></div>
    <div class="card"><div class="t">多头(上涨趋势 / 自然回升 / 次级回升)</div><div class="v" style="color:${bullColor}">${counts.bull}</div></div>
    <div class="card"><div class="t">空头(次级回撤 / 自然回撤 / 下跌趋势)</div><div class="v" style="color:${bearColor}">${counts.bear}</div></div>
  </div>
  <div class="chips">${chips}</div>
  <table>
    <thead><tr>
      <th>股票名称</th><th class="num">现价</th><th>所处状态</th><th class="num">持续时间</th>
      <th class="num">状态起始</th><th class="num">跌破转弱</th><th class="num">站上转强</th><th>近期信号</th>
    </tr></thead>
    <tbody>${trs}
    </tbody>
  </table>
  ${missNote}
  <p class="foot">生成于 ${new Date().toLocaleString('zh-CN')} · 牛来六态趋势分析 · 仅个人参考,不构成投资建议</p>
</div>
</body>
</html>
`
}
