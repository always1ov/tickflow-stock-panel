/**
 * [fork 增强] 今日总览 —— 决策汇聚层。
 *
 * 把六态趋势/AI 信号预案/持仓出场线/监控触发聚合成一屏, 版面顺序:
 * 市场天气(定基调) → 值得关注(买什么) → 需要行动(持仓风险) → 持仓体检。
 * 行动区与持仓体检相邻 —— 两者都是持仓管理, 连着看不用来回滚。
 * 数据全部来自既有模块,零新计算;AI 导读可选(手动点击,一次调用)。
 */
import { Fragment, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import {
  AlertTriangle, CheckCircle2, ChevronDown, Compass, Download, Layers, Loader2,
  RefreshCw, SlidersHorizontal, Sparkles, Sunrise, Target,
} from 'lucide-react'
import {
  api, TODAY_BOARDS, type KeltnerVerdict, type SignalAiSchedule, type TodayAiSchedule,
  type TodayOverview, type TodayPick, type TodayPrefs,
} from '@/lib/api'
import { toast } from '@/components/Toast'
import { PageShell } from '@/components/PageShell'
import { VerdictHover } from '@/components/stock-analysis/VerdictHover'
import { QK } from '@/lib/queryKeys'
import { cn } from '@/lib/cn'

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
  // [R43] 通道位置标: 到上沿用暖色(偏贵), 到下沿用冷色(低吸位置)
  // [R47] 导出件的通道结论标: 浅色排版单独一套配色
  const vStyle = (v: KeltnerVerdict) => ({
    sell: 'background:#fdecec;color:#c0392b',
    buy: 'background:#e6f4fb;color:#1c6ea4',
    hold: 'background:#fdf0e3;color:#c78326',
    avoid: 'background:#f0f1f3;color:#8a919f',
    watch: 'background:#f0f1f3;color:#5b6472',
  }[v.tone])
  const actionRows = d.actions.map(a => `
      <li><i style="background:${a.severity === 'high' ? bull : '#c78326'}"></i>
        <b>${esc(a.name)}</b>${sym(a.name, a.symbol)} ${esc(a.text)}</li>`).join('')
  const oppRows = d.opportunities.map(o => `
      <li><b class="score">${o.score}</b>
        <span><b>${esc(o.name)}</b>${sym(o.name, o.symbol)}${o.board ? ` <span class="adv" style="background:#eef1f5;color:#5b6472">${esc(o.board)}</span>` : ''}${o.mainline ? ` <span class="adv" style="background:#f4e6f7;color:#8b3fa0">主线${o.mainline.rank}·${esc(o.mainline.member)}</span>` : ''}${o.verdict ? ` <span class="adv" style="${vStyle(o.verdict)}">${esc(o.verdict.title)}</span>` : ''}${o.advice ? ` <span class="adv">${esc(o.advice.text)}</span>` : ''} ${esc(o.text)}
        <span class="why">${esc(o.why)}</span>${o.advice?.plan ? `<span class="why" style="color:#1c6ea4">建仓路径:${esc(o.advice.plan)}</span>` : ''}</span></li>`).join('')
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
  const genAt = new Date().toLocaleString('zh-CN')
  return `<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>今日总览 · ${esc(d.as_of ?? '')}</title>
<style>
  body{margin:0;padding:32px 24px;background:#f7f8fa;color:#1f2329;font:14px/1.6 -apple-system,'PingFang SC','Microsoft YaHei',sans-serif}
  .wrap{max-width:1000px;margin:0 auto}
  h1{font-size:20px;margin:0 0 4px}
  h2{font-size:14px;margin:22px 0 8px;display:flex;align-items:center;gap:6px}
  .meta{color:#8a919f;font-size:12px;margin-bottom:18px}
  .posture{display:inline-block;border-radius:999px;padding:2px 14px;font-weight:600;color:#fff}
  .weather{background:#fff;border:1px solid #e5e6eb;border-radius:8px;padding:12px 16px;display:flex;gap:14px;align-items:center;flex-wrap:wrap}
  .brief{background:#f3efff;border:1px solid #ddd0fa;border-radius:8px;padding:12px 16px;font-size:13px;margin-top:14px}
  ul.items{list-style:none;margin:0;padding:0;background:#fff;border:1px solid #e5e6eb;border-radius:8px}
  ul.items li{padding:9px 14px;border-bottom:1px solid #f0f1f3;font-size:13px;display:flex;gap:8px;align-items:baseline}
  ul.items li>span{min-width:0;flex:1}
  ul.items li:last-child{border-bottom:none}
  ul.items i{width:7px;height:7px;border-radius:50%;display:inline-block;flex:none;position:relative;top:-1px}
  .empty{background:#fff;border:1px solid #e5e6eb;border-radius:8px;padding:14px 16px;font-size:13px;color:#8a919f}
  table{width:100%;border-collapse:collapse;background:#fff;border:1px solid #e5e6eb;border-radius:8px;overflow:hidden}
  th{font-size:12px;font-weight:500;color:#8a919f;text-align:left;padding:8px 12px;border-bottom:1px solid #e5e6eb;background:#fafbfc;white-space:nowrap}
  td{padding:8px 12px;border-bottom:1px solid #f0f1f3;font-size:13px;white-space:nowrap}
  td.name{white-space:normal}
  tr:last-child td{border-bottom:none}
  .num{font-variant-numeric:tabular-nums;text-align:right}
  th.num,td.num{text-align:right}
  .sym{color:#a0a6b1;font-size:11px}
  .score{flex:none;background:#f0f1f3;color:#4e5666;border-radius:3px;padding:1px 5px;font-size:11px;font-variant-numeric:tabular-nums}
  .why{display:block;color:#8a919f;font-size:11px;margin-top:2px}
  .adv{background:#e8f3fb;color:#1c6ea4;border-radius:3px;padding:1px 5px;font-size:11px;white-space:nowrap;display:inline-block}
  .sym,.score{white-space:nowrap}
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
    ${d.weather.market ? `<span class="posture" style="background:${postureColor[d.weather.market.mode] ?? '#8a919f'};font-size:11px;padding:1px 10px">大盘${esc(d.weather.market.mode)}</span>` : ''}
    <span style="font-size:13px;color:#4e5666">${esc(d.weather.posture_reason)}</span>
    <span style="margin-left:auto;font-size:12px;color:#8a919f">涨势 <b style="color:${bull}">${d.weather.bull}</b> / 跌势 <b style="color:${bear}">${d.weather.bear}</b> · 刚转强 ${d.weather.new_bull} · 刚转弱 ${d.weather.new_bear}</span>
  </div>
  ${(() => {
    // [R37] 中观一行: 钱在往哪儿聚 —— 导出件里同样保留, 否则打印出来只剩大盘与个股两层
    const m = d.meso
    if (!m || !(m.amount || m.breadth || m.mainline)) return ''
    const parts: string[] = []
    if (m.amount) parts.push(`成交额 <b>${esc(m.amount.text)}</b>${m.amount.pct_rank != null ? ` (${(m.amount.pct_rank * 100).toFixed(0)}% 分位·${esc(m.amount.label ?? '')})` : ''}`)
    if (m.breadth) parts.push(`<b style="color:${bull}">${m.breadth.up}</b> 涨 / <b style="color:${bear}">${m.breadth.down}</b> 跌`)
    if (m.mainline) parts.push(`${m.mainline.stale ? '主线(已停更)' : '今日主线'} ${m.mainline.rows.slice(0, 3).map(x => `${esc(x.member)}(${x.limit_up_count})`).join('、')}`)
    return `<div class="meta" style="margin-top:-6px">中观 · ${parts.join(' · ')}</div>`
  })()}
  ${brief ? `<div class="brief">✦ ${esc(brief)}</div>` : ''}
  <h2>🎯 值得关注(${d.opportunities.length}·已按把握分筛选${d.opportunities_filtered > 0 ? `,滤掉 ${d.opportunities_filtered} 只` : ''})</h2>
  ${d.opportunities.length ? `<ul class="items">${oppRows}</ul>` : '<div class="empty">今日没有把握足够的买入机会 —— 等待比出手更常见</div>'}
  <h2>⚠️ 需要行动(${d.actions.length})</h2>
  ${d.actions.length ? `<ul class="items">${actionRows}</ul>` : '<div class="empty">今日无需操作 —— 管住手</div>'}
  <h2>💼 持仓体检(${d.holdings.length})${d.portfolio ? `<span style="font-weight:400;font-size:12px;color:#8a919f;margin-left:8px">组合:平均浮盈 ${d.portfolio.avg_pnl != null ? (d.portfolio.avg_pnl * 100).toFixed(1) + '%' : '—'} · 已触发 ${d.portfolio.triggered} · 逼近出场线 ${d.portfolio.near_exit} · 空头趋势 ${d.portfolio.bearish}${d.portfolio.total_weight != null ? ` · 总仓位 ${(d.portfolio.total_weight / 10).toFixed(1)}成${d.portfolio.drawdown != null ? ` · 距净值高点 -${(d.portfolio.drawdown * 100).toFixed(1)}%` : ''}` : ''}</span>` : ''}</h2>
  ${d.holdings.length ? `<table>
    <thead><tr><th>标的</th><th class="num">现价</th><th class="num">仓位</th><th class="num">浮盈</th><th class="num">出场线</th><th>阶段</th><th>趋势</th><th>操作建议</th></tr></thead>
    <tbody>${holdRows}</tbody>
  </table>` : '<div class="empty">暂无持仓标记</div>'}
  <p class="foot">牛来 · 六态趋势 + ATR 出场线 + 生命线(20日线) · 仅个人参考,不构成投资建议</p>
</div>
</body>
</html>
`
}

/** [R18] 时段感知: 盘前/盘中/盘后各自该怎么用这页(北京时间) */
function sessionPhaseHint(live: boolean | undefined): { label: string; hint: string } {
  const now = new Date()
  const bj = new Date(now.toLocaleString('en-US', { timeZone: 'Asia/Shanghai' }))
  const day = bj.getDay()
  const mins = bj.getHours() * 60 + bj.getMinutes()
  if (day === 0 || day === 6) {
    return { label: '休市', hint: '周末休市 —— 复盘与做下周计划的时间,数据为上一交易日定稿。' }
  }
  if (mins < 9 * 60 + 30) {
    return {
      label: '盘前',
      hint: '计划时段:以昨收定稿数据定今天的计划 —— 该卖的(行动区)、该盯的(触发价+建仓路径)、买多少(建议仓位)。',
    }
  }
  if (mins < 15 * 60) {
    return live
      ? {
          label: '盘中',
          hint: '执行时段:按盘前计划执行到价预案;实时数字用来盯距离。盘中冒出的新信号只记录,等收盘确认再动手。',
        }
      : {
          label: '盘中',
          hint: '执行时段(实时行情未开):当前为昨收数据,打开左下角「实时行情」后可盘中盯距离。',
        }
  }
  if (mins < 20 * 60) {
    return {
      label: '盘后',
      hint: '日线一般 17:30~20:00 落盘;落盘后刷新,这里就是当日定稿 —— 纪律判定(生命线/出场线/六态)以定稿为准,顺手做明天的计划。',
    }
  }
  return { label: '盘后', hint: '当日数据应已定稿 —— 按定稿数据复盘,并做好明天的计划。' }
}

// [R40] 板块徽章。20cm 的两个板(创业/科创)与 30cm 的北交所用暖色标出来 ——
// 同一个把握分, 20cm 的票波动天然更大, 仓位不该一样。
// [R47] 机会区的通道结论标。与决策台「结论」列、导出件同一份数据 ——
// tone 由后端给, 界面不自己判, 三处不会各说各的。
const VERDICT_TAG_CLS: Record<KeltnerVerdict['tone'], string> = {
  sell: 'bg-red-400/20 text-red-300',
  buy: 'bg-sky-400/15 text-sky-300',
  hold: 'bg-amber-400/20 text-amber-300',
  avoid: 'bg-border/40 text-muted',
  watch: 'bg-border/40 text-muted',
}

/**
 * 三档通道结论标 —— 挂在机会区每条候选上。
 *
 * 这里的语气和持仓那侧相反: 同一个"到上沿", 持仓是止盈时机, 买入是追高。
 * 所以徽标只放结论标题, 具体怎么解读由悬停里那句话说清。
 */
function VerdictTag({ v, holding }: { v?: KeltnerVerdict | null; holding?: boolean }) {
  if (!v) return null
  // [R49] 原生 title 换成分段排版的悬停卡片。note 这句两侧不一样, 所以由调用方给 ——
  // 同一个"到上沿", 持仓侧是止盈时机, 买入候选侧是追高, 写死在 verdict 里对不上两边。
  return (
    <VerdictHover
      v={v}
      note={holding
        ? '你正持有它 —— 到上沿是止盈时机, 到下沿才谈加仓。'
        : '这是买入候选 —— 通道位置影响的是"这一笔值不值"。与持仓侧相反: 持仓到上沿是止盈时机, 买入到上沿是追高。'}
    >
      <span className={`ml-1.5 cursor-help rounded px-1 py-0.5 text-[9px] ${VERDICT_TAG_CLS[v.tone]}`}>
        {v.title}
      </span>
    </VerdictHover>
  )
}

const BOARD_CLS: Record<string, string> = {
  沪主板: 'bg-border/40 text-muted',
  深主板: 'bg-border/40 text-muted',
  创业板: 'bg-orange-400/15 text-orange-300',
  科创板: 'bg-orange-400/15 text-orange-300',
  北交所: 'bg-rose-400/15 text-rose-300',
}
const BOARD_LIMIT_CN: Record<string, string> = {
  沪主板: '10%', 深主板: '10%', 创业板: '20%', 科创板: '20%', 北交所: '30%',
}

const POSTURE_STYLE: Record<string, string> = {
  进攻: 'border-red-400/40 bg-red-400/10 text-red-400',
  谨慎: 'border-amber-400/40 bg-amber-400/10 text-amber-300',
  防守: 'border-emerald-400/40 bg-emerald-400/10 text-emerald-400',
  观察: 'border-border bg-base text-muted',
}

// ===== [R122] 机会区表格 —— 15 张同质卡片 → 一行一只 =====
//
// 版式设计(先画后写, 见 FORK_NOTES R122):
//   ┌──┬──────────┬────────────────┬──────┬──────┬────────┬─┐
//   │分│ 名称/代码 │ 信号            │ 主线 │建议仓│ 结论标 │▸│
//   ├──┴──────────┴────────────────┴──────┴──────┴────────┴─┤
//   │  ▸ 展开: 规则依据 · 建仓路径(金字塔三步)                │
//   └────────────────────────────────────────────────────────┘
//
// 为什么从卡片改表格: 旧版每只票 4~5 行, 其中"建仓路径:先试 0.5 成 → 站稳 X
// 3 日加至 1 成 → …"这句每张卡一模一样, 15 只就是 15 遍模板文字, 眼睛扫不动,
// 真正有区分度的信息(把握分、量比、距关键点)反而埋在长句里。表格把可比字段
// 对齐成列, 模板文字收进展开行 —— 要看细节点开就是, 不看不占地方。
//
// 把握分保留数字, 但补一条**分布条**: 顶上一串 100/100/97/95 光看数字没有区
// 分度, 条形按今日候选里的相对位置画, 一眼看出"这只在今天算高还是算低"。
function ScoreCell({ score, rank, total }: { score: number; rank: number; total: number }) {
  const tone = score >= 80 ? 'bg-danger' : score >= 70 ? 'bg-warning' : 'bg-muted'
  return (
    <span
      className="inline-flex w-9 shrink-0 flex-col items-center gap-0.5"
      title={`把握分 ${score}(综合信号新鲜度与 AI 置信度) —— 今日候选里排第 ${rank}/${total}`}
    >
      <span className={`font-mono text-[10px] font-semibold ${
        score >= 80 ? 'text-danger' : score >= 70 ? 'text-warning' : 'text-muted'}`}>
        {score}
      </span>
      <span className="h-0.5 w-full overflow-hidden rounded-full bg-border/60">
        <span className={`block h-full rounded-full transition-all duration-enter ease-smooth ${tone}`}
              style={{ width: `${Math.max(6, Math.min(100, score))}%` }} />
      </span>
    </span>
  )
}

function OpportunityTable({ rows, pickedSymbols, onOpen }: {
  rows: TodayOverview['opportunities']
  pickedSymbols: Set<string>
  onOpen: (symbol: string, name: string) => void
}) {
  const [open, setOpen] = useState<string | null>(null)
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b border-border/40 text-[10px] text-muted">
            <th className="w-12 px-3 py-1.5 text-center font-normal">把握</th>
            <th className="px-2 py-1.5 text-left font-normal">名称</th>
            <th className="px-2 py-1.5 text-left font-normal">信号</th>
            <th className="hidden px-2 py-1.5 text-right font-normal md:table-cell"
                title="现价距触发价还差几个点。负数=已越过触发价">距触发</th>
            <th className="hidden px-2 py-1.5 text-right font-normal md:table-cell"
                title="量比 ——放量突破才是真金,缩量突破多半是假的">量比</th>
            <th className="hidden px-2 py-1.5 text-left font-normal lg:table-cell">主线</th>
            <th className="hidden px-2 py-1.5 text-right font-normal sm:table-cell">建议仓位</th>
            <th className="w-7 px-1 py-1.5" aria-label="展开" />
          </tr>
        </thead>
        <tbody>
          {rows.map((o, i) => {
            const picked = pickedSymbols.has(o.symbol)
            const expanded = open === o.symbol
            return (
              <Fragment key={o.symbol}>
                <tr
                  className={cn('group border-b border-border/25 transition-colors duration-hover',
                    picked ? 'bg-amber-400/[0.07]' : 'hover:bg-elevated/40')}
                >
                  <td className="px-3 py-2 text-center align-top">
                    <ScoreCell score={o.score} rank={i + 1} total={rows.length} />
                  </td>
                  <td className="px-2 py-2 align-top">
                    <button
                      onClick={() => onOpen(o.symbol, o.name)}
                      className="text-left font-medium text-foreground hover:text-accent hover:underline transition-colors duration-hover cursor-pointer"
                    >
                      {o.name}
                    </button>
                    <div className="mt-0.5 flex flex-wrap items-center gap-1">
                      <span className="font-mono text-[9px] text-muted">{o.symbol}</span>
                      {o.board && (
                        <span title={`${o.board} —— 涨跌停幅度 ${BOARD_LIMIT_CN[o.board] ?? '10%'}`}
                              className={`rounded px-1 py-0.5 text-[9px] ${BOARD_CLS[o.board] ?? 'bg-border/40 text-muted'}`}>
                          {o.board}
                        </span>
                      )}
                      {picked && <span className="text-[9px] text-amber-300">★ AI 优选</span>}
                    </div>
                  </td>
                  <td className="px-2 py-2 align-top text-foreground/85">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <span>{o.text}</span>
                      <VerdictTag v={o.verdict} />
                      {o.intraday && (
                        <span title="这个信号由盘中实时价触发,收盘可能收回去 —— 只记录观察,收盘确认后再动手"
                              className="rounded bg-amber-400/15 px-1 py-0.5 text-[9px] text-amber-300">
                          盘中·待收盘确认
                        </span>
                      )}
                    </div>
                  </td>
                  {/* [R123] 这两列是今天唯二决定"动不动手"的数字: 距触发回答
                      "能不能动", 量比回答"这个突破是不是真的" */}
                  <td className="hidden whitespace-nowrap px-2 py-2 text-right align-top font-mono md:table-cell">
                    {o.gap_pct == null ? <span className="text-[10px] text-muted/50">—</span> : (
                      <span className={o.gap_pct <= 0 ? 'text-danger'
                        : o.gap_pct <= 1.5 ? 'text-warning' : 'text-secondary'}
                        title={o.gap_pct <= 0 ? '已越过触发价' : `还差 ${o.gap_pct}% 到触发价`}>
                        {o.gap_pct > 0 ? '+' : ''}{o.gap_pct}%
                      </span>
                    )}
                  </td>
                  <td className="hidden whitespace-nowrap px-2 py-2 text-right align-top font-mono md:table-cell">
                    {o.vol_ratio == null ? <span className="text-[10px] text-muted/50">—</span> : (
                      <span className={o.vol_ratio >= 1.5 ? 'text-danger'
                        : o.vol_ratio < 0.8 ? 'text-success' : 'text-secondary'}
                        title={o.vol_ratio >= 1.5 ? '放量' : o.vol_ratio < 0.8 ? '缩量,假突破风险' : ''}>
                        {o.vol_ratio.toFixed(2)}
                      </span>
                    )}
                  </td>
                  <td className="hidden px-2 py-2 align-top lg:table-cell">
                    {o.mainline ? (
                      <span
                        title={
                          `今日第 ${o.mainline.rank} 主线「${o.mainline.member}」,该概念今日 ${o.mainline.limit_up_count} 家涨停` +
                          (o.mainline.also.length ? `;同时还属于 ${o.mainline.also.join('、')}` : '') +
                          ' —— 板块效应是佐证不是理由:量价不扎实的票在第一主线里也不该买。没有这个标只说明它单打独斗,不扣分'
                        }
                        className="whitespace-nowrap rounded bg-fuchsia-400/15 px-1.5 py-0.5 text-[9px] text-fuchsia-300"
                      >
                        主线{o.mainline.rank}·{o.mainline.member}
                      </span>
                    ) : <span className="text-[10px] text-muted/50">—</span>}
                  </td>
                  <td className="hidden whitespace-nowrap px-2 py-2 text-right align-top sm:table-cell">
                    {o.advice ? (
                      <span title={`${o.advice.why} —— 仅供参考的上限建议, 不是操作指令`}
                            className="rounded bg-sky-400/15 px-1.5 py-0.5 text-[9px] text-sky-300">
                        {o.advice.text}
                      </span>
                    ) : <span className="text-[10px] text-muted/50">—</span>}
                  </td>
                  <td className="px-1 py-2 align-top">
                    <button
                      onClick={() => setOpen(expanded ? null : o.symbol)}
                      aria-expanded={expanded}
                      aria-label={expanded ? '收起细节' : '展开细节'}
                      className="rounded p-1 text-muted transition-colors duration-hover hover:bg-elevated hover:text-foreground"
                    >
                      <ChevronDown className={cn('h-3.5 w-3.5 transition-transform duration-expand ease-smooth',
                        expanded && 'rotate-180')} />
                    </button>
                  </td>
                </tr>
                {expanded && (
                  <tr className="border-b border-border/25 bg-base/40">
                    <td colSpan={8} className="px-4 py-2.5">
                      <div className="animate-rise-in space-y-1 text-[11px] leading-5">
                        <div className="text-muted">{o.why}</div>
                        {o.advice?.plan && (
                          <div className="text-sky-300/90"
                               title="金字塔建仓:每一步由价格确认驱动;假突破最多损失一个试仓(比例可在「门槛」面板调)">
                            建仓路径:{o.advice.plan}
                          </div>
                        )}
                      </div>
                    </td>
                  </tr>
                )}
              </Fragment>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

// ===== [R121] AI 优选面板 —— 把「凭什么信它」摆到台面上 =====
//
// 旧版这里只有一行字: 名字 + 理由。理由里那些数字(涨 7.2%、量比 1.25、守住
// 2372)看着很具体, 但**没有任何东西检查它们是不是真的** —— 模型把量比 0.87
// 写成 1.25、把关键位编到一个该股从没到过的价位, 界面照样原样展示, 而用户会
// 照着这个数去挂单。新版补上两样东西, 都直接摆在优选旁边:
//   1. **逐条数字对账**: 后端拿送审时喂给 AI 的那份日K 核对理由里的每个数字,
//      对不上标存疑、价位离谱直接驳回(驳回的不当推荐展示, 折到最下面)
//   2. **历史命中率**: 过往优选 T+1/T+3/T+5 的胜率与平均收益 —— 靠不靠谱,
//      最后只能用记录说话。带口径说明, 不说清口径的胜率就是误导。
const VERDICT_STYLE: Record<string, { cls: string; label: string }> = {
  已核对: { cls: 'bg-emerald-400/15 text-emerald-300 border-emerald-400/30', label: '✓ 数字已核对' },
  待查:   { cls: 'bg-border/40 text-muted border-border', label: '理由无数字可核' },
  存疑:   { cls: 'bg-amber-400/15 text-amber-300 border-amber-400/30', label: '⚠ 存疑' },
  驳回:   { cls: 'bg-danger/15 text-danger border-danger/30', label: '✕ 已驳回' },
}

function CheckRow({ c }: { c: NonNullable<TodayPick['checks']>[number] }) {
  const actual = Array.isArray(c.actual) ? `${c.actual[0]}~${c.actual[1]}` : c.actual
  return (
    <li className="flex items-baseline gap-1.5 font-mono text-[10px]">
      <span className={c.ok === true ? 'text-emerald-400' : c.ok === false ? 'text-danger' : 'text-muted'}>
        {c.ok === true ? '✓' : c.ok === false ? '✕' : '?'}
      </span>
      <span className="text-muted">{c.kind}</span>
      <span className="text-foreground/80">AI 说 {c.said}</span>
      {actual !== null && actual !== undefined && (
        <span className={c.ok === false ? 'text-danger' : 'text-muted'}>· 实际 {actual}</span>
      )}
    </li>
  )
}

function TrackRecordBar() {
  const q = useQuery({
    queryKey: QK.todayAiTrackRecord,
    queryFn: api.todayAiTrackRecord,
    staleTime: 10 * 60 * 1000,
  })
  const s = q.data?.stats
  if (!s || (s.t1.n === 0 && s.t3.n === 0 && s.t5.n === 0)) {
    return (
      <span className="text-[10px] text-muted">
        历史命中率:样本还不够(已记录 {q.data?.recorded_days ?? 0} 天,每天优选后自动累计)
      </span>
    )
  }
  const cell = (k: 't1' | 't3' | 't5', label: string) => {
    const v = s[k]
    if (!v.n) return null
    const good = (v.win_rate ?? 0) >= 50
    return (
      <span key={k} className="whitespace-nowrap">
        <span className="text-muted">{label} </span>
        <span className={good ? 'text-danger' : 'text-success'}>
          {v.win_rate}% 胜 / 均 {(v.avg ?? 0) > 0 ? '+' : ''}{v.avg}%
        </span>
        <span className="text-muted/70"> ({v.n})</span>
      </span>
    )
  }
  return (
    <span className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5 text-[10px]"
          title={q.data?.caveat}>
      <span className="text-muted">历史命中率</span>
      {(['t1', 't3', 't5'] as const).map((k, i) => cell(k, ['T+1', 'T+3', 'T+5'][i]))}
      <span className="text-muted/60">· 收盘价口径,未计滑点</span>
    </span>
  )
}

function AiPickPanel({ picks, analyzed, opportunities, onOpen }: {
  picks: TodayPick[]
  analyzed: number
  opportunities: TodayOverview['opportunities']
  onOpen: (symbol: string, name: string) => void
}) {
  const [openChecks, setOpenChecks] = useState<string | null>(null)
  // 驳回的不当推荐展示 —— 一条编造价位的建议, 比没有建议更糟
  const shown = picks.filter(p => p.verdict !== '驳回')
  const rejected = picks.filter(p => p.verdict === '驳回')

  return (
    <div className="border-b border-amber-400/20 bg-amber-400/[0.06] px-4 py-2.5 text-xs">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <span className="text-[10px] font-medium text-amber-300">
          AI 优选 {shown.length} 只
          <span className="ml-1.5 font-normal text-muted">· 已对比 {analyzed} 只的日 K 与量能后选出</span>
        </span>
        <TrackRecordBar />
      </div>

      {shown.length === 0 && rejected.length === 0 ? (
        <div className="mt-1.5 text-muted">
          AI 逐一看过这 {analyzed} 只的量价后,认为都不够理想 —— 空仓等待也是决策
        </div>
      ) : (
        <ul className="mt-1.5 space-y-1.5">
          {shown.map((p, i) => {
            const o = opportunities.find((x) => x.symbol === p.symbol)
            const style = VERDICT_STYLE[p.verdict ?? '待查'] ?? VERDICT_STYLE.待查
            const open = openChecks === p.symbol
            return (
              // [R122] 入场: 320ms 上移淡入, 逐条错开 60ms —— AI 跑完后结果是
              // "长出来"的, 不是突然闪现; 只给优选卡, 表格行不做(每次刷新都动会闹)
              <li key={p.symbol}
                  style={{ animationDelay: `${i * 60}ms` }}
                  className="animate-rise-in rounded border border-border/40 bg-base/40 px-2.5 py-1.5">
                <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
                  <button
                    onClick={() => onOpen(p.symbol, o?.name ?? p.name ?? p.symbol)}
                    className="font-medium text-foreground hover:underline cursor-pointer"
                  >
                    {o?.name ?? p.name ?? p.symbol}
                  </button>
                  <span className={`rounded border px-1.5 py-0.5 text-[9px] ${style.cls}`}
                        title={p.verdict_note || undefined}>
                    {style.label}
                  </span>
                  {!!p.checks?.length && (
                    <button
                      onClick={() => setOpenChecks(open ? null : p.symbol)}
                      className="text-[9px] text-muted hover:text-foreground"
                    >
                      {open ? '收起对账' : `对账 ${p.checks.length} 项`}
                    </button>
                  )}
                </div>
                <div className="mt-0.5 text-foreground/80">{p.reason}</div>
                {p.verdict === '存疑' && p.verdict_note && (
                  <div className="mt-1 text-[10px] text-amber-300/90">{p.verdict_note}</div>
                )}
                {open && p.checks && (
                  <ul className="mt-1.5 space-y-0.5 border-t border-border/40 pt-1.5">
                    {p.checks.map((c, i) => <CheckRow key={i} c={c} />)}
                  </ul>
                )}
              </li>
            )
          })}
        </ul>
      )}

      {rejected.length > 0 && (
        <div className="mt-2 rounded border border-danger/25 bg-danger/[0.05] px-2.5 py-1.5">
          <div className="text-[10px] font-medium text-danger">
            {rejected.length} 条被驳回,没有当作推荐
          </div>
          <ul className="mt-1 space-y-0.5">
            {rejected.map((p) => (
              <li key={p.symbol} className="text-[10px] leading-5 text-muted">
                <span className="text-foreground/70">{p.name || p.symbol}</span>
                <span className="mx-1">·</span>
                <span className="line-through">{p.reason}</span>
                <div className="text-danger/80">{p.verdict_note}</div>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

export function Today() {
  const qc = useQueryClient()
  const navigate = useNavigate()
  const q = useQuery({
    queryKey: QK.todayOverview,
    queryFn: () => api.todayOverview(),
    staleTime: 60_000,
    // [R27] 每小时自动刷新一次: 盘后数据落盘/定时 AI 跑完后不必手点
    refetchInterval: 60 * 60 * 1000,
    refetchOnWindowFocus: true,
  })
  // AI 导读+优选合一: 一次调用同时产出导读正文与量价优选结果。
  // [R27] 结果已落盘, 页面进来先显示缓存(state 为 null 时回落到 q.data.ai),
  // 刷新/次日进来不再空白, 定时任务的产出也能直接看到。
  const [brief, setBrief] = useState<string | null>(null)
  const [picks, setPicks] = useState<TodayPick[] | null>(null)
  const [analyzed, setAnalyzed] = useState(0)
  // 失败必须在页面上留痕(toast 一闪即逝, 用户会以为"点了没反应")
  const [aiError, setAiError] = useState<string | null>(null)
  const aiMut = useMutation({
    mutationFn: () => api.todayAi(),
    onMutate: () => setAiError(null),
    onSuccess: (r) => {
      if (r.error) { setAiError(r.error); toast(r.error, 'error'); return }
      setBrief(r.brief || null)
      setPicks(r.picks ?? [])
      setAnalyzed(r.analyzed ?? 0)
      // [R121] 刚落了一条台账 → 命中率重取(样本数会变)
      qc.invalidateQueries({ queryKey: QK.todayAiTrackRecord })
      const v = r.verify
      if (v?.rejected) toast(`AI 优选有 ${v.rejected} 条数字对不上日K, 已驳回`, 'error')
      else if (v?.doubtful) toast(`AI 优选有 ${v.doubtful} 条存疑, 已标出`, 'error')
    },
    onError: (e: Error) => {
      setAiError(`AI 分析失败: ${e.message}`)
      toast(`AI 分析失败: ${e.message}`, 'error')
    },
  })
  // [R27] AI 定时配置(门槛面板内)
  const todayAiSched = useQuery({
    queryKey: QK.todayAiSchedule,
    queryFn: () => api.todayAiScheduleGet(),
    staleTime: 5 * 60_000,
  })
  const signalAiSched = useQuery({
    queryKey: QK.signalAiSchedule,
    queryFn: () => api.signalAiScheduleGet(),
    staleTime: 5 * 60_000,
  })
  const todayAiSchedMut = useMutation({
    mutationFn: (body: TodayAiSchedule) => api.todayAiScheduleSet(body),
    onSuccess: (r) => {
      todayAiSched.refetch()
      toast(r.enabled
        ? `定时导读·优选已开启:工作日 ${String(r.hour).padStart(2, '0')}:${String(r.minute).padStart(2, '0')}`
        : '定时导读·优选已关闭', 'success')
    },
    onError: (e: Error) => toast(e.message, 'error'),
  })
  const signalAiSchedMut = useMutation({
    mutationFn: (body: SignalAiSchedule) => api.signalAiScheduleSet(body),
    onSuccess: (r) => {
      signalAiSched.refetch()
      toast(r.enabled
        ? `定时个股信号已开启:工作日 ${String(r.hour).padStart(2, '0')}:${String(r.minute).padStart(2, '0')} · ${r.scope === 'held' ? '只跑持有' : '全部自选'} · 间隔 ${r.gap_seconds}秒`
        : '定时个股信号已关闭', 'success')
    },
    onError: (e: Error) => toast(e.message, 'error'),
  })

  const [prefsOpen, setPrefsOpen] = useState(false)
  // 滑块拖动中的即时值(null = 用服务端返回的偏好); 松手才落库
  const [minScore, setMinScore] = useState<number | null>(null)
  const prefsMut = useMutation({
    mutationFn: (body: Partial<TodayPrefs>) => api.todaySavePrefs(body),
    onSuccess: (p, vars) => {
      toast(
        'boards' in vars
          ? (p.boards.length ? `只看:${p.boards.join('、')}` : '板块过滤已取消,全部板块都看')
          : `门槛已保存:把握分 ≥ ${p.min_score},最多 ${p.max_show} 条`,
        'success')
      setMinScore(null)
      setPicks(null)  // 候选集变了, 旧的 AI 优选结果不再对应
      q.refetch()
    },
    onError: (e: Error) => {
      toast(`保存失败: ${e.message}`, 'error')
      setMinScore(null)
    },
  })

  // [R19] 确定性刷新: 先全量拉一遍自选实时(轮转覆盖到每一只), 再刷新总览
  const refreshMut = useMutation({
    mutationFn: async () => {
      let live: Awaited<ReturnType<typeof api.intradayRefreshFull>> | null = null
      try {
        live = await api.intradayRefreshFull()
      } catch { /* 实时服务不可用(未开实时/未配 key)→ 只刷收盘数据 */ }
      await q.refetch()
      return live
    },
    onSuccess: (live) => {
      if (live?.live_count) {
        toast(
          live.full_coverage === false
            ? `实时已拉取 ${live.live_count} 只(额度有限未全覆盖,其余轮转中)`
            : `实时已全量同步 ${live.live_count} 只`,
          'success',
        )
      }
    },
  })

  const goStock = (symbol: string, name: string) =>
    navigate(`/stock-analysis?symbol=${encodeURIComponent(symbol)}&name=${encodeURIComponent(name)}`)

  const d = q.data
  // 本次会话生成过就用 state, 否则用服务端缓存(手动/定时生成的都在里面)
  const aiCache = d?.ai ?? null
  const shownBrief = brief ?? aiCache?.brief ?? null
  const shownPicks = picks ?? aiCache?.picks ?? null
  // [R40] 板块过滤当前值。空 = 全看; 由服务端偏好驱动, 刷新/换设备都保持
  const boardFilter = d?.prefs?.boards ?? []
  const shownAnalyzed = picks ? analyzed : (aiCache?.analyzed ?? 0)
  const aiMeta = brief ? null : aiCache   // 缓存来源与时间(自己刚生成的不必标注)
  // [R37] 中观快照。提出来是为了在 JSX 的 map 回调里也保住类型收窄
  const meso = d?.meso ?? null
  const mainline = meso?.mainline ?? null

  // [R60] 页头交给 PageShell —— 这一页原来手搓了一个 h1 + 自己的 1500px 限宽,
  // 于是它和别的页在同一块屏幕上的边界、留白、标题字号都对不上。
  const asOfLine = d?.as_of ? (
    <>
      数据截至 {d.as_of} · 自选 {d.watchlist_total} 只(其中 {d.trend_total} 只有趋势判定)
      {d.live ? (
        <span
          className="ml-1.5 text-emerald-400"
          title={`实时叠加层已覆盖 ${d.live_count} 只自选;六态/距离为盘中临时口径,纪律判定(生命线/出场线触发)仍以收盘为准`}
        >
          ● 实时中({d.live_count} 只)
        </span>
      ) : (
        <span className="ml-1.5 text-amber-300/80" title="当前为上一交易日收盘数据">
          收盘口径 —— 打开左下角「实时行情」开关后,盘中这里就是实时数据
        </span>
      )}
    </>
  ) : undefined

  return (
    <PageShell
      title="今日总览"
      titleExtra={<Sunrise className="h-4 w-4 text-amber-300" />}
      subtitle={asOfLine}
      right={(
        <div className="flex items-center gap-2">
          <button
            onClick={() => {
              if (!d) return
              const html = buildTodayHtml(d, shownBrief)
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
            className="inline-flex items-center gap-1 rounded-btn border border-sky-400/30 bg-sky-400/10 px-2.5 py-1 text-[10px] text-sky-300 hover:bg-sky-400/20 disabled:opacity-50 transition-colors cursor-pointer"
          >
            <Download className="h-3 w-3" />
            导出 HTML
          </button>
          <button
            onClick={() => aiMut.mutate()}
            disabled={aiMut.isPending || !d}
            title="一次生成盘前导读, 并调取候选的日 K 与量能做横向对比选出 1-3 只(耗时约十几秒)"
            className="inline-flex items-center gap-1 rounded-btn border border-violet-400/30 bg-violet-400/10 px-2.5 py-1 text-[10px] text-violet-300 hover:bg-violet-400/20 disabled:opacity-50 transition-colors cursor-pointer"
          >
            {aiMut.isPending ? <Loader2 className="h-3 w-3 animate-spin" /> : <Sparkles className="h-3 w-3" />}
            AI 导读·优选
          </button>
          <button
            onClick={() => refreshMut.mutate()}
            disabled={refreshMut.isPending || q.isFetching}
            title="先把全部自选的实时行情立即拉一遍(轮转全覆盖),再刷新本页 —— 实时行情未开启时仅刷新收盘数据"
            className="inline-flex items-center gap-1 rounded-btn border border-border bg-base px-2.5 py-1 text-[10px] text-muted hover:text-foreground disabled:opacity-50 transition-colors cursor-pointer"
          >
            <RefreshCw className={`h-3 w-3 ${(refreshMut.isPending || q.isFetching) ? 'animate-spin' : ''}`} />
            {refreshMut.isPending ? '同步中…' : '刷新'}
          </button>
        </div>
      )}
    >
      {/* [R122] 时段提示条并入下方「市场天气」横幅 —— 三条通栏横幅(时段/天气/中观)
          在首屏堆掉近三分之一高度, 而时段只是一句"现在该怎么用这页"的说明,
          不值得独占一条。现在它是天气条右上角的一个徽章, 悬停看全文。 */}

      {aiError && (
        <div className="flex items-start justify-between gap-3 rounded-lg border border-red-400/30 bg-red-400/[0.07] px-4 py-3 text-xs text-red-300">
          <span>AI 导读·优选没有成功:{aiError}</span>
          <button
            onClick={() => aiMut.mutate()}
            disabled={aiMut.isPending}
            className="shrink-0 rounded border border-red-400/40 px-2 py-0.5 text-[10px] hover:bg-red-400/10 disabled:opacity-50 cursor-pointer"
          >
            重试
          </button>
        </div>
      )}
      {shownBrief && (
        <div className="rounded-lg border border-violet-400/20 bg-violet-400/[0.06] px-4 py-3 text-xs leading-relaxed text-foreground/90">
          <Sparkles className="mr-1.5 inline h-3.5 w-3.5 text-violet-300" />
          {shownBrief}
          {aiMeta && (
            <span
              className="ml-2 whitespace-nowrap text-[10px] text-muted"
              title={`生成于 ${new Date(aiMeta.created_at).toLocaleString('zh-CN')}${aiMeta.as_of ? ` · 基于 ${aiMeta.as_of} 数据` : ''}`}
            >
              ({aiMeta.source === 'scheduled' ? '定时生成' : '上次生成'}
              {aiMeta.as_of && aiMeta.as_of !== d?.as_of ? ' · 数据已更新,建议重新生成' : ''})
            </span>
          )}
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
          {/* ③ 市场天气(最上面一条横幅, 定基调) —— 左侧徽章+理由, 右侧统计定宽对齐,
              避免理由长短不一时统计块被挤得忽上忽下 */}
          <div className="flex items-start gap-4 rounded-lg border border-border/60 bg-surface/40 px-4 py-3">
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <Compass className="h-4 w-4 shrink-0 text-sky-400" />
                <span className={`inline-flex rounded-btn border px-3 py-0.5 text-sm font-medium ${POSTURE_STYLE[d.weather.posture] ?? POSTURE_STYLE['观察']}`}>
                  {d.weather.posture}
                </span>
                {/* [R122] 时段徽章(原独立横幅): 标签常显, 用法说明收进 title */}
                {(() => {
                  const phase = sessionPhaseHint(d.live)
                  return (
                    <span title={phase.hint}
                          className="rounded border border-border/60 bg-elevated/50 px-1.5 py-0.5 text-[10px] font-medium text-secondary">
                      {phase.label}
                    </span>
                  )
                })()}
                {d.weather.market && (
                  <span
                    title={
                      `基准 ${d.weather.market.benchmark_name ?? '—'}(${d.weather.market.as_of ?? '—'})` +
                      (d.weather.market.metrics.close != null
                        ? ` · 收盘 ${d.weather.market.metrics.close} / 50日线 ${d.weather.market.metrics.ma50} / 年线 ${d.weather.market.metrics.ma200} / 年动量 ${((d.weather.market.metrics.momentum_12m ?? 0) * 100).toFixed(1)}%`
                        : '') +
                      ` —— 最终姿态取大盘与自选中更保守的一方`
                    }
                    className={`inline-flex items-center gap-1 rounded-btn border px-2 py-0.5 text-[10px] ${POSTURE_STYLE[d.weather.market.mode] ?? POSTURE_STYLE['观察']}`}
                  >
                    {d.weather.market.benchmark_name ?? '大盘'}·{d.weather.market.mode}
                    {d.weather.market.pending && <span className="opacity-70">(将转{d.weather.market.pending.mode} {d.weather.market.pending.streak}/{d.weather.market.pending.need})</span>}
                  </span>
                )}
              </div>
              <p className="mt-1.5 text-xs leading-relaxed text-muted">{d.weather.posture_reason}</p>
            </div>
            <div className="shrink-0 space-y-0.5 text-right font-mono text-[11px] text-muted">
              <div title="自选中处于涨势/跌势的只数">
                涨势 <span className="font-semibold text-red-400">{d.weather.bull}</span>
                <span className="mx-1 text-muted/40">/</span>
                跌势 <span className="font-semibold text-emerald-400">{d.weather.bear}</span>
              </div>
              <div title="今天新转强/新转弱的只数">
                刚转强 {d.weather.new_bull} · 刚转弱 {d.weather.new_bear}
              </div>
            </div>
          </div>

          {/* [R37] 中观快照 —— 三层推导 大盘 → 主线 → 个股 里缺的那一层。
              上面那条横幅是"大盘"层, 下面机会区是"个股"层, 这一条回答
              "今天的钱在往哪儿聚" */}
          {meso && (meso.amount || meso.breadth || mainline) && (
            <div className="flex flex-wrap items-center gap-x-5 gap-y-1.5 rounded-lg border border-border/60 bg-surface/40 px-4 py-2 text-[11px]">
              <span className="flex shrink-0 items-center gap-1.5 text-muted">
                <Layers className="h-3.5 w-3.5 text-fuchsia-400" />
                中观
              </span>
              {meso.amount && (
                <span
                  title={
                    `两市成交额 ${meso.amount.text}${meso.amount.date ? `(${meso.amount.date})` : ''}` +
                    (meso.amount.pct_rank != null
                      ? ` —— 在最近 ${meso.amount.sample} 个交易日里排在 ${(meso.amount.pct_rank * 100).toFixed(0)}% 分位`
                      : ` —— 历史样本只有 ${meso.amount.sample} 天, 不足以给出分位`)
                  }
                  className="font-mono text-muted"
                >
                  成交额 <span className="font-semibold text-foreground">{meso.amount.text}</span>
                  {meso.amount.pct_rank != null && (
                    <span className="ml-1 text-muted/80">
                      {(meso.amount.pct_rank * 100).toFixed(0)}% 分位 · {meso.amount.label}
                    </span>
                  )}
                </span>
              )}
              {meso.breadth && (
                <span title={`全市场涨跌家数(${meso.breadth.date})`} className="font-mono text-muted">
                  <span className="font-semibold text-red-400">{meso.breadth.up}</span> 涨
                  <span className="mx-1 text-muted/40">/</span>
                  <span className="font-semibold text-emerald-400">{meso.breadth.down}</span> 跌
                </span>
              )}
              {mainline && (
                <span className="flex min-w-0 flex-wrap items-center gap-1.5">
                  <span className="shrink-0 text-muted">
                    {mainline.stale ? '主线(数据已停更)' : '今日主线'}
                  </span>
                  {mainline.rows.slice(0, 3).map((m) => (
                    <span
                      key={m.member}
                      title={`第 ${m.rank} 名 · ${m.limit_up_count} 家涨停 · 最高 ${m.max_boards} 连板${m.leader_symbol ? ` · 龙头 ${m.leader_symbol}` : ''}`}
                      className={`shrink-0 rounded px-1.5 py-0.5 ${
                        mainline.stale ? 'bg-border/40 text-muted' : 'bg-fuchsia-400/15 text-fuchsia-300'
                      }`}
                    >
                      {m.member}
                      <span className="ml-1 font-mono opacity-70">{m.limit_up_count} 家涨停</span>
                    </span>
                  ))}
                  <span
                    title={
                      (mainline.stale
                        ? `主线数据停在 ${mainline.date},已经 ${mainline.age_days} 天没更新 —— 只作展示, 不参与机会区打分。到「数据」页重跑一次涨停梯队相关批次即可恢复。`
                        : `按 ${mainline.date} 的涨停梯队聚合:同一概念内涨停家数多、最高连板高、梯队不断层的排在前面。`) +
                      ` ${meso.membership_note}`
                    }
                    className="shrink-0 cursor-help text-muted/50"
                  >
                    ⓘ
                  </span>
                </span>
              )}
            </div>
          )}


          {/* ② 机会区(已按把握分筛选排序; AI 优选可再精选) */}
          <section className="rounded-lg border border-border/60 bg-surface/40 overflow-hidden">
            <div className="flex flex-wrap items-center gap-2 border-b border-border/40 px-4 py-2.5">
              <Target className="h-4 w-4 text-red-400" />
              <span className="text-sm font-medium text-foreground">值得关注</span>
              <span
                title={d.live
                  ? '现价与距触发价按盘中最新价计算;带「盘中·待收盘确认」标的信号等收盘定稿'
                  : `所有现价/距离为 ${d.as_of ?? '上一交易日'} 收盘快照 —— 打开左下角「实时行情」后自动实时`}
                className={`rounded border px-1.5 py-0.5 text-[9px] ${d.live ? 'border-emerald-400/30 bg-emerald-400/10 text-emerald-400' : 'border-amber-400/30 bg-amber-400/10 text-amber-300'}`}
              >
                {d.live ? '实时口径' : `昨收快照 ${d.as_of ?? ''}`}
              </span>
              <span className="text-[10px] text-muted">
                {d.opportunities.length} 项 · 把握分 ≥ {d.prefs.min_score} 才显示
                {d.opportunities_filtered > 0 && `(已滤掉 ${d.opportunities_filtered} 只)`}
                {boardFilter.length > 0 && (
                  <span
                    className="text-sky-300"
                    title="板块过滤在服务端于截断前生效 —— 显示的是该板块内把握分最高的前几只, 不是从已截断的列表里再挑"
                  >
                    {' '}· 只看 {boardFilter.join('、')}
                  </span>
                )}
                {d.position_hint && (
                  <span title="由当前姿态决定的总仓位建议上限(进攻8成/谨慎5成/防守2成/观察3成)——所有持仓加起来别超过这个数">
                    {' '}· 总仓位基调 ≤{d.position_hint.posture_cap * 10}成
                  </span>
                )}
              </span>
              {/* [R40] 板块筛选。过滤在后端做 —— 前端筛的话会漏掉被 max_show 截掉的票,
                  看到的"主板机会"是残缺的而你不会知道 */}
              <div className="flex items-center gap-1">
                <button
                  onClick={() => prefsMut.mutate({ boards: [] })}
                  disabled={prefsMut.isPending}
                  title="不过滤, 所有板块都看"
                  className={`rounded-btn border px-2 py-0.5 text-[10px] transition-colors cursor-pointer disabled:opacity-50 ${
                    boardFilter.length === 0
                      ? 'border-sky-400/40 bg-sky-400/15 text-sky-300'
                      : 'border-border bg-base text-muted hover:text-foreground'
                  }`}
                >
                  全部
                </button>
                {TODAY_BOARDS.map((b) => {
                  const on = boardFilter.includes(b)
                  return (
                    <button
                      key={b}
                      onClick={() => prefsMut.mutate({
                        boards: on ? boardFilter.filter((x) => x !== b) : [...boardFilter, b],
                      })}
                      disabled={prefsMut.isPending}
                      title={`${on ? '取消' : '只看'}${b}(可多选)`}
                      className={`rounded-btn border px-2 py-0.5 text-[10px] transition-colors cursor-pointer disabled:opacity-50 ${
                        on
                          ? 'border-sky-400/40 bg-sky-400/15 text-sky-300'
                          : 'border-border bg-base text-muted hover:text-foreground'
                      }`}
                    >
                      {b}
                    </button>
                  )
                })}
              </div>
              <div className="ml-auto flex items-center gap-2">
                <button
                  onClick={() => setPrefsOpen((v) => !v)}
                  title="调整显示门槛(把握分下限与最多显示条数)"
                  className={`inline-flex items-center gap-1 rounded-btn border px-2.5 py-1 text-[10px] transition-colors cursor-pointer ${
                    prefsOpen ? 'border-sky-400/40 bg-sky-400/15 text-sky-300'
                      : 'border-border bg-base text-muted hover:text-foreground'
                  }`}
                >
                  <SlidersHorizontal className="h-3 w-3" />
                  门槛
                </button>
              </div>
            </div>
            {prefsOpen && (
              <div className="flex flex-wrap items-center gap-x-5 gap-y-3 border-b border-border/40 bg-base/40 px-4 py-3">
                <label className="flex items-center gap-2 text-[11px] text-muted">
                  <span className="whitespace-nowrap">最低把握分</span>
                  <input
                    type="range" min={0} max={100} step={5}
                    value={minScore ?? d.prefs.min_score}
                    onChange={(e) => setMinScore(Number(e.target.value))}
                    onPointerUp={() => {
                      if (minScore != null && minScore !== d.prefs.min_score) prefsMut.mutate({ min_score: minScore })
                    }}
                    className="w-36 accent-sky-400 cursor-pointer"
                  />
                  <span className="w-6 font-mono text-foreground">{minScore ?? d.prefs.min_score}</span>
                </label>
                <label className="flex items-center gap-2 text-[11px] text-muted">
                  <span className="whitespace-nowrap">最多显示</span>
                  <input
                    type="number" min={1} max={50}
                    defaultValue={d.prefs.max_show}
                    onBlur={(e) => {
                      const v = Number(e.target.value)
                      if (v && v !== d.prefs.max_show) prefsMut.mutate({ max_show: v })
                    }}
                    className="w-14 rounded border border-border bg-surface px-2 py-1 font-mono text-foreground outline-none focus:border-sky-400/50"
                  />
                  <span>条</span>
                </label>
                <label className="flex items-center gap-2 text-[11px] text-muted" title="单只票最多占总资金的比例;建议仓位 = 上限 × 把握分系数 × 波动率压缩">
                  <span className="whitespace-nowrap">单票上限</span>
                  <input
                    type="number" min={5} max={100} step={5}
                    defaultValue={d.prefs.max_single}
                    onBlur={(e) => {
                      const v = Number(e.target.value)
                      if (v && v !== d.prefs.max_single) prefsMut.mutate({ max_single: v })
                    }}
                    className="w-14 rounded border border-border bg-surface px-2 py-1 font-mono text-foreground outline-none focus:border-sky-400/50"
                  />
                  <span>%</span>
                </label>
                <label className="flex items-center gap-2 text-[11px] text-muted" title="能接受的单日波动;票的日波幅(ATR/价)超过它时按比例压低建议仓位,只压不加">
                  <span className="whitespace-nowrap">目标日波动</span>
                  <input
                    type="number" min={1} max={10}
                    defaultValue={d.prefs.target_vol}
                    onBlur={(e) => {
                      const v = Number(e.target.value)
                      if (v && v !== d.prefs.target_vol) prefsMut.mutate({ target_vol: v })
                    }}
                    className="w-14 rounded border border-border bg-surface px-2 py-1 font-mono text-foreground outline-none focus:border-sky-400/50"
                  />
                  <span>%</span>
                </label>
                <label className="flex items-center gap-2 text-[11px] text-muted" title="组合净值从高点回撤超过此值 → 需要行动区置顶'纪律性降仓'提醒(需在决策台填各持仓的仓位%)">
                  <span className="whitespace-nowrap">回撤纪律线</span>
                  <input
                    type="number" min={3} max={30}
                    defaultValue={d.prefs.max_drawdown}
                    onBlur={(e) => {
                      const v = Number(e.target.value)
                      if (v && v !== d.prefs.max_drawdown) prefsMut.mutate({ max_drawdown: v })
                    }}
                    className="w-14 rounded border border-border bg-surface px-2 py-1 font-mono text-foreground outline-none focus:border-sky-400/50"
                  />
                  <span>%</span>
                </label>
                <label className="flex items-center gap-2 text-[11px] text-muted" title="建仓路径第一步: 试仓占目标仓位的比例(买'对不对')">
                  <span className="whitespace-nowrap">试仓</span>
                  <input
                    type="number" min={10} max={60} step={5}
                    defaultValue={d.prefs.pyramid_probe}
                    onBlur={(e) => {
                      const v = Number(e.target.value)
                      if (v && v !== d.prefs.pyramid_probe) prefsMut.mutate({ pyramid_probe: v })
                    }}
                    className="w-14 rounded border border-border bg-surface px-2 py-1 font-mono text-foreground outline-none focus:border-sky-400/50"
                  />
                  <span>%</span>
                </label>
                <label className="flex items-center gap-2 text-[11px] text-muted" title="建仓路径第二步: 站稳关键点 N 日后加至目标仓位的比例(买'稳不稳'), 第三步回踩不破上满">
                  <span className="whitespace-nowrap">确认加至</span>
                  <input
                    type="number" min={40} max={90} step={5}
                    defaultValue={d.prefs.pyramid_confirm}
                    onBlur={(e) => {
                      const v = Number(e.target.value)
                      if (v && v !== d.prefs.pyramid_confirm) prefsMut.mutate({ pyramid_confirm: v })
                    }}
                    className="w-14 rounded border border-border bg-surface px-2 py-1 font-mono text-foreground outline-none focus:border-sky-400/50"
                  />
                  <span>%</span>
                </label>
                <label className="flex items-center gap-2 text-[11px] text-muted" title="'站稳'的定义: 收盘连续 N 日守住关键点才执行加仓">
                  <span className="whitespace-nowrap">站稳</span>
                  <input
                    type="number" min={1} max={5}
                    defaultValue={d.prefs.pyramid_days}
                    onBlur={(e) => {
                      const v = Number(e.target.value)
                      if (v && v !== d.prefs.pyramid_days) prefsMut.mutate({ pyramid_days: v })
                    }}
                    className="w-14 rounded border border-border bg-surface px-2 py-1 font-mono text-foreground outline-none focus:border-sky-400/50"
                  />
                  <span>日</span>
                </label>
                <span className="text-[10px] text-muted/70">
                  把握分调高更严格;单票上限与目标日波动决定「建议仓位」;试仓/确认加至/站稳决定「建仓路径」。卖出提醒不受任何门槛影响。
                </span>
                {/* [R27] AI 定时自动运行 */}
                <div className="flex w-full flex-wrap items-center gap-x-5 gap-y-2 border-t border-border/40 pt-3">
                  <label className="flex items-center gap-2 text-[11px] text-muted" title="工作日到点自动生成导读·优选并存下来, 次日进页面直接看结果">
                    <input
                      type="checkbox"
                      checked={todayAiSched.data?.enabled ?? false}
                      onChange={(e) => todayAiSchedMut.mutate({
                        enabled: e.target.checked,
                        hour: todayAiSched.data?.hour ?? 18,
                        minute: todayAiSched.data?.minute ?? 30,
                      })}
                      className="h-3.5 w-3.5 accent-violet-500"
                    />
                    <span className="whitespace-nowrap">定时导读·优选</span>
                    <input
                      type="time"
                      value={`${String(todayAiSched.data?.hour ?? 18).padStart(2, '0')}:${String(todayAiSched.data?.minute ?? 30).padStart(2, '0')}`}
                      onChange={(e) => {
                        const [h, m] = e.target.value.split(':').map(Number)
                        if (!Number.isNaN(h)) todayAiSchedMut.mutate({
                          enabled: todayAiSched.data?.enabled ?? false, hour: h, minute: m,
                        })
                      }}
                      className="rounded border border-border bg-surface px-1.5 py-0.5 font-mono text-foreground outline-none focus:border-violet-400/50"
                    />
                  </label>
                  <label className="flex items-center gap-2 text-[11px] text-muted" title="工作日到点批量刷新个股 AI 信号; 每只之间留间隔, 不会打满接口">
                    <input
                      type="checkbox"
                      checked={signalAiSched.data?.enabled ?? false}
                      onChange={(e) => signalAiSchedMut.mutate({
                        ...(signalAiSched.data ?? { hour: 19, minute: 0, scope: 'held' as const, gap_seconds: 20 }),
                        enabled: e.target.checked,
                      })}
                      className="h-3.5 w-3.5 accent-violet-500"
                    />
                    <span className="whitespace-nowrap">定时个股信号</span>
                    <input
                      type="time"
                      value={`${String(signalAiSched.data?.hour ?? 19).padStart(2, '0')}:${String(signalAiSched.data?.minute ?? 0).padStart(2, '0')}`}
                      onChange={(e) => {
                        const [h, m] = e.target.value.split(':').map(Number)
                        if (!Number.isNaN(h) && signalAiSched.data) {
                          signalAiSchedMut.mutate({ ...signalAiSched.data, hour: h, minute: m })
                        }
                      }}
                      className="rounded border border-border bg-surface px-1.5 py-0.5 font-mono text-foreground outline-none focus:border-violet-400/50"
                    />
                    <select
                      value={signalAiSched.data?.scope ?? 'held'}
                      onChange={(e) => signalAiSched.data && signalAiSchedMut.mutate({
                        ...signalAiSched.data, scope: e.target.value as 'held' | 'watchlist',
                      })}
                      className="rounded border border-border bg-surface px-1.5 py-0.5 text-foreground outline-none focus:border-violet-400/50"
                    >
                      <option value="held">只跑持有</option>
                      <option value="watchlist">全部自选</option>
                    </select>
                    <span className="whitespace-nowrap">间隔</span>
                    <input
                      type="number" min={5} max={300}
                      value={signalAiSched.data?.gap_seconds ?? 20}
                      onChange={(e) => signalAiSched.data && signalAiSchedMut.mutate({
                        ...signalAiSched.data, gap_seconds: Number(e.target.value) || 20,
                      })}
                      className="w-14 rounded border border-border bg-surface px-1.5 py-0.5 font-mono text-foreground outline-none focus:border-violet-400/50"
                    />
                    <span>秒/只</span>
                  </label>
                  <span className="text-[10px] text-muted/70">
                    建议放在盘后日线落盘之后(17:30~20:00);个股多时用「只跑持有」更省
                  </span>
                </div>
                {prefsMut.isPending && <Loader2 className="h-3 w-3 animate-spin text-muted" />}
              </div>
            )}
            {shownPicks && (
              <AiPickPanel
                picks={shownPicks}
                analyzed={shownAnalyzed}
                opportunities={d.opportunities}
                onOpen={goStock}
              />
            )}
            {d.opportunities.length === 0 ? (
              <div className="px-4 py-5 text-xs text-muted">
                今日没有把握足够的买入机会 —— 等待比出手更常见
                {d.opportunities_filtered > 0 && `(有 ${d.opportunities_filtered} 只信号把握不足,已替你滤掉)`}
              </div>
            ) : (
              <OpportunityTable
                rows={d.opportunities}
                pickedSymbols={new Set((shownPicks ?? []).filter(p => p.verdict !== '驳回').map(p => p.symbol))}
                onOpen={goStock}
              />
            )}
          </section>

          {/* ① 行动区 */}
          <section className="rounded-lg border border-border/60 bg-surface/40 overflow-hidden">
            <div className="flex items-center gap-2 border-b border-border/40 px-4 py-2.5">
              <AlertTriangle className="h-4 w-4 text-red-400" />
              <span className="text-sm font-medium text-foreground">需要行动</span>
              <span className="text-[10px] text-muted">{d.actions.length} 项</span>
              <span
                title={d.live
                  ? '距离/价格按盘中最新价计算;"已跌破→清仓"的纪律判定仍以收盘为准'
                  : `所有距离/价格为 ${d.as_of ?? '上一交易日'} 收盘快照 —— 盘中已变化的不会反映,打开左下角「实时行情」后自动实时`}
                className={`rounded border px-1.5 py-0.5 text-[9px] ${d.live ? 'border-emerald-400/30 bg-emerald-400/10 text-emerald-400' : 'border-amber-400/30 bg-amber-400/10 text-amber-300'}`}
              >
                {d.live ? '实时口径' : `昨收快照 ${d.as_of ?? ''}`}
              </span>
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

          {/* ④ 持仓体检 */}
          <section className="rounded-lg border border-border/60 bg-surface/40 overflow-hidden">
            <div className="flex flex-wrap items-center gap-2 border-b border-border/40 px-4 py-2.5">
              <span className="text-sm font-medium text-foreground">持仓体检</span>
              <span className="text-[10px] text-muted">{d.holdings.length} 只(已触发/最接近出场线的排前面)</span>
              {d.portfolio && (
                <span className={`ml-auto text-[10px] ${d.portfolio.triggered > 0 ? 'text-red-400' : 'text-muted'}`}>
                  组合:平均浮盈{' '}
                  <span className={d.portfolio.avg_pnl == null ? '' : d.portfolio.avg_pnl > 0 ? 'text-red-400' : 'text-emerald-400'}>
                    {d.portfolio.avg_pnl != null ? `${(d.portfolio.avg_pnl * 100).toFixed(1)}%` : '—'}
                  </span>
                  {' '}· 已触发出场 {d.portfolio.triggered} · 逼近出场线 {d.portfolio.near_exit} · 空头趋势 {d.portfolio.bearish}
                  {d.portfolio.total_weight != null && (
                    <span title="由各持仓「仓位%」汇总;超过姿态基调或回撤超纪律线会进「需要行动」">
                      {' '}· 总仓位 {(d.portfolio.total_weight / 10).toFixed(1)}成
                      {d.portfolio.posture_cap != null && `(基调≤${d.portfolio.posture_cap * 10}成)`}
                      {d.portfolio.drawdown != null && ` · 距净值高点 -${(d.portfolio.drawdown * 100).toFixed(1)}%`}
                    </span>
                  )}
                </span>
              )}
            </div>
            {d.holdings.length === 0 ? (
              <div className="px-4 py-5 text-xs text-muted">
                暂无持仓标记 —— 在个股分析页决策台把持有的票标「持有」并填成本,这里就会出现仓位全景
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[720px] text-xs">
                  <thead className="text-[10px] text-muted">
                    <tr className="text-left">
                      <th className="px-4 py-1.5 font-normal">标的</th>
                      <th className="px-2 py-1.5 font-normal text-right">现价</th>
                      <th className="px-2 py-1.5 font-normal text-right">仓位</th>
                      <th className="px-2 py-1.5 font-normal text-right">浮盈</th>
                      <th className="px-2 py-1.5 font-normal text-right">出场线</th>
                      <th className="px-2 py-1.5 font-normal text-center">阶段</th>
                      <th className="px-2 py-1.5 font-normal text-center">趋势</th>
                      <th className="px-2 py-1.5 font-normal text-center">AI 信号</th>
                      <th className="px-4 py-1.5 font-normal text-center">操作建议</th>
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
                          <VerdictTag v={h.heat?.verdict} holding />
                        </td>
                        <td className="px-2 py-1.5 text-right font-mono">{h.close?.toFixed(2) ?? '—'}</td>
                        <td className="px-2 py-1.5 text-right font-mono text-muted" title="在决策台持有标记旁填「仓%」后显示">
                          {h.weight != null ? `${h.weight}%` : '—'}
                        </td>
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
                        <td className="px-2 py-1.5 text-center text-[10px] text-muted">{h.signal ?? '—'}</td>
                        <td className="px-4 py-1.5 text-center text-[10px]" title={h.stance_why}>
                          <span className={
                            h.stance === '离场' ? 'font-semibold text-red-400'
                              : h.stance === '减仓' ? 'text-amber-300'
                                : h.stance === '加仓' ? 'text-red-300'
                                  : 'text-muted'
                          }>
                            {h.stance}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </>
      )}
    </PageShell>
  )
}
