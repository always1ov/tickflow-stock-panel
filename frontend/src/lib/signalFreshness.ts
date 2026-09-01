/**
 * [fork 增强] R131 AI 信号「要不要重算」的判据。
 *
 * 起因: 「AI 分析全部」每次点都把全部自选重跑一遍。70 只就是 70 次 AI 调用,
 * 而其中绝大多数当天已经分析过、输入数据一个字都没变 —— 纯烧钱。
 *
 * 关键认识: **该不该重算, 首先由数据决定, 不是由时间决定。**
 * 信号是拿日 K 算出来的。只要没有新的 K 线落盘, 再跑一遍喂给 AI 的还是同一份
 * 输入, 结论自然也差不多 —— 花的钱买不到新信息。所以主判据是:
 *
 *   信号是否**已经看过最新那根 K 线**?
 *
 * 怎么判: 拿信号的生成时刻与「数据基准日当天收盘」比。as_of 那根 K 线不可能
 * 在收盘前落盘, 所以生成于收盘之前的信号必定没见过它。这个近似是**保守**的
 * (收盘到实际落盘之间生成的信号会被多算一次), 方向刻意如此 —— 宁可多花一次
 * 调用, 也不能把没看过新数据的旧信号当成最新的摆在用户面前。
 *
 * 时间阈值只是安全阀: 长假期间数据连着几天不更新, 有它才不至于永远不重算,
 * 也给「换了 AI 档位想重跑」留个自然出口。单只想强制重算, 点行内那个 ✨ 即可,
 * 所以批量按钮做成纯增量, 不需要再加一个「强制全部」的控件。
 */

/** 信号年龄超过这个小时数就允许重算 —— 安全阀, 不是主判据 */
export const SIGNAL_TTL_HOURS = 24

/** A 股收盘(北京时间); as_of 那根日 K 不可能早于此刻落盘 */
const CLOSE_HOUR = 15

export interface FreshnessInput {
  /** 已有信号的生成时刻(ISO); 没有信号传 null/undefined */
  createdAt?: string | null
  /** 当前数据基准日 YYYY-MM-DD(enriched 的 as_of); 取不到传 null */
  asOf?: string | null
  now?: Date
  ttlHours?: number
}

/** 这只标的需不需要重新跑 AI 信号。 */
export function needsAnalysis({ createdAt, asOf, now, ttlHours = SIGNAL_TTL_HOURS }: FreshnessInput): boolean {
  if (!createdAt) return true                       // 从没分析过
  const created = new Date(createdAt)
  if (Number.isNaN(created.getTime())) return true  // 时间戳坏了, 按没分析过处理

  const ref = now ?? new Date()
  if ((ref.getTime() - created.getTime()) / 3_600_000 > ttlHours) return true

  if (asOf) {
    // as_of 当天 15:00 —— 早于它的信号必定没见过这根 K 线
    const [y, m, d] = asOf.split('-').map(Number)
    if (y && m && d) {
      const barLanded = new Date(y, m - 1, d, CLOSE_HOUR, 0, 0, 0)
      if (created.getTime() < barLanded.getTime()) return true
    }
  }
  return false
}

/** 从一批标的里挑出需要重算的。signals 取不到就是"没分析过"。 */
export function pickStale(
  symbols: string[],
  signals: Record<string, { created_at?: string } | undefined>,
  asOf: string | null | undefined,
  opts?: { now?: Date; ttlHours?: number },
): string[] {
  return symbols.filter(s => needsAnalysis({
    createdAt: signals[s]?.created_at,
    asOf,
    now: opts?.now,
    ttlHours: opts?.ttlHours,
  }))
}
