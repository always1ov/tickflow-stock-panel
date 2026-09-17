import type { FlipOrder, FlipPaper } from './api'

/**
 * [R372] 本轮持有天数：成交当天算第 1 个交易日，清仓后重置。
 * 只读本次模拟盘的完整流水和净值日历，不拿设备日期补天数。
 * 这里的 sell 是模拟盘的整笔清仓，不用于其他模块的部分减仓。
 */
export function getFlipHoldingDays(
  orders: readonly Pick<FlipOrder, 'symbol' | 'date' | 'act'>[],
  nav: readonly Pick<FlipPaper['nav'][number], 'date'>[],
  asOf: FlipPaper['as_of'],
): Map<string, number> {
  const days = new Map<string, number>()
  if (!asOf) return days

  const calendar = [...new Set(nav.map((row) => row.date))]
    .filter((date) => date <= asOf).sort()
  // 日历缺失时显示缺数，而不是把自然日/工作日伪装成交易日。
  if (calendar.at(-1) !== asOf) return days
  const dayIndex = new Map(calendar.map((date, index) => [date, index]))
  const firstBuy = new Map<string, string>()

  // 不改变查询缓存中的流水顺序；同一轮内重复买入不重置起点。
  for (const order of [...orders].sort((a, b) => a.date.localeCompare(b.date))) {
    if (order.date > asOf) continue
    if (order.act === 'sell') firstBuy.delete(order.symbol)
    else if (order.act === 'buy' && !firstBuy.has(order.symbol)) {
      firstBuy.set(order.symbol, order.date)
    }
  }

  for (const [symbol, date] of firstBuy) {
    const start = dayIndex.get(date)
    if (start !== undefined) days.set(symbol, calendar.length - start)
  }
  return days
}
