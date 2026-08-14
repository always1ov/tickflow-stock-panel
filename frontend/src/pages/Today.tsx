/**
 * [fork 增强] 今日总览 —— 决策汇聚层。
 *
 * 把六态趋势/AI 信号预案/持仓出场线/监控触发按"需要行动的紧迫度"聚合成一屏:
 * ① 行动区(必须处理) ② 机会区(值得看) ③ 市场天气(定基调) ④ 持仓体检。
 * 数据全部来自既有模块,零新计算;AI 导读可选(手动点击,一次调用)。
 */
import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import {
  AlertTriangle, CheckCircle2, Compass, Download, Loader2, RefreshCw, Sparkles, Sunrise, Target,
} from 'lucide-react'
import { api, type TodayOverview } from '@/lib/api'
import { toast } from '@/components/Toast'

// ===== 自包含 HTML 导出(内联样式浅色排版, 无脚本无外链, 可存档/分享) =====

function esc(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

function buildTodayHtml(d: TodayOverview, brief: string | null): string {
  const bull = '#d03050'
  const bear = '#18a058'
  const postureColor: Record<string, string> = { 进攻: bull, 谨慎: '#c78326', 防守: bear, 观察: '#8a919f' }
  const sym = (name: string, symbol: string) =>
    symbol && symbol !== name ? ` <span class="sym">${esc(symbol)}</span>` : ''
  const actionRows = d.actions.map(a => `
      <li><i style="background:${a.severity === 'high' ? bull : '#c78326'}"></i>
        <b>${esc(a.name)}</b>${sym(a.name, a.symbol)} ${esc(a.text)}</li>`).join('')
  const oppRows = d.opportunities.map(o => `
      <li><i style="background:${bull}"></i>
        <b>${esc(o.name)}</b>${sym(o.name, o.symbol)} ${esc(o.text)}</li>`).join('')
  const holdRows = d.holdings.map(h => `
      <tr>
        <td>${esc(h.name)}${sym(h.name, h.symbol)}</td>
        <td class="num">${h.close?.toFixed(2) ?? '—'}</td>
        <td class="num" style="color:${h.pnl_pct == null ? '#8a919f' : h.pnl_pct > 0 ? bull : bear}">${h.pnl_pct != null ? (h.pnl_pct * 100).toFixed(1) + '%' : '—'}</td>
        <td class="num" style="color:${h.exit_triggered ? bull : '#1f2329'}">${h.line != null ? h.line.toFixed(2) + (h.exit_triggered ? ' 已触发' : '') : '—'}</td>
        <td>${esc(h.stage_cn ?? '—')}</td>
        <td style="color:${h.trend_side === '多头' ? bull : bear}">${h.trend_cn ? `${esc(h.trend_cn)} ${h.trend_duration}天` : '—'}</td>
      </tr>`).join('')
  const genAt = new Date().toLocaleString('zh-CN')
  return `<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>今日总览 · ${esc(d.as_of ?? '')}</title>
<style>
  body{margin:0;padding:32px 24px;background:#f7f8fa;color:#1f2329;font:14px/1.6 -apple-system,'PingFang SC','Microsoft YaHei',sans-serif}
  .wrap{max-width:860px;margin:0 auto}
  h1{font-size:20px;margin:0 0 4px}
  h2{font-size:14px;margin:22px 0 8px;display:flex;align-items:center;gap:6px}
  .meta{color:#8a919f;font-size:12px;margin-bottom:18px}
  .posture{display:inline-block;border-radius:999px;padding:2px 14px;font-weight:600;color:#fff}
  .weather{background:#fff;border:1px solid #e5e6eb;border-radius:8px;padding:12px 16px;display:flex;gap:14px;align-items:center;flex-wrap:wrap}
  .brief{background:#f3efff;border:1px solid #ddd0fa;border-radius:8px;padding:12px 16px;font-size:13px;margin-top:14px}
  ul.items{list-style:none;margin:0;padding:0;background:#fff;border:1px solid #e5e6eb;border-radius:8px}
  ul.items li{padding:9px 14px;border-bottom:1px solid #f0f1f3;font-size:13px;display:flex;gap:8px;align-items:baseline}
  ul.items li:last-child{border-bottom:none}
  ul.items i{width:7px;height:7px;border-radius:50%;display:inline-block;flex:none;position:relative;top:-1px}
  .empty{background:#fff;border:1px solid #e5e6eb;border-radius:8px;padding:14px 16px;font-size:13px;color:#8a919f}
  table{width:100%;border-collapse:collapse;background:#fff;border:1px solid #e5e6eb;border-radius:8px;overflow:hidden}
  th{font-size:12px;font-weight:500;color:#8a919f;text-align:left;padding:8px 12px;border-bottom:1px solid #e5e6eb;background:#fafbfc}
  td{padding:8px 12px;border-bottom:1px solid #f0f1f3;font-size:13px}
  tr:last-child td{border-bottom:none}
  .num{font-variant-numeric:tabular-nums;text-align:right}
  th.num,td.num{text-align:right}
  .sym{color:#a0a6b1;font-size:11px}
  .foot{margin-top:18px;color:#a0a6b1;font-size:11px}
  @media print{body{background:#fff;padding:0}}
</style>
</head>
<body>
<div class="wrap">
  <h1>今日总览</h1>
  <div class="meta">数据截至 ${esc(d.as_of ?? '—')} · 自选 ${d.watchlist_total} 只(其中 ${d.trend_total} 只有趋势判定)· 生成于 ${genAt}</div>
  <div class="weather">
    <span class="posture" style="background:${postureColor[d.weather.posture] ?? '#8a919f'}">${esc(d.weather.posture)}</span>
    <span style="font-size:13px;color:#4e5666">${esc(d.weather.posture_reason)}</span>
    <span style="margin-left:auto;font-size:12px;color:#8a919f">涨势 <b style="color:${bull}">${d.weather.bull}</b> / 跌势 <b style="color:${bear}">${d.weather.bear}</b> · 刚转强 ${d.weather.new_bull} · 刚转弱 ${d.weather.new_bear}</span>
  </div>
  ${brief ? `<div class="brief">✦ ${esc(brief)}</div>` : ''}
  <h2>⚠️ 需要行动(${d.actions.length})</h2>
  ${d.actions.length ? `<ul class="items">${actionRows}</ul>` : '<div class="empty">今日无需操作 —— 管住手</div>'}
  <h2>🎯 值得关注(${d.opportunities.length})</h2>
  ${d.opportunities.length ? `<ul class="items">${oppRows}</ul>` : '<div class="empty">暂无新信号 —— 等待比出手更常见</div>'}
  <h2>💼 持仓体检(${d.holdings.length})</h2>
  ${d.holdings.length ? `<table>
    <thead><tr><th>标的</th><th class="num">现价</th><th class="num">浮盈</th><th class="num">出场线</th><th>阶段</th><th>趋势</th></tr></thead>
    <tbody>${holdRows}</tbody>
  </table>` : '<div class="empty">暂无持仓标记</div>'}
  <p class="foot">TickFlow Stock Panel · 六态趋势 + ATR 出场线 + 生命线(20日线) · 仅个人参考,不构成投资建议</p>
</div>
</body>
</html>
`
}

const POSTURE_STYLE: Record<string, string> = {
  进攻: 'border-red-400/40 bg-red-400/10 text-red-400',
  谨慎: 'border-amber-400/40 bg-amber-400/10 text-amber-300',
  防守: 'border-emerald-400/40 bg-emerald-400/10 text-emerald-400',
  观察: 'border-border bg-base text-muted',
}

export function Today() {
  const navigate = useNavigate()
  const q = useQuery({
    queryKey: ['today-overview'],
    queryFn: () => api.todayOverview(),
    staleTime: 60_000,
  })
  const [brief, setBrief] = useState<string | null>(null)
  const briefMut = useMutation({
    mutationFn: () => api.todayBrief(),
    onSuccess: (r) => {
      if (r.error) toast(r.error, 'error')
      else setBrief(r.brief ?? null)
    },
    onError: (e: Error) => toast(`导读生成失败: ${e.message}`, 'error'),
  })

  const goStock = (symbol: string, name: string) =>
    navigate(`/stock-analysis?symbol=${encodeURIComponent(symbol)}&name=${encodeURIComponent(name)}`)

  const d = q.data

  return (
    <div className="p-4 md:p-6 max-w-[1500px] mx-auto space-y-4">
      {/* 头部 */}
      <div className="flex flex-wrap items-center gap-3">
        <Sunrise className="h-5 w-5 text-amber-300" />
        <h1 className="text-base font-semibold text-foreground">今日总览</h1>
        {d?.as_of && <span className="text-[10px] text-muted">数据截至 {d.as_of} · 自选 {d.watchlist_total} 只(其中 {d.trend_total} 只有趋势判定)</span>}
        <div className="ml-auto flex items-center gap-2">
          <button
            onClick={() => {
              if (!d) return
              const html = buildTodayHtml(d, brief)
              const blob = new Blob([html], { type: 'text/html;charset=utf-8' })
              const url = URL.createObjectURL(blob)
              const a = document.createElement('a')
              a.href = url
              a.download = `今日总览_${(d.as_of ?? new Date().toISOString().slice(0, 10)).replace(/-/g, '')}.html`
              a.click()
              URL.revokeObjectURL(url)
            }}
            disabled={!d}
            title="导出为自包含 HTML 页面(可存档/分享;已生成 AI 导读会一并带上)"
            className="inline-flex items-center gap-1 rounded-full border border-sky-400/30 bg-sky-400/10 px-2.5 py-1 text-[10px] text-sky-300 hover:bg-sky-400/20 disabled:opacity-50 transition-colors cursor-pointer"
          >
            <Download className="h-3 w-3" />
            导出 HTML
          </button>
          <button
            onClick={() => briefMut.mutate()}
            disabled={briefMut.isPending || !d}
            className="inline-flex items-center gap-1 rounded-full border border-violet-400/30 bg-violet-400/10 px-2.5 py-1 text-[10px] text-violet-300 hover:bg-violet-400/20 disabled:opacity-50 transition-colors cursor-pointer"
          >
            {briefMut.isPending ? <Loader2 className="h-3 w-3 animate-spin" /> : <Sparkles className="h-3 w-3" />}
            AI 导读
          </button>
          <button
            onClick={() => q.refetch()}
            disabled={q.isFetching}
            className="inline-flex items-center gap-1 rounded-full border border-border bg-base px-2.5 py-1 text-[10px] text-muted hover:text-foreground disabled:opacity-50 transition-colors cursor-pointer"
          >
            <RefreshCw className={`h-3 w-3 ${q.isFetching ? 'animate-spin' : ''}`} />
            刷新
          </button>
        </div>
      </div>

      {brief && (
        <div className="rounded-lg border border-violet-400/20 bg-violet-400/[0.06] px-4 py-3 text-xs leading-relaxed text-foreground/90">
          <Sparkles className="mr-1.5 inline h-3.5 w-3.5 text-violet-300" />
          {brief}
        </div>
      )}

      {q.isLoading && (
        <div className="flex items-center justify-center py-16"><Loader2 className="h-5 w-5 animate-spin text-muted" /></div>
      )}
      {q.isError && (
        <div className="rounded-lg border border-red-400/30 bg-red-400/10 px-4 py-3 text-xs text-red-400">
          总览加载失败:{(q.error as Error)?.message}
        </div>
      )}

      {d && (
        <>
          {/* ③ 市场天气(放最上面一条横幅, 定基调) */}
          <div className="flex flex-wrap items-center gap-3 rounded-lg border border-border/60 bg-surface/40 px-4 py-3">
            <Compass className="h-4 w-4 text-sky-400" />
            <span className={`inline-flex rounded-full border px-3 py-0.5 text-sm font-medium ${POSTURE_STYLE[d.weather.posture] ?? POSTURE_STYLE['观察']}`}>
              {d.weather.posture}
            </span>
            <span className="text-xs text-muted">{d.weather.posture_reason}</span>
            <span className="ml-auto text-[11px] font-mono text-muted">
              涨势 <span className="text-red-400 font-semibold">{d.weather.bull}</span>
              <span className="mx-1 text-muted/40">/</span>
              跌势 <span className="text-emerald-400 font-semibold">{d.weather.bear}</span>
              <span className="mx-2 text-muted/40">·</span>
              刚转强 {d.weather.new_bull} · 刚转弱 {d.weather.new_bear}
            </span>
          </div>

          {/* ① 行动区 */}
          <section className="rounded-lg border border-border/60 bg-surface/40 overflow-hidden">
            <div className="flex items-center gap-2 border-b border-border/40 px-4 py-2.5">
              <AlertTriangle className="h-4 w-4 text-red-400" />
              <span className="text-sm font-medium text-foreground">需要行动</span>
              <span className="text-[10px] text-muted">{d.actions.length} 项</span>
            </div>
            {d.actions.length === 0 ? (
              <div className="flex items-center gap-2 px-4 py-5 text-xs text-muted">
                <CheckCircle2 className="h-4 w-4 text-emerald-400" />
                今日无需操作 —— 这本身就是有价值的信息,管住手
              </div>
            ) : (
              <ul className="grid lg:grid-cols-2 -mb-px">
                {d.actions.map((a, i) => (
                  <li key={i} className="border-b border-border/30 lg:odd:border-r">
                    <button
                      onClick={() => a.symbol && goStock(a.symbol, a.name)}
                      className="flex w-full items-start gap-2.5 px-4 py-2.5 text-left hover:bg-elevated/40 transition-colors cursor-pointer"
                    >
                      <span className={`mt-0.5 h-1.5 w-1.5 shrink-0 rounded-full ${a.severity === 'high' ? 'bg-red-400' : 'bg-amber-300'}`} />
                      <span className="text-xs leading-relaxed">
                        <span className="font-medium text-foreground">{a.name}</span>
                        {a.symbol && a.symbol !== a.name && <span className="ml-1.5 text-[9px] font-mono text-muted">{a.symbol}</span>}
                        <span className="ml-2 text-foreground/80">{a.text}</span>
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </section>

          {/* ② 机会区 */}
          <section className="rounded-lg border border-border/60 bg-surface/40 overflow-hidden">
            <div className="flex items-center gap-2 border-b border-border/40 px-4 py-2.5">
              <Target className="h-4 w-4 text-red-400" />
              <span className="text-sm font-medium text-foreground">值得关注</span>
              <span className="text-[10px] text-muted">{d.opportunities.length} 项 · 刚开始走强的票 + 接近买入触发价的票</span>
            </div>
            {d.opportunities.length === 0 ? (
              <div className="px-4 py-5 text-xs text-muted">暂无新信号 —— 等待比出手更常见</div>
            ) : (
              <ul className="grid lg:grid-cols-2 -mb-px">
                {d.opportunities.map((o, i) => (
                  <li key={i} className="border-b border-border/30 lg:odd:border-r">
                    <button
                      onClick={() => goStock(o.symbol, o.name)}
                      className="flex w-full items-start gap-2.5 px-4 py-2.5 text-left hover:bg-elevated/40 transition-colors cursor-pointer"
                    >
                      <span className="mt-0.5 h-1.5 w-1.5 shrink-0 rounded-full bg-red-400/70" />
                      <span className="text-xs leading-relaxed">
                        <span className="font-medium text-foreground">{o.name}</span>
                        {o.symbol !== o.name && <span className="ml-1.5 text-[9px] font-mono text-muted">{o.symbol}</span>}
                        <span className="ml-2 text-foreground/80">{o.text}</span>
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </section>

          {/* ④ 持仓体检 */}
          <section className="rounded-lg border border-border/60 bg-surface/40 overflow-hidden">
            <div className="flex items-center gap-2 border-b border-border/40 px-4 py-2.5">
              <span className="text-sm font-medium text-foreground">持仓体检</span>
              <span className="text-[10px] text-muted">{d.holdings.length} 只(已触发/最接近出场线的排前面)</span>
            </div>
            {d.holdings.length === 0 ? (
              <div className="px-4 py-5 text-xs text-muted">
                暂无持仓标记 —— 在个股分析页决策台把持有的票标「持有」并填成本,这里就会出现仓位全景
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[640px] text-xs">
                  <thead className="text-[10px] text-muted">
                    <tr className="text-left">
                      <th className="px-4 py-1.5 font-normal">标的</th>
                      <th className="px-2 py-1.5 font-normal text-right">现价</th>
                      <th className="px-2 py-1.5 font-normal text-right">浮盈</th>
                      <th className="px-2 py-1.5 font-normal text-right">出场线</th>
                      <th className="px-2 py-1.5 font-normal text-center">阶段</th>
                      <th className="px-2 py-1.5 font-normal text-center">趋势</th>
                      <th className="px-4 py-1.5 font-normal text-center">AI 信号</th>
                    </tr>
                  </thead>
                  <tbody>
                    {d.holdings.map((h) => (
                      <tr
                        key={h.symbol}
                        onClick={() => goStock(h.symbol, h.name)}
                        className="border-t border-border/30 hover:bg-elevated/40 cursor-pointer"
                      >
                        <td className="px-4 py-1.5">
                          <span className="font-medium text-foreground">{h.name}</span>
                          {h.symbol !== h.name && <span className="ml-1.5 text-[9px] font-mono text-muted">{h.symbol}</span>}
                        </td>
                        <td className="px-2 py-1.5 text-right font-mono">{h.close?.toFixed(2) ?? '—'}</td>
                        <td className={`px-2 py-1.5 text-right font-mono ${h.pnl_pct == null ? 'text-muted' : h.pnl_pct > 0 ? 'text-red-400' : h.pnl_pct < 0 ? 'text-emerald-400' : 'text-muted'}`}>
                          {h.pnl_pct != null ? `${(h.pnl_pct * 100).toFixed(1)}%` : '—'}
                        </td>
                        <td className={`px-2 py-1.5 text-right font-mono ${h.exit_triggered ? 'text-red-400' : (h.distance_pct ?? -1) > -0.03 ? 'text-amber-300' : 'text-muted'}`}>
                          {h.line != null ? `${h.line.toFixed(2)}${h.exit_triggered ? ' 已触发' : h.distance_pct != null ? ` · 距${(Math.abs(h.distance_pct) * 100).toFixed(1)}%` : ''}` : '—'}
                        </td>
                        <td className="px-2 py-1.5 text-center text-[10px] text-muted">{h.stage_cn ?? '—'}</td>
                        <td className="px-2 py-1.5 text-center text-[10px]">
                          {h.trend_cn ? (
                            <span className={h.trend_side === '多头' ? 'text-red-400' : 'text-emerald-400'}>
                              {h.trend_cn} {h.trend_duration}天
                            </span>
                          ) : '—'}
                        </td>
                        <td className="px-4 py-1.5 text-center text-[10px] text-muted">{h.signal ?? '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </>
      )}
    </div>
  )
}
