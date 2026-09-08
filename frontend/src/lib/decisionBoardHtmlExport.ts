/**
 * [fork 增强] 自选决策台 —— 自包含 HTML 导出(通道结论存档件)。
 *
 * [R167] 从 WatchlistDecisionBoard.tsx 拆出。纯函数不碰 React, 与今日总览的
 * lib/todayHtmlExport.ts 同一模式: (行, 总数) → 一份可存档的 HTML 字符串。
 */
import type { KeltnerBand, KeltnerBands, KeltnerVerdict, TrendInfo, Urgency } from '@/lib/api'

export type ExportRow = {
  symbol: string; name: string; close: number | null; changePct: number | null
  held: boolean; pnl: number | null
  trend?: TrendInfo; kc?: KeltnerBands
  /** [R178] 该动了 —— 导出件里最该先看的一列, 排在最前面 */
  urg?: Urgency
}

// [R178] 「该动了」的浅色配色。与 EXPORT_TONE 同一个理由: 导出件是浅色排版。
const EXPORT_URGENCY: Record<Urgency['level'], string> = {
  triggered: 'background:#fdecec;color:#c0392b;font-weight:600',
  near: 'background:#fdf0e3;color:#c78326',
  flip: 'background:#f3ecfd;color:#7b4fc0',
  band: 'background:#e6f4fb;color:#1c6ea4',
  idle: 'color:#b6bcc7',
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

export function buildBoardHtml(rows: ExportRow[], total: number): string {
  const bull = '#d03050'
  const bear = '#18a058'
  const pos = (b?: KeltnerBand) => (b ? esc(b.pos_cn) : '—')
  const body = rows.map(r => {
    const v = r.kc?.verdict
    return `
      <tr>
        <td>${r.urg && r.urg.level !== 'idle'
          ? `<span class="tag" style="${EXPORT_URGENCY[r.urg.level]}" title="${esc(r.urg.reason)}">${esc(r.urg.label)}${
              r.urg.distance != null ? ' ' + (r.urg.distance * 100).toFixed(1) + '%' : ''}</span>`
          : '—'}</td>
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
    只列出<b>要动的</b>或「结论」列有内容的标的 —— 既没触发、三档通道又都在中部的票没有信息量, 不占篇幅。<br>
    通道口径:短期 MA20±2ATR / 中期 MA60±2.5ATR / 长期 MA120±3ATR,<b>收盘价</b>判定。<br>
    结论说的是<b>位置</b>(贵不贵), 不是会不会继续涨。清仓与否看止盈线与生命线, 优先级在通道之上。<br>
    「该动」是纯规则判定(已触发 &gt; 逼近 &gt; 刚变盘 &gt; 到轨), <b>AI 不参与</b> —— 它只解释, 不决定先看谁。
  </div>
  <table>
    <thead><tr>
      <th>该动</th><th>标的</th><th class="num">现价</th><th class="num">涨跌</th><th>仓位</th>
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

