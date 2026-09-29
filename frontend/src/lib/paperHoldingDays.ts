/**
 * [fork R562] 虚拟账户持有天数 —— 转折模拟盘那一列(R372)搬进虚拟账户, 所有账户都有。
 *
 * 口径沿用 R372: 这一轮建仓那天算第 1 个交易日, 清仓后重置; 天数只按**净值日历**
 * (作者每个交易日盘后定版的那一行)数, 不拿设备日期补 —— 日历里找不到建仓那天
 * (当天刚成交、还没结算定版)就缺数, 不把自然日伪装成交易日。
 *
 * 与 R372 的差别只在「清仓」怎么认: 模拟盘每次卖出都是整笔清仓, 虚拟账户可以手动
 * 部分减仓 —— 所以这里逐笔累计股数, **归零**才算清仓; 加仓、减仓都不重置起点。
 */
export interface HoldingFill {
  symbol: string
  date: string
  side: string
  qty?: number | null
  kind?: string | null
}

export function paperHoldingDays(fills: readonly HoldingFill[], navDates: readonly string[]): Map<string, number> {
  const days = new Map<string, number>()
  const calendar = [...new Set(navDates)].sort()
  if (!calendar.length) return days
  const dayIndex = new Map(calendar.map((d, i) => [d, i]))

  const qty = new Map<string, number>()
  const start = new Map<string, string>()
  // 台账按追加顺序给; 按日期稳定排一次, 不改调用方的数组
  for (const f of [...fills].sort((a, b) => a.date.localeCompare(b.date))) {
    if (f.kind === 'corp_action' || (f.side !== 'buy' && f.side !== 'sell')) continue
    const before = qty.get(f.symbol) ?? 0
    const after = before + (f.side === 'buy' ? 1 : -1) * (f.qty ?? 0)
    if (before <= 0 && after > 0) start.set(f.symbol, f.date)
    if (after <= 0) start.delete(f.symbol)
    qty.set(f.symbol, Math.max(0, after))
  }
  for (const [symbol, date] of start) {
    const i = dayIndex.get(date)
    if (i !== undefined) days.set(symbol, calendar.length - i)
  }
  return days
}
