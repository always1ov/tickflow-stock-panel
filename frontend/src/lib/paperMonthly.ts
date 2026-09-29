/**
 * [fork R562] 虚拟账户逐月收益 —— 转折模拟盘那一排月度格子(R357)搬进虚拟账户, 所有账户都有。
 *
 * 口径与 R357 一字不差(后端 flip_portfolio._monthly):
 *   · 每个月单独算, 月与月之间不重叠: 这个月的收益 = 月末净值 / 上月末净值 - 1;
 *   · 基准取**上月最后一天**, 不是本月第一天 —— 否则那一天自己的涨跌被吃掉;
 *   · 第一个月没有上月, 基准是本金;
 *   · 首尾两个月一律标残月: 账户从月中开户、最后一个月还没走完, 结构上如此, 不去猜。
 *
 * 输入是作者按交易日定版的净值(nav/daily.jsonl), 不是回放。
 */
export interface MonthReturn {
  /** YYYY-MM */
  month: string
  /** 月末净值 */
  nav: number
  /** 这个月有几个交易日 */
  days: number
  ret: number
  partial: boolean
}

export function monthlyReturns(nav: readonly { date: string; nav: number }[], base: number): MonthReturn[] {
  const out: (MonthReturn & { base: number })[] = []
  let prev = base
  for (const row of nav) {
    const month = row.date.slice(0, 7)
    const last = out.at(-1)
    if (!last || last.month !== month) {
      out.push({ month, base: prev, nav: row.nav, days: 1, ret: 0, partial: false })
    } else {
      last.nav = row.nav
      last.days += 1
    }
    prev = row.nav
  }
  return out.map(({ base: b, ...m }, i) => ({
    ...m,
    ret: b ? m.nav / b - 1 : 0,
    partial: i === 0 || i === out.length - 1,
  }))
}
