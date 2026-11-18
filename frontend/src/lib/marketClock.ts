/**
 * [R319] A 股市场时钟 —— **一处产地**。
 *
 * 「现在是盘前 / 盘中 / 盘后 / 休市」这个判断原来写在 `MarketStatusCard` 里,
 * 今日总览要按它决定刷新节奏(盘中开着实时时 60 秒一刷, 否则每小时), 第二个
 * 消费方一出现就得把它抽出来 —— 两处各写一份 `new Date().toLocaleString(…)`,
 * 哪天一处改了边界另一处不跟, 卡片说「盘中」而页面按盘后节奏刷, 没有任何
 * 东西会报错。
 *
 * 只用浏览器时钟, 不打接口: 这是前端节奏与提示语的依据, 不是交易日判定
 * (节假日在这里仍显示为工作日 —— 交易日探针在后端, 见 `trading_day.py`)。
 */

export type CnMarketPhase = 'weekend' | 'pre' | 'open' | 'post'

/** 北京时间的「周几」与「当天第几分钟」—— 两个原始读数, 其余都从它们推。 */
export function cnClock(now: Date = new Date()): { day: number; mins: number } {
  const bj = new Date(now.toLocaleString('en-US', { timeZone: 'Asia/Shanghai' }))
  return { day: bj.getDay(), mins: bj.getHours() * 60 + bj.getMinutes() }
}

/**
 * 北京时间的日期字符串 `YYYY-MM-DD`。
 *
 * [R814] 从 `lib/marketSession.ts` 收进来的: 那个文件自己又写了一份
 * `Intl.DateTimeFormat(timeZone: 'Asia/Shanghai')`, 于是全仓有了第二个换时区的
 * 产地(R319 要拦的就是这个)。日期与分钟数现在同出 `marketClock` 一处。
 */
export function cnDate(now: Date = new Date()): string {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric', month: '2-digit', day: '2-digit',
  }).formatToParts(now)
  const get = (type: string) => parts.find(p => p.type === type)?.value ?? ''
  return `${get('year')}-${get('month')}-${get('day')}`
}

/** 展示用时段: 与 `MarketStatusCard` 的提示语同一套边界(09:30 / 15:00)。 */export function cnMarketPhase(now: Date = new Date()): CnMarketPhase {
  const { day, mins } = cnClock(now)
  if (day === 0 || day === 6) return 'weekend'
  if (mins < 9 * 60 + 30) return 'pre'
  if (mins < 15 * 60) return 'open'
  return 'post'
}

/**
 * 实时行情**可能在跑**的窗口: 工作日 09:15 ~ 15:05。
 *
 * 边界照抄后端 `realtime_schedule.py`(09:15 集合竞价开始拉, 15:05 收盘后留
 * 5 分钟给收盘定版)—— 今日总览的盘中刷新节奏跟着这个窗口走, 而不是跟着
 * 09:30~15:00 的展示时段: 竞价与收盘定版那几分钟正是数字在变的时候。
 */
export function inRealtimeWindow(now: Date = new Date()): boolean {
  const { day, mins } = cnClock(now)
  if (day === 0 || day === 6) return false
  return mins >= 9 * 60 + 15 && mins <= 15 * 60 + 5
}
