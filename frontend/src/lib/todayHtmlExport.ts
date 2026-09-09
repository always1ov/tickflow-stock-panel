/**
 * [fork 增强] 今日总览 —— 自包含 HTML 导出。
 *
 * [R167] 从 Today.tsx 拆出。纯函数, 不碰 React: (总览数据, AI 导读, 优选) → 一份
 * 可存档/分享的 HTML 字符串。放在 lib 而不是 components, 因为它没有任何渲染语义。
 */
import type { TodayOverview, TodayPick } from '@/lib/api'
// 位置/量能的状态词与屏幕共用一份定义 —— 「多少算多」的分界只该有一处
import { posWord, volWord } from '@/components/today/OpportunityTable'

// ===== 自包含 HTML 导出(内联样式浅色排版, 无脚本无外链, 可存档/分享) =====
//
// [R143] 与界面同步。这份导出件从 R47 之后就没跟上过 —— 界面已经换了整套评分
// (R134 的硬门槛 + R189 的质地×时机两轴)、加了门槛漏斗、把主线/AI/胜率/通道结论收编成"注记",
// 导出件却还在按 v1 的样子打印一个光秃秃的把握分。**存档件与屏幕说的不是同一件
// 事, 比没有存档更糟**: 事后复盘时你会拿它当"当时看到的东西", 而它不是。
//
// 同步的三块:
//   [R179] 顺序与屏幕一致: 市场状态 → 需要行动 → 持仓体检 → 值得关注。
//   风险排在机会前面 —— 导出件常被打印出来照着做, 顺序错了后果和屏幕上一样。
//   1. 市场状态 —— 与屏幕一样的五个统计格(总仓位基调/出手结构/自选强弱/
//      全市场/成交额) + 主线 + 姿态理由
//   2. AI 导读与优选 —— 优选带上 R121 的核对结论(已核对/存疑/待查), 驳回的
//      单独列出。**存档件尤其不能只印结论不印核对状态**
//   3. 值得关注 —— [R214] 跟着屏幕改成 把握 / 名称 / 结论 / 走势 / 建议仓位:
//      结论提到依据前面, 位置与量比从数字换成状态词(共用屏幕那份阈值),
//      注记退到每行下面的小字。仍然与屏幕列一一对应。

function esc(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

export function buildTodayHtml(d: TodayOverview, brief: string | null,
                        picks: TodayPick[] | null): string {
  const bull = '#d03050'
  const bear = '#18a058'
  const postureColor: Record<string, string> = { 进攻: bull, 谨慎: '#c78326', 防守: bear, 观察: '#8a919f' }
  const sym = (name: string, symbol: string) =>
    symbol && symbol !== name ? ` <span class="sym">${esc(symbol)}</span>` : ''
  const noteStyle: Record<string, string> = {
    good: 'background:#e8f7ee;color:#18794e',
    bad: 'background:#fdecec;color:#c0392b',
    info: 'background:#f0f1f3;color:#5b6472',
  }
  // [R189] 两轴分解条: 打印出来也要能一眼看出这分是谁给的
  const dimBar = (o: TodayOverview['opportunities'][number]) => {
    const rows: [string, number | null | undefined, string][] = [
      ['质地', o.axes?.quality, bull], ['时机', o.axes?.timing, '#1c6ea4'],
    ]
    return `<span class="dims">${rows.map(([, v, c]) =>
      `<i style="background:${c};height:${v == null ? 0 : Math.max(8, Math.min(100, v))}%"></i>`).join('')}</span>`
  }

  const actionRows = d.actions.map(a => `
      <li><i style="background:${a.severity === 'high' ? bull : '#c78326'}"></i>
        <b>${esc(a.name)}</b>${sym(a.name, a.symbol)} ${esc(a.text)}</li>`).join('')

  // [R214] 列结构跟着屏幕走: 把握 / 名称 / 结论 / 走势 / 建议仓位。
  //
  // 屏幕上「位置」「量比」两列数字换成了状态词, 这里也换 —— 而且**直接调屏幕
  // 那两个函数**, 不在这边抄一份阈值。分界抄成两份, 屏幕说「放量刚好」而存档
  // 说「量太大」的那天就没法查了。存档件与屏幕说的不是同一件事, 比没有存档更糟。
  //
  // 「注记·不计分」的独立列跟着屏幕撤掉, 挪到下面那行小字里 —— 它本来就写着
  // 不计分, 是版面上优先级最低的东西, 但不该丢。
  const oppRows = d.opportunities.map(o => {
    const p = o.channel_pct != null ? posWord(o.channel_pct) : null
    const v = o.vol_ratio != null ? volWord(o.vol_ratio) : null
    const trend = [
      esc(o.text),
      o.trend_state_cn ? `<span class="adv" style="background:#f0f1f3;color:#5b6472">${esc(o.trend_state_cn)}</span>` : '',
      o.intraday ? '<span class="adv" style="background:#fdf0e3;color:#c78326">盘中·待收盘确认</span>' : '',
    ].filter(Boolean).join(' ')
    const words = [
      p ? `<span title="${esc(p.why)}">${esc(p.cn)}</span>` : '',
      v ? `<span title="${esc(v.why)}">${esc(v.cn)}</span>` : '',
      o.gap_pct == null ? ''
        : `${o.gap_pct <= 0 ? '已过关键点' : o.gap_pct <= 1.5 ? '就差' : '还差'} ${Math.abs(o.gap_pct).toFixed(1)}%`,
    ].filter(Boolean).join(' · ')
    const notes = (o.notes ?? [])
      .map(n => `<span class="adv" style="${noteStyle[n.tone] ?? noteStyle.info}">${esc(n.label)}</span>`)
      .join(' ')
    return `
      <tr>
        <td class="num"><b class="score">${o.score}${o.partial ? '<sup>*</sup>' : ''}</b>${dimBar(o)}</td>
        <td class="name"><b>${esc(o.name)}</b>${sym(o.name, o.symbol)}${o.board ? ` <span class="adv" style="background:#eef1f5;color:#5b6472">${esc(o.board)}</span>` : ''}</td>
        <td>${o.action ? `<span class="adv" style="${o.action.code === 'today' ? 'background:#e6ecfb;color:#3451a8;font-weight:600' : o.action.code === 'after_close' ? 'background:#fdf0e3;color:#c78326' : noteStyle.info}">${esc(o.action.label)}</span><br><span style="font-size:10px;color:#5b6472">${esc(o.action.reason)}</span>` : '—'}</td>
        <td class="sig">${trend}${words ? `<br><span style="font-size:10px;color:#5b6472">${words}</span>` : ''}</td>
        <td>${o.advice ? `<span class="adv">${esc(o.advice.text)}</span>` : '—'}</td>
      </tr>
      <tr class="sub"><td></td><td colspan="4">${esc(o.why || '')}${notes ? ` · 佐证(不计分):${notes}` : ''}${o.advice?.plan ? ` · <span style="color:#1c6ea4">建仓路径:${esc(o.advice.plan)}</span>` : ''}</td></tr>`
  }).join('')

  const holdRows = d.holdings.map(h => `
      <tr>
        <td class="name">${esc(h.name)}${sym(h.name, h.symbol)}</td>
        <td class="num">${h.close?.toFixed(2) ?? '—'}</td>
        <td class="num">${h.weight != null ? h.weight + '%' : '—'}</td>
        <td class="num" style="color:${h.pnl_pct == null ? '#8a919f' : h.pnl_pct > 0 ? bull : bear}">${h.pnl_pct != null ? (h.pnl_pct * 100).toFixed(1) + '%' : '—'}</td>
        <td class="num" style="color:${h.exit_triggered ? bull : '#1f2329'}">${h.line != null ? h.line.toFixed(2) + (h.exit_triggered ? ' 已触发' : '') : '—'}</td>
        <td>${esc(h.stage_cn ?? '—')}</td>
        <td style="color:${h.trend_side === '多头' ? bull : bear}">${h.trend_cn ? `${esc(h.trend_cn)} ${h.trend_duration}天` : '—'}</td>
        <td style="color:${h.stance === '离场' ? bull : h.stance === '减仓' ? '#c78326' : '#4e5666'};font-weight:${h.stance === '离场' ? 700 : 400}">${esc(h.stance)}</td>
      </tr>`).join('')

  // 与屏幕同款的五个统计格
  const cap = d.position_hint?.posture_cap
  const m = d.meso
  const stat = (label: string, value: string, sub = '') =>
    `<div class="cell"><div class="k">${label}</div><div class="v">${value}</div>${sub ? `<div class="s">${sub}</div>` : ''}</div>`
  const stats = [
    stat('总仓位基调', cap != null ? `≤${(cap * 10).toFixed(0)}成` : '—', `${esc(d.weather.posture)}档`),
    stat('出手结构', d.gates?.candidates ? `${d.gates.passed}/${d.gates.candidates}` : '—', '只候选过门槛'),
    stat('自选强弱', `<b style="color:${bull}">${d.weather.bull}</b> / <b style="color:${bear}">${d.weather.bear}</b>`,
      `刚转强 ${d.weather.new_bull} · 刚转弱 ${d.weather.new_bear}`),
    stat('全市场', m?.breadth ? `<b style="color:${bull}">${m.breadth.up}</b> / <b style="color:${bear}">${m.breadth.down}</b>` : '—', '涨 / 跌'),
    stat('两市成交额', m?.amount ? esc(m.amount.text) : '—',
      m?.amount?.pct_rank != null ? `${(m.amount.pct_rank * 100).toFixed(0)}% 分位 · ${esc(m.amount.label ?? '')}` : ''),
  ].join('')

  const shown = (picks ?? []).filter(p => p.verdict !== '驳回')
  const rejected = (picks ?? []).filter(p => p.verdict === '驳回')
  const pickStyle: Record<string, string> = {
    已核对: 'background:#e8f7ee;color:#18794e', 存疑: 'background:#fdf0e3;color:#c78326',
    待查: 'background:#f0f1f3;color:#5b6472', 驳回: 'background:#fdecec;color:#c0392b',
  }
  const genAt = new Date().toLocaleString('zh-CN')
  return `<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>今日总览 · ${esc(d.as_of ?? '')}</title>
<style>
  body{margin:0;padding:32px 24px;background:#f7f8fa;color:#1f2329;font:14px/1.6 -apple-system,'PingFang SC','Microsoft YaHei',sans-serif}
  .wrap{max-width:1100px;margin:0 auto}
  h1{font-size:20px;margin:0 0 4px}
  h2{font-size:14px;margin:22px 0 8px;display:flex;align-items:center;gap:6px}
  .meta{color:#8a919f;font-size:12px;margin-bottom:18px}
  .posture{display:inline-block;border-radius:999px;padding:2px 14px;font-weight:600;color:#fff}
  .card{background:#fff;border:1px solid #e5e6eb;border-radius:8px;overflow:hidden}
  .hd{padding:10px 16px;border-bottom:1px solid #f0f1f3;display:flex;gap:10px;align-items:center;flex-wrap:wrap}
  .grid{display:grid;grid-template-columns:repeat(5,1fr)}
  .cell{padding:9px 14px;border-right:1px solid #f0f1f3}
  .cell:last-child{border-right:none}
  .cell .k{font-size:11px;color:#8a919f}
  .cell .v{font-size:15px;font-weight:600;font-variant-numeric:tabular-nums;margin-top:2px}
  .cell .s{font-size:11px;color:#a0a6b1;margin-top:2px}
  .row{padding:8px 16px;border-top:1px solid #f0f1f3;font-size:12px;color:#5b6472}
  .brief{background:#f3efff;border:1px solid #ddd0fa;border-radius:8px;padding:12px 16px;margin-top:14px}
  .brief p{margin:6px 0 0;font-size:13px;line-height:1.8;max-width:80ch}
  .picks{margin:8px 0 0;padding:0;list-style:none}
  .picks li{font-size:12px;padding:3px 0;border-top:1px solid #e7defa}
  ul.items{list-style:none;margin:0;padding:0;background:#fff;border:1px solid #e5e6eb;border-radius:8px}
  ul.items li{padding:9px 14px;border-bottom:1px solid #f0f1f3;font-size:13px;display:flex;gap:8px;align-items:baseline}
  ul.items li:last-child{border-bottom:none}
  ul.items i{width:7px;height:7px;border-radius:50%;display:inline-block;flex:none;position:relative;top:-1px}
  .empty{background:#fff;border:1px solid #e5e6eb;border-radius:8px;padding:14px 16px;font-size:13px;color:#8a919f}
  table{width:100%;border-collapse:collapse;background:#fff;border:1px solid #e5e6eb;border-radius:8px;overflow:hidden}
  th{font-size:12px;font-weight:500;color:#8a919f;text-align:left;padding:8px 12px;border-bottom:1px solid #e5e6eb;background:#fafbfc;white-space:nowrap}
  td{padding:7px 12px;border-bottom:1px solid #f0f1f3;font-size:13px;white-space:nowrap;vertical-align:middle}
  td.name,td.sig{white-space:normal}
  tr.sub td{border-bottom:1px solid #f0f1f3;padding:0 12px 7px;font-size:11px;color:#8a919f;white-space:normal}
  tr:last-child td{border-bottom:none}
  .num{font-variant-numeric:tabular-nums;text-align:right}
  th.num,td.num{text-align:right}
  .sym{color:#a0a6b1;font-size:11px}
  .score{background:#f0f1f3;color:#4e5666;border-radius:3px;padding:1px 5px;font-size:11px;font-variant-numeric:tabular-nums}
  .dims{display:inline-flex;align-items:flex-end;gap:2px;height:14px;margin-left:5px;vertical-align:middle}
  .dims i{width:3px;background:#dfe2e7;border-radius:2px;display:block}
  .adv{background:#e8f3fb;color:#1c6ea4;border-radius:3px;padding:1px 5px;font-size:11px;white-space:nowrap;display:inline-block}
  .foot{margin-top:18px;color:#a0a6b1;font-size:11px}
  @media print{body{background:#fff;padding:0}}
</style>
</head>
<body>
<div class="wrap">
  <h1>今日总览</h1>
  <div class="meta">数据截至 ${esc(d.as_of ?? '—')} · 自选 ${d.watchlist_total} 只(其中 ${d.trend_total} 只有趋势判定)· 生成于 ${genAt}</div>

  <div class="card">
    <div class="hd">
      <span class="posture" style="background:${postureColor[d.weather.posture] ?? '#8a919f'}">${esc(d.weather.posture)}</span>
      ${d.weather.market ? `<span class="posture" style="background:${postureColor[d.weather.market.mode] ?? '#8a919f'};font-size:11px;padding:1px 10px">${esc(d.weather.market.benchmark_name ?? '大盘')}·${esc(d.weather.market.mode)}</span>` : ''}
      <span style="font-size:12px;color:#8a919f">${esc(d.weather.posture_reason)}</span>
    </div>
    <div class="grid">${stats}</div>
    ${m?.mainline ? `<div class="row">${m.mainline.stale ? '主线(已停更)' : '今日主线'} · ${m.mainline.rows.slice(0, 3).map(x => `<b>${esc(x.member)}</b> ${x.limit_up_count} 家涨停`).join(' · ')}</div>` : ''}
    ${d.gates?.text ? `<div class="row">三道硬门槛 · ${esc(d.gates.text)}</div>` : ''}
  </div>

  ${brief || shown.length || rejected.length ? `<div class="brief">
    <b style="font-size:11px;color:#7a4fd0">✦ AI 导读·优选</b>
    ${brief ? `<p>${esc(brief)}</p>` : ''}
    ${shown.length ? `<ul class="picks">${shown.map(p => `<li><b>${esc(p.name || p.symbol)}</b> <span class="adv" style="${pickStyle[p.verdict ?? '待查'] ?? pickStyle.待查}">${esc(p.verdict ?? '待查')}</span> ${esc(p.reason)}${p.verdict_note ? ` <span style="color:#c78326">(${esc(p.verdict_note)})</span>` : ''}</li>`).join('')}</ul>` : ''}
    ${rejected.length ? `<ul class="picks">${rejected.map(p => `<li style="color:#8a919f"><b>${esc(p.name || p.symbol)}</b> <span class="adv" style="${pickStyle.驳回}">已驳回</span> <s>${esc(p.reason)}</s> ${esc(p.verdict_note ?? '')}</li>`).join('')}</ul>` : ''}
  </div>` : ''}

  <h2>⚠️ 需要行动(${d.actions.length})</h2>
  ${d.actions.length ? `<ul class="items">${actionRows}</ul>` : '<div class="empty">今日无需操作 —— 管住手</div>'}
  <h2>💼 持仓体检(${d.holdings.length})${d.portfolio ? `<span style="font-weight:400;font-size:12px;color:#8a919f;margin-left:8px">组合:平均浮盈 ${d.portfolio.avg_pnl != null ? (d.portfolio.avg_pnl * 100).toFixed(1) + '%' : '—'} · 已触发 ${d.portfolio.triggered} · 逼近出场线 ${d.portfolio.near_exit} · 空头趋势 ${d.portfolio.bearish}${d.portfolio.total_weight != null ? ` · 总仓位 ${(d.portfolio.total_weight / 10).toFixed(1)}成${d.portfolio.drawdown != null ? ` · 距净值高点 -${(d.portfolio.drawdown * 100).toFixed(1)}%` : ''}` : ''}</span>` : ''}</h2>
  ${d.holdings.length ? `<table>
    <thead><tr><th>标的</th><th class="num">现价</th><th class="num">仓位</th><th class="num">浮盈</th><th class="num">出场线</th><th>阶段</th><th>趋势</th><th>操作建议</th></tr></thead>
    <tbody>${holdRows}</tbody>
  </table>` : '<div class="empty">暂无持仓标记</div>'}
  <h2>🎯 值得关注(${d.opportunities.length}·${d.prefs.min_hist_pct > 0 ? `只看历史前 ${100 - d.prefs.min_hist_pct}%` : '未设门槛'}${d.opportunities_filtered > 0 ? `,滤掉 ${d.opportunities_filtered} 只` : ''})</h2>
  ${d.opportunities.length ? `<table>
    <thead><tr><th class="num">把握</th><th>名称</th><th>结论</th><th>走势</th><th>建议仓位</th></tr></thead>
    <tbody>${oppRows}</tbody>
  </table>
  <div class="meta" style="margin:6px 0 0">把握分 = √(质地 × 时机),先过四道硬门槛才打分;两条竖线依次是质地与时机的得分。质地 = 趋势模板八条 / 磨底节拍 / 相对强度 / 六态(以月计变化);时机 = 新鲜度 / 通道位置 / 量比 / 换手(逐日变化)。用几何平均是为了不让一边补另一边 —— 质地 95 时机 15 不该和两边都 55 打平。分数带 * 表示有因子缺数据,总分偏乐观。「走势」那一列是凭什么把这只挑出来:信号 + 六态 + 位置 + 量能 + 距关键点。位置与量能只说状态词 —— 要读懂 68% 和 1.82,得先知道多少算多。佐证(主线 / AI 信号 / 历史胜率 / 通道结论)在每行下面的小字里,一律不参与打分。</div>`
    : '<div class="empty">今日没有把握足够的买入机会 —— 等待比出手更常见</div>'}

  <p class="foot">牛来 · 六态趋势 + ATR 出场线 + 生命线(20日线) + 把握分 v3(四门槛 + 质地×时机) · 仅个人参考,不构成投资建议</p>
</div>
</body>
</html>
`
}

