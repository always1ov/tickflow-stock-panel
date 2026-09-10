/**
 * [fork 增强 R273] 复盘状态时间轴的配色与格子构造 —— 三个页签共用。
 *
 * 单拎出来是因为**组合速查在另一个文件里**(`decision-board/ComboView.tsx`), 而它由
 * `StockReviewDialog` 引入; 把这些放在弹窗里再让 ComboView 反向 import 就成了循环。
 * 这里只有纯数据与纯函数, 谁 import 都不会成环。
 */
import type { TimelineCell } from '@/components/stock-analysis/StateTimeline'
import type { KeltnerVerdict, LivermoreState, ReviewRow } from '@/lib/api'

export const BAND_CN: Record<'s' | 'm' | 'l', string> = { s: '短期', m: '中期', l: '长期' }

/** 与决策台「结论」列同一套配色 —— 两处不一样的话, 翻历史时得在脑子里做一次换算。 */
export const VERDICT_BAR: Record<KeltnerVerdict['tone'], string> = {
  sell: 'bg-red-400',
  buy: 'bg-sky-400',
  hold: 'bg-amber-400',
  avoid: 'bg-border',
  watch: 'bg-secondary/60',
}

/**
 * [R273] 六态 → 时间轴上的实心底色。
 *
 * 徽标那套(`trendBadgeCls`)是**描边**样式, 铺不成色带。这里另给一套实心的, 但
 * **色相沿用同一条规矩**: A 股惯例多头红、空头绿; 六个态排成一条从最多头到最空头的
 * 梯子(UT → NR → SR | SREA → NREA → DT), 用同一色相的深浅表示"多头到什么程度"。
 * 六个各给一个独立颜色的话, 色带看起来就只是花的, 读不出方向。
 */
export const TREND_FILL: Record<LivermoreState, string> = {
  UT: 'bg-bull',
  NR: 'bg-bull/70',
  SR: 'bg-bull/40',
  SREA: 'bg-bear/40',
  NREA: 'bg-bear/70',
  DT: 'bg-bear',
}
export const TREND_LEGEND = [
  { cls: 'bg-bull', label: '上涨趋势' },
  { cls: 'bg-bull/70', label: '自然回升' },
  { cls: 'bg-bull/40', label: '次级回升' },
  { cls: 'bg-bear/40', label: '次级回撤' },
  { cls: 'bg-bear/70', label: '自然回撤' },
  { cls: 'bg-bear', label: '下跌趋势' },
]

/**
 * [R273] 三档位置 → 底色。偏贵一头红、通道内灰、偏便宜一头蓝 ——
 * 与决策台「结论」列的买卖配色同向, 免得同一件事在两处要在脑子里换算一次。
 */
export const POS_FILL: Record<string, string> = {
  above: 'bg-red-400',
  near_upper: 'bg-red-400/50',
  inside: 'bg-border',
  near_lower: 'bg-sky-400/50',
  below: 'bg-sky-400',
}
export const POS_LEGEND = [
  { cls: 'bg-red-400', label: '破上轨' },
  { cls: 'bg-red-400/50', label: '贴上轨' },
  { cls: 'bg-border', label: '通道内' },
  { cls: 'bg-sky-400/50', label: '贴下轨' },
  { cls: 'bg-sky-400', label: '破下轨' },
]

/** [R273] 通道结论色带的图例 —— 与 `VERDICT_BAR` 同一套色, 那是决策台「结论」列的配色。 */
export const VERDICT_LEGEND = [
  { cls: VERDICT_BAR.sell, label: '偏卖' },
  { cls: VERDICT_BAR.hold, label: '持有' },
  { cls: VERDICT_BAR.watch, label: '观察' },
  { cls: VERDICT_BAR.buy, label: '偏买' },
  { cls: VERDICT_BAR.avoid, label: '回避' },
]

/**
 * [R273] 时间轴用的格子。**必须按时间正序** —— 复盘接口的 `rows` 是新→旧(表格要把
 * 最近的排在最前), 直接铺出来时间轴就是倒着的, 而人读时间轴一律从左往右。
 */
export function chrono(rows: ReviewRow[]): ReviewRow[] {
  return [...rows].reverse()
}

export function trendCells(rows: ReviewRow[]): TimelineCell[] {
  return chrono(rows).map(r => ({
    key: r.date,
    cls: r.trend ? TREND_FILL[r.trend.state] : 'bg-border/40',
    title: r.trend
      ? `${r.date} ${r.trend.state_cn} 第 ${r.trend.day} 天${r.trend.flipped ? ' · 这天转折' : ''}`
      : `${r.date} 无状态`,
  }))
}

export function verdictCells(rows: ReviewRow[]): TimelineCell[] {
  return chrono(rows).map(r => ({
    key: r.date,
    cls: r.verdict ? VERDICT_BAR[r.verdict.tone] : 'bg-border/40',
    title: r.verdict ? `${r.date} ${r.verdict.title}` : `${r.date} 三档都在中部, 位置上没结论`,
  }))
}

export function bandCells(rows: ReviewRow[], k: 's' | 'm' | 'l'): TimelineCell[] {
  return chrono(rows).map(r => {
    const b = r.bands?.[k]
    return {
      key: r.date,
      cls: b ? (POS_FILL[b.pos] ?? 'bg-border/40') : 'bg-border/20',
      title: b ? `${r.date} ${BAND_CN[k]}${b.pos_cn}` : `${r.date} ${BAND_CN[k]}算不出来`,
    }
  })
}

export function rangeHint(rows: ReviewRow[]): string {
  const c = chrono(rows)
  return c.length ? `${c[0].date} → ${c[c.length - 1].date} · ${c.length} 天` : ''
}

