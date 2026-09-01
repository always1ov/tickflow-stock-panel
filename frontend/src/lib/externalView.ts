/**
 * [fork 增强] R117 外部网页「抓取模式」的固定数据契约(前端侧类型 + 展示口径)。
 *
 * 链路: 后端抓原文 → 面板自己的 AI 按固定提示词整理成 JSON → 后端
 * `external_view.normalize_spec` 收敛(字段/类型/上限都在那儿定死) → 这里只
 * 负责**怎么显示**。归一化不在前端做, 所以这个文件没有校验逻辑。
 */

export type ExtTone = 'up' | 'down' | 'flat' | 'plain' | 'delta'

export interface ExtStat {
  label: string
  value: string
  hint?: string | null
  tone: ExtTone
}

export interface ExtColumn {
  key: string
  label: string
  align: 'left' | 'right' | 'center'
  /** delta = 按正负染红绿并补 + 号; 其余按 tone 直接染色 */
  tone: ExtTone
  unit?: string | null
}

export interface ExtSection {
  title?: string | null
  note?: string | null
  columns: ExtColumn[]
  rows: Record<string, unknown>[]
}

export interface ExtSpec {
  title?: string | null
  subtitle?: string | null
  updated_at?: string | null
  stats: ExtStat[]
  sections: ExtSection[]
  notes: string[]
}

/** 表格单元格取值 → 展示文本(数值保留至多 4 位小数并去掉尾零)。 */
export function formatCell(value: unknown, col: ExtColumn): string {
  if (value === null || value === undefined || value === '') return '—'
  let text: string
  if (typeof value === 'number' && Number.isFinite(value)) {
    text = Number.isInteger(value) ? String(value) : String(Number(value.toFixed(4)))
    if (col.tone === 'delta' && value > 0) text = `+${text}`
  } else if (typeof value === 'object') {
    text = JSON.stringify(value)
  } else {
    text = String(value)
  }
  return col.unit ? `${text}${col.unit}` : text
}

/** 配色 —— delta 按正负染, 其余按自身 tone。A 股口径: 红涨绿跌。 */
export function cellToneClass(value: unknown, tone: ExtTone): string {
  if (tone === 'delta') {
    const n = typeof value === 'number' ? value : Number(String(value).replace(/[+%,\s]/g, ''))
    if (!Number.isFinite(n) || n === 0) return 'text-secondary'
    return n > 0 ? 'text-danger' : 'text-success'
  }
  if (tone === 'up') return 'text-danger'
  if (tone === 'down') return 'text-success'
  if (tone === 'flat') return 'text-muted'
  return 'text-secondary'
}
