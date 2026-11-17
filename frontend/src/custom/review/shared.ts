/**
 * 复盘页共用的小工具 (R791 拆页时集中到一处, 原来散在 Page.tsx)。
 *
 * 口径提醒: overview 的 indices.change_pct / breadth.up_pct / seal_rate / *_pct /
 * emotion.score 都是【已是百分比值】(如 1.2 表示 1.2%), 直接 toFixed, 不要 *100。
 * 同一个读数只有一个产地 —— 涨跌配色 / 情绪配色都从这里出, 各组件不再各写一套。
 */

export function fmtPctAlready(v: number | null | undefined, digits = 2, withSign = false): string {
  if (v == null || Number.isNaN(v)) return '—'
  const sign = withSign && v > 0 ? '+' : ''
  return `${sign}${v.toFixed(digits)}%`
}

export function pctClass(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v) || v === 0) return 'text-muted'
  return v > 0 ? 'text-bull' : 'text-bear'
}

/** A 股惯例: 强势=红, 弱势=绿 (对齐 Dashboard scoreColor)。 */
export function scoreColor(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return '#71717A'
  if (v >= 70) return '#F04438'
  if (v >= 55) return '#FB923C'
  if (v >= 45) return '#F59E0B'
  if (v >= 30) return '#84CC16'
  return '#12B76A'
}

/** 归档时刻: ISO → "MM-DD HH:mm"。 */
export function fmtArchivedAt(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  const mm = String(d.getMonth() + 1).padStart(2, '0')
  const dd = String(d.getDate()).padStart(2, '0')
  const hh = String(d.getHours()).padStart(2, '0')
  const mi = String(d.getMinutes()).padStart(2, '0')
  return `${mm}-${dd} ${hh}:${mi}`
}

// 指数简称映射: 全称太长(上证指数/深证成指/创业板指/科创综指), 摘要条放不下
const INDEX_SHORT: Record<string, string> = {
  '上证指数': '上', '深证成指': '深', '创业板指': '创', '科创综指': '科', '科创50': '科',
}

export function indexShort(name?: string | null, symbol?: string): string {
  if (!name) return symbol ?? '—'
  return INDEX_SHORT[name] ?? (name.replace(/指数|成指|A股|综指|50/g, '').slice(0, 2) || name.slice(0, 1))
}

// 批量替换文本中的指数全称为简称(兼容存量旧报告 —— 它们存盘时 summary 还是全称)
const INDEX_FULL_RE = /上证指数|深证成指|创业板指|科创综指|科创50/g

export function shortenIndexNames(text: string): string {
  return text.replace(INDEX_FULL_RE, (m) => INDEX_SHORT[m] ?? m)
}

// 从 summary 的指数段(如「上-2.26%、深-3.44%、创-4.07%、科-2.02%」)
// 解析出 [{name, pctStr, pctNum}], 供档案带按涨跌染色渲染
const INDEX_PCT_RE = /([上深创科])([+-]?\d+\.\d+%)/g

export function parseIndexPcts(indexSegment: string): { name: string; pctStr: string; pctNum: number }[] {
  const out: { name: string; pctStr: string; pctNum: number }[] = []
  for (const m of indexSegment.matchAll(INDEX_PCT_RE)) {
    out.push({ name: m[1], pctStr: m[2], pctNum: parseFloat(m[2]) })
  }
  return out
}
