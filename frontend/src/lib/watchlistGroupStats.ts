/**
 * 自选分组涨跌幅 — 等权平均口径。
 *
 * 组内每只成员取「实时优先、收盘兜底」的涨跌幅(与自选表格展示同源:
 * rt_pct ?? change_pct, 小数单位), 算术平均即分组涨跌幅。等权最贴合
 * 自选的"个人组合"视角 — 透明且无需市值数据。
 */

import { fmtPct } from '@/lib/format'

export interface GroupPctInfo {
  /** 等权平均涨跌幅(小数, 0.0123 = +1.23%, 与 enriched change_pct 同单位); 无有效样本为 null */
  pct: number | null
  up: number
  down: number
  flat: number
  /** 参与统计的样本数(涨跌幅非空的成员) */
  sampled: number
  /** 中位数涨跌幅(小数); 无有效样本为 null */
  median: number | null
  /** 组内最大涨跌幅(小数); 无有效样本为 null */
  max: number | null
  /** 组内最小涨跌幅(小数); 无有效样本为 null */
  min: number | null
}

/** key: 'all' | 'ungrouped' | 分组 id */
export type GroupPctMap = Record<string, GroupPctInfo>

/**
 * 单只标的的展示涨跌幅: 实时优先、收盘兜底(与自选表格/卡片展示同源,
 * 小数单位), 无有效数据为 null。分组统计与分组卡片排序共用此口径。
 */
export function rowPct(
  row: { rt_pct?: number | null; change_pct?: number | null } | undefined,
): number | null {
  const pct = row ? row.rt_pct ?? row.change_pct : null
  return pct == null || !Number.isFinite(pct) ? null : pct
}

export function computeGroupPcts(
  entries: { symbol: string; group_ids?: string[] | null }[],
  rowsBySymbol: Map<string, { rt_pct?: number | null; change_pct?: number | null }>,
): GroupPctMap {
  const buckets = new Map<string, { pcts: number[]; up: number; down: number; flat: number }>()
  const add = (key: string, pct: number | null | undefined) => {
    if (pct == null || !Number.isFinite(pct)) return
    const b = buckets.get(key) ?? { pcts: [], up: 0, down: 0, flat: 0 }
    b.pcts.push(pct)
    if (pct > 0) b.up++
    else if (pct < 0) b.down++
    else b.flat++
    buckets.set(key, b)
  }
  for (const entry of entries) {
    const row = rowsBySymbol.get(entry.symbol)
    const pct = rowPct(row)
    add('all', pct)
    // 多组并存: 一股计入每个所属分组; 不属于任何分组才计未分组
    const gids = entry.group_ids ?? []
    if (gids.length === 0) add('ungrouped', pct)
    else for (const gid of gids) add(gid, pct)
  }
  const out: GroupPctMap = {}
  for (const [key, b] of buckets) {
    const sortedPcts = [...b.pcts].sort((a, c) => a - c)
    const mid = Math.floor(sortedPcts.length / 2)
    const median = sortedPcts.length === 0
      ? null
      : sortedPcts.length % 2 === 1
        ? sortedPcts[mid]
        : (sortedPcts[mid - 1] + sortedPcts[mid]) / 2
    out[key] = {
      pct: b.pcts.length ? b.pcts.reduce((a, c) => a + c, 0) / b.pcts.length : null,
      up: b.up,
      down: b.down,
      flat: b.flat,
      sampled: b.pcts.length,
      median,
      max: sortedPcts.length ? sortedPcts[sortedPcts.length - 1] : null,
      min: sortedPcts.length ? sortedPcts[0] : null,
    }
  }
  return out
}

/** 涨跌色 (A 股惯例红涨绿跌) */
export function groupPctColor(pct: number | null): string {
  if (pct == null || pct === 0) return 'text-muted'
  return pct > 0 ? 'text-bull' : 'text-bear'
}

// ===== 分组统计条指标契约 =====

/** 分组统计指标: 等权平均 / 中位数 / 上涨占比(以50%为轴) / 组内最强 / 组内最弱 */
// [R508] 「指标 / 排序 / 卡片显示项」那套配置(GROUP_METRICS / sortGroupKeys / loadGroupStatsConfig …)
// 随分组统计条与分组卡片一起撤了; 留下的是分组条、侧栏、小分队网格三处共用的等权涨跌口径。

export function groupPctTitle(info: GroupPctInfo | undefined): string {
  if (!info || info.pct == null) return '暂无涨跌幅数据'
  return `等权平均 ${fmtPct(info.pct)} · 上涨${info.up} 下跌${info.down} 平${info.flat} (共${info.sampled}只)`
}
