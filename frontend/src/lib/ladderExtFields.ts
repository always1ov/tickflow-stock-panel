/**
 * [R50] 连板梯队的 ext 字段配置与取值。
 *
 * 原本这几个函数长在 `pages/LimitUpLadder.tsx` 里 —— 那时只有梯队页用得到。
 * 「AI 打板复盘」搬到复盘页之后, 两个页面都要按同一份配置去读题材/行业:
 * 各写一份的话, 梯队页显示的题材和喂给 AI 的题材迟早对不上, 而那正是这份
 * 清单的判断依据。
 *
 * 配置本身存在 localStorage(用户在梯队页的「字段配置」里设的), 两边共读一份。
 */
import { storage } from '@/lib/storage'
import type { LimitLadderStock } from '@/lib/api'
import type { ExtColumnDisplayConfig } from '@/lib/watchlist-columns'

/** 每个字段的完整配置：字段来源 + 渲染方式 */
export interface ExtFieldItem {
  /** "config_id.field_name"，空=不显示 */
  field?: string
  /** 渲染配置（分隔符、显示模式、maxTags 等） */
  display?: ExtColumnDisplayConfig
}

export interface BrokenFailedConfig {
  /** 炸板：计算N板以上（0=不限，即首板炸板也算） */
  brokenMinBoards?: number
  /** 断板：计算N板以上 */
  failedMinBoards?: number
  /** 是否计算炸板数 */
  brokenCount?: boolean
  /** 是否计算断板数 */
  failedCount?: boolean
  /** 是否显示炸板股票 */
  brokenShow?: boolean
  /** 是否显示断板股票 */
  failedShow?: boolean
}

export interface ExtFieldConfig {
  concept?: ExtFieldItem
  industry?: ExtFieldItem
  /** 炸板/断板过滤配置 */
  bf?: BrokenFailedConfig
  /** 显示概念分布统计 */
  showConceptStats?: boolean
  /** 显示行业分布统计 */
  showIndustryStats?: boolean
  /** 显示分组概念分布统计 */
  showConceptGroupStats?: boolean
  /** 显示分组行业分布统计 */
  showIndustryGroupStats?: boolean
}

export const DEFAULT_BF: BrokenFailedConfig = {
  brokenMinBoards: 0,
  failedMinBoards: 0,
  brokenCount: true,
  failedCount: true,
  brokenShow: true,
  failedShow: true,
}

export function loadExtFields(): ExtFieldConfig {
  const raw = storage.limitLadderExtFields.get({}) as any
  if (!raw) return {}
  // 兼容旧格式 { concept: "id.field", conceptSep: "x" }
  if (typeof raw.concept === 'string') {
    return {
      concept: raw.concept ? { field: raw.concept, display: { displayMode: 'tag', separator: raw.conceptSep } } : undefined,
      industry: raw.industry ? { field: raw.industry, display: { displayMode: 'tag', separator: raw.industrySep } } : undefined,
    }
  }
  return raw
}

/** 根据显示开关过滤 extFields */
export function resolveExtFields(fields: ExtFieldConfig, showConcept: boolean, showIndustry: boolean): ExtFieldConfig {
  return {
    concept: showConcept ? fields.concept : undefined,
    industry: showIndustry ? fields.industry : undefined,
    showConceptGroupStats: fields.showConceptGroupStats,
    showIndustryGroupStats: fields.showIndustryGroupStats,
  }
}

export function buildExtColumnsParam(fields: ExtFieldConfig): string | undefined {
  const parts = [fields.concept?.field, fields.industry?.field].filter(Boolean)
  return parts.length > 0 ? parts.join(',') : undefined
}

/** 从 stock row 中取出 ext 字段值，按配置渲染 */
export function getExtTags(stock: LimitLadderStock, item?: ExtFieldItem): string[] {
  if (!item?.field) return []
  const key = item.field.replace('.', '__')
  const v = (stock as unknown as Record<string, unknown>)[key]
  if (v == null) return []
  const str = String(v)
  if (!str) return []

  const cfg = item.display
  if (cfg?.displayMode === 'text') return [str]

  const sep = cfg?.separator?.trim() || null
  const tags = sep
    ? str.split(sep).map(s => s.trim()).filter(Boolean)
    : str.split(/[、,，;；\-]/).map(s => s.trim()).filter(Boolean)

  const maxTags = cfg?.maxTags ?? 0
  const sliced = maxTags > 0 ? tags.slice(0, maxTags) : tags
  const hiddenIndices = maxTags > 0 ? cfg?.hiddenIndices : undefined
  return hiddenIndices?.length
    ? sliced.filter((_, i) => !hiddenIndices.includes(i))
    : sliced
}
